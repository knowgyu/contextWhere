from __future__ import annotations

import json
import re
from pathlib import Path

from .schemas import EvidenceRecord, redact_text as redact_unsafe_text

SESSION_FIELDS = ("goal", "constraints", "decisions", "changes", "verification", "follow-ups", "followups")
PATH_RE = re.compile(r"(?:/[\w .@+-]+){2,}|[A-Za-z]:\\[^\s]+")
PROMPT_LOG_RE = re.compile(r"prompt\s*log|raw\s*transcript|secret", re.IGNORECASE)


def redact_text(value: str) -> tuple[str, list[str]]:
    omitted: list[str] = []
    text = redact_unsafe_text(value)
    if PROMPT_LOG_RE.search(text):
        text = PROMPT_LOG_RE.sub("[REDACTED_SENSITIVE]", text)
        omitted.append("prompt_logs")
    if PATH_RE.search(text):
        text = PATH_RE.sub("[REDACTED_PATH]", text)
        omitted.append("local_path")
    return text, sorted(set(omitted))


def structured_summary(text: str) -> tuple[str, dict[str, str], list[str]]:
    data: dict[str, str] = {}
    omitted: list[str] = []
    for raw in text.splitlines():
        if ":" not in raw:
            continue
        key, value = raw.split(":", 1)
        norm = key.strip().lower()
        if norm in SESSION_FIELDS:
            clean, om = redact_text(value.strip())
            data[norm] = clean
            omitted.extend(om)
    if data:
        summary = "\n".join(f"{k}: {v}" for k, v in data.items())
        return summary, data, sorted(set(omitted))
    clean, omitted = redact_text(text.strip().splitlines()[0][:500] if text.strip() else "")
    return clean, {}, omitted


def capture_session_text(text: str, source_ref: str = "stdin") -> EvidenceRecord:
    title = "CLI agent session capture"
    metadata = {}
    omitted: list[str] = []
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            safe_meta = {}
            for key in SESSION_FIELDS:
                if key in parsed:
                    clean, om = redact_text(str(parsed[key]))
                    safe_meta[key] = clean
                    omitted.extend(om)
            title_text = str(safe_meta.get("goal") or parsed.get("title") or title)
            title, title_omitted = redact_text(title_text)
            omitted.extend(title_omitted)
            metadata = safe_meta
    except json.JSONDecodeError:
        summary, metadata, omitted = structured_summary(text)
        title = metadata.get("goal") or title
    else:
        summary = "\n".join(f"{k}: {v}" for k, v in metadata.items())
    snippet_source = (metadata.get("goal") or summary) if metadata else summary
    snippet = snippet_source.strip()[:500]
    return EvidenceRecord(
        provider="cli-agent",
        source_ref=source_ref,
        kind="session",
        title=title,
        snippet=snippet,
        summary=summary,
        provenance="capture-session",
        metadata=metadata,
        omitted_fields=sorted(set(omitted)),
    )


def capture_session_file(path: Path) -> EvidenceRecord:
    digest_ref = f"file:{path.name}"
    record = capture_session_text(path.read_text(encoding="utf-8"), source_ref=digest_ref)
    if str(path) != path.name:
        record.omitted_fields = sorted(set(record.omitted_fields + ["local_path"]))
    return record
