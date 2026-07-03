from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .db import connect, query_evidence_with_mode
from .schemas import utc_now

MAX_RECALL_LIMIT = 100


def normalize_limit(limit: int) -> int:
    if limit < 1 or limit > MAX_RECALL_LIMIT:
        raise ValueError(f"limit must be between 1 and {MAX_RECALL_LIMIT}")
    return limit


def bundle_id(name: str, query: str) -> str:
    raw = f"{name.strip().lower()}:{query.strip().lower()}:{utc_now()}"
    return f"recall:{hashlib.sha1(raw.encode('utf-8')).hexdigest()[:12]}"


def create_bundle(db_path: Path, name: str, query: str, limit: int = 20) -> dict:
    name = " ".join(name.strip().split())
    query = query.strip()
    if not name:
        raise ValueError("name is required")
    if not query:
        raise ValueError("query is required")
    limit = normalize_limit(limit)
    rows, mode = query_evidence_with_mode(db_path, query, limit=limit)
    evidence_ids = [row["evidence_id"] for row in rows]
    bid = bundle_id(name, query)
    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO recall_bundles(bundle_id, name, query, search_mode, limit_value, evidence_ids, created_at)
            VALUES(?,?,?,?,?,?,?)
            """,
            (bid, name, query, mode, limit, json.dumps(evidence_ids), utc_now()),
        )
        conn.commit()
    return {"ok": True, "bundle_id": bid, "name": name, "query": query, "search_mode": mode, "evidence_ids": evidence_ids, "items": rows}


def list_bundles(db_path: Path, limit: int = 50) -> list[dict]:
    limit = normalize_limit(limit)
    with connect(db_path) as conn:
        rows = conn.execute("SELECT * FROM recall_bundles ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        item["evidence_ids"] = json.loads(item.get("evidence_ids") or "[]")
        result.append(item)
    return result


def show_bundle(db_path: Path, bundle_id_value: str) -> dict:
    with connect(db_path) as conn:
        row = conn.execute("SELECT * FROM recall_bundles WHERE bundle_id = ?", (bundle_id_value,)).fetchone()
        if row is None:
            return {"ok": False, "error": "bundle not found", "bundle_id": bundle_id_value}
        bundle = dict(row)
        evidence_ids = json.loads(bundle.get("evidence_ids") or "[]")
        if evidence_ids:
            placeholders = ",".join("?" for _ in evidence_ids)
            rows = conn.execute(f"SELECT * FROM evidence WHERE evidence_id IN ({placeholders})", evidence_ids).fetchall()
            by_id = {r["evidence_id"]: dict(r) for r in rows}
            items = [by_id[eid] for eid in evidence_ids if eid in by_id]
        else:
            items = []
    bundle["evidence_ids"] = evidence_ids
    return {"ok": True, "bundle": bundle, "items": items}
