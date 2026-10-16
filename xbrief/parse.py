"""Posts out of a Following-tab page, for either site build.

The new app's layout (xweb, read from its own query definitions on 2026-10-12): entries carry `entry_id` and
`sort_index`; a post is `tweet_results.result` with `details.full_text`, `details.created_at_ms`,
`core.user_results.result.core.screen_name`, `url_entities`, `media_entities2`, `reply_to_results`,
`reply_to_user_results`, `quoted_tweet_results`, `legacy.retweeted_status_results`, `note_tweet` for long
posts. The old app's layout (legacy): `entryId`, `sortIndex`, `itemContent.tweet_results.result.legacy.*`.

Every field is read defensively: X adds and renames fields often, and a post that cannot be read is kept as
a placeholder with its id, never dropped silently.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime

TWITTER_EPOCH_MS = 1288834974657


def snowflake_ms(post_id: str | int) -> int:
    return (int(post_id) >> 22) + TWITTER_EPOCH_MS


def ms_to_snowflake(ms: int) -> int:
    return (ms - TWITTER_EPOCH_MS) << 22


@dataclass
class Post:
    id: str
    handle: str
    name: str
    created_ms: int
    text: str
    links: list[dict] = field(default_factory=list)  # {short, url, display}
    media: list[dict] = field(default_factory=list)  # {type, url}
    reply_to_id: str | None = None
    reply_to_handle: str | None = None
    quote: "Post | None" = None
    retweet_of: "Post | None" = None
    unreadable: str | None = None  # why the post could not be read
    article: dict | None = None  # an X Article the post carries: {title, preview, url}, and `text` once read whole

    @property
    def url(self) -> str:
        return f"https://x.com/{self.handle or 'i'}/status/{self.id}"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Post":
        d = dict(d)
        for k in ("quote", "retweet_of"):
            if d.get(k):
                d[k] = cls.from_dict(d[k])
        return cls(**d)


@dataclass
class Entry:
    entry_id: str
    sort_index: str
    posts: list[Post]  # one for an item, several for a conversation module, in display order
    promoted: bool = False

    @property
    def newest_id(self) -> int:
        ids = [int(p.id) for p in self.posts if p.id.isdigit()]
        return max(ids) if ids else 0


def g(obj, *path, default=None):
    for k in path:
        if isinstance(obj, dict):
            obj = obj.get(k)
        elif isinstance(obj, list) and isinstance(k, int) and -len(obj) <= k < len(obj):
            obj = obj[k]
        else:
            return default
        if obj is None:
            return default
    return obj


def _unwrap(result: dict | None) -> dict | None:
    """TweetWithVisibilityResults and preview wrappers hold the post one level down."""
    if not isinstance(result, dict):
        return None
    if result.get("__typename") in ("TweetWithVisibilityResults", "TweetPreviewDisplay") or (
        "tweet" in result and "rest_id" not in result
    ):
        return result.get("tweet")
    return result


def _user(result: dict) -> tuple[str, str]:
    u = g(result, "core", "user_results", "result") or {}
    handle = g(u, "core", "screen_name") or g(u, "legacy", "screen_name") or ""
    name = g(u, "core", "name") or g(u, "legacy", "name") or ""
    return handle, name


def _legacy_created_ms(s: str | None) -> int | None:
    if not s:
        return None
    try:
        return int(datetime.strptime(s, "%a %b %d %H:%M:%S %z %Y").timestamp() * 1000)
    except ValueError:
        return None


def _trim(text: str, rng) -> str:
    """Cut the trailing media link the way the website does (display_text_range is in code points)."""
    if isinstance(rng, list) and len(rng) == 2 and all(isinstance(x, int) for x in rng):
        return text[rng[0] : rng[1]]
    return text


def _links(urls) -> list[dict]:
    out = []
    for u in urls or []:
        if isinstance(u, dict) and u.get("expanded_url"):
            out.append({"short": u.get("url") or "", "url": u["expanded_url"], "display": u.get("display_url") or u["expanded_url"]})
    return out


def _media_item(m: dict) -> dict | None:
    url = m.get("media_url_https")
    if not url:
        return None
    kind = m.get("type") or "photo"
    return {"type": kind, "url": url}


def _article(r: dict, links: list[dict]) -> dict | None:
    """An X Article's title and the opening the feed carries with it. Its full text is on its own page, which the
    job never opens (rule 1)."""
    a = g(r, "article", "article_results", "result")
    if not isinstance(a, dict) or not (a.get("title") or a.get("preview_text")):
        return None
    url = next((ln["url"] for ln in links if "/i/article/" in (ln.get("url") or "")), None)
    if not url and str(a.get("rest_id") or "").isdigit():
        url = f"https://x.com/i/article/{a['rest_id']}"
    return {"title": a.get("title") or "", "preview": a.get("preview_text") or "", "url": url}


def post_from_result(result: dict | None, depth: int = 0) -> Post | None:
    r = _unwrap(result)
    if not isinstance(r, dict):
        return None
    typename = r.get("__typename")
    pid = str(r.get("rest_id") or g(r, "legacy", "id_str") or "")
    if typename in ("TweetTombstone", "TweetUnavailable") or not pid:
        if not pid:
            return None
        return Post(pid, "", "", snowflake_ms(pid), "", unreadable=typename)
    handle, name = _user(r)
    leg = r.get("legacy") or {}
    details = r.get("details") or {}
    note = g(r, "note_tweet", "note_tweet_results", "result") or {}

    if details:  # xweb
        text = note.get("text") or _trim(details.get("full_text") or "", details.get("display_text_range"))
        created = details.get("created_at_ms") or snowflake_ms(pid)
        links = _links(g(note, "entity_set", "urls") if note.get("text") else None) or _links(r.get("url_entities"))
        media = [x for x in (_media_item(m) for m in r.get("media_entities2") or []) if x]
        reply_to_id = g(r, "reply_to_results", "rest_id")
        reply_to_handle = g(r, "reply_to_user_results", "result", "core", "screen_name")
        quoted = g(r, "quoted_tweet_results", "result")
        retweeted = g(leg, "retweeted_status_results", "result")
    else:  # legacy
        text = note.get("text") or _trim(leg.get("full_text") or "", leg.get("display_text_range"))
        created = _legacy_created_ms(leg.get("created_at")) or snowflake_ms(pid)
        links = _links(g(note, "entity_set", "urls") if note.get("text") else None) or _links(g(leg, "entities", "urls"))
        media = [x for x in (_media_item(m) for m in g(leg, "extended_entities", "media") or g(leg, "entities", "media") or []) if x]
        reply_to_id = leg.get("in_reply_to_status_id_str")
        reply_to_handle = leg.get("in_reply_to_screen_name")
        # a quoted post's own quote comes as nested_quoted_tweet_results (213 in a month's reads, 2026-10-16)
        quoted = g(r, "quoted_status_result", "result") or g(r, "nested_quoted_tweet_results", "result")
        retweeted = g(leg, "retweeted_status_result", "result")

    post = Post(
        id=pid, handle=handle, name=name, created_ms=int(created), text=text, links=links, media=media,
        reply_to_id=str(reply_to_id) if reply_to_id else None, reply_to_handle=reply_to_handle,
        article=_article(r, links),
    )
    if depth < 3:  # a repost of a quote of a quote is the deepest X sends
        post.quote = post_from_result(quoted, depth + 1) if quoted else None
        post.retweet_of = post_from_result(retweeted, depth + 1) if retweeted else None
    return post


def timeline(page: dict) -> dict:
    return g(page, "data", "home", "home_timeline_urt") or {}


def _item_post(content: dict) -> Post | None:
    # xweb: content.content.tweet_results ; legacy: content.itemContent.tweet_results
    inner = content.get("content") or content.get("itemContent") or {}
    res = g(inner, "tweet_results", "result")
    if res is None:
        return None
    return post_from_result(res) or Post("", "", "", 0, "", unreadable="no post in the entry")


def _is_promoted(entry_id: str, content: dict) -> bool:
    inner = content.get("content") or content.get("itemContent") or {}
    return entry_id.startswith("promoted") or bool(inner.get("promotedMetadata") or inner.get("promoted_metadata"))


def entries(page: dict) -> tuple[list[Entry], str | None]:
    """The page's post entries in display order, and the cursor to the next (older) page."""
    out: list[Entry] = []
    bottom = None
    for ins in timeline(page).get("instructions") or []:
        raw = list(ins.get("entries") or [])
        if isinstance(ins.get("entry"), dict):
            raw.append(ins["entry"])
        for e in raw:
            eid = e.get("entry_id") or e.get("entryId") or ""
            sidx = str(e.get("sort_index") or e.get("sortIndex") or "")
            c = e.get("content") or {}
            kind = c.get("__typename") or c.get("entryType") or ""
            if "Cursor" in kind:
                if (c.get("cursor_type") or c.get("cursorType")) == "Bottom":
                    bottom = c.get("value")
                continue
            if "Module" in kind:
                posts = []
                for it in c.get("items") or []:
                    ic = g(it, "item") or {}
                    p = _item_post(ic)
                    if p:
                        posts.append(p)
                if posts:
                    out.append(Entry(eid, sidx, posts, _is_promoted(eid, c)))
                continue
            p = _item_post(c)
            if p:
                out.append(Entry(eid, sidx, [p], _is_promoted(eid, c)))
    return out, bottom


