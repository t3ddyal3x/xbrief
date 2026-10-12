"""Every test runs offline in a throwaway data dir: the real login, raw pages and briefs are never touched."""

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


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*a, **kw):
        raise RuntimeError("a test tried to open a network connection")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


@pytest.fixture(autouse=True)
def fresh_data(monkeypatch, tmp_path):
    """Each test gets its own empty data dir."""
    d = tmp_path / "data"
    for name, sub in [("DATA", ""), ("SECRETS", "secrets"), ("RAW", "raw"), ("BRIEFS", "briefs"), ("CACHE", "cache"),
                      ("LOGS", "logs")]:
        monkeypatch.setattr(config, name, d / sub if sub else d)
    monkeypatch.setattr(config, "ACCOUNTS_DB", d / "secrets" / "accounts.db")
    monkeypatch.setattr(config, "STATE", d / "state.json")
    monkeypatch.setattr(config, "SITE", d / "site.json")
    config.ensure_dirs()
    yield d
