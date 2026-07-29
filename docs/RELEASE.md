# contextWhere release guide

## Release checklist

1. Verify version alignment:
   - `pyproject.toml` `[project].version`
   - `src/contextwhere/__init__.py` `__version__`
2. Run verification:
   ```bash
   python -m compileall -q src tests
   pytest -q
   python -m contextwhere verify --json
   ```
   `verify` must report every current smoke step as passed, including evidence inspection, context pack, local capture, and maintenance.
3. Run smoke flow in a temporary root:
   ```bash
   TMP=$(mktemp -d)
   mkdir -p "$TMP/work_wiki"
   cp -R work_wiki/. "$TMP/work_wiki/"
   python -m contextwhere init --root "$TMP" --json
   python -m contextwhere providers health --all --root "$TMP" --json
   python -m contextwhere ingest --provider mailwhere --fixture tests/fixtures/mailwhere_tasks.json --root "$TMP" --json
   python -m contextwhere query contextWhere --root "$TMP" --json
   python -m contextwhere wiki draft --root "$TMP" --limit 2 --output "$TMP/draft.json" --json
   python -m contextwhere wiki apply --root "$TMP" "$TMP/draft.json" --json
   python -m contextwhere lint --root "$TMP" --json
   python -m contextwhere capture-session --root "$TMP" --file tests/fixtures/session.md --json
   rm -rf "$TMP"
   ```
4. Run code review and adversarial QA gates.
5. Clean generated artifacts that should not be released: `.pytest_cache`, `__pycache__`, `*.egg-info`, local `.venv`.
6. Commit with the Lore commit protocol.
7. Tag the release:
   ```bash
   git tag -a vX.Y.Z -m "vX.Y.Z: <release summary>"
   git push origin main --tags
   ```

If no Git remote is configured, stop after local tag creation and record the missing remote as the only release blocker.
