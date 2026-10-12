"""Every brief and every post read, in one SQLite file (`~/Data/xbrief-data/xbrief.db`), for the page's history and
search, plus the page's settings and the schedule's memory.

A run is stored whole when its brief is written (`cli.publish`): its meta, the writer's topics, its conversations,
and each post, which is kept once however many runs saw it. Posts are kept for good: a post is a few hundred bytes of
text, and the raw pages they came from are pruned after 30 days. Runs write and the server reads, in two processes;
WAL lets them share the file.

Search is SQLite's own full-text index over each post's words (with what it reposts or quotes) and its accounts.
"""

from __future__ import annotations

import contextlib
import datetime as dt
import json
import re
import sqlite3

from . import config
from .brief import Brief, Topic
from .parse import Post

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT UNIQUE NOT NULL,          -- 2026-10-12-0857-am: the run's start and label
  label TEXT NOT NULL,
  started_ms INTEGER NOT NULL,
  meta TEXT NOT NULL,                 -- collect.Result.meta()
  brief TEXT NOT NULL,                -- {topics: [{title, summary, posts}], other: [...], writer_error}
  threads TEXT NOT NULL,              -- [[post id, ...], ...]: conversations of three posts or more, in order
  n_posts INTEGER NOT NULL,
  n_topics INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS posts (
  id TEXT PRIMARY KEY,
  handle TEXT NOT NULL,
  created_ms INTEGER NOT NULL,
  doc TEXT NOT NULL                   -- parse.Post.to_dict()
);
CREATE INDEX IF NOT EXISTS posts_handle ON posts (handle COLLATE NOCASE, created_ms);
CREATE INDEX IF NOT EXISTS posts_created ON posts (created_ms);
CREATE TABLE IF NOT EXISTS run_posts (
  run_id INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
  post_id TEXT NOT NULL,
  PRIMARY KEY (run_id, post_id)
);
CREATE INDEX IF NOT EXISTS run_posts_post ON run_posts (post_id);
CREATE VIRTUAL TABLE IF NOT EXISTS posts_fts USING fts5 (
  post_id UNINDEXED, body, who, tokenize = 'unicode61 remove_diacritics 2'
);
CREATE TABLE IF NOT EXISTS schedule (
  day TEXT NOT NULL,                  -- 2026-10-12, local
  label TEXT NOT NULL,
  fire_ms INTEGER NOT NULL,
  fired_ms INTEGER,                   -- NULL: not yet; -1: skipped
  PRIMARY KEY (day, label)
);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""

DEFAULTS = {"schedule": False, "windows": {k: list(v) for k, v in config.WINDOWS.items()}}


@contextlib.contextmanager
def db():
    con = sqlite3.connect(config.DB, timeout=15)
    con.row_factory = sqlite3.Row
    try:
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA foreign_keys=ON")
        con.executescript(SCHEMA)
        with con:
            yield con
    finally:
        con.close()


# ── runs ────────────────────────────────────────────────────────────────────────────────────────────


def _body(p: Post) -> str:
    parts = [p.text]
    for inner in (p.retweet_of, p.quote, p.retweet_of and p.retweet_of.quote):
        if inner:
            parts.append(inner.text)
    parts += [ln.get("url") or "" for ln in p.links]
    return "\n".join(x for x in parts if x)


def _who(p: Post) -> str:
    out = [p.handle, p.name]
    for inner in (p.retweet_of, p.quote):
        if inner:
            out += [inner.handle, inner.name]
    return " ".join(x for x in out if x)


def save_run(name: str, label: str, meta: dict, b: Brief, posts: dict[str, Post], threads: list[list[str]]) -> int:
    """Store one run whole. Writing a run again (a rebrief) replaces it."""
    doc = {"topics": [t.__dict__ for t in b.topics], "other": b.other, "writer_error": b.writer_error}
    with db() as con:
        con.execute("DELETE FROM runs WHERE name = ?", (name,))
        cur = con.execute(
            "INSERT INTO runs (name, label, started_ms, meta, brief, threads, n_posts, n_topics) VALUES (?,?,?,?,?,?,?,?)",
            (name, label, int(meta.get("started_ms") or 0), json.dumps(meta), json.dumps(doc), json.dumps(threads),
             len(posts), len(b.topics)))
        run_id = cur.lastrowid
        for p in posts.values():
            con.execute("INSERT INTO posts (id, handle, created_ms, doc) VALUES (?,?,?,?) ON CONFLICT(id) DO UPDATE "
                        "SET handle = excluded.handle, created_ms = excluded.created_ms, doc = excluded.doc",
                        (p.id, p.handle, p.created_ms, json.dumps(p.to_dict(), ensure_ascii=False)))
            con.execute("DELETE FROM posts_fts WHERE post_id = ?", (p.id,))
            con.execute("INSERT INTO posts_fts (post_id, body, who) VALUES (?,?,?)", (p.id, _body(p), _who(p)))
            con.execute("INSERT OR IGNORE INTO run_posts (run_id, post_id) VALUES (?,?)", (run_id, p.id))
    return run_id


def runs(limit: int = 500) -> list[dict]:
    """Newest first: name, label, started_ms, meta, n_posts, n_topics."""
    with db() as con:
        rows = con.execute("SELECT name, label, started_ms, meta, n_posts, n_topics, json_extract(brief, '$.writer_error') "
                           "AS writer_error FROM runs ORDER BY started_ms DESC, id DESC LIMIT ?", (limit,)).fetchall()
    return [{**dict(r), "meta": json.loads(r["meta"])} for r in rows]


def latest_name() -> str | None:
    with db() as con:
        r = con.execute("SELECT name FROM runs ORDER BY started_ms DESC, id DESC LIMIT 1").fetchone()
    return r["name"] if r else None


