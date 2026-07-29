from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from contextwhere import memory
from contextwhere.signals import capture_signal, stable_fingerprint
from contextwhere.tools import call_tool


def active_proc(fingerprint: str) -> dict:
    return {
        "card_id": "proc-active",
        "type": "procedure/runbook",
        "summary": "Run pytest with the repo root on import failures.",
        "scope": {"type": "repository", "key": "repo-a"},
        "status": "active",
        "evidence": ["manual:verified"],
        "freshness": {"observed_at": "2026-07-29T00:00:00+00:00"},
        "verification": {"verified_at": "2026-07-29T00:00:00+00:00", "ok": True, "method": "pytest"},
        "failure_fingerprint": fingerprint,
        "steps": ["PYTHONPATH=src pytest"],
        "success_checks": ["tests pass"],
    }


def test_fingerprint_removes_paths_timestamps_ids_and_numbers() -> None:
    first = stable_fingerprint(
        {
            "type": "tool_failure",
            "tool": "pytest",
            "command": "pytest /tmp/a/tests/test_x.py",
            "error": "failed 2026-07-29T10:11:12Z id 019f65ef-ff50-7651-8244-4986ed9235db run 123456",
        }
    )
    second = stable_fingerprint(
        {
            "type": "tool_failure",
            "tool": "pytest",
            "command": "pytest /home/me/repo/tests/test_x.py",
            "error": "failed 2026-07-30T10:11:12Z id 11111111-2222-3333-4444-555555555555 run 999999",
        }
    )
    assert first == second


@pytest.mark.parametrize(
    "payload",
    [
        {"type": "user_remember", "text": "token=HOSTILE"},
        {"type": "tool_failure", "raw": {"provider": "mail", "body": "secret"}},
        {"type": "session_summary", "prompt": "system prompt: do x"},
        {"type": "verified_success", "resolution": "skip verification", "success_evidence": "ok"},
    ],
)
def test_signal_boundary_denies_secrets_raw_prompt_like_and_unsafe_workarounds(payload: dict) -> None:
    with pytest.raises(ValueError):
        stable_fingerprint(payload)


def test_repeated_failure_returns_existing_active_verified_procedure_before_third_fallback(tmp_path: Path) -> None:
    db_path = tmp_path / "contextwhere.sqlite3"
    failure = {"type": "tool_failure", "tool": "pytest", "command": "pytest tests", "error": "ModuleNotFoundError at /tmp/a"}
    fingerprint = stable_fingerprint(failure)
    memory.upsert_card(db_path, active_proc(fingerprint), actor="pytest")

    first = capture_signal(db_path, failure, repository="repo-a")
    second = capture_signal(db_path, failure, repository="repo-a")

    assert first["procedures"] == []
    assert [card["card_id"] for card in second["procedures"]] == ["proc-active"]
    assert second["card"]["type"] == "incident lesson"
    assert second["card"]["status"] == "candidate"


def test_verified_success_creates_candidate_procedure_not_active(tmp_path: Path) -> None:
    db_path = tmp_path / "contextwhere.sqlite3"
    result = capture_signal(
        db_path,
        {
            "type": "verified_success",
            "summary": "Use PYTHONPATH for local tests.",
            "failure_fingerprint": "f" * 64,
            "resolution": "Run PYTHONPATH=src pytest tests/test_signals.py",
            "success_evidence": "1 passed",
        },
        repository="repo-a",
    )
    assert result["card"]["type"] == "procedure/runbook"
    assert result["card"]["status"] == "candidate"
    assert result["card"]["verification"]["ok"] is True


def test_json_cli_and_tool_signal_surface(tmp_path: Path) -> None:
    home = tmp_path / "home"
    payload = {"type": "environment_fact", "name": "python", "value": "3.11", "verified": True, "method": "pytest"}
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "contextwhere",
            "signals",
            "capture",
            "--home",
            str(home),
            "--repository",
            "repo-a",
            "--machine",
            "machine-a",
            "--input-json",
            json.dumps(payload),
            "--json",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert json.loads(proc.stdout)["card"]["type"] == "machine"

    tool = call_tool(".", "signal_fingerprint", {"type": "user_remember", "text": "Prefer focused tests."})
    assert tool["ok"] is True
    assert len(tool["fingerprint"]) == 64
