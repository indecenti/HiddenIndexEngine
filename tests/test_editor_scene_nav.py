"""
tests/test_editor_scene_nav.py

Previous / next scene buttons of the editor status bar (and Ctrl+PageUp /
Ctrl+PageDown).

  - the neighbours follow the campaign order across levels: after the last
    scene of a level comes the first scene of the next one;
  - a button is drawn only when its scene exists, next to its anchor (Previous
    right after Selector, Next right after Play);
  - the row of buttons never overlaps itself nor the status message, in the
    longest language at the largest UI scale.
"""

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pytest

pygame = pytest.importorskip("pygame")

from editor.core.io import scene_neighbors
from editor.mixins.render_topbar import RenderTopbarMixin
from editor.ui.draw import _init_fonts
from engine.language_manager import LanguageManager

ROOT = Path("games") / "G" / "levels"
LEVELS = [
    {"id": "l1", "scenes": [ROOT / "l1" / "a", ROOT / "l1" / "b"]},
    {"id": "l2", "scenes": [ROOT / "l2" / "c"]},
]


@pytest.fixture(scope="module", autouse=True)
def _pygame_init():
    pygame.init()
    pygame.display.set_mode((64, 64))
    _init_fonts(1.0)
    yield
    _init_fonts(1.0)
    pygame.quit()


# -- neighbours -----------------------------------------------------------------

def test_the_middle_scene_has_both_neighbours():
    prev_s, next_s = scene_neighbors(LEVELS, ROOT / "l1" / "b")
    assert prev_s.name == "a" and next_s.name == "c"


def test_the_order_runs_across_levels():
    prev_s, _next = scene_neighbors(LEVELS, ROOT / "l2" / "c")
    assert prev_s.name == "b"


def test_the_ends_have_one_side_only():
    assert scene_neighbors(LEVELS, ROOT / "l1" / "a")[0] is None
    assert scene_neighbors(LEVELS, ROOT / "l2" / "c")[1] is None


def test_a_scene_json_path_is_the_same_scene():
    assert scene_neighbors(LEVELS, ROOT / "l1" / "a" / "scene.json")[1].name == "b"


def test_a_scene_outside_every_level_has_no_neighbours():
    assert scene_neighbors(LEVELS, Path("elsewhere")) == (None, None)
    assert scene_neighbors([], ROOT / "l1" / "a") == (None, None)
    assert scene_neighbors(LEVELS, None) == (None, None)


# -- status bar -------------------------------------------------------------------

class Bar(RenderTopbarMixin):
    def __init__(self, scene, lang="en", size=(1280, 720), scale=1.0, msg=""):
        self.screen = pygame.Surface(size)
        self.screen_size = size
        self.ui_scale = scale
        self.state = "edit"
        self.game_name = "Malonno_Survivors"
        self.levels = LEVELS
        self.scene_path = ROOT / scene[0] / scene[1]
        self.scene_dirty = False
        self.undo_stack = []
        self.status_col = (255, 200, 80)
        self.active_tooltip = ""
        self.lang_manager = LanguageManager()
        self.lang_manager.load_for_game("engine", lang)
        self.status_msg = msg
        _init_fonts(scale)

    def _TR(self, key, *args):
        return self.lang_manager.get(key, args[0] if args else key)

    def draw(self):
        self._r_status(*self.screen_size)
        return self._status_hitboxes


def test_the_first_scene_has_only_next():
    hits = Bar(("l1", "a")).draw()
    assert "prev" not in hits and "next" in hits


def test_the_last_scene_has_only_previous():
    hits = Bar(("l2", "c")).draw()
    assert "prev" in hits and "next" not in hits


def test_previous_follows_the_selector_and_next_follows_play():
    hits = Bar(("l1", "b")).draw()
    order = sorted(hits, key=lambda k: hits[k].x)
    assert order == ["back", "prev", "save", "play", "next"]


@pytest.mark.parametrize("lang", ["en", "it", "de", "fr", "es"])
@pytest.mark.parametrize("scale", [1.0, 1.5])
def test_the_buttons_never_overlap_nor_the_message(lang, scale):
    bar = Bar(("l1", "b"), lang=lang, scale=scale,
              msg="Scene: Sotterranei_Villa_Rosa  (73)")
    hits = bar.draw()
    rects = sorted(hits.values(), key=lambda r: r.x)
    for a, b in zip(rects, rects[1:]):
        assert a.right <= b.left, (lang, scale, a, b)
    msg_left = bar._status_spans["msg"][0]
    assert rects[-1].right < msg_left


def test_the_tooltip_names_the_target_scene():
    bar = Bar(("l1", "b"))
    bar.draw()
    nxt = bar._status_hitboxes["next"]
    pygame.mouse.set_pos(nxt.center)
    bar.active_tooltip = ""
    bar._status_nav_button("next", ROOT / "l2" / "Chiesa_Abbandonata", nxt.x, nxt.y,
                           nxt.h, *nxt.center)
    assert "Chiesa Abbandonata" in bar.active_tooltip
