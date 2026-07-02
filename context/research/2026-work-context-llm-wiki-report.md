# 2026 Autoresearch: 업무 메일·문서·코드 활동을 LLM Wiki / Context Store로 만드는 방법

작성일: 2026-07-02  
범위: 해외 논문/공식문서/블로그/GeekNews/HN 계열 논의 기반. 개인·소규모 팀 업무 컨텍스트 저장소 설계 제안.  
대상 환경: `MailWhere`(Outlook COM 기반 read-only mail/task provider), `OfficeWhere`(문서 provider), CLI coding agents/OMX/Codex 계열 작업 기록.

## 1. 결론 요약

당장 추천하는 방향은 **“원문은 불변 보관 + LLM이 유지하는 Markdown Wiki + 검색/그래프/메모리 보조 계층”**의 3~4층 구조다.

- **Raw Vault**: 메일, 첨부, Office 문서, 코드 작업 로그/PRD/테스트 결과를 원문/스냅샷으로 보존. LLM은 원문을 수정하지 않는다.
- **Compiled Wiki**: LLM이 `projects/`, `people/`, `decisions/`, `tasks/`, `systems/`, `meetings/`, `code/` 등의 Markdown 페이지를 갱신한다. 질문할 때마다 원문을 다시 캐는 RAG가 아니라, 업무 지식이 누적되는 “컴파일된 지식층”이다.
- **Evidence Index**: MailWhere/OfficeWhere/CLI logs에서 나온 source id, 시간, 발신자, 파일 path, commit, 명령 결과를 SQLite/BM25/FTS/optional vector로 색인한다. Wiki의 모든 핵심 주장은 evidence id를 가진다.
- **Memory/Graph Layer**: 반복되는 선호, 장기 프로젝트 상태, 사람·조직·문서·결정 간 관계, 시간에 따른 변화는 temporal knowledge graph나 agent memory 형태로 따로 관리한다.
- **Governance Layer**: 권한, 민감정보, 보존기간, 삭제, 원문 접근, 외부 모델 전송 여부를 정책화한다.

핵심은 **RAG 하나로 끝내지 않는 것**이다. 2026년 흐름은 “vector DB에 다 넣고 검색”에서 **Wiki/Memory/Graph/Hybrid Retrieval/Connector/Governance를 목적별로 분리**하는 쪽으로 이동했다.

## 2. 2026년 트렌드: 사람들이 어떻게 풀고 있나

### A. Karpathy식 LLM Wiki: RAG가 아니라 “컴파일된 지식”

Andrej Karpathy의 LLM Wiki 아이디어는 원문을 매번 검색하는 대신 LLM이 원문을 읽고 **영속적 Markdown Wiki**를 갱신하는 패턴이다. 원문은 불변 source of truth, Wiki는 LLM이 소유·갱신, schema/AGENTS.md가 작업 규칙을 제공한다. GeekNews 요약도 이 구조를 Raw sources / Wiki / Schema 3계층으로 설명한다.

실무적 의미:
- 업무 지식은 “질문할 때 검색”보다 “일이 발생할 때 정리”해야 복리처럼 쌓인다.
- Markdown/Git/Obsidian 계열은 사람이 읽고 diff/revert하기 쉬워 개인 업무 저장소에 강하다.
- 단점은 Wiki가 커질수록 오래된 요약, 모순, 중복, 출처 누락이 생긴다는 것. 그래서 lint/maintenance pass가 필수다.

### B. Agent memory는 RAG와 다른 문제

Mem0 논문은 장기 대화·세션 연속성을 위해 salient memory를 추출·통합·검색하는 구조를 제안하고, full-context 대비 p95 latency와 token cost를 크게 줄였다고 보고한다. Zep/Graphiti 논문은 static RAG만으로는 지속 변화하는 비즈니스 데이터와 대화 히스토리를 다루기 어렵고, 시간 인식 knowledge graph가 필요하다고 주장한다.

