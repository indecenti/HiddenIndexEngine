"""
editor/tools/bg_cache.py

BG analysis cache + ADVANCED METRICS specifiche per scatter intelligente.

Persiste l'intera BGAnalysis in SQLite (BLOB compressi), indicizzata per:
  - SHA256 dell'immagine BG (byte-level)
  - tier IA usato (0=classic, 1=light, 2=pro, 3=ultra)
  - versione dello schema metriche

NUOVE METRICHE AVANZATE (mai viste in editor HO):
  1. hideability_map     : score per cella "quanto si nasconde bene un oggetto qui"
                          combinazione di texture entropy + edge density + saliency penalty
  2. placement_zones     : cluster di celle contigue con stessa classe ADE20K (poligoni)
  3. anchor_points       : punti chiave geometrici (corner detector Harris + edge intersection)
  4. zone_palettes       : palette HSV dominante per ogni zona semantica (per color match)
  5. texture_entropy     : Shannon entropy della texture per cella (zone "rumorose" sono buone)
  6. local_complexity    : Laplacian variance per cella (focus areas alto = dettaglio)

Schema:
    CREATE TABLE bg_analysis (
        bg_sha256       TEXT NOT NULL,
        bg_w INTEGER, bg_h INTEGER,
        cell_px INTEGER, cell_w INTEGER, cell_h INTEGER,
        model_tier      INTEGER NOT NULL,
        schema_ver      TEXT NOT NULL,
        edge_density    BLOB, saliency       BLOB, hue BLOB, sat BLOB, val BLOB,
        grad_orient     BLOB,
        horizontal_score BLOB, anchor_edge BLOB, normal_orient BLOB,
        semantic        BLOB, semantic_score BLOB, clip_grid BLOB,
        hideability_map BLOB, texture_entropy BLOB, local_complexity BLOB,
        anchor_points_json TEXT, zone_palettes_json TEXT,
        computed_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (bg_sha256, model_tier, schema_ver)
    );
"""

from __future__ import annotations

import hashlib
import io
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

DB_REL_PATH = "engine/data/bg_cache.db"
SCHEMA_VER = "v2"

try:
    import cv2
    _HAS_CV2 = True
except Exception:
    _HAS_CV2 = False


# ─────────────────────────────────────────────────────────────────────────────
# UTILS
# ─────────────────────────────────────────────────────────────────────────────

def compute_bg_sha256(bg_surface) -> str:
    """SHA256 dei byte raw RGB del BG. Identifica univocamente l'immagine."""
    import pygame
    arr = pygame.surfarray.array3d(bg_surface).swapaxes(0, 1)  # (H, W, 3) uint8
    return hashlib.sha256(arr.tobytes()).hexdigest()


def _np_to_blob(arr: Optional[np.ndarray]) -> Optional[bytes]:
    """Serializza un ndarray in bytes (npy format), None se arr None."""
    if arr is None:
        return None
    buf = io.BytesIO()
    np.save(buf, arr, allow_pickle=False)
    return buf.getvalue()


def _blob_to_np(blob: Optional[bytes]) -> Optional[np.ndarray]:
    if blob is None:
        return None
    return np.load(io.BytesIO(blob), allow_pickle=False)


# ─────────────────────────────────────────────────────────────────────────────
# ADVANCED METRICS (specifiche per scatter)
# ─────────────────────────────────────────────────────────────────────────────

def compute_texture_entropy(rgb: np.ndarray, cell_h: int, cell_w: int, cell_px: int) -> np.ndarray:
    """Per ogni cella, Shannon entropy dell'istogramma di luminanza (8 bin).

    Risultato: (cell_h, cell_w) float32 0..1 normalizzato. Alta entropia = zona
    "rumorosa" dove gli oggetti si nascondono bene.
    """
    if _HAS_CV2:
        gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    else:
        gray = (0.299 * rgb[..., 0] + 0.587 * rgb[..., 1] + 0.114 * rgb[..., 2]).astype(np.uint8)
    out = np.zeros((cell_h, cell_w), dtype=np.float32)
    bin_edges = np.linspace(0, 256, 9)
    for cy in range(cell_h):
        for cx in range(cell_w):
            block = gray[cy*cell_px:(cy+1)*cell_px, cx*cell_px:(cx+1)*cell_px]
            hist, _ = np.histogram(block, bins=bin_edges)
            total = hist.sum()
            if total > 0:
                p = hist / total
                p = p[p > 0]
                ent = -(p * np.log2(p)).sum()
                out[cy, cx] = ent / 3.0  # max entropy 8 bins = log2(8) = 3
    return np.clip(out, 0.0, 1.0)


