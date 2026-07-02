# START HERE — contextWhere handoff

## User intent

The user wants a serious long-term project, not a throwaway MVP, to preserve and operationalize work context across:

- **MailWhere**: Outlook COM-based mail/task/evidence provider.
- **OfficeWhere**: local document provider/search/compare system.
- **CLI coding agents**: Codex/OMX/Claude Code-style sessions, plans, tests, diffs, commits, and decisions.

The user explicitly does **not** want to manually maintain a wiki every day. The desired system should run automatically/agentically: ingest evidence, update a Markdown wiki, lint stale/contradictory pages, and later support graph/memory.

## Key conclusion from research

Do not build “just a vector DB RAG.” Build:

```text
Raw providers -> Evidence ledger/search -> Agent-maintained Markdown Wiki -> Automation/lint -> Optional graph/memory
```

The Markdown wiki is necessary as the durable, human-readable, LLM-editable compiled knowledge layer. The repo/engine is needed for automation: ingest, search, MCP/CLI tools, lint, graph extraction, permissions, and scheduled consolidation.

## Why a repo is needed

A plain Markdown folder can start the habit, but the user wants ongoing automation. The repo should provide:

- provider connectors/adapters for MailWhere and OfficeWhere
- evidence schema and search
- wiki page templates and update rules
- ingest jobs
- weekly/daily lint jobs
- action gates for raw-open/OS-visible actions
- CLI agent session capture
- future MCP server/tools
- future graph/memory layer

## Important design constraints

- Local-first by default.
- Raw mail/doc sources are immutable and should not be edited by LLMs.
- LLM writes only compiled wiki pages and project-owned metadata.
- MailWhere/OfficeWhere should be accessed through provider APIs/contracts, not by directly scraping private DB internals unless explicitly designed as an owned adapter.
- Raw mail body, full addresses, attachments, and sensitive local paths should not be sent to external models by default.
- OS-visible actions such as opening mail/documents, reply/move/delete/reindex must be gated through explicit `action_request` style approval.
- Every important wiki claim should point to evidence IDs.

## Existing local context

Relevant local workspace paths discovered:

- `/home/knowgyu/workspace/MailWhere`
- `/home/knowgyu/workspace/OfficeWhere`
- `/home/knowgyu/workspace/where-skills/docs/mailwhere-provider-contract.md`
- `/home/knowgyu/workspace/where-skills/docs/officewhere-provider-notes.md`

Current research artifacts copied into this repo:

- `context/research/2026-work-context-llm-wiki-report.md`
- `context/research/autoresearch-result.json`

## Suggested next session plan

1. Inspect this folder.
2. Read the research report and wiki rules.
3. Decide repo stack after checking the user's preferred runtime for Windows native PC.
   - Likely candidates: Python + SQLite for portability; optional Node/TypeScript if MCP/tooling ergonomics dominate.
4. Create a 0.1.0 plan/tag strategy.
5. Implement the first skeleton:
   - config
   - evidence schema
   - provider adapter interfaces
   - Markdown wiki writer/validator
   - CLI commands: `init`, `ingest`, `lint`, `query`, `capture-session`
6. Keep MailWhere/OfficeWhere integrations read-only initially.

## Recommended initial product name

`contextWhere`

Working meaning: one place where work context from mail, office documents, and code agents becomes durable and reusable.
