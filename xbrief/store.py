"""Every brief and every post read, in one SQLite file (`~/Data/xbrief-data/xbrief.db`), for the page's history and
search, plus the page's settings and the schedule's memory.

A run is stored whole when its brief is written (`cli.publish`): its meta, the writer's topics, its conversations,
and each post, which is kept once however many runs saw it. Posts are kept for good: a post is a few hundred bytes of
text, and the raw pages they came from are pruned after 30 days. Runs write and the server reads, in two processes;
WAL lets them share the file.

Search is SQLite's own full-text index over each post's words (with what it reposts or quotes) and its accounts.
Its rows are keyed by the post's id itself (X's ids are numbers that fit SQLite's rowid, and stay put through a
VACUUM), so storing a post replaces its row by key. The first build kept the id in a column the index cannot look
up, so every replace scanned the whole index; `_upgrade_fts` rebuilds such an index once, from the posts.
"""

from __future__ import annotations

import contextlib
import datetime as dt
import json
import re
import sqlite3

from . import config, parse
from .brief import Brief, Thesis, Topic
from .parse import Post

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT UNIQUE NOT NULL,          -- 2026-10-12-0857-am: the run's start and label
  label TEXT NOT NULL,
  started_ms INTEGER NOT NULL,
  meta TEXT NOT NULL,                 -- collect.Result.meta()
  brief TEXT NOT NULL,                -- {theses, topics: [{title, summary, posts, key, focus}], other: [...], writer_error}
  threads TEXT NOT NULL,              -- [[post id, ...], ...]: conversations of three posts or more, in order
  n_posts INTEGER NOT NULL,
  n_topics INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS runs_started ON runs (started_ms, id);
CREATE TABLE IF NOT EXISTS posts (
  id TEXT PRIMARY KEY,
  handle TEXT NOT NULL,
  created_ms INTEGER NOT NULL,
  doc TEXT NOT NULL                   -- parse.Post.to_dict()
);
CREATE INDEX IF NOT EXISTS posts_handle ON posts (handle COLLATE NOCASE, created_ms);
CREATE INDEX IF NOT EXISTS posts_created ON posts (created_ms);
CREATE INDEX IF NOT EXISTS posts_rt_handle  -- search's "@account": the account a repost is of, written as search writes it
  ON posts (json_extract(doc, '$.retweet_of.handle') COLLATE NOCASE, created_ms);
