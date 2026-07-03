# Decision 0002: Reframe contextWhere as a workspace context OS

Date: 2026-07-03

## Decision

contextWhere is not a MailWhere/OfficeWhere companion app. It is a local-first workspace context OS that gathers source-backed evidence from many work surfaces, keeps tenant/scope boundaries, maintains a Markdown wiki, and builds small context packs for agents.

## Drivers

1. The user works across many repos and tools, so repo-local `.omx` and per-agent memories currently drift apart.
2. Agents need real work context for mail, GitHub, Jenkins/deploy, and project decisions instead of generic answers.
3. Full-context prompting and blanket document ingestion are both too noisy and too risky.
4. The user wants automation, not manual daily wiki bookkeeping.

## Consequences

- MailWhere and OfficeWhere remain important optional providers, but the core architecture must support agent sessions, git/GitHub, Jenkins/deploy, and repo-local state as first-class sources.
- The next implementation should prioritize scope/tenant metadata and context pack generation before deeper provider-specific features.
- OfficeWhere should stay selective: file links, explicit queries, snippets, and source locators instead of full document mirroring.
- Graph/vector memory remains an accelerator, not a foundation requirement.

## Rejected

- Mail+Office-only product boundary: too narrow for the stated final goal.
- Single global memory bucket: violates tenant/scope separation and prompt budget control.
- Always-on RAG over every raw document: too opaque, expensive, and hard to govern.
- Manual wiki-only workflow: conflicts with the automation requirement.
