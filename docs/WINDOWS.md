# Windows 11 setup

contextWhere targets Windows 11 first. Use PowerShell 7+ or Windows PowerShell.

## User install

If `uv` is installed:

```powershell
uv tool install git+https://github.com/knowgyu/contextWhere.git
contextwhere verify --json
contextwhere maintain --json
contextwhere autostart plan --json
```

Without `uv`, use `pipx`:

```powershell
py -m pip install --user pipx
py -m pipx ensurepath
pipx install git+https://github.com/knowgyu/contextWhere.git
contextwhere verify --json
```

Open a new PowerShell if `contextwhere` is not found after install.

## Development checkout

```powershell
git clone https://github.com/knowgyu/contextWhere.git
cd contextWhere
uv sync
uv run pytest -q
uv run contextwhere verify --json
uv run contextwhere maintain --json
```

If not using `uv`:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
py -m pip install -U pip
py -m pip install -e . pytest
pytest -q
contextwhere verify --json
```

## Autostart

Preview the Task Scheduler command first:

```powershell
contextwhere autostart plan --json
```

Install only after the plan looks right:

```powershell
contextwhere autostart install
```

This creates a Windows Task Scheduler task named `contextWhereMaintain` that runs:

```powershell
python -m contextwhere maintain --root <repo-or-workspace> --json
```

It is not a daemon. Python starts, runs local maintenance, then exits.

## Routine commands

```powershell
contextwhere maintain --json
contextwhere context pack --query "current task" --json
contextwhere evidence show <evidence_id> --json
```

Live MailWhere/OfficeWhere ingest remains explicit; routine autostart does not run live provider search.
