"""
tests/test_editor_lang_modal.py

The translation editor: the most complex modal of the editor, and the one whose
whole job is finding what is missing.

Its layout used to be written three times - the wheel handler with module
constants, the renderer with its own locals, the click handler with a third
copy - and the copies already disagreed:

  * the search box was drawn at dy+48 and hit-tested at dy+45, so its top
    three pixels did nothing;
  * the rows were clipped at dh-header-48 while clicks were rejected past
    dh-50, so the last row could be drawn and not clicked.

None of it followed the font either. `_lang_geometry()` is now the only place
the layout is computed, and this pins it, together with the tools the dialog
was missing: per-language completion, a filter for the incomplete keys, and a
name for a key that is created.
"""

from __future__ import annotations

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pytest

pygame = pytest.importorskip("pygame")

from editor.constants import LANGS, UI_SCALE_MAX, UI_SCALE_MIN
from editor.mixins.lang_modal import LangModalMixin
from editor.mixins.lang_translate import LangTranslateMixin
from editor.ui.draw import _init_fonts, _text_wh
from engine.language_manager import LanguageManager

SIZE = (1600, 900)


@pytest.fixture(scope="module", autouse=True)
def _pygame_init():
    pygame.init()
    pygame.display.set_mode((64, 64))
    _init_fonts(1.0)
    yield
    _init_fonts(1.0)
    pygame.quit()


class FakeLang(LangModalMixin, LangTranslateMixin):
    """The translation editor without an editor behind it."""

    def __init__(self, data=None, context="global", size=SIZE):
        self.screen = pygame.Surface(size)
        self.LANGS = list(LANGS)
        self.lang_manager = LanguageManager()
        self.lang_manager.load_for_game("engine", "en")
        self._lang_context = context
        self._lang_data = data or {
            "en": {"a": "Alpha", "b": "Beta", "c": ""},
            "it": {"a": "Alfa", "b": "", "c": ""},
            "es": {"a": "Alfa", "b": "Beta", "c": ""},
            "fr": {"a": "Alpha", "b": "Beta", "c": ""},
            "de": {"a": "Alpha", "b": "Beta", "c": ""},
        }
        self._lang_keys = sorted({k for d in self._lang_data.values() for k in d})
        self._lang_filtered_keys = self._lang_keys[:]
        self._lang_search = ""
        self._lang_search_active = False
        self._lang_only_missing = False
        self._lang_naming = None
        self._lang_name_buf = ""
        self._lang_new_keys: set = set()
        self._lang_sel = None
        self._lang_buf = ""
        self._lang_cursor = 0
        self._lang_scroll = 0
        self._lang_dirty = False
        self._lang_modal = True
        self._lang_footer_hitboxes: dict = {}
        self._lang_tr_init()
        self.status: list = []
        self.saved = False
        self.closed = False

    def _TR(self, key, *args):
        return self.lang_manager.get(key, *args)

    def _status(self, message, colour=None, seconds=0):
        self.status.append(message)

    def _bump_catalog_rev(self):
        pass

    def _lang_save(self):
        self.saved = True

    def _lang_try_close(self):
        self.closed = True
        return True

    def _mark_dirty(self):
        pass


def _many_keys(n=200):
    data = {lang: {f"k{i:03d}": f"{lang}{i}" for i in range(n)} for lang in LANGS}
    return FakeLang(data)


# ─────────────────────────────────────────────────────────────────────────────
# 1. GEOMETRIA UNICA
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("scale", (UI_SCALE_MIN, 1.0, UI_SCALE_MAX))
def test_the_table_fits_inside_the_dialog(scale):
    _init_fonts(scale)
    try:
        geo = _many_keys()._lang_geometry(*SIZE)
        assert geo["box"].contains(geo["content"])
        assert geo["box"].contains(geo["search"])
        assert geo["box"].contains(geo["filter"])
        assert geo["content"].bottom <= geo["footer_y"]
    finally:
        _init_fonts(1.0)


@pytest.mark.parametrize("scale", (UI_SCALE_MIN, 1.0, UI_SCALE_MAX))
def test_the_rows_that_fit_are_the_rows_that_are_counted(scale):
    _init_fonts(scale)
    try:
        geo = _many_keys()._lang_geometry(*SIZE)
        assert geo["visible_rows"] * geo["row_h"] <= geo["content"].h
        assert (geo["visible_rows"] + 1) * geo["row_h"] > geo["content"].h
    finally:
        _init_fonts(1.0)


