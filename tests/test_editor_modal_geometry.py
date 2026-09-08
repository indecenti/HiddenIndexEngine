"""
tests/test_editor_modal_geometry.py

Modal dialogs: the geometry is computed once and the click handler uses what
the renderer drew.

Every dialog in the editor used to write its layout twice - the renderer
accumulated offsets, the click handler restated them as literals - and the two
copies had already drifted apart:

  * the tag picker hit-tested its close button 4 px above where it was drawn;
  * the translation editor did the same on the whole footer (4 px on y, 2 px on
    the height), and its two buttons were fixed at 140/150 px, so a translated
    label overlapped the next button and ran past the right edge;
  * the new-object dialog restated seven row offsets (54, 114, 148, ...) that
    the renderer only reproduced by accident, and none of them followed the
    font, so above UI scale 1.0 a label ran into the field under it;
  * the icon picker clamped its scroll with a hand-picked "3 rows are probably
    visible".

These pin the shared helpers and the published hitboxes.
"""

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pytest

pygame = pytest.importorskip("pygame")

from editor.constants import LANGS, UI_SCALE_MAX, UI_SCALE_MIN
from editor.mixins.icon_modal import IconModalMixin
from editor.mixins.newobj_modal import NewObjModalMixin
from editor.ui.draw import _init_fonts, _text_wh
from engine.language_manager import LanguageManager


@pytest.fixture(scope="module", autouse=True)
def _pygame_init():
    pygame.init()
    pygame.display.set_mode((64, 64))
    _init_fonts(1.0)
    yield
    _init_fonts(1.0)
    pygame.quit()


class _Host:
    """Shared bits every modal mixin reads off the editor."""

    def __init__(self, lang: str = "en", size=(1280, 720)):
        self.screen = pygame.Surface(size)
        self.screen_size = size
        self.lang_manager = LanguageManager()
        self.lang_manager.load_for_game("engine", lang)

    def _TR(self, key, *args):
        return self.lang_manager.get(key, *args)


class FakeNewObj(_Host, NewObjModalMixin):
    def __init__(self, lang="en", **kw):
        _Host.__init__(self, lang, **kw)
        self._newobj = {"id": "", "icon_path": "", "detection": "circle",
                        "radius": 30, "width": 60, "height": 60, "hint": 30,
                        "remove_bg": False, "autotrim": False}
        self._newobj_field = "id"
        self._newobj_buf = ""
        self._newobj_modal = True
        self._newobj_busy = False

    def _newobj_poll(self):
        pass

    def _load_img(self, path, size):
        return None


class FakeIcons(_Host, IconModalMixin):
    def __init__(self, count: int, lang="en", **kw):
        _Host.__init__(self, lang, **kw)
        self._icon_list = [Path(f"icon_{i}.png") for i in range(count)]
        self._icon_scroll = 0
        self._icon_modal = True


# ─────────────────────────────────────────────────────────────────────────────
# NUOVO OGGETTO
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("lang", LANGS)
@pytest.mark.parametrize("scale", (UI_SCALE_MIN, 1.0, UI_SCALE_MAX))
def test_newobj_rows_never_overlap_and_stay_in_the_dialog(lang, scale):
    _init_fonts(scale)
    try:
        host = FakeNewObj(lang)
        host._r_newobj_modal(1280, 720)
        hits = host._newobj_hitboxes
        assert hits, "the dialog must publish its hitboxes"
        rows = [hits[k] for k in ("id", "icon", "radius", "width", "height",
                                  "hint", "add")]
        for first, second in zip(rows, rows[1:]):
            assert first.bottom <= second.top, (
                f"{lang} at {scale}: rows overlap ({first} / {second})")
    finally:
        _init_fonts(1.0)


@pytest.mark.parametrize("lang", LANGS)
@pytest.mark.parametrize("scale", (UI_SCALE_MIN, 1.0, UI_SCALE_MAX))
def test_newobj_labels_fit_beside_their_field(lang, scale):
    _init_fonts(scale)
    try:
        host = FakeNewObj(lang)
        column = host._newobj_label_col()
        for key, default in host._NEWOBJ_LABELS:
            width = _text_wh(host._TR(key, default), "sm")[0]
            assert width <= column - 20, (
                f"{lang} at {scale}: {default} does not fit the label column")
    finally:
        _init_fonts(1.0)


def test_newobj_label_column_follows_the_ui_scale():
    host = FakeNewObj()
    _init_fonts(UI_SCALE_MIN)
    small = host._newobj_label_col()
    _init_fonts(UI_SCALE_MAX)
    large = host._newobj_label_col()
    _init_fonts(1.0)
    assert large > small


