# Install contextWhere

Version: 0.16.0

contextWhere targets Windows 11 first and also supports Linux/macOS development checkouts. It stores repository evidence under the repository and reusable memory under a global home.

## Paths

| Purpose | Windows default | Linux/macOS default |
| --- | --- | --- |
| Global home | `%USERPROFILE%\.contextwhere\` | `~/.contextwhere/` |
| Global DB | `%USERPROFILE%\.contextwhere\contextwhere.sqlite3` | `~/.contextwhere/contextwhere.sqlite3` |
| Registry | `%USERPROFILE%\.contextwhere\registry.json` | `~/.contextwhere/registry.json` |
| Repo state | `<repo>\.contextwhere\` | `<repo>/.contextwhere/` |

Use `--home <path>` for portable tests or managed-PC validation.

## Operator install (no checkout or `uv`)

Requires Python 3.11+. Run this from the repository that contextWhere should
manage; it installs the CLI, initializes global and repository-local storage,
registers both scopes, and verifies the result.

Linux/macOS:

```bash
python3 -m pip install --user --upgrade https://github.com/knowgyu/contextWhere/archive/refs/heads/main.zip
python3 -m contextwhere quickstart --root . --workspace .. --json
```

Windows PowerShell:

```powershell
py -m pip install --user --upgrade https://github.com/knowgyu/contextWhere/archive/refs/heads/main.zip
py -m contextwhere quickstart --root . --workspace .. --json
```

After opening a new terminal if necessary, the everyday checks are:

```bash
contextwhere status --json
contextwhere preflight --json
```

`quickstart` never installs agent bridges or contacts providers. Those remain
explicit opt-in actions.

## Development checkout

```bash
git clone https://github.com/knowgyu/contextWhere.git
cd contextWhere
uv sync
uv run pytest -q
uv run contextwhere verify --json
```

Without `uv`:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -U pip
python -m pip install -e . pytest
pytest -q
contextwhere verify --json
```

## Manual global setup

Preview first:

```bash
contextwhere setup --dry-run --json
```

Create global home, memory DB, registry, draft directories, and audit directories:

```bash
contextwhere setup --json
contextwhere doctor --json
```

Install advisory agent bridges only after reviewing the target paths:

```bash
contextwhere integrations status --agent all --json
contextwhere integrations install --agent codex --dry-run --json
contextwhere integrations install --agent codex --json
```

Use `--agent claude` or `--agent gemini` for the other supported agents. `setup --install-integrations --json` installs all bridges; use it only when that side effect is intended.

## Manual workspace and repository registration

```bash
contextwhere registry register workspace /home/you/workspace --json
contextwhere registry register repository /home/you/workspace/contextWhere --workspace /home/you/workspace --json
contextwhere registry list --json
contextwhere registry resolve /home/you/workspace/contextWhere --json
```

## Initialize a repository

```bash
contextwhere init --json
contextwhere status --json
contextwhere providers matrix --json
contextwhere context pack --query "current task" --json
```

## Optional autostart

Preview the local maintenance task:

```bash
contextwhere autostart plan --json
```

Install only after checking the command and path:

```bash
contextwhere autostart install
```

Windows creates a Task Scheduler task named `contextWhereMaintain`. Linux writes a user-level systemd timer. Both run `contextwhere maintain --json`; neither starts a long-running daemon.

## Live providers

MailWhere live ingest is explicit:

```bash
contextwhere ingest --provider mailwhere --limit 50 --json
```

OfficeWhere live search is explicit and loopback/local only:

```bash
contextwhere ingest --provider officewhere --query "file or project hint" --limit 25 --json
```

If a provider is missing, timed out, unsafe, or returns invalid output, contextWhere returns structured `ok:false`/`status:"unavailable"` output. That is safe to continue from and should not be documented as a successful live check.
