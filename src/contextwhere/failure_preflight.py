from __future__ import annotations

from pathlib import Path
from typing import Any

from . import memory
from .signals import capture_signal, preflight as signal_preflight, sanitize_text


def normalize_failure_fingerprint(text: str) -> str:
    return sanitize_text(text)


def observe_failure(db_path: Path, *, repository: str | None = None, machine: str | None = None, command: str = "", output: str = "", threshold: int = 3) -> dict[str, Any]:
    fingerprint = normalize_failure_fingerprint(output or command)
    sanitized_output = normalize_failure_fingerprint(output)
    result = capture_signal(
        db_path,
        {"type": "tool_failure", "tool": "command", "command": command, "error": sanitized_output, "fingerprint": fingerprint},
        repository=repository,
        machine=machine,
        threshold=max(1, threshold - 1),
    )
    result["observation_count"] = result.pop("failure_count")
    result["next_action"] = "use_verified_procedure_before_fallback" if result.get("procedures") else "record_observation"
    return result


def promote_failure_procedure(db_path: Path, *, failure_fingerprint: str, **_: Any) -> dict[str, Any]:
    raise ValueError("unresolved failure cannot be promoted to active procedure without verified success evidence")


def _latest_failure_fingerprint(db_path: Path, repository: str | None) -> str | None:
    if not repository:
        return None
    for status in ("candidate", "observed"):
        for card in memory.list_cards(db_path, scope_type="repository", scope_key=repository, status=status, limit=20):
            if card.get("type") == "incident lesson" and card.get("failure_fingerprint"):
                return str(card["failure_fingerprint"])
    return None


def record_verified_success(
    db_path: Path,
    *,
    repository: str | None = None,
    machine: str | None = None,
    command: str = "",
    output: str = "",
    steps: list[str] | None = None,
    evidence_id: str = "",
    failure_fingerprint: str | None = None,
    **_: Any,
) -> dict[str, Any]:
    fingerprint = failure_fingerprint or _latest_failure_fingerprint(db_path, repository) or normalize_failure_fingerprint(command)
    result = capture_signal(
        db_path,
        {
            "type": "verified_success",
            "summary": str(_.get("procedure_summary") or f"Verified resolution for {command or 'failure'}"),
            "failure_fingerprint": fingerprint,
            "resolution": command,
            "success_evidence": output or evidence_id or "verified success",
            "steps": steps or [command],
            "success_checks": _.get("success_checks") or ([f"{command} exits 0"] if command else ["command exits 0"]),
            "fingerprint": fingerprint,
        },
        repository=repository,
        machine=machine,
    )
    card = result["card"]
    if evidence_id and evidence_id not in card["evidence_ids"]:
        card["evidence_ids"].append(evidence_id)
        card["evidence"] = card["evidence_ids"]
        memory.upsert_card(db_path, card, actor="contextwhere-failure-preflight", reason="verified_success_evidence")
        card = memory.get_card(db_path, card["card_id"]) or card
    return {"ok": True, "candidate": card}


def observe_signal(
    db_path: Path,
    *,
    repository: str | None = None,
    machine: str | None = None,
    signal_type: str,
    summary: str = "",
    text: str = "",
    verified: bool = False,
    **extra: Any,
) -> dict[str, Any]:
    aliases = {"session_blocker": "blocker", "verified_environment_fact": "environment_fact", "verified_resolution": "verified_success"}
    kind = aliases.get(signal_type, signal_type)
    payload: dict[str, Any] = {"type": kind, "summary": summary, "text": text, **extra}
    if kind == "session_summary":
        from .signals import assert_safe_signal

        try:
            assert_safe_signal(payload)
        except ValueError:
            payload["text"] = summary
    if signal_type == "user_correction":
        payload["summary"] = f"correction: {summary or text}"
        payload.setdefault("reason", "correction")
    if kind == "verified_success":
        payload.setdefault("success_evidence", text or summary)
        payload.setdefault("resolution", text or summary)
    if kind == "environment_fact":
        payload.update({"name": summary or text, "value": text or summary, "verified": verified})
    return capture_signal(db_path, payload, repository=repository, machine=machine)


def preflight(db_path: Path, *, repository: str | None = None, machine: str | None = None, failure_fingerprint: str | None = None, threshold: int = 2) -> dict[str, Any]:
    return signal_preflight(db_path, repository=repository, machine=machine, fingerprint=failure_fingerprint, threshold=threshold)
