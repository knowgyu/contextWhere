---
type: system
status: active
sensitivity: confidential
source_count: 1
evidence_ids:
  - local:where-skills/docs/mailwhere-provider-contract.md
last_verified: 2026-07-02
stale_after: 2026-08-02
confidence: medium
related:
  - ../projects/contextwhere.md
---

# MailWhere

MailWhere is expected to act as a read-only mail/task/evidence provider backed by Outlook COM and local storage.

## Desired role in contextWhere

- Provide sanitized mail/task/review/evidence results.
- Hide Outlook COM, deduplication, FTS, and privacy details behind a stable provider contract.
- Return source IDs and snippets suitable for wiki evidence links.
- Avoid mutation tools by default.

## Integration stance

Do not directly mutate mail. Do not expose raw body/full addresses/attachments unless explicitly requested and policy allows it.
