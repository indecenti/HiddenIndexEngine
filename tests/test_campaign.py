"""
tests/test_campaign.py

engine/campaign.py: campaign order, unlocks, resume target and what a finished
scene records. Pure logic over an in-memory save, so no game folder is needed.
"""

from __future__ import annotations

import pytest

from engine.campaign import (TIMER_COMPLETE, TIMER_FAIL, Campaign, ordered_level_ids,
                             ordered_scene_ids, timer_behavior)


class MemorySave:
    """The SaveManager surface Campaign uses, without a file."""

    def __init__(self) -> None:
        self.data = {"scores": {}, "stars": {}, "unlocked_levels": [], "unlocked_scenes": {}}

    def get_progress(self, key, default=None):
        return self.data.get(key, default)

    def unlock_level(self, level_id):
        if level_id not in self.data["unlocked_levels"]:
            self.data["unlocked_levels"].append(level_id)
            self.data["unlocked_scenes"].setdefault(level_id, 0)

    def unlock_scene(self, level_id, index):
        if index > self.data["unlocked_scenes"].get(level_id, 0):
            self.data["unlocked_scenes"][level_id] = index

    def set_scene_score(self, level_id, scene_id, score, stars):
        sc = self.data["scores"].setdefault(level_id, {})
        st = self.data["stars"].setdefault(level_id, {})
        if score > sc.get(scene_id, 0):
            sc[scene_id] = score
        if stars > st.get(scene_id, 0):
            st[scene_id] = stars


LEVELS = {
    "b_second": {"scenes": [{"id": "b1"}, {"id": "b2"}]},
    "a_first": {"scenes": [{"id": "a2", "order": 2}, {"id": "a1", "order": 1},
                           {"id": "a3", "order": 3}]},
    "empty": {"scenes": []},
}
CONFIG = {"levels": ["a_first", "b_second"]}


@pytest.fixture
def campaign():
    save = MemorySave()
    c = Campaign("__test__", save, game_config=CONFIG, level_configs=LEVELS)
    c.ensure_started()
    return c


def test_scenes_follow_their_order_field_then_position():
    cfg = {"scenes": [{"id": "x", "order": 2}, {"id": "y"}, {"id": "z", "order": 0}]}
    assert ordered_scene_ids(cfg) == ["z", "y", "x"]


def test_levels_follow_the_game_config_then_the_orphans():
    assert ordered_level_ids(["b", "a"], ["a", "c", "b", "d"]) == ["b", "a", "c", "d"]


def test_a_level_without_scenes_is_left_out_of_the_chain(campaign):
    assert campaign.levels() == ["a_first", "b_second"]


def test_an_unknown_timer_mode_is_the_relaxed_one():
    assert timer_behavior({}) == TIMER_COMPLETE
    assert timer_behavior({"timer_behavior": "FAIL"}) == TIMER_FAIL
    assert timer_behavior({"timer_behavior": "sudden_death"}) == TIMER_COMPLETE


def test_a_new_game_opens_only_the_first_scene(campaign):
    assert campaign.is_scene_unlocked("a_first", 0)
    assert not campaign.is_scene_unlocked("a_first", 1)
    assert not campaign.is_level_unlocked("b_second")
    assert not campaign.is_scene_unlocked("b_second", 0)
    assert campaign.resume_target().scene_id == "a1"
    assert not campaign.has_progress()


def test_completing_a_scene_unlocks_the_next_and_points_to_it(campaign):
    nxt = campaign.record_result("a_first", "a1", 900, 3, failed=False)
    assert (nxt.level_id, nxt.scene_id) == ("a_first", "a2")
    assert campaign.is_scene_unlocked("a_first", 1)
    assert campaign.resume_target().scene_id == "a2"
    assert campaign.has_progress()


def test_the_last_scene_opens_the_next_level(campaign):
    for sid in ("a1", "a2", "a3"):
        nxt = campaign.record_result("a_first", sid, 100, 2, failed=False)
    assert (nxt.level_id, nxt.scene_id) == ("b_second", "b1")
    assert campaign.is_level_unlocked("b_second")
    assert campaign.is_level_completed("a_first")


def test_the_end_of_the_campaign_has_no_next_step(campaign):
    for lv in campaign.levels():
        for sid in campaign.scenes(lv):
            last = campaign.record_result(lv, sid, 100, 2, failed=False)
    assert last is None
    assert campaign.resume_target() is None


def test_a_lost_scene_records_and_unlocks_nothing(campaign):
    assert campaign.record_result("a_first", "a1", 400, 1, failed=True) is None
    assert not campaign.is_scene_unlocked("a_first", 1)
    assert campaign.best_score("a_first", "a1") == 0
    assert not campaign.has_progress()


def test_a_replay_never_lowers_the_best(campaign):
    campaign.record_result("a_first", "a1", 900, 3, failed=False)
    campaign.record_result("a_first", "a1", 100, 1, failed=False)
    assert campaign.best_score("a_first", "a1") == 900
    assert campaign.best_stars("a_first", "a1") == 3


def test_the_level_progress_counts_scenes_and_stars(campaign):
    campaign.record_result("a_first", "a1", 900, 3, failed=False)
    campaign.record_result("a_first", "a2", 500, 2, failed=False)
    assert campaign.level_progress("a_first") == (2, 3, 5, 9)


def test_a_locked_scene_names_what_unlocks_it(campaign):
    req = campaign.unlock_requirement("a_first", 2)
    assert req.scene_id == "a2"
    req = campaign.unlock_requirement("b_second", 0)
    assert (req.level_id, req.scene_id) == ("a_first", "a3")
    assert campaign.unlock_requirement("a_first", 0) is None
