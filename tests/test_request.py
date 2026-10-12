import json
import pathlib

from xbrief import request, site

REAL_OP = (pathlib.Path(__file__).parent / "fixtures" / "xweb_home_op_2026-10-12.js").read_text()
XWEB = site.xweb_op_from_chunk(REAL_OP, "C", "E")
LEGACY = site.Op("legacy", "QID", "HomeLatestTimeline", "M", "M", features={"f1": True}, field_toggles={})

PV1 = "__relay_internal__pv__xclientsfeaturesappviewerisloggedinrelayprovider"
PV2 = "__relay_internal__pv__xclientsfeaturestranslationnoteautotranslationenabledrelayprovider"


def test_xweb_first_page_is_a_get_with_relays_variables():
    r = request.build(XWEB, 20, None, None)
    assert r.method == "GET" and r.body is None
    assert r.url == "https://api.x.com/graphql/y49GF7so_QZnYwGbOJYXGg/HomeLatestTimelineQuery"
    assert r.params == {"variables": '{"count":20,"cursor":null,"enableRanking":false,"requestContext":"launch",'
                                     f'"seenTweetIds":null,"{PV1}":true,"{PV2}":false}}'}
    assert r.headers == {"origin": "https://x.com", "referer": "https://x.com/", "sec-fetch-site": "same-site"}


def test_xweb_later_page_reports_what_was_seen_by_post():
    r = request.build(XWEB, 20, "CUR", ["1", "2"])
    assert r.method == "POST" and r.params is None
    assert list(r.body) == ["queryId", "variables"] and r.body["queryId"] == "y49GF7so_QZnYwGbOJYXGg"
    v = r.body["variables"]
    assert list(v)[:5] == ["count", "cursor", "enableRanking", "requestContext", "seenTweetIds"]
    assert v["cursor"] == "CUR" and v["requestContext"] is None and v["seenTweetIds"] == ["1", "2"]


def test_xweb_later_page_without_seen_ids_is_a_get():
    r = request.build(XWEB, 20, "CUR", [])
    assert r.method == "GET" and json.loads(r.params["variables"])["cursor"] == "CUR"


def test_legacy_pages_are_posts_with_features():
    r = request.build(LEGACY, 20, None, None)
    assert r.method == "POST" and r.url == "https://x.com/i/api/graphql/QID/HomeLatestTimeline"
    assert list(r.body) == ["variables", "features", "queryId"]
    assert r.body["variables"] == {"count": 20, "includePromotedContent": True, "latestControlAvailable": True,
                                   "requestContext": "launch", "seenTweetIds": []}
    assert r.headers["sec-fetch-site"] == "same-origin" and r.headers["referer"] == "https://x.com/home"
    r2 = request.build(LEGACY, 20, "CUR", ["9"])
    assert r2.body["variables"]["cursor"] == "CUR" and "requestContext" not in r2.body["variables"]
    assert r2.body["variables"]["seenTweetIds"] == ["9"]
