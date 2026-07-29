---
type: system
status: active
sensitivity: confidential
source_count: 3
evidence_ids:
  - local:OfficeWhere/docs/provider-contract.md
  - decision:0002-workspace-context-os
  - local:contextWhere/src/contextwhere/providers/officewhere.py
last_verified: 2026-07-29
stale_after: 2026-10-29
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

Packaged OfficeWhere uses a dynamic loopback port. contextWhere consumes the user-scoped `provider-discovery.json`, rejects non-loopback URLs, and falls back safely when a discovery file is stale. Explicit `--officewhere-base-url` remains available.
