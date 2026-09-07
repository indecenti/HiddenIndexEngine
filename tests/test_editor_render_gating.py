"""
tests/test_editor_render_gating.py

Idle cost of the editor: the text cache of editor/ui/draw.py, the memoized
catalog view of RenderPanelsMixin and the frame gating of LevelEditor.run().
Fake hosts on the single mixin: no full editor.
"""

from __future__ import annotations

import os
import time

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pytest

pygame = pytest.importorskip("pygame")

from editor import constants as C
from editor.mixins.render_panels import RenderPanelsMixin
from editor.ui import draw


@pytest.fixture(scope="module", autouse=True)
def _pygame_init():
    pygame.init()
    pygame.display.set_mode((64, 64))
    draw._init_fonts(1.0)
    yield
    pygame.quit()


@pytest.fixture(autouse=True)
def _clean_caches():
    draw.clear_text_cache()
    draw.clear_anim_request()
    yield
    draw.clear_text_cache()
    draw.clear_anim_request()


# -----------------------------------------------------------------------------
# TEXT CACHE
# -----------------------------------------------------------------------------

def test_same_text_is_rendered_once():
    """Identical text, font and color give back the very same surface."""
    a = draw._txt("Objects", "sm", (200, 200, 200))
    b = draw._txt("Objects", "sm", (200, 200, 200))
    assert a is b
    assert len(draw._TEXT_CACHE) == 1


def test_color_font_and_content_are_part_of_the_key():
    base = draw._txt("Objects", "sm", (200, 200, 200))
    assert draw._txt("Objects", "sm", (10, 10, 10)) is not base
    assert draw._txt("Objects", "md", (200, 200, 200)) is not base
    assert draw._txt("Effects", "sm", (200, 200, 200)) is not base
    assert len(draw._TEXT_CACHE) == 4


def test_cache_evicts_the_oldest_entries_first():
    for i in range(C.TEXT_CACHE_MAX + 10):
        draw._txt(f"row {i}", "sm", (1, 2, 3))
    assert len(draw._TEXT_CACHE) == C.TEXT_CACHE_MAX
    # The first rows are gone, the last ones are still there.
    assert ("row 0", "sm", (1, 2, 3)) not in draw._TEXT_CACHE
    last = C.TEXT_CACHE_MAX + 9
    assert (f"row {last}", "sm", (1, 2, 3)) in draw._TEXT_CACHE


def test_changing_the_fonts_drops_the_cache():
    draw._txt("Objects", "sm", (200, 200, 200))
    draw._text_wh("Objects", "sm")
    assert draw._TEXT_CACHE and draw._SIZE_CACHE
    try:
        draw._init_fonts(1.25)
        assert not draw._TEXT_CACHE
        assert not draw._SIZE_CACHE
    finally:
        draw._init_fonts(1.0)


def test_truncated_text_still_truncates_and_is_cached():
    surf = pygame.Surface((200, 40))
    long_text = "a very long object label that cannot fit"
    full = draw._draw_text(surf, long_text, "sm", (200, 200, 200), 0, 0)
    clipped = draw._draw_text(surf, long_text, "sm", (200, 200, 200), 0, 0, max_w=60)
    assert clipped <= 60 < full
    key = (long_text, "sm", (200, 200, 200), 60)
    assert key in draw._TEXT_CACHE
    # A second call reuses the cached surface instead of measuring again.
    assert draw._draw_text(surf, long_text, "sm", (200, 200, 200), 0, 0, max_w=60) == clipped


def test_text_metrics_are_cached():
    first = draw._text_wh("Objects", "sm")
    assert draw._text_wh("Objects", "sm") == first
    assert len(draw._SIZE_CACHE) == 1


# -----------------------------------------------------------------------------
# ANIMATION REQUEST
# -----------------------------------------------------------------------------

def test_animation_request_round_trip():
    assert not draw.anim_requested()
    draw.request_anim_frame()
    assert draw.anim_requested()
    draw.clear_anim_request()
    assert not draw.anim_requested()


def test_a_focused_field_asks_for_another_frame():
    """The glow ring pulses with time, so it needs a frame after this one."""
    surf = pygame.Surface((300, 60))
    rect = pygame.Rect(0, 0, 200, 30)

    draw._input_box(surf, rect, "text", focused=False)
    assert not draw.anim_requested()

    draw._input_box(surf, rect, "text", focused=True)
    assert draw.anim_requested()


# -----------------------------------------------------------------------------
# FRAME GATING
# -----------------------------------------------------------------------------

class FakeFrameHost:
    """Host exposing only what LevelEditor._frame_needed reads."""

    def __init__(self):
        from editor.editor_base import LevelEditor
        self._frame_needed = LevelEditor._frame_needed.__get__(self)
        self._needs_redraw = False
        self._anim_active = False
        self._loading = False
        self.status_until = 0
        self._last_frame_t = time.time()


def test_an_idle_editor_skips_the_frame():
    assert FakeFrameHost()._frame_needed() is False


@pytest.mark.parametrize("field, value", [
    ("_needs_redraw", True),        # input arrived
    ("_anim_active", True),         # the last frame drew something animated
    ("_loading", True),             # blocking operation in progress
    ("status_until", 1.0),          # the status message expires on its own
])
def test_every_reason_to_draw_forces_the_frame(field, value):
    host = FakeFrameHost()
    setattr(host, field, value)
    assert host._frame_needed() is True


