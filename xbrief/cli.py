"""xbrief run | rebrief | probe | login | status. See README.md."""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import os
import random
import re
import sys
import time

from . import brief, collect, config, page, parse

LABELS = {"am": "morning", "pm": "evening"}


def log(msg: str) -> None:
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}"
    print(line, flush=True)
    config.LOGS.mkdir(parents=True, exist_ok=True)
    with open(config.LOGS / "run.log", "a") as f:
        f.write(line + "\n")


def label_now() -> str:
    return "am" if dt.datetime.now().hour < 12 else "pm"


def jitter_seconds(label: str, now: dt.datetime, rng: random.Random) -> float:
    """A random wait that lands inside the label's window; 0 if the window is already over (a late wake)."""
    start_s, end_s = config.WINDOWS[label]
    start = now.replace(hour=int(start_s[:2]), minute=int(start_s[3:]), second=0, microsecond=0)
    end = now.replace(hour=int(end_s[:2]), minute=int(end_s[3:]), second=0, microsecond=0)
    lo = max(0.0, (start - now).total_seconds())
    hi = (end - now).total_seconds() - 15 * 60  # leave the read and the writing time inside the window
    return rng.uniform(lo, hi) if hi > lo else 0.0


def entries_of(pages: list[dict]) -> list[parse.Entry]:
    out = []
    for p in pages:
        out.extend(parse.entries(p)[0])
    return out


def archive(exclude: str | None = None) -> list[tuple[str, str]]:
    out = []
    for p in sorted(config.BRIEFS.glob("20*.html"), reverse=True)[:20]:
        if p.name == exclude:
            continue
        try:
            d = dt.datetime.strptime(p.name[:15], "%Y-%m-%d-%H%M")
            lab = LABELS.get(p.stem.rsplit("-", 1)[-1], "")
            out.append((f"{d.strftime('%a %-d %b')} · {lab}", p.name))
        except ValueError:
            continue
    return out


def publish(pages: list[dict], meta: dict, label: str, ask=brief.ask_claude) -> str:
    ents = entries_of(pages)
    b, posts = brief.write(ents, ask=ask)
    started = dt.datetime.fromtimestamp((meta.get("started_ms") or time.time() * 1000) / 1000)
    name = f"{started.strftime('%Y-%m-%d-%H%M')}-{label}.html"
    title = f"X brief · {LABELS.get(label, label)}"
    html = page.render(b, posts, ents, meta, title, archive(exclude=name))
    config.BRIEFS.mkdir(parents=True, exist_ok=True)
    for target in (config.BRIEFS / name, config.BRIEFS / "index.html"):
        tmp = target.with_suffix(".part")
        tmp.write_text(html)
        tmp.replace(target)
    log(f"brief {name}: {len(posts)} posts, {len(b.topics)} topics"
        + (f", writer failed: {b.writer_error}" if b.writer_error else ""))
    return name


def cmd_run(a) -> int:
    config.ensure_dirs()
    label = a.label or label_now()
    if not a.now:
        wait = jitter_seconds(label, dt.datetime.now(), random.Random())
        log(f"run {label}: starting in {wait / 60:.0f} min")
        time.sleep(wait)
    if a.max_pages:
        config.MAX_PAGES = a.max_pages
    res = asyncio.run(collect.run())
    path = collect.save_raw(res, label)
    log(f"read {len(res.pages)} pages ({res.build or 'no site'}): {res.stop}" + (" · GAP" if res.gap else "")
        + f" · raw {os.path.basename(path)}")
    publish(res.pages, res.meta(), label)
    pruned = collect.prune_raw()
    if pruned:
        log(f"deleted {pruned} raw files older than {config.RAW_KEEP_DAYS} days")
    return 0 if res.normal else 1


def cmd_rebrief(a) -> int:
    raw = json.loads(open(a.raw).read())
    label = os.path.basename(a.raw).rsplit("-", 1)[-1].removesuffix(".json")
    publish(raw["pages"], raw["meta"], label if label in LABELS else "am")
    return 0


