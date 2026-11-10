"""xbrief serve | run | rebrief | articles | probe | login | status | sites. See README.md."""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import os
import re
import sys
import time

from . import brief, collect, config, page, parse, runner, store, videos

LABELS = page.LABELS
log = runner.log


def entries_of(pages: list[dict]) -> list[parse.Entry]:
    out = []
    for p in pages:
        out.extend(parse.entries(p)[0])
    return out


def threads_of(entries: list[parse.Entry], posts: dict) -> list[list[str]]:
    """The conversations of three posts or more that the brief holds, each in display order."""
    return [[p.id for p in e.posts] for e in entries if len(e.posts) >= 3 and any(p.id in posts for p in e.posts)]


# ── a morning caught up ─────────────────────────────────────────────────────────────────────────────
# The early run reads the night and writes the brief before the operator wakes; their Brief now later that morning
# reads only what came after, and writes the morning's one brief again over both reads (operator, 2026-10-20:
# docs/plans/2026-10-20_early-run.md). The brief keeps the early run's name; its meta lists each read (`reads`).

READ_KEYS = tuple(collect.Result(0).meta())  # what a read's meta holds


def reads_of(meta: dict, label: str) -> list[dict]:
    """The reads a stored brief was written from, each with its raw file: one, or each read of a morning caught up."""
    if meta.get("reads"):
        return meta["reads"]
    return [{**{k: meta.get(k) for k in READ_KEYS},
             "raw": meta.get("raw") or str(collect.raw_path(meta.get("started_ms") or 0, label))}]


def combine(reads: list[dict]) -> tuple[list[dict], dict, dict]:
    """Several reads as one: their pages in order, their Articles, and one meta. The window opens where the first read
    began; the read ended where the last did; a read that stopped early or left a gap is said."""
    pages: list[dict] = []
    articles: dict[str, list[dict]] = {}
    for r in reads:
        raw = collect.load_raw(r["raw"])
        pages += raw["pages"]
        for pid, pgs in (raw.get("articles") or {}).items():
            articles.setdefault(pid, []).extend(pgs)
    first, last = reads[0], reads[-1]
    early = [r["stop"] for r in reads if not r.get("normal")]
    meta = {**{k: last.get(k) for k in READ_KEYS}, "started_ms": first.get("started_ms"),
            "boundary_id": first.get("boundary_id"), "normal": not early, "stop": "; ".join(early) or last.get("stop"),
            "gap": any(r.get("gap") for r in reads), "ranked": any(r.get("ranked") for r in reads),
            **{k: sum(r.get(k) or 0 for r in reads) for k in ("page_count", "articles_read", "articles_left")},
            "reads": reads}
    return pages, articles, meta


def catching_up(label: str, started_ms: int) -> dict | None:
    """The brief this run catches up: the newest, when it is of the same day and the same label."""
    prev = (store.runs(limit=1) or [None])[0]
    if not prev or prev["label"] != label:
        return None
    same_day = dt.date.fromtimestamp(prev["started_ms"] / 1000) == dt.date.fromtimestamp(started_ms / 1000)
    return prev if same_day else None


def publish_raw(path, read_videos=None) -> str:
    """Write a saved run's brief again: the whole morning it belongs to, if it was one read of a morning caught up."""
    name = os.path.basename(str(path))
    run = next((r for r in store.runs() if any(os.path.basename(x["raw"]) == name for x in r["meta"].get("reads") or [])), None)
    if run:
        pages, articles, meta = combine(run["meta"]["reads"])
    else:
        raw = collect.load_raw(path)
        pages, articles, meta = raw["pages"], raw.get("articles"), raw["meta"]
    return publish(pages, meta, label_of(path), articles=articles, read_videos=read_videos)


