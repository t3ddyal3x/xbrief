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
        quoted = g(r, "quoted_status_result", "result")
        retweeted = g(leg, "retweeted_status_result", "result")

    post = Post(
        id=pid, handle=handle, name=name, created_ms=int(created), text=text, links=links, media=media,
        reply_to_id=str(reply_to_id) if reply_to_id else None, reply_to_handle=reply_to_handle,
    )
    if depth < 2:
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
