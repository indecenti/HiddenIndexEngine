"""
editor/tools/object_palette.py

Palette estesa per oggetti del catalogo (k=8 colori dominanti con frequency
e variance), persistita in engine/data/object_profiles.db (colonna palette_ext).

A differenza della palette top-3 storica (usata da scatter_engine), la palette
estesa cattura distribuzione cromatica REALE dell'icona e permette al
color_similarity di pesare i contributi per frequency.

Struttura JSON salvata:
  [
    {"h": 0.0..1.0, "s": 0.0..1.0, "v": 0.0..1.0,  # HSV centroide
     "w": 0.0..1.0,                                  # frequency (frazione pixel)
     "var": 0.0..1.0},                               # varianza intra-cluster (RGB norm)
    ...
  ]
Ordinata per w decrescente. Max PALETTE_K elementi.
"""

from __future__ import annotations

import json
import logging
import math
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np

log = logging.getLogger(__name__)

try:
    import cv2
    _HAS_CV2 = True
except Exception:
    _HAS_CV2 = False

PALETTE_K = 8                  # numero cluster k-means
PALETTE_VERSION = "v1"
OBJ_PROFILES_DB = "engine/data/object_profiles.db"


# ─────────────────────────────────────────────────────────────────────────────
# CORE: extraction
# ─────────────────────────────────────────────────────────────────────────────

