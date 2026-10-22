"""Read the Following tab newest first, from the last post the previous run reached, in the operator's own Brave.

One run: Brave opens x.com/home on the job's profile (hidden, never in front), the Following tab is clicked unless
X already shows it, and the page is scrolled with the mouse wheel at a reading pace. The feed pages x.com itself
downloads are kept, until one reaches the previous run's newest post, the feed stops, or a cap. Anything X pushes back
with (an error status, a login or challenge page, a feed that stops loading) ends the run at once and nothing is
retried. What was read is saved raw, one file a run, and the brief says how the run ended.
"""

from __future__ import annotations

import asyncio
import json
import math
import pathlib
import random
import re
import time
from dataclasses import dataclass, field

from . import config, parse

TIMELINE = re.compile(r"/graphql/[\w-]+/HomeLatestTimeline(?:Query)?(?:[?#]|$)")
# logged out (the landing page, a login flow) or held up (a lock, a challenge)
# Paths of the main page. Logged out (the landing page, a login flow) or held up (a lock, a challenge):
BLOCKED = re.compile(r"^/(?:$|i/flow/|(?:login|logout)(?:[/?#]|$)|account/access)", re.I)
UPSELL = re.compile(r"^/i/premium_sign_up", re.I)  # an offer a person closes with Escape
# what a post's own page fetches; an Article's whole body comes in the first (2026-10-15), embedded posts in the second
ARTICLE_API = re.compile(r"/graphql/[\w-]+/(?:TweetResultByRestId|TweetResultsByRestIds|TweetDetail)(?:Query)?(?:[?#]|$)")
ARTICLE_WAIT_S = 20


def path_of(url: str) -> str:
    from urllib.parse import urlparse

    return urlparse(url).path or "/"
FOLLOWING_TAB = ["//a[@role='tab'][.//span[text()='Following']]", "(//*[@role='tablist']//*[@role='tab'])[2]"]
# Clicking the selected Following tab opens its sort menu: Recent (newest first) or Popular (ranked).
RECENT_ITEM = ["//*[@role='menuitem'][.//span[text()='Recent']]", "//*[@role='menu']//*[@role='menuitem'][1]"]
LOAD_WAIT_S = 30
FIRST_PAGE_WAIT_S = 20
STALL_WHEELS = 15  # wheel turns at the end of the page without a new feed page before the feed counts as stopped
                   # (X's first Recent page holds ~100 posts: turns are only counted once the page's end is near)


@dataclass
class Result:
    started_ms: int
    finished_ms: int = 0
    stop: str = ""
    normal: bool = False
    gap: bool = False
    boundary_id: int = 0
    newest_id: int = 0
    pages: list[dict] = field(default_factory=list)
    build: str = ""  # "legacy" (x.com/i/api) or "xweb" (api.x.com), read off the feed request the page made
    ranked: bool = False  # the Following tab is sorted by Popular (enableRanking), not Recent
    reread_site: bool = False
    articles: dict[str, list[dict]] = field(default_factory=dict)  # post id → what its own page fetched
    articles_read: int = 0  # Articles read whole
    articles_left: int = 0  # Articles past config.MAX_ARTICLES, left at their opening

    def meta(self) -> dict:
        d = {k: v for k, v in self.__dict__.items() if k not in ("pages", "articles")}
        d["page_count"] = len(self.pages)
        return d


class Stop(Exception):
    def __init__(self, why: str, normal: bool = False, gap: bool = False):
        super().__init__(why)
        self.why, self.normal, self.gap = why, normal, gap


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


def wheel_pause(rng: random.Random) -> float:
    """Seconds between wheel turns: mostly about a second, now and then a long stop to read. Redrawn, never
    clamped, so no value piles up."""
    s = rng.lognormvariate(math.log(1.3), 0.6)
    while not 0.35 <= s <= 7.0:
        s = rng.lognormvariate(math.log(1.3), 0.6)
    if rng.random() < 0.04:
        s += rng.uniform(8.0, 45.0)
    return s


