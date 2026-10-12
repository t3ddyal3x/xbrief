"""The app's pages, built on the server: a brief, the history of briefs, and search over every post kept.

Every piece of post text is escaped, and every link and byline is built here from the posts, never from Claude's
words. The one script is the app's own (static/app.js: the run button, its progress, the schedule form); the
server's Content-Security-Policy allows no other, and images load from X's image servers only.
Tokyo Night / Tokyo Day like the other local pages; Iowan Old Style (on every Mac) to read, a mono for handles.
"""

from __future__ import annotations

import html
import re
import time
from collections import Counter

from .brief import Brief, Topic
from .parse import Post

CSP = ("default-src 'none'; img-src https://pbs.twimg.com; style-src 'self'; script-src 'self'; connect-src 'self'; "
       "base-uri 'none'; form-action 'self'; frame-ancestors 'none'")
LABELS = {"am": "morning", "pm": "evening"}
HOURS = [("", "since last"), ("12", "last 12 h"), ("24", "last 24 h"), ("48", "last 48 h")]


def esc(s) -> str:
    return html.escape(str(s or ""), quote=True)


def safe_url(u: str) -> str | None:
    return u if isinstance(u, str) and re.match(r"https?://", u) else None


def hhmm(ms: int) -> str:
    return time.strftime("%H:%M", time.localtime(ms / 1000))


def day(ms: int) -> str:
    return time.strftime("%a %-d %b %H:%M", time.localtime(ms / 1000))


def rich_text(p: Post) -> str:
    """The post's text, escaped, with its t.co links shown as their real address."""
    text = esc(p.text)
    for ln in p.links:
        short, url = ln.get("short"), safe_url(ln.get("url"))
        if short and url:
            text = text.replace(esc(short), f'<a href="{esc(url)}" rel="noreferrer">{esc(ln.get("display") or url)}</a>')
    return re.sub(r"\s*https://t\.co/\w+\s*$", "", text)  # a media link left at the very end


def imgs(p: Post) -> str:
    if not p.media:
        return ""
    out = []
    for m in p.media[:4]:
        u = safe_url(m.get("url"))
        if not u or not u.startswith("https://pbs.twimg.com/"):
            continue
        tag = "" if m.get("type") == "photo" else f'<span class="v">{esc(m.get("type"))}</span>'
        out.append(f'<a href="{esc(p.url)}" rel="noreferrer"><img loading="lazy" referrerpolicy="no-referrer" '
                   f'src="{esc(u)}?name=small" alt="">{tag}</a>')
    return f'<div class="imgs">{"".join(out)}</div>' if out else ""


def post_html(p: Post, also: str = "") -> str:
    """One post; `also` is a piece of markup added at the end of its byline (search: the brief it came from)."""
    if p.unreadable:
        return (f'<div class="post"><div class="meta"><a href="{esc(p.url)}" rel="noreferrer">a post X would not show '
                f'({esc(p.unreadable)})</a>{also}</div></div>')
    shown, lead = p, ""
    if p.retweet_of:
        shown = p.retweet_of
        lead = f'<span>reposted by @{esc(p.handle)}</span>'
    reply = f'<span>replying to @{esc(shown.reply_to_handle)}</span>' if shown.reply_to_handle else ""
    quote = ""
    if shown.quote and not shown.quote.unreadable:
        q = shown.quote
        quote = (f'<div class="q"><div class="meta"><a href="{esc(q.url)}" rel="noreferrer">@{esc(q.handle)}</a>'
                 f'<span>{day(q.created_ms)}</span></div><div class="t">{rich_text(q)}</div>{imgs(q)}</div>')
    return (f'<div class="post"><div class="meta"><a href="{esc(shown.url)}" rel="noreferrer">@{esc(shown.handle)}</a>'
            f'<span>{esc(shown.name)}</span><span>{day(shown.created_ms)}</span>{lead}{reply}{also}</div>'
            f'<div class="t">{rich_text(shown)}</div>{imgs(shown)}{quote}</div>')


