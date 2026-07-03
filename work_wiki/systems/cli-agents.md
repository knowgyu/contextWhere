---
type: system
status: active
sensitivity: internal
source_count: 2
evidence_ids:
  - autoresearch:2026-work-context-llm-wiki-report
  - decision:0002-workspace-context-os
last_verified: 2026-07-03
stale_after: 2026-08-03
confidence: high
related:
  - ../projects/contextwhere.md
---

# CLI Agents

CLI agents include Codex, OMX, Claude Code, Gemini, and similar local coding/research/planning/verification sessions.

## Desired role in contextWhere

Agent sessions are first-class evidence providers. Each meaningful session should produce a durable summary with:

- goal;
- constraints;
- decisions;
- changed files;
- verification evidence;
- unresolved risks;
- follow-ups;
- source locator back to the original session/log when safe.

Stable lessons should be promoted into `procedures/`, `decisions/`, `systems/`, or project pages. Raw prompt logs and sensitive local paths should stay omitted by default.

## Capture stance

Prefer automatic local capture through existing logs/hooks/plugins. The user should not manually maintain daily notes. Context packs should retrieve only the relevant session summaries for the current repo/task/scope.
