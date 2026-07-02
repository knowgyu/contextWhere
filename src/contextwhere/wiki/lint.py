from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import date
from pathlib import Path
from typing import Any

REQUIRED = {"type", "status", "sensitivity", "source_count", "evidence_ids", "last_verified", "stale_after", "confidence", "related"}
CONTROL_DOCS = {"AGENTS.md"}


@dataclass
class LintIssue:
    path: str
    code: str
    message: str
    severity: str = "warning"

    def to_dict(self) -> dict:
        return asdict(self)


def parse_scalar(value: str) -> Any:
    value = value.strip()
    if value == "[]":
        return []
    if value.isdigit():
        return int(value)
    return value


def parse_frontmatter(text: str) -> tuple[dict[str, Any], bool]:
    if not text.startswith("---\n"):
        return {}, False
    end = text.find("\n---", 4)
    if end == -1:
        return {}, False
    block = text[4:end]
    fields: dict[str, Any] = {}
    current: str | None = None
    for line in block.splitlines():
        if not line.strip():
            continue
        stripped = line.strip()
        if stripped.startswith("-") and current:
            fields.setdefault(current, [])
            if not isinstance(fields[current], list):
                fields[current] = []
            fields[current].append(stripped[1:].strip())
            continue
        if ":" in line and not line.startswith(" "):
            key, value = line.split(":", 1)
            current = key.strip()
            fields[current] = parse_scalar(value)
    return fields, True


def evidence_empty(value: Any) -> bool:
    if value is None or value == "":
        return True
    if isinstance(value, list):
        return len(value) == 0
    return value == "[]"


def lint_wiki(wiki_dir: Path) -> list[LintIssue]:
    issues: list[LintIssue] = []
    index = wiki_dir / "index.md"
    index_text = index.read_text(encoding="utf-8") if index.exists() else ""
    if not index.exists():
        issues.append(LintIssue(str(index), "missing-index", "work_wiki/index.md is missing", "error"))
    today = date.today().isoformat()
    for path in sorted(wiki_dir.rglob("*.md")):
        if path.name in CONTROL_DOCS or path.name == "log.md":
            continue
        rel = path.relative_to(wiki_dir).as_posix()
        text = path.read_text(encoding="utf-8")
        fields, has_fm = parse_frontmatter(text)
        if rel == "index.md":
            continue
        if not has_fm:
            issues.append(LintIssue(rel, "missing-frontmatter", "Page is missing YAML frontmatter", "error"))
        else:
            missing = REQUIRED - set(fields)
            for key in sorted(missing):
                issues.append(LintIssue(rel, "missing-frontmatter-field", f"Missing frontmatter field: {key}"))
            if evidence_empty(fields.get("evidence_ids")):
                issues.append(LintIssue(rel, "missing-evidence", "Important page has no evidence IDs"))
            stale_after = str(fields.get("stale_after", ""))
            if stale_after and stale_after < today:
                issues.append(LintIssue(rel, "stale-page", f"Page stale_after {stale_after} is before today {today}"))
        if rel not in index_text:
            issues.append(LintIssue(rel, "missing-index-entry", "Page is not referenced from index.md"))
        if "needs_review" in text:
            issues.append(LintIssue(rel, "needs-review", "Page contains needs_review marker"))
    return issues
