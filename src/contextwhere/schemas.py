from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any

SENSITIVE_KEYS = {
    "raw_body",
    "body",
    "full_addresses",
    "recipients",
    "attachments",
    "prompt_logs",
    "api_key",
    "local_path",
    "path",
    "source_path",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass
class UnavailableProvider:
    provider: str
    reason: str
    details: dict[str, Any] = field(default_factory=dict)
    ok: bool = False
    status: str = "unavailable"
    safe_to_continue: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class EvidenceRecord:
    provider: str
    source_ref: str
    kind: str
    title: str = ""
    snippet: str = ""
    summary: str = ""
    occurred_at: str | None = None
    sensitivity: str = "internal"
    provenance: str = ""
    confidence: str = "medium"
    metadata: dict[str, Any] = field(default_factory=dict)
    omitted_fields: list[str] = field(default_factory=list)

    def normalized_text(self) -> str:
        return "\n".join(part for part in [self.title, self.snippet, self.summary] if part)


def is_sensitive_key(key: str) -> bool:
    low = key.lower()
    return low in SENSITIVE_KEYS or low.endswith("_path") or low.endswith("_body")


def sanitize_value(value: Any, prefix: str = "") -> tuple[Any, list[str]]:
    omitted: list[str] = []
    if isinstance(value, dict):
        clean: dict[str, Any] = {}
        for key, child in value.items():
            full = f"{prefix}.{key}" if prefix else key
            if is_sensitive_key(key):
                omitted.append(full)
                continue
            child_clean, child_omitted = sanitize_value(child, full)
            clean[key] = child_clean
            omitted.extend(child_omitted)
        return clean, sorted(set(omitted))
    if isinstance(value, list):
        clean_list = []
        for idx, child in enumerate(value):
            child_clean, child_omitted = sanitize_value(child, f"{prefix}[{idx}]")
            clean_list.append(child_clean)
            omitted.extend(child_omitted)
        return clean_list, sorted(set(omitted))
    return value, []


def sanitize_mapping(data: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    clean, omitted = sanitize_value(data)
    return clean, omitted


def evidence_from_item(provider: str, item: dict[str, Any], default_kind: str = "item") -> EvidenceRecord:
    clean, omitted = sanitize_mapping(item)
    kind = str(clean.get("kind") or default_kind)
    source_ref = str(clean.get("source_id") or clean.get("id") or clean.get("file_id") or clean.get("task_id") or "unknown")
    title = str(clean.get("title") or clean.get("subject") or clean.get("name") or source_ref)
    snippet = str(clean.get("evidence_snippet") or clean.get("snippet") or clean.get("reason") or "")
    occurred_at = clean.get("received_at") or clean.get("source_received_at") or clean.get("modified_at") or clean.get("due_at")
    provenance = str(clean.get("provenance") or provider)
    metadata = {k: v for k, v in clean.items() if k not in {"kind", "source_id", "id", "file_id", "task_id", "title", "subject", "name", "evidence_snippet", "snippet", "reason", "received_at", "source_received_at", "modified_at", "due_at", "provenance"}}
    return EvidenceRecord(
        provider=provider,
        source_ref=source_ref,
        kind=kind,
        title=title,
        snippet=snippet,
        occurred_at=str(occurred_at) if occurred_at else None,
        provenance=provenance,
        metadata=metadata,
        omitted_fields=omitted,
    )
