# contextWhere Work Wiki Rules

This wiki is maintained by LLM agents and automation. Humans may review and correct it, but routine upkeep should be automated.

## Layers

- Raw sources are immutable. Never edit original mail, document, or code evidence.
- Evidence records store source IDs, snippets, metadata, timestamps, sensitivity, and provenance.
- Wiki pages are compiled knowledge. They may be rewritten by agents when evidence changes.

## Agent rules

1. Read `index.md` before answering or editing.
2. Prefer updating existing pages over creating duplicates.
3. Every important claim must include evidence IDs or be marked `needs_review`.
4. Do not invent facts. If evidence is weak, mark confidence low.
5. Do not open mail/documents or perform OS-visible actions automatically.
6. Keep pages concise and linked.
7. Log ingest, query, lint, merge, and deletion-cascade events in `log.md`.
8. If new evidence contradicts old content, preserve the contradiction and mark affected pages `needs_review`.

## Page frontmatter template

```yaml
---
type: project|person|decision|system|procedure|meeting|concept|session
status: active|stale|archived|needs_review
sensitivity: public|internal|confidential|secret
source_count: 0
evidence_ids: []
last_verified: YYYY-MM-DD
stale_after: YYYY-MM-DD
confidence: low|medium|high
related: []
---
```
