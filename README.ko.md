# contextWhere

[English](README.md)

contextWhere는 개발자·운영자 에이전트를 위한 로컬 우선 워크스페이스 컨텍스트
OS입니다. 저장소 상태, 에이전트 세션, MailWhere, OfficeWhere,
GitHub/Jenkins 형태의 업무 시스템, 명시적 메모에서 정제된 증거를 수집하고,
이를 scope가 지정된 Context Card, Markdown draft, compact context pack으로
만듭니다.

## 현재 릴리스

- 로컬 버전: **0.16.0**
- 저장소: <https://github.com/knowgyu/contextWhere>
- 기본 브랜치: `main`

v0.16.0은 기존의 repo-local evidence/wiki/context-pack 기반 위에 전역 home
메모리 계층, registry/scope, Context Card lifecycle, signals/preflight,
repository/global draft-apply 흐름, setup/doctor, Codex/Claude/Gemini advisory
integration을 추가했습니다.

## 하는 일

- repo-local evidence를 `<repo>/.contextwhere/contextwhere.sqlite3`에 보관합니다.
- 재사용 가능한 scope 메모리를 전역 home에 보관합니다. Linux/macOS는
  `~/.contextwhere/`, Windows는 `%USERPROFILE%\.contextwhere\`입니다.
- 전역 registry에 workspace와 repository를 등록합니다.
- Context Card를 `global`, `workspace`, `repository`, `machine` scope로 저장합니다.
- blocker, tool failure, environment fact, correction, session summary,
  verified success 같은 정제된 signal을 수집합니다.
- 반복 작업 전에 active이며 만료되지 않은 card로 preflight context를 만듭니다.
- 문서 갱신은 먼저 draft로 만들며, `apply`는 명시적이고 감사됩니다.
- 요청한 경우에만 Codex, Claude, Gemini용 작은 advisory bridge를 설치합니다.

원본 메일·문서·prompt log·provider 상태를 수정하지 않습니다. Provider text는
증거이며 instruction이 아닙니다.

## 설치하고 바로 사용하기

운영자용 경로는 Python 3.11+만 필요하며 checkout이나 `uv`는 필요하지 않습니다.
contextWhere가 관리할 저장소에서 실행합니다.

```bash
python3 -m pip install --user --upgrade https://github.com/knowgyu/contextWhere/archive/refs/heads/main.zip
python3 -m contextwhere quickstart --root . --workspace .. --json
```

`quickstart`는 전역 home과 저장소별 저장소를 만들고, workspace/repository를 등록한
뒤 둘 다 확인합니다. 필요하면 새 터미널을 연 뒤 `contextwhere status --json` 또는
`contextwhere preflight --json`만 실행하면 됩니다. Windows에서는 `python3` 대신
`py`를 사용합니다.

## Contributor checkout

```bash
uv sync
uv run pytest -q
uv run contextwhere setup --dry-run --json
uv run contextwhere setup --json
uv run contextwhere doctor --json
```

## MailWhere 및 OfficeWhere와 함께 사용하기

contextWhere는 MailWhere와 OfficeWhere 곁에서 로컬 우선 컨텍스트 companion으로
동작합니다. 세 도구는 같은 PC에 두며, contextWhere가 provider 데이터를 업로드하거나
provider 접근을 스스로 시작하지 않습니다.

빠른 설치 뒤 다음의 작은 순서로 사용합니다.

1. Provider가 필요하면 각자의 릴리스 채널에서 MailWhere와 OfficeWhere를 설치하거나 갱신합니다.
2. `contextwhere status --json`으로 로컬 설정을 확인합니다.
3. `contextwhere integrations install --agent codex --dry-run --json`으로 agent bridge를 미리 보고, 대상 경로를 검토한 뒤에만 설치합니다.
4. Provider evidence가 실제로 필요할 때만 MailWhere/OfficeWhere ingest 또는 search를 실행합니다. 일반 agent preflight는 scope가 맞는 active card만 읽습니다.

## 배포 상태

다음 설치 방식은 checksum과 local Codex plugin을 포함한 Windows portable companion
bundle입니다. 아직 **릴리스 asset으로 제공되지 않습니다**. public npm 배포는 보류되어
있으며, 위의 직접 Python 설치가 현재 운영자 경로이고 `uv`는 contributor 전용입니다.

repo-local 점검과 context 명령을 실행합니다.

```bash
contextwhere status --json
contextwhere providers matrix --json
contextwhere context pack --query "current task" --json
contextwhere maintain --json
```

## Context Card 예시

```bash
cat > /tmp/context-card.json <<'JSON'
{
  "card_id": "repo-check-before-release",
  "version": "context-card-v1",
  "type": "procedure/runbook",
  "summary": "Run contextWhere verification before release.",
  "scope": {"type": "repository", "key": "contextWhere"},
  "status": "candidate",
  "sensitivity": "internal",
  "confidence": "medium",
  "evidence_ids": ["manual:release-check"],
  "source_locators": ["docs/RELEASE.md"],
  "freshness": {"observed_at": "2026-07-29T00:00:00+00:00"},
  "verification": {"verified_at": "2026-07-29T00:00:00+00:00", "ok": true, "method": "local smoke"},
  "steps": ["Run pytest", "Run contextwhere verify"],
  "success_checks": ["Both commands exit 0"]
}
JSON

