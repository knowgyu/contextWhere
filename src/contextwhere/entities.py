from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, asdict
from pathlib import Path

from .db import connect, query_evidence_with_mode
from .schemas import utc_now

KNOWN_SYSTEMS = {"contextWhere", "MailWhere", "OfficeWhere"}
CAMEL_WHERE_RE = re.compile(r"\b[A-Za-z][A-Za-z0-9]*(?:Where|where)\b")
BACKTICK_RE = re.compile(r"`([^`]{2,80})`")


@dataclass(frozen=True)
class EntityCandidate:
    name: str
    entity_type: str
    confidence: str = "medium"

    def to_dict(self) -> dict:
        return asdict(self)


def normalize_name(name: str) -> str:
    return " ".join(name.strip().split())[:120]


def entity_id(name: str, entity_type: str) -> str:
    raw = f"{entity_type}:{normalize_name(name).lower()}"
    return f"{entity_type}:{hashlib.sha1(raw.encode('utf-8')).hexdigest()[:12]}"


def guess_type(name: str) -> str:
    if name in KNOWN_SYSTEMS or name.endswith("Where") or name.endswith("where"):
        return "system"
    if "/" in name or name.endswith(".md"):
        return "document"
    return "concept"


def candidates_from_text(text: str) -> list[EntityCandidate]:
    seen: set[tuple[str, str]] = set()
    candidates: list[EntityCandidate] = []
    for match in CAMEL_WHERE_RE.findall(text):
        name = normalize_name(match)
        typ = guess_type(name)
        key = (name.lower(), typ)
        if key not in seen:
            seen.add(key)
            candidates.append(EntityCandidate(name=name, entity_type=typ, confidence="high" if name in KNOWN_SYSTEMS else "medium"))
    for match in BACKTICK_RE.findall(text):
        name = normalize_name(match)
        if not name or len(name.split()) > 6:
            continue
        typ = guess_type(name)
        key = (name.lower(), typ)
        if key not in seen:
            seen.add(key)
            candidates.append(EntityCandidate(name=name, entity_type=typ, confidence="medium"))
    return candidates


def evidence_text(row: dict) -> str:
    return "\n".join(str(row.get(key) or "") for key in ("provider", "source_ref", "kind", "title", "snippet", "summary", "provenance"))


def upsert_entity(conn, candidate: EntityCandidate) -> str:
    eid = entity_id(candidate.name, candidate.entity_type)
    now = utc_now()
    conn.execute(
        """
        INSERT INTO entities(entity_id, name, entity_type, confidence, created_at, updated_at)
        VALUES(?,?,?,?,?,?)
        ON CONFLICT(entity_id) DO UPDATE SET
          name=excluded.name,
          entity_type=excluded.entity_type,
          confidence=excluded.confidence,
          updated_at=excluded.updated_at
        """,
        (eid, candidate.name, candidate.entity_type, candidate.confidence, now, now),
    )
    return eid


def extract_entities(db_path: Path, query: str = "", limit: int = 100) -> dict:
    rows, search_mode = query_evidence_with_mode(db_path, query, limit=limit)
    inserted_entities: set[str] = set()
    linked = 0
    relationships = 0
    with connect(db_path) as conn:
        for row in rows:
            evidence_id_value = str(row["evidence_id"])
            entity_ids: list[str] = []
            for candidate in candidates_from_text(evidence_text(row)):
                eid = upsert_entity(conn, candidate)
                inserted_entities.add(eid)
                entity_ids.append(eid)
                cursor = conn.execute(
                    """
                    INSERT OR IGNORE INTO evidence_entities(evidence_id, entity_id, relation, confidence, created_at)
                    VALUES(?,?,?,?,?)
                    """,
                    (evidence_id_value, eid, "mentions", candidate.confidence, utc_now()),
                )
                linked += cursor.rowcount
            unique_ids = sorted(set(entity_ids))
            for idx, subject in enumerate(unique_ids):
                for obj in unique_ids[idx + 1 :]:
                    cursor = conn.execute(
                        """
                        INSERT OR IGNORE INTO relationships(subject_entity_id, predicate, object_entity_id, evidence_id, confidence, created_at)
                        VALUES(?,?,?,?,?,?)
                        """,
                        (subject, "co_occurs_with", obj, evidence_id_value, "low", utc_now()),
                    )
                    relationships += cursor.rowcount
        conn.commit()
    return {
        "ok": True,
        "search_mode": search_mode,
        "evidence_scanned": len(rows),
        "entities_seen": len(inserted_entities),
        "evidence_links_attempted": linked,
        "relationships_attempted": relationships,
    }


def list_entities(db_path: Path, limit: int = 100) -> list[dict]:
    with connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT e.*, COUNT(ee.evidence_id) AS evidence_count
            FROM entities e
            LEFT JOIN evidence_entities ee ON ee.entity_id = e.entity_id
            GROUP BY e.entity_id
            ORDER BY evidence_count DESC, e.name ASC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def list_relationships(db_path: Path, limit: int = 100) -> list[dict]:
    with connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT r.*, s.name AS subject_name, o.name AS object_name
            FROM relationships r
            JOIN entities s ON s.entity_id = r.subject_entity_id
            JOIN entities o ON o.entity_id = r.object_entity_id
            ORDER BY r.id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]
