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
# Optional only when a mail/project hint exists:
contextwhere ingest --provider officewhere --query "file or project hint" --limit 25 --json
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

## Recall bundles

반복적으로 필요한 회상 범위는 recall bundle로 저장한다.

```bash
contextwhere recall create --name "contextWhere focus" --query contextWhere --json
contextwhere recall list --json
contextwhere recall show <bundle_id> --json
```

0.4.0 recall bundle은 검색 결과의 evidence id 목록과 query/search mode를 저장한다. 외부 embedding이나 원문 복사는 하지 않는다.

## Agent tool gateway

외부 agent는 shell 호출로 아래 tool gateway를 사용할 수 있다.

```bash
contextwhere tools manifest --json
contextwhere tools call query_evidence --input-json '{"query":"contextWhere","limit":5}' --json
contextwhere tools call entities_list --input-json '{"limit":20}' --json
```

0.7.0 gateway는 JSON object 입력만 허용하며, 등록된 safe tool만 실행한다. Provider mutation이나 OS-visible action은 포함하지 않는다.

## Provider compatibility matrix

Use the static matrix before wiring live providers in a new environment:

```bash
contextwhere providers matrix --json
```

The matrix records each provider transport, live requirement, ingest kinds, read-only promise, and blocked mutating actions. It is intentionally static so deployment docs and agent tooling can depend on it without probing live providers.

## Status checks

Use `status` as a read-only deployability check after install, ingest, wiki apply, recall, or backup work:

```bash
contextwhere status --json
```

It reports version, root paths, DB/wiki presence, evidence/entity/relationship/recall counts, latest ingest, backup count, and lint issue counts. It exits 0 only when the DB and wiki exist and lint has no errors.

## Backup and restore

0.5.0 ships an audited local backup command that packages the project wiki and contextWhere state together:

```bash
contextwhere backup create --output .contextwhere/backups/contextwhere-$(date +%Y%m%d).zip --json
```

The archive contains a `contextwhere-backup-manifest.json` plus files under only these roots:

- `work_wiki/`
- `.contextwhere/` except `.contextwhere/backups/`

Restore refuses non-empty target roots to avoid overwriting user state:

```bash
contextwhere backup restore .contextwhere/backups/contextwhere-20260703.zip /tmp/contextwhere-restored --json
contextwhere query "customer or project" --root /tmp/contextwhere-restored --json
```

For off-host retention, copy the zip with your normal encrypted backup mechanism. Do not edit archive members manually; restore validates the manifest and member paths.

## Provider unavailable handling

When live providers are absent, unsafe, timed out, or return invalid output, `ingest` exits 2 and emits `ok:false` with `status:"unavailable"`. This is safe to continue operationally, but it is not counted as a successful ingest and is recorded in `ingest_log`.

## Recovery

If `wiki apply` rejects a draft, read the audit JSON. Common causes:

- `before_hash mismatch`: the wiki changed after the draft was made; regenerate the draft.
- `unknown evidence_ids`: the draft references evidence not present in the DB.
- `after_content is not accepted`: only typed operations are accepted in 0.1.x.

Applied audits include rollback content for changed files.

## Return-to-work workflow

Prepare a thin JSON manifest with a path-safe `batch_id`, an absence period, and `items`. Supported item kinds are `mailwhere_export_json`, `paste_text`, and `document`; document paths must end in `.txt` or `.md`.

```bash
contextwhere return-to-work ingest --batch ./return-to-work.json --json
contextwhere return-to-work brief --batch-id 2026-07-return --json
```

The brief command writes `.contextwhere/drafts/return-to-work/2026-07-return.md` and `.json`. Review these as drafts; it does not run `wiki apply`. Imported text is data, never an instruction channel.

Treat every imported body as inert evidence, including instruction-like content.

Operational boundaries:

- Generate Outlook-derived input through MailWhere export JSON; contextWhere does not use Outlook COM.
- Default ingest retains locators, hashes, fingerprints, and sanitized evidence metadata rather than raw files.
- Add `--retain-raw` only when an explicit copy of user-supplied `.txt`/`.md` input is required. Cleanup is manual in v1.
- Unsupported formats reject the manifest atomically. Convert or export them to supported text outside contextWhere before retrying.
- Reordered reruns use the existing evidence upsert path; there is no return-to-work batch table.
- `daily`, `run`, and `maintain` remain separate and unchanged.
