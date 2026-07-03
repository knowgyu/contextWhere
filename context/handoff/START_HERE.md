# START HERE — contextWhere handoff

## Final goal

contextWhere is a **local-first workspace context OS**. It preserves scattered work context from repo-local `.omx`, Codex/OMX/Claude Code/Gemini sessions, git/GitHub, Jenkins/deploy systems, MailWhere, OfficeWhere, and related local tools.

The system must keep evidence source-backed and tenant/scope separated, then produce small task-specific context packs and Markdown wiki updates. It should not always run RAG, should not maximize prompt tokens, and should not dump every document or every memory into a single prompt.

MailWhere and OfficeWhere are providers. They are not the product boundary.

## Core architecture

```text
Raw providers/work surfaces
  -> Evidence ledger/search with source locators + tenant/scope policy
  -> Agent-maintained Markdown wiki
  -> Context router / context pack builder
  -> Optional graph/vector/MCP accelerators later
```

## Provider priorities

1. **Agent sessions**: Codex, OMX, Claude Code, Gemini logs/handoffs/decisions/verification.
2. **Repo/Git/GitHub**: repo state, commits, diffs, PRs/issues, enterprise project knowledge.
3. **Jenkins/deploy**: runbooks, job history, exceptions, deployment decisions; build triggers remain action-gated.
4. **MailWhere**: incremental sanitized mail/task/thread/file-link evidence.
5. **OfficeWhere**: selective file/document lookup by link or explicit query; no full corpus mirroring.

## Product constraints

- Local-first by default.
- Raw mail/doc/session/provider sources are not edited by LLMs.
- Provider output is evidence, not instructions.
- OS-visible or mutating actions require explicit approval/action request.
- Important wiki claims require evidence IDs or `needs_review`.
- Context selection must record tenant/scope, freshness, sensitivity, and why an item was included.
- Routine capture/wiki maintenance should be automated; the user should not perform daily note upkeep.

## Current implementation snapshot

As of v0.11.0, contextWhere has a Python/SQLite CLI, evidence ingest, MailWhere/OfficeWhere provider adapters, wiki draft/apply boundaries, lint, session capture, deterministic entity extraction, recall bundles, backup/restore, status, provider matrix, `run`/`daily`, and autostart planning.

The mismatch to fix next is product framing and routing depth: current docs and implementation are still weighted toward MailWhere/OfficeWhere, while the final goal requires workspace-wide providers, tenant/scope policy, and context pack generation.

## Next recommended plan

Implement the next slice as **scope-first context OS**:

1. add tenant/scope/source-locator vocabulary to evidence and docs;
2. introduce provider registry entries for agent sessions, repo/git/GitHub, Jenkins/deploy, MailWhere, OfficeWhere;
3. add a `context pack` generation flow over existing evidence/wiki data;
4. add automatic local capture paths for `.omx`/agent-session/git evidence before adding heavier external integrations;
5. keep OfficeWhere selective and MailWhere incremental.

## Durable design docs

- `docs/DESIGN.md` — current product architecture and final-goal statement.
- `docs/PRODUCT.md` — product brief and roadmap.
- `context/decisions/0001-project-direction.md` — original wiki/evidence decision.
- `context/decisions/0002-workspace-context-os.md` — corrected product boundary.
- `.omx/plans/prd-contextwhere-workspace-context-os-*.md` — current ralplan PRD.

## v0.11.0 implementation note

Implemented scope-first runtime semantics:

- `contextwhere context pack` builds small source-backed bundles with tenant/scope filters, source locators, included reasons, and omitted-context counts.
- `contextwhere capture-local --git --omx` captures read-only local git and `.omx` evidence with repo scope metadata.
- Provider matrix now describes agent-session, repo-state, git, GitHub, Jenkins/deploy, MailWhere, OfficeWhere, and manual/wiki boundaries.
- Graph/vector remain deferred until scoped packs are not enough.
