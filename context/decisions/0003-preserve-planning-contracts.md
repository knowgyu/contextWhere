# Decision 0003: Preserve contracts, not generated OMX plans

Date: 2026-07-29

## Decision

Keep durable product decisions in `docs/`, `context/decisions/`, the handoff, and
tests. Do not version generated `.omx/` planning, review, or runtime artifacts.

## Preserved contracts

- `ingest` never mutates `work_wiki/`.
- `wiki draft` records evidence IDs, targets, before hashes, proposed changes,
  confidence, and policy reasons without changing canonical wiki files.
- `wiki apply` is the only canonical wiki mutation path. It is explicit,
  deterministic, reversible, and writes before/after audit evidence.
- Missing providers return structured unavailable results and remain safe to
  continue; missing MailWhere storage must not create DB/WAL/SHM files.
- OfficeWhere accepts loopback URLs only and refuses broad empty-query sweeps.
- The end-to-end fixture gate remains:
  `init -> ingest -> query -> wiki draft -> wiki apply -> lint`.
- Context packs remain metadata-first and scoped by tenant, source locator,
  freshness, sensitivity, and included/omitted reasons.
- Git capture failures are visible, unknown sensitivity fails closed, and
  graph/vector expansion remains deferred.

## Rationale

The maintained tests and current design documents now enforce these contracts.
Keeping older generated plans beside them duplicated guidance, retained retired
`where-skills` paths, and let stale workflow text compete with shipped behavior.