def test_the_row_height_follows_the_font():
    host = _many_keys()
    _init_fonts(UI_SCALE_MIN)
    small = host._lang_geometry(*SIZE)["row_h"]
    _init_fonts(UI_SCALE_MAX)
    large = host._lang_geometry(*SIZE)["row_h"]
    _init_fonts(1.0)
    assert large > small


def test_the_key_column_follows_the_keys():
    short = FakeLang()._lang_geometry(*SIZE)["key_col"]
    data = {lang: {"a_very_long_translation_key_name_indeed_x" * 2: "v"}
            for lang in LANGS}
    long = FakeLang(data)._lang_geometry(*SIZE)["key_col"]
    assert long > short


def test_the_language_columns_share_what_is_left():
    geo = FakeLang()._lang_geometry(*SIZE)
    assert (geo["key_col"] + geo["lang_w"] * len(LANGS)
            <= geo["content"].w + len(LANGS))


def test_max_scroll_leaves_no_row_unreachable():
    host = _many_keys(200)
    geo = host._lang_geometry(*SIZE)
    assert geo["max_scroll"] == 200 - geo["visible_rows"]


def test_the_wheel_is_clamped_to_the_table():
    host = _many_keys(200)
    top = host._lang_geometry(*SIZE)["max_scroll"]
    host._lang_modal_wheel(-1000)
    assert host._lang_scroll == top
    host._lang_modal_wheel(1000)
    assert host._lang_scroll == 0


def test_the_effect_context_has_its_own_geometry():
    geo = FakeLang(context="fx")._lang_geometry(*SIZE)
    assert geo["is_fx"] is True
    assert geo["key_col"] == 0 and geo["max_scroll"] == 0


# ─────────────────────────────────────────────────────────────────────────────
# 2. IL CLICK COLPISCE CIO' CHE E' DISEGNATO
# ─────────────────────────────────────────────────────────────────────────────

def test_the_top_pixel_of_the_search_box_focuses_it():
    """It used to be drawn three pixels below where it was hit-tested."""
    host = FakeLang()
    geo = host._lang_geometry(*SIZE)
    host._lang_click(geo["search"].centerx, geo["search"].top + 1, *SIZE)
    assert host._lang_search_active is True


def test_a_click_below_the_search_box_leaves_it():
    host = FakeLang()
    host._lang_search_active = True
    geo = host._lang_geometry(*SIZE)
    host._lang_click(geo["search"].centerx, geo["search"].bottom + 40, *SIZE)
    assert host._lang_search_active is False


def test_the_last_visible_row_can_be_clicked():
    """It used to be drawn two pixels past where clicks stopped being taken."""
    host = _many_keys(200)
    geo = host._lang_geometry(*SIZE)
    row = geo["visible_rows"] - 1
    cell = host._lang_cell_rect(geo, row, 0)
    host._lang_click(cell.centerx, cell.centery, *SIZE)
    assert host._lang_sel == (row, 0)


def test_clicking_a_cell_loads_its_value():
    host = FakeLang()
    geo = host._lang_geometry(*SIZE)
    cell = host._lang_cell_rect(geo, 0, 1)          # key "a", italian
    host._lang_click(cell.centerx, cell.centery, *SIZE)
    assert host._lang_sel == (0, 1) and host._lang_buf == "Alfa"


def test_moving_to_another_cell_commits_the_previous_one():
    host = FakeLang()
    geo = host._lang_geometry(*SIZE)
    first = host._lang_cell_rect(geo, 0, 0)
    host._lang_click(first.centerx, first.centery, *SIZE)
    host._lang_buf = "edited"
    second = host._lang_cell_rect(geo, 1, 0)
    host._lang_click(second.centerx, second.centery, *SIZE)
    assert host._lang_data["en"]["a"] == "edited"


def test_a_click_outside_the_table_selects_nothing():
    host = FakeLang()
    geo = host._lang_geometry(*SIZE)
    host._lang_click(geo["box"].x + 2, geo["footer_y"] - 2, *SIZE)
    assert host._lang_sel is None


# ─────────────────────────────────────────────────────────────────────────────
# 3. TROVARE CIO' CHE MANCA
# ─────────────────────────────────────────────────────────────────────────────

def test_completion_counts_the_filled_values():
    host = FakeLang()
    done = host._lang_completion()
    assert done["en"] == 67          # a and b of a, b, c
    assert done["it"] == 33          # only a
    assert all(0 <= v <= 100 for v in done.values())


