from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .schemas import normalize_sensitivity, safety_messages

CARD_VERSION = "v1"
CARD_TYPES = {"constraint/preference", "procedure/runbook", "decision/ADR", "incident lesson"}
SCOPE_TYPES = {"global", "workspace", "repository", "machine"}
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
UNSAFE_TERMS = (
    "bypass auth",
    "ignore failing security",
    "disable security",
    "skip verification",
    "node_tls_reject_unauthorized=0",
    "disable scanner",
)


@dataclass(frozen=True)
class CardScope:
    type: str
    key: str

    @classmethod
    def from_value(cls, value: Any) -> "CardScope":
        if isinstance(value, dict):
            return cls(type=str(value.get("type") or "").strip(), key=str(value.get("key") or "").strip())
        text = str(value or "").strip()
        if ":" in text:
            scope_type, scope_key = text.split(":", 1)
            return cls(scope_type, scope_key)
        return cls(text, "default" if text == "global" else "")

    def to_dict(self) -> dict[str, str]:
        return {"type": self.type, "key": self.key}


@dataclass(frozen=True)
class ContextCard:
    type: str
    summary: str
    scope: CardScope
    status: str
    evidence: list[str]
    verification: dict[str, Any]
    freshness: dict[str, Any]
    sensitivity: str = "internal"
    notes: str = ""
    raw_envelope: dict[str, Any] = field(default_factory=dict, compare=False)
    card_id: str | None = None
    version: str = CARD_VERSION

    @classmethod
    def from_envelope(cls, envelope: dict[str, Any]) -> "ContextCard":
        evidence = envelope.get("evidence") if "evidence" in envelope else envelope.get("evidence_ids", [])
        return cls(
            card_id=str(envelope.get("card_id") or "").strip() or None,
            version=str(envelope.get("version") or CARD_VERSION),
            type=str(envelope.get("type") or envelope.get("card_type") or "").strip(),
            summary=str(envelope.get("summary") or "").strip(),
            scope=CardScope.from_value(envelope.get("scope")),
            status=str(envelope.get("status") or "").strip(),
            evidence=[str(item).strip() for item in evidence] if isinstance(evidence, list) else [],
            verification=envelope.get("verification") if isinstance(envelope.get("verification"), dict) else {},
            freshness=envelope.get("freshness") if isinstance(envelope.get("freshness"), dict) else {},
            sensitivity=normalize_sensitivity(envelope.get("sensitivity") or "internal"),
            notes=str(envelope.get("notes") or ""),
            raw_envelope=dict(envelope),
        )

    def to_envelope(self) -> dict[str, Any]:
        data = {
            "version": self.version,
            "type": self.type,
            "summary": self.summary,
            "scope": self.scope.to_dict(),
            "status": self.status,
            "evidence": list(self.evidence),
            "verification": dict(self.verification),
            "freshness": dict(self.freshness),
            "sensitivity": self.sensitivity,
            "notes": self.notes,
        }
        if self.card_id:
            data["card_id"] = self.card_id
        return data


def legal_transition(from_status: str, to_status: str) -> bool:
    return from_status == to_status or to_status in LEGAL_TRANSITIONS.get(from_status, set())


def lint_card(card: ContextCard) -> list[str]:
    messages: list[str] = []
    messages.extend(safety_messages(card.raw_envelope or card.to_envelope()))
    if card.version != CARD_VERSION:
        messages.append("version must be v1")
    if card.type not in CARD_TYPES:
        messages.append("type must be one of: " + ", ".join(sorted(CARD_TYPES)))
    if not card.summary:
        messages.append("summary is required")
    elif len(card.summary) > 280:
        messages.append("summary must be <= 280 characters")
    if card.scope.type not in SCOPE_TYPES:
        messages.append("scope.type must be global, workspace, repository, or machine")
    if not card.scope.key:
        messages.append("scope.key is required")
    if not card.status:
        messages.append("status is required")
    elif card.status not in STATUSES:
        messages.append("status is invalid")
    if not card.evidence:
        messages.append("evidence is required")
    for index, evidence_id in enumerate(card.evidence):
        if not evidence_id:
            messages.append(f"evidence[{index}] is required")
    if len(card.evidence) > 20:
        messages.append("evidence must contain <= 20 ids")
    if not card.freshness:
        messages.append("freshness is required")
    elif len(str(card.freshness)) > 400:
        messages.append("freshness must be <= 400 characters")
    if len(card.notes) > 2000:
        messages.append("notes must be <= 2000 characters")
    if card.type == "procedure/runbook":
        if not card.verification.get("verified_at"):
            messages.append("verification.verified_at is required")
        if card.verification.get("ok") is not True:
            messages.append("verification.ok must be true")
        if "success_checks=" not in card.notes and "success_checks" not in card.verification:
            messages.append("success_checks are required")
    if card.scope.type == "machine" and not card.freshness.get("observed_at"):
        messages.append("freshness.observed_at is required")
    lowered = card.notes.lower()
    if any(term in lowered for term in UNSAFE_TERMS):
        messages.append("unsafe workaround is not allowed")
    return messages


def require_valid_card(card: ContextCard) -> None:
    errors = lint_card(card)
    if errors:
        raise ValueError("; ".join(errors))