def compute_local_complexity(rgb: np.ndarray, cell_h: int, cell_w: int, cell_px: int) -> np.ndarray:
    """Laplacian variance per cella. Alta = zona "in focus" con tanti dettagli.

    Risultato: (cell_h, cell_w) float32 0..1 normalizzato.
    """
    if _HAS_CV2:
        gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY).astype(np.float32)
        lap = cv2.Laplacian(gray, cv2.CV_32F, ksize=3)
        lap_sq = lap * lap
    else:
        gray = (0.299 * rgb[..., 0] + 0.587 * rgb[..., 1] + 0.114 * rgb[..., 2]).astype(np.float32)
        # Diff lineare come fallback
        dx = np.abs(np.diff(gray, axis=1, prepend=gray[:, :1]))
        dy = np.abs(np.diff(gray, axis=0, prepend=gray[:1, :]))
        lap_sq = (dx + dy) ** 2
    h, w = lap_sq.shape
    h_eff = (cell_h * cell_px); w_eff = (cell_w * cell_px)
    lap_sq = lap_sq[:h_eff, :w_eff]
    reshaped = lap_sq.reshape(cell_h, cell_px, cell_w, cell_px)
    var = reshaped.var(axis=(1, 3))
    # Normalizza con max osservato
    vmax = var.max() if var.max() > 1e-6 else 1.0
    return (var / vmax).astype(np.float32)


def compute_hideability(edge_density: np.ndarray, saliency: np.ndarray,
                        texture_entropy: np.ndarray, local_complexity: np.ndarray) -> np.ndarray:
    """Score "quanto un oggetto si nasconde bene qui" 0..1.

    Combinazione esperta:
    - +edge_density (alta = molto rumore visivo, nasconde)
    - +texture_entropy (alta = molta varianza = scarso pattern preciso)
    - +local_complexity (alta = molti micro-dettagli)
    - -saliency (bassa = occhio non guarda li')
    """
    score = (
        0.35 * edge_density
        + 0.30 * texture_entropy
        + 0.20 * local_complexity
        + 0.15 * (1.0 - saliency)
    )
    return np.clip(score, 0.0, 1.0).astype(np.float32)


