"""
tests/test_hint_system.py

engine/hint_system.py decides when the game starts glowing an object by itself
and what asking for a hint costs. It had no test.

The scene objects are stubs carrying only the fields the system reads, and the
effects engine records the calls instead of spawning particles.
"""

from __future__ import annotations

import pytest

from engine.hint_system import HintSystem


class FakeObject:
    """The fields HintSystem reads off a SceneObject."""

    def __init__(self, instance_id, is_goal=True, found=False, hint_delay=30,
                 layer="objects_mid", detection_type="circle",
                 x=100.0, y=200.0, width=40.0, height=60.0):
        self.instance_id = instance_id
        self.is_goal = is_goal
        self.found = found
        self.hint_delay = hint_delay
        self.layer = layer
        self.detection_type = detection_type
        self.x, self.y = x, y
        self.width, self.height = width, height


class FakeEffects:
    def __init__(self):
        self.hints: list = []

    def spawn_hint_effect(self, cx, cy):
        self.hints.append((cx, cy))


@pytest.fixture
def effects():
    return FakeEffects()


@pytest.fixture
def system(effects):
    return HintSystem(scaling_manager=None, effects_engine=effects)


@pytest.fixture
def objects():
    return [FakeObject("a"), FakeObject("b"), FakeObject("c")]


def run(system, objects, seconds: float, dt: float = 0.5) -> None:
    for _ in range(int(seconds / dt)):
        system.update(dt, objects)


# -----------------------------------------------------------------------------
# AUTO HINT: ONE OBJECT AT A TIME
# -----------------------------------------------------------------------------

def test_nothing_glows_before_the_delay(system, objects):
    system.reset_for_scene(objects)
    run(system, objects, seconds=25.0)
    assert all(system.get_hint_intensity(o.instance_id) == 0.0 for o in objects)


def test_only_one_object_glows_at_a_time(system, objects):
    """Every object is ready at once, and the scene must not light up whole."""
    system.reset_for_scene(objects)
    run(system, objects, seconds=32.0)
    glowing = [o.instance_id for o in objects if system.get_hint_intensity(o.instance_id) > 0]
    assert glowing == ["a"], f"expected only the first object, got {glowing}"


def test_the_glow_grows_with_the_wait(system, objects):
    system.reset_for_scene(objects)
    run(system, objects, seconds=31.0)
    early = system.get_hint_intensity("a")
    run(system, objects, seconds=5.0)
    later = system.get_hint_intensity("a")
    assert 0 < early < later <= 1.0


def test_the_glow_never_passes_full(system, objects):
    system.reset_for_scene(objects)
    run(system, objects, seconds=44.0)
    assert system.get_hint_intensity("a") <= 1.0


def test_a_hidden_object_is_hinted_harder(system):
    """The low layer is the hard one to spot, so its glow is boosted."""
    low = [FakeObject("low", layer="objects_low")]
    high = [FakeObject("high", layer="objects_high")]

    system.reset_for_scene(low)
    system.per_object_inactivity["low"] = 30.0
    system.update(0.5, low)
    low_glow = system.get_hint_intensity("low")

    system.reset_for_scene(high)
    system.per_object_inactivity["high"] = 30.0
    system.update(0.5, high)
    high_glow = system.get_hint_intensity("high")

    assert low_glow > high_glow


def test_the_glow_gives_up_after_its_window_and_starts_over(system, objects):
    """Fifteen seconds of glow, then it goes dark and the wait restarts."""
    system.reset_for_scene(objects)
    run(system, objects, seconds=30.5)
    assert system.get_hint_intensity("a") > 0
    run(system, objects, seconds=15.0)
    assert system.get_hint_intensity("a") == 0.0
    # The wait restarted from zero and is climbing again, nowhere near ready.
    assert system.per_object_inactivity["a"] < objects[0].hint_delay / 2


def test_finding_an_object_puts_out_its_glow(system, objects):
    system.reset_for_scene(objects)
    run(system, objects, seconds=32.0)
    assert system.get_hint_intensity("a") > 0

    objects[0].found = True
    system.reset_object_timer("a")
    system.update(0.5, objects)

    assert system.get_hint_intensity("a") == 0.0


def test_a_found_object_hands_the_turn_to_the_next_one(system, objects):
    system.reset_for_scene(objects)
    run(system, objects, seconds=32.0)
    objects[0].found = True
    system.reset_object_timer("a")
    system.update(0.5, objects)
    assert system.get_hint_intensity("b") > 0


def test_a_decoration_is_never_hinted(system):
    objects = [FakeObject("goal"), FakeObject("decoration", is_goal=False)]
    system.reset_for_scene(objects)
    run(system, objects, seconds=32.0)
    assert system.get_hint_intensity("decoration") == 0.0


def test_the_automatic_hint_can_be_switched_off(system, objects):
    system.reset_for_scene(objects)
    system.auto_hint_enabled = False
    run(system, objects, seconds=40.0)
    assert all(system.get_hint_intensity(o.instance_id) == 0.0 for o in objects)


# -----------------------------------------------------------------------------
# MANUAL HINT: COST AND COOLDOWN
# -----------------------------------------------------------------------------

def test_asking_for_a_hint_lights_the_first_object_left(system, objects, effects):
    system.reset_for_scene(objects)
    ok, _penalty = system.use_manual_hint(objects)
    assert ok is True
    assert system.get_manual_glow(objects[0]) > 0
    assert effects.hints, "the particles must be spawned on the object"


