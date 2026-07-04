from __future__ import annotations

import argparse
import hashlib
import json
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
