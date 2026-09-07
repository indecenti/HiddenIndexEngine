"""
tests/test_utils_safe_io.py

engine/utils.py holds the two calls the project's rules make mandatory: every
JSON write goes through safe_write_json, every deletion through safe_delete.
Both are the last line before losing a scene, a catalog or a save, and neither
had a test.

safe_delete works against get_base_path, so the tests point that at their own
directory: nothing here touches the repository's trash or audit log.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from engine import utils


@pytest.fixture
def base(tmp_path, monkeypatch):
    """A throwaway project root, so the trash and the audit log land in it."""
    monkeypatch.setattr(utils, "get_base_path", lambda: tmp_path)
    return tmp_path


def read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


# -----------------------------------------------------------------------------
# WRITING JSON
# -----------------------------------------------------------------------------

def test_a_write_round_trips(tmp_path):
    target = tmp_path / "scene.json"
    data = {"id": "attic", "objects": [{"x": 10, "y": 20}]}
    assert utils.safe_write_json(target, data) is True
    assert read(target) == data


def test_the_temporary_file_is_not_left_behind(tmp_path):
    target = tmp_path / "scene.json"
    utils.safe_write_json(target, {"a": 1})
    assert list(tmp_path.glob("*.tmp")) == []


def test_missing_directories_are_created(tmp_path):
    target = tmp_path / "games" / "g1" / "levels" / "scene.json"
    assert utils.safe_write_json(target, {"a": 1}) is True
    assert read(target) == {"a": 1}


def test_a_second_write_replaces_the_first(tmp_path):
    target = tmp_path / "scene.json"
    utils.safe_write_json(target, {"version": 1})
    utils.safe_write_json(target, {"version": 2})
    assert read(target) == {"version": 2}


def test_data_that_cannot_be_serialized_leaves_the_file_untouched(tmp_path):
    """Serializing first is the whole point: a bad object must not truncate
    a scene that was fine on disk."""
    target = tmp_path / "scene.json"
    utils.safe_write_json(target, {"good": True})

    class NotSerializable:
        pass

    assert utils.safe_write_json(target, {"bad": NotSerializable()}) is False
    assert read(target) == {"good": True}, "the previous content must survive"
    assert list(tmp_path.glob("*.tmp")) == [], "and no debris is left"


def test_a_write_that_fails_halfway_leaves_the_file_untouched(tmp_path, monkeypatch):
    """The replace is what makes it atomic: if it never happens, the old file
    is still the whole old file."""
    target = tmp_path / "scene.json"
    utils.safe_write_json(target, {"good": True})

    def boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(utils.os, "replace", boom)
    assert utils.safe_write_json(target, {"new": True}) is False
    assert read(target) == {"good": True}
    assert list(tmp_path.glob("*.tmp")) == [], "the orphan temporary is cleaned up"


def test_accented_text_is_written_as_itself(tmp_path):
    """ensure_ascii is off by default, so the files stay readable."""
    target = tmp_path / "strings.json"
    utils.safe_write_json(target, {"city": "Città"})
    assert "Città" in target.read_text(encoding="utf-8")
    assert read(target)["city"] == "Città"


def test_the_keys_can_be_sorted_on_request(tmp_path):
    target = tmp_path / "sorted.json"
    utils.safe_write_json(target, {"b": 1, "a": 2}, sort_keys=True)
    text = target.read_text(encoding="utf-8")
    assert text.index('"a"') < text.index('"b"')


def test_the_indent_can_be_chosen(tmp_path):
    flat = tmp_path / "flat.json"
    wide = tmp_path / "wide.json"
    utils.safe_write_json(flat, {"a": {"b": 1}}, indent=0)
    utils.safe_write_json(wide, {"a": {"b": 1}}, indent=8)
    assert len(wide.read_text(encoding="utf-8")) > len(flat.read_text(encoding="utf-8"))


def test_a_path_given_as_a_string_works_too(tmp_path):
    target = tmp_path / "scene.json"
    assert utils.safe_write_json(str(target), {"a": 1}) is True
    assert read(target) == {"a": 1}


# -----------------------------------------------------------------------------
# DELETING
# -----------------------------------------------------------------------------

def trash_files(base: Path) -> list[Path]:
    root = base / ".editor_trash"
    return sorted(p for p in root.rglob("*") if p.is_file()) if root.exists() else []


def test_a_deleted_file_goes_to_the_trash_instead_of_disappearing(base):
    victim = base / "games" / "g1" / "scene.json"
    victim.parent.mkdir(parents=True)
    victim.write_text('{"keep": "me"}', encoding="utf-8")

    assert utils.safe_delete(victim, reason="test") is True

    assert not victim.exists()
    saved = trash_files(base)
    assert len(saved) == 1
    assert saved[0].read_text(encoding="utf-8") == '{"keep": "me"}'


def test_the_trash_keeps_the_path_the_file_came_from(base):
    victim = base / "games" / "g1" / "levels" / "scene.json"
    victim.parent.mkdir(parents=True)
    victim.write_text("x", encoding="utf-8")

    utils.safe_delete(victim)

    saved = trash_files(base)[0]
    assert saved.parts[-4:] == ("games", "g1", "levels", "scene.json")


def test_deleting_what_is_not_there_is_not_an_error(base):
    assert utils.safe_delete(base / "never_existed.json") is True


def test_a_whole_directory_can_be_deleted(base):
    victim = base / "games" / "g1"
    (victim / "levels").mkdir(parents=True)
    (victim / "levels" / "scene.json").write_text("x", encoding="utf-8")
    (victim / "config.json").write_text("y", encoding="utf-8")

    assert utils.safe_delete(victim) is True

    assert not victim.exists()
    assert len(trash_files(base)) == 2, "everything under it must be kept"


def test_deleting_the_same_name_twice_keeps_both_copies(base):
    for content in ("first", "second"):
        victim = base / "scene.json"
        victim.write_text(content, encoding="utf-8")
        assert utils.safe_delete(victim) is True

    saved = trash_files(base)
    assert len(saved) == 2, "the second delete must not overwrite the first"
    assert {p.read_text(encoding="utf-8") for p in saved} == {"first", "second"}


def test_every_deletion_is_written_down(base):
    victim = base / "scene.json"
    victim.write_text("x", encoding="utf-8")
    utils.safe_delete(victim, reason="removed by the auditor")

    log = (base / ".editor_audit.log").read_text(encoding="utf-8")
    assert "DELETE" in log
    assert "scene.json" in log
    assert "removed by the auditor" in log


def test_the_empty_folder_left_behind_can_be_swept_up(base):
    victim = base / "games" / "g1" / "only_child.json"
    victim.parent.mkdir(parents=True)
    victim.write_text("x", encoding="utf-8")

    utils.safe_delete(victim, also_remove_empty_parent=True)

    assert not (base / "games" / "g1").exists()


def test_a_folder_with_something_left_in_it_is_kept(base):
    victim = base / "games" / "g1" / "one.json"
    victim.parent.mkdir(parents=True)
    victim.write_text("x", encoding="utf-8")
    (base / "games" / "g1" / "two.json").write_text("y", encoding="utf-8")

    utils.safe_delete(victim, also_remove_empty_parent=True)

    assert (base / "games" / "g1" / "two.json").exists()


def test_a_file_from_outside_the_project_is_still_kept(base, tmp_path):
    outside = tmp_path.parent / "outside_the_project.json"
    outside.write_text("stranger", encoding="utf-8")
    try:
        assert utils.safe_delete(outside) is True
        saved = trash_files(base)
        assert len(saved) == 1
        assert saved[0].name == "outside_the_project.json"
    finally:
        outside.unlink(missing_ok=True)


# -----------------------------------------------------------------------------
# EMPTYING THE TRASH
# -----------------------------------------------------------------------------

def test_old_sessions_are_purged_and_recent_ones_kept(base):
    trash = base / ".editor_trash"
    old = trash / "20200101_120000"
    recent = trash / _now_stamp()
    for session in (old, recent):
        session.mkdir(parents=True)
        (session / "scene.json").write_text("x", encoding="utf-8")

    removed = utils.cleanup_trash(max_age_days=7)

    assert removed == 1
    assert not old.exists()
    assert recent.exists()


def test_a_folder_that_is_not_a_session_is_left_alone(base):
    trash = base / ".editor_trash"
    stranger = trash / "not_a_timestamp"
    stranger.mkdir(parents=True)
    (stranger / "file.txt").write_text("x", encoding="utf-8")

    assert utils.cleanup_trash(max_age_days=0) == 0
    assert stranger.exists()


def test_emptying_a_trash_that_was_never_used_is_free(base):
    assert utils.cleanup_trash() == 0


def _now_stamp() -> str:
    import datetime
    return datetime.datetime.now().strftime("%Y%m%d_%H%M%S")


# -----------------------------------------------------------------------------
# PATHS
# -----------------------------------------------------------------------------

def test_a_writable_path_has_its_folder_ready(base, monkeypatch):
    monkeypatch.setattr(utils, "is_android_runtime", lambda: False)
    path = utils.get_writable_path("save_game.json")
    assert path.parent.is_dir(), "the saves folder must exist before writing"
    assert path.parent.name == "saves"


def test_a_writable_subfolder_is_created_too(base, monkeypatch):
    monkeypatch.setattr(utils, "is_android_runtime", lambda: False)
    path = utils.get_writable_path("profiles", "player1.json")
    assert path.parent.is_dir()


def test_a_resource_that_exists_is_found_where_it_is(base):
    asset = base / "engine" / "assets" / "icon.png"
    asset.parent.mkdir(parents=True)
    asset.write_bytes(b"png")
    assert utils.get_resource_path("engine", "assets", "icon.png") == asset


def test_a_resource_that_is_missing_still_answers_with_a_path(base):
    """The caller checks exists() itself; the helper must not raise."""
    path = utils.get_resource_path("engine", "assets", "nope.png")
    assert path == base / "engine" / "assets" / "nope.png"
    assert not path.exists()


def test_the_android_runtime_is_recognised_by_its_environment(monkeypatch):
    monkeypatch.delenv("ANDROID_ARGUMENT", raising=False)
    assert utils.is_android_runtime() is False
    monkeypatch.setenv("ANDROID_ARGUMENT", "/data/data/app")
    assert utils.is_android_runtime() is True
