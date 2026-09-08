"""
tests/test_editor_recent_objects.py

The strip of recently placed objects at the top of the catalog.

Placing objects is the repetitive action of the editor and the catalog holds
over a thousand entries, so coming back to one just used meant finding it in
the list again. The strip remembers the last ones placed, per project, across
sessions - which only helps if the list is ordered, de-duplicated, capped, and
never offers an object the catalog no longer has.
"""

from __future__ import annotations

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pytest

pygame = pytest.importorskip("pygame")

from editor.constants import RECENT_OBJECTS_MAX
from editor.mixins.object_ops import ObjectOpsMixin


class FakeCatalogHost(ObjectOpsMixin):
    """Only the state the recent list needs; the settings stay in memory."""

    def __init__(self, game="Game", catalog_ids=("a", "b", "c", "d")):
        self.game_name = game
        self.catalog = [{"id": i} for i in catalog_ids]
        self.settings: dict = {}

    def _load_editor_settings(self):
        return dict(self.settings)

    def _save_editor_setting(self, key, value):
        self.settings[key] = value


def test_nothing_is_remembered_at_first():
    assert FakeCatalogHost()._recent_objects() == []


def test_the_last_placed_object_comes_first():
    host = FakeCatalogHost()
    host._note_object_used("a")
    host._note_object_used("b")
    assert host._recent_objects() == ["b", "a"]


def test_placing_the_same_object_again_moves_it_to_the_front():
    host = FakeCatalogHost()
    for cat_id in ("a", "b", "c", "a"):
        host._note_object_used(cat_id)
    assert host._recent_objects() == ["a", "c", "b"]


def test_the_list_is_capped():
    host = FakeCatalogHost(catalog_ids=[f"o{i}" for i in range(50)])
    for i in range(50):
        host._note_object_used(f"o{i}")
    assert len(host._recent_objects()) == RECENT_OBJECTS_MAX
    assert host._recent_objects()[0] == "o49"


def test_each_project_has_its_own_list():
    host = FakeCatalogHost(game="One")
    host._note_object_used("a")
    host.game_name = "Two"
    host._note_object_used("b")
    assert host._recent_objects() == ["b"]
    host.game_name = "One"
    assert host._recent_objects() == ["a"]


def test_an_object_no_longer_in_the_catalog_is_not_offered():
    host = FakeCatalogHost()
    host._note_object_used("a")
    host._note_object_used("gone")
    assert host._recent_objects() == ["a"]


def test_the_stored_list_keeps_what_the_catalog_lost():
    """Filtering happens on read: switching style must not erase the history."""
    host = FakeCatalogHost()
    host._note_object_used("a")
    host.catalog = []
    assert host._recent_objects() == []
    host.catalog = [{"id": "a"}]
    assert host._recent_objects() == ["a"]


def test_without_a_project_nothing_is_recorded():
    host = FakeCatalogHost(game=None)
    host._note_object_used("a")
    assert host.settings == {} and host._recent_objects() == []


def test_an_empty_id_is_ignored():
    host = FakeCatalogHost()
    host._note_object_used("")
    assert host.settings == {}