def test_newobj_click_uses_the_rects_that_were_drawn():
    host = FakeNewObj()
    host._r_newobj_modal(1280, 720)
    field = host._newobj_hitboxes["height"]
    host._newobj_field = "id"
    host._newobj_click(field.centerx, field.centery, 1280, 720)
    assert host._newobj_field == "height"


def test_newobj_click_before_the_first_frame_is_a_no_op():
    host = FakeNewObj()
    host._newobj_click(10, 10, 1280, 720)     # never rendered: no hitboxes yet
    assert host._newobj_modal is True


def test_newobj_cancel_closes_the_dialog():
    host = FakeNewObj()
    host._r_newobj_modal(1280, 720)
    cancel = host._newobj_hitboxes["cancel"]
    host._newobj_click(cancel.centerx, cancel.centery, 1280, 720)
    assert host._newobj_modal is False


# ─────────────────────────────────────────────────────────────────────────────
# SELETTORE ICONE
# ─────────────────────────────────────────────────────────────────────────────

def test_icon_scroll_stops_at_the_last_row():
    host = FakeIcons(count=200)
    geo = host._icon_grid_metrics(1280, 720)
    assert geo["max_scroll"] == geo["rows"] - geo["visible_rows"]
    assert geo["max_scroll"] > 0


def test_icon_scroll_is_zero_when_everything_fits():
    host = FakeIcons(count=3)
    assert host._icon_grid_metrics(1280, 720)["max_scroll"] == 0


def test_icon_wheel_never_scrolls_past_the_end():
    host = FakeIcons(count=50)
    host.screen = pygame.Surface((1280, 720))
    geo = host._icon_grid_metrics(1280, 720)
    for _ in range(200):
        host._icon_wheel(pygame.event.Event(pygame.MOUSEWHEEL, {"y": -1}))
    assert host._icon_scroll == geo["max_scroll"]
    for _ in range(200):
        host._icon_wheel(pygame.event.Event(pygame.MOUSEWHEEL, {"y": 1}))
    assert host._icon_scroll == 0


def test_icon_wheel_needs_the_modal_open():
    host = FakeIcons(count=50)
    host._icon_modal = False
    host._icon_wheel(pygame.event.Event(pygame.MOUSEWHEEL, {"y": -1}))
    assert host._icon_scroll == 0


def test_icon_items_of_the_first_page_are_inside_the_grid():
    host = FakeIcons(count=200)
    geo = host._icon_grid_metrics(1280, 720)
    for i in range(geo["cols"] * geo["visible_rows"]):
        assert geo["grid"].contains(host._icon_item_rect(geo, i)), i


def test_icon_dialog_fits_a_small_window():
    host = FakeIcons(count=20)
    geo = host._icon_grid_metrics(800, 600)
    assert pygame.Rect(0, 0, 800, 600).contains(geo["box"])
    assert geo["box"].contains(geo["grid"])
    assert geo["box"].contains(geo["cancel"])


# ─────────────────────────────────────────────────────────────────────────────
# AUDITOR
# ─────────────────────────────────────────────────────────────────────────────

from editor.constants import STATUS_H, TOP_BAR_H  # noqa: E402
from editor.mixins.auditor import AuditorMixin  # noqa: E402


class FakeAuditor(_Host, AuditorMixin):
    def __init__(self, issues: int, lang="en", **kw):
        _Host.__init__(self, lang, **kw)
        self._auditor_issues = [{"severity": "err", "title": f"t{i}",
                                 "detail": "d", "repaired": False}
                                for i in range(issues)]
        self._auditor_scroll = 0
        self._auditor_game_id = "SomeGame"


@pytest.mark.parametrize("scale", (UI_SCALE_MIN, 1.0, UI_SCALE_MAX))
def test_auditor_stays_between_the_top_bar_and_the_status_bar(scale):
    _init_fonts(scale)
    try:
        geo = FakeAuditor(issues=40)._auditor_layout(1280, 720)
        assert geo["box"].top >= TOP_BAR_H
        assert geo["box"].bottom <= 720 - STATUS_H
    finally:
        _init_fonts(1.0)


@pytest.mark.parametrize("scale", (UI_SCALE_MIN, 1.0, UI_SCALE_MAX))
def test_auditor_rows_fit_the_list_area(scale):
    _init_fonts(scale)
    try:
        geo = FakeAuditor(issues=40)._auditor_layout(1280, 720)
        assert geo["visible_rows"] * geo["item_h"] <= geo["list"].h
        assert geo["box"].contains(geo["list"])
    finally:
        _init_fonts(1.0)


