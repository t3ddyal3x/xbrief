"""Every test runs in a throwaway data dir, so the real login, raw pages and briefs are never touched. Tests are
offline, except those marked `browser`, which drive the real Brave against a fake x.com on loopback and run only
with `bin/tests --browser`."""

import os
import pathlib
import socket
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix="xbrief-test-")
os.environ["XBRIEF_DATA_DIR"] = _TMP  # before xbrief.config is imported anywhere
sys.path.insert(0, str(pathlib.Path(__file__).parent))

import pytest  # noqa: E402

from xbrief import config  # noqa: E402

assert str(config.DATA) == _TMP, "tests must not see the real data dir"


def pytest_configure(config):
    config.addinivalue_line("markers", "browser: drives the real Brave against a fake x.com (bin/tests --browser)")


def pytest_collection_modifyitems(config, items):
    if os.environ.get("XBRIEF_BROWSER_TESTS") == "1":
        return
    skip = pytest.mark.skip(reason="needs Brave: bin/tests --browser")
    for item in items:
        if item.get_closest_marker("browser"):
            item.add_marker(skip)


@pytest.fixture(autouse=True)
def no_network(monkeypatch, request):
    if request.node.get_closest_marker("browser"):
        return  # loopback only: a local Brave and a fake x.com

    def refuse(*a, **kw):
        raise RuntimeError("a test tried to open a network connection")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


@pytest.fixture(autouse=True)
def fresh_data(monkeypatch, tmp_path):
    """Each test gets its own empty data dir."""
    d = tmp_path / "data"
    for name, sub in [("DATA", ""), ("SECRETS", "secrets"), ("RAW", "raw"), ("LOGS", "logs"), ("DB", "xbrief.db"),
                      ("LOCK", "run.lock"), ("PROGRESS", "progress.json")]:
        monkeypatch.setattr(config, name, d / sub if sub else d)
    monkeypatch.setattr(config, "PROFILE", d / "secrets" / "brave")
    monkeypatch.setattr(config, "OLD_LOGIN", d / "secrets" / "old-login")
    monkeypatch.setattr(config, "STATE", d / "state.json")
    config.ensure_dirs()
    yield d
