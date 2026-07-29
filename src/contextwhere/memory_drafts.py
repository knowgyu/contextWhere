from __future__ import annotations

import hashlib
import json
import re
import uuid
from pathlib import Path
from typing import Any

from . import memory
from .cards import safety_messages
from .schemas import utc_now

DRAFT_TYPE = "memory-doc-ops-v1"
TERMINAL_CARD_STATUSES = {"stale", "superseded", "rejected"}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else ""


def _slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip()).strip("-._")
    return slug[:80] or "default"


def _scope(card: dict[str, Any]) -> dict[str, str]:
    scope = card.get("scope") or {}
    if isinstance(scope, dict):
        return {"type": str(scope.get("type") or ""), "key": str(scope.get("key") or "")}
    text = str(scope)
    if ":" in text:
        scope_type, scope_key = text.split(":", 1)
        return {"type": scope_type, "key": scope_key}
    return {"type": text, "key": "default" if text == "global" else ""}


def _card_type(card: dict[str, Any]) -> str:
    return str(card.get("type") or card.get("card_type") or "")


def _existing_workspace_doc(root: Path) -> tuple[str, Path] | None:
    for rel in ("WORKSPACE.md", "../WORKSPACE.md"):
        path = (root / rel).resolve()
        try:
            path.relative_to(root.resolve().parent)
        except ValueError:
            continue
        if path.exists():
            return rel, path
    return None


def route_card(card: dict[str, Any], *, root: Path, home: Path) -> dict[str, str]:
    scope = _scope(card)
    card_type = _card_type(card)
    if scope["type"] == "repository":
        for locator in card.get("source_locators") or []:
            rel = str(locator).replace("\\", "/")
            if not rel.startswith("/") and ".." not in Path(rel).parts and rel.endswith(".md") and (root / rel).exists():
                return {"base": "repository", "rel": rel, "path": str(root / rel)}
        if card_type in {"procedure/runbook", "procedure", "runbook"}:
            rel = "docs/OPERATIONS.md"
        elif card_type in {"decision/ADR", "decision", "adr"}:
            rel = "docs/DESIGN.md"
        else:
            rel = "AGENTS.md" if (root / "AGENTS.md").exists() else "work_wiki/AGENTS.md"
        return {"base": "repository", "rel": rel, "path": str(root / rel)}
    if scope["type"] == "workspace":
        existing = _existing_workspace_doc(root)
        if existing:
            rel, path = existing
            return {"base": "workspace", "rel": rel, "path": str(path)}
        rel = f"memory/workspace-{_slug(scope['key'])}.md"
        return {"base": "global_home", "rel": rel, "path": str(home / rel)}
    rel = f"memory/{_slug(scope['type'] or 'global')}-{_slug(scope['key'] or 'default')}.md"
    return {"base": "global_home", "rel": rel, "path": str(home / rel)}


def _target_path(target: dict[str, str], *, root: Path, home: Path) -> Path:
    rel = str(target.get("rel") or "")
    base = str(target.get("base") or "")
    if rel.startswith("/"):
        raise ValueError("unsafe target")
    if base == "repository":
        if ".." in Path(rel).parts or not rel.endswith(".md"):
            raise ValueError("unsafe target")
        path = (root / rel).resolve()
        path.relative_to(root.resolve())
        return path
    if base == "workspace":
        path = Path(str(target.get("path") or "")).expanduser().resolve()
        path.relative_to(root.resolve().parent)
        if path.name != "WORKSPACE.md":
            raise ValueError("unsafe target")
        return path
    if base == "global_home":
        path = (home / rel).resolve()
        path.relative_to(home.resolve())
        if not rel.startswith("memory/") or path.suffix != ".md":
            raise ValueError("unsafe target")
        return path
    raise ValueError("unsafe target")


def _public_target(target: dict[str, str]) -> str:
    return target["rel"] if target.get("base") == "repository" else target["path"]


def _target_from_draft(draft: dict[str, Any], *, root: Path, home: Path) -> tuple[dict[str, str], Path]:
    info = draft.get("target_info")
    if not isinstance(info, dict):
        raise ValueError("unsafe target")
    return info, _target_path(info, root=root, home=home)


