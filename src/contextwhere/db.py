from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Iterable

from .schemas import EvidenceRecord, utc_now

SCHEMA = """
CREATE TABLE IF NOT EXISTS evidence (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  evidence_id TEXT NOT NULL UNIQUE,
  provider TEXT NOT NULL,
  source_ref TEXT NOT NULL,
  kind TEXT NOT NULL,
  title TEXT NOT NULL DEFAULT '',
  snippet TEXT NOT NULL DEFAULT '',
  summary TEXT NOT NULL DEFAULT '',
  occurred_at TEXT,
  ingested_at TEXT NOT NULL,
  sensitivity TEXT NOT NULL DEFAULT 'internal',
  provenance TEXT NOT NULL DEFAULT '',
  confidence TEXT NOT NULL DEFAULT 'medium',
  content_hash TEXT NOT NULL,
  omitted_fields TEXT NOT NULL DEFAULT '[]',
  metadata TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS action_requests (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  action_type TEXT NOT NULL,
  target_ref TEXT NOT NULL,
  reason TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS ingest_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  provider TEXT NOT NULL,
  command TEXT NOT NULL,
  status TEXT NOT NULL,
  created_at TEXT NOT NULL,
  details TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS entities (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  entity_id TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  entity_type TEXT NOT NULL,
  confidence TEXT NOT NULL DEFAULT 'low',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS evidence_entities (
  evidence_id TEXT NOT NULL,
  entity_id TEXT NOT NULL,
  relation TEXT NOT NULL DEFAULT 'mentions',
  confidence TEXT NOT NULL DEFAULT 'low',
  created_at TEXT NOT NULL,
  PRIMARY KEY(evidence_id, entity_id, relation)
);
CREATE TABLE IF NOT EXISTS relationships (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  subject_entity_id TEXT NOT NULL,
  predicate TEXT NOT NULL,
  object_entity_id TEXT NOT NULL,
  evidence_id TEXT NOT NULL,
  confidence TEXT NOT NULL DEFAULT 'low',
  created_at TEXT NOT NULL,
  UNIQUE(subject_entity_id, predicate, object_entity_id, evidence_id)
);

CREATE TABLE IF NOT EXISTS context_cards (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  card_id TEXT NOT NULL UNIQUE,
  version TEXT NOT NULL DEFAULT 'context-card-v1',
  card_type TEXT NOT NULL,
  summary TEXT NOT NULL,
  scope TEXT NOT NULL,
  status TEXT NOT NULL,
  sensitivity TEXT NOT NULL DEFAULT 'internal',
  confidence TEXT NOT NULL DEFAULT 'medium',
  evidence_ids TEXT NOT NULL DEFAULT '[]',
  source_locators TEXT NOT NULL DEFAULT '[]',
  verification TEXT NOT NULL DEFAULT '{}',
  freshness TEXT NOT NULL DEFAULT '{}',
  rule TEXT NOT NULL DEFAULT '',
  rationale TEXT NOT NULL DEFAULT '',
  steps TEXT NOT NULL DEFAULT '[]',
  preconditions TEXT NOT NULL DEFAULT '[]',
  success_checks TEXT NOT NULL DEFAULT '[]',
  decision TEXT NOT NULL DEFAULT '',
  drivers TEXT NOT NULL DEFAULT '[]',
  alternatives TEXT NOT NULL DEFAULT '[]',
  failure_fingerprint TEXT NOT NULL DEFAULT '',
  lesson TEXT NOT NULL DEFAULT '',
  resolution TEXT NOT NULL DEFAULT '',
  supersedes TEXT NOT NULL DEFAULT '[]',
  superseded_by TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS context_card_audit (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  card_id TEXT NOT NULL,
  event TEXT NOT NULL,
  from_status TEXT,
  to_status TEXT,
  reason TEXT NOT NULL DEFAULT '',
  evidence_ids TEXT NOT NULL DEFAULT '[]',
  actor TEXT NOT NULL DEFAULT 'contextwhere',
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS recall_bundles (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  bundle_id TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  query TEXT NOT NULL,
  search_mode TEXT NOT NULL,
  limit_value INTEGER NOT NULL,
  evidence_ids TEXT NOT NULL DEFAULT '[]',
  created_at TEXT NOT NULL
);
"""

FTS_SCHEMA = """
CREATE VIRTUAL TABLE IF NOT EXISTS evidence_fts USING fts5(evidence_id UNINDEXED, title, snippet, summary);
"""


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: Path) -> None:
    with connect(db_path) as conn:
        conn.executescript(SCHEMA)
        try:
            conn.executescript(FTS_SCHEMA)
        except sqlite3.OperationalError:
            pass


