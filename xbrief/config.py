"""Paths, caps and run windows. One home for each setting."""

import os
import pathlib

HOME = pathlib.Path.home()
DATA = pathlib.Path(os.environ.get("XBRIEF_DATA_DIR", HOME / "Data" / "xbrief-data"))
SECRETS = DATA / "secrets"
PROFILE = SECRETS / "brave"  # the job's own Brave profile: the X login lives here, never read by a session
OLD_LOGIN = SECRETS / "accounts.db"  # the twscrape login of the first build; `xbrief login` deletes it
RAW = DATA / "raw"  # one file a run, the feed pages as x.com downloaded them; kept RAW_KEEP_DAYS
LOGS = DATA / "logs"
STATE = DATA / "state.json"  # the newest post the last good run reached
DB = DATA / "xbrief.db"  # every brief and every post read, kept for history and search (store.py)
LOCK = DATA / "run.lock"  # held by the one run going (flock), whoever started it
PROGRESS = DATA / "progress.json"  # what the run going (or the last one) is doing, for the page

HOST, PORT = "127.0.0.1", 8795  # the app (server.py), behind Caddy at xbrief.localhost

HOME_URL = os.environ.get("XBRIEF_HOME_URL", "https://x.com/home")
CLAUDE = os.environ.get("XBRIEF_CLAUDE", str(HOME / ".local" / "bin" / "claude"))
MODEL = os.environ.get("XBRIEF_MODEL") or "claude-opus-5-5"  # the writer: Opus (operator, 2026-10-12; never
# Sonnet); named, so it never follows the subscription's default

# The sites tab (sites.py): public pages read once a day, direct, each new post summarised. A source lists its posts
# in an RSS feed or a sitemap (`match`: the part of a post's address that marks it as a post).
# `x`: the people behind a source, by X handle (accounts the operator follows); the Sites page shows their posts
# from the Following tab's reads beside the source's write-ups, and never reads their profiles
SITES = [
    {"key": "sigil", "name": "Sigil Fund", "home": "https://www.sigilfund.com/insights",
     "list": "https://www.sigilfund.com/sitemap.xml", "kind": "sitemap", "match": "/blog/", "x": ["Fiskantes"]},
    {"key": "zeeprime", "name": "Zee Prime", "home": "https://zeeprime.capital/writing/",
     "list": "https://zeeprime.capital/rss/", "kind": "rss"},
    # Capriole moved its updates to Substack in May 2026 (capriole.com/update-70 says so); the feed carries each post whole
    {"key": "capriole", "name": "Capriole", "home": "https://caprioleio.substack.com/",
     "list": "https://caprioleio.substack.com/feed", "kind": "rss", "x": ["caprioleio"]},
]
SITE_MODEL = os.environ.get("XBRIEF_SITE_MODEL") or "claude-fable-5-1"  # Fable for summaries (operator, 2026-10-12)
SITES_LOCK = DATA / "sites.lock"  # held by the one site check going
SITES_X_MAX = 120  # the Sites page's right-hand column: at most this many of the people's posts
SITES_X_SCAN = 2000  # of each source's people's newest posts kept, matched against its write-ups' topics
SITES_AFTER = "07:00"  # the daily check runs at the first look after this, local time, once a day

RAW_KEEP_DAYS = 30
MAX_PAGES = 20  # hard cap a run: a Recent page holds ~85 entries, a day is ~5 pages (hand run 2026-10-12)
MAX_MINUTES = 40  # hard cap on one run's scrolling
FIRST_RUN_HOURS = 24  # with no earlier run, read back this far (operator, 2026-10-12: a full day)

# Each scheduled run starts at a random minute inside its window, the laptop's own time. These are the
# defaults: the operator sets the windows, and turns the schedule on or off, on the page (store.settings).
WINDOWS = {"am": ("05:30", "07:30"), "pm": ("17:00", "20:00")}


def ensure_dirs() -> None:
    for d in (DATA, RAW, LOGS):
        d.mkdir(parents=True, exist_ok=True)
    SECRETS.mkdir(parents=True, exist_ok=True)
    os.chmod(SECRETS, 0o700)
    os.chmod(DATA, 0o700)
