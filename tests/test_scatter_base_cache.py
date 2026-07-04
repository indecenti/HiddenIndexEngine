"""
tests/test_scatter_base_cache.py

Regression guard per l'ottimizzazione "cache della score matrix per catalog_id"
(scatter_engine._build_base_score_matrix / _build_score_matrix).

INVARIANTE BLINDATA: la base object-invariant precalcolata e riusata deve produrre
una matrice di score IDENTICA al ricalcolo monolitico, a parita' di seed RNG. Se
qualcuno aggiunge alla base un termine che dipende dallo stato di piazzamento
(occupied) o consuma RNG, questi test devono fallire.

Non richiede pygame ne' asset: costruisce BGAnalysis/ObjAnalysis sintetici.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from editor.tools.scatter_engine import (
    BGAnalysis, ObjAnalysis, _get_weights,
    _build_base_score_matrix, _build_score_matrix,
    place_objects,
)


def _make_bg(with_ultra: bool) -> BGAnalysis:
    rng = np.random.default_rng(7)
    ch, cw, cp = 6, 8, 48
    f = lambda: rng.random((ch, cw)).astype(np.float32)

    semantic_score = semantic = clip_grid = None
    structural_orient = rng.uniform(-math.pi / 2, math.pi / 2, (ch, cw)).astype(np.float32)
    structural_orient[0, 0] = np.nan  # esercita il ramo NaN dell'allineamento forma
    contours = [{
        "cx": 120.0, "cy": 100.0, "w": 90.0, "h": 70.0,
        "hu": [1e-3, -2e-4, 3e-5, 1e-5, -4e-6, 2e-6, -1e-6],
    }]

    if with_ultra:
        ss = np.full((ch, cw), 0.4, dtype=np.float32)
        ss[0, :] = -1.0          # riga "cielo" proibita -> veto
        ss[ch - 1, :] = 1.0
        semantic_score = ss
        semantic = rng.integers(0, 20, (ch, cw)).astype(np.int32)
        clip_grid = rng.standard_normal((2, 3, 4)).astype(np.float32)

    return BGAnalysis(
        bg_w=cw * cp, bg_h=ch * cp, cell_w=cw, cell_h=ch, cell_px=cp,
        edge_density=f(), saliency=f(), hue=f(), sat=f(), val=f(),
        grad_orient=rng.uniform(-math.pi, math.pi, (ch, cw)).astype(np.float32),
        horizontal_score=f(), anchor_edge=f(),
        semantic=semantic, semantic_score=semantic_score, clip_grid=clip_grid,
        structural_orient=structural_orient, contours=contours,
        color_uniformity=f(),
    )


def _make_obj(with_ultra: bool, cid: str = "obj_test") -> ObjAnalysis:
    return ObjAnalysis(
        catalog_id=cid,
        palette=[(0.1, 0.6, 0.7), (0.5, 0.3, 0.4), (0.8, 0.2, 0.9)],
        edge_orient=0.4, aspect=1.2, size_class="mid",
        clip_emb=(np.array([0.2, -0.5, 0.3, 0.8], dtype=np.float32) if with_ultra else None),
        context_profile=({"floor": 0.25, "table": 0.22, "wall": 0.19} if with_ultra else None),
        shape={"compactness": 0.4, "aspect_real": 0.5, "axis_angle": 0.3,
               "hu": [1.1e-3, -2.1e-4, 2.9e-5, 1.1e-5, -3.9e-6, 2.1e-6, -1.1e-6],
               "support_bot": 0.5, "hang_top": 0.0},
        palette_ext=[
            {"h": 0.1, "s": 0.6, "v": 0.7, "w": 0.5, "var": 0.02},
            {"h": 0.5, "s": 0.1, "v": 0.4, "w": 0.3, "var": 0.05},
            {"h": 0.8, "s": 0.3, "v": 0.9, "w": 0.2, "var": 0.01},
        ],
    )


@pytest.mark.parametrize("with_ultra", [False, True], ids=["tier0", "ultra"])
def test_base_cache_equivalent_to_monolithic(with_ultra):
    """base precalcolata e riusata == ricalcolo interno, bit-identico."""
    bg = _make_bg(with_ultra)
    obj = _make_obj(with_ultra)
    occupied = np.random.default_rng(99).random((bg.cell_h, bg.cell_w)).astype(np.float32)
    weights = _get_weights("hard", "real")

    np.random.seed(0)
    a = _build_score_matrix(bg, obj, weights, occupied)              # base=None

    np.random.seed(0)
    base = _build_base_score_matrix(bg, obj, weights)
    base_snapshot = base.copy()
    b = _build_score_matrix(bg, obj, weights, occupied, base=base)   # base riusata

    assert np.array_equal(a, b)                  # equivalenza esatta
    assert np.array_equal(base, base_snapshot)   # base non mutata dal wrapper
    assert not np.array_equal(base, a)           # base priva di jitter/veto


@pytest.mark.parametrize("with_ultra", [False, True], ids=["tier0", "ultra"])
def test_deterministic_same_seed(with_ultra):
    bg = _make_bg(with_ultra)
    obj = _make_obj(with_ultra)
    occupied = np.random.default_rng(99).random((bg.cell_h, bg.cell_w)).astype(np.float32)
    weights = _get_weights("hard", "real")
    np.random.seed(0)
    a = _build_score_matrix(bg, obj, weights, occupied)
    np.random.seed(0)
    a2 = _build_score_matrix(bg, obj, weights, occupied)
    assert np.array_equal(a, a2)


def test_semantic_veto_hard_mask():
    """Le celle proibite (cielo/muro) sono -1e9 nel finale ma non nella base."""
    bg = _make_bg(with_ultra=True)
    obj = _make_obj(with_ultra=True)
    occupied = np.ones((bg.cell_h, bg.cell_w), dtype=np.float32)
    weights = _get_weights("hard", "real")
    np.random.seed(0)
    s = _build_score_matrix(bg, obj, weights, occupied)
    base = _build_base_score_matrix(bg, obj, weights)
    veto = bg.semantic_score <= -0.99
    assert np.all(s[veto] <= -1e8)     # vetate nel finale
    assert np.all(s[~veto] > -1e8)     # non vetate altrove
    assert np.all(base[veto] > -1e8)   # la base NON contiene il veto


def test_place_objects_uses_cache_and_is_deterministic(monkeypatch):
    """place_objects costruisce la base poche volte (cache) e resta deterministico."""
    bg = _make_bg(with_ultra=False)
    analyses, entries = {}, {}
    for i in range(4):
        analyses[f"obj{i}"] = _make_obj(False, cid=f"obj{i}")
        entries[f"obj{i}"] = {"tags": [], "default_detection": "circle", "default_radius": 24}

    import editor.tools.scatter_engine as se
    n_calls = {"v": 0}
    orig = se._build_base_score_matrix

    def counting(*a, **k):
        n_calls["v"] += 1
        return orig(*a, **k)

    monkeypatch.setattr(se, "_build_base_score_matrix", counting)
    placed = se.place_objects(bg, analyses, entries, count=8, difficulty="medium",
                              style="real", allowed_layers=["objects_low"], seed=42)
    assert len(placed) > 0
    # Senza cache sarebbe ~1 build per tentativo (centinaia). Con cache: <= 2*pool
    # (viability gate + miss del loop, una per id distinto).
    assert n_calls["v"] <= 2 * len(analyses)

    monkeypatch.setattr(se, "_build_base_score_matrix", orig)
    p1 = se.place_objects(bg, analyses, entries, count=8, difficulty="medium",
                          style="real", allowed_layers=["objects_low"], seed=123)
    p2 = se.place_objects(bg, analyses, entries, count=8, difficulty="medium",
                          style="real", allowed_layers=["objects_low"], seed=123)
    assert len(p1) == len(p2)
    for a, b in zip(p1, p2):
        assert a.catalog_id == b.catalog_id
        assert abs(a.x - b.x) < 1e-6 and abs(a.y - b.y) < 1e-6
