"""Paths, the job's environment and the run windows. One home for each setting."""

import os
import pathlib

HOME = pathlib.Path.home()
DATA = pathlib.Path(os.environ.get("XBRIEF_DATA_DIR", HOME / "Data" / "xbrief-data"))
SECRETS = DATA / "secrets"
ACCOUNTS_DB = SECRETS / "accounts.db"  # twscrape's login file: plain cookies, mode 600, never printed
RAW = DATA / "raw"  # one file a run, the pages as X sent them; kept RAW_KEEP_DAYS
BRIEFS = DATA / "briefs"  # what Caddy serves at xbrief.localhost
CACHE = DATA / "cache"  # X's script files, by their content-hashed names
LOGS = DATA / "logs"
STATE = DATA / "state.json"  # the newest post the last good run reached
SITE = DATA / "site.json"  # which site build the account is served, and its Following-tab request

CLAUDE = os.environ.get("XBRIEF_CLAUDE", str(HOME / ".local" / "bin" / "claude"))
MODEL = os.environ.get("XBRIEF_MODEL") or None  # None: the subscription's default model

RAW_KEEP_DAYS = 30
MAX_PAGES = 40  # hard cap a run (20 posts a page). Set from the first hand run's count.
FIRST_RUN_HOURS = 12  # with no earlier run, read back this far
PAGE_SIZE = 20  # what the website itself asks for

# Each run starts at a random minute inside its window, the laptop's own time.
# launchd fires at the window's start; the job sleeps a random part of the window first.
WINDOWS = {"am": ("05:30", "07:30"), "pm": ("17:00", "20:00")}

# The job's environment for twscrape (the xbrief fork). Set in code, so a hand run and the
# LaunchAgent behave the same.
TWS_ENV = {
    "TWS_TELEMETRY": "0",  # no PostHog usage tracking
    "DO_NOT_TRACK": "1",
    "TWS_HTTP_BACKEND": "curl",  # the browser-handshake backend
    "TWS_XHR_HEADERS": "1",  # the page's own fetch() headers, not page-load headers
    "TWS_RAISE_WHEN_NO_ACCOUNT": "1",  # a locked or logged-out account ends the run, never waits
    "TWS_CURL_RETRIES": "0",  # one attempt
    "TWS_FAIL_LIMIT": "1",  # no retry on the same account
    "TWS_XCLID_TRIES": "2",  # one refresh of a stale anti-bot id, no more
    "TWS_XCLID_PAGE": "https://x.com/home",  # the page a person on this account opens
}
# Same place as the operator: the home connection the browser uses. Never the tunnel or a proxy.
PROXY_VARS = ["TWS_PROXY", "ALL_PROXY", "all_proxy", "HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy"]


def apply_job_env() -> None:
    """Call before twscrape is imported."""
    os.environ.update(TWS_ENV)
    for k in PROXY_VARS:
        os.environ.pop(k, None)


def ensure_dirs() -> None:
    for d in (DATA, RAW, BRIEFS, CACHE, LOGS):
        d.mkdir(parents=True, exist_ok=True)
    SECRETS.mkdir(parents=True, exist_ok=True)
    os.chmod(SECRETS, 0o700)
    os.chmod(DATA, 0o700)
