# contextWhere

contextWhere는 MailWhere, OfficeWhere, CLI 코딩 에이전트에서 흩어지는 업무 맥락을 로컬 우선 evidence ledger와 LLM 유지보수형 Markdown wiki로 누적하기 위한 자동화 엔진이다.

이 README는 최종 goal을 새로 세운 시점인 **2026-07-03 08:23 KST 전후**의 프로젝트 상태를 기준으로 작성했다. 그 시점의 목표는 단순 0.1.0 MVP가 아니라, 설치·검증·운영·릴리즈·다음 페이즈 태그까지 이어갈 수 있는 배포 가능한 제품 기반을 계속 확장하는 것이다.

## 현재 릴리즈

- 최신 로컬 버전: **0.2.0**
- 공개 원격 저장소: <https://github.com/knowgyu/contextWhere>
- 기본 브랜치: `main`
- 기준 태그:
  - `v0.1.0`: safe provider ingest foundation
  - `v0.1.1`: Korean README and operational verification foundation
  - `v0.2.0`: deterministic entity extraction and relationship seed

## 왜 만드는가

업무 메일, 로컬 Office 문서, CLI agent 세션은 시간이 지나면 맥락이 사라진다. contextWhere는 이를 매번 vector DB에만 넣는 방식이 아니라 다음 층으로 나눈다.

1. **Raw/source providers**: MailWhere, OfficeWhere, CLI agent session artifacts.
2. **Evidence layer**: source ID, snippet, metadata, timestamp, sensitivity, provenance.
3. **Compiled Markdown Wiki**: 프로젝트, 사람, 결정, 작업, 시스템, 절차를 agent가 갱신하는 사람이 읽을 수 있는 지식층.
4. **Automation layer**: ingest, query, lint, draft/apply, stale check, handoff generation.
5. **Future graph/memory layer**: 사람·프로젝트·문서·결정 간 관계와 temporal memory.

핵심 원칙은 **원문은 불변, provider 결과는 untrusted evidence, wiki 변경은 감사 가능한 제한 작업**이다.

## 0.1.x에서 되는 것

- Python/SQLite 기반 로컬 CLI.
- MailWhere/OfficeWhere read-only provider adapter.
- SQLite evidence table + FTS 검색.
- 민감 필드 기본 생략:
  - raw mail body
  - full addresses / recipients
  - attachments
  - prompt logs / raw transcripts
  - local paths
- `wiki draft`: 비파괴 draft 생성.
- `wiki apply`: DB evidence 기반 typed operation만 적용, before-hash 검증, audit/rollback JSON 기록.
- `capture-session`: CLI agent 세션 요약 evidence 저장.
- `lint`: work_wiki frontmatter/evidence/lifecycle 점검.
- `verify`: 설치 후 자체 smoke 검증.
- `entities extract/list/relationships`: evidence에서 deterministic entity와 co-occurrence relationship seed 추출.
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
contextwhere entities list --json
```

중요 운영 환경에서는 `wiki apply`를 자동화하기 전에 draft를 확인한다. `wiki apply`는 감사 로그와 rollback 내용을 남기지만, compiled wiki에 들어가는 문장은 장기 지식이 되므로 신중하게 적용한다.

## 안전 경계

- `ingest`는 evidence DB만 갱신하며 `work_wiki`를 직접 바꾸지 않는다.
- provider output은 명령이 아니라 untrusted evidence로 취급한다.
- provider health/ingest log도 raw payload를 출력/저장하지 않고 safe telemetry만 남긴다.
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

- **0.1.0**: safe provider ingest foundation.
- **0.1.1**: 한국어 README, 설치 후 `verify`, cron/systemd 운영 예제.
- **0.2.0**: deterministic entity extraction과 relationship table seed.
- **0.2.x 이후**: people/projects/decisions/tasks 전용 extractor와 wiki 승격 workflow 강화.
- **0.3.x**: MCP/tool server로 agent가 contextWhere를 직접 조회·기록.
- **0.4.x**: 선택적 local embedding/vector recall.
- **1.0**: backup/restore, migration policy, provider compatibility matrix, 안정 운영 문서까지 포함한 local-first context platform.

## 개발/검증 명령

```bash
python -m compileall -q src tests
pytest -q
npx --yes pyright src tests
python -m contextwhere verify --json
```

릴리즈 전에는 temp-root smoke와 adversarial QA를 함께 수행한다. 자세한 절차는 `docs/RELEASE.md`를 따른다.
