"""One page of the Following tab, shaped as the page that build serves sends it.

xweb (read from x-web's own code, 2026-10-12): the first page is a GET to
api.x.com/graphql/<id>/HomeLatestTimelineQuery?variables=<json> with requestContext "launch". A later page
carries the ids of the posts already on screen (seenTweetIds), and a request with those is a POST of
{"queryId", "variables"} to the same address. The variables are Relay's: every argument in the operation's
order, null where unset, then the provided variables. No features block.

legacy (the old web app, from published captures; check against Brave's network tab on the first run): a
POST to x.com/i/api/graphql/<id>/HomeLatestTimeline with {"variables", "features", "queryId"}.

The headers are a fetch() from https://x.com: api.x.com is another origin on the same site; x.com/i/api
is the same origin. The fork adds the rest (identity, auth, the anti-bot id) in Chrome's order.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from .site import Op

ORIGIN = "https://x.com"


@dataclass
class Req:
    method: str
    url: str
    params: dict | None
    body: dict | None
    headers: dict


def _xweb_variables(op: Op, page_size: int, cursor: str | None, seen: list[str] | None) -> dict:
    given = {"count": page_size, "cursor": cursor, "enableRanking": False}
    if cursor is None:
        given["requestContext"] = "launch"
    if seen:
        given["seenTweetIds"] = seen
    out = {}
    for name, default in op.variables:
        out[name] = given[name] if given.get(name) is not None else default
    for name, value in op.provided.items():
        out[name] = value
    return out


def build(op: Op, page_size: int, cursor: str | None, seen: list[str] | None) -> Req:
    if op.build == "xweb":
        url = f"https://api.x.com/graphql/{op.query_id}/{op.name}"
        variables = _xweb_variables(op, page_size, cursor, seen)
        headers = {"origin": ORIGIN, "referer": ORIGIN + "/", "sec-fetch-site": "same-site"}
        if seen:
            return Req("POST", url, None, {"queryId": op.query_id, "variables": variables}, headers)
        return Req("GET", url, {"variables": json.dumps(variables, separators=(",", ":"))}, None, headers)

    if op.build == "legacy":
        url = f"https://x.com/i/api/graphql/{op.query_id}/{op.name}"
        variables: dict = {"count": page_size}
        if cursor:
            variables["cursor"] = cursor
        variables.update({"includePromotedContent": True, "latestControlAvailable": True})
        if cursor is None:
            variables["requestContext"] = "launch"
        variables["seenTweetIds"] = seen or []
        body: dict = {"variables": variables, "features": op.features}
        if op.field_toggles:
            body["fieldToggles"] = op.field_toggles
        body["queryId"] = op.query_id
        headers = {"origin": ORIGIN, "referer": ORIGIN + "/home", "sec-fetch-site": "same-origin"}
        return Req("POST", url, None, body, headers)

    raise ValueError(f"unknown build {op.build!r}")
