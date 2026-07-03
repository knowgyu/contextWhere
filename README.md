# contextWhere

contextWhere는 MailWhere, OfficeWhere, CLI 코딩 에이전트에서 흩어지는 업무 맥락을 로컬 우선 evidence ledger와 LLM 유지보수형 Markdown wiki로 누적하기 위한 자동화 엔진이다.

목표는 단순 MVP가 아니라, 설치·검증·운영·릴리즈·다음 페이즈까지 이어갈 수 있는 배포 가능한 제품 기반을 계속 확장하는 것이다.

## 현재 릴리즈

- 최신 로컬 버전: **0.7.1**
- 공개 원격 저장소: <https://github.com/knowgyu/contextWhere>
- 기본 브랜치: `main`
- 기준 태그:
  - `v0.1.0`: safe provider ingest foundation
  - `v0.1.1`: Korean README and operational verification foundation
  - `v0.2.0`: deterministic entity extraction and relationship seed
  - `v0.3.0`: agent JSON tool gateway
  - `v0.4.0`: local recall bundles
  - `v0.5.0`: audited local backup and restore foundation
  - `v0.6.0`: operational status command and deployability check
  - `v0.7.0`: provider compatibility matrix
  - `v0.7.1`: documentation repair release

## 왜 만드는가

업무 메일, 로컬 Office 문서, CLI agent 세션은 시간이 지나면 맥락이 사라진다. contextWhere는 이를 vector DB 하나에만 넣지 않고 다음 층으로 나눈다.

1. **Raw/source providers**: MailWhere, OfficeWhere, CLI agent session artifacts.
2. **Evidence layer**: source ID, snippet, metadata, timestamp, sensitivity, provenance.
3. **Compiled Markdown Wiki**: 프로젝트, 사람, 결정, 작업, 시스템, 절차를 agent가 갱신하는 사람이 읽을 수 있는 지식층.
4. **Automation layer**: ingest, query, lint, draft/apply, stale check, handoff generation.
5. **Future graph/memory layer**: 사람·프로젝트·문서·결정 간 관계와 temporal memory.

핵심 원칙은 **원문은 불변, provider 결과는 untrusted evidence, wiki 변경은 감사 가능한 제한 작업**이다.

## 현재 되는 것

- Python/SQLite 기반 로컬 CLI.
- MailWhere/OfficeWhere read-only provider adapter.
- SQLite evidence table + FTS 검색.
- 민감 필드 기본 생략: raw mail body, full addresses/recipients, attachments, prompt logs/raw transcripts, local paths.
- `wiki draft`: 비파괴 draft 생성.
- `wiki apply`: DB evidence 기반 typed operation만 적용, before-hash 검증, audit/rollback JSON 기록.
- `capture-session`: CLI agent 세션 요약 evidence 저장.
- `lint`: work_wiki frontmatter/evidence/lifecycle 점검.
- `verify`: 설치 후 자체 smoke 검증.
- `entities extract/list/relationships`: evidence에서 deterministic entity와 co-occurrence relationship seed 추출.
- `tools manifest/call`: 외부 agent가 안전한 JSON tool gateway로 query/capture/entities/recall 기능 호출.
- `recall create/list/show`: evidence query 결과를 재현 가능한 local recall bundle로 저장.
- `backup create/restore`: `work_wiki`와 `.contextwhere`를 manifest 포함 zip으로 백업하고 빈 target에만 복원.
- `status`: DB/wiki/ingest/entity/recall/backup/lint 상태를 read-only JSON으로 점검.
- `providers matrix`: MailWhere/OfficeWhere provider별 live requirement, 안전 경계, ingest kind를 JSON으로 고정.
- Ubuntu cron/systemd 운영 예제.

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
```

Fixture 기반 안전 ingest:

```bash
contextwhere ingest --provider mailwhere --fixture tests/fixtures/mailwhere_tasks.json --json
contextwhere query contextWhere --json
contextwhere wiki draft --query contextWhere --output .contextwhere/drafts/wiki/latest.json --json
contextwhere wiki apply .contextwhere/drafts/wiki/latest.json --json
contextwhere lint --json
contextwhere entities extract --json
contextwhere entities list --json
contextwhere tools manifest --json
contextwhere tools call query_evidence --input-json '{"query":"contextWhere"}' --json
contextwhere recall create --name "contextWhere focus" --query contextWhere --json
contextwhere recall list --json
contextwhere backup create --output .contextwhere/backups/contextwhere-$(date +%Y%m%d).zip --json
contextwhere status --json
```

## 운영 흐름

일상 운영의 기본 루틴은 다음과 같다.

```bash
contextwhere providers health --all --json
contextwhere ingest --provider mailwhere --limit 100 --json
contextwhere ingest --provider officewhere --query "recent work" --limit 100 --json
contextwhere query "프로젝트나 고객명" --json
contextwhere wiki draft --query "프로젝트나 고객명" --json
contextwhere lint --json
contextwhere entities extract --json
contextwhere recall create --name "contextWhere focus" --query contextWhere --json
contextwhere backup create --output .contextwhere/backups/contextwhere-$(date +%Y%m%d).zip --json
contextwhere status --json
```

복원은 덮어쓰기를 방지하기 위해 비어 있거나 존재하지 않는 target root에만 수행한다.

```bash
contextwhere backup restore .contextwhere/backups/contextwhere-20260703.zip /tmp/contextwhere-restored --json
```

중요 운영 환경에서는 `wiki apply`를 자동화하기 전에 draft를 확인한다.

## 안전 경계

- `ingest`는 evidence DB만 갱신하며 `work_wiki`를 직접 바꾸지 않는다.
- Provider output은 명령이 아니라 untrusted evidence로 취급한다.
- Provider health/ingest log도 raw payload를 출력/저장하지 않고 telemetry만 남긴다.
- OfficeWhere base URL은 loopback/local만 허용한다.
- 메일 열기, 문서 열기, 답장, 이동, 삭제, reindex/rescan 같은 OS-visible/mutating action은 자동 실행하지 않는다.

## 문서

- 설치: [`docs/INSTALL.md`](docs/INSTALL.md)
- 운영: [`docs/OPERATIONS.md`](docs/OPERATIONS.md)
- 운영 스케줄: [`docs/SCHEDULES.md`](docs/SCHEDULES.md)
- 제품 브리프/로드맵: [`docs/PRODUCT.md`](docs/PRODUCT.md)
- 릴리즈: [`docs/RELEASE.md`](docs/RELEASE.md)
- Wiki 규칙: [`work_wiki/AGENTS.md`](work_wiki/AGENTS.md)

## 릴리즈 로드맵

- **0.7.x**: live MailWhere/OfficeWhere 연결 테스트, migration command, selective local recall.
- **0.8.x**: people/projects/decisions/tasks 전용 typed wiki promotion.
- **0.9.x**: MCP/long-running agent tool surface.
- **1.0**: provider contracts, release artifacts, migration policy가 안정화된 local-first context platform.

## 검증

```bash
python -m compileall -q src tests
pytest -q
npx --yes pyright src tests
python -m contextwhere verify --json
```

릴리즈 전에는 temp-root smoke와 adversarial QA를 함께 수행한다. 자세한 절차는 `docs/RELEASE.md`를 따른다.
