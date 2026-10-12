"""The run's decisions, against a scripted browser that emits the DevTools events Brave would."""

import asyncio
import json
import os
import pathlib
import random

from builders import BASE_MS, sid, xw_item, xw_module, xw_page, xw_tweet

from xbrief import collect, config, parse

HOME = "https://x.com/home"
LATEST = "https://x.com/i/api/graphql/NmDBT3APtNxDpMqIEauu7A/HomeLatestTimeline?variables=x"


class FakeBrowser:
    """Pages arrive one per `wheels_per_page` wheel turns after the Following tab is clicked."""

    def __init__(self, pages, *, remembered=False, status=200, nav_to=HOME, upsell=None, wheels_per_page=3,
                 tab_found=True, latest_url=LATEST, ranked=False, has_menu=True, popular_pages=None):
        self.pages, self.remembered, self.status, self.nav_to = list(pages), remembered, status, nav_to
        self.upsell, self.wheels_per_page, self.tab_found, self.latest_url = upsell, wheels_per_page, tab_found, latest_url
        self.events = asyncio.Queue()
        self.bodies, self.calls, self.wheels, self.clicks, self.keys = {}, [], 0, 0, []
        self.closed = self.started = False
        self.n = 0
        self.ranked, self.has_menu, self.popular = ranked, has_menu, list(popular_pages or [])
        self.tab_selected = remembered
        self.menu_open = False
        self.last_xpath = ""
        self.page_wheels = 0  # wheel turns before the page's end is near (0: always at the end)

    async def start(self):
        self.started = True
        return self

    async def close(self):
        self.closed = True

    def ev(self, method, **params):
        self.events.put_nowait({"method": method, "params": params})

    def emit_page(self):
        source = self.popular if (self.ranked and self.popular) else self.pages
        if not source:
            return
        rid = f"r{self.n}"
        self.n += 1
        post = json.dumps({"variables": {"count": 20, "enableRanking": self.ranked}, "queryId": "q"})
        self.ev("Network.requestWillBeSent", requestId=rid, request={"url": self.latest_url, "method": "POST", "postData": post})
        self.ev("Network.responseReceived", requestId=rid, response={"status": self.status})
        if self.status == 200:
            self.bodies[rid] = json.dumps(source.pop(0))
            self.ev("Network.loadingFinished", requestId=rid)

    async def send(self, method, params=None):
        self.calls.append(method)
        if method == "Page.navigate":
            self.ev("Network.requestWillBeSent", requestId="ft", request={"url": "https://x.com/i/api/graphql/Q/HomeTimeline"})
            self.ev("Page.frameNavigated", frame={"id": "main", "url": self.nav_to})
            self.ev("Page.loadEventFired")
            if self.upsell:
                self.ev("Page.navigatedWithinDocument", frameId="main", url="https://x.com/i/premium_sign_up")
            if self.remembered:
                self.emit_page()
        if method == "Network.getResponseBody":
            return {"body": self.bodies.pop(params["requestId"]), "base64Encoded": False}
        if method == "Page.getLayoutMetrics":  # a long page: the end is near only after `page_wheels` turns
            y = min(self.wheels, self.page_wheels) * 1000
            return {"cssVisualViewport": {"pageY": y, "clientHeight": 900}, "cssContentSize": {"height": self.page_wheels * 1000 + 900}}
        return {}

    async def find_box(self, xpath):
        self.last_xpath = xpath
        if "menu" in xpath:
            return (150.0, 90.0) if (self.menu_open and self.has_menu) else None
        return (120.0, 24.0) if self.tab_found else None

    async def click(self, x, y):
        self.clicks += 1
        if "menu" in self.last_xpath:  # Recent chosen
            self.menu_open, self.ranked = False, False
            self.emit_page()
        elif self.tab_selected:
            self.menu_open = True
        else:
            self.tab_selected = True
            self.emit_page()

    async def key(self, name):
        self.keys.append(name)
        if self.upsell == "closes":
            self.ev("Page.navigatedWithinDocument", frameId="main", url=HOME)
        self.menu_open = False

    async def at_bottom(self, within=1.5):
        m = await self.send("Page.getLayoutMetrics")
        vp, cs = m["cssVisualViewport"], m["cssContentSize"]
        return vp["pageY"] + vp["clientHeight"] >= cs["height"] - within * vp["clientHeight"]

    async def wheel(self, dy):
        self.wheels += 1
        if self.wheels % self.wheels_per_page == 0:
            self.emit_page()


def page(minutes_list, bottom="CUR"):
    return xw_page([xw_item(xw_tweet(m, f"u{m}", f"post {m}")) for m in minutes_list], bottom=bottom)


