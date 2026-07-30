from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import platform
import shlex
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Any
from dataclasses import dataclass, field

from .capture import capture_session_file, capture_session_text
from .config import ensure_dirs, resolve_paths
from .db import get_evidence, init_db, insert_evidence, log_ingest, query_evidence_with_mode
from .providers.base import ProviderResult, load_fixture_records
from .providers.mailwhere import MailWhereProvider
from .providers.officewhere import OfficeWhereProvider
from .schemas import EvidenceRecord, evidence_from_item, utc_now
from .wiki import apply_wiki_draft, create_wiki_draft, lint_wiki
from .verify import run_verify
from .entities import extract_entities, list_entities, list_relationships
from .tools import call_tool, manifest as tools_manifest, parse_input as parse_tool_input
from .recall import create_bundle, list_bundles, show_bundle
from .backup import create_backup, restore_backup
from .status import project_status
from .provider_matrix import provider_matrix
from .context_pack import build_context_pack, render_markdown
from .local_capture import capture_git, capture_omx
from .return_to_work import build_brief, ingest_manifest
from .registry import list_entries, register, registry_path, resolve
from . import memory as memory_api
from .memory_drafts import apply_memory_draft, create_memory_draft
from .setup import doctor_home, setup_home
from .signals import capture_signal, preflight as signals_preflight, stable_fingerprint
from .integrations import install as install_integrations, status as integration_status, uninstall as uninstall_integrations


def emit(data: Any, as_json: bool = False) -> None:
    if as_json:
        print(json.dumps(data, indent=2, ensure_ascii=False, default=str))
    else:
        if isinstance(data, str):
            print(data)
        else:
            print(json.dumps(data, indent=2, ensure_ascii=False, default=str))


def cmd_init(args: argparse.Namespace) -> int:
    paths = resolve_paths(args.root)
    ensure_dirs(paths)
    init_db(paths.db_path)
    emit({"ok": True, "root": str(paths.root), "db_path": str(paths.db_path), "draft_dir": str(paths.draft_dir), "audit_dir": str(paths.audit_dir)}, args.json)
    return 0


@dataclass
class IngestOutcome:
    provider: str
    records: list[Any] = field(default_factory=list)
    status: str = "ok"
    unavailable: dict[str, Any] | None = None
    details: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.status == "ok"



def provider_telemetry(result: ProviderResult) -> dict[str, Any]:
    telemetry: dict[str, Any] = {
        "provider": result.provider,
        "ok": result.ok,
        "status": result.status,
        "item_count": len(result.items),
    }
    if result.unavailable:
        telemetry["unavailable"] = {
            "provider": result.unavailable.get("provider"),
            "reason": result.unavailable.get("reason"),
            "status": result.unavailable.get("status"),
            "safe_to_continue": result.unavailable.get("safe_to_continue"),
        }
    if result.manifest is not None:
        telemetry["manifest_keys"] = sorted(str(k) for k in result.manifest.keys())
    return telemetry


def outcome_from_provider_result(result: ProviderResult, kind: str) -> IngestOutcome:
    if not result.ok:
        telemetry = provider_telemetry(result)
        return IngestOutcome(
            provider=result.provider,
            status=result.status,
            unavailable=telemetry.get("unavailable"),
            details=telemetry,
        )
    return IngestOutcome(
        provider=result.provider,
        records=[evidence_from_item(result.provider, item, kind) for item in result.items],
        details=provider_telemetry(result),
    )


def repo_scope(root: str | Path) -> str:
    return f"repo:{Path(root).resolve().name}"


def repo_tenant(root: str | Path) -> str:
    digest = hashlib.sha1(str(Path(root).resolve()).encode("utf-8")).hexdigest()[:8]
    return f"{repo_scope(root)}:{digest}"


def stamp_routing(records: list[EvidenceRecord], root: str | Path, provider: str) -> list[EvidenceRecord]:
    for record in records:
        record.metadata.setdefault("tenant", repo_tenant(root))
        record.metadata.setdefault("scope", repo_scope(root))
        record.metadata.setdefault("source_kind", record.metadata.get("source_kind") or provider)
        record.metadata.setdefault("source_locator", f"{record.provider}:{record.kind}:{record.source_ref}")
        record.metadata.setdefault("observed_at", record.occurred_at or utc_now())
    return records