def topic_posts(ids: list[str], posts: dict[str, Post], thr: dict[str, list[Post]]) -> list[Post]:
    """The topic's posts newest first, a conversation kept together where its first post falls."""
    shown: list[Post] = []
    seen: set[str] = set()
    for pid in sorted(ids, key=lambda x: -posts[x].created_ms):
        for p in thr.get(pid) or [posts[pid]]:
            if p.id not in seen:
                seen.add(p.id)
                shown.append(p)
    return shown


def topic_html(t: Topic, posts: dict[str, Post], thr: dict[str, list[Post]]) -> str:
    shown = topic_posts(t.posts, posts, thr)
    handles = list(dict.fromkeys((p.retweet_of or p).handle for p in shown))
    who = ", ".join(f"@{h}" for h in handles[:6]) + (f" and {len(handles) - 6} more" if len(handles) > 6 else "")
    label = f"{len(shown)} post{'s' if len(shown) != 1 else ''} · {who}"
    return (f'<p>{esc(t.summary)}</p><details><summary>{esc(label)}</summary>'
            f'{"".join(post_html(p) for p in shown)}</details>')


def status_html(meta: dict, b: Brief, n_posts: int, n_accounts: int) -> str:
    lines = []
    if not meta.get("normal"):
        lines.append(f"<b>The read stopped early:</b> {esc(meta.get('stop'))}.")
    if meta.get("gap"):
        lines.append("<b>Gap:</b> some posts between the last brief and this one were not read.")
    if meta.get("ranked"):
        lines.append("<b>Popular order:</b> X is sorting the Following tab by Popular, which can leave posts out. "
                     "Set it to Recent to get every post.")
    if b.writer_error:
        lines.append(f"<b>No summary this time</b> ({esc(b.writer_error)}). Every post is listed below as read.")
    from .parse import snowflake_ms

    since = f"since {day(snowflake_ms(meta['boundary_id']))} · " if meta.get("boundary_id") else ""
    head = (f"{since}{esc(meta.get('stop') or 'read')} · {n_posts} posts from {n_accounts} accounts · "
            f"read {hhmm(meta.get('started_ms') or 0)}–{hhmm(meta.get('finished_ms') or 0)}")
    if meta.get("reread_site"):
        head += f" · X deployed a new site; its request was read again ({esc(meta.get('build'))})"
    if not lines:
        return f'<div class="status quiet">{head}</div>'
    cls = "bad" if not meta.get("page_count") else "warn"
    return f'<div class="status {cls}">{"<br>".join(lines)}<br><span class="mono">{head}</span></div>'




# ── the app's frame ─────────────────────────────────────────────────────────────────────────────────


def run_title(name: str, label: str, started_ms: int) -> str:
    return f"{time.strftime('%a %-d %b', time.localtime(started_ms / 1000))} · {LABELS.get(label, label)}"


def live_html(live: dict) -> str:
    cls = {"on": " on", "bad": " bad"}.get(live.get("kind", ""), "")
    text = esc(live.get("text"))
    if live.get("href"):
        text = f'{text} <a href="{esc(live["href"])}">{esc(live.get("link") or "open")}</a>'
    return f'<p class="live{cls}" id="live" aria-live="polite">{text}</p>'


def rail(active: str, live: dict, extra: str = "", running: bool = False) -> str:
    tabs = "".join(f'<a href="{href}"{" aria-current=page" if key == active else ""}>{name}</a>'
                   for key, href, name in (("brief", "/", "Brief"), ("history", "/history", "History")))
    opts = "".join(f'<option value="{v}">{esc(t)}</option>' for v, t in HOURS)
    return (f'<nav class="rail"><h1><a href="/">X brief</a></h1><p class="tabs">{tabs}</p>'
            + ("" if active == "search" else  # the search page has its own form
               f'<form class="find ctl" action="/search" method="get" role="search">'
               f'<input type="search" name="q" placeholder="Search posts" aria-label="Search posts"></form>')
            + f'<form class="run ctl" id="run"><select name="hours" aria-label="What to read">{opts}</select>'
            f'<button type="submit"{" disabled" if running else ""}>Brief now</button></form>'
            f'{live_html(live)}{extra}</nav>')


