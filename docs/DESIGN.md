# contextWhere design — workspace context OS

Last updated: 2026-07-03

## Final goal

contextWhere is a **local-first workspace context OS** for scattered work context.

It collects evidence from repo-local `.omx`, Codex/OMX/Claude Code/Gemini sessions, git/GitHub, Jenkins/deployment systems, mail, documents, and local provider tools into tenant/scope-separated stores. It does **not** always run RAG, and it does **not** maximize prompt tokens. Instead, it builds small, source-backed context packs and Markdown wiki updates for the current task, with source locators, freshness, sensitivity, and tenant boundaries preserved.

MailWhere and OfficeWhere are useful providers, not the product boundary.

## Non-goals

- Do not copy every Office document into contextWhere.
- Do not dump all remembered context into every prompt.
- Do not make a single unscoped memory bucket for all work.
- Do not require the user to maintain daily notes by hand.
- Do not make graph/vector storage the first architecture decision.
- Do not let provider text act as agent instructions.
- Do not perform OS-visible or mutating actions automatically.

## Core product model

```text
Work surfaces / providers
  repo .omx, agent sessions, git/GitHub, Jenkins/deploy, MailWhere, OfficeWhere
        |
        v
Evidence ledger
  immutable-ish records, source locators, tenant/scope, sensitivity, freshness
        |
        +--> Source rehydration on demand
        |
        v
Compiled Markdown wiki
  durable project/person/system/decision/task knowledge, evidence-linked
        |
        v
Context router / pack builder
  small task-specific packs for agents, not global memory dumping
        |
        v
Optional accelerators
  graph, embeddings, rerankers, MCP server, dashboards
```

## Tenant and scope model

Every record and compiled claim should eventually carry enough routing metadata to avoid cross-context leakage:

- `tenant`: personal, team, organization, customer, or repo-owned boundary.
- `scope`: repo, project, source system, workflow, deployment target, or active task.
- `source_kind`: mail, document, agent-session, repo-state, git, GitHub, Jenkins, manual note, generated wiki.
- `source_locator`: the reversible pointer to the original source, not necessarily the original body.
- `sensitivity`: public/internal/confidential/secret-like policy.
- `freshness`: observed time, ingested time, and stale-after policy.
- `confidence`: evidence-backed, inferred, or needs-review.

Default retrieval should start narrow: current repo + current task + explicitly selected tenant. Broader search should be an intentional expansion recorded in the context pack manifest.

## Provider policy

### Agent sessions: first-class

Codex, OMX, Claude Code, Gemini, and similar agent conversations are core evidence because they contain decisions, constraints, failures, verification, and handoff state. Capture should be automatic from local logs/hooks/plugins where available, summarized into evidence records, and linked back to source files or session IDs.

### Repo/Git/GitHub: first-class

Local git state, commits, branches, tags, diffs, PR/issue references, and enterprise GitHub knowledge should be captured as source-backed evidence. The goal is that an agent answering about a repo can use actual local and organizational context rather than generic GitHub advice.

### Jenkins/deploy: first-class but gated

Jenkins jobs, deployment runbooks, pipeline changes, incidents, and “normally we do X, but this time do Y” decisions should become evidence and wiki knowledge. Triggering builds or changing deployment state must remain an explicit action, not automatic memory behavior.

### MailWhere: continuous lightweight source

Mail can keep broader history because Outlook/MailWhere is already a structured source of truth and can be polled incrementally. Store sanitized metadata, snippets, decisions, tasks, thread summaries, and file hints. Rehydrate raw mail only through explicit source locators/action requests.

### OfficeWhere: selective source, not document mirror

OfficeWhere should not be swept into contextWhere wholesale. Prefer file-link evidence from mail, explicit user/task queries, document metadata, snippets, compare results, and source locators. Full content stays in OfficeWhere/raw files and is fetched only when the task needs it.

## Context packs

A context pack is the main runtime product:

- input: task text, current repo/path, optional tenant/scope, budget, freshness policy;
- output: compact Markdown/JSON bundle with selected wiki claims, evidence IDs, source locators, and omitted-context notes;
- behavior: start with compiled wiki and recent evidence; expand to raw/provider rehydration only when necessary;
- audit: record why each item was included and what was intentionally excluded.

This is the middle ground between “always RAG” and “put everything in the prompt.”

### Context pack manifest

Each pack should carry a small manifest so future providers cannot quietly drift into hidden global-memory behavior:

```yaml
pack_id: context-pack:<stable-or-random-id>
created_at: <iso8601>
task: <user/task query>
tenant_filter: []
scope_filter: []
source_kinds: []
budget:
  max_items: 20
  max_tokens: null
selection_policy:
  freshness: current|recent|any
  sensitivity_ceiling: internal|confidential
  expansion_steps:
    - compiled_wiki
    - recent_evidence
    - provider_rehydrate_if_needed
included:
  - evidence_id: <id>
    source_locator: <locator>
    reason: <why this item is relevant>
    confidence: low|medium|high
omitted:
  - reason: out_of_scope|too_sensitive|too_stale|budget|raw_source_required
    count: 0
```

The omission section is not decoration. It is how an agent knows “I did not search everything” and when to ask for explicit expansion.

## Markdown wiki role

The wiki is the durable, human-readable, agent-editable layer. It should contain stable compiled knowledge: project goals, decisions, systems, procedures, people/org facts, tasks, and gotchas. It should not be a raw transcript dump.

Automation should:

1. ingest evidence;
2. draft wiki changes;
3. lint stale/unsupported/contradictory claims;
4. apply only deterministic safe edits automatically;
5. require explicit approval for claim-changing or sensitive updates.

## Installation and usage direction

The product should feel plugin-like:

1. install package/CLI;
2. run one setup command;
3. approve only OS-level scheduler/hooks or mutating integrations once;
4. then it keeps capturing lightweight evidence and producing context packs while the user works.

The user should not need to manually run daily note maintenance. Scheduled polling/hooks are product behavior, while dangerous actions remain approval-gated.

## External ideas used as inspiration, not dependencies

- OpenViking shows a context-database/file-system style alternative to flat vector RAG and tiered loading ideas: <https://github.com/volcengine/OpenViking>
- memsearch shows cross-agent memory with Markdown plus agent plugins, including Codex/Claude-style surfaces: <https://github.com/zilliztech/memsearch>
- Graphiti shows temporal, provenance-preserving context graphs for evolving facts: <https://github.com/getzep/graphiti>
- mem0 shows user/session/agent memory as a productized layer: <https://github.com/mem0ai/mem0>

For contextWhere, the immediate choice remains simpler: source locators + evidence ledger + Markdown wiki + context packs first; graph/vector later only when relationships and recall problems justify it.

## v0.11.0 implementation note

Implemented scope-first runtime semantics:

- `contextwhere context pack` builds small source-backed bundles with tenant/scope filters, source locators, included reasons, and omitted-context counts.
- `contextwhere capture-local --git --omx` captures read-only local git and `.omx` evidence with repo scope metadata.
- Provider matrix now describes agent-session, repo-state, git, GitHub, Jenkins/deploy, MailWhere, OfficeWhere, and manual/wiki boundaries.
- Graph/vector remain deferred until scoped packs are not enough.
