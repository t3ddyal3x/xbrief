"""The app: the store and its search, one run at a time, the schedule, and the server's routes and perimeter, all
in-process (the server is driven through a fake socket, so no test opens a connection)."""

import datetime as dt
import io
import json
import random

from builders import BASE_MS, xw_item, xw_module, xw_page, xw_tweet

from xbrief import brief, cli, config, page, parse, runner, server, store


def publish(posts, label="am", minutes=0, ask=None):
    pages = [xw_page([xw_item(t) if not isinstance(t, list) else xw_module(t, f"conv-{i}") for i, t in enumerate(posts)])]
    meta = {"stop": "caught up", "normal": True, "gap": False, "started_ms": BASE_MS + minutes * 60_000,
            "finished_ms": BASE_MS + minutes * 60_000 + 1, "page_count": 1, "boundary_id": 0}
    return cli.publish(pages, meta, label, ask=ask or (lambda t: "{}"))


# ── the store and search ────────────────────────────────────────────────────────────────────────────


def test_search_by_words_accounts_and_dates():
    publish([xw_tweet(1, "bob", "Rates were cut by the Fed"), xw_tweet(2, "amy", "Nothing about money"),
             xw_tweet(3, "dave", "RT", retweet=xw_tweet(-5, "alice", "The Fed meets today"))])
    later = publish([xw_tweet(600, "bob", "Another rate cut soon?")], label="pm", minutes=600)
    texts = lambda hits: [(p.retweet_of or p).text for p, _ in hits]  # noqa: E731
    assert texts(store.search("fed")[0]) == ["The Fed meets today", "Rates were cut by the Fed"]  # newest first
    assert texts(store.search("rat")[0]) == ["Another rate cut soon?", "Rates were cut by the Fed"]  # words begin with
    assert texts(store.search("@BOB")[0]) == ["Another rate cut soon?", "Rates were cut by the Fed"]
    assert texts(store.search("@alice")[0]) == ["The Fed meets today"]  # a repost is found by its author too
    assert texts(store.search("fed @bob")[0]) == ["Rates were cut by the Fed"]
    hits, _ = store.search("soon")
    assert hits[0][1] == later  # each post with the brief that had it
    day = dt.datetime.fromtimestamp((BASE_MS + 600 * 60_000) / 1000).strftime("%Y-%m-%d")
    assert texts(store.search("", since=day)[0])[0] == "Another rate cut soon?"
    assert store.search("") == ([], False)


def test_search_survives_any_input():
    publish([xw_tweet(1, "bob", 'say "hi" (now) AND-OR NEAR * ^')])
    for q in ['"', '"hi', "AND", "NEAR(", "*", "^", "'; drop table posts; --", "@", "@@x", "-x", "(", "hi)"]:
        store.search(q)  # never a syntax error from the full-text index
    assert len(store.search('"hi" (now)')[0]) == 1


def test_a_post_seen_twice_is_kept_once_and_cut_is_reported():
    publish([xw_tweet(1, "bob", "same post")])
    publish([xw_tweet(1, "bob", "same post")], label="pm", minutes=600)
    assert store.counts()["posts"] == 1
    with store.db() as con:  # its row in the word index replaced, not added to
        assert con.execute("SELECT count(*) FROM posts_fts").fetchone()[0] == 1
    for i in range(5):
        publish([xw_tweet(100 + i, "x", f"many {i}")], minutes=1000 + i)
    hits, cut = store.search("many", limit=3)
    assert len(hits) == 3 and cut


def test_threads_come_back_whole():
    name = publish([[xw_tweet(5, "gina", "1/ a"), xw_tweet(6, "gina", "2/ b"), xw_tweet(7, "gina", "3/ c")]])
    run = store.load_run(name)
    conv = next(iter(run["threads"].values()))
    assert [p.text for p in conv] == ["1/ a", "2/ b", "3/ c"]


# ── one run at a time ───────────────────────────────────────────────────────────────────────────────


def test_one_run_at_a_time():
    held = runner.take_lock()
    assert held and runner.running() and runner.take_lock() is None
    assert runner.start(hours=12) is False
    held.close()
    assert not runner.running()


