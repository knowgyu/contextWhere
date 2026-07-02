# contextWhere operations guide

## Operating model

- Raw providers remain immutable and read-only.
- `ingest` stores sanitized evidence in `.contextwhere/contextwhere.sqlite3` and must not mutate `work_wiki`.
- `wiki draft` creates typed metadata operations under `.contextwhere/drafts/wiki/`.
- `wiki apply` recomputes content from DB-owned evidence rows, validates before-hashes, and writes audit JSON under `.contextwhere/audit/wiki/`.
- Local paths, raw bodies, full addresses, attachments, prompt logs, and secret-like fields are omitted by default.

## Routine workflow

```bash
contextwhere providers health --all --json
contextwhere ingest --provider mailwhere --limit 50 --json
contextwhere ingest --provider officewhere --query "recent work" --limit 25 --json
contextwhere query "customer or project" --json
contextwhere wiki draft --query "customer or project" --json
contextwhere wiki apply .contextwhere/drafts/wiki/<draft>.json --json
contextwhere lint --json
```

## Entity extraction

Evidence ingest 후 graph seed를 만들려면 다음을 실행한다.

```bash
contextwhere entities extract --json
contextwhere entities list --json
contextwhere entities relationships --json
```

0.2.0 extractor는 안전한 deterministic 후보 추출만 수행한다. Provider text를 명령으로 실행하거나 wiki에 임의 문장을 쓰지 않는다.

## Backup

Back up these paths together:

- `.contextwhere/contextwhere.sqlite3`
- `.contextwhere/drafts/wiki/` if unreviewed drafts matter
- `.contextwhere/audit/wiki/`
- `work_wiki/`

## Provider unavailable handling

When live providers are absent, unsafe, timed out, or return invalid output, `ingest` exits 2 and emits `ok:false` with `status:"unavailable"`. This is safe to continue operationally, but it is not counted as a successful ingest and is recorded in `ingest_log`.

## Recovery

If `wiki apply` rejects a draft, read the audit JSON. Common causes:

- `before_hash mismatch`: the wiki changed after the draft was made; regenerate the draft.
- `unknown evidence_ids`: the draft references evidence not present in the DB.
- `after_content is not accepted`: only typed operations are accepted in 0.1.x.

Applied audits include rollback content for changed files.