def wheel_delta(rng: random.Random) -> float:
    if rng.random() < 0.05:
        return -rng.uniform(120, 400)  # a glance back up
    return rng.uniform(240, 880)


# ── the feed, as the page downloads it ──────────────────────────────────────────────────────────────


class Feed:
    def __init__(self, browser, progress=None):
        self.b = browser
        self.progress = progress or (lambda phase, **kw: None)  # tells the page what the run is doing
        self.tracked: dict[str, str] = {}  # requestId → url
        self.pages: list[dict] = []
        self.urls: list[str] = []
        self.loaded = False
        self.problem: str | None = None
        self.main_url = ""
        self.main_frame: str | None = None
        self.ranked: bool | None = None  # from the feed request's own variables; None until one is seen
        self.feed_done = False  # the feed is read: its requests still in flight are cut off by leaving the tab
        self.article_for: str | None = None  # the post whose page is open, while Articles are read
        self.art_tracked: dict[str, str] = {}  # requestId → that post's id
        self.article_pages: dict[str, list[dict]] = {}

    async def pump(self, seconds: float) -> None:
        """Handle the browser's events for `seconds` (or until the page has a problem)."""
        end = time.monotonic() + seconds
        drained = False
        while not self.problem:
            if not self.b.events.empty() and not drained:  # what has already arrived is always handled
                ev = self.b.events.get_nowait()
            else:
                left = end - time.monotonic()
                if left <= 0:
                    return
                drained = True  # from here the deadline rules, however fast events keep coming (a video's chunks)
                try:
                    ev = await asyncio.wait_for(self.b.events.get(), left)
                except asyncio.TimeoutError:
                    return
            await self.handle(ev)

    async def handle(self, ev: dict) -> None:
        m, p = ev.get("method"), ev.get("params") or {}
        if self.feed_done and (p.get("requestId") in self.tracked or TIMELINE.search((p.get("request") or {}).get("url", ""))):
            self.tracked.pop(p.get("requestId"), None)  # the browser's doing, not X's
            return
        if m == "Network.requestWillBeSent":
            url = (p.get("request") or {}).get("url", "")
            if TIMELINE.search(url):
                self.tracked[p["requestId"]] = url
                self.ranked = bool(self.ranked) or ranking_of(p.get("request") or {})
            elif self.article_for and ARTICLE_API.search(url):
                self.art_tracked[p["requestId"]] = self.article_for
        elif p.get("requestId") in self.art_tracked:
            await self._article_event(m, p)
        elif m == "Network.responseReceived" and p.get("requestId") in self.tracked:
            status = (p.get("response") or {}).get("status", 0)
            if status != 200:
                self.problem = f"X answered the feed request with HTTP {status}" + (" (rate limited)" if status == 429 else "")
        elif m == "Network.loadingFinished" and p.get("requestId") in self.tracked:
            rid = p["requestId"]
            url = self.tracked.pop(rid)
            body = await self.b.send("Network.getResponseBody", {"requestId": rid})
            text = body.get("body") or ""
            if body.get("base64Encoded"):
                import base64

                text = base64.b64decode(text).decode("utf-8", "replace")
            try:
                page = json.loads(text)
            except ValueError:
                self.problem = "X answered the feed request with something other than JSON"
                return
            if not parse.timeline(page):
                errs = "; ".join(str(e.get("message", e)) for e in (page.get("errors") or []))[:300]
                self.problem = f"X answered without a feed ({errs or 'no errors given'})"
                return
            self.pages.append(page)
            self.urls.append(url)
            # counted over the pages kept, so the Popular pages dropped on switching to Recent drop out too
            posts = sum(len(e.posts) for pg in self.pages for e in parse.entries(pg)[0] if not e.promoted)
            self.progress("reading", pages=len(self.pages), posts=posts)
        elif m == "Network.loadingFailed" and p.get("requestId") in self.tracked:
            self.problem = f"the feed request failed ({p.get('errorText', 'no reason given')})"
        elif m == "Page.frameNavigated" and not (p.get("frame") or {}).get("parentId"):
            self.main_frame = p["frame"].get("id")
            self._at(p["frame"].get("url", ""))
        elif m == "Page.navigatedWithinDocument" and p.get("frameId") == self.main_frame:
            self._at(p.get("url", ""))
        elif m == "Page.loadEventFired":
            self.loaded = True
        elif m == "xbrief.closed":
            self.problem = f"the browser closed ({p.get('error', '')})"[:200]


    async def _article_event(self, m: str, p: dict) -> None:
        """A post's own page, open to read its Article: X pushing back here ends the run like on the feed."""
        if m == "Network.responseReceived":
            status = (p.get("response") or {}).get("status", 0)
            if status != 200:
                self.problem = f"X answered a post's page with HTTP {status}" + (" (rate limited)" if status == 429 else "")
        elif m == "Network.loadingFinished":
            pid = self.art_tracked.pop(p["requestId"])
            body = await self.b.send("Network.getResponseBody", {"requestId": p["requestId"]})
            text = body.get("body") or ""
            if body.get("base64Encoded"):
                import base64

                text = base64.b64decode(text).decode("utf-8", "replace")
            try:
                page = json.loads(text)
            except ValueError:
                self.problem = "X answered a post's page with something other than JSON"
                return
            if not page.get("data"):
                errs = "; ".join(str(e.get("message", e)) for e in (page.get("errors") or []))[:300]
                self.problem = f"X answered a post's page without the post ({errs or 'no errors given'})"
                return
            self.article_pages.setdefault(pid, []).append(page)
        elif m == "Network.loadingFailed":
            self.art_tracked.pop(p["requestId"], None)
            self.problem = f"a post's page failed to load ({p.get('errorText', 'no reason given')})"

    def _at(self, url: str) -> None:
        self.main_url = url
        if BLOCKED.search(path_of(url)):
            self.problem = (f"X sent the page to {url.split('?')[0]}: logged out, or X wants something from you "
                            "(open xbrief/bin/xbrief login to see)")

    @property
    def upsell(self) -> bool:
        return bool(self.main_url) and bool(UPSELL.search(path_of(self.main_url)))


