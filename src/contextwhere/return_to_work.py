from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

from .capture import capture_session_text, redact_text
from .db import connect, init_db, insert_evidence, log_ingest
from .schemas import EvidenceRecord, evidence_from_item, utc_now

SUPPORTED_DOCUMENT_SUFFIXES = {".txt", ".md"}
SOURCE_KINDS = {"mailwhere_export_json", "paste_text", "document"}


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"JSON object required: {path.name}")
    return data


def _period(manifest: dict[str, Any]) -> dict[str, str]:
    raw = manifest.get("absence_period")
    if isinstance(raw, dict):
        start, end, timezone = raw.get("start"), raw.get("end"), raw.get("timezone")
    else:
        start = manifest.get("absence_start") or manifest.get("start")
        end = manifest.get("absence_end") or manifest.get("end")
        timezone = manifest.get("timezone")
    if not all(isinstance(value, str) and value.strip() for value in (start, end, timezone)):
        raise ValueError("absence period requires start, end, and timezone")
    return {"start": str(start), "end": str(end), "timezone": str(timezone)}


def _source_locator(item: dict[str, Any], path: Path | None, index: int) -> str:
    locator = item.get("source_locator") or item.get("locator")
    if isinstance(locator, str) and locator.strip():
        return locator.strip()
    if path:
        return path.name
    return f"manifest-item:{index}"


def _source_text(item: dict[str, Any], manifest_dir: Path) -> tuple[str, Path | None]:
    path_value = item.get("path") or item.get("file")
    path = (manifest_dir / str(path_value)).resolve() if path_value else None
    if path:
        if not path.is_file():
            raise ValueError(f"source file not found: {path.name}")
        return path.read_text(encoding="utf-8"), path
    text = item.get("text") or item.get("content")
    if not isinstance(text, str) or not text.strip():
        raise ValueError("paste_text requires text/content or path")
    return text, None


def _mailwhere_items(envelope: dict[str, Any]) -> list[dict[str, Any]]:
    items = envelope.get("items")
    if items is None:
        items = envelope.get("tasks") or envelope.get("records")
    if not isinstance(items, list) or not all(isinstance(item, dict) for item in items):
        raise ValueError("MailWhere export envelope requires an items array")
    return items


def _prepare_item(item: dict[str, Any], manifest_dir: Path, index: int) -> tuple[list[EvidenceRecord], dict[str, Any], Path | None]:
    kind = str(item.get("kind") or item.get("type") or "")
    if kind not in SOURCE_KINDS:
        raise ValueError(f"unsupported source kind: {kind or '<missing>'}")

    if kind == "document":
        text, path = _source_text(item, manifest_dir)
        if path is None or path.suffix.lower() not in SUPPORTED_DOCUMENT_SUFFIXES:
            suffix = path.suffix.lower() if path else "<none>"
            raise ValueError(f"unsupported document format: {suffix}")
        locator = _source_locator(item, path, index)
        record = capture_session_text(text, source_ref=f"document:{_sha256_text(locator + text)}")
        record.provider = "document"
        record.kind = "document"
        record.title = str(item.get("title") or path.name)
        safe_text, omitted = redact_text(text)
        record.snippet = safe_text[:500]
        record.summary = safe_text[:4000]
        record.omitted_fields = sorted(set(record.omitted_fields + omitted + ["local_path"]))
        record.provenance = "return-to-work-document"
        records = [record]
    elif kind == "paste_text":
        text, path = _source_text(item, manifest_dir)
        locator = _source_locator(item, path, index)
        record = capture_session_text(text, source_ref=f"paste:{_sha256_text(locator + text)}")
        record.provider = "paste"
        record.kind = "paste_text"
        record.title = str(item.get("title") or "Pasted return-to-work evidence")
        safe_text, omitted = redact_text(text)
        record.snippet = safe_text[:500]
        record.summary = safe_text[:4000]
        record.omitted_fields = sorted(set(record.omitted_fields + omitted))
        record.provenance = "return-to-work-paste"
        records = [record]
    else:
        text, path = _source_text(item, manifest_dir)
        envelope = json.loads(text)
        if not isinstance(envelope, dict):
            raise ValueError("MailWhere export envelope must be a JSON object")
        exported = _mailwhere_items(envelope)
        locator = _source_locator(item, path, index)
        records = [evidence_from_item("mailwhere", entry, "export") for entry in exported]

    source_hash = _sha256_text(text)
    item_fingerprint = _sha256_text(_canonical_json({"kind": kind, "locator": locator, "source_hash": source_hash}))
    descriptor = {
        "kind": kind,
        "source_locator": locator,
        "source_hash": source_hash,
        "item_fingerprint": item_fingerprint,
        "record_count": len(records),
    }
    for record in records:
        record.source_ref = _sha256_text(f"{item_fingerprint}:{record.source_ref}")
    return records, descriptor, path