def compute_structural_orient(rgb: np.ndarray, cell_h: int, cell_w: int, cell_px: int) -> np.ndarray:
    """Per ogni cella, calcola angolo DOMINANTE delle linee strutturali via HoughLinesP.

    Una mensola orizzontale → angolo ~0. Un muro verticale → ~pi/2.
    Restituisce (cell_h, cell_w) float32 in [-pi/2, pi/2]. NaN dove no linee.
    """
    out = np.full((cell_h, cell_w), np.nan, dtype=np.float32)
    if not _HAS_CV2:
        return out
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    edges = cv2.Canny(gray, 50, 150, apertureSize=3)
    lines = cv2.HoughLinesP(edges, rho=1, theta=np.pi/180, threshold=80,
                            minLineLength=cell_px, maxLineGap=cell_px // 2)
    if lines is None:
        return out
    # Per ogni cella accumula somma vettoriale degli angoli (mod pi)
    sum_cos = np.zeros((cell_h, cell_w), dtype=np.float32)
    sum_sin = np.zeros((cell_h, cell_w), dtype=np.float32)
    weight = np.zeros((cell_h, cell_w), dtype=np.float32)
    for line in lines.reshape(-1, 4):
        x1, y1, x2, y2 = line
        ang = math.atan2(y2 - y1, x2 - x1)
        # Mod pi (l'asse, non il vettore)
        if ang > math.pi / 2: ang -= math.pi
        if ang < -math.pi / 2: ang += math.pi
        length = math.hypot(x2 - x1, y2 - y1)
        # Rasterizza segmento e accumula per cella
        steps = max(2, int(length / (cell_px / 2)))
        for k in range(steps + 1):
            t = k / steps
            x = int(x1 + t * (x2 - x1))
            y = int(y1 + t * (y2 - y1))
            cx, cy = x // cell_px, y // cell_px
            if 0 <= cy < cell_h and 0 <= cx < cell_w:
                sum_cos[cy, cx] += math.cos(2 * ang) * length / steps
                sum_sin[cy, cx] += math.sin(2 * ang) * length / steps
                weight[cy, cx] += length / steps
    mask = weight > 1e-6
    out[mask] = 0.5 * np.arctan2(sum_sin[mask], sum_cos[mask])
    return out


def compute_anchor_points(rgb: np.ndarray, max_points: int = 300) -> list[tuple[int, int]]:
    """Estrae anchor points (punti notevoli per "incollare" oggetti) via Harris corner.

    Restituisce lista di (x, y) coord in pixel del BG. Limit a max_points top.
    """
    if not _HAS_CV2:
        return []
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    # goodFeaturesToTrack: corner detector veloce e robusto
    corners = cv2.goodFeaturesToTrack(
        gray, maxCorners=max_points, qualityLevel=0.01, minDistance=40, blockSize=7
    )
    if corners is None:
        return []
    pts = corners.reshape(-1, 2).astype(int)
    return [(int(p[0]), int(p[1])) for p in pts]


def compute_bg_contours(rgb: np.ndarray, max_contours: int = 400,
                        min_area_px: int = 600, max_area_frac: float = 0.10) -> list[dict]:
    """Estrae i contorni dominanti del BG con relativi Hu moments e bbox orientato.

    Servono al matchShapes per il trompe-l'oeil: l'oggetto da scatterare viene
    confrontato per FORMA con i contorni del BG, e finisce dove c'e' una sagoma
    visivamente compatibile (es. ancora -> arco curvo, rastrello -> linee parallele).

    Args:
      rgb: array (H, W, 3) uint8
      max_contours: numero massimo restituito (top per area)
      min_area_px: scarta contorni piu' piccoli di questa area
      max_area_frac: scarta contorni che coprono piu' di questa frazione del BG (intere zone)

    Returns:
      list di dict serializzabili:
        {cx, cy, w, h, angle_deg, area, aspect, hu: [7 float log-signed]}
    """
    if not _HAS_CV2:
        return []
    h, w = rgb.shape[:2]
    max_area = int(w * h * max_area_frac)
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 1.4)
    edges = cv2.Canny(blurred, 60, 160)
    # Dilatazione leggera per chiudere piccoli gap
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    closed = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel, iterations=1)
    contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return []

    out = []
    for c in contours:
        area = float(cv2.contourArea(c))
        if area < min_area_px or area > max_area:
            continue
        # minAreaRect: bbox orientato
        try:
            ((cx, cy), (rw, rh), angle_deg) = cv2.minAreaRect(c)
        except Exception:
            continue
        if rw < 6 or rh < 6:
            continue
        aspect = float(min(rw, rh) / max(rw, rh))
        # Hu moments log-signed (matchShapes-friendly)
        try:
            m = cv2.moments(c)
            hu = cv2.HuMoments(m).flatten()
            hu_log = (-np.sign(hu) * np.log10(np.abs(hu) + 1e-30)).astype(np.float32)
        except Exception:
            continue
        out.append({
            "cx": float(cx), "cy": float(cy),
            "w": float(rw), "h": float(rh),
            "angle_deg": float(angle_deg),
            "area": area,
            "aspect": aspect,
            "hu": hu_log.tolist(),
        })

    # Ordina per area decrescente, take top N
    out.sort(key=lambda d: d["area"], reverse=True)
    return out[:max_contours]


def compute_zone_palettes(rgb: np.ndarray, semantic: Optional[np.ndarray]) -> dict:
    """Per ogni classe semantica presente, calcola la palette HSV dominante (3 colori).

    Restituisce dict[class_id -> list of [h, s, v] (3 colori normalizzati 0..1)].
    Vuoto se semantic None.
    """
    if semantic is None:
        return {}
    if _HAS_CV2:
        hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV).astype(np.float32)
        hsv[..., 0] /= 180.0
        hsv[..., 1] /= 255.0
        hsv[..., 2] /= 255.0
    else:
        # Fallback minimo
        return {}
    out = {}
    unique_classes = np.unique(semantic)
    for cls in unique_classes:
        cls_id = int(cls)
        mask = (semantic == cls)
        if mask.sum() < 100:  # zone troppo piccole skip
            continue
        pix = hsv[mask]
        # Downsample if too many pixels
        if len(pix) > 5000:
            idx = np.random.default_rng(42).choice(len(pix), 5000, replace=False)
            pix = pix[idx]
        # K-means semplice (k=3)
        from sklearn.cluster import KMeans  # disponibile? Fallback random
        try:
            km = KMeans(n_clusters=3, n_init=3, random_state=42)
            km.fit(pix)
            centers = km.cluster_centers_
        except Exception:
            # Random 3 pixel come fallback
            rng = np.random.default_rng(42)
            idx3 = rng.choice(len(pix), 3, replace=False)
            centers = pix[idx3]
        out[cls_id] = [[float(c[0]), float(c[1]), float(c[2])] for c in centers]
    return out