def test_a_run_in_a_terminal_waits_for_the_lock(monkeypatch):
    held = runner.take_lock()
    called = []
    monkeypatch.setattr(cli.collect, "run", lambda **kw: called.append(1))
    assert cli.main(["run", "--now", "--label", "am"]) == 3 and not called
    held.close()


def test_a_run_waits_out_a_look_at_the_lock(monkeypatch):
    real, tries = runner.take_lock, []

    def busy_once(path=None):
        tries.append(1)
        return None if len(tries) == 1 else real(path)  # the page's status held it the first time

    monkeypatch.setattr(runner, "take_lock", busy_once)
    f = runner.acquire(wait_s=1)
    assert f is not None and len(tries) == 2
    f.close()


def test_a_double_click_starts_one_run(monkeypatch):
    spawned = []
    monkeypatch.setattr(runner.subprocess, "Popen", lambda *a, **kw: spawned.append(a))
    assert runner.start(hours=12) is True
    assert runner.start(hours=12) is False  # its process has not taken the lock yet
    assert len(spawned) == 1


def test_run_command():
    cmd = runner.run_cmd("pm", 24.0)
    assert cmd[1:] == ["-m", "xbrief", "run", "--now", "--label", "pm", "--hours", "24"]
    assert "--hours" not in runner.run_cmd("am", None)


# ── the schedule ────────────────────────────────────────────────────────────────────────────────────

DAY = dt.date(2026, 10, 12)
SETT = {"schedule": True, "windows": {"am": ["05:30", "07:30"], "pm": ["17:00", "20:00"]}}


def at(h, m=0):
    return dt.datetime.combine(DAY, dt.time(h, m))


def test_fire_times_land_inside_the_window():
    rng = random.Random(1)
    for _ in range(300):
        t = dt.datetime.fromtimestamp(runner.pick_fire(DAY, ["05:30", "07:30"], rng) / 1000)
        assert at(5, 30) <= t <= at(7, 15)


def test_a_window_switched_off_never_runs_and_keeps_its_times():
    rng, sett = random.Random(2), {**SETT, "off": ["pm"]}
    assert runner.due(at(7, 20), sett, None, rng) == "am"
    assert runner.due(at(20, 0), sett, None, rng) is None and set(store.slots(DAY.isoformat())) == {"am"}
    ok = {"schedule": True, "windows": SETT["windows"], "off": ["pm"]}
    code, _, body = call("POST", "/api/settings", ok)
    assert code == 200 and json.loads(body)["settings"]["off"] == ["pm"]
    assert store.settings()["windows"]["pm"] == ["17:00", "20:00"]
    assert call("POST", "/api/settings", {**ok, "off": ["noon"]})[0] == 400
    html = call("GET", "/history")[2]
    assert '<input type="checkbox" name="amon" checked>' in html and '<input type="checkbox" name="pmon">' in html


def test_each_slot_fires_once():
    rng = random.Random(2)
    assert runner.due(at(5, 0), SETT, None, rng) is None
    assert runner.due(at(7, 20), SETT, None, rng) == "am"
    assert runner.due(at(7, 21), SETT, None, rng) is None
    assert runner.due(at(20, 0), SETT, None, rng) == "pm"
    assert runner.due(at(23, 0), SETT, None, rng) is None


def test_asleep_through_both_runs_the_later_once():
    assert runner.due(at(21, 0), SETT, None, random.Random(3)) == "pm"
    s = store.slots(DAY.isoformat())
    assert s["am"]["fired_ms"] == -1 and s["pm"]["fired_ms"] > 0


def test_a_hand_run_within_the_hour_covers_the_slot():
    hand = int(at(7, 0).timestamp() * 1000)
    assert runner.due(at(7, 20), SETT, hand, random.Random(4)) is None
    assert store.slots(DAY.isoformat())["am"]["fired_ms"] == -1


def test_schedule_off_starts_nothing():
    assert runner.due(at(21, 0), {**SETT, "schedule": False}, None, random.Random(5)) is None


def test_turning_it_on_at_night_does_not_start_the_morning():
    runner.apply_settings(SETT, now=at(12, 0))
    s = store.slots(DAY.isoformat())
    assert s["am"]["fired_ms"] == -1 and s["pm"]["fired_ms"] is None
    assert runner.due(at(12, 1), SETT, None, random.Random(6)) is None
    assert runner.next_fire(at(12, 1)) == s["pm"]["fire_ms"]


