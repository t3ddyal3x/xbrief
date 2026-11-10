"""The app's pages, built on the server: a brief, the history of briefs, search over every post kept, and the sites.

Every piece of post text is escaped, and every link and byline is built here from the posts, never from Claude's
words. The one script is the app's own (static/app.js: the run button, its progress, the schedule form); the
server's Content-Security-Policy allows no other, and images load from X's image servers only.
Tokyo Night / Tokyo Day like the other local pages; Iowan Old Style (on every Mac) for what Claude wrote, the
system sans for what people posted. A brief is a front page (docs/plans/2026-10-14_rework.md): stories ranked by
how many people talked about each, the focus (config.FOCUS) and the top four open with their key posts beside them,
the rest a line each.
"""

from __future__ import annotations

import html
import re
import time
from urllib.parse import quote, urlencode

from . import config, parse, sites, videos
from .brief import Brief, Thesis, Topic
from .parse import Post

CSP = ("default-src 'none'; img-src https://pbs.twimg.com; style-src 'self'; script-src 'self'; connect-src 'self'; "
       "base-uri 'none'; form-action 'self'; frame-ancestors 'none'")
LABELS = {"am": "morning", "pm": "evening"}
_MARK = ('<svg class="mark" viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.6"'
         ' stroke-linecap="round" stroke-linejoin="round">{}</svg>')
MARKS = {"am": _MARK.format('<path d="M5 18a7 7 0 0 1 14 0"/><path d="M2 21h20M12 5v3M4.2 9.8l1.9 1.9M19.8 9.8l-1.9 1.9'
                            'M1.5 18H3M21 18h1.5"/>'),  # a sun on the horizon
         "pm": _MARK.format('<path d="M20 15.5A8.5 8.5 0 0 1 8.5 4 8.5 8.5 0 1 0 20 15.5z"/>')}  # a crescent moon
HOURS = [("", "since last"), ("12", "last 12 h"), ("24", "last 24 h"), ("48", "last 48 h")]
POST_REF = re.compile(r"\s*\[\[(\d{1,25})\]\]")  # an older brief's pointer at a post that stands out
EMOJI = re.compile("[\U0001F000-\U0001FAFF\u2600-\u27BF\uFE0F\u200D]")  # dropped from names on the key posts


def esc(s) -> str:
    return html.escape(str(s or ""), quote=True)


def safe_url(u: str) -> str | None:
    return u if isinstance(u, str) and re.match(r"https?://", u) else None


def hhmm(ms: int) -> str:
    return time.strftime("%H:%M", time.localtime(ms / 1000))


def day(ms: int) -> str:
    return time.strftime("%a %-d %b %H:%M", time.localtime(ms / 1000))


def rich_text(p: Post) -> str:
    """The post's text, escaped, with its t.co links shown as their real address. X sends the text with &, < and >
    already as entities ("16% -&gt; 43%"); they are read back first, so they are escaped once, not twice."""
    text = esc(html.unescape(p.text or ""))
    art = p.article
    if art:  # an X Article: its title, linking to the post (whose page shows it whole), and its opening
        block = (f'<a class="art" href="{esc(p.url)}" rel="noreferrer">{esc(art.get("title") or "Article")}</a>'
                 + (f'\n{esc(art["preview"])}…' if art.get("preview") else ""))
        short = next((ln.get("short") for ln in p.links if ln.get("short") and ln.get("url") == art.get("url")), None)
        text = text.replace(esc(short), block) if short and esc(short) in text else (text.rstrip() + "\n" + block).lstrip()
    for ln in p.links:
        short, url = ln.get("short"), safe_url(ln.get("url"))
        if short and url:
            text = text.replace(esc(short), f'<a href="{esc(url)}" rel="noreferrer">{esc(ln.get("display") or url)}</a>')
    return re.sub(r"\s*https://t\.co/\w+\s*$", "", text)  # a media link left at the very end


