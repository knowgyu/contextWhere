# contextWhere Wiki Log

## [2026-07-02] init | project handoff

Initialized contextWhere folder from autoresearch discussion. Copied research report and validator result. Created initial wiki rules, index, and system pages.

## 2026-07-02 — contextWhere 0.1.0 foundation implementation

- Added Python/SQLite CLI skeleton for `init`, provider health/manifest, fixture/live ingest, query, wiki lint, wiki draft/apply, and capture-session.
- Added safety boundary: ingest does not mutate `work_wiki`; wiki mutation is only via constrained audited `wiki apply`.
- Evidence: `context/decisions/0003-preserve-planning-contracts.md`, tests under `tests/`.

## 2026-07-03 — contextWhere 0.1.1 operational verification

- README를 한국어 기준 문서로 재작성하고 final-goal handoff 시점의 상태를 반영했다.
- `contextwhere verify --json` 설치 후 smoke 명령을 추가했다.
- Ubuntu cron/systemd 운영 스케줄 예제를 추가했다.
- Evidence: `docs/releases/v0.1.1.md`, `src/contextwhere/verify.py`, tests under `tests/`.

## 2026-07-03 — contextWhere 0.2.0 entity graph seed

- Evidence ledger 위에 deterministic entity extraction과 relationship seed tables를 추가했다.
- `contextwhere entities extract/list/relationships` CLI를 추가했다.
- `contextwhere verify --json` smoke에 entity extraction 단계를 포함했다.
- Evidence: `docs/releases/v0.2.0.md`, `src/contextwhere/entities.py`, tests under `tests/`.

## 2026-07-03 — contextWhere 0.3.0 agent tool gateway

- 외부 agent가 사용할 수 있는 `contextwhere tools manifest/call` JSON gateway를 추가했다.
- Query, capture-session, entity extraction/list/relationship list tool을 등록했다.
- Evidence: `docs/releases/v0.3.0.md`, `src/contextwhere/tools.py`, tests under `tests/`.

## 2026-07-03 — contextWhere 0.4.0 local recall bundles

- Evidence query 결과를 저장하는 local recall bundle 기능을 추가했다.
- `contextwhere recall create/list/show` CLI와 tool gateway recall calls를 추가했다.
- `contextwhere verify --json` smoke에 recall bundle 단계를 포함했다.
- Evidence: `docs/releases/v0.4.0.md`, `src/contextwhere/recall.py`, tests under `tests/`.

## 2026-07-03 — contextWhere 0.5.0 audited backup/restore

- Added manifest-based local backup archive for `work_wiki/` and `.contextwhere/`.
- Restore validates archive members and refuses non-empty targets to avoid overwriting user state.
- Evidence: `docs/releases/v0.5.0.md`, `src/contextwhere/backup.py`, tests under `tests/`.

## 2026-07-03 — contextWhere 0.6.0 operational status

- Added read-only `contextwhere status --json` for deployability checks.
- Verify smoke now includes status after capture/recall workflows.
- Evidence: `docs/releases/v0.6.0.md`, `src/contextwhere/status.py`, tests under `tests/`.

## 2026-07-03 — contextWhere 0.7.0 provider compatibility matrix

- Added static `contextwhere providers matrix --json` for deployment/provider contracts.
- Matrix documents MailWhere and OfficeWhere transport, live requirements, ingest kinds, and safety boundaries.
- Evidence: `docs/releases/v0.7.0.md`, `src/contextwhere/provider_matrix.py`, tests under `tests/`.

## 2026-07-03 — workspace context OS goal correction

- Reframed contextWhere from MailWhere/OfficeWhere-centered memory into a workspace context OS.
- Added tenant/scope/source-locator/context-pack language to durable docs and wiki rules.
- Preserved MailWhere and OfficeWhere as providers, not product boundary.
- Evidence: `docs/DESIGN.md`, `context/decisions/0002-workspace-context-os.md`.

## 2026-07-29 — provider ownership and legacy wrapper review

- Confirmed MailWhere owns Outlook mirror/search, OfficeWhere owns document indexing/search, and contextWhere owns cross-provider evidence/wiki/context packs.
- Replaced live wiki evidence links to `where-skills` with current product contracts.
- Marked `where-skills` as an archive candidate, blocked only by the unresolved OfficeWhere dynamic-port discovery consumer gap.
- Evidence: `docs/DESIGN.md`, `MailWhere/docs/ARCHITECTURE.md`, `OfficeWhere/docs/provider-contract.md`.

## 2026-07-29 — where-skills retirement completed

- Moved OfficeWhere packaged dynamic-port discovery into the contextWhere provider adapter.
- Kept explicit loopback URL overrides and stale-discovery fallback.
- Closed the last unique `where-skills` runtime gap so the standalone wrapper can remain archived.
- Evidence: `src/contextwhere/providers/officewhere.py`, `tests/test_contextwhere.py`, `docs/releases/v0.15.1.md`.

## 2026-07-29 — generated planning surfaces retired

- Condensed durable writer-boundary, provider-unavailable, fixture-flow, and scope-safety contracts into Decision 0003.
- Removed tracked generated `.omx` plans/reviews and ignored future local OMX runtime state.
- Corrected current product docs to record `where-skills` as already retired.
- Evidence: `context/decisions/0003-preserve-planning-contracts.md`, `docs/releases/v0.15.2.md`.