def shell(title: str, rail_html: str, main: str, at: str = "") -> str:
    """`at`: the brief this page shows, so the rail does not offer it as new."""
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="referrer" content="no-referrer"><title>{esc(title)}</title>
<link rel="stylesheet" href="/app.css"><script src="/app.js" defer></script></head>
<body{f' data-at="{esc(at)}"' if at else ""}><div class="wrap">{rail_html}<main>{main}</main></div></body></html>
"""


# ── a brief ─────────────────────────────────────────────────────────────────────────────────────────


def brief_main(b: Brief, posts: dict[str, Post], thr: dict[str, list[Post]], meta: dict) -> tuple[str, list[str]]:
    """The brief's body and the rail's list of its topics."""
    accounts = Counter(p.handle for p in posts.values())  # who I follow; a repost counts as the reposter
    sections, toc = [], []
    for i, t in enumerate(b.topics):
        sid = f"t{i}"
        toc.append(f'<li><a href="#{sid}">{esc(t.title)}</a><span class="n">{len(t.posts)}</span></li>')
        sections.append(f'<section id="{sid}"><h2>{esc(t.title)}</h2>{topic_html(t, posts, thr)}</section>')
    if b.other:
        rest = topic_posts([i for i in b.other if i in posts], posts, thr)
        toc.append(f'<li><a href="#other">Everything else</a><span class="n">{len(rest)}</span></li>')
        sections.append(f'<section id="other"><h2>Everything else</h2><p class="empty">Memes, pictures, one-liners '
                        f'and reposts with nothing to add: {len(rest)} posts, as read.</p>'
                        f'<details><summary>{len(rest)} posts</summary>{"".join(post_html(p) for p in rest)}</details></section>')
    if not posts:
        sections.append('<p class="empty">Nothing new from the accounts you follow since the last brief.</p>')
    return status_html(meta, b, len(posts), len(accounts)) + "".join(sections), toc


def brief_page(run: dict, earlier: list[dict], live: dict, running: bool = False) -> str:
    meta = run["meta"]
    title = run_title(run["name"], run["label"], meta.get("started_ms") or 0)
    main, toc = brief_main(run["brief"], run["posts"], run["threads"], meta)
    others = [r for r in earlier if r["started_ms"] < (meta.get("started_ms") or 0)][:10]  # older than this one
    arch = "".join(f'<li><a href="/b/{esc(r["name"])}">{esc(run_title(r["name"], r["label"], r["started_ms"]))}</a>'
                   f'<span class="n">{r["n_posts"]}</span></li>' for r in others)
    extra = (f'<h2>{esc(title)}</h2><p class="when">read {day(meta.get("started_ms") or 0)}</p>'
             f'<ol>{"".join(toc)}</ol>'
             + (f'<h2>Earlier</h2><ul>{arch}</ul><a class="more" href="/history">All briefs</a>' if arch else ""))
    return shell(f"X brief · {title}", rail("brief", live, extra, running=running), main, at=run["name"])


def empty_page(live: dict, running: bool = False) -> str:
    main = ('<p class="empty">No brief yet. <b>Brief now</b> reads your Following tab in the job\'s Brave and '
            'writes the first one; it takes a few minutes.</p>')
    return shell("X brief", rail("brief", live, running=running), main)


# ── history ─────────────────────────────────────────────────────────────────────────────────────────


def ending(meta: dict, writer_error: str | None) -> tuple[str, str]:
    """How a run ended, in the history's words, and how loudly to say it."""
    if not meta.get("page_count"):
        return meta.get("stop") or "read nothing", "bad"
    bits = [] if meta.get("normal") else [f"stopped early: {meta.get('stop')}"]
    if meta.get("gap"):
        bits.append("gap")
    if writer_error:
        bits.append("no summary")
    if bits:
        return " · ".join(bits), "warn"
    return meta.get("stop") or "", ""


