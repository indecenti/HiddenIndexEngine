"""
tests/test_editor_ui_layout.py

Chrome layout of the editor: what used to break silently here was the geometry
written twice, once in the renderer and once next to it as a constant.

  1. a button is as wide as the label it has to show, at any UI scale;
  2. the canvas toolbar never overlaps itself, never leaves the canvas and
     stays clear of the zoom/coordinates HUD, in all five languages and at the
     extremes of the UI scale;
  3. the F1 shortcut panel parses the two shortcut strings without losing a
     row and without listing the same key twice;
  4. the recent scenes list collapses two spellings of the same path and drops
     an entry that is not a scene folder.

Host fake on the mixins only: no editor, no window.
"""

from __future__ import annotations

import json
import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pytest

pygame = pytest.importorskip("pygame")

from editor.constants import LANGS, MODE_SELECT, UI_SCALE_MAX, UI_SCALE_MIN
from editor.mixins.io_ops import _is_scene_dir, _resolve_recent
from editor.mixins.render_canvas import RenderCanvasMixin
from editor.mixins.shortcuts_overlay import ShortcutsOverlayMixin, _parse_shortcuts
from editor.mixins.viewport import ViewportMixin
from editor.ui.draw import _button_w, _init_fonts, _text_wh
from engine.language_manager import LanguageManager


@pytest.fixture(scope="module", autouse=True)
def _pygame_init():
    pygame.init()
    pygame.display.set_mode((64, 64))
    _init_fonts(1.0)
    yield
    _init_fonts(1.0)
    pygame.quit()


class FakeChrome(RenderCanvasMixin, ShortcutsOverlayMixin, ViewportMixin):
    """Minimal host for the toolbar layout and the shortcuts panel."""

    def __init__(self, lang: str = "en", size=(1280, 720)):
        self.screen = pygame.Surface(size)
        self.screen_size = size
        self.panel_l_w = 300
        self.panel_r_w = 300
        self.panels_visible = True
        self.mode = MODE_SELECT
        self.zoom = 1.0
        self.origin_x = 0.0
        self.origin_y = 0.0
        self.show_overlay = False
        self.show_grid = False
        self.show_icons = True
        self.effects_catalog_sel = None
        self.lang_manager = LanguageManager()
        self.lang_manager.load_for_game("engine", lang)

    def _TR(self, key, *args):
        return self.lang_manager.get(key, *args)

    def _update_layout(self):
        pass

    def _mark_dirty(self):
        pass


# ─────────────────────────────────────────────────────────────────────────────
# 1. LARGHEZZA BOTTONI
# ─────────────────────────────────────────────────────────────────────────────

def test_button_width_follows_the_label():
    assert _button_w("Save") < _button_w("Save the whole scene")


def test_button_width_follows_the_ui_scale():
    _init_fonts(1.0)
    small = _button_w("Speichern", icon="save")
    _init_fonts(UI_SCALE_MAX)
    large = _button_w("Speichern", icon="save")
    _init_fonts(1.0)
    assert large > small


def test_button_width_never_below_the_minimum():
    assert _button_w("x", min_w=140) == 140


# ─────────────────────────────────────────────────────────────────────────────
# 2. TOOLBAR CANVAS
# ─────────────────────────────────────────────────────────────────────────────

def _layout_cases():
    return [(lang, scale)
            for lang in LANGS
            for scale in (UI_SCALE_MIN, 1.0, UI_SCALE_MAX)]


@pytest.mark.parametrize("lang,scale", _layout_cases())
def test_toolbar_items_never_overlap_and_stay_inside_the_canvas(lang, scale):
    _init_fonts(scale)
    try:
        host = FakeChrome(lang)
        canvas = host._canvas_rect()
        items = host._get_toolbar_layout()
        assert items, "the toolbar must always offer the tools"
        for item in items:
            assert canvas.contains(item["r"]), (
                f"{lang} at {scale}: {item['id']} leaves the canvas")
        for i, first in enumerate(items):
            for second in items[i + 1:]:
                assert not first["r"].colliderect(second["r"]), (
                    f"{lang} at {scale}: {first['id']} overlaps {second['id']}")
    finally:
        _init_fonts(1.0)


@pytest.mark.parametrize("lang,scale", _layout_cases())
def test_toolbar_labels_fit_their_button(lang, scale):
    _init_fonts(scale)
    try:
        host = FakeChrome(lang)
        for item in host._get_toolbar_layout():
            text_w = _text_wh(item["lbl"], "sm")[0]
            assert text_w <= item["r"].w, (
                f"{lang} at {scale}: {item['lbl']} is clipped")
    finally:
        _init_fonts(1.0)


def test_toolbar_stays_clear_of_the_canvas_hud():
    """The HUD pill sits bottom right, every toolbar row well above it."""
    host = FakeChrome("de", size=(1280, 720))
    canvas = host._canvas_rect()
    host._r_canvas_hud(canvas)          # must not raise, and draws bottom right
    toolbar_bottom = max(item["r"].bottom for item in host._get_toolbar_layout())
    assert toolbar_bottom < canvas.bottom - 40


