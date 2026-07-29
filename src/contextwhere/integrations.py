from __future__ import annotations

import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any


MARKER_START = "<!-- BEGIN contextWhere agent bridge -->"
MARKER_END = "<!-- END contextWhere agent bridge -->"
OWNED_HEADER = "# contextWhere agent bridge"


@dataclass(frozen=True)
class AgentSpec:
    name: str
    command: str
    instruction_parts: tuple[str, ...]
    owned_parts: tuple[tuple[str, ...], ...]


SPECS: dict[str, AgentSpec] = {
    "codex": AgentSpec("codex", "codex", (".codex", "AGENTS.md"), ((".codex", "skills", "contextwhere-memory", "SKILL.md"),)),
    "claude": AgentSpec("claude", "claude", (".claude", "CLAUDE.md"), ((".claude", "commands", "contextwhere.md"),)),
    "gemini": AgentSpec("gemini", "gemini", (".gemini", "GEMINI.md"), ((".gemini", "commands", "contextwhere.toml"),)),
}


def default_home() -> Path:
    if os.environ.get("CONTEXTWHERE_TEST_PLATFORM", "").lower() == "windows":
        profile = os.environ.get("USERPROFILE")
        if profile:
            return Path(profile).expanduser()
    return Path.home()


def agent_home(contextwhere_home: str | Path | None = None) -> Path:
    if contextwhere_home is None:
        cw_home = default_home() / ".contextwhere"
    else:
        cw_home = Path(contextwhere_home).expanduser().resolve()
    return cw_home.parent if cw_home.name == ".contextwhere" else cw_home


def _path(home: Path, parts: tuple[str, ...]) -> Path:
    return home.joinpath(*parts)


def bridge_text() -> str:
    return (
        "<!-- BEGIN contextWhere agent bridge -->\n"
        "contextWhere advisory memory bridge: before repeated failures or uncertain repo context, run `contextwhere preflight --json`; "
        "after verified fixes or blockers, record sanitized signals with `contextwhere signals capture --json`. "
        "contextWhere code remains authority for scope, secret, and unsafe-workaround checks.\n"
        "<!-- END contextWhere agent bridge -->\n"
    )


def owned_file_text(agent: str) -> str:
    if agent == "gemini":
        return (
            'description = "Use contextWhere scoped memory"\n'
            'prompt = "Run contextwhere preflight --json for scoped memory and contextwhere signals capture --json for sanitized verified outcomes. ContextWhere enforces secret, scope, and unsafe-workaround checks."\n'
        )
    return (
        f"{OWNED_HEADER}\n\n"
        "Use `contextwhere preflight --json` for scoped memory before repeating failures.\n"
        "Use `contextwhere signals capture --json` for sanitized blockers, corrections, and verified fixes.\n"
        "ContextWhere code is the authority for secret, scope, and unsafe-workaround checks.\n"
    )


def marker_state(text: str) -> str:
    has_start = MARKER_START in text
    has_end = MARKER_END in text
    if has_start and has_end and text.index(MARKER_START) < text.index(MARKER_END):
        return "present"
    if has_start or has_end:
        return "corrupt"
    return "absent"


def _has_marker(text: str) -> bool:
    return marker_state(text) == "present"


def _with_marker(text: str) -> str:
    block = bridge_text()
    if _has_marker(text):
        before, rest = text.split(MARKER_START, 1)
        _, after = rest.split(MARKER_END, 1)
        return before.rstrip() + "\n\n" + block + after.lstrip("\n")
    return (text.rstrip() + "\n\n" if text.strip() else "") + block


def _without_marker(text: str) -> str:
    if not _has_marker(text):
        return text
    before, rest = text.split(MARKER_START, 1)
    _, after = rest.split(MARKER_END, 1)
    return (before.rstrip() + "\n" + after.lstrip("\n")).strip() + "\n" if (before + after).strip() else ""


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        Path(tmp).replace(path)
    finally:
        Path(tmp).unlink(missing_ok=True)


