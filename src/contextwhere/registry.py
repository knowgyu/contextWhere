from __future__ import annotations

import hashlib
import json
from pathlib import Path, PureWindowsPath
from typing import Any

from .config import resolve_global_home


def registry_path(home: str | Path | None = None) -> Path:
    return (Path(home) if home is not None else resolve_global_home()) / "registry.json"


def _stable_path_key(path: str | Path) -> str:
    text = str(path)
    if "\\" in text or (len(text) > 1 and text[1] == ":"):
        return str(PureWindowsPath(text)).replace("\\", "/").rstrip("/").lower()
    return str(Path(path).expanduser().resolve())


def stable_id(kind: str, path: str | Path) -> str:
    digest = hashlib.sha1(f"{kind}:{_stable_path_key(path)}".encode("utf-8")).hexdigest()[:12]
    return f"{kind}-{digest}"


def load_registry(home: str | Path | None = None) -> dict[str, Any]:
    path = registry_path(home)
    if not path.exists():
        return {"version": 1, "workspaces": {}, "repositories": {}}
    data = json.loads(path.read_text(encoding="utf-8"))
    data.setdefault("version", 1)
    data.setdefault("workspaces", {})
    data.setdefault("repositories", {})
    return data


def save_registry(data: dict[str, Any], home: str | Path | None = None) -> None:
    path = registry_path(home)
    payload = json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    if path.exists() and path.read_text(encoding="utf-8") == payload:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(payload, encoding="utf-8")
    tmp.replace(path)


def register_workspace(path: str | Path, home: str | Path | None = None) -> dict[str, Any]:
    return register("workspace", path, home=home)


def register_repository(
    path: str | Path,
    *,
    workspace: str | Path | None = None,
    home: str | Path | None = None,
) -> dict[str, Any]:
    return register("repository", path, workspace=workspace, home=home)


def register(
    kind: str,
    path: str | Path,
    *,
    workspace: str | Path | None = None,
    home: str | Path | None = None,
) -> dict[str, Any]:
    if kind not in {"workspace", "repository"}:
        raise ValueError("kind must be workspace or repository")
    root = Path(path).expanduser().resolve()
    entry = {
        "id": stable_id(kind, root),
        "kind": kind,
        "name": root.name,
        "path": str(root),
    }
    if kind == "repository" and workspace is not None:
        entry["workspace_id"] = stable_id("workspace", workspace)

    data = load_registry(home)
    bucket = "workspaces" if kind == "workspace" else "repositories"
    data[bucket][entry["id"]] = entry
    save_registry(data, home)
    return entry


def list_entries(kind: str | None = None, home: str | Path | None = None) -> list[dict[str, Any]]:
    data = load_registry(home)
    if kind == "workspace":
        entries = data["workspaces"].values()
    elif kind == "repository":
        entries = data["repositories"].values()
    elif kind is None:
        entries = [*data["workspaces"].values(), *data["repositories"].values()]
    else:
        raise ValueError("kind must be workspace, repository, or None")
    order = {"workspace": 0, "repository": 1}
    return sorted(entries, key=lambda entry: (order.get(entry["kind"], 99), entry["path"]))


def resolve(identifier: str | Path, kind: str | None = None, home: str | Path | None = None) -> dict[str, Any] | None:
    data = load_registry(home)
    buckets = []
    if kind in {None, "workspace"}:
        buckets.append(data["workspaces"])
    if kind in {None, "repository"}:
        buckets.append(data["repositories"])
    if not buckets:
        raise ValueError("kind must be workspace, repository, or None")

    target_path = None
    identifier_text = str(identifier)
    if not identifier_text.startswith(("workspace-", "repository-")):
        target_path = str(Path(identifier).expanduser().resolve())
    for bucket in buckets:
        if identifier_text in bucket:
            return bucket[identifier_text]
        if target_path:
            for entry in bucket.values():
                if entry.get("path") == target_path:
                    return entry
    return None


def missing_entries(home: str | Path | None = None) -> list[dict[str, Any]]:
    return [entry for entry in list_entries(home=home) if not Path(entry["path"]).exists()]
