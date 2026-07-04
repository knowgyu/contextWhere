# contextWhere 운영 스케줄 예제

설치 후 기본 운영은 `contextwhere autostart install` 한 번이면 된다. 이 명령은 OS 기본 스케줄러에 `contextwhere maintain --json`을 등록한다. 이 기본 maintain는 OfficeWhere 문서 검색을 하지 않는다.

## 사전 점검

```bash
contextwhere verify --json
contextwhere maintain --json
contextwhere autostart plan --json
```

## 자동 실행 설치

Interactive Y/N:

```bash
contextwhere autostart install
```

Scripted install:

```bash
contextwhere autostart install --yes --json
```

Linux에서는 user-level systemd timer를 쓰고, Windows에서는 Task Scheduler를 쓴다. 자체 daemon은 두지 않는다.

## 운영 원칙

- 원문 provider는 read-only로만 사용한다.
- 자동 실행은 `maintain`까지가 기본이다.
- `wiki apply`는 자동 실행하지 않는다. 중요한 운영 환경에서는 사람이 draft를 확인한 뒤 적용한다.
- `.contextwhere/contextwhere.sqlite3`, `.contextwhere/audit/wiki/`, `work_wiki/`는 함께 백업한다.
