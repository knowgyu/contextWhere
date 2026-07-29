# contextWhere release guide

Version: 0.16.0

## Version alignment

Update all of these together:

- `pyproject.toml` `[project].version`
- `src/contextwhere/__init__.py` `__version__`
- `README.md`
- `docs/releases/v<version>.md`

## Local verification

```bash
uv run python -m compileall -q src tests
uv run pytest -q
uv run contextwhere verify --json
```

`verify` must include current smoke coverage for setup/doctor, registry, Context Cards, preflight/signals, draft/apply boundaries, evidence inspection, context packs, local capture, and maintenance.

## Documentation smoke

Run command syntax checks used by docs:

```bash
uv run contextwhere --help
uv run contextwhere setup --help
uv run contextwhere doctor --help
uv run contextwhere registry --help
uv run contextwhere memory --help
uv run contextwhere signals --help
uv run contextwhere integrations --help
```

Run a temporary-home smoke before release:

```bash
TMP=$(mktemp -d)
HOME_ARG="$TMP/home/.contextwhere"
REPO_ARG="$TMP/repo"
mkdir -p "$REPO_ARG/work_wiki" "$REPO_ARG/docs"
printf '# Smoke wiki\n' > "$REPO_ARG/work_wiki/index.md"
printf '# Smoke operations\n' > "$REPO_ARG/docs/OPERATIONS.md"

uv run contextwhere setup --home "$HOME_ARG" --json
uv run contextwhere doctor --home "$HOME_ARG" --json
uv run contextwhere registry --home "$HOME_ARG" register workspace "$TMP" --json
uv run contextwhere registry --home "$HOME_ARG" register repository "$REPO_ARG" --workspace "$TMP" --json
uv run contextwhere init --root "$REPO_ARG" --json
uv run contextwhere status --root "$REPO_ARG" --json
uv run contextwhere preflight --home "$HOME_ARG" --repository smoke --json
```

## Windows managed-PC release gate

Before claiming Windows production readiness, run `docs/WINDOWS.md` on the target managed PC and save the JSON outputs. Required live checks are:

- setup/doctor against `%USERPROFILE%\.contextwhere`;
- registry workspace/repository registration;
- local repo status/context/maintain commands;
- MailWhere live ingest, or explicit `status:"unavailable"` gap;
- OfficeWhere live discovery/search, or explicit `status:"unavailable"` gap;
- agent bridge dry-run and any approved install/doctor output;
- Task Scheduler plan/install output if autostart is part of the release claim.

Do not claim live company-PC checks from WSL or a development fixture.

## Publish checklist

```bash
git status --short
git tag --list 'v0.16.0'
gh release view v0.16.0 --json tagName,name,isDraft,isPrerelease,url,assets
```

A tag is not a published release. Verify the GitHub Release and assets when release publication is requested.
