from __future__ import annotations

import json
import os
import platform
import sqlite3
from pathlib import Path
from typing import Any

from .config import resolve_global_home
from .memory import init_memory_db, schema_signature
from .registry import load_registry, missing_entries, registry_path, save_registry
from .integrations import status as integration_status

DIRS = ("drafts", "audit", "drafts/memory", "audit/memory")
INTEGRATIONS = ("codex", "claude", "gemini")


def _platform_name() -> str:
    return os.environ.get("CONTEXTWHERE_TEST_PLATFORM") or platform.system()


def _default_home() -> Path:
    if _platform_name().lower() == "windows":
        userprofile = os.environ.get("USERPROFILE")
        if userprofile:
            return Path(userprofile).expanduser() / ".contextwhere"
    return resolve_global_home()


def _issue(code: str, message: str, *, path: Path | None = None) -> dict[str, str]:
    item = {"code": code, "message": message}
    if path is not None:
        item["path"] = str(path)
    return item


def _can_write(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True) if path.suffix == "" else path.parent.mkdir(parents=True, exist_ok=True)
        probe = path / ".contextwhere-write-test" if path.suffix == "" else path.with_suffix(path.suffix + ".write-test")
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return True
    except OSError:
        return False


def _check_permissions(paths: list[Path]) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    for path in paths:
        if path.exists() and not os.access(path, os.R_OK):
            issues.append(_issue("permission_read_failed", "Path is not readable", path=path))
        target = path if path.is_dir() or not path.suffix else path.parent
        if target.exists() and not os.access(target, os.W_OK):
            issues.append(_issue("permission_write_failed", "Path is not writable", path=target))
    return issues


def plan_home(home: str | Path | None = None) -> dict[str, Any]:
    base = Path(home).expanduser().resolve() if home else _default_home()
    db_path = base / "contextwhere.sqlite3"
    dirs = [base, *(base / item for item in DIRS)]
    return {
        "home": str(base),
        "db_path": str(db_path),
        "registry_path": str(registry_path(base)),
        "dirs": [str(path) for path in dirs],
        "platform": _platform_name(),
        **_integration_plan(base),
    }



def _integration_plan(base: Path) -> dict[str, Any]:
    state = integration_status(base)
    live = state["integrations"]
    integrations = {
        name: {**item, "command_available": item["available"], "available": item["installed"], "reason": item["reason"] if item["installed"] else "deferred"}
        for name, item in live.items()
    }
    return {
        "integrations": integrations,
        "integration_statuses": live,
        "agent_bridges": {
            "installed": any(item["installed"] for item in live.values()),
            "status": "installed" if any(item["installed"] for item in live.values()) else "not_installed",
            "integrations": list(INTEGRATIONS),
        },
    }

def setup_home(home: str | Path | None = None, *, dry_run: bool = False, install_agent_bridges: bool = False) -> dict[str, Any]:
    plan = plan_home(home)
    base = Path(plan["home"])
    db_path = Path(plan["db_path"])
    reg_path = Path(plan["registry_path"])
    actions: list[dict[str, str]] = []

    for raw in plan["dirs"]:
        path = Path(raw)
        if not path.exists():
            actions.append({"action": "create_dir", "path": str(path)})
            if not dry_run:
                path.mkdir(parents=True, exist_ok=True)

    if not db_path.exists():
        actions.append({"action": "init_db", "path": str(db_path)})
    if not dry_run:
        init_memory_db(db_path)

    if not reg_path.exists():
        actions.append({"action": "init_registry", "path": str(reg_path)})
    if not dry_run:
        save_registry(load_registry(base), home=base)

    if install_agent_bridges:
        from .integrations import install as install_agent_integrations

        bridge_result = install_agent_integrations(base, dry_run=dry_run)
        actions.extend(bridge_result.get("actions", []))

    result = doctor_home(base, mutate=False)
    if dry_run:
        result["ok"] = True
        result["status"] = "dry_run"
        result["issues"] = []
        result["checks"] = []
    idempotent = not actions
    plan = plan_home(base)
    result.update({"dry_run": dry_run, "actions": actions, "would_create": actions, "idempotent": idempotent, **plan})
    return result


