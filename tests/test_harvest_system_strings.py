"""
tests/test_harvest_system_strings.py

IoOpsMixin._audit_translations re-aligns the system strings a game carries
(menu, HUD) with the engine's. Harvesting only ever filled MISSING keys, so a
value copied from the wrong language - Malonno's de/es/fr shipped the Italian
"Impostazioni", "Riprendi", "Volume Musica" - or a placeholder written while
the engine lacked the key ("Mission Complete") stayed in the game forever.
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

ENGINE = {
    "it": {"btn_settings": "Impostazioni", "mission_complete": "Livello Completato!",
           "btn_play": "Gioca"},
    "en": {"btn_settings": "Settings", "mission_complete": "Level Complete!",
           "btn_play": "Play"},
    "de": {"btn_settings": "Einstellungen", "mission_complete": "Level geschafft!",
           "btn_play": "Spielen"},
}


def _write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


@pytest.fixture(scope="module", autouse=True)
def _pygame_init():
    pygame.init()
    pygame.display.set_mode((8, 8))
    yield
    pygame.quit()


@pytest.fixture
def game(tmp_path):
    for lang, data in ENGINE.items():
        _write(tmp_path / "engine" / "assets" / "strings" / f"{lang}.json", data)
    game_path = tmp_path / "games" / "G"
    _write(game_path / "levels" / "L" / "S" / "scene.json", {"objects": []})
    _write(game_path / "strings" / "de.json", {
        "game_title": "G",
        "btn_settings": "Impostazioni",          # Italian copied into German
        "mission_complete": "Mission Complete",  # placeholder from an old harvest
        "btn_play": "Los geht's",                # a real override of the game
    })
    host = SimpleNamespace(game_path=game_path, base_path=tmp_path, game_name="G",
                           scene_path=None, LANGS=["de"], catalog=[],
                           _status=lambda *a, **k: None, _TR=lambda k, d: d)
    IoOpsMixin._audit_translations(host, {"objects": []})
    return json.loads((game_path / "strings" / "de.json").read_text(encoding="utf-8"))


def test_a_value_from_another_language_is_replaced(game):
    assert game["btn_settings"] == "Einstellungen"


def test_an_old_placeholder_is_replaced(game):
    assert game["mission_complete"] == "Level geschafft!"


def test_a_real_override_of_the_game_is_kept(game):
    assert game["btn_play"] == "Los geht's"