def test_the_particles_land_on_the_middle_of_a_rectangle(system, effects):
    obj = FakeObject("r", detection_type="rect", x=100.0, y=200.0, width=40.0, height=60.0)
    system.reset_for_scene([obj])
    system.use_manual_hint([obj])
    assert effects.hints[0] == (120.0, 230.0)


def test_the_particles_land_on_the_centre_of_a_circle(system, effects):
    obj = FakeObject("c", detection_type="circle", x=100.0, y=200.0)
    system.reset_for_scene([obj])
    system.use_manual_hint([obj])
    assert effects.hints[0] == (100.0, 200.0)


def test_the_first_hint_on_an_object_is_free_and_the_next_ones_are_not(system, objects):
    """Pinned as the code has it: the penalty list starts at zero, so the first
    hint on a given object costs nothing and the second one is the first to."""
    system.reset_for_scene(objects)
    _ok, first = system.use_manual_hint(objects)
    system.manual_hint_cooldown = 0.0
    _ok, second = system.use_manual_hint(objects)
    system.manual_hint_cooldown = 0.0
    _ok, third = system.use_manual_hint(objects)
    assert (first, second, third) == (0, -50, -75)


def test_the_cost_is_counted_for_each_object_on_its_own(system):
    a, b = FakeObject("a"), FakeObject("b")
    system.reset_for_scene([a, b])

    _ok, first_on_a = system.use_manual_hint([a, b])
    system.manual_hint_cooldown = 0.0
    a.found = True
    _ok, first_on_b = system.use_manual_hint([a, b])

    assert first_on_a == first_on_b == 0, "each object starts its own count"


def test_a_hint_is_refused_while_it_is_cooling_down(system, objects):
    system.reset_for_scene(objects)
    assert system.use_manual_hint(objects)[0] is True
    assert system.can_use_hint() is False
    assert system.use_manual_hint(objects)[0] is False


def test_the_cooldown_runs_out_with_time(system, objects):
    system.reset_for_scene(objects)
    system.use_manual_hint(objects)
    assert system.get_cooldown_percent() == pytest.approx(1.0)
    run(system, objects, seconds=system.manual_hint_cooldown_max + 1.0)
    assert system.get_cooldown_percent() == 0.0
    assert system.can_use_hint() is True


def test_the_button_gives_up_after_the_third_hint(system, objects):
    system.reset_for_scene(objects)
    for _ in range(system.max_hints_before_disable):
        assert system.use_manual_hint(objects)[0] is True
        system.manual_hint_cooldown = 0.0
    assert system.can_use_hint() is False
    assert system.use_manual_hint(objects)[0] is False


def test_a_hint_with_nothing_left_to_find_is_refused(system, objects):
    for o in objects:
        o.found = True
    system.reset_for_scene(objects)
    assert system.use_manual_hint(objects)[0] is False
    assert system.hints_used_total == 0, "a refused hint must not be charged"


def test_a_manual_hint_beats_the_automatic_one(system, objects):
    """The object the player asked for is the one that must stand out."""
    system.reset_for_scene(objects)
    run(system, objects, seconds=32.0)          # "a" is glowing by itself
    system.use_manual_hint(objects)
    system.update(0.1, objects)
    assert system.get_manual_glow(objects[0]) > 0


def test_the_manual_glow_fades_out(system, objects):
    system.reset_for_scene(objects)
    system.use_manual_hint(objects)
    assert system.get_manual_glow(objects[0]) > 0
    run(system, objects, seconds=3.0)
    assert system.get_manual_glow(objects[0]) == 0.0


def test_a_hint_pushes_back_the_automatic_one(system, objects):
    """Asking for a hint restarts the wait, so the two do not pile up."""
    system.reset_for_scene(objects)
    run(system, objects, seconds=29.0)
    system.use_manual_hint(objects)
    assert system.per_object_inactivity["a"] == 0.0


def test_the_effects_can_be_suppressed(system, objects, effects):
    system.reset_for_scene(objects)
    ok, _penalty = system.use_manual_hint(objects, suppress_fx=True)
    assert ok is True
    assert effects.hints == []
    assert system.get_manual_glow(objects[0]) == 0.0
    assert system.hints_used_total == 1, "it still counts as used"


# -----------------------------------------------------------------------------
# BETWEEN SCENES
# -----------------------------------------------------------------------------

def test_a_new_scene_starts_with_a_clean_slate(system, objects):
    system.reset_for_scene(objects)
    system.use_manual_hint(objects)
    run(system, objects, seconds=5.0)

    system.reset_for_scene(objects)

    assert system.hints_used_total == 0
    assert system.manual_hint_cooldown == 0.0
    assert system.can_use_hint() is True
    assert all(v == 0.0 for v in system.per_object_inactivity.values())
    assert system.per_object_manual_hint_timer == {}


def test_the_statistics_report_what_was_used(system, objects):
    system.reset_for_scene(objects)
    assert system.get_stats()["no_hints_achievement"] is True

    system.use_manual_hint(objects)

    stats = system.get_stats()
    assert stats["hints_used"] == 1
    assert stats["per_object"]["a"] == 1
    assert stats["no_hints_achievement"] is False


def test_the_reported_counts_are_a_copy(system, objects):
    """The caller saves these: it must not be handed the live dictionary."""
    system.reset_for_scene(objects)
    system.use_manual_hint(objects)
    stats = system.get_stats()
    stats["per_object"]["a"] = 999
    assert system.hints_per_obj["a"] == 1


def test_the_layer_intensities_can_be_retuned(system):
    system.configure_layer_intensity({"objects_low": 2.0, "objects_mid": 0.5})
    assert system.layer_hint_intensity["objects_low"] == 2.0
    assert system.layer_hint_intensity["objects_mid"] == 0.5
