"""Read the Following tab newest first, from the last post the previous run reached.

One run: load x.com/home once (the fork computes the anti-bot id from it, and its HTML says which site build
this account gets), find that build's Following-tab request, then read page after page with reading-like
pauses on one connection until the page reaches the previous run's newest post. Anything X pushes back with
(a rate limit, a challenge, a logout, an error) ends the run at once; nothing is retried. What was read is
saved raw, one file a run, and the brief says how the run ended.
"""

from __future__ import annotations

import asyncio
import json
import math
import random
import time
from dataclasses import dataclass, field

from . import config, parse, request, site

Sleep = asyncio.sleep


@dataclass
class Result:
    started_ms: int
    finished_ms: int = 0
    stop: str = ""  # how the run ended, in words
    normal: bool = False  # ended by catching up (or reaching the end of a first read)
    gap: bool = False  # stopped before reaching the previous run's newest post
    boundary_id: int = 0
    newest_id: int = 0
    pages: list[dict] = field(default_factory=list)
    build: str = ""
    reread_site: bool = False

    def meta(self) -> dict:
        d = {k: v for k, v in self.__dict__.items() if k != "pages"}
        d["page_count"] = len(self.pages)
        return d


# ── state ───────────────────────────────────────────────────────────────────────────────────────────


def load_state() -> dict:
    try:
        return json.loads(config.STATE.read_text())
    except (OSError, ValueError):
        return {}


def save_state(state: dict) -> None:
    tmp = config.STATE.with_suffix(".part")
    tmp.write_text(json.dumps(state, indent=1, sort_keys=True))
    tmp.replace(config.STATE)


# ── pacing ──────────────────────────────────────────────────────────────────────────────────────────


def reading_pause(rng: random.Random) -> float:
    """Seconds between pages: mostly a few seconds, now and then much longer, never the same twice."""
    s = rng.lognormvariate(math.log(6.0), 0.55)
    while not 2.0 <= s <= 25.0:  # redraw, never clamp: a clamp piles pauses onto one exact value
        s = rng.lognormvariate(math.log(6.0), 0.55)
    if rng.random() < 0.10:
        s += rng.uniform(20.0, 90.0)
    return s


def seen_split(ids: list[str], carried: list[str]) -> tuple[list[str], list[str]]:
    """(ids reported as seen with the next page, ids still below the fold). The next page loads as the
    reader nears the bottom, so the last few posts of a page have not been on screen yet."""
    on_screen = carried + ids[:-3] if len(ids) > 3 else carried
    return on_screen, ids[-3:] if len(ids) > 3 else ids


# ── the run ─────────────────────────────────────────────────────────────────────────────────────────


async def fetch_script(url: str) -> str:
    """A script file from X's CDN, as the page's own <script type=module> fetch: no cookies (another site)."""
    from curl_cffi.requests import AsyncSession
    from twscrape.http import order_xhr_headers

    headers = order_xhr_headers(
        {"origin": "https://x.com", "referer": "https://x.com/", "sec-fetch-site": "cross-site",
         "sec-fetch-dest": "script", "priority": "u=1"}
    )
    async with AsyncSession(impersonate="chrome150") as s:
        rep = await s.get(url, headers=headers, default_headers=False)
        if rep.status_code != 200:
            raise site.SiteError(f"script {url.rsplit('/', 1)[-1]}: HTTP {rep.status_code}")
        return rep.text


async def _explain_no_account(pool) -> str:
    accs = await pool.get_all()
    if not accs:
        return "no login: the operator runs xbrief/bin/xbrief login"
    a = accs[0]
    if not a.active:
        return f"X ended the session or blocked the account ({a.error_msg or 'no reason given'})"
    if a.locks:
        until = max(a.locks.values())
        return f"X rate-limited the account until {until.astimezone().strftime('%H:%M')}"
    return "the account was unavailable"