def imgs(p: Post, most: int = 4) -> str:
    if not p.media:
        return ""
    out = []
    for m in p.media[:most]:
        u = safe_url(m.get("url"))
        if not u or not u.startswith("https://pbs.twimg.com/"):
            continue
        tag = "" if m.get("type") == "photo" else f'<span class="v">{esc(m.get("type"))}</span>'
        out.append(f'<a href="{esc(p.url)}" rel="noreferrer"><img loading="lazy" referrerpolicy="no-referrer" '
                   f'src="{esc(u)}?name=small" alt="">{tag}</a>')
    return f'<div class="imgs">{"".join(out)}</div>' if out else ""


def mins(s) -> str:
    return f"{round((s or 0) / 60)} min"


def vids(p: Post) -> str:
    """A post's long videos: one line each (Video, its length, its title) that opens to the summary of its whole
    transcript, Claude's view under its own label, and where the transcript came from, with a link to read it."""
    out = []
    for v in p.videos:
        s = v.get("summary") or {}
        pts = "".join(f"<li>{esc(x)}</li>" for x in s.get("points") or [])
        calls = "".join(f"<li>{esc(x)}</li>" for x in s.get("calls") or [])
        key = v.get("key") or ""
        out.append(
            f'<details class="vid" data-by="@{esc(p.handle)}"><summary><b>{kind(v)}</b> · {mins(v.get("duration_s"))}'
            + "".join(f" · {esc(v[k])}" for k in ("show", "title") if v.get(k)) + "</summary>"
            + (f'<p>{esc(s["gist"])}</p>' if s.get("gist") else "")
            + (f"<ol>{pts}</ol>" if pts else "") + (f"<h4>Calls</h4><ul>{calls}</ul>" if calls else "")
            + (f'<p class="view"><b>Claude\'s view</b> {esc(s["view"])}</p>' if s.get("view") else "")
            + f'<p class="src">Transcript: {esc(v.get("source") or "")} · '
            + f'<a href="/video/{quote(key)}">read it</a> · <a href="{esc(safe_url(v.get("url")) or p.url)}" '
            + f'rel="noreferrer">{"listen" if v.get("kind") == "podcast" else "watch"}</a></p></details>')
    return "".join(out)


def kind(v: dict) -> str:
    return "Podcast" if v.get("kind") == "podcast" else "Video"


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
                 f'<span>{day(q.created_ms)}</span></div><div class="t">{marked(rich_text(q), words)}</div>{imgs(q)}{vids(q)}</div>')
    name = f'<b>{esc(shown.name)}</b>' if shown.name and shown.name != shown.handle else ""
    return (f'<div class="post"><div class="meta">{name}<a href="{esc(shown.url)}" rel="noreferrer">@{esc(shown.handle)}</a>'
            f'<span>{day(shown.created_ms)}</span>{lead}{reply}{also}</div>'
            f'<div class="t">{marked(rich_text(shown), words)}</div>{imgs(shown)}{vids(shown)}{quote}</div>')


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


LEAD = 4  # stories told in full after the focus; the rest are a line each (Bloomberg's Five Things: the focus and four)


def folded(ids: list[str], posts: dict[str, Post], thr: dict[str, list[Post]]) -> str:
    """The posts behind a story, folded under a line that says how many and whose."""
    shown = topic_posts([i for i in ids if i in posts], posts, thr)
    if not shown:
        return ""
    handles = list(dict.fromkeys((p.retweet_of or p).handle for p in shown))
    who = ", ".join(f"@{h}" for h in handles[:6]) + (f" and {len(handles) - 6} more" if len(handles) > 6 else "")
    label = f"{count(len(shown), 'post', 'posts')} · {who}"
    return f'<details class="fold"><summary>{esc(label)}</summary>{"".join(post_html(p) for p in shown)}</details>'


def plain(text: str) -> str:
    """A gist as text: the [[post id]] marks of briefs before the re-work taken out."""
    return " ".join(POST_REF.sub("", text or "").split())


def cited(text: str, posts: dict[str, Post]) -> list[str]:
    """The posts an older brief's paragraph pointed at, in order, once each: its key posts."""
    return list(dict.fromkeys(i for i in re.findall(r"\[\[(\d{1,25})\]\]", text or "") if i in posts))


