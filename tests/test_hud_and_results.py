"""
tests/test_hud_and_results.py

What the player looks at while playing and right after: engine/hud_manager.py
and engine/results_screen.py. Neither had a test, so a crash while drawing the
objective list or the score panel only showed up on screen.

Headless, with the real ScalingManager and a translation function that hands
back the key, so nothing depends on a language file being present.
"""

from __future__ import annotations

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pytest

pygame = pytest.importorskip("pygame")

from engine.hud_manager import HintConfirmDialog, HudManager
from engine.results_screen import ResultsScreen
from engine.scaling_manager import ScalingManager

SCREEN_SIZE = (1280, 720)
DT = 1 / 60.0


class FakeObject:
    """The fields the HUD reads off a SceneObject."""

    def __init__(self, instance_id, name="Lamp", found=False, is_goal=True):
        self.instance_id = instance_id
        self.catalog_id = instance_id
        self.name = name
        self.label_key = f"obj_{instance_id}"
        self.found = found
        self.is_goal = is_goal
        self.icon = ""
        self.layer = "objects_mid"


class FakeLang:
    """Answers with the key, so no language file is needed."""

    def get(self, key, *args, **kwargs):
        return key

    def __call__(self, key, *args, **kwargs):
        return key


@pytest.fixture(scope="module")
def screen():
    pygame.init()
    pygame.font.init()
    surface = pygame.display.set_mode(SCREEN_SIZE)
    yield surface
    pygame.quit()


@pytest.fixture
def scaling(screen):
    sm = ScalingManager()
    sm.update_screen_size(*SCREEN_SIZE)
    return sm


@pytest.fixture
def objects():
    return [FakeObject(f"obj_{i}", name=f"Object {i}") for i in range(5)]


# -----------------------------------------------------------------------------
# HUD
# -----------------------------------------------------------------------------

@pytest.fixture
def hud(scaling):
    return HudManager(scaling, FakeLang(), {"position": "bottom"}, *SCREEN_SIZE)


def test_the_hud_draws_the_objectives(hud, screen, objects):
    hud.setup(objects, time_elapsed=0.0)
    screen.fill((0, 0, 0))
    blank = pygame.image.tostring(screen, "RGB")

    for _ in range(5):
        hud.update(DT, (640, 360), time_elapsed=1.0, score=100)
        hud.draw(screen, 1.0)

    assert pygame.image.tostring(screen, "RGB") != blank, "the HUD drew nothing"


def test_the_hud_survives_a_scene_with_no_objectives(hud, screen):
    """A scene of pure decoration must not divide by its zero objectives."""
    hud.setup([], time_elapsed=0.0)
    for _ in range(3):
        hud.update(DT, (640, 360), time_elapsed=1.0, score=0)
        hud.draw(screen, 1.0)


def test_the_hud_survives_every_objective_being_found(hud, screen, objects):
    for o in objects:
        o.found = True
    hud.setup(objects, time_elapsed=0.0)
    for _ in range(3):
        hud.update(DT, (640, 360), time_elapsed=30.0, score=500)
        hud.draw(screen, 30.0)


def test_the_hud_shows_only_a_window_of_a_long_list(scaling, screen):
    """Forty objectives must not be painted over each other."""
    many = [FakeObject(f"o{i}") for i in range(40)]
    hud = HudManager(scaling, FakeLang(), {"position": "bottom", "max_visible_goals": 7},
                     *SCREEN_SIZE)
    hud.setup(many, time_elapsed=0.0)
    hud.update(DT, (640, 360), time_elapsed=1.0, score=0)
    hud.draw(screen, 1.0)
    assert len(hud._visible_objects) <= 7


def test_the_window_moves_on_as_objectives_are_found(scaling, screen):
    many = [FakeObject(f"o{i}") for i in range(20)]
    hud = HudManager(scaling, FakeLang(), {"position": "bottom", "max_visible_goals": 5},
                     *SCREEN_SIZE)
    hud.setup(many, time_elapsed=0.0)
    first_window = [o.instance_id for o in hud._visible_objects]

    for o in many[:5]:
        o.found = True
    hud.update(DT, (640, 360), time_elapsed=5.0, score=500)

    assert [o.instance_id for o in hud._visible_objects] != first_window


