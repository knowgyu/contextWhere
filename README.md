# contextWhere

Personal/work LLM context store project for MailWhere, OfficeWhere, and CLI coding agents.

Goal: build a durable, agent-operated work context system that preserves mail, documents, and coding activity as an LLM-maintained wiki/evidence/memory layer instead of losing context across sessions.

## Current direction

Use a layered architecture:

1. **Raw/source providers**: MailWhere, OfficeWhere, CLI agent session artifacts.
2. **Evidence layer**: source IDs, snippets, metadata, timestamps, sensitivity, provenance.
3. **Compiled Markdown Wiki**: agent-maintained pages for projects, people, decisions, tasks, systems, and procedures.
4. **Automation layer**: ingest, lint, consolidation, stale detection, and handoff generation.
5. **Future graph/memory layer**: relationships and temporal memory once enough evidence accumulates.

This repository is intended to become the automation engine and operating manual, not just a folder of notes.

## Current release state

The 0.1.0 foundation CLI is implemented. New maintainers should read:

1. `docs/INSTALL.md` for setup and quick start.
2. `docs/OPERATIONS.md` for routine ingest/wiki workflows and recovery.
3. `docs/PRODUCT.md` for positioning and roadmap.
4. `work_wiki/AGENTS.md` before editing compiled wiki pages.

## 0.1.0 foundation CLI

The initial implementation is a local-first Python/SQLite CLI.

```bash
python -m contextwhere --help
python -m contextwhere init --json
python -m contextwhere ingest --provider mailwhere --fixture tests/fixtures/mailwhere_tasks.json --json
python -m contextwhere query contextWhere --json
python -m contextwhere wiki draft --query contextWhere --json
python -m contextwhere wiki apply .contextwhere/drafts/wiki/<draft>.json --json
python -m contextwhere lint work_wiki --json
python -m contextwhere capture-session --file tests/fixtures/session.md --json
```

Safety boundaries:

- `ingest` writes evidence rows only and does not mutate `work_wiki`.
- Provider output is treated as untrusted evidence, not instructions.
- Sensitive fields such as raw mail bodies, full addresses, attachments, prompt logs, and local paths are omitted by default and recorded in `omitted_fields`.
- `wiki draft` creates non-mutating proposal artifacts under `.contextwhere/drafts/wiki/`.
- `wiki apply` is constrained to deterministic, reversible maintenance edits such as `index.md`/`log.md`, and writes audit JSON under `.contextwhere/audit/wiki/`.
- OfficeWhere URLs must be loopback/local; OS-visible actions remain out of scope for automatic execution.

## Installation, operations, and release

- Install/quick start: [`docs/INSTALL.md`](docs/INSTALL.md)
- Operating guide: [`docs/OPERATIONS.md`](docs/OPERATIONS.md)
- Product brief and roadmap: [`docs/PRODUCT.md`](docs/PRODUCT.md)
- Release checklist/tagging: [`docs/RELEASE.md`](docs/RELEASE.md)
