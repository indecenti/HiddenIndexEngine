"""
tests/test_menu_chrome.py

Contract of the menu CHROME (engine/menu_system.py), the part a player reads
rather than the part a skin paints:

  1. the main state carries the game title, and no identifier ever reaches the
     screen with its separators ("Malonno_Survivors", "welcome_to_malonno");
  2. every theme lays the buttons out on the same vertical rhythm, so switching
     theme does not move the menu up and down the screen;
  3. corner chrome (back, quit) is excluded from the carousel, which used to
     let the main menu scroll sideways because of the quit button;
  4. the settings rows share one grid: same left edge, same width, same step,
     one pill width for every value;
  5. every theme ships the complete icon set, with a distinct icon per action -
     music and SFX (and resolution and fullscreen) used to share one.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pytest

pygame = pytest.importorskip("pygame")

from engine import menu_system as ms_mod
from engine.menu_system import MenuSystem
from engine.menu_theme import MenuTheme, ThemeManager
from engine.scaling_manager import ScalingManager

ROOT = Path(__file__).resolve().parents[1]
THEMES_DIR = ROOT / "engine" / "assets" / "themes"
THEMES = ("default", "horror", "kids", "cyber_neon", "mystery", "android_std")
REF_W, REF_H = 1280, 720

# The icon names the menu can ask for; a theme missing one falls back to a
# generic glyph, which is how music and SFX ended up sharing a gramophone.
REQUIRED_ICONS = ("play", "levels", "settings", "quit", "back", "new_game",
                  "audio", "sfx", "language", "fullscreen", "resolution",
                  "vibration", "lock")


@pytest.fixture(scope="module", autouse=True)
def _pygame_init():
    pygame.init()
    pygame.display.set_mode((REF_W // 2, REF_H // 2))
    yield
    pygame.quit()


class FakeLang:
    """Language manager stub: returns the requested default, never a key."""

    current_language = "en"

    def __init__(self, table: dict | None = None) -> None:
        self.table = table or {}

    def get(self, key, default=None):
        if key in self.table:
            return self.table[key]
        return default if default is not None else key

    def __call__(self, key, default=None):
        return self.table.get(key, default)


def _menu(theme_id: str = "default", state: str = "main", lang=None) -> MenuSystem:
    sm = ScalingManager()
    sm.update_screen_size(REF_W, REF_H)
    menu = MenuSystem(sm, lang or FakeLang(), game_id="__test__", save_manager=None)
    menu.theme = ThemeManager.get_theme(theme_id)
    from engine.menu_skins import get_skin
    menu.skin = get_skin(menu.theme)
    menu.change_state(state)
    return menu


# ── 1. Titles and names a player can read ───────────────────────────────────

def test_main_state_shows_the_game_title():
    menu = _menu()
    menu.game_title = "Malonno Survivors"
    assert menu._state_title_text() == "Malonno Survivors"


def test_game_title_never_keeps_the_folder_separators():
    menu = _menu()
    menu.game_id = "Malonno_Survivors"
    assert menu._resolve_game_title() == "Malonno Survivors"


def test_the_game_title_is_larger_than_a_state_header():
    menu = _menu()
    main_size = menu._state_title_size()
    menu.state = "settings"
    assert main_size > menu._state_title_size()


@pytest.mark.parametrize("raw, expected", [
    ("welcome_to_malonno", "Welcome To Malonno"),
    ("BRESCIA_EDOLO", "Brescia Edolo"),
    ("Formis", "Formis"),
    ("", ""),
])
def test_identifiers_become_names(raw, expected):
    assert MenuSystem._pretty_name(raw) == expected


# ── 2. One vertical rhythm for every theme ──────────────────────────────────

def test_every_theme_places_the_icon_row_at_the_same_height():
    """The rhythm is shared; only a skin may nudge a button off it.

    `arrange` is allowed to apply vertical offsets (the kids arc, the horror
    scatter), so the buttons are checked against the row centre with the room
    those offsets need - not against each other.
    """
    centres = {_menu(theme_id)._row_center_y() for theme_id in THEMES}
    assert len(centres) == 1, f"themes disagree on the row centre: {centres}"

    for theme_id in THEMES:
        menu = _menu(theme_id)
        rows = [b for b in menu.buttons if not menu._is_fixed(b)]
        assert rows, theme_id
        for b in rows:
            drift = abs(b.ref_rect.centery - menu._row_center_y())
            assert drift <= 40, f"{theme_id}: button {drift}px off the row"


@pytest.mark.parametrize("theme_id", THEMES)
def test_cards_stay_inside_the_screen(theme_id):
    """A 200px tall level card centred on the icon row fell off the bottom."""
    menu = _menu(theme_id, state="levels")
    card = menu._std_btn("Level", "goto_scenes:x", 0, 1, override_w=640, override_h=200)
    assert card.ref_rect.top >= 0
    assert card.ref_rect.bottom <= REF_H - ms_mod.SAFE_BOTTOM


def test_captions_share_one_baseline_under_the_icons():
    menu = _menu()
    baseline = menu._icon_label_baseline(menu.scaling_manager)
    for b in menu.buttons:
        if menu._is_fixed(b):
            continue
        assert baseline > b.ref_rect.bottom, "the caption would sit on the icon"


# ── 3. Corner chrome is not part of the carousel ────────────────────────────

def test_the_quit_button_does_not_make_the_main_menu_scroll():
    menu = _menu()
    assert any(b.action == "quit" and menu._is_fixed(b) for b in menu.buttons)
    assert menu.max_scroll_x == 0


def test_the_back_button_is_fixed_chrome():
    menu = _menu(state="settings")
    back = [b for b in menu.buttons if b.action.startswith("goto_")]
    assert back and all(menu._is_fixed(b) for b in back)


# ── 4. The settings list is a grid ──────────────────────────────────────────

def test_settings_rows_share_one_grid():
    """Same column for every row; the step only widens between two groups."""
    menu = _menu(state="settings")
    rows = [b.ref_rect for b in menu.buttons if not menu._is_fixed(b)]
    rows += [s.row_ref for s in menu.sliders]
    assert len(rows) >= 4
    assert len({r.x for r in rows}) == 1, "rows do not share the left edge"
    assert len({r.w for r in rows}) == 1, "rows do not share the width"
    assert len({r.h for r in rows}) == 1, "rows do not share the height"

    group_tops = {round(y) for _, y in menu._settings_groups}
    assert len(group_tops) >= 2, "the settings list lost its groups"

    tops = sorted(r.y for r in rows)
    in_group = ms_mod.SETTINGS_ROW_STEP
    between = in_group + ms_mod.SETTINGS_GROUP_GAP + ms_mod.SETTINGS_GROUP_H + 8
    for a, b in zip(tops, tops[1:]):
        assert (b - a) in (in_group, between), f"unexpected row step: {b - a}"


def test_settings_fit_inside_the_safe_area():
    """The list is read top to bottom: it may not run off the bottom edge."""
    menu = _menu(state="settings")
    rows = [b.ref_rect for b in menu.buttons if not menu._is_fixed(b)]
    rows += [s.row_ref for s in menu.sliders]
    assert max(r.bottom for r in rows) <= REF_H - ms_mod.SAFE_BOTTOM
    assert min(r.top for r in rows) >= ms_mod.STATE_TITLE_Y


def test_every_slider_row_keeps_room_for_its_readout():
    """The percentage used to be printed on top of the slider handle."""
    menu = _menu(state="settings")
    assert menu.sliders
    for s in menu.sliders:
        gap = s.row_ref.right - ms_mod.SETTINGS_PAD - s.ref_rect.right
        assert gap >= ms_mod.SETTINGS_READOUT_W * 0.5, gap


def test_settings_rows_carry_their_label_and_value_apart():
    menu = _menu(state="settings")
    toggles = [b for b in menu.buttons if not menu._is_fixed(b)]
    assert toggles
    for b in toggles:
        assert getattr(b, "label_text", ""), "a toggle row lost its label"
        assert b.text, "a toggle row lost its value"
        assert b.label_text != b.text


# ── 4b. Composition details ─────────────────────────────────────────────────

def test_corner_chrome_stays_inside_the_safe_area():
    """Back and quit are the two buttons a TV or a notch can eat."""
    for state in ("main", "settings"):
        menu = _menu(state=state)
        for b in menu.buttons:
            if not menu._is_fixed(b):
                continue
            assert b.ref_rect.left >= ms_mod.SAFE_X - 1
            assert b.ref_rect.right <= REF_W - ms_mod.SAFE_X + 1
            assert b.ref_rect.top >= ms_mod.SAFE_TOP - 1
            bottom = b.ref_rect.bottom
            if b.action == "quit" and menu._has_icon_labels():
                bottom += ms_mod.ICON_LABEL_GAP + ms_mod.ICON_LABEL_SIZE
            assert bottom <= REF_H - ms_mod.SAFE_BOTTOM + 1, (state, b.action)


@pytest.mark.parametrize("theme_id", THEMES)
def test_the_first_action_is_drawn_larger(theme_id):
    """Play / Continue / Resume is what the player came for."""
    menu = _menu(theme_id)
    row = [b for b in menu.buttons if not menu._is_fixed(b)]
    assert row and row[0].primary
    assert all(not b.primary for b in row[1:])
    assert row[0].ref_rect.w > row[1].ref_rect.w


def test_the_primary_action_shows_the_play_glyph():
    """`goto_levels` is the level list elsewhere, but Play on the main menu."""
    menu = _menu()
    assert menu._icon_for("goto_levels") == "play"
    menu.state = "levels"
    assert menu._icon_for("goto_levels") == "goto_levels"


def test_captions_clear_the_largest_icon():
    menu = _menu()
    baseline = menu._icon_label_baseline(menu.scaling_manager)
    primary = next(b for b in menu.buttons if getattr(b, "primary", False))
    assert baseline >= primary.ref_rect.bottom


def test_the_scene_list_says_which_level_it_belongs_to():
    menu = _menu(state="scenes")
    menu.selected_level = "welcome_to_malonno"
    assert menu._state_subtitle_text() == "Welcome To Malonno"
    menu.state = "settings"
    assert menu._state_subtitle_text() == ""


def test_the_build_line_only_shows_on_the_main_state():
    menu = _menu()
    menu.game_version = "v1.41"
    screen = pygame.Surface((REF_W, REF_H))
    before = pygame.image.tostring(screen, "RGB")
    menu.state = "settings"
    menu._draw_footer(screen, menu.scaling_manager)
    assert pygame.image.tostring(screen, "RGB") == before
    menu.state = "main"
    menu._draw_footer(screen, menu.scaling_manager)
    assert pygame.image.tostring(screen, "RGB") != before


def test_the_edge_fade_only_covers_the_side_with_more_content():
    """Fading the left edge while the first card rests against it just dims it."""
    menu = _menu(state="scenes")
    menu.max_scroll_x = 600.0        # a carousel with cards past the right edge
    menu.scroll_x = 0.0
    screen = pygame.Surface((REF_W, REF_H))
    menu._draw_edge_fade(screen, REF_W, REF_H)
    assert screen.get_at((2, REF_H // 2))[:3] == (0, 0, 0), "left edge faded too early"
    assert screen.get_at((REF_W - 2, REF_H // 2))[:3] != (0, 0, 0)


# ── 5. Icon sets ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("theme_id", THEMES)
def test_every_theme_ships_the_complete_icon_set(theme_id):
    icons = {p.stem for p in (THEMES_DIR / theme_id / "icons").glob("*.png")}
    missing = set(REQUIRED_ICONS) - icons
    assert not missing, f"{theme_id} is missing {sorted(missing)}"


@pytest.mark.parametrize("theme_id", THEMES)
def test_actions_that_mean_different_things_get_different_icons(theme_id):
    data = json.loads((THEMES_DIR / theme_id / "theme.json").read_text(encoding="utf-8"))
    theme = MenuTheme(data)
    pairs = (("set_music_volume", "set_sfx_volume"), ("toggle_res", "toggle_fs"))
    for first, second in pairs:
        a, b = theme.get_icon(first), theme.get_icon(second)
        assert a is not None and b is not None, (theme_id, first, second)
        assert a is not b, f"{theme_id}: {first} and {second} share one icon"


@pytest.mark.parametrize("theme_id", THEMES)
def test_every_theme_defines_its_settings_row_colour(theme_id):
    data = json.loads((THEMES_DIR / theme_id / "theme.json").read_text(encoding="utf-8"))
    theme = MenuTheme(data)
    r, g, b, alpha = theme.row_bg()
    assert 0 <= alpha <= 255
    # The pill must separate from the row it sits on, in both directions.
    assert theme.row_value_bg() != (r, g, b)


# ── 5b. Colour: everything the player reads has to be readable ──────────────

# What the engine paints under the chrome: the menu poster with its scrim
# baked in on the photo themes, the painted sky on kids.
BACKDROPS = {
    "default": (26, 30, 38), "android_std": (26, 30, 38), "cyber_neon": (24, 28, 36),
    "horror": (10, 8, 10), "kids": (120, 190, 170), "mystery": (28, 26, 24),
}
# The caption gradient baked into a card bottom, over a mid grey photograph.
CARD_CAPTION_BG = (22, 22, 22)


def _over(rgba, background):
    """Composite an RGBA colour over an opaque one."""
    if len(rgba) < 4:
        return tuple(rgba[:3])
    alpha = rgba[3] / 255.0
    return tuple(int(rgba[i] * alpha + background[i] * (1 - alpha)) for i in range(3))


@pytest.mark.parametrize("theme_id", THEMES)
def test_the_chrome_stays_readable(theme_id):
    """Contrast of every text/surface pair the chrome actually paints.

    WCAG ratios: 4.5 for body text, 3.0 for large text and for decoration that
    carries meaning. This caught red-on-black body text (3.6) and a section
    header painted with a fully transparent accent, i.e. pure black on black.
    """
    data = json.loads((THEMES_DIR / theme_id / "theme.json").read_text(encoding="utf-8"))
    theme = MenuTheme(data)
    back = BACKDROPS[theme_id]
    row = _over(theme.row_bg(), back)

    pairs = [
        ("icon caption", theme.color3("text_normal"), back, 4.5),
        ("row label", theme.color3("text_normal"), row, 4.5),
        ("row value", theme.color3("text_normal"), theme.row_value_bg(), 3.0),
        ("hover text", theme.color3("text_hover"), row, 4.5),
        ("section header", theme.accent_on(theme.scrim_color()), back, 3.0),
        ("card name", theme.caption_text(False), CARD_CAPTION_BG, 4.5),
        ("locked card name", theme.caption_text(True), CARD_CAPTION_BG, 3.0),
    ]
    for name, fg, bg, need in pairs:
        ratio = MenuTheme.contrast(fg, bg)
        assert ratio >= need, f"{theme_id}: {name} is {ratio:.2f}:1, needs {need}:1"


@pytest.mark.parametrize("theme_id", THEMES)
def test_every_theme_resolves_a_usable_accent(theme_id):
    """`btn_border_hover` is a border colour; some themes leave it invisible."""
    data = json.loads((THEMES_DIR / theme_id / "theme.json").read_text(encoding="utf-8"))
    theme = MenuTheme(data)
    assert max(theme.accent()) >= 24, "the accent has no colour at all"


# ── 6. A full frame still draws on every theme ──────────────────────────────

@pytest.mark.parametrize("theme_id", THEMES)
@pytest.mark.parametrize("state", ["main", "settings", "pause"])
def test_a_frame_draws_on_every_theme_and_state(theme_id, state):
    menu = _menu(theme_id, state)
    screen = pygame.Surface((REF_W, REF_H))
    menu.update(0.1, -100, -100)
    menu.draw(screen)          # must not raise
    assert not menu.skin._disabled_hooks