@pytest.mark.parametrize("flag", ["_scatter_busy", "_img_editor_busy"])
def test_a_running_background_job_keeps_drawing(flag):
    host = FakeFrameHost()
    setattr(host, flag, True)
    assert host._frame_needed() is True


class FakeEventHost:
    """Host exposing only what InputHandlersMixin._handle_events reads."""

    def __init__(self):
        from editor.mixins.input_handlers import InputHandlersMixin
        self._handle_events = InputHandlersMixin._handle_events.__get__(self)
        self.modal_stack = []
        self._img_editor_active = False
        self._needs_redraw = False


def test_any_event_asks_for_a_frame():
    """Gating must never swallow the repaint of an uncovered window."""
    host = FakeEventHost()
    pygame.event.clear()
    host._handle_events()
    assert host._needs_redraw is False       # empty queue, nothing to draw

    # WINDOWEXPOSED is what the OS sends when the window comes back in front.
    pygame.event.post(pygame.event.Event(pygame.WINDOWEXPOSED))
    host._handle_events()
    assert host._needs_redraw is True
    pygame.event.clear()


def test_the_heartbeat_draws_an_idle_editor_anyway():
    """A worker thread changes state without events: never stay dark for long."""
    host = FakeFrameHost()
    host._last_frame_t = time.time() - C.IDLE_HEARTBEAT_S - 0.01
    assert host._frame_needed() is True


# -----------------------------------------------------------------------------
# CATALOG VIEW MEMOIZATION
# -----------------------------------------------------------------------------

CATALOG = [
    {"id": "lampada", "style": "real", "tags": ["casa", "luce"], "label_key": "obj_lampada"},
    {"id": "citta_alta", "style": "real", "tags": ["citta"], "label_key": "obj_citta_alta"},
    {"id": "gatto", "style": "cartoon", "tags": ["animali", "casa"], "label_key": "obj_gatto"},
    {"id": "albero", "style": "cartoon", "tags": ["natura"], "label_key": "obj_albero"},
]

# Accented label of the "citta" tag: the search has to match it typed flat.
CITTA_LABEL = "Città"


class FakeCatalogHost(RenderPanelsMixin):
    """Host minimo per _catalog_view: catalogo, stringhe e revisione."""

    LANGS = ["en", "it"]

    def __init__(self):
        self.catalog = [dict(c) for c in CATALOG]
        self.current_lang = "en"
        self._catalog_rev = 0
        self._lang_data = {"en": {"obj_lampada": "Lamp"}, "it": {"obj_lampada": "Lampada"}}
        self.translations = {"tag_citta": CITTA_LABEL, "tag_casa": "Home"}
        self.tr_calls = 0

    def _TR(self, key, default=None):
        self.tr_calls += 1
        return self.translations.get(key, default if default is not None else key)

    def _bump_catalog_rev(self):
        self._catalog_rev += 1


def test_the_view_filters_by_style_and_counts_every_style():
    host = FakeCatalogHost()
    counts, _tags, filtered = host._catalog_view("cartoon", set(), "", "")
    assert counts["tutti"] == 4
    assert counts["real"] == 2 and counts["cartoon"] == 2
    assert [c["id"] for c in filtered] == ["gatto", "albero"]


def test_the_view_filters_by_tag_and_by_query():
    host = FakeCatalogHost()
    _c, _t, by_tag = host._catalog_view("tutti", {"casa"}, "", "")
    assert {c["id"] for c in by_tag} == {"lampada", "gatto"}

    _c, _t, by_id = host._catalog_view("tutti", set(), "albe", "")
    assert [c["id"] for c in by_id] == ["albero"]

    # The label lives only in _lang_data, the search has to reach it.
    _c, _t, by_label = host._catalog_view("tutti", set(), "lampada", "")
    assert [c["id"] for c in by_label] == ["lampada"]


def test_the_query_ignores_the_accents_of_a_translated_tag():
    host = FakeCatalogHost()
    _c, _t, filtered = host._catalog_view("tutti", set(), "citta", "")
    assert [c["id"] for c in filtered] == ["citta_alta"]


def test_active_tags_come_first_in_the_chips():
    host = FakeCatalogHost()
    _c, tags, _f = host._catalog_view("cartoon", {"natura"}, "", "")
    assert tags[0][0] == "natura"


def test_the_same_filters_are_computed_once():
    host = FakeCatalogHost()
    first = host._catalog_view("real", set(), "", "")
    host.tr_calls = 0
    second = host._catalog_view("real", set(), "", "")
    assert second is first          # identical object, nothing recomputed
    assert host.tr_calls == 0


def test_a_catalog_change_invalidates_the_view():
    host = FakeCatalogHost()
    before = host._catalog_view("tutti", set(), "", "")
    host.catalog.append(
        {"id": "nuovo", "style": "real", "tags": ["casa"], "label_key": "obj_nuovo"})
    host._bump_catalog_rev()
    after = host._catalog_view("tutti", set(), "", "")
    assert after is not before
    assert "nuovo" in {c["id"] for c in after[2]}


def test_the_view_cache_is_bounded():
    host = FakeCatalogHost()
    for i in range(C.CATALOG_VIEW_CACHE_MAX + 5):
        host._catalog_view("tutti", set(), f"q{i}", "")
    assert len(host._catalog_view_cache) == C.CATALOG_VIEW_CACHE_MAX
