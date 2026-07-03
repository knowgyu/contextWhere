from __future__ import annotations

import sqlite3
from pathlib import Path

from . import __version__
from .config import resolve_paths
from .wiki import lint_wiki


def table_count(conn: sqlite3.Connection, table: str) -> int | None:
    try:
        row = conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()
    except sqlite3.OperationalError:
        return None
    return int(row["count"])


def latest_ingest(conn: sqlite3.Connection) -> dict | None:
    try:
        row = conn.execute("SELECT provider, command, status, created_at, details FROM ingest_log ORDER BY id DESC LIMIT 1").fetchone()
    except sqlite3.OperationalError:
        return None
    return dict(row) if row else None


def project_status(root: str | Path = ".") -> dict:
    paths = resolve_paths(root)
    db_exists = paths.db_path.exists()
    wiki_exists = paths.wiki_dir.exists()
    lint_issues = [issue.to_dict() for issue in lint_wiki(paths.wiki_dir)] if wiki_exists else []
    lint_error_count = sum(1 for issue in lint_issues if issue["severity"] == "error")
    counts: dict[str, int | None] = {
        "evidence": 0,
        "ingest_log": 0,
        "entities": 0,
        "relationships": 0,
        "recall_bundles": 0,
    }
    latest = None
    if db_exists:
        conn = sqlite3.connect(paths.db_path)
        conn.row_factory = sqlite3.Row
        try:
            for table in counts:
                counts[table] = table_count(conn, table)
            latest = latest_ingest(conn)
        finally:
            conn.close()
    backup_dir = paths.data_dir / "backups"
    backup_count = len([p for p in backup_dir.glob("*.zip") if p.is_file()]) if backup_dir.exists() else 0
    ok = db_exists and wiki_exists and lint_error_count == 0
    return {
        "ok": ok,
        "version": __version__,
        "root": str(paths.root),
        "db_path": str(paths.db_path),
        "db_exists": db_exists,
        "wiki_dir": str(paths.wiki_dir),
        "wiki_exists": wiki_exists,
        "counts": counts,
        "backup_count": backup_count,
        "latest_ingest": latest,
        "lint_error_count": lint_error_count,
        "lint_warning_count": sum(1 for issue in lint_issues if issue["severity"] == "warning"),
        "lint_issues": lint_issues[:10],
    }
