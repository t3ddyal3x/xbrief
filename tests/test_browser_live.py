"""The real Brave, hidden, against a fake x.com on loopback (`bin/tests --browser`). Checks what only the real
browser can show: the window never comes to the front, the page reports itself visible and active while hidden,
the mouse wheel makes the page fetch its next feed page, and the browser is gone afterwards."""

import asyncio
import random
import subprocess

import pytest
from builders import lg_item, lg_page, lg_tweet, sid
from fake_x import FakeX

from xbrief import collect, config
from xbrief.browser import Browser, running

pytestmark = pytest.mark.browser


def front() -> str:
    return subprocess.run(["osascript", "-e", 'tell application "System Events" to get name of first process whose frontmost is true'],
                          capture_output=True, text=True).stdout.strip()


def feed_pages(n):
    return [lg_page([lg_item(lg_tweet(1000 - i * 20 - j, f"u{j}", f"post {i}-{j}")) for j in range(20)], bottom=str(i + 1))
            for i in range(n)]


def run_against(fx, monkeypatch):
    monkeypatch.setattr(collect, "wheel_pause", lambda rng: 0.25)  # fast, for the test only
    b = Browser(config.PROFILE)
    return asyncio.run(collect.run(rng=random.Random(2), browser=b, home_url=fx.home))


def test_reads_the_following_tab_hidden(monkeypatch):
    collect.save_state({"newest_id": int(sid(1000 - 3 * 20 - 5))})  # inside the fourth page
    fx = FakeX(feed_pages(6))
    before = front()
    try:
        res = run_against(fx, monkeypatch)
    finally:
        fx.stop()
    assert res.stop == "caught up" and res.normal and len(res.pages) == 4, res.stop
    assert front() == before
    latest = [r for r in fx.log if r["op"] == "HomeLatestTimeline"]
    assert [r["i"] for r in latest] == [0, 1, 2, 3]
    assert all(r["vis"] == "visible" and r["active"] == "yes" for r in fx.log)
    assert not running(config.PROFILE)


def test_rate_limit_stops_at_once(monkeypatch):
    fx = FakeX(feed_pages(3), status=429)
    try:
        res = run_against(fx, monkeypatch)
    finally:
        fx.stop()
    assert "HTTP 429" in res.stop and not res.pages
    assert len([r for r in fx.log if r["op"] == "HomeLatestTimeline"]) == 1  # nothing retried
    assert not running(config.PROFILE)


def test_logged_out_stops_before_any_feed_request(monkeypatch):
    fx = FakeX(feed_pages(1))
    fx.redirect_home_to = f"http://127.0.0.1:{fx.port}/i/flow/login?redirect_after_login=%2Fhome"
    try:
        res = run_against(fx, monkeypatch)
    finally:
        fx.stop()
    assert "X sent the page to" in res.stop and "/i/flow/login" in res.stop
    assert not [r for r in fx.log if r["op"] == "HomeLatestTimeline"]
    assert not running(config.PROFILE)
