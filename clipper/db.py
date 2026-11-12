"""SQLite state: sources, clips, posts."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone

from .config import data_dir

SCHEMA = """
CREATE TABLE IF NOT EXISTS sources (
    id TEXT PRIMARY KEY,               -- 'yt:<videoId>' or 'file:<sha1>'
    niche TEXT NOT NULL,
    kind TEXT NOT NULL,                -- youtube | inbox
    url TEXT,
    title TEXT,
    channel_id TEXT,
    channel_title TEXT,
    license TEXT,                      -- creativeCommon | youtube | permission | owned
    rights_basis TEXT,                 -- why we are allowed to use it
    duration_s REAL,
    views INTEGER,
    published_at TEXT,
    local_path TEXT,
    captions_path TEXT,
    status TEXT NOT NULL DEFAULT 'discovered',  -- discovered|rejected|fetched|mined|failed
    reject_reason TEXT,
    meta TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS clips (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id TEXT NOT NULL REFERENCES sources(id),
    niche TEXT NOT NULL,
    start_s REAL NOT NULL,
    end_s REAL NOT NULL,
    score REAL,
    hook TEXT,
    title TEXT,
    description TEXT,
    reason TEXT,
    path TEXT,
    status TEXT NOT NULL DEFAULT 'planned',  -- planned|rendered|qa_failed|approved|rejected|published
    qa_report TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    clip_id INTEGER NOT NULL REFERENCES clips(id),
    platform TEXT NOT NULL,            -- youtube | instagram
    account TEXT NOT NULL,             -- niche name (one account per niche per platform)
    remote_id TEXT,
    url TEXT,
    status TEXT NOT NULL,              -- published | failed | dry_run
    error TEXT,
    posted_at TEXT NOT NULL,
    UNIQUE (clip_id, platform)         -- a clip goes to at most ONE account per platform
);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(path=None) -> sqlite3.Connection:
    path = path or data_dir() / "clipper.db"
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    return conn


def upsert_source(conn, **fields) -> bool:
    """Insert a source if new. Returns True if inserted."""
    fields.setdefault("created_at", now())
    if isinstance(fields.get("meta"), (dict, list)):
        fields["meta"] = json.dumps(fields["meta"])
    cols = ", ".join(fields)
    qs = ", ".join("?" for _ in fields)
    cur = conn.execute(f"INSERT OR IGNORE INTO sources ({cols}) VALUES ({qs})", list(fields.values()))
    conn.commit()
    return cur.rowcount == 1


def update(conn, table: str, key, **fields) -> None:
    sets = ", ".join(f"{k} = ?" for k in fields)
    conn.execute(f"UPDATE {table} SET {sets} WHERE id = ?", [*fields.values(), key])
    conn.commit()


def posts_today(conn, platform: str, account: str) -> int:
    day = datetime.now(timezone.utc).date().isoformat()
    row = conn.execute(
        "SELECT COUNT(*) FROM posts WHERE platform=? AND account=? AND status='published' AND posted_at >= ?",
        (platform, account, day),
    ).fetchone()
    return row[0]
