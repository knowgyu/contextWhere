---
type: project
status: active
sensitivity: internal
source_count: 4
evidence_ids:
  - autoresearch:2026-work-context-llm-wiki-report
  - decision:0001-project-direction
  - decision:0002-workspace-context-os
  - local:contextWhere/docs/DESIGN.md
last_verified: 2026-07-29
stale_after: 2026-10-29
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

The current `0.15.1` code provides the scoped evidence ledger, provider ingest, OfficeWhere packaged discovery, wiki draft/apply boundaries, context packs, session and local git/`.omx` capture, recall/backup/status, `run`/`daily`/`maintain`, autostart planning, and return-to-work drafts.

## Remaining product goal

- validate live MailWhere/OfficeWhere paths on the managed Windows PC;
- add approved read-only GitHub/Jenkins providers;
- keep OfficeWhere selective and graph/vector optional.
