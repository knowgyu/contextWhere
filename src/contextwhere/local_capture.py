from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

from .capture import capture_session_file, redact_text
from .schemas import EvidenceRecord, utc_now


def _scope(root: Path) -> str:
    return f"repo:{root.resolve().name}"


def _tenant(root: Path) -> str:
    digest = hashlib.sha1(str(root.resolve()).encode("utf-8")).hexdigest()[:8]
    return f"{_scope(root)}:{digest}"


def _meta(root: Path, source_kind: str, source_locator: str, stale_after: str | None = None) -> dict[str, str]:
    data = {
        "tenant": _tenant(root),
        "scope": _scope(root),
        "source_kind": source_kind,
        "source_locator": source_locator,
        "observed_at": utc_now(),
    }
    if stale_after:
        data["stale_after"] = stale_after
    return data


def capture_omx(root: Path, limit: int = 20) -> list[EvidenceRecord]:
    records: list[EvidenceRecord] = []
    for base in (root / ".omx" / "plans", root / ".omx" / "context"):
        if not base.exists():
            continue
        for path in sorted(base.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]:
            record = capture_session_file(path)
            record.provider = "agent-session"
            record.provenance = "capture-local-omx"
            record.metadata.update(_meta(root, "agent-session", f"file://{path.relative_to(root)}"))
            records.append(record)
    return records


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=root, text=True, capture_output=True, check=False)


def _git_unavailable(root: Path, command: str, result: subprocess.CompletedProcess[str]) -> EvidenceRecord:
    clean, omitted = redact_text((result.stderr or result.stdout or "git command failed").strip()[:500])
    return EvidenceRecord(
        provider="git",
        source_ref=command,
        kind="unavailable",
        title=f"Git capture unavailable: {command}",
        snippet=clean,
        summary=clean,
        provenance="capture-local-git",
        confidence="high",
        metadata={**_meta(root, "git", f"git:{command}"), "returncode": result.returncode},
        omitted_fields=omitted,
    )


def capture_git(root: Path, limit: int = 5) -> list[EvidenceRecord]:
    if not (root / ".git").exists():
        return []
    status_result = _git(root, "status", "--short", "--branch")
    if status_result.returncode != 0:
        return [_git_unavailable(root, "status", status_result)]
    status = status_result.stdout.strip()
    records = [EvidenceRecord(
        provider="git",
        source_ref="status",
        kind="repo-state",
        title="Git working tree status",
        snippet=status[:500],
        summary=status,
        provenance="capture-local-git",
        confidence="high",
        metadata=_meta(root, "git", "git:status"),
    )]
    log_result = _git(root, "log", f"-{max(1, limit)}", "--pretty=format:%H%x09%cI%x09%s")
    if log_result.returncode != 0:
        records.append(_git_unavailable(root, "log", log_result))
        return records
    for line in log_result.stdout.strip().splitlines():
        commit, when, subject = (line.split("\t", 2) + ["", "", ""])[:3]
        short = commit[:12]
        records.append(EvidenceRecord(
            provider="git",
            source_ref=commit,
            kind="commit",
            title=subject,
            snippet=f"{short} {subject}",
            occurred_at=when,
            provenance="capture-local-git",
            confidence="high",
            metadata=_meta(root, "git", f"git:commit:{commit}"),
        ))
    return records
