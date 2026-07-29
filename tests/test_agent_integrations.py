from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def run_cw(args: list[str], *, home: Path, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    merged = os.environ.copy()
    merged.update({"PYTHONPATH": str(REPO_ROOT / "src"), "HOME": str(home), "USERPROFILE": str(home), "PATH": ""})
    if env:
        merged.update(env)
    return subprocess.run([sys.executable, "-m", "contextwhere", *args], cwd=REPO_ROOT, env=merged, text=True, capture_output=True, check=False)


def payload(result: subprocess.CompletedProcess[str]) -> dict:
    assert result.returncode == 0, result.stderr or result.stdout
    return json.loads(result.stdout)


def cw_home(home: Path) -> Path:
    return home / ".contextwhere"


def test_integration_install_status_uninstall_is_marker_bounded_and_idempotent(tmp_path: Path) -> None:
    home = tmp_path / "home"
    codex_agents = home / ".codex" / "AGENTS.md"
    codex_agents.parent.mkdir(parents=True)
    codex_agents.write_text("keep me\n", encoding="utf-8")

    dry = payload(run_cw(["integrations", "install", "--home", str(cw_home(home)), "--agent", "codex", "--dry-run", "--json"], home=home))
    assert dry["dry_run"] is True
    assert codex_agents.read_text(encoding="utf-8") == "keep me\n"

    first = payload(run_cw(["integrations", "install", "--home", str(cw_home(home)), "--agent", "codex", "--json"], home=home))
    assert first["integrations"]["codex"]["installed"] is True
    assert first["integrations"]["codex"]["available"] is False
    assert "BEGIN contextWhere agent bridge" in codex_agents.read_text(encoding="utf-8")
    assert (home / ".codex" / "AGENTS.md.contextwhere.bak").read_text(encoding="utf-8") == "keep me\n"
    assert (home / ".codex" / "skills" / "contextwhere-memory" / "SKILL.md").exists()

    second = payload(run_cw(["integrations", "install", "--home", str(cw_home(home)), "--agent", "codex", "--json"], home=home))
    assert second["actions"] == []
    assert second["idempotent"] is True

    gone = payload(run_cw(["integrations", "uninstall", "--home", str(cw_home(home)), "--agent", "codex", "--json"], home=home))
    assert gone["integrations"]["codex"]["installed"] is False
    assert codex_agents.read_text(encoding="utf-8") == "keep me\n"
    assert not (home / ".codex" / "skills" / "contextwhere-memory" / "SKILL.md").exists()


def test_setup_and_doctor_report_integrations_without_requiring_agents(tmp_path: Path) -> None:
    home = tmp_path / "home"
    setup = payload(run_cw(["setup", "--home", str(cw_home(home)), "--json"], home=home))
    assert setup["ok"] is True
    assert setup["agent_bridges"]["status"] in {"not_installed", "installed"}
    assert set(setup["integrations"]) == {"codex", "claude", "gemini"}
    assert all(item["safe_to_continue"] for item in setup["integrations"].values())

    doctor = payload(run_cw(["doctor", "--home", str(cw_home(home)), "--json"], home=home))
    assert doctor["ok"] is True
    assert any(check["code"] == "integration_codex" for check in doctor["checks"])


def test_integrations_use_windows_userprofile_fake_home(tmp_path: Path) -> None:
    profile = tmp_path / "Users" / "alice"
    env = {"CONTEXTWHERE_TEST_PLATFORM": "Windows", "USERPROFILE": str(profile), "HOME": str(tmp_path / "posix")}
    result = payload(run_cw(["integrations", "install", "--agent", "gemini", "--json"], home=profile, env=env))
    assert Path(result["home"]) == profile
    assert (profile / ".gemini" / "GEMINI.md").exists()
    assert (profile / ".gemini" / "commands" / "contextwhere.toml").exists()
