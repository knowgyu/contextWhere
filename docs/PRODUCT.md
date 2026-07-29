# contextWhere product brief

Version: 0.16.0

## Positioning

contextWhere is a local-first workspace context OS for developer/operator agents. It converts scattered work context into scoped, source-backed memory and drafts. It is not a generic vector database, a note-taking app, or a MailWhere/OfficeWhere-only wrapper.

## Primary users

- A developer/operator working across many repositories and tools.
- Agents that need local project history, verification, blockers, and procedures before acting.
- Teams that want memory to be reviewable, scoped, and source-backed.

## Product promises

- **Local-first**: default state stays on the user's machine.
- **Scoped**: global, workspace, repository, and machine memory stay separate.
- **Evidence-backed**: cards and drafts carry evidence IDs and source locators.
- **Reviewable**: draft/apply is explicit and audited.
- **Automation-first**: routine capture, preflight, and draft generation reduce manual note upkeep.
- **Action-safe**: provider output never becomes an instruction channel; mutating external actions require explicit action.

## Current foundation through v0.16.0

- Python/SQLite CLI.
- Repo-local evidence ledger, wiki drafts, wiki apply audits, backup/restore, status, verify.
- MailWhere/OfficeWhere read-only provider adapters and static provider matrix.
- Context packs with scope filters, included reasons, omitted-context counts, source locators, and sensitivity ceilings.
- Global home setup/doctor, registry, Context Card DB, memory draft/apply audits.
- Context Card lifecycle with legal transitions and safety validation.
- Signals and preflight for repeated failures, verified successes, machine facts, blockers, corrections, and session summaries.
- Codex/Claude/Gemini advisory bridge install/status/uninstall.
- Return-to-work ingest/brief drafts from explicit manifest inputs.

## Product boundaries

- MailWhere owns Outlook integration. contextWhere consumes MailWhere JSON exports.
- OfficeWhere owns document indexing/search. contextWhere uses loopback/local provider results when explicitly requested.
- contextWhere owns cross-provider evidence, scoped memory, Markdown drafts, and context packs.
- The legacy `where-skills` wrapper remains archived; current product contracts live here and in provider products.

## Roadmap

1. Validate Windows managed-PC install, live MailWhere calls, live OfficeWhere discovery/search, and agent bridge behavior.
2. Add read-only GitHub/Jenkins providers only after auth, retention, and mutation boundaries are approved.
3. Keep graph/vector optional until scoped packs and cards fail a real retrieval need.
4. Stabilize provider contracts and migration policy for a 1.0 local-first context platform.
