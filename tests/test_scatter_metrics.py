"""
tests/test_scatter_metrics.py

Metrica unica di camuffamento (scatter_metrics): il pop_score deve ordinare
correttamente i casi canonici — oggetto identico al BG quasi invisibile,
oggetto a contrasto pieno in evidenza — e i componenti nuovi (rim, texture)
devono catturare cio' che la vecchia media-vs-anello non vedeva.
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
from editor.tools.scatter_metrics import (
    ObjectCamouflage, aggregate_pop, measure_placements, summarize_camouflage,
    W_RIM,
)


@pytest.fixture(scope="module", autouse=True)
def _pygame_init():
    pygame.init()
    pygame.display.set_mode((64, 64))
    yield
    pygame.quit()


def _make_icon(tmp_path, name: str, rgb: tuple[int, int, int], size: int = 64,
               border_rgb: tuple[int, int, int] | None = None,
               border_px: int = 0):
    surf = pygame.Surface((size, size), pygame.SRCALPHA)
    surf.fill((*rgb, 255))
    if border_rgb is not None and border_px > 0:
        pygame.draw.rect(surf, (*border_rgb, 255),
                         pygame.Rect(0, 0, size, size), border_px)
    p = tmp_path / name
    pygame.image.save(surf, str(p))
    return p


def _placed(cid: str, x: float, y: float, size: float = 64.0) -> PlacedObject:
    return PlacedObject(
        catalog_id=cid, x=x, y=y, scale=1.0, rotation=0.0,
        flip_x=False, flip_y=False, alpha=255,
        color_filter=(255, 255, 255), detection_type="circle",
        width=size, height=size, radius=size / 2, layer="objects_mid",
        visibility_score=0.5,
    )


def _measure_one(bg, cid, entries, tmp_path):
    out = measure_placements(bg, [_placed(cid, 200, 150)], entries,
                             game_path=tmp_path, repo_root=tmp_path)
    assert len(out) == 1
    return out[0]


def test_ordinamento_match_vs_contrasto(tmp_path):
    """Identico al BG -> pop basso; magenta su verde -> pop alto."""
    bg = pygame.Surface((400, 300))
    bg.fill((60, 140, 60))
    _make_icon(tmp_path, "same.png", (60, 140, 60))
    _make_icon(tmp_path, "contrast.png", (255, 40, 200))
    entries = {"same": {"icon": "same.png"}, "contrast": {"icon": "contrast.png"}}

    m_same = _measure_one(bg, "same", entries, tmp_path)
    m_con = _measure_one(bg, "contrast", entries, tmp_path)
    assert m_same.pop_score < 6.0
    assert m_same.interior_delta_e < 5.0
    assert m_same.rim_delta_e is not None and m_same.rim_delta_e < 5.0
    assert m_con.pop_score > 40.0
    assert m_con.rim_delta_e is not None and m_con.rim_delta_e > 50.0
    assert m_con.boundary_contrast > 0.0
    assert m_con.pop_score > m_same.pop_score + 30.0


def test_rim_vede_il_bordo_che_la_media_ignora(tmp_path):
    """Oggetto verde con SOLO il bordo magenta: la media interna resta vicina
    al BG (la vecchia metrica lo prometteva "ok"), ma il rim deve denunciarlo."""
    bg = pygame.Surface((400, 300))
    bg.fill((60, 140, 60))
    _make_icon(tmp_path, "solid.png", (60, 140, 60), size=64)
    _make_icon(tmp_path, "edged.png", (60, 140, 60), size=64,
               border_rgb=(255, 40, 200), border_px=5)
    entries = {"solid": {"icon": "solid.png"}, "edged": {"icon": "edged.png"}}

    m_solid = _measure_one(bg, "solid", entries, tmp_path)
    m_edged = _measure_one(bg, "edged", entries, tmp_path)
    # Il bordo sposta poco la media (interior), moltissimo il rim
    assert m_edged.rim_delta_e is not None and m_solid.rim_delta_e is not None
    assert m_edged.rim_delta_e > m_solid.rim_delta_e + 20.0
    assert m_edged.pop_score > m_solid.pop_score + 10.0
    assert m_edged.interior_delta_e < m_edged.rim_delta_e


def test_texture_mismatch_liscio_su_rumore(tmp_path):
    """Sprite piatto grigio su BG rumoroso con stessa media: interior quasi
    zero, ma il mismatch di texture deve emergere."""
    rng = np.random.default_rng(5)
    noise = rng.integers(64, 192, (300, 400, 3), dtype=np.uint8)
    bg_noisy = pygame.surfarray.make_surface(noise.swapaxes(0, 1))
    bg_flat = pygame.Surface((400, 300))
    bg_flat.fill((128, 128, 128))
    _make_icon(tmp_path, "flat.png", (128, 128, 128))
    entries = {"flat": {"icon": "flat.png"}}

    m_noise = _measure_one(bg_noisy, "flat", entries, tmp_path)
    m_flat = _measure_one(bg_flat, "flat", entries, tmp_path)
    assert m_noise.texture_mismatch > m_flat.texture_mismatch + 1.0
    # Il clutter dell'anello rumoroso pero' ammorbidisce il pop complessivo
    assert m_noise.clutter > m_flat.clutter


def test_aggregate_pop_fallback_rim_e_clutter():
    """rim None -> il suo peso ricade sull'interior; il clutter divide."""
    base = aggregate_pop(20.0, 10.0, None, 0.0, 0.0, 0.0, clutter=0.0)
    with_rim = aggregate_pop(20.0, 10.0, 20.0, 0.0, 0.0, 0.0, clutter=0.0)
    assert base == pytest.approx(with_rim)  # rim==interior -> identico
    softened = aggregate_pop(20.0, 10.0, 20.0, 0.0, 0.0, 0.0, clutter=1.0)
    assert softened < with_rim
    # rim molto peggiore dell'interior deve alzare il pop
    worse_rim = aggregate_pop(20.0, 10.0, 60.0, 0.0, 0.0, 0.0, clutter=0.0)
    assert worse_rim == pytest.approx(with_rim + W_RIM * 40.0)


def test_icona_mancante_e_summary(tmp_path):
    bg = pygame.Surface((200, 200))
    bg.fill((60, 140, 60))
    entries = {"ghost": {"icon": "non_esiste.png"}}
    out = measure_placements(bg, [_placed("ghost", 100, 100)], entries,
                             tmp_path, tmp_path)
    assert out == []
    assert summarize_camouflage(out) == {"total": 0}


def test_downscale_oggetto_enorme(tmp_path):
    """Sprite 600px: il patch viene ridotto (PATCH_MAX_SIDE) senza errori e
    con verdetto coerente (identico al BG -> pop basso)."""
    bg = pygame.Surface((900, 700))
    bg.fill((90, 90, 160))
    _make_icon(tmp_path, "big.png", (90, 90, 160), size=64)
    entries = {"big": {"icon": "big.png"}}
    placed = [_placed("big", 450, 350, size=600.0)]
    out = measure_placements(bg, placed, entries, tmp_path, tmp_path)
    assert len(out) == 1
    assert out[0].pop_score < 6.0

    s = summarize_camouflage(out)
    assert s["total"] == 1
    assert isinstance(s["pop_mean"], float)