def ranking_of(request: dict) -> bool:
    """Whether a feed request asks for X's ranked (Popular) order. Unknown counts as ranked: the safe reading."""
    from urllib.parse import parse_qs, urlparse

    raw = None
    if request.get("postData"):
        try:
            raw = json.loads(request["postData"]).get("variables")
        except ValueError:
            raw = None
    else:
        q = parse_qs(urlparse(request.get("url", "")).query).get("variables", [None])[0]
        try:
            raw = json.loads(q) if q else None
        except ValueError:
            raw = None
    if not isinstance(raw, dict) or "enableRanking" not in raw:
        return True
    return bool(raw["enableRanking"])


def build_of(url: str) -> str:
    return "xweb" if url.startswith("https://api.x.com/") else "legacy"


# ── the run ─────────────────────────────────────────────────────────────────────────────────────────


async def run(rng: random.Random | None = None, sleep=None, now_ms: int | None = None, browser=None,
              home_url: str | None = None, hours: float | None = None, progress=None) -> Result:
    """`hours`: read back that far from now instead of to where the last run stopped (an ad-hoc brief).
    `progress(phase, **counts)` is told what the run is doing (runner.write_progress)."""
    rng = rng or random.Random()
    sleep = sleep or asyncio.sleep
    now_ms = now_ms or int(time.time() * 1000)
    home_url = home_url or config.HOME_URL
    res = Result(started_ms=now_ms)
    state = load_state()
    first = hours is not None or not state.get("newest_id")  # a chosen window reads to a time, not to a post
    if hours is not None:
        res.boundary_id = parse.ms_to_snowflake(now_ms - int(hours * 3_600_000))
    else:
        res.boundary_id = int(state.get("newest_id") or parse.ms_to_snowflake(now_ms - config.FIRST_RUN_HOURS * 3_600_000))

    if browser is None:
        if not config.PROFILE.exists():
            res.stop = "no login: the operator runs xbrief/bin/xbrief login"
            return _done(res)
        from .browser import Browser

        browser = Browser(config.PROFILE)
    feed = Feed(browser, progress)
    try:
        feed.progress("opening Brave")
        await browser.start()
        await browser.send("Page.enable")
        # the browser keeps response bodies for getResponseBody; a feed page is ~0.4 MB, a run at most MAX_PAGES
        await browser.send("Network.enable", {"maxTotalBufferSize": 60_000_000, "maxResourceBufferSize": 4_000_000})
        feed.progress("opening x.com")
        await browser.send("Page.navigate", {"url": home_url})
        t0 = time.monotonic()
        while not feed.loaded and not feed.problem and time.monotonic() - t0 < LOAD_WAIT_S:
            await feed.pump(0.5)
        _check(feed)
        if not feed.loaded:
            raise Stop("x.com/home did not finish loading")
        await feed.pump(3 + rng.uniform(0, 3))  # a person looks at the page before clicking
        _check(feed)
        if feed.upsell:
            await browser.key("Escape")
            await feed.pump(2.5)
            if feed.upsell:
                raise Stop("X is showing a Premium offer that Escape does not close (open xbrief/bin/xbrief login to see)")
        if not feed.pages and not feed.tracked:
            await _click_following(browser, feed, rng)
        t0 = time.monotonic()
        while not feed.pages and not feed.problem and time.monotonic() - t0 < FIRST_PAGE_WAIT_S:
            await feed.pump(0.5)
        _check(feed)
        if not feed.pages:
            raise Stop("the Following tab did not load: X may be showing a notice that needs you "
                       "(open xbrief/bin/xbrief login to see)")
        if feed.ranked:
            await _choose_recent(browser, feed, rng)
        res.build = build_of(feed.urls[0])
        try:
            await _read(browser, feed, res, first, rng, sleep)
        except Stop as s:
            res.stop, res.normal, res.gap = s.why, s.normal, s.gap
        if not feed.problem and (res.normal or res.stop.startswith("stopped at the cap")):  # ended on its own
            # terms (caught up, the end, a cap), never after X pushed back or the feed stalled: now its Articles
            await read_articles(browser, feed, res, wanted(feed.pages, res.boundary_id), rng, sleep)
    except Stop as s:
        res.stop, res.normal, res.gap = s.why, s.normal, s.gap
    except Exception as e:  # anything else ends the run, says what it was, and is never retried
        res.stop = f"{type(e).__name__}: {e}"[:400]
    finally:
        try:
            await browser.close()
        except Exception:
            pass
    res.pages = feed.pages
    res.articles = feed.article_pages
    res.ranked = bool(feed.ranked)
    if feed.pages and not res.build:
        res.build = build_of(feed.urls[0])
    res.newest_id = max([0] + [e.newest_id for p in feed.pages for e in parse.entries(p)[0] if not e.promoted])
    return _done(res)