2026년 1차 연구도 같은 방향으로 더 명확해졌다. **Graph-based Agent Memory**(2026-02)는 agent memory를 graph 관점에서 taxonomy화하고, extraction→storage→retrieval→evolution lifecycle을 핵심 기술 축으로 본다. 이는 업무 저장소가 단순 문서 검색이 아니라 “기억이 생성·조직·검색·갱신되는 시스템”이어야 함을 뒷받침한다. **MemMachine**(2026-04)은 personalized AI agent에서 short-term, long-term episodic, profile memory를 결합하되, lossy extraction을 줄이기 위해 전체 conversational episode를 보존하는 ground-truth-preserving 구조를 제안한다. 즉 2026년 흐름은 “요약만 저장”이 아니라 **원문/episode 보존 + 적응형 retrieval + 프로필/장기기억 분리**다.

실무적 의미:
- “메일/문서 검색”은 RAG 문제지만, “내가 이 고객을 어떻게 대했는지”, “지난번 결정이 왜 바뀌었는지”, “이 사람과 프로젝트 관계가 시간에 따라 어떻게 변했는지”는 memory/temporal graph 문제다.
- 개인 업무 저장소에는 최소 세 종류의 기억이 필요하다.
  1. **Factual memory**: 프로젝트, 사람, 시스템의 현재 사실.
  2. **Episodic/evidence memory**: 특정 메일/회의/문서/커밋에서 나온 사건.
  3. **Procedural memory**: 내가 반복하는 업무 방식, CLI agent가 익힌 절차, 검증 루틴.

### C. GraphRAG / Hybrid RAG: 복잡한 업무 질문에는 관계가 필요

Microsoft GraphRAG 문서는 naive semantic search가 “connect the dots”와 큰 문서/코퍼스의 holistic understanding에서 약하다고 보고, entities/relationships/community summaries를 만들어 global/local query에 쓰는 방식을 제시한다.

실무적 의미:
- “A 고객 건이 왜 지연됐지?” 같은 질문은 메일 몇 개의 유사도 검색이 아니라 사람·문서·결정·날짜·작업 간 관계를 따라가야 한다.
- 다만 처음부터 Neo4j/GraphRAG 대형 인프라로 시작하면 과하다. Markdown page의 frontmatter와 SQLite edge table로 시작하고, 필요할 때 Graphiti/GraphRAG로 확장하는 편이 맞다.

### D. Local-first / low-storage retrieval

LEANN 같은 연구는 개인 기기에서 대규모 문서 검색을 가능하게 하려면 embedding 저장 비용 자체가 병목이라고 본다. HN 논의에서도 “몇 년치 이메일 vector DB가 50GB+가 될 수 있다”는 현실적 문제가 언급된다.

실무적 의미:
- Outlook PST/OST·첨부·Office 문서 전체를 무작정 embedding하면 저장·재색인·권한 문제가 커진다.
- 1차는 BM25/SQLite FTS + metadata filtering + deterministic provider search가 좋다.
- Vector는 “애매한 자연어 회상”이 필요한 범위에만 선택적으로 쓴다.

### E. Enterprise connector 흐름: 인덱싱형 vs 실시간 federated

Microsoft 365 Copilot connectors는 외부 데이터를 Microsoft Graph에 색인하는 synced connector와, MCP를 통해 실시간으로 원천 시스템에서 가져오는 federated connector를 구분한다. 민감하거나 동적인 데이터는 실시간 fetch가 유리하다.

실무적 의미:
- MailWhere/OfficeWhere도 같은 철학을 따라야 한다.
- 오래 보존할 sanitized metadata/snippet은 local index에 넣고, 민감한 원문/첨부는 provider가 권한 확인 후 필요 시 read-only로 가져오게 한다.
- “모든 원문을 하나의 LLM DB로 복사”는 편하지만 보안·삭제·동기화 실패가 크다.

### F. 보안/거버넌스가 핵심 기능으로 승격

OWASP LLM Top 10은 prompt injection, sensitive information disclosure, excessive agency 등 LLM 앱의 핵심 위험을 정리한다. 업무 메일·문서 저장소는 민감정보가 많기 때문에, 검색 품질보다 먼저 access control/provenance/redaction/audit가 필요하다.

실무적 의미:
- 메일/문서 원문을 외부 LLM에 자동 전송하지 않는다.
- LLM이 source mail open, 문서 열기, 메일 회신/이동/삭제 같은 OS-visible/mutation action을 자동 실행하지 않게 한다.
- Wiki page에는 `sensitivity`, `source_count`, `last_verified`, `confidence`, `supersedes`, `stale_after` 같은 lifecycle metadata가 필요하다.

