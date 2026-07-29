from __future__ import annotations

import json
from pathlib import Path

from contextwhere import memory
from contextwhere.memory_drafts import apply_memory_draft, create_memory_draft


def card(**overrides):
    data = {
        "card_id": "proc-1",
        "version": "v1",
        "type": "procedure/runbook",
        "summary": "Run verify before release.",
        "scope": {"type": "repository", "key": "repo-a"},
        "status": "active",
        "sensitivity": "internal",
        "evidence": ["manual:test"],
        "source_locators": ["file:README.md"],
        "verification": {"verified_at": "2026-07-29T00:00:00+00:00", "method": "pytest", "ok": True},
        "freshness": {"observed_at": "2026-07-29T00:00:00+00:00", "stale_after": "2099-01-01T00:00:00+00:00"},
        "steps": ["python -m contextwhere verify --json"],
        "success_checks": ["ok true"],
    }
    data.update(overrides)
    return data


def test_repository_procedure_draft_applies_explicitly_with_before_hash(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    (root / "docs").mkdir()
    target = root / "docs" / "OPERATIONS.md"
    target.write_text("# Ops\n", encoding="utf-8")
    home = tmp_path / "home" / ".contextwhere"
    db_path = home / "contextwhere.sqlite3"
    memory.upsert_card(db_path, card(), actor="pytest")

    draft_path = create_memory_draft(db_path, card_id="proc-1", root=root, home=home)
    draft = json.loads(draft_path.read_text(encoding="utf-8"))

    assert draft["target_info"]["base"] == "repository"
    assert draft["target"] == "docs/OPERATIONS.md"
    assert draft["before_hash"]
    assert draft["evidence_ids"] == ["manual:test"]
    assert draft["source_locators"] == ["file:README.md"]
    assert target.read_text(encoding="utf-8") == "# Ops\n"

    audit_path = apply_memory_draft(draft_path, db_path=db_path, root=root, home=home)
    audit = json.loads(audit_path.read_text(encoding="utf-8"))

    assert audit["status"] == "applied"
    assert "proc-1" in target.read_text(encoding="utf-8")


def test_memory_apply_rejects_stale_target_and_source_mismatch(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    (root / "docs").mkdir()
    target = root / "docs" / "OPERATIONS.md"
    target.write_text("# Ops\n", encoding="utf-8")
    home = tmp_path / "home" / ".contextwhere"
    db_path = home / "contextwhere.sqlite3"
    memory.upsert_card(db_path, card(), actor="pytest")
    draft_path = create_memory_draft(db_path, card_id="proc-1", root=root, home=home)

    target.write_text("# Ops\nchanged\n", encoding="utf-8")
    audit = json.loads(apply_memory_draft(draft_path, db_path=db_path, root=root, home=home).read_text(encoding="utf-8"))
    assert audit["status"] == "rejected"
    assert "before_hash mismatch" in audit["refused_reasons"]

    target.write_text("# Ops\n", encoding="utf-8")
    memory.upsert_card(db_path, card(evidence=["manual:changed"]), actor="pytest")
    audit = json.loads(apply_memory_draft(draft_path, db_path=db_path, root=root, home=home).read_text(encoding="utf-8"))
    assert audit["status"] == "rejected"
    assert "evidence_ids source mismatch" in audit["refused_reasons"]


def test_workspace_and_global_cards_route_to_workspace_or_global_home(tmp_path: Path) -> None:
    root = tmp_path / "workspace" / "repo"
    root.mkdir(parents=True)
    workspace_doc = tmp_path / "workspace" / "WORKSPACE.md"
    workspace_doc.write_text("# Workspace\n", encoding="utf-8")
    home = tmp_path / "home" / ".contextwhere"
    db_path = home / "contextwhere.sqlite3"
    memory.upsert_card(db_path, card(card_id="workspace-1", type="constraint/preference", scope={"type": "workspace", "key": "ws-a"}, rule="Share repo routing."), actor="pytest")
    memory.upsert_card(db_path, card(card_id="machine-1", type="machine", scope={"type": "machine", "key": "host-a"}, rule="Local-only."), actor="pytest")

    workspace_draft = json.loads(create_memory_draft(db_path, card_id="workspace-1", root=root, home=home).read_text(encoding="utf-8"))
    machine_draft = json.loads(create_memory_draft(db_path, card_id="machine-1", root=root, home=home).read_text(encoding="utf-8"))

    assert workspace_draft["target_info"]["base"] == "workspace"
    assert workspace_draft["target"] == str(workspace_doc)
    assert machine_draft["target_info"] == {"base": "global_home", "rel": "memory/machine-host-a.md", "path": str(home / "memory" / "machine-host-a.md")}