def _check(feed: Feed) -> None:
    if feed.problem:
        raise Stop(feed.problem)


async def _click_following(browser, feed: Feed, rng: random.Random) -> None:
    for xpath in FOLLOWING_TAB:
        box = await browser.find_box(xpath)
        if box:
            await browser.click(box[0] + rng.uniform(-8, 8), box[1] + rng.uniform(-3, 3))
            return
    raise Stop("could not find the Following tab on x.com/home")


async def _choose_recent(browser, feed: Feed, rng: random.Random) -> bool:
    """The operator reads Recent. If the job's profile shows Popular, choose Recent in the tab's own menu, as a
    person would, and keep only what the feed shows after that. If the menu is not there, carry on in Popular order
    (the reader handles it and the brief says so)."""
    tab = None
    for xpath in FOLLOWING_TAB:
        tab = await browser.find_box(xpath)
        if tab:
            break
    if not tab:
        return False
    await browser.click(tab[0] + rng.uniform(-6, 6), tab[1] + rng.uniform(-2, 2))
    await feed.pump(1.2 + rng.uniform(0, 0.8))
    item = None
    for xpath in RECENT_ITEM:
        item = await browser.find_box(xpath)
        if item:
            break
    if not item:
        await browser.key("Escape")
        await feed.pump(0.5)
        return False
    before = len(feed.pages)
    feed.ranked = None
    await browser.click(item[0] + rng.uniform(-10, 10), item[1] + rng.uniform(-2, 2))
    t0 = time.monotonic()
    while len(feed.pages) == before and not feed.problem and time.monotonic() - t0 < FIRST_PAGE_WAIT_S:
        await feed.pump(0.5)
    _check(feed)
    if len(feed.pages) == before:
        raise Stop("the Following tab did not reload after choosing Recent")
    del feed.pages[:before], feed.urls[:before]  # the Popular pages read before the switch
    return True