def history_page(runs: list[dict], sett: dict, today: dict, live: dict, running: bool = False) -> str:
    rows = []
    for r in runs:
        end, cls = ending(r["meta"], r.get("writer_error"))
        n = f'{r["n_posts"]} posts · {r["n_topics"]} topics'
        rows.append(f'<li><a href="/b/{esc(r["name"])}">{esc(run_title(r["name"], r["label"], r["started_ms"]))}'
                    f' {hhmm(r["started_ms"])}</a><span class="n">{n}</span>'
                    f'<span class="end {cls}">{esc(end)}</span></li>')
    w = sett["windows"]
    win = "".join(f'<div class="w"><span>{LABELS[k]}</span><input type="time" name="{k}0" value="{esc(w[k][0])}" '
                  f'aria-label="{LABELS[k]} from" required><span>to</span><input type="time" name="{k}1" '
                  f'value="{esc(w[k][1])}" aria-label="{LABELS[k]} to" required></div>' for k in ("am", "pm"))
    slots = []
    for k in ("am", "pm"):
        s = today.get(k)
        if not s:
            continue
        if s["fired_ms"] is None:
            slots.append(f"{LABELS[k]} at {hhmm(s['fire_ms'])}")
        elif s["fired_ms"] == -1:
            slots.append(f"{LABELS[k]} skipped")
        else:
            slots.append(f"{LABELS[k]} started {hhmm(s['fired_ms'])}")
    today_line = f'<p class="note">Today: {esc(" · ".join(slots))}.</p>' if slots and sett["schedule"] else ""
    main = (f'<section id="schedule"><h2>Schedule</h2>'
            f'<form class="sched ctl" id="sched"><label><input type="checkbox" name="on"'
            f'{" checked" if sett["schedule"] else ""}> Two briefs a day</label>{win}'
            f'<button type="submit">Save</button></form>'
            f'<p class="note" id="sched-msg">Each run starts at a random minute inside its window.</p>{today_line}</section>'
            f'<section><h2>Briefs</h2>'
            + (f'<ol class="runs">{"".join(rows)}</ol>' if rows else '<p class="empty">No brief yet.</p>')
            + '</section>')
    return shell("X brief · history", rail("history", live, running=running), main)


# ── search ──────────────────────────────────────────────────────────────────────────────────────────


def search_page(q: str, since: str, until: str, hits: list[tuple[Post, str | None]], cut: bool, kept: dict,
                titles: dict[str, str], live: dict, running: bool = False) -> str:
    form = (f'<form class="search ctl" action="/search" method="get" role="search">'
            f'<input type="search" name="q" value="{esc(q)}" placeholder="words, @account" aria-label="Words or @account" autofocus>'
            f'<input type="date" name="since" value="{esc(since)}" aria-label="From"><span class="to">to</span>'
            f'<input type="date" name="until" value="{esc(until)}" aria-label="To"></form>')
    if not (q.strip() or since or until):
        first = f" since {time.strftime('%-d %b %Y', time.localtime(kept['first_ms'] / 1000))}" if kept.get("first_ms") else ""
        body = (f'<p class="hits">{kept.get("posts", 0)} posts kept from {kept.get("runs", 0)} briefs{esc(first)}. '
                f'Every word must appear; @name picks an account.</p>')
    elif not hits:
        body = '<p class="hits">No post matches. Fewer words, or a wider range of dates.</p>'
    else:
        out, last_day = [], None
        for p, run in hits:
            d = time.strftime("%a %-d %b %Y", time.localtime(p.created_ms / 1000))
            if d != last_day:
                out.append(f'<h3 class="day">{esc(d)}</h3>')
                last_day = d
            also = (f'<a class="from" href="/b/{esc(run)}">{esc(titles.get(run, run))}</a>' if run else "")
            out.append(post_html(p, also))
        n = f"{len(hits)} post{'s' if len(hits) != 1 else ''}" + (", the newest shown; narrow the search for the rest" if cut else "")
        body = f'<p class="hits">{esc(n)}</p>' + "".join(out)
    return shell(f"X brief · {q or 'search'}", rail("search", live, running=running), form + body)
