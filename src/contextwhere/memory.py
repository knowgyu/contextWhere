from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from .schemas import safety_messages
from .db import init_db
from .schemas import normalize_sensitivity, utc_now

VERSION = "v1"
VERSION_ALIASES = {"v1", "context-card-v1"}
CARD_TYPES = {"constraint/preference", "procedure/runbook", "decision/ADR", "incident lesson", "machine", "constraint", "preference", "procedure", "runbook", "decision", "adr", "incident_lesson"}
ACTIVE_PREFLIGHT_TYPES = {"constraint/preference", "procedure/runbook"}
TYPE_ALIASES = {"constraint": "constraint/preference", "preference": "constraint/preference", "procedure": "procedure/runbook", "runbook": "procedure/runbook", "decision": "decision/ADR", "adr": "decision/ADR", "incident_lesson": "incident lesson"}
STATUSES = {"observed", "candidate", "needs_review", "active", "stale", "superseded", "rejected"}
LEGAL_TRANSITIONS = {
    "observed": {"candidate", "rejected"},
    "candidate": {"needs_review", "active", "rejected"},
    "needs_review": {"active", "rejected"},
    "active": {"stale", "superseded", "rejected"},
    "stale": {"superseded", "rejected"},
    "superseded": set(),
    "rejected": set(),
}
TEXT_FIELDS = ("rule", "rationale", "decision", "failure_fingerprint", "lesson", "resolution")
LIST_FIELDS = ("evidence_ids", "source_locators", "steps", "preconditions", "success_checks", "drivers", "alternatives", "supersedes")
JSON_FIELDS = ("verification", "freshness")
UNSAFE_WORKAROUND_TERMS = ("bypass auth", "ignore failing security", "disable security", "skip verification")