def load_run(name: str) -> dict | None:
    """One run, ready for page.render: label, meta, Brief, posts (id → Post), threads (id → its conversation)."""
    with db() as con:
        r = con.execute("SELECT * FROM runs WHERE name = ?", (name,)).fetchone()
        if not r:
            return None
        rows = con.execute("SELECT p.id, p.doc FROM run_posts rp JOIN posts p ON p.id = rp.post_id "
                           "WHERE rp.run_id = ? ORDER BY p.created_ms DESC", (r["id"],)).fetchall()
    posts = {row["id"]: Post.from_dict(json.loads(row["doc"])) for row in rows}
    doc = json.loads(r["brief"])
    b = Brief(topics=[Topic(**t) for t in doc.get("topics") or []], other=doc.get("other") or [],
              writer_error=doc.get("writer_error"))
    thr: dict[str, list[Post]] = {}
    for ids in json.loads(r["threads"]):
        conv = [posts[i] for i in ids if i in posts]
        if len(conv) >= 3:
            for p in conv:
                thr.setdefault(p.id, conv)
    return {"name": r["name"], "label": r["label"], "meta": json.loads(r["meta"]), "brief": b, "posts": posts,
            "threads": thr}


# ── search ──────────────────────────────────────────────────────────────────────────────────────────

HANDLE = re.compile(r"(?<!\w)@(\w{1,15})\b")


def parse_query(q: str) -> tuple[list[str], list[str]]:
    """`@name` words pick accounts; every other word must appear (any word that begins with it)."""
    handles = HANDLE.findall(q or "")
    words = re.findall(r"[^\s\"]+", HANDLE.sub(" ", q or ""))
    return handles, words


def _fts(words: list[str]) -> str:
    return " ".join('"' + w.replace('"', '""') + '"*' for w in words)


def day_ms(day: str, end: bool = False) -> int | None:
    """A local date (YYYY-MM-DD) as epoch ms: its first millisecond, or with `end` its last."""
    try:
        d = dt.datetime.strptime(day, "%Y-%m-%d")
    except (TypeError, ValueError):
        return None
    if end:
        d += dt.timedelta(days=1)
    return int(d.timestamp() * 1000) - (1 if end else 0)


def search(q: str, since: str = "", until: str = "", limit: int = 300) -> tuple[list[tuple[Post, str]], bool]:
    """Posts that match, newest first, each with the first brief that had it; and whether the list was cut at
    `limit`. Nothing to look for returns nothing."""
    handles, words = parse_query(q)
    lo, hi = day_ms(since), day_ms(until, end=True)
    if not (handles or words or lo or hi):
        return [], False
    where, args = [], []
    if words:
        where.append("p.id IN (SELECT post_id FROM posts_fts WHERE posts_fts MATCH ?)")
        args.append(_fts(words))
    if handles:
        # the account that posted, or the account a repost is of
        marks = ",".join("?" * len(handles))
        where.append(f"(p.handle COLLATE NOCASE IN ({marks}) OR "
                     f"json_extract(p.doc, '$.retweet_of.handle') COLLATE NOCASE IN ({marks}))")
        args += handles + handles
    if lo:
        where.append("p.created_ms >= ?")
        args.append(lo)
    if hi:
        where.append("p.created_ms <= ?")
        args.append(hi)
    sql = (f"SELECT p.doc, (SELECT r.name FROM run_posts rp JOIN runs r ON r.id = rp.run_id WHERE rp.post_id = p.id "
           f"ORDER BY r.started_ms LIMIT 1) AS run FROM posts p WHERE {' AND '.join(where)} "
           f"ORDER BY p.created_ms DESC LIMIT ?")
    with db() as con:
        rows = con.execute(sql, args + [limit + 1]).fetchall()
    out = [(Post.from_dict(json.loads(r["doc"])), r["run"]) for r in rows[:limit]]
    return out, len(rows) > limit


def counts() -> dict:
    with db() as con:
        r = con.execute("SELECT (SELECT count(*) FROM runs) AS runs, (SELECT count(*) FROM posts) AS posts, "
                        "(SELECT min(created_ms) FROM posts) AS first_ms").fetchone()
    return dict(r)


# ── settings and the schedule's memory ──────────────────────────────────────────────────────────────


def settings() -> dict:
    with db() as con:
        rows = con.execute("SELECT key, value FROM settings").fetchall()
    out = json.loads(json.dumps(DEFAULTS))
    out.update({r["key"]: json.loads(r["value"]) for r in rows})
    return out


def save_settings(new: dict) -> None:
    with db() as con:
        for k, v in new.items():
            con.execute("INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                        (k, json.dumps(v)))


def slots(day: str) -> dict[str, dict]:
    with db() as con:
        rows = con.execute("SELECT label, fire_ms, fired_ms FROM schedule WHERE day = ?", (day,)).fetchall()
    return {r["label"]: dict(r) for r in rows}


def put_slot(day: str, label: str, fire_ms: int, fired_ms: int | None = None) -> None:
    with db() as con:
        con.execute("INSERT OR IGNORE INTO schedule (day, label, fire_ms, fired_ms) VALUES (?,?,?,?)",
                    (day, label, fire_ms, fired_ms))


def mark_slot(day: str, label: str, fired_ms: int) -> None:
    with db() as con:
        con.execute("UPDATE schedule SET fired_ms = ? WHERE day = ? AND label = ?", (fired_ms, day, label))


def forget_unfired(day: str) -> None:
    with db() as con:
        con.execute("DELETE FROM schedule WHERE day = ? AND fired_ms IS NULL", (day,))
