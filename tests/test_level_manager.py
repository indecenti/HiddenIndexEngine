"""
tests/test_level_manager.py

Scoring and rewards of engine/level_manager.py, the module that decides what
a finished scene is worth. It had no test, and the web runtime replicates
these same formulas (see docs/web/WEB_EXPORT_SYNC.md), so a drift here is a
drift between the two builds of the same game.

The scoring entry points are pure static methods, so they are exercised
directly. RewardTracker only needs its config dict.
"""

from __future__ import annotations

import pytest

from engine.level_manager import (
    BONUS_TIME_MAX,
    MISS_PENALTY_CURVE,
    POINTS_PER_OBJECT,
    STAR_MULTIPLIER,
    LevelManager,
    RewardTracker,
)


def score_of(found, total, scene_score, elapsed, total_time, failed=False):
    return LevelManager.compute_scene_score(
        found, total, scene_score, elapsed, total_time, failed)


# -----------------------------------------------------------------------------
# TIME BONUS
# -----------------------------------------------------------------------------

def test_finding_everything_instantly_earns_the_whole_bonus():
    bonus, stars, _score = score_of(5, 5, 500, 0.0, 100.0)
    assert bonus == BONUS_TIME_MAX
    assert stars == 3


def test_the_bonus_shrinks_with_the_time_taken():
    half, _, _ = score_of(5, 5, 500, 50.0, 100.0)
    most, _, _ = score_of(5, 5, 500, 10.0, 100.0)
    assert half == BONUS_TIME_MAX // 2
    assert most > half


def test_running_out_of_time_earns_no_bonus_instead_of_a_negative_one():
    """Overtime must floor at zero, never turn into points taken away."""
    bonus, stars, score = score_of(5, 5, 500, 150.0, 100.0)
    assert bonus == 0
    assert stars == 2
    assert score > 0


def test_a_scene_with_no_time_limit_earns_no_bonus():
    bonus, _stars, _score = score_of(5, 5, 500, 0.0, 0.0)
    assert bonus == 0


def test_missing_one_object_cancels_the_bonus():
    bonus, stars, _score = score_of(4, 5, 400, 0.0, 100.0)
    assert bonus == 0
    assert stars == 1


def test_failing_cancels_the_bonus_however_fast_it_was():
    bonus, stars, _score = score_of(5, 5, 500, 0.0, 100.0, failed=True)
    assert bonus == 0
    assert stars == 1


# -----------------------------------------------------------------------------
# STARS
# -----------------------------------------------------------------------------

def test_three_stars_need_everything_found_and_two_thirds_of_the_bonus():
    """The cut is at 66% of the maximum bonus, so at a third of the time."""
    elapsed_at_cut = 100.0 * (1 - 0.66)
    _b, just_under, _s = score_of(5, 5, 500, elapsed_at_cut + 1.0, 100.0)
    _b, just_over, _s = score_of(5, 5, 500, elapsed_at_cut - 1.0, 100.0)
    assert just_under == 2
    assert just_over == 3


def test_two_stars_for_everything_found_but_slowly():
    _bonus, stars, _score = score_of(5, 5, 500, 90.0, 100.0)
    assert stars == 2


def test_one_star_whenever_something_is_left_behind():
    for found in (0, 1, 4):
        _bonus, stars, _score = score_of(found, 5, found * 100, 0.0, 100.0)
        assert stars == 1, f"{found}/5 should be one star"


# -----------------------------------------------------------------------------
# THE FINAL SCORE
# -----------------------------------------------------------------------------

def test_the_star_multiplier_is_applied_to_points_plus_bonus():
    bonus, stars, score = score_of(5, 5, 500, 0.0, 100.0)
    assert score == (500 + bonus) * STAR_MULTIPLIER[stars]


@pytest.mark.parametrize("stars", sorted(STAR_MULTIPLIER))
def test_only_three_stars_double_the_score(stars):
    assert STAR_MULTIPLIER[stars] == (2 if stars == 3 else 1)


def test_a_score_dragged_below_zero_by_penalties_stays_negative():
    """Misses can take more than the finds gave: the result must not be faked."""
    _bonus, stars, score = score_of(1, 5, -300, 10.0, 100.0)
    assert stars == 1
    assert score == -300


def test_a_scene_with_no_objects_to_find_is_treated_as_complete():
    """Zero of zero counts as everything found. Pinned, not endorsed: a scene
    with no goal object earns the full bonus and three stars."""
    bonus, stars, _score = score_of(0, 0, 0, 0.0, 100.0)
    assert bonus == BONUS_TIME_MAX
    assert stars == 3


# -----------------------------------------------------------------------------
# MISS PENALTY
# -----------------------------------------------------------------------------

def test_the_penalty_grows_with_the_streak():
    penalties = [LevelManager.miss_penalty(n) for n in range(1, len(MISS_PENALTY_CURVE) + 1)]
    assert penalties == MISS_PENALTY_CURVE
    assert penalties == sorted(penalties), "the curve must never go down"


def test_the_penalty_stops_growing_at_the_end_of_the_curve():
    last = MISS_PENALTY_CURVE[-1]
    assert LevelManager.miss_penalty(len(MISS_PENALTY_CURVE)) == last
    assert LevelManager.miss_penalty(len(MISS_PENALTY_CURVE) + 50) == last


@pytest.mark.parametrize("streak", [0, -1, -100])
def test_a_streak_below_one_is_charged_as_the_first_miss(streak):
    assert LevelManager.miss_penalty(streak) == MISS_PENALTY_CURVE[0]