## 3. 비교: 무엇을 어디에 써야 하나

| 접근 | 장점 | 약점 | 이 상황에서의 역할 |
|---|---|---|---|
| Plain Markdown LLM Wiki | 단순, Git diff, 사람/LLM 모두 읽기 쉬움, 장기 축적 | 커지면 탐색/중복/모순 관리 필요 | 최상위 업무 지식층. 프로젝트/사람/결정/절차를 컴파일 |
| BM25/SQLite FTS | 빠름, 로컬, 디버깅 쉬움, 한국어 전처리 가능 | 의미 유사 검색 약함 | MailWhere/OfficeWhere 원문·snippet 검색의 기본 |
| Vector RAG | 애매한 자연어 회상에 강함 | 저장비용, chunking, 권한/삭제/재색인 문제 | 선별된 문서/요약/첨부에 선택 적용 |
| Graph/GraphRAG | 관계·멀티홉·시간 추론에 강함 | 구축/정제 비용 큼 | 사람-프로젝트-결정-문서 관계가 쌓인 뒤 확장 |
| Agent memory (Mem0/Zep류) | 대화/세션 연속성, 선호·작업 상태 유지 | 잘못 기억/과잉 저장 위험 | CLI agent와 사용자의 장기 선호·작업 프로토콜 저장 |
| M365 Copilot connectors류 | 조직 권한/검색 생태계와 잘 맞음 | Microsoft 테넌트·관리자 정책 의존 | 회사 표준 Copilot로 확장할 때 참고/연동 |

## 4. 추천 아키텍처

```text
                 ┌─────────────────────────────┐
                 │        Query / Agents        │
                 │ Codex/OMX, chat, dashboards  │
                 └──────────────┬──────────────┘
                                │
                read index first│write back after work
                                ▼
┌──────────────────────────────────────────────────────────┐
│ Compiled LLM Wiki (Markdown + Git)                       │
│ index.md, log.md, projects/, people/, decisions/, code/   │
│ page metadata: sensitivity, evidence_ids, confidence      │
└──────────────┬──────────────────────────┬────────────────┘
               │                          │
       evidence lookup              memory/relations
               ▼                          ▼
┌─────────────────────────┐      ┌─────────────────────────┐
│ Evidence Index          │      │ Temporal Graph / Memory  │
│ SQLite FTS/BM25 + meta  │      │ entities, edges, states  │
│ optional vector subset  │      │ preferences, procedures  │
└──────────────┬──────────┘      └──────────────┬──────────┘
               │                                │
    provider read-only APIs                     │
               ▼                                ▼
┌──────────────────────────────────────────────────────────┐
│ Raw Vault / Source Providers                             │
│ MailWhere: Outlook COM + local storage/search/task        │
│ OfficeWhere: document provider/search/compare             │
│ CLI agents: sessions, plans, diffs, tests, commits        │
│ Original files/messages immutable, access controlled      │
└──────────────────────────────────────────────────────────┘
```

### 4.1 Wiki 디렉터리 초안

```text
work_wiki/
  AGENTS.md                  # 이 wiki를 다루는 규칙
  index.md                   # 모든 페이지의 one-line catalog
  log.md                     # ingest/query/lint chronicle
  inbox.md                   # 아직 정리 안 된 capture queue
  projects/
    project-<slug>.md
  people/
    person-<slug>.md
  organizations/
  decisions/
    YYYY-MM-DD-<decision>.md
  tasks/
    task-ledger.md
  systems/
    mailwhere.md
    officewhere.md
    codex-omx.md
  procedures/
    weekly-review.md
    source-ingest.md
  evidence/
    evidence-ledger.sqlite   # 또는 별도 data/ 밑
  archive/
```

### 4.2 Wiki page frontmatter

```yaml
---
type: project|person|decision|system|procedure|meeting|concept
status: active|stale|archived|needs_review
sensitivity: public|internal|confidential|secret
source_count: 12
evidence_ids:
  - mailwhere:message:...
  - officewhere:file:...
  - codex:session:...
last_verified: 2026-07-02
stale_after: 2026-08-02
confidence: medium
supersedes: []
related:
  - [[people/...]]
  - [[decisions/...]]
---
```

## 5. MailWhere 적용안

