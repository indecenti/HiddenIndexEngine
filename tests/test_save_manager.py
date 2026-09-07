"""
tests/test_save_manager.py

The player's progress: engine/save_manager.py is the only thing standing
between a finished level and losing it. It had no test at all.

Covers the round trip, a missing file, a corrupt one, a save written by an
older version of the game, and the record keeping of scores and stars.
"""

from __future__ import annotations

import json

import pytest

from engine.save_manager import SaveManager


@pytest.fixture
def saves_dir(tmp_path, monkeypatch):
    """Redirect the save file into the test's own directory."""
    import engine.save_manager as sm

    target = tmp_path / "saves"
    target.mkdir()
    monkeypatch.setattr(sm, "get_writable_path",
                        lambda name: target / name, raising=True)
    return target


@pytest.fixture
def manager(saves_dir):
    return SaveManager("test_game")


def read_file(saves_dir) -> dict:
    path = saves_dir / "save_test_game.json"
    return json.loads(path.read_text(encoding="utf-8"))


# -----------------------------------------------------------------------------
# FIRST RUN AND ROUND TRIP
# -----------------------------------------------------------------------------

def test_a_first_run_writes_a_blank_save(saves_dir):
    manager = SaveManager("test_game")
    path = saves_dir / "save_test_game.json"
    assert path.exists(), "the first run must leave a save on disk"
    assert manager.data["unlocked_levels"] == []
    assert manager.data["scores"] == {}
    assert read_file(saves_dir)["version"] == "1.0"


def test_progress_survives_a_restart(saves_dir):
    first = SaveManager("test_game")
    first.unlock_level("level_1")
    first.unlock_scene("level_1", 3)
    first.set_scene_score("level_1", "attic", 4200, 3)
    first.set_progress("current_scene", "attic")

    second = SaveManager("test_game")
    assert second.data["unlocked_levels"] == ["level_1"]
    assert second.data["unlocked_scenes"]["level_1"] == 3
    assert second.data["scores"]["level_1"]["attic"] == 4200
    assert second.data["stars"]["level_1"]["attic"] == 3
    assert second.get_progress("current_scene") == "attic"


def test_two_games_keep_separate_progress(saves_dir):
    one = SaveManager("game_one")
    SaveManager("game_two")
    one.unlock_level("level_1")
    assert SaveManager("game_two").data["unlocked_levels"] == []
    assert SaveManager("game_one").data["unlocked_levels"] == ["level_1"]


# -----------------------------------------------------------------------------
# A DAMAGED FILE MUST NOT COST THE PLAYER THEIR PROGRESS
# -----------------------------------------------------------------------------

def test_a_corrupt_save_is_quarantined_not_overwritten(saves_dir):
    """The unreadable file stays on disk: it may still be recoverable by hand."""
    path = saves_dir / "save_test_game.json"
    path.write_text('{"unlocked_levels": ["level_1", "level_', encoding="utf-8")

    manager = SaveManager("test_game")

    assert manager.data["unlocked_levels"] == [], "must start from a clean state"
    quarantined = list(saves_dir.glob("save_test_game.json.corrupt-*"))
    assert len(quarantined) == 1, "the damaged file must be kept aside"
    assert "level_1" in quarantined[0].read_text(encoding="utf-8")
    assert path.exists(), "a fresh save must take its place"


def test_an_empty_file_is_treated_as_corrupt(saves_dir):
    (saves_dir / "save_test_game.json").write_text("", encoding="utf-8")
    manager = SaveManager("test_game")
    assert manager.data["scores"] == {}
    assert list(saves_dir.glob("*.corrupt-*"))


# -----------------------------------------------------------------------------
# A SAVE WRITTEN BY AN OLDER VERSION
# -----------------------------------------------------------------------------

def test_keys_the_old_save_never_had_come_from_the_defaults(saves_dir):
    """A save from before a field existed must still load, not crash."""
    (saves_dir / "save_test_game.json").write_text(json.dumps({
        "version": "0.9",
        "unlocked_levels": ["level_1"],
        "scores": {"level_1": {"attic": 100}},
    }), encoding="utf-8")

    manager = SaveManager("test_game")

    assert manager.data["unlocked_levels"] == ["level_1"]
    assert manager.data["scores"]["level_1"]["attic"] == 100
    # Never written by that version, so they come from the blueprint.
    assert manager.data["stars"] == {}
    assert manager.data["unlocked_scenes"] == {}
    assert manager.data["achievements"] == []


def test_a_score_for_a_level_with_no_stars_yet_does_not_crash(saves_dir):
    """Half written progress: scores knows the level, stars does not.

    Reachable from any save produced before stars existed, and from any
    partial write: set_scene_score only creates the stars branch when the
    scores one is missing too, so the two can be out of step.
    """
    (saves_dir / "save_test_game.json").write_text(json.dumps({
        "scores": {"level_1": {"attic": 100}},
        "stars": {},
    }), encoding="utf-8")

    manager = SaveManager("test_game")
    manager.set_scene_score("level_1", "attic", 500, 2)

    assert manager.data["scores"]["level_1"]["attic"] == 500
    assert manager.data["stars"]["level_1"]["attic"] == 2