def go(b, now_minutes=60):
    slept = []

    async def sleep(s):
        slept.append(s)

    told = []
    res = asyncio.run(collect.run(rng=random.Random(1), sleep=sleep, now_ms=BASE_MS + now_minutes * 60_000, browser=b,
                                  progress=lambda phase, **kw: told.append((phase, kw))))
    res.slept, res.told = slept, told
    return res


def set_state(minutes):
    collect.save_state({"newest_id": int(sid(minutes))})


def test_catches_up_at_the_previous_newest_post():
    set_state(20)
    b = FakeBrowser([page([50, 45, 40]), page([35, 30, 25]), page([22, 20, 18])])
    res = go(b)
    assert res.normal and res.stop == "caught up" and not res.gap and len(res.pages) == 3
    assert res.build == "legacy" and b.clicks == 1 and b.closed
    assert res.newest_id == int(sid(50)) and collect.load_state()["newest_id"] == int(sid(50))
    assert b.wheels == 6 and len(res.slept) == 6


def test_a_remembered_following_tab_is_not_clicked():
    set_state(20)
    b = FakeBrowser([page([50, 20])], remembered=True)
    res = go(b)
    assert res.stop == "caught up" and b.clicks == 0


def test_new_app_build_is_read_off_the_request():
    set_state(20)
    res = go(FakeBrowser([page([50, 20])], latest_url="https://api.x.com/graphql/y49/HomeLatestTimelineQuery?variables=x"))
    assert res.build == "xweb" and res.stop == "caught up"


def test_first_run_reads_back_the_window():
    res = go(FakeBrowser([page([50, 40]), page([-60 * 23, -60 * 25])]), now_minutes=60)
    assert res.normal and res.stop == "read back to the start of the window"


def test_a_chosen_window_ignores_where_the_last_run_stopped():
    set_state(50)  # the last run reached 50 min after base; a 2-hour ad-hoc read goes further back anyway
    b = FakeBrowser([page([55, 52]), page([48, 30]), page([-70, -80])])
    slept = []

    async def sleep(s):
        slept.append(s)

    res = asyncio.run(collect.run(rng=random.Random(1), sleep=sleep, now_ms=BASE_MS + 60 * 60_000, browser=b, hours=2))
    assert res.stop == "read back to the start of the window" and len(res.pages) == 3
    assert res.boundary_id == parse.ms_to_snowflake(BASE_MS + 60 * 60_000 - 2 * 3_600_000)
    assert collect.load_state()["newest_id"] == int(sid(55))  # the next scheduled run carries on from here


def test_end_of_feed_before_the_boundary_is_a_gap():
    set_state(10)
    res = go(FakeBrowser([page([50, 40], bottom=None)]))
    assert res.gap and not res.normal and res.stop == "reached the end of what X serves"
    assert collect.load_state()["newest_id"] == int(sid(50))


def test_page_cap_is_a_gap(monkeypatch):
    monkeypatch.setattr(config, "MAX_PAGES", 2)
    set_state(1)
    res = go(FakeBrowser([page([50, 49]), page([48, 47]), page([46])]))
    assert res.gap and res.stop.startswith("stopped at the cap of 2 pages")


def test_feed_that_stops_loading_is_a_gap():
    set_state(1)
    b = FakeBrowser([page([50, 49])], wheels_per_page=10_000)
    res = go(b)
    assert res.gap and res.stop == "the feed stopped loading while scrolling" and b.wheels == collect.STALL_WHEELS


def test_a_long_page_is_scrolled_to_its_end_before_a_stall_is_called():
    set_state(1)
    b = FakeBrowser([page([50, 49])], wheels_per_page=10_000)
    b.page_wheels = 60  # X's ~100-post first page: well past STALL_WHEELS turns
    res = go(b)
    # the end counts as near 1.5 viewports out, which the fake's 1000 px turns reach two turns early
    assert res.stop == "the feed stopped loading while scrolling" and b.wheels == 58 + collect.STALL_WHEELS


def test_rate_limit_ends_the_run_and_keeps_the_boundary():
    set_state(1)
    res = go(FakeBrowser([page([50])], status=429))
    assert "HTTP 429" in res.stop and "rate limited" in res.stop and not res.pages
    assert collect.load_state()["newest_id"] == int(sid(1))


def test_logged_out_landing_ends_the_run():
    for url in ("https://x.com/", "https://x.com/i/flow/login?redirect_after_login=%2Fhome", "https://x.com/account/access"):
        b = FakeBrowser([page([50])], nav_to=url)
        res = go(b)
        assert "X sent the page to" in res.stop and b.clicks == 0 and b.closed, url


def test_premium_offer_is_closed_with_escape():
    set_state(20)
    b = FakeBrowser([page([50, 20])], upsell="closes")
    res = go(b)
    assert b.keys == ["Escape"] and res.stop == "caught up"


