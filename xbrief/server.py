"""The xbrief app: one local server, its pages, the run button, and the schedule.

    bin/xbrief serve           (the LaunchAgent com.xbrief.app runs this; http://xbrief.localhost)

    /                   the newest brief
    /b/<name>           one brief (2026-10-12-0857-am)
    /theses, /b/<name>/theses   the same brief (the Theses tab is now the brief's Theses part)
    /history            every brief, and the schedule
    /sites              what the sites on the list posted, each read and summarised (sites.py)
    /search?q=&since=&until=    every post kept: words, @accounts, dates
    /api/status         what a run is doing, or when the next one starts (the page asks every few seconds)
    POST /api/run       {"hours": null | 1..168}: start a run now (409 while one is going)
    POST /api/settings  {"schedule": bool, "windows": {"am": [from, to], "pm": [from, to]}, "off": ["pm"]}
    POST /api/sites     {"daily": bool} to set the daily check, or {"check": true} to check the sites now
    /api/sites          whether a site check is going, and when the last one ended
    /api/health         what the doctor reads

LOCALHOST ONLY, the perimeter macro and Hyperlitmus use (restated, not imported: no app imports another's code):
bind 127.0.0.1, refuse a `Host` that is not a loopback name (DNS rebinding) and an `Origin` from another site. The
two writes also want a JSON body, which a cross-site form cannot send: a web page elsewhere must never be able to
start a read of the operator's X account. Nothing is cached by the browser (`no-store`).

The server reads X never: a run is its own process (`runner.start`), and the schedule thread here only starts one.
"""

from __future__ import annotations

import datetime as dt
import json
import re
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from . import config, page, runner, sites, store, videos

STATIC = Path(__file__).resolve().parent / "static"
FILES = {"/app.css": ("app.css", "text/css; charset=utf-8"), "/app.js": ("app.js", "text/javascript; charset=utf-8")}
RUN_NAME = re.compile(r"^/b/(\d{4}-\d{2}-\d{2}-\d{4}-(?:am|pm))(/theses)?$")
HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
MAX_POST = 4096
TICK_S = 20
READY_FOR_MS = 30 * 60_000  # how long the rail offers a new brief
PHASES = {"starting": "Starting", "opening Brave": "Opening Brave", "opening x.com": "Opening x.com",
          "writing the brief": "Writing the brief"}


def live(at: str | None = None, now: dt.datetime | None = None) -> dict:
    """The rail's one line: what a run is doing, a brief just written, a run that failed, or the next run."""
    now = now or dt.datetime.now()
    now_ms = int(now.timestamp() * 1000)
    pr = runner.read_progress()
    on = runner.running() or runner.just_started(now_ms)
    if on:
        phase = pr.get("phase") or "starting"
        if phase == "reading":
            text = f"Reading · {pr.get('pages', 0)} pages · {pr.get('posts', 0)} posts"
        elif phase == "reading Articles":
            text = f"Reading Articles · {pr.get('articles', 0) + 1} of {pr.get('of', 0)}"
        elif phase == "transcribing videos":
            text = f"Transcribing videos · {pr.get('videos', 0) + 1} of {pr.get('of', 0)}"
            return {"running": True, "kind": "on", "text": text, "slow": True}
        elif phase == "writing the brief" and pr.get("writing_ms"):  # the long part: say how long it has run
            mins = max(0, now_ms - pr["writing_ms"]) // 60_000
            text = f"Writing the brief · {pr.get('posts', 0)} posts" + (f" · {mins} min" if mins else "")
            return {"running": True, "kind": "on", "text": text, "slow": True}  # the page asks every 5 s, not 1.5
        else:
            text = PHASES.get(phase, phase.capitalize())
        return {"running": True, "kind": "on", "text": text}
    recent = now_ms - (pr.get("updated_ms") or 0) < READY_FOR_MS
    if pr.get("phase") == "failed" and recent:
        return {"running": False, "kind": "bad", "text": f"The last run failed: {pr.get('error')}"}
    if pr.get("done") is False and pr.get("phase") and recent:
        return {"running": False, "kind": "bad", "text": "The last run ended without finishing (logs/runs.log)."}
    if pr.get("done") and pr.get("name") and (pr.get("at") or pr["name"]) != at and recent:
        if pr.get("normal") is False:  # the brief says so at its top too
            return {"running": False, "kind": "bad", "text": f"The run stopped early: {pr.get('stop')}.",
                    "href": f"/b/{pr['name']}", "link": "Open"}
        caught = pr.get("at", pr["name"]) != pr["name"]  # a morning's brief written again with a later read
        return {"running": False, "kind": "", "text": "Brief caught up." if caught else "New brief.",
                "href": f"/b/{pr['name']}", "link": "Open"}
    if pr.get("done") and pr.get("note") and recent:  # a catch-up that found nothing new
        return {"running": False, "kind": "", "text": pr["note"]}
    sett = store.settings()
    if not sett["schedule"]:
        return {"running": False, "kind": "", "text": "Schedule off.", "href": "/history#schedule", "link": "Set"}
    nxt = runner.next_fire(now)
    return {"running": False, "kind": "",
            "text": f"Next run {page.hhmm(nxt)}." if nxt else "Next run tomorrow."}


