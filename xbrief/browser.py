"""The operator's own Brave, on a profile kept for this job, driven over the DevTools protocol.

Why a real browser: everything X sees (the browser build, its connection fingerprint, headers, the anti-bot id,
the request names, the cookies) is produced by Brave and by x.com's own code, so nothing is imitated and a deploy
of x.com is followed the way any browser follows it. The job only opens the page, clicks the Following tab, scrolls
with the mouse wheel, and keeps the feed responses the page itself downloads.

How it stays quiet: Brave is started with no window, then one window is opened in the background (it never comes
to the front, checked 2026-10-12) and parked at the right edge of the rightmost screen, where macOS leaves 40 px of
it showing, behind the operator's windows. It is not hidden or minimised: a hidden page reports itself hidden (X's
x-twitter-active-user becomes "no") and stops drawing, so clicks and scrolling do nothing (checked 2026-10-12).
Background throttling is off, so a covered window keeps behaving as a visible, scrolled page. Nothing is evaluated inside the page: no Runtime domain, no injected script.
Only Page, Network, DOM (to find the tab) and Input are used.
"""

from __future__ import annotations

import asyncio
import json
import os
import pathlib
import subprocess
import time
from typing import Any


BRAVE_APP = os.environ.get("XBRIEF_BRAVE_APP", "/Applications/Brave Browser.app")
FLAGS = [
    "--no-first-run",
    "--no-default-browser-check",
    "--no-startup-window",
    "--remote-debugging-port=0",  # Brave picks a free port and writes it to DevToolsActivePort
    "--remote-debugging-address=127.0.0.1",
    "--disable-backgrounding-occluded-windows",
    "--disable-renderer-backgrounding",
    "--disable-background-timer-throttling",
]
WINDOW = {"width": 1440, "height": 900}


class BrowserError(Exception): ...


def launch(profile: pathlib.Path, extra: list[str] | None = None, background: bool = True) -> None:
    """Start a separate Brave instance on `profile`. `open -n` gives it its own process; `-g` and
    --no-startup-window keep it from taking the front."""
    profile.mkdir(parents=True, exist_ok=True)
    os.chmod(profile, 0o700)
    (profile / "DevToolsActivePort").unlink(missing_ok=True)
    cmd = ["open", "-n"] + (["-g"] if background else []) + ["-a", BRAVE_APP, "--args", f"--user-data-dir={profile}"]
    cmd += (FLAGS if background else [f for f in FLAGS if f != "--no-startup-window"]) + (extra or [])
    subprocess.run(cmd, check=True)


def running(profile: pathlib.Path) -> list[int]:
    r = subprocess.run(["pgrep", "-f", "--", f"--user-data-dir={profile}"], capture_output=True, text=True)
    return [int(x) for x in r.stdout.split()]


def park_left() -> int:
    """The x where a window shows only macOS's minimum 40 px: the right edge of the rightmost screen, less 40."""
    js = ('ObjC.import("AppKit");var s=$.NSScreen.screens,r=0;for(var i=0;i<s.count;i++){var f=s.objectAtIndex(i).frame;'
          'r=Math.max(r,f.origin.x+f.size.width)};r')
    out = subprocess.run(["osascript", "-l", "JavaScript", "-e", js], capture_output=True, text=True).stdout.strip()
    try:
        return int(float(out)) - 40
    except ValueError:
        return 0


