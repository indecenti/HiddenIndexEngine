"""
tests/test_editor_outline.py

Scene outline (editor/mixins/outline.py):

  1. the rows follow search and filters, and keep the index of the object in
     scene_data["objects"] (what selection, canvas and properties speak);
  2. selection: plain click, ctrl toggle, shift range, double click frames;
  3. the eye/lock buttons act on the selection when the row belongs to it;
  4. the list follows a selection made elsewhere (canvas, undo, object ops);
  5. _reveal_selection pans without ever changing the zoom.

Host fake on the mixins only: no editor, no window.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pytest

pygame = pytest.importorskip("pygame")

from editor.constants import OUTLINE_ROW_H, STATUS_H, TOP_BAR_H
from editor.mixins.outline import OutlineMixin
from editor.mixins.viewport import ViewportMixin


@pytest.fixture(scope="module", autouse=True)
def _pygame_init():
    pygame.init()
    pygame.display.set_mode((64, 64))
    yield
    pygame.quit()


def _obj(cat_id, x=100, y=100, layer="objects_mid", goal=False, minigame=None):
    o = {"catalog_id": cat_id, "x": x, "y": y, "detection_type": "circle",
         "radius": 20, "layer": layer, "is_goal": goal}
    if minigame:
        o["minigame_trigger"] = minigame
    return o


class FakeOutline(OutlineMixin, ViewportMixin):
    """Minimal host for the outline and the viewport helpers it calls."""

    def __init__(self, objects=None, screen_h=720):
        self.screen = pygame.Surface((1280, screen_h))
        self.screen_size = (1280, screen_h)
        self.scene_data = {"objects": list(objects or [])}
        self.catalog = []
        self.game_path = None
        self.active_layer = "objects_mid"
        self.panel_l_w = 360
        self.panel_r_w = 260
        self.panels_visible = True
        self.r_tab = "layers"
        self.selected_idx = None
        self.selected_indices = []
        self.sel_effect_idx = None
        self.scene_dirty = False
        self.outline_search = ""
        self.outline_searching = False
        self.outline_scroll = 0
        self.outline_filter_goal = False
        self.outline_filter_layer = False
        self._outline_anchor = None
        self._outline_last_sel = None
        self.zoom = 1.0
        self.origin_x = 0.0
        self.origin_y = 0.0
        self.bg_surf = None
        self._layout_init = True
        self.undo_labels: list[str] = []
        self.statuses: list[str] = []
        self.zoomed = 0
        self.revealed = 0
        self.dirty = 0

    # -- host stubs ----------------------------------------------------------
    def _TR(self, key, default=None, *args):
        return default if default is not None else key

    def _get_friendly_name(self, obj):
        return {"ca_key_ring": "Key ring", "ca_apple_red": "Red apple"}.get(
            obj.get("catalog_id", ""), obj.get("catalog_id", "?"))

    def _push_undo(self, label="", coalesce_key=None):
        self.undo_labels.append(label)

    def _status(self, msg, color=None, duration=0):
        self.statuses.append(str(msg))

    def _mark_dirty(self):
        self.dirty += 1

    def _load_img(self, path, size):
        return None

    def _get_obj_bbox(self, obj):
        r = obj.get("radius", 20)
        return (obj["x"] - r, obj["y"] - r, obj["x"] + r, obj["y"] + r)

    def _zoom_to_selection(self):
        self.zoomed += 1

    def _load_editor_settings(self):
        return {}


class RevealHost(FakeOutline):
    """Same host, but with the real _reveal_selection under test."""

    def _reveal_selection(self, margin: int = 40):
        return ViewportMixin._reveal_selection(self, margin)


def _reveal_counting(host):
    host._reveal_selection = lambda margin=40: setattr(host, "revealed", host.revealed + 1)
    return host


def _mods(monkeypatch, value):
    monkeypatch.setattr(pygame.key, "get_mods", lambda: value)


# ── 1. Rows, search and filters ─────────────────────────────────────────────

def _sample_host():
    return _reveal_counting(FakeOutline([
        _obj("ca_key_ring", 100, 100),
        _obj("ca_apple_red", 200, 200, goal=True),
        _obj("ca_lamp", 300, 300, layer="objects_high"),
        _obj("ca_door", 400, 400, minigame="sudoku"),
    ]))


def test_rows_keep_the_scene_index():
    ed = _sample_host()
    assert [i for i, _o in ed._outline_rows()] == [0, 1, 2, 3]


def test_search_matches_id_name_and_layer():
    ed = _sample_host()
    ed.outline_search = "apple"                 # catalog_id
    assert [i for i, _o in ed._outline_rows()] == [1]
    ed.outline_search = "key ring"              # friendly name
    assert [i for i, _o in ed._outline_rows()] == [0]
    ed.outline_search = "objects_high"          # layer
    assert [i for i, _o in ed._outline_rows()] == [2]
    ed.outline_search = "sudoku"                # minigame trigger
    assert [i for i, _o in ed._outline_rows()] == [3]
    ed.outline_search = "nothing here"
    assert ed._outline_rows() == []


def test_goal_and_layer_filters():
    ed = _sample_host()
    ed.outline_filter_goal = True
    assert [i for i, _o in ed._outline_rows()] == [1]
    ed.outline_filter_goal = False
    ed.outline_filter_layer = True              # active_layer = objects_mid
    assert [i for i, _o in ed._outline_rows()] == [0, 1, 3]


# ── 2. Selection ────────────────────────────────────────────────────────────

def test_click_selects_single_and_reveals(monkeypatch):
    ed = _sample_host()
    _mods(monkeypatch, 0)
    rows = ed._outline_rows()
    ed._outline_select(2, 2, rows)
    assert ed.selected_idx == 2 and ed.selected_indices == [2]
    assert ed.r_tab == "props"                  # the inspector follows the pick
    assert ed.revealed == 1 and ed.zoomed == 0  # reveal pans, it does not zoom


def test_ctrl_click_toggles(monkeypatch):
    ed = _sample_host()
    rows = ed._outline_rows()
    _mods(monkeypatch, 0)
    ed._outline_select(0, 0, rows)
    _mods(monkeypatch, pygame.KMOD_CTRL)
    ed._outline_select(2, 2, rows)
    assert ed.selected_indices == [0, 2] and ed.selected_idx == 2
    ed._outline_select(0, 0, rows)              # same row again: removed
    assert ed.selected_indices == [2] and ed.selected_idx == 2


def test_shift_click_selects_the_range(monkeypatch):
    ed = _sample_host()
    rows = ed._outline_rows()
    _mods(monkeypatch, 0)
    ed._outline_select(1, 1, rows)              # anchor
    _mods(monkeypatch, pygame.KMOD_SHIFT)
    ed._outline_select(3, 3, rows)
    assert ed.selected_indices == [1, 2, 3] and ed.selected_idx == 3


def test_shift_range_uses_the_filtered_rows(monkeypatch):
    """With a filter on, the range must span what is listed, not the scene."""
    ed = _sample_host()
    ed.outline_filter_layer = True              # rows: 0, 1, 3
    rows = ed._outline_rows()
    _mods(monkeypatch, 0)
    ed._outline_select(0, 0, rows)
    _mods(monkeypatch, pygame.KMOD_SHIFT)
    ed._outline_select(2, 3, rows)
    assert ed.selected_indices == [0, 1, 3]


def test_double_click_frames_the_object(monkeypatch):
    ed = _sample_host()
    rows = ed._outline_rows()
    _mods(monkeypatch, 0)
    ed._outline_select(1, 1, rows)
    ed._outline_select(1, 1, rows)              # within DOUBLE_CLICK_S
    assert ed.zoomed == 1 and ed.revealed == 1

    ed.zoomed = 0
    ed._outline_last_click_t = time.time() - 5   # too slow: not a double click
    ed._outline_select(1, 1, rows)
    assert ed.zoomed == 0


# ── 3. Eye / lock ───────────────────────────────────────────────────────────

def test_flag_toggle_applies_to_the_whole_selection():
    ed = _sample_host()
    ed.selected_indices = [0, 1]
    ed.selected_idx = 1
    ed._outline_toggle_flag(0, "editor_hidden")
    objs = ed.scene_data["objects"]
    assert objs[0]["editor_hidden"] and objs[1]["editor_hidden"]
    assert not objs[2].get("editor_hidden", False)
    assert ed.undo_labels == ["Editor flags"] and ed.scene_dirty
    ed._outline_toggle_flag(0, "editor_hidden")           # toggles back
    assert not objs[0]["editor_hidden"] and not objs[1]["editor_hidden"]


def test_flag_toggle_on_a_row_outside_the_selection():
    ed = _sample_host()
    ed.selected_indices = [0]
    ed.selected_idx = 0
    ed._outline_toggle_flag(3, "editor_locked")
    objs = ed.scene_data["objects"]
    assert objs[3]["editor_locked"] and not objs[0].get("editor_locked", False)


# ── 4. Search box and following the selection ───────────────────────────────

class _Key:
    def __init__(self, key, unicode=""):
        self.key = key
        self.unicode = unicode


def test_search_typing_is_consumed_only_when_focused():
    ed = _sample_host()
    assert ed._outline_key(_Key(pygame.K_a, "a")) is False
    ed.outline_searching = True
    assert ed._outline_key(_Key(pygame.K_a, "A")) is True
    assert ed.outline_search == "a"                        # lower cased
    ed._outline_key(_Key(pygame.K_BACKSPACE))
    assert ed.outline_search == ""
    ed._outline_key(_Key(pygame.K_ESCAPE))
    assert ed.outline_searching is False


def test_the_list_follows_a_selection_made_elsewhere():
    many = [_obj(f"ca_{i}", i * 10, 10) for i in range(200)]
    ed = _reveal_counting(FakeOutline(many, screen_h=400))
    visible = ed._outline_visible_rows(400)
    assert visible < 200

    ed.selected_idx = 150                                  # e.g. picked on canvas
    ed._outline_follow_selection()
    assert ed.outline_scroll <= 150 < ed.outline_scroll + visible

    ed.selected_idx = 3
    ed._outline_follow_selection()
    assert ed.outline_scroll <= 3 < ed.outline_scroll + visible

    ed._outline_follow_selection()                         # idle: no jitter
    scroll = ed.outline_scroll
    ed._outline_follow_selection()
    assert ed.outline_scroll == scroll


def test_scroll_is_clamped_to_the_row_count():
    ed = _reveal_counting(FakeOutline([_obj(f"ca_{i}") for i in range(10)], screen_h=720))
    ed._outline_scroll_by(-50)                             # wheel down, hard
    assert ed.outline_scroll == ed._outline_max_scroll(720)
    ed._outline_scroll_by(50)
    assert ed.outline_scroll == 0


# ── 5. Reveal never touches the zoom ────────────────────────────────────────

def test_reveal_pans_only_when_needed_and_keeps_the_zoom():
    ed = RevealHost([_obj("ca_key_ring", 100, 100), _obj("ca_far", 9000, 9000)])
    ed.zoom = 1.0
    ed.origin_x, ed.origin_y = 400.0, 40.0                 # canvas starts at x=360

    ed.selected_idx = 0                                    # on screen already
    before = (ed.origin_x, ed.origin_y, ed.zoom)
    ed._reveal_selection()
    assert (ed.origin_x, ed.origin_y, ed.zoom) == before

    ed.selected_idx = 1                                    # far outside
    ed._reveal_selection()
    assert ed.zoom == 1.0, "reveal must never change the zoom"
    cr = ed._canvas_rect()
    sx, sy = ed._r2s(9000, 9000)
    assert cr.collidepoint(sx, sy), "the object must end up inside the canvas"


def test_row_geometry_fits_the_panel():
    """The header must leave room for at least one row on the smallest window."""
    ed = _sample_host()
    top = ed._outline_list_top()
    assert top > TOP_BAR_H + 32
    assert ed._outline_visible_rows(720) >= 1
    assert (720 - STATUS_H - top) // OUTLINE_ROW_H == ed._outline_visible_rows(720)
