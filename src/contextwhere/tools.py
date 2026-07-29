from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .capture import capture_session_text
from .config import ensure_dirs, resolve_paths
from .db import init_db, insert_evidence, query_evidence_with_mode
from .entities import extract_entities, list_entities, list_relationships
from .recall import create_bundle, list_bundles, show_bundle
from .signals import capture_signal, memory_db, preflight as signals_preflight, stable_fingerprint

MAX_LIMIT = 500

TOOL_MANIFEST: list[dict[str, Any]] = [

    {
        "name": "signal_fingerprint",
        "description": "Return the stable sanitized fingerprint for a capture signal.",
        "input_schema": {"type": "object", "properties": {"type": {"type": "string"}}, "required": ["type"]},
        "safe": True,
        "mutates": False,
    },
    {
        "name": "capture_signal",
        "description": "Capture a sanitized memory signal and optional card candidate.",
        "input_schema": {"type": "object", "properties": {"type": {"type": "string"}, "repository": {"type": "string"}, "machine": {"type": "string"}, "home": {"type": "string"}}, "required": ["type"]},
        "safe": True,
        "mutates": True,
    },
    {
        "name": "signal_preflight",
        "description": "Return active verified procedures for a repeated failure fingerprint without invoking providers.",
        "input_schema": {"type": "object", "properties": {"fingerprint": {"type": "string"}, "repository": {"type": "string"}, "machine": {"type": "string"}}},
        "safe": True,
        "mutates": False,
    },
    {
        "name": "query_evidence",
        "description": "Search sanitized evidence rows with FTS/fallback query.",
        "input_schema": {"type": "object", "properties": {"query": {"type": "string"}, "limit": {"type": "integer", "minimum": 1, "maximum": MAX_LIMIT}}, "required": ["query"]},
        "safe": True,
        "mutates": False,
    },
    {
        "name": "capture_session",
        "description": "Store a redacted CLI-agent session summary as evidence.",
        "input_schema": {"type": "object", "properties": {"text": {"type": "string"}, "source_ref": {"type": "string"}}, "required": ["text"]},
        "safe": True,
        "mutates": True,
    },
    {
        "name": "entities_extract",
        "description": "Extract deterministic entity and relationship seeds from sanitized evidence.",
        "input_schema": {"type": "object", "properties": {"query": {"type": "string"}, "limit": {"type": "integer", "minimum": 1, "maximum": MAX_LIMIT}}},
        "safe": True,
        "mutates": True,
    },
    {
        "name": "entities_list",
        "description": "List extracted entities with evidence counts.",
        "input_schema": {"type": "object", "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": MAX_LIMIT}}},
        "safe": True,
        "mutates": False,
    },
    {
        "name": "relationships_list",
        "description": "List deterministic entity relationships.",
        "input_schema": {"type": "object", "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": MAX_LIMIT}}},
        "safe": True,
        "mutates": False,
    },
    {
        "name": "recall_create",
        "description": "Create a reproducible local recall bundle from a query.",
        "input_schema": {"type": "object", "properties": {"name": {"type": "string"}, "query": {"type": "string"}, "limit": {"type": "integer", "minimum": 1, "maximum": 100}}, "required": ["name", "query"]},
        "safe": True,
        "mutates": True,
    },
    {
        "name": "recall_list",
        "description": "List saved local recall bundles.",
        "input_schema": {"type": "object", "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 100}}},
        "safe": True,
        "mutates": False,
    },
    {
        "name": "recall_show",
        "description": "Show a saved recall bundle and its current evidence rows.",
        "input_schema": {"type": "object", "properties": {"bundle_id": {"type": "string"}}, "required": ["bundle_id"]},
        "safe": True,
        "mutates": False,
    },
]

TOOL_BY_NAME = {tool["name"]: tool for tool in TOOL_MANIFEST}
READ_ONLY_TOOLS = {tool["name"] for tool in TOOL_MANIFEST if not tool["mutates"]}
MUTATING_TOOLS = {tool["name"] for tool in TOOL_MANIFEST if tool["mutates"]}


class ToolInputError(ValueError):
    pass


def manifest() -> dict[str, Any]:
    return {"ok": True, "tool_count": len(TOOL_MANIFEST), "tools": TOOL_MANIFEST}


def parse_input(input_json: str | None, input_file: str | None = None) -> dict[str, Any]:
    if input_file:
        raw = Path(input_file).read_text(encoding="utf-8")
    else:
        raw = input_json or "{}"
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ToolInputError("tool input must be a JSON object")
    return parsed