def test_turning_it_on_inside_a_window_does_not_start_a_run_at_once():
    runner.apply_settings(SETT, now=at(6, 0))
    s = store.slots(DAY.isoformat())
    assert at(6, 0) <= dt.datetime.fromtimestamp(s["am"]["fire_ms"] / 1000) <= at(7, 15)
    store.forget_unfired(DAY.isoformat())
    runner.apply_settings(SETT, now=at(7, 20))  # too late in the window to hold a run
    assert store.slots(DAY.isoformat())["am"]["fired_ms"] == -1


def test_moving_a_window_redraws_the_slots_not_yet_run():
    runner.apply_settings(SETT, now=at(4, 0))
    runner.apply_settings({**SETT, "windows": {"am": ["06:00", "06:30"], "pm": ["21:00", "22:00"]}}, now=at(4, 0))
    t = runner.next_fire(at(4, 0))
    assert at(6, 0) <= dt.datetime.fromtimestamp(t / 1000) <= at(6, 15)


def test_tick_starts_a_scheduled_run():
    store.save_settings(SETT)
    started = []
    assert runner.tick(at(20, 0), random.Random(7), starter=lambda **kw: started.append(kw) or True) == "pm"
    assert started == [{"label": "pm", "by": "schedule"}]


# ── the server ──────────────────────────────────────────────────────────────────────────────────────


class FakeSock:
    def __init__(self, data: bytes):
        self.r, self.w = io.BytesIO(data), io.BytesIO()

    def makefile(self, mode, *a, **kw):
        return self.r if "r" in mode else self.w

    def sendall(self, b):
        self.w.write(b)

    def settimeout(self, t):
        pass

    def shutdown(self, how):
        pass

    def close(self):
        pass


def call(method, path, body=None, host="xbrief.localhost", headers=None):
    head = {"Host": host, **(headers or {})}
    data = b""
    if body is not None:
        data = json.dumps(body).encode()
        head.setdefault("Content-Type", "application/json")
        head["Content-Length"] = str(len(data))
    raw = f"{method} {path} HTTP/1.1\r\n" + "".join(f"{k}: {v}\r\n" for k, v in head.items() if v is not None)
    sock = FakeSock(raw.encode() + b"Connection: close\r\n\r\n" + data)
    server.Handler(sock, ("127.0.0.1", 50000), None)
    out = sock.w.getvalue()
    status = int(out.split(b" ", 2)[1])
    head_b, _, payload = out.partition(b"\r\n\r\n")
    return status, head_b.decode(), payload.decode()


def test_the_perimeter():
    assert call("GET", "/", host="evil.example")[0] == 421
    assert call("GET", "/", headers={"Origin": "https://evil.example"})[0] == 403
    assert call("POST", "/api/run", {"hours": 12}, headers={"Origin": "https://evil.example"})[0] == 403
    # a form post from anywhere has no JSON body
    assert call("POST", "/api/run", None, headers={"Content-Type": "application/x-www-form-urlencoded",
                                                   "Content-Length": "0"})[0] == 400
    code, head, _ = call("GET", "/")
    assert code == 200 and "Content-Security-Policy: default-src 'none'" in head and "no-store" in head


def test_pages(monkeypatch):
    assert "No brief yet" in call("GET", "/")[2]
    name = publish([xw_tweet(1, "bob", "Rates were cut <b>today</b>")])
    code, _, html = call("GET", "/")
    assert code == 200 and "Rates were cut &lt;b&gt;today&lt;/b&gt;" in html and f'data-at="{name}"' in html
    assert call("GET", f"/b/{name}")[0] == 200
    assert call("GET", "/b/2020-01-01-0000-am")[0] == 404
    assert call("GET", "/b/../../etc/passwd")[0] == 404
    code, _, html = call("GET", "/search?q=rates")
    assert code == 200 and "1 post<" in html and f'href="/b/{name}"' in html
    code, _, html = call("GET", "/history")
    assert code == 200 and f'href="/b/{name}"' in html and 'id="sched"' in html
    assert call("GET", "/app.js")[0] == 200 and call("GET", "/app.css")[0] == 200
    code, _, html = call("GET", "/theses")  # the old Theses tab: the brief, whose Theses part it now is
    assert code == 200 and f'data-at="{name}"' in html and f'href="/b/{name}" aria-current' in html
    assert call("GET", f"/b/{name}/theses")[0] == 200 and call("GET", "/b/2020-01-01-0000-am/theses")[0] == 404