def _backup(path: Path) -> Path:
    backup = path.with_name(path.name + ".contextwhere.bak")
    if not backup.exists():
        _atomic_write(backup, path.read_text(encoding="utf-8"))
    return backup


def _owned_file_matches(path: Path, agent: str) -> bool:
    return path.exists() and path.read_text(encoding="utf-8") == owned_file_text(agent)


def _specs(agent: str = "all") -> list[AgentSpec]:
    if agent == "all":
        return list(SPECS.values())
    if agent not in SPECS:
        raise ValueError(f"unsupported agent: {agent}")
    return [SPECS[agent]]


def status(home: str | Path | None = None, *, agent: str = "all", doctor: bool = False) -> dict[str, Any]:
    base = agent_home(home)
    integrations: dict[str, Any] = {}
    issues: list[dict[str, str]] = []
    for spec in _specs(agent):
        instruction = _path(base, spec.instruction_parts)
        owned = [_path(base, parts) for parts in spec.owned_parts]
        command_path = shutil.which(spec.command)
        marker = False
        marker_status = "absent"
        read_error = ""
        if instruction.exists():
            if not os.access(instruction, os.R_OK):
                read_error = "permission denied reading instruction file"
            else:
                try:
                    marker_status = marker_state(instruction.read_text(encoding="utf-8"))
                    marker = marker_status == "present"
                except OSError as exc:
                    read_error = f"read failed: {type(exc).__name__}"
        owned_present = all(path.exists() for path in owned)
        try:
            owned_ok = all(_owned_file_matches(path, spec.name) for path in owned)
        except OSError:
            owned_ok = False
        installed = bool(marker and owned_ok)
        if read_error:
            item_status = "error"
            issues.append({"code": f"integration_{spec.name}_read_failed", "message": read_error, "path": str(instruction), "repair_hint": "Fix instruction-file permissions"})
        elif marker_status == "corrupt":
            item_status = "corrupt_marker"
            issues.append({"code": f"integration_{spec.name}_marker_corrupt", "message": "contextWhere marker is incomplete", "path": str(instruction), "repair_hint": "Run contextwhere integrations uninstall/install for this agent"})
        elif installed:
            item_status = "installed"
        elif instruction.exists():
            item_status = "not_installed"
        else:
            item_status = "unavailable"
        integrations[spec.name] = {
            "agent": spec.name,
            "available": command_path is not None,
            "command": spec.command,
            "command_path": command_path or "",
            "installed": installed,
            "status": item_status,
            "reason": item_status if item_status != "unavailable" else "deferred",
            "instruction_path": str(instruction),
            "marker_present": marker,
            "marker_status": marker_status,
            "owned_files": [str(path) for path in owned],
            "owned_files_present": owned_present,
            "owned_files_owned": owned_ok,
            "safe_to_continue": True,
        }
    ok = not issues
    overall = "installed" if integrations and all(item["status"] == "installed" for item in integrations.values()) else "unavailable"
    if issues:
        overall = "unhealthy"
    return {"ok": ok, "home": str(base), "status": overall, "integrations": integrations, "issues": issues}