CREATE TABLE IF NOT EXISTS run_posts (
  run_id INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
  post_id TEXT NOT NULL,
  PRIMARY KEY (run_id, post_id)
);
CREATE INDEX IF NOT EXISTS run_posts_post ON run_posts (post_id);
CREATE VIRTUAL TABLE IF NOT EXISTS posts_fts USING fts5 (  -- rowid: the post's id as a number, and no copy of the text
  body, who, content = '', contentless_delete = 1, tokenize = 'unicode61 remove_diacritics 2'
);
CREATE TABLE IF NOT EXISTS schedule (
  day TEXT NOT NULL,                  -- 2026-10-12, local
  label TEXT NOT NULL,
  fire_ms INTEGER NOT NULL,
  fired_ms INTEGER,                   -- NULL: not yet; -1: skipped
  PRIMARY KEY (day, label)
);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS site_posts (  -- the Sites tab (sites.py): every post a source has listed
  url TEXT PRIMARY KEY,
  source TEXT NOT NULL,               -- config.SITES key
  published_ms INTEGER,
  seen_ms INTEGER NOT NULL,           -- the check that found it
  baseline INTEGER NOT NULL,          -- 1: already there at the source's first check, never read
  doc TEXT NOT NULL                   -- {title, url, published_ms, chars, summary: {gist, points, calls, view}, error}
);
CREATE INDEX IF NOT EXISTS site_posts_source ON site_posts (source, baseline);
"""

DEFAULTS = {"schedule": False, "windows": {k: list(v) for k, v in config.WINDOWS.items()}, "sites_daily": True}
_ready: set[str] = set()  # the databases this process has already given the schema and looked at for the old index


@contextlib.contextmanager
def db():
    con = sqlite3.connect(config.DB, timeout=15)
    con.row_factory = sqlite3.Row
    try:
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA foreign_keys=ON")
        if str(config.DB) not in _ready:
            con.executescript(SCHEMA)
            _upgrade_fts(con)
            _ready.add(str(config.DB))
        with con:
            yield con
    finally:
        con.close()


# ── runs ────────────────────────────────────────────────────────────────────────────────────────────


def _body(p: Post) -> str:
    parts = [p.text]
    xs = parse.inner(p)
    parts += [x.text for x in xs[1:]]
    for x in xs:
        for v in x.videos:  # the whole transcript (kept in videos/ alone), so search reaches what was said
            parts += [v.get("title") or "", (v.get("summary") or {}).get("gist") or "", _transcript(v.get("key") or "")]
        if x.article:
            parts += [x.article.get("title") or "", x.article.get("text") or x.article.get("preview") or ""]
    parts += [ln.get("url") or "" for ln in p.links]
    return "\n".join(x for x in parts if x)


def _who(p: Post) -> str:
    out = [p.handle, p.name]
    for inner in (p.retweet_of, p.quote):
        if inner:
            out += [inner.handle, inner.name]
    return " ".join(x for x in out if x)


def _transcript(key: str) -> str:
    from . import videos  # videos → sites → store

    return (videos.kept(key) or {}).get("transcript") or "" if key else ""


def _old_fts(con) -> bool:
    row = con.execute("SELECT sql FROM sqlite_master WHERE name = 'posts_fts'").fetchone()
    return bool(row and "contentless_delete" not in row[0])


def _upgrade_fts(con) -> None:
    """Rebuild an older index (the first build's `post_id` column; one that kept its own copy of the text) as the
    schema's, from the posts, once, and drop the transcripts the posts once carried (videos/ keeps them). The
    server and a run may both open the file first: the second finds the work done."""
    if not _old_fts(con):
        return
    con.execute("BEGIN IMMEDIATE")
    try:
        if _old_fts(con):
            con.execute("DROP TABLE posts_fts")
            con.execute(re.search(r"CREATE VIRTUAL TABLE[^;]+\)", SCHEMA).group(0))
            for (doc,) in con.execute("SELECT doc FROM posts").fetchall():
                p = Post.from_dict(json.loads(doc))
                if _drop_transcripts(p):
                    con.execute("UPDATE posts SET doc = ? WHERE id = ?", (json.dumps(p.to_dict(), ensure_ascii=False), p.id))
                _index(con, p)
        con.execute("COMMIT")
    except BaseException:
        con.execute("ROLLBACK")
        raise


def _drop_transcripts(p: Post) -> bool:
    """Whether the post (or what it reposts or quotes) still carried a video's transcript, now taken off it."""
    found = False
    for x in parse.inner(p):
        for v in x.videos:
            found = v.pop("transcript", None) is not None or found
    return found


def _index(con, p: Post) -> None:
    """The post's row in the full-text index, replaced by key. X's post ids are numbers; one that is not (never
    seen) is left out of word search, and is still found by account and date."""
    if not p.id.isdigit():
        return
    con.execute("DELETE FROM posts_fts WHERE rowid = ?", (int(p.id),))
    con.execute("INSERT INTO posts_fts (rowid, body, who) VALUES (?,?,?)", (int(p.id), _body(p), _who(p)))


def save_run(name: str, label: str, meta: dict, b: Brief, posts: dict[str, Post], threads: list[list[str]]) -> int:
    """Store one run whole. Writing a run again (a rebrief) replaces it."""
    doc = {"theses": [t.__dict__ for t in b.theses],
           "topics": [t.__dict__ for t in b.topics], "other": b.other, "writer_error": b.writer_error}
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
            _index(con, p)
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
              writer_error=doc.get("writer_error"),
              theses=[Thesis(**t) for t in doc.get("theses") or []])  # briefs before 2026-10-14 have none
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
        where.append("p.id IN (SELECT CAST(rowid AS TEXT) FROM posts_fts WHERE posts_fts MATCH ?)")
        args.append(_fts(words))
    if handles:
        # the account that posted, or the account a repost is of
        marks = ",".join("?" * len(handles))
        # each half through its own index (an OR here walks every post)
        where.append(f"p.id IN (SELECT id FROM posts WHERE handle COLLATE NOCASE IN ({marks}) UNION "
                     f"SELECT id FROM posts WHERE json_extract(doc, '$.retweet_of.handle') COLLATE NOCASE IN ({marks}))")
        args += handles + handles
    if lo:
        where.append("p.created_ms >= ?")
        args.append(lo)
    if hi:
        where.append("p.created_ms <= ?")
        args.append(hi)
    # the matching ids are cut to `limit` first, and only those posts' records read: a record can hold a whole transcript
    sql = (f"WITH hit AS (SELECT p.id, p.created_ms FROM posts p WHERE {' AND '.join(where)} "
           f"ORDER BY p.created_ms DESC, p.id DESC LIMIT ?) "
           f"SELECT p.doc, (SELECT r.name FROM run_posts rp JOIN runs r ON r.id = rp.run_id WHERE rp.post_id = p.id "
           f"ORDER BY r.started_ms LIMIT 1) AS run FROM hit JOIN posts p ON p.id = hit.id "
           f"ORDER BY hit.created_ms DESC, hit.id DESC")
    with db() as con:
        rows = con.execute(sql, args + [limit + 1]).fetchall()
    out = [(Post.from_dict(json.loads(r["doc"])), r["run"]) for r in rows[:limit]]
    return out, len(rows) > limit


def counts() -> dict:
    with db() as con:
        r = con.execute("SELECT (SELECT count(*) FROM runs) AS runs, (SELECT count(*) FROM posts) AS posts, "
                        "(SELECT min(created_ms) FROM posts) AS first_ms").fetchone()
    return dict(r)


# ── the Sites tab ───────────────────────────────────────────────────────────────────────────────────


def site_urls(source: str) -> set[str]:
    with db() as con:
        return {r[0] for r in con.execute("SELECT url FROM site_posts WHERE source = ?", (source,))}


def save_site_post(doc: dict, seen_ms: int) -> None:
    """A post a source listed: read and summarised, or (`baseline`) only noted as already there."""
    base = bool(doc.pop("baseline", False))
    with db() as con:
        con.execute("INSERT INTO site_posts (url, source, published_ms, seen_ms, baseline, doc) VALUES (?,?,?,?,?,?) "
                    "ON CONFLICT(url) DO UPDATE SET published_ms = excluded.published_ms, baseline = excluded.baseline, "
                    "doc = excluded.doc",
                    (doc["url"], doc["source"], doc.get("published_ms"), seen_ms, int(base),
                     json.dumps(doc, ensure_ascii=False)))


def site_posts(limit: int = 200) -> list[dict]:
    """The posts that were read, newest first (by their own date, else when the check found them)."""
    with db() as con:
        rows = con.execute("SELECT doc, seen_ms FROM site_posts WHERE baseline = 0 "
                           "ORDER BY coalesce(published_ms, seen_ms) DESC LIMIT ?", (limit,)).fetchall()
    return [{**json.loads(r["doc"]), "seen_ms": r["seen_ms"]} for r in rows]


def site_counts() -> dict[str, int]:
    with db() as con:
        return {r[0]: r[1] for r in con.execute("SELECT source, count(*) FROM site_posts GROUP BY source")}


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