# ── X Articles, read whole off the post's own page ──────────────────────────────────────────────────

ARTICLE_LIMIT = 60_000  # characters of an Article kept: the longest seen (2026-10-15) was 25,000
HEADS = {"header-one": "## ", "header-two": "### ", "unordered-list-item": "- ", "blockquote": "> "}


def _tweet_results(o, out: list) -> list:
    """Every post result anywhere in a response, nested ones too (TweetResultByRestId, TweetResultsByRestIds,
    TweetDetail all carry them under different paths)."""
    if isinstance(o, dict):
        if o.get("__typename") == "Tweet":
            out.append(o)
        elif o.get("__typename") == "TweetWithVisibilityResults" and isinstance(o.get("tweet"), dict):
            out.append(o["tweet"])  # the post inside carries no __typename of its own
        for v in o.values():
            _tweet_results(v, out)
    elif isinstance(o, list):
        for v in o:
            _tweet_results(v, out)
    return out


def article_text(a: dict, embedded: dict[str, Post]) -> str:
    """An Article's body (its `content_state`: Draft.js blocks and an entity map) as plain text: headings and lists
    marked, each image as its caption, each post it embeds as that post's words (when the page fetched it), each
    link's address after its paragraph."""
    cs = a.get("content_state") or {}
    em = cs.get("entityMap") or {}
    ents = ({str(e.get("key")): e.get("value") or {} for e in em if isinstance(e, dict)} if isinstance(em, list)
            else {str(k): v or {} for k, v in em.items()})
    out, n = [], 0
    for b in cs.get("blocks") or []:
        kind, text = b.get("type"), (b.get("text") or "").strip()
        n = n + 1 if kind == "ordered-list-item" else 0
        refs = [ents.get(str(r.get("key"))) or {} for r in b.get("entityRanges") or []]
        if kind == "atomic":
            for e in refs:
                d = e.get("data") or {}
                if e.get("type") == "TWEET":
                    p = embedded.get(str(d.get("tweetId")))
                    out.append(f"[a post by @{p.handle}: {p.text}]" if p and not p.unreadable else "[an embedded post]")
                elif e.get("type") == "MEDIA":
                    out.append(f"[image: {d['caption'].strip()}]" if (d.get("caption") or "").strip() else "[image]")
            continue
        if not text:
            continue
        urls = [(e.get("data") or {}).get("url") for e in refs if e.get("type") == "LINK"]
        tail = "".join(f" ({u})" for u in urls if u)
        out.append((f"{n}. " if n else HEADS.get(kind, "")) + text + tail)
    return "\n\n".join(out)[:ARTICLE_LIMIT]