def _safe_file_hint(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    hint = value.replace("\\", "/").split("/")[-1].strip()
    return hint if hint and hint not in {".", ".."} else None


def mail_file_link_records(item: dict[str, Any], default_kind: str) -> list[EvidenceRecord]:
    hints: list[str] = []
    for key in ("attachments", "attachment_names", "file_hints", "linked_files"):
        value = item.get(key)
        if isinstance(value, list):
            hints.extend(h for child in value if (h := _safe_file_hint(child)))
        elif h := _safe_file_hint(value):
            hints.append(h)
    if not hints:
        return []
    mail_ref = str(item.get("source_id") or item.get("id") or item.get("task_id") or "unknown")
    title = str(item.get("title") or item.get("subject") or mail_ref)
    records: list[EvidenceRecord] = []
    for hint in sorted(set(hints)):
        link_ref = hashlib.sha1(f"{mail_ref}:{hint}".encode("utf-8")).hexdigest()[:12]
        records.append(EvidenceRecord(
            provider="mailwhere",
            source_ref=link_ref,
            kind="file_link",
            title=f"Mail file link: {hint}",
            snippet=f"Mail '{title}' references file hint '{hint}'.",
            occurred_at=str(item.get("received_at") or item.get("source_received_at") or item.get("due_at") or "") or None,
            provenance="mailwhere_file_link",
            confidence="medium",
            metadata={"mail_source_ref": mail_ref, "file_hint": hint, "mail_kind": str(item.get("kind") or default_kind)},
            omitted_fields=["raw_body", "full_addresses", "attachments", "prompt_logs"],
        ))
    return records

def cmd_providers(args: argparse.Namespace) -> int:
    if args.action == "matrix":
        emit(provider_matrix(), args.json)
        return 0
    results = []
    providers = [args.provider] if (args.provider != "all" and not getattr(args, "all", False)) else ["mailwhere", "officewhere"]
    for name in providers:
        if name == "mailwhere":
            provider = MailWhereProvider(command=args.mailwhere_command, db=args.mailwhere_db)
            result = provider.manifest() if args.action == "manifest" else provider.health()
        else:
            provider = OfficeWhereProvider(base_url=args.officewhere_base_url)
            result = provider.manifest() if args.action == "manifest" else provider.health()
        results.append(provider_telemetry(result))
    emit({"ok": all(r["ok"] for r in results), "results": results}, args.json)
    return 0


def provider_records(args: argparse.Namespace) -> IngestOutcome:
    if args.fixture:
        records = load_fixture_records(args.provider, Path(args.fixture), default_kind=args.kind or "item")
        if args.provider == "mailwhere":
            try:
                payload = json.loads(Path(args.fixture).read_text(encoding="utf-8"))
                for item in payload.get("items", []):
                    if isinstance(item, dict):
                        records.extend(mail_file_link_records(item, args.kind or "item"))
            except (OSError, json.JSONDecodeError):
                pass
        return IngestOutcome(provider=args.provider, records=stamp_routing(records, args.root, args.provider), details={"fixture": str(args.fixture)})
    if args.provider == "mailwhere":
        provider = MailWhereProvider(command=args.mailwhere_command, db=args.mailwhere_db)
        records = []
        unavailable = []
        details: dict[str, Any] = {}
        for result, kind in ((provider.list_tasks(limit=args.limit), "task"), (provider.list_review_candidates(limit=args.limit), "review_candidate")):
            details[kind] = provider_telemetry(result)
            if result.ok:
                for item in result.items:
                    records.append(evidence_from_item("mailwhere", item, kind))
                    records.extend(mail_file_link_records(item, kind))
            else:
                unavailable_summary = provider_telemetry(result).get("unavailable")
                if unavailable_summary:
                    unavailable.append(unavailable_summary)
        if unavailable and not records:
            return IngestOutcome(
                provider="mailwhere",
                status="unavailable",
                unavailable={"provider": "mailwhere", "reason": "all_sources_unavailable", "results": unavailable, "ok": False, "status": "unavailable", "safe_to_continue": True},
                details=details,
            )
        return IngestOutcome(provider="mailwhere", records=stamp_routing(records, args.root, "mailwhere"), details=details)
    if args.provider == "officewhere":
        provider = OfficeWhereProvider(base_url=args.officewhere_base_url)
        health = provider.health()
        if args.officewhere_base_url and not health.ok:
            return outcome_from_provider_result(health, "document")
        if not (args.query or "").strip():
            return IngestOutcome(
                provider="officewhere",
                status="unavailable",
                unavailable={"provider": "officewhere", "reason": "query_required", "status": "unavailable", "safe_to_continue": True},
                details={"query_required": True},
            )
        if not health.ok:
            return outcome_from_provider_result(health, "document")
        outcome = outcome_from_provider_result(provider.search(args.query or "", limit=args.limit), "document")
        outcome.records = stamp_routing(outcome.records, args.root, "officewhere")
        return outcome
    raise SystemExit(f"unsupported provider: {args.provider}")


def cmd_ingest(args: argparse.Namespace) -> int:
    paths = resolve_paths(args.root)
    ensure_dirs(paths)
    init_db(paths.db_path)
    before_hashes = {p: (paths.wiki_dir / p).read_bytes() if (paths.wiki_dir / p).exists() else b"" for p in ["index.md", "log.md"]}
    outcome = provider_records(args)
    ids = insert_evidence(paths.db_path, outcome.records) if outcome.ok else []
    status = outcome.status
    log_ingest(paths.db_path, args.provider, "ingest", status, {"inserted": len(ids), "fixture": bool(args.fixture), "unavailable": outcome.unavailable, "details": outcome.details})
    after_hashes = {p: (paths.wiki_dir / p).read_bytes() if (paths.wiki_dir / p).exists() else b"" for p in ["index.md", "log.md"]}
    wiki_unchanged = before_hashes == after_hashes
    payload = {"ok": outcome.ok, "status": status, "inserted": len(ids), "evidence_ids": ids, "wiki_unchanged": wiki_unchanged}
    if outcome.unavailable:
        payload["unavailable"] = outcome.unavailable
    emit(payload, args.json)
    return 0 if outcome.ok else 2


def run_ingest_step(args: argparse.Namespace, provider: str) -> dict[str, Any]:
    paths = resolve_paths(args.root)
    ingest_args = {"fixture": None, "kind": None, **vars(args), "provider": provider}
    outcome = provider_records(argparse.Namespace(**ingest_args))
    ids = insert_evidence(paths.db_path, outcome.records) if outcome.ok else []
    log_ingest(paths.db_path, provider, "daily", outcome.status, {"inserted": len(ids), "unavailable": outcome.unavailable, "details": outcome.details})
    result: dict[str, Any] = {"provider": provider, "ok": outcome.ok, "status": outcome.status, "inserted": len(ids), "evidence_ids": ids}
    if outcome.unavailable:
        result["unavailable"] = outcome.unavailable
    return result


def cmd_daily(args: argparse.Namespace) -> int:
    paths = resolve_paths(args.root)
    ensure_dirs(paths)
    init_db(paths.db_path)
    steps: list[dict[str, Any]] = [{"step": "init", "ok": True, "db_path": str(paths.db_path)}]

    ingest_results = [run_ingest_step(args, "mailwhere")]
    if args.officewhere_query:
        ingest_results.append(run_ingest_step(argparse.Namespace(**{**vars(args), "query": args.officewhere_query}), "officewhere"))
    else:
        ingest_results.append({"provider": "officewhere", "ok": True, "status": "skipped", "reason": "officewhere requires explicit --officewhere-query"})
    steps.append({"step": "ingest", "ok": True, "results": ingest_results})

    entity_result = extract_entities(paths.db_path, query=args.query or "", limit=args.limit)
    steps.append({"step": "entities", "ok": bool(entity_result.get("ok")), "result": entity_result})

    draft_path = create_wiki_draft(paths.db_path, paths.wiki_dir, paths.draft_dir, query=args.query or "", limit=args.limit)
    steps.append({"step": "wiki_draft", "ok": True, "draft_path": str(draft_path)})

    issues = [issue.to_dict() for issue in lint_wiki(paths.wiki_dir)]
    lint_ok = not any(i["severity"] == "error" for i in issues)
    steps.append({"step": "lint", "ok": lint_ok, "issues": issues})

    status = project_status(args.root)
    steps.append({"step": "status", "ok": bool(status.get("ok")), "result": status})

    payload = {"ok": all(step["ok"] for step in steps), "steps": steps, "note": "wiki drafts are not applied automatically"}
    emit(payload, args.json)
    return 0 if payload["ok"] else 2


def autostart_command(root: Path) -> list[str]:
    return [sys.executable, "-m", "contextwhere", "maintain", "--root", str(root), "--json"]


def autostart_plan(root: Path, interval: str) -> dict[str, Any]:
    system = platform.system().lower()
    command = autostart_command(root)
    if system == "windows":
        task_name = "contextWhereMaintain"
        return {
            "platform": "windows",
            "task_name": task_name,
            "command": command,
            "install_command": [
                "schtasks",
                "/Create",
                "/TN",
                task_name,
                "/SC",
                "MINUTE",
                "/MO",
                str(max(1, int(interval.rstrip("m")) if interval.endswith("m") else 15)),
                "/TR",
                subprocess.list2cmdline(command),
                "/F",
            ],
        }
    service = """[Unit]
Description=contextWhere maintenance run
After=network-online.target

[Service]
Type=oneshot
WorkingDirectory={root}
ExecStart={cmd}
""".format(root=root, cmd=" ".join(shlex.quote(part) for part in command))
    timer = """[Unit]
Description=Run contextWhere maintenance

[Timer]
OnBootSec=5min
OnUnitActiveSec={interval}
Persistent=true

[Install]
WantedBy=timers.target
""".format(interval=interval)
    config_dir = Path.home() / ".config" / "systemd" / "user"
    return {
        "platform": "systemd-user",
        "service_path": str(config_dir / "contextwhere-maintain.service"),
        "timer_path": str(config_dir / "contextwhere-maintain.timer"),
        "service": service,
        "timer": timer,
        "enable_command": ["systemctl", "--user", "enable", "--now", "contextwhere-maintain.timer"],
    }


def cmd_autostart(args: argparse.Namespace) -> int:
    paths = resolve_paths(args.root)
    plan = autostart_plan(paths.root, args.interval)
    if args.autostart_command == "plan" or args.dry_run:
        emit({"ok": True, "plan": plan}, args.json)
        return 0

    if not args.yes:
        if not sys.stdin.isatty():
            emit({"ok": False, "error": "confirmation required; rerun with --yes or use autostart plan"}, args.json)
            return 2
        answer = input("Install contextWhere autostart for this user? [y/N] ").strip().lower()
        if answer not in {"y", "yes"}:
            emit({"ok": False, "cancelled": True}, args.json)
            return 2

    system = plan["platform"]
    try:
        if system == "windows":
            subprocess.run(plan["install_command"], check=True)
        else:
            Path(plan["service_path"]).parent.mkdir(parents=True, exist_ok=True)
            Path(plan["service_path"]).write_text(plan["service"], encoding="utf-8")
            Path(plan["timer_path"]).write_text(plan["timer"], encoding="utf-8")
            subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
            subprocess.run(plan["enable_command"], check=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        emit({"ok": False, "error": f"autostart install failed: {type(exc).__name__}: {exc}", "plan": plan}, args.json)
        return 2
    emit({"ok": True, "installed": True, "plan": plan}, args.json)
    return 0


def cmd_query(args: argparse.Namespace) -> int:
    paths = resolve_paths(args.root)
    rows, mode = query_evidence_with_mode(paths.db_path, args.query, limit=args.limit)
    emit({"ok": True, "search_mode": mode, "items": rows}, args.json)
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    result = project_status(args.root)
    emit(result, args.json)
    return 0 if result.get("ok") else 2


def cmd_lint(args: argparse.Namespace) -> int:
    paths = resolve_paths(args.root)
    wiki_dir = Path(args.wiki_dir) if args.wiki_dir else paths.wiki_dir
    issues = [issue.to_dict() for issue in lint_wiki(wiki_dir)]
    emit({"ok": not any(i["severity"] == "error" for i in issues), "issues": issues}, args.json)
    return 1 if any(i["severity"] == "error" for i in issues) else 0


def cmd_capture_session(args: argparse.Namespace) -> int:
    paths = resolve_paths(args.root)
    ensure_dirs(paths)
    init_db(paths.db_path)
    record = capture_session_file(Path(args.file)) if args.file else capture_session_text(sys.stdin.read(), "stdin")
    stamp_routing([record], paths.root, "agent-session")
    ids = insert_evidence(paths.db_path, [record])
    emit({"ok": True, "evidence_ids": ids}, args.json)
    return 0


def cmd_capture_local(args: argparse.Namespace) -> int:
    paths = resolve_paths(args.root)
    ensure_dirs(paths)
    init_db(paths.db_path)
    records: list[EvidenceRecord] = []
    use_git = args.git or not args.omx
    use_omx = args.omx or not args.git
    if use_omx:
        records.extend(capture_omx(paths.root, limit=args.limit))
    if use_git:
        records.extend(capture_git(paths.root, limit=args.limit))
    stamp_routing(records, paths.root, "local")
    ids = insert_evidence(paths.db_path, records)
    git_failed = any(record.provider == "git" and record.kind == "unavailable" for record in records)
    status = "unavailable" if git_failed and use_git else "ok"
    log_ingest(paths.db_path, "local", "capture-local", status, {"inserted": len(ids), "git": use_git, "omx": use_omx})
    emit({"ok": status == "ok", "status": status, "inserted": len(ids), "evidence_ids": ids}, args.json)
    return 0 if status == "ok" else 2


def cmd_return_to_work(args: argparse.Namespace) -> int:
    try:
        if args.return_to_work_command == "ingest":
            result = ingest_manifest(Path(args.root), Path(args.batch), retain_raw=args.retain_raw)
        elif args.return_to_work_command == "brief":
            result = build_brief(Path(args.root), args.batch_id)
        else:
            raise SystemExit(f"unsupported return-to-work command: {args.return_to_work_command}")
    except (OSError, ValueError, json.JSONDecodeError, sqlite3.Error) as exc:
        result = {"ok": False, "error": f"return-to-work failed: {type(exc).__name__}: {exc}"}
        emit(result, args.json)
        return 2
    emit(result, args.json)
    return 0


def _step(name: str, ok: bool, status: str, detail: str = "") -> dict[str, Any]:
    return {"name": name, "ok": ok, "status": status, "detail": detail}


def _decode_row_json(row: dict[str, Any]) -> dict[str, Any]:
    for key in ("metadata", "omitted_fields"):
        try:
            row[key] = json.loads(row.get(key) or ("[]" if key == "omitted_fields" else "{}"))
        except (TypeError, json.JSONDecodeError):
            row[key] = [] if key == "omitted_fields" else {}
    return row


def cmd_evidence(args: argparse.Namespace) -> int:
    if args.evidence_command != "show":
        raise SystemExit(f"unsupported evidence command: {args.evidence_command}")
    paths = resolve_paths(args.root)
    if not paths.db_path.exists():
        emit({"ok": False, "error": "contextWhere database not initialized"}, args.json)
        return 2
    if not args.evidence_id and not args.source_locator:
        emit({"ok": False, "error": "evidence_id or --source-locator required"}, args.json)
        return 2
    row = get_evidence(paths.db_path, args.evidence_id, args.source_locator)
    if not row:
        emit({"ok": False, "error": "evidence not found"}, args.json)
        return 2
    result = {"ok": True, "evidence": _decode_row_json(row)}
    emit(result, args.json)
    return 0


def cmd_maintain(args: argparse.Namespace) -> int:
    paths = resolve_paths(args.root)
    ensure_dirs(paths)
    init_db(paths.db_path)
    steps: list[dict[str, Any]] = []

    records = capture_omx(paths.root, limit=args.limit) + capture_git(paths.root, limit=args.limit)
    stamp_routing(records, paths.root, "local")
    ids = insert_evidence(paths.db_path, records)
    git_failed = any(record.provider == "git" and record.kind == "unavailable" for record in records)
    capture_ok = not (git_failed and args.strict_git)
    steps.append(_step("capture-local", capture_ok, "unavailable" if git_failed else "ok", f"inserted={len(ids)}"))
    log_ingest(paths.db_path, "local", "maintain", "unavailable" if git_failed else "ok", {"inserted": len(ids), "strict_git": args.strict_git})

    pack = build_context_pack(paths.db_path, task=args.task or args.query, query=args.query, scope=repo_scope(paths.root), max_items=args.max_items)
    steps.append(_step("context-pack", True, "ok", pack["manifest"]["pack_id"]))

    if paths.wiki_dir.exists():
        issues = [issue.to_dict() for issue in lint_wiki(paths.wiki_dir)]
        errors = [issue for issue in issues if issue.get("severity") == "error"]
        steps.append(_step("lint", not errors, "error" if errors else "ok", f"issues={len(issues)}"))
    else:
        steps.append(_step("lint", True, "warning", "work_wiki missing"))

    status = project_status(paths.root)
    steps.append(_step("status", True, "ok", f"evidence={status.get('counts', {}).get('evidence', 0)}"))

    ok = all(step["ok"] for step in steps)
    result = {"ok": ok, "status": "ok" if ok else "unavailable", "steps": steps, "evidence_ids": ids, "context_pack": pack["manifest"], "status_summary": status}
    emit(result, args.json)
    return 0 if ok else 2


def cmd_context(args: argparse.Namespace) -> int:
    if args.context_command != "pack":
        raise SystemExit(f"unsupported context command: {args.context_command}")
    paths = resolve_paths(args.root)
    if not paths.db_path.exists():
        emit({"ok": False, "error": "contextWhere database not initialized"}, args.json)
        return 2
    pack = build_context_pack(
        paths.db_path,
        task=args.task or args.query or "current task",
        query=args.query or "",
        tenant=args.tenant,
        scope=args.scope if args.scope or args.all_scopes else repo_scope(paths.root),
        source_kinds=[part.strip() for part in (args.source_kinds or "").split(",") if part.strip()],
        max_items=args.max_items,
        sensitivity_ceiling=args.sensitivity_ceiling,
        include_stale=args.include_stale,
        include_history=args.include_history,
    )
    if args.format == "markdown":
        emit(render_markdown(pack), False)
    else:
        emit(pack, True)
    return 0


def cmd_wiki_draft(args: argparse.Namespace) -> int:
    paths = resolve_paths(args.root)
    ensure_dirs(paths)
    draft = create_wiki_draft(paths.db_path, paths.wiki_dir, paths.draft_dir, query=args.query or "", limit=args.limit)
    output = getattr(args, "output", None)
    if output:
        target = Path(output)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(draft.read_text(encoding="utf-8"), encoding="utf-8")
        draft = target
    emit({"ok": True, "draft_path": str(draft)}, args.json)
    return 0


def cmd_wiki_apply(args: argparse.Namespace) -> int:
    paths = resolve_paths(args.root)
    ensure_dirs(paths)
    audit = apply_wiki_draft(Path(args.draft), paths.root, paths.audit_dir, db_path=paths.db_path)
    audit_data = json.loads(audit.read_text(encoding="utf-8"))
    emit({"ok": audit_data["status"] == "applied", "audit_path": str(audit), "audit": audit_data}, args.json)
    return 0 if audit_data["status"] == "applied" else 2


def cmd_verify(args: argparse.Namespace) -> int:
    result = run_verify(Path(args.verify_root) if args.verify_root else None, keep=args.keep)
    emit(result, args.json)
    return 0 if result["ok"] else 2


def cmd_entities(args: argparse.Namespace) -> int:
    paths = resolve_paths(args.root)
    ensure_dirs(paths)
    init_db(paths.db_path)
    if args.entities_command == "extract":
        result = extract_entities(paths.db_path, query=args.query or "", limit=args.limit)
    elif args.entities_command == "list":
        result = {"ok": True, "items": list_entities(paths.db_path, limit=args.limit)}
    elif args.entities_command == "relationships":
        result = {"ok": True, "items": list_relationships(paths.db_path, limit=args.limit)}
    else:
        raise SystemExit(f"unsupported entities command: {args.entities_command}")
    emit(result, args.json)
    return 0


def cmd_backup(args: argparse.Namespace) -> int:
    try:
        if args.backup_command == "create":
            result = create_backup(args.root, args.output)
        elif args.backup_command == "restore":
            result = restore_backup(args.backup, args.target_root)
        else:
            raise SystemExit(f"unsupported backup command: {args.backup_command}")
    except (OSError, ValueError, json.JSONDecodeError, zipfile.BadZipFile) as exc:
        result = {"ok": False, "error": f"backup failed: {type(exc).__name__}: {exc}"}
        emit(result, args.json)
        return 2
    emit(result, args.json)
    return 0 if result.get("ok") else 2


def cmd_recall(args: argparse.Namespace) -> int:
    paths = resolve_paths(args.root)
    ensure_dirs(paths)
    init_db(paths.db_path)
    try:
        if args.recall_command == "create":
            result = create_bundle(paths.db_path, name=args.name, query=args.query, limit=args.limit)
        elif args.recall_command == "list":
            result = {"ok": True, "items": list_bundles(paths.db_path, limit=args.limit)}
        elif args.recall_command == "show":
            result = show_bundle(paths.db_path, args.bundle_id)
        else:
            raise SystemExit(f"unsupported recall command: {args.recall_command}")
    except ValueError as exc:
        result = {"ok": False, "error": str(exc)}
        emit(result, args.json)
        return 2
    emit(result, args.json)
    return 0 if result.get("ok") else 2


def cmd_tools(args: argparse.Namespace) -> int:
    if args.tools_command == "manifest":
        result = tools_manifest()
    elif args.tools_command == "call":
        try:
            payload = parse_tool_input(args.input_json, args.input_file)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            result = {"ok": False, "tool": args.tool_name, "error": f"invalid input: {type(exc).__name__}"}
            emit(result, args.json)
            return 2
        try:
            result = call_tool(args.root, args.tool_name, payload)
        except ValueError as exc:
            result = {"ok": False, "tool": args.tool_name, "error": f"invalid input: {exc}"}
            emit(result, args.json)
            return 2
    else:
        raise SystemExit(f"unsupported tools command: {args.tools_command}")
    emit(result, args.json)
    return 0 if result.get("ok") else 2


def cmd_registry(args: argparse.Namespace) -> int:
    try:
        if args.registry_command == "register":
            entry = register(args.kind, args.path, workspace=args.workspace, home=args.home)
            result = {"ok": True, "entry": entry, "registry_path": str(registry_path(args.home))}
        elif args.registry_command == "list":
            result = {
                "ok": True,
                "entries": list_entries(args.kind, home=args.home),
                "registry_path": str(registry_path(args.home)),
            }
        elif args.registry_command == "resolve":
            entry = resolve(args.identifier, kind=args.kind, home=args.home)
            if entry is None:
                emit({"ok": False, "error": "registry entry not found"}, args.json)
                return 2
            result = {"ok": True, "entry": entry, "registry_path": str(registry_path(args.home))}
        else:
            raise SystemExit(f"unsupported registry command: {args.registry_command}")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        emit({"ok": False, "error": f"registry failed: {type(exc).__name__}: {exc}"}, args.json)
        return 2
    emit(result, args.json)
    return 0



def _current_repository_key(value: str | None = None) -> str:
    return value or Path.cwd().resolve().name


def _current_machine_key(value: str | None = None) -> str:
    return value or platform.node() or "local"


def _memory_preflight(db_path: Path, *, repository: str | None, machine: str | None, limit: int | None) -> dict[str, Any]:
    repository_key = _current_repository_key(repository)
    machine_key = _current_machine_key(machine)
    max_cards = limit if limit is not None else 8
    cards = memory_api.preflight_lookup(db_path, repository_key=repository_key, machine_key=machine_key, limit=max_cards)
    return {"ok": True, "scope": {"repository": repository_key, "machine": machine_key}, "cards": cards, "db_path": str(db_path)}


def _memory_preflight_from_args(args: argparse.Namespace, db_path: Path) -> dict[str, Any]:
    has_scope_flags = any(
        getattr(args, name, None)
        for name in ("scope", "scope_type", "scope_key")
    ) or getattr(args, "registered", False)
    repository = getattr(args, "repository", None)
    machine = getattr(args, "machine", None)
    if has_scope_flags:
        scope = _memory_scope(args)
        if scope is None:
            raise ValueError("memory preflight scope requires --scope type:key, --scope-type/--scope-key, or --registered")
        scope_type, scope_key = scope
        if scope_type == "repository":
            repository = scope_key
        elif scope_type == "machine":
            machine = scope_key
        else:
            raise ValueError(f"memory preflight supports repository or machine scope, not {scope_type or 'empty'}")
    return _memory_preflight(db_path, repository=repository, machine=machine, limit=getattr(args, "limit", None))

def _read_json_arg(args: argparse.Namespace) -> dict[str, Any]:
    if getattr(args, "input_file", None):
        return json.loads(Path(args.input_file).read_text(encoding="utf-8"))
    if getattr(args, "input_json", None):
        return json.loads(args.input_json)
    return {}


def _memory_db(home: str | None) -> Path:
    from .config import resolve_global_home

    base = Path(home).expanduser().resolve() if home else resolve_global_home()
    return base / "contextwhere.sqlite3"


def _parse_scope(value: str | None) -> tuple[str, str] | None:
    if not value:
        return None
    if ":" not in value:
        raise ValueError("--scope must be type:key")
    scope_type, scope_key = value.split(":", 1)
    return scope_type, scope_key


def _memory_scope(args: argparse.Namespace, payload: dict[str, Any] | None = None) -> tuple[str, str] | None:
    parsed = _parse_scope(getattr(args, "scope", None))
    if parsed:
        return parsed
    if getattr(args, "registered", False):
        entry = resolve(args.root, home=args.home)
        if entry is None:
            raise ValueError("registered scope not found; run registry register first")
        return str(entry["kind"]), str(entry["id"])
    if getattr(args, "scope_type", None) and getattr(args, "scope_key", None):
        return args.scope_type, args.scope_key
    if getattr(args, "repository", None):
        return "repository", args.repository
    if payload and payload.get("scope"):
        scope = payload["scope"]
        if isinstance(scope, dict):
            return str(scope.get("type") or ""), str(scope.get("key") or "")
        return _parse_scope(str(scope))
    return None

def _with_scope(payload: dict[str, Any], scope_type: str, scope_key: str) -> dict[str, Any]:
    data = dict(payload)
    data.setdefault("scope", {"type": scope_type, "key": scope_key})
    return data


def _promote_status(status: str) -> str:
    if status == "observed":
        return "candidate"
    if status in {"candidate", "needs_review"}:
        return "active"
    return status


def cmd_memory(args: argparse.Namespace) -> int:
    db_path = _memory_db(args.home)
    try:
        if args.memory_command == "preflight":
            result = _memory_preflight_from_args(args, db_path)
        elif args.memory_command in {"observe", "create"}:
            payload = _read_json_arg(args)
            scope = _memory_scope(args, payload)
            if scope is None:
                raise ValueError("memory observe/create requires payload scope, --scope, --registered, or --repository")
            scope_type, scope_key = scope
            payload = _with_scope(payload, scope_type, scope_key)
            payload.setdefault("status", "observed" if args.memory_command == "observe" else "candidate")
            card_id = memory_api.upsert_card(db_path, payload, actor="contextwhere-cli", reason=args.reason or args.memory_command)
            result = {"ok": True, "card": memory_api.get_card(db_path, card_id), "audit": memory_api.audit_rows(db_path, card_id), "db_path": str(db_path)}
        elif args.memory_command == "list":
            scope = _memory_scope(args)
            if scope is None:
                raise ValueError("memory list requires --scope, --registered, or --repository")
            scope_type, scope_key = scope
            cards = memory_api.list_cards(db_path, scope_type=scope_type, scope_key=scope_key, status=args.status, limit=args.limit)
            order = {"active": 0, "candidate": 1, "needs_review": 2, "observed": 3, "stale": 4, "superseded": 5, "rejected": 6}
            cards.sort(key=lambda item: (order.get(item.get("status"), 99), item.get("card_id", "")))
            result = {"ok": True, "cards": cards, "db_path": str(db_path)}
        elif args.memory_command == "show":
            card = memory_api.get_card(db_path, args.card_id)
            if card is None:
                emit({"ok": False, "error": "card not found", "code": "card_not_found"}, args.json)
                return 2
            result = {"ok": True, "card": card, "audit": memory_api.audit_rows(db_path, args.card_id), "db_path": str(db_path)}
        elif args.memory_command == "promote":
            card = memory_api.get_card(db_path, args.card_id)
            if card is None:
                emit({"ok": False, "error": "card not found", "code": "card_not_found"}, args.json)
                return 2
            target = args.to or _promote_status(card["status"])
            memory_api.transition_card(db_path, args.card_id, target, reason=args.reason or "promote", actor="contextwhere-cli")
            result = {"ok": True, "card": memory_api.get_card(db_path, args.card_id), "audit": memory_api.audit_rows(db_path, args.card_id), "db_path": str(db_path)}
        elif args.memory_command == "reject":
            memory_api.transition_card(db_path, args.card_id, "rejected", reason=args.reason or "reject", actor="contextwhere-cli")
            result = {"ok": True, "card": memory_api.get_card(db_path, args.card_id), "audit": memory_api.audit_rows(db_path, args.card_id), "db_path": str(db_path)}
        elif args.memory_command == "supersede":
            payload = _read_json_arg(args)
            scope = _memory_scope(args, payload)
            if scope is not None:
                payload = _with_scope(payload, *scope)
            card_id = memory_api.supersede_card(db_path, args.card_id, payload, actor="contextwhere-cli", reason=args.reason or "supersede")
            old_card = memory_api.get_card(db_path, args.card_id)
            new_card = memory_api.get_card(db_path, card_id)
            result = {"ok": True, "old": old_card, "new": new_card, "old_card": old_card, "new_card": new_card, "audit": memory_api.audit_events(db_path), "db_path": str(db_path)}
        elif args.memory_command == "draft":
            home = db_path.parent
            draft = create_memory_draft(db_path, card_id=args.card_id, root=Path(getattr(args, "root", ".")), home=home, supersede=getattr(args, "supersede", None))
            output = getattr(args, "output", None)
            if output:
                target = Path(output)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(draft.read_text(encoding="utf-8"), encoding="utf-8")
                draft = target
            result = {"ok": True, "draft_path": str(draft), "draft": json.loads(draft.read_text(encoding="utf-8")), "note": "memory drafts are not applied automatically", "db_path": str(db_path)}
        elif args.memory_command == "apply":
            home = db_path.parent
            audit = apply_memory_draft(Path(args.draft), db_path=db_path, root=Path(getattr(args, "root", ".")), home=home)
            audit_data = json.loads(audit.read_text(encoding="utf-8"))
            result = {"ok": audit_data["status"] == "applied", "audit_path": str(audit), "audit": audit_data, "db_path": str(db_path)}
        else:
            raise SystemExit(f"unsupported memory command: {args.memory_command}")
    except (OSError, ValueError, json.JSONDecodeError, KeyError) as exc:
        emit({"ok": False, "error": str(exc), "code": type(exc).__name__}, args.json)
        return 2
    emit(result, args.json)
    return 0 if result.get("ok") else 2


def cmd_preflight(args: argparse.Namespace) -> int:
    db_path = _memory_db(args.home)
    result = _memory_preflight(db_path, repository=args.repository, machine=args.machine, limit=args.limit)
    emit(result, args.json)
    return 0


def _signal_db(args: argparse.Namespace) -> Path:
    return _memory_db(getattr(args, "home", None))


def cmd_signals(args: argparse.Namespace) -> int:
    db_path = _signal_db(args)
    try:
        if args.signals_command == "fingerprint":
            payload = _read_json_arg(args)
            result = {"ok": True, "fingerprint": stable_fingerprint(payload)}
        elif args.signals_command == "capture":
            payload = _read_json_arg(args)
            result = capture_signal(db_path, payload, repository=args.repository, machine=args.machine, threshold=args.threshold)
            result["db_path"] = str(db_path)
        elif args.signals_command == "preflight":
            result = signals_preflight(db_path, repository=args.repository, machine=args.machine, fingerprint=args.fingerprint, threshold=args.threshold)
            result["db_path"] = str(db_path)
        else:
            raise SystemExit(f"unsupported signals command: {args.signals_command}")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        emit({"ok": False, "error": str(exc), "code": type(exc).__name__}, args.json)
        return 2
    emit(result, args.json)
    return 0 if result.get("ok") else 2




def cmd_drafts(args: argparse.Namespace) -> int:
    db_path = _memory_db(args.home)
    home = db_path.parent
    try:
        if args.drafts_command == "create":
            draft = create_memory_draft(db_path, card_id=args.card_id, root=Path(args.root), home=home, supersede=getattr(args, "supersede", None))
            result = {"ok": True, "status": "draft", "draft_path": str(draft), "draft": json.loads(draft.read_text(encoding="utf-8")), "note": "memory drafts are not applied automatically"}
        elif args.drafts_command == "apply":
            audit = apply_memory_draft(Path(args.draft), db_path=db_path, root=Path(args.root), home=home)
            audit_data = json.loads(audit.read_text(encoding="utf-8"))
            issues = [{"message": reason} for reason in audit_data.get("refused_reasons", [])]
            result = {"ok": audit_data["status"] == "applied", "status": audit_data["status"], "audit_path": str(audit), "audit": audit_data, "refused_reasons": audit_data.get("refused_reasons", []), "issues": issues}
        else:
            raise SystemExit(f"unsupported drafts command: {args.drafts_command}")
    except (OSError, ValueError, json.JSONDecodeError, KeyError) as exc:
        emit({"ok": False, "error": str(exc), "refused_reasons": [str(exc)], "code": type(exc).__name__}, args.json)
        return 2
    emit(result, args.json)
    return 0 if result.get("ok") else 2

def cmd_integrations(args: argparse.Namespace) -> int:
    try:
        if args.integrations_command == "status":
            result = integration_status(args.home, agent=args.agent)
        elif args.integrations_command == "doctor":
            result = integration_status(args.home, agent=args.agent, doctor=True)
        elif args.integrations_command == "install":
            result = install_integrations(args.home, agent=args.agent, dry_run=args.dry_run)
        elif args.integrations_command == "uninstall":
            result = uninstall_integrations(args.home, agent=args.agent, dry_run=args.dry_run)
        else:
            raise SystemExit(f"unsupported integrations command: {args.integrations_command}")
    except ValueError as exc:
        emit({"ok": False, "error": str(exc)}, args.json)
        return 2
    emit(result, args.json)
    return 0 if result.get("ok") else 2

def cmd_setup(args: argparse.Namespace) -> int:
    result = setup_home(args.home, dry_run=args.dry_run, install_agent_bridges=getattr(args, "install_integrations", False))
    emit(result, args.json)
    return 0 if result.get("ok") else 2


def cmd_doctor(args: argparse.Namespace) -> int:
    result = doctor_home(args.home)
    emit(result, args.json)
    return 0 if result.get("ok") else 2


def cmd_quickstart(args: argparse.Namespace) -> int:
    root = Path(args.root).expanduser().resolve()
    workspace = Path(args.workspace).expanduser().resolve() if args.workspace else root.parent
    setup = setup_home(args.home)
    home = setup["home"]

    paths = resolve_paths(root)
    ensure_dirs(paths)
    init_db(paths.db_path)
    paths.wiki_dir.mkdir(parents=True, exist_ok=True)
    index = paths.wiki_dir / "index.md"
    if not index.exists():
        index.write_text("# ContextWhere Wiki Index\n", encoding="utf-8")
    workspace_entry = register("workspace", workspace, home=home)
    repository_entry = register("repository", root, workspace=workspace, home=home)
    doctor = doctor_home(home)
    status = project_status(root)
    result = {
        "ok": doctor["ok"] and status["ok"],
        "home": home,
        "workspace": workspace_entry,
        "repository": repository_entry,
        "status": status,
        "doctor": doctor,
        "next_steps": [
            f"contextwhere preflight --repository {root.name} --json",
            f"contextwhere status --root {root} --json",
        ],
    }
    emit(result, args.json)
    return 0 if result["ok"] else 2

def add_common(p: argparse.ArgumentParser) -> None:
    p.add_argument("--json", action="store_true")
    p.add_argument("--root", dest="root_override")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="contextwhere")
    parser.add_argument("--root", default=".")
    parser.add_argument("--json", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("init")
    add_common(p)
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("providers")
    add_common(p)
    p.add_argument("action", choices=["health", "manifest", "matrix"])
    p.add_argument("--provider", choices=["all", "mailwhere", "officewhere"], default="all")
    p.add_argument("--all", action="store_true", help="Check all providers (compatibility alias)")
    p.add_argument("--mailwhere-command", default="MailWhere.Cli.exe")
    p.add_argument("--mailwhere-db")
    p.add_argument("--officewhere-base-url")
    p.set_defaults(func=cmd_providers)

    p = sub.add_parser("ingest")
    add_common(p)
    p.add_argument("--provider", choices=["mailwhere", "officewhere"], required=True)
    p.add_argument("--fixture")
    p.add_argument("--kind")
    p.add_argument("--query", default="")
    p.add_argument("--limit", type=int, default=50)
    p.add_argument("--mailwhere-command", default="MailWhere.Cli.exe")
    p.add_argument("--mailwhere-db")
    p.add_argument("--officewhere-base-url")
    p.set_defaults(func=cmd_ingest)

    for command_name in ("daily", "run"):
        p = sub.add_parser(command_name)
        add_common(p)
        p.add_argument("--query", default="recent work")
        p.add_argument("--limit", type=int, default=50)
        p.add_argument("--mailwhere-command", default="MailWhere.Cli.exe")
        p.add_argument("--mailwhere-db")
        p.add_argument("--officewhere-base-url")
        p.add_argument("--officewhere-query", help="Opt-in OfficeWhere search. Daily skips document search unless this is set.")
        p.set_defaults(func=cmd_daily)

    autostart = sub.add_parser("autostart")
    add_common(autostart)
    autostart_sub = autostart.add_subparsers(dest="autostart_command", required=True)
    for action in ("plan", "install"):
        p = autostart_sub.add_parser(action)
        add_common(p)
        p.add_argument("--interval", default="15m")
        p.add_argument("--yes", action="store_true")
        p.add_argument("--dry-run", action="store_true")
        p.set_defaults(func=cmd_autostart)

    p = sub.add_parser("query")
    add_common(p)
    p.add_argument("query")
    p.add_argument("--limit", type=int, default=20)
    p.set_defaults(func=cmd_query)

    p = sub.add_parser("status")
    add_common(p)
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("lint")
    add_common(p)
    p.add_argument("wiki_dir", nargs="?")
    p.set_defaults(func=cmd_lint)

    p = sub.add_parser("capture-session")
    add_common(p)
    p.add_argument("--file")
    p.set_defaults(func=cmd_capture_session)

    p = sub.add_parser("capture-local")
    add_common(p)
    p.add_argument("--git", action="store_true", help="Capture read-only git status/log evidence")
    p.add_argument("--omx", action="store_true", help="Capture repo-local .omx plan/context files as agent-session evidence")
    p.add_argument("--limit", type=int, default=20)
    p.set_defaults(func=cmd_capture_local)

    return_to_work = sub.add_parser("return-to-work")
    add_common(return_to_work)
    return_to_work_sub = return_to_work.add_subparsers(dest="return_to_work_command", required=True)
    p = return_to_work_sub.add_parser("ingest")
    add_common(p)
    p.add_argument("--batch", required=True, help="Path to a thin return-to-work manifest JSON file")
    p.add_argument("--retain-raw", action="store_true", help="Copy user-supplied text files into the batch raw vault")
    p.set_defaults(func=cmd_return_to_work)
    p = return_to_work_sub.add_parser("brief")
    add_common(p)
    p.add_argument("--batch-id", required=True)
    p.set_defaults(func=cmd_return_to_work)

    context = sub.add_parser("context")
    add_common(context)
    context_sub = context.add_subparsers(dest="context_command", required=True)
    p = context_sub.add_parser("pack")
    add_common(p)
    p.add_argument("--query", default="")
    p.add_argument("--task", default="")
    p.add_argument("--tenant")
    p.add_argument("--scope")
    p.add_argument("--all-scopes", action="store_true", help="Do not default to the current repo scope")
    p.add_argument("--source-kinds", default="")
    p.add_argument("--max-items", type=int, default=20)
    p.add_argument("--sensitivity-ceiling", choices=["public", "internal", "confidential", "secret-like"], default="internal")
    p.add_argument("--include-stale", action="store_true")
    p.add_argument("--include-history", action="store_true")
    p.add_argument("--format", choices=["json", "markdown"], default="json")
    p.set_defaults(func=cmd_context)

    evidence = sub.add_parser("evidence")
    add_common(evidence)
    evidence_sub = evidence.add_subparsers(dest="evidence_command", required=True)
    p = evidence_sub.add_parser("show")
    add_common(p)
    p.add_argument("evidence_id", nargs="?")
    p.add_argument("--source-locator")
    p.set_defaults(func=cmd_evidence)

    p = sub.add_parser("maintain")
    add_common(p)
    p.add_argument("--query", default="contextWhere")
    p.add_argument("--task", default="routine maintenance")
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--max-items", type=int, default=20)
    p.add_argument("--strict-git", action="store_true", help="Return non-zero if git capture reports unavailable")
    p.set_defaults(func=cmd_maintain)

    p = sub.add_parser("verify")
    p.add_argument("--json", action="store_true")
    p.add_argument("--verify-root", help="Optional parent directory under which a contextwhere-verify-* root is created")
    p.add_argument("--keep", action="store_true", help="Keep the temporary verification root and print its path")
    p.set_defaults(func=cmd_verify)

    entities = sub.add_parser("entities")
    add_common(entities)
    entities_sub = entities.add_subparsers(dest="entities_command", required=True)
    p = entities_sub.add_parser("extract")
    add_common(p)
    p.add_argument("--query", default="")
    p.add_argument("--limit", type=int, default=100)
    p.set_defaults(func=cmd_entities)
    p = entities_sub.add_parser("list")
    add_common(p)
    p.add_argument("--limit", type=int, default=100)
    p.set_defaults(func=cmd_entities)
    p = entities_sub.add_parser("relationships")
    add_common(p)
    p.add_argument("--limit", type=int, default=100)
    p.set_defaults(func=cmd_entities)

    backup = sub.add_parser("backup")
    add_common(backup)
    backup_sub = backup.add_subparsers(dest="backup_command", required=True)
    p = backup_sub.add_parser("create")
    add_common(p)
    p.add_argument("--output", required=True)
    p.set_defaults(func=cmd_backup)
    p = backup_sub.add_parser("restore")
    p.add_argument("backup")
    p.add_argument("target_root")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_backup)

    recall = sub.add_parser("recall")
    add_common(recall)
    recall_sub = recall.add_subparsers(dest="recall_command", required=True)
    p = recall_sub.add_parser("create")
    add_common(p)
    p.add_argument("--name", required=True)
    p.add_argument("--query", required=True)
    p.add_argument("--limit", type=int, default=20)
    p.set_defaults(func=cmd_recall)
    p = recall_sub.add_parser("list")
    add_common(p)
    p.add_argument("--limit", type=int, default=50)
    p.set_defaults(func=cmd_recall)
    p = recall_sub.add_parser("show")
    add_common(p)
    p.add_argument("bundle_id")
    p.set_defaults(func=cmd_recall)

    tools = sub.add_parser("tools")
    add_common(tools)
    tools_sub = tools.add_subparsers(dest="tools_command", required=True)
    p = tools_sub.add_parser("manifest")
    add_common(p)
    p.set_defaults(func=cmd_tools)
    p = tools_sub.add_parser("call")
    add_common(p)
    p.add_argument("tool_name")
    p.add_argument("--input-json")
    p.add_argument("--input-file")
    p.set_defaults(func=cmd_tools)

    registry = sub.add_parser("registry")
    add_common(registry)
    registry.add_argument("--home")
    registry_sub = registry.add_subparsers(dest="registry_command", required=True)
    p = registry_sub.add_parser("register")
    add_common(p)
    p.add_argument("kind", choices=["workspace", "repository"])
    p.add_argument("path", nargs="?", default=".")
    p.add_argument("--workspace")
    p.add_argument("--home", default=argparse.SUPPRESS)
    p.set_defaults(func=cmd_registry)
    p = registry_sub.add_parser("list")
    add_common(p)
    p.add_argument("kind", nargs="?", choices=["workspace", "repository"])
    p.add_argument("--home", default=argparse.SUPPRESS)
    p.set_defaults(func=cmd_registry)
    p = registry_sub.add_parser("resolve")
    add_common(p)
    p.add_argument("identifier")
    p.add_argument("--kind", choices=["workspace", "repository"])
    p.add_argument("--home", default=argparse.SUPPRESS)
    p.set_defaults(func=cmd_registry)


    drafts = sub.add_parser("drafts")
    drafts_sub = drafts.add_subparsers(dest="drafts_command", required=True)
    p = drafts_sub.add_parser("create")
    p.add_argument("--home")
    p.add_argument("--root", default=".")
    p.add_argument("--card-id", required=True)
    p.add_argument("--supersede", action="append", default=[])
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_drafts)
    p = drafts_sub.add_parser("apply")
    p.add_argument("draft")
    p.add_argument("--home")
    p.add_argument("--root", default=".")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_drafts)

    memory = sub.add_parser("memory")
    memory.add_argument("--home")
    memory.add_argument("--registered", action="store_true")
    memory.add_argument("--scope")
    memory.add_argument("--scope-type", choices=["global", "workspace", "repository", "machine"])
    memory.add_argument("--scope-key")
    memory.add_argument("--repository")
    memory_sub = memory.add_subparsers(dest="memory_command", required=True)

    def add_memory_common(p: argparse.ArgumentParser) -> None:
        p.add_argument("--json", action="store_true")
        p.add_argument("--root", default=".")
        p.add_argument("--home", default=argparse.SUPPRESS)
        p.add_argument("--registered", action="store_true", default=argparse.SUPPRESS)
        p.add_argument("--scope", default=argparse.SUPPRESS)
        p.add_argument("--scope-type", choices=["global", "workspace", "repository", "machine"], default=argparse.SUPPRESS)
        p.add_argument("--scope-key", default=argparse.SUPPRESS)
        p.add_argument("--repository", default=argparse.SUPPRESS)

    for action in ("observe", "create"):
        p = memory_sub.add_parser(action)
        add_memory_common(p)
        p.add_argument("--input-json")
        p.add_argument("--input-file")
        p.add_argument("--reason", default="")
        p.set_defaults(func=cmd_memory)
    p = memory_sub.add_parser("list")
    add_memory_common(p)
    p.add_argument("--status")
    p.add_argument("--limit", type=int, default=50)
    p.set_defaults(func=cmd_memory)
    p = memory_sub.add_parser("show")
    add_memory_common(p)
    p.add_argument("card_id")
    p.add_argument("--audit", action="store_true")
    p.set_defaults(func=cmd_memory)
    p = memory_sub.add_parser("promote")
    add_memory_common(p)
    p.add_argument("card_id")
    p.add_argument("--status", "--to", dest="to", choices=["candidate", "needs_review", "active", "stale"])
    p.add_argument("--reason", default="")
    p.set_defaults(func=cmd_memory)
    p = memory_sub.add_parser("reject")
    add_memory_common(p)
    p.add_argument("card_id")
    p.add_argument("--reason", default="")
    p.set_defaults(func=cmd_memory)
    p = memory_sub.add_parser("supersede")
    add_memory_common(p)
    p.add_argument("card_id")
    p.add_argument("--input-json")
    p.add_argument("--input-file")
    p.add_argument("--reason", default="")
    p.set_defaults(func=cmd_memory)
    p = memory_sub.add_parser("draft")
    add_memory_common(p)
    p.add_argument("card_id")
    p.add_argument("--output")
    p.add_argument("--supersede", action="append", default=[])
    p.set_defaults(func=cmd_memory)
    p = memory_sub.add_parser("apply")
    add_memory_common(p)
    p.add_argument("draft")
    p.set_defaults(func=cmd_memory)
    p = memory_sub.add_parser("preflight")
    add_memory_common(p)
    p.add_argument("--machine")
    p.add_argument("--limit", type=int, default=8)
    p.set_defaults(func=cmd_memory)


    signals = sub.add_parser("signals")
    signals.add_argument("--home")
    signals.add_argument("--repository")
    signals.add_argument("--machine")
    signals.add_argument("--threshold", type=int, default=2)
    signals.add_argument("--json", action="store_true")
    signals_sub = signals.add_subparsers(dest="signals_command", required=True)
    for action in ("capture", "fingerprint"):
        p = signals_sub.add_parser(action)
        p.add_argument("--home", default=argparse.SUPPRESS)
        p.add_argument("--repository", default=argparse.SUPPRESS)
        p.add_argument("--machine", default=argparse.SUPPRESS)
        p.add_argument("--threshold", type=int, default=2)
        p.add_argument("--json", action="store_true")
        p.add_argument("--input-json")
        p.add_argument("--input-file")
        p.set_defaults(func=cmd_signals)
    p = signals_sub.add_parser("preflight")
    p.add_argument("--home", default=argparse.SUPPRESS)
    p.add_argument("--repository", default=argparse.SUPPRESS)
    p.add_argument("--machine", default=argparse.SUPPRESS)
    p.add_argument("--threshold", type=int, default=2)
    p.add_argument("--fingerprint")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_signals)

    p = sub.add_parser("preflight")
    p.add_argument("--json", action="store_true")
    p.add_argument("--home")
    p.add_argument("--repository")
    p.add_argument("--machine")
    p.add_argument("--limit", type=int, default=8)
    p.set_defaults(func=cmd_preflight)


    integrations = sub.add_parser("integrations")
    integrations.add_argument("--home")
    integrations.add_argument("--json", action="store_true")
    integrations.add_argument("--agent", choices=["all", "codex", "claude", "gemini"], default="all")
    integrations_sub = integrations.add_subparsers(dest="integrations_command", required=True)
    for action in ("status", "doctor", "install", "uninstall"):
        p = integrations_sub.add_parser(action)
        p.add_argument("--home", default=argparse.SUPPRESS)
        p.add_argument("--json", action="store_true")
        p.add_argument("--agent", choices=["all", "codex", "claude", "gemini"], default="all")
        if action in {"install", "uninstall"}:
            p.add_argument("--dry-run", action="store_true")
        else:
            p.set_defaults(dry_run=False)
        p.set_defaults(func=cmd_integrations)

    p = sub.add_parser("setup")
    p.add_argument("--home")
    p.add_argument("--root", default=".")
    p.add_argument("--json", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--install-integrations", action="store_true")
    p.set_defaults(func=cmd_setup)

    p = sub.add_parser("doctor")
    p.add_argument("--home")
    p.add_argument("--root", default=".")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_doctor)

    p = sub.add_parser("quickstart", help="Initialize global and repository-local storage, then verify both")
    p.add_argument("--home")
    p.add_argument("--root", default=".")
    p.add_argument("--workspace", help="Defaults to the parent of --root")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_quickstart)

    wiki = sub.add_parser("wiki")
    wiki_sub = wiki.add_subparsers(dest="wiki_command", required=True)
    p = wiki_sub.add_parser("draft")
    add_common(p)
    p.add_argument("--query", default="")
    p.add_argument("--limit", type=int, default=10)
    p.add_argument("--output", help="Optional path to copy the generated draft JSON for scripts")
    p.set_defaults(func=cmd_wiki_draft)
    p = wiki_sub.add_parser("apply")
    add_common(p)
    p.add_argument("draft")
    p.set_defaults(func=cmd_wiki_apply)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if getattr(args, "root_override", None):
        args.root = args.root_override
    return args.func(args)
