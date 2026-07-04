"""
tests/test_scatter_vectorize.py

Regression guard per le vettorizzazioni A2 (loop per-cella -> numpy):
  - bg_cache.compute_texture_entropy
  - bg_cache._orient_accumulate (rasterizzazione strutturale)
  - scatter_engine._dominant_class_per_cell (moda semantica)

Ogni test confronta la versione vettorizzata con una REIMPLEMENTAZIONE DI
RIFERIMENTO del vecchio doppio loop, su input sintetico. Se una vettorizzazione
diverge dal comportamento originale, il test fallisce.
"""

from __future__ import annotations

import math

import numpy as np

import editor.tools.bg_cache as bc
from editor.tools.scatter_engine import _dominant_class_per_cell


CH, CW, CP = 5, 7, 48  # griglia 5x7, immagine 240x336


# ── RIFERIMENTI (copia esatta della logica pre-vettorizzazione) ──────────────

def _ref_texture_entropy(rgb, ch, cw, cp):
    if bc._HAS_CV2:
        import cv2
        gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    else:
        gray = (0.299 * rgb[..., 0] + 0.587 * rgb[..., 1]
                + 0.114 * rgb[..., 2]).astype(np.uint8)
    out = np.zeros((ch, cw), dtype=np.float32)
    bin_edges = np.linspace(0, 256, 9)
    for cy in range(ch):
        for cx in range(cw):
            block = gray[cy * cp:(cy + 1) * cp, cx * cp:(cx + 1) * cp]
            hist, _ = np.histogram(block, bins=bin_edges)
            total = hist.sum()
            if total > 0:
                p = hist / total
                p = p[p > 0]
                out[cy, cx] = -(p * np.log2(p)).sum() / 3.0
    return np.clip(out, 0.0, 1.0)


def _ref_orient(lines, ch, cw, cp):
    out = np.full((ch, cw), np.nan, dtype=np.float32)
    sum_cos = np.zeros((ch, cw), dtype=np.float32)
    sum_sin = np.zeros((ch, cw), dtype=np.float32)
    weight = np.zeros((ch, cw), dtype=np.float32)
    for line in lines.reshape(-1, 4):
        x1, y1, x2, y2 = line
        ang = math.atan2(y2 - y1, x2 - x1)
        if ang > math.pi / 2: ang -= math.pi
        if ang < -math.pi / 2: ang += math.pi
        length = math.hypot(x2 - x1, y2 - y1)
        steps = max(2, int(length / (cp / 2)))
        for k in range(steps + 1):
            t = k / steps
            x = int(x1 + t * (x2 - x1))
            y = int(y1 + t * (y2 - y1))
            cx, cy = x // cp, y // cp
            if 0 <= cy < ch and 0 <= cx < cw:
                sum_cos[cy, cx] += math.cos(2 * ang) * length / steps
                sum_sin[cy, cx] += math.sin(2 * ang) * length / steps
                weight[cy, cx] += length / steps
    mask = weight > 1e-6
    out[mask] = 0.5 * np.arctan2(sum_sin[mask], sum_cos[mask])
    return out


def _ref_dominant(sr, ch, cw, cp):
    out = np.zeros((ch, cw), dtype=np.int32)
    for cyi in range(ch):
        for cxi in range(cw):
            block = sr[cyi * cp:(cyi + 1) * cp, cxi * cp:(cxi + 1) * cp]
            flat = block.flatten()
            if flat.size > 0:
                out[cyi, cxi] = int(np.bincount(flat).argmax())
    return out


# ── TEST ─────────────────────────────────────────────────────────────────────

def test_texture_entropy_matches_reference():
    rng = np.random.default_rng(11)
    rgb = rng.integers(0, 256, (CH * CP, CW * CP, 3), dtype=np.uint8)
    got = bc.compute_texture_entropy(rgb, CH, CW, CP)
    ref = _ref_texture_entropy(rgb, CH, CW, CP)
    assert got.shape == (CH, CW)
    assert np.allclose(got, ref, atol=1e-6), np.abs(got - ref).max()


def test_texture_entropy_uniform_block_is_zero():
    # Un blocco a luminanza costante ha entropia 0 (un solo bin popolato).
    rgb = np.full((CP, CP, 3), 128, dtype=np.uint8)
    got = bc.compute_texture_entropy(rgb, 1, 1, CP)
    assert float(got[0, 0]) == 0.0


def test_orient_accumulate_matches_reference():
    rng = np.random.default_rng(5)
    W, H = CW * CP, CH * CP
    lines = np.stack([
        rng.integers(0, W, 40), rng.integers(0, H, 40),
        rng.integers(0, W, 40), rng.integers(0, H, 40),
    ], axis=1).astype(np.int32)
    got = bc._orient_accumulate(lines, CH, CW, CP)
    ref = _ref_orient(lines, CH, CW, CP)
    # La maschera NaN (celle senza linee) deve essere IDENTICA: le celle colpite
    # hanno weight >> 1e-6, nessun caso borderline.
    assert np.array_equal(np.isnan(got), np.isnan(ref))
    # Gli angoli differiscono al piu' di ~1e-6 (ULP float32): np.add.at arrotonda
    # in modo leggermente diverso dal += sequenziale. Numericamente equivalente.
    assert np.allclose(got, ref, atol=1e-5, equal_nan=True), np.nanmax(np.abs(got - ref))


def test_dominant_class_matches_reference():
    rng = np.random.default_rng(3)
    sr = rng.integers(0, 25, (CH * CP, CW * CP)).astype(np.int32)
    got = _dominant_class_per_cell(sr, CH, CW, CP)
    ref = _ref_dominant(sr, CH, CW, CP)
    assert np.array_equal(got, ref)


def test_dominant_class_tiebreak_lowest_id():
    # Cella 48x48: meta' classe 2, meta' classe 9 -> pari conteggio -> vince 2.
    block = np.empty((CP, CP), dtype=np.int32)
    block[:, :CP // 2] = 9
    block[:, CP // 2:] = 2
    got = _dominant_class_per_cell(block, 1, 1, CP)
    assert int(got[0, 0]) == 2