def publish(pages: list[dict], meta: dict, label: str, ask=brief.ask_claude, articles: dict | None = None,
            read_videos=None) -> str:
    """Write the brief and store the run whole (store.save_run); the page reads it from there. `articles`: what
    each Article post's own page fetched (collect.read_articles), so the writer reads those Articles whole.
    `read_videos(posts)`: the long videos of the brief's posts, transcribed and summarised (videos.read_all)."""
    ents = entries_of(pages)
    parse.attach_articles(ents, parse.articles_in([pg for v in (articles or {}).values() for pg in v]))
    if read_videos:
        docs, left = read_videos(brief.unique_posts(ents, int(meta.get("boundary_id") or 0)))
        videos.attach(ents, docs)
        meta = {**meta, "videos_read": sum(1 for d in docs.values() if d.get("summary")), "videos_left": left,
                "videos_failed": [{k: d.get(k) for k in ("key", "by", "kind", "title", "url", "error")}
                                  for d in docs.values() if d.get("error")]}
    b, posts = brief.write(ents, ask=ask, after_id=int(meta.get("boundary_id") or 0))
    started = dt.datetime.fromtimestamp((meta.get("started_ms") or time.time() * 1000) / 1000)
    name = f"{started.strftime('%Y-%m-%d-%H%M')}-{label}"
    store.save_run(name, label, meta, b, posts, threads_of(ents, posts))
    log(f"brief {name}: {len(posts)} posts, {len(b.theses)} theses, {len(b.topics)} topics"
        + (f", writer failed: {b.writer_error}" if b.writer_error else ""))
    return name


def cmd_run(a) -> int:
    config.ensure_dirs()
    label = a.label or runner.label_now()
    lock = runner.acquire()
    if lock is None:
        log(f"run {label}: another run is going; this one did not start")
        return 3
    pr, now_ms = runner.read_progress(), int(time.time() * 1000)
    if not (pr.get("phase") == "starting" and now_ms - (pr.get("started_ms") or 0) < 60_000):  # not started by the page
        runner.write_progress(fresh=True, label=label, hours=a.hours, by="terminal", started_ms=now_ms)
    runner.write_progress(phase="starting", done=False, pid=os.getpid())
    try:
        if a.max_pages:
            config.MAX_PAGES = a.max_pages
        res = asyncio.run(collect.run(hours=a.hours, progress=lambda phase, **kw: runner.write_progress(phase=phase, **kw)))
        path = collect.save_raw(res, label)
        log(f"read {len(res.pages)} pages ({res.build or 'no site'}): {res.stop}" + (" · GAP" if res.gap else "")
            + (f" · {res.articles_read} Articles read whole" if res.articles_read else "")
            + (f", {res.articles_left} past the cap" if res.articles_left else "") + f" · raw {os.path.basename(path)}")
        pages, articles, meta = res.pages, res.articles, {**res.meta(), "raw": path}
        prev = catching_up(label, res.started_ms) if a.hours is None else None
        if prev:
            if not brief.unique_posts(entries_of(res.pages), int(res.boundary_id or 0)):
                log(f"caught up {prev['name']}: nothing new since its read")
                runner.write_progress(phase="done", done=True, name=prev["name"], stop=res.stop, normal=res.normal,
                                      at=page.at_of(prev["name"], prev["meta"]),
                                      note=f"Nothing new since {time.strftime('%H:%M', time.localtime(prev['meta'].get('finished_ms', 0) / 1000))}.")
                return 0 if res.normal else 1
            try:
                pages, articles, meta = combine(reads_of(prev["meta"], prev["label"]) + [reads_of(meta, label)[0]])
                log(f"catching up {prev['name']}: its brief is written again with this read")
            except (OSError, ValueError, KeyError) as e:  # its raw file is gone: this read is a brief of its own
                log(f"could not catch up {prev['name']} ({type(e).__name__}: {e}); a brief of its own")
        n = len(brief.unique_posts(entries_of(pages), int(meta.get("boundary_id") or 0)))  # what the writer gets
        runner.write_progress(phase="writing the brief", stop=res.stop, normal=res.normal, posts=n,
                              writing_ms=int(time.time() * 1000))

        def read_videos(posts):
            out = videos.read_all(posts, progress=lambda phase, **kw: runner.write_progress(phase=phase, **kw), log=log)
            runner.write_progress(phase="writing the brief", writing_ms=int(time.time() * 1000))  # the clock restarts
            return out

        name = publish(pages, meta, label, articles=articles, read_videos=read_videos)
        runner.write_progress(phase="done", done=True, name=name, at=page.at_of(name, meta))
        pruned = collect.prune_raw()
        if pruned:
            log(f"deleted {pruned} raw files older than {config.RAW_KEEP_DAYS} days")
        return 0 if res.normal else 1
    except BaseException as e:
        runner.write_progress(phase="failed", done=True, error=f"{type(e).__name__}: {e}"[:300])
        raise
    finally:
        lock.close()