def test_an_objective_is_active_only_while_it_is_on_the_list(scaling):
    many = [FakeObject(f"o{i}") for i in range(20)]
    hud = HudManager(scaling, FakeLang(), {"position": "bottom", "max_visible_goals": 3},
                     *SCREEN_SIZE)
    hud.setup(many, time_elapsed=0.0)
    shown = [o.instance_id for o in hud._visible_objects]
    assert hud.is_target_active(shown[0]) is True
    assert hud.is_target_active("o19") is False


def test_the_score_climbs_towards_its_target(hud, screen, objects):
    hud.setup(objects, time_elapsed=0.0)
    hud.update(DT, (640, 360), time_elapsed=1.0, score=1000)
    first = hud._score_display
    for _ in range(10):
        hud.update(DT, (640, 360), time_elapsed=1.0, score=1000)
    assert hud._score_display > first
    assert hud._score_display <= 1000


def _run(hud, frames=60):
    for _ in range(frames):
        hud.update(DT, (0, 0), time_elapsed=1.0, score=0)


@pytest.fixture
def mobile_hud(scaling, monkeypatch):
    """The HUD as the APK runs it: a drawer instead of a fixed bar.

    The touch path is decided at construction, fonts included, so the runtime
    has to look like Android before the HUD is built. Flipping the flag
    afterwards would leave the mobile fonts unloaded and is not what a device
    ever does.
    """
    monkeypatch.setenv("ANDROID_ARGUMENT", "/data/data/app")
    hud = HudManager(scaling, FakeLang(), {"position": "bottom"}, *SCREEN_SIZE)
    assert hud._android is True
    return hud


def test_on_the_desktop_there_is_no_drawer(hud):
    """The bar is always there, so opening a drawer changes nothing on screen."""
    hud.open_drawer()
    _run(hud)
    assert hud.is_drawer_open() is False


def test_the_drawer_slides_open_and_shut(mobile_hud):
    """It is open once the animation has moved it, not on the call."""
    mobile_hud.open_drawer(seconds=4.0)
    assert mobile_hud.is_drawer_open() is False, "nothing has moved yet"
    _run(mobile_hud)
    assert mobile_hud.is_drawer_open() is True

    mobile_hud.close_drawer()
    _run(mobile_hud)
    assert mobile_hud.is_drawer_open() is False


def test_the_drawer_toggles(mobile_hud):
    mobile_hud.toggle_drawer()
    _run(mobile_hud)
    assert mobile_hud.is_drawer_open() is True
    mobile_hud.toggle_drawer()
    _run(mobile_hud)
    assert mobile_hud.is_drawer_open() is False


def test_the_drawer_closes_itself_after_a_while(mobile_hud):
    """Opened by a swipe, it must not sit over the scene forever."""
    mobile_hud.open_drawer(seconds=1.0)
    _run(mobile_hud, frames=30)
    assert mobile_hud.is_drawer_open() is True
    _run(mobile_hud, frames=240)
    assert mobile_hud.is_drawer_open() is False


def test_the_mobile_hud_draws(mobile_hud, screen, objects):
    mobile_hud.setup(objects, time_elapsed=0.0)
    mobile_hud.open_drawer()
    screen.fill((0, 0, 0))
    blank = pygame.image.tostring(screen, "RGB")
    for _ in range(60):
        mobile_hud.update(DT, (640, 360), time_elapsed=1.0, score=100)
        mobile_hud.draw(screen, 1.0)
    assert pygame.image.tostring(screen, "RGB") != blank


def test_a_resize_is_taken_without_a_crash(hud, objects):
    hud.setup(objects, time_elapsed=0.0)
    for size in ((1920, 1080), (800, 480), SCREEN_SIZE):
        surface = pygame.Surface(size)
        hud._sm.update_screen_size(*size)
        hud._rebuild_surface()
        hud.update(DT, (10, 10), time_elapsed=1.0, score=100)
        hud.draw(surface, 1.0)


# -----------------------------------------------------------------------------
# THE HINT CONFIRMATION
# -----------------------------------------------------------------------------

@pytest.fixture
def dialog():
    return HintConfirmDialog(*SCREEN_SIZE, lang_fn=FakeLang())


def test_the_dialog_stays_out_of_the_way_until_it_is_shown(dialog, screen):
    fonts = (pygame.font.Font(None, 24), pygame.font.Font(None, 16))
    screen.fill((0, 0, 0))
    blank = pygame.image.tostring(screen, "RGB")
    dialog.update(DT, (0, 0))
    dialog.draw(screen, *fonts)
    assert pygame.image.tostring(screen, "RGB") == blank


