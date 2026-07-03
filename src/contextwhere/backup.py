from __future__ import annotations

import json
import shutil
import zipfile
from pathlib import Path

from .config import resolve_paths
from .schemas import utc_now

BACKUP_MANIFEST = "contextwhere-backup-manifest.json"
INCLUDE_DIRS = ["work_wiki", ".contextwhere"]
EXCLUDE_DIRS = [".contextwhere/backups"]


def is_excluded(path: Path, root: Path) -> bool:
    rel = path.relative_to(root).as_posix()
    return any(rel == excluded or rel.startswith(f"{excluded}/") for excluded in EXCLUDE_DIRS)


def safe_arcname(path: Path, root: Path) -> str:
    rel = path.relative_to(root).as_posix()
    if rel.startswith("../") or rel.startswith("/") or ".." in Path(rel).parts:
        raise ValueError(f"unsafe backup path: {rel}")
    return rel


def create_backup(root: str | Path, output: str | Path) -> dict:
    paths = resolve_paths(root)
    out = Path(output).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    included: list[str] = []
    manifest = {
        "format": "contextwhere-backup-v1",
        "created_at": utc_now(),
        "root_name": paths.root.name,
        "included_roots": INCLUDE_DIRS,
        "excluded_roots": EXCLUDE_DIRS,
    }
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(BACKUP_MANIFEST, json.dumps(manifest, indent=2, ensure_ascii=False))
        for rel_dir in INCLUDE_DIRS:
            base = paths.root / rel_dir
            if not base.exists():
                continue
            for file in sorted(base.rglob("*")):
                if not file.is_file() or is_excluded(file, paths.root) or file.resolve() == out:
                    continue
                arc = safe_arcname(file, paths.root)
                zf.write(file, arc)
                included.append(arc)
    return {"ok": True, "backup_path": str(out), "included_count": len(included), "included": included}


def validate_member(name: str) -> None:
    if not name:
        raise ValueError("empty archive member")
    path = Path(name)
    if name.startswith("/") or ".." in path.parts or name == BACKUP_MANIFEST:
        if name == BACKUP_MANIFEST:
            return
        raise ValueError(f"unsafe archive member: {name}")
    if not (name.startswith("work_wiki/") or name.startswith(".contextwhere/")):
        raise ValueError(f"unsupported archive member: {name}")


def restore_backup(backup: str | Path, target_root: str | Path) -> dict:
    archive = Path(backup).resolve()
    target = Path(target_root).resolve()
    if target.exists() and any(target.iterdir()):
        return {"ok": False, "error": "target root must be empty or absent", "target_root": str(target)}
    restored: list[str] = []
    with zipfile.ZipFile(archive, "r") as zf:
        names = zf.namelist()
        if BACKUP_MANIFEST not in names:
            return {"ok": False, "error": "missing backup manifest"}
        manifest = json.loads(zf.read(BACKUP_MANIFEST).decode("utf-8"))
        if manifest.get("format") != "contextwhere-backup-v1":
            return {"ok": False, "error": "unsupported backup format"}
        for name in names:
            validate_member(name)
        target.mkdir(parents=True, exist_ok=True)
        for name in names:
            if name == BACKUP_MANIFEST or name.endswith("/"):
                continue
            dest = target / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(name) as src, dest.open("wb") as dst:
                shutil.copyfileobj(src, dst)
            restored.append(name)
    return {"ok": True, "target_root": str(target), "restored_count": len(restored), "restored": restored}