현재 `where-skills/docs/mailwhere-provider-contract.md`는 MailWhere를 read-only mail/task provider로 보고, Outlook COM/local storage/dedup/FTS/privacy를 stable provider 뒤에 숨기자는 방향이다. 이 설계는 이번 목적에 잘 맞다.

### 추천 capture 단위

- `task_list`, `review_candidate_list`: 업무 액션 후보를 Wiki `tasks/task-ledger.md`와 해당 project page에 반영.
- `search_mail_context`: 질문형 evidence lookup. Wiki 답변에 mail evidence id를 붙인다.
- raw body/addresses/attachments는 기본 제외. 필요 시 명시적 user approval 또는 local-only summarizer.

### 메일 ingest 정책

1. **Sanitized metadata first**: subject, sender display, received_at, thread id, snippet, attachment names, source id.
2. **Thread compaction**: 같은 thread는 최신/결정/액션 중심으로 요약. quoted history/signature 제거.
3. **Project/person linking**: 발신자·수신자·키워드·첨부명으로 project/person page 후보 생성.
4. **Decision/action extraction**: “결정됨/보류/마감/담당/리스크”만 Wiki에 승격.
5. **Raw opening gate**: 원문 열기, 첨부 열기, 답장/이동/삭제는 자동 금지.

### MailWhere가 제공하면 좋은 추가 endpoint

- `search_evidence(query, filters)` — snippet+metadata+source id 반환.
- `get_thread_summary(thread_id, redaction=default)` — full raw 대신 thread-level summary.
- `list_recent_decision_candidates(days=7)` — 결정/요청/기한이 있는 메일 후보.
- `resolve_source(source_id)` — 사용자가 요청했을 때 Outlook에서 열기 위한 explicit action request.

## 6. OfficeWhere 적용안

현재 `OfficeWhere Provider Notes`는 loopback provider, read-oriented API, source paths/snippets sensitive, reindex/rescan/settings/delete/open 자동 금지라는 규칙을 갖고 있다. 이것도 이번 목적에 맞다.

### 문서 ingest 정책

- 문서 원본은 Raw Vault/source system에 둔다.
- OfficeWhere search/compare 결과에서 문서 제목, path hash 또는 local path, modified_at, snippet, duplicate/group info를 evidence로 저장한다.
- Word/PPT/Excel은 “문서 전체 요약”보다 “업무 단위 추출”이 중요하다.
  - proposal/보고서: 목적, 주요 주장, 숫자, 결정 요청, 관련 프로젝트.
  - 회의록: 참석자, 결정, 액션, 열린 이슈.
  - Excel: sheet purpose, key tables, data lineage, known caveats.
  - PPT: audience, storyline, reused slides, final vs draft 여부.

### OfficeWhere가 제공하면 좋은 추가 endpoint

- `extract_outline(file_id)` — 제목/섹션/슬라이드 구조.
- `extract_decisions(file_id)` — 문서 내 의사결정/요청/마감 후보.
- `get_document_fingerprint(file_id)` — 중복/버전 추적.
- `compare_versions(file_id_a, file_id_b)` — app-owned cache만 허용.

## 7. CLI coding agents / OMX / Codex 적용안

코딩 업무는 이미 CLI agent가 수행하므로 “세션 후 정리”가 핵심이다.

### 저장해야 할 것

- Goal/mission: 사용자가 무엇을 원했는가.
- Constraints: 하지 말아야 할 것, 보안/호환성 조건.
- Plan: PRD/test-spec/ralplan/team plan.
- Decisions: 왜 이 구현을 택했는가, 거절한 대안.
- Changes: 파일, API, 마이그레이션, config.
- Verification: 실행한 테스트, 실패, 미검증.
- Follow-ups: 남은 리스크와 다음 작업.

### 추천 방식

- 각 agent session 종료 시 `code/sessions/YYYY-MM-DD-<repo>-<slug>.md`를 생성.
- 안정화된 지식은 `systems/<repo>.md`, `procedures/<workflow>.md`, `decisions/`로 승격.
- 커밋 메시지의 Lore trailers와 Wiki decision page를 연결.
- 반복되는 절차는 `procedures/` 또는 Codex skill/AGENTS.md 업데이트 후보로 저장.

## 8. 운영 루틴

### Daily ingest

