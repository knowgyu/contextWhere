---
type: project
status: active
sensitivity: internal
source_count: 3
evidence_ids:
  - autoresearch:2026-work-context-llm-wiki-report
  - decision:0001-project-direction
  - decision:0002-workspace-context-os
last_verified: 2026-07-03
stale_after: 2026-08-03
confidence: high
related:
  - ../systems/mailwhere.md
  - ../systems/officewhere.md
  - ../systems/cli-agents.md
---

# contextWhere

contextWhere is a local-first workspace context OS. It collects evidence from repo-local `.omx`, agent sessions, git/GitHub, Jenkins/deploy systems, MailWhere, OfficeWhere, and related tools, then maintains evidence-linked Markdown wiki knowledge and task-specific context packs.

## Current thesis

The core product is not mail/document memory. MailWhere and OfficeWhere are optional providers inside a broader scoped evidence system.

Use this order:

1. raw providers/work surfaces;
2. evidence ledger with source locators and tenant/scope metadata;
3. compiled Markdown wiki;
4. context pack router for agents;
5. optional graph/vector only after relationship data justifies it.

## Current foundation status

v0.10.0 provides Python/SQLite CLI foundations: provider ingest, wiki draft/apply boundaries, lint, capture-session, entities, recall bundles, backup/restore, status, `run`/`daily`, autostart planning, and MailWhere file-link evidence.

## Next product goal

Reframe the next slice around workspace context OS semantics:

- tenant/scope/source-locator vocabulary;
- provider registry for agent sessions, repo/git/GitHub, Jenkins/deploy, MailWhere, OfficeWhere;
- context pack generation;
- automatic local capture for `.omx` and agent-session evidence;
- selective OfficeWhere lookup rather than full document mirroring.