async def _read(browser, feed: Feed, res: Result, first: bool, rng: random.Random, sleep) -> None:
    done = 0  # pages already judged
    stalled = 0
    t_end = time.monotonic() + config.MAX_MINUTES * 60
    while True:
        while done < len(feed.pages):
            ents, cursor = parse.entries(feed.pages[done])
            done += 1
            real = [e for e in ents if not e.promoted]
            caught = "read back to the start of the window" if first else "caught up"
            if feed.ranked:  # Popular mixes old posts in: done when a whole page has nothing newer
                if real and not any(e.newest_id > res.boundary_id for e in real):
                    raise Stop(caught, normal=True)
            elif any(0 < e.newest_id <= res.boundary_id for e in real):  # Recent: newest first
                raise Stop(caught, normal=True)
            if not cursor or not real:
                raise Stop("reached the end of what X serves", normal=first, gap=not first)
            if done >= config.MAX_PAGES:
                raise Stop(f"stopped at the cap of {config.MAX_PAGES} pages", gap=True)
            stalled = 0
        _check(feed)
        if stalled >= STALL_WHEELS:
            raise Stop("the feed stopped loading while scrolling", gap=True)
        if time.monotonic() > t_end:
            raise Stop(f"stopped at the cap of {config.MAX_MINUTES} minutes", gap=True)
        await browser.wheel(wheel_delta(rng))
        stalled = stalled + 1 if await browser.at_bottom() else 0
        pause = wheel_pause(rng)
        if sleep is asyncio.sleep:
            await feed.pump(pause)
        else:  # tests: time passes in the fake sleep, events are handled at once
            await sleep(pause)
            await feed.pump(0)


def wanted(pages: list[dict], after_id: int) -> list[parse.Post]:
    """The Articles the brief will hold, newest post first, each once: posts newer than the last brief (as
    brief.unique_posts takes them) that carry an Article, or repost or quote one."""
    out: dict[str, parse.Post] = {}
    for pg in pages:
        for e in parse.entries(pg)[0]:
            if e.promoted or (after_id and e.newest_id <= after_id):
                continue
            for p in e.posts:
                for x in parse.with_article(p):
                    if x.id.isdigit() and x.handle:
                        out.setdefault(x.id, x)
    return sorted(out.values(), key=lambda x: -int(x.id))


async def read_articles(browser, feed: Feed, res: Result, posts: list[parse.Post], rng: random.Random, sleep) -> None:
    """Open each post's own page, as a person opens an Article from the feed, and keep what the page fetches: the
    Article whole. At most config.MAX_ARTICLES a run. X pushing back ends the reading, and the run says so at the
    top of the brief; what was already read is kept."""
    res.articles_left = max(0, len(posts) - config.MAX_ARTICLES)
    feed.feed_done = True
    try:
        for i, post in enumerate(posts[:config.MAX_ARTICLES]):
            feed.progress("reading Articles", articles=i, of=min(len(posts), config.MAX_ARTICLES))
            feed.article_for = post.id
            await browser.send("Page.navigate", {"url": f"https://x.com/{post.handle}/status/{post.id}"})
            t0 = time.monotonic()
            while (post.id not in parse.articles_in(feed.article_pages.get(post.id) or []) and not feed.problem
                   and time.monotonic() - t0 < ARTICLE_WAIT_S):
                await feed.pump(0.5)
            _check(feed)
            if post.id not in parse.articles_in(feed.article_pages.get(post.id) or []):
                raise Stop(f"@{post.handle}'s Article did not load")
            res.articles_read += 1
            pause = rng.uniform(4, 12)  # a person reads a while before the next one
            if sleep is asyncio.sleep:
                await feed.pump(pause)
            else:
                await sleep(pause)
                await feed.pump(0)
            _check(feed)
    except Stop as s:
        res.stop, res.normal = f"{res.stop}; then, reading Articles: {s.why}", False
    finally:
        feed.article_for = None


