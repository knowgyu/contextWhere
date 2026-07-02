---
type: project
status: active
sensitivity: internal
source_count: 1
evidence_ids:
  - autoresearch:2026-work-context-llm-wiki-report
last_verified: 2026-07-02
stale_after: 2026-08-02
confidence: high
related:
  - ../systems/mailwhere.md
  - ../systems/officewhere.md
  - ../systems/cli-agents.md
---

# contextWhere

contextWhere is the planned automation engine and LLM-maintained work wiki for preserving work context from mail, office documents, and coding agents.

## Current thesis

Use MailWhere and OfficeWhere as read-only evidence providers, then let agents maintain a compiled Markdown wiki with source-backed claims. Add search/lint/automation first, then graph/memory when relationship data accumulates.

## Current foundation status

0.1.0 now provides the first project skeleton: versioned Python CLI, SQLite evidence schema, read-only provider adapters, constrained wiki draft/apply boundaries, wiki lint, capture-session, tests, and release/operations docs.

## Next release-hardening goal

Exercise live MailWhere/OfficeWhere environments, add scheduled ingest examples, and expand typed wiki operations without weakening the audited apply boundary.
