# contextWhere

contextWhere is a local-first workspace context OS for developer/operator agents. It collects sanitized evidence from repo state, agent sessions, MailWhere, OfficeWhere, GitHub/Jenkins-style work systems, and explicit notes, then turns that evidence into scoped Context Cards, Markdown drafts, and compact context packs.

## Current release

- Local version: **0.16.0**
- Repository: <https://github.com/knowgyu/contextWhere>
- Default branch: `main`

v0.16.0 adds the global home memory layer, registry/scopes, Context Card lifecycle, signals/preflight, repository/global draft-apply flow, setup/doctor, and Codex/Claude/Gemini advisory integrations on top of the earlier repo-local evidence/wiki/context-pack foundation.

## What it does

- Keeps repo-local evidence in `<repo>/.contextwhere/contextwhere.sqlite3`.
- Keeps reusable scoped memory in the global home: `~/.contextwhere/` on Linux/macOS or `%USERPROFILE%\.contextwhere\` on Windows.
- Registers workspaces and repositories in the global registry.
- Stores Context Cards by scope: `global`, `workspace`, `repository`, or `machine`.
- Captures sanitized signals such as blockers, tool failures, environment facts, corrections, session summaries, and verified successes.
- Builds preflight context from active, non-expired cards before repeated work.
- Creates draft documentation updates first; `apply` is explicit and audited.
- Installs small advisory bridges for Codex, Claude, and Gemini only when requested.

It does not edit raw mail, documents, prompt logs, or provider state. Provider text is evidence, not instructions.

## Quick start from a checkout

```bash
uv sync
uv run pytest -q
uv run contextwhere setup --dry-run --json
uv run contextwhere setup --json
uv run contextwhere doctor --json
```

## Using with MailWhere and OfficeWhere

contextWhere can run alongside MailWhere and OfficeWhere as a local-first
context companion. Keep the tools on the same PC; contextWhere does not upload
provider data or start provider access by itself.

For the current `v0.16.0` release, install from this checkout (the commands
above), then use this small setup sequence:

1. Install or update MailWhere and OfficeWhere from their own release channels
   if you need those providers.
2. Run `contextwhere setup --json` and `contextwhere doctor --json`.
3. Preview an agent bridge with `contextwhere integrations install --agent codex --dry-run --json`; install only after reviewing the reported path.
4. Run MailWhere or OfficeWhere ingest/search only when you explicitly need
   provider evidence. Normal agent preflight reads only scoped active cards.

## Distribution status

The intended next installer is a Windows portable companion bundle with
checksums and a local Codex plugin. It is **not yet a released asset**. Public
npm publication is deferred; `uv` remains the contributor and current
checkout-install tool until the portable bundle exists.

Register the workspace and repository:

```bash
uv run contextwhere registry register workspace /home/you/workspace --json
uv run contextwhere registry register repository /home/you/workspace/contextWhere --workspace /home/you/workspace --json
uv run contextwhere registry list --json
```

Run repo-local checks and context commands:

```bash
uv run contextwhere init --json
uv run contextwhere providers matrix --json
uv run contextwhere status --json
uv run contextwhere context pack --query "current task" --json
uv run contextwhere maintain --json
```

## Context Card example

```bash
cat > /tmp/context-card.json <<'JSON'
{
  "card_id": "repo-check-before-release",
  "version": "context-card-v1",
  "type": "procedure/runbook",
  "summary": "Run contextWhere verification before release.",
  "scope": {"type": "repository", "key": "contextWhere"},
  "status": "candidate",
  "sensitivity": "internal",
  "confidence": "medium",
  "evidence_ids": ["manual:release-check"],
  "source_locators": ["docs/RELEASE.md"],
  "freshness": {"observed_at": "2026-07-29T00:00:00+00:00"},
  "verification": {"verified_at": "2026-07-29T00:00:00+00:00", "ok": true, "method": "local smoke"},
  "steps": ["Run pytest", "Run contextwhere verify"],
  "success_checks": ["Both commands exit 0"]
}
JSON

uv run contextwhere memory --scope repository:contextWhere observe --input-file /tmp/context-card.json --reason documented --json
uv run contextwhere memory --scope repository:contextWhere list --json
uv run contextwhere preflight --repository contextWhere --json
```

## Signals and preflight

```bash
uv run contextwhere signals capture --repository contextWhere --input-json '{"type":"environment_fact","name":"python","value":"3.12","verified":true,"method":"local smoke"}' --json
uv run contextwhere signals preflight --repository contextWhere --fingerprint <fingerprint> --json
```

Repeated tool failures can surface matching active verified procedures after the configured threshold. Verified successes create candidate procedure cards; they do not become active automatically.

## Agent integrations

```bash
uv run contextwhere integrations status --agent all --json
uv run contextwhere integrations install --agent codex --dry-run --json
uv run contextwhere integrations install --agent codex --json
```

Supported agents: `codex`, `claude`, `gemini`. Installation inserts a bounded marker into that agent's user instruction file and writes one owned helper file. It creates backups and can be removed with `integrations uninstall`.

## Safety boundaries

- Default storage is sanitized evidence, source locators, hashes, fingerprints, and card metadata.
- Raw mail bodies, prompt logs, full local paths, credentials, and secret-like values are rejected or redacted by default.
- `wiki draft`, `memory draft`, and `drafts create` do not apply changes automatically.
- `wiki apply`, `memory apply`, and `drafts apply` check trusted draft type, before-hash, target path, card status, evidence IDs, source locators, freshness, and unsafe content.
- OfficeWhere URLs must be loopback/local.
- Live MailWhere, OfficeWhere, GitHub, Jenkins, scheduler, and agent-integration checks remain explicit operator actions.

## Documentation

- [Design](docs/DESIGN.md)
- [Product brief](docs/PRODUCT.md)
- [Install](docs/INSTALL.md)
- [Windows](docs/WINDOWS.md)
- [Operations](docs/OPERATIONS.md)
- [Release](docs/RELEASE.md)
- [Handoff](context/handoff/START_HERE.md)
- [v0.16.0 release notes](docs/releases/v0.16.0.md)
