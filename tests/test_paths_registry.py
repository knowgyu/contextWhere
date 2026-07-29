from __future__ import annotations

import json
from pathlib import Path

from contextwhere.config import resolve_global_home, resolve_paths
from contextwhere import registry


def test_resolve_global_home_uses_path_home_contextwhere_on_non_windows(monkeypatch, tmp_path):
    fake_home = tmp_path / "home"
    monkeypatch.setattr("contextwhere.config.platform.system", lambda: "Linux")
    monkeypatch.setattr("contextwhere.config.Path.home", lambda: fake_home)

    assert resolve_global_home() == fake_home / ".contextwhere"


def test_resolve_global_home_uses_userprofile_contextwhere_on_windows(monkeypatch, tmp_path):
    userprofile = tmp_path / "Users" / "alice"
    monkeypatch.setattr("contextwhere.config.platform.system", lambda: "Windows")
    monkeypatch.setenv("USERPROFILE", str(userprofile))

    assert resolve_global_home() == userprofile / ".contextwhere"


def test_resolve_global_home_falls_back_to_path_home_when_windows_userprofile_missing(monkeypatch, tmp_path):
    fake_home = tmp_path / "fallback-home"
    monkeypatch.setattr("contextwhere.config.platform.system", lambda: "Windows")
    monkeypatch.delenv("USERPROFILE", raising=False)
    monkeypatch.setattr("contextwhere.config.Path.home", lambda: fake_home)

    assert resolve_global_home() == fake_home / ".contextwhere"


def test_registry_home_override_keeps_registry_in_explicit_home(tmp_path):
    global_home = tmp_path / "portable-home" / ".contextwhere"
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    registry.register_workspace(workspace, home=global_home)

    assert registry.registry_path(global_home) == global_home / "registry.json"
    assert (global_home / "registry.json").exists()


def test_register_workspace_returns_stable_id_and_is_idempotent(tmp_path):
    global_home = tmp_path / "home" / ".contextwhere"
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    first = registry.register_workspace(workspace, home=global_home)
    second = registry.register_workspace(workspace, home=global_home)

    assert first["id"] == second["id"]
    assert [entry["id"] for entry in registry.list_entries(kind="workspace", home=global_home)] == [first["id"]]


def test_register_repository_returns_stable_id_and_resolves_entry(tmp_path):
    global_home = tmp_path / "home" / ".contextwhere"
    repo = tmp_path / "workspace" / "repo"
    repo.mkdir(parents=True)

    first = registry.register_repository(repo, home=global_home)
    second = registry.register_repository(repo, home=global_home)

    assert first["id"] == second["id"]
    assert registry.resolve(first["id"], home=global_home)["path"] == str(repo.resolve())


def test_register_normalized_equivalent_posix_paths_is_idempotent(tmp_path):
    global_home = tmp_path / "home" / ".contextwhere"
    repo = tmp_path / "workspace" / "repo"
    repo.mkdir(parents=True)
    equivalent = repo / "." / "subdir" / ".."

    first = registry.register_repository(repo, home=global_home)
    second = registry.register_repository(equivalent, home=global_home)

    assert first["id"] == second["id"]
    assert len(registry.list_entries(kind="repository", home=global_home)) == 1


def test_registry_ids_are_stable_across_reload(tmp_path):
    global_home = tmp_path / "home" / ".contextwhere"
    workspace = tmp_path / "workspace"
    repo = workspace / "repo"
    repo.mkdir(parents=True)

    workspace_entry = registry.register_workspace(workspace, home=global_home)
    repo_entry = registry.register_repository(repo, home=global_home)

    reloaded = {entry["path"]: entry["id"] for entry in registry.list_entries(home=global_home)}
    assert reloaded[str(workspace.resolve())] == workspace_entry["id"]
    assert reloaded[str(repo.resolve())] == repo_entry["id"]


def test_windows_equivalent_path_strings_have_same_stable_id():
    first = registry.stable_id("repository", "C:/Users/Alice/work/repo")
    second = registry.stable_id("repository", r"c:\Users\Alice\work\repo\.")

    assert first == second


def test_missing_paths_are_reported_without_rewriting_registry_entry(tmp_path):
    global_home = tmp_path / "home" / ".contextwhere"
    repo = tmp_path / "workspace" / "repo"
    repo.mkdir(parents=True)
    entry = registry.register_repository(repo, home=global_home)
    before = json.loads((global_home / "registry.json").read_text(encoding="utf-8"))
    repo.rmdir()

    missing = registry.missing_entries(home=global_home)
    after = json.loads((global_home / "registry.json").read_text(encoding="utf-8"))

    assert [item["id"] for item in missing] == [entry["id"]]
    assert after == before


def test_resolve_paths_repo_outputs_stay_repo_local(tmp_path):
    paths = resolve_paths(tmp_path)

    assert paths.root == tmp_path.resolve()
    assert paths.data_dir == tmp_path.resolve() / ".contextwhere"
    assert paths.db_path == tmp_path.resolve() / ".contextwhere" / "contextwhere.sqlite3"
    assert paths.wiki_dir == tmp_path.resolve() / "work_wiki"
    assert paths.draft_dir == tmp_path.resolve() / ".contextwhere" / "drafts" / "wiki"
    assert paths.audit_dir == tmp_path.resolve() / ".contextwhere" / "audit" / "wiki"


def test_global_registry_init_does_not_mutate_existing_repo_contextwhere_db(tmp_path):
    repo = tmp_path / "repo"
    repo_db = repo / ".contextwhere" / "contextwhere.sqlite3"
    repo_db.parent.mkdir(parents=True)
    repo_db.write_bytes(b"existing repo db bytes")
    global_home = tmp_path / "home" / ".contextwhere"

    registry.save_registry(registry.load_registry(global_home), home=global_home)

    assert repo_db.read_bytes() == b"existing repo db bytes"