def test_narrow_canvas_wraps_the_toolbar_instead_of_overflowing():
    wide = FakeChrome("de", size=(1600, 720))
    narrow = FakeChrome("de", size=(1000, 720))
    rows_wide = {item["r"].y for item in wide._get_toolbar_layout()}
    rows_narrow = {item["r"].y for item in narrow._get_toolbar_layout()}
    assert len(rows_narrow) > len(rows_wide)


# ─────────────────────────────────────────────────────────────────────────────
# 3. PANNELLO SCORCIATOIE (F1)
# ─────────────────────────────────────────────────────────────────────────────

def test_parse_shortcuts_splits_key_and_description():
    assert _parse_shortcuts("Ctrl+S=Save R=Rotate") == [
        ("Ctrl+S", "Save"), ("R", "Rotate")]


def test_parse_shortcuts_keeps_multi_word_descriptions():
    assert _parse_shortcuts("Space+drag=Pan the view") == [
        ("Space+drag", "Pan the view")]


def test_parse_shortcuts_ignores_a_leading_stray_word():
    assert _parse_shortcuts("hello Ctrl+S=Save") == [("Ctrl+S", "Save")]


def test_shortcut_rows_list_each_key_once():
    host = FakeChrome("en")
    keys = [k.casefold() for k, _ in host._shortcuts_rows()]
    assert len(keys) == len(set(keys))


def test_shortcut_rows_are_capitalised():
    host = FakeChrome("en")
    for _, desc in host._shortcuts_rows():
        assert desc[:1] == desc[:1].upper()


def test_every_language_produces_shortcut_rows():
    for lang in LANGS:
        assert FakeChrome(lang)._shortcuts_rows(), lang


def test_f1_panel_toggles():
    host = FakeChrome("en")
    assert host._shortcuts_close() is False
    host._shortcuts_toggle()
    assert host._shortcuts_open is True
    assert host._shortcuts_close() is True
    assert host._shortcuts_open is False


# ─────────────────────────────────────────────────────────────────────────────
# 4. PROGETTI RECENTI
# ─────────────────────────────────────────────────────────────────────────────

def test_two_spellings_of_the_same_path_resolve_equal(tmp_path):
    scene = tmp_path / "levels" / "One" / "Room"
    scene.mkdir(parents=True)
    weird = tmp_path / "levels" / "One" / ".." / "One" / "Room"
    assert _resolve_recent(scene) == _resolve_recent(weird)


def test_resolve_recent_of_nothing_is_empty():
    assert _resolve_recent("") == ""
    assert _resolve_recent(None) == ""


def test_a_scene_folder_is_one_holding_a_scene_json(tmp_path):
    scene = tmp_path / "Room"
    scene.mkdir()
    assert _is_scene_dir(scene) is False
    (scene / "scene.json").write_text(json.dumps({"objects": []}),
                                      encoding="utf-8")
    assert _is_scene_dir(scene) is True
    # the scene.json itself is a file, not a scene folder
    assert _is_scene_dir(scene / "scene.json") is False


# ─────────────────────────────────────────────────────────────────────────────
# 5. OUTLINE: GEOMETRIA CHE SEGUE LA SCALA UI
# ─────────────────────────────────────────────────────────────────────────────

from editor.mixins.outline import OutlineMixin  # noqa: E402


class FakeOutlineHost(OutlineMixin):
    """Just enough state for the outline geometry helpers."""

    panel_l_w = 300
    scene_data = {"objects": []}


def test_outline_row_grows_with_the_ui_scale():
    host = FakeOutlineHost()
    _init_fonts(UI_SCALE_MIN)
    small = host._outline_row_h()
    _init_fonts(UI_SCALE_MAX)
    large = host._outline_row_h()
    _init_fonts(1.0)
    assert large > small


def test_outline_row_always_fits_its_text():
    host = FakeOutlineHost()
    for scale in (UI_SCALE_MIN, 1.0, UI_SCALE_MAX):
        _init_fonts(scale)
        try:
            assert host._outline_row_h() > _text_wh("Ag", "sm")[1]
        finally:
            _init_fonts(1.0)


def test_outline_header_grows_with_the_ui_scale():
    host = FakeOutlineHost()
    _init_fonts(UI_SCALE_MIN)
    small = host._outline_list_top()
    _init_fonts(UI_SCALE_MAX)
    large = host._outline_list_top()
    _init_fonts(1.0)
    assert large > small


def test_drawing_primitives_work_before_init_fonts():
    """A layout computed before the first frame must not raise on the fonts."""
    import editor.ui.draw as draw
    saved = dict(draw._FONTS)
    draw._FONTS.clear()
    try:
        assert _text_wh("Ag", "sm")[1] > 0
    finally:
        draw._FONTS.clear()
        draw._FONTS.update(saved)