def articles_in(responses: list[dict]) -> dict[str, str]:
    """Post id → its Article's whole text, for every post in these responses whose Article body came with it."""
    raw = [r for resp in responses for r in _tweet_results(resp, [])]
    embedded = {p.id: p for p in (post_from_result(r, depth=2) for r in raw) if p and p.id}
    out: dict[str, str] = {}
    for r in raw:
        a = g(r, "article", "article_results", "result") or {}
        pid = str(r.get("rest_id") or "")
        if pid and pid not in out and (a.get("content_state") or {}).get("blocks"):
            out[pid] = article_text(a, embedded)
    return out


def inner(p: Post) -> list[Post]:
    """The post and everything inside it: what it reposts, what that quotes, and what a quote quotes."""
    out = [p]
    for x in (p.retweet_of, p.quote):
        if x:
            out += inner(x)
    return out


def with_article(p: Post) -> list[Post]:
    """The post, and what it reposts or quotes at any depth, that carry an Article."""
    return [x for x in inner(p) if x.article]


def attach_articles(entries: list[Entry], texts: dict[str, str]) -> int:
    """Give each post whose Article was read its whole text (`article["text"]`). Returns how many got one."""
    n = 0
    for e in entries:
        for p in e.posts:
            for x in with_article(p):
                if x.id in texts:
                    x.article["text"] = texts[x.id]
                    n += 1
    return n