uv run contextwhere memory --scope repository:contextWhere observe --input-file /tmp/context-card.json --reason documented --json
uv run contextwhere memory --scope repository:contextWhere list --json
uv run contextwhere preflight --repository contextWhere --json
```

## Signal과 preflight

```bash
uv run contextwhere signals capture --repository contextWhere --input-json '{"type":"environment_fact","name":"python","value":"3.12","verified":true,"method":"local smoke"}' --json
uv run contextwhere signals preflight --repository contextWhere --fingerprint <fingerprint> --json
```

반복되는 tool failure는 설정된 임계값 뒤에 일치하는 active verified procedure를
보일 수 있습니다. Verified success는 candidate procedure card를 만들지만 자동으로
active가 되지는 않습니다.

## Agent integration

```bash
uv run contextwhere integrations status --agent all --json
uv run contextwhere integrations install --agent codex --dry-run --json
uv run contextwhere integrations install --agent codex --json
```

지원 agent는 `codex`, `claude`, `gemini`입니다. 설치는 해당 agent의 user instruction
file에 범위가 제한된 marker를 넣고, 하나의 owned helper file을 작성합니다. Backup을
만들며 `integrations uninstall`로 제거할 수 있습니다.

## 안전 경계

- 기본 저장 대상은 정제된 evidence, source locator, hash, fingerprint, card metadata입니다.
- 원본 메일 body, prompt log, 전체 local path, credential, secret처럼 보이는 값은 기본적으로 거부하거나 redaction합니다.
- `wiki draft`, `memory draft`, `drafts create`는 변경을 자동 적용하지 않습니다.
- `wiki apply`, `memory apply`, `drafts apply`는 trusted draft type, before-hash, target path, card status, evidence ID, source locator, freshness, unsafe content를 확인합니다.
- OfficeWhere URL은 loopback/local이어야 합니다.
- Live MailWhere, OfficeWhere, GitHub, Jenkins, scheduler, agent integration 점검은 모두 명시적인 operator action으로 유지됩니다.

## 문서

- [설계](docs/DESIGN.md)
- [제품 개요](docs/PRODUCT.md)
- [설치](docs/INSTALL.md)
- [Windows](docs/WINDOWS.md)
- [운영](docs/OPERATIONS.md)
- [릴리스](docs/RELEASE.md)
- [Handoff](context/handoff/START_HERE.md)
- [v0.16.0 릴리스 노트](docs/releases/v0.16.0.md)
