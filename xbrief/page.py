"""The app's pages, built on the server: a brief, its theses, the history of briefs, and search over every post kept.

Every piece of post text is escaped, and every link and byline is built here from the posts, never from Claude's
words. The one script is the app's own (static/app.js: the run button, its progress, the schedule form); the
server's Content-Security-Policy allows no other, and images load from X's image servers only.
Tokyo Night / Tokyo Day like the other local pages; Iowan Old Style (on every Mac) to read, a mono for handles.
"""

from __future__ import annotations

import html
import re
import time
from urllib.parse import quote, urlencode

from . import config
from .brief import Brief, Thesis, Topic
from .parse import Post

CSP = ("default-src 'none'; img-src https://pbs.twimg.com; style-src 'self'; script-src 'self'; connect-src 'self'; "
       "base-uri 'none'; form-action 'self'; frame-ancestors 'none'")
LABELS = {"am": "morning", "pm": "evening"}
HOURS = [("", "since last"), ("12", "last 12 h"), ("24", "last 24 h"), ("48", "last 48 h")]
POST_REF = re.compile(r"\s*\[\[(\d{1,25})\]\]")  # the writer's pointer at a post that stands out


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


def marked(text: str, words: list[str]) -> str:
    """Escaped post text with each searched word marked where a word begins with it, as the search matches; never
    inside a link's markup or an escape."""
    ws = [w for w in (re.sub(r"\W+", "", w) for w in words) if w]
    if not ws:
        return text
    pat = re.compile(r"(<[^>]*>|&#?\w+;)|(?<!\w)(" + "|".join(re.escape(esc(w)) for w in ws) + ")", re.I)
    return pat.sub(lambda m: m.group(1) or f"<mark>{m.group(2)}</mark>", text)


def post_html(p: Post, also: str = "", words: list[str] | None = None) -> str:
    """One post; `also` is a piece of markup added at the end of its byline (search: the brief it came from), and
    `words` the searched words, marked in its text."""
    if p.unreadable:
        return (f'<div class="post"><div class="meta"><a href="{esc(p.url)}" rel="noreferrer">a post X would not show '
                f'({esc(p.unreadable)})</a>{also}</div></div>')
    shown, lead = p, ""
    if p.retweet_of:
        shown = p.retweet_of
        lead = f'<span>reposted by @{esc(p.handle)}</span>'
    reply = f'<span>replying to @{esc(shown.reply_to_handle)}</span>' if shown.reply_to_handle else ""
    words = words or []
    quote = ""
    if shown.quote and not shown.quote.unreadable:
        q = shown.quote
        quote = (f'<div class="q"><div class="meta"><a href="{esc(q.url)}" rel="noreferrer">@{esc(q.handle)}</a>'
                 f'<span>{day(q.created_ms)}</span></div><div class="t">{marked(rich_text(q), words)}</div>{imgs(q)}</div>')
    name = f'<b>{esc(shown.name)}</b>' if shown.name and shown.name != shown.handle else ""
    return (f'<div class="post"><div class="meta">{name}<a href="{esc(shown.url)}" rel="noreferrer">@{esc(shown.handle)}</a>'
            f'<span>{day(shown.created_ms)}</span>{lead}{reply}{also}</div>'
            f'<div class="t">{marked(rich_text(shown), words)}</div>{imgs(shown)}{quote}</div>')


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


class Notes:
    """Numbers the margin notes down one page, 1, 2, 3, in reading order."""

    def __init__(self) -> None:
        self.n = 0

    def next(self) -> int:
        self.n += 1
        return self.n


def opening(p: Post, limit: int = 180) -> str:
    """A post's first words for a margin note: its text without links, cut at a word near `limit`."""
    text = re.sub(r"\s*https?://\S+", "", p.text or "").strip()
    text = re.sub(r"\s+", " ", text)
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0].rstrip(",.;:—-") + "…"


