"""Paths, caps and run windows. One home for each setting."""

import os
import pathlib

HOME = pathlib.Path.home()
DATA = pathlib.Path(os.environ.get("XBRIEF_DATA_DIR", HOME / "Data" / "xbrief-data"))
SECRETS = DATA / "secrets"
PROFILE = SECRETS / "brave"  # the job's own Brave profile: the X login lives here, never read by a session
OLD_LOGIN = SECRETS / "accounts.db"  # the twscrape login of the first build; `xbrief login` deletes it
RAW = DATA / "raw"  # one file a run, the feed pages as x.com downloaded them; kept RAW_KEEP_DAYS
BRIEFS = DATA / "briefs"  # what Caddy serves at xbrief.localhost
LOGS = DATA / "logs"
STATE = DATA / "state.json"  # the newest post the last good run reached

HOME_URL = os.environ.get("XBRIEF_HOME_URL", "https://x.com/home")
CLAUDE = os.environ.get("XBRIEF_CLAUDE", str(HOME / ".local" / "bin" / "claude"))
MODEL = os.environ.get("XBRIEF_MODEL") or None  # None: the subscription's default model

RAW_KEEP_DAYS = 30
MAX_PAGES = 20  # hard cap a run: a Recent page holds ~85 entries, a day is ~5 pages (hand run 2026-10-12)
MAX_MINUTES = 40  # hard cap on one run's scrolling
FIRST_RUN_HOURS = 24  # with no earlier run, read back this far (operator, 2026-10-12: a full day)

# Each run starts at a random minute inside its window, the laptop's own time.
# launchd fires at the window's start; the job sleeps a random part of the window first.
WINDOWS = {"am": ("05:30", "07:30"), "pm": ("17:00", "20:00")}


def ensure_dirs() -> None:
    for d in (DATA, RAW, BRIEFS, LOGS):
        d.mkdir(parents=True, exist_ok=True)
    SECRETS.mkdir(parents=True, exist_ok=True)
    os.chmod(SECRETS, 0o700)
    os.chmod(DATA, 0o700)