def _connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _loads(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


def _issue(code: str, field: str, message: str) -> dict[str, str]:
    return {"code": code, "field": field, "message": message}


def _scope_string(scope: Any) -> str:
    if isinstance(scope, dict):
        scope_type = str(scope.get("type") or "").strip()
        scope_key = str(scope.get("key") or "").strip()
        return scope_type if scope_type == "global" and not scope_key else f"{scope_type}:{scope_key}"
    return str(scope or "").strip()


def _scope_dict(scope: Any) -> dict[str, str]:
    if isinstance(scope, dict):
        return {"type": str(scope.get("type") or "").strip(), "key": str(scope.get("key") or "").strip()}
    scope_str = _scope_string(scope)
    if ":" in scope_str:
        scope_type, scope_key = scope_str.split(":", 1)
        return {"type": scope_type, "key": scope_key}
    return {"type": scope_str, "key": "default" if scope_str == "global" else ""}


def _scope_type(scope: Any) -> str:
    return _scope_dict(scope)["type"]


def is_legal_transition(from_status: str, to_status: str) -> bool:
    return from_status == to_status or to_status in LEGAL_TRANSITIONS.get(from_status, set())


def lint_card(payload: dict[str, Any]) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    for message in safety_messages(payload):
        issues.append(_issue("unsafe_content", "card", message))
    if payload.get("version") not in VERSION_ALIASES:
        issues.append(_issue("invalid_version", "version", f"version must be {VERSION}"))
    card_type = payload.get("type") or payload.get("card_type")
    if card_type not in CARD_TYPES:
        issues.append(_issue("invalid_card_type", "type", "unsupported type"))

    summary = payload.get("summary")
    if not summary:
        issues.append(_issue("missing_summary", "summary", "summary is required"))
    elif len(str(summary)) > 280:
        issues.append(_issue("summary_too_long", "summary", "summary must be <= 280 characters"))

    scope = payload.get("scope")
    if not scope:
        issues.append(_issue("missing_scope", "scope", "scope is required"))
    else:
        scope_dict = _scope_dict(scope)
        if scope_dict["type"] not in {"global", "workspace", "repository", "machine"}:
            issues.append(_issue("invalid_scope", "scope.type", "scope.type must be global, workspace, repository, or machine"))
        if not scope_dict["key"]:
            issues.append(_issue("missing_scope_key", "scope.key", "scope.key is required"))

    status = payload.get("status")
    if not status:
        issues.append(_issue("missing_status", "status", "status is required"))
    elif status not in STATUSES:
        issues.append(_issue("invalid_status", "status", "unsupported status"))

    evidence = payload.get("evidence") if "evidence" in payload else payload.get("evidence_ids")
    if not evidence:
        issues.append(_issue("missing_evidence", "evidence", "at least one evidence id is required"))
    elif not isinstance(evidence, list):
        issues.append(_issue("invalid_evidence", "evidence", "evidence must be a list"))
    else:
        for index, item in enumerate(evidence):
            if not str(item):
                issues.append(_issue("invalid_evidence", f"evidence[{index}]", f"evidence[{index}] is required"))
        if len(evidence) > 20:
            issues.append(_issue("envelope_too_large", "evidence", "evidence must contain <= 20 ids"))

    freshness = payload.get("freshness")
    if freshness is None:
        issues.append(_issue("missing_freshness", "freshness", "freshness is required"))
    elif not isinstance(freshness, dict):
        issues.append(_issue("invalid_freshness", "freshness", "freshness must be an object"))
    elif len(str(freshness)) > 400:
        issues.append(_issue("freshness_too_long", "freshness", "freshness must be <= 400 characters"))

    if len(str(payload.get("rule", ""))) > 1200:
        issues.append(_issue("rule_too_long", "rule", "rule must be <= 1200 characters"))
    if len(str(payload.get("notes", ""))) > 2000:
        issues.append(_issue("notes_too_long", "notes", "notes must be <= 2000 characters"))
    if len(payload.get("source_locators") or []) > 32:
        issues.append(_issue("envelope_too_large", "source_locators", "source_locators must contain <= 32 entries"))

    verification = payload.get("verification") or {}
    if card_type in {"procedure", "runbook", "procedure/runbook"}:
        if not verification.get("verified_at"):
            issues.append(_issue("missing_verification_timestamp", "verification.verified_at", "verification.verified_at is required"))
        if verification.get("ok") is not True:
            issues.append(_issue("verification_not_successful", "verification.ok", "verification.ok must be true"))
        if not payload.get("success_checks"):
            issues.append(_issue("missing_success_checks", "success_checks", "success_checks are required"))

    if (card_type == "machine" or _scope_type(payload.get("scope")) == "machine") and not (isinstance(freshness, dict) and freshness.get("observed_at")):
        issues.append(_issue("missing_freshness_observed_at", "freshness.observed_at", "freshness.observed_at is required"))

    haystack = " ".join(str(item).lower() for item in payload.get("steps") or []) + " " + str(payload.get("notes") or "").lower()
    if any(term in haystack for term in UNSAFE_WORKAROUND_TERMS):
        issues.append(_issue("unsafe_workaround", "notes", "unsafe workaround is not allowed"))
    return issues

def _require_valid(payload: dict[str, Any]) -> None:
    issues = lint_card(payload)
    if issues:
        raise ValueError("; ".join(issue["code"] for issue in issues))


def init_memory_db(db_path: Path) -> None:
    init_db(db_path)
    with _connect(db_path) as conn:
        existing = {row["name"] for row in conn.execute("PRAGMA table_info(context_cards)")}
        columns = {
            "version": "TEXT NOT NULL DEFAULT 'context-card-v1'",
            "card_type": "TEXT NOT NULL DEFAULT ''",
            "summary": "TEXT NOT NULL DEFAULT ''",
            "scope": "TEXT NOT NULL DEFAULT ''",
            "status": "TEXT NOT NULL DEFAULT 'observed'",
            "sensitivity": "TEXT NOT NULL DEFAULT 'internal'",
            "confidence": "TEXT NOT NULL DEFAULT 'medium'",
            "evidence_ids": "TEXT NOT NULL DEFAULT '[]'",
            "source_locators": "TEXT NOT NULL DEFAULT '[]'",
            "verification": "TEXT NOT NULL DEFAULT '{}'",
            "freshness": "TEXT NOT NULL DEFAULT '{}'",
            "rule": "TEXT NOT NULL DEFAULT ''",
            "rationale": "TEXT NOT NULL DEFAULT ''",
            "steps": "TEXT NOT NULL DEFAULT '[]'",
            "preconditions": "TEXT NOT NULL DEFAULT '[]'",
            "success_checks": "TEXT NOT NULL DEFAULT '[]'",
            "decision": "TEXT NOT NULL DEFAULT ''",
            "drivers": "TEXT NOT NULL DEFAULT '[]'",
            "alternatives": "TEXT NOT NULL DEFAULT '[]'",
            "failure_fingerprint": "TEXT NOT NULL DEFAULT ''",
            "lesson": "TEXT NOT NULL DEFAULT ''",
            "resolution": "TEXT NOT NULL DEFAULT ''",
            "supersedes": "TEXT NOT NULL DEFAULT '[]'",
            "superseded_by": "TEXT",
            "created_at": "TEXT NOT NULL DEFAULT ''",
            "updated_at": "TEXT NOT NULL DEFAULT ''",
        }
        for name, ddl in columns.items():
            if name not in existing:
                conn.execute(f"ALTER TABLE context_cards ADD COLUMN {name} {ddl}")
        conn.execute(
            """
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
            )
            """
        )
        conn.commit()


def _normalize(payload: dict[str, Any]) -> dict[str, Any]:
    data = dict(payload)
    data["version"] = str(data.get("version") or VERSION)
    data["card_id"] = str(data.get("card_id") or "").strip()
    raw_type = str(data.get("type") or data.get("card_type") or "").strip()
    data["card_type"] = TYPE_ALIASES.get(raw_type, raw_type)
    data["type"] = data["card_type"]
    data["summary"] = str(data.get("summary") or "").strip()
    data["scope"] = _scope_string(data.get("scope"))
    data["status"] = str(data.get("status") or "observed").strip()
    data["sensitivity"] = normalize_sensitivity(data.get("sensitivity") or "internal")
    data["confidence"] = str(data.get("confidence") or "medium")
    if "evidence" in data and "evidence_ids" not in data:
        data["evidence_ids"] = data["evidence"]
    for field in LIST_FIELDS:
        value = data.get(field) or []
        data[field] = value if isinstance(value, list) else [str(value)]
    data["evidence"] = data["evidence_ids"]
    for field in JSON_FIELDS:
        value = data.get(field) or {}
        data[field] = value if isinstance(value, dict) else {}
    for field in TEXT_FIELDS:
        data[field] = str(data.get(field) or "")
    return data


def _row_to_payload(row: sqlite3.Row) -> dict[str, Any]:
    data = {"card_id": row["card_id"], "version": row["version"], "type": row["card_type"], "card_type": row["card_type"], "summary": row["summary"], "scope": _scope_dict(row["scope"]), "scope_key": row["scope"], "status": row["status"], "sensitivity": row["sensitivity"], "confidence": row["confidence"], "superseded_by": row["superseded_by"], "created_at": row["created_at"], "updated_at": row["updated_at"]}
    for field in LIST_FIELDS:
        data[field] = _loads(row[field], [])
    data["evidence"] = data["evidence_ids"]
    for field in JSON_FIELDS:
        data[field] = _loads(row[field], {})
    for field in TEXT_FIELDS:
        data[field] = row[field]
    return data


def upsert_card(db_path: Path, payload: dict[str, Any], *, actor: str = "contextwhere", reason: str = "upsert") -> str:
    init_memory_db(db_path)
    data = _normalize(payload)
    _require_valid(data)
    now = utc_now()
    with _connect(db_path) as conn:
        current = conn.execute("SELECT status FROM context_cards WHERE card_id = ?", (data["card_id"],)).fetchone()
        if current and not is_legal_transition(str(current["status"]), data["status"]):
            raise ValueError(f"illegal lifecycle transition: {current['status']} -> {data['status']}")
        params = {
            **{k: data[k] for k in ("card_id", "version", "card_type", "summary", "scope", "status", "sensitivity", "confidence")},
            **{k: _json(data[k]) for k in LIST_FIELDS + JSON_FIELDS},
            **{k: data[k] for k in TEXT_FIELDS},
            "superseded_by": data.get("superseded_by"),
            "created_at": now,
            "updated_at": now,
        }
        conn.execute(
            """
            INSERT INTO context_cards(card_id, version, card_type, summary, scope, status, sensitivity, confidence, evidence_ids, source_locators, verification, freshness, rule, rationale, steps, preconditions, success_checks, decision, drivers, alternatives, failure_fingerprint, lesson, resolution, supersedes, superseded_by, created_at, updated_at)
            VALUES(:card_id, :version, :card_type, :summary, :scope, :status, :sensitivity, :confidence, :evidence_ids, :source_locators, :verification, :freshness, :rule, :rationale, :steps, :preconditions, :success_checks, :decision, :drivers, :alternatives, :failure_fingerprint, :lesson, :resolution, :supersedes, :superseded_by, :created_at, :updated_at)
            ON CONFLICT(card_id) DO UPDATE SET
              version=excluded.version, card_type=excluded.card_type, summary=excluded.summary, scope=excluded.scope,
              status=excluded.status, sensitivity=excluded.sensitivity, confidence=excluded.confidence,
              evidence_ids=excluded.evidence_ids, source_locators=excluded.source_locators, verification=excluded.verification,
              freshness=excluded.freshness, rule=excluded.rule, rationale=excluded.rationale, steps=excluded.steps,
              preconditions=excluded.preconditions, success_checks=excluded.success_checks, decision=excluded.decision,
              drivers=excluded.drivers, alternatives=excluded.alternatives, failure_fingerprint=excluded.failure_fingerprint,
              lesson=excluded.lesson, resolution=excluded.resolution, supersedes=excluded.supersedes,
              superseded_by=excluded.superseded_by, updated_at=excluded.updated_at
            """,
            params,
        )
        if not current or str(current["status"]) != data["status"]:
            conn.execute(
                "INSERT INTO context_card_audit(card_id, event, from_status, to_status, reason, evidence_ids, actor, created_at) VALUES(?,?,?,?,?,?,?,?)",
                (data["card_id"], "status", str(current["status"]) if current else None, data["status"], reason, _json(data["evidence_ids"]), actor, now),
            )
        conn.commit()
    return data["card_id"]


def get_card(db_path: Path, card_id: str) -> dict[str, Any] | None:
    init_memory_db(db_path)
    with _connect(db_path) as conn:
        row = conn.execute("SELECT * FROM context_cards WHERE card_id = ?", (card_id,)).fetchone()
    return _row_to_payload(row) if row else None


def supersede_card(db_path: Path, old_card_id: str, new_payload: dict[str, Any], *, actor: str = "contextwhere", reason: str = "supersede") -> str:
    init_memory_db(db_path)
    new_data = _normalize(new_payload)
    new_data["status"] = "active"
    new_data["supersedes"] = sorted(set(new_data.get("supersedes", []) + [old_card_id]))
    _require_valid(new_data)
    now = utc_now()
    with _connect(db_path) as conn:
        old = conn.execute("SELECT * FROM context_cards WHERE card_id = ?", (old_card_id,)).fetchone()
        if not old:
            raise KeyError(old_card_id)
        if not is_legal_transition(str(old["status"]), "superseded"):
            raise ValueError(f"illegal lifecycle transition: {old['status']} -> superseded")
        old_evidence = _loads(old["evidence_ids"], [])
        params = {
            **{k: new_data[k] for k in ("card_id", "version", "card_type", "summary", "scope", "status", "sensitivity", "confidence")},
            **{k: _json(new_data[k]) for k in LIST_FIELDS + JSON_FIELDS},
            **{k: new_data[k] for k in TEXT_FIELDS},
            "superseded_by": new_data.get("superseded_by"),
            "created_at": now,
            "updated_at": now,
        }
        conn.execute(
            """
            INSERT INTO context_cards(card_id, version, card_type, summary, scope, status, sensitivity, confidence, evidence_ids, source_locators, verification, freshness, rule, rationale, steps, preconditions, success_checks, decision, drivers, alternatives, failure_fingerprint, lesson, resolution, supersedes, superseded_by, created_at, updated_at)
            VALUES(:card_id, :version, :card_type, :summary, :scope, :status, :sensitivity, :confidence, :evidence_ids, :source_locators, :verification, :freshness, :rule, :rationale, :steps, :preconditions, :success_checks, :decision, :drivers, :alternatives, :failure_fingerprint, :lesson, :resolution, :supersedes, :superseded_by, :created_at, :updated_at)
            """,
            params,
        )
        conn.execute("UPDATE context_cards SET status = ?, superseded_by = ?, updated_at = ? WHERE card_id = ?", ("superseded", new_data["card_id"], now, old_card_id))
        conn.execute("INSERT INTO context_card_audit(card_id, event, from_status, to_status, reason, evidence_ids, actor, created_at) VALUES(?,?,?,?,?,?,?,?)", (old_card_id, "status", old["status"], "superseded", reason, _json(old_evidence), actor, now))
        conn.execute("INSERT INTO context_card_audit(card_id, event, from_status, to_status, reason, evidence_ids, actor, created_at) VALUES(?,?,?,?,?,?,?,?)", (new_data["card_id"], "supersede", None, "active", reason, _json(new_data["evidence_ids"]), actor, now))
        conn.commit()
    return new_data["card_id"]


def audit_events(db_path: Path) -> list[dict[str, Any]]:
    init_memory_db(db_path)
    with _connect(db_path) as conn:
        rows = conn.execute("SELECT * FROM context_card_audit ORDER BY id").fetchall()
    return [dict(row) for row in rows]


def schema_signature(db_path: Path) -> list[tuple[str, str]]:
    init_memory_db(db_path)
    with _connect(db_path) as conn:
        rows = conn.execute("SELECT type, name, sql FROM sqlite_master WHERE type IN ('table','index','view','trigger') ORDER BY type, name").fetchall()
    return [(row["type"], row["name"] + ":" + (row["sql"] or "")) for row in rows]


def _active_rows(db_path: Path, scopes: list[str], now: str | None = None) -> list[dict[str, Any]]:
    placeholders = ",".join("?" for _ in scopes)
    with _connect(db_path) as conn:
        rows = conn.execute(
            f"SELECT * FROM context_cards WHERE status = 'active' AND scope IN ({placeholders}) ORDER BY CASE scope WHEN 'global:default' THEN 0 ELSE 1 END, id",
            scopes,
        ).fetchall()
    result = []
    for row in rows:
        item = _row_to_payload(row)
        stale_after = item.get("freshness", {}).get("stale_after")
        if now and stale_after and stale_after < now:
            continue
        result.append(item)
    return result


def active_lookup(db_path: Path, *, workspace_scope: str | None = None, repository_scope: str | None = None, machine_scope: str | None = None, workspace_key: str | None = None, repository_key: str | None = None, machine_key: str | None = None, now: str | None = None) -> list[dict[str, Any]]:
    init_memory_db(db_path)
    workspace_scope = workspace_scope or (f"workspace:{workspace_key}" if workspace_key else None)
    repository_scope = repository_scope or (f"repository:{repository_key}" if repository_key else None)
    machine_scope = machine_scope or (f"machine:{machine_key}" if machine_key else None)
    scopes = ["global:default"] + [_scope_string(s) for s in (workspace_scope, repository_scope, machine_scope) if s]
    return _active_rows(db_path, scopes, now=now)


def _compact_preflight_card(card: dict[str, Any]) -> dict[str, Any]:
    return {
        key: card[key]
        for key in ("card_id", "type", "summary", "scope", "status", "sensitivity", "confidence", "evidence_ids", "source_locators", "verification", "freshness")
        if key in card
    }


def preflight_lookup(db_path: Path, *, repository_key: str | None = None, machine_key: str | None = None, limit: int = 8, now: str | None = None) -> list[dict[str, Any]]:
    init_memory_db(db_path)
    scopes = [_scope_string(s) for s in (f"repository:{repository_key}" if repository_key else None, f"machine:{machine_key}" if machine_key else None) if s]
    if not scopes:
        return []
    cards = [card for card in _active_rows(db_path, scopes, now=now) if card.get("type") in ACTIVE_PREFLIGHT_TYPES]
    return [_compact_preflight_card(card) for card in cards[:limit]]


# Compatibility names for the first local smoke written before tests landed.
def transition_card(db_path: Path, card_id: str, status: str, *, reason: str = "", evidence: list[str] | None = None, actor: str = "contextwhere") -> None:
    current = get_card(db_path, card_id)
    if not current:
        raise KeyError(card_id)
    if not is_legal_transition(current["status"], status):
        raise ValueError(f"illegal lifecycle transition: {current['status']} -> {status}")
    if current["status"] == status:
        return
    now = utc_now()
    with _connect(db_path) as conn:
        conn.execute("UPDATE context_cards SET status = ?, updated_at = ? WHERE card_id = ?", (status, now, card_id))
        conn.execute("INSERT INTO context_card_audit(card_id, event, from_status, to_status, reason, evidence_ids, actor, created_at) VALUES(?,?,?,?,?,?,?,?)", (card_id, "status", current["status"], status, reason, _json(evidence or []), actor, now))
        conn.commit()


def list_cards(db_path: Path, *, scope_type: str, scope_key: str, status: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    scope = f"{scope_type}:{scope_key}"
    init_memory_db(db_path)
    sql = "SELECT * FROM context_cards WHERE scope = ?"
    params: list[Any] = [scope]
    if status:
        sql += " AND status = ?"
        params.append(status)
    sql += " ORDER BY updated_at DESC, id DESC LIMIT ?"
    params.append(limit)
    with _connect(db_path) as conn:
        rows = conn.execute(sql, params).fetchall()
    return [_row_to_payload(row) for row in rows]


def audit_rows(db_path: Path, card_id: str) -> list[dict[str, Any]]:
    return [row for row in audit_events(db_path) if row["card_id"] == card_id]
