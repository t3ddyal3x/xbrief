"""xbrief run | rebrief | probe | login | status. See README.md."""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import getpass
import json
import os
import random
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
    """Open x.com/home once as the account and report the site build and its Following-tab request.
    Reads no feed."""
    config.ensure_dirs()
    config.apply_job_env()
    from twscrape import API
    from twscrape.queue_client import XClIdGenStore

    from . import request, site

    async def go():
        api = API(pool=str(config.ACCOUNTS_DB), raise_when_no_account=True)
        accs = await api.pool.get_all()
        if not accs:
            print("no login: run xbrief/bin/xbrief login")
            return 1
        gen = await XClIdGenStore.get(accs[0].username, cookies=accs[0].cookies)
        op, reread = await site.resolve(gen.page_html or "", collect.fetch_script)
        req = request.build(op, config.PAGE_SIZE, None, None)
        print(f"build      {op.build}{' (read just now)' if reread else ' (saved)'}")
        print(f"request    {req.method} {req.url}")
        print(f"from       {op.script.rsplit('/', 1)[-1]}")
        if req.params:
            print(f"variables  {req.params['variables']}")
        if req.body:
            print(f"body       {json.dumps(req.body)[:600]}")
        print("Compare with Brave (profile public): x.com/home, Following tab, DevTools, Network, filter HomeLatest.")
        return 0

    try:
        return asyncio.run(go())
    except Exception as e:
        print(f"probe failed: {type(e).__name__}: {e}")
        return 1


def cmd_login(a) -> int:
    """Store the X session from the public Brave profile. Run in your own terminal; nothing is echoed."""
    config.ensure_dirs()
    config.apply_job_env()
    from twscrape import AccountsPool

    print("In Brave (profile public): x.com, DevTools, Application, Cookies, https://x.com.")
    handle = input("Your X handle, without @: ").strip().lstrip("@")
    auth = getpass.getpass("auth_token value (hidden): ").strip()
    ct0 = getpass.getpass("ct0 value (hidden): ").strip()
    if not (handle and auth and ct0):
        print("nothing stored: all three are needed")
        return 1

    async def go():
        pool = AccountsPool(str(config.ACCOUNTS_DB))
        await pool.add_account_cookies(handle, f"auth_token={auth}; ct0={ct0}")

    old = os.umask(0o077)
    try:
        asyncio.run(go())
    finally:
        os.umask(old)
    os.chmod(config.ACCOUNTS_DB, 0o600)
    print(f"stored for @{handle} in {config.ACCOUNTS_DB} (mode 600). Next: xbrief/bin/xbrief probe")
    return 0


def cmd_status(a) -> int:
    config.apply_job_env()
    st = collect.load_state()
    if st.get("newest_id"):
        print(f"newest post read  {dt.datetime.fromtimestamp(parse.snowflake_ms(st['newest_id']) / 1000):%a %-d %b %H:%M}")
    from . import site

    op = site.load_saved()
    print(f"site              {op.build + ' ' + op.name + ' ' + op.query_id if op else 'not read yet'}")
    raws = sorted(config.RAW.glob("*.json"))
    if raws:
        meta = json.loads(raws[-1].read_text())["meta"]
        print(f"last run          {raws[-1].name}: {meta['stop']}{' · GAP' if meta.get('gap') else ''}")
    if config.ACCOUNTS_DB.exists():
        from twscrape import AccountsPool

        accs = asyncio.run(AccountsPool(str(config.ACCOUNTS_DB)).get_all())
        for x in accs:
            locks = {k: v.astimezone().strftime('%H:%M') for k, v in x.locks.items() if v.timestamp() > time.time()}
            print(f"login             @{x.username} {'active' if x.active else 'INACTIVE: ' + str(x.error_msg)}"
                  + (f" · locked {locks}" if locks else ""))
    else:
        print("login             none")
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
    sub.add_parser("probe", help="open x.com/home once and show the request a run would send").set_defaults(fn=cmd_probe)
    sub.add_parser("login", help="store the X session (run it in your own terminal)").set_defaults(fn=cmd_login)
    sub.add_parser("status", help="the last run, the site build, the login's state").set_defaults(fn=cmd_status)
    a = p.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
