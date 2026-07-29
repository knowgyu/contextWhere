from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import time
from pathlib import Path
from typing import Any

from .cards import safety_messages
from .db import insert_evidence
from .memory import active_lookup, get_card, init_memory_db, transition_card, upsert_card
from .schemas import EvidenceRecord, utc_now

DEFAULT_FALLBACK_THRESHOLD = 2
SIGNAL_TYPES = {
    "user_remember",
    "user_correction",
    "tool_failure",
    "verified_success",
    "session_summary",
    "blocker",
    "environment_fact",
}

PROMPTISH_KEYS = {"prompt", "messages", "raw_prompt", "system", "developer", "conversation"}
RAW_KEYS = {"raw", "raw_body", "body", "full_text", "provider_payload", "provider_raw", "headers", "attachments"}
UNSAFE_TEXT = re.compile(
    r"(?i)(-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----|\b(?:api[_-]?key|token|password|secret)\s*[=:]\s*\S+|\bsystem prompt\b|\bdeveloper prompt\b|ignore failing security|disable security|bypass auth|skip verification|NODE_TLS_REJECT_UNAUTHORIZED|disable scanner|ignore previous instructions)"
)

_PATH_RE = re.compile(r"(?i)(?:[a-z]:\\[^\s'\"]+|/(?:[^\s/'\"]+/){1,}[^\s'\"]+)")
_ISO_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}[tT ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?\b")
_UUID_RE = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I)
_SECRET_RE = re.compile(
    r"(?i)(-----BEGIN [A-Z ]*(?:PRIVATE KEY|CERTIFICATE)[A-Z ]*-----.*?-----END [A-Z ]*(?:PRIVATE KEY|CERTIFICATE)[A-Z ]*-----|\b(?:authorization\s*:\s*bearer|api[_-]?key|token|password|passwd|pwd|secret|cookie|database_url)\s*[=:]\s*\S+|\b(?:sk_live|ghp|xox[baprs])_[A-Za-z0-9_\-]+|postgres://\S+)"
)
_PROMPT_RE = re.compile(r"(?is)(<system>.*?</system>|\bignore previous instructions\b|\bsystem prompt\b|\bdeveloper prompt\b|\bpromote all candidates\b)")
_HEX_RE = re.compile(r"\b[0-9a-f]{12,}\b", re.I)
_RUN_ID_RE = re.compile(r"(?i)run_id=[A-Za-z0-9_-]+")
_NUMBER_RE = re.compile(r"\b\d{5,}\b")
_EMAIL_RE = re.compile(r"\b[^\s@]+@[^\s@]+\.[^\s@]+\b")
_LINE_RE = re.compile(r"(?i)\bline\s+\d+\b")
_SENTINEL_RE = re.compile(r"\b[A-Z0-9_]*SENTINEL[A-Z0-9_]*\b")


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def memory_db(home: str | None = None) -> Path:
    from .config import resolve_global_home

    return (Path(home).expanduser().resolve() if home else resolve_global_home()) / "contextwhere.sqlite3"


def _walk(value: Any, path: str = "") -> list[tuple[str, Any]]:
    if isinstance(value, dict):
        out: list[tuple[str, Any]] = []
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else str(key)
            out.extend(_walk(child, child_path))
        return out
    if isinstance(value, list):
        out = []
        for i, child in enumerate(value):
            out.extend(_walk(child, f"{path}[{i}]"))
        return out
    return [(path, value)]


def assert_no_unsafe_signal_fields(payload: dict[str, Any]) -> None:
    for path, _value in _walk(payload):
        key = path.rsplit(".", 1)[-1].split("[", 1)[0].lower()
        if key in PROMPTISH_KEYS or key in RAW_KEYS:
            raise ValueError(f"unsafe signal field: {path}")


def assert_safe_signal(payload: dict[str, Any]) -> None:
    for message in safety_messages(payload):
        raise ValueError(f"unsafe signal content: {message}")
    for path, value in _walk(payload):
        key = path.rsplit(".", 1)[-1].split("[", 1)[0].lower()
        if key in PROMPTISH_KEYS or key in RAW_KEYS:
            raise ValueError(f"unsafe signal field: {path}")
        if isinstance(value, str) and UNSAFE_TEXT.search(value):
            raise ValueError(f"unsafe signal content: {path}")


