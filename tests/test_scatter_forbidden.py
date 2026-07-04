"""
tests/test_scatter_forbidden.py

Zone vietate (camouflage v3): forbidden mask unificata (volti + celle manuali +
classe person), veto duro in _build_score_matrix, geometria di face_cell_mask,
costanti ADE20K e determinismo di place_objects con maschera attiva.

Non richiede pygame ne' modelli: maschere e BGAnalysis sintetici.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from editor.tools.scatter_engine import (
    BGAnalysis, ObjAnalysis, _get_weights,
    _build_score_matrix, build_forbidden_mask, place_objects,
    SCORE_VETO_THRESHOLD,
)
from editor.tools.face_zones import face_cell_mask
from editor.tools.scatter_models import (
    ADE20K_PROHIBITED, ADE20K_PERSON_LIKE, ADE20K_WALL_LIKE, ADE20K_TABLE_LIKE,
    ADE20K_ID2LABEL_SUBSET,
)


def _make_bg(ch: int = 12, cw: int = 16, face: bool = False,
             person: bool = False) -> BGAnalysis:
    rng = np.random.default_rng(3)
    cp = 48
    f = lambda: rng.random((ch, cw)).astype(np.float32)
    face_mask = None
    if face:
        face_mask = np.zeros((ch, cw), dtype=bool)
        face_mask[2:4, 3:6] = True
    semantic = None
    if person:
        semantic = np.zeros((ch, cw), dtype=np.int32)
        semantic[8:10, 10:12] = 12  # person
    return BGAnalysis(
        bg_w=cw * cp, bg_h=ch * cp, cell_w=cw, cell_h=ch, cell_px=cp,
        edge_density=f(), saliency=f(), hue=f(), sat=f(), val=f(),
        grad_orient=rng.uniform(-math.pi, math.pi, (ch, cw)).astype(np.float32),
        face_mask=face_mask, semantic=semantic,
    )


def _make_obj(cid: str = "obj0") -> ObjAnalysis:
    return ObjAnalysis(
        catalog_id=cid,
        palette=[(0.1, 0.6, 0.7), (0.5, 0.3, 0.4), (0.8, 0.2, 0.9)],
        edge_orient=0.2, aspect=1.0, size_class="mid",
        palette_ext=[{"h": 0.1, "s": 0.6, "v": 0.7, "w": 1.0, "var": 0.02}],
    )


# ── build_forbidden_mask ─────────────────────────────────────────────────────

def test_forbidden_mask_none_se_vuota():
    bg = _make_bg()
    assert build_forbidden_mask(bg) is None
    assert build_forbidden_mask(bg, set()) is None


def test_forbidden_mask_unione():
    bg = _make_bg(face=True, person=True)
    manual = {(0, 0), (15, 11), (99, 99), (-1, 3)}  # ultime due fuori griglia
    mask = build_forbidden_mask(bg, manual)
    assert mask is not None
    # Volti
    assert mask[2:4, 3:6].all()
    # Person (semantic == 12)
    assert mask[8:10, 10:12].all()
    # Manuali dentro griglia (coords (cx, cy) -> mask[cy, cx])
    assert mask[0, 0] and mask[11, 15]
    # Fuori griglia ignorate senza errori; il resto libero
    assert not mask[5, 5]


def test_costanti_ade20k():
    """Fix audit #42 + person: id verificati sul mapping 0-based del checkpoint."""
    assert 12 in ADE20K_PERSON_LIKE
    assert 12 in ADE20K_PROHIBITED
    assert 9 not in ADE20K_WALL_LIKE      # grass NON e' un muro
    assert 25 not in ADE20K_TABLE_LIKE    # house NON e' un tavolo
    assert 24 in ADE20K_TABLE_LIKE        # shelf
    # Ogni id usato nei set chiave e' documentato nel subset
    for i in ADE20K_PERSON_LIKE | ADE20K_WALL_LIKE | ADE20K_TABLE_LIKE:
        assert i in ADE20K_ID2LABEL_SUBSET


