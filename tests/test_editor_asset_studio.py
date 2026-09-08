"""
tests/test_editor_asset_studio.py

The asset studio sidebar: three columns that used to be constants.

The columns sat at fixed offsets (10 / 165 / 320) inside a fixed 480 px
sidebar, with 145 px sliders and 150 px footer buttons, and the numbers were
written twice: once in the renderer and once in the click handler. Two things
followed from that, both visible in a screenshot at UI scale 1.5 in German:
every heading was drawn over the column to its left, and the labels were cut
to "AUTO-ZUSCH...". The footer walked off the left edge of the modal.

Everything is now derived from `_img_editor_metrics`, so these tests can ask
the geometry directly:

  1. no two controls of the sidebar overlap, in five languages at three
     scales, on a small screen and a large one;
  2. every control stays inside the modal;
  3. the sidebar never eats the canvas;
  4. the click handler and the renderer read the same rects.
"""

from __future__ import annotations

import os
from types import SimpleNamespace

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pytest

pygame = pytest.importorskip("pygame")

from editor.constants import LANGS
from editor.mixins.img_editor import (
    ImgEditorMixin, STUDIO_SCALE_MIN, WORK_MIN_W,
)
from editor.ui.draw import _init_fonts
from engine.language_manager import LanguageManager

SIZES = [(1280, 720), (1600, 900), (1920, 1080)]
SCALES = [1.0, 1.25, 1.5]


@pytest.fixture(scope="module", autouse=True)
def _pygame_init():
    pygame.init()
    pygame.display.set_mode((64, 64))
    _init_fonts(1.0)
    yield
    _init_fonts(1.0)
    pygame.quit()


class FakeStudio(ImgEditorMixin):
    """Host for the studio geometry: no editor, no image, no window."""

    def __init__(self, lang="en", size=(1600, 900), scale=1.0):
        self.screen = pygame.Surface(size)
        self.screen_size = size
        self.lang_manager = LanguageManager()
        self.lang_manager.load_for_game("engine", lang)
        self._img_editor_save_confirm = False
        self._img_editor_copy_confirm = False
        self._img_editor_exit_confirm = False
        _init_fonts(scale)

    def _TR(self, key, *args):
        return self.lang_manager.get(key, args[0] if args else key)

    def geometry(self):
        ex, ey, ew, eh = self._img_editor_get_modal_rect()
        m = self._img_editor_metrics(ex, ey, ew, eh)
        rects = {}
        for column in (self._img_editor_col1_rects(m),
                       self._img_editor_col2_rects(m),
                       self._img_editor_col3_rects(m)):
            for name, value in column.items():
                if isinstance(value, list):
                    for index, rect in enumerate(value):
                        rects[f"{name}{index}"] = rect
                else:
                    rects[name] = value
        for index, rect in enumerate(
                self._img_editor_footer_rects(ex, ey, ew, eh)):
            rects[f"footer{index}"] = rect
        return SimpleNamespace(modal=pygame.Rect(ex, ey, ew, eh), m=m,
                               rects=rects)


def _cases():
    return [(lang, scale, size)
            for lang in LANGS for scale in SCALES for size in SIZES]


CASES = _cases()
IDS = [f"{lang}-{scale}-{size[0]}x{size[1]}" for lang, scale, size in CASES]


# -----------------------------------------------------------------------------
# 1. NOTHING IS DRAWN OVER ANYTHING ELSE
# -----------------------------------------------------------------------------

@pytest.mark.parametrize("lang,scale,size", CASES, ids=IDS)
def test_no_two_controls_of_the_studio_overlap(lang, scale, size):
    g = FakeStudio(lang, size, scale).geometry()
    items = sorted(g.rects.items())
    for i, (name_a, rect_a) in enumerate(items):
        for name_b, rect_b in items[i + 1:]:
            assert not rect_a.colliderect(rect_b), (
                f"{lang} @{scale} {size}: {name_a} {tuple(rect_a)} overlaps "
                f"{name_b} {tuple(rect_b)}")


@pytest.mark.parametrize("lang,scale,size", CASES, ids=IDS)
def test_every_control_stays_inside_the_modal(lang, scale, size):
    g = FakeStudio(lang, size, scale).geometry()
    for name, rect in g.rects.items():
        assert g.modal.contains(rect), (
            f"{lang} @{scale} {size}: {name} {tuple(rect)} is outside the "
            f"modal {tuple(g.modal)}")


@pytest.mark.parametrize("lang,scale,size", CASES, ids=IDS)
def test_the_sidebar_never_eats_the_canvas(lang, scale, size):
    g = FakeStudio(lang, size, scale).geometry()
    canvas_w = g.m["sb_x"] - g.modal.x
    assert canvas_w >= WORK_MIN_W, (
        f"{lang} @{scale} {size}: only {canvas_w}px left for the image")


