"""
tests/test_scatter_visibility_band.py

Enforcement banda di visibilita' (camouflage v3, audit #4): easy CAP-pa la
nascondibilita' (niente oggetti troppo nascosti), hard la richiede. Su un BG
crafted dove OGNI cella e' un nascondiglio perfetto (vs ~= 1.0), easy non deve
piazzare nulla e hard deve piazzare normalmente.

Copre anche l'estrazione di _visibility_score e la verifica Delta-E footprint.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from editor.tools.scatter_engine import (
    BGAnalysis, ObjAnalysis, _visibility_score, _color_similarity,
    _footprint_delta_e, _obj_dominant_lab, place_objects,
    VISIBILITY_BAND, VIS_BAND_RELAX_GAIN,
)

try:
    import cv2
    _HAS_CV2 = True
except Exception:
    _HAS_CV2 = False


def _perfect_hideout_bg(ch: int = 12, cw: int = 16) -> BGAnalysis:
    """Ogni cella: edge pieno, saliency zero, piano d'appoggio pieno."""
    cp = 48
    return BGAnalysis(
        bg_w=cw * cp, bg_h=ch * cp, cell_w=cw, cell_h=ch, cell_px=cp,
        edge_density=np.ones((ch, cw), dtype=np.float32),
        saliency=np.zeros((ch, cw), dtype=np.float32),
        hue=np.full((ch, cw), 0.1, dtype=np.float32),
        sat=np.full((ch, cw), 0.6, dtype=np.float32),
        val=np.full((ch, cw), 0.7, dtype=np.float32),
        grad_orient=np.zeros((ch, cw), dtype=np.float32),
        horizontal_score=np.ones((ch, cw), dtype=np.float32),
    )


def _matching_obj(cid: str = "obj0") -> ObjAnalysis:
    """Palette identica al BG: color similarity massima."""
    return ObjAnalysis(
        catalog_id=cid,
        palette=[(0.1, 0.6, 0.7)] * 3,
        edge_orient=0.0, aspect=1.0, size_class="mid",
        palette_ext=[{"h": 0.1, "s": 0.6, "v": 0.7, "w": 1.0, "var": 0.01}],
    )


def test_visibility_score_formula():
    bg = _perfect_hideout_bg()
    obj = _matching_obj()
    vs = _visibility_score(bg, obj, 5, 5, anchor_below_val=1.0, style="real")
    # 0.30*1 + 0.30*1 + 0.15*1 + 0.10*1 + 0.15*1 = 1.0
    assert vs == pytest.approx(1.0, abs=1e-6)
    vs_la = _visibility_score(bg, obj, 5, 5, anchor_below_val=1.0, style="line_art")
    # 0.45*1 + 0.30*1 + 0.10*1 + 0.15*1 = 1.0
    assert vs_la == pytest.approx(1.0, abs=1e-6)


def test_easy_rifiuta_nascondigli_perfetti_hard_li_accetta():
    bg = _perfect_hideout_bg()
    obj = _matching_obj()
    analyses = {"obj0": obj}
    entries = {"obj0": {"tags": [], "default_detection": "circle",
                        "default_radius": 20}}
    # Sanity: la banda easy anche col relax massimo non arriva a vs ~= 1.0
    assert VISIBILITY_BAND["easy"][1] + VIS_BAND_RELAX_GAIN < 0.95

    placed_easy = place_objects(bg, analyses, entries, count=6, difficulty="easy",
                                style="real", allowed_layers=["objects_mid"], seed=5)
    placed_hard = place_objects(bg, analyses, entries, count=6, difficulty="hard",
                                style="real", allowed_layers=["objects_mid"], seed=5)
    assert len(placed_easy) == 0, \
        "easy non deve accettare piazzamenti con nascondibilita' ~1.0 (floor risolvibilita')"
    assert len(placed_hard) > 0


def test_visibility_dentro_banda_massima():
    """I vs dei piazzati stanno nella banda allargata al massimo relax."""
    rng = np.random.default_rng(11)
    ch, cw, cp = 12, 16, 48
    f = lambda: rng.random((ch, cw)).astype(np.float32)
    bg = BGAnalysis(
        bg_w=cw * cp, bg_h=ch * cp, cell_w=cw, cell_h=ch, cell_px=cp,
        edge_density=f(), saliency=f(), hue=f(), sat=f(), val=f(),
        grad_orient=rng.uniform(-math.pi, math.pi, (ch, cw)).astype(np.float32),
    )
    obj = _matching_obj()
    analyses = {"obj0": obj}
    entries = {"obj0": {"tags": [], "default_detection": "circle",
                        "default_radius": 20}}
    placed = place_objects(bg, analyses, entries, count=6, difficulty="medium",
                           style="real", allowed_layers=["objects_mid"], seed=42)
    lo, hi = VISIBILITY_BAND["medium"]
    for p in placed:
        # visibility_score registrato = vs del piazzamento (nessuno swap con un
        # solo catalog_id: gli swap tra oggetti identici non superano l'isteresi)
        assert lo - VIS_BAND_RELAX_GAIN - 1e-6 <= p.visibility_score <= hi + VIS_BAND_RELAX_GAIN + 1e-6


# ── Delta-E footprint ────────────────────────────────────────────────────────

@pytest.mark.skipif(not _HAS_CV2, reason="richiede cv2 per le conversioni Lab")
def test_footprint_delta_e():
    ch, cw, cp = 4, 4, 48
    h_px, w_px = ch * cp, cw * cp
    # BG full-res rosso puro
    rgb = np.zeros((h_px, w_px, 3), dtype=np.uint8)
    rgb[..., 0] = 220
    lab_full = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB)
    bg = BGAnalysis(
        bg_w=w_px, bg_h=h_px, cell_w=cw, cell_h=ch, cell_px=cp,
        edge_density=np.zeros((ch, cw), dtype=np.float32),
        saliency=np.zeros((ch, cw), dtype=np.float32),
        hue=np.zeros((ch, cw), dtype=np.float32),
        sat=np.zeros((ch, cw), dtype=np.float32),
        val=np.zeros((ch, cw), dtype=np.float32),
        grad_orient=np.zeros((ch, cw), dtype=np.float32),
        lab_full=lab_full,
    )
    # Oggetto rosso (hue 0, sat/val alti) -> Delta-E piccolo
    obj_red = ObjAnalysis(
        catalog_id="red", palette=[(0.0, 0.9, 0.86)], edge_orient=0.0,
        aspect=1.0, size_class="mid",
        palette_ext=[{"h": 0.0, "s": 0.9, "v": 0.86, "w": 1.0, "var": 0.0}])
    # Oggetto verde -> Delta-E grande
    obj_green = ObjAnalysis(
        catalog_id="green", palette=[(0.33, 0.9, 0.8)], edge_orient=0.0,
        aspect=1.0, size_class="mid",
        palette_ext=[{"h": 0.33, "s": 0.9, "v": 0.8, "w": 1.0, "var": 0.0}])

    labs_red = _obj_dominant_lab(obj_red)
    labs_green = _obj_dominant_lab(obj_green)
    de_red = _footprint_delta_e(bg, labs_red, 10, 10, 100, 100)
    de_green = _footprint_delta_e(bg, labs_green, 10, 10, 100, 100)
    assert de_red is not None and de_green is not None
    assert de_red < 30.0 < de_green
    # Patch degenere / lab_full assente -> None (verifica non applicabile)
    assert _footprint_delta_e(bg, labs_red, 0, 0, 1, 1) is None
    bg.lab_full = None
    assert _footprint_delta_e(bg, labs_red, 10, 10, 100, 100) is None