def test_run_button(monkeypatch):
    started = []
    monkeypatch.setattr(runner, "start", lambda **kw: started.append(kw) or True)
    assert call("POST", "/api/run", {"hours": 24})[0] == 202 and started[-1]["hours"] == 24
    assert call("POST", "/api/run", {"hours": None})[0] == 202 and started[-1]["hours"] is None
    for bad in ({"hours": 0}, {"hours": 500}, {"hours": "12"}, {"hours": True}):
        assert call("POST", "/api/run", bad)[0] == 400
    monkeypatch.setattr(runner, "start", lambda **kw: False)
    assert call("POST", "/api/run", {"hours": None})[0] == 409


def test_settings_are_checked():
    ok = {"schedule": True, "windows": {"am": ["05:30", "07:30"], "pm": ["17:00", "20:00"]}}
    code, _, body = call("POST", "/api/settings", ok)
    assert code == 200 and store.settings()["schedule"] is True
    for bad in ({**ok, "schedule": "yes"}, {**ok, "windows": {"am": ["05:30", "07:30"]}},
                {**ok, "windows": {"am": ["5:30", "07:30"], "pm": ["17:00", "20:00"]}},
                {**ok, "windows": {"am": ["07:30", "07:40"], "pm": ["17:00", "20:00"]}}):
        assert call("POST", "/api/settings", bad)[0] == 400


def test_live_line():
    now = at(12, 0)
    assert server.live(now=now)["text"] == "Schedule off."
    runner.write_progress(fresh=True, phase="reading", pages=3, posts=180, done=False,
                          started_ms=int(now.timestamp() * 1000))
    held = runner.take_lock()
    assert server.live(now=now) == {"running": True, "kind": "on", "text": "Reading · 3 pages · 180 posts"}
    runner.write_progress(phase="writing the brief", posts=150, writing_ms=int(now.timestamp() * 1000))
    assert server.live(now=now)["text"] == "Writing the brief · 150 posts"
    lv = server.live(now=now + dt.timedelta(minutes=4, seconds=50))
    assert lv["text"] == "Writing the brief · 150 posts · 4 min" and lv["slow"]  # the page asks less often
    held.close()
    runner.write_progress(phase="done", done=True, name="2026-10-12-1200-pm")
    lv = server.live(now=dt.datetime.now())
    assert lv["href"] == "/b/2026-10-12-1200-pm" and lv["text"] == "New brief."
    assert server.live("2026-10-12-1200-pm", now=dt.datetime.now())["text"] == "Schedule off."  # the page shows it
    runner.write_progress(normal=False, stop="X answered the feed request with HTTP 429")
    lv = server.live(now=dt.datetime.now())
    assert lv["kind"] == "bad" and "HTTP 429" in lv["text"] and lv["href"] == "/b/2026-10-12-1200-pm"
    runner.write_progress(phase="failed", done=True, error="BrowserError: no port")
    assert server.live(now=dt.datetime.now())["kind"] == "bad"


def test_the_first_builds_word_index_is_rebuilt_once():
    publish([xw_tweet(1, "bob", "Rates were cut"), xw_tweet(2, "amy", "Nothing here")])
    with store.db() as con:  # make the index the first build had: the post id in a column
        con.execute("DROP TABLE posts_fts")
        con.execute("CREATE VIRTUAL TABLE posts_fts USING fts5 (post_id UNINDEXED, body, who)")
        con.execute("INSERT INTO posts_fts (post_id, body, who) SELECT id, 'stale', handle FROM posts")
    store._ready.clear()  # a new process
    assert [p.text for p, _ in store.search("rates")[0]] == ["Rates were cut"]
    assert store.search("stale")[0] == []
    with store.db() as con:
        sql = con.execute("SELECT sql FROM sqlite_master WHERE name = 'posts_fts'").fetchone()[0]
        assert "post_id" not in sql and "contentless_delete" in sql  # it keeps no copy of the text
        assert con.execute("SELECT count(*) FROM posts_fts").fetchone()[0] == 2


# ── a morning caught up (docs/plans/2026-10-20_early-run.md) ───────────────────────────────────────