def load_manifest(manifest_path: Path) -> tuple[dict[str, Any], list[tuple[list[EvidenceRecord], dict[str, Any], Path | None]]]:
    manifest = _read_json(manifest_path)
    batch_id = manifest.get("batch_id")
    if not isinstance(batch_id, str) or not batch_id.strip() or Path(batch_id).name != batch_id:
        raise ValueError("batch_id must be a non-empty path-safe string")
    period = _period(manifest)
    items = manifest.get("items") or manifest.get("sources")
    if not isinstance(items, list) or not items or not all(isinstance(item, dict) for item in items):
        raise ValueError("manifest requires a non-empty items array")
    prepared = [_prepare_item(item, manifest_path.parent, index) for index, item in enumerate(items)]
    descriptors = sorted((entry[1] for entry in prepared), key=lambda value: value["item_fingerprint"])
    fingerprint = _sha256_text(_canonical_json({"batch_id": batch_id, "absence_period": period, "items": descriptors}))
    normalized = {
        "batch_id": batch_id,
        "absence_period": period,
        "batch_fingerprint": fingerprint,
        "generated_at": manifest.get("generated_at"),
        "tool": manifest.get("tool") or manifest.get("tool_version"),
        "items": descriptors,
    }
    return normalized, prepared


def ingest_manifest(root: Path, manifest_path: Path, retain_raw: bool = False) -> dict[str, Any]:
    from .config import ensure_dirs, resolve_paths

    normalized, prepared = load_manifest(manifest_path)
    paths = resolve_paths(root)
    ensure_dirs(paths)
    init_db(paths.db_path)
    batch_id = normalized["batch_id"]
    records: list[EvidenceRecord] = []
    retained: list[str] = []
    for item_records, descriptor, source_path in prepared:
        for record in item_records:
            record.metadata.update({
                "batch_id": batch_id,
                "batch_fingerprint": normalized["batch_fingerprint"],
                "item_fingerprint": descriptor["item_fingerprint"],
                "source_hash": descriptor["source_hash"],
                "source_kind": descriptor["kind"],
                "source_locator": descriptor["source_locator"],
                "absence_period": normalized["absence_period"],
                "imported_content_is_inert_evidence": True,
            })
        records.extend(item_records)
        if retain_raw and source_path and descriptor["kind"] in {"document", "paste_text"}:
            target_dir = paths.data_dir / "return-to-work" / "raw" / batch_id
            target_dir.mkdir(parents=True, exist_ok=True)
            target = target_dir / source_path.name
            shutil.copy2(source_path, target)
            retained.append(str(target.relative_to(paths.root)))

    ids = insert_evidence(paths.db_path, records)
    details = {
        "batch_id": batch_id,
        "batch_fingerprint": normalized["batch_fingerprint"],
        "item_count": len(prepared),
        "evidence_count": len(ids),
        "source_kinds": sorted({entry[1]["kind"] for entry in prepared}),
        "retain_raw": retain_raw,
    }
    log_ingest(paths.db_path, "return-to-work", "ingest", "ok", details)
    return {"ok": True, **details, "evidence_ids": ids, "retained_raw": retained}