# -----------------------------------------------------------------------------
# SCORES AND STARS KEEP THE BEST RUN
# -----------------------------------------------------------------------------

def test_a_better_run_replaces_the_record(manager):
    manager.set_scene_score("level_1", "attic", 100, 1)
    manager.set_scene_score("level_1", "attic", 900, 3)
    assert manager.data["scores"]["level_1"]["attic"] == 900
    assert manager.data["stars"]["level_1"]["attic"] == 3


def test_a_worse_run_leaves_the_record_alone(manager):
    manager.set_scene_score("level_1", "attic", 900, 3)
    manager.set_scene_score("level_1", "attic", 100, 1)
    assert manager.data["scores"]["level_1"]["attic"] == 900
    assert manager.data["stars"]["level_1"]["attic"] == 3


def test_score_and_stars_are_recorded_apart(manager):
    """More points with fewer stars keeps the best of each."""
    manager.set_scene_score("level_1", "attic", 100, 3)
    manager.set_scene_score("level_1", "attic", 900, 1)
    assert manager.data["scores"]["level_1"]["attic"] == 900
    assert manager.data["stars"]["level_1"]["attic"] == 3


def test_scenes_of_the_same_level_are_scored_apart(manager):
    manager.set_scene_score("level_1", "attic", 100, 1)
    manager.set_scene_score("level_1", "cellar", 200, 2)
    assert manager.data["scores"]["level_1"] == {"attic": 100, "cellar": 200}


# -----------------------------------------------------------------------------
# UNLOCKING
# -----------------------------------------------------------------------------

def test_unlocking_a_level_opens_its_first_scene(manager):
    manager.unlock_level("level_1")
    assert manager.data["unlocked_scenes"]["level_1"] == 0
    assert manager.is_scene_unlocked("level_1", 0)
    assert not manager.is_scene_unlocked("level_1", 1)


def test_unlocking_the_same_level_twice_changes_nothing(manager):
    manager.unlock_level("level_1")
    manager.unlock_scene("level_1", 4)
    manager.unlock_level("level_1")
    assert manager.data["unlocked_levels"] == ["level_1"]
    assert manager.data["unlocked_scenes"]["level_1"] == 4, "must not go back to 0"


def test_scenes_only_ever_unlock_forward(manager):
    manager.unlock_level("level_1")
    manager.unlock_scene("level_1", 3)
    manager.unlock_scene("level_1", 1)
    assert manager.data["unlocked_scenes"]["level_1"] == 3
    assert manager.is_scene_unlocked("level_1", 3)
    assert not manager.is_scene_unlocked("level_1", 4)


def test_a_scene_of_an_unknown_level_is_locked_past_the_first(manager):
    assert manager.is_scene_unlocked("never_seen", 0)
    assert not manager.is_scene_unlocked("never_seen", 1)


# -----------------------------------------------------------------------------
# RESET
# -----------------------------------------------------------------------------

def test_reset_clears_everything_on_disk_too(saves_dir):
    manager = SaveManager("test_game")
    manager.unlock_level("level_1")
    manager.set_scene_score("level_1", "attic", 500, 2)

    manager.reset_progress()

    assert manager.data["unlocked_levels"] == []
    assert manager.data["scores"] == {}
    assert read_file(saves_dir)["scores"] == {}
    assert SaveManager("test_game").data["unlocked_levels"] == []


# -----------------------------------------------------------------------------
# THE WRITE ITSELF
# -----------------------------------------------------------------------------

def test_every_change_reaches_the_disk_immediately(saves_dir):
    """The game can be killed at any moment: nothing may stay only in memory."""
    manager = SaveManager("test_game")
    manager.set_progress("current_level", "level_2")
    assert read_file(saves_dir)["current_level"] == "level_2"
    manager.unlock_level("level_2")
    assert read_file(saves_dir)["unlocked_levels"] == ["level_2"]
    manager.set_scene_score("level_2", "hall", 10, 1)
    assert read_file(saves_dir)["scores"]["level_2"]["hall"] == 10


def test_a_failed_write_leaves_the_previous_save_intact(saves_dir, monkeypatch):
    """An atomic write means a broken one never truncates what was there."""
    manager = SaveManager("test_game")
    manager.set_scene_score("level_1", "attic", 500, 2)
    good = read_file(saves_dir)

    import engine.save_manager as sm
    monkeypatch.setattr(sm, "safe_write_json", lambda *a, **k: False)
    manager.set_scene_score("level_1", "attic", 900, 3)

    assert read_file(saves_dir) == good, "the file on disk must not be damaged"
