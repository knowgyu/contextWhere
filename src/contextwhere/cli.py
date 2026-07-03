from __future__ import annotations

import argparse
import json
import sys
import zipfile
from pathlib import Path
from typing import Any
from dataclasses import dataclass, field

from .capture import capture_session_file, capture_session_text
from .config import ensure_dirs, resolve_paths
from .db import init_db, insert_evidence, log_ingest, query_evidence_with_mode
from .providers.base import ProviderResult, load_fixture_records
from .providers.mailwhere import MailWhereProvider
from .providers.officewhere import OfficeWhereProvider
from .schemas import evidence_from_item
from .wiki import apply_wiki_draft, create_wiki_draft, lint_wiki
from .verify import run_verify
from .entities import extract_entities, list_entities, list_relationships
from .tools import call_tool, manifest as tools_manifest, parse_input as parse_tool_input
from .recall import create_bundle, list_bundles, show_bundle
from .backup import create_backup, restore_backup
from .status import project_status


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


def cmd_providers(args: argparse.Namespace) -> int:
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
        return IngestOutcome(
            provider=args.provider,
            records=load_fixture_records(args.provider, Path(args.fixture), default_kind=args.kind or "item"),
            details={"fixture": str(args.fixture)},
        )
    if args.provider == "mailwhere":
        provider = MailWhereProvider(command=args.mailwhere_command, db=args.mailwhere_db)
        records = []
        unavailable = []
        details: dict[str, Any] = {}
        for result, kind in ((provider.list_tasks(limit=args.limit), "task"), (provider.list_review_candidates(limit=args.limit), "review_candidate")):
            details[kind] = provider_telemetry(result)
            if result.ok:
                records.extend(evidence_from_item("mailwhere", item, kind) for item in result.items)
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
        return IngestOutcome(provider="mailwhere", records=records, details=details)
    if args.provider == "officewhere":
        provider = OfficeWhereProvider(base_url=args.officewhere_base_url)
        return outcome_from_provider_result(provider.search(args.query or "", limit=args.limit), "document")
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
    ids = insert_evidence(paths.db_path, [record])
    emit({"ok": True, "evidence_ids": ids}, args.json)
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
    p.add_argument("action", choices=["health", "manifest"])
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
