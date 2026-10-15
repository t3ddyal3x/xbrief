"""Following-tab pages in both layouts, built field by field from X's own definitions (xweb: the
HomeLatestTimelineQuery normalization read on 2026-10-12; legacy: the old web app's long-published shape)."""

from xbrief.parse import ms_to_snowflake

BASE_MS = 1_760_270_400_000  # 2025-10-12 12:00 UTC; ids below are snowflakes from here


def sid(minutes: int) -> str:
    return str(ms_to_snowflake(BASE_MS + minutes * 60_000))


# ── xweb ───────────────────────────────────────────────────────────────────────────────────────────


def xw_user(handle, name=None):
    return {"result": {"__typename": "User", "rest_id": "u" + handle, "core": {"screen_name": handle, "name": name or handle.title()}}}


def xw_tweet(minutes, handle, text, *, urls=None, media=None, reply_to=None, quote=None, retweet=None, note=None, rng=None):
    pid = sid(minutes)
    t = {
        "__typename": "Tweet",
        "rest_id": pid,
        "core": {"user_results": xw_user(handle)},
        "details": {"full_text": text, "created_at_ms": BASE_MS + minutes * 60_000},
        "url_entities": urls or [],
        "media_entities2": media or [],
        "legacy": {"lang": "en"},
    }
    if rng:
        t["details"]["display_text_range"] = rng
    if reply_to:
        t["reply_to_results"] = {"rest_id": reply_to[0]}
        t["reply_to_user_results"] = {"rest_id": "x", "result": {"__typename": "User", "core": {"screen_name": reply_to[1]}}}
    if quote:
        t["quoted_tweet_results"] = {"rest_id": quote["rest_id"], "result": quote}
    if retweet:
        t["legacy"]["retweeted_status_results"] = {"rest_id": retweet["rest_id"], "result": retweet}
    if note:
        t["note_tweet"] = {"is_expandable": True, "note_tweet_results": {"result": {"__typename": "NoteTweet", "text": note, "entity_set": {"urls": urls or []}}}}
    return t


def xw_item(tweet, entry_id=None, promoted=False):
    content = {"__typename": "TimelineTweet", "tweet_results": {"rest_id": tweet.get("rest_id"), "result": tweet}}
    if promoted:
        content["promoted_metadata"] = {"advertiser_results": {}}
    return {"entry_id": entry_id or f"tweet-{tweet.get('rest_id') or 'x'}", "sort_index": tweet.get("rest_id") or "1",
            "content": {"__typename": "TimelineTimelineItem", "content": content}}


def xw_module(tweets, entry_id):
    return {"entry_id": entry_id, "sort_index": max(t["rest_id"] for t in tweets),
            "content": {"__typename": "TimelineTimelineModule",
                        "items": [{"entry_id": f"{entry_id}-{i}", "item": {"content": {"__typename": "TimelineTweet",
                                  "tweet_results": {"rest_id": t["rest_id"], "result": t}}}} for i, t in enumerate(tweets)]}}


def xw_cursor(kind, value):
    return {"entry_id": f"cursor-{kind.lower()}-{value}", "sort_index": "0",
            "content": {"__typename": "TimelineTimelineCursor", "cursor_type": kind, "value": value}}


def xw_page(entries, bottom="CUR"):
    es = [xw_cursor("Top", "TOP")] + entries + ([xw_cursor("Bottom", bottom)] if bottom else [])
    return {"data": {"home": {"home_timeline_urt": {"instructions": [{"__typename": "TimelineAddEntries", "entries": es}]}, "id": "h"}}}


# ── legacy ─────────────────────────────────────────────────────────────────────────────────────────


def lg_tweet(minutes, handle, text, *, urls=None, media=None, reply_to=None, quote=None, retweet=None):
    import datetime as dt

    pid = sid(minutes)
    created = dt.datetime.fromtimestamp((BASE_MS + minutes * 60_000) / 1000, dt.timezone.utc).strftime("%a %b %d %H:%M:%S +0000 %Y")
    leg = {"id_str": pid, "full_text": text, "created_at": created, "entities": {"urls": urls or []},
           "conversation_id_str": pid}
    if media:
        leg["extended_entities"] = {"media": media}
    if reply_to:
        leg["in_reply_to_status_id_str"], leg["in_reply_to_screen_name"] = reply_to
    if retweet:
        leg["retweeted_status_result"] = {"result": retweet}
    t = {"__typename": "Tweet", "rest_id": pid,
         "core": {"user_results": {"result": {"__typename": "User", "legacy": {"screen_name": handle, "name": handle.title()}}}},
         "legacy": leg}
    if quote:
        t["quoted_status_result"] = {"result": quote}
    return t


def lg_item(tweet, promoted=False):
    ic = {"itemType": "TimelineTweet", "tweet_results": {"result": tweet}}
    if promoted:
        ic["promotedMetadata"] = {}
    eid = ("promoted-tweet-" if promoted else "tweet-") + tweet["rest_id"]
    return {"entryId": eid, "sortIndex": tweet["rest_id"], "content": {"entryType": "TimelineTimelineItem", "itemContent": ic}}


def lg_module(tweets, entry_id):
    return {"entryId": entry_id, "sortIndex": tweets[-1]["rest_id"],
            "content": {"entryType": "TimelineTimelineModule",
                        "items": [{"entryId": f"{entry_id}-{i}", "item": {"itemContent": {"itemType": "TimelineTweet",
                                  "tweet_results": {"result": t}}}} for i, t in enumerate(tweets)]}}


def lg_page(entries, bottom="CUR"):
    es = entries + ([{"entryId": "cursor-bottom-1", "sortIndex": "0", "content": {"entryType": "TimelineTimelineCursor",
                     "cursorType": "Bottom", "value": bottom}}] if bottom else [])
    return {"data": {"home": {"home_timeline_urt": {"instructions": [{"type": "TimelineAddEntries", "entries": es}]}}}}


def with_article(tweet, title="A Title", preview="The opening.", blocks=None, entities=None):
    """The post carries an X Article; with `blocks` the Article's body too (as its own page fetches it)."""
    a = {"rest_id": "9" + tweet["rest_id"], "title": title, "preview_text": preview}
    if blocks is not None:
        a["content_state"] = {"blocks": blocks, "entityMap": entities or []}
    tweet["article"] = {"article_results": {"result": a}}
    return tweet


def post_page(tweet, *embedded):
    """What TweetResultByRestId answers for a post's own page; TweetResultsByRestIds' list for embedded posts."""
    return {"data": {"tweetResult": {"result": tweet}, "more": [{"result": t} for t in embedded]}}
