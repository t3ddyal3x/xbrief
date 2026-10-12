import asyncio
import json
import pathlib

import pytest

from xbrief import config, site

FIX = pathlib.Path(__file__).parent / "fixtures"
REAL_OP = (FIX / "xweb_home_op_2026-10-12.js").read_text()

ENTRY = "https://abs.twimg.com/x-web/x-web/entry-client-ABC123.js"
XWEB_HTML = f'<html><script type="module" async="" src="{ENTRY}"></script></html>'
MAIN = "https://abs.twimg.com/responsive-web/client-web/main.abc123ef.js"
LEGACY_HTML = (f'<script src="{MAIN}"></script><script>window.__INITIAL_STATE__={{"featureSwitch":'
               '{"defaultConfig":{"f1":{"value":true},"f2":{"value":true}},"user":{"config":{"f2":{"value":false}}}}};'
               'window.__META_DATA__={}</script>')
MAIN_JS = ('x={queryId:"OLDID",operationName:"HomeTimeline",operationType:"query",metadata:{featureSwitches:[],fieldToggles:[]}},'
           'y={queryId:"QID123",operationName:"HomeLatestTimeline",operationType:"query",'
           'metadata:{featureSwitches:["f1","f2","responsive_web_edit_tweet_api_enabled","f_unknown"],fieldToggles:["withX"]}}')


def fake_cdn(files: dict, log: list):
    async def get(url):
        log.append(url.rsplit("/", 1)[-1])
        if url not in files:
            raise AssertionError(f"unexpected fetch {url}")
        return files[url]
    return get


def test_detect():
    assert site.detect(XWEB_HTML) == ("xweb", ENTRY)
    assert site.detect(LEGACY_HTML) == ("legacy", MAIN)
    with pytest.raises(site.LoggedOut):
        site.detect('<script src="https://abs.twimg.com/x-web/x-web/entry-client-logged-out-B.js">')
    with pytest.raises(site.SiteError):
        site.detect("<html>a challenge page</html>")


def test_xweb_op_from_the_real_definition():
    op = site.xweb_op_from_chunk(REAL_OP, "C", ENTRY)
    assert op.query_id == "y49GF7so_QZnYwGbOJYXGg" and op.name == "HomeLatestTimelineQuery"
    assert [n for n, _ in op.variables][:5] == ["count", "cursor", "enableRanking", "requestContext", "seenTweetIds"]
    assert dict(map(tuple, op.variables))["enableRanking"] is False
    assert list(op.provided.values()) == [True, False]
    assert "isloggedin" in list(op.provided)[0]


def test_xweb_search_prefers_home_files_and_caches():
    a = "https://abs.twimg.com/x-web/x-web/assets/"
    files = {
        ENTRY: 'import"./assets/aaa-1.js";import"./assets/zzz-2.js";import("./assets/home-3.js")',
        a + "aaa-1.js": 'import"./bbb-4.js"', a + "zzz-2.js": "", a + "bbb-4.js": "",
        a + "home-3.js": "var q;" + REAL_OP,
    }
    log = []
    op = asyncio.run(site.xweb_op(ENTRY, fake_cdn(files, log)))
    assert op.query_id == "y49GF7so_QZnYwGbOJYXGg" and op.script == a + "home-3.js"
    assert log == ["entry-client-ABC123.js", "home-3.js"]  # found before the others were fetched
    log.clear()
    asyncio.run(site.xweb_op(ENTRY, fake_cdn(files, log)))
    assert log == []  # content-hashed names: read from the cache


def test_legacy_op_reads_ids_and_switches():
    log = []
    op = asyncio.run(site.resolve(LEGACY_HTML, fake_cdn({MAIN: MAIN_JS}, log)))[0]
    assert op.build == "legacy" and op.query_id == "QID123" and op.name == "HomeLatestTimeline"
    assert op.features["f1"] is True and op.features["f2"] is False  # the account's own value wins
    assert op.features["responsive_web_edit_tweet_api_enabled"] is True  # the fork's fallback
    assert op.features["f_unknown"] is False
    assert op.field_toggles == {"withX": False}


def test_resolve_saves_and_rereads_only_on_a_new_deploy():
    a = "https://abs.twimg.com/x-web/x-web/assets/"
    files = {ENTRY: 'import"./assets/home-3.js"', a + "home-3.js": REAL_OP}
    op, reread = asyncio.run(site.resolve(XWEB_HTML, fake_cdn(files, [])))
    assert reread and json.loads(config.SITE.read_text())["query_id"] == op.query_id
    op2, reread2 = asyncio.run(site.resolve(XWEB_HTML, fake_cdn({}, [])))
    assert not reread2 and op2 == op
    new_entry = ENTRY.replace("ABC123", "DEF456")
    files2 = {new_entry: 'import"./assets/home-3.js"'}
    op3, reread3 = asyncio.run(site.resolve(XWEB_HTML.replace("ABC123", "DEF456"), fake_cdn(files2, [])))
    assert reread3 and op3.page_script == new_entry


def test_missing_operation_is_an_error():
    with pytest.raises(site.SiteError):
        asyncio.run(site.xweb_op(ENTRY, fake_cdn({ENTRY: ""}, [])))
    with pytest.raises(site.SiteError):
        site.legacy_op(LEGACY_HTML, MAIN, "nothing here")


def test_cache_refuses_odd_names():
    with pytest.raises(site.SiteError):
        asyncio.run(site.cached("https://abs.twimg.com/x/../../etc/passwd", fake_cdn({}, [])))
