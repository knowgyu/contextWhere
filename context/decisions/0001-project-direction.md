# Decision 0001: Build contextWhere as an automation engine around an LLM-maintained Markdown wiki

Date: 2026-07-02

## Decision

Start `contextWhere` as a dedicated project folder/repo for automating work-context capture across MailWhere, OfficeWhere, and CLI coding agents.

The system should not rely on the user manually maintaining notes. It should provide automation around a compiled Markdown wiki and evidence layer.

## Rationale

A Markdown wiki alone is simple and durable, but long-term use requires ingest, search, lint, consolidation, provider adapters, action gates, and eventually graph/memory.

## Rejected

- Pure vector DB RAG as the central system: too opaque and hard to govern/delete/debug.
- Manual-only Obsidian vault: too much human bookkeeping.
- Immediate full graph system: likely premature before evidence/entities accumulate.

## Next

Create project skeleton, versioning strategy, provider adapter contracts, evidence schema, and first automation commands.
