"""
tests/test_scatter_swap.py

Regression guard per A5: memoizzazione di _score_at dentro _swap_optimize.
La cache (chiave (catalog_id, cy, cx)) deve restituire score IDENTICI, quindi gli
swap accettati e l'output devono coincidere bit-per-bit con la versione non
memoizzata. Confronto contro una reimplementazione di riferimento del codice
pre-cache.
"""

from __future__ import annotations

import copy

import numpy as np

from editor.tools.scatter_engine import (
    PlacedObject, ObjAnalysis, BGAnalysis, _color_similarity, _swap_optimize,
    _get_weights,
)


def _make_bg():
    """BGAnalysis minimale: _swap_optimize usa solo edge/sal/hue/sat/val +
    horizontal_score + semantic_score."""
    rng = np.random.default_rng(7)
    ch, cw, cp = 6, 8, 48
    f = lambda: rng.random((ch, cw)).astype(np.float32)
    ss = np.full((ch, cw), 0.4, dtype=np.float32)
    ss[0, :] = -1.0
    return BGAnalysis(
        bg_w=cw * cp, bg_h=ch * cp, cell_w=cw, cell_h=ch, cell_px=cp,
        edge_density=f(), saliency=f(), hue=f(), sat=f(), val=f(),
        grad_orient=f(), horizontal_score=f(), semantic_score=ss,
    )


def _ref_swap_optimize(placed, bg, catalog_analyses, weights, max_iters=2):
    """Copia esatta della logica pre-memoizzazione (nessuna cache)."""
    def _score_at(obj_an, cy, cx):
        s = 0.30 * float(bg.edge_density[cy, cx])
        s += 0.30 * float(1.0 - bg.saliency[cy, cx])
        s += 0.15 * _color_similarity(obj_an.palette, float(bg.hue[cy, cx]),
                                       float(bg.sat[cy, cx]), float(bg.val[cy, cx]))
        if bg.horizontal_score is not None:
            s += 0.15 * float(bg.horizontal_score[cy, cx])
        if bg.semantic_score is not None:
            s += 0.10 * max(0.0, float(bg.semantic_score[cy, cx]))
        return s

    for _ in range(max_iters):
        improved = 0
        for i in range(len(placed)):
            for j in range(i + 1, len(placed)):
                obj_i, obj_j = placed[i], placed[j]
                cell_px = bg.cell_px
                cyi = int(min(bg.cell_h - 1, max(0, obj_i.y / cell_px)))
                cxi = int(min(bg.cell_w - 1, max(0, obj_i.x / cell_px)))
                cyj = int(min(bg.cell_h - 1, max(0, obj_j.y / cell_px)))
                cxj = int(min(bg.cell_w - 1, max(0, obj_j.x / cell_px)))
                an_i = catalog_analyses.get(obj_i.catalog_id)
                an_j = catalog_analyses.get(obj_j.catalog_id)
                if an_i is None or an_j is None:
                    continue
                cur = _score_at(an_i, cyi, cxi) + _score_at(an_j, cyj, cxj)
                swap = _score_at(an_j, cyi, cxi) + _score_at(an_i, cyj, cxj)
                if swap > cur + 0.02:
                    placed[i] = PlacedObject(
                        catalog_id=obj_j.catalog_id, x=obj_i.x, y=obj_i.y,
                        scale=obj_j.scale, rotation=obj_i.rotation,
                        flip_x=obj_j.flip_x, flip_y=obj_j.flip_y,
                        alpha=obj_j.alpha, color_filter=obj_j.color_filter,
                        detection_type=obj_j.detection_type, width=obj_j.width,
                        height=obj_j.height, radius=obj_j.radius, layer=obj_i.layer,
                        visibility_score=_score_at(an_j, cyi, cxi))
                    placed[j] = PlacedObject(
                        catalog_id=obj_i.catalog_id, x=obj_j.x, y=obj_j.y,
                        scale=obj_i.scale, rotation=obj_j.rotation,
                        flip_x=obj_i.flip_x, flip_y=obj_i.flip_y,
                        alpha=obj_i.alpha, color_filter=obj_i.color_filter,
                        detection_type=obj_i.detection_type, width=obj_i.width,
                        height=obj_i.height, radius=obj_i.radius, layer=obj_j.layer,
                        visibility_score=_score_at(an_i, cyj, cxj))
                    improved += 1
        if improved == 0:
            break
    return placed


def _make_scenario(n: int):
    bg = _make_bg()
    rng = np.random.default_rng(42)
    analyses, placed = {}, []
    for k in range(n):
        cid = f"c{k}"
        # palette dominante distinta per oggetto (cosi' gli swap cambiano davvero)
        h = (k * 0.137) % 1.0
        analyses[cid] = ObjAnalysis(
            catalog_id=cid,
            palette=[(h, 0.7, 0.6), ((h + 0.3) % 1.0, 0.4, 0.5)],
            edge_orient=0.0, aspect=1.0, size_class="mid",
        )
        cw, ch, cp = bg.cell_w, bg.cell_h, bg.cell_px
        x = ((k % cw) + 0.5) * cp
        y = (((k // cw) % ch) + 0.5) * cp
        placed.append(PlacedObject(
            catalog_id=cid, x=float(x), y=float(y), scale=1.0, rotation=0.0,
            flip_x=False, flip_y=False, alpha=255, color_filter=(255, 255, 255),
            detection_type="circle", width=40.0, height=40.0, radius=20.0,
            layer="objects_low", visibility_score=0.0))
    return bg, analyses, placed


def test_swap_memoization_matches_reference():
    bg, analyses, placed = _make_scenario(n=16)
    weights = _get_weights("hard", "real")
    got = _swap_optimize(copy.deepcopy(placed), bg, analyses, weights, max_iters=2)
    ref = _ref_swap_optimize(copy.deepcopy(placed), bg, analyses, weights, max_iters=2)
    assert len(got) == len(ref)
    for g, r in zip(got, ref):
        assert g == r  # dataclass eq su tutti i campi, visibility_score incluso


def test_swap_triggers_some_swaps():
    # Sanity: lo scenario produce almeno uno swap (altrimenti il test sopra e' vuoto)
    bg, analyses, placed = _make_scenario(n=16)
    weights = _get_weights("hard", "real")
    before = [p.catalog_id for p in copy.deepcopy(placed)]
    after = [p.catalog_id for p in _swap_optimize(copy.deepcopy(placed), bg,
                                                  analyses, weights, max_iters=2)]
    assert before != after