def check_settings(body: dict) -> dict:
    """The schedule as sent by the page, checked: two windows of HH:MM, each at least 20 minutes long, and the
    ones switched off (their times kept)."""
    if not isinstance(body.get("schedule"), bool):
        raise ValueError("schedule must be true or false")
    wins = body.get("windows")
    if not isinstance(wins, dict) or set(wins) != set(config.WINDOWS):
        raise ValueError("a morning and an evening window")
    out = {}
    for k, w in wins.items():
        if not (isinstance(w, list) and len(w) == 2 and all(isinstance(x, str) and HHMM.match(x) for x in w)):
            raise ValueError("times as HH:MM")
        a, b = (int(x[:2]) * 60 + int(x[3:]) for x in w)
        if b - a < 20:
            raise ValueError(f"the {page.LABELS[k]} window must run at least 20 minutes")
        out[k] = w
    off = body.get("off", [])
    if not (isinstance(off, list) and set(off) <= set(config.WINDOWS)):
        raise ValueError("off: the windows switched off")
    return {"schedule": body["schedule"], "windows": out, "off": sorted(set(off))}


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "xbrief"
    timeout = 10

    def log_message(self, fmt, *args):
        pass

    @staticmethod
    def _hostname(authority: str) -> str:
        a = authority.strip().lower()
        return a.split("]")[0] + "]" if a.startswith("[") else a.split(":")[0]

    @classmethod
    def _is_local(cls, authority: str) -> bool:
        n = cls._hostname(authority)
        return n in {"127.0.0.1", "localhost", "::1", "[::1]"} or n.endswith(".localhost")

    def parse_request(self) -> bool:  # noqa: N802
        if not super().parse_request():
            return False
        host = self.headers.get("Host")
        if host is not None and not self._is_local(host):
            self.send_error(421, "this server answers for localhost only")
            return False
        origin = self.headers.get("Origin")
        if origin is not None and not self._is_local(urlparse(origin).netloc):
            self.send_error(403, "cross-site requests are not accepted")
            return False
        return True

    def _send(self, body: bytes, ctype: str, code: int = 200) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Security-Policy", page.CSP)
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _html(self, text: str, code: int = 200) -> None:
        self._send(text.encode(), "text/html; charset=utf-8", code)

    def _json(self, payload, code: int = 200) -> None:
        self._send(json.dumps(payload, separators=(",", ":")).encode(), "application/json", code)

    def do_HEAD(self):  # noqa: N802
        self.do_GET()

    def _body(self) -> dict:
        ctype = self.headers.get("Content-Type", "").split(";")[0].strip().lower()
        n = int(self.headers.get("Content-Length") or 0)
        if ctype != "application/json" or not 0 < n <= MAX_POST:
            raise ValueError("a JSON body")
        body = json.loads(self.rfile.read(n))
        if not isinstance(body, dict):
            raise ValueError("a JSON object")
        return body

    def do_POST(self):  # noqa: N802
        path = urlparse(self.path).path
        try:
            body = self._body()
            if path == "/api/run":
                hours = body.get("hours")
                if hours is not None and (isinstance(hours, bool) or not isinstance(hours, (int, float))
                                          or not 1 <= hours <= 168):
                    raise ValueError("hours from 1 to 168, or null for since the last brief")
                if not runner.start(hours=hours, by="page"):
                    return self._json({"error": "a run is already going"}, 409)
                return self._json({"started": True, "live": live()}, 202)
            if path == "/api/settings":
                sett = runner.apply_settings(check_settings(body))
                return self._json({"settings": sett, "live": live()})
            if path == "/api/sites":
                if body.get("check") is True:
                    if not sites.start(by="page"):
                        return self._json({"error": "a check is already going"}, 409)
                    return self._json({"started": True}, 202)
                if not isinstance(body.get("daily"), bool):
                    raise ValueError("daily must be true or false, or check true")
                store.save_settings({"sites_daily": body["daily"]})
                return self._json({"daily": body["daily"]})
            return self._json({"error": "no such route"}, 404)
        except ValueError as e:
            return self._json({"error": str(e)}, 400)
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            return self._json({"error": type(e).__name__}, 500)

    def do_GET(self):  # noqa: N802
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        path = unquote(u.path)
        try:
            if path in FILES:
                name, ctype = FILES[path]
                return self._send((STATIC / name).read_bytes(), ctype)
            if path == "/api/status":
                return self._json(live(q.get("at")))
            if path == "/api/sites":
                return self._json({"checking": sites.running() or sites.just_started(),
                                   "checked_ms": store.settings().get("sites_checked_ms")})
            if path == "/sites":
                lv = live()
                key = q.get("s", "") if q.get("s") in {sites.group(s) for s in config.SITES} else ""
                text = q.get("q", "")[:200]
                words = store.parse_query(text)[1]
                shown = [s for s in config.SITES if not key or sites.group(s) == key]
                docs = [d for d in store.site_posts() if d["source"] in {s["key"] for s in shown} and sites.matches(d, words)]
                lines = {d["url"]: sites.found_lines(d.get("text") or "", words) for d in docs} if words else {}
                return self._html(page.sites_page(docs, config.SITES, store.settings(), store.site_counts(),
                                                  sites.running() or sites.just_started(), lv, lv["running"],
                                                  key, text, words, lines))
            if path == "/api/health":
                return self._json({"ok": True, "port": config.PORT, "running": runner.running(), **store.counts(),
                                   "schedule": store.settings()["schedule"]})
            m = RUN_NAME.match(path)
            if path in ("/", "/theses") or m:
                name = m.group(1) if m else store.latest_name()
                run = store.load_run(name) if name else None  # /theses: the tab it once had, now the brief's Theses
                lv = live(page.at_of(name, run["meta"]) if run else name)
                if name is None:
                    return self._html(page.empty_page(lv, lv["running"]))
                if run is None:
                    return self._html(page.shell("X brief", page.topbar("brief", lv, running=lv["running"]),
                                                 '<p class="empty">No brief by that name. <a href="/history">Every '
                                                 'brief</a>.</p>'), 404)
                return self._html(page.brief_page(run, store.runs(), lv, lv["running"]))
            if path.startswith("/video/"):
                doc = videos.kept(path.removeprefix("/video/"))
                lv = live()
                if doc is None:
                    return self._html(page.shell("X brief", page.topbar("", lv, running=lv["running"]),
                                                 '<p class="empty">No video by that name.</p>'), 404)
                return self._html(page.video_page(doc, lv, lv["running"]))
            if path == "/history":
                lv = live()
                return self._html(page.history_page(store.runs(), store.settings(),
                                                    store.slots(dt.date.today().isoformat()), lv, lv["running"]))
            if path == "/search":
                lv = live()
                text, since, until = q.get("q", "")[:200], q.get("since", ""), q.get("until", "")
                hits, cut = store.search(text, since, until)
                titles = {r["name"]: page.run_title(r["label"], r["started_ms"]) for r in store.runs()}
                return self._html(page.search_page(text, since, until, hits, cut, store.counts(), titles, lv,
                                                   lv["running"]))
            return self._json({"error": "no such route"}, 404)
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            return self._json({"error": type(e).__name__}, 500)


def schedule_loop(stop: threading.Event) -> None:
    while True:  # a look at once on start, then every TICK_S
        try:
            label = runner.tick()
            if label:
                print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} schedule: started the {page.LABELS[label]} run", flush=True)
        except Exception:  # noqa: BLE001  the page keeps serving; the next tick tries again
            traceback.print_exc()
        try:
            if sites.tick():
                print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} schedule: started the daily site check", flush=True)
        except Exception:  # noqa: BLE001
            traceback.print_exc()
        if stop.wait(TICK_S):
            return


def serve(port: int = config.PORT) -> None:
    config.ensure_dirs()
    store.counts()  # makes the database before the first request
    stop = threading.Event()
    threading.Thread(target=schedule_loop, args=(stop,), daemon=True, name="schedule").start()
    httpd = ThreadingHTTPServer((config.HOST, port), Handler)
    httpd.daemon_threads = True
    print(f"xbrief on http://{config.HOST}:{port}  (http://xbrief.localhost)", flush=True)
    try:
        httpd.serve_forever()
    finally:
        stop.set()
