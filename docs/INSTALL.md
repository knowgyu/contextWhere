# contextWhere install and quick start

contextWhere 0.13.0 is a local-first Python/SQLite CLI and workspace context OS slice. Provider ingest is read-only; wiki writes happen only through audited `wiki apply` drafts.

## Requirements

- Python 3.11+
- SQLite with FTS5 support
- Optional: MailWhere CLI (`MailWhere.Cli.exe`) on Windows for live mail/task ingest
- Optional: OfficeWhere loopback HTTP provider for live document search

## Easiest user install

From this repo:

```bash
python -m pip install --user pipx
python -m pipx ensurepath
pipx install git+https://github.com/knowgyu/contextWhere.git
contextwhere verify --json
```

If using `uv`:

```bash
uv tool install git+https://github.com/knowgyu/contextWhere.git
contextwhere verify --json
```

## Development install

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -U pip
python -m pip install -e . pytest
pytest -q
contextwhere verify --json
```

## First run

```bash
contextwhere init --json
contextwhere providers matrix --json
contextwhere providers health --all --json
contextwhere run --json
contextwhere autostart plan --json
```

`run` runs init, MailWhere ingest, file-link evidence creation, entity extraction, wiki draft, lint, and status. It skips OfficeWhere document search unless `--officewhere-query` is set. It does not apply wiki drafts automatically.

To keep it running without manual commands, inspect the plan and install user-level autostart once:

```bash
contextwhere autostart plan --json
contextwhere autostart install
```

`install` asks for Y/N unless `--yes` is passed.

## Live provider examples

MailWhere:

```bash
contextwhere run \
  --mailwhere-command MailWhere.Cli.exe \
  --json
```

OfficeWhere search is opt-in and must be loopback/local:

```bash
contextwhere run \
  --officewhere-base-url http://127.0.0.1:18765 \
  --officewhere-query "file or project hint from mail" \
  --json
```

Missing providers return structured `status:"unavailable"` entries and are safe to continue. Non-loopback OfficeWhere URLs are rejected as `unsafe_url`.

## Backup restore smoke

```bash
contextwhere backup create --output .contextwhere/backups/contextwhere-$(date +%Y%m%d).zip --json
contextwhere backup restore .contextwhere/backups/contextwhere-20260703.zip /tmp/contextwhere-restored --json
contextwhere query contextWhere --root /tmp/contextwhere-restored --json
```

## Routine maintenance

```bash
contextwhere maintain --json
```

This is local-only. Missing `work_wiki`, `.git`, or `.omx` is safe; broken git is a warning unless `--strict-git` is set.


### Evidence inspection

```bash
contextwhere evidence show <evidence_id> --json
contextwhere evidence show --source-locator <locator> --json
```

This reads sanitized local evidence rows only; provider rehydration remains explicit future work.
