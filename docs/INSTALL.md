# contextWhere install and quick start

contextWhere 0.1.0 is a local-first Python/SQLite CLI. It is safe to run on a workstation or server because provider ingest is read-only and wiki writes happen only through audited `wiki apply` drafts.

## Requirements

- Python 3.11+
- SQLite with FTS5 support (included in standard CPython builds on Ubuntu and Windows Python installers)
- Optional: MailWhere CLI (`MailWhere.Cli.exe`) on Windows for live mail/task ingest
- Optional: OfficeWhere loopback HTTP provider for live document search

## Development install

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -U pip
python -m pip install -e . pytest
pytest -q
```

## First run

```bash
contextwhere init --json
contextwhere providers health --all --json
contextwhere ingest --provider mailwhere --fixture tests/fixtures/mailwhere_tasks.json --json
contextwhere query contextWhere --json
contextwhere wiki draft --query contextWhere --output .contextwhere/drafts/wiki/latest.json --json
contextwhere wiki apply .contextwhere/drafts/wiki/latest.json --json
contextwhere lint --json
contextwhere capture-session --file tests/fixtures/session.md --json
```

## Live provider examples

MailWhere:

```bash
contextwhere ingest \
  --provider mailwhere \
  --mailwhere-command MailWhere.Cli.exe \
  --limit 50 \
  --json
```

OfficeWhere must be loopback/local:

```bash
contextwhere ingest \
  --provider officewhere \
  --officewhere-base-url http://127.0.0.1:18765 \
  --query "project name" \
  --limit 25 \
  --json
```

Non-loopback OfficeWhere URLs are rejected as `unsafe_url`. Live ingest returns exit code 2 with `ok:false`, `status:"unavailable"`, and provider details when a live provider is missing or unsafe; fixture ingest remains a local test path.
