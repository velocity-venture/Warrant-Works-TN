"""SQLite persistence and the content-addressed file store.

Everything the program knows lives under one data directory:

    data/warrantworks.sqlite3   records, decisions, revisions, audit trail
    data/blobs/ab/abcdef...     original uploads and exports, by SHA-256

Originals are never modified.  Revisions and exports are append-only; a new
master is a new revision that points at its parent.  The audit table is a
hash chain, so any edit to a past entry is detectable (see ``verify_audit``).
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

SCHEMA = """
CREATE TABLE IF NOT EXISTS families (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    form_type TEXT NOT NULL,
    description TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    archived INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    family_id TEXT NOT NULL REFERENCES families(id),
    role TEXT NOT NULL CHECK (role IN ('version','approved_master')),
    label TEXT NOT NULL,
    filename TEXT NOT NULL,
    kind TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    size INTEGER NOT NULL,
    preview_sha256 TEXT,
    extraction TEXT NOT NULL,
    uploaded_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    removed INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS requirements (
    id TEXT PRIMARY KEY,
    family_id TEXT NOT NULL REFERENCES families(id),
    text TEXT NOT NULL,
    note TEXT DEFAULT '',
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    active INTEGER DEFAULT 1
);
CREATE TABLE IF NOT EXISTS comparisons (
    id TEXT PRIMARY KEY,
    family_id TEXT NOT NULL REFERENCES families(id),
    mode TEXT NOT NULL CHECK (mode IN ('approved_reference','consensus')),
    anchor_doc_id TEXT NOT NULL,
    base_doc_id TEXT NOT NULL,
    doc_ids TEXT NOT NULL,
    result TEXT NOT NULL,
    proposals TEXT NOT NULL,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS decisions (
    id TEXT PRIMARY KEY,
    comparison_id TEXT NOT NULL REFERENCES comparisons(id),
    item_id TEXT NOT NULL,
    choice TEXT NOT NULL,
    text TEXT NOT NULL,
    reason TEXT DEFAULT '',
    follows_proposal INTEGER NOT NULL,
    decided_by TEXT NOT NULL,
    decided_at TEXT NOT NULL,
    superseded_by TEXT
);
CREATE INDEX IF NOT EXISTS ix_decisions_cmp ON decisions(comparison_id, item_id);
CREATE TABLE IF NOT EXISTS revisions (
    id TEXT PRIMARY KEY,
    family_id TEXT NOT NULL REFERENCES families(id),
    comparison_id TEXT NOT NULL REFERENCES comparisons(id),
    number INTEGER NOT NULL,
    parent_id TEXT,
    status TEXT NOT NULL CHECK (status IN ('draft','approved','superseded')),
    mode TEXT NOT NULL,
    segments TEXT NOT NULL,
    checklist TEXT NOT NULL,
    note TEXT DEFAULT '',
    content_sha256 TEXT NOT NULL,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    approved_by TEXT,
    approved_at TEXT,
    UNIQUE (family_id, number)
);
CREATE TABLE IF NOT EXISTS exports (
    id TEXT PRIMARY KEY,
    revision_id TEXT NOT NULL REFERENCES revisions(id),
    format TEXT NOT NULL,
    filename TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    size INTEGER NOT NULL,
    verification TEXT NOT NULL,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS audit (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    family_id TEXT,
    details TEXT NOT NULL,
    prev_hash TEXT NOT NULL,
    hash TEXT NOT NULL
);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class Store:
    def __init__(self, data_dir: str | Path):
        self.root = Path(data_dir)
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "blobs").mkdir(exist_ok=True)
        self.db_path = self.root / "warrantworks.sqlite3"
        self._lock = threading.RLock()
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False, isolation_level=None)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.execute("PRAGMA synchronous=FULL")
        self.conn.executescript(SCHEMA)

    # ------------------------------------------------------------ blobs
    def put_blob(self, data: bytes) -> str:
        h = sha256(data)
        p = self.root / "blobs" / h[:2] / h
        if not p.exists():
            p.parent.mkdir(exist_ok=True)
            tmp = p.with_suffix(".tmp")
            tmp.write_bytes(data)
            tmp.replace(p)
        return h

    def get_blob(self, h: str) -> bytes:
        data = (self.root / "blobs" / h[:2] / h).read_bytes()
        if sha256(data) != h:
            raise IOError(f"Stored file {h} failed its integrity check")
        return data

    # ------------------------------------------------------------- rows
    def execute(self, sql: str, params: Iterable[Any] = ()) -> sqlite3.Cursor:
        with self._lock:
            return self.conn.execute(sql, tuple(params))

    def one(self, sql: str, params: Iterable[Any] = ()) -> dict | None:
        r = self.execute(sql, params).fetchone()
        return dict(r) if r else None

    def all(self, sql: str, params: Iterable[Any] = ()) -> list[dict]:
        return [dict(r) for r in self.execute(sql, params).fetchall()]

    def insert(self, table: str, row: dict) -> None:
        cols = ",".join(row)
        qs = ",".join("?" for _ in row)
        vals = [json.dumps(v) if isinstance(v, (dict, list)) else v for v in row.values()]
        self.execute(f"INSERT INTO {table} ({cols}) VALUES ({qs})", vals)

    def transaction(self):
        return _Tx(self)

    # ------------------------------------------------------------ audit
    def audit(self, actor: str, action: str, family_id: str | None, details: dict) -> dict:
        with self._lock:
            last = self.one("SELECT hash FROM audit ORDER BY seq DESC LIMIT 1")
            prev = last["hash"] if last else "0" * 64
            ts = now()
            body = json.dumps({"ts": ts, "actor": actor, "action": action, "family_id": family_id,
                               "details": details, "prev": prev}, sort_keys=True)
            h = sha256(body.encode())
            self.execute("INSERT INTO audit (ts, actor, action, family_id, details, prev_hash, hash) "
                         "VALUES (?,?,?,?,?,?,?)", (ts, actor, action, family_id, json.dumps(details, sort_keys=True), prev, h))
            return {"ts": ts, "hash": h}

    def verify_audit(self) -> dict:
        prev = "0" * 64
        n = 0
        for r in self.all("SELECT * FROM audit ORDER BY seq"):
            body = json.dumps({"ts": r["ts"], "actor": r["actor"], "action": r["action"],
                               "family_id": r["family_id"], "details": json.loads(r["details"]),
                               "prev": prev}, sort_keys=True)
            if r["prev_hash"] != prev or sha256(body.encode()) != r["hash"]:
                return {"ok": False, "entries": n, "broken_at": r["seq"]}
            prev = r["hash"]
            n += 1
        return {"ok": True, "entries": n, "head": prev}


class _Tx:
    def __init__(self, store: Store):
        self.store = store

    def __enter__(self):
        self.store._lock.acquire()
        self.store.conn.execute("BEGIN IMMEDIATE")
        return self.store

    def __exit__(self, exc_type, exc, tb):
        try:
            self.store.conn.execute("ROLLBACK" if exc_type else "COMMIT")
        finally:
            self.store._lock.release()
        return False


def loads(v: str | None, default: Any = None) -> Any:
    if v is None:
        return default
    return json.loads(v)