def _typed_content(card: dict[str, Any]) -> dict[str, Any]:
    card_type = _card_type(card)
    content: dict[str, Any] = {"type": card_type, "summary": card.get("summary", "")}
    for key in ("rule", "rationale", "steps", "preconditions", "success_checks", "decision", "drivers", "alternatives", "failure_fingerprint", "lesson", "resolution"):
        value = card.get(key)
        if value:
            content[key] = value
    return content


def render_card_section(card: dict[str, Any]) -> str:
    content = _typed_content(card)
    lines = [f"### {card['card_id']} — {content['summary']}", "", f"- Scope: {_scope(card)['type']}:{_scope(card)['key']}", f"- Type: {content['type']}", f"- Evidence: {', '.join(card.get('evidence_ids') or card.get('evidence') or [])}"]
    if card.get("source_locators"):
        lines.append(f"- Sources: {', '.join(card['source_locators'])}")
    for key in ("rule", "rationale", "decision", "lesson", "resolution", "failure_fingerprint"):
        if content.get(key):
            lines += ["", f"**{key.replace('_', ' ').title()}**", "", str(content[key])]
    for key in ("steps", "preconditions", "success_checks", "drivers", "alternatives"):
        if content.get(key):
            lines += ["", f"**{key.replace('_', ' ').title()}**"]
            lines += [f"- {item}" for item in content[key]]
    return "\n".join(lines).rstrip() + "\n"