async def run(rng: random.Random | None = None, sleep=None, now_ms: int | None = None, api=None, get_script=None) -> Result:
    config.apply_job_env()
    rng = rng or random.Random()
    sleep = sleep or Sleep
    get_script = get_script or fetch_script
    now_ms = now_ms or int(time.time() * 1000)
    res = Result(started_ms=now_ms)

    state = load_state()
    first = not state.get("newest_id")
    res.boundary_id = int(state.get("newest_id") or parse.ms_to_snowflake(now_ms - config.FIRST_RUN_HOURS * 3_600_000))

    from twscrape import API
    from twscrape.accounts_pool import NoAccountError
    from twscrape.queue_client import XClIdGenStore

    if api is None and not config.ACCOUNTS_DB.exists():  # never create the login file outside `xbrief login`
        res.stop = "no login: the operator runs xbrief/bin/xbrief login"
        return _done(res)
    api = api or API(pool=str(config.ACCOUNTS_DB), raise_when_no_account=True)
    try:
        accs = await api.pool.get_all()
        if not accs:
            res.stop = "no login: the operator runs xbrief/bin/xbrief login"
            return _done(res)
        acc = accs[0]
        if not acc.active:
            res.stop = await _explain_no_account(api.pool)
            return _done(res)

        gen = await XClIdGenStore.get(acc.username, cookies=acc.cookies)
        op, res.reread_site = await site.resolve(gen.page_html or "", get_script)
        res.build = op.build

        cursor, carried, newest = None, [], 0
        async with api.raw_session(op.name) as s:
            for n in range(config.MAX_PAGES):
                if n:
                    await sleep(reading_pause(rng))
                seen = None
                if n:
                    seen, carried = seen_split(last_ids, carried)
                req = request.build(op, config.PAGE_SIZE, cursor, seen)
                rep = await s.req(req.method, req.url, params=req.params, headers=req.headers, json=req.body)
                if rep is None:
                    res.stop = "X refused the request (blocked or challenged); see logs/run.log"
                    break
                page = rep.json()
                res.pages.append(page)
                if not parse.timeline(page):
                    errs = "; ".join(str(e.get("message", e)) for e in (page.get("errors") or []))[:300]
                    res.stop = f"X answered without a feed ({errs or 'no errors given'})"
                    if any(w in errs.lower() for w in ("persisted", "not found", "feature", "query")):
                        config.SITE.unlink(missing_ok=True)  # read the site again next run
                    break
                ents, cursor = parse.entries(page)
                real = [e for e in ents if not e.promoted]
                newest = max([newest] + [e.newest_id for e in real])
                if any(0 < e.newest_id <= res.boundary_id for e in real):
                    res.stop, res.normal = ("read back to the start of the window" if first else "caught up"), True
                    break
                if not cursor or not real:
                    res.stop = "reached the end of what X serves"
                    res.gap = not first
                    res.normal = first
                    break
                last_ids = [p.id for e in real for p in e.posts]
            else:
                res.stop = f"stopped at the cap of {config.MAX_PAGES} pages"
                res.gap = True
        res.newest_id = newest
    except NoAccountError:
        res.stop = await _explain_no_account(api.pool)
    except site.LoggedOut as e:
        res.stop = str(e)
    except Exception as e:  # anything else ends the run, says what it was, and is never retried
        hint = " (x.com/home did not load as a logged-in page)" if type(e).__name__.startswith("XClId") else ""
        res.stop = f"{type(e).__name__}: {e}"[:400] + hint
    return _done(res)


def _done(res: Result) -> Result:
    res.finished_ms = int(time.time() * 1000)
    if res.pages and res.newest_id > res.boundary_id:
        st = load_state()
        st.update(newest_id=res.newest_id, last_read_ms=res.finished_ms)
        save_state(st)
    return res


def save_raw(res: Result, label: str) -> str:
    config.RAW.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y-%m-%d_%H%M", time.localtime(res.started_ms / 1000))
    path = config.RAW / f"{stamp}-{label}.json"
    tmp = path.with_suffix(".part")
    tmp.write_text(json.dumps({"meta": res.meta(), "pages": res.pages}))
    tmp.replace(path)
    return str(path)


def prune_raw(now_ms: int | None = None) -> int:
    cutoff = (now_ms or int(time.time() * 1000)) / 1000 - config.RAW_KEEP_DAYS * 86400
    n = 0
    for p in config.RAW.glob("*.json"):
        if p.stat().st_mtime < cutoff:
            p.unlink()
            n += 1
    return n
