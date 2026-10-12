"""One run at a time, what it is doing, and the schedule that starts the two daily ones.

The lock is an flock on `run.lock`, held by `xbrief run` for its whole life, whoever started it (the page, the
schedule, a terminal): the kernel lets go of it when the process ends, however it ends. The run tells the page
what it is doing through `progress.json`.

The server starts a run as its own process in its own session, so restarting the server never kills a read halfway
(its Brave would be left open). The schedule lives here, not in launchd, so the page can turn it on and off and
move its windows: one decision, one home (store.settings).
"""

from __future__ import annotations

import datetime as dt
import fcntl
import json
import os
import random
import subprocess
import sys
import time
from pathlib import Path

from . import config, store

REPO = Path(__file__).resolve().parent.parent
RECENT_RUN_MS = 60 * 60_000  # a slot that falls due within an hour of another run's start is skipped


# ── the lock ────────────────────────────────────────────────────────────────────────────────────────


def take_lock():
    """The open lock file, held; None if a run already holds it. Keep the returned file open for the run's life."""
    config.LOCK.parent.mkdir(parents=True, exist_ok=True)
    f = open(config.LOCK, "a+")
    try:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        f.close()
        return None
    return f


def running() -> bool:
    f = take_lock()
    if f is None:
        return True
    f.close()  # closing lets go of it
    return False


# ── progress ────────────────────────────────────────────────────────────────────────────────────────


def write_progress(**kw) -> None:
    cur = read_progress() if not kw.get("fresh") else {}
    kw.pop("fresh", None)
    cur.update(kw, updated_ms=int(time.time() * 1000))
    tmp = config.PROGRESS.with_suffix(".part")
    tmp.write_text(json.dumps(cur))
    tmp.replace(config.PROGRESS)


def read_progress() -> dict:
    try:
        return json.loads(config.PROGRESS.read_text())
    except (OSError, ValueError):
        return {}


# ── starting a run ──────────────────────────────────────────────────────────────────────────────────


def label_now(now: dt.datetime | None = None) -> str:
    return "am" if (now or dt.datetime.now()).hour < 12 else "pm"


def run_cmd(label: str, hours: float | None) -> list[str]:
    cmd = [sys.executable, "-m", "xbrief", "run", "--now", "--label", label]
    if hours is not None:
        cmd += ["--hours", f"{hours:g}"]
    return cmd


def start(label: str | None = None, hours: float | None = None, by: str = "page") -> bool:
    """Start `xbrief run` in the background. False if one is already going."""
    if running():
        return False
    label = label or label_now()
    write_progress(fresh=True, phase="starting", label=label, hours=hours, by=by,
                   started_ms=int(time.time() * 1000), done=False)
    config.LOGS.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "PYTHONPATH": str(REPO), "PYTHONUNBUFFERED": "1"}
    with open(config.LOGS / "runs.log", "a") as log:
        subprocess.Popen(run_cmd(label, hours), cwd=REPO, env=env, stdin=subprocess.DEVNULL, stdout=log,
                         stderr=subprocess.STDOUT, start_new_session=True)
    return True


# ── the schedule ────────────────────────────────────────────────────────────────────────────────────


def _at(day: dt.date, hhmm: str) -> dt.datetime:
    return dt.datetime.combine(day, dt.time(int(hhmm[:2]), int(hhmm[3:5])))


def pick_fire(day: dt.date, window: list[str], rng: random.Random) -> int:
    """A random minute in the window, leaving the read and the writing time before its end (15 minutes)."""
    start, end = _at(day, window[0]), _at(day, window[1]) - dt.timedelta(minutes=15)
    t = start + dt.timedelta(seconds=rng.uniform(0, max(0.0, (end - start).total_seconds())))
    return int(t.timestamp() * 1000)


def fill_day(day: dt.date, sett: dict, rng: random.Random, skip_ended_before: dt.datetime | None = None) -> None:
    """Make today's slots. With `skip_ended_before` (the schedule was just turned on or moved), a window already
    over is recorded as skipped, so turning it on at night does not start the morning's run."""
    key = day.isoformat()
    have = store.slots(key)
    for label, window in sett["windows"].items():
        if label in have:
            continue
        over = skip_ended_before is not None and _at(day, window[1]) <= skip_ended_before
        store.put_slot(key, label, pick_fire(day, window, rng), -1 if over else None)


def due(now: dt.datetime, sett: dict, last_run_ms: int | None, rng: random.Random) -> str | None:
    """The label to run now, if any, and the slot bookkeeping that goes with it. A laptop asleep through a window
    runs it late on waking, as launchd would; if two are due at once only the later runs (it reads from where the
    last run stopped, so nothing is lost) and the earlier is skipped. A slot that falls due within an hour of another
    run's start (a hand run) is skipped."""
    if not sett.get("schedule"):
        return None
    fill_day(now.date(), sett, rng)
    key, now_ms = now.date().isoformat(), int(now.timestamp() * 1000)
    ready = sorted((s["fire_ms"], label) for label, s in store.slots(key).items()
                   if s["fired_ms"] is None and s["fire_ms"] <= now_ms and label in sett["windows"])
    if not ready:
        return None
    for _, label in ready[:-1]:
        store.mark_slot(key, label, -1)
    fire_ms, label = ready[-1]
    if last_run_ms and now_ms - last_run_ms < RECENT_RUN_MS:
        store.mark_slot(key, label, -1)
        return None
    store.mark_slot(key, label, now_ms)
    return label


def next_fire(now: dt.datetime) -> int | None:
    """When the schedule starts its next run today, or None."""
    s = [x["fire_ms"] for x in store.slots(now.date().isoformat()).values() if x["fired_ms"] is None]
    return min(s) if s else None


def apply_settings(new: dict, now: dt.datetime | None = None) -> dict:
    """Store new settings; a change of schedule redraws today's slots that have not run."""
    now = now or dt.datetime.now()
    store.save_settings(new)
    sett = store.settings()
    store.forget_unfired(now.date().isoformat())
    if sett["schedule"]:
        fill_day(now.date(), sett, random.Random(), skip_ended_before=now)
    return sett


def tick(now: dt.datetime | None = None, rng: random.Random | None = None, starter=start) -> str | None:
    """One look at the clock (the server calls this every 20 s). Waits while a run is going."""
    if running():
        return None
    now = now or dt.datetime.now()
    starts = [r["started_ms"] for r in store.runs(limit=1)] + [read_progress().get("started_ms") or 0]
    last_ms = max(starts) or None
    label = due(now, store.settings(), last_ms, rng or random.Random())
    if label and starter(label=label, by="schedule"):
        return label
    return None
