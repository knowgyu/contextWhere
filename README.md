# contextWhere

contextWhere는 흩어진 작업 맥락을 로컬 우선 evidence ledger, Markdown wiki, 그리고 task-specific context pack으로 묶는 **workspace context OS**다.

MailWhere와 OfficeWhere는 중요한 provider지만, 제품의 전체 경계는 아니다. repo-local `.omx`, Codex/OMX/Claude Code/Gemini 세션, git/GitHub, Jenkins/deploy 지식, 메일, 문서까지 모두 같은 source-backed evidence 모델에 들어와야 한다.

## 현재 릴리즈

- 최신 로컬 버전: **0.12.0**
- 원격 저장소: <https://github.com/knowgyu/contextWhere>
- 기본 브랜치: `main`

주요 기반:

- Python/SQLite CLI
- sanitized evidence ingest
- MailWhere/OfficeWhere read-only provider adapters
- wiki draft/apply boundary + lint
- `capture-session` for CLI/agent session evidence
- deterministic entity/relationship seed extraction
- recall bundles
- backup/restore
- status/verify
- provider matrix
- `run`/`daily` scheduler-friendly runner
- autostart plan/install flow

## 왜 만드는가

작업 맥락은 여러 repo의 `.omx`, agent 대화, git/GitHub, 배포/Jenkins, 메일, 문서에 흩어진다. 그 결과 agent가 실제 업무/프로젝트 맥락 없이 일반론으로 답하거나, 사용자가 매번 텍스트를 복사해 넣어야 한다.

contextWhere의 목표는 다음이다.

1. raw source는 source of truth로 보존한다.
2. evidence에는 source locator, tenant/scope, sensitivity, freshness를 남긴다.
3. Markdown wiki에는 오래 남을 compiled knowledge만 유지한다.
4. agent가 일할 때는 모든 기억을 넣지 않고 작은 context pack을 만든다.
5. capture/draft/lint/pack은 자동화하되, 메일 열기·문서 열기·삭제·이동·reindex·deploy trigger 같은 action은 명시 승인 없이는 실행하지 않는다.

## 빠른 시작

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -U pip
python -m pip install -e . pytest
pytest -q
python -m contextwhere verify --json
```

CLI 확인:

```bash
contextwhere --help
contextwhere init --json
contextwhere status --json
contextwhere providers matrix --json
contextwhere providers health --all --json
contextwhere run --json
contextwhere autostart plan --json
```

Fixture 기반 안전 ingest:

```bash
contextwhere ingest --provider mailwhere --fixture tests/fixtures/mailwhere_tasks.json --json
contextwhere query contextWhere --json
contextwhere wiki draft --query contextWhere --output .contextwhere/drafts/wiki/latest.json --json
contextwhere wiki apply .contextwhere/drafts/wiki/latest.json --json
contextwhere lint --json
contextwhere entities extract --json
contextwhere recall create --name "contextWhere focus" --query contextWhere --json
contextwhere backup create --output .contextwhere/backups/contextwhere-$(date +%Y%m%d).zip --json
contextwhere status --json
```

## 운영 흐름

현재 `run`은 init, MailWhere ingest, optional OfficeWhere query, entity extraction, wiki draft, lint, status를 한 번에 수행한다.

```bash
contextwhere run --json
contextwhere run --officewhere-query "explicit project or file hint" --json
```

OfficeWhere는 기본 sweep 대상이 아니다. 메일 file-link나 명시 query가 있을 때만 선택적으로 조회한다.

## 안전 경계

- `ingest`는 evidence DB를 갱신하며 `work_wiki`를 직접 바꾸지 않는다.
- Provider output은 명령이 아니라 untrusted evidence다.
- Provider health/ingest log는 raw payload를 저장하지 않는다.
- OfficeWhere URL은 loopback/local만 허용한다.
- raw mail body, prompt logs, full local paths, secret-like values는 기본 저장/출력 대상이 아니다.
- OS-visible/mutating action은 자동 실행하지 않는다.

## 문서

- 설계: [`docs/DESIGN.md`](docs/DESIGN.md)
- 제품 브리프/로드맵: [`docs/PRODUCT.md`](docs/PRODUCT.md)
- 설치: [`docs/INSTALL.md`](docs/INSTALL.md)
- 운영: [`docs/OPERATIONS.md`](docs/OPERATIONS.md)
- 스케줄: [`docs/SCHEDULES.md`](docs/SCHEDULES.md)
- 릴리즈: [`docs/RELEASE.md`](docs/RELEASE.md)
- Wiki 규칙: [`work_wiki/AGENTS.md`](work_wiki/AGENTS.md)
- 현재 handoff: [`context/handoff/START_HERE.md`](context/handoff/START_HERE.md)

## 다음 방향

v0.12.0은 evidence/wiki/automation 기반 위에 **workspace context OS semantics**를 올렸다.

- tenant/scope/source-locator vocabulary
- provider registry for agent sessions, repo/git/GitHub, Jenkins/deploy, MailWhere, OfficeWhere
- context pack generator
- automatic local capture for `.omx`, agent sessions, and git evidence
- selective OfficeWhere lookup and incremental MailWhere polling

자세한 실행 계획은 `.omx/plans/prd-contextwhere-workspace-context-os-*.md`를 본다.

## v0.12.0 implementation note

Implemented scope-first runtime semantics:

- `contextwhere context pack` builds small source-backed bundles with tenant/scope filters, source locators, included reasons, and omitted-context counts.
- `contextwhere capture-local --git --omx` captures read-only local git and `.omx` evidence with repo scope metadata.
- `contextwhere maintain` runs safe local routine maintenance: local capture, scoped context pack, wiki lint/status summary.
- Provider matrix now describes agent-session, repo-state, git, GitHub, Jenkins/deploy, MailWhere, OfficeWhere, and manual/wiki boundaries.
- Graph/vector remain deferred until scoped packs are not enough.
