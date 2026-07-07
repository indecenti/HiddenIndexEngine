"""
tests/test_scene_smoke.py

Smoke / integrazione: carica OGNI scene.json reale attraverso il VERO SceneLoader
(validazione schema + join col catalogo + integrita' referenziale catalog_id) e
verifica che ogni goal sia colpibile dalla sua stessa hitbox.

E' la rete di regressione che avrebbe intercettato:
  - il crash NameError nel render loop (un caricamento scena che arriva fino al draw),
  - il bug "oggetto invisibile" (catalog_id mancante -> goal non trovabile).
A differenza di test_coordinate_e2e (che usa dict costruiti a mano), qui passa il
loader reale, quindi esercita load_and_validate e _select_objects sui dati veri.
"""
from __future__ import annotations

import glob
import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _all_scenes() -> list[str]:
    return sorted(glob.glob(str(ROOT / "games" / "*" / "levels" / "**" / "scene.json"), recursive=True))


def _ids_from_path(scene_path: str) -> tuple[str, str, str]:
    """(game_id, level_id, scene_id) da games/<g>/levels/<l>/<s>/scene.json."""
    p = Path(scene_path).resolve()
    parts = p.parts
    game_id = parts[parts.index("games") + 1]
    scene_id = p.parent.name
    level_id = p.parent.parent.name
    return game_id, level_id, scene_id


@pytest.fixture(scope="module", autouse=True)
def _headless_display():
    """Display pygame headless: serve a load_scene per .convert()/.convert_alpha()."""
    import pygame
    if not pygame.display.get_init():
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
        pygame.display.init()
    if pygame.display.get_surface() is None:
        pygame.display.set_mode((64, 64))
    yield


_SCENES = _all_scenes()


@pytest.mark.skipif(not _SCENES, reason="nessuna scena reale trovata")
@pytest.mark.parametrize("scene_path", _SCENES, ids=[Path(s).parent.name for s in _SCENES])
def test_real_scene_loads_and_goals_hittable(scene_path):
    from engine.catalog_manager import load_catalog
    from engine.scene_loader import SceneLoader
    from engine.scaling_manager import ScalingManager
    from engine.click_detector import ClickDetector

    game_id, level_id, scene_id = _ids_from_path(scene_path)
    loader = SceneLoader(game_id, load_catalog(game_id))

    # load_scene esercita json_validator.load_and_validate + _select_objects.
    # Se la scena e' malformata o un campo e' incompatibile, qui solleva.
    scene = loader.load_scene(level_id, scene_id)
    assert scene is not None, f"load_scene ha restituito None per '{scene_id}'"
    if not scene.objects:
        # Scena placeholder senza contenuto: non e' un bug della pipeline.
        # Il debito contenuti e' segnalato dall'Auditor dell'editor (ERR
        # "scena non risolvibile"), che e' il posto giusto per vederlo.
        pytest.skip(f"scena '{scene_id}' vuota: contenuto non ancora creato")

    goals = [o for o in scene.objects if o.is_goal]
    assert goals, f"scena '{scene_id}' senza goal"

    detector = ClickDetector(ScalingManager())
    for o in goals:
        if o.detection_type == "mask":
            continue  # il mask-hit richiede la maschera caricata: fuori scope dello smoke
        if o.detection_type == "rect":
            cx, cy = o.x + o.width / 2.0, o.y + o.height / 2.0
        else:  # "circle" (default)
            cx, cy = o.x, o.y
        assert detector._hit_test(o, cx, cy), (
            f"goal '{o.instance_id}' ({o.detection_type}) in '{scene_id}' non "
            f"colpito al suo centro ({cx:.0f},{cy:.0f}) -- hitbox incoerente"
        )