- MailWhere: 오늘/어제 받은 direct 업무 메일, review candidates, due tasks.
- OfficeWhere: 최근 수정/열람 문서, 중복/버전 후보.
- CLI: 오늘 생성된 plans, tests, commits, OMX notes.
- Output: `log.md` entry + 관련 project/person/task page 업데이트.

### Weekly lint

체크리스트:
- 출처 없는 주장 제거/표시.
- stale_after 지난 페이지 `needs_review` 전환.
- 같은 프로젝트가 여러 이름으로 중복됐는지 merge 후보 생성.
- orphan page 확인.
- source_count 낮은 중요한 주장 재검증.
- 완료된 task archive.
- 민감도 높은 페이지 외부 모델 사용 금지 표시.

### Query workflow

1. `index.md`와 관련 page 먼저 읽기.
2. Wiki가 부족하면 Evidence Index 검색.
3. 그래도 부족하면 MailWhere/OfficeWhere provider에 read-only query.
4. 답변에는 source ids와 confidence 포함.
5. 질문 자체가 새 insight면 Wiki에 query result page 또는 관련 page 업데이트.

## 9. 개인정보/보안/삭제 원칙

- 기본은 **local-first**. 외부 LLM에는 sanitized snippets와 필요한 최소 context만.
- ACL/permission은 원천 시스템 기준을 보존한다. 색인 DB가 권한을 우회하면 안 된다.
- 모든 evidence row는 `source_provider`, `source_id`, `created_at`, `retention_until`, `sensitivity`, `hash`, `deleted_at` 필드를 갖는다.
- 삭제 요청은 raw vault, evidence index, vector index, wiki citations에 모두 반영해야 한다.
- prompt injection 방어: 메일/문서 본문은 instruction이 아니라 untrusted data로 취급.
- LLM output은 action으로 바로 실행하지 않는다. 특히 메일 회신/삭제/파일 열기/명령 실행은 별도 승인.

### 9.1 실행 가능한 governance control plane

**권한 확인 위치**

1. Provider boundary: MailWhere/OfficeWhere가 source permission과 local policy를 1차로 적용한다. where-skills/agent는 SQLite나 Outlook/Office 원본을 직접 읽지 않는다.
2. Evidence Index boundary: evidence row마다 `principal`, `source_acl_hash`, `sensitivity`, `allowed_ops=[search,snippet,open_request]`를 저장한다. 검색 결과 반환 전 현재 principal과 sensitivity policy를 재검사한다.
3. Prompt assembly boundary: LLM context에 넣기 직전 redaction policy를 다시 적용한다. 이 단계에서 full address, raw body, path, attachment body, secrets는 기본 제외한다.

**Redaction policy**

- `public/internal`: title, short snippet, timestamp, source id 허용.
- `confidential`: snippet은 300자 이하, 사람/회사/금액/계약정보는 rule+LLM redactor로 마스킹, 외부 모델 전송 금지 기본값.
- `secret`: Wiki에는 존재 사실과 local source id만 기록. 원문/요약/embedding 생성 금지.
- 모든 redacted output은 `redaction_version`과 `omitted_fields`를 기록해 나중에 왜 답변이 불완전했는지 추적한다.

**Raw open / OS-visible action gate**

- `open_source_mail`, `open_document`, `show_in_folder`, `reply`, `move`, `delete`, `reindex`는 agent가 직접 실행하지 않고 `action_request` row만 생성한다.
- action request에는 `reason`, `source_id`, `requested_by`, `risk`, `expires_at`가 필요하다. 사용자가 UI/CLI에서 승인해야 provider가 실행한다.
- read-only preview도 `confidential` 이상이면 local-only viewer를 우선한다.

**Delete / retention cascade**

삭제 또는 보존기간 만료 시 순서:

1. Raw Vault/provider에 source tombstone 기록. 원천 삭제가 불가능한 Outlook/Office 항목은 local index exclusion tombstone을 둔다.
2. Evidence Index에서 `deleted_at`, `delete_reason`, `tombstone_hash` 설정. 검색 기본 결과에서 제외.
3. Vector index가 있다면 해당 chunk/vector id를 삭제하고 rebuild queue에 넣는다. 삭제 불가능한 ANN 구조는 shard rebuild 대상 표시.
4. Graph/memory edge에서 해당 evidence를 근거로 한 edge를 `unsupported` 또는 `needs_review`로 전환한다.
5. Wiki page의 `evidence_ids`에서 제거하고, 근거가 사라진 주장은 `needs_review` block으로 이동한다.
6. `log.md`에 cascade 결과와 미처리 항목을 남긴다.

