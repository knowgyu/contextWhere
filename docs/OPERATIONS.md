# contextWhere operations guide

Version: 0.16.0

## Operating model

- Repo-local commands operate on `<repo>/.contextwhere/` and `work_wiki/`.
- Global memory commands operate on `~/.contextwhere/` or `%USERPROFILE%\.contextwhere` unless `--home` is provided.
- Providers are read-only evidence sources.
- Draft commands create reviewable JSON or Markdown artifacts first.
- Apply commands are explicit and audited.

## Routine local workflow

```bash
contextwhere init --json
contextwhere status --json
contextwhere providers health --all --json
contextwhere maintain --json
contextwhere context pack --query "current task" --json
```

`maintain` is local and scheduler-friendly. It does not run live provider searches by default.

## Registry workflow

```bash
contextwhere setup --json
contextwhere registry register workspace /home/you/workspace --json
contextwhere registry register repository /home/you/workspace/contextWhere --workspace /home/you/workspace --json
contextwhere registry list --json
```

Use registered scopes when an agent should resolve repository context from the global registry instead of a guessed path.

## Context Card workflow

Create or observe a card:

```bash
contextwhere memory --scope repository:contextWhere observe --input-file ./card.json --reason "verified local procedure" --json
contextwhere memory --scope repository:contextWhere list --json
```

Promote only through legal lifecycle transitions:

```bash
contextwhere memory promote repo-check-before-release --to active --reason "verified and reviewed"
```

Active cards are the only reusable guidance returned by preflight. Terminal or stale cards remain audit history.

## Memory draft/apply workflow

```bash
contextwhere memory --scope repository:contextWhere draft repo-check-before-release --output .contextwhere/drafts/memory/repo-check-before-release.json --json
contextwhere memory --scope repository:contextWhere apply .contextwhere/drafts/memory/repo-check-before-release.json --root . --json
```

Review the draft before apply. Apply rejects stale, unsafe, terminal-status, mismatched, or path-escaping drafts and writes an audit record under the global home.

## Wiki draft/apply workflow

```bash
contextwhere wiki draft --query "release" --limit 5 --output .contextwhere/drafts/wiki/release.json --json
contextwhere wiki apply .contextwhere/drafts/wiki/release.json --json
contextwhere lint --json
```

`wiki draft` reads sanitized repo-local evidence. `wiki apply` writes only accepted typed operations and audits the result.

## Signals and failure preflight

Capture a sanitized environment fact:

```bash
contextwhere signals capture --repository contextWhere --input-json '{"type":"environment_fact","name":"python","value":"3.12","verified":true,"method":"local smoke"}' --json
```

Check scoped active cards before work:

```bash
contextwhere preflight --repository contextWhere --machine devbox --json
```

For repeated failures, compute/carry a fingerprint and ask for matching procedures:

```bash
contextwhere signals preflight --repository contextWhere --machine devbox --fingerprint <fingerprint> --json
```

Unsafe signal content is rejected or redacted: secrets, raw provider bodies, prompt-like instruction fields, and unsafe workaround language.

## Agent integrations

```bash
contextwhere integrations status --agent all --json
contextwhere integrations install --agent codex --dry-run --json
contextwhere integrations doctor --agent codex --json
contextwhere integrations uninstall --agent codex --json
```

Install edits user-level agent instruction files. Treat it as an explicit operator action, not routine maintenance.

## Provider operations

MailWhere:

```bash
contextwhere ingest --provider mailwhere --limit 50 --json
```

OfficeWhere:

```bash
contextwhere ingest --provider officewhere --query "file or project hint" --limit 25 --json
```

Provider unavailable output is operationally safe but is not a successful live-provider validation.

## Backup and restore

```bash
contextwhere backup create --output .contextwhere/backups/contextwhere-$(date +%Y%m%d).zip --json
contextwhere backup restore .contextwhere/backups/contextwhere-20260729.zip /tmp/contextwhere-restored --json
```

Restore refuses non-empty target roots. Keep off-host copies in the normal encrypted backup system.

## Return-to-work briefs

```bash
contextwhere return-to-work ingest --batch ./return-to-work.json --json
contextwhere return-to-work brief --batch-id 2026-07-return --json
```

Supported manifest item kinds are `mailwhere_export_json`, `paste_text`, and `.txt`/`.md` `document`. Generated briefs are drafts; they do not mutate the wiki automatically.
