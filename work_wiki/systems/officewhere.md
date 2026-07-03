---
type: system
status: active
sensitivity: confidential
source_count: 2
evidence_ids:
  - local:where-skills/docs/officewhere-provider-notes.md
  - decision:0002-workspace-context-os
last_verified: 2026-07-03
stale_after: 2026-08-03
confidence: high
related:
  - ../projects/contextwhere.md
---

# OfficeWhere

OfficeWhere is a read-oriented local document provider for search, files, duplicates, groups, and compare operations.

## Desired role in contextWhere

OfficeWhere should provide selective document evidence:

- explicit user/task query results;
- mail-derived file-link lookup;
- metadata/snippets/compare results;
- source locators for later user-approved opening or deeper inspection.

## Integration stance

Do not mirror the full document corpus into contextWhere. Do not store raw document bodies or sensitive full local paths by default. Do not run open/show/reindex/rescan/delete automatically.
