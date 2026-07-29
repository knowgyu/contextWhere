---
type: system
status: active
sensitivity: confidential
source_count: 2
evidence_ids:
  - local:MailWhere/docs/ARCHITECTURE.md
  - local:contextWhere/src/contextwhere/providers/mailwhere.py
last_verified: 2026-07-29
stale_after: 2026-10-29
confidence: high
related:
  - ../projects/contextwhere.md
---

# MailWhere

MailWhere is the read-only Outlook mail mirror, task state, and SQLite/FTS5 search provider. contextWhere consumes its sanitized CLI/export contract and never calls Outlook COM.

## Desired role in contextWhere

- Provide sanitized mail/task/review/evidence results through `MailWhere.Cli`.
- Hide Outlook COM, deduplication, FTS, and privacy details behind a stable provider contract.
- Return local task/review IDs; bounded mail snippets remain an explicit `search-mail` surface and Outlook StoreID/EntryID stay internal.
- Avoid mutation tools by default.

## Integration stance

Do not directly mutate mail. Do not copy the full mail corpus into contextWhere. Raw source opening remains an explicit MailWhere action.
