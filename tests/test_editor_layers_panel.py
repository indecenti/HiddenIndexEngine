"""
tests/test_editor_layers_panel.py

The layers panel: rows, an eye column and a lock column.

The row height and the two icon columns were three constants in the renderer
and the same three constants again in the click handler, all chosen for the
font at UI scale 1.0. Two things followed: at scale 1.5 the "VIS" and "LOCK"
headings were drawn past the right edge of the panel while the icons stayed
24 px wide under a font half again as large, and any change to one copy of the
numbers moved the click away from what the user could see.

The renderer publishes `_layers_hitboxes` and the click handler reads it, so
these tests can check the two are the same thing.
"""

from __future__ import annotations

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pytest

pygame = pytest.importorskip("pygame")

from editor.constants import LANGS, TOP_BAR_H
from editor.mixins.input_handlers import InputHandlersMixin
from editor.mixins.render_panels import RenderPanelsMixin
from editor.ui.draw import _init_fonts, _text_wh
from engine.language_manager import LanguageManager

SCALES = [1.0, 1.25, 1.5]


@pytest.fixture(scope="module", autouse=True)
def _pygame_init():
    pygame.init()
    pygame.display.set_mode((64, 64))
    _init_fonts(1.0)
    yield
    _init_fonts(1.0)
    pygame.quit()


class FakePanel(RenderPanelsMixin, InputHandlersMixin):
    """Host for the layers panel only: no editor, no window."""

    def __init__(self, lang="en", size=(1600, 900), scale=1.0, panel_w=340):
        self.screen = pygame.Surface(size)
        self.screen_size = size
        self.panel_r_w = panel_w
        self.r_tab = "layers"
        self.active_layer = "layer_mid"
        self.selected_idx = 0
        self.sel_effect_idx = None
        self.layer_vis = {}
        self.layer_locked = {}
        self.active_tooltip = ""
        self.scene_data = {"objects": [{"layer": "layer_mid"} for _ in range(5)]}
        self.lang_manager = LanguageManager()
        self.lang_manager.load_for_game("engine", lang)
        self.dirty = False
        _init_fonts(scale)

    def _TR(self, key, *args):
        return self.lang_manager.get(key, args[0] if args else key)

    def _mark_dirty(self):
        self.dirty = True

    def draw(self):
        self._r_layers(self.screen_size[0] - self.panel_r_w, self.screen_size[1])
        return self._layers_hitboxes


CASES = [(lang, scale) for lang in LANGS for scale in SCALES]
IDS = [f"{lang}-{scale}" for lang, scale in CASES]


# -----------------------------------------------------------------------------
# 1. EVERYTHING THE PANEL DRAWS STAYS IN THE PANEL
# -----------------------------------------------------------------------------

@pytest.mark.parametrize("lang,scale", CASES, ids=IDS)
def test_the_icons_stay_inside_the_panel(lang, scale):
    panel = FakePanel(lang, scale=scale)
    hits = panel.draw()
    left = panel.screen_size[0] - panel.panel_r_w
    for kind in ("eye", "lock"):
        for lid, rect in hits[kind].items():
            assert rect.left >= left and rect.right <= panel.screen_size[0], (
                f"{lang} @{scale}: the {kind} of {lid} is outside the panel")


@pytest.mark.parametrize("lang,scale", CASES, ids=IDS)
def test_the_two_headings_fit_over_their_columns(lang, scale):
    """"VIS" and "LOCK" used to be placed 82 and 52 px from the right edge,
    which is a measurement of the English words at scale 1.0."""
    panel = FakePanel(lang, scale=scale)
    panel.draw()
    eye_x, lock_x, icon = panel._layers_columns()
    spans = []
    for key, default, column in (("layers_label_vis", "VIS", eye_x),
                                 ("layers_label_lock", "LOCK", lock_x)):
        label = panel._TR(key, default)
        width = _text_wh(label, "sm")[0]
        start = column + icon // 2 - width // 2
        assert start >= 0, f"{lang} @{scale}: {label!r} starts left of the panel"
        assert start + width <= panel.panel_r_w, (
            f"{lang} @{scale}: {label!r} runs past the right edge")
        spans.append((label, start, start + width))
    (first, _, first_end), (second, second_start, _) = spans
    assert first_end <= second_start, (
        f"{lang} @{scale}: {first!r} is written over {second!r}")


@pytest.mark.parametrize("lang,scale", CASES, ids=IDS)
def test_the_eye_and_the_lock_do_not_overlap(lang, scale):
    panel = FakePanel(lang, scale=scale)
    hits = panel.draw()
    for lid, eye in hits["eye"].items():
        lock = hits["lock"].get(lid)
        if lock is not None:
            assert not eye.colliderect(lock), f"{lang} @{scale}: {lid}"


@pytest.mark.parametrize("lang,scale", CASES, ids=IDS)
def test_the_rows_are_a_stack_that_never_overlaps(lang, scale):
    panel = FakePanel(lang, scale=scale)
    rows = [row for _, row in panel.draw()["rows"]]
    assert len(rows) >= 5
    for upper, lower in zip(rows, rows[1:]):
        assert upper.bottom <= lower.top, f"{lang} @{scale}: rows overlap"


def test_a_row_grows_with_the_font():
    small = FakePanel(scale=1.0).draw()["rows"][0][1]
    large = FakePanel(scale=1.5).draw()["rows"][0][1]
    assert large.height > small.height


# -----------------------------------------------------------------------------
# 2. THE CLICK LANDS ON WHAT WAS DRAWN
# -----------------------------------------------------------------------------

def _click(panel, rect):
    """Click the centre of a published rect, in the panel's own coordinates."""
    left = panel.screen_size[0] - panel.panel_r_w
    panel._layers_click(rect.centerx - left, rect.centery - TOP_BAR_H)


@pytest.mark.parametrize("scale", SCALES)
def test_clicking_the_eye_toggles_that_layer(scale):
    panel = FakePanel(scale=scale)
    hits = panel.draw()
    lid, eye = next(iter(hits["eye"].items()))
    assert panel.layer_vis.get(lid, True) is True
    _click(panel, eye)
    assert panel.layer_vis[lid] is False, f"@{scale}: the eye missed its icon"


@pytest.mark.parametrize("scale", SCALES)
def test_clicking_the_lock_toggles_that_layer(scale):
    panel = FakePanel(scale=scale)
    hits = panel.draw()
    lid, lock = next(iter(hits["lock"].items()))
    _click(panel, lock)
    assert panel.layer_locked[lid] is True, f"@{scale}: the lock missed its icon"


@pytest.mark.parametrize("scale", SCALES)
def test_clicking_a_row_selects_that_layer(scale):
    panel = FakePanel(scale=scale)
    rows = panel.draw()["rows"]
    lid, row = rows[-1]
    _click(panel, row)
    assert panel.active_layer == lid, f"@{scale}: the click selected {panel.active_layer}"


def test_every_row_is_reachable():
    """A stack of rows where one is unreachable is the usual symptom of the
    click walking down its own copy of the geometry."""
    panel = FakePanel(scale=1.5)
    rows = panel.draw()["rows"]
    for lid, row in rows:
        panel.active_layer = None
        panel.selected_idx = 0
        _click(panel, row)
        assert panel.active_layer == lid, f"row {lid} is not reachable"


def test_a_click_before_the_first_render_does_nothing():
    """The panel can be clicked in the frame it is opened."""
    panel = FakePanel()
    panel._layers_click(10, 100)      # must not raise
