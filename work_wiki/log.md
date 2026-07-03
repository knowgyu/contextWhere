# contextWhere Wiki Log

## [2026-07-02] init | project handoff

Initialized contextWhere folder from autoresearch discussion. Copied research report and validator result. Created initial wiki rules, index, and system pages.

## 2026-07-02 — contextWhere 0.1.0 foundation implementation

- Added Python/SQLite CLI skeleton for `init`, provider health/manifest, fixture/live ingest, query, wiki lint, wiki draft/apply, and capture-session.
- Added safety boundary: ingest does not mutate `work_wiki`; wiki mutation is only via constrained audited `wiki apply`.
- Evidence: `.omx/plans/ralplan-contextwhere-0.1.0-20260702T150136Z.md`, tests under `tests/`.

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
