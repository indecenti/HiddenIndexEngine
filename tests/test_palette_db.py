"""
tests/test_palette_db.py

Regression guard per A6: save_palette puo' riusare una connessione SQLite condivisa
(uso batch in build_palettes_for_catalog) invece di aprirne una per oggetto. Il
risultato su disco deve essere identico al percorso con connessione propria.
"""

from __future__ import annotations

import sqlite3

from editor.tools.object_palette import (
    save_palette, get_palettes_for_style, ensure_palette_columns,
    ColorCluster, OBJ_PROFILES_DB,
)


def test_save_palette_shared_vs_own_connection(tmp_path):
    ensure_palette_columns(tmp_path)
    clusters = [
        ColorCluster(h=0.10, s=0.50, v=0.70, w=0.60, var=0.02),
        ColorCluster(h=0.40, s=0.20, v=0.50, w=0.30, var=0.05),
    ]

    # Percorso 1: connessione propria (con=None)
    save_palette(tmp_path, "cidA", "real", clusters)

    # Percorso 2: connessione condivisa (uso batch)
    con = sqlite3.connect(str(tmp_path / OBJ_PROFILES_DB))
    try:
        save_palette(tmp_path, "cidB", "real", clusters, con=con)
    finally:
        con.close()

    got = get_palettes_for_style("real", tmp_path)
    assert "cidA" in got and "cidB" in got
    assert got["cidA"] == got["cidB"]                  # stesso payload
    assert got["cidA"][0]["h"] == 0.10
    assert got["cidA"][1]["w"] == 0.30


def test_save_palette_shared_connection_upsert(tmp_path):
    """Riusando la connessione, un secondo save sullo stesso id fa UPDATE (no dup)."""
    ensure_palette_columns(tmp_path)
    con = sqlite3.connect(str(tmp_path / OBJ_PROFILES_DB))
    try:
        save_palette(tmp_path, "cid", "real",
                     [ColorCluster(0.1, 0.5, 0.7, 0.6, 0.02)], con=con)
        save_palette(tmp_path, "cid", "real",
                     [ColorCluster(0.9, 0.1, 0.2, 0.4, 0.01)], con=con)
        n = con.execute(
            "SELECT COUNT(*) FROM object_profile WHERE catalog_id='cid'").fetchone()[0]
    finally:
        con.close()
    assert n == 1
    got = get_palettes_for_style("real", tmp_path)
    assert got["cid"][0]["h"] == 0.9  # ultimo valore
