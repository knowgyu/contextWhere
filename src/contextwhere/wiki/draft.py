from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import Path

from contextwhere.db import connect
from contextwhere.schemas import utc_now

SAFE_DRAFT_TYPE = "wiki-ops-v1"
SAFE_TARGETS = {"work_wiki/index.md", "work_wiki/log.md"}
SAFE_OPS = {"append_index_entry", "append_log_entry"}


def sha(path: Path) -> str:
    if not path.exists():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def evidence_rows(db_path: Path, query: str = "", limit: int = 10) -> list[dict]:
    from contextwhere.db import query_evidence

    return query_evidence(db_path, query, limit=limit)


def evidence_lookup(db_path: Path, evidence_ids: list[str]) -> dict[str, dict]:
    if not evidence_ids:
        return {}
    placeholders = ",".join("?" for _ in evidence_ids)
    with connect(db_path) as conn:
        rows = conn.execute(f"SELECT * FROM evidence WHERE evidence_id IN ({placeholders})", evidence_ids).fetchall()
    return {row["evidence_id"]: dict(row) for row in rows}


def evidence_exists(db_path: Path, evidence_id: str) -> bool:
    return evidence_id in evidence_lookup(db_path, [evidence_id])


def render_index_entry(evidence_id: str, title: str) -> str:
    safe_title = " ".join(str(title).split())[:200]
    return f"- evidence:{evidence_id} — {safe_title}"