# -----------------------------------------------------------------------------
# 2. THE COLUMNS ARE COLUMNS
# -----------------------------------------------------------------------------

@pytest.mark.parametrize("lang", LANGS)
def test_the_three_columns_are_in_order_and_do_not_touch(lang):
    studio = FakeStudio(lang, (1600, 900), 1.5)
    g = studio.geometry()
    m = g.m
    assert m["col1_x"] < m["col2_x"] < m["col3_x"]
    assert m["col1_x"] + m["col_w"] <= m["col2_x"]
    assert m["col2_x"] + m["col_w"] <= m["col3_x"]
    assert m["col3_x"] + m["col_w"] <= g.modal.right


@pytest.mark.parametrize("lang", LANGS)
def test_a_column_is_as_wide_as_its_widest_label(lang):
    """The German "HINTERGRUND ENTFERNEN" is what sets the width there."""
    from editor.ui.draw import _button_w

    studio = FakeStudio(lang, (1920, 1080), 1.0)
    m = studio.geometry().m
    label = studio._TR("img_remove_bg", "REMOVE BACKGROUND")
    assert m["col_w"] >= _button_w(label, "sm")


# -----------------------------------------------------------------------------
# 3. THE SCALE GIVES WAY BEFORE THE LAYOUT DOES
# -----------------------------------------------------------------------------

def test_a_small_window_reduces_the_studio_scale():
    small = FakeStudio("de", (1280, 720), 1.5)
    large = FakeStudio("de", (1920, 1080), 1.5)
    assert small.geometry().m["scale"] < large.geometry().m["scale"]


def test_the_scale_never_collapses():
    tiny = FakeStudio("de", (900, 500), 1.5)
    assert tiny.geometry().m["scale"] >= STUDIO_SCALE_MIN


def test_the_scale_never_exceeds_the_ui_scale():
    for scale in SCALES:
        studio = FakeStudio("en", (1920, 1080), scale)
        assert studio.geometry().m["scale"] <= scale + 1e-9


# -----------------------------------------------------------------------------
# 4. THE FOOTER
# -----------------------------------------------------------------------------

@pytest.mark.parametrize("lang,scale,size", CASES, ids=IDS)
def test_the_footer_buttons_are_a_row_inside_the_modal(lang, scale, size):
    studio = FakeStudio(lang, size, scale)
    ex, ey, ew, eh = studio._img_editor_get_modal_rect()
    rects = studio._img_editor_footer_rects(ex, ey, ew, eh)
    assert len(rects) == 3
    assert rects[0].x >= ex, "the footer walked off the left edge"
    for left, right in zip(rects, rects[1:]):
        assert left.right <= right.left
        assert left.y == right.y


@pytest.mark.parametrize("lang", LANGS)
def test_a_footer_button_holds_its_label(lang):
    from editor.ui.draw import _text_wh

    studio = FakeStudio(lang, (1600, 900), 1.0)
    ex, ey, ew, eh = studio._img_editor_get_modal_rect()
    rects = studio._img_editor_footer_rects(ex, ey, ew, eh)
    for label, rect in zip(studio._img_editor_footer_labels(), rects):
        assert _text_wh(label, "sm")[0] + 10 <= rect.w, (
            f"{lang}: {label!r} does not fit its button")


def test_the_confirmation_label_also_fits():
    """Arming a button swaps its label: the row must still hold it."""
    from editor.ui.draw import _text_wh

    for lang in LANGS:
        studio = FakeStudio(lang, (1600, 900), 1.0)
        studio._img_editor_save_confirm = True
        studio._img_editor_exit_confirm = True
        ex, ey, ew, eh = studio._img_editor_get_modal_rect()
        rects = studio._img_editor_footer_rects(ex, ey, ew, eh)
        for label, rect in zip(studio._img_editor_footer_labels(), rects):
            assert _text_wh(label, "sm")[0] + 10 <= rect.w, (lang, label)


# -----------------------------------------------------------------------------
# 5. NO LABEL IS LEFT IN ONE LANGUAGE
# -----------------------------------------------------------------------------

@pytest.mark.parametrize("lang", LANGS)
def test_every_studio_label_is_translated(lang):
    """The sidebar drew eight English buttons under translated headings, and
    the footer said SALVA / COPIA / ESCI to everyone."""
    import json
    import pathlib
    import re

    source = pathlib.Path("editor/mixins/img_editor.py").read_text(encoding="utf-8")
    keys = set(re.findall(r'_TR\(\s*"(img_[a-z0-9_]+)"', source))
    strings = json.loads(
        pathlib.Path(f"engine/assets/strings/{lang}.json").read_text(encoding="utf-8"))
    missing = sorted(k for k in keys if k not in strings)
    assert not missing, f"{lang} has no text for {missing}"
