# contextWhere design — workspace context OS

Last updated: 2026-07-29
Version: 0.16.0

## Goal

contextWhere gives agents a local, source-backed memory layer for a workspace without turning every source into a prompt dump. It stores sanitized evidence, derives scoped Context Cards, drafts Markdown updates, and builds small task-specific context packs.

MailWhere and OfficeWhere are providers. They are not the product boundary.

## Storage model

```text
Work surfaces/providers
  -> sanitized evidence ledger with source locators
  -> scoped Context Cards in global home
  -> reviewed Markdown/wiki drafts
  -> task-specific preflight and context packs
```

There are two storage areas:

| Area | Default path | Owns |
| --- | --- | --- |
| Repo state | `<repo>/.contextwhere/` | repo-local evidence DB, wiki drafts, wiki apply audits, backups |
| Global home | `~/.contextwhere/` or `%USERPROFILE%\.contextwhere\` | registry, reusable Context Cards, memory drafts/audits, setup/doctor state |

The repo-local path keeps project evidence close to the repository. The global home keeps reusable memory separate from a single checkout.

## Registry and scope model

`contextwhere registry` records workspaces and repositories in the global home registry. Stable IDs are derived from normalized paths.

Context Cards and preflight lookup use four scope types:

- `global`: applies broadly; key defaults to `default`.
- `workspace`: applies to one workspace path or workspace ID.
- `repository`: applies to one repository.
- `machine`: applies to one device or managed-PC environment.

Default lookup is narrow: global + selected workspace + selected repository + selected machine. Broader lookup must be explicit.

## Context Card envelope

A Context Card is a bounded memory item, not raw chat history. Required fields include:

- `card_id`
- `version`: `context-card-v1` (alias `v1` is accepted)
- `type`: `constraint/preference`, `procedure/runbook`, `decision/ADR`, `incident lesson`, or `machine`
- `summary`
- `scope`
- `status`
- `sensitivity`
- `confidence`
- `evidence_ids` or `evidence`
- `freshness`

Procedure/runbook cards require successful verification metadata and success checks before they can be trusted as reusable procedure memory.

## Lifecycle

Allowed status path:

```text
observed -> candidate -> needs_review -> active -> stale
candidate -> active
candidate -> rejected
active -> superseded
```

Illegal promotions are rejected. `preflight` returns active, non-expired cards only. `rejected`, `superseded`, `stale`, and expired cards stay auditable but are not active guidance.

## Signals and preflight

Signals are sanitized events that can create evidence and candidate cards. Supported use cases include:

- repeated `tool_failure`
- `verified_success`
- `environment_fact`
- user correction
- blocker
- session summary

`contextwhere preflight` returns active scoped cards for a repository/machine. `contextwhere signals preflight` additionally filters procedures by a failure fingerprint. Repeated failures can surface verified procedures after the threshold; they do not execute fallback actions.

## Draft/apply design

Drafts are explicit intermediate artifacts.

- `wiki draft` writes repo-local wiki draft JSON.
- `memory draft` and `drafts create` render Context Cards into target Markdown sections.
- `apply` commands are explicit and audited.
- Apply rejects untrusted draft types, path escapes, before-hash mismatch, missing card/evidence/source-locator data, terminal card statuses, stale freshness, and unsafe content.

This keeps automation useful without letting an agent silently rewrite project knowledge.

## Agent integrations

The integration layer supports Codex, Claude, and Gemini.

- `integrations status` reports availability, marker state, owned helper files, and safe-to-continue status.
- `integrations install` inserts a small bounded marker into the user instruction file and writes one owned helper command/skill file.
- `integrations uninstall` removes only the contextWhere marker and owned helper files.
- `setup --install-integrations` can install all bridges after setup.

The bridge is advisory: it asks agents to run preflight before repeated failures and capture sanitized signals after verified outcomes. It does not override the current repository's code or instructions.

## Provider policy

- **MailWhere**: read-only mail/task/thread source. contextWhere consumes sanitized JSON exports; Outlook COM stays behind MailWhere.
- **OfficeWhere**: selective loopback/local document search by explicit query or file hint; no full-corpus mirroring.
- **Agent sessions**: capture decisions, constraints, blockers, verification, and handoff state, not raw prompts.
- **Git/GitHub/Jenkins/deploy**: read-only evidence by default; builds, deployments, labels, comments, and other mutations require explicit action.

## Deferred by design

- No graph/vector store until scoped evidence and cards are not enough.
- No live provider polling in `maintain` by default.
- No automatic wiki application for claim-changing updates.
- No company-PC validation claims without running the smoke checklist on that machine.