def test_a_miss_is_always_worth_a_fraction_of_a_find():
    """The first miss must not wipe out more than one found object."""
    assert MISS_PENALTY_CURVE[0] < POINTS_PER_OBJECT


# -----------------------------------------------------------------------------
# REWARD TRACKER: EARNING HINTS
# -----------------------------------------------------------------------------

def finds_to_next_hint(tracker: RewardTracker, limit: int = 40) -> int:
    """How many finds it takes to be granted the next hint."""
    for n in range(1, limit + 1):
        _combo, earned, _bonus = tracker.on_object_found(dt_since_scene_start=10.0)
        if earned:
            return n
    raise AssertionError(f"no hint after {limit} finds")


def test_the_hints_get_harder_to_earn_within_a_scene():
    """Five finds for the first extra hint, then seven, then nine."""
    tracker = RewardTracker({}, initial_hints=2)
    assert finds_to_next_hint(tracker) == 5
    assert finds_to_next_hint(tracker) == 7
    assert finds_to_next_hint(tracker) == 9


def test_earning_a_hint_adds_it_to_the_pool():
    tracker = RewardTracker({}, initial_hints=2)
    finds_to_next_hint(tracker)
    assert tracker.get_available_hints() == 3
    assert tracker.get_stats()["earned_this_scene"] == 1


def test_the_progress_bar_resets_after_a_hint_and_never_passes_one():
    tracker = RewardTracker({}, initial_hints=0)
    for _ in range(3):
        tracker.on_object_found(dt_since_scene_start=10.0)
        assert 0.0 <= tracker.get_earn_progress() <= 1.0
    finds_to_next_hint(tracker)
    assert tracker.get_earn_progress() == 0.0


def test_a_hint_is_spent_only_when_there_is_one():
    tracker = RewardTracker({}, initial_hints=1)
    assert tracker.consume_hint() is True
    assert tracker.get_available_hints() == 0
    assert tracker.consume_hint() is False
    assert tracker.get_available_hints() == 0, "must never go below zero"


def test_a_granted_hint_can_be_added_by_hand():
    tracker = RewardTracker({}, initial_hints=0)
    tracker.add_hint()
    assert tracker.get_available_hints() == 1
    assert tracker.get_stats()["earned_this_scene"] == 1


# -----------------------------------------------------------------------------
# REWARD TRACKER: THE OPENING BONUS
# -----------------------------------------------------------------------------

def test_the_first_find_within_a_second_pays_a_bonus():
    tracker = RewardTracker({}, initial_hints=0)
    _combo, _earned, bonus = tracker.on_object_found(dt_since_scene_start=0.5)
    assert bonus == 50
    assert tracker.get_stats()["first_second_bonus_earned"] is True


def test_the_opening_bonus_can_be_retuned_from_the_config():
    tracker = RewardTracker({"hint_earn_config": {"first_second_bonus": 120}})
    _combo, _earned, bonus = tracker.on_object_found(dt_since_scene_start=0.9)
    assert bonus == 120


def test_a_slower_first_find_pays_nothing():
    tracker = RewardTracker({}, initial_hints=0)
    _combo, _earned, bonus = tracker.on_object_found(dt_since_scene_start=1.1)
    assert bonus == 0
    assert tracker.get_stats()["first_second_bonus_earned"] is False


def test_the_opening_bonus_is_paid_once_per_scene():
    tracker = RewardTracker({}, initial_hints=0)
    tracker.on_object_found(dt_since_scene_start=0.1)
    _combo, _earned, second = tracker.on_object_found(dt_since_scene_start=0.2)
    assert second == 0


# -----------------------------------------------------------------------------
# REWARD TRACKER: COMBO
# -----------------------------------------------------------------------------

def test_without_configured_thresholds_there_is_no_combo():
    """No shipped game_config.json declares combo_thresholds, so this is what
    every game gets today."""
    tracker = RewardTracker({}, initial_hints=0)
    combo, _earned, _bonus = tracker.on_object_found(dt_since_scene_start=0.1)
    assert combo == 0


def test_the_combo_counts_the_thresholds_the_clock_is_still_under():
    tracker = RewardTracker({"hint_earn_config": {
        "combo_thresholds": [{"time": 2.0}, {"time": 5.0}, {"time": 10.0}]}})
    assert tracker.on_object_found(dt_since_scene_start=1.0)[0] == 3
    assert tracker.on_object_found(dt_since_scene_start=4.0)[0] == 2
    assert tracker.on_object_found(dt_since_scene_start=8.0)[0] == 1


def test_the_combo_is_measured_from_the_start_of_the_scene():
    """Pinned, not endorsed: the level is read off the clock since the scene
    began, not off the gap between two finds, so past the largest threshold no
    chain of fast finds can score a combo again."""
    tracker = RewardTracker({"hint_earn_config": {"combo_thresholds": [{"time": 2.0}]}})
    assert tracker.on_object_found(dt_since_scene_start=30.0)[0] == 0
    assert tracker.on_object_found(dt_since_scene_start=30.1)[0] == 0


def test_a_combo_speeds_up_the_earning_of_hints():
    plain = RewardTracker({}, initial_hints=0)
    with_combo = RewardTracker({"hint_earn_config": {
        "combo_thresholds": [{"time": 100.0}, {"time": 100.0}]}})
    plain.on_object_found(dt_since_scene_start=10.0)
    with_combo.on_object_found(dt_since_scene_start=10.0)
    assert with_combo.get_earn_progress() > plain.get_earn_progress()