def create_memory_draft(db_path: Path, *, card_id: str, root: Path, home: Path, draft_dir: Path | None = None, supersede: list[str] | None = None) -> Path:
    card = memory.get_card(db_path, card_id)
    if not card:
        raise KeyError(card_id)
    if card.get("status") in TERMINAL_CARD_STATUSES:
        raise ValueError(f"card status not applyable: {card.get('status')}")
    target = route_card(card, root=root, home=home)
    target_path = _target_path(target, root=root, home=home)
    evidence_ids = sorted(str(x) for x in (card.get("evidence_ids") or card.get("evidence") or []))
    source_locators = sorted(str(x) for x in (card.get("source_locators") or []))
    section = render_card_section(card)
    public_target = _public_target(target)
    operation = {"op": "append_card_section", "card_id": card_id, "target": public_target, "content": _typed_content(card), "text": section}
    supersedes = sorted(set(str(x) for x in (supersede or card.get("supersedes") or []) if str(x)))
    if supersedes:
        operation["supersedes"] = supersedes
    draft = {
        "draft_id": str(uuid.uuid4()),
        "draft_type": DRAFT_TYPE,
        "created_at": utc_now(),
        "created_by": "contextwhere-cli",
        "status": "draft",
        "source_card_id": card_id,
        "card_id": card_id,
        "card_status": card.get("status"),
        "scope": _scope(card),
        "target_scope": _scope(card),
        "owner": {"base": target["base"], "scope": _scope(card)},
        "target": public_target,
        "target_info": target,
        "before_hash": sha(target_path),
        "evidence_ids": evidence_ids,
        "source_locators": source_locators,
        "freshness_checks": card.get("freshness") or {},
        "operations": [operation],
        "refused_reasons": [],
        "note": "memory drafts are not applied automatically",
    }
    out_dir = draft_dir or home / "drafts" / "memory"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{draft['draft_id']}.json"
    path.write_text(json.dumps(draft, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def _audit(audit_dir: Path, audit: dict[str, Any]) -> Path:
    audit_dir.mkdir(parents=True, exist_ok=True)
    path = audit_dir / f"{audit['audit_id']}.json"
    path.write_text(json.dumps(audit, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def _reject(audit_dir: Path, *, command: str, reasons: list[str], draft: dict[str, Any] | None = None) -> Path:
    return _audit(audit_dir, {"audit_id": str(uuid.uuid4()), "command": command, "created_at": utc_now(), "status": "rejected", "source_card_id": (draft or {}).get("source_card_id") or (draft or {}).get("card_id"), "card_id": (draft or {}).get("card_id"), "target": (draft or {}).get("target"), "before_hash": (draft or {}).get("before_hash", ""), "after_hash": "", "evidence_ids": (draft or {}).get("evidence_ids", []), "source_locators": (draft or {}).get("source_locators", []), "refused_reasons": sorted(set(reasons))})


def apply_memory_draft(draft_path: Path, *, db_path: Path, root: Path, home: Path, audit_dir: Path | None = None) -> Path:
    out_audit_dir = audit_dir or home / "audit" / "memory"
    try:
        draft = json.loads(draft_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return _reject(out_audit_dir, command="memory apply", reasons=[f"invalid draft JSON: {type(exc).__name__}"])

    refused = list(draft.get("refused_reasons") or [])
    if draft.get("draft_type") != DRAFT_TYPE or draft.get("created_by") != "contextwhere-cli":
        refused.append("untrusted draft")
    operations = draft.get("operations") or []
    if len(operations) != 1 or operations[0].get("op") != "append_card_section":
        refused.append("unsupported operations")

    card = memory.get_card(db_path, str(draft.get("card_id") or ""))
    expected_target_info: dict[str, str] | None = None
    if not card:
        refused.append("card not found")
    else:
        if card.get("status") in TERMINAL_CARD_STATUSES:
            refused.append(f"card status not applyable: {card.get('status')}")
        if _scope(card) != draft.get("scope"):
            refused.append("scope mismatch")
        if sorted(card.get("evidence_ids") or card.get("evidence") or []) != sorted(draft.get("evidence_ids") or []):
            refused.append("evidence_ids source mismatch")
        if sorted(card.get("source_locators") or []) != sorted(draft.get("source_locators") or []):
            refused.append("source_locators source mismatch")
        stale_after = (card.get("freshness") or {}).get("stale_after")
        if stale_after and stale_after < utc_now():
            refused.append("freshness stale")
        for message in safety_messages(card):
            refused.append(message)
        try:
            expected_target_info = route_card(card, root=root, home=home)
        except (OSError, ValueError):
            refused.append("unsafe target")

    target = draft.get("target_info") or draft.get("target") or {}
    try:
        target_info, target_path = _target_from_draft(draft, root=root, home=home)
        target = _public_target(target_info)
        if expected_target_info is None or target_info != expected_target_info:
            refused.append("target source mismatch")
            if expected_target_info is not None:
                target_path = _target_path(expected_target_info, root=root, home=home)
                target = _public_target(expected_target_info)
    except (OSError, ValueError):
        target_path = home / "unsafe-target"
        refused.append("unsafe target")
    if sha(target_path) != str(draft.get("before_hash") or ""):
        refused.append("before_hash mismatch")

    before = target_path.read_text(encoding="utf-8") if target_path.exists() else ""
    after = before
    if card and operations:
        op = operations[0]
        text = op.get("text")
        trusted_text = render_card_section(card)
        if op.get("card_id") != card.get("card_id") or op.get("target") != target or op.get("content") != _typed_content(card) or text != trusted_text:
            refused.append("operation source mismatch")
        marker = f"<!-- contextwhere:memory-card {card['card_id']} -->"
        block = f"{marker}\n{trusted_text}<!-- /contextwhere:memory-card {card['card_id']} -->\n"
        if marker not in before:
            after = before.rstrip() + ("\n\n" if before.strip() else "") + "## contextWhere memory\n\n" + block

    supersedes = sorted(set(str(x) for op in operations for x in (op.get("supersedes") or [])))
    for old_id in supersedes:
        old = memory.get_card(db_path, old_id)
        if not old:
            refused.append(f"supersede card not found: {old_id}")
        elif old.get("status") == "rejected" or (old.get("status") == "superseded" and old.get("superseded_by") != draft.get("card_id")):
            refused.append(f"supersede card not applyable: {old_id}")

    status = "rejected" if refused else "applied"
    after_hash = ""
    if status == "applied":
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(after if after.endswith("\n") else after + "\n", encoding="utf-8")
        after_hash = sha(target_path)
        for old_id in supersedes:
            old = memory.get_card(db_path, old_id)
            if old and old.get("status") != "superseded":
                memory.transition_card(db_path, old_id, "superseded", reason=f"memory draft {draft.get('draft_id')}", actor="contextwhere-cli")
    audit = {"audit_id": str(uuid.uuid4()), "command": "memory apply", "created_at": utc_now(), "status": status, "source_card_id": draft.get("source_card_id") or draft.get("card_id"), "card_id": draft.get("card_id"), "target": target, "before_hash": draft.get("before_hash", ""), "after_hash": after_hash, "evidence_ids": draft.get("evidence_ids", []), "source_locators": draft.get("source_locators", []), "supersedes": supersedes, "refused_reasons": sorted(set(refused))}
    return _audit(out_audit_dir, audit)
