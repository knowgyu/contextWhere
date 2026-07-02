# contextWhere 운영 스케줄 예제

0.1.1부터는 설치 후 `contextwhere verify --json`으로 로컬 smoke를 바로 확인할 수 있다. 아래 예제는 실제 MailWhere/OfficeWhere가 있는 환경에서 주기 ingest를 붙이기 위한 템플릿이다.

## 사전 점검

```bash
python -m contextwhere verify --json
contextwhere providers health --all --json
```

`providers health`가 `ok:false`여도 provider가 설치되어 있지 않다는 뜻일 수 있다. 실제 운영 ingest에서는 `ingest`가 `status:"unavailable"`과 exit code 2를 반환하면 성공 ingest로 계산하지 않는다.

## cron 예제

`docs/examples/cron/contextwhere.crontab`를 참고한다.

```cron
# 매일 08:15 MailWhere read-only ingest
15 8 * * * cd /opt/contextWhere && . .venv/bin/activate && contextwhere ingest --provider mailwhere --limit 100 --json >> logs/contextwhere-ingest.log 2>&1

# 매일 08:25 wiki lint
25 8 * * * cd /opt/contextWhere && . .venv/bin/activate && contextwhere lint --json >> logs/contextwhere-lint.log 2>&1
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
- 자동 실행은 `ingest`, `query`, `lint`, `wiki draft`까지가 기본이다.
- `wiki apply`는 감사 로그와 rollback을 남기지만, 중요한 운영 환경에서는 사람이 draft를 확인한 뒤 적용한다.
- `.contextwhere/contextwhere.sqlite3`, `.contextwhere/audit/wiki/`, `work_wiki/`는 함께 백업한다.
