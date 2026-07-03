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

## 0.2.0 graph seed

- Evidence rows에서 deterministic entity candidate를 추출한다.
- `entities`, `evidence_entities`, `relationships` SQLite tables를 생성한다.
- `entities extract/list/relationships` CLI로 wiki/agent가 관계 seed를 조회할 수 있다.

## 0.3.0 agent tool gateway

- `tools manifest`로 agent가 호출 가능한 tool 목록과 input schema를 확인한다.
- `tools call`로 query/capture/entities 기능을 JSON object 입력으로 호출한다.
- 정식 MCP/장기 실행 server 이전의 안정적인 CLI tool gateway로 사용한다.

## 0.4.0 local recall bundles

- 반복 query 결과를 `recall_bundles` table에 저장한다.
- bundle은 evidence id 목록, query, search mode, limit을 보존한다.
- 외부 embedding/API 없이 local-first recall 단위를 만든다.

## 0.5.0 audited backup/restore

- `backup create` packages `work_wiki/` and `.contextwhere/` with a manifest.
- `backup restore` validates archive member paths and restores only into an empty or absent root.
- Backup/restore keeps the local-first product deployable without requiring a hosted service.

## 0.6.0 operational status

- `status` gives operators and agents a read-only deployability summary.
- It reports DB/wiki presence, latest ingest, counts, backup count, and lint health.
- The command is safe for missing roots and does not initialize or mutate state.

## 0.7.0 provider compatibility matrix

- `providers matrix` exposes provider contracts as CLI-readable JSON.
- MailWhere and OfficeWhere list live requirements, ingest kinds, and safety boundaries.
- The matrix is static/read-only and complements live `providers health`.

## 0.8.0 daily runner

- `daily` runs init, read-only provider ingest, entity extraction, wiki draft, lint, and status in one command.
- Provider unavailable states are safe structured results, not destructive failures.
- Wiki drafts are created but not applied automatically.

## 0.9.0 autostart installer

- `autostart plan` shows the OS scheduler integration without mutating user state.
- `autostart install` asks Y/N before installing a user-level systemd timer or Windows scheduled task.
- The scheduled job runs `daily`; no custom long-running daemon is owned by contextWhere.

## 0.9.1 OfficeWhere daily policy

- Daily runs do not search OfficeWhere by default.
- OfficeWhere search requires explicit `--officewhere-query`.
- The intended next step is MailWhere-to-OfficeWhere file-link evidence, not full document mirroring.

## 0.10.0 file-link evidence

- MailWhere attachment/file hints create `file_link` evidence records.
- `run` is added as the product-facing alias for scheduled polling; `daily` remains as a compatibility alias.
- OfficeWhere remains opt-in and should be queried from mail-derived file/project hints, not broad document sweeps.

## Roadmap

1. 0.1.x: strengthen provider compatibility, add scheduled ingest examples, broaden wiki operations with the same typed/audited model.
2. 0.2.0: deterministic entity extraction and relationship seed. 0.2.x: richer people/projects/decisions/tasks extraction and promotion workflows.
3. 0.3.0: JSON CLI tool gateway. 0.3.x: MCP server and long-running agent tool surfaces.
4. 0.4.0: local recall bundles. 0.4.x: selective local embedding/vector layer for ambiguous recall.
5. 0.5.0: audited backup/restore foundation.
6. 0.6.0: operational status command.
7. 0.7.0: provider compatibility matrix.
8. 0.8.0: unattended daily runner.
9. 0.9.0: user-level autostart installer.
10. 0.10.0: MailWhere file-link evidence and run alias. 0.10.x: link lookup refinement, migration command, selective local recall.
11. 1.0: stable local-first context platform with documented provider contracts, release artifacts, and migration policy.
