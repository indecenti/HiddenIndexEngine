"""
tests/test_scatter_saliency.py

Contratto della saliency dello scatter engine (editor/tools/scatter_engine.py):

  - _spectral_residual_saliency e' la saliency di default (numpy puro, nessuna
    dipendenza dal modulo contrib cv2.saliency che il pin opencv-python NON include):
    deve evidenziare i punti focali reali (contenuto), non solo il centro immagine.
  - Il fallback finale center-prior resta l'ultima spiaggia se anche la FFT fallisce.
  - analyze_background produce sempre una griglia saliency normalizzata 0..1.
"""
from __future__ import annotations

import os

import numpy as np
import pytest

from editor.tools.scatter_engine import (
    _resize_bilinear,
    _spectral_residual_saliency,
    analyze_background,
)


# ─────────────────────────────────────────────────────────────────────────────
# _spectral_residual_saliency
# ─────────────────────────────────────────────────────────────────────────────

def _synthetic_bg_with_blob(h: int = 240, w: int = 320) -> tuple[np.ndarray, tuple]:
    """BG texturizzato uniforme + blob ad alto contrasto DECENTRATO in alto a sinistra.

    Restituisce (gray uint8, slice del blob). Il rumore evita che il residuo
    spettrale collassi (immagine perfettamente piatta = nessuno spettro).
    """
    rng = np.random.default_rng(42)
    gray = (rng.normal(100, 6, size=(h, w))).clip(0, 255).astype(np.uint8)
    blob = (slice(h // 6, h // 6 + h // 6), slice(w // 8, w // 8 + w // 8))
    gray[blob] = 240
    return gray, blob


def test_spectral_residual_highlights_offcenter_blob():
    """Il blob decentrato deve essere piu' saliente del resto: il vecchio fallback
    center-prior lo avrebbe penalizzato perche' lontano dal centro."""
    gray, blob = _synthetic_bg_with_blob()
    sal = _spectral_residual_saliency(gray)

    assert sal.shape == gray.shape
    assert sal.dtype == np.float32
    assert float(sal.min()) >= 0.0 and float(sal.max()) <= 1.0 + 1e-5

    inside = float(sal[blob].mean())
    outside_mask = np.ones_like(sal, dtype=bool)
    outside_mask[blob] = False
    outside = float(sal[outside_mask].mean())
    assert inside > outside * 2, f"blob {inside:.3f} non domina il fondo {outside:.3f}"


def test_spectral_residual_constant_image_no_nan():
    """Immagine piatta: range spettrale nullo, deve restituire zeri finiti (no NaN)."""
    gray = np.full((120, 160), 128, dtype=np.uint8)
    sal = _spectral_residual_saliency(gray)
    assert np.isfinite(sal).all()
    assert float(sal.min()) >= 0.0 and float(sal.max()) <= 1.0 + 1e-5


def test_spectral_residual_accepts_float_input():
    """Il ramo senza cv2 produce gray float32: la funzione deve accettarlo."""
    gray, _ = _synthetic_bg_with_blob(h=96, w=128)
    sal = _spectral_residual_saliency(gray.astype(np.float32))
    assert sal.shape == (96, 128)
    assert np.isfinite(sal).all()


def test_resize_bilinear_matches_shape_and_range():
    rng = np.random.default_rng(7)
    a = rng.random((37, 53)).astype(np.float32)
    out = _resize_bilinear(a, 96, 200)
    assert out.shape == (96, 200)
    # Interpolazione: mai fuori dal range dei campioni originali
    assert float(out.min()) >= float(a.min()) - 1e-6
    assert float(out.max()) <= float(a.max()) + 1e-6


# ─────────────────────────────────────────────────────────────────────────────
# analyze_background (integrazione, no cache)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def _pygame_headless():
    import pygame
    if not pygame.display.get_init():
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
        pygame.display.init()
    yield pygame


def test_analyze_background_saliency_grid(_pygame_headless):
    """La saliency in BGAnalysis e' una griglia (cell_h, cell_w) in [0, 1]
    (normalizzazione p95 + clip, v3) e la cella del blob decentrato domina la
    media del resto: col vecchio center-prior sarebbe stato il contrario."""
    pygame = _pygame_headless
    gray, blob = _synthetic_bg_with_blob(h=240, w=320)
    rgb = np.repeat(gray[..., None], 3, axis=2)
    surface = pygame.surfarray.make_surface(rgb.swapaxes(0, 1))

    analysis = analyze_background(surface, cell_px=48, use_cache=False)

    assert analysis.saliency.shape == (analysis.cell_h, analysis.cell_w)
    assert float(analysis.saliency.min()) >= 0.0
    assert float(analysis.saliency.max()) <= 1.0 + 1e-5

    blob_cy = (blob[0].start + blob[0].stop) // 2 // 48
    blob_cx = (blob[1].start + blob[1].stop) // 2 // 48
    blob_val = float(analysis.saliency[blob_cy, blob_cx])
    rest = analysis.saliency.copy()
    rest[blob_cy, blob_cx] = np.nan
    rest_mean = float(np.nanmean(rest))
    assert blob_val > rest_mean, (
        f"cella blob ({blob_cy},{blob_cx})={blob_val:.3f} non domina la media {rest_mean:.3f}"
    )
