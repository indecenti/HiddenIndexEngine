"""
tests/test_save_keeps_game_owned_objects.py

Saving a scene pruned every local catalog entry not placed in any scene, and then
its translated name. For a game whose objects were generated for it (icons only in
games/<id>/objects, nothing in the engine) that wiped the catalog: Ultimo_Treno went
from 127 objects to 5. Only harvested copies - icon also present in engine/assets,
so they can be harvested again - may be pruned; game-owned entries and their names
stay.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pytest

pygame = pytest.importorskip("pygame")

from editor.mixins.io_ops import IoOpsMixin


def _write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


@pytest.fixture(scope="module", autouse=True)
def _pygame_init():
    pygame.init()
    pygame.display.set_mode((8, 8))
    yield
    pygame.quit()


def test_icon_in_engine_tells_harvested_copies_from_game_owned(tmp_path):
    engine_assets = tmp_path / "engine" / "assets"
    (engine_assets / "objects").mkdir(parents=True)
    (engine_assets / "objects" / "clock.png").write_bytes(b"png")
    assert IoOpsMixin._icon_in_engine("objects/clock.png", engine_assets)
    assert not IoOpsMixin._icon_in_engine("objects/ticket.png", engine_assets)
    assert not IoOpsMixin._icon_in_engine("", engine_assets)


def test_names_of_unplaced_game_objects_survive_the_audit(tmp_path):
    _write(tmp_path / "engine" / "assets" / "strings" / "en.json", {})
    game_path = tmp_path / "games" / "G"
    _write(game_path / "levels" / "L" / "S" / "scene.json", {"objects": []})
    _write(game_path / "objects_catalog.json", {"objects": [
        {"id": "ticket", "label_key": "obj_ticket", "icon": "objects/ticket.png"}]})
    _write(game_path / "strings" / "en.json", {
        "game_title": "G", "obj_ticket": "Old Ticket", "obj_gone": "Gone"})
    host = SimpleNamespace(game_path=game_path, base_path=tmp_path, game_name="G",
                           scene_path=None, LANGS=["en"], catalog=[],
                           _status=lambda *a, **k: None, _TR=lambda k, d: d)
    IoOpsMixin._audit_translations(host, {"objects": []})
    strings = json.loads((game_path / "strings" / "en.json").read_text(encoding="utf-8"))
    assert strings["obj_ticket"] == "Old Ticket"
    assert "obj_gone" not in strings