def create_wiki_draft(db_path: Path, wiki_dir: Path, draft_dir: Path, query: str = "", limit: int = 10) -> Path:
    draft_dir.mkdir(parents=True, exist_ok=True)
    rows = evidence_rows(db_path, query, limit=limit)
    index = wiki_dir / "index.md"
    index_text = index.read_text(encoding="utf-8") if index.exists() else "# contextWhere Wiki Index\n"
    ops = []
    for row in rows:
        line = render_index_entry(row["evidence_id"], row["title"] or row["source_ref"])
        if line not in index_text:
            ops.append({
                "op": "append_index_entry",
                "target": "work_wiki/index.md",
                "evidence_id": row["evidence_id"],
                "title": row["title"] or row["source_ref"],
            })
    draft = {
        "draft_id": str(uuid.uuid4()),
        "draft_type": SAFE_DRAFT_TYPE,
        "created_by": "contextwhere wiki draft",
        "created_at": utc_now(),
        "status": "draft",
        "policy_reason": "typed metadata-only wiki maintenance operations",
        "evidence_ids": [row["evidence_id"] for row in rows],
        "target_files": sorted({op["target"] for op in ops} or {"work_wiki/index.md"}),
        "before_hashes": {"work_wiki/index.md": sha(index)},
        "operations": ops,
        # Legacy field intentionally empty; apply recomputes content from operations.
        "after_content": {},
        "patch": "",
        "refused_reasons": [],
    }
    path = draft_dir / f"{draft['draft_id']}.json"
    path.write_text(json.dumps(draft, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def apply_operations(draft: dict, root: Path, evidence_by_id: dict[str, dict] | None = None) -> tuple[dict[str, str], list[str]]:
    outputs: dict[str, str] = {}
    refused: list[str] = []
    evidence_by_id = evidence_by_id or {}
    grouped: dict[str, list[dict]] = {}
    for op in draft.get("operations") or []:
        name = op.get("op")
        target = op.get("target")
        if name not in SAFE_OPS:
            refused.append(f"unsupported operation: {name}")
            continue
        if target not in SAFE_TARGETS:
            refused.append(f"unsupported target: {target}")
            continue
        grouped.setdefault(target, []).append(op)
    for target, ops in grouped.items():
        path = root / target
        current = path.read_text(encoding="utf-8") if path.exists() else ""
        text = current.rstrip()
        additions: list[str] = []
        if target == "work_wiki/index.md":
            for op in ops:
                if op.get("op") != "append_index_entry":
                    refused.append(f"operation {op.get('op')} not allowed for {target}")
                    continue
                evidence_id = str(op.get("evidence_id", ""))
                evidence = evidence_by_id.get(evidence_id)
                if not evidence:
                    refused.append(f"missing canonical evidence for {evidence_id}")
                    continue
                line = render_index_entry(evidence_id, str(evidence.get("title") or evidence.get("source_ref") or evidence_id))
                if line and line not in current and line not in additions:
                    additions.append(line)
            if additions:
                text += "\n\n## Evidence draft candidates\n\n" + "\n".join(additions)
        elif target == "work_wiki/log.md":
            for op in ops:
                if op.get("op") != "append_log_entry":
                    refused.append(f"operation {op.get('op')} not allowed for {target}")
                    continue
                evidence_id = str(op.get("evidence_id", ""))
                evidence = evidence_by_id.get(evidence_id)
                if not evidence:
                    refused.append(f"missing canonical evidence for {evidence_id}")
                    continue
                title = " ".join(str(evidence.get("title") or evidence.get("source_ref") or evidence_id).split())[:200]
                additions.append(f"- {utc_now()} evidence:{evidence_id} — {title}")
            if additions:
                text += "\n" + "\n".join(additions)
        outputs[target] = text + ("\n" if text else "")
    return outputs, refused


def validate_draft(draft: dict, root: Path, db_path: Path | None = None) -> tuple[list[str], dict[str, str]]:
    refused: list[str] = list(draft.get("refused_reasons") or [])
    if draft.get("draft_type") != SAFE_DRAFT_TYPE or draft.get("created_by") != "contextwhere wiki draft":
        refused.append("untrusted or unsupported draft provenance")
    if draft.get("after_content"):
        refused.append("after_content is not accepted; apply recomputes content from typed operations")
    operations = draft.get("operations") or []
    if not operations:
        refused.append("missing operations")
    target_files = sorted({op.get("target") for op in operations if op.get("target")})
    declared_targets = sorted(draft.get("target_files") or [])
    if declared_targets != target_files:
        refused.append("target_files do not match operations")
    before_hashes = draft.get("before_hashes") or {}
    for rel in target_files:
        if rel not in SAFE_TARGETS:
            refused.append("0.1.0 apply only supports deterministic index/log maintenance")
            continue
        current_hash = sha(root / rel)
        expected = before_hashes.get(rel, "")
        if current_hash != expected:
            refused.append(f"before_hash mismatch for {rel}")
    evidence_ids = sorted({str(op.get("evidence_id", "")) for op in operations if op.get("evidence_id")})
    if not evidence_ids:
        refused.append("missing evidence_ids")
    declared_evidence_ids = sorted(str(eid) for eid in (draft.get("evidence_ids") or []))
    if declared_evidence_ids != evidence_ids:
        refused.append("evidence_ids do not match operations")
    evidence_by_id = {}
    if db_path is not None:
        evidence_by_id = evidence_lookup(db_path, evidence_ids)
        missing = [eid for eid in evidence_ids if eid not in evidence_by_id]
        if missing:
            refused.append(f"unknown evidence_ids: {missing}")
    outputs, op_refused = apply_operations(draft, root, evidence_by_id=evidence_by_id)
    refused.extend(op_refused)
    return sorted(set(refused)), outputs


def apply_wiki_draft(draft_path: Path, root: Path, audit_dir: Path, db_path: Path | None = None) -> Path:
    audit_dir.mkdir(parents=True, exist_ok=True)
    audit_id = str(uuid.uuid4())
    try:
        draft = json.loads(draft_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        audit = {
            "audit_id": audit_id,
            "command": "wiki apply",
            "created_at": utc_now(),
            "status": "rejected",
            "policy_reason": "invalid draft input",
            "evidence_ids": [],
            "target_files": [],
            "before_hashes": {},
            "after_hashes": {},
            "patch": "",
            "rollback": {},
            "refused_reasons": [f"invalid draft JSON: {type(exc).__name__}"],
        }
        path = audit_dir / f"{audit_id}.json"
        path.write_text(json.dumps(audit, indent=2, ensure_ascii=False), encoding="utf-8")
        return path
    refused, outputs = validate_draft(draft, root, db_path=db_path)
    target_files = sorted(outputs)
    before_hashes = {}
    after_hashes = {}
    status = "rejected" if refused else "applied"
    rollback = {}
    if not refused:
        for rel, content in outputs.items():
            path = root / rel
            before_hashes[rel] = sha(path)
            rollback[rel] = path.read_text(encoding="utf-8") if path.exists() else ""
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            after_hashes[rel] = sha(path)
    audit = {
        "audit_id": audit_id,
        "command": "wiki apply",
        "created_at": utc_now(),
        "status": status,
        "policy_reason": draft.get("policy_reason", ""),
        "evidence_ids": sorted({str(op.get("evidence_id", "")) for op in draft.get("operations") or [] if op.get("evidence_id")}),
        "target_files": target_files or draft.get("target_files", []),
        "before_hashes": before_hashes or draft.get("before_hashes", {}),
        "after_hashes": after_hashes,
        "patch": draft.get("patch", ""),
        "rollback": rollback,
        "refused_reasons": refused,
    }
    path = audit_dir / f"{audit_id}.json"
    path.write_text(json.dumps(audit, indent=2, ensure_ascii=False), encoding="utf-8")
    return path
