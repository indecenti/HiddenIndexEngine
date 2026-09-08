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
from editor.mixins.shortcuts_overlay import ShortcutsOverlayMixin
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

def test_shortcut_panel_lists_every_bound_command():
    """The panel is the whole registry, not a hand-kept subset."""
    from editor.commands import COMMANDS
    host = FakeChrome("en")
    listed = {entry[2] for column in host._shortcuts_columns()
              for block in column for entry in block if entry[0] == "row"}
    assert listed == {c.label for c in COMMANDS if c.keys}


def test_shortcut_panel_uses_two_columns_when_there_is_room():
    host = FakeChrome("en")
    assert len(host._shortcuts_columns(max_rows=1000)) == 2


def test_shortcut_panel_adds_columns_when_the_window_is_short():
    host = FakeChrome("en")
    roomy = host._shortcuts_columns(max_rows=1000)
    cramped = host._shortcuts_columns(max_rows=20)
    assert len(cramped) > len(roomy)


def test_shortcut_panel_honours_the_row_budget_when_it_can():
    host = FakeChrome("en")
    for budget in (20, 25, 40):
        columns = host._shortcuts_columns(max_rows=budget)
        assert max(sum(len(b) for b in c) for c in columns) <= budget, budget


def test_shortcut_panel_never_splits_a_group_to_meet_the_budget():
    """With a budget below the tallest group, the group stays whole."""
    host = FakeChrome("en")
    tallest = max(len(b) for b in host._shortcuts_blocks())
    columns = host._shortcuts_columns(max_rows=2)
    assert max(sum(len(b) for b in c) for c in columns) == tallest


def test_shortcut_panel_keeps_a_group_in_one_column():
    host = FakeChrome("en")
    seen = set()
    for column in host._shortcuts_columns(max_rows=10):
        headers = {b[0][1] for b in column}
        assert not (headers & seen)
        seen |= headers


def test_shortcut_panel_never_drops_a_command():
    host = FakeChrome("en")
    for budget in (1, 5, 12, 100):
        rows = [e for column in host._shortcuts_columns(max_rows=budget)
                for block in column for e in block if e[0] == "row"]
        assert len(rows) == len({r[2] for r in rows}) > 30, budget


@pytest.mark.parametrize("lang", LANGS)
def test_shortcut_panel_is_translated(lang):
    host = FakeChrome(lang)
    rows = [e for column in host._shortcuts_columns()
            for block in column for e in block]
    assert len(rows) > 20, lang


@pytest.mark.parametrize("lang", LANGS)
@pytest.mark.parametrize("scale", (UI_SCALE_MIN, 1.0, UI_SCALE_MAX))
@pytest.mark.parametrize("size", ((1280, 720), (1600, 900), (1920, 1080)))
def test_shortcut_panel_content_stays_inside_the_panel(lang, scale, size):
    """A short window adds a column instead of drawing past the panel."""
    from editor.constants import SHORTCUTS_ROW_H
    _init_fonts(scale)
    try:
        host = FakeChrome(lang, size=size)
        geo = host._shortcuts_geometry(*size)
        box = geo["box"]
        assert pygame.Rect((0, 0), size).contains(box)
        body_bottom = geo["body_top"] + geo["rows"] * SHORTCUTS_ROW_H
        assert body_bottom <= box.bottom, (
            f"{lang} at {scale} on {size}: rows spill out of the panel")
    finally:
        _init_fonts(1.0)


@pytest.mark.parametrize("size", ((1280, 720), (1920, 1080)))
def test_shortcut_panel_columns_fit_side_by_side(size):
    host = FakeChrome("de", size=size)
    geo = host._shortcuts_geometry(*size)
    n = len(geo["columns"])
    assert geo["column_w"] > 0
    assert n * geo["column_w"] <= geo["box"].w


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


# ─────────────────────────────────────────────────────────────────────────────
# 6. CONTROLLI ZOOM NELL'HUD DEL CANVAS
# ─────────────────────────────────────────────────────────────────────────────

def test_hud_publishes_its_controls():
    host = FakeChrome("en")
    host._r_canvas_hud(host._canvas_rect())
    assert set(host._hud_hitboxes) == {"zoom_out", "zoom_in", "fit"}


@pytest.mark.parametrize("lang", LANGS)
@pytest.mark.parametrize("scale", (UI_SCALE_MIN, 1.0, UI_SCALE_MAX))
def test_hud_controls_stay_inside_the_canvas(lang, scale):
    _init_fonts(scale)
    try:
        host = FakeChrome(lang)
        canvas = host._canvas_rect()
        host._r_canvas_hud(canvas)
        for name, rect in host._hud_hitboxes.items():
            assert canvas.contains(rect), f"{lang} at {scale}: {name} leaves the canvas"
    finally:
        _init_fonts(1.0)


def test_hud_controls_never_overlap():
    host = FakeChrome("de")
    host._r_canvas_hud(host._canvas_rect())
    rects = list(host._hud_hitboxes.values())
    for i, first in enumerate(rects):
        for second in rects[i + 1:]:
            assert not first.colliderect(second)


def test_hud_zoom_buttons_change_the_zoom():
    host = FakeChrome("en")
    host._r_canvas_hud(host._canvas_rect())
    before = host.zoom
    zoom_in = host._hud_hitboxes["zoom_in"]
    assert host._hud_click(zoom_in.centerx, zoom_in.centery) is True
    assert host.zoom > before
    zoom_out = host._hud_hitboxes["zoom_out"]
    host._hud_click(zoom_out.centerx, zoom_out.centery)
    assert host.zoom == pytest.approx(before)


def test_hud_click_elsewhere_is_not_consumed():
    host = FakeChrome("en")
    host._r_canvas_hud(host._canvas_rect())
    assert host._hud_click(0, 0) is False


def test_hud_click_before_the_first_frame_is_a_no_op():
    assert FakeChrome("en")._hud_click(10, 10) is False
