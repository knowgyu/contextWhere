# contextWhere product brief

## Positioning

contextWhere turns mail, office documents, and coding-agent sessions into a local-first evidence ledger plus an LLM-maintained Markdown work wiki.

It is not a generic vector database. It separates raw providers, sanitized evidence, compiled wiki knowledge, and future graph/memory layers so work context can be governed, audited, and reused.

## 0.1.0 value proposition

- Safe read-only provider ingest foundation for MailWhere and OfficeWhere.
- SQLite/FTS evidence ledger with provider/source/provenance metadata.
- Agent-safe wiki drafting and audited deterministic apply boundaries.
- CLI session capture for Codex/OMX-style work continuity.
- Lint rules that keep the wiki source-backed and lifecycle-aware.

## Primary users

- A solo operator or small technical team that works across Outlook mail, local Office documents, and CLI coding agents.
- Users who want accumulated context without manually maintaining a daily wiki.

## Safety promise

- No automatic raw mail/document mutation.
- No automatic OS-visible open/reply/delete/reindex actions.
- No provider text is trusted as an instruction.
- Sensitive/raw fields are omitted by default and omissions are auditable.
- Wiki writes are deliberate, constrained, and reversible through audit logs.

## 0.1.1 operational foundation

- Korean README aligned to the final-goal handoff context.
- `contextwhere verify --json` install-time smoke command.
- Cron/systemd schedule examples for Ubuntu-style operations.

## Roadmap

1. 0.1.x: strengthen provider compatibility, add scheduled ingest examples, broaden wiki operations with the same typed/audited model.
2. 0.2.x: entity extraction and relationship tables for people/projects/decisions/tasks.
3. 0.3.x: MCP server and agent tool surfaces.
4. 0.4.x: selective local embedding/vector layer for ambiguous recall.
5. 1.0: stable local-first context platform with documented provider contracts, backup/restore, release artifacts, and migration policy.
