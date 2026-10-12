"""The brief as a static page, served by Caddy from ~/Data/xbrief-data/briefs/ at xbrief.localhost.

No script runs on it (the content policy allows none); images load from X's image servers only. Every piece of
post text is escaped, and every link and byline is built here from the posts, never from Claude's words.
Tokyo Night / Tokyo Day like the other local pages; Iowan Old Style (on every Mac) to read, a mono for handles.
"""

from __future__ import annotations

import html
import re
import time
from collections import Counter

from .brief import Brief, Item
from .parse import Entry, Post

CSP = ("default-src 'none'; img-src https://pbs.twimg.com; style-src 'unsafe-inline'; "
       "base-uri 'none'; form-action 'none'")

CSS = """
:root{--bg:#e1e2e7;--panel:#d5d6db;--fg:#3760bf;--ink:#343b58;--dim:#6172b0;--rule:#c4c8da;
--link:#2e7de9;--warn:#b15c00;--bad:#f52a65;--ok:#587539;color-scheme:light}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#1a1b26;--panel:#16161e;--fg:#7aa2f7;
--ink:#c0caf5;--dim:#737aa2;--rule:#292e42;--link:#7dcfff;--warn:#ff9e64;--bad:#f7768e;--ok:#9ece6a;color-scheme:dark}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:17px/1.55 "Iowan Old Style","New York",ui-serif,Georgia,serif;
-webkit-font-smoothing:antialiased}
a{color:var(--link);text-decoration-thickness:1px;text-underline-offset:2px}
a:focus-visible,summary:focus-visible{outline:2px solid var(--link);outline-offset:2px}
.mono,.rail,.by,.meta,.status,summary{font-family:"SF Mono",ui-monospace,Menlo,monospace}
.wrap{display:grid;grid-template-columns:minmax(200px,260px) minmax(0,46rem);gap:4rem;justify-content:center;
padding:3rem 2rem 6rem}
.rail{position:sticky;top:2rem;align-self:start;font-size:12.5px;line-height:1.5;color:var(--dim)}
.rail h1{font:600 13px/1.3 "SF Mono",ui-monospace,Menlo,monospace;color:var(--fg);margin:0 0 .2rem;letter-spacing:.02em}
.rail .when{margin:0 0 1.6rem}
.rail ol,.rail ul{list-style:none;margin:0 0 1.8rem;padding:0}
.rail li{display:flex;justify-content:space-between;gap:1rem;padding:.12rem 0}
.rail li a{color:var(--ink);text-decoration:none}.rail li a:hover{color:var(--link)}
.rail .n{color:var(--dim)}
.rail h2{font:inherit;text-transform:uppercase;letter-spacing:.08em;font-size:11px;margin:0 0 .5rem;color:var(--dim)}
.status{font-size:13px;padding:.7rem .9rem;border-left:3px solid var(--warn);background:var(--panel);margin:0 0 2.5rem;color:var(--ink)}
.status.bad{border-color:var(--bad)}.status.quiet{border-color:var(--ok);background:none;padding-left:.9rem;color:var(--dim)}
.status b{color:var(--warn)}.status.bad b{color:var(--bad)}
section{margin:0 0 3rem}
section>h2{font:600 1.45rem/1.25 "Iowan Old Style","New York",ui-serif,Georgia,serif;color:var(--fg);margin:0 0 1.1rem;
padding-bottom:.4rem;border-bottom:1px solid var(--rule)}
.item{margin:0 0 1.35rem}
.item p{margin:0}
.by{display:block;font-size:12px;color:var(--dim);margin-top:.25rem}
.by a{color:var(--dim);text-decoration:none}.by a:hover{color:var(--link)}
details{margin-top:.35rem}
summary{cursor:pointer;font-size:12px;color:var(--dim);list-style:none}
summary::-webkit-details-marker{display:none}
summary::before{content:"+ ";}details[open]>summary::before{content:"− "}
.post{border-left:1px solid var(--rule);padding:.5rem 0 .5rem 1rem;margin:.5rem 0 0;font-size:15.5px}
.post .meta{font-size:12px;color:var(--dim);display:flex;gap:.8rem;flex-wrap:wrap;margin-bottom:.15rem}
.post .meta a{color:var(--dim)}
.post .t{white-space:pre-wrap;overflow-wrap:anywhere}
.post .q{margin:.5rem 0 0;padding:.4rem .8rem;background:var(--panel);border-radius:4px;font-size:14.5px}
.imgs{display:flex;flex-wrap:wrap;gap:.4rem;margin-top:.5rem}
.imgs a{position:relative;display:block}
.imgs img{display:block;max-height:240px;max-width:100%;border-radius:4px;background:var(--panel)}
.imgs .v{position:absolute;left:.4rem;bottom:.4rem;font:11px "SF Mono",ui-monospace,Menlo,monospace;
background:#000a;color:#fff;padding:.1rem .35rem;border-radius:3px}
.empty{color:var(--dim)}
@media (max-width:860px){.wrap{grid-template-columns:minmax(0,1fr);gap:1.5rem;padding:1.5rem 16px 4rem}
.rail{position:static}.rail ol{columns:2}}
@media (prefers-reduced-motion:reduce){*{transition:none!important}}
"""


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