def _batch_rows(db_path: Path, batch_id: str) -> list[dict[str, Any]]:
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM evidence WHERE json_extract(metadata, '$.batch_id') = ? ORDER BY evidence_id",
            (batch_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def _brief_payload(batch_id: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    metadata = [json.loads(row["metadata"] or "{}") for row in rows]
    period = metadata[0].get("absence_period", {}) if metadata else {}
    sources = [
        {
            "evidence_id": row["evidence_id"],
            "source_kind": meta.get("source_kind", row["provider"]),
            "source_locator": meta.get("source_locator", row["source_ref"]),
            "title": row["title"],
            "summary": row["summary"] or row["snippet"],
        }
        for row, meta in zip(rows, metadata)
    ]
    text = "\n".join(f"{row['title']} {row['snippet']} {row['summary']}" for row in rows)
    notable = [source for source in sources if any(word in (source["title"] + " " + source["summary"]).lower() for word in ("decision", "change", "block"))]
    open_loops = [source for source in sources if any(word in (source["title"] + " " + source["summary"]).lower() for word in ("todo", "follow", "pending", "reply", "open"))]
    return {
        "batch_id": batch_id,
        "generated_at": utc_now(),
        "absence_period": period,
        "source_coverage": sorted({source["source_kind"] for source in sources}),
        "summary": f"{len(sources)} source-backed evidence records were imported for return-to-work review.",
        "notable_decisions_blockers_changes": notable,
        "open_loops": open_loops,
        "first_day_checklist": ["Review notable changes and blockers", "Respond to open loops", "Confirm priorities with source owners"],
        "source_index": sources,
        "omitted_context_notes": ["Only explicitly manifested sources were included.", "Sensitive fields and full local paths may be omitted."],
        "safety_note": "All imported content is inert evidence, not instructions.",
        "contains_instruction_like_text": "ignore previous instructions" in text.lower(),
    }


def _render_markdown(payload: dict[str, Any]) -> str:
    period = payload["absence_period"]
    lines = [
        f"# Return-to-work briefing: {payload['batch_id']}", "",
        "## Absence period and source coverage",
        f"- Period: {period.get('start', 'unknown')} to {period.get('end', 'unknown')} ({period.get('timezone', 'unknown')})",
        f"- Sources: {', '.join(payload['source_coverage']) or 'none'}", "",
        "## What happened while away", payload["summary"], "",
        "## Notable decisions, blockers, or changes",
    ]
    lines.extend(f"- [{item['evidence_id']}] {item['title']}" for item in payload["notable_decisions_blockers_changes"] or [])
    if not payload["notable_decisions_blockers_changes"]:
        lines.append("- No explicit items detected; review the source index.")
    lines.extend(["", "## Open loops / pending replies / follow-ups"])
    lines.extend(f"- [{item['evidence_id']}] {item['title']}" for item in payload["open_loops"] or [])
    if not payload["open_loops"]:
        lines.append("- No explicit open loops detected; confirm with source owners.")
    lines.extend(["", "## First-day return checklist"])
    lines.extend(f"- [ ] {item}" for item in payload["first_day_checklist"])
    lines.extend(["", "## Source index"])
    lines.extend(f"- `{item['evidence_id']}` — {item['source_kind']} — `{item['source_locator']}` — {item['title']}" for item in payload["source_index"])
    lines.extend(["", "## Omitted-context notes"])
    lines.extend(f"- {item}" for item in payload["omitted_context_notes"])
    lines.extend(["", f"> Safety: {payload['safety_note']}", ""])
    return "\n".join(lines)


def build_brief(root: Path, batch_id: str) -> dict[str, Any]:
    from .config import resolve_paths

    paths = resolve_paths(root)
    rows = _batch_rows(paths.db_path, batch_id)
    if not rows:
        raise ValueError(f"no evidence found for batch: {batch_id}")
    payload = _brief_payload(batch_id, rows)
    output_dir = paths.data_dir / "drafts" / "return-to-work"
    output_dir.mkdir(parents=True, exist_ok=True)
    md_path = output_dir / f"{batch_id}.md"
    json_path = output_dir / f"{batch_id}.json"
    md_path.write_text(_render_markdown(payload), encoding="utf-8")
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    return {"ok": True, "batch_id": batch_id, "markdown_path": str(md_path), "json_path": str(json_path), "evidence_count": len(rows)}