def _check(code: str, ok: bool, message: str, *, path: Path | None = None, repair_hint: str = "") -> dict[str, Any]:
    item: dict[str, Any] = {"code": code, "ok": ok, "message": message, "repair_hint": repair_hint}
    if path is not None:
        item["path"] = str(path)
    return item


def doctor_home(home: str | Path | None = None, *, mutate: bool = False) -> dict[str, Any]:
    plan = plan_home(home)
    base = Path(plan["home"])
    db_path = Path(plan["db_path"])
    reg_path = Path(plan["registry_path"])
    checks: list[dict[str, Any]] = []

    for raw in plan["dirs"]:
        path = Path(raw)
        checks.append(_check("dir_exists" if path.is_dir() else "missing_dir", path.is_dir(), "Required directory exists" if path.is_dir() else "Required directory is missing", path=path, repair_hint="Run contextwhere setup --home <path>"))

    if not db_path.exists():
        checks.append(_check("db_missing", False, "Global memory database is missing", path=db_path, repair_hint="Run contextwhere setup --home <path>"))
    else:
        try:
            if mutate:
                init_memory_db(db_path)
            sig = schema_signature(db_path)
            names = {name.split(":", 1)[0] for _, name in sig}
            missing = [name for name in ("context_cards", "context_card_audit") if name not in names]
            checks.append(_check("db_schema", not missing, "Database schema is complete" if not missing else f"Database missing {', '.join(missing)}", path=db_path, repair_hint="Run contextwhere setup --home <path>"))
        except (OSError, sqlite3.Error) as exc:
            checks.append(_check("db_schema_error", False, f"Database schema check failed: {type(exc).__name__}", path=db_path, repair_hint="Restore or recreate the global database"))

    if not reg_path.exists():
        checks.append(_check("registry_missing", False, "Registry file is missing", path=reg_path, repair_hint="Run contextwhere setup --home <path>"))
    elif reg_path.is_dir():
        checks.append(_check("registry_invalid", False, "Registry cannot be read: IsADirectoryError", path=reg_path, repair_hint="Move the directory and rerun contextwhere setup"))
    else:
        try:
            load_registry(base)
            checks.append(_check("registry", True, "Registry is readable", path=reg_path))
        except json.JSONDecodeError:
            checks.append(_check("registry_invalid", False, "Registry cannot be read: JSONDecodeError", path=reg_path, repair_hint="Fix registry.json or move it aside and rerun setup"))
        except OSError:
            checks.append(_check("registry_invalid", False, "Registry cannot be read: OSError", path=reg_path, repair_hint="Fix file permissions"))
        except ValueError:
            checks.append(_check("registry_invalid", False, "Registry cannot be read: ValueError", path=reg_path, repair_hint="Fix registry.json or move it aside and rerun setup"))

    try:
        for entry in missing_entries(base):
            checks.append(_check("registry_path_missing", False, f"Registered {entry.get('kind')} path is missing", path=Path(entry.get("path", "")), repair_hint="Re-register or remove the stale registry entry"))
    except (OSError, ValueError):
        pass

    for issue in _check_permissions([base, db_path, reg_path]):
        checks.append(_check(issue["code"], False, issue["message"], path=Path(issue.get("path", "")), repair_hint="Fix filesystem permissions"))

    for name, item in plan["integrations"].items():
        checks.append(
            _check(
                f"integration_{name}",
                True,
                f"Integration {item['status']}" + ("; agent command unavailable" if not item["available"] else ""),
                path=Path(item["instruction_path"]),
                repair_hint="Run contextwhere integrations install --agent all --home <path>",
            )
        )

    ok = all(item["ok"] for item in checks)
    issues = [{"code": item["code"], "message": item["message"], "path": item.get("path", ""), "repair_hint": item["repair_hint"]} for item in checks if not item["ok"]]
    return {**plan, "ok": ok, "status": "healthy" if ok else "unhealthy", "checks": checks, "issues": issues}