**Audit**

- 모든 provider query, prompt assembly, action request, wiki write-back은 append-only audit log에 남긴다.
- audit log에는 raw content를 저장하지 않고 source id/hash/operation/result count만 저장한다.

## 10. Query-to-retrieval decision matrix

| 질문 유형 | 1차 경로 | 2차 경로 | 금지/주의 | 예시 |
|---|---|---|---|---|
| 현재 프로젝트 상태 | Wiki `projects/` + `tasks/` | Evidence Index recent filter | 오래된 summary 단독 답변 금지 | “A 프로젝트 지금 뭐 남았지?” |
| 특정 메일/문서 찾기 | MailWhere/OfficeWhere provider search | SQLite FTS/BM25, metadata filter | raw body 외부 전송 금지 | “2월 임원 보고자료 메일” |
| 사람/조직 관계 | Wiki `people/`, graph edges | Mail thread/document co-occurrence | 단일 메일로 관계 단정 금지 | “B팀 C님은 어떤 건 담당?” |
| 결정의 이유 | `decisions/` page | 원문 evidence ids → provider snippets | 출처 없는 회상 금지 | “왜 이 설계를 버렸지?” |
| 애매한 의미 검색 | BM25+multi-query | 선택적 vector search | 전체 mailbox embedding 기본 금지 | “예전에 비슷한 장애” |
| 멀티홉/전체 흐름 | graph/community summary | GraphRAG/temporal graph | 구축 전에는 confidence 낮게 표시 | “고객 이슈가 왜 반복?” |
| 개인 선호/반복 절차 | `procedures/`, agent memory | session summaries | 민감 사실 자동 profile화 금지 | “내가 배포 전 항상 뭘 확인?” |
| 원문 확인/OS action | action_request | 사용자 승인 후 provider open | agent direct action 금지 | “그 메일 열어줘” |

## 11. 단계별 로드맵

### Phase 0 — 이번 주: 파일 기반 MVP

- `work_wiki/` 생성, Git 초기화.
- `index.md`, `log.md`, `AGENTS.md`, 기본 디렉터리 생성.
- MailWhere/OfficeWhere provider search 결과를 수동 또는 스크립트로 Markdown evidence block에 붙여넣기.
- CLI 작업 종료 때 session summary를 Wiki에 남기기.

### Phase 1 — 2~3주: Evidence Index

- SQLite 테이블: `sources`, `evidence`, `entities`, `edges`, `wiki_pages`.
- BM25/FTS 검색과 metadata filters 구현.
- MailWhere/OfficeWhere provider에서 sanitized ingest.
- Wiki page frontmatter와 evidence ids 강제.

### Phase 2 — 1~2개월: 자동 maintenance

- daily ingest agent, weekly lint agent.
- 중복/모순/stale detector.
- project/person auto-linking.
- OfficeWhere version compare와 MailWhere thread compaction.

### Phase 3 — 이후: Hybrid/Graph/Memory 확장

- vector index는 선별 corpus에만 도입.
- temporal graph는 project/person/decision/task 관계가 충분히 쌓인 뒤 도입.
- agent memory는 사용자 선호/절차/반복 실패/검증 패턴 중심으로 제한.
- Microsoft 365 Copilot과 연결해야 한다면 synced/federated connector 모델을 참고해 “무엇을 색인하고 무엇을 실시간 fetch할지” 구분.

## 12. Ranked recommendation

| 순위 | 권장 | Effort | Impact | 이유 |
|---|---|---:|---:|---|
| Do now | Markdown/Git `work_wiki` + `index.md`/`log.md`/frontmatter 표준화 | 낮음 | 높음 | 바로 쌓이기 시작하고 되돌리기 쉽다. |
| Do now | MailWhere/OfficeWhere sanitized evidence block 표준화 | 낮음~중간 | 높음 | 출처 없는 요약을 막는다. |
| Do next | SQLite FTS/BM25 Evidence Index | 중간 | 높음 | 전체 embedding 없이 메일/문서 회상이 가능하다. |
| Do next | daily ingest + weekly lint 자동화 | 중간 | 높음 | 장기 품질은 maintenance가 좌우한다. |
| Defer | vector index 전체 도입 | 중간~높음 | 중간 | 저장/삭제/권한 비용이 커서 선별 corpus 후 도입. |
| Defer | full GraphRAG/temporal graph infra | 높음 | 높음(나중) | 관계 데이터가 충분히 쌓인 뒤 효과가 난다. |
| Defer | M365 Copilot connector 연동 | 높음 | 상황 의존 | 조직/테넌트/관리자 정책이 필요하다. |

