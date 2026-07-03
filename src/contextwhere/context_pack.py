from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .db import query_evidence_with_mode
from .schemas import normalize_sensitivity, utc_now

SENSITIVITY_ORDER = {"public": 0, "internal": 1, "confidential": 2, "secret-like": 3}


def _meta(row: dict[str, Any]) -> dict[str, Any]:
    try:
        value = json.loads(row.get("metadata") or "{}")
        return value if isinstance(value, dict) else {}
    except json.JSONDecodeError:
        return {}


def _split_csv(value: str | None) -> list[str]:
    return [part.strip() for part in (value or "").split(",") if part.strip()]


def _too_sensitive(row: dict[str, Any], ceiling: str) -> bool:
    return SENSITIVITY_ORDER.get(normalize_sensitivity(row.get("sensitivity") or "internal"), 3) > SENSITIVITY_ORDER.get(normalize_sensitivity(ceiling), 1)


def _is_stale(meta: dict[str, Any], now: datetime | None = None) -> bool:
    stale_after = meta.get("stale_after")
    if not isinstance(stale_after, str) or not stale_after.strip():
        return False
    try:
        stamp = stale_after.replace("Z", "+00:00")
        dt = datetime.fromisoformat(stamp)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return False
    return dt < (now or datetime.now(timezone.utc))


def _source_locator(row: dict[str, Any], meta: dict[str, Any]) -> str:
    return str(meta.get("source_locator") or f"{row.get('provider')}:{row.get('kind')}:{row.get('source_ref')}")


def _reason(row: dict[str, Any], meta: dict[str, Any], query: str) -> str:
    bits = []
    if query:
        bits.append("query-match")
    if meta.get("scope"):
        bits.append(f"scope:{meta['scope']}")
    if meta.get("tenant"):
        bits.append(f"tenant:{meta['tenant']}")
    return ", ".join(bits) or "recent-evidence"


def build_context_pack(
    db_path: Path,
    *,
    task: str,
    query: str = "",
    tenant: str | None = None,
    scope: str | None = None,
    source_kinds: list[str] | None = None,
    max_items: int = 20,
    sensitivity_ceiling: str = "internal",
    include_stale: bool = False,
    include_history: bool = False,
) -> dict[str, Any]:
    rows, mode = query_evidence_with_mode(db_path, query, limit=max(max_items * 5, max_items, 20))
    omitted: dict[str, int] = {"out_of_scope": 0, "too_sensitive": 0, "stale": 0, "superseded": 0, "budget": 0}
    included = []
    source_kinds = source_kinds or []

    for row in rows:
        meta = _meta(row)
        if tenant and meta.get("tenant") != tenant:
            omitted["out_of_scope"] += 1
            continue
        if scope and meta.get("scope") != scope:
            omitted["out_of_scope"] += 1
            continue
        if source_kinds and str(meta.get("source_kind") or row.get("provider")) not in source_kinds:
            omitted["out_of_scope"] += 1
            continue
        if _too_sensitive(row, sensitivity_ceiling):
            omitted["too_sensitive"] += 1
            continue
        if not include_history and meta.get("superseded_by"):
            omitted["superseded"] += 1
            continue
        if not include_stale and _is_stale(meta):
            omitted["stale"] += 1
            continue
        if len(included) >= max_items:
            omitted["budget"] += 1
            continue
        included.append({
            "evidence_id": row["evidence_id"],
            "title": row.get("title") or "",
            "snippet": row.get("snippet") or "",
            "source_locator": _source_locator(row, meta),
            "source_kind": str(meta.get("source_kind") or row.get("provider")),
            "tenant": meta.get("tenant"),
            "scope": meta.get("scope"),
            "freshness": {
                "observed_at": meta.get("observed_at") or row.get("occurred_at"),
                "ingested_at": row.get("ingested_at"),
                "stale_after": meta.get("stale_after"),
            },
            "sensitivity": row.get("sensitivity"),
            "confidence": row.get("confidence"),
            "reason": _reason(row, meta, query),
        })

    pack_id = "context-pack:" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    manifest = {
        "pack_id": pack_id,
        "created_at": utc_now(),
        "task": task,
        "tenant_filter": tenant,
        "scope_filter": scope,
        "source_kinds": source_kinds,
        "budget": {"max_items": max_items, "max_tokens": None},
        "selection_policy": {
            "search_mode": mode,
            "freshness": "current" if not include_stale else "any",
            "sensitivity_ceiling": sensitivity_ceiling,
            "include_history": include_history,
            "expansion_steps": ["evidence_ledger", "provider_rehydrate_if_needed"],
        },
        "included": [{k: item[k] for k in ("evidence_id", "source_locator", "reason", "confidence")} for item in included],
        "omitted": [{"reason": key, "count": count} for key, count in omitted.items() if count],
    }
    return {"ok": True, "format": "contextwhere-context-pack-v1", "manifest": manifest, "items": included}


def render_markdown(pack: dict[str, Any]) -> str:
    manifest = pack["manifest"]
    lines = [
        f"# Context pack — {manifest['task']}",
        "",
        f"- pack_id: `{manifest['pack_id']}`",
        f"- created_at: `{manifest['created_at']}`",
        f"- tenant_filter: `{manifest.get('tenant_filter')}`",
        f"- scope_filter: `{manifest.get('scope_filter')}`",
        f"- sensitivity_ceiling: `{manifest['selection_policy']['sensitivity_ceiling']}`",
        "",
        "## Included evidence",
    ]
    for item in pack["items"]:
        lines.extend([
            "",
            f"### {item['title'] or item['evidence_id']}",
            f"- evidence_id: `{item['evidence_id']}`",
            f"- source_locator: `{item['source_locator']}`",
            f"- reason: {item['reason']}",
            f"- freshness: `{item['freshness']}`",
            f"- confidence: `{item['confidence']}`",
            "",
            item["snippet"],
        ])
    lines.extend(["", "## Omitted context"])
    for item in manifest["omitted"]:
        lines.append(f"- {item['reason']}: {item['count']}")
    if not manifest["omitted"]:
        lines.append("- none")
    return "\n".join(lines).rstrip() + "\n"