def linked(text: str, posts: dict[str, Post], notes: Notes | None = None) -> str:
    """A summary, escaped, each [[post id]] made a small link to that post on X; an id not in this brief is dropped.
    With `notes`, the link carries a number and the post itself goes in the margin beside the sentence: name,
    @handle, time and its opening words (wide screens only; narrow ones keep the ↗). Built from the post, never
    from the writer's words."""
    def go(m: re.Match) -> str:
        p = posts.get(m.group(1))
        if not p:
            return ""
        shown = p.retweet_of or p
        url = esc(shown.url)
        link = (f'<a class="go" href="{url}" rel="noreferrer" title="the post on X" aria-label="the post on X">'
                + (f'<span class="num">{notes.next()}</span>' if notes else "") + '<span class="arr">↗</span></a>')
        if not notes:
            return "&nbsp;" + link
        name = f'<b>{esc(shown.name)}</b> ' if shown.name and shown.name != shown.handle else ""
        return (f'{link}<span class="sn"><span class="sn-by"><span class="sn-n">{notes.n}</span>{name}'
                f'<a href="{url}" rel="noreferrer">@{esc(shown.handle)}</a> · {hhmm(shown.created_ms)}</span>'
                f'<span class="sn-t">{esc(opening(shown))}</span></span>')
    return POST_REF.sub(go, esc(text))


def lead(html_text: str, words: int = 3) -> str:
    """A section's opening: its first few words set in small caps, as a book opens a section."""
    return re.sub(r"^((?:[^\s<&]+\s+){0,%d}[^\s<&]+)" % (words - 1), r'<span class="nt">\1</span>', html_text, count=1)


def folded(ids: list[str], posts: dict[str, Post], thr: dict[str, list[Post]]) -> str:
    """The posts behind a paragraph, folded under a line that says how many and whose."""
    shown = topic_posts([i for i in ids if i in posts], posts, thr)
    if not shown:
        return ""
    handles = list(dict.fromkeys((p.retweet_of or p).handle for p in shown))
    who = ", ".join(f"@{h}" for h in handles[:6]) + (f" and {len(handles) - 6} more" if len(handles) > 6 else "")
    label = f"{len(shown)} post{'s' if len(shown) != 1 else ''} · {who}"
    return f'<details><summary>{esc(label)}</summary>{"".join(post_html(p) for p in shown)}</details>'


def topic_html(t: Topic, posts: dict[str, Post], thr: dict[str, list[Post]], notes: Notes | None = None) -> str:
    return f'<p>{lead(linked(t.summary, posts, notes))}</p>{folded(t.posts, posts, thr)}'


def bar(n: int, most: int) -> str:
    """A topic's share of the brief, drawn as a short bar beside its count: the big stories stand out unread."""
    w = max(4, round(100 * n / most)) if most else 0
    return f'<svg class="bar" viewBox="0 0 100 4" preserveAspectRatio="none" aria-hidden="true"><rect width="{w}" height="4"/></svg>'


def thesis_html(t: Thesis, posts: dict[str, Post], thr: dict[str, list[Post]], sid: str, h: int = 2) -> str:
    """One thesis: the claim, the argument as posted, what follows if it holds, then Claude's view under its own
    label (the only opinion in a brief), and the post itself, folded."""
    first = posts.get(t.posts[0]) if t.posts else None
    shown = (first.retweet_of or first) if first else None
    by = (f'<p class="by"><a href="{esc(shown.url)}" rel="noreferrer">@{esc(shown.handle)}</a> · '
          f'{day(shown.created_ms)}</p>' if shown else "")
    steps = "".join(f"<li>{esc(x)}</li>" for x in t.steps)
    view = "".join(f"<p><b>{k}</b> {esc(v)}</p>" for k, v in (("Weak spots", t.weak_spots), ("Wrong if", t.wrong_if)) if v)
    sub = f"h{h + 1}"
    return (f'<section id="{sid}" class="thesis"><h{h}>{esc(t.claim)}</h{h}>{by}'
            + (f'<{sub}>Argument</{sub}><ol class="steps">{steps}</ol>' if steps else "")
            + (f'<{sub}>If it holds</{sub}><p>{esc(t.if_it_holds)}</p>' if t.if_it_holds else "")
            + (f'<div class="view"><{sub}>Claude\'s view</{sub}>{view}</div>' if view else "")
            + folded(t.posts, posts, thr) + "</section>")


def author(t: Thesis, posts: dict[str, Post]) -> str:
    p = posts.get(t.posts[0]) if t.posts else None
    return f"@{(p.retweet_of or p).handle}" if p else ""


def masthead(title: str, dek: str, strip: str = "") -> str:
    return f'<header class="mast"><h1>{title}</h1>{strip}<p class="dek">{dek}</p></header>'