## 13. 추천 기술 선택

개인/로컬 우선 MVP:
- Markdown + Git + Obsidian
- SQLite FTS5/BM25
- Python ingestion scripts
- optional: sqlite-vec 또는 pgvector는 나중
- Mermaid/Dataview로 Wiki 시각화

확장 후보:
- Graphiti/Zep류 temporal graph: 관계·시간 추론이 중요해질 때
- GraphRAG: 큰 narrative private corpus에서 global synthesis가 필요할 때
- LEANN류 low-storage vector index: 개인 기기에서 대용량 semantic search가 필요할 때
- M365 Copilot connectors/MCP federated connector: 조직 Copilot 생태계에 붙일 때

## 14. 가장 중요한 설계 판단

1. **원문과 Wiki를 분리한다.** Wiki는 재작성 가능하지만 원문은 불변 evidence다.
2. **요약보다 provenance가 중요하다.** 출처 없는 요약은 시간이 지나면 쓰레기가 된다.
3. **메일/문서/코드 활동을 같은 entity model로 묶는다.** 사람, 프로젝트, 결정, 작업, 문서, 코드 변경은 서로 연결되어야 한다.
4. **vector-first가 아니라 retrieval ladder를 쓴다.** index → Wiki page → FTS/BM25 → provider live search → vector/graph.
5. **LLM에게 쓰기 권한은 Wiki에만 준다.** 원문, 메일, 문서, OS action은 read-only/explicit gate.
6. **maintenance를 기능으로 본다.** ingest보다 lint, stale detection, contradiction handling이 장기 성공을 좌우한다.

## 15. 참고한 주요 sources

- Karpathy, “llm-wiki” gist: https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f
- MindStudio, “Build a Personal Knowledge Base: 70x Faster Than RAG” (2026-04-14): https://www.mindstudio.ai/blog/karpathy-llm-wiki-pattern-personal-knowledge-base-without-rag
- GeekNews, “LLM-Wiki - LLM을 활용하여 개인 지식저장소 구축 하기”: https://news.hada.io/topic?id=28208
- GeekNews, “WUPHF - Karpathy 스타일 LLM 위키를 에이전트들이 직접 유지하는 시스템”: https://news.hada.io/topic?id=28910
- GeekNews, “GBrain — 오픈소스 개인 지식 베이스”: https://news.hada.io/topic?id=28323
- Yang et al., “Graph-based Agent Memory: Taxonomy, Techniques, and Applications,” arXiv:2602.05665: https://arxiv.org/abs/2602.05665
- Wang et al., “MemMachine: A Ground-Truth-Preserving Memory System for Personalized AI Agents,” arXiv:2604.04853: https://arxiv.org/abs/2604.04853
- Chhikara et al., “Mem0: Building Production-Ready AI Agents with Scalable Long-Term Memory,” arXiv:2504.19413: https://arxiv.org/abs/2504.19413
- Rasmussen et al., “Zep: A Temporal Knowledge Graph Architecture for Agent Memory,” arXiv:2501.13956: https://arxiv.org/abs/2501.13956
- “LEANN: A Low-Storage Vector Index,” arXiv:2506.08276: https://arxiv.org/html/2506.08276v1
- Microsoft GraphRAG docs: https://microsoft.github.io/graphrag/
- Microsoft 365 Copilot connectors overview: https://learn.microsoft.com/en-us/microsoft-365/copilot/connectors/overview
- OWASP Top 10 for LLM Applications / GenAI Security Project: https://owasp.org/www-project-top-10-for-large-language-model-applications/
- Local workspace evidence: `where-skills/docs/mailwhere-provider-contract.md`, `where-skills/docs/officewhere-provider-notes.md`