def test_premium_offer_that_stays_ends_the_run():
    b = FakeBrowser([page([50])], upsell="stays")
    res = go(b)
    assert "Premium offer" in res.stop and b.clicks == 0


def test_missing_tab_ends_the_run():
    res = go(FakeBrowser([page([50])], tab_found=False))
    assert res.stop == "could not find the Following tab on x.com/home"


def test_no_profile_means_no_login():
    res = asyncio.run(collect.run(now_ms=BASE_MS))
    assert res.stop.startswith("no login") and not config.PROFILE.exists()


def test_browser_is_closed_even_on_an_unexpected_error():
    class Broken(FakeBrowser):
        async def find_box(self, xpath):
            raise RuntimeError("boom")

    b = Broken([page([50])])
    res = go(b)
    assert res.stop == "RuntimeError: boom" and b.closed


def test_promoted_posts_never_end_the_read():
    set_state(20)
    p1 = xw_page([xw_item(xw_tweet(50, "a", "x")), xw_item(xw_tweet(1, "ad", "old ad"), entry_id="promoted-1", promoted=True)])
    res = go(FakeBrowser([p1, page([20])]))
    assert len(res.pages) == 2 and res.stop == "caught up"


def test_boundary_uses_the_newest_post_in_a_module():
    set_state(20)
    mod = xw_module([xw_tweet(-100, "a", "old parent"), xw_tweet(30, "b", "new reply")], "home-conversation-9")
    res = go(FakeBrowser([xw_page([xw_item(xw_tweet(40, "c", "x")), mod]), page([10])]))
    assert len(res.pages) == 2


def test_pacing_varies_and_never_repeats():
    rng = random.Random(7)
    xs = [collect.wheel_pause(rng) for _ in range(800)]
    assert min(xs) >= 0.35 and max(xs) <= 52 and len(set(xs)) == 800
    assert sum(x > 8 for x in xs) > 10
    ds = [collect.wheel_delta(rng) for _ in range(400)]
    assert any(d < 0 for d in ds) and all(-400 <= d <= 880 for d in ds)


def test_raw_is_saved_and_pruned():
    set_state(20)
    res = go(FakeBrowser([page([50, 20])]))
    path = pathlib.Path(collect.save_raw(res, "am"))
    assert path.name.endswith("-am.json.gz") and path.read_bytes()[:2] == b"\x1f\x8b"  # gzip
    saved = collect.load_raw(path)
    assert saved["meta"]["stop"] == "caught up" and saved["meta"]["page_count"] == 1
    os.utime(path, (0, 0))
    assert collect.prune_raw() == 1 and not path.exists()


def test_popular_order_is_switched_to_recent():
    set_state(20)
    popular = [page([50, 3, 44])]  # ranked: an old post mixed in
    b = FakeBrowser([page([50, 45, 40]), page([30, 20])], ranked=True, popular_pages=popular)
    res = go(b)
    assert res.stop == "caught up" and not res.ranked and len(res.pages) == 2  # the Popular page was dropped
    assert b.clicks == 3  # the tab, the tab again (its menu), Recent
    assert res.told[-1] == ("reading", {"pages": 2, "posts": 5})  # the dropped Popular page is not counted
    assert [t[0] for t in res.told[:2]] == ["opening Brave", "opening x.com"]


def test_popular_without_a_menu_reads_to_a_page_with_nothing_new():
    set_state(20)
    popular = [page([50, 3, 44]), page([41, 2, 25]), page([19, 1, 10])]
    b = FakeBrowser([], ranked=True, has_menu=False, popular_pages=popular)
    res = go(b)
    assert res.ranked and res.stop == "caught up" and len(res.pages) == 3 and b.keys == ["Escape"]


def test_unknown_order_counts_as_popular():
    assert collect.ranking_of({"url": "https://x.com/i/api/graphql/q/HomeLatestTimeline"}) is True
    assert collect.ranking_of({"postData": '{"variables": {"enableRanking": false}}'}) is False
    v = '%7B%22enableRanking%22%3Afalse%7D'
    assert collect.ranking_of({"url": f"https://api.x.com/graphql/q/HomeLatestTimelineQuery?variables={v}"}) is False


def test_brief_leaves_out_what_an_earlier_brief_had():
    from xbrief import brief

    ents = parse.entries(page([50, 3, 44]))[0]
    posts = brief.unique_posts(ents, after_id=int(sid(20)))
    assert sorted(posts) == sorted([sid(50), sid(44)])


def test_snowflake_helpers_agree_with_builders():
    assert parse.snowflake_ms(sid(0)) == BASE_MS
