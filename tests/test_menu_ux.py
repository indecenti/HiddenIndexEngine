"""
tests/test_menu_ux.py

Regressions of the menu UI/UX plan (docs/engine/MENU_UX_PLAN.md), found by
walking every menu page with tools/menu_audit.py:

  1. the results panel asked for upper-case keys that no language file has,
     so the player read MISSION_COMPLETE and TOTAL_SCORE;
  2. the panel never grew past its 520 px reference, so at 1440p it covered
     15% of the width, and its second stats row ended under the button;
  3. the default theme's main view - which every game inherits - had no
     save-dependent buttons: with a save there was no New Game and no Continue;
  4. the settings list scrolled over the state header, and rows hidden under
     it were still clickable.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pytest

pygame = pytest.importorskip("pygame")

from engine import menu_system as ms_mod
from engine.menu_system import MenuSystem
from engine.menu_theme import ThemeManager, load_theme_for_game
from engine.results_screen import STAT_VALUE_SIZE, ResultsScreen
from engine.scaling_manager import ScalingManager

ROOT = Path(__file__).resolve().parents[1]
STRINGS_DIR = ROOT / "engine" / "assets" / "strings"
LANGS = ("en", "it", "de", "es", "fr")
REF_W, REF_H = 1280, 720
GAMES = sorted(p.parent.parent.name for p in (ROOT / "games").glob("*/ui_theme/theme.json"))


@pytest.fixture(scope="module", autouse=True)
def _pygame_init():
    pygame.init()
    pygame.display.set_mode((REF_W // 2, REF_H // 2))
    yield
    pygame.quit()


class KeyLang:
    """Hands back the key itself: a missing translation shows as a raw key."""

    current_language = "en"

    def get(self, key, default=None):
        return key

    def __call__(self, key, default=None):
        return key


def _scaling(w: int, h: int) -> ScalingManager:
    sm = ScalingManager()
    sm.update_screen_size(w, h)
    return sm


# -- 1. results strings ------------------------------------------------------

def _results_keys() -> set[str]:
    src = (ROOT / "engine" / "results_screen.py").read_text(encoding="utf-8")
    return set(re.findall(r"self\.lang\(\s*[\"']([^\"']+)[\"']", src))


def test_the_results_panel_asks_for_real_keys():
    keys = _results_keys()
    assert keys, "the results panel reads no string at all"
    assert all(k == k.lower() for k in keys), sorted(keys)


@pytest.mark.parametrize("lang", LANGS)
def test_every_results_key_is_translated(lang):
    table = json.loads((STRINGS_DIR / f"{lang}.json").read_text(encoding="utf-8"))
    missing = sorted(k for k in _results_keys() if not table.get(k, "").strip())
    assert not missing, f"{lang}: {missing}"


# -- 2. results layout -------------------------------------------------------

@pytest.mark.parametrize("size", [(1280, 720), (1920, 1080), (2560, 1440)])
def test_the_results_panel_keeps_its_share_of_the_screen(size):
    sm = _scaling(*size)
    results = ResultsScreen(*size, lang_fn=KeyLang(), scaling_manager=sm)
    _x, _y, panel_w, _h, cs = results._layout()
    assert cs == pytest.approx(sm.scale, rel=0.02)
    assert panel_w == pytest.approx(ResultsScreen._REF_W * sm.scale, rel=0.02)


@pytest.mark.parametrize("size", [(1280, 720), (2400, 1080), (1024, 600)])
def test_the_stats_rows_stay_above_the_button(size):
    sm = _scaling(*size)
    results = ResultsScreen(*size, lang_fn=KeyLang(), scaling_manager=sm)
    _x, _y, panel_w, panel_h, cs = results._layout()
    row1_y, row2_y, sep_y, _sx, _sw = results.stats_layout(panel_w, panel_h, cs)
    value_h = results._font("arial_b", STAT_VALUE_SIZE, cs).get_height()
    btn = results.get_continue_button_rect(0, 0, panel_w, panel_h, cs)
    assert sep_y < row1_y < row2_y
    assert row1_y + value_h <= row2_y
    assert row2_y + value_h <= btn.top


# -- 3. main view with and without a save -------------------------------------

def _menu_with(theme, has_save: bool) -> MenuSystem:
    menu = MenuSystem(_scaling(REF_W, REF_H), KeyLang(), game_id="__test__", save_manager=None)
    menu.theme = theme
    from engine.menu_skins import get_skin
    menu.skin = get_skin(theme)
    menu.change_state("main", has_save=has_save)
    return menu


def _actions(menu: MenuSystem) -> list[str]:
    return [b.action for b in menu.buttons]


@pytest.mark.parametrize("game_id", GAMES)
def test_with_a_save_the_main_menu_offers_continue_and_new_game(game_id):
    menu = _menu_with(load_theme_for_game(game_id), has_save=True)
    actions = _actions(menu)
    assert "confirm_new" in actions, actions
    assert actions[0] == "goto_levels"
    assert [b.text for b in menu.buttons][0] == "btn_continue"


@pytest.mark.parametrize("game_id", GAMES)
def test_without_a_save_there_is_play_and_no_new_game(game_id):
    menu = _menu_with(load_theme_for_game(game_id), has_save=False)
    actions = _actions(menu)
    assert "confirm_new" not in actions, actions
    assert [b.text for b in menu.buttons][0] == "btn_play"


# -- 4. settings viewport -----------------------------------------------------

def _settings_menu() -> MenuSystem:
    menu = _menu_with(ThemeManager.get_theme("default"), has_save=False)
    menu.change_state("settings")
    return menu


def _rows(menu: MenuSystem) -> list:
    return [b for b in menu.buttons if not menu._is_fixed(b)] + list(menu.sliders)


def test_a_row_scrolled_under_the_header_cannot_be_clicked():
    menu = _settings_menu()
    first = min(_rows(menu), key=lambda item: item.ref_rect.y)
    # Scroll until the first row sits entirely above the list viewport.
    menu.scroll_y = first.ref_rect.bottom - ms_mod.SETTINGS_VIEWPORT_TOP + 60
    is_slider = first in menu.sliders
    assert menu._get_hitbox(first, is_slider=is_slider).w == 0


def test_the_back_button_is_never_clipped_by_the_list():
    menu = _settings_menu()
    menu.scroll_y = 400
    back = next(b for b in menu.buttons if menu._is_fixed(b))
    assert menu._get_hitbox(back).w > 0


def test_the_list_is_clipped_under_the_header_when_drawn():
    menu = _settings_menu()
    sm = menu.scaling_manager
    clip = menu._settings_viewport(sm, REF_W, REF_H)
    assert clip.top == ms_mod.SETTINGS_VIEWPORT_TOP
    assert clip.bottom == REF_H
    screen = pygame.Surface((REF_W, REF_H))
    menu.scroll_y = menu.max_scroll_y or 200
    menu.draw(screen)
    assert screen.get_clip() == screen.get_rect(), "the draw pass leaked its clip"


# -- 5. card pages ---------------------------------------------------------------

def _scene_menu(theme_id: str = "default", size=(REF_W, REF_H)) -> MenuSystem:
    menu = MenuSystem(_scaling(*size), KeyLang(), game_id="Malonno_Survivors",
                      save_manager=None)
    menu.theme = ThemeManager.get_theme(theme_id)
    from engine.menu_skins import get_skin
    menu.skin = get_skin(menu.theme)
    menu.selected_level = "Welcome_To_Malonno"
    menu.change_state("scenes", extra_data="Welcome_To_Malonno")
    return menu


def _cards(menu: MenuSystem) -> list:
    return [b for b in menu.buttons if b.image is not None]


def test_every_scene_is_on_a_page_and_every_page_is_whole():
    menu = _scene_menu()
    cards = _cards(menu)
    assert len(cards) == 14
    assert menu._pages == -(-len(cards) // menu._per_page)
    for card in cards:
        page = int(card.ref_rect.x // REF_W)
        local = card.ref_rect.move(-page * REF_W, 0)
        assert 0 <= local.left and local.right <= REF_W, card.text


def test_the_arrows_turn_the_pages_and_dim_at_the_ends():
    menu = _scene_menu()
    menu._set_page(0, instant=True)
    prev, nxt = menu._pager_btns
    assert prev.action == "none" and nxt.action == "page_next"
    assert menu.turn_page(1) and menu._page == 1
    assert menu.target_scroll_x == REF_W
    assert prev.action == "page_prev"
    for _ in range(20):
        menu.turn_page(1)
    assert menu._page == menu._pages - 1 and nxt.action == "none"
    assert not menu.turn_page(1)


def test_a_click_on_an_arrow_turns_the_page_inside_the_menu():
    menu = _scene_menu()
    menu._set_page(0, instant=True)
    nxt = menu._pager_btns[1]
    assert menu.process_click(*nxt.ref_rect.center) == "page_turn"
    assert menu._page == 1


def test_the_wheel_turns_pages_on_the_card_states():
    menu = _scene_menu()
    menu._set_page(0, instant=True)
    menu.handle_scroll(-1)
    assert menu._page == 1
    menu.handle_scroll(1)
    assert menu._page == 0


def test_the_arrows_are_big_enough_to_touch():
    menu = _scene_menu()
    for arrow in menu._pager_btns:
        assert min(arrow.ref_rect.size) >= 48


def test_cards_keep_the_aspect_of_the_screenshot():
    menu = _scene_menu()
    card = _cards(menu)[0]
    assert card.image.get_size() == card.ref_rect.size


@pytest.mark.parametrize("theme_id", ["default", "android_std", "cyber_neon"])
def test_every_theme_fits_at_least_one_whole_card_per_page(theme_id):
    menu = _scene_menu(theme_id)
    assert menu._per_page >= 1
    for card in _cards(menu):
        page = int(card.ref_rect.x // REF_W)
        assert card.ref_rect.right - page * REF_W <= REF_W - ms_mod.SAFE_X