# ─────────────────────────────────────────────────────────────────────────────
# SQLITE CACHE
# ─────────────────────────────────────────────────────────────────────────────

def db_path(base_path: Path) -> Path:
    return base_path / DB_REL_PATH


def _ensure_schema(con: sqlite3.Connection):
    con.executescript("""
        CREATE TABLE IF NOT EXISTS bg_analysis (
            bg_sha256       TEXT NOT NULL,
            bg_w            INTEGER, bg_h INTEGER,
            cell_px         INTEGER, cell_w INTEGER, cell_h INTEGER,
            model_tier      INTEGER NOT NULL,
            schema_ver      TEXT NOT NULL,
            edge_density    BLOB,
            saliency        BLOB,
            hue             BLOB, sat BLOB, val BLOB,
            grad_orient     BLOB,
            horizontal_score BLOB, anchor_edge BLOB, normal_orient BLOB,
            semantic        BLOB, semantic_score BLOB, clip_grid BLOB,
            hideability_map BLOB, texture_entropy BLOB, local_complexity BLOB,
            anchor_points_json TEXT, zone_palettes_json TEXT,
            structural_orient BLOB,
            computed_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (bg_sha256, model_tier, schema_ver)
        );
        CREATE INDEX IF NOT EXISTS idx_sha ON bg_analysis(bg_sha256);
    """)
    # Migrazione: aggiungi colonna se schema vecchio
    cur = con.cursor()
    cur.execute("PRAGMA table_info(bg_analysis)")
    cols = {row[1] for row in cur.fetchall()}
    if "structural_orient" not in cols:
        try:
            cur.execute("ALTER TABLE bg_analysis ADD COLUMN structural_orient BLOB")
        except Exception:
            pass
    if "contours_json" not in cols:
        try:
            cur.execute("ALTER TABLE bg_analysis ADD COLUMN contours_json TEXT")
        except Exception:
            pass
    con.commit()


def _connect(base_path: Path) -> sqlite3.Connection:
    p = db_path(base_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(p))
    con.execute("PRAGMA journal_mode = WAL")
    con.execute("PRAGMA synchronous = NORMAL")
    _ensure_schema(con)
    return con


def has_cache(bg_sha256: str, model_tier: int, base_path: Path) -> bool:
    p = db_path(base_path)
    if not p.exists(): return False
    con = sqlite3.connect(str(p))
    try:
        row = con.execute(
            "SELECT 1 FROM bg_analysis WHERE bg_sha256=? AND model_tier=? AND schema_ver=?",
            (bg_sha256, model_tier, SCHEMA_VER)
        ).fetchone()
        return row is not None
    finally:
        con.close()


def save(bg, model_tier: int, base_path: Path,
         hideability_map: Optional[np.ndarray] = None,
         texture_entropy: Optional[np.ndarray] = None,
         local_complexity: Optional[np.ndarray] = None,
         anchor_points: Optional[list] = None,
         zone_palettes: Optional[dict] = None,
         structural_orient: Optional[np.ndarray] = None,
         contours: Optional[list] = None) -> str:
    """Salva BGAnalysis nel DB. Restituisce bg_sha256."""
    # bg e' una BGAnalysis instance (importata da scatter_engine, evito circular import)
    con = _connect(base_path)
    sha = bg.bg_sha256 if hasattr(bg, 'bg_sha256') else "unknown"
    try:
        con.execute("""
            INSERT OR REPLACE INTO bg_analysis (
                bg_sha256, bg_w, bg_h, cell_px, cell_w, cell_h,
                model_tier, schema_ver,
                edge_density, saliency, hue, sat, val, grad_orient,
                horizontal_score, anchor_edge, normal_orient,
                semantic, semantic_score, clip_grid,
                hideability_map, texture_entropy, local_complexity,
                anchor_points_json, zone_palettes_json,
                structural_orient, contours_json
            ) VALUES (?,?,?,?,?,?, ?,?, ?,?,?,?,?,?, ?,?,?, ?,?,?, ?,?,?, ?,?, ?, ?)
        """, (
            sha, bg.bg_w, bg.bg_h, bg.cell_px, bg.cell_w, bg.cell_h,
            model_tier, SCHEMA_VER,
            _np_to_blob(bg.edge_density), _np_to_blob(bg.saliency),
            _np_to_blob(bg.hue), _np_to_blob(bg.sat), _np_to_blob(bg.val),
            _np_to_blob(bg.grad_orient),
            _np_to_blob(bg.horizontal_score), _np_to_blob(bg.anchor_edge),
            _np_to_blob(bg.normal_orient),
            _np_to_blob(bg.semantic), _np_to_blob(bg.semantic_score),
            _np_to_blob(bg.clip_grid),
            _np_to_blob(hideability_map), _np_to_blob(texture_entropy),
            _np_to_blob(local_complexity),
            json.dumps(anchor_points or []),
            json.dumps(zone_palettes or {}),
            _np_to_blob(structural_orient),
            json.dumps(contours or []),
        ))
        con.commit()
        log.info(f"[BG_CACHE] saved sha={sha[:12]}... tier={model_tier}")
        return sha
    finally:
        con.close()


