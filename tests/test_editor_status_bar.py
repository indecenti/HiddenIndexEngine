"""
tests/test_editor_status_bar.py

The bottom bar of the editor: three text runs on one line.

Left of it are the buttons, then the status message; on the right the
game/scene/undo block; centred between them the "F1 = shortcuts" pointer. The
three were positioned independently, and each guard measured the wrong thing:
the hint asked whether there was room after the *start* of the status message,
so "Scena: Formis (73 oggetti)" in Italian at UI scale 1.25 was written over by
it, and the info block on the right had no width limit at all.

The renderer now publishes the span it drew for each run and these tests read
them back, which is the only way to check three runs that share a line.
"""

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pytest

pygame = pytest.importorskip("pygame")

from editor.constants import LANGS
from editor.mixins.render_topbar import RenderTopbarMixin
from editor.ui.draw import _init_fonts
from engine.language_manager import LanguageManager


@pytest.fixture(scope="module", autouse=True)
def _pygame_init():
    pygame.init()
    pygame.display.set_mode((64, 64))
    _init_fonts(1.0)
    yield
    _init_fonts(1.0)
    pygame.quit()


class FakeBar(RenderTopbarMixin):
    """Host for the status bar only: no editor, no window."""

    def __init__(self, lang="en", size=(1280, 720), scale=1.0,
                 game="Malonno_Survivors", scene="Formis", msg=""):
        self.screen = pygame.Surface(size)
        self.screen_size = size
        self.ui_scale = scale
        self.state = "edit"
        self.game_name = game
        self.scene_path = Path(f"games/{game}/levels/l1/{scene}/scene.json")
        self.scene_dirty = False
        self.undo_stack = []
        self.status_col = (255, 200, 80)
        self.active_tooltip = ""
        self.lang_manager = LanguageManager()
        self.lang_manager.load_for_game("engine", lang)
        self.status_msg = msg or self._TR("tb_scene") + f" {scene}  (73)"
        _init_fonts(scale)

    def _TR(self, key, *args):
        return self.lang_manager.get(key, args[0] if args else key)

    def _ui_scale(self):
        return self.ui_scale

    def draw(self):
        w, h = self.screen_size
        self._r_status(w, h)
        return self._status_spans


def _overlaps(a, b):
    return a is not None and b is not None and a[0] < b[1] and b[0] < a[1]


# ─────────────────────────────────────────────────────────────────────────────
# 1. THE THREE RUNS NEVER WRITE OVER EACH OTHER
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("lang", LANGS)
@pytest.mark.parametrize("scale", [1.0, 1.25, 1.5])
@pytest.mark.parametrize("size", [(1280, 720), (1600, 900), (1920, 1080)])
def test_the_bar_never_writes_one_run_over_another(lang, scale, size):
    spans = FakeBar(lang=lang, size=size, scale=scale).draw()
    msg, info, hint = spans.get("msg"), spans.get("info"), spans.get("hint")
    assert not _overlaps(msg, info), f"status message over the info block: {spans}"
    assert not _overlaps(msg, hint), f"status message over the hint: {spans}"
    assert not _overlaps(hint, info), f"hint over the info block: {spans}"


def test_a_long_status_message_takes_the_hint_off_the_bar():
    """The message wins: it is what the editor is telling the user right now."""
    spans = FakeBar(msg="Scene saved to games/Malonno_Survivors/levels/one/"
                        "Formis/scene.json with 73 objects").draw()
    assert "hint" not in spans, "the hint must give way, not overlap"
    assert not _overlaps(spans["msg"], spans["info"])


def test_a_long_project_name_stays_inside_the_bar():
    spans = FakeBar(game="A" * 80, scene="B" * 40, size=(1280, 720)).draw()
    assert spans["info"][1] <= 1280, "the info block ran off the right edge"
    assert not _overlaps(spans["msg"], spans["info"])


def test_the_hint_is_shown_when_there_is_room_for_it():
    """Suppressing it always would also pass the overlap tests."""
    spans = FakeBar(msg="", size=(1920, 1080)).draw()
    assert "hint" in spans


# ─────────────────────────────────────────────────────────────────────────────
# 2. THE BUTTONS ARE AS WIDE AS THEIR LABELS
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("lang", LANGS)
def test_the_bar_buttons_do_not_overlap_in_any_language(lang):
    bar = FakeBar(lang=lang, scale=1.5)
    bar.draw()
    rects = [bar._status_hitboxes[k] for k in ("back", "save", "play")
             if k in bar._status_hitboxes]
    assert len(rects) == 3
    for left, right in zip(rects, rects[1:]):
        assert left.right <= right.left, f"{lang}: bar buttons overlap"


@pytest.mark.parametrize("lang", LANGS)
def test_the_status_message_starts_after_the_buttons(lang):
    bar = FakeBar(lang=lang, scale=1.5)
    spans = bar.draw()
    assert spans["msg"][0] >= bar._status_hitboxes["play"].right