def test_the_dialog_draws_once_shown(dialog, screen):
    fonts = (pygame.font.Font(None, 24), pygame.font.Font(None, 16))
    dialog.show(hints_remaining=2, can_use=True, penalty=50)
    screen.fill((0, 0, 0))
    blank = pygame.image.tostring(screen, "RGB")
    for _ in range(10):
        dialog.update(DT, (640, 360))
        dialog.draw(screen, *fonts)
    assert pygame.image.tostring(screen, "RGB") != blank


def test_the_dialog_can_be_dismissed_with_a_key(dialog):
    """It answers the keyboard once it has finished sliding in."""
    dialog.show(hints_remaining=2, can_use=True)
    for _ in range(60):
        dialog.update(DT, (0, 0))
    assert dialog.handle_key(pygame.K_ESCAPE) == "cancel_hint"
    for _ in range(60):
        dialog.update(DT, (0, 0))
    assert dialog.handle_key(pygame.K_ESCAPE) is None, "and stops once dismissed"


def test_a_hidden_dialog_ignores_the_keyboard(dialog):
    assert dialog.handle_key(pygame.K_ESCAPE) is None


# -----------------------------------------------------------------------------
# RESULTS SCREEN
# -----------------------------------------------------------------------------

@pytest.fixture
def results(scaling, screen):
    return ResultsScreen(*SCREEN_SIZE, lang_fn=FakeLang(), scaling_manager=scaling)


def test_nothing_is_drawn_before_the_scene_ends(results, screen):
    screen.fill((0, 0, 0))
    blank = pygame.image.tostring(screen, "RGB")
    results.update(DT)
    results.draw(screen)
    assert pygame.image.tostring(screen, "RGB") == blank


@pytest.mark.parametrize("stars", [0, 1, 2, 3])
def test_the_panel_is_drawn_for_every_star_count(results, screen, stars):
    results.show(score=1500, stars=stars, time_elapsed=42.0,
                 objects_found=5, total_objects=5)
    screen.fill((0, 0, 0))
    blank = pygame.image.tostring(screen, "RGB")
    for _ in range(30):
        results.update(DT)
        results.draw(screen)
    assert pygame.image.tostring(screen, "RGB") != blank


def test_a_lost_scene_is_drawn_too(results, screen):
    results.show(score=0, stars=1, time_elapsed=120.0, is_failed=True,
                 objects_found=2, total_objects=5)
    for _ in range(30):
        results.update(DT)
        results.draw(screen)


def test_a_star_count_out_of_range_is_brought_back_in(results):
    results.show(score=0, stars=99, time_elapsed=1.0)
    assert results.stars == 3
    results.show(score=0, stars=-5, time_elapsed=1.0)
    assert results.stars == 0


def test_the_score_counts_up_to_the_real_one(results):
    results.show(score=2000, stars=3, time_elapsed=10.0)
    assert results.display_score == 0
    for _ in range(60):
        results.update(DT)
    assert results.display_score == 2000


def test_a_negative_score_is_shown_as_it_is(results, screen):
    """Penalties can take a run below zero and the panel must say so."""
    results.show(score=-450, stars=1, time_elapsed=30.0)
    for _ in range(60):
        results.update(DT)
        results.draw(screen)
    assert results.display_score == -450


def test_the_continue_button_ignores_clicks_until_it_has_appeared(results):
    """A click landing during the opening animation must not skip the panel."""
    results.show(score=100, stars=2, time_elapsed=5.0)
    panel = results._layout()
    button = results.get_continue_button_rect(panel[0], panel[1], panel[2], panel[3], panel[4])
    assert results.check_click(button.center) is False

    for _ in range(60):
        results.update(DT)
    assert results.check_click(button.center) is True


def test_a_click_away_from_the_button_does_nothing(results):
    results.show(score=100, stars=2, time_elapsed=5.0)
    for _ in range(60):
        results.update(DT)
    assert results.check_click((5, 5)) is False


def test_a_hidden_panel_answers_no_click(results):
    results.show(score=100, stars=2, time_elapsed=5.0)
    for _ in range(60):
        results.update(DT)
    results.hide()
    assert results.check_click((640, 360)) is False


def test_the_panel_follows_a_resize(results, screen):
    results.show(score=100, stars=3, time_elapsed=5.0)
    for size in ((1920, 1080), (800, 480)):
        results.on_resize(*size)
        surface = pygame.Surface(size)
        for _ in range(5):
            results.update(DT)
            results.draw(surface)
        assert (results.screen_w, results.screen_h) == size
