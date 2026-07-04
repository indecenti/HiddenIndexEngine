"""
tests/test_bg_cache_v3.py

Schema v3 della cache BG: roundtrip dei nuovi tensori (face_mask, depth_grid),
isolamento dalle entry v2 (mai ritornate) e purge dello schema vecchio.
"""

from __future__ import annotations

import sqlite3

import numpy as np
import pytest

from editor.tools import bg_cache
from editor.tools.scatter_engine import BGAnalysis


def _make_bg(sha: str) -> BGAnalysis:
    ch, cw, cp = 6, 8, 48
    rng = np.random.default_rng(5)
    f = lambda: rng.random((ch, cw)).astype(np.float32)
    face = np.zeros((ch, cw), dtype=bool)
    face[1:3, 2:4] = True
    return BGAnalysis(
        bg_w=cw * cp, bg_h=ch * cp, cell_w=cw, cell_h=ch, cell_px=cp,
        edge_density=f(), saliency=f(), hue=f(), sat=f(), val=f(),
        grad_orient=f(),
        bg_sha256=sha,
        face_mask=face,
        depth_grid=f(),
    )


def test_schema_ver_v3():
    assert bg_cache.SCHEMA_VER == "v3.1"


def test_roundtrip_v3(tmp_path):
    sha = "a" * 64
    bg = _make_bg(sha)
    bg_cache.save(bg, model_tier=0, base_path=tmp_path,
                  face_mask=bg.face_mask, depth_grid=bg.depth_grid)
    loaded = bg_cache.load(sha, model_tier=0, base_path=tmp_path)
    assert loaded is not None
    assert np.array_equal(loaded["edge_density"], bg.edge_density)
    assert np.array_equal(loaded["face_mask"], bg.face_mask)
    assert np.array_equal(loaded["depth_grid"], bg.depth_grid)
    # Tier diverso -> miss
    assert bg_cache.load(sha, model_tier=2, base_path=tmp_path) is None


def test_v2_non_ritornata_e_purgata(tmp_path):
    sha = "b" * 64
    bg = _make_bg(sha)
    # Salva una entry regolare (v3), poi inietta una entry con schema v2
    bg_cache.save(bg, model_tier=0, base_path=tmp_path)
    db = bg_cache.db_path(tmp_path)
    con = sqlite3.connect(str(db))
    con.execute(
        "INSERT OR REPLACE INTO bg_analysis "
        "(bg_sha256, bg_w, bg_h, cell_px, cell_w, cell_h, model_tier, schema_ver) "
        "VALUES (?, 100, 100, 48, 2, 2, 1, 'v2')", (sha,))
    con.commit()
    con.close()

    # La entry v2 non viene mai letta (la SELECT filtra su SCHEMA_VER)
    assert bg_cache.load(sha, model_tier=1, base_path=tmp_path) is None
    # Il prossimo save (che passa da _connect) purga lo schema vecchio
    bg2 = _make_bg("c" * 64)
    bg_cache.save(bg2, model_tier=0, base_path=tmp_path)
    con = sqlite3.connect(str(db))
    rows = con.execute(
        "SELECT COUNT(*) FROM bg_analysis WHERE schema_ver != ?",
        (bg_cache.SCHEMA_VER,)).fetchone()[0]
    con.close()
    assert rows == 0


def test_campi_none_sopravvivono(tmp_path):
    """face_mask/depth_grid None -> roundtrip con None (colonne nullable)."""
    sha = "d" * 64
    bg = _make_bg(sha)
    bg.face_mask = None
    bg.depth_grid = None
    bg_cache.save(bg, model_tier=0, base_path=tmp_path)
    loaded = bg_cache.load(sha, model_tier=0, base_path=tmp_path)
    assert loaded is not None
    assert loaded["face_mask"] is None
    assert loaded["depth_grid"] is None