def require_string(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ToolInputError(f"{key} must be a non-empty string")
    return value


def optional_string(payload: dict[str, Any], key: str, default: str = "") -> str:
    value = payload.get(key, default)
    if value is None:
        return default
    if not isinstance(value, str):
        raise ToolInputError(f"{key} must be a string")
    return value


def bounded_limit(payload: dict[str, Any], default: int) -> int:
    value = payload.get("limit", default)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ToolInputError("limit must be an integer")
    if value < 1 or value > MAX_LIMIT:
        raise ToolInputError(f"limit must be between 1 and {MAX_LIMIT}")
    return value


def not_initialized(name: str) -> dict[str, Any]:
    return {"ok": True, "tool": name, "not_initialized": True, "items": []}


def call_tool(root: str | Path, name: str, payload: dict[str, Any]) -> dict[str, Any]:
    if name not in TOOL_BY_NAME:
        return {"ok": False, "tool": name, "error": f"unknown tool: {name}"}


    if name == "signal_fingerprint":
        return {"ok": True, "tool": name, "fingerprint": stable_fingerprint(payload)}
    if name == "capture_signal":
        home = optional_string(payload, "home", "") or None
        repository = optional_string(payload, "repository", "") or None
        machine = optional_string(payload, "machine", "") or None
        threshold = payload.get("threshold", 2)
        if isinstance(threshold, bool) or not isinstance(threshold, int) or threshold < 1:
            raise ToolInputError("threshold must be a positive integer")
        signal_payload = {k: v for k, v in payload.items() if k not in {"home", "repository", "machine", "threshold"}}
        result = capture_signal(memory_db(home), signal_payload, repository=repository, machine=machine, threshold=threshold)
        result["tool"] = name
        return result
    if name == "signal_preflight":
        home = optional_string(payload, "home", "") or None
        repository = optional_string(payload, "repository", "") or None
        machine = optional_string(payload, "machine", "") or None
        fingerprint = optional_string(payload, "fingerprint", "") or None
        threshold = payload.get("threshold", 2)
        if isinstance(threshold, bool) or not isinstance(threshold, int) or threshold < 1:
            raise ToolInputError("threshold must be a positive integer")
        result = signals_preflight(memory_db(home), repository=repository, machine=machine, fingerprint=fingerprint, threshold=threshold)
        result["tool"] = name
        return result
    if name == "query_evidence":
        query = require_string(payload, "query")
        limit = bounded_limit(payload, 20)
        paths = resolve_paths(root)
        if not paths.db_path.exists():
            return not_initialized(name)
        rows, mode = query_evidence_with_mode(paths.db_path, query, limit=limit)
        return {"ok": True, "tool": name, "search_mode": mode, "items": rows}
    if name == "capture_session":
        text = require_string(payload, "text")
        source_ref = optional_string(payload, "source_ref", "tool:session") or "tool:session"
        paths = resolve_paths(root)
        ensure_dirs(paths)
        init_db(paths.db_path)
        record = capture_session_text(text, source_ref=source_ref)
        ids = insert_evidence(paths.db_path, [record])
        return {"ok": True, "tool": name, "evidence_ids": ids}
    if name == "entities_extract":
        query = optional_string(payload, "query")
        limit = bounded_limit(payload, 100)
        paths = resolve_paths(root)
        ensure_dirs(paths)
        init_db(paths.db_path)
        result = extract_entities(paths.db_path, query=query, limit=limit)
        result["tool"] = name
        return result
    if name == "entities_list":
        limit = bounded_limit(payload, 100)
        paths = resolve_paths(root)
        if not paths.db_path.exists():
            return not_initialized(name)
        return {"ok": True, "tool": name, "items": list_entities(paths.db_path, limit=limit)}
    if name == "relationships_list":
        limit = bounded_limit(payload, 100)
        paths = resolve_paths(root)
        if not paths.db_path.exists():
            return not_initialized(name)
        return {"ok": True, "tool": name, "items": list_relationships(paths.db_path, limit=limit)}
    if name == "recall_create":
        recall_name = require_string(payload, "name")
        query = require_string(payload, "query")
        limit = bounded_limit(payload, 20)
        paths = resolve_paths(root)
        ensure_dirs(paths)
        init_db(paths.db_path)
        result = create_bundle(paths.db_path, recall_name, query, limit=limit)
        result["tool"] = name
        return result
    if name == "recall_list":
        limit = bounded_limit(payload, 50)
        paths = resolve_paths(root)
        if not paths.db_path.exists():
            return not_initialized(name)
        return {"ok": True, "tool": name, "items": list_bundles(paths.db_path, limit=limit)}
    if name == "recall_show":
        bundle_id = require_string(payload, "bundle_id")
        paths = resolve_paths(root)
        if not paths.db_path.exists():
            return {"ok": False, "tool": name, "error": "bundle not found", "bundle_id": bundle_id}
        result = show_bundle(paths.db_path, bundle_id)
        result["tool"] = name
        return result
    return {"ok": False, "tool": name, "error": f"unknown tool: {name}"}
