# contextWhere install and quick start

contextWhere 0.15.1 targets Windows 11 first, with Ubuntu supported. It is a local-first Python/SQLite CLI workspace context OS slice. Provider ingest is read-only; wiki writes happen only through audited `wiki apply` drafts.

## Requirements

- Windows 11 + PowerShell, or Ubuntu 22.04+
- Python 3.11+
- SQLite with FTS5 support
- Optional on Windows: MailWhere CLI (`MailWhere.Cli.exe`) for live mail/task ingest
- Optional: OfficeWhere loopback HTTP provider for live document search

## Windows 11 user install

```powershell
uv tool install git+https://github.com/knowgyu/contextWhere.git
contextwhere verify --json
contextwhere maintain --json
contextwhere autostart plan --json
```

If `contextwhere` is not found, open a new PowerShell so PATH updates apply.

Without `uv`:

```powershell
py -m pip install --user pipx
py -m pipx ensurepath
pipx install git+https://github.com/knowgyu/contextWhere.git
contextwhere verify --json
```

## Windows 11 development checkout

```powershell
git clone https://github.com/knowgyu/contextWhere.git
cd contextWhere
uv sync
uv run pytest -q
uv run contextwhere verify --json
uv run contextwhere maintain --json
```

Without `uv`:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
py -m pip install -U pip
py -m pip install -e . pytest
pytest -q
contextwhere verify --json
```

## Ubuntu support path

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -U pip
python -m pip install -e . pytest
pytest -q
contextwhere verify --json
contextwhere maintain --json
```

## First run

```powershell
contextwhere init --json
contextwhere providers matrix --json
contextwhere providers health --all --json
contextwhere maintain --json
contextwhere autostart plan --json
```

To keep local maintenance running without manual commands, inspect the plan and install user-level autostart once:

```powershell
contextwhere autostart plan --json
contextwhere autostart install
```

On Windows this registers a Task Scheduler task named `contextWhereMaintain`. On Ubuntu it writes a user-level systemd timer. Both run `contextwhere maintain --json`; neither starts a daemon.

## Live provider examples

MailWhere:

```powershell
contextwhere run --mailwhere-command MailWhere.Cli.exe --json
```

OfficeWhere search is opt-in and must be loopback/local:

```powershell
contextwhere run --officewhere-base-url http://127.0.0.1:18765 --officewhere-query "file or project hint from mail" --json
```

Packaged OfficeWhere normally uses a dynamic loopback port. contextWhere reads the current user-scoped `provider-discovery.json` first and falls back to the development URL when discovery is absent or stale. `OFFICEWHERE_BASE_URL` or `--officewhere-base-url` remains an explicit loopback-only override. Missing providers return structured `status:"unavailable"` entries and are safe to continue. Non-loopback URLs are rejected as `unsafe_url`.

## Routine maintenance

```powershell
contextwhere maintain --json
```

Local-only. Missing `work_wiki`, `.git`, or `.omx` is safe; broken git is a warning unless `--strict-git` is set.

## Evidence inspection

```powershell
contextwhere evidence show <evidence_id> --json
contextwhere evidence show --source-locator <locator> --json
```

This reads sanitized local evidence rows only; provider rehydration remains explicit future work.
