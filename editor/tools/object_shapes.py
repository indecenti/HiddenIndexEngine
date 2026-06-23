"""
editor/tools/object_shapes.py

Shape analysis dei PNG del catalogo. Estrae la FORMA REALE (silhouette) tramite
canale alpha. Pre-calcoli salvati in object_profiles.db (schema esteso con
colonne shape_*).

Metriche estratte (per ogni icona):
  - principal_axis_angle : asse principale via PCA su pixel non-trasparenti, [-pi/2, pi/2]
                           (un cavallo allungato orizzontale: ~0; una scopa verticale: ~pi/2)
  - aspect_real          : rapporto degli autovalori PCA (1.0 = simmetrico, 0 = lineare)
  - compactness          : 4πA / P² del contorno alpha. 1.0=cerchio perfetto, <0.3=lungo/sottile
  - solidity             : Area_silhouette / Area_convex_hull (0.5=oggetto frastagliato, 1.0=convesso)
  - bbox_oriented        : (cx, cy, w, h, angle) del minAreaRect
  - support_bottom_frac  : frazione di pixel non-trasparenti negli ultimi 20% di altezza
                           (alta = oggetto ha base larga = poggia bene)
  - hangability_top_frac : frazione di pixel nel primo 20% di altezza (alta = ha attacco superiore)
  - silhouette_poly      : poligono semplificato (max 24 punti)
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


# ─────────────────────────────────────────────────────────────────────────────
# SHAPE METRICS
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ShapeMetrics:
    principal_axis_angle: float  # rad, [-pi/2, pi/2]
    aspect_real: float           # 0..1, rapporto sqrt(eig_min/eig_max)
    compactness: float           # 4πA/P², 0..1
    solidity: float              # 0..1
    bbox_oriented: tuple         # (cx_rel, cy_rel, w_rel, h_rel, angle_deg)  rel = 0..1
    support_bottom_frac: float   # 0..1
    hangability_top_frac: float  # 0..1
    silhouette_poly: list        # list of (x_rel, y_rel) 0..1
    hu_log: list                 # 7 Hu moments, signed log-transformed (scale-invariant)


def compute_shape_metrics(icon_path: Path) -> Optional[ShapeMetrics]:
    """Estrae metriche di forma dal canale alpha del PNG."""
    if not _HAS_CV2:
        return None
    try:
        # IMREAD_UNCHANGED per il canale alpha
        img = cv2.imread(str(icon_path), cv2.IMREAD_UNCHANGED)
        if img is None or img.shape[2] != 4:
            return None
        alpha = img[..., 3]
    except Exception as e:
        log.debug(f"shape: cannot open {icon_path}: {e}")
        return None

    # Maschera silhouette (alpha > 64)
    mask = (alpha > 64).astype(np.uint8) * 255
    h, w = mask.shape
    if mask.sum() < 50 * 255:
        return None  # icona vuota

    # ── PRINCIPAL AXIS via PCA ─────────────────────────────────────────
    ys, xs = np.where(mask > 0)
    if len(xs) < 3:
        return None
    coords = np.stack([xs.astype(np.float32), ys.astype(np.float32)], axis=1)
    coords_c = coords - coords.mean(axis=0)
    # SVD per autovalori/autovettori
    try:
        _, s, vt = np.linalg.svd(coords_c, full_matrices=False)
        # primo vettore principale
        v_main = vt[0]
        angle = math.atan2(v_main[1], v_main[0])
        # Normalizza in [-pi/2, pi/2] (asse, non vettore orientato)
        if angle > math.pi / 2:
            angle -= math.pi
        elif angle < -math.pi / 2:
            angle += math.pi
        # aspect: ratio degli autovalori (s² = eigenvalues)
        if s[0] > 1e-6:
            aspect_real = float(s[1] / s[0])
        else:
            aspect_real = 1.0
    except Exception:
        angle = 0.0
        aspect_real = 1.0

    # ── CONTORNI e metriche di shape ──────────────────────────────────
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    # Contorno piu' grande (silhouette principale)
    main_c = max(contours, key=cv2.contourArea)
    area = cv2.contourArea(main_c)
    perimeter = cv2.arcLength(main_c, closed=True)
    compactness = (4 * math.pi * area / (perimeter * perimeter)) if perimeter > 0 else 0.0
    compactness = min(1.0, compactness)

    # Solidity = area / area_convex_hull
    try:
        hull = cv2.convexHull(main_c)
        hull_area = cv2.contourArea(hull)
        solidity = float(area / hull_area) if hull_area > 0 else 0.0
    except Exception:
        solidity = 0.0

    # bbox_oriented: minimo rect ruotato attorno alla silhouette
    try:
        ((cx, cy), (rw, rh), rot_deg) = cv2.minAreaRect(main_c)
        bbox_oriented = (
            float(cx / w), float(cy / h),
            float(rw / w), float(rh / h),
            float(rot_deg),
        )
    except Exception:
        bbox_oriented = (0.5, 0.5, 1.0, 1.0, 0.0)

    # ── Support / hangability ─────────────────────────────────────────
    bottom_band = mask[int(h * 0.80):, :]
    top_band = mask[:int(h * 0.20), :]
    bottom_frac = float(bottom_band.sum()) / float(mask.sum())
    top_frac = float(top_band.sum()) / float(mask.sum())

    # ── Silhouette poly (semplificato a ~24 punti) ────────────────────
    try:
        eps = 0.01 * perimeter
        approx = cv2.approxPolyDP(main_c, eps, closed=True)
        # Limita a 24 max (semplifica ancora se serve)
        if len(approx) > 24:
            eps *= 2
            approx = cv2.approxPolyDP(main_c, eps, closed=True)
        approx = approx.reshape(-1, 2)
        silhouette_poly = [(float(p[0]) / w, float(p[1]) / h) for p in approx[:24]]
    except Exception:
        silhouette_poly = []

    # ── Hu moments (7, invarianti per traslazione/scala/rotazione) ────
    # Trasformazione log-signed standard per range numerico utilizzabile.
    try:
        m = cv2.moments(main_c)
        hu = cv2.HuMoments(m).flatten()  # (7,)
        # signed log: -sign(h) * log10(|h|+eps)
        hu_log = (-np.sign(hu) * np.log10(np.abs(hu) + 1e-30)).astype(np.float32).tolist()
    except Exception:
        hu_log = [0.0] * 7

    return ShapeMetrics(
        principal_axis_angle=angle,
        aspect_real=aspect_real,
        compactness=compactness,
        solidity=solidity,
        bbox_oriented=bbox_oriented,
        support_bottom_frac=bottom_frac,
        hangability_top_frac=top_frac,
        silhouette_poly=silhouette_poly,
        hu_log=hu_log,
    )


# ─────────────────────────────────────────────────────────────────────────────
# DB INTEGRATION (estende object_profiles.db con colonne shape_*)
# ─────────────────────────────────────────────────────────────────────────────

OBJ_PROFILES_DB = "engine/data/object_profiles.db"


def ensure_shape_columns(base_path: Path):
    """Aggiunge colonne shape_* a object_profile (se non esistono)."""
    p = base_path / OBJ_PROFILES_DB
    p.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(p))
    cur = con.cursor()
    # Garantisce la tabella base anche se build_profiles non e' ancora girato
    # (altrimenti 'no such table: object_profile' o precompute silenziosamente perso).
    from editor.tools.object_profiles import _ensure_schema
    _ensure_schema(con)
    # Check colonne esistenti
    cur.execute("PRAGMA table_info(object_profile)")
    cols = {row[1] for row in cur.fetchall()}
    new_cols = {
        "shape_axis_angle":   "REAL",
        "shape_aspect_real":  "REAL",
        "shape_compactness":  "REAL",
        "shape_solidity":     "REAL",
        "shape_bbox":         "TEXT",
        "shape_support_bot":  "REAL",
        "shape_hang_top":     "REAL",
        "shape_silhouette":   "TEXT",
        "shape_hu":           "TEXT",   # 7 Hu moments log-signed (JSON)
        "shape_version":      "TEXT",
    }
    added = 0
    for col, typ in new_cols.items():
        if col not in cols:
            cur.execute(f"ALTER TABLE object_profile ADD COLUMN {col} {typ}")
            added += 1
    if added:
        con.commit()
        log.info(f"[SHAPES] aggiunte {added} colonne shape_* a object_profile")
    con.close()


SHAPE_VERSION = "v2"  # v2: aggiunge Hu moments per matchShapes vs contorni BG


def build_shapes_for_catalog(catalog: list[dict], style: str, base_path: Path,
                              overwrite: bool = False,
                              progress_cb=None) -> int:
    """Pre-compute shape metrics per oggetti dello stile, salva in object_profiles.db."""
    ensure_shape_columns(base_path)
    p = base_path / OBJ_PROFILES_DB
    con = sqlite3.connect(str(p))
    cur = con.cursor()

    style_pool = [c for c in catalog if c.get("style", "real") == style]
    if not style_pool:
        log.warning(f"[SHAPES] nessun oggetto stile '{style}'")
        con.close()
        return 0

    # Skip set
    if not overwrite:
        existing = set()
        for row in cur.execute(
            "SELECT catalog_id FROM object_profile WHERE shape_version = ?", (SHAPE_VERSION,)):
            existing.add(row[0])
    else:
        existing = set()

    to_process = [c for c in style_pool if c["id"] not in existing]
    log.info(f"[SHAPES] {len(to_process)}/{len(style_pool)} da processare per '{style}'")

    t0 = time.time()
    n_done = 0
    n_skipped = 0
    for i, entry in enumerate(to_process):
        cid = entry["id"]
        icon_rel = entry.get("icon", "")
        candidates = [
            base_path / "engine" / "assets" / icon_rel,
            base_path / icon_rel,
        ]
        icon_path = next((p for p in candidates if p.exists()), None)
        if not icon_path:
            n_skipped += 1
            continue
        sm = compute_shape_metrics(icon_path)
        if sm is None:
            n_skipped += 1
            continue
        # Update riga esistente (gia' presente da CLIP profile)
        # Se la riga non c'e' la insert (per oggetti senza CLIP profile)
        cur.execute("""
            INSERT INTO object_profile (catalog_id, style, prompts_ver, visual_emb, profile,
                                        shape_axis_angle, shape_aspect_real, shape_compactness,
                                        shape_solidity, shape_bbox, shape_support_bot,
                                        shape_hang_top, shape_silhouette, shape_hu, shape_version)
            VALUES (?, ?, 'v1', x'', '{}',
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(catalog_id) DO UPDATE SET
                shape_axis_angle   = excluded.shape_axis_angle,
                shape_aspect_real  = excluded.shape_aspect_real,
                shape_compactness  = excluded.shape_compactness,
                shape_solidity     = excluded.shape_solidity,
                shape_bbox         = excluded.shape_bbox,
                shape_support_bot  = excluded.shape_support_bot,
                shape_hang_top     = excluded.shape_hang_top,
                shape_silhouette   = excluded.shape_silhouette,
                shape_hu           = excluded.shape_hu,
                shape_version      = excluded.shape_version
        """, (cid, style,
              sm.principal_axis_angle, sm.aspect_real, sm.compactness, sm.solidity,
              json.dumps(sm.bbox_oriented), sm.support_bottom_frac,
              sm.hangability_top_frac, json.dumps(sm.silhouette_poly),
              json.dumps(sm.hu_log), SHAPE_VERSION))
        n_done += 1
        if progress_cb and (i + 1) % 100 == 0:
            try: progress_cb(i + 1, len(to_process))
            except Exception: pass

    con.commit()
    con.close()
    dt = time.time() - t0
    log.info(f"[SHAPES] done '{style}': {n_done} processed, {n_skipped} skipped in {dt:.1f}s")
    return n_done


def get_shapes_for_style(style: str, base_path: Path) -> dict:
    """Bulk lookup shape metrics per stile. Restituisce dict[cid -> dict]."""
    p = base_path / OBJ_PROFILES_DB
    if not p.exists():
        return {}
    con = sqlite3.connect(str(p))
    out = {}
    try:
        # Verifica esistenza colonne shape_*
        cur = con.cursor()
        cur.execute("PRAGMA table_info(object_profile)")
        cols = {row[1] for row in cur.fetchall()}
        if "shape_axis_angle" not in cols:
            return {}
        # shape_hu puo' essere assente nei DB precedenti la versione v2
        has_hu = "shape_hu" in cols
        select_hu = ", shape_hu" if has_hu else ""
        for row in cur.execute(f"""
            SELECT catalog_id, shape_axis_angle, shape_aspect_real, shape_compactness,
                   shape_solidity, shape_bbox, shape_support_bot,
                   shape_hang_top, shape_silhouette{select_hu}
            FROM object_profile WHERE style = ? AND shape_version IS NOT NULL
        """, (style,)):
            cid = row[0]
            out[cid] = {
                "axis_angle":  row[1],
                "aspect_real": row[2],
                "compactness": row[3],
                "solidity":    row[4],
                "bbox":        json.loads(row[5]) if row[5] else None,
                "support_bot": row[6],
                "hang_top":    row[7],
                "silhouette":  json.loads(row[8]) if row[8] else [],
                "hu":          json.loads(row[9]) if has_hu and row[9] else None,
            }
        return out
    finally:
        con.close()


def get_stats(base_path: Path) -> dict:
    p = base_path / OBJ_PROFILES_DB
    if not p.exists():
        return {"db_exists": False}
    con = sqlite3.connect(str(p))
    try:
        out = {"db_exists": True, "by_style": {}}
        for row in con.execute("""
            SELECT style, COUNT(*) FROM object_profile
            WHERE shape_version IS NOT NULL GROUP BY style
        """):
            out["by_style"][row[0]] = row[1]
        out["total_with_shape"] = sum(out["by_style"].values())
        return out
    finally:
        con.close()
