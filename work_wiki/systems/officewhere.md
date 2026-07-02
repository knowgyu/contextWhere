---
type: system
status: active
sensitivity: confidential
source_count: 1
evidence_ids:
  - local:where-skills/docs/officewhere-provider-notes.md
last_verified: 2026-07-02
stale_after: 2026-08-02
confidence: medium
related:
  - ../projects/contextwhere.md
---

# OfficeWhere

OfficeWhere is expected to act as a read-oriented local document provider for search, files, duplicates, groups, and compare.

## Desired role in contextWhere

- Provide document evidence: file IDs, titles, snippets, timestamps, duplicate/version grouping, and compare results.
- Keep local paths and snippets sensitive.
- Avoid automatic open/show/reindex/rescan/delete operations.

## Integration stance

Use provider APIs where possible. Treat document paths and snippets as local sensitive data.
