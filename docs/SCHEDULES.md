# contextWhere 운영 스케줄 예제

설치 후 기본 운영은 `contextwhere daily --json` 하나면 된다. 이 명령은 provider ingest, entity extract, wiki draft, lint, status를 실행하지만 `wiki apply`는 자동 실행하지 않는다.

## 사전 점검

```bash
contextwhere verify --json
contextwhere providers health --all --json
contextwhere daily --json
```

`providers health`가 `ok:false`여도 provider가 설치되어 있지 않다는 뜻일 수 있다. `daily`는 unavailable provider를 구조화해서 기록하고 계속 진행한다.

## cron 예제

```cron
# 매일 08:15 read-only daily run
15 8 * * * cd /opt/contextWhere && contextwhere daily --json >> logs/contextwhere-daily.log 2>&1

# 매일 08:25 backup
25 8 * * * cd /opt/contextWhere && contextwhere backup create --output .contextwhere/backups/contextwhere-$(date +\%Y\%m\%d).zip --json >> logs/contextwhere-backup.log 2>&1
```

## systemd timer 예제

`docs/examples/systemd/`의 unit/timer 파일을 `/etc/systemd/system/`에 복사한 뒤 경로와 사용자명을 환경에 맞게 수정한다.

```bash
sudo cp docs/examples/systemd/contextwhere-ingest.service /etc/systemd/system/
sudo cp docs/examples/systemd/contextwhere-ingest.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now contextwhere-ingest.timer
systemctl list-timers contextwhere-ingest.timer
```

## 운영 원칙

- 원문 provider는 read-only로만 사용한다.
- 자동 실행은 `daily`까지가 기본이다.
- `wiki apply`는 감사 로그와 rollback을 남기지만, 중요한 운영 환경에서는 사람이 draft를 확인한 뒤 적용한다.
- `.contextwhere/contextwhere.sqlite3`, `.contextwhere/audit/wiki/`, `work_wiki/`는 함께 백업한다.
