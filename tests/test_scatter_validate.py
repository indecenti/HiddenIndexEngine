"""
tests/test_scatter_validate.py

Validatore post-render del camouflage (scatter_validate): un oggetto dello
stesso colore del BG deve risultare "ok", uno a contrasto pieno "fail";
il clutter dell'anello riduce la severita'.
"""

from __future__ import annotations

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import numpy as np
import pytest

pygame = pytest.importorskip("pygame")
cv2 = pytest.importorskip("cv2")

from editor.tools.scatter_engine import PlacedObject
from editor.tools.scatter_validate import (
    validate_placements, summarize, annotate,
)


@pytest.fixture(scope="module", autouse=True)
def _pygame_init():
    pygame.init()
    pygame.display.set_mode((64, 64))
    yield
    pygame.quit()


def _make_icon(tmp_path, name: str, rgb: tuple[int, int, int]):
    surf = pygame.Surface((64, 64), pygame.SRCALPHA)
    surf.fill((*rgb, 255))
    p = tmp_path / name
    pygame.image.save(surf, str(p))
    return p


def _placed(cid: str, x: float, y: float) -> PlacedObject:
    return PlacedObject(
        catalog_id=cid, x=x, y=y, scale=1.0, rotation=0.0,
        flip_x=False, flip_y=False, alpha=255,
        color_filter=(255, 255, 255), detection_type="circle",
        width=64, height=64, radius=32, layer="objects_mid",
        visibility_score=0.5,
    )


def test_verdetti_match_e_contrasto(tmp_path):
    # BG verde uniforme 400x300
    bg = pygame.Surface((400, 300))
    bg.fill((60, 140, 60))
    _make_icon(tmp_path, "same.png", (60, 140, 60))     # identico al BG
    _make_icon(tmp_path, "contrast.png", (255, 40, 200))  # magenta acceso
    entries = {
        "same": {"icon": "same.png"},
        "contrast": {"icon": "contrast.png"},
    }
    placed = [_placed("same", 100, 150), _placed("contrast", 300, 150)]
    results = validate_placements(bg, placed, entries,
                                  game_path=tmp_path, repo_root=tmp_path)
    assert len(results) == 2
    by_id = {r["catalog_id"]: r for r in results}
    assert by_id["same"]["verdict"] == "ok"
    assert by_id["same"]["delta_e"] < 5.0
    assert by_id["contrast"]["verdict"] == "fail"
    assert by_id["contrast"]["delta_e"] > 50.0

    stats = summarize(results)
    assert stats["total"] == 2 and stats["ok"] == 1 and stats["fail"] == 1

    # annotate non deve sollevare
    annotate(bg.copy(), results)


def test_clutter_riduce_severita(tmp_path):
    # BG rumoroso (clutter alto): lo stesso oggetto a contrasto deve avere
    # score EFFETTIVO piu' basso che su BG uniforme.
    rng = np.random.default_rng(3)
    noise = rng.integers(0, 255, (300, 400, 3), dtype=np.uint8)
    bg_noisy = pygame.surfarray.make_surface(noise.swapaxes(0, 1))
    bg_flat = pygame.Surface((400, 300))
    bg_flat.fill((128, 128, 128))
    _make_icon(tmp_path, "obj.png", (255, 60, 60))
    entries = {"obj": {"icon": "obj.png"}}
    placed = [_placed("obj", 200, 150)]

    r_noisy = validate_placements(bg_noisy, placed, entries, tmp_path, tmp_path)
    r_flat = validate_placements(bg_flat, placed, entries, tmp_path, tmp_path)
    assert r_noisy and r_flat
    assert r_noisy[0]["clutter"] > r_flat[0]["clutter"]
    # A parita' di delta cromatico, il clutter abbassa lo score
    assert r_noisy[0]["score"] < r_noisy[0]["delta_e"] + 0.5 * r_noisy[0]["delta_l"]


def test_icona_mancante_saltata(tmp_path):
    bg = pygame.Surface((200, 200))
    bg.fill((60, 140, 60))
    entries = {"ghost": {"icon": "non_esiste.png"}}
    placed = [_placed("ghost", 100, 100)]
    results = validate_placements(bg, placed, entries, tmp_path, tmp_path)
    assert results == []