def install(home: str | Path | None = None, *, agent: str = "all", dry_run: bool = False) -> dict[str, Any]:
    base = agent_home(home)
    actions: list[dict[str, str]] = []
    changed_files: list[str] = []
    backup_paths: list[str] = []
    issues: list[dict[str, str]] = []
    for spec in _specs(agent):
        instruction = _path(base, spec.instruction_parts)
        if instruction.exists() and not os.access(instruction, os.R_OK | os.W_OK):
            issues.append({"code": f"integration_{spec.name}_permission", "message": "permission denied reading or writing instruction file", "path": str(instruction), "repair_hint": "Fix instruction-file permissions"})
            continue
        try:
            old = instruction.read_text(encoding="utf-8") if instruction.exists() else ""
        except OSError as exc:
            issues.append({"code": f"integration_{spec.name}_read_failed", "message": f"read failed: {type(exc).__name__}", "path": str(instruction), "repair_hint": "Fix instruction-file permissions"})
            continue
        if marker_state(old) == "corrupt":
            issues.append({"code": f"integration_{spec.name}_marker_corrupt", "message": "contextWhere marker is incomplete", "path": str(instruction), "repair_hint": "Run contextwhere integrations uninstall/install for this agent"})
            continue
        conflict = False
        for owned in (_path(base, parts) for parts in spec.owned_parts):
            if not owned.exists():
                continue
            try:
                owned_old = owned.read_text(encoding="utf-8")
            except OSError as exc:
                issues.append({"code": f"integration_{spec.name}_owned_read_failed", "message": f"owned file read failed: {type(exc).__name__}", "path": str(owned), "repair_hint": "Move or fix the existing file before installing"})
                conflict = True
            else:
                if owned_old != owned_file_text(spec.name):
                    issues.append({"code": f"integration_{spec.name}_owned_file_conflict", "message": "existing owned-file path is not contextWhere-owned", "path": str(owned), "repair_hint": "Move the file or replace it with exact contextWhere content"})
                    conflict = True
        if conflict:
            continue
        new = _with_marker(old)
        if new != old:
            if instruction.exists():
                backup_path = str(instruction.with_name(instruction.name + ".contextwhere.bak"))
                backup_paths.append(backup_path)
                actions.append({"action": "backup", "path": backup_path, "agent": spec.name})
            changed_files.append(str(instruction))
            actions.append({"action": "write_marker", "path": str(instruction), "agent": spec.name})
            if not dry_run:
                if instruction.exists():
                    _backup(instruction)
                _atomic_write(instruction, new)
        for owned in (_path(base, parts) for parts in spec.owned_parts):
            if owned.exists():
                continue
            actions.append({"action": "write_owned_file", "path": str(owned), "agent": spec.name})
            if not dry_run:
                _atomic_write(owned, owned_file_text(spec.name))
    result = status(base, agent=agent)
    if dry_run:
        result = status(base, agent=agent)
    if issues:
        result.update({"ok": False, "status": "unhealthy", "issues": issues})
    elif actions:
        result["status"] = "installed"
    result.update({"dry_run": dry_run, "actions": actions, "would_change": actions, "changed_files": changed_files, "backup_paths": backup_paths, "idempotent": not actions})
    return result


def uninstall(home: str | Path | None = None, *, agent: str = "all", dry_run: bool = False) -> dict[str, Any]:
    base = agent_home(home)
    actions: list[dict[str, str]] = []
    changed_files: list[str] = []
    backup_paths: list[str] = []
    for spec in _specs(agent):
        instruction = _path(base, spec.instruction_parts)
        if instruction.exists():
            old = instruction.read_text(encoding="utf-8")
            new = _without_marker(old)
            if new != old:
                backup_path = str(instruction.with_name(instruction.name + ".contextwhere.bak"))
                backup_paths.append(backup_path)
                actions.append({"action": "backup", "path": backup_path, "agent": spec.name})
                changed_files.append(str(instruction))
                actions.append({"action": "remove_marker", "path": str(instruction), "agent": spec.name})
                if not dry_run:
                    _backup(instruction)
                    _atomic_write(instruction, new)
        for owned in (_path(base, parts) for parts in spec.owned_parts):
            if _owned_file_matches(owned, spec.name):
                actions.append({"action": "remove_owned_file", "path": str(owned), "agent": spec.name})
                if not dry_run:
                    owned.unlink()
    result = status(base, agent=agent)
    result["status"] = "uninstalled" if actions else result.get("status", "unavailable")
    result.update({"ok": True, "dry_run": dry_run, "actions": actions, "would_change": actions, "changed_files": changed_files, "backup_paths": backup_paths, "idempotent": not actions})
    return result