def label_of(raw_path) -> str:
    label = os.path.basename(str(raw_path)).rsplit("-", 1)[-1].removesuffix(".gz").removesuffix(".json")
    return label if label in LABELS else "am"


def cmd_rebrief(a) -> int:
    publish_raw(a.raw, read_videos=lambda posts: videos.read_all(posts, log=log))
    return 0


def cmd_articles(a) -> int:
    """Read whole, in the job's Brave, the Articles of a saved run that its read did not, then write its brief again."""
    lock = runner.acquire()
    if lock is None:
        log("articles: a run is going; try again after it")
        return 3
    try:
        code = 0
        try:
            n = asyncio.run(collect.articles_for_raw(a.raw))
            log(f"articles {os.path.basename(a.raw)}: {n} read whole")
        except collect.Stop as s:  # what was read before X pushed back is kept, and the brief written with it
            log(f"articles {os.path.basename(a.raw)}: stopped: {s.why}")
            code = 1
        publish_raw(a.raw, read_videos=lambda posts: videos.read_all(posts, log=log))
        return code
    finally:
        lock.close()


def cmd_serve(a) -> int:
    from . import server

    server.serve()
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
        feed_vars: list[str] = []
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
                    if collect.TIMELINE.search(url):  # the feed request's variables: no cookies, those are headers
                        req = ev["params"]["request"]
                        body = req.get("postData") or ""
                        try:
                            variables = json.loads(body).get("variables") if body else None
                        except ValueError:
                            variables = None
                        if variables is None:
                            from urllib.parse import parse_qs, urlparse

                            variables = parse_qs(urlparse(url).query).get("variables", ["?"])[0]
                        feed_vars.append(f"{req.get('method')} {json.dumps(variables) if not isinstance(variables, str) else variables}")
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
        for v in feed_vars:
            print(f"Following  {v[:700]}")
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
    print("done. Next: xbrief/bin/xbrief probe")
    return 0


def cmd_status(a) -> int:
    st = collect.load_state()
    if st.get("newest_id"):
        print(f"newest post read  {dt.datetime.fromtimestamp(parse.snowflake_ms(st['newest_id']) / 1000):%a %-d %b %H:%M}")
    raws = collect.raw_files()
    if raws:
        meta = collect.load_raw(raws[-1])["meta"]
        print(f"last run          {raws[-1].name}: {meta['stop']}{' · GAP' if meta.get('gap') else ''}"
              f" ({meta.get('page_count', 0)} pages, {meta.get('build') or 'no feed'})")
    from .browser import running

    print(f"login profile     {'present' if config.PROFILE.exists() else 'none: run xbrief/bin/xbrief login'}"
          + (" (open now)" if running(config.PROFILE) else ""))
    return 0


def cmd_sites(a) -> int:
    from . import sites

    return sites.cmd(a)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="xbrief")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("serve", help="the app at xbrief.localhost, and the schedule (the LaunchAgent runs this)").set_defaults(fn=cmd_serve)
    r = sub.add_parser("run", help="read the Following tab and write the brief")
    r.add_argument("--label", choices=list(LABELS))
    r.add_argument("--now", action="store_true", help=argparse.SUPPRESS)  # every run starts at once; still accepted
    r.add_argument("--max-pages", type=int)
    r.add_argument("--hours", type=float, help="read back this many hours from now, not to where the last run stopped")
    r.set_defaults(fn=cmd_run)
    rb = sub.add_parser("rebrief", help="write the brief again from a saved raw file")
    rb.add_argument("raw")
    rb.set_defaults(fn=cmd_rebrief)
    ar = sub.add_parser("articles", help="read whole the Articles of a saved run (opens their pages), then rebrief it")
    ar.add_argument("raw")
    ar.set_defaults(fn=cmd_articles)
    sub.add_parser("probe", help="open x.com/home once (hidden) and say whether the job is logged in").set_defaults(fn=cmd_probe)
    sub.add_parser("login", help="open the job's Brave profile so you can log in to X").set_defaults(fn=cmd_login)
    sub.add_parser("status", help="the last run and the login profile").set_defaults(fn=cmd_status)
    sub.add_parser("sites", help="check the sites on the list now and summarise their new posts").set_defaults(fn=cmd_sites)
    a = p.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
