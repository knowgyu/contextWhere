from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from .base import ProviderResult, result_unavailable


class MailWhereProvider:
    provider = "mailwhere"

    def __init__(self, command: str = "MailWhere.Cli.exe", db: str | None = None, timeout: float = 10.0):
        self.command = command
        self.db = db
        self.timeout = timeout

    def _run(self, args: list[str]) -> ProviderResult:
        exe = shutil.which(self.command) or (self.command if Path(self.command).exists() else None)
        if not exe:
            return result_unavailable(self.provider, "command_missing", command=self.command)
        cmd = [exe, *args, "--json"]
        if self.db:
            cmd.extend(["--db", self.db])
        try:
            proc = subprocess.run(cmd, text=True, capture_output=True, timeout=self.timeout, check=False)
        except subprocess.TimeoutExpired:
            return result_unavailable(self.provider, "timeout", command=cmd)
        try:
            payload: dict[str, Any] = json.loads(proc.stdout or "{}")
        except json.JSONDecodeError:
            return result_unavailable(self.provider, "invalid_json", exit_code=proc.returncode, stderr=proc.stderr)
        if proc.returncode == 2:
            return result_unavailable(self.provider, str(payload.get("error") or payload.get("code") or "database_not_found"), exit_code=2)
        if proc.returncode != 0:
            return result_unavailable(self.provider, "command_failed", exit_code=proc.returncode, stderr=proc.stderr, payload=payload)
        raw_items = payload.get("items")
        items = [item for item in raw_items if isinstance(item, dict)] if isinstance(raw_items, list) else []
        return ProviderResult(provider=self.provider, ok=True, status="ok", items=items, manifest=payload if args and args[0] == "manifest" else None, details=payload)

    def health(self) -> ProviderResult:
        return self._run(["health"])

    def manifest(self) -> ProviderResult:
        return self._run(["manifest"])

    def list_tasks(self, status: str = "open", due_window: str = "7d", limit: int = 50) -> ProviderResult:
        return self._run(["list-tasks", "--status", status, "--due-window", due_window, "--limit", str(limit)])

    def list_review_candidates(self, limit: int = 25) -> ProviderResult:
        return self._run(["list-review-candidates", "--limit", str(limit)])
