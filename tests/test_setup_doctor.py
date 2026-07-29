from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]


def run_cw(args: list[str], *, home: Path, cwd: Path | None = None, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    merged = os.environ.copy()
    merged.update(
        {
            "PYTHONPATH": str(REPO_ROOT / "src"),
            "HOME": str(home),
            "USERPROFILE": str(home),
            "UV_CACHE_DIR": str(REPO_ROOT / ".uv-cache"),
        }
    )
    if env:
        merged.update(env)
    return subprocess.run(
        [sys.executable, "-m", "contextwhere", *args],
        cwd=cwd or REPO_ROOT,
        env=merged,
        text=True,
        capture_output=True,
        check=False,
    )


def payload(result: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    assert result.stdout, result.stderr
    return json.loads(result.stdout)


def assert_ok(result: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    data = payload(result)
    assert result.returncode == 0, result.stderr or result.stdout
    assert data["ok"] is True
    return data


def assert_not_ok(result: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    data = payload(result)
    assert result.returncode != 0, result.stdout
    assert data["ok"] is False
    assert data.get("error") or data.get("issues")
    return data


def file_hashes(root: Path) -> dict[str, str]:
    if not root.exists():
        return {}
    return {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def cw_home(home: Path) -> Path:
    return home / ".contextwhere"


def card(card_id: str, status: str = "observed", scope_key: str = "repo-a", summary: str | None = None) -> dict[str, Any]:
    return {
        "card_id": card_id,
        "version": "context-card-v1",
        "type": "constraint/preference",
        "summary": summary or f"Remember {card_id}",
        "scope": {"type": "repository", "key": scope_key},
        "status": status,
        "sensitivity": "internal",
        "confidence": "medium",
        "evidence_ids": [f"ev-{card_id}"],
        "source_locators": [f"pytest:{card_id}"],
        "freshness": {"observed_at": "2026-07-29T00:00:00+00:00", "stale_after": "2099-01-01T00:00:00+00:00"},
        "rule": f"Use {card_id}",
    }


def write_json(path: Path, data: dict[str, Any]) -> Path:
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def memory_args(home: Path, subcommand: str, *rest: str, scope_key: str = "repo-a") -> list[str]:
    return [
        "memory",
        subcommand,
        "--home",
        str(cw_home(home)),
        "--scope-type",
        "repository",
        "--scope-key",
        scope_key,
        *rest,
        "--json",
    ]


def test_memory_lifecycle_cli_enforces_transitions_and_writes_audit(tmp_path: Path) -> None:
    home = tmp_path / "home"
    first = write_json(tmp_path / "first.json", card("cli-card", status="observed"))
    second = write_json(tmp_path / "second.json", card("cli-card-v2", status="active", summary="Corrected card"))

    observed = assert_ok(run_cw(memory_args(home, "observe", "--input-file", str(first), "--reason", "remembered"), home=home))
    assert observed["card"]["card_id"] == "cli-card"
    assert observed["card"]["status"] == "observed"
    assert observed["audit"][-1]["reason"] == "remembered"

    illegal = assert_not_ok(run_cw(memory_args(home, "promote", "cli-card", "--to", "active", "--reason", "skip review"), home=home))
    assert "illegal" in json.dumps(illegal).lower()

    assert_ok(run_cw(memory_args(home, "promote", "cli-card", "--to", "candidate", "--reason", "triaged"), home=home))
    active = assert_ok(run_cw(memory_args(home, "promote", "cli-card", "--to", "active", "--reason", "verified"), home=home))
    assert active["card"]["status"] == "active"

    replacement = assert_ok(run_cw(memory_args(home, "supersede", "cli-card", "--input-file", str(second), "--reason", "correction"), home=home))
    assert replacement["old"]["status"] == "superseded"
    assert replacement["new"]["card_id"] == "cli-card-v2"
    assert replacement["new"]["supersedes"] == ["cli-card"]
    assert [event["to_status"] for event in replacement["audit"] if event["card_id"] == "cli-card"] == ["observed", "candidate", "active", "superseded"]

    reject_file = write_json(tmp_path / "reject.json", card("reject-me", status="candidate"))
    assert_ok(run_cw(memory_args(home, "observe", "--input-file", str(reject_file), "--reason", "candidate"), home=home))
    rejected = assert_ok(run_cw(memory_args(home, "reject", "reject-me", "--reason", "wrong"), home=home))
    assert rejected["card"]["status"] == "rejected"
    assert rejected["audit"][-1]["reason"] == "wrong"


def test_memory_list_show_and_preflight_are_explicit_home_and_scope_isolated(tmp_path: Path) -> None:
    home_a = tmp_path / "home-a"
    home_b = tmp_path / "home-b"
    for payload_card in [
        card("repo-a-active", status="active", scope_key="repo-a"),
        card("repo-b-active", status="active", scope_key="repo-b"),
        card("repo-a-candidate", status="candidate", scope_key="repo-a"),
    ]:
        path = write_json(tmp_path / f"{payload_card['card_id']}.json", payload_card)
        assert_ok(run_cw(memory_args(home_a, "observe", "--input-file", str(path), "--reason", "seed", scope_key=payload_card["scope"]["key"]), home=home_a))

    other = write_json(tmp_path / "other.json", card("other-home", status="active", scope_key="repo-a"))
    assert_ok(run_cw(memory_args(home_b, "observe", "--input-file", str(other), "--reason", "seed"), home=home_b))

    listed = assert_ok(run_cw(memory_args(home_a, "list"), home=home_a))
    assert {item["card_id"] for item in listed["cards"]} == {"repo-a-active", "repo-a-candidate"}

    shown = assert_ok(run_cw(memory_args(home_a, "show", "repo-a-active"), home=home_a))
    assert shown["card"]["card_id"] == "repo-a-active"
    assert shown["audit"]

    preflight = assert_ok(run_cw(["preflight", "--home", str(cw_home(home_a)), "--repository", "repo-a", "--machine", "machine-a", "--limit", "5", "--json"], home=home_a))
    assert [item["card_id"] for item in preflight["cards"]] == ["repo-a-active"]
    assert preflight["scope"] == {"repository": "repo-a", "machine": "machine-a"}
    assert "other-home" not in json.dumps(preflight)


def test_setup_dry_run_is_non_mutating_and_reports_agent_bridges_deferred(tmp_path: Path) -> None:
    home = tmp_path / "home"
    repo = tmp_path / "repo"
    repo_db = repo / ".contextwhere" / "contextwhere.sqlite3"
    repo_db.parent.mkdir(parents=True)
    repo_db.write_bytes(b"existing repo bytes")

    result = assert_ok(run_cw(["setup", "--home", str(cw_home(home)), "--dry-run", "--json"], home=home, cwd=repo))
    assert result["dry_run"] is True
    assert result["actions"]
    assert all(item["reason"] == "deferred" for item in result["integrations"].values())
    assert not cw_home(home).exists()
    assert repo_db.read_bytes() == b"existing repo bytes"


def test_setup_twice_is_idempotent_and_does_not_install_p0_agent_bridges(tmp_path: Path) -> None:
    home = tmp_path / "home"
    args = ["setup", "--home", str(cw_home(home)), "--json"]

    first = assert_ok(run_cw(args, home=home))
    before = file_hashes(home)
    second = assert_ok(run_cw(args, home=home))
    assert second["actions"] == []
    assert file_hashes(home) == before
    assert all(item["available"] is False and item["reason"] == "deferred" for item in first["integrations"].values())
    assert all(item["available"] is False and item["reason"] == "deferred" for item in second["integrations"].values())
    assert not (home / ".codex").exists()
    assert not (home / ".claude").exists()
    assert not (home / ".gemini").exists()


def test_doctor_reports_fresh_missing_corrupt_and_unreadable_actionable_status(tmp_path: Path) -> None:
    home = tmp_path / "home"
    assert_ok(run_cw(["setup", "--home", str(cw_home(home)), "--json"], home=home))

    fresh = assert_ok(run_cw(["doctor", "--home", str(cw_home(home)), "--json"], home=home))
    assert fresh["issues"] == []

    missing = assert_not_ok(run_cw(["doctor", "--home", str(tmp_path / "missing"), "--json"], home=home))
    assert any(check["code"] == "missing_dir" and check.get("path") for check in missing["issues"])

    registry = cw_home(home) / "registry.json"
    registry.write_text("{not json", encoding="utf-8")
    corrupt = assert_not_ok(run_cw(["doctor", "--home", str(cw_home(home)), "--json"], home=home))
    assert any(check["code"] == "registry_invalid" and "JSONDecodeError" in check["message"] and check.get("path") for check in corrupt["issues"])

    registry.unlink()
    registry.mkdir()
    unreadable = assert_not_ok(run_cw(["doctor", "--home", str(cw_home(home)), "--json"], home=home))
    assert any(check["code"] == "registry_invalid" and "IsADirectoryError" in check["message"] and check.get("path") for check in unreadable["issues"])


def test_setup_and_doctor_use_windows_userprofile_home_when_simulated(tmp_path: Path) -> None:
    userprofile = tmp_path / "Users" / "alice"
    env = {"CONTEXTWHERE_TEST_PLATFORM": "Windows", "USERPROFILE": str(userprofile), "HOME": str(tmp_path / "ignored-posix-home")}

    setup = assert_ok(run_cw(["setup", "--json"], home=userprofile, env=env))
    assert Path(setup["home"]) == userprofile / ".contextwhere"
    assert (userprofile / ".contextwhere").exists()

    doctor = assert_ok(run_cw(["doctor", "--json"], home=userprofile, env=env))
    assert Path(doctor["home"]) == userprofile / ".contextwhere"
    assert doctor["platform"] == "Windows"
