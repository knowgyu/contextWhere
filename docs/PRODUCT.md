# contextWhere product brief

## Positioning

contextWhere is a local-first workspace context OS for agents. It turns scattered work surfaces into source-backed evidence, maintains a Markdown work wiki, and builds small context packs for the current task.

It is not a generic vector database, not a MailWhere/OfficeWhere-only app, and not a prompt-token maximizer.

## Primary users

- A developer/operator working across many repos, `.omx` folders, agent sessions, mail, documents, GitHub, and deployment systems.
- Agents that need the user's actual work context instead of generic advice.
- Small technical workflows that need local-first evidence, auditability, and selective retrieval.

## Product promises

- **Workspace-wide**: repo `.omx`, Codex/OMX/Claude/Gemini sessions, git/GitHub, Jenkins/deploy, mail, and documents are all valid providers.
- **Scoped**: tenant/scope/sensitivity/freshness decide what is eligible for a task.
- **Evidence-backed**: wiki claims and context packs point back to source locators/evidence IDs.
- **Automation-first**: capture, draft, lint, and pack generation should run with minimal user babysitting.
- **Action-safe**: opening mail/docs, replying, moving, deleting, reindexing, or triggering deploys requires explicit approval.

## Current foundation through v0.15.0

- Python/SQLite CLI with local evidence ledger.
- MailWhere/OfficeWhere read-only adapters and provider matrix.
- Sanitized evidence ingest with omitted-field policy.
- Wiki draft/apply safety boundary and lint.
- CLI agent session capture.
- Deterministic entity/relationship seed extraction.
- Recall bundles, backup/restore, status, `run`/`daily`, and autostart planning.
- MailWhere file-link evidence and selective OfficeWhere policy.

## Corrected roadmap

### 0.11.x — workspace context OS semantics

- Add tenant/scope/source-locator vocabulary to evidence and generated artifacts.
- Add provider registry entries for agent sessions, repo/git/GitHub, Jenkins/deploy, MailWhere, and OfficeWhere.
- Add context pack generation as the main runtime output.
- Update docs/install flow so the product feels plugin-like after first approval.

### 0.12.x — automatic local capture

- Capture `.omx` plans/logs/state and Codex/OMX session summaries from local files.
- Add import surfaces for Claude Code and Gemini logs where locally available.
- Add git commit/branch/tag/diff evidence capture.
- Keep raw prompts and sensitive local paths redacted by default.

### 0.13.x — external work-system providers

- Add GitHub issue/PR/release evidence through explicit auth/config.
- Add Jenkins/deploy runbook/job evidence through read-only provider contracts.
- Keep build/deploy triggers action-gated.

### 1.0 — stable local-first context platform

- Stable provider contract and migration policy.
- Context pack CLI/tool/MCP surface.
- Markdown wiki governance and lint gates.
- Backup/restore and audit completeness.
- Optional graph/vector acceleration only where it improves real routing quality.

## Provider-specific policy

- **MailWhere**: incremental polling is appropriate; keep sanitized mail/task/thread summaries, decisions, and file hints.
- **OfficeWhere**: do not mirror all documents; use explicit query, mail-linked file hints, snippets, metadata, and source locators.
- **Agent sessions**: first-class; summarize decisions, constraints, changed files, verification, and follow-ups.
- **Git/GitHub/Jenkins**: first-class; use read-only evidence by default, require approval for mutating actions.

## v0.15.0 implementation note

Implemented scope-first runtime semantics:

- `contextwhere context pack` builds small source-backed bundles with tenant/scope filters, source locators, included reasons, and omitted-context counts.
- `contextwhere capture-local --git --omx` captures read-only local git and `.omx` evidence with repo scope metadata.
- Provider matrix now describes agent-session, repo-state, git, GitHub, Jenkins/deploy, MailWhere, OfficeWhere, and manual/wiki boundaries.
- Graph/vector remain deferred until scoped packs are not enough.

## Return-to-work briefing

`return-to-work ingest|brief` packages a chosen absence period into a source-backed Markdown/JSON draft. Its thin manifest accepts MailWhere export JSON, pasted text, and explicit `.txt`/`.md` documents. It reuses the evidence ledger rather than adding a batch table or graph/vector dependency.

The feature preserves product safety boundaries: Outlook COM stays behind MailWhere, locator/hash retention is the default, raw copies require `--retain-raw`, imported instructions remain inert evidence, and generated briefs never mutate the canonical work wiki automatically. Existing `daily`, `run`, and `maintain` workflows keep their current behavior.

The stable draft paths are `.contextwhere/drafts/return-to-work/<batch_id>.md` and `.json`.