def post_html(p: Post) -> str:
    if p.unreadable:
        return (f'<div class="post"><div class="meta"><a href="{esc(p.url)}" rel="noreferrer">a post X would not show '
                f'({esc(p.unreadable)})</a></div></div>')
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
            f'<span>{esc(shown.name)}</span><span>{day(shown.created_ms)}</span>{lead}{reply}</div>'
            f'<div class="t">{rich_text(shown)}</div>{imgs(shown)}{quote}</div>')


def threads(entries: list[Entry]) -> dict[str, list[Post]]:
    """Post id → its whole conversation, for conversations of three posts or more."""
    out: dict[str, list[Post]] = {}
    for e in entries:
        if len(e.posts) >= 3:
            for p in e.posts:
                out.setdefault(p.id, e.posts)
    return out


def item_html(it: Item, posts: dict[str, Post], thr: dict[str, list[Post]]) -> str:
    shown: list[Post] = []
    ids: set[str] = set()
    is_thread = False
    for pid in it.posts:
        group = thr.get(pid)
        if group:
            is_thread = True
        for p in group or [posts[pid]]:
            if p.id not in ids:
                ids.add(p.id)
                shown.append(p)
    first: dict[str, Post] = {}  # each author once, linked to their first post in the item
    for pid in it.posts:
        p = posts[pid].retweet_of or posts[pid]
        first.setdefault(p.handle, p)
    by = " · ".join(f'<a href="{esc(p.url)}" rel="noreferrer">@{esc(h)}</a>' for h, p in first.items())
    label = "thread" if is_thread else ("post" if len(shown) == 1 else f"{len(shown)} posts")
    return (f'<div class="item"><p>{esc(it.summary)}</p><span class="by">{by}</span>'
            f'<details{" open" if is_thread else ""}><summary>{esc(label)}</summary>'
            f'{"".join(post_html(p) for p in shown)}</details></div>')


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


def render(b: Brief, posts: dict[str, Post], entries: list[Entry], meta: dict, title: str,
           archive: list[tuple[str, str]]) -> str:
    thr = threads(entries)
    accounts = Counter(p.handle for p in posts.values())  # who I follow; a repost counts as the reposter
    sections, toc = [], []
    for i, (topic, items) in enumerate(b.topics):
        sid = f"t{i}"
        toc.append(f'<li><a href="#{sid}">{esc(topic)}</a><span class="n">{len(items)}</span></li>')
        sections.append(f'<section id="{sid}"><h2>{esc(topic)}</h2>{"".join(item_html(it, posts, thr) for it in items)}</section>')
    rest = list(b.other)
    if b.unplaced:
        rest += [Item("", [pid]) for pid in sorted(b.unplaced, key=lambda x: -posts[x].created_ms)]
    if rest:
        toc.append(f'<li><a href="#other">Everything else</a><span class="n">{len(rest)}</span></li>')
        body = "".join(item_html(it, posts, thr) if it.summary else
                       f'<div class="item">{post_html(posts[it.posts[0]])}</div>' for it in rest)
        sections.append(f'<section id="other"><h2>Everything else</h2>{body}</section>')
    if not posts:
        sections.append('<p class="empty">Nothing new from the accounts you follow since the last brief.</p>')
    arch = "".join(f'<li><a href="{esc(href)}">{esc(name)}</a></li>' for name, href in archive)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="{CSP}"><meta name="referrer" content="no-referrer">
<title>{esc(title)}</title><style>{CSS}</style></head>
<body><div class="wrap"><nav class="rail"><h1>{esc(title)}</h1>
<p class="when">{day(meta.get('started_ms') or int(time.time() * 1000))}</p>
<h2>Topics</h2><ol>{"".join(toc)}</ol>{f'<h2>Earlier</h2><ul>{arch}</ul>' if arch else ''}</nav>
<main>{status_html(meta, b, len(posts), len(accounts))}{"".join(sections)}</main></div></body></html>
"""