def sanitize_text(value: str) -> str:
    text = _SECRET_RE.sub("<secret>", str(value))
    text = _PROMPT_RE.sub("<prompt>", text)
    text = _SENTINEL_RE.sub("<redacted>", text)
    text = _PATH_RE.sub("<path>", text)
    text = _ISO_RE.sub("<time>", text)
    text = _UUID_RE.sub("<id>", text)
    text = _RUN_ID_RE.sub("run_id=<id>", text)
    text = _LINE_RE.sub("line <num>", text)
    text = _HEX_RE.sub("<id>", text)
    text = _NUMBER_RE.sub("<num>", text)
    text = _EMAIL_RE.sub("<email>", text)
    return re.sub(r"\s+", " ", text).strip().lower()


def normalized_text(payload: dict[str, Any], keys: tuple[str, ...]) -> str:
    parts = []
    for key in keys:
        value = payload.get(key)
        if isinstance(value, (dict, list)):
            parts.append(_json(value))
        elif value not in (None, ""):
            parts.append(str(value))
    return sanitize_text(" | ".join(parts))


def sanitize_failure_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "tool_failure",
        "tool": sanitize_text(str(payload.get("tool") or "tool"))[:80],
        "command": sanitize_text(str(payload.get("command") or ""))[:240],
        "error": normalized_text(payload, ("error", "output"))[:1200],
        "exit_code": str(payload.get("exit_code") or ""),
    }


def failure_summary(payload: dict[str, Any]) -> str:
    clean = sanitize_failure_payload(payload)
    return normalized_text(clean, ("tool", "command", "error", "exit_code"))[:1200]


def stable_fingerprint(payload: dict[str, Any]) -> str:
    signal_type = str(payload.get("type") or "").strip()
    if signal_type == "tool_failure":
        assert_no_unsafe_signal_fields(payload)
        material = failure_summary(payload)
    else:
        assert_safe_signal(payload)
        if signal_type == "verified_success":
            material = normalized_text(payload, ("tool", "command", "failure", "resolution", "success_evidence"))
        elif signal_type == "environment_fact":
            material = normalized_text(payload, ("name", "value", "method"))
        else:
            material = normalized_text(payload, ("text", "summary", "reason", "resolution"))
    return hashlib.sha256(f"{signal_type}:{material}".encode("utf-8")).hexdigest()


def _scope(repository: str | None, machine: str | None = None) -> dict[str, str]:
    return {"type": "machine", "key": machine} if machine else {"type": "repository", "key": repository or "default"}


def _count_failures(db_path: Path, fingerprint: str) -> int:
    init_memory_db(db_path)
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM evidence WHERE provider = ? AND kind = ? AND json_extract(metadata, '$.fingerprint') = ?",
            ("contextwhere", "signal/tool_failure", fingerprint),
        ).fetchone()
    return int(row[0]) if row else 0


