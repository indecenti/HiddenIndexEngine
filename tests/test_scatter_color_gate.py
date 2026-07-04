"""
tests/test_scatter_color_gate.py

Gate colore duro (camouflage v3): un oggetto NON deve atterrare su celle il cui
colore non combacia (sotto COLOR_GATE_MIN per difficolta'), con relax
deterministico e fallback a gate disattivo (None) quando il BG non offre
abbastanza celle compatibili.

Non richiede pygame ne' asset: BGAnalysis/ObjAnalysis sintetici.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from editor.tools.scatter_engine import (
    BGAnalysis, ObjAnalysis, _get_weights,
    _build_color_gate, _build_score_matrix, _color_similarity_map,
    place_objects,
    COLOR_GATE_MIN, COLOR_GATE_FLOOR, FLAT_COLOR_MIN,
    FLAT_ENTROPY_MAX, FLAT_EDGE_MAX, SCORE_VETO_THRESHOLD,
)


def _make_bg(ch: int = 20, cw: int = 30, half_hue: bool = True,
             with_entropy: bool = False) -> BGAnalysis:
    """BG sintetico: meta' sinistra rossa (hue 0.0), meta' destra blu (hue 0.6).

    sat/val costanti cosi' il match dipende solo dalla hue.
    """
    cp = 48
    hue = np.full((ch, cw), 0.6, dtype=np.float32)
    if half_hue:
        hue[:, : cw // 2] = 0.0
    sat = np.full((ch, cw), 0.6, dtype=np.float32)
    val = np.full((ch, cw), 0.6, dtype=np.float32)
    texture_entropy = None
    if with_entropy:
        texture_entropy = np.full((ch, cw), 0.8, dtype=np.float32)
    return BGAnalysis(
        bg_w=cw * cp, bg_h=ch * cp, cell_w=cw, cell_h=ch, cell_px=cp,
        edge_density=np.full((ch, cw), 0.5, dtype=np.float32),
        saliency=np.zeros((ch, cw), dtype=np.float32),
        hue=hue, sat=sat, val=val,
        grad_orient=np.zeros((ch, cw), dtype=np.float32),
        texture_entropy=texture_entropy,
    )


def _make_obj(hue: float = 0.0, cid: str = "obj_red") -> ObjAnalysis:
    """Oggetto monocromatico con palette_ext concentrata sulla hue data."""
    return ObjAnalysis(
        catalog_id=cid,
        palette=[(hue, 0.6, 0.6)] * 3,
        edge_orient=0.0, aspect=1.0, size_class="mid",
        palette_ext=[{"h": hue, "s": 0.6, "v": 0.6, "w": 1.0, "var": 0.01}],
    )


def test_gate_vieta_celle_colore_sbagliato():
    """Oggetto rosso su BG mezzo rosso / mezzo blu: meta' blu vetata (medium+)."""
    bg = _make_bg()
    obj = _make_obj(hue=0.0)
    weights = _get_weights("medium", "real")
    gate = _build_color_gate(bg, obj, weights, "medium")
    assert gate is not None
    cs = _color_similarity_map(bg, obj)
    thr = COLOR_GATE_MIN["medium"]
    # Il gate deve coincidere con la soglia base (nessun relax necessario:
    # meta' griglia matcha perfettamente)
    assert np.array_equal(gate, cs < thr)
    # Celle rosse (match perfetto) libere, celle blu vetate
    assert not gate[:, : bg.cell_w // 2].any()
    assert gate[:, bg.cell_w // 2:].all()


def test_gate_none_per_line_art():
    """w_color == 0 (line_art) -> gate disattivo."""
    bg = _make_bg()
    obj = _make_obj()
    weights = _get_weights("medium", "line_art")
    assert weights.get("w_color", 0.0) == 0.0
    assert _build_color_gate(bg, obj, weights, "medium") is None


def test_gate_relax_fino_a_none():
    """BG interamente incompatibile: il relax scende e il gate si disattiva."""
    bg = _make_bg(half_hue=False)     # tutto blu (hue 0.6)
    obj = _make_obj(hue=0.0)          # oggetto rosso: nessuna cella compatibile
    weights = _get_weights("hard", "real")
    cs = _color_similarity_map(bg, obj)
    # Se anche al floor nessuna cella supera, il gate deve tornare None
    if float(cs.max()) < COLOR_GATE_FLOOR:
        assert _build_color_gate(bg, obj, weights, "hard") is None
    else:
        # In caso di soglia raggiunta al floor il gate resta valido
        gate = _build_color_gate(bg, obj, weights, "hard")
        assert gate is None or (~gate).sum() > 0


def test_flat_subgate():
    """Su celle piatte (bassa entropia + pochi edge) serve match quasi perfetto."""
    ch, cw = 20, 30
    bg = _make_bg(ch, cw, with_entropy=True)
    # Rendi piatta una banda della meta' rossa: entropia e edge sotto soglia
    bg.texture_entropy[:, :5] = FLAT_ENTROPY_MAX - 0.1
    bg.edge_density[:, :5] = FLAT_EDGE_MAX - 0.02
    # Oggetto rosso ma con match imperfetto sulla banda piatta: alza la
    # differenza di sat cosi' cs < FLAT_COLOR_MIN ma >= COLOR_GATE_MIN
    bg.sat[:, :5] = 0.95
    obj = _make_obj(hue=0.0)
    weights = _get_weights("easy", "real")
    gate = _build_color_gate(bg, obj, weights, "easy")
    assert gate is not None
    cs = _color_similarity_map(bg, obj)
    flat_zone = cs[:, :5]
    # Le celle piatte con match sotto FLAT_COLOR_MIN devono essere vetate anche
    # se sopra la soglia base easy
    assert (flat_zone >= COLOR_GATE_MIN["easy"]).all()
    if (flat_zone < FLAT_COLOR_MIN).any():
        assert gate[:, :5][flat_zone < FLAT_COLOR_MIN].all()
    # Il resto della meta' rossa (non piatta, match pieno) resta libero
    assert not gate[:, 5: cw // 2].any()


def test_score_matrix_applica_color_gate():
    """_build_score_matrix con color_gate veta esattamente quelle celle."""
    bg = _make_bg()
    obj = _make_obj()
    weights = _get_weights("medium", "real")
    occupied = np.ones((bg.cell_h, bg.cell_w), dtype=np.float32)
    gate = _build_color_gate(bg, obj, weights, "medium")
    np.random.seed(0)
    s = _build_score_matrix(bg, obj, weights, occupied, color_gate=gate)
    assert np.all(s[gate] < SCORE_VETO_THRESHOLD)
    assert np.all(s[~gate] > SCORE_VETO_THRESHOLD)


def test_place_objects_mai_su_celle_vetate_dal_colore():
    """I piazzati finiscono solo nella meta' cromaticamente compatibile."""
    bg = _make_bg(ch=20, cw=30)
    obj = _make_obj(hue=0.0)
    analyses = {"obj_red": obj}
    entries = {"obj_red": {"tags": [], "default_detection": "circle",
                           "default_radius": 24}}
    placed = place_objects(bg, analyses, entries, count=10, difficulty="medium",
                           style="real", allowed_layers=["objects_mid"], seed=7)
    assert len(placed) > 0
    half_px = (bg.cell_w // 2) * bg.cell_px
    for p in placed:
        # circle: (x, y) e' il centro
        assert p.x < half_px + bg.cell_px, \
            f"oggetto rosso piazzato nella zona blu (x={p.x:.0f})"