def a_read(monkeypatch, at_hm, minutes, boundary_min, newest_min):
    """Make the next `xbrief run` read these posts (minutes after BASE_MS) at this local time of 2026-10-21."""
    from builders import sid

    from xbrief import collect

    started = int(dt.datetime(2026, 10, 21, *at_hm).timestamp() * 1000)

    async def fake(hours=None, progress=None):
        return collect.Result(started_ms=started, finished_ms=started + 120_000, stop="caught up", normal=True,
                              boundary_id=int(sid(boundary_min)), newest_id=int(sid(newest_min)), build="xweb",
                              pages=[xw_page([xw_item(xw_tweet(m, f"p{m}", f"post {m}")) for m in minutes])])

    monkeypatch.setattr(cli.collect, "run", fake)


def a_writer(monkeypatch):
    asked = []

    class Sub:
        @staticmethod
        def run(cmd, input=None, **kw):
            asked.append([json.loads(ln)["text"] for ln in input.split("BEGIN POSTS\n", 1)[1].splitlines()])
            return type("R", (), {"returncode": 0, "stdout": "{}", "stderr": ""})()

    monkeypatch.setattr(brief, "subprocess", Sub)
    return asked


def test_a_brief_now_the_same_morning_catches_up_the_early_brief_as_one(monkeypatch):
    asked = a_writer(monkeypatch)
    a_read(monkeypatch, (5, 12), [3, 2, 1], 0, 3)
    assert cli.main(["run", "--now", "--label", "am"]) == 0
    early = store.latest_name()
    assert early == "2026-10-21-0512-am" and asked[-1] == ["post 3", "post 2", "post 1"]

    a_read(monkeypatch, (7, 4), [5, 4, 3], 3, 5)  # the read stops on the page that reaches post 3
    assert cli.main(["run", "--now", "--label", "am"]) == 0
    assert asked[-1] == ["post 3", "post 2", "post 1", "post 5", "post 4"]  # every post of the morning, each once
    runs = store.runs()
    assert [r["name"] for r in runs] == [early] and runs[0]["n_posts"] == 5  # one brief, under the early run's name
    meta = runs[0]["meta"]
    assert [r["raw"].rsplit("/", 1)[1] for r in meta["reads"]] == ["2026-10-21_0512-am.json.gz", "2026-10-21_0704-am.json.gz"]
    assert meta["boundary_id"] == meta["reads"][0]["boundary_id"] and meta["page_count"] == 2
    assert "pulled 05:12, updated 07:04" in page.run_dek(meta, {})

    lv = server.live(early, now=dt.datetime.now())  # the page showing the early brief is told it was caught up
    assert lv["text"] == "Brief caught up." and lv["href"] == f"/b/{early}"
    assert server.live(page.at_of(early, meta), now=dt.datetime.now())["text"] == "Schedule off."
    code, _, html = call("GET", "/")
    assert code == 200 and f'data-at="{early}~2"' in html and f'href="/b/{early}"' in html

    asked.clear()  # a rebrief of either read writes the whole morning again
    cli.main(["rebrief", meta["reads"][0]["raw"]])
    assert asked[-1] == ["post 3", "post 2", "post 1", "post 5", "post 4"] and store.runs()[0]["meta"]["reads"]

    asked.clear()
    a_read(monkeypatch, (7, 30), [5], 5, 5)  # nothing new: the brief is left as it is, and the page says so
    assert cli.main(["run", "--now", "--label", "am"]) == 0 and asked == []
    assert server.live(page.at_of(early, meta), now=dt.datetime.now())["text"] == "Nothing new since 07:06."


def test_a_run_of_another_day_or_window_is_a_brief_of_its_own(monkeypatch):
    asked = a_writer(monkeypatch)
    a_read(monkeypatch, (5, 12), [3, 2, 1], 0, 3)
    cli.main(["run", "--now", "--label", "am"])
    a_read(monkeypatch, (17, 30), [5, 4, 3], 3, 5)
    cli.main(["run", "--now", "--label", "pm"])
    assert asked[-1] == ["post 5", "post 4"] and len(store.runs()) == 2
    assert cli.main(["run", "--now", "--label", "am", "--hours", "6"]) == 0  # a chosen window: its own brief
    assert len(store.runs()) == 3
