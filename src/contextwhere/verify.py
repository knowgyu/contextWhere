from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Callable

from .config import resolve_paths
from .db import init_db, insert_evidence, query_evidence_with_mode
from .schemas import evidence_from_item
from .wiki import apply_wiki_draft, create_wiki_draft, lint_wiki
from .capture import capture_session_text
from .entities import extract_entities, list_entities


@dataclass
class VerifyStep:
    name: str
    ok: bool
    detail: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def write_minimal_wiki(root: Path) -> None:
    wiki = root / "work_wiki"
    (wiki / "projects").mkdir(parents=True, exist_ok=True)
    (wiki / "index.md").write_text(
        "# contextWhere Wiki Index\n\n## Project docs\n\n- `projects/contextwhere.md` — contextWhere project overview.\n",
        encoding="utf-8",
    )
    (wiki / "log.md").write_text("# contextWhere Wiki Log\n", encoding="utf-8")
    (wiki / "projects" / "contextwhere.md").write_text(
        "---\n"
        "type: project\nstatus: active\nsensitivity: internal\nsource_count: 1\n"
        "evidence_ids:\n  - verify:fixture\nlast_verified: 2026-07-03\nstale_after: 2099-01-01\n"
        "confidence: high\nrelated: []\n---\n\n# contextWhere\n",
        encoding="utf-8",
    )


def sample_record() -> dict:
    return {
        "kind": "task",
        "id": "verify-task-1",
        "title": "Verify contextWhere installation",
        "reason": "Smoke test should exercise evidence, query, wiki draft/apply, lint, and capture-session.",
        "source_received_at": "2026-07-03T00:00:00+09:00",
        "raw_body": "SECRET RAW BODY SHOULD NOT PERSIST",
        "full_addresses": ["secret@example.com"],
        "prompt_logs": "SECRET PROMPT SHOULD NOT PERSIST",
    }


def run_step(steps: list[VerifyStep], name: str, fn: Callable[[], str]) -> None:
    try:
        detail = fn()
    except Exception as exc:  # pragma: no cover - surfaced in CLI output
        steps.append(VerifyStep(name=name, ok=False, detail=f"{type(exc).__name__}: {exc}"))
    else:
        steps.append(VerifyStep(name=name, ok=True, detail=detail))


def run_verify(root: Path | None = None, keep: bool = False) -> dict:
    temp_dir: tempfile.TemporaryDirectory[str] | None = None
    if root is None and keep:
        work_root = Path(tempfile.mkdtemp(prefix="contextwhere-verify-"))
    elif root is None:
        temp_dir = tempfile.TemporaryDirectory(prefix="contextwhere-verify-")
        work_root = Path(temp_dir.name)
    else:
        parent = root.resolve()
        parent.mkdir(parents=True, exist_ok=True)
        work_root = Path(tempfile.mkdtemp(prefix="contextwhere-verify-", dir=parent))
    steps: list[VerifyStep] = []

    def init_step() -> str:
        write_minimal_wiki(work_root)
        paths = resolve_paths(work_root)
        init_db(paths.db_path)
        return str(paths.db_path)

    def ingest_step() -> str:
        paths = resolve_paths(work_root)
        ids = insert_evidence(paths.db_path, [evidence_from_item("verify", sample_record(), "task")])
        if not ids:
            raise RuntimeError("no evidence inserted")
        return ids[0]

    def query_step() -> str:
        paths = resolve_paths(work_root)
        rows, mode = query_evidence_with_mode(paths.db_path, "contextWhere", limit=5)
        if not rows:
            raise RuntimeError("query returned no rows")
        return mode

    def wiki_step() -> str:
        paths = resolve_paths(work_root)
        draft = create_wiki_draft(paths.db_path, paths.wiki_dir, paths.draft_dir, query="contextWhere", limit=5)
        audit = apply_wiki_draft(draft, paths.root, paths.audit_dir, db_path=paths.db_path)
        audit_data = json.loads(audit.read_text(encoding="utf-8"))
        if audit_data.get("status") != "applied":
            raise RuntimeError(f"wiki apply rejected: {audit_data.get('refused_reasons')}")
        return str(audit)

    def lint_step() -> str:
        paths = resolve_paths(work_root)
        issues = [issue.to_dict() for issue in lint_wiki(paths.wiki_dir)]
        errors = [issue for issue in issues if issue.get("severity") == "error"]
        if errors:
            raise RuntimeError(f"lint errors: {errors}")
        return f"{len(issues)} issue(s)"

    def entities_step() -> str:
        paths = resolve_paths(work_root)
        result = extract_entities(paths.db_path, query="contextWhere", limit=10)
        entities = list_entities(paths.db_path, limit=10)
        if not entities:
            raise RuntimeError(f"no entities extracted: {result}")
        return str(len(entities))

    def capture_step() -> str:
        paths = resolve_paths(work_root)
        record = capture_session_text("Goal: verify contextWhere\nVerification: pytest-style smoke\n", "verify:session")
        ids = insert_evidence(paths.db_path, [record])
        if not ids:
            raise RuntimeError("capture evidence not inserted")
        return ids[0]

    try:
        for name, fn in [
            ("init", init_step),
            ("ingest", ingest_step),
            ("query", query_step),
            ("wiki-draft-apply", wiki_step),
            ("lint", lint_step),
            ("entities-extract", entities_step),
            ("capture-session", capture_step),
        ]:
            run_step(steps, name, fn)
            if not steps[-1].ok:
                break
        return {
            "ok": all(step.ok for step in steps),
            "root": str(work_root),
            "kept": bool(root is not None or keep),
            "steps": [step.to_dict() for step in steps],
        }
    finally:
        if temp_dir is not None:
            temp_dir.cleanup()
