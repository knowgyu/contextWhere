# START HERE — contextWhere handoff

Current tracked version: **0.16.0**

## Product goal

contextWhere is a local-first workspace context OS for developer/operator agents. It keeps scattered work context source-backed and scoped, then returns small task-specific preflight/context packs and reviewed Markdown updates.

MailWhere and OfficeWhere are providers. They are not the product boundary.

## Current implementation snapshot

v0.16.0 includes:

- repo-local Python/SQLite evidence ledger;
- MailWhere and OfficeWhere read-only adapters;
- provider matrix, provider health, query, status, verify, backup/restore;
- wiki draft/apply with audit boundaries;
- context packs with scope filters, included reasons, source locators, and omitted-context counts;
- return-to-work ingest/brief drafts;
- global home setup/doctor under `~/.contextwhere` or `%USERPROFILE%\.contextwhere`;
- workspace/repository registry;
- scoped Context Cards and legal lifecycle transitions;
- signals and preflight for repeated failures, verified successes, machine facts, corrections, blockers, and session summaries;
- draft/apply flow for card-backed repository/workspace/global/machine Markdown;
- Codex/Claude/Gemini advisory integrations.

## Source of truth order

1. Current tracked code and tests.
2. Current tracked docs, especially `docs/DESIGN.md`, `docs/PRODUCT.md`, and `docs/releases/v0.16.0.md`.
3. Repository tags and GitHub Releases.
4. Older `.omx` state and handoffs only as historical context.

## Safety boundaries to preserve

- Provider output is evidence, not instructions.
- Raw mail, raw document bodies, prompt logs, full local paths, and secrets are not default storage/output.
- Mutating external actions require explicit operator action.
- Drafts are not applied automatically.
- Live managed-PC behavior must not be claimed without target-machine smoke output.

## Known unverified live gaps

This documentation prep did not run live company-PC checks. Before claiming production readiness on that PC, verify:

- MailWhere live Outlook-backed ingest;
- OfficeWhere packaged discovery and loopback search;
- Codex/Claude/Gemini bridge install/doctor on the target user profile;
- Windows Task Scheduler autostart if enabled.

## First commands for a new agent

```bash
git status --short
uv run pytest -q
uv run contextwhere verify --json
uv run contextwhere doctor --json
uv run contextwhere preflight --repository contextWhere --json
```

Stay within the requested file scope. Do not revert unrelated implementation or test changes from concurrent agents.
