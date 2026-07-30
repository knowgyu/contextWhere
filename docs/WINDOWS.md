# Windows 11 setup and smoke checklist

Version: 0.16.0

Use this on a Windows 11 managed PC with PowerShell. The checklist separates local CLI checks from live provider checks so documentation does not imply unverified company-PC state.

## Operator install (no checkout or `uv`)

Requires Python 3.11+. In PowerShell, change to the repository that
contextWhere should manage and run:

```powershell
py -m pip install --user --upgrade https://github.com/knowgyu/contextWhere/archive/refs/heads/main.zip
py -m contextwhere quickstart --root . --workspace .. --json
```

This installs the CLI, creates `%USERPROFILE%\.contextwhere`, initializes the
repository-local `.contextwhere`, registers both scopes, and verifies them.
Open a new terminal if `contextwhere` is not yet on PATH, then use:

```powershell
contextwhere status --json
contextwhere preflight --json
```

`quickstart` does not install agent bridges or access MailWhere/OfficeWhere.

## Contributor checkout

```powershell
git clone https://github.com/knowgyu/contextWhere.git
cd contextWhere
uv sync
uv run pytest -q
uv run contextwhere verify --json
```

If `uv` is unavailable:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
py -m pip install -U pip
py -m pip install -e . pytest
pytest -q
contextwhere verify --json
```

## Global home setup

```powershell
contextwhere setup --dry-run --json
contextwhere setup --json
contextwhere doctor --json
```

Expected default home: `%USERPROFILE%\.contextwhere`.

## Register local scopes

```powershell
contextwhere registry register workspace C:\Users\<you>\workspace --json
contextwhere registry register repository C:\Users\<you>\workspace\contextWhere --workspace C:\Users\<you>\workspace --json
contextwhere registry list --json
```

## Managed-PC smoke checklist

Run each command and keep the JSON output as release evidence.

### Local-only checks

```powershell
contextwhere doctor --json
contextwhere init --json
contextwhere status --json
contextwhere providers matrix --json
contextwhere context pack --query "current task" --json
contextwhere maintain --json
```

Pass criteria:

- commands exit 0 unless a known optional provider is unavailable;
- JSON includes `ok:true` for local setup/doctor/status checks;
- paths resolve under the expected repo and `%USERPROFILE%\.contextwhere`;
- no secret-like values, raw mail bodies, or prompt logs appear in output.

### Agent bridge checks

```powershell
contextwhere integrations status --agent all --json
contextwhere integrations install --agent codex --dry-run --json
```

Only run non-dry install when the operator approves editing that agent's user instruction file:

```powershell
contextwhere integrations install --agent codex --json
contextwhere integrations doctor --agent codex --json
```

Repeat with `claude` or `gemini` only if those tools are installed and approved on the PC.

### Live MailWhere check

```powershell
contextwhere ingest --provider mailwhere --limit 10 --json
```

Pass criteria: MailWhere is installed, command exits 0, output is sanitized JSON, and evidence count increases. If MailWhere is absent or blocked by policy, record `status:"unavailable"` as an unverified live-provider gap.

### Live OfficeWhere check

```powershell
contextwhere ingest --provider officewhere --query "known project or file hint" --limit 10 --json
```

Pass criteria: OfficeWhere discovery resolves a loopback/local endpoint, command exits 0, and returned evidence is sanitized. Non-loopback URLs must be rejected.

## Explicit unverified gaps

As of v0.16.0 documentation prep, this repository has not verified live commands on the user's managed Windows PC. Do not claim:

- live MailWhere Outlook data ingestion works on that PC;
- live OfficeWhere packaged discovery/search works on that PC;
- Codex/Claude/Gemini bridge installation was applied on that PC;
- Task Scheduler autostart runs on that PC.

Claim those only after saving smoke-output evidence from the target machine.