def _sanitize_for_output(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _sanitize_for_output(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_sanitize_for_output(v) for v in value]
    if isinstance(value, str):
        return sanitize_text(value)
    return value


def active_verified_procedures(db_path: Path, *, fingerprint: str, repository: str | None = None, machine: str | None = None) -> list[dict[str, Any]]:
    cards = active_lookup(db_path, repository_key=repository, machine_key=machine)
    return [
        _sanitize_for_output(card)
        for card in cards
        if card.get("type") in {"procedure", "runbook", "procedure/runbook"}
        and card.get("failure_fingerprint") == fingerprint
        and (card.get("verification") or {}).get("ok") is True
    ]


def _short(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def _signal_text(payload: dict[str, Any], signal_type: str) -> tuple[str, str, str]:
    if signal_type == "tool_failure":
        text = failure_summary(payload)
        return f"repeated tool failure: {text[:180]}", text[:500], text[:500]
    title = sanitize_text(str(payload.get("title") or payload.get("summary") or signal_type))[:180]
    snippet = normalized_text(payload, ("text", "summary", "error", "resolution", "name", "value"))[:500]
    summary = sanitize_text(str(payload.get("summary") or payload.get("text") or signal_type))[:500]
    return title, snippet, summary


def _evidence(db_path: Path, signal_type: str, fingerprint: str, payload: dict[str, Any]) -> str:
    init_memory_db(db_path)
    now = utc_now()
    title, snippet, summary = _signal_text(payload, signal_type)
    record = EvidenceRecord(
        provider="contextwhere",
        source_ref=f"signal:{signal_type}:{_short(fingerprint)}:{time.time_ns()}",
        kind=f"signal/{signal_type}",
        title=title,
        snippet=snippet,
        summary=summary,
        occurred_at=str(payload.get("occurred_at") or now),
        sensitivity="internal",
        provenance="signal-capture",
        confidence=str(payload.get("confidence") or "medium"),
        metadata={"fingerprint": fingerprint, "signal_type": signal_type},
    )
    return insert_evidence(db_path, [record])[0]


def _candidate_card(db_path: Path, card: dict[str, Any], *, actor: str, reason: str) -> dict[str, Any]:
    card_id = upsert_card(db_path, card, actor=actor, reason=reason)
    return _sanitize_for_output(get_card(db_path, card_id) or card)


def _reject_cards(db_path: Path, card_ids: list[str], evidence_id: str) -> list[str]:
    rejected: list[str] = []
    for card_id in card_ids:
        card = get_card(db_path, card_id)
        if card and card.get("status") not in {"rejected", "superseded"}:
            transition_card(db_path, card_id, "rejected", reason="correction", actor="contextwhere-signal", evidence=[evidence_id])
            rejected.append(card_id)
    return rejected


def capture_signal(db_path: Path, payload: dict[str, Any], *, repository: str | None = None, machine: str | None = None, threshold: int = DEFAULT_FALLBACK_THRESHOLD) -> dict[str, Any]:
    signal_type = str(payload.get("type") or "").strip()
    if signal_type not in SIGNAL_TYPES:
        raise ValueError(f"unsupported signal type: {signal_type}")
    if signal_type != "tool_failure":
        assert_safe_signal(payload)
    else:
        assert_no_unsafe_signal_fields(payload)
    fingerprint = str(payload.get("fingerprint") or stable_fingerprint(payload))
    evidence_payload = dict(payload)
    if signal_type == "tool_failure":
        evidence_payload.update(sanitize_failure_payload(payload))
    evidence_id = _evidence(db_path, signal_type, fingerprint, evidence_payload)
    result: dict[str, Any] = {"ok": True, "signal_type": signal_type, "fingerprint": fingerprint, "evidence_id": evidence_id}

    if signal_type == "tool_failure":
        clean_failure = failure_summary(evidence_payload)
        count = _count_failures(db_path, fingerprint)
        procedures = active_verified_procedures(db_path, fingerprint=fingerprint, repository=repository, machine=machine) if count >= threshold else []
        card = {
            "card_id": f"incident-{_short(fingerprint)}",
            "type": "incident lesson",
            "summary": f"repeated tool failure: {clean_failure[:240]}",
            "scope": _scope(repository),
            "status": "candidate" if count >= threshold else "observed",
            "evidence": [evidence_id],
            "freshness": {"observed_at": utc_now()},
            "failure_fingerprint": fingerprint,
            "lesson": clean_failure[:1200],
        }
        result.update({"failure_count": count, "procedures": procedures, "card": _candidate_card(db_path, card, actor="contextwhere-signal", reason="tool_failure")})
    elif signal_type == "verified_success":
        if not payload.get("success_evidence"):
            raise ValueError("verified_success requires success_evidence")
        card = {
            "card_id": f"proc-{_short(fingerprint)}",
            "type": "procedure/runbook",
            "summary": sanitize_text(str(payload.get("summary") or payload.get("resolution") or "Verified procedure"))[:280],
            "scope": _scope(repository),
            "status": "candidate",
            "evidence": [evidence_id],
            "freshness": {"observed_at": utc_now()},
            "verification": {"verified_at": utc_now(), "ok": True, "method": "signal:verified_success"},
            "failure_fingerprint": str(payload.get("failure_fingerprint") or fingerprint),
            "steps": [sanitize_text(str(step))[:300] for step in (payload.get("steps") or [payload.get("resolution") or "repeat verified resolution"])],
            "success_checks": [sanitize_text(str(check))[:200] for check in (payload.get("success_checks") or [payload.get("success_evidence")])],
            "resolution": sanitize_text(str(payload.get("resolution") or ""))[:1200],
        }
        result["card"] = _candidate_card(db_path, card, actor="contextwhere-signal", reason="verified_success")
    elif signal_type == "environment_fact":
        if not (payload.get("verified") is True or (isinstance(payload.get("verification"), dict) and payload["verification"].get("ok") is True)):
            raise ValueError("environment_fact requires verified=true or verification.ok=true")
        card = {
            "card_id": f"machine-{_short(fingerprint)}",
            "type": "machine",
            "summary": sanitize_text(str(payload.get("summary") or f"{payload.get('name')} is verified"))[:280],
            "scope": _scope(repository, machine),
            "status": "candidate",
            "evidence": [evidence_id],
            "freshness": {"observed_at": utc_now()},
            "verification": payload.get("verification") or {"verified_at": utc_now(), "ok": True, "method": str(payload.get("method") or "signal")},
            "rule": normalized_text(payload, ("name", "value"))[:1200],
        }
        result["card"] = _candidate_card(db_path, card, actor="contextwhere-signal", reason="environment_fact")
    elif signal_type in {"user_remember", "user_correction"}:
        rejected = _reject_cards(db_path, [str(x) for x in payload.get("rejects", [])], evidence_id)
        card = {
            "card_id": f"remember-{_short(fingerprint)}",
            "type": "constraint/preference",
            "summary": sanitize_text(str(payload.get("summary") or payload.get("text") or signal_type))[:280],
            "scope": _scope(repository),
            "status": "candidate",
            "evidence": [evidence_id],
            "freshness": {"observed_at": utc_now()},
            "rule": sanitize_text(str(payload.get("text") or payload.get("summary") or ""))[:1200],
            "rationale": sanitize_text(str(payload.get("reason") or ""))[:1200],
            "supersedes": [str(x) for x in payload.get("supersedes", [])],
        }
        result.update({"card": _candidate_card(db_path, card, actor="contextwhere-signal", reason=signal_type), "rejected": rejected})
    elif signal_type in {"session_summary", "blocker"}:
        text = sanitize_text(str(payload.get("text") or payload.get("summary") or ""))
        card = {
            "card_id": f"{signal_type.replace('_', '-')}-{_short(fingerprint)}",
            "type": "incident lesson" if signal_type == "blocker" else "decision/ADR",
            "summary": sanitize_text(str(payload.get("summary") or text or signal_type))[:280],
            "scope": _scope(repository),
            "status": "observed",
            "evidence": [evidence_id],
            "freshness": {"observed_at": utc_now()},
            "lesson": text[:1200] if signal_type == "blocker" else "",
            "decision": text[:1200] if signal_type == "session_summary" else "",
        }
        result["card"] = _candidate_card(db_path, card, actor="contextwhere-signal", reason=signal_type)
    return _sanitize_for_output(result)


def preflight(db_path: Path, *, repository: str | None = None, machine: str | None = None, fingerprint: str | None = None, threshold: int = DEFAULT_FALLBACK_THRESHOLD) -> dict[str, Any]:
    procedures: list[dict[str, Any]] = []
    if fingerprint and _count_failures(db_path, fingerprint) >= threshold:
        procedures = active_verified_procedures(db_path, fingerprint=fingerprint, repository=repository, machine=machine)
    return _sanitize_for_output({"ok": True, "scope": {"repository": repository, "machine": machine}, "fingerprint": fingerprint, "threshold": threshold, "procedures": procedures})
