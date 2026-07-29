from __future__ import annotations

from dataclasses import dataclass, field, asdict
import re
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

SENSITIVITY_ALIASES = {
    "public": "public",
    "internal": "internal",
    "confidential": "confidential",
    "restricted": "secret-like",
    "secret": "secret-like",
    "secret-like": "secret-like",
}


def normalize_sensitivity(value: Any) -> str:
    if not isinstance(value, str):
        return "internal"
    return SENSITIVITY_ALIASES.get(value.strip().lower(), "secret-like")



SECRET_VALUE_PATTERNS = (
    (re.compile(r"-----BEGIN [A-Z ]*(?:PRIVATE KEY|CERTIFICATE)[A-Z ]*-----.*?-----END [A-Z ]*(?:PRIVATE KEY|CERTIFICATE)[A-Z ]*-----", re.IGNORECASE | re.DOTALL), "<redacted-secret>"),
    (re.compile(r"\b(?:password|passwd|pwd|token|api[_-]?key|secret|cookie)\s*[:=]\s*\S+", re.IGNORECASE), "<redacted-secret>"),
    (re.compile(r"\bauthorization\s*:\s*bearer\s+\S+", re.IGNORECASE), "<redacted-secret>"),
    (re.compile(r"\b(?:OPENAI_API_KEY|AWS_SECRET_ACCESS_KEY|GITHUB_TOKEN|SLACK_BOT_TOKEN)\s*=\s*\S+", re.IGNORECASE), "<redacted-secret>"),
    (re.compile(r"(?:^|\n)From: .+\nSubject: .+", re.IGNORECASE | re.DOTALL), "<redacted-raw-message>"),
    (re.compile(r"\b(?:full mail body|body text copied verbatim|raw document|raw mail)\b", re.IGNORECASE), "<redacted-raw-content>"),
)
PROMPT_LIKE_PATTERNS = (
    re.compile(r"ignore (?:all )?(?:previous|prior|above) instructions", re.IGNORECASE),
    re.compile(r"disregard (?:all )?(?:previous|prior|above) instructions", re.IGNORECASE),
    re.compile(r"(?:system|developer) prompt", re.IGNORECASE),
    re.compile(r"you are now", re.IGNORECASE),
    re.compile(r"delete (?:the )?(?:wiki|memory|database|files)", re.IGNORECASE),
)
UNSAFE_WORKAROUND_PATTERNS = (
    re.compile(r"NODE_TLS_REJECT_UNAUTHORIZED\s*=\s*0", re.IGNORECASE),
    re.compile(r"\b(?:curl\s+)?-k\b|\b--insecure\b", re.IGNORECASE),
    re.compile(r"\b(?:rejectUnauthorized|verify)\s*[:=]\s*false", re.IGNORECASE),
    re.compile(r"\b(?:bypass|disable|skip|ignore)\s+(?:tls|ssl|cert(?:ificate)?(?: verification)?|auth(?:entication|orization)?|security|scanner|verification)\b", re.IGNORECASE),
    re.compile(r"\bignore failing security\b", re.IGNORECASE),
)
UNSAFE_SECRET_KEYS = {
    "token", "access_token", "refresh_token", "password", "passwd", "pwd", "cookie", "set_cookie",
    "private_key", "privatekey", "raw_cert", "raw_certificate", "certificate_pem", "raw_env",
    "env_dump", "raw_body", "body", "raw_mail", "raw_email", "raw_document", "raw_doc",
    "document_body", "mail_body", "full_body", "content_raw",
}


def is_unsafe_key(key: str) -> bool:
    normalized = key.lower().replace("-", "_")
    return normalized in UNSAFE_SECRET_KEYS or normalized.endswith(("_token", "_password", "_cookie", "_private_key"))


def _redact_secret_values(value: str) -> str:
    text = value
    for pattern, replacement in SECRET_VALUE_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def redact_text(value: str) -> str:
    text = _redact_secret_values(value)
    if any(pattern.search(text) for pattern in PROMPT_LIKE_PATTERNS):
        return "<neutralized-prompt-instruction>"
    return text


def redact_stored_evidence_text(value: str) -> str:
    text = _redact_secret_values(value)
    if any(pattern.search(text) for pattern in PROMPT_LIKE_PATTERNS):
        return "<neutralized-prompt-instruction>"
    return text


def safety_messages(value: Any, path: str = "card") -> list[str]:
    messages: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if is_unsafe_key(str(key)):
                messages.append(f"unsafe secret-bearing field rejected: {child_path}")
            messages.extend(safety_messages(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            messages.extend(safety_messages(child, f"{path}[{index}]"))
    elif isinstance(value, str):
        for pattern, _ in SECRET_VALUE_PATTERNS:
            if pattern.search(value):
                messages.append(f"unsafe secret-like value rejected: {path}")
                break
        for pattern in PROMPT_LIKE_PATTERNS:
            if pattern.search(value):
                messages.append(f"unsafe prompt-like instruction rejected: {path}")
                break
        for pattern in UNSAFE_WORKAROUND_PATTERNS:
            if pattern.search(value):
                messages.append(f"unsafe workaround rejected: {path}")
                break
    return messages

ROUTING_KEYS = {
    "tenant",
    "scope",
    "source_kind",
    "source_locator",
    "observed_at",
    "valid_from",
    "valid_until",
    "stale_after",
    "supersedes",
    "superseded_by",
}


def routing_metadata(data: dict[str, Any], provider: str, default_kind: str) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    for key in ROUTING_KEYS:
        value = data.get(key)
        if value not in (None, ""):
            metadata[key] = value
    metadata.setdefault("source_kind", str(data.get("source_kind") or provider))
    if "source_locator" not in metadata:
        source_ref = data.get("source_id") or data.get("id") or data.get("file_id") or data.get("task_id")
        if source_ref:
            metadata["source_locator"] = f"{provider}:{data.get('kind') or default_kind}:{source_ref}"
    return metadata



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

    def __post_init__(self) -> None:
        self.title = redact_stored_evidence_text(str(self.title or ""))
        self.snippet = redact_stored_evidence_text(str(self.snippet or ""))
        self.summary = redact_stored_evidence_text(str(self.summary or ""))
        clean_metadata, omitted = sanitize_mapping(self.metadata)
        self.metadata = clean_metadata
        self.omitted_fields = sorted(set(self.omitted_fields + omitted))

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
    if isinstance(value, str):
        return redact_text(value), []
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
    metadata = {k: v for k, v in clean.items() if k not in {"kind", "source_id", "id", "file_id", "task_id", "title", "subject", "name", "evidence_snippet", "snippet", "reason", "received_at", "source_received_at", "modified_at", "due_at", "provenance", "sensitivity", "confidence"}}
    metadata.update(routing_metadata(clean, provider, kind))
    return EvidenceRecord(
        provider=provider,
        source_ref=source_ref,
        kind=kind,
        title=title,
        snippet=snippet,
        occurred_at=str(occurred_at) if occurred_at else None,
        sensitivity=normalize_sensitivity(clean.get("sensitivity") or "internal"),
        provenance=provenance,
        confidence=str(clean.get("confidence") or "medium"),
        metadata=metadata,
        omitted_fields=omitted,
    )