# ── face_cell_mask (pura, no cv2/modelli) ────────────────────────────────────

def test_face_cell_mask_geometria():
    # Box 96x96 px con origine (96, 96) su celle 48px: celle 2..3 in x e y,
    # +25% dilatazione per lato -> da cella 1 a cella 4 incluse
    m = face_cell_mask([(96.0, 96.0, 192.0, 192.0)], cell_w=10, cell_h=10,
                       cell_px=48, dilate_frac=0.25)
    assert m.dtype == bool and m.shape == (10, 10)
    assert m[1:5, 1:5].all()
    assert not m[0, :].any() and not m[6:, :].any()


def test_face_cell_mask_clipping_e_degenerati():
    # Box fuori griglia in parte: clip senza errori; box degenere ignorato
    m = face_cell_mask([(-100.0, -100.0, 30.0, 30.0), (50.0, 50.0, 50.0, 50.0)],
                       cell_w=5, cell_h=5, cell_px=48)
    assert m[0, 0]
    assert int(m.sum()) < 25


# ── veto in _build_score_matrix ──────────────────────────────────────────────

def test_score_matrix_applica_forbidden():
    bg = _make_bg(face=True)
    obj = _make_obj()
    weights = _get_weights("medium", "real")
    occupied = np.ones((bg.cell_h, bg.cell_w), dtype=np.float32)
    mask = build_forbidden_mask(bg)
    np.random.seed(0)
    s = _build_score_matrix(bg, obj, weights, occupied, forbidden_mask=mask)
    assert np.all(s[mask] < SCORE_VETO_THRESHOLD)
    assert np.all(s[~mask] > SCORE_VETO_THRESHOLD)


def test_score_matrix_default_none_invariato():
    """Senza kwargs nuovi il risultato e' bit-identico al comportamento storico."""
    bg = _make_bg()
    obj = _make_obj()
    weights = _get_weights("hard", "real")
    occupied = np.random.default_rng(9).random((bg.cell_h, bg.cell_w)).astype(np.float32)
    np.random.seed(1)
    a = _build_score_matrix(bg, obj, weights, occupied)
    np.random.seed(1)
    b = _build_score_matrix(bg, obj, weights, occupied,
                            forbidden_mask=None, color_gate=None)
    assert np.array_equal(a, b)


# ── place_objects con maschera ───────────────────────────────────────────────

def test_place_objects_evita_zone_vietate_ed_e_deterministico():
    ch, cw = 14, 20
    bg = _make_bg(ch, cw)
    # Blocco vietato grande al centro (in coords (cx, cy))
    manual = {(cx, cy) for cx in range(8, 14) for cy in range(5, 10)}
    mask = build_forbidden_mask(bg, manual)
    obj = _make_obj()
    analyses = {"obj0": obj}
    entries = {"obj0": {"tags": [], "default_detection": "circle",
                        "default_radius": 20}}

    p1 = place_objects(bg, analyses, entries, count=8, difficulty="easy",
                       style="real", allowed_layers=["objects_mid"], seed=123,
                       forbidden_mask=mask)
    p2 = place_objects(bg, analyses, entries, count=8, difficulty="easy",
                       style="real", allowed_layers=["objects_mid"], seed=123,
                       forbidden_mask=mask)
    assert len(p1) == len(p2) > 0
    for a, b in zip(p1, p2):
        assert a.catalog_id == b.catalog_id
        assert abs(a.x - b.x) < 1e-6 and abs(a.y - b.y) < 1e-6

    # Nessun centro nell'INTERNO del blocco vietato (1 cella di margine per il
    # jitter sub-cella del refinement locale)
    cp = bg.cell_px
    for p in p1:
        ccx = int(p.x // cp)
        ccy = int(p.y // cp)
        inside_core = (9 <= ccx <= 12) and (6 <= ccy <= 8)
        assert not inside_core, f"oggetto dentro la zona vietata: cella ({ccx},{ccy})"