def content_hash(record: EvidenceRecord) -> str:
    payload = json.dumps({
        "provider": record.provider,
        "source_ref": record.source_ref,
        "kind": record.kind,
        "title": record.title,
        "snippet": record.snippet,
        "summary": record.summary,
        "metadata": record.metadata,
    }, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def evidence_id(record: EvidenceRecord) -> str:
    raw = f"{record.provider}:{record.kind}:{record.source_ref}"
    suffix = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]
    return f"{record.provider}:{record.kind}:{suffix}"


def log_ingest(db_path: Path, provider: str, command: str, status: str, details: dict | None = None) -> None:
    with connect(db_path) as conn:
        conn.execute(
            "INSERT INTO ingest_log(provider, command, status, created_at, details) VALUES(?,?,?,?,?)",
            (provider, command, status, utc_now(), json.dumps(details or {}, ensure_ascii=False, sort_keys=True)),
        )
        conn.commit()


def insert_evidence(db_path: Path, records: Iterable[EvidenceRecord]) -> list[str]:
    ids: list[str] = []
    with connect(db_path) as conn:
        for record in records:
            eid = evidence_id(record)
            ids.append(eid)
            ch = content_hash(record)
            conn.execute(
                """
                INSERT INTO evidence(evidence_id, provider, source_ref, kind, title, snippet, summary, occurred_at, ingested_at, sensitivity, provenance, confidence, content_hash, omitted_fields, metadata)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(evidence_id) DO UPDATE SET
                  title=excluded.title, snippet=excluded.snippet, summary=excluded.summary, occurred_at=excluded.occurred_at,
                  ingested_at=excluded.ingested_at, sensitivity=excluded.sensitivity, provenance=excluded.provenance,
                  confidence=excluded.confidence, content_hash=excluded.content_hash, omitted_fields=excluded.omitted_fields, metadata=excluded.metadata
                """,
                (eid, record.provider, record.source_ref, record.kind, record.title, record.snippet, record.summary, record.occurred_at,
                 utc_now(), record.sensitivity, record.provenance, record.confidence, ch,
                 json.dumps(record.omitted_fields), json.dumps(record.metadata, ensure_ascii=False, sort_keys=True)),
            )
            try:
                conn.execute("DELETE FROM evidence_fts WHERE evidence_id = ?", (eid,))
                conn.execute("INSERT INTO evidence_fts(evidence_id, title, snippet, summary) VALUES(?,?,?,?)", (eid, record.title, record.snippet, record.summary))
            except sqlite3.OperationalError:
                pass
        conn.commit()
    return ids


def query_evidence_with_mode(db_path: Path, query: str, limit: int = 20) -> tuple[list[dict], str]:
    with connect(db_path) as conn:
        if not query:
            rows = conn.execute("SELECT * FROM evidence ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
            return [dict(row) for row in rows], "recent"
        try:
            rows = conn.execute(
                """
                SELECT e.* FROM evidence_fts f JOIN evidence e ON e.evidence_id = f.evidence_id
                WHERE evidence_fts MATCH ? LIMIT ?
                """,
                (query, limit),
            ).fetchall()
            if rows:
                return [dict(row) for row in rows], "fts"
        except sqlite3.OperationalError:
            pass
        like = f"%{query}%"
        rows = conn.execute(
            "SELECT * FROM evidence WHERE title LIKE ? OR snippet LIKE ? OR summary LIKE ? OR source_ref LIKE ? LIMIT ?",
            (like, like, like, like, limit),
        ).fetchall()
        return [dict(row) for row in rows], "like-fallback"


def query_evidence(db_path: Path, query: str, limit: int = 20) -> list[dict]:
    rows, _mode = query_evidence_with_mode(db_path, query, limit)
    return rows


def get_evidence(db_path: Path, evidence_id: str | None = None, source_locator: str | None = None) -> dict | None:
    if not evidence_id and not source_locator:
        raise ValueError("evidence_id or source_locator required")
    with connect(db_path) as conn:
        if evidence_id:
            row = conn.execute("SELECT * FROM evidence WHERE evidence_id = ?", (evidence_id,)).fetchone()
        else:
            row = conn.execute("SELECT * FROM evidence WHERE json_extract(metadata, '$.source_locator') = ?", (source_locator,)).fetchone()
    return dict(row) if row else None