def _kmeans_weighted_rgb(pixels_rgb: np.ndarray, k: int, iters: int = 10
                         ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """K-means RGB con init++ . Restituisce (centers (k,3), weights (k,), var (k,))."""
    n = len(pixels_rgb)
    if n == 0:
        return np.zeros((k, 3), np.float32), np.zeros(k, np.float32), np.zeros(k, np.float32)
    if n <= k:
        centers = np.zeros((k, 3), np.float32)
        centers[:n] = pixels_rgb
        weights = np.zeros(k, np.float32); weights[:n] = 1.0 / n
        return centers, weights, np.zeros(k, np.float32)

    rng = np.random.default_rng(42)
    pix = pixels_rgb.astype(np.float32)
    # k-means++ seeding
    idx0 = int(rng.integers(0, n))
    centers = [pix[idx0]]
    for _ in range(k - 1):
        diffs = pix[:, None, :] - np.asarray(centers)[None, :, :]
        d2 = (diffs * diffs).sum(axis=2).min(axis=1) + 1e-6
        probs = d2 / d2.sum()
        idx = int(rng.choice(n, p=probs))
        centers.append(pix[idx])
    centers = np.stack(centers).astype(np.float32)

    labels = np.zeros(n, dtype=np.int32)
    for _ in range(iters):
        diffs = pix[:, None, :] - centers[None, :, :]
        dists2 = (diffs * diffs).sum(axis=2)
        labels = dists2.argmin(axis=1)
        for ki in range(k):
            m = labels == ki
            if m.any():
                centers[ki] = pix[m].mean(axis=0)

    # Frequency + variance per cluster
    weights = np.zeros(k, np.float32)
    variances = np.zeros(k, np.float32)
    for ki in range(k):
        m = labels == ki
        cnt = int(m.sum())
        weights[ki] = cnt / n
        if cnt > 1:
            spread = pix[m] - centers[ki]
            # varianza media in spazio RGB normalizzato 0..1 (norm su 255^2 * 3)
            variances[ki] = float((spread * spread).sum(axis=1).mean() / (255.0 * 255.0 * 3.0))
    return centers, weights, variances


@dataclass
class ColorCluster:
    h: float  # 0..1
    s: float
    v: float
    w: float  # frequency
    var: float


def compute_palette_extended(icon_path: Path, k: int = PALETTE_K) -> Optional[list[ColorCluster]]:
    """Estrae palette estesa da un PNG con alpha.

    - Pixel "puri" via alpha cascade 200 -> 128 -> 64
    - K-means RGB con k=8, k-means++ init
    - Conversione a HSV alla fine
    - Ordinata per weight desc
    """
    try:
        from PIL import Image
        img = Image.open(icon_path).convert("RGBA")
    except Exception as e:
        log.debug(f"[PALETTE] cannot open {icon_path}: {e}")
        return None

    arr = np.array(img)
    if arr.shape[-1] < 4:
        return None
    alpha = arr[..., 3]
    rgb = arr[..., :3]
    mask = alpha > 200
    if mask.sum() < 100:
        mask = alpha > 128
    if mask.sum() < 50:
        mask = alpha > 64
    if not mask.any():
        return None

    pixels = rgb[mask]
    # Downsample per perf
    if len(pixels) > 8000:
        rng = np.random.default_rng(0)
        idx = rng.choice(len(pixels), 8000, replace=False)
        pixels = pixels[idx]

    centers_rgb, weights, variances = _kmeans_weighted_rgb(pixels.astype(np.float32), k=k)

    # Convert centers to HSV
    if _HAS_CV2:
        hsv = cv2.cvtColor(centers_rgb.reshape(-1, 1, 3).astype(np.uint8), cv2.COLOR_RGB2HSV)
        hsv = hsv.reshape(-1, 3).astype(np.float32)
    else:
        # numpy fallback
        c = centers_rgb / 255.0
        mx = c.max(axis=1)
        mn = c.min(axis=1)
        d = mx - mn
        h = np.zeros(len(c), dtype=np.float32)
        for i in range(len(c)):
            if d[i] < 1e-6:
                h[i] = 0
            elif mx[i] == c[i, 0]:
                h[i] = ((c[i, 1] - c[i, 2]) / d[i]) % 6
            elif mx[i] == c[i, 1]:
                h[i] = ((c[i, 2] - c[i, 0]) / d[i]) + 2
            else:
                h[i] = ((c[i, 0] - c[i, 1]) / d[i]) + 4
        h = h * 30  # 0..180 OpenCV
        s = np.where(mx > 0, d / np.maximum(mx, 1e-6), 0) * 255
        v = mx * 255
        hsv = np.stack([h, s, v], axis=1).astype(np.float32)

    clusters = []
    for i in range(len(centers_rgb)):
        if weights[i] < 0.005:  # cluster degenerati (<0.5% pixel) scartati
            continue
        clusters.append(ColorCluster(
            h=float(hsv[i, 0]) / 180.0,
            s=float(hsv[i, 1]) / 255.0,
            v=float(hsv[i, 2]) / 255.0,
            w=float(weights[i]),
            var=float(variances[i]),
        ))
    clusters.sort(key=lambda c: -c.w)
    return clusters


# ─────────────────────────────────────────────────────────────────────────────
# DB (estende object_profiles.db con colonne palette_ext + palette_version)
# ─────────────────────────────────────────────────────────────────────────────

def ensure_palette_columns(base_path: Path):
    """Aggiunge colonne palette_ext (TEXT) e palette_version (TEXT) se mancanti."""
    p = base_path / OBJ_PROFILES_DB
    if not p.exists():
        log.warning(f"[PALETTE] {p} non esiste, build profiles prima")
        return
    con = sqlite3.connect(str(p))
    try:
        cur = con.cursor()
        cur.execute("PRAGMA table_info(object_profile)")
        cols = {row[1] for row in cur.fetchall()}
        added = 0
        for col, typ in [("palette_ext", "TEXT"), ("palette_version", "TEXT")]:
            if col not in cols:
                try:
                    cur.execute(f"ALTER TABLE object_profile ADD COLUMN {col} {typ}")
                    added += 1
                except Exception as e:
                    log.warning(f"[PALETTE] migrate fail {col}: {e}")
        if added:
            con.commit()
            log.info(f"[PALETTE] migrate object_profile: +{added} cols")
    finally:
        con.close()


def save_palette(base_path: Path, catalog_id: str, style: str,
                  clusters: list[ColorCluster]):
    """Persiste palette estesa per un oggetto. UPSERT semplice."""
    p = base_path / OBJ_PROFILES_DB
    con = sqlite3.connect(str(p))
    try:
        payload = json.dumps([
            {"h": c.h, "s": c.s, "v": c.v, "w": c.w, "var": c.var}
            for c in clusters
        ])
        cur = con.cursor()
        # Verifica esistenza riga
        cur.execute("SELECT 1 FROM object_profile WHERE catalog_id = ?", (catalog_id,))
        if cur.fetchone():
            cur.execute("""
                UPDATE object_profile
                SET palette_ext = ?, palette_version = ?
                WHERE catalog_id = ?
            """, (payload, PALETTE_VERSION, catalog_id))
        else:
            # INSERT minimo: solo palette + chiavi obbligatorie
            cur.execute("""
                INSERT INTO object_profile
                  (catalog_id, style, prompts_ver, visual_emb, profile,
                   palette_ext, palette_version)
                VALUES (?, ?, 'v1', x'', '{}', ?, ?)
            """, (catalog_id, style, payload, PALETTE_VERSION))
        con.commit()
    finally:
        con.close()


def get_palettes_for_style(style: str, base_path: Path) -> dict[str, list[dict]]:
    """Bulk lookup palette estesa per stile. Restituisce dict[cid -> list[dict]].

    Ogni dict cluster: {"h": .., "s": .., "v": .., "w": .., "var": ..}
    """
    p = base_path / OBJ_PROFILES_DB
    if not p.exists():
        return {}
    con = sqlite3.connect(str(p))
    out = {}
    try:
        cur = con.cursor()
        cur.execute("PRAGMA table_info(object_profile)")
        cols = {row[1] for row in cur.fetchall()}
        if "palette_ext" not in cols:
            return {}
        for row in cur.execute("""
            SELECT catalog_id, palette_ext
            FROM object_profile
            WHERE style = ? AND palette_ext IS NOT NULL AND palette_version IS NOT NULL
        """, (style,)):
            try:
                out[row[0]] = json.loads(row[1])
            except Exception:
                continue
        return out
    finally:
        con.close()


# ─────────────────────────────────────────────────────────────────────────────
# Build batch (per script di setup)
# ─────────────────────────────────────────────────────────────────────────────

def build_palettes_for_catalog(catalog: list[dict], style: str, base_path: Path,
                                overwrite: bool = False,
                                progress_cb=None) -> int:
    """Pre-compute palette estesa per oggetti dello stile."""
    ensure_palette_columns(base_path)
    p = base_path / OBJ_PROFILES_DB
    con = sqlite3.connect(str(p))
    cur = con.cursor()

    style_pool = [c for c in catalog if c.get("style", "real") == style]
    if not style_pool:
        con.close()
        return 0

    existing = set()
    if not overwrite:
        for row in cur.execute(
            "SELECT catalog_id FROM object_profile WHERE palette_version = ?",
            (PALETTE_VERSION,)
        ):
            existing.add(row[0])
    to_process = [c for c in style_pool if c["id"] not in existing]
    log.info(f"[PALETTE] {len(to_process)}/{len(style_pool)} da processare per '{style}'")

    con.close()

    t0 = time.time()
    n_done = 0
    for i, entry in enumerate(to_process):
        cid = entry["id"]
        icon_rel = entry.get("icon", "")
        candidates = [
            base_path / "engine" / "assets" / icon_rel,
            base_path / icon_rel,
        ]
        icon_path = next((p for p in candidates if p.exists()), None)
        if not icon_path:
            continue
        clusters = compute_palette_extended(icon_path)
        if not clusters:
            continue
        save_palette(base_path, cid, style, clusters)
        n_done += 1
        if progress_cb and (i + 1) % 50 == 0:
            try: progress_cb(i + 1, len(to_process))
            except Exception: pass

    dt = time.time() - t0
    log.info(f"[PALETTE] build done '{style}': {n_done} processed in {dt:.1f}s")
    return n_done