@pytest.mark.parametrize("scale", (UI_SCALE_MIN, 1.0, UI_SCALE_MAX))
def test_auditor_row_shows_both_of_its_lines(scale):
    _init_fonts(scale)
    try:
        geo = FakeAuditor(issues=3)._auditor_layout(1280, 720)
        needed = _text_wh("Ag", "sm")[1] + _text_wh("Ag", "xs")[1]
        assert geo["item_h"] > needed
    finally:
        _init_fonts(1.0)


@pytest.mark.parametrize("scale", (UI_SCALE_MIN, 1.0, UI_SCALE_MAX))
def test_auditor_header_holds_title_and_project(scale):
    _init_fonts(scale)
    try:
        geo = FakeAuditor(issues=3)._auditor_layout(1280, 720)
        stacked = _text_wh("Ag", "lg")[1] + _text_wh("Ag", "sm")[1]
        assert geo["header_h"] > stacked
    finally:
        _init_fonts(1.0)


def test_auditor_scroll_stops_at_the_last_row():
    host = FakeAuditor(issues=40)
    geo = host._auditor_layout(1280, 720)
    assert geo["max_scroll"] == 40 - geo["visible_rows"]


def test_auditor_scroll_is_zero_when_everything_fits():
    assert FakeAuditor(issues=2)._auditor_layout(1280, 720)["max_scroll"] == 0


@pytest.mark.parametrize("lang", LANGS)
def test_auditor_header_buttons_never_collide(lang):
    geo = FakeAuditor(issues=5, lang=lang)._auditor_layout(1280, 720)
    assert not geo["rescan"].colliderect(geo["close"])
    assert geo["box"].contains(geo["rescan"])
    assert geo["box"].contains(geo["close"])


# ─────────────────────────────────────────────────────────────────────────────
# PLAYLIST: BARRA DI SEEK
# ─────────────────────────────────────────────────────────────────────────────

from editor.mixins import music_modal as mm  # noqa: E402


def test_seek_hitbox_sits_on_the_bar_that_is_drawn():
    """The bar is drawn on the row surface; the hitbox is the same place."""
    list_x, row_y = 100, 400
    hit = mm._seek_bar_rect(list_x, row_y)
    drawn_x = list_x + mm._ROW_PAD_X + mm._BAR_X
    drawn_y = row_y + mm._ROW_PAD_Y + mm._BAR_Y
    assert hit.x == drawn_x
    assert hit.width == mm._BAR_W
    # the bar itself is a few pixels tall: the hitbox is centred on it
    assert hit.top <= drawn_y <= hit.bottom
    assert hit.top <= drawn_y + mm._BAR_H <= hit.bottom


def test_seek_hitbox_is_easy_to_hit():
    hit = mm._seek_bar_rect(0, 0)
    assert hit.height >= mm._BAR_H * 4


def test_seek_hitbox_follows_the_row():
    first = mm._seek_bar_rect(0, 0)
    second = mm._seek_bar_rect(0, mm._ROW_H)
    assert second.y - first.y == mm._ROW_H


# ─────────────────────────────────────────────────────────────────────────────
# DIALOGHI SEMPRE DENTRO LA FINESTRA
# ─────────────────────────────────────────────────────────────────────────────

from editor.constants import MIN_EDITOR_HEIGHT, MIN_EDITOR_WIDTH  # noqa: E402
from editor.ui.draw import dialog_rect  # noqa: E402


def test_a_dialog_is_clamped_to_the_window():
    """The playlist and the video picker asked for 1100x800 on a 1280x720
    window: their title and their footer buttons were off screen."""
    box = dialog_rect(MIN_EDITOR_WIDTH, MIN_EDITOR_HEIGHT, 1100, 800)
    assert pygame.Rect(0, 0, MIN_EDITOR_WIDTH, MIN_EDITOR_HEIGHT).contains(box)


def test_a_dialog_that_fits_is_left_alone():
    box = dialog_rect(1920, 1080, 800, 600)
    assert (box.w, box.h) == (800, 600)


def test_a_dialog_is_centred():
    box = dialog_rect(1000, 800, 400, 200)
    assert box.centerx == 500 and box.centery == 400


def test_a_dialog_keeps_the_margin_it_is_given():
    box = dialog_rect(1000, 800, 5000, 5000, margin=50)
    assert (box.w, box.h) == (900, 700)


def test_a_dialog_never_collapses_on_a_tiny_window():
    box = dialog_rect(100, 80, 800, 600)
    assert box.w >= 120 and box.h >= 120
