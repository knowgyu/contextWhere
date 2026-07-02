---
type: procedure
status: active
sensitivity: internal
source_count: 1
evidence_ids:
  - autoresearch:2026-work-context-llm-wiki-report
last_verified: 2026-07-02
stale_after: 2026-08-02
confidence: medium
related:
  - source-ingest.md
---

# Wiki Lint Procedure

Periodic lint should check:

- pages without evidence
- stale pages past `stale_after`
- duplicate people/projects/organizations
- contradictions between new evidence and compiled pages
- orphan pages not linked from index or related pages
- unsupported claims after deletion cascade
- missing `index.md` entries