def cmd_probe(a) -> int:
    """Open x.com/home once in the job's Brave (hidden) and say whether it is logged in and which web app X
    serves. No click, no scroll: reads no feed."""
    config.ensure_dirs()
    if not config.PROFILE.exists():
        print("no login: run xbrief/bin/xbrief login")
        return 1
    from .browser import Browser

    async def go():
        b = Browser(config.PROFILE)
        feed = collect.Feed(b)
        seen: list[str] = []
        try:
            await b.start()
            await b.send("Page.enable")
            await b.send("Network.enable")
            await b.send("Page.navigate", {"url": config.HOME_URL})
            t0 = time.monotonic()
            while time.monotonic() - t0 < 25 and not feed.problem:
                try:
                    ev = await asyncio.wait_for(b.events.get(), 1)
                except asyncio.TimeoutError:
                    if feed.loaded and time.monotonic() - t0 > 8:
                        break
                    continue
                if ev.get("method") == "Network.requestWillBeSent":
                    url = ev["params"]["request"]["url"]
                    m = re.search(r"/graphql/[\w-]+/(\w+)", url)
                    if m and m.group(1) not in [x.split()[0] for x in seen]:
                        seen.append(f"{m.group(1)} ({collect.build_of(url)})")
                if ev.get("method") != "Network.loadingFinished":
                    await feed.handle(ev)
        finally:
            await b.close()
        print(f"page       {feed.main_url or '(none)'}")
        if feed.problem:
            print(f"problem    {feed.problem}")
            return 1
        print("logged in  yes" if seen else "logged in  unclear: x.com/home made no feed requests")
        for x in seen[:12]:
            print(f"request    {x}")
        return 0 if seen else 1

    try:
        return asyncio.run(go())
    except Exception as e:
        print(f"probe failed: {type(e).__name__}: {e}")
        return 1


def cmd_login(a) -> int:
    """Open the job's own Brave profile in an ordinary window for the operator to log in to X."""
    config.ensure_dirs()
    from .browser import login_window, running

    print("A separate Brave window opens on X's login page. It is the job's own profile, not your usual one.")
    print("  1. Log in to your main X account.")
    print("  2. Close anything X shows (Premium offer, Terms notice) the way you would.")
    print("  3. Click the Following tab once.")
    print("  4. Quit that Brave with cmd+Q while its window is in front.")
    login_window(config.PROFILE)
    t0 = time.time()
    while not running(config.PROFILE) and time.time() - t0 < 20:
        time.sleep(0.5)
    print("waiting for you to quit that Brave …", flush=True)
    while running(config.PROFILE) and time.time() - t0 < 3600:
        time.sleep(2)
    if config.OLD_LOGIN.exists():
        config.OLD_LOGIN.unlink()
        print("deleted the first build's login file (the cookies pasted earlier)")
    print("done. Next: xbrief/bin/xbrief probe")
    return 0


def cmd_status(a) -> int:
    st = collect.load_state()
    if st.get("newest_id"):
        print(f"newest post read  {dt.datetime.fromtimestamp(parse.snowflake_ms(st['newest_id']) / 1000):%a %-d %b %H:%M}")
    raws = sorted(config.RAW.glob("*.json"))
    if raws:
        meta = json.loads(raws[-1].read_text())["meta"]
        print(f"last run          {raws[-1].name}: {meta['stop']}{' · GAP' if meta.get('gap') else ''}"
              f" ({meta.get('page_count', 0)} pages, {meta.get('build') or 'no feed'})")
    from .browser import running

    print(f"login profile     {'present' if config.PROFILE.exists() else 'none: run xbrief/bin/xbrief login'}"
          + (" (open now)" if running(config.PROFILE) else ""))
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="xbrief")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="read the Following tab and write the brief")
    r.add_argument("--label", choices=list(LABELS))
    r.add_argument("--now", action="store_true", help="start now, not at a random minute in the window")
    r.add_argument("--max-pages", type=int)
    r.set_defaults(fn=cmd_run)
    rb = sub.add_parser("rebrief", help="write the brief again from a saved raw file")
    rb.add_argument("raw")
    rb.set_defaults(fn=cmd_rebrief)
    sub.add_parser("probe", help="open x.com/home once (hidden) and say whether the job is logged in").set_defaults(fn=cmd_probe)
    sub.add_parser("login", help="open the job's Brave profile so you can log in to X").set_defaults(fn=cmd_login)
    sub.add_parser("status", help="the last run and the login profile").set_defaults(fn=cmd_status)
    a = p.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
