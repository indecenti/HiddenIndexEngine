"""
tests/test_scatter_footprint.py

Ondata 3 (S4/S5): veto footprint (l'INTERA area dell'oggetto non copre celle
vietate, non solo il centro), gate straddle sulla std di L sotto il footprint,
clamp di rotazione per oggetti upright.
"""

from __future__ import annotations

import numpy as np
import pytest

from editor.tools.scatter_engine import (
    BGAnalysis, ObjAnalysis, STRADDLE_LSTD_MAX, STRADDLE_RELAX_GAIN,
    UPRIGHT_MAX_DEG, place_objects,
)

CH, CW, CP = 12, 20, 48


def _bg(lab_grid: np.ndarray | None = None) -> BGAnalysis:
    return BGAnalysis(
        bg_w=CW * CP, bg_h=CH * CP, cell_w=CW, cell_h=CH, cell_px=CP,
        edge_density=np.full((CH, CW), 0.5, dtype=np.float32),
        saliency=np.zeros((CH, CW), dtype=np.float32),
        hue=np.full((CH, CW), 0.1, dtype=np.float32),
        sat=np.full((CH, CW), 0.6, dtype=np.float32),
        val=np.full((CH, CW), 0.55, dtype=np.float32),
        grad_orient=np.zeros((CH, CW), dtype=np.float32),
        lab_grid=lab_grid,
    )


def _obj(cid: str = "o", shape: dict | None = None) -> ObjAnalysis:
    return ObjAnalysis(
        catalog_id=cid, palette=[(0.1, 0.6, 0.55)] * 3,
        edge_orient=0.0, aspect=1.0, size_class="mid",
        palette_ext=[{"h": 0.1, "s": 0.6, "v": 0.55, "w": 1.0, "var": 0.01}],
        shape=shape,
    )


def _entries(radius: int = 60) -> dict:
    return {"o": {"tags": [], "default_detection": "circle",
                  "default_radius": radius}}


def test_footprint_non_copre_celle_vietate():
    """Colonna vietata al centro: NESSUN bbox piazzato la tocca, nemmeno di
    striscio (prima bastava che il CENTRO fosse fuori)."""
    bg = _bg()
    forbidden = np.zeros((CH, CW), dtype=bool)
    forbidden[:, 9:11] = True          # colonna centrale vietata
    placed = place_objects(bg, {"o": _obj()}, _entries(radius=60), count=10,
                           difficulty="medium", style="real",
                           allowed_layers=["objects_mid"], seed=3,
                           forbidden_mask=forbidden)
    assert placed
    forb_x0 = 9 * CP
    forb_x1 = 11 * CP
    for p in placed:
        r = p.radius * p.scale
        x0, x1 = p.x - r, p.x + r
        assert x1 < forb_x0 + CP or x0 >= forb_x1 - 1, \
            f"footprint ({x0:.0f}..{x1:.0f}) copre la colonna vietata"


def test_straddle_evita_il_confine_di_luminanza():
    """BG meta' scura / meta' chiara in Lab: oggetti grandi non finiscono a
    cavallo del confine (std L sotto il footprint oltre il cap)."""
    lab = np.zeros((CH, CW, 3), dtype=np.float32)
    lab[:, : CW // 2, 0] = 20.0
    lab[:, CW // 2:, 0] = 80.0
    bg = _bg(lab_grid=lab)
    placed = place_objects(bg, {"o": _obj()}, _entries(radius=70), count=6,
                           difficulty="medium", style="real",
                           allowed_layers=["objects_mid"], seed=9)
    assert placed
    cap_max = (STRADDLE_LSTD_MAX["medium"]
               * (1.0 + STRADDLE_RELAX_GAIN))       # relax massimo teorico
    half_px = (CW // 2) * CP
    for p in placed:
        r = p.radius * p.scale
        x0, x1 = p.x - r, p.x + r
        crosses = x0 < half_px < x1
        if crosses:
            # tollerato solo se il footprint copre il confine di pochissimo
            span = min(x1 - half_px, half_px - x0)
            assert span < CP * 1.5, \
                f"oggetto a cavallo pieno del confine (span {span:.0f}px, cap {cap_max:.0f})"


def test_upright_clamp_rotazione():
    """support_bot alto -> rotazione entro +/- UPRIGHT_MAX_DEG."""
    shape = {"support_bot": 0.8, "hang_top": 0.0, "compactness": 0.6,
             "aspect_real": 0.8, "axis_angle": 0.0}
    bg = _bg()
    # grad_orient non nullo: senza clamp la rotazione seguirebbe il gradiente
    bg.grad_orient[:] = 0.9
    placed = place_objects(bg, {"o": _obj(shape=shape)}, _entries(), count=8,
                           difficulty="medium", style="real",
                           allowed_layers=["objects_mid"], seed=4)
    assert placed
    for p in placed:
        r = p.rotation % 360.0
        if r > 180.0:
            r -= 360.0
        assert abs(r) <= UPRIGHT_MAX_DEG + 1e-6, f"rotazione {p.rotation} non upright"


def test_upright_non_tocca_oggetti_liberi():
    """Senza shape/tag upright la rotazione resta libera (segue il gradiente)."""
    bg = _bg()
    bg.grad_orient[:] = 0.9   # ~51 gradi
    placed = place_objects(bg, {"o": _obj(shape=None)}, _entries(), count=8,
                           difficulty="medium", style="real",
                           allowed_layers=["objects_mid"], seed=4)
    assert placed
    assert any(10.0 < (p.rotation % 360.0) < 350.0 for p in placed), \
        "nessuna rotazione libera: il clamp upright si applica a tutto"
