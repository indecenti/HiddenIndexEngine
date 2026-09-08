"""
tests/test_editor_browser_header.py

The header strip of the three project-browser columns.

Games, Levels and Scenes each carry a row of small buttons in their heading.
They were a list of rects at -32, -62, -92, -122, -152 and -182 px from the
right edge of the column, written once in the renderer and once in the click
handler, and none of it scaled: at UI scale 1.25 "DUP" was drawn as "D..." and
"MV" as "M...", and at 1.5 the strip ran under the column title.

`_GS_HEADER_BUTTONS` now declares the strip and `_gs_header_rects` places it,
so the two halves cannot drift and the tests can check the placement.
"""

from __future__ import annotations

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import json
from pathlib import Path

import pytest

pygame = pytest.importorskip("pygame")

from editor.constants import LANGS
from editor.mixins.game_select import GameSelectMixin
from editor.ui.draw import _init_fonts, _text_wh

ROOT = Path(__file__).resolve().parents[1]
SCALES = [1.0, 1.25, 1.5]
COLUMNS = (0, 1, 2)


@pytest.fixture(scope="module", autouse=True)
def _pygame_init():
    pygame.init()
    pygame.display.set_mode((64, 64))
    _init_fonts(1.0)
    yield
    _init_fonts(1.0)
    pygame.quit()


class FakeBrowser(GameSelectMixin):
    """Host for the header geometry only."""

    def __init__(self, scale=1.0):
        _init_fonts(scale)


def rects(scale, column, col_w=420, cx2=30, cy2=200):
    return FakeBrowser(scale)._gs_header_rects(column, cx2, cy2, col_w)


@pytest.mark.parametrize("scale", SCALES)
@pytest.mark.parametrize("column", COLUMNS)
def test_the_strip_never_overlaps_itself(scale, column):
    placed = list(rects(scale, column).items())
    for i, (name_a, rect_a) in enumerate(placed):
        for name_b, rect_b in placed[i + 1:]:
            assert not rect_a.colliderect(rect_b), (
                f"column {column} @{scale}: {name_a} overlaps {name_b}")


@pytest.mark.parametrize("scale", SCALES)
@pytest.mark.parametrize("column", COLUMNS)
def test_the_strip_stays_inside_its_column(scale, column):
    col_w, cx2 = 420, 30
    for name, rect in rects(scale, column, col_w, cx2).items():
        assert rect.right <= cx2 + col_w, f"{name} runs past the column"
        assert rect.left >= cx2, f"{name} starts before the column"


@pytest.mark.parametrize("scale", SCALES)
@pytest.mark.parametrize("column", COLUMNS)
def test_the_strip_leaves_a_readable_title(scale, column):
    """The title is clamped to the room before the strip, so what has to be
    checked is that some room is left: a title clamped to nothing is a header
    with no name on it."""
    col_w, cx2 = 420, 30
    leftmost = min(r.left for r in rects(scale, column, col_w, cx2).values())
    room = leftmost - (cx2 + 12) - 8
    assert room >= 4 * _text_wh("W", "sm")[0], (
        f"column {column} @{scale}: only {room}px left for the title")


@pytest.mark.parametrize("column", COLUMNS)
def test_a_button_holds_its_label(column):
    browser = FakeBrowser(1.0)
    placed = rects(1.0, column)
    for name, label, _tip, _destructive in browser._GS_HEADER_BUTTONS[column]:
        width = _text_wh(label, "xs")[0]
        assert width <= placed[name].w, f"{label!r} does not fit its button"


def test_a_button_grows_with_the_font():
    small = rects(1.0, 2)["dup"]
    large = rects(1.5, 2)["dup"]
    assert large.w > small.w and large.h > small.h


@pytest.mark.parametrize("column", COLUMNS)
def test_the_destructive_button_is_set_apart(column):
    """A wider gap before the delete: it is next to buttons that only build."""
    placed = rects(1.0, column)
    names = [n for n, *_ in FakeBrowser._GS_HEADER_BUTTONS[column]]
    delete = placed["delete"]
    right_neighbour = names[names.index("delete") - 1]
    ordinary = [placed[n] for n in names if n not in ("delete", right_neighbour)]
    gap_to_delete = placed[right_neighbour].left - delete.right
    ordinary_gaps = [abs(a.left - b.right) for a, b in zip(ordinary, ordinary[1:])]
    if ordinary_gaps:
        assert gap_to_delete > min(ordinary_gaps)


@pytest.mark.parametrize("column", COLUMNS)
def test_every_button_has_a_tooltip_in_every_language(column):
    strings = {lang: json.loads(
        (ROOT / "engine" / "assets" / "strings" / f"{lang}.json")
        .read_text(encoding="utf-8")) for lang in LANGS}
    for _name, _label, tip_key, _destructive in FakeBrowser._GS_HEADER_BUTTONS[column]:
        for lang in LANGS:
            assert tip_key in strings[lang], f"{lang} has no {tip_key}"


def test_every_declared_button_has_an_action():
    """A button the dispatcher does not know does nothing when clicked."""
    import inspect

    source = inspect.getsource(GameSelectMixin._gs_header_action)
    for column in COLUMNS:
        for name, *_ in GameSelectMixin._GS_HEADER_BUTTONS[column]:
            assert f'"{name}"' in source, f"{name} has no action"