def run_dek(meta: dict, n_posts: int, n_accounts: int) -> str:
    """How much the run read and when."""
    dek = (f"{n_posts} posts from {n_accounts} accounts · "
           f"read {hhmm(meta.get('started_ms') or 0)}–{hhmm(meta.get('finished_ms') or 0)}")
    if meta.get("reread_site"):
        dek += f" · X deployed a new site; its request was read again ({esc(meta.get('build'))})"
    return dek


def window_strip(meta: dict, posts: dict[str, Post], hype: set[str]) -> str:
    """The window the read covered, from the last brief's newest post to the end of the read, a tick at each post's
    time and HYPE's in mint: a quiet night, a busy hour or a hole shows at a glance. Drawn on the server, no script."""
    from .parse import snowflake_ms

    times = [p.created_ms for p in posts.values() if p.created_ms]
    if not times:
        return ""
    lo = snowflake_ms(meta["boundary_id"]) if meta.get("boundary_id") else min(times)
    hi = max(meta.get("finished_ms") or 0, max(times))
    if hi <= lo:
        return ""
    span = hi - lo
    ticks = []
    for pid, p in sorted(posts.items(), key=lambda kv: kv[0] in hype):  # HYPE's drawn last, on top
        if not p.created_ms or p.created_ms < lo:
            continue
        x = (p.created_ms - lo) / span * 1000
        ticks.append(f'<rect class="h" x="{x:.1f}" y="0" width="2.4" height="30"/>' if pid in hype
                     else f'<rect x="{x:.1f}" y="9" width="1.6" height="21"/>')
    hours = []  # a faint mark on each local hour, for scale
    t = (lo // 3_600_000 + 1) * 3_600_000
    while t < hi:
        hours.append(f'<rect class="hr" x="{(t - lo) / span * 1000:.1f}" y="30" width="1" height="5"/>')
        t += 3_600_000
    since = f"since {day(lo)}" if meta.get("boundary_id") else f"from {day(lo)}"
    return (f'<figure class="strip" aria-label="When the {len(times)} posts were made, {since} to {hhmm(hi)}">'
            f'<svg viewBox="0 0 1000 35" preserveAspectRatio="none" aria-hidden="true">'
            f'<rect class="base" x="0" y="30" width="1000" height="1"/>{"".join(hours)}{"".join(ticks)}</svg>'
            f'<figcaption><span>{since}</span><span>{hhmm(hi)}</span></figcaption></figure>')


def status_html(meta: dict, b: Brief) -> str:
    """Said only when something went wrong: how the read ended, a gap, the order, a missing summary."""
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
    if not lines:
        return ""
    cls = "bad" if not meta.get("page_count") else "warn"
    return f'<div class="status {cls}" role="status">{"<br>".join(lines)}</div>'




# ── the app's frame ─────────────────────────────────────────────────────────────────────────────────


def run_title(name: str, label: str, started_ms: int) -> str:
    return f"{time.strftime('%a %-d %b', time.localtime(started_ms / 1000))} · {LABELS.get(label, label)}"


def run_when(started_ms: int) -> str:
    """A run in a list: its day and the minute it started, which tells two runs of one morning apart."""
    return time.strftime("%a %-d %b %H:%M", time.localtime(started_ms / 1000))


def run_head(label: str, started_ms: int) -> str:
    """A brief's headline: the day in full and the part of it."""
    return (f"{time.strftime('%A %-d %B', time.localtime(started_ms / 1000))} "
            f"<span>{esc(LABELS.get(label, label))}</span>")


def live_html(live: dict) -> str:
    cls = {"on": " on", "bad": " bad"}.get(live.get("kind", ""), "")
    text = esc(live.get("text"))
    if live.get("href"):
        text = f'{text} <a href="{esc(live["href"])}">{esc(live.get("link") or "open")}</a>'
    return f'<p class="live{cls}" id="live" aria-live="polite">{text}</p>'


def rail(active: str, live: dict, extra: str = "", running: bool = False, at: str = "") -> str:
    """`at`: the brief on show, so Brief and Theses stay on it; elsewhere they open the newest."""
    tabs = "".join(f'<a href="{href}"{" aria-current=page" if key == active else ""}>{name}</a>'
                   for key, href, name in (("brief", f"/b/{esc(at)}" if at else "/", "Brief"),
                                           ("theses", f"/b/{esc(at)}/theses" if at else "/theses", "Theses"),
                                           ("sites", "/sites", "Sites"),
                                           ("history", "/history", "History")))
    opts = "".join(f'<option value="{v}">{esc(t)}</option>' for v, t in HOURS)
    return (f'<nav class="rail"><p class="brand"><a href="/">X brief</a></p><p class="tabs">{tabs}</p>'
            + ("" if active == "search" else  # the search page has its own form
               f'<form class="find ctl" action="/search" method="get" role="search">'
               f'<input type="search" name="q" placeholder="Search posts" aria-label="Search posts"></form>')
            + f'<form class="run ctl" id="run"><select name="hours" aria-label="What to read">{opts}</select>'
            f'<button type="submit"{" disabled" if running else ""}>Brief now</button></form>'
            f'{live_html(live)}{extra}</nav>')


def shell(title: str, rail_html: str, main: str, at: str = "", side: str = "") -> str:
    """`at`: the brief this page shows, so the rail does not offer it as new; `side`: a right-hand column."""
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="referrer" content="no-referrer"><title>{esc(title)}</title>
<link rel="stylesheet" href="/app.css"><script src="/app.js" defer></script></head>
<body{f' data-at="{esc(at)}"' if at else ""}><div class="wrap{" has-side" if side else ""}">{rail_html}<main>{main}</main>{side}</div></body></html>
"""


# ── a brief ─────────────────────────────────────────────────────────────────────────────────────────


def brief_main(b: Brief, posts: dict[str, Post], thr: dict[str, list[Post]], meta: dict,
               name: str = "") -> tuple[str, list[str]]:
    """The brief's body and the rail's list of its parts: HYPE, a line for each thesis (written up on the Theses
    tab), the topics, everything else."""
    sections, toc = [], []
    notes = Notes()
    on_hype = [t for t in b.theses if t.hype]
    n_hype = len(b.hype.posts if b.hype else []) + sum(len(t.posts) for t in on_hype)
    most = max([n_hype] + [len(t.posts) for t in b.topics])  # the bars' scale: the biggest story
    if b.hype or on_hype:
        toc.append(f'<li><a href="#hype">HYPE</a>{bar(n_hype, most)}<span class="n">{n_hype}</span></li>')
        sections.append('<section id="hype" class="hype"><h2>HYPE</h2>'
                        + (f'<p>{lead(linked(b.hype.summary, posts, notes))}</p>{folded(b.hype.posts, posts, thr)}'
                           if b.hype else "")
                        + "".join(thesis_html(t, posts, thr, f"h{i}", 3) for i, t in enumerate(on_hype)) + "</section>")
    theses = [t for t in b.theses if not t.hype]
    if theses:
        base = f"/b/{esc(name)}/theses" if name else "/theses"
        items = "".join(f'<li><a href="{base}#th{i}">{esc(t.claim)}</a> <span class="by">{esc(author(t, posts))}</span></li>'
                        for i, t in enumerate(theses))
        toc.append(f'<li><a href="#theses">Theses</a><span class="n">{len(theses)}</span></li>')
        sections.append(f'<section id="theses"><h2>Theses</h2><ol class="theses">{items}</ol></section>')
    for i, t in enumerate(b.topics):
        sid = f"t{i}"
        toc.append(f'<li><a href="#{sid}">{esc(t.title)}</a>{bar(len(t.posts), most)}<span class="n">{len(t.posts)}</span></li>')
        sections.append(f'<section id="{sid}"><h2>{esc(t.title)}</h2>{topic_html(t, posts, thr, notes)}</section>')
    if b.other:
        rest = topic_posts([i for i in b.other if i in posts], posts, thr)
        toc.append(f'<li><a href="#other">Everything else</a><span class="n">{len(rest)}</span></li>')
        sections.append(f'<section id="other"><h2>Everything else</h2><p class="empty">Memes, pictures, one-liners '
                        f'and reposts with nothing to add: {len(rest)} posts, as read.</p>'
                        f'<details><summary>{len(rest)} posts</summary>{"".join(post_html(p) for p in rest)}</details></section>')
    if not posts:
        sections.append('<p class="empty">Nothing new from the accounts you follow since the last brief.</p>')
    return status_html(meta, b) + "".join(sections), toc


def brief_page(run: dict, earlier: list[dict], live: dict, running: bool = False) -> str:
    meta = run["meta"]
    title = run_title(run["name"], run["label"], meta.get("started_ms") or 0)
    main, toc = brief_main(run["brief"], run["posts"], run["threads"], meta, run["name"])
    accounts = len({p.handle for p in run["posts"].values()})  # who I follow; a repost counts as the reposter
    b = run["brief"]
    hype = set(b.hype.posts if b.hype else []) | {i for t in b.theses if t.hype for i in t.posts}
    main = masthead(run_head(run["label"], meta.get("started_ms") or 0), run_dek(meta, len(run["posts"]), accounts),
                    window_strip(meta, run["posts"], hype)) + main
    # older than this one, and briefs only: a run that read nothing is on History with what stopped it
    others = [r for r in earlier if r["started_ms"] < (meta.get("started_ms") or 0)
              and ending(r["meta"], r.get("writer_error"))[1] != "bad"][:10]
    arch = "".join(f'<li><a href="/b/{esc(r["name"])}">{esc(run_when(r["started_ms"]))}</a>'
                   f'<span class="n">{r["n_posts"]}</span></li>' for r in others)
    extra = (f'<ol class="toc">{"".join(toc)}</ol>'
             + (f'<h2>Earlier</h2><ul>{arch}</ul><a class="more" href="/history">All briefs</a>' if arch else ""))
    return shell(f"X brief · {title}", rail("brief", live, extra, running=running, at=run["name"]), main, at=run["name"])


def theses_page(run: dict, live: dict, running: bool = False) -> str:
    """Every thesis of one brief written up, longest first; those about HYPE are on the Brief, in its HYPE part."""
    meta, b = run["meta"], run["brief"]
    title = run_title(run["name"], run["label"], meta.get("started_ms") or 0)
    theses = [t for t in b.theses if not t.hype]
    main = "".join(thesis_html(t, run["posts"], run["threads"], f"th{i}") for i, t in enumerate(theses))
    if not theses:
        main = '<p class="empty">No theses in this brief.</p>'
    on_hype = sum(t.hype for t in b.theses)
    if on_hype:
        main += (f'<p class="note">{on_hype} more about HYPE: <a href="/b/{esc(run["name"])}#hype">the Brief\'s '
                 f'HYPE part</a>.</p>')
    n = f"{len(theses)} thes{'is' if len(theses) == 1 else 'es'}" if theses else "none"
    main = masthead(f'Theses <span>{esc(title)}</span>', f'{n} · longest first') + main
    toc = "".join(f'<li><a href="#th{i}">{esc(t.claim)}</a></li>' for i, t in enumerate(theses))
    extra = f'<ol class="claims toc">{toc}</ol>' if toc else ""
    return shell(f"X brief · theses · {title}", rail("theses", live, extra, running=running, at=run["name"]), main,
                 at=run["name"])


def empty_page(live: dict, running: bool = False, active: str = "brief") -> str:
    main = ('<p class="empty">No brief yet. <b>Brief now</b> reads your Following tab in the job\'s Brave and '
            'writes the first one; it takes a few minutes.</p>')
    return shell("X brief", rail(active, live, running=running), main)


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
    return "", ""


def history_page(runs: list[dict], sett: dict, today: dict, live: dict, running: bool = False) -> str:
    rows = []
    for r in runs:
        end, cls = ending(r["meta"], r.get("writer_error"))
        n = f'{r["n_posts"]} posts · {r["n_topics"]} topics'
        if cls == "bad":
            n = "read nothing"
        rows.append(f'<li class="{cls}"><a href="/b/{esc(r["name"])}">{esc(run_when(r["started_ms"]))}</a>'
                    f'<span class="lb">{esc(LABELS.get(r["label"], r["label"]))}</span><span class="n">{n}</span>'
                    + (f'<span class="end {cls}">{esc(end)}</span>' if end else "") + '</li>')
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
    briefs = ('<section><h2>Briefs</h2>'
              + (f'<ol class="runs">{"".join(rows)}</ol>' if rows else '<p class="empty">No brief yet.</p>')
              + '</section>')
    main = (briefs + f'<section id="schedule"><h2>Schedule</h2>'
            f'<form class="sched ctl" id="sched"><label><input type="checkbox" name="on"'
            f'{" checked" if sett["schedule"] else ""}> Two briefs a day</label>{win}'
            f'<button type="submit">Save</button></form>'
            f'<p class="note" id="sched-msg">Each run starts at a random minute inside its window.</p>{today_line}</section>')
    return shell("X brief · history", rail("history", live, running=running), main)


# ── search ──────────────────────────────────────────────────────────────────────────────────────────


def store_words(q: str) -> list[str]:
    from .store import parse_query

    return parse_query(q)[1]


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
            out.append(post_html(p, also, store_words(q)))
        n = f"{len(hits)} post{'s' if len(hits) != 1 else ''}" + (", the newest shown; narrow the search for the rest" if cut else "")
        body = f'<p class="hits">{esc(n)}</p>' + "".join(out)
    return shell(f"X brief · {q or 'search'}", rail("search", live, running=running), form + body)


# ── sites ───────────────────────────────────────────────────────────────────────────────────────────


def x_links(handles: list[str]) -> str:
    return " ".join(f'<a href="https://x.com/{esc(h)}" rel="noreferrer">@{esc(h)}</a>' for h in handles)


def sites_href(key: str = "", q: str = "") -> str:
    args = urlencode([(k, v) for k, v in (("s", key), ("q", q)) if v])
    return "/sites" + ("?" + args if args else "")


def site_post_html(d: dict, names: dict[str, str], i: int, people: dict[str, list[str]] | None = None,
                   words: list[str] | None = None, lines: list[str] | None = None) -> str:
    """One post from a site: its title linked to the page, the gist, the points, the calls it makes, and Claude's
    view under its own label; with a search, the article's lines that hold the words. The link is the stored
    address, and only an http(s) one."""
    url = safe_url(d.get("url"))
    title = esc(d.get("title") or d.get("url"))
    head = f'<a href="{esc(url)}" rel="noreferrer">{title}</a>' if url else title
    when = d.get("published_ms") or d.get("seen_ms") or 0
    who = (people or {}).get(d.get("source")) or []
    by = (f'<p class="by">{esc(names.get(d.get("source"), d.get("source")))} · '
          + (x_links(who) + " · " if who else "") +
          f'{time.strftime("%a %-d %b %Y", time.localtime(when / 1000))}</p>')
    found = "".join(f"<li>{marked(esc(x), words or [])}</li>" for x in lines or [])
    found = f'<h3>In the article</h3><ul class="steps found">{found}</ul>' if found else ""
    s = d.get("summary") or {}
    if d.get("error") or not s:
        return (f'<section id="s{i}" class="thesis site"><h2>{head}</h2>{by}{found}'
                f'<p class="empty">No summary ({esc(d.get("error") or "nothing came back")}). Open the post to read it.</p></section>')
    points = "".join(f"<li>{esc(x)}</li>" for x in s.get("points") or [])
    calls = "".join(f"<li>{esc(x)}</li>" for x in s.get("calls") or [])
    return (f'<section id="s{i}" class="thesis site"><h2>{head}</h2>{by}'
            + (f'<p>{esc(s["gist"])}</p>' if s.get("gist") else "") + found
            + (f'<h3>Points</h3><ol class="steps">{points}</ol>' if points else "")
            + (f'<h3>Calls</h3><ul class="steps">{calls}</ul>' if calls else "")
            + (f'<div class="view"><h3>Claude\'s view</h3><p>{esc(s["view"])}</p></div>' if s.get("view") else "")
            + "</section>")


def side_html(xposts: list[Post], posts: list[dict], handles: list[str], q: str, words: list[str]) -> str:
    """The right-hand column: the people's posts on X, newest first, with a mark where each write-up falls among
    them, so what they said before and after it reads in order."""
    if not handles:
        return ('<aside class="side"><h2>On X</h2><p class="empty">No one from this source is followed on X.</p>'
                '</aside>')
    items = [(p.created_ms, 1, post_html(p, words=words)) for p in xposts]
    for i, d in enumerate(posts):
        when = d.get("published_ms") or d.get("seen_ms") or 0
        items.append((when, 0, f'<p class="mk"><a href="#s{i}">{esc(d.get("title") or d.get("url"))}</a>'
                               f'<span>{time.strftime("%-d %b %Y", time.localtime(when / 1000))}</span></p>'))
    items.sort(key=lambda t: (t[0], t[1]), reverse=True)
    find = " ".join(["@" + h for h in handles] + ([q] if q else []))
    empty = (f'<p class="empty">Nothing by them{" with these words" if words else ""} in what the briefs have '
             f'read.</p>' if not xposts else "")
    return (f'<aside class="side"><h2>On X</h2><p class="by">{x_links(handles)} · '
            f'<a href="/search?q={esc(quote(find))}">Every post kept</a></p>{empty}{"".join(h for _, _, h in items)}'
            f'</aside>')


def sites_page(posts: list[dict], sources: list[dict], sett: dict, counts: dict[str, int], checking: bool,
               live: dict, running: bool = False, xposts: list[Post] | None = None, key: str = "", q: str = "",
               words: list[str] | None = None, lines: dict[str, list[str]] | None = None) -> str:
    """The write-ups in the middle, newest first, and their people's posts on X on the right; narrowed to one
    source (`key`) and to the words searched (`q`), the write-ups showing the article's lines that hold them. Below,
    the list itself, when each was last checked, and the daily check's switch."""
    words, lines = words or [], lines or {}
    names = {s["key"]: s["name"] for s in sources}
    shown = [s for s in sources if not key or s["key"] == key]
    handles = [h for s in shown for h in s.get("x") or []]
    state = sett.get("sites_state") or {}
    people = {s["key"]: s.get("x") or [] for s in sources}
    find = (f'<form class="find ctl sitefind" action="/sites" method="get" role="search">'
            + (f'<input type="hidden" name="s" value="{esc(key)}">' if key else "")
            + f'<input type="search" name="q" value="{esc(q)}" placeholder="Search {esc(names[key]) if key else "the sites"}'
            f' and their people on X" aria-label="Search the sites"></form>')
    main = "".join(site_post_html(d, names, i, people, words, lines.get(d["url"])) for i, d in enumerate(posts))
    if not posts:
        main = ('<p class="empty">No write-up holds these words.</p>' if words else
                '<p class="empty">Nothing read yet. <b>Check now</b> reads each site\'s list and its newest post.</p>')
    rows = []
    for s in sources:
        st = state.get(s["key"]) or {}
        if st.get("error"):
            note, cls = f"could not read its list: {st['error']}", "bad"
        elif st.get("checked_ms"):
            note, cls = f"checked {day(st['checked_ms'])} · {st.get('new', 0)} new · {counts.get(s['key'], 0)} known", ""
        else:
            note, cls = "not checked yet", ""
        rows.append(f'<li><a href="{esc(safe_url(s["home"]) or "")}" rel="noreferrer">{esc(s["name"])}</a>'
                    f'<span class="n">{x_links(s.get("x") or [])}</span><span class="end {cls}">{esc(note)}</span></li>')
    last = sett.get("sites_checked_ms")
    line = ("Checking the sites now…" if checking else
            f"Last checked {day(last)}." if last else "Not checked yet.")
    ctl = (f'<form class="sched ctl" id="sites"><label><input type="checkbox" name="daily"'
           f'{" checked" if sett.get("sites_daily", True) else ""}> Check once a day, after {esc(config.SITES_AFTER)}</label>'
           f'<div class="w2"><button type="submit" name="act" value="save">Save</button>'
           f'<button type="button" id="sites-now"{" disabled" if checking else ""}>Check now</button></div></form>'
           f'<p class="note" id="sites-msg"{" data-checking=1" if checking else ""}>{esc(line)}</p>')
    pick = "".join(f'<li><a href="{esc(sites_href(k, q))}"{" aria-current=page" if k == key else ""}>{esc(n)}</a></li>'
                   for k, n in [("", "All")] + [(s["key"], s["name"]) for s in sources])
    toc = "".join(f'<li><a href="#s{i}">{esc(d.get("title") or d.get("url"))}</a></li>' for i, d in enumerate(posts[:40]))
    extra = f'<h2>Sources</h2><ol class="claims pick">{pick}</ol>' + (f'<h2>Posts</h2><ol class="claims">{toc}</ol>' if toc else "")
    main = (find + main + f'<section id="list"><h2>The list</h2><ol class="runs">{"".join(rows)}</ol>{ctl}'
            f'<p class="note">New sites are added in xbrief/config.py (SITES): an RSS feed or a sitemap.</p></section>')
    return shell("X brief · sites", rail("sites", live, extra, running=running), main,
                 side=side_html(xposts or [], posts, handles, q, words))