def people(ids: list[str], posts: dict[str, Post]) -> int:
    """How many of the people followed posted in a story: the page's rank (Nuzzel's). A repost counts as the
    reposter's, since they are the one followed."""
    return len({posts[i].handle.lower() for i in ids if i in posts})


def ranked(ts: list[Topic], posts: dict[str, Post]) -> list[Topic]:
    return sorted(ts, key=lambda t: (-people(t.posts, posts), -len(t.posts)))


def count(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"


def tight(p: Post) -> str:
    """A post's text for a card: its blank lines made single breaks, so more of it shows in the space."""
    return re.sub(r"\n\s*\n+", "\n", rich_text(p).strip())


def card(p: Post) -> str:
    """A key post as it was written, beside the story it carries: name, @handle and time (the link to X), its text,
    its first picture, what it quotes. Built from the post alone."""
    if p.unreadable:
        return ""
    shown = p.retweet_of or p
    name = EMOJI.sub("", shown.name or "").strip()
    who = ((f'<b>{esc(name)}</b>' if name and name != shown.handle else "")
           + f'<a href="{esc(shown.url)}" rel="noreferrer">@{esc(shown.handle)} · {hhmm(shown.created_ms)}</a>'
           + (f'<span>reposted by @{esc(p.handle)}</span>' if p.retweet_of else ""))
    q = shown.quote
    quote = (f'<div class="q"><p class="who"><a href="{esc(q.url)}" rel="noreferrer">@{esc(q.handle)}</a></p>'
             f'<div class="t">{tight(q)}</div>{vids(q)}</div>' if q and not q.unreadable else "")
    return (f'<article class="card"><p class="who">{who}</p><div class="t">{tight(shown)}</div>'
            f'{imgs(shown, 1)}{vids(shown)}{quote}</article>')


def said(ids: list[str], posts: dict[str, Post]) -> str:
    cards = "".join(card(posts[i]) for i in ids if i in posts)
    return f'<div class="said">{cards}</div>' if cards else ""


def story_html(t: Topic, posts: dict[str, Post], thr: dict[str, list[Post]], sid: str, lead: bool) -> str:
    """A story: its headline, its gist, the posts behind it folded, and its key posts beside it in their own words.
    A lead story is open; any other is one line (headline, how many people) that opens in place."""
    key = [i for i in (t.key or cited(t.summary, posts)) if i in posts][:3]
    gist = plain(t.summary)
    words = ('<div class="words">' + (f'<p class="gist">{esc(gist)}</p>' if gist else "")
             + folded(t.posts, posts, thr) + '</div>')
    body = f'<div class="body{" two" if key else ""}">{words}{said(key, posts)}</div>'
    if lead:
        head = f'<h3>{esc(t.title)}</h3>' if t.title else ""
        return f'<article class="story lead" id="{sid}">{head}{body}</article>'
    n = people(t.posts, posts)
    return (f'<details class="story line" id="{sid}"><summary><h3>{esc(t.title)}</h3>'
            f'<span class="n">{count(n, "person", "people")}</span></summary>{body}</details>')


def thesis_html(t: Thesis, posts: dict[str, Post], thr: dict[str, list[Post]], sid: str) -> str:
    """One thesis as a line, its claim and who argues it, that opens in place: the argument as posted, what follows
    if it holds, then Claude's view under its own label (the only opinion in a brief); the post itself beside it,
    the rest of its thread folded."""
    first = posts.get(t.posts[0]) if t.posts else None
    shown = (first.retweet_of or first) if first else None
    steps = "".join(f"<li>{esc(x)}</li>" for x in t.steps)
    view = "".join(f"<p><b>{k}</b> {esc(v)}</p>" for k, v in (("Weak spots", t.weak_spots), ("Wrong if", t.wrong_if)) if v)
    words = ('<div class="words">'
             + (f'<h4>Argument</h4><ol class="steps">{steps}</ol>' if steps else "")
             + (f'<h4>If it holds</h4><p>{esc(t.if_it_holds)}</p>' if t.if_it_holds else "")
             + (f'<div class="view"><h4>Claude\'s view</h4>{view}</div>' if view else "")
             + folded(t.posts[1:], posts, thr) + '</div>')
    key = said(t.posts[:1], posts)
    inner = parse.inner(shown) if shown else []
    vs = [v for x in inner for v in x.videos]
    mark = "Article · " if any(x.article for x in inner) else f"{kind(vs[0])} · " if vs else ""
    who = f'<span class="n">{mark}@{esc(shown.handle)}</span>' if shown else ""
    return (f'<details class="story line thesis" id="{sid}"><summary><h3>{esc(t.claim)}</h3>{who}</summary>'
            f'<div class="body{" two" if key else ""}">{words}{key}</div></details>')


def masthead(title: str, dek: str) -> str:
    return f'<header class="mast"><h1>{title}</h1><p class="dek">{dek}</p></header>'


def at_of(name: str, meta: dict) -> str:
    """Which version of a brief a page shows, so the live line can say when it was caught up (cli.at_of)."""
    n = len(meta.get("reads") or [])
    return f"{name}~{n}" if n > 1 else name


def window(meta: dict, posts: dict[str, Post]) -> tuple[int, int] | None:
    """The span a brief covers: from the last brief's newest post (else its own oldest) to the end of the read."""
    from .parse import snowflake_ms

    times = [p.created_ms for p in posts.values() if p.created_ms]
    if not times:
        return None
    lo = snowflake_ms(meta["boundary_id"]) if meta.get("boundary_id") else min(times)
    hi = max(meta.get("finished_ms") or 0, max(times))
    return (lo, hi) if hi > lo else None


def run_dek(meta: dict, posts: dict[str, Post]) -> str:
    """How many posts since when, the minute it was pulled and, a morning caught up, the minute of each update."""
    reads = meta.get("reads") or [meta]
    dek = f"{len(posts)} posts"
    span = window(meta, posts)
    if span:
        dek += f" {'since' if meta.get('boundary_id') else 'from'} {day(span[0])}"
    dek += " · " + ", ".join(f"{'pulled' if i == 0 else 'updated'} {hhmm(r.get('started_ms') or 0)}"
                             for i, r in enumerate(reads))
    if meta.get("reread_site"):
        dek += f" · X deployed a new site; its request was read again ({esc(meta.get('build'))})"
    return dek


def failed_html(f: dict | str) -> str:
    """One video a brief could not read: who posted it, its title, why in plain words, and its summary when a later
    run has read it. Briefs before 2026-10-20 kept only "key: error"."""
    if isinstance(f, str):
        key, _, err = f.partition(": ")
        f = {"key": key, "error": err}
    key = f.get("key") or ""
    d = videos.kept(key) or {}
    by, title = f.get("by") or d.get("by"), f.get("title") or d.get("title")
    url = f.get("url") or d.get("url") or (f"https://www.youtube.com/watch?v={key[3:]}" if key.startswith("yt-") else None)
    what = esc(title) if title else ("a podcast" if key[:3] in ("sp-", "ap-") else "a video")
    if safe_url(url):
        what = f'<a href="{esc(safe_url(url))}" rel="noreferrer">{what}</a>'
    return ((f"@{esc(by)} · " if by else "") + what + f": {esc(videos.why(f.get('error')))}."
            + (f' <a href="/video/{quote(key)}">Read since</a>.' if d.get("summary") else ""))


def status_html(meta: dict, b: Brief) -> str:
    """Said only when something went wrong: how the read ended, a gap, the order, a missing summary."""
    lines = []
    if not meta.get("normal"):
        lines.append(f"<b>The read stopped early:</b> {esc(meta.get('stop'))}.")
    if meta.get("gap"):
        lines.append("<b>Gap:</b> some posts between the last brief and this one were not read.")
    if meta.get("videos_left"):
        lines.append(f"<b>Videos:</b> {meta['videos_left']} long videos past the cap of {config.MAX_VIDEOS} were not "
                     "transcribed.")
    if meta.get("videos_failed"):
        lines.append("<b>Videos not read:</b>" + "".join(f"<br>{failed_html(f)}" for f in meta["videos_failed"]))
    if meta.get("articles_left"):
        lines.append(f"<b>Articles:</b> {meta['articles_left']} past the cap of {config.MAX_ARTICLES} were read from "
                     "their opening only.")
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


def run_head(label: str, started_ms: int) -> str:
    """A brief's headline: the day in full and the part of it."""
    return (f"{time.strftime('%A %-d %B', time.localtime(started_ms / 1000))} "
            f"<span>{esc(LABELS.get(label, label))}{MARKS.get(label, '')}</span>")


def live_html(live: dict) -> str:
    cls = {"on": " on", "bad": " bad"}.get(live.get("kind", ""), "")
    text = esc(live.get("text"))
    if live.get("href"):
        text = f'{text} <a href="{esc(live["href"])}">{esc(live.get("link") or "open")}</a>'
    return f'<p class="live{cls}" id="live" aria-live="polite">{text}</p>'


def topbar(active: str, live: dict, running: bool = False, at: str = "") -> str:
    """The one bar every page shares: the tabs, search, and Brief now with its live line. `at`: the brief on show,
    so Brief stays on it; elsewhere it opens the newest."""
    tabs = "".join(f'<a href="{href}"{" aria-current=page" if key == active else ""}>{name}</a>'
                   for key, href, name in (("brief", f"/b/{esc(at)}" if at else "/", "Brief"),
                                           ("sites", "/sites", "Sites"),
                                           ("history", "/history", "History")))
    opts = "".join(f'<option value="{v}">{esc(t)}</option>' for v, t in HOURS)
    find = ("" if active == "search" else  # the search page has its own form
            '<form class="find ctl" action="/search" method="get" role="search">'
            '<input type="search" name="q" placeholder="Search posts" aria-label="Search posts"></form>')
    return (f'<header class="top"><div class="bar"><a class="brand" href="/">X brief</a><nav class="tabs">{tabs}</nav>'
            f'{find}<div class="act">{live_html(live)}<form class="run ctl" id="run">'
            f'<select name="hours" aria-label="What to read">{opts}</select>'
            f'<button type="submit"{" disabled" if running else ""}>Brief now</button></form></div></div></header>')


def shell(title: str, top: str, main: str, at: str = "") -> str:
    """`at`: the brief this page shows, so the live line does not offer it as new."""
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="referrer" content="no-referrer"><title>{esc(title)}</title>
<link rel="stylesheet" href="/app.css"><script src="/app.js" defer></script></head>
<body{f' data-at="{esc(at)}"' if at else ""}>{top}<div class="wrap"><main>{main}</main></div></body></html>
"""


# ── a brief ─────────────────────────────────────────────────────────────────────────────────────────


def brief_main(b: Brief, posts: dict[str, Post], thr: dict[str, list[Post]], meta: dict) -> str:
    """The brief: the focus's stories and theses first, open; the four stories most people talked about, open; every
    other story a line; the theses a line each; everything else folded. Each opens in place."""
    sections = []
    focus = ranked([t for t in b.topics if t.focus], posts)
    on_focus = [t for t in b.theses if t.focus]
    if focus or on_focus:
        sections.append(f'<section id="focus"><h2 class="label">{esc((config.FOCUS or {}).get("name") or "Focus")}</h2>'
                        + "".join(story_html(t, posts, thr, f"h{i}", True) for i, t in enumerate(focus))
                        + "".join(thesis_html(t, posts, thr, f"ht{i}") for i, t in enumerate(on_focus)) + "</section>")
    rest = ranked([t for t in b.topics if not t.focus], posts)
    lead, more = rest[:LEAD], rest[LEAD:]
    if lead:
        sections.append('<section id="lead">' + "".join(story_html(t, posts, thr, f"t{i}", True)
                                                        for i, t in enumerate(lead)) + "</section>")
    many = [t for t in more if people(t.posts, posts) > 1]
    one = more[len(many):]  # ranked: everything after the stories more than one person posted in
    if many:
        sections.append(f'<section id="more"><h2 class="label">{count(len(many), "more story", "more stories")}</h2>'
                        + "".join(story_html(t, posts, thr, f"t{i + LEAD}", False) for i, t in enumerate(many))
                        + "</section>")
    if one:  # the long tail: two columns on a wide screen, so it scans in half the height
        sections.append(f'<section id="one"><h2 class="label">{count(len(one), "story", "stories")} from one person'
                        f'</h2><div class="pair">'
                        + "".join(story_html(t, posts, thr, f"t{i + LEAD + len(many)}", False) for i, t in enumerate(one))
                        + "</div></section>")
    theses = [t for t in b.theses if not t.focus]
    if theses:
        sections.append('<section id="theses"><h2 class="label">Theses</h2>'
                        + "".join(thesis_html(t, posts, thr, f"th{i}") for i, t in enumerate(theses)) + "</section>")
    if b.other:
        rest_posts = topic_posts([i for i in b.other if i in posts], posts, thr)
        sections.append(f'<section id="other"><details class="story line"><summary><h3>Everything else</h3>'
                        f'<span class="n">{count(len(rest_posts), "post", "posts")}</span></summary>'
                        f'<p class="empty">Memes, pictures, one-liners and reposts with nothing to add, as read.</p>'
                        f'{"".join(post_html(p) for p in rest_posts)}</details></section>')
    if not posts:
        sections.append('<p class="empty">Nothing new from the accounts you follow since the last brief.</p>')
    return status_html(meta, b) + "".join(sections)


def brief_page(run: dict, earlier: list[dict], live: dict, running: bool = False) -> str:
    meta = run["meta"]
    title = run_title(run["name"], run["label"], meta.get("started_ms") or 0)
    main = brief_main(run["brief"], run["posts"], run["threads"], meta)
    # the brief before this one, and briefs only: a run that read nothing is on History with what stopped it
    prev = next((r for r in earlier if r["started_ms"] < (meta.get("started_ms") or 0)
                 and ending(r["meta"], r.get("writer_error"))[1] != "bad"), None)
    dek = run_dek(meta, run["posts"])
    if prev:
        dek += f' · <a href="/b/{esc(prev["name"])}">previous brief</a>'
    main = masthead(run_head(run["label"], meta.get("started_ms") or 0), dek) + main
    return shell(f"X brief · {title}", topbar("brief", live, running=running, at=run["name"]), main,
                 at=at_of(run["name"], meta))


def empty_page(live: dict, running: bool = False, active: str = "brief") -> str:
    main = ('<p class="empty">No brief yet. <b>Brief now</b> reads your Following tab in the job\'s Brave and '
            'writes the first one; it takes a few minutes.</p>')
    return shell("X brief", topbar(active, live, running=running), main)


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
        n = f'{r["n_posts"]} posts · {r["n_topics"]} stories'
        if cls == "bad":
            n = "read nothing"
        rows.append(f'<li class="{cls}"><a href="/b/{esc(r["name"])}">{esc(day(r["started_ms"]))}</a>'
                    f'<span class="lb">{esc(LABELS.get(r["label"], r["label"]))}</span><span class="n">{n}</span>'
                    + (f'<span class="end {cls}">{esc(end)}</span>' if end else "") + '</li>')
    w = sett["windows"]
    off = sett.get("off") or []
    win = "".join(f'<div class="w"><label><input type="checkbox" name="{k}on"{"" if k in off else " checked"}> '
                  f'{LABELS[k]}</label><input type="time" name="{k}0" value="{esc(w[k][0])}" '
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
            f'{" checked" if sett["schedule"] else ""}> On</label>{win}'
            f'<button type="submit">Save</button></form>'
            f'<p class="note" id="sched-msg">Each run starts at a random minute inside its window.</p>{today_line}</section>')
    return shell("X brief · history", topbar("history", live, running=running), main)


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
        from .store import parse_query

        out, last_day, words = [], None, parse_query(q)[1]
        for p, run in hits:
            d = time.strftime("%a %-d %b %Y", time.localtime(p.created_ms / 1000))
            if d != last_day:
                out.append(f'<h3 class="day">{esc(d)}</h3>')
                last_day = d
            also = (f'<a class="from" href="/b/{esc(run)}">{esc(titles.get(run, run))}</a>' if run else "")
            out.append(post_html(p, also, words))
        n = count(len(hits), "post", "posts") + (", the newest shown; narrow the search for the rest" if cut else "")
        body = f'<p class="hits">{esc(n)}</p>' + "".join(out)
    return shell(f"X brief · {q or 'search'}", topbar("search", live, running=running), form + body)


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


def sites_page(posts: list[dict], sources: list[dict], sett: dict, counts: dict[str, int], checking: bool,
               live: dict, running: bool = False, key: str = "", q: str = "", words: list[str] | None = None,
               lines: dict[str, list[str]] | None = None) -> str:
    """The write-ups, newest first; narrowed to one pick (`key`: a source, or one person's sources together) and to
    the words searched (`q`), the write-ups showing the article's lines that hold them. Below, the list itself, when
    each was last checked, and the daily check's switch. What the people say on X is the brief's, not this page's."""
    words, lines = words or [], lines or {}
    names = {s["key"]: s["name"] for s in sources}
    picks = {}  # a pick's name: its first source's
    for s in sources:
        picks.setdefault(sites.group(s), s["name"])
    state = sett.get("sites_state") or {}
    people = {s["key"]: s.get("x") or [] for s in sources}
    find = (f'<form class="find ctl sitefind" action="/sites" method="get" role="search">'
            + (f'<input type="hidden" name="s" value="{esc(key)}">' if key else "")
            + f'<input type="search" name="q" value="{esc(q)}" placeholder="Search {esc(picks[key]) if key else "the sites"}"'
            f' aria-label="Search the sites"></form>')
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
                   for k, n in [("", "All"), *picks.items()])
    main = (find + f'<ul class="pick" aria-label="Sources">{pick}</ul>' + main + f'<section id="list"><h2>The list</h2><ol class="runs">{"".join(rows)}</ol>{ctl}'
            f'<p class="note">New sites are added in xbrief/config.py (SITES): an RSS feed or a sitemap.</p></section>')
    return shell("X brief · sites", topbar("sites", live, running=running), main)


def paragraphs(text: str, most: int = 120) -> list[str]:
    """A transcript in paragraphs: one at each line (a show's transcript has a line a speaker's turn), and within a
    line a break at the first sentence's end after `most` * 2/3 words, or at `most` words where a stretch has no full
    stop (X's captions are often unpunctuated)."""
    out = []
    for line in text.splitlines():
        cur: list[str] = []
        for w in line.split():
            cur.append(w)
            if (len(cur) >= most * 2 // 3 and w[-1] in ".?!") or len(cur) >= most:
                out.append(" ".join(cur))
                cur = []
        out += [" ".join(cur)] if cur else []
    return out


def video_page(doc: dict, live: dict, running: bool = False) -> str:
    """One long video's whole transcript, as it was read, with its summary above it."""
    pod = doc.get("kind") == "podcast"
    title = doc.get("title") or f"A video posted by @{doc.get('by', '')}"
    head = (f'<h2>{esc(title)}</h2><p class="hits">{esc(doc["show"]) + " · " if doc.get("show") else ""}'
            f'Posted by @{esc(doc.get("by", ""))} · {mins(doc.get("duration_s"))} · '
            f'transcript: {esc(doc.get("source") or "none")} · <a href="{esc(safe_url(doc.get("url")) or "")}" '
            f'rel="noreferrer">{"listen" if pod else "watch"}</a></p>')
    v = Post(id="", handle=doc.get("by", ""), name="", created_ms=0, text="",
             videos=[{**{k: doc.get(k) for k in ("key", "kind", "url", "duration_s", "show", "title", "source", "summary")}}])
    body = '<div class="tx">' + "".join(f"<p>{esc(x)}</p>" for x in paragraphs(
        doc.get("transcript") or doc.get("skip") or doc.get("error") or "")) + "</div>"
    return shell(title, topbar("", live, running=running), f'<section class="video">{head}{vids(v)}{body}</section>')
