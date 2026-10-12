import asyncio
import datetime as dt
import json
import os
import pathlib
import random

import pytest
from builders import BASE_MS, sid, xw_item, xw_page, xw_tweet

from xbrief import collect, config, parse

REAL_OP = (pathlib.Path(__file__).parent / "fixtures" / "xweb_home_op_2026-10-12.js").read_text()
ENTRY = "https://abs.twimg.com/x-web/x-web/entry-client-ABC123.js"
HTML = f'<script type="module" src="{ENTRY}"></script>'
FILES = {ENTRY: 'import"./assets/home-3.js"', "https://abs.twimg.com/x-web/x-web/assets/home-3.js": REAL_OP}


async def cdn(url):
    return FILES[url]


class Acc:
    def __init__(self, active=True, locks=None, error_msg=None):
        self.username, self.cookies, self.active = "me", {"auth_token": "a", "ct0": "c"}, active
        self.locks, self.error_msg = locks or {}, error_msg


class Rep:
    def __init__(self, page):
        self.page = page

    def json(self):
        return self.page


class Session:
    def __init__(self, script, calls):
        self.script, self.calls = script, calls

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def req(self, method, url, params=None, headers=None, json=None):
        self.calls.append({"method": method, "url": url, "params": params, "json": json, "headers": headers})
        step = self.script.pop(0)
        if isinstance(step, Exception):
            raise step
        return None if step is None else Rep(step)


class Pool:
    def __init__(self, accs):
        self.accs = accs

    async def get_all(self):
        return self.accs


class Api:
    def __init__(self, script, accs=None):
        self.pool, self.script, self.calls = Pool([Acc()] if accs is None else accs), script, []

    def raw_session(self, name):
        self.name = name
        return Session(self.script, self.calls)


@pytest.fixture(autouse=True)
def page_load(monkeypatch):
    from twscrape.queue_client import XClIdGenStore

    class Gen:
        page_html = HTML

    async def get(username, proxy=None, cookies=None, fresh=False):
        return Gen()

    monkeypatch.setattr(XClIdGenStore, "get", get)


def page(minutes_list, bottom="CUR"):
    return xw_page([xw_item(xw_tweet(m, f"u{m}", f"post {m}")) for m in minutes_list], bottom=bottom)


def go(api, now_minutes=60, sleeps=None):
    async def sleep(s):
        (sleeps if sleeps is not None else []).append(s)

    return asyncio.run(collect.run(rng=random.Random(1), sleep=sleep, now_ms=BASE_MS + now_minutes * 60_000,
                                   api=api, get_script=cdn))


def set_state(minutes):
    collect.save_state({"newest_id": int(sid(minutes))})


def test_catches_up_at_the_previous_newest_post():
    set_state(20)
    api = Api([page([50, 45, 40]), page([35, 30, 25]), page([22, 20, 18])])
    sleeps = []
    res = go(api, sleeps=sleeps)
    assert res.normal and res.stop == "caught up" and not res.gap and len(res.pages) == 3
    assert res.newest_id == int(sid(50)) and collect.load_state()["newest_id"] == int(sid(50))
    assert len(sleeps) == 2 and all(2 <= s <= 25 + 90 for s in sleeps)
    assert api.name == "HomeLatestTimelineQuery"


def test_requests_follow_the_page():
    set_state(20)
    api = Api([page([50, 49, 48, 47, 46]), page([30, 20])])
    go(api)
    first, second = api.calls
    assert first["method"] == "GET" and json.loads(first["params"]["variables"])["requestContext"] == "launch"
    assert second["method"] == "POST" and second["json"]["variables"]["cursor"] == "CUR"
    assert second["json"]["variables"]["seenTweetIds"] == [sid(50), sid(49)]  # the last three were below the fold
    assert first["headers"]["origin"] == "https://x.com"


def test_first_run_reads_back_the_window():
    api = Api([page([50, 40]), page([-60 * 11, -60 * 13])])
    res = go(api, now_minutes=60)
    assert res.normal and res.stop == "read back to the start of the window" and not res.gap