def load(bg_sha256: str, model_tier: int, base_path: Path) -> Optional[dict]:
    """Carica i dati cached. Restituisce dict con i campi della BGAnalysis + extra."""
    p = db_path(base_path)
    if not p.exists(): return None
    con = sqlite3.connect(str(p))
    try:
        # Verifica colonne disponibili (contours_json puo' essere assente in DB vecchi)
        cur = con.cursor()
        cur.execute("PRAGMA table_info(bg_analysis)")
        cols = {r[1] for r in cur.fetchall()}
        has_contours = "contours_json" in cols
        sel_contours = ", contours_json" if has_contours else ""
        row = con.execute(f"""
            SELECT bg_w, bg_h, cell_px, cell_w, cell_h,
                   edge_density, saliency, hue, sat, val, grad_orient,
                   horizontal_score, anchor_edge, normal_orient,
                   semantic, semantic_score, clip_grid,
                   hideability_map, texture_entropy, local_complexity,
                   anchor_points_json, zone_palettes_json,
                   structural_orient{sel_contours}
            FROM bg_analysis WHERE bg_sha256=? AND model_tier=? AND schema_ver=?
        """, (bg_sha256, model_tier, SCHEMA_VER)).fetchone()
        if not row:
            return None
        contours = []
        if has_contours and row[23]:
            try:
                contours = json.loads(row[23])
            except Exception:
                contours = []
        return {
            "bg_w": row[0], "bg_h": row[1], "cell_px": row[2],
            "cell_w": row[3], "cell_h": row[4],
            "edge_density": _blob_to_np(row[5]),
            "saliency": _blob_to_np(row[6]),
            "hue": _blob_to_np(row[7]), "sat": _blob_to_np(row[8]), "val": _blob_to_np(row[9]),
            "grad_orient": _blob_to_np(row[10]),
            "horizontal_score": _blob_to_np(row[11]),
            "anchor_edge": _blob_to_np(row[12]),
            "normal_orient": _blob_to_np(row[13]),
            "semantic": _blob_to_np(row[14]),
            "semantic_score": _blob_to_np(row[15]),
            "clip_grid": _blob_to_np(row[16]),
            "hideability_map": _blob_to_np(row[17]),
            "texture_entropy": _blob_to_np(row[18]),
            "local_complexity": _blob_to_np(row[19]),
            "anchor_points": [tuple(p) for p in json.loads(row[20] or "[]")],
            "zone_palettes": json.loads(row[21] or "{}"),
            "structural_orient": _blob_to_np(row[22]),
            "contours": contours,
        }
    finally:
        con.close()


def get_stats(base_path: Path) -> dict:
    p = db_path(base_path)
    if not p.exists(): return {"db_exists": False}
    con = sqlite3.connect(str(p))
    try:
        out = {"db_exists": True, "entries": []}
        for row in con.execute(
            "SELECT bg_sha256, bg_w, bg_h, model_tier, computed_at FROM bg_analysis"
        ):
            out["entries"].append({
                "sha": row[0][:12] + "...",
                "size": f"{row[1]}x{row[2]}",
                "tier": row[3],
                "at": row[4],
            })
        out["total"] = len(out["entries"])
        # File size
        out["db_size_mb"] = p.stat().st_size / 1024 / 1024
        return out
    finally:
        con.close()