def test_completion_of_an_empty_project_is_full():
    assert FakeLang({lang: {} for lang in LANGS})._lang_completion()["en"] == 100


def test_a_key_missing_anywhere_is_incomplete():
    host = FakeLang()
    assert host._lang_is_incomplete("a") is False
    assert host._lang_is_incomplete("b") is True     # missing in italian
    assert host._lang_is_incomplete("c") is True


def test_the_filter_lists_only_the_incomplete_keys():
    host = FakeLang()
    host._lang_toggle_only_missing()
    assert host._lang_filtered_keys == ["b", "c"]
    host._lang_toggle_only_missing()
    assert host._lang_filtered_keys == ["a", "b", "c"]


def test_the_filter_combines_with_the_search():
    host = FakeLang()
    host._lang_toggle_only_missing()
    host._lang_search = "b"
    host._lang_update_filter()
    assert host._lang_filtered_keys == ["b"]


def test_the_filter_clears_a_selection_that_would_point_elsewhere():
    host = FakeLang()
    host._lang_sel = (2, 0)
    host._lang_toggle_only_missing()
    assert host._lang_sel is None and host._lang_scroll == 0


# ─────────────────────────────────────────────────────────────────────────────
# 4. UNA CHIAVE NUOVA HA UN NOME
# ─────────────────────────────────────────────────────────────────────────────

def test_a_new_key_is_created_and_named_right_away():
    host = FakeLang()
    host._lang_add_key()
    assert "new_key" in host._lang_keys
    assert host._lang_naming is not None, "the name editor must open"
    assert host._lang_name_buf == "new_key"


def test_a_new_key_never_collides():
    host = FakeLang()
    host._lang_add_key()
    host._lang_finish_naming(commit=False)
    host._lang_add_key()
    assert sorted(k for k in host._lang_keys if k.startswith("new_key")) == [
        "new_key", "new_key_2"]


def test_naming_renames_the_key_in_every_language():
    host = FakeLang()
    host._lang_add_key()
    host._lang_name_buf = "tip_intro"
    host._lang_finish_naming(commit=True)
    assert "tip_intro" in host._lang_keys and "new_key" not in host._lang_keys
    for lang in LANGS:
        assert "tip_intro" in host._lang_data[lang]
        assert "new_key" not in host._lang_data[lang]


def test_naming_keeps_what_was_already_typed_in_the_cells():
    host = FakeLang()
    host._lang_add_key()
    host._lang_data["en"]["new_key"] = "Hello"
    host._lang_name_buf = "greeting"
    host._lang_finish_naming(commit=True)
    assert host._lang_data["en"]["greeting"] == "Hello"


def test_naming_refuses_a_name_already_taken():
    host = FakeLang()
    host._lang_add_key()
    host._lang_name_buf = "a"
    host._lang_finish_naming(commit=True)
    assert "new_key" in host._lang_keys, "the key keeps its name"
    assert host.status, "and the user is told why"


def test_cancelling_the_name_keeps_the_generated_one():
    host = FakeLang()
    host._lang_add_key()
    host._lang_name_buf = "whatever"
    host._lang_finish_naming(commit=False)
    assert "new_key" in host._lang_keys and "whatever" not in host._lang_keys


def test_only_a_key_created_here_can_be_renamed():
    host = FakeLang()
    host._lang_add_key()
    host._lang_finish_naming(commit=True)
    assert host._lang_new_keys == {"new_key"}
    geo = host._lang_geometry(*SIZE)
    row = host._lang_filtered_keys.index("a")
    key_cell = pygame.Rect(geo["content"].x,
                           geo["table_top"] + row * geo["row_h"],
                           geo["key_col"], geo["row_h"] - 2)
    host._lang_click(key_cell.centerx, key_cell.centery, *SIZE)
    assert host._lang_naming is None, "an existing key is not renameable"


def test_typing_a_name_never_leaks_into_the_search():
    host = FakeLang()
    host._lang_add_key()
    host._lang_key(pygame.event.Event(pygame.KEYDOWN, {"key": ord("x"),
                                                       "unicode": "x"}))
    assert host._lang_name_buf.endswith("x")
    assert host._lang_search == ""


def test_escape_closes_the_name_editor_without_touching_the_modal():
    host = FakeLang()
    host._lang_add_key()
    host._lang_key(pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_ESCAPE,
                                                       "unicode": ""}))
    assert host._lang_naming is None and host.closed is False