async def articles_for_raw(path) -> int:
    """Read whole the Articles of a saved run that its read did not (one from before 2026-10-15, or cut short), into
    the same raw file; `xbrief rebrief` then writes its brief with them. Returns how many were read."""
    raw = load_raw(path)
    have = parse.articles_in([pg for v in (raw.get("articles") or {}).values() for pg in v])
    posts = [p for p in wanted(raw["pages"], int(raw["meta"].get("boundary_id") or 0)) if p.id not in have]
    if not posts:
        return 0
    from .browser import Browser

    browser = Browser(config.PROFILE)
    feed = Feed(browser)
    res = Result(started_ms=int(time.time() * 1000), stop="saved run", normal=True)
    try:
        await browser.start()
        await browser.send("Page.enable")
        await browser.send("Network.enable", {"maxTotalBufferSize": 60_000_000, "maxResourceBufferSize": 8_000_000})
        await read_articles(browser, feed, res, posts, random.Random(), asyncio.sleep)
    finally:
        await browser.close()
    arts = raw.setdefault("articles", {})
    for pid, pages in feed.article_pages.items():
        arts.setdefault(pid, []).extend(pages)
    raw["meta"]["articles_read"] = len(parse.articles_in([pg for v in arts.values() for pg in v]))
    _write_raw(pathlib.Path(path), raw)
    if not res.normal:
        raise Stop(res.stop.removeprefix("saved run; then, "))
    return res.articles_read


def _done(res: Result) -> Result:
    res.finished_ms = int(time.time() * 1000)
    if res.pages and res.newest_id > res.boundary_id:
        st = load_state()
        st.update(newest_id=res.newest_id, last_read_ms=res.finished_ms)
        save_state(st)
    return res


def raw_path(started_ms: int, label: str) -> pathlib.Path:
    """A run's raw file, named by its start (the laptop's clock, as the brief's own name) and label."""
    return config.RAW / f"{time.strftime('%Y-%m-%d_%H%M', time.localtime(started_ms / 1000))}-{label}.json.gz"


def save_raw(res: Result, label: str) -> str:
    """One gzip file a run: a feed page is ~0.4 MB as JSON and compresses 7×, and 30 days of runs would otherwise
    near a gigabyte."""
    config.RAW.mkdir(parents=True, exist_ok=True)
    path = raw_path(res.started_ms, label)
    _write_raw(path, {"meta": res.meta(), "pages": res.pages, "articles": res.articles})
    return str(path)


def _write_raw(path, raw: dict) -> None:
    import gzip

    tmp = path.with_suffix(".part")
    with gzip.open(tmp, "wt", compresslevel=6) as f:
        json.dump(raw, f)
    tmp.replace(path)


def load_raw(path) -> dict:
    import gzip

    path = str(path)
    opener = gzip.open if path.endswith(".gz") else open
    with opener(path, "rt") as f:
        return json.load(f)


def raw_files() -> list:
    if not config.RAW.is_dir():  # before the first login or run
        return []
    return sorted(p for p in config.RAW.iterdir() if p.name.endswith((".json", ".json.gz")))


def prune_raw(now_ms: int | None = None) -> int:
    cutoff = (now_ms or int(time.time() * 1000)) / 1000 - config.RAW_KEEP_DAYS * 86400
    n = 0
    for p in raw_files():
        if p.stat().st_mtime < cutoff:
            p.unlink()
            n += 1
    return n