class Browser:
    def __init__(self, profile: pathlib.Path):
        self.profile = profile
        self.port: int | None = None
        self._ws = None
        self._browser_ws = None
        self._id = 0
        self._pending: dict[int, asyncio.Future] = {}
        self.events: asyncio.Queue = asyncio.Queue()
        self._reader: asyncio.Task | None = None
        self.target_id: str | None = None

    # ── lifecycle ───────────────────────────────────────────────────────────────────────────────────

    async def start(self, park: bool = True, timeout: float = 30.0) -> "Browser":
        if running(self.profile):
            raise BrowserError("the job's Brave profile is already open (a login window, or a run that did not end)")
        launch(self.profile)
        port_file = self.profile / "DevToolsActivePort"
        t0 = time.monotonic()
        while not port_file.exists() or not port_file.read_text().strip():
            if time.monotonic() - t0 > timeout:
                raise BrowserError("Brave did not open its DevTools port")
            await asyncio.sleep(0.2)
        self.port = int(port_file.read_text().split()[0])
        from websockets.asyncio.client import connect

        version = await _get_json(f"http://127.0.0.1:{self.port}/json/version")
        self._browser_ws = await connect(version["webSocketDebuggerUrl"], max_size=None)
        made = await self._browser_call("Target.createTarget", {"url": "about:blank", "newWindow": True,
                                                                 "background": True, **WINDOW})
        self.target_id = made["targetId"]
        if park:
            win = await self._browser_call("Browser.getWindowForTarget", {"targetId": self.target_id})
            await self._browser_call("Browser.setWindowBounds",
                                     {"windowId": win["windowId"], "bounds": {"left": park_left(), "top": 120}})
        self._ws = await connect(f"ws://127.0.0.1:{self.port}/devtools/page/{self.target_id}", max_size=None)
        self._reader = asyncio.create_task(self._read())
        return self

    async def close(self) -> None:
        try:
            if self._browser_ws is not None:
                await self._browser_call("Browser.close", {})
        except Exception:
            pass
        for ws in (self._ws, self._browser_ws):
            try:
                if ws is not None:
                    await ws.close()
            except Exception:
                pass
        if self._reader:
            self._reader.cancel()
        for _ in range(50):
            if not running(self.profile):
                return
            await asyncio.sleep(0.2)
        for pid in running(self.profile):  # never leave a stray browser behind
            try:
                os.kill(pid, 15)
            except OSError:
                pass

    # ── protocol ────────────────────────────────────────────────────────────────────────────────────

    async def _browser_call(self, method: str, params: dict) -> dict:
        self._id += 1
        await self._browser_ws.send(json.dumps({"id": self._id, "method": method, "params": params}))
        while True:
            msg = json.loads(await asyncio.wait_for(self._browser_ws.recv(), 15))
            if msg.get("id") == self._id:
                if "error" in msg:
                    raise BrowserError(f"{method}: {msg['error'].get('message')}")
                return msg.get("result") or {}

    async def _read(self) -> None:
        try:
            async for raw in self._ws:
                msg = json.loads(raw)
                if "id" in msg and msg["id"] in self._pending:
                    fut = self._pending.pop(msg["id"])
                    if not fut.done():
                        fut.set_result(msg)
                elif "method" in msg:
                    await self.events.put(msg)
        except Exception as e:  # the page closed or the browser went away
            await self.events.put({"method": "xbrief.closed", "params": {"error": str(e)}})

    async def send(self, method: str, params: dict | None = None, timeout: float = 20.0) -> dict:
        self._id += 1
        i = self._id
        fut = asyncio.get_running_loop().create_future()
        self._pending[i] = fut
        await self._ws.send(json.dumps({"id": i, "method": method, "params": params or {}}))
        msg = await asyncio.wait_for(fut, timeout)
        if "error" in msg:
            raise BrowserError(f"{method}: {msg['error'].get('message')}")
        return msg.get("result") or {}

    # ── what the job does with it ───────────────────────────────────────────────────────────────────

    async def find_box(self, xpath: str) -> tuple[float, float] | None:
        """The centre of the first element an XPath finds, read through DOM (no script runs in the page)."""
        await self.send("DOM.getDocument", {"depth": 0})
        s = await self.send("DOM.performSearch", {"query": xpath})
        try:
            if not s.get("resultCount"):
                return None
            ids = (await self.send("DOM.getSearchResults", {"searchId": s["searchId"], "fromIndex": 0, "toIndex": 1}))["nodeIds"]
            if not ids or not ids[0]:
                return None
            q = (await self.send("DOM.getBoxModel", {"nodeId": ids[0]}))["model"]["content"]
            return (q[0] + q[2] + q[4] + q[6]) / 4, (q[1] + q[3] + q[5] + q[7]) / 4
        finally:
            await self.send("DOM.discardSearchResults", {"searchId": s["searchId"]})

    async def click(self, x: float, y: float) -> None:
        await self.send("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x, "y": y})
        await asyncio.sleep(0.08)
        await self.send("Input.dispatchMouseEvent", {"type": "mousePressed", "x": x, "y": y, "button": "left", "clickCount": 1})
        await asyncio.sleep(0.07)
        await self.send("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": x, "y": y, "button": "left", "clickCount": 1})

    async def key(self, name: str) -> None:
        codes = {"Escape": 27}
        base = {"key": name, "code": name, "windowsVirtualKeyCode": codes[name], "nativeVirtualKeyCode": codes[name]}
        await self.send("Input.dispatchKeyEvent", {"type": "rawKeyDown", **base})
        await asyncio.sleep(0.06)
        await self.send("Input.dispatchKeyEvent", {"type": "keyUp", **base})

    async def at_bottom(self, within: float = 1.5) -> bool:
        """Whether the page is scrolled to within `within` viewports of its end (Page.getLayoutMetrics: no script
        runs). True when the metrics cannot be read, so a caller never scrolls forever on their account."""
        try:
            m = await self.send("Page.getLayoutMetrics")
            vp, cs = m["cssVisualViewport"], m["cssContentSize"]
            return vp["pageY"] + vp["clientHeight"] >= cs["height"] - within * vp["clientHeight"]
        except (BrowserError, KeyError, TypeError):
            return True

    async def wheel(self, dy: float, x: float | None = None, y: float | None = None) -> None:
        x = WINDOW["width"] / 2 if x is None else x
        y = WINDOW["height"] / 2 if y is None else y
        await self.send("Input.dispatchMouseEvent", {"type": "mouseWheel", "x": x, "y": y, "deltaX": 0, "deltaY": dy})


async def _get_json(url: str) -> Any:
    def get():
        import urllib.request

        with urllib.request.urlopen(url, timeout=5) as r:
            return json.load(r)

    return await asyncio.to_thread(get)


def login_window(profile: pathlib.Path, url: str = "https://x.com/login") -> None:
    """For the operator: the job's profile in an ordinary Brave window, at the front."""
    if running(profile):
        raise BrowserError("the job's Brave profile is already open")
    profile.mkdir(parents=True, exist_ok=True)
    os.chmod(profile, 0o700)
    subprocess.run(["open", "-n", "-a", BRAVE_APP, "--args", f"--user-data-dir={profile}", "--no-first-run",
                    "--no-default-browser-check", url], check=True)

