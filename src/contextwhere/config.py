from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Paths:
    root: Path
    data_dir: Path
    db_path: Path
    wiki_dir: Path
    draft_dir: Path
    audit_dir: Path


def resolve_paths(root: str | Path = ".") -> Paths:
    root_path = Path(root).resolve()
    state = root_path / ".contextwhere"
    return Paths(
        root=root_path,
        data_dir=state,
        db_path=state / "contextwhere.sqlite3",
        wiki_dir=root_path / "work_wiki",
        draft_dir=state / "drafts" / "wiki",
        audit_dir=state / "audit" / "wiki",
    )


def ensure_dirs(paths: Paths) -> None:
    paths.data_dir.mkdir(parents=True, exist_ok=True)
    paths.draft_dir.mkdir(parents=True, exist_ok=True)
    paths.audit_dir.mkdir(parents=True, exist_ok=True)
