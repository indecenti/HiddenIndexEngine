"""
tests/test_scatter_refinements.py

Guard per i refinements model-independent della PHASE B:
  - B7: _center_prior_saliency (fallback saliency decorrelato dall'edge)
  - B8: _uniformity_reweight (boost color-match senza saturazione/clip)
"""

from __future__ import annotations

import numpy as np
import pytest

from editor.tools.scatter_engine import _center_prior_saliency, _uniformity_reweight


# ── B7: fallback saliency ─────────────────────────────────────────────────────

def test_center_prior_saliency_radial():
    sal = _center_prior_saliency(100, 120)
    assert sal.shape == (100, 120)
    assert sal.dtype == np.float32
    assert sal[50, 60] == pytest.approx(1.0, abs=1e-3)   # 1 al centro
    assert sal[0, 0] < 0.05 and sal[99, 119] < 0.05      # ~0 agli angoli
    # centro >> bordo: l'occhio guarda il centro
    assert sal[50, 60] > sal[10, 10] > sal[0, 0]
    assert sal.min() >= -1e-6 and sal.max() <= 1.0 + 1e-6


def test_center_prior_saliency_is_edge_independent():
    # Proprieta' chiave del fix: la saliency di fallback NON dipende dal contenuto
    # dell'immagine (solo dalle dimensioni), quindi (1-saliency) non si annulla piu'
    # con w_edge. La firma stessa lo garantisce: non accetta edge in input.
    import inspect
    params = list(inspect.signature(_center_prior_saliency).parameters)
    assert params == ["h", "w"]


# ── B8: color uniformity reweight ─────────────────────────────────────────────

def test_uniformity_reweight_no_saturation_vs_old_clip():
    cs = np.array([0.80, 0.90, 0.95, 1.00], dtype=np.float32)
    unif = np.ones_like(cs)
    out = _uniformity_reweight(cs, unif)
    # Vecchia formula: clip(cs*(1+0.6*unif*cs), 0, 1) -> tutti schiacciati a 1.0
    old = np.clip(cs * (1.0 + 0.6 * unif * cs), 0.0, 1.0)
    assert np.all(old == 1.0)                  # vecchio: appiattiti (no discriminazione)
    assert np.all(np.diff(out) > 0)            # nuovo: monotono, valori distinti
    assert out[-1] == pytest.approx(1.6)


def test_uniformity_reweight_zero_uniformity_identity():
    cs = np.array([0.3, 0.6, 0.9], dtype=np.float32)
    out = _uniformity_reweight(cs, np.zeros_like(cs))
    assert np.allclose(out, cs)                # unif=0 -> fattore 1 -> cs invariato


def test_uniformity_reweight_monotone_in_cs():
    cs = np.linspace(0, 1, 50).astype(np.float32)
    for u in (0.0, 0.5, 1.0):
        out = _uniformity_reweight(cs, np.full_like(cs, u))
        assert np.all(np.diff(out) >= 0)       # monotono non decrescente per ogni uniformita'