def test_end_of_feed_before_the_boundary_is_a_gap():
    set_state(10)
    res = go(Api([page([50, 40], bottom=None)]))
    assert res.gap and not res.normal and res.stop == "reached the end of what X serves"
    assert collect.load_state()["newest_id"] == int(sid(50))  # still advances: what is lost is lost


def test_page_cap_is_a_gap(monkeypatch):
    monkeypatch.setattr(config, "MAX_PAGES", 2)
    set_state(1)
    res = go(Api([page([50, 49]), page([48, 47]), page([2])]))
    assert res.gap and len(res.pages) == 2 and res.stop.startswith("stopped at the cap")


def test_refused_request_ends_the_run_without_retry():
    set_state(1)
    api = Api([page([50, 40]), None, page([3])])
    res = go(api)
    assert not res.normal and "refused" in res.stop and len(api.calls) == 2


def test_no_account_explains_the_lock():
    from twscrape.accounts_pool import NoAccountError

    set_state(1)
    until = dt.datetime(2026, 10, 12, 9, 45, tzinfo=dt.timezone.utc)
    api = Api([NoAccountError("x")], accs=[Acc(locks={"HomeLatestTimelineQuery": until})])
    res = go(api)
    assert "rate-limited" in res.stop and not res.pages
    assert collect.load_state()["newest_id"] == int(sid(1))  # nothing read: the boundary stays


def test_inactive_login_stops_before_any_request():
    api = Api([], accs=[Acc(active=False, error_msg="(32) Could not authenticate you")])
    res = go(api)
    assert "ended the session" in res.stop and "(32)" in res.stop and api.calls == []


def test_no_login():
    res = go(Api([], accs=[]))
    assert res.stop.startswith("no login")


def test_feed_error_clears_the_saved_site():
    set_state(1)
    res = go(Api([{"errors": [{"message": "PersistedQueryNotFound"}]}]))
    assert "without a feed" in res.stop and not config.SITE.exists()


def test_promoted_posts_never_end_the_read():
    set_state(20)
    p1 = xw_page([xw_item(xw_tweet(50, "a", "x")), xw_item(xw_tweet(1, "ad", "old ad"), entry_id="promoted-1", promoted=True)])
    res = go(Api([p1, page([20])]))
    assert len(res.pages) == 2 and res.stop == "caught up"


def test_job_env_is_set_and_proxies_removed(monkeypatch):
    monkeypatch.setenv("HTTPS_PROXY", "socks5://127.0.0.1:1080")
    monkeypatch.setenv("TWS_PROXY", "socks5://127.0.0.1:1080")
    go(Api([], accs=[]))
    assert "HTTPS_PROXY" not in os.environ and "TWS_PROXY" not in os.environ
    for k, v in config.TWS_ENV.items():
        assert os.environ[k] == v


def test_reading_pauses_vary():
    rng = random.Random(7)
    xs = [collect.reading_pause(rng) for _ in range(500)]
    assert min(xs) >= 2 and max(xs) <= 115 and len(set(xs)) == 500
    assert sum(x > 25 for x in xs) > 10  # the occasional long stop


def test_raw_is_saved_and_pruned():
    set_state(20)
    res = go(Api([page([50, 20])]))
    path = pathlib.Path(collect.save_raw(res, "am"))
    saved = json.loads(path.read_text())
    assert saved["meta"]["stop"] == "caught up" and saved["meta"]["page_count"] == 1 and len(saved["pages"]) == 1
    os.utime(path, (0, 0))
    assert collect.prune_raw() == 1 and not path.exists()


def test_boundary_uses_the_newest_post_in_a_module():
    from builders import xw_module

    set_state(20)
    mod = xw_module([xw_tweet(-100, "a", "old parent"), xw_tweet(30, "b", "new reply")], "home-conversation-9")
    res = go(Api([xw_page([xw_item(xw_tweet(40, "c", "x")), mod]), page([10])]))
    assert len(res.pages) == 2  # the old parent did not stop the read


def test_parse_ms_helpers_agree_with_builders():
    assert parse.snowflake_ms(sid(0)) == BASE_MS
