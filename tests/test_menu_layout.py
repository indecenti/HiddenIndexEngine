"""
tests/test_menu_layout.py

Layout rules of the menus (tools/menu_layout_check.py) on the boxes that
MenuSystem records through its layout probe: nothing cut by the screen edge,
icons inside their buttons, no overlapping texts or controls, no text below
the readable floor.

Every theme, the reference size and a 4:3 one (where the letterbox offset used
to put captions inside the icons), every page including the paged level and
scene cards.
"""

from __future__ import annotations

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pytest

pygame = pytest.importorskip("pygame")

from engine.menu_skins import get_skin
from engine.menu_system import MenuSystem
from engine.menu_theme import ThemeManager
from engine.scaling_manager import ScalingManager
from tools.menu_layout_check import check_frame

THEMES = ("default", "horror", "kids", "cyber_neon", "mystery", "android_std")
SIZES = ((1280, 720), (1024, 768))
SETTLE_FRAMES = 30
DT = 1 / 30


@pytest.fixture(scope="module", autouse=True)
def _pygame_init():
    pygame.init()
    pygame.display.set_mode((64, 64))
    yield
    pygame.quit()


class EnglishDefaults:
    """Language stub answering with the English default the code passes."""

    current_language = "en"

    def get(self, key, default=None):
        return default if default is not None else key.replace("btn_", "").upper()

    def __call__(self, key, default=None):
        return default


def _frame(theme_id: str, state: str, size: tuple[int, int], has_save: bool = True):
    sm = ScalingManager()
    sm.update_screen_size(*size)
    menu = MenuSystem(sm, EnglishDefaults(), game_id="Malonno_Survivors", save_manager=None)
    menu.theme = ThemeManager.get_theme(theme_id)
    menu.skin = get_skin(menu.theme)
    menu.change_state(state, has_save=has_save, extra_data="Welcome_To_Malonno")
    for _ in range(SETTLE_FRAMES):
        menu.update(DT, -100, -100)
    menu.layout_probe = []
    menu.draw(pygame.Surface(size))
    return menu.layout_probe, sm.scale


# -- the rules themselves -------------------------------------------------------

def test_a_box_past_the_screen_edge_is_cut():
    boxes = [("button", pygame.Rect(1200, 10, 120, 60), "x")]
    assert [v.rule for v in check_frame(boxes, (1280, 720))] == ["cut"]


def test_an_icon_bigger_than_its_button_is_reported():
    boxes = [("button", pygame.Rect(100, 100, 80, 80), "a"),
             ("icon", pygame.Rect(90, 90, 100, 100), "a")]
    assert "icon-out-of-button" in [v.rule for v in check_frame(boxes, (1280, 720))]


def test_a_text_is_allowed_on_its_own_button_only():
    own = [("button", pygame.Rect(100, 100, 200, 60), "a"),
           ("text", pygame.Rect(120, 110, 100, 30), "a")]
    assert check_frame(own, (1280, 720)) == []
    other = [("button", pygame.Rect(100, 100, 200, 60), "a"),
             ("text", pygame.Rect(120, 110, 100, 30), "b")]
    assert [v.rule for v in check_frame(other, (1280, 720))] == ["text-over-button"]


def test_two_texts_touching_by_a_pixel_are_not_an_overlap():
    boxes = [("text", pygame.Rect(0, 0, 100, 30), "a"),
             ("text", pygame.Rect(0, 29, 100, 30), "b")]
    assert check_frame(boxes, (1280, 720)) == []


def test_a_text_below_the_floor_is_too_small():
    boxes = [("text", pygame.Rect(0, 0, 100, 12), "a")]
    assert [v.rule for v in check_frame(boxes, (1280, 720))] == ["text-too-small"]


def test_the_probe_is_off_in_the_game():
    sm = ScalingManager()
    sm.update_screen_size(1280, 720)
    menu = MenuSystem(sm, EnglishDefaults(), game_id="Malonno_Survivors", save_manager=None)
    assert menu.layout_probe is None
    menu.draw(pygame.Surface((1280, 720)))
    assert menu.layout_probe is None


# -- every theme, every page without cards ------------------------------------

@pytest.mark.parametrize("size", SIZES, ids=lambda s: f"{s[0]}x{s[1]}")
@pytest.mark.parametrize("state", ["main", "pause", "confirm_new", "settings"])
@pytest.mark.parametrize("theme_id", THEMES)
def test_the_page_is_clean(theme_id, state, size):
    boxes, scale = _frame(theme_id, state, size)
    assert boxes, "the probe recorded nothing"
    problems = check_frame(boxes, size, scale)
    assert not problems, "\n".join(map(str, problems))


def test_the_main_page_without_a_save_is_clean():
    boxes, scale = _frame("default", "main", (1280, 720), has_save=False)
    assert not check_frame(boxes, (1280, 720), scale)


# -- the card pages -----------------------------------------------------------

@pytest.mark.parametrize("size", SIZES, ids=lambda s: f"{s[0]}x{s[1]}")
@pytest.mark.parametrize("state", ["levels", "scenes"])
@pytest.mark.parametrize("theme_id", THEMES)
def test_the_card_page_is_clean(theme_id, state, size):
    boxes, scale = _frame(theme_id, state, size)
    assert any(k == "card" for k, _r, _o in boxes), "no card was drawn"
    problems = check_frame(boxes, size, scale)
    assert not problems, "\n".join(map(str, problems))
