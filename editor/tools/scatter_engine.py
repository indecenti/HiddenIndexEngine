"""
editor/tools/scatter_engine.py

Auto-scatter intelligente per scene hidden-object. Posiziona oggetti pescati
da un catalogo (filtrato per stile e opzionalmente per tag tema) in modo che
si camuffino col background il piu possibile, usando 6 leve combinate:

  1. Edge density del BG (oggetti dove l'occhio "annega" nel rumore visivo)
  2. Saliency map (zone dove l'occhio NON guarda di default)
  3. Color similarity HSV (palette oggetto vicina alla palette zona BG)
  4. Edge orientation matching (rotazione oggetto allineata al gradient locale)
  5. Scala proporzionata al BG con jitter
  6. Tint colore chirurgico (solo se delta hue forte)
     + alpha 75-85 per oggetti vetro/cristallo
     + flip H casuale per oggetti senza orientamento canonico

Architettura:
  - BGAnalysis: pre-process del background (one-shot per scena)
  - CatalogAnalysis: pre-process del catalogo dello stile (cached su disco)
  - ScatterEngine.place_objects(...): pipeline completa di sampling
"""

from __future__ import annotations

import json
import logging
import math
import random
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional, Sequence

import numpy as np

log = logging.getLogger(__name__)

# Cell size della grid di scoring: tradeoff fra precisione e performance.
# 48px = grid ~115x65 su un BG 5476x3072.
CELL_PX = 48

# Catalog cache su disco
CATALOG_CACHE_DIR = ".editor_cache"
CATALOG_CACHE_VERSION = 2  # v2: palette via k-means RGB (no HSV-SV), alpha>200

# ── COSTANTI CAMOUFLAGE v3 ──────────────────────────────────────────────────
# Score sentinella per le celle vietate (hard veto): nessun termine additivo
# puo' risollevarle. Era un letterale -1e9 sparso in piu' punti.
SCORE_VETO = -1e9
# Soglia per riconoscere una cella vetata leggendo la score matrix (i termini
# additivi possono spostare SCORE_VETO di qualche unita', mai di ordini di
# grandezza).
SCORE_VETO_THRESHOLD = -1e8
# Normalizzazione ASSOLUTA dell'edge density: frazione di pixel Canny per cella
# oltre la quale la cella e' "completamente busy". Sostituisce il max
# per-griglia, che rendeva i punteggi non comparabili fra scene (su un BG
# piatto la cella meno piatta veniva promossa a 1.0).
EDGE_DENSITY_ABS_REF = 0.20
# Normalizzazione robusta della saliency: percentile di riferimento del massimo
# (la saliency resta relativa alla scena — l'attenzione E' una competizione
# intra-scena — ma senza dipendere da un singolo outlier).
SALIENCY_NORM_PERCENTILE = 0.95
# Gate colore DURO: similarita' colore minima per cella, per difficolta'.
# Sotto soglia la cella e' vetata per quell'oggetto: nessun altro termine
# (edge, profile, clip...) puo' compensare un pessimo match cromatico.
COLOR_GATE_MIN = {"easy": 0.35, "medium": 0.55, "hard": 0.68}
# Zone piatte (bassa entropia texture + pochi edge): li' un oggetto salta
# all'occhio, ammesso solo se quasi invisibile cromaticamente.
FLAT_ENTROPY_MAX = 0.25
FLAT_EDGE_MAX = 0.12
FLAT_COLOR_MIN = 0.75
# Relax deterministico del gate colore quando restano troppo poche celle valide.
COLOR_GATE_MIN_CELLS = 40
COLOR_GATE_MIN_FRAC = 0.03
COLOR_GATE_RELAX_STEP = 0.08
COLOR_GATE_FLOOR = 0.25
# Verifica footprint in Lab (Delta-E 1976) post-selezione: oltre la soglia
# l'oggetto "stacca" dai pixel reali sotto il footprint (la media di cella a
# 48px puo' mentire su zone variegate). Cap rilassato linearmente col
# progredire dei tentativi (attempts_frac) per non svuotare il piazzamento.
DELTAE_MAX = {"easy": 45.0, "medium": 34.0, "hard": 26.0}
DELTAE_RELAX_GAIN = 1.0
DELTAE_PATCH_MAX_SIDE = 64  # lato max del subsample deterministico del patch
# Veto saliency: frazione delle celle PIU' salienti vetata a runtime (le zone
# dove l'occhio va per primo sono "in bella vista"). 0 = disattivo.
SALIENCY_VETO_TOP_FRAC = {"easy": 0.0, "medium": 0.08, "hard": 0.15}
# Guard anti over-veto: se le celle libere scendono sotto questa frazione della
# griglia, la SOLA componente saliency viene droppata (mai volti/manuale/person).
MIN_ALLOWED_CELLS_FRAC = 0.10
# Tint di harmonization in Lab: quota di colore del footprint mixata nel
# color_filter (il resto verso bianco = tint piu' leggero). Cresce con la
# difficolta': hard fonde di piu'.
TINT_MIX = {"easy": 0.15, "medium": 0.30, "hard": 0.45}
TINT_MIN_L = 30.0       # clamp della L del footprint (no black-crush del tint)
TINT_MIN_CHROMA = 12.0  # sotto: zona grigia -> mix dimezzato (no colore falso)
# Banda di visibilita' su vs (= qualita' del nascondiglio, 0..1): [min, max]
# per difficolta'. Il MAX e' il floor di risolvibilita' (audit #4): nessun
# oggetto deve essere di fatto introvabile. Il MIN evita piazzamenti banali.
VISIBILITY_BAND = {"easy": (0.05, 0.55), "medium": (0.20, 0.78), "hard": (0.35, 0.90)}
VIS_BAND_RELAX_GAIN = 0.25  # allargamento banda proporzionale ad attempts_frac
# Scala per profondita' (tier>=1): moltiplicatore da lontano (MIN) a vicino (MAX).
DEPTH_SCALE_MIN = 0.85
DEPTH_SCALE_MAX = 1.25
# ── v3.1: anti-pile + scelta oggetto per zona ────────────────────────────────
# Candidati oggetto valutati per tentativo: vince chi ha lo score migliore
# nella macro-zona corrente (scelta color/size-aware invece di pesca cieca).
OBJ_CANDIDATES_PER_ATTEMPT = 3
# Pool pruning: un oggetto il cui gate colore fallisce anche al floor (nessuna
# zona compatibile sul BG) viene tolto dal pool, purche' ne restino almeno N.
POOL_MIN_AFTER_COLOR_PRUNE = 3
# Cross-layer: le bbox dei layer gia' piazzati vengono ristrette di questa
# frazione per lato ad alta densita' (prima la separazione era proprio OFF:
# tre passate indipendenti si accatastavano sugli stessi hotspot).
CROSS_LAYER_SHRINK_FRAC = 0.25
# Veto "mezz'aria": celle piatte nella meta' superiore del BG con edge quasi
# nullo nelle 2 celle sotto = cielo/vuoto, un oggetto ci fluttuerebbe.
FLOATING_EDGE_BELOW_MAX = 0.06
# ── v3.2: mismatch di croma nel color matching ───────────────────────────────
# Un oggetto GRIGIO/metallico su una zona satura stacca (il percorso "gray"
# ignora la hue e dava match alti ovunque il value combaciasse: toaster sugli
# alberi). Penalita' proporzionale alla saturazione del BG oltre la soglia.
GRAY_ON_SAT_PENALTY = 0.6
CHROMA_NEUTRAL_SAT = 0.15   # sotto: cluster/cella considerati "grigi"
GRAY_PENALTY_SAT_START = 0.25
# Simmetrico: oggetto SATURO su zona quasi grigia (la hue del BG e' rumore,
# il termine hue non vale nulla): il match si basa su sat/val con penalita'
# proporzionale alla saturazione dell'oggetto.
SAT_ON_GRAY_PENALTY = 0.35


# ────────────────────────────────────────────────────────────────────────────
# OPTIONAL OPENCV
# ────────────────────────────────────────────────────────────────────────────
try:
    import cv2  # type: ignore
    _HAS_CV2 = True
except Exception:
    _HAS_CV2 = False
    log.warning("cv2 non disponibile, scatter funziona ma senza saliency")


# ────────────────────────────────────────────────────────────────────────────
# DATA CLASSES
# ────────────────────────────────────────────────────────────────────────────

@dataclass
class BGAnalysis:
    """Risultato del pre-process del background."""
    bg_w: int
    bg_h: int
    cell_w: int      # numero celle in larghezza
    cell_h: int      # numero celle in altezza
    cell_px: int     # dimensione cella in px del BG

    edge_density: np.ndarray   # shape (cell_h, cell_w), float 0..1
    saliency: np.ndarray       # shape (cell_h, cell_w), float 0..1 (1 = guarda lì)
    hue: np.ndarray            # shape (cell_h, cell_w), float 0..1 (Hue OpenCV / 180)
    sat: np.ndarray            # shape (cell_h, cell_w), float 0..1
    val: np.ndarray            # shape (cell_h, cell_w), float 0..1
    grad_orient: np.ndarray    # shape (cell_h, cell_w), float -pi..pi

    # Campi IA opzionali (None se nessun modello attivo)
    model_tier: int = 0
    horizontal_score: Optional[np.ndarray] = None
    anchor_edge: Optional[np.ndarray] = None
    normal_orient: Optional[np.ndarray] = None
    # Tier ULTRA: campi semantici aggiuntivi
    semantic: Optional[np.ndarray] = None
    semantic_score: Optional[np.ndarray] = None
    clip_grid: Optional[np.ndarray] = None
    # Metriche avanzate (sempre calcolate)
    hideability_map: Optional[np.ndarray] = None       # (cell_h, cell_w) 0..1
    texture_entropy: Optional[np.ndarray] = None       # (cell_h, cell_w) 0..1
    local_complexity: Optional[np.ndarray] = None      # (cell_h, cell_w) 0..1
    anchor_points: Optional[list] = None               # list di (x, y) pixel BG
    zone_palettes: Optional[dict] = None               # {class_id -> [HSV center]*3}
    structural_orient: Optional[np.ndarray] = None     # (cell_h, cell_w) angolo lineee dominanti, -pi/2..pi/2
    contours: Optional[list] = None                    # list di dict {cx,cy,w,h,angle_deg,area,aspect,hu}
    bg_sha256: Optional[str] = None                    # hash per cache key
    # Campi runtime per camouflage preciso (NON persistiti in cache: ricalcolati
    # ad ogni run dal BG, costo trascurabile).
    color_uniformity: Optional[np.ndarray] = None      # (cell_h, cell_w) 0..1, 1=zona cromaticamente uniforme
    hsv_full: Optional[np.ndarray] = None              # (H,W,3) HSV full-res per campionare il footprint reale
    lab_full: Optional[np.ndarray] = None              # (H,W,3) Lab (OpenCV uint8) per verifica Delta-E footprint
    # Zone vietate (v3): persistite in cache; unione in build_forbidden_mask().
    face_mask: Optional[np.ndarray] = None             # (cell_h, cell_w) bool, celle con volti rilevati
    depth_grid: Optional[np.ndarray] = None            # (cell_h, cell_w) 0..1 NEARNESS (1 = vicino alla camera)


@dataclass
class ObjAnalysis:
    """Pre-process di un singolo oggetto del catalogo."""
    catalog_id: str
    palette: list[tuple[float, float, float]]  # 3 colori HSV normalizzati 0..1
    edge_orient: float    # orientamento gradiente dominante del bordo, -pi..pi
    aspect: float         # width / height
    size_class: str       # "small" | "mid" | "big"
    clip_emb: Optional[np.ndarray] = None
    context_profile: Optional[dict] = None
    # Shape metrics da object_shapes
    shape: Optional[dict] = None  # {axis_angle, aspect_real, compactness, solidity, support_bot, hang_top}
    # Palette estesa (k=8, con frequency e variance) da object_palette
    palette_ext: Optional[list[dict]] = None  # [{h,s,v,w,var}, ...] ord. per w desc


# ────────────────────────────────────────────────────────────────────────────
# BG PRE-PROCESS
# ────────────────────────────────────────────────────────────────────────────

def _surface_to_rgb_array(surface) -> np.ndarray:
    """Converte pygame.Surface in numpy array RGB shape (H, W, 3) uint8."""
    import pygame
    arr = pygame.surfarray.array3d(surface)  # (W, H, 3)
    return np.ascontiguousarray(arr.swapaxes(0, 1))  # (H, W, 3)


def _aggregate_to_grid(arr: np.ndarray, cell_h: int, cell_w: int, cell_px: int,
                       mode: str = "mean") -> np.ndarray:
    """Riduce un array 2D (H, W) a (cell_h, cell_w) aggregando per cella."""
    h, w = arr.shape[:2]
    # Crop ai multipli di cell_px
    h_eff, w_eff = cell_h * cell_px, cell_w * cell_px
    arr = arr[:h_eff, :w_eff]
    # Reshape (cell_h, cell_px, cell_w, cell_px)
    reshaped = arr.reshape(cell_h, cell_px, cell_w, cell_px)
    if mode == "mean":
        return reshaped.mean(axis=(1, 3))
    elif mode == "max":
        return reshaped.max(axis=(1, 3))
    else:
        return reshaped.sum(axis=(1, 3))


def _uniformity_reweight(cs: np.ndarray, color_uniformity: np.ndarray) -> np.ndarray:
    """Premia il color-match nelle zone cromaticamente uniformi, senza saturare.

    cs * (1 + 0.6*uniformita'*cs): in una zona uniforme che combacia, l'oggetto
    SPARISCE, quindi il match va premiato. La versione precedente clippava il
    risultato a 1.0, schiacciando molte celle ad alto cs allo stesso valore e
    appiattendo la discriminazione tra le MIGLIORI posizioni di camuffamento.
    Senza il tetto la funzione resta monotona in cs (valori distinti -> score
    distinti), preservando l'ordinamento ai vertici; il camuffamento da clutter
    (zone variegate) resta gestito dal termine edge.
    """
    return cs * (1.0 + 0.6 * color_uniformity * cs)


def _center_prior_saliency(h: int, w: int) -> np.ndarray:
    """Saliency di fallback (quando cv2.saliency e' assente): center-prior puro.

    NON usa edge_density di proposito: lo score di piazzamento somma gia'
    w_edge*edge_density, e una saliency ~edge faceva si' che il termine
    w_sal*(1-saliency) penalizzasse esattamente le zone ad alto edge che w_edge
    premia (camuffamento da clutter), annullandone in parte il contributo. Il
    center-prior dipende SOLO dalla posizione (gli occhi tendono al centro),
    quindi i due termini non si combattono. Restituisce (h, w) float32 in [0,1]:
    1 al centro, ~0 agli angoli.
    """
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    cy_c, cx_c = h / 2.0, w / 2.0
    max_d = math.hypot(cy_c, cx_c)
    return (1.0 - np.sqrt((yy - cy_c) ** 2 + (xx - cx_c) ** 2) / max_d).astype(np.float32)


def _dominant_class_per_cell(semantic_raw: np.ndarray, cell_h: int, cell_w: int,
                             cell_px: int) -> np.ndarray:
    """Classe semantica dominante (moda) per cella.

    NB: np.bincount per blocco (C-level) e' gia' il modo piu' veloce di calcolare
    la moda qui. Le alternative full-numpy (offset+bincount, o block-sum per
    classe) allocano l'intera immagine e a misura risultano PIU' lente del loop
    (es. ~400ms vs ~70ms su un BG 5K). Estratto in funzione per testabilita' e per
    separare lo scoring semantico (vettorizzato a parte nel chiamante).
    Tie-break: a pari conteggio vince la classe con id piu' basso.
    """
    out = np.zeros((cell_h, cell_w), dtype=np.int32)
    for cyi in range(cell_h):
        for cxi in range(cell_w):
            block = semantic_raw[cyi * cell_px:(cyi + 1) * cell_px,
                                 cxi * cell_px:(cxi + 1) * cell_px]
            flat = block.flatten()
            if flat.size > 0:
                out[cyi, cxi] = int(np.bincount(flat).argmax())
    return out


def analyze_background(bg_surface, cell_px: int = CELL_PX, ia_model=None,
                       base_path: Optional[Path] = None, use_cache: bool = True) -> BGAnalysis:
    """Pre-process del BG: edge density, saliency, palette locale, gradient orientation
    + (se ia_model) depth/normals/semantic/CLIP + metriche avanzate.

    Cache SQLite (se base_path fornito e use_cache=True):
      - Chiave: SHA256 del BG + model_tier + schema_ver
      - Hit: ricarica tutti i tensor da DB (no ricalcolo)
      - Miss: calcola tutto e salva
    """
    rgb = _surface_to_rgb_array(bg_surface)

    # ── CHECK CACHE ─────────────────────────────────────────────────────
    model_tier_for_cache = getattr(ia_model, "tier", 0) if ia_model else 0
    bg_sha = None
    if use_cache and base_path is not None:
        try:
            from editor.tools import bg_cache as _bg_cache
            bg_sha = _bg_cache.compute_bg_sha256(bg_surface)
            cached = _bg_cache.load(bg_sha, model_tier_for_cache, base_path)
            if cached is not None:
                log.info(f"[SCATTER] BG cache HIT sha={bg_sha[:12]}... tier={model_tier_for_cache}")
                analysis = BGAnalysis(
                    bg_w=cached["bg_w"], bg_h=cached["bg_h"],
                    cell_w=cached["cell_w"], cell_h=cached["cell_h"], cell_px=cached["cell_px"],
                    edge_density=cached["edge_density"],
                    saliency=cached["saliency"],
                    hue=cached["hue"], sat=cached["sat"], val=cached["val"],
                    grad_orient=cached["grad_orient"],
                    model_tier=model_tier_for_cache,
                    horizontal_score=cached["horizontal_score"],
                    anchor_edge=cached["anchor_edge"],
                    normal_orient=cached["normal_orient"],
                    semantic=cached["semantic"],
                    semantic_score=cached["semantic_score"],
                    clip_grid=cached["clip_grid"],
                    hideability_map=cached["hideability_map"],
                    texture_entropy=cached["texture_entropy"],
                    local_complexity=cached["local_complexity"],
                    anchor_points=cached["anchor_points"],
                    zone_palettes=cached["zone_palettes"],
                    structural_orient=cached.get("structural_orient"),
                    contours=cached.get("contours") or [],
                    bg_sha256=bg_sha,
                    face_mask=cached.get("face_mask"),
                    depth_grid=cached.get("depth_grid"),
                )
                _attach_runtime_color(analysis, rgb)
                return analysis
            else:
                log.info(f"[SCATTER] BG cache MISS sha={bg_sha[:12]}... tier={model_tier_for_cache}")
        except Exception as e:
            log.warning(f"[SCATTER] BG cache lookup failed ({e})")

    h, w, _ = rgb.shape
    cell_w = max(1, w // cell_px)
    cell_h = max(1, h // cell_px)
    log.info(f"[SCATTER] BG analysis {w}x{h}, grid {cell_w}x{cell_h} @ {cell_px}px"
             + (f", IA tier={ia_model.tier}" if ia_model else ""))
    t0 = time.time()

    # Edge density via Canny (oppure fallback Sobel se cv2 manca)
    if _HAS_CV2:
        gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
        blurred = cv2.GaussianBlur(gray, (5, 5), 1.4)
        edges = cv2.Canny(blurred, 60, 160)
        edges_f = edges.astype(np.float32) / 255.0
    else:
        gray = (0.299 * rgb[..., 0] + 0.587 * rgb[..., 1] + 0.114 * rgb[..., 2]).astype(np.float32)
        gx = np.abs(np.diff(gray, axis=1, prepend=gray[:, :1]))
        gy = np.abs(np.diff(gray, axis=0, prepend=gray[:1, :]))
        edges_f = np.clip((gx + gy) / 255.0, 0, 1).astype(np.float32)

    edge_density = _aggregate_to_grid(edges_f, cell_h, cell_w, cell_px, "mean")
    # Normalizzazione ASSOLUTA (v3): la scala e' fissa, non relativa al max della
    # griglia. Un BG piatto resta piatto (prima la sua cella meno piatta veniva
    # promossa a 1.0, falsando i confronti fra scene e i gate a soglia assoluta).
    edge_density = np.clip(edge_density / EDGE_DENSITY_ABS_REF, 0.0, 1.0).astype(np.float32)

    # Saliency
    sal = None
    if _HAS_CV2 and hasattr(cv2, "saliency"):
        try:
            saliency_obj = cv2.saliency.StaticSaliencyFineGrained_create()
            ok, sal = saliency_obj.computeSaliency(rgb)
            if ok:
                sal = sal.astype(np.float32)
            else:
                sal = None
        except Exception as e:
            log.warning(f"[SCATTER] saliency cv2 fallita ({e}), uso fallback classico")
            sal = None
    if sal is None:
        # Fallback (cv2.saliency assente): center-prior puro, senza la componente
        # edge che prima si annullava con w_edge (vedi _center_prior_saliency).
        sal = _center_prior_saliency(h, w)
    saliency = _aggregate_to_grid(sal, cell_h, cell_w, cell_px, "mean")
    # Normalizzazione robusta (v3): riferimento = p95 invece del max, cosi' un
    # singolo outlier non schiaccia tutta la mappa. Clip per il tail sopra p95.
    smax = max(float(np.quantile(saliency, SALIENCY_NORM_PERCENTILE)), 1e-6)
    saliency = np.clip(saliency / smax, 0.0, 1.0).astype(np.float32)

    # HSV per cella (per color matching)
    if _HAS_CV2:
        hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    else:
        hsv = _rgb_to_hsv_np(rgb)
    hue = _aggregate_to_grid(hsv[..., 0].astype(np.float32), cell_h, cell_w, cell_px, "mean") / 180.0
    sat = _aggregate_to_grid(hsv[..., 1].astype(np.float32), cell_h, cell_w, cell_px, "mean") / 255.0
    val = _aggregate_to_grid(hsv[..., 2].astype(np.float32), cell_h, cell_w, cell_px, "mean") / 255.0

    # Gradient orientation (Sobel dominante per cella)
    if _HAS_CV2:
        sobel_x = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
        sobel_y = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    else:
        gray = (0.299 * rgb[..., 0] + 0.587 * rgb[..., 1] + 0.114 * rgb[..., 2]).astype(np.float32)
        sobel_x = np.diff(gray, axis=1, prepend=gray[:, :1])
        sobel_y = np.diff(gray, axis=0, prepend=gray[:1, :])
    # Per cella: media vettori orientati (peso = magnitudo)
    mag = np.sqrt(sobel_x ** 2 + sobel_y ** 2)
    gx = _aggregate_to_grid(sobel_x * (mag > 10), cell_h, cell_w, cell_px, "sum")
    gy = _aggregate_to_grid(sobel_y * (mag > 10), cell_h, cell_w, cell_px, "sum")
    grad_orient = np.arctan2(gy, gx).astype(np.float32)

    # ── IA opzionale: depth + normals + (tier ULTRA) semantic/clip ────────
    horizontal_score = None
    anchor_edge = None
    normal_orient = None
    semantic_grid = None
    semantic_score_grid = None
    clip_grid = None
    depth_grid = None
    semantic_raw_full = None  # accessibile alle metriche avanzate
    model_tier = 0
    if ia_model is not None and getattr(ia_model, "tier", 0) >= 1:
        t_ia = time.time()
        try:
            out = ia_model.analyze(rgb)
            model_tier = out.get("tier", 0)
            depth = out.get("depth")
            normals = out.get("normals")
            semantic_raw = out.get("semantic")  # solo ULTRA
            semantic_raw_full = semantic_raw    # expose alle metriche
            clip_raw = out.get("clip_grid")     # solo ULTRA
            if semantic_raw is not None:
                from editor.tools.scatter_models import (
                    ADE20K_FLOOR_LIKE, ADE20K_TABLE_LIKE, ADE20K_PROHIBITED,
                )
                preferred = ADE20K_FLOOR_LIKE | ADE20K_TABLE_LIKE
                prohibited = ADE20K_PROHIBITED
                # Classe dominante (moda) per cella, vettorizzata.
                semantic_grid = _dominant_class_per_cell(
                    semantic_raw, cell_h, cell_w, cell_px)
                # score per cella: -1 vietato (cielo/muro), +1 preferito
                # (pavimento/tavolo), 0.4 neutro. Il vietato PRECEDE il preferito
                # (come l'if/elif originale): applico preferito poi vietato.
                semantic_score_grid = np.full((cell_h, cell_w), 0.4, dtype=np.float32)
                if preferred:
                    semantic_score_grid[np.isin(
                        semantic_grid, np.fromiter(preferred, dtype=np.int64))] = 1.0
                if prohibited:
                    semantic_score_grid[np.isin(
                        semantic_grid, np.fromiter(prohibited, dtype=np.int64))] = -1.0
            if clip_raw is not None:
                clip_grid = clip_raw  # (gy, gx, 512)
            if depth is not None:
                # anchor_edge: zone con forte transizione di depth (bordo strutturale)
                if _HAS_CV2:
                    d_edge = cv2.Sobel(depth, cv2.CV_32F, 1, 0, ksize=3) ** 2 + \
                             cv2.Sobel(depth, cv2.CV_32F, 0, 1, ksize=3) ** 2
                    d_edge = np.sqrt(d_edge)
                else:
                    d_edge = np.abs(np.diff(depth, axis=1, prepend=depth[:, :1])) + \
                             np.abs(np.diff(depth, axis=0, prepend=depth[:1, :]))
                anchor_edge = _aggregate_to_grid(d_edge.astype(np.float32),
                                                  cell_h, cell_w, cell_px, "mean")
                ae_max = anchor_edge.max() if anchor_edge.max() > 1e-6 else 1.0
                anchor_edge = (anchor_edge / ae_max).astype(np.float32)

                # depth_grid (v3): profondita' per cella come NEARNESS 0..1
                # (1 = vicino alla camera). Serve alla scala per profondita'.
                # Tier 1 (Depth Anything) emette disparity-like: alto = vicino,
                # gia' nel verso giusto. Tier 2/3 (Metric3D) emette depth
                # metrica normalizzata: alto = lontano -> inverto.
                dg = _aggregate_to_grid(depth.astype(np.float32),
                                        cell_h, cell_w, cell_px, "mean")
                if model_tier >= 2:
                    dg = 1.0 - dg
                depth_grid = np.clip(dg, 0.0, 1.0).astype(np.float32)

            if normals is not None and normals.ndim == 3:
                # horizontal_score: normale che punta verso l'alto = piano orizzontale
                # In camera coords, "up" e' Y negativo (per immagini), Z verso camera.
                # Approssimazione: |Ny| alto e Nz alto = piano (verticale o orizzontale).
                # Per HO scene usiamo: |Ny| > 0.6 e Nz > 0.5 indica piano "appoggiabile".
                ny = normals[..., 1]
                nz = normals[..., 2]
                # Piano orizzontale generico: |Y component| alto (normale verticale)
                horiz = np.clip(np.abs(ny) - 0.3, 0, 1) * np.clip(nz, 0, 1)
                horizontal_score = _aggregate_to_grid(horiz.astype(np.float32),
                                                      cell_h, cell_w, cell_px, "mean")
                hs_max = horizontal_score.max() if horizontal_score.max() > 1e-6 else 1.0
                horizontal_score = (horizontal_score / hs_max).astype(np.float32)

                # normal_orient: angolo della normale proiettata sul piano XY (per snap rotation)
                # arctan2(Ny_smooth, Nx_smooth)
                nx = normals[..., 0]
                nx_g = _aggregate_to_grid(nx.astype(np.float32), cell_h, cell_w, cell_px, "mean")
                ny_g = _aggregate_to_grid(ny.astype(np.float32), cell_h, cell_w, cell_px, "mean")
                normal_orient = np.arctan2(ny_g, nx_g).astype(np.float32)

            log.info(f"[SCATTER] IA tier{model_tier} processed in {(time.time()-t_ia)*1000:.0f}ms"
                     f" (model: {out.get('ms', 0):.0f}ms)")
        except Exception as e:
            log.exception(f"[SCATTER] IA processing fallito: {e}")
            horizontal_score = None
            anchor_edge = None

    # ── METRICHE AVANZATE per scatter intelligente ────────────────────────
    t_adv = time.time()
    texture_entropy = None
    local_complexity = None
    hideability_map = None
    anchor_points = []
    zone_palettes = {}
    structural_orient = None
    contours = []
    try:
        from editor.tools import bg_cache as _bg_cache
        texture_entropy = _bg_cache.compute_texture_entropy(rgb, cell_h, cell_w, cell_px)
        local_complexity = _bg_cache.compute_local_complexity(rgb, cell_h, cell_w, cell_px)
        hideability_map = _bg_cache.compute_hideability(
            edge_density, saliency, texture_entropy, local_complexity
        )
        anchor_points = _bg_cache.compute_anchor_points(rgb, max_points=300)
        structural_orient = _bg_cache.compute_structural_orient(rgb, cell_h, cell_w, cell_px)
        contours = _bg_cache.compute_bg_contours(rgb, max_contours=400)
        # zone_palettes usa la semantic FULL-RES (H,W) non quella aggregata in celle
        try:
            zone_palettes = _bg_cache.compute_zone_palettes(rgb, semantic_raw_full)
        except Exception as ze:
            log.debug(f"[SCATTER] zone_palettes failed: {ze}")
            zone_palettes = {}
        log.info(f"[SCATTER] advanced metrics in {(time.time()-t_adv)*1000:.0f}ms "
                 f"(entropy+complexity+hideability+{len(anchor_points)} anchors "
                 f"+{len(zone_palettes)} palettes, {len(contours)} contours)")
    except Exception as e:
        log.warning(f"[SCATTER] metriche avanzate fallite: {e}")
        # tieni i defaults (gia' settati sopra)

    # ── FACE DETECTION (v3): zone vietate, tier-indipendente ──────────────
    face_mask = None
    try:
        from editor.tools.face_zones import detect_face_boxes, face_cell_mask
        boxes = detect_face_boxes(rgb, base_path) if base_path is not None else []
        if boxes:
            # body_extend: sotto ogni volto veta anche il box corpo (busto/
            # braccia dei personaggi in piedi), non solo la faccia.
            face_mask = face_cell_mask(boxes, cell_w, cell_h, cell_px,
                                       body_extend=True)
            log.info(f"[SCATTER] face mask: {len(boxes)} volti, "
                     f"{int(face_mask.sum())} celle vietate (corpo incluso)")
    except Exception as e:
        log.warning(f"[SCATTER] face detection fallita: {e}")

    dt = time.time() - t0
    log.info(f"[SCATTER] BG analysis done in {dt:.2f}s")

    bg_result = BGAnalysis(
        bg_w=w, bg_h=h, cell_w=cell_w, cell_h=cell_h, cell_px=cell_px,
        edge_density=edge_density, saliency=saliency,
        hue=hue, sat=sat, val=val, grad_orient=grad_orient,
        model_tier=model_tier,
        horizontal_score=horizontal_score,
        anchor_edge=anchor_edge,
        normal_orient=normal_orient,
        semantic=semantic_grid,
        semantic_score=semantic_score_grid,
        clip_grid=clip_grid,
        hideability_map=hideability_map,
        texture_entropy=texture_entropy,
        local_complexity=local_complexity,
        anchor_points=anchor_points,
        zone_palettes=zone_palettes,
        structural_orient=structural_orient,
        contours=contours,
        bg_sha256=bg_sha,
        face_mask=face_mask,
        depth_grid=depth_grid,
    )

    # ── SAVE CACHE ───────────────────────────────────────────────────────
    if use_cache and base_path is not None and bg_sha is not None:
        try:
            from editor.tools import bg_cache as _bg_cache
            _bg_cache.save(bg_result, model_tier_for_cache, base_path,
                           hideability_map=hideability_map,
                           texture_entropy=texture_entropy,
                           local_complexity=local_complexity,
                           anchor_points=anchor_points,
                           zone_palettes=zone_palettes,
                           structural_orient=structural_orient,
                           contours=contours,
                           face_mask=face_mask,
                           depth_grid=depth_grid)
        except Exception as e:
            log.warning(f"[SCATTER] BG cache save failed: {e}")

    _attach_runtime_color(bg_result, rgb)
    return bg_result


def _rgb_to_hsv_np(rgb: np.ndarray) -> np.ndarray:
    """Fallback RGB->HSV puro numpy (formato OpenCV: H 0..180, S 0..255, V 0..255)."""
    r = rgb[..., 0].astype(np.float32) / 255.0
    g = rgb[..., 1].astype(np.float32) / 255.0
    b = rgb[..., 2].astype(np.float32) / 255.0
    cmax = np.maximum(np.maximum(r, g), b)
    cmin = np.minimum(np.minimum(r, g), b)
    delta = cmax - cmin
    h = np.zeros_like(cmax)
    mask = delta > 1e-6
    rmask = mask & (cmax == r)
    gmask = mask & (cmax == g) & ~rmask
    bmask = mask & (cmax == b) & ~rmask & ~gmask
    h[rmask] = ((g[rmask] - b[rmask]) / delta[rmask]) % 6
    h[gmask] = (b[gmask] - r[gmask]) / delta[gmask] + 2
    h[bmask] = (r[bmask] - g[bmask]) / delta[bmask] + 4
    h = (h * 30).astype(np.float32)  # OpenCV ha H in [0, 180)
    s = np.where(cmax > 1e-6, delta / cmax * 255, 0).astype(np.float32)
    v = (cmax * 255).astype(np.float32)
    return np.stack([h, s, v], axis=-1)


def _attach_runtime_color(analysis: "BGAnalysis", rgb: np.ndarray) -> None:
    """Calcola HSV full-res + uniformita' cromatica per cella e li attacca all'analisi.

    Campi runtime (non in cache). Servono al camouflage PRECISO:
      - hsv_full permette di campionare i pixel reali sotto il footprint
        dell'oggetto invece di affidarsi alla media grossolana della cella;
      - color_uniformity (1 = zona molto uniforme) individua le porzioni dove un
        oggetto dello stesso colore SPARISCE: e' li' che vogliamo mimetizzare.
    """
    try:
        hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV) if _HAS_CV2 else _rgb_to_hsv_np(rgb)
        analysis.hsv_full = hsv
        # Lab full-res per la verifica Delta-E del footprint (v3). Solo con cv2:
        # senza, la verifica degrada a no-op (lab_full resta None).
        if _HAS_CV2:
            analysis.lab_full = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB)
        ch, cw, cpx = analysis.cell_h, analysis.cell_w, analysis.cell_px
        sat_full = hsv[..., 1].astype(np.float32) / 255.0
        val_full = hsv[..., 2].astype(np.float32) / 255.0
        sat_sq = _aggregate_to_grid(sat_full * sat_full, ch, cw, cpx, "mean")
        val_sq = _aggregate_to_grid(val_full * val_full, ch, cw, cpx, "mean")
        sat_var = np.clip(sat_sq - analysis.sat * analysis.sat, 0.0, None)
        val_var = np.clip(val_sq - analysis.val * analysis.val, 0.0, None)
        chroma_std = np.sqrt(sat_var + val_var)
        # 0.22 ~= std oltre la quale la cella e' troppo variegata per un
        # camouflage cromatico affidabile (il colore dell'oggetto staccherebbe).
        analysis.color_uniformity = np.clip(1.0 - chroma_std / 0.22, 0.0, 1.0).astype(np.float32)
    except Exception as e:
        log.warning(f"[SCATTER] runtime color attach fallito: {e}")


def _sample_footprint_hsv(bg: "BGAnalysis", x0: float, y0: float,
                          x1: float, y1: float) -> Optional[tuple[float, float, float]]:
    """Colore HSV (0..1) reale della porzione di sfondo coperta dal footprint.

    Usa la mediana per sat/val (robusta agli outlier) e la media circolare per la
    hue: cattura il colore dominante effettivo sotto l'oggetto, non un sommario
    sfocato della cella da 48px.
    """
    hsv = getattr(bg, "hsv_full", None)
    if hsv is None:
        return None
    H, W = hsv.shape[:2]
    xa = max(0, int(x0)); ya = max(0, int(y0))
    xb = min(W, int(x1)); yb = min(H, int(y1))
    if xb - xa < 2 or yb - ya < 2:
        return None
    patch = hsv[ya:yb, xa:xb].reshape(-1, 3).astype(np.float32)
    ang = patch[:, 0] / 180.0 * 2.0 * math.pi  # hue ciclica
    hx = float(np.mean(np.cos(ang))); hy = float(np.mean(np.sin(ang)))
    h = (math.atan2(hy, hx) / (2.0 * math.pi)) % 1.0
    s = float(np.median(patch[:, 1])) / 255.0
    v = float(np.median(patch[:, 2])) / 255.0
    return (h, s, v)


def _footprint_lab_median(bg: "BGAnalysis", x0: float, y0: float,
                          x1: float, y1: float) -> Optional[tuple[float, float, float]]:
    """Mediana Lab (L 0..100, a/b ~-128..127) del footprint, subsample deterministico."""
    lab = bg.lab_full
    if lab is None:
        return None
    H, W = lab.shape[:2]
    xa = max(0, int(x0)); ya = max(0, int(y0))
    xb = min(W, int(x1)); yb = min(H, int(y1))
    if xb - xa < 2 or yb - ya < 2:
        return None
    sy = max(1, (yb - ya) // DELTAE_PATCH_MAX_SIDE)
    sx = max(1, (xb - xa) // DELTAE_PATCH_MAX_SIDE)
    patch = lab[ya:yb:sy, xa:xb:sx].reshape(-1, 3).astype(np.float32)
    med = np.median(patch, axis=0)
    return (float(med[0]) * (100.0 / 255.0),
            float(med[1]) - 128.0,
            float(med[2]) - 128.0)


def _lab_harmonize_tint(bg: "BGAnalysis", x0: float, y0: float, x1: float, y1: float,
                        difficulty: str) -> Optional[tuple[int, int, int]]:
    """Tint di harmonization in Lab: colore del footprint mixato verso bianco.

    Sostituisce il vecchio tint HSV (mix fisso max 0.35 dipendente dal delta
    hue): qui il mix e' funzione della DIFFICOLTA' (hard fonde di piu') e il
    target e' la mediana Lab reale del footprint, con clamp su L (niente tint
    nero) e mix dimezzato su zone grigie (chroma bassa: iniettare colore
    sarebbe un falso). Il contratto PlacedObject.color_filter (RGB
    moltiplicativo applicato dall'engine) resta invariato: zero modifiche a
    engine/web. Ritorna None se lab_full/cv2 mancano (fallback HSV storico).
    """
    if not _HAS_CV2:
        return None
    med = _footprint_lab_median(bg, x0, y0, x1, y1)
    if med is None:
        return None
    fl, fa, fb = med
    fl = max(fl, TINT_MIN_L)
    mix = TINT_MIX.get(difficulty, TINT_MIX["medium"])
    if math.hypot(fa, fb) < TINT_MIN_CHROMA:
        mix *= 0.5
    lab_px = np.uint8([[[int(round(fl * 255.0 / 100.0)),
                         int(round(min(255.0, max(0.0, fa + 128.0)))),
                         int(round(min(255.0, max(0.0, fb + 128.0))))]]])
    rgb_px = cv2.cvtColor(lab_px, cv2.COLOR_LAB2RGB)[0, 0]
    r, g, b = int(rgb_px[0]), int(rgb_px[1]), int(rgb_px[2])
    # Mix verso bianco: stesso pattern di _hsv_to_tint_rgb (tint "leggero").
    wr = int(mix * r + (1.0 - mix) * 255)
    wg = int(mix * g + (1.0 - mix) * 255)
    wb = int(mix * b + (1.0 - mix) * 255)
    return (max(0, min(255, wr)), max(0, min(255, wg)), max(0, min(255, wb)))


def _obj_dominant_rgb(obj: "ObjAnalysis") -> list[tuple[int, int, int]]:
    """Colori dominanti dell'oggetto in RGB (per applicare il tint prima del
    confronto Lab). Sorgente: cluster palette_ext con w >= 0.15 (fallback:
    primo cluster, poi palette top-3 legacy). Senza cv2 ritorna [].
    """
    if not _HAS_CV2:
        return []
    src: list[tuple[float, float, float]] = []
    if obj.palette_ext:
        src = [(c["h"], c["s"], c["v"]) for c in obj.palette_ext
               if c.get("w", 0.0) >= 0.15]
        if not src:
            c0 = obj.palette_ext[0]
            src = [(c0["h"], c0["s"], c0["v"])]
    elif obj.palette:
        src = [tuple(p) for p in obj.palette[:3]]
    out: list[tuple[int, int, int]] = []
    for h, s, v in src:
        hsv_px = np.uint8([[[int(h * 180) % 180, int(s * 255), int(v * 255)]]])
        rgb_px = cv2.cvtColor(hsv_px, cv2.COLOR_HSV2RGB)[0, 0]
        out.append((int(rgb_px[0]), int(rgb_px[1]), int(rgb_px[2])))
    return out


def _rgb_list_to_lab(rgbs: list[tuple[int, int, int]]
                     ) -> list[tuple[float, float, float]]:
    """RGB -> Lab VERO (L 0..100, a/b ~-128..127). Senza cv2 ritorna []."""
    if not _HAS_CV2 or not rgbs:
        return []
    arr = np.uint8([[list(c) for c in rgbs]])  # (1, N, 3)
    lab = cv2.cvtColor(arr, cv2.COLOR_RGB2LAB)[0].astype(np.float32)
    # OpenCV Lab uint8: L in 0..255 (=L*255/100), a/b con offset +128.
    return [(float(px[0]) * (100.0 / 255.0),
             float(px[1]) - 128.0,
             float(px[2]) - 128.0) for px in lab]


def _obj_dominant_lab(obj: "ObjAnalysis") -> list[tuple[float, float, float]]:
    """Colori dominanti dell'oggetto in Lab vero (senza tint)."""
    return _rgb_list_to_lab(_obj_dominant_rgb(obj))


def _footprint_delta_e(bg: "BGAnalysis",
                       obj_labs: list[tuple[float, float, float]],
                       x0: float, y0: float, x1: float, y1: float) -> Optional[float]:
    """Delta-E 1976 minimo fra la mediana Lab del footprint reale e i colori
    dominanti dell'oggetto (gia' in Lab vero, da _obj_dominant_lab).

    Il patch full-res viene sottocampionato con stride deterministico a lato
    max DELTAE_PATCH_MAX_SIDE (costo costante anche su footprint enormi).
    Ritorna None (verifica non applicabile) se lab_full manca o il patch e'
    degenere: il chiamante in quel caso NON rifiuta.
    """
    if not obj_labs:
        return None
    med = _footprint_lab_median(bg, x0, y0, x1, y1)
    if med is None:
        return None
    bg_l, bg_a, bg_b = med
    best = min(math.sqrt((bg_l - ol) ** 2 + (bg_a - oa) ** 2 + (bg_b - ob) ** 2)
               for ol, oa, ob in obj_labs)
    return float(best)


# ────────────────────────────────────────────────────────────────────────────
# CATALOG PRE-PROCESS
# ────────────────────────────────────────────────────────────────────────────

def _kmeans_palette_rgb(pixels_rgb: np.ndarray, k: int = 3, iters: int = 8) -> np.ndarray:
    """K-means su pixel RGB (0..255). Restituisce k centri in RGB.

    Clustering nello spazio RGB euclideo: stabile, niente problemi di hue ciclica.
    Inizializzazione tipo k-means++: primo centro random, gli altri scelti
    per massima distanza dai precedenti (evita centri ridondanti).
    """
    if len(pixels_rgb) == 0:
        return np.zeros((k, 3), dtype=np.float32)
    if len(pixels_rgb) <= k:
        out = np.zeros((k, 3), dtype=np.float32)
        out[:len(pixels_rgb)] = pixels_rgb
        return out
    rng = np.random.default_rng(42)
    pix = pixels_rgb.astype(np.float32)
    # k-means++ init
    idx0 = int(rng.integers(0, len(pix)))
    centers = [pix[idx0]]
    for _ in range(k - 1):
        d2 = np.min(np.linalg.norm(pix[:, None, :] - np.asarray(centers)[None, :, :], axis=2), axis=1)
        d2 = d2 * d2 + 1e-6
        probs = d2 / d2.sum()
        idx = int(rng.choice(len(pix), p=probs))
        centers.append(pix[idx])
    centers = np.stack(centers).astype(np.float32)
    for _ in range(iters):
        dists = np.linalg.norm(pix[:, None, :] - centers[None, :, :], axis=2)
        labels = dists.argmin(axis=1)
        for ki in range(k):
            mask = labels == ki
            if mask.any():
                centers[ki] = pix[mask].mean(axis=0)
    return centers


def _icon_palette_and_orient(icon_path: Path) -> tuple[list[tuple[float, float, float]], float, float]:
    """Apre un'icona PNG, estrae palette HSV dominante (k=3) e orientamento bordo.

    Restituisce: (palette_normalized_0_1, edge_orient_radians, aspect_ratio).
    Palette normalizzata su 0..1 sia per H, S, V (più comoda per scoring).
    """
    try:
        from PIL import Image
    except ImportError:
        return ([(0.5, 0.5, 0.5)] * 3, 0.0, 1.0)

    try:
        img = Image.open(icon_path).convert("RGBA")
    except Exception as e:
        log.warning(f"[SCATTER] cannot open icon {icon_path}: {e}")
        return ([(0.5, 0.5, 0.5)] * 3, 0.0, 1.0)

    arr = np.array(img)
    if arr.shape[-1] < 4:
        # No alpha → fallback grigio
        return ([(0.5, 0.5, 0.5)] * 3, 0.0, arr.shape[1] / max(1, arr.shape[0]))
    alpha = arr[..., 3]
    rgb = arr[..., :3]
    # PIXEL PURI ONLY: alpha > 200 esclude antialiasing (RGB inquinato dal BG trasparente).
    # Fallback a 128 se troppi pochi pixel "puri", poi a 64 come ultima risorsa.
    mask = alpha > 200
    if mask.sum() < 100:
        mask = alpha > 128
    if mask.sum() < 50:
        mask = alpha > 64
    if not mask.any():
        return ([(0.5, 0.5, 0.5)] * 3, 0.0, arr.shape[1] / max(1, arr.shape[0]))

    # Downsample per velocità (max 4000 pixel per kmeans)
    pixels_rgb = rgb[mask]
    if len(pixels_rgb) > 4000:
        idx = np.random.default_rng(0).choice(len(pixels_rgb), 4000, replace=False)
        pixels_rgb = pixels_rgb[idx]

    # K-means in spazio RGB (stabile, no hue ciclica). Poi conversione a HSV
    # solo per i centri finali — preserva i colori "veri" dell'icona.
    centers_rgb = _kmeans_palette_rgb(pixels_rgb.astype(np.float32), k=3)
    # Ordina i centri per FREQUENZA (n. pixel assegnati): palette[0] diventa il
    # colore PIU' PRESENTE nell'icona, non un cluster di init arbitrario.
    if len(centers_rgb) > 1:
        _pf = pixels_rgb.astype(np.float32)
        _d = np.linalg.norm(_pf[:, None, :] - centers_rgb[None, :, :], axis=2)
        _labels = _d.argmin(axis=1)
        _counts = np.bincount(_labels, minlength=len(centers_rgb)).astype(np.float32)
        centers_rgb = centers_rgb[np.argsort(-_counts)]
    if _HAS_CV2:
        hsv_centers = cv2.cvtColor(
            centers_rgb.reshape(-1, 1, 3).astype(np.uint8), cv2.COLOR_RGB2HSV
        ).reshape(-1, 3).astype(np.float32)
    else:
        hsv_centers = _rgb_to_hsv_np(
            centers_rgb.reshape(-1, 1, 3).astype(np.uint8)
        ).reshape(-1, 3).astype(np.float32)
    palette = [(float(c[0]) / 180.0, float(c[1]) / 255.0, float(c[2]) / 255.0) for c in hsv_centers]

    # Edge orientation dominante sull'icona
    aspect = arr.shape[1] / max(1, arr.shape[0])
    if _HAS_CV2:
        gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
        edges = cv2.Canny(gray, 50, 150)
        edges = edges * (mask.astype(np.uint8))
        sobel_x = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3) * edges / 255.0
        sobel_y = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3) * edges / 255.0
        if edges.sum() > 0:
            mean_x = sobel_x.sum() / max(1, edges.sum() / 255.0)
            mean_y = sobel_y.sum() / max(1, edges.sum() / 255.0)
            orient = float(math.atan2(mean_y, mean_x))
        else:
            orient = 0.0
    else:
        orient = 0.0

    return palette, orient, aspect


def precompute_catalog(
    catalog: Sequence[dict],
    style: str,
    base_path: Path,
    *,
    force_rebuild: bool = False,
    clip_model=None,  # editor.tools.scatter_models.ClipVisual istanza, opzionale
) -> dict[str, ObjAnalysis]:
    """Pre-calcola palette + orient (+ CLIP emb se clip_model fornito) per ogni oggetto.

    Cache su disco: <base_path>/.editor_cache/scatter_<style>.json (palette/orient).
    Cache CLIP embeddings: scatter_clip_<style>.npz (separato, opzionale).
    """
    cache_dir = base_path / CATALOG_CACHE_DIR
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / f"scatter_{style.replace(' ', '_')}.json"
    clip_cache_file = cache_dir / f"scatter_clip_{style.replace(' ', '_')}.npz"

    style_pool = [c for c in catalog if c.get("style", "real") == style]
    if not style_pool:
        log.warning(f"[SCATTER] nessun oggetto con style='{style}' nel catalogo")
        return {}

    catalog_lookup = {c["id"]: c for c in style_pool}
    ids = sorted(c["id"] for c in style_pool)
    fingerprint = {"v": CATALOG_CACHE_VERSION, "ids": ids}

    analyses: dict[str, ObjAnalysis] = {}
    loaded_from_cache = False

    # Tenta cache (palette + orient)
    if cache_file.exists() and not force_rebuild:
        try:
            with open(cache_file, encoding="utf-8") as f:
                cached = json.load(f)
            if cached.get("fingerprint") == fingerprint:
                log.info(f"[SCATTER] catalog cache HIT for '{style}' ({len(ids)} items)")
                for cid, data in cached["analyses"].items():
                    analyses[cid] = ObjAnalysis(
                        catalog_id=cid,
                        palette=[tuple(p) for p in data["palette"]],
                        edge_orient=data["edge_orient"],
                        aspect=data["aspect"],
                        size_class=data["size_class"],
                    )
                loaded_from_cache = True
        except Exception as e:
            log.warning(f"[SCATTER] cache read failed ({e}), rebuilding")
            analyses = {}

    # Rebuild palette+orient (solo se non da cache)
    if not loaded_from_cache:
        log.info(f"[SCATTER] precomputing catalog '{style}' ({len(ids)} items)...")
        t0 = time.time()
        for entry in style_pool:
            cid = entry["id"]
            icon_rel = entry.get("icon", "")
            candidates = [
                base_path / "engine" / "assets" / icon_rel,
                base_path / icon_rel,
            ]
            icon_path = next((p for p in candidates if p.exists()), None)
            if not icon_path:
                log.debug(f"[SCATTER] icon missing for {cid}: {icon_rel}")
                continue

            palette, orient, aspect = _icon_palette_and_orient(icon_path)

            tags = entry.get("tags", [])
            if "piccolo" in tags:
                size_class = "small"
            elif "grande" in tags:
                size_class = "big"
            else:
                size_class = "mid"

            analyses[cid] = ObjAnalysis(
                catalog_id=cid, palette=palette, edge_orient=orient,
                aspect=aspect, size_class=size_class,
            )

        dt = time.time() - t0
        log.info(f"[SCATTER] precompute done {len(analyses)}/{len(ids)} in {dt:.2f}s")

    # Save cache (palette + orient) — solo se rebuild
    if not loaded_from_cache:
        try:
            payload = {
                "fingerprint": fingerprint,
                "analyses": {
                    cid: {
                        "palette": [list(p) for p in a.palette],
                        "edge_orient": a.edge_orient,
                        "aspect": a.aspect,
                        "size_class": a.size_class,
                    }
                    for cid, a in analyses.items()
                },
            }
            tmp = cache_file.with_suffix(".json.tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
            import os
            os.replace(tmp, cache_file)
            log.info(f"[SCATTER] cache saved: {cache_file}")
        except Exception as e:
            log.warning(f"[SCATTER] cache write failed: {e}")

    # ── OBJECT PROFILES (zero-shot CLIP context affinity, da SQLite) ──────
    # Carica i profili context per ogni oggetto se il DB esiste.
    try:
        from editor.tools.object_profiles import get_profiles_for_style
        prof_dict = get_profiles_for_style(style, base_path)
        loaded_profs = 0
        for cid, rec in prof_dict.items():
            if cid in analyses:
                analyses[cid].context_profile = rec.profile
                loaded_profs += 1
        if loaded_profs:
            log.info(f"[SCATTER] loaded {loaded_profs} context profiles for '{style}' (from SQLite)")
    except Exception as e:
        log.debug(f"[SCATTER] object_profiles non disponibile ({e})")

    # ── SHAPE METRICS (silhouette / PCA / compactness, da SQLite) ─────────
    # Carica le metriche di forma reale (canale alpha) per ogni oggetto.
    try:
        from editor.tools.object_shapes import get_shapes_for_style
        shapes_dict = get_shapes_for_style(style, base_path)
        loaded_shapes = 0
        for cid, shape_data in shapes_dict.items():
            if cid in analyses:
                analyses[cid].shape = shape_data
                loaded_shapes += 1
        if loaded_shapes:
            log.info(f"[SCATTER] loaded {loaded_shapes} shape metrics for '{style}' (from SQLite)")
    except Exception as e:
        log.debug(f"[SCATTER] object_shapes non disponibile ({e})")

    # ── PALETTE ESTESA (k=8 con frequency/variance, da SQLite) ────────────
    # Carica la palette dettagliata. Se mancante per un oggetto, la calcoliamo
    # al volo dal PNG e la salviamo (auto-backfill, una volta per oggetto).
    try:
        from editor.tools.object_palette import (
            get_palettes_for_style, compute_palette_extended,
            save_palette, ensure_palette_columns,
        )
        ensure_palette_columns(base_path)
        pal_dict = get_palettes_for_style(style, base_path)
        loaded_pal = 0
        backfilled = 0
        for cid, an in analyses.items():
            if cid in pal_dict:
                an.palette_ext = pal_dict[cid]
                loaded_pal += 1
                continue
            # Backfill: ricalcola dal PNG
            entry = catalog_lookup.get(cid)
            if not entry:
                continue
            icon_rel = entry.get("icon", "")
            candidates = [
                base_path / "engine" / "assets" / icon_rel,
                base_path / icon_rel,
            ]
            icon_path = next((q for q in candidates if q.exists()), None)
            if not icon_path:
                continue
            clusters = compute_palette_extended(icon_path)
            if not clusters:
                continue
            try:
                save_palette(base_path, cid, style, clusters)
            except Exception as se:
                log.debug(f"[SCATTER] palette save fail {cid}: {se}")
            an.palette_ext = [
                {"h": c.h, "s": c.s, "v": c.v, "w": c.w, "var": c.var}
                for c in clusters
            ]
            backfilled += 1
        if loaded_pal or backfilled:
            log.info(f"[SCATTER] palette ext '{style}': {loaded_pal} loaded, "
                     f"{backfilled} backfilled")
    except Exception as e:
        log.debug(f"[SCATTER] palette estesa non disponibile ({e})")

    # ── CLIP embeddings (opzionale, solo se richiesto) ────────────────────
    if clip_model is not None:
        # Tenta cache esistente
        clip_loaded = False
        if clip_cache_file.exists() and not force_rebuild:
            try:
                data = np.load(clip_cache_file, allow_pickle=False)
                cached_ids = list(data["ids"])
                cached_emb = data["emb"]
                if cached_ids == sorted(analyses.keys()):
                    for i, cid in enumerate(cached_ids):
                        if cid in analyses:
                            analyses[cid].clip_emb = cached_emb[i]
                    log.info(f"[SCATTER] CLIP cache HIT '{style}' ({len(cached_ids)} items)")
                    clip_loaded = True
            except Exception as e:
                log.warning(f"[SCATTER] CLIP cache read failed ({e}), rebuild")

        if not clip_loaded:
            log.info(f"[SCATTER] precomputing CLIP embeddings '{style}'...")
            t0 = time.time()
            try:
                from PIL import Image
            except ImportError:
                log.warning("[SCATTER] PIL non disponibile, skip CLIP embeddings")
                return analyses
            for entry in style_pool:
                cid = entry["id"]
                if cid not in analyses:
                    continue
                icon_rel = entry.get("icon", "")
                candidates = [
                    base_path / "engine" / "assets" / icon_rel,
                    base_path / icon_rel,
                ]
                icon_path = next((p for p in candidates if p.exists()), None)
                if not icon_path:
                    continue
                try:
                    img = Image.open(icon_path).convert("RGB")
                    arr = np.array(img)
                    analyses[cid].clip_emb = clip_model.encode_image(arr)
                except Exception as e:
                    log.debug(f"[SCATTER] CLIP encode failed for {cid}: {e}")
            dt = time.time() - t0
            log.info(f"[SCATTER] CLIP embeddings done in {dt:.1f}s")
            # Save cache
            try:
                ids = sorted(analyses.keys())
                emb_matrix = np.zeros((len(ids), 512), dtype=np.float32)
                for i, cid in enumerate(ids):
                    if analyses[cid].clip_emb is not None:
                        emb_matrix[i] = analyses[cid].clip_emb
                np.savez(clip_cache_file, ids=np.array(ids), emb=emb_matrix)
                log.info(f"[SCATTER] CLIP cache saved: {clip_cache_file}")
            except Exception as e:
                log.warning(f"[SCATTER] CLIP cache write failed: {e}")

    return analyses


# ────────────────────────────────────────────────────────────────────────────
# SAMPLING / PLACEMENT
# ────────────────────────────────────────────────────────────────────────────

# Difficulty presets: pesi delle 6 leve
# (w_edge, w_low_saliency, w_color, w_orient, w_anticluster, jitter)
DIFFICULTY_PRESETS = {
    # w_profile: bonus per affinity zero-shot oggetto<->classe ADE20K (DB SQLite)
    # w_shape: matching forma oggetto <-> struttura locale BG (compactness, axis alignment)
    # NB: il COLORE e' il segnale primario di mimetismo (un oggetto si nasconde
    # bene dove il suo colore dominante combacia col fondo). edge/profile/clip
    # sono secondari (tie-breaker / plausibilita'); w_semantic resta per FRENARE
    # i posti impossibili (cielo/muro, score negativo) piu' che per attrarre.
    "easy":   {"w_edge": 0.35, "w_sal": 0.2, "w_color": 0.6, "w_orient": 0.1,
               "w_cluster": 0.3, "w_support": 0.3, "w_anchor": 0.2,
               "w_semantic": 0.5, "w_clip": 0.2, "w_profile": 0.4,
               "w_shape": 0.3, "w_shape_match": 0.20, "w_physics": 0.30,
               "jitter": 0.6},
    "medium": {"w_edge": 0.5, "w_sal": 0.45, "w_color": 1.2, "w_orient": 0.35,
               "w_cluster": 0.6, "w_support": 0.5, "w_anchor": 0.35,
               "w_semantic": 0.7, "w_clip": 0.35, "w_profile": 0.7,
               "w_shape": 0.7, "w_shape_match": 0.45, "w_physics": 0.55,
               "jitter": 0.4},
    "hard":   {"w_edge": 0.65, "w_sal": 0.8, "w_color": 1.8, "w_orient": 0.6,
               "w_cluster": 0.8, "w_support": 0.7, "w_anchor": 0.5,
               "w_semantic": 0.95, "w_clip": 0.5, "w_profile": 1.0,
               "w_shape": 1.1, "w_shape_match": 0.75, "w_physics": 0.9,
               "jitter": 0.2},
}

# Style overrides: moltiplicatori applicati ai pesi di difficolta'.
# line_art e' bianco/nero: hue/sat sono rumore, conta solo edge/forma/struttura.
# cartoon ha palette satura e forme nette: enfasi su colore e forma.
# real (default) usa i pesi base senza override.
STYLE_WEIGHT_OVERRIDES = {
    "line_art": {
        "w_color":       0.0,   # B/N: disabilita color matching e tint
        "w_edge":        1.30,  # edge density e' il segnale dominante
        "w_orient":      1.40,  # allineamento alle linee del BG
        "w_shape":       1.50,  # la forma e' l'unico discriminante visivo
        "w_shape_match": 2.00,  # match Hu con contorni BG: trompe-l'oeil massimo
        "w_physics":     0.80,  # scene line_art hanno meno semantic info affidabile
        "w_clip":        0.50,  # CLIP e' poco discriminante su immagini B/N
    },
    "cartoon": {
        "w_color":       1.30,  # palette satura e piatta: il colore e' affidabilissimo
        "w_shape":       1.20,
        "w_shape_match": 1.30,
        "w_physics":     1.00,
        "w_edge":        0.85,
    },
}


def _get_weights(difficulty: str, style: str = "real") -> dict:
    """Pesi di scoring per (difficulty, style). Style applica multiplier sui pesi base."""
    base = dict(DIFFICULTY_PRESETS.get(difficulty, DIFFICULTY_PRESETS["medium"]))
    overrides = STYLE_WEIGHT_OVERRIDES.get(style, {})
    for key, mult in overrides.items():
        if key in base:
            base[key] = base[key] * mult
    return base


def _hue_distance(h1: float, h2: float) -> float:
    """Distanza ciclica fra due Hue normalizzate 0..1 (output 0..0.5)."""
    d = abs(h1 - h2)
    return min(d, 1.0 - d)


def _orient_match(o1: float, o2: float) -> float:
    """Quanto sono allineati due angoli (-pi..pi). Output 0..1 (1 = paralleli o anti-paralleli)."""
    # Trattiamo gli angoli mod pi (direzione gradiente, non senso)
    diff = abs((o1 - o2 + math.pi / 2) % math.pi - math.pi / 2)  # 0..pi/2
    return 1.0 - (diff / (math.pi / 2))


def _shape_match_map_for_object(bg: BGAnalysis, obj_hu: list) -> Optional[np.ndarray]:
    """Per ogni cella della grid, score [0..1] di similarita' di forma fra l'oggetto
    (descritto dai suoi 7 Hu moments log-signed) e i contorni del BG vicini.

    Logica:
      - Per ogni contorno BG, calcola I1-style distance sui Hu inversi.
      - Converte la distanza in score via exp(-dist).
      - "Splasha" lo score sulle celle coperte dal bbox del contorno con
        falloff gaussiano dal centro.

    Restituisce None se non ci sono contorni o Hu validi.
    """
    if not bg.contours or obj_hu is None or len(obj_hu) != 7:
        return None
    cell_h, cell_w = bg.edge_density.shape
    cell_px = bg.cell_px
    out = np.zeros((cell_h, cell_w), dtype=np.float32)
    obj_arr = np.asarray(obj_hu, dtype=np.float32)
    inv_obj = np.where(np.abs(obj_arr) > 1e-10, 1.0 / obj_arr, 0.0)

    for c in bg.contours:
        hu_c = c.get("hu")
        if hu_c is None or len(hu_c) != 7:
            continue
        hu_arr = np.asarray(hu_c, dtype=np.float32)
        inv_c = np.where(np.abs(hu_arr) > 1e-10, 1.0 / hu_arr, 0.0)
        dist = float(np.sum(np.abs(inv_obj - inv_c)))
        # exp falloff: dist=0 -> 1.0, dist=1 -> 0.37, dist=3 -> 0.05
        score = math.exp(-dist)
        if score < 0.08:
            continue
        cx_cell = c["cx"] / cell_px
        cy_cell = c["cy"] / cell_px
        rx = max(1.0, (c["w"] / cell_px) * 0.5)
        ry = max(1.0, (c["h"] / cell_px) * 0.5)
        radius = max(rx, ry)
        cy_min = max(0, int(cy_cell - radius))
        cy_max = min(cell_h - 1, int(cy_cell + radius))
        cx_min = max(0, int(cx_cell - radius))
        cx_max = min(cell_w - 1, int(cx_cell + radius))
        if cy_min > cy_max or cx_min > cx_max:
            continue
        yy, xx = np.mgrid[cy_min:cy_max + 1, cx_min:cx_max + 1]
        d2 = ((yy - cy_cell) ** 2 + (xx - cx_cell) ** 2) / (radius * radius + 1e-6)
        local = (np.exp(-d2) * score).astype(np.float32)
        sub = out[cy_min:cy_max + 1, cx_min:cx_max + 1]
        np.maximum(sub, local, out=sub)
    # Normalizzazione lieve: porta il max a 1 senza distorcere troppo i ranking
    mx = float(out.max())
    if mx > 1e-6:
        out = out / max(mx, 0.5)  # se max e' gia' < 0.5, non amplificare oltre 1
        out = np.clip(out, 0.0, 1.0)
    return out


def _best_contour_for_cell(bg: BGAnalysis, obj_hu: list,
                            cx_px: float, cy_px: float,
                            obj_aspect_real: Optional[float] = None
                            ) -> tuple[Optional[dict], float]:
    """Trova il contour BG che meglio matcha (forma + posizione) il punto (cx_px, cy_px).

    Score combinato:
      hu_score       (exp(-I1_distance) sui Hu inversi)
      * proximity    (decadimento esponenziale rispetto al raggio del contour)
      * aspect_match (1 - |aspect_obj - aspect_contour|, floor 0.3)

    Restituisce (contour_dict | None, combined_score 0..1).
    """
    if not bg.contours or obj_hu is None or len(obj_hu) != 7:
        return None, 0.0
    obj_arr = np.asarray(obj_hu, dtype=np.float32)
    inv_obj = np.where(np.abs(obj_arr) > 1e-10, 1.0 / obj_arr, 0.0)
    best = None
    best_score = 0.0
    cell_px = bg.cell_px
    for c in bg.contours:
        hu_c = c.get("hu")
        if hu_c is None or len(hu_c) != 7:
            continue
        hu_arr = np.asarray(hu_c, dtype=np.float32)
        inv_c = np.where(np.abs(hu_arr) > 1e-10, 1.0 / hu_arr, 0.0)
        dist = float(np.sum(np.abs(inv_obj - inv_c)))
        hu_score = math.exp(-dist)
        if hu_score < 0.10:
            continue
        # Proximity: distanza dal centro normalizzata al raggio del contour
        dx = cx_px - c["cx"]
        dy = cy_px - c["cy"]
        radius = max(c["w"], c["h"]) / 2.0
        dist_norm = math.hypot(dx, dy) / max(radius, float(cell_px))
        proximity = math.exp(-dist_norm)  # 1 al centro, ~0.37 al raggio
        # Aspect match (opzionale)
        aspect_match = 1.0
        if obj_aspect_real is not None:
            aspect_match = max(0.3, 1.0 - abs(c["aspect"] - obj_aspect_real))
        score = hu_score * proximity * aspect_match
        if score > best_score:
            best_score = score
            best = c
    return best, best_score


def _visibility_score(bg: BGAnalysis, obj_an: ObjAnalysis, cy: int, cx: int,
                      anchor_below_val: float, style: str) -> float:
    """Qualita' del nascondiglio 0..~1 per la cella scelta (piu' alto = piu'
    nascosto). Estratta dal loop di place_objects per l'enforcement della banda
    di visibilita' e per i test. Per line_art il colore vale 0 (B/N): il peso
    si sposta su edge. Pura e deterministica.
    """
    if style == "line_art":
        vs = (
            0.45 * float(bg.edge_density[cy, cx])
            + 0.30 * float(1.0 - bg.saliency[cy, cx])
            + 0.10 * anchor_below_val
        )
    else:
        vs = (
            0.30 * float(bg.edge_density[cy, cx])
            + 0.30 * float(1.0 - bg.saliency[cy, cx])
            + 0.15 * _color_similarity(obj_an.palette, float(bg.hue[cy, cx]),
                                       float(bg.sat[cy, cx]), float(bg.val[cy, cx]))
            + 0.10 * anchor_below_val
        )
    if bg.horizontal_score is not None:
        vs += 0.15 * float(bg.horizontal_score[cy, cx])
    else:
        vs += 0.15 * 0.5  # neutro
    return vs


def _color_similarity(obj_palette: list[tuple[float, float, float]],
                      hue: float, sat: float, val: float) -> float:
    """Score 0..1 di quanto la palette dell'oggetto si fonde con la zona."""
    if not obj_palette:
        return 0.5
    best = 0.0
    for h, s, v in obj_palette:
        # Hue distance pesa di più; sat/val differences pesano meno
        d_h = _hue_distance(h, hue) * 2.0  # 0..1
        d_s = abs(s - sat)
        d_v = abs(v - val)
        # Per oggetti grigi (saturation bassa), hue non conta
        if s < 0.15 and sat < 0.15:
            score = 1.0 - (d_v + d_s) / 2
        else:
            score = 1.0 - (0.6 * d_h + 0.2 * d_s + 0.2 * d_v)
        if score > best:
            best = score
    return float(max(0.0, min(1.0, best)))


def _region_extent_for_cell(bg: "BGAnalysis", cx_px: float, cy_px: float,
                            max_window_px: float
                            ) -> Optional[tuple[float, float, float, float]]:
    """Stima la regione di sfondo cromaticamente omogenea attorno al punto.

    Cresce (connected component) i pixel simili al seed in HSV su `hsv_full`,
    dentro una finestra locale (per costo contenuto), e ne misura il minAreaRect.

    Ritorna (rw, rh, angle_long_deg, confidence) in px BG, o None:
      - rw, rh: lati del rettangolo orientato minimo della regione;
      - angle_long_deg: orientamento del lato LUNGO (0..180, 0 = orizzontale);
      - confidence 0..1: alta se la regione e' ben delimitata DENTRO la finestra
        (se tocca tutti i bordi la sua estensione e' ambigua -> confidence bassa).
    """
    hsv = getattr(bg, "hsv_full", None)
    if hsv is None or not _HAS_CV2:
        return None
    H, W = hsv.shape[:2]
    win = int(max(24.0, max_window_px))
    x0 = max(0, int(cx_px - win)); y0 = max(0, int(cy_px - win))
    x1 = min(W, int(cx_px + win)); y1 = min(H, int(cy_px + win))
    if x1 - x0 < 8 or y1 - y0 < 8:
        return None
    roi = hsv[y0:y1, x0:x1]
    sx = min(max(int(cx_px) - x0, 0), roi.shape[1] - 1)
    sy = min(max(int(cy_px) - y0, 0), roi.shape[0] - 1)
    h0 = float(roi[sy, sx, 0]); s0 = float(roi[sy, sx, 1]); v0 = float(roi[sy, sx, 2])
    hh = roi[..., 0].astype(np.float32)
    ss = roi[..., 1].astype(np.float32)
    vv = roi[..., 2].astype(np.float32)
    dh = np.abs(hh - h0); dh = np.minimum(dh, 180.0 - dh)   # hue ciclica (0..180)
    ds = np.abs(ss - s0); dv = np.abs(vv - v0)
    # Su zone poco sature la hue e' rumore: ci si affida a sat/val.
    if s0 < 40:
        mask = (ds < 45) & (dv < 45)
    else:
        mask = (dh < 14) & (ds < 55) & (dv < 60)
    mask_u8 = mask.astype(np.uint8)
    try:
        kernel = np.ones((3, 3), np.uint8)
        mask_u8 = cv2.morphologyEx(mask_u8, cv2.MORPH_CLOSE, kernel)
        num, labels = cv2.connectedComponents(mask_u8, connectivity=4)
        lab = int(labels[sy, sx])
        if lab == 0:
            return None
        comp = (labels == lab).astype(np.uint8)
        area_comp = int(comp.sum())
        if area_comp < 16:
            return None
        cnts, _ = cv2.findContours(comp, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not cnts:
            return None
        cnt = max(cnts, key=cv2.contourArea)
        (_rcx, _rcy), (rw, rh), angle = cv2.minAreaRect(cnt)
    except Exception:
        return None
    if rw < 2 or rh < 2:
        return None
    fill = area_comp / max(1.0, rw * rh)
    borders = (int(comp[:, 0].any()) + int(comp[:, -1].any())
               + int(comp[0, :].any()) + int(comp[-1, :].any()))
    bounded = {0: 1.0, 1: 1.0, 2: 0.6, 3: 0.3, 4: 0.12}[borders]
    conf = float(max(0.0, min(1.0, fill)) * bounded)
    long_is_w = rw >= rh
    angle_long = angle if long_is_w else angle + 90.0
    return (float(rw), float(rh), float(angle_long % 180.0), conf)


@dataclass
class PlacedObject:
    """Risultato del piazzamento di un singolo oggetto."""
    catalog_id: str
    x: float
    y: float
    scale: float
    rotation: float
    flip_x: bool
    flip_y: bool
    alpha: int
    color_filter: tuple[int, int, int]
    detection_type: str
    width: float
    height: float
    radius: float
    layer: str
    visibility_score: float = 0.0


def _color_similarity_map(bg: BGAnalysis, obj: ObjAnalysis) -> np.ndarray:
    """Similarita' colore PURA per cella (cell_h, cell_w), 0..1.

    Usa palette_ext (k=8 con frequency e variance) se disponibile, altrimenti
    fallback alla palette top-3 storica. Per ciascun cluster: hue ciclico +
    sat + val, score 0..1. Output per cella = blend fra il match del colore
    dominante e la somma pesata per frequency (preserva il contributo dei
    colori secondari invece di prendere solo il max).

    NB: NON applica _uniformity_reweight (lo fa _build_base_score_matrix, per
    mantenere l'ordine delle operazioni bit-identico). Funzione pura e
    deterministica: e' la sorgente sia del termine additivo w_color sia del
    gate colore duro (_build_color_gate).
    """
    cs = np.zeros_like(bg.edge_density)
    palette_iter = None
    if obj.palette_ext:
        palette_iter = obj.palette_ext  # list of dicts {h,s,v,w,var}
        w_sum = sum(c.get("w", 0.0) for c in palette_iter) or 1.0
    if palette_iter:
        # cs_w  = match medio pesato sull'intera palette (coerenza globale)
        # cs_dom = miglior match fra i colori DOMINANTI (w>=0.15)
        # Blend: premia il colore dominante senza ignorare il resto. Evita la
        # diluizione che penalizzava gli oggetti multi-colore (es. ciambella
        # rosa con foro scuro) anche su una zona perfettamente rosa.
        cs_w = np.zeros_like(cs)
        cs_dom = np.zeros_like(cs)
        for c in palette_iter:
            h = c["h"]; ss = c["s"]; vv = c["v"]; ww = c.get("w", 0.0)
            if ww < 0.01:  # cluster trascurabili
                continue
            score = _cluster_color_score(bg, h, ss, vv)
            cs_w = cs_w + (ww / w_sum) * score
            if ww >= 0.15:
                cs_dom = np.maximum(cs_dom, score)
        cs = np.clip(0.6 * cs_dom + 0.4 * cs_w, 0.0, 1.0)
    else:
        # Fallback: palette top-3 senza pesi (legacy)
        for h, s, v in obj.palette:
            cs = np.maximum(cs, _cluster_color_score(bg, h, s, v))
        cs = np.clip(cs, 0.0, 1.0)
    return cs


def _cluster_color_score(bg: BGAnalysis, h: float, ss: float, vv: float) -> np.ndarray:
    """Match 0..1 di UN colore HSV dell'oggetto contro ogni cella del BG.

    v3.2: mismatch di CROMA esplicito nei due sensi.
      - Cluster grigio (ss < CHROMA_NEUTRAL_SAT): hue irrilevante, match su
        sat/val MA penalita' crescente con la saturazione del BG (un grigio
        su una zona satura stacca: il vecchio percorso dava match alti a un
        toaster metallico sugli alberi verdi).
      - Cluster saturo su cella quasi grigia: la hue del BG e' rumore, il
        termine hue non discrimina; match su sat/val con penalita'
        proporzionale alla saturazione dell'oggetto (un oggetto colorato su
        una zona grigia stacca).
    """
    d_h = np.minimum(np.abs(bg.hue - h), 1.0 - np.abs(bg.hue - h)) * 2.0
    d_s = np.abs(bg.sat - ss)
    d_v = np.abs(bg.val - vv)
    if ss < CHROMA_NEUTRAL_SAT:
        score = 1.0 - (0.5 * d_s + 0.5 * d_v)
        score = score - GRAY_ON_SAT_PENALTY * np.clip(
            bg.sat - GRAY_PENALTY_SAT_START, 0.0, 1.0)
    else:
        score = 1.0 - (0.6 * d_h + 0.2 * d_s + 0.2 * d_v)
        bg_gray = bg.sat < CHROMA_NEUTRAL_SAT
        score_on_gray = 1.0 - (0.5 * d_s + 0.3 * d_v) - SAT_ON_GRAY_PENALTY * ss
        score = np.where(bg_gray, score_on_gray, score)
    return np.clip(score, 0.0, 1.0)


def _build_color_gate(bg: BGAnalysis, obj: ObjAnalysis, weights: dict,
                      difficulty: str) -> Optional[np.ndarray]:
    """Maschera bool (cell_h, cell_w) di celle VIETATE per match colore scarso.

    True = cella vetata per questo oggetto. Il gate rende reale il requisito
    "l'oggetto atterra su una zona dello stesso colore": senza gate, un pessimo
    match cromatico veniva compensato dagli altri termini additivi.

      - Veto base: cs_raw < COLOR_GATE_MIN[difficulty].
      - Sub-gate zone piatte: su celle a bassa entropia/edge (muro nudo, tavolo
        vuoto) un oggetto e' in bella vista, ammesso solo se cs >= FLAT_COLOR_MIN.
      - Relax deterministico: se le celle valide sono troppo poche, la soglia
        scende a passi di COLOR_GATE_RELAX_STEP; sotto COLOR_GATE_FLOOR il gate
        prova senza sub-gate piatto, e in ultima istanza si disattiva (None)
        invece di svuotare il piazzamento.

    Ritorna None (gate disattivo) se w_color <= 0 (es. line_art) o se anche il
    relax completo lascerebbe troppo poche celle. Pura e RNG-free: cacheable
    per catalog_id (stesso contratto di determinismo della base matrix).
    """
    if weights.get("w_color", 0.0) <= 0.0:
        return None
    cs_raw = _color_similarity_map(bg, obj)
    n_cells = cs_raw.size
    min_allowed = max(COLOR_GATE_MIN_CELLS, int(COLOR_GATE_MIN_FRAC * n_cells))

    flat = None
    if bg.texture_entropy is not None:
        flat = ((bg.texture_entropy < FLAT_ENTROPY_MAX)
                & (bg.edge_density < FLAT_EDGE_MAX))

    thr = COLOR_GATE_MIN.get(difficulty, COLOR_GATE_MIN["medium"])
    while thr >= COLOR_GATE_FLOOR:
        veto = cs_raw < thr
        if flat is not None:
            veto = veto | (flat & (cs_raw < FLAT_COLOR_MIN))
        if int((~veto).sum()) >= min_allowed:
            return veto
        thr -= COLOR_GATE_RELAX_STEP
    # Ultimo tentativo: soglia al floor SENZA sub-gate piatto (e' spesso il
    # sub-gate a svuotare BG molto uniformi).
    veto = cs_raw < COLOR_GATE_FLOOR
    if int((~veto).sum()) >= min_allowed:
        log.debug(f"[SCATTER] color gate '{obj.catalog_id}': relax a floor senza flat-gate")
        return veto
    log.warning(f"[SCATTER] color gate '{obj.catalog_id}': nessuna soglia lascia "
                f">={min_allowed} celle, gate disattivato")
    return None


def _build_base_score_matrix(
    bg: BGAnalysis,
    obj: ObjAnalysis,
    weights: dict,
) -> np.ndarray:
    """Parte OBJECT-INVARIANT della matrice di score (cell_h, cell_w).

    Contiene tutti i termini che dipendono solo da (bg, obj, weights) e NON dallo
    stato di piazzamento: e' quindi cacheabile per catalog_id ed e' la parte
    COSTOSA (color similarity, profile, clip, shape-match). I termini per-tentativo
    (anti-cluster w_cluster*occupied, jitter, veto semantico) sono aggiunti da
    _build_score_matrix(). Nessuna estrazione random qui dentro.
    """
    # ── COLOR SIMILARITY per cella (estratta in _color_similarity_map) ────
    cs = _color_similarity_map(bg, obj)

    # ── CAMOUFLAGE PRECISO: premia le zone cromaticamente uniformi ──────────
    # La media per cella mente: una zona variegata puo' avere una media che
    # combacia con l'oggetto pur facendolo staccare. color_uniformity (da std
    # cromatica reale) distingue le porzioni dove l'oggetto SPARISCE davvero.
    # Boost moltiplicativo dove match e uniformita' sono entrambi alti; non
    # penalizza il camuffamento da clutter (gestito dal termine edge).
    if bg.color_uniformity is not None:
        cs = _uniformity_reweight(cs, bg.color_uniformity)

    # Orient match
    if abs(obj.edge_orient) > 1e-3:
        diff = np.abs(((bg.grad_orient - obj.edge_orient) + math.pi / 2) % math.pi - math.pi / 2)
        om = 1.0 - diff / (math.pi / 2)
    else:
        om = np.zeros_like(bg.edge_density)

    # Combine: pesi classici (il termine anti-cluster w_cluster*occupied e' aggiunto
    # da _build_score_matrix perche' dipende dallo stato di piazzamento corrente).
    s = (
        weights["w_edge"]   * bg.edge_density
        + weights["w_sal"]    * (1.0 - bg.saliency)
        + weights["w_color"]  * cs
        + weights["w_orient"] * om
    )

    # Bonus IA tier 2: piani orizzontali + bordi strutturali
    if bg.horizontal_score is not None and "w_support" in weights:
        s = s + weights["w_support"] * bg.horizontal_score
    if bg.anchor_edge is not None and "w_anchor" in weights:
        s = s + weights["w_anchor"] * bg.anchor_edge

    # Bonus IA tier 3 ULTRA: semantic (floor/table) e CLIP similarity
    if bg.semantic_score is not None and "w_semantic" in weights:
        # semantic_score: -1 prohibited (sky/wall), 0.4 neutro, 1.0 preferred.
        # v3: rimappato in [0,1] prima del peso — un termine SIGNED [-1,1] in una
        # somma di termini [0,1] aveva scala doppia e distorceva il ranking
        # (audit #1). Il divieto delle zone prohibited e' gestito ESCLUSIVAMENTE
        # dal veto duro in _build_score_matrix, non da questa penalita' additiva.
        s = s + weights["w_semantic"] * (bg.semantic_score + 1.0) * 0.5

    # ── OBJECT PROFILE: affinity zero-shot oggetto -> classe ADE20K per cella ──
    # Mappa context_profile + bg.semantic (classe per cella) -> score matrix
    if (bg.semantic is not None and obj.context_profile is not None
            and "w_profile" in weights):
        from editor.tools.object_profiles import ADE_TO_CONTEXT
        # Pre-calcolo: per ogni classe ADE20K presente nel grid, qual e' lo score profile?
        unique_classes = np.unique(bg.semantic)
        prof_lookup = {}
        for cls in unique_classes:
            ctx = ADE_TO_CONTEXT.get(int(cls))
            if ctx:
                prof_lookup[int(cls)] = float(obj.context_profile.get(ctx, 0.0))
            else:
                prof_lookup[int(cls)] = 0.15  # neutro per classi non mappate
        # Vectorize: profile_score[cy, cx] = prof_lookup[semantic[cy, cx]]
        profile_score = np.zeros_like(s)
        for cls, val in prof_lookup.items():
            mask = (bg.semantic == cls)
            profile_score[mask] = val
        # Normalizza profile_score (e' nella range ~0.18-0.28) → spalmato 0..1
        # Mapping piu' aggressivo: (x - 0.18) / 0.10, clipped
        profile_score = np.clip((profile_score - 0.18) / 0.10, 0.0, 1.0)
        s = s + weights["w_profile"] * profile_score

    if bg.clip_grid is not None and obj.clip_emb is not None and "w_clip" in weights:
        # Cosine similarity (entrambi L2-normalized)
        gy, gx, _ = bg.clip_grid.shape
        clip_sim = bg.clip_grid @ obj.clip_emb  # (gy, gx)
        # INTERPOLAZIONE BILINEARE: ogni cella scoring riceve il valore interpolato
        # fra le 4 patch CLIP adiacenti. Smoothing spaziale invece di blocchi netti.
        scale_y = (gy - 1) / max(1, bg.cell_h - 1)
        scale_x = (gx - 1) / max(1, bg.cell_w - 1)
        fy = np.arange(bg.cell_h) * scale_y
        fx = np.arange(bg.cell_w) * scale_x
        y0 = np.clip(np.floor(fy).astype(np.int32), 0, gy - 1)
        y1 = np.clip(y0 + 1, 0, gy - 1)
        x0 = np.clip(np.floor(fx).astype(np.int32), 0, gx - 1)
        x1 = np.clip(x0 + 1, 0, gx - 1)
        wy = (fy - y0).astype(np.float32)[:, None]
        wx = (fx - x0).astype(np.float32)[None, :]
        # Bilinear interp
        c00 = clip_sim[y0[:, None], x0[None, :]]
        c01 = clip_sim[y0[:, None], x1[None, :]]
        c10 = clip_sim[y1[:, None], x0[None, :]]
        c11 = clip_sim[y1[:, None], x1[None, :]]
        clip_score = (c00 * (1 - wy) * (1 - wx)
                      + c01 * (1 - wy) * wx
                      + c10 * wy * (1 - wx)
                      + c11 * wy * wx)
        clip_score = (clip_score + 1.0) / 2.0  # cosine [-1,1] → [0,1]
        s = s + weights["w_clip"] * clip_score

    # ── SHAPE↔STRUCTURE MATCHING ─────────────────────────────────────────
    # Usa la forma reale dell'oggetto (PCA su alpha) per matchare:
    #   - compactness oggetto vs edge_density locale del BG
    #     (oggetto compatto/rotondo -> zone meno strutturate; oggetto frastagliato
    #      -> zone con texture/edge piu' busy che ne mascherano i dettagli)
    #   - asse principale oggetto vs structural_orient del BG
    #     (oggetto allungato -> zone con linee dominanti nella stessa direzione)
    if obj.shape is not None and "w_shape" in weights:
        compactness = float(obj.shape.get("compactness", 0.5))   # 1.0=rotondo, <0.3=allungato
        aspect_real = float(obj.shape.get("aspect_real", 1.0))   # 1.0=simmetrico, 0=lineare
        axis_angle  = float(obj.shape.get("axis_angle", 0.0))    # rad, -pi/2..pi/2

        # (a) Compactness matching: oggetti compatti preferiscono zone smooth/uniformi
        # (poche edge), oggetti elongated/frastagliati preferiscono zone busy.
        # complexity_local = mix di edge_density e (1 - smooth). Range ~0..1.
        complexity_local = bg.edge_density  # gia' 0..1
        # target_complexity = inversa della compactness (compactness 1 -> target 0)
        target_complexity = 1.0 - compactness
        # match score = 1 - |complexity_local - target_complexity|
        compact_match = 1.0 - np.abs(complexity_local - target_complexity)
        compact_match = np.clip(compact_match, 0.0, 1.0)

        # (b) Axis alignment (solo per oggetti allungati: aspect_real < 0.7)
        # Confronta axis_angle con structural_orient locale del BG (modulo pi).
        if (bg.structural_orient is not None and aspect_real < 0.7):
            so = bg.structural_orient  # (cell_h, cell_w), -pi/2..pi/2, NaN dove no linee
            # diff angolare nel modulo pi/2: ((a-b)+pi/2) mod pi - pi/2
            diff = ((so - axis_angle) + math.pi / 2) % math.pi - math.pi / 2
            align = 1.0 - np.abs(diff) / (math.pi / 2)
            # Dove structural_orient e' NaN (zone senza linee dominanti), align=0.5 neutro
            align = np.where(np.isnan(so), 0.5, align)
            # Mix alignment + compact match, peso alignment cresce con elongation.
            elong = 1.0 - aspect_real  # 0=simmetrico, 1=lineare
            shape_score = (1.0 - 0.5 * elong) * compact_match + 0.5 * elong * align
        else:
            shape_score = compact_match

        s = s + weights["w_shape"] * shape_score

    # ── SHAPE-MATCH via Hu moments vs contorni BG (trompe-l'oeil) ─────────
    # Cerca sullo sfondo le sagome visivamente compatibili con l'oggetto
    # (per forma, non per categoria) e splasha il loro punteggio sulle celle
    # che le contengono. Determinante per line_art e per oggetti "iconici".
    if (obj.shape is not None and obj.shape.get("hu") is not None
            and bg.contours and "w_shape_match" in weights
            and weights["w_shape_match"] > 0.0):
        sm_map = _shape_match_map_for_object(bg, obj.shape["hu"])
        if sm_map is not None:
            s = s + weights["w_shape_match"] * sm_map

    # ── PHYSICS PRIORS via support_bot / hang_top ─────────────────────────
    # Oggetti con base larga (support_bot alto: libro, vaso) gravitano verso
    # celle che hanno "qualcosa di solido" sotto (edge_density alta o classe
    # ADE20K floor/table). Oggetti con attacco superiore (hang_top alto:
    # lampada, tenda) gravitano verso celle con "qualcosa di solido" sopra
    # (ceiling/wall). Penalizza il piazzamento fluttuante per categoria fisica.
    if (obj.shape is not None and "w_physics" in weights
            and weights["w_physics"] > 0.0):
        support = float(obj.shape.get("support_bot", 0.0))
        hang = float(obj.shape.get("hang_top", 0.0))
        physics = np.zeros_like(s)

        if support > 0.40:
            # Edge density delle 2 celle sotto: alta = "c'e' qualcosa che regge"
            ab = np.zeros_like(s)
            for offset in (1, 2):
                shifted = np.roll(bg.edge_density, -offset, axis=0)
                shifted[-offset:] = 0
                ab = ab + shifted
            ab = ab * 0.5
            # Mappa [0..1] -> [-1..+1]: vuoto sotto penalizza, pieno premia
            physics = physics + support * (2.0 * ab - 1.0)
            # Bonus extra se classe semantica SOTTO e' "preferred" (pavimento/tavolo)
            if bg.semantic_score is not None:
                sem_below = np.roll(bg.semantic_score, -1, axis=0)
                sem_below[-1:] = 0
                physics = physics + 0.5 * support * sem_below

        if hang > 0.40:
            aa = np.zeros_like(s)
            for offset in (1, 2):
                shifted = np.roll(bg.edge_density, offset, axis=0)
                shifted[:offset] = 0
                aa = aa + shifted
            aa = aa * 0.5
            physics = physics + hang * (2.0 * aa - 1.0)
            if bg.semantic_score is not None:
                sem_above = np.roll(bg.semantic_score, 1, axis=0)
                sem_above[:1] = 0
                physics = physics + 0.5 * hang * sem_above

        s = s + weights["w_physics"] * physics

    return s


def _build_score_matrix(
    bg: BGAnalysis,
    obj: ObjAnalysis,
    weights: dict,
    occupied: np.ndarray,  # shape (cell_h, cell_w) float, decrementato dopo ogni piazzato
    base: Optional[np.ndarray] = None,
    forbidden_mask: Optional[np.ndarray] = None,
    color_gate: Optional[np.ndarray] = None,
) -> np.ndarray:
    """Matrice di score completa (cell_h, cell_w) per piazzare l'oggetto.

    = parte object-invariant (base) + termini per-tentativo: anti-cluster
    (w_cluster*occupied), jitter e veti duri. Se `base` e' fornita (cache per
    catalog_id nel loop di place_objects) la parte costosa non viene ricostruita;
    il risultato e' identico a base=None. `base` non viene mai mutata (l'addizione
    crea sempre un nuovo array).

    forbidden_mask: bool (cell_h, cell_w), celle vietate object-invariant
      (volti, zone dipinte a mano, classe person). Default None = nessun veto.
    color_gate: bool (cell_h, cell_w), celle vietate per QUESTO oggetto perche'
      il match cromatico e' sotto soglia (vedi _build_color_gate). Default None.
    Entrambi applicati per ULTIMI, dopo ogni termine additivo: nulla puo'
    risollevare una cella vetata.
    """
    s = base if base is not None else _build_base_score_matrix(bg, obj, weights)

    # Anti-cluster: stato di piazzamento corrente (occupied basso = zona gia' presa).
    s = s + weights["w_cluster"] * occupied

    # Jitter random per spezzare il determinismo (entropia di sampling). Consuma
    # esattamente 1 estrazione RNG per chiamata, come la versione monolitica
    # precedente: la sequenza random (e quindi le piazzate a parita' di seed) resta
    # invariata sia con base=None sia con base precalcolata.
    s = s + weights["jitter"] * np.random.random(s.shape)

    # HARD VETO semantico: le celle proibite (cielo/muro, semantic_score==-1) non
    # sono MAI valide, qualunque sia il match cromatico/clutter. Prima erano solo
    # una penalita' additiva (-w_semantic) che un buon color match poteva superare,
    # facendo "fluttuare" oggetti nel cielo. Applicato per ultimo cosi' nulla puo'
    # risollevarle. Attivo solo in ULTRA (semantic_score disponibile).
    if bg.semantic_score is not None:
        s = np.where(bg.semantic_score <= -0.99, SCORE_VETO, s)

    # HARD VETO zone vietate (volti/manuale/person) e gate colore per-oggetto.
    if forbidden_mask is not None:
        s = np.where(forbidden_mask, SCORE_VETO, s)
    if color_gate is not None:
        s = np.where(color_gate, SCORE_VETO, s)
    return s


def compute_debug_maps(bg: BGAnalysis, obj: Optional[ObjAnalysis], weights: dict,
                       forbidden_mask: Optional[np.ndarray],
                       difficulty: str) -> dict[str, np.ndarray]:
    """Mappe di debug (cell_h, cell_w) float 0..1 per overlay/QA. Pura, RNG-free.

      score      : base score normalizzata 0..1 per l'oggetto dato (celle vetate
                   = 0). Se obj e' None usa hideability_map (o zeri).
      forbidden  : forbidden_mask come float (1 = vietata).
      saliency   : bg.saliency.
      color_gate : gate colore per l'oggetto come float (1 = vetata); zeri se
                   gate disattivo o obj None.
    """
    shape = (bg.cell_h, bg.cell_w)
    out: dict[str, np.ndarray] = {}

    gate = None
    if obj is not None:
        gate = _build_color_gate(bg, obj, weights, difficulty)
        base = _build_base_score_matrix(bg, obj, weights)
        veto = np.zeros(shape, dtype=bool)
        if bg.semantic_score is not None:
            veto |= bg.semantic_score <= -0.99
        if forbidden_mask is not None:
            veto |= forbidden_mask.astype(bool)
        if gate is not None:
            veto |= gate
        valid = base[~veto]
        if valid.size > 0 and float(valid.max() - valid.min()) > 1e-6:
            norm = (base - float(valid.min())) / float(valid.max() - valid.min())
        else:
            norm = np.zeros(shape, dtype=np.float32)
        norm = np.clip(norm, 0.0, 1.0)
        norm[veto] = 0.0
        out["score"] = norm.astype(np.float32)
    elif bg.hideability_map is not None:
        out["score"] = bg.hideability_map.astype(np.float32)
    else:
        out["score"] = np.zeros(shape, dtype=np.float32)

    if forbidden_mask is not None:
        out["forbidden"] = forbidden_mask.astype(np.float32)
    else:
        out["forbidden"] = np.zeros(shape, dtype=np.float32)
    out["saliency"] = bg.saliency.astype(np.float32)
    out["color_gate"] = (gate.astype(np.float32) if gate is not None
                         else np.zeros(shape, dtype=np.float32))
    return out


def build_forbidden_mask(bg: BGAnalysis,
                         manual_cells: Optional[set[tuple[int, int]]] = None
                         ) -> Optional[np.ndarray]:
    """Maschera bool (cell_h, cell_w) delle celle SEMPRE vietate al piazzamento.

    Unione di:
      - bg.face_mask (volti rilevati, tutti i tier)
      - celle dipinte a mano dal designer (manual_cells, coords (cx, cy),
        bounds-checked)
      - classe semantica "person" (tier 3; ridondante col veto semantico ma
        tiene UNA maschera valida per tutti i tier e alimenta l'overlay debug)

    Ritorna None se non c'e' nulla da vietare (fast-path per il chiamante).
    Pura e deterministica.
    """
    mask = np.zeros((bg.cell_h, bg.cell_w), dtype=bool)
    any_veto = False
    if bg.face_mask is not None and bg.face_mask.shape == mask.shape:
        mask |= bg.face_mask.astype(bool)
        any_veto = any_veto or bool(bg.face_mask.any())
    if manual_cells:
        for (mcx, mcy) in manual_cells:
            if 0 <= mcy < bg.cell_h and 0 <= mcx < bg.cell_w:
                mask[mcy, mcx] = True
                any_veto = True
    if bg.semantic is not None:
        from editor.tools.scatter_models import ADE20K_PERSON_LIKE
        person = np.isin(bg.semantic, np.fromiter(ADE20K_PERSON_LIKE, dtype=np.int64))
        if person.any():
            mask |= person
            any_veto = True
    return mask if any_veto else None


def place_objects(
    bg: BGAnalysis,
    catalog_analyses: dict[str, ObjAnalysis],
    catalog_entries: dict[str, dict],
    *,
    count: int,
    difficulty: str = "medium",
    style: str = "real",
    tag_filter: Optional[str] = None,
    existing_bboxes: Optional[list[tuple[float, float, float, float]]] = None,
    seed: Optional[int] = None,
    ref_diag: float = 1469.0,  # diagonale REF 1280x720
    allowed_layers: Optional[list[str]] = None,
    edge_margin_px: int = 24,
    forbidden_mask: Optional[np.ndarray] = None,
) -> list[PlacedObject]:
    """Pipeline completa di sampling.

    Args:
      bg, catalog_analyses, catalog_entries, count, difficulty, tag_filter, existing_bboxes, seed: come prima
      ref_diag: diagonale della scena REF (per calcolare scale proporzionata).
      allowed_layers: lista dei layer su cui distribuire (es. ["objects_low", "objects_mid"]).
                      Default: tutti e 3 (low/mid/high).
      edge_margin_px: margine di sicurezza dai bordi BG (in px).
      forbidden_mask: bool (cell_h, cell_w), celle vietate object-invariant
                      (volti + zone dipinte + person). None = nessun veto extra.
    """
    if seed is not None:
        random.seed(seed)
        np.random.seed(seed)

    weights = _get_weights(difficulty, style)

    # Gate colore per-oggetto (RNG-free, dipende solo da bg/obj/weights/difficulty):
    # cacheato per catalog_id, condiviso fra viability pre-screen, main loop e swap.
    color_gate_cache: dict[str, Optional[np.ndarray]] = {}

    def _color_gate_for(cid_: str) -> Optional[np.ndarray]:
        if cid_ not in color_gate_cache:
            color_gate_cache[cid_] = _build_color_gate(
                bg, catalog_analyses[cid_], weights, difficulty)
        return color_gate_cache[cid_]

    if not allowed_layers:
        allowed_layers = ["objects_low", "objects_mid", "objects_high"]

    pool_ids = [
        cid for cid, an in catalog_analyses.items()
        if (cid in catalog_entries)
        and (tag_filter is None or tag_filter in catalog_entries[cid].get("tags", []))
    ]
    if not pool_ids:
        log.warning(f"[SCATTER] pool vuoto (style/tag '{tag_filter}')")
        return []

    # ── VETO SALIENCY (v3): le celle in cima alla mappa di attenzione sono
    # "in bella vista": vetate a runtime (non persistite), OR-ate nella
    # forbidden mask cosi' propagano a ricorsione multi-layer e swap. Guard
    # anti over-veto: se resterebbero troppo poche celle libere, si droppa la
    # SOLA componente saliency (mai i veti volti/manuale/person). Idempotente:
    # i sub-pass per layer ricalcolano la stessa unione.
    sal_frac = SALIENCY_VETO_TOP_FRAC.get(difficulty, 0.0)
    if sal_frac > 0.0:
        thr_sal = float(np.quantile(bg.saliency, 1.0 - sal_frac))
        sal_veto = bg.saliency >= thr_sal
        combined = sal_veto if forbidden_mask is None else (forbidden_mask | sal_veto)
        n_free = int((~combined).sum())
        if n_free >= int(MIN_ALLOWED_CELLS_FRAC * combined.size):
            forbidden_mask = combined
        else:
            log.info(f"[SCATTER] saliency veto droppato: lascerebbe solo "
                     f"{n_free}/{combined.size} celle libere")

    # ── VETO CIELO + "MEZZ'ARIA" (v3.1): a qualunque tier (il veto semantico
    # cielo esiste solo in ULTRA). Due componenti, stessa guardia anti
    # over-veto della saliency:
    #   1. CIELO: regione piatta CONNESSA al bordo superiore del BG
    #      (flood-fill 4-conn attraverso celle piatte). Becca anche gli
    #      oggetti "cromaticamente compatibili" col cielo (carta bianca su
    #      azzurro pallido) che il gate colore lascerebbe passare.
    #   2. MEZZ'ARIA: celle piatte nella meta' superiore con edge quasi nullo
    #      nelle 2 celle sottostanti (vuoto non connesso al top).
    if bg.texture_entropy is not None:
        flat_cells = ((bg.texture_entropy < FLAT_ENTROPY_MAX)
                      & (bg.edge_density < FLAT_EDGE_MAX))
        # 1) flood-fill dal bordo superiore attraverso le celle piatte
        sky = np.zeros_like(flat_cells)
        sky[0, :] = flat_cells[0, :]
        _changed = True
        while _changed:
            grown = sky.copy()
            grown[1:, :] |= sky[:-1, :] & flat_cells[1:, :]
            grown[:-1, :] |= sky[1:, :] & flat_cells[:-1, :]
            grown[:, 1:] |= sky[:, :-1] & flat_cells[:, 1:]
            grown[:, :-1] |= sky[:, 1:] & flat_cells[:, :-1]
            _changed = bool((grown != sky).any())
            sky = grown
        # Dilata di 1 cella: le celle di CONFINE del cielo (contorno nuvole,
        # cima della silhouette alberi) hanno edge > 0 e fermano il flood, ma
        # un oggetto li' e' visivamente "mezzo nel cielo".
        if sky.any():
            dil = sky.copy()
            dil[1:, :] |= sky[:-1, :]
            dil[:-1, :] |= sky[1:, :]
            dil[:, 1:] |= sky[:, :-1]
            dil[:, :-1] |= sky[:, 1:]
            sky = dil
        # 2) mezz'aria: piatto in alto senza appoggio sotto
        below = np.zeros_like(bg.edge_density)
        for _off in (1, 2):
            _sh = np.roll(bg.edge_density, -_off, axis=0)
            _sh[-_off:] = 0
            below += _sh
        below *= 0.5
        floating = flat_cells & (below < FLOATING_EDGE_BELOW_MAX)
        floating[bg.cell_h // 2:, :] = False  # solo meta' superiore
        air_veto = sky | floating
        if air_veto.any():
            combined = air_veto if forbidden_mask is None else (forbidden_mask | air_veto)
            n_free = int((~combined).sum())
            if n_free >= int(MIN_ALLOWED_CELLS_FRAC * combined.size):
                forbidden_mask = combined
            else:
                log.info("[SCATTER] veto cielo/mezz'aria droppato (troppe celle vietate)")

    n_layers = len(allowed_layers)

    # ── VIABILITY GATE: pre-screening del pool ────────────────────────────
    # Per ogni candidato, calcola il massimo score raggiungibile sul BG
    # in condizioni ideali (spazio libero, no jitter). Se un oggetto e' troppo
    # sotto il top del pool, scartiamolo: non si nascondera' bene comunque,
    # e finirebbe a sporcare il piazzamento. Threshold relativo al top per
    # adattarsi a BG difficili (se tutti scorano basso, non svuotare il pool).
    if n_layers <= 1 or count < n_layers:
        # eseguiamo il gate una sola volta (non nella ricorsione per-layer)
        _occ_full = np.ones((bg.cell_h, bg.cell_w), dtype=np.float32)
        _w_no_jitter = dict(weights); _w_no_jitter["jitter"] = 0.0
        viability = {}
        for cid in pool_ids:
            try:
                sc = _build_score_matrix(bg, catalog_analyses[cid], _w_no_jitter, _occ_full,
                                         forbidden_mask=forbidden_mask,
                                         color_gate=_color_gate_for(cid))
                viability[cid] = float(sc.max())
            except Exception as e:
                log.debug(f"[SCATTER] viability fail for {cid}: {e}")
                viability[cid] = -1e9
        if viability:
            top_v = max(viability.values())
            if top_v > 0.0:
                gate = top_v * 0.10  # 10% del top: scarto solo i visibilmente peggiori
                kept = [cid for cid in pool_ids if viability[cid] >= gate]
                excluded = [cid for cid in pool_ids if viability[cid] < gate]
                if excluded:
                    log.info(f"[SCATTER] viability gate: {len(excluded)}/{len(pool_ids)} "
                             f"esclusi (top={top_v:.2f}, gate={gate:.2f})")
                    for cid in excluded[:5]:
                        log.debug(f"[SCATTER]   skip '{cid}' viability={viability[cid]:.2f}")
                if kept:
                    pool_ids = kept

        # ── POOL PRUNING COLORE (v3.1) ────────────────────────────────────
        # Un oggetto il cui gate colore fallisce anche al floor (None con
        # w_color > 0) non ha NESSUNA zona compatibile su questo BG: prima il
        # gate si disattivava e l'oggetto finiva ovunque (es. giallo nel
        # cielo). Ora viene tolto dal pool, purche' ne restino abbastanza.
        if weights.get("w_color", 0.0) > 0.0 and len(pool_ids) > POOL_MIN_AFTER_COLOR_PRUNE:
            no_match = [cid for cid in pool_ids if _color_gate_for(cid) is None]
            if no_match and len(pool_ids) - len(no_match) >= POOL_MIN_AFTER_COLOR_PRUNE:
                pool_ids = [cid for cid in pool_ids if cid not in set(no_match)]
                log.info(f"[SCATTER] color prune: esclusi {len(no_match)} oggetti "
                         f"senza zone compatibili ({', '.join(no_match[:5])}...)")

    # ── SPLIT PER LAYER ────────────────────────────────────────────────
    # Se ci sono piu' layer attivi, dividi count uniformemente e fai un pass
    # separato per ogni layer (occupied map indipendente per ciascuno).
    # Gli oggetti di layer diversi possono essere visualmente vicini perche'
    # in-game sono su Z diversi (rimescolati separatamente).
    if n_layers > 1 and count >= n_layers:
        counts_per_layer = [count // n_layers] * n_layers
        remainder = count - sum(counts_per_layer)
        for i in range(remainder):
            counts_per_layer[i] += 1
        log.info(f"[SCATTER] split per layer: {count} totali = "
                 + " + ".join(f"{c} {l}" for c, l in zip(counts_per_layer, allowed_layers)))
        # Shuffle ordine layer per ogni run (varianza tra runs)
        layers_shuffled = list(zip(allowed_layers, counts_per_layer))
        random.shuffle(layers_shuffled)
        all_placed = []
        # CROSS-LAYER SEPARATION (v3.1): SEMPRE attiva. Prima veniva spenta
        # sopra 50 oggetti/layer e tre passate indipendenti si accatastavano
        # sugli stessi hotspot (pile di oggetti sovrapposti). Ad alta densita'
        # le bbox accumulate vengono RISTRETTE (CROSS_LAYER_SHRINK_FRAC per
        # lato): overlap parziale tollerato, stacking totale no.
        count_per_layer = counts_per_layer[0] if counts_per_layer else 0
        shrink_cross = count_per_layer > 50
        cross_layer_bboxes = list(existing_bboxes or [])
        log.info(f"[SCATTER] cross-layer separation: ON"
                 f"{' (bbox ristrette, density alta)' if shrink_cross else ''}")

        def _shrunk(bb: tuple[float, float, float, float]
                    ) -> tuple[float, float, float, float]:
            if not shrink_cross:
                return bb
            x0, y0, x1, y1 = bb
            dx = (x1 - x0) * CROSS_LAYER_SHRINK_FRAC
            dy = (y1 - y0) * CROSS_LAYER_SHRINK_FRAC
            return (x0 + dx, y0 + dy, x1 - dx, y1 - dy)

        for lid, lcount in layers_shuffled:
            if lcount <= 0:
                continue
            # Bboxes da passare: existing globali + bbox dei layer gia' piazzati
            sub_existing = list(cross_layer_bboxes)
            layer_placed = place_objects(
                bg, catalog_analyses, catalog_entries,
                count=lcount, difficulty=difficulty,
                style=style,
                tag_filter=tag_filter,
                existing_bboxes=sub_existing,
                seed=None,
                ref_diag=ref_diag,
                allowed_layers=[lid],
                edge_margin_px=edge_margin_px,
                forbidden_mask=forbidden_mask,
            )
            all_placed.extend(layer_placed)
            # Accumula bbox di questo layer per i sub-pass successivi
            # (ristrette ad alta densita': vedi _shrunk)
            for p in layer_placed:
                if p.detection_type == "circle":
                    r = p.radius * p.scale
                    cross_layer_bboxes.append(_shrunk((p.x - r, p.y - r,
                                                       p.x + r, p.y + r)))
                else:
                    w = p.width * p.scale
                    h = p.height * p.scale
                    cross_layer_bboxes.append(_shrunk((p.x, p.y,
                                                       p.x + w, p.y + h)))
        # Swap optimization globale (cross-layer) per migliorare match catalog↔posizione.
        # Gate-aware: uno swap non deve spostare un oggetto su una cella vetata per lui.
        if len(all_placed) >= 2:
            for cid_swap in {p.catalog_id for p in all_placed}:
                if cid_swap in catalog_analyses:
                    _color_gate_for(cid_swap)
            all_placed = _swap_optimize(all_placed, bg, catalog_analyses, weights, max_iters=2,
                                        color_gates=color_gate_cache,
                                        forbidden_mask=forbidden_mask)
        log.info(f"[SCATTER] TOTALE multi-layer: {len(all_placed)}/{count}")
        return all_placed

    cell_px = bg.cell_px
    # Scala proporzionata alla REF (1280x720). default_radius/width sono "in REF px".
    bg_scale = bg.bg_w / 1280.0

    # ── STRATIFICAZIONE: dividi BG in macro-zone per garantire copertura ─────
    # Crea una griglia 4x3 di zone macro. Per N oggetti, distribuisce idealmente
    # ~N/12 per zona, sceglie poi le celle migliori all'interno della zona.
    ZONE_COLS, ZONE_ROWS = 4, 3
    total_zones = ZONE_COLS * ZONE_ROWS
    # Per ogni oggetto, sceglie la zona round-robin con shuffle iniziale
    zone_order = list(range(total_zones)) * (count // total_zones + 2)
    random.shuffle(zone_order)

    # ── Layer round-robin tra quelli scelti ──────────────────────────────────
    layer_rot = list(allowed_layers) * (count // len(allowed_layers) + 2)
    random.shuffle(layer_rot)

    placed: list[PlacedObject] = []
    occupied = np.ones((bg.cell_h, bg.cell_w), dtype=np.float32)
    if existing_bboxes:
        for (x_min, y_min, x_max, y_max) in existing_bboxes:
            _mark_occupied(occupied, bg, x_min, y_min, x_max, y_max, value=0.05, radius_factor=1.5)

    # ── DENSITY-ADAPTIVE PARAMS ────────────────────────────────────────
    # 6 livelli di densita'. semantic_relax = riduce peso semantic+clip per
    # permettere placement anche su zone "meno ideali" (necessario in density alta).
    if count <= 20:
        anti_cluster_strength = 0.85
        overlap_margin_factor = 0.20
        gauss_sigma_scale = 0.9
        semantic_relax = 1.0   # full semantic weight
        max_total_attempts = max(800, count * 50)
    elif count <= 50:
        anti_cluster_strength = 0.60
        overlap_margin_factor = 0.28
        gauss_sigma_scale = 0.75
        semantic_relax = 0.9
        max_total_attempts = max(2500, count * 60)
    elif count <= 100:
        anti_cluster_strength = 0.35
        overlap_margin_factor = 0.32   # v3.1: era 0.40, troppa compenetrazione
        gauss_sigma_scale = 0.50
        semantic_relax = 0.5
        max_total_attempts = max(8000, count * 100)
    elif count <= 200:
        anti_cluster_strength = 0.20
        overlap_margin_factor = 0.38   # v3.1: era 0.50
        gauss_sigma_scale = 0.40
        semantic_relax = 0.25
        max_total_attempts = max(15000, count * 120)
    else:
        # Densita' estrema (>200): semantic e CLIP quasi spenti, riempi ovunque
        anti_cluster_strength = 0.10
        overlap_margin_factor = 0.42   # v3.1: era 0.60 (pile di oggetti)
        gauss_sigma_scale = 0.30
        semantic_relax = 0.10
        max_total_attempts = min(50000, count * 150)

    # Applica relax ai weights (riduce w_semantic, w_clip senza modificare globalmente)
    weights = dict(weights)  # copia per non modificare il preset globale
    if "w_semantic" in weights:
        weights["w_semantic"] *= semantic_relax
    if "w_clip" in weights:
        weights["w_clip"] *= semantic_relax

    log.info(f"[SCATTER] density mode: count={count}, strength={anti_cluster_strength}, "
             f"overlap={overlap_margin_factor:.0%}, sigma={gauss_sigma_scale}, "
             f"sem_relax={semantic_relax}, max_attempts={max_total_attempts}")
    # Cache della parte object-invariant della score matrix, per catalog_id.
    # Entro un singolo place_objects i weights sono costanti: la base di un dato id
    # non cambia tra i tentativi, quindi la calcoliamo una volta sola invece di
    # ricostruirla a ogni tentativo (fino a max_total_attempts). E' il maggior
    # risparmio del piazzamento perche' la base contiene i termini costosi
    # (color similarity, profile, clip, shape-match).
    base_score_cache: dict[str, np.ndarray] = {}
    # Colori dominanti RGB per la verifica Delta-E post-tint (per cid).
    dominant_rgb_cache: dict[str, list[tuple[int, int, int]]] = {}
    total_attempts = 0
    reject_reasons = {"score_neg": 0, "overlap": 0, "too_big": 0,
                      "color_deltaE": 0, "vis_band": 0}

    # HARD MASK occupancy: soglia sotto la quale una cella e' considerata gia'
    # presa. Dipende solo da count: loop-invariante (v3.1: spostata fuori dal
    # loop, serve anche alla scelta dell'oggetto per zona).
    if count <= 20:
        occ_threshold = 0.7
    elif count <= 50:
        occ_threshold = 0.45
    elif count <= 100:
        occ_threshold = 0.30   # v3.1: era 0.25
    elif count <= 200:
        occ_threshold = 0.20   # v3.1: era 0.12 (celle gia' prese rieleggibili)
    else:
        occ_threshold = 0.12   # v3.1: era 0.05

    def _base_for(cid_: str) -> np.ndarray:
        b = base_score_cache.get(cid_)
        if b is None:
            b = _build_base_score_matrix(bg, catalog_analyses[cid_], weights)
            base_score_cache[cid_] = b
        return b

    while len(placed) < count and total_attempts < max_total_attempts:
        total_attempts += 1

        # ── ZONA corrente PRIMA della scelta oggetto (v3.1) ───────────────
        zone_idx = zone_order[len(placed) % len(zone_order)]
        zx, zy = zone_idx % ZONE_COLS, zone_idx // ZONE_COLS
        z_x0 = int(zx * bg.cell_w / ZONE_COLS)
        z_x1 = int((zx + 1) * bg.cell_w / ZONE_COLS)
        z_y0 = int(zy * bg.cell_h / ZONE_ROWS)
        z_y1 = int((zy + 1) * bg.cell_h / ZONE_ROWS)
        z_sl = (slice(z_y0, z_y1), slice(z_x0, z_x1))

        # ── SCELTA OGGETTO PER ZONA (v3.1): K candidati, vince chi matcha ──
        # meglio la macro-zona corrente (base score cacheata + gate + celle
        # libere). Prima l'oggetto era pescato a caso e POI si cercava una
        # cella per lui: colore/forma/dimensione non guidavano la SCELTA.
        cand_ids = [random.choice(pool_ids)
                    for _ in range(OBJ_CANDIDATES_PER_ATTEMPT)]
        cid = cand_ids[0]
        uniq = list(dict.fromkeys(cand_ids))
        if len(uniq) > 1:
            free_z = occupied[z_sl] >= occ_threshold
            if forbidden_mask is not None:
                free_z = free_z & ~forbidden_mask[z_sl]
            best_val = -1e18
            for c in uniq:
                m = free_z
                g = _color_gate_for(c)
                if g is not None:
                    m = m & ~g[z_sl]
                if not m.any():
                    continue
                val = float(_base_for(c)[z_sl][m].max())
                if val > best_val:
                    best_val = val
                    cid = c
        obj_an = catalog_analyses[cid]
        entry = catalog_entries[cid]

        # ── DIMENSIONE: USA I VALORI DEL CATALOGO + ASPECT RATIO DEL PNG ──
        dt = entry.get("default_detection", "circle")
        png_aspect = obj_an.aspect if obj_an.aspect > 0 else 1.0
        if dt == "circle":
            ref_radius = entry.get("default_radius", 30)
            target_area = (ref_radius * 2) ** 2
            ref_w = math.sqrt(target_area * png_aspect)
            ref_h = math.sqrt(target_area / png_aspect)
        else:
            ref_w = entry.get("default_width", 60)
            ref_h = entry.get("default_height", 60)
            cat_aspect = ref_w / max(1, ref_h)
            if abs(cat_aspect - png_aspect) > 0.4 and png_aspect > 0:
                target_area = ref_w * ref_h
                ref_w = math.sqrt(target_area * png_aspect)
                ref_h = math.sqrt(target_area / png_aspect)
            ref_radius = max(ref_w, ref_h) / 2
        # Scale finale = BG scale + piccolo jitter percettivo
        # Density-aware scale: per count alto riduci oggetti per fitting fisico
        # (300 oggetti 240x240 non ci stanno in BG 5K senza overlap massivo)
        if count <= 50:
            density_scale = 1.0
        elif count <= 100:
            density_scale = 0.85
        elif count <= 200:
            density_scale = 0.65
        else:
            density_scale = 0.50
        scale = bg_scale * density_scale * random.uniform(0.92, 1.08)
        # eff size in pixel del BG
        eff_w = ref_w * scale
        eff_h = ref_h * scale
        eff_size = max(eff_w, eff_h)
        eff_radius = ref_radius * scale

        # ── SCORE MATRIX + zona stratificata ──────────────────────────────
        # Base object-invariant da cache (calcolata una volta per id), poi i
        # termini per-tentativo (occupied/jitter/veto) aggiunti dal wrapper.
        base_score = _base_for(cid)
        score = _build_score_matrix(bg, obj_an, weights, occupied, base=base_score,
                                    forbidden_mask=forbidden_mask,
                                    color_gate=_color_gate_for(cid))

        # Applica mask occupancy: celle troppo occupate = "score -inf"
        # (occ_threshold calcolata pre-loop, v3.1)
        score = np.where(occupied < occ_threshold, SCORE_VETO, score)

        # Boost per la zona stratificata corrente (bound gia' calcolati sopra)
        zone_score = np.zeros_like(score)
        zone_score[z_y0:z_y1, z_x0:z_x1] = 0.5
        score = score + zone_score

        # ── ANTI-FLOATING: bonus se sotto la cella c'è "qualcosa" ────────
        # Per una cella (cy, cx), guardo l'edge density delle 2 celle sotto.
        # Se sotto è "vuoto" (low edge), penalizzo.
        anchor_below = np.zeros_like(score)
        for offset in (1, 2):
            shifted = np.roll(bg.edge_density, -offset, axis=0)
            shifted[-offset:] = 0  # zone fuori BG
            anchor_below += shifted
        anchor_below /= 2.0
        # Anti-floating weight (forte, sempre attivo)
        anchor_w = 0.6
        score = score + anchor_w * anchor_below

        # ── ESCLUDI celle troppo vicine ai bordi BG ─────────────────────
        # Margine in celle = ceil(eff_size/2 / cell_px) + safety
        margin_cells = int(math.ceil((eff_size / 2 + edge_margin_px) / cell_px))
        if margin_cells > 0:
            score[:margin_cells, :] = SCORE_VETO
            score[-margin_cells:, :] = SCORE_VETO
            score[:, :margin_cells] = SCORE_VETO
            score[:, -margin_cells:] = SCORE_VETO

        # Top-K adaptive in base a size_class E al numero piazzati.
        # Mano a mano che la mappa si satura (placed alto), allargo K per accettare
        # celle "meno buone" e non bloccarmi su top zone esauste.
        progress = len(placed) / max(1, count)
        if obj_an.size_class == "small":
            k_top_base = 6
        elif obj_an.size_class == "big":
            k_top_base = 16
        else:
            k_top_base = 12
        # Espandi K progressivamente quando la map si satura (50%, 75%, 90%)
        if progress > 0.5:
            k_top_base = int(k_top_base * (1 + progress))

        flat = score.flatten()
        if flat.max() < SCORE_VETO_THRESHOLD:
            reject_reasons["score_neg"] += 1
            continue
        k_top = min(k_top_base, len(flat))
        top_idxs = np.argpartition(flat, -k_top)[-k_top:]
        top_scores = flat[top_idxs]
        s_norm = (top_scores - top_scores.max()) * 1.5  # T leggermente piu' alta (meno greedy)
        probs = np.exp(s_norm)
        probs = probs / probs.sum()
        cell_idx = int(np.random.choice(top_idxs, p=probs))
        cy, cx = divmod(cell_idx, bg.cell_w)

        # LOCAL REFINEMENT: cerca il miglior punto in 3x3 celle attorno
        # (sub-cell precision tramite multi-sample + best-pick)
        best_local_x = (cx + 0.5) * cell_px
        best_local_y = (cy + 0.5) * cell_px
        best_local_score = float(score[cy, cx])
        for _ in range(6):  # 6 sample random nel quadrante 3x3 centrato
            sx_off = random.uniform(-cell_px, cell_px)
            sy_off = random.uniform(-cell_px, cell_px)
            try_x = (cx + 0.5) * cell_px + sx_off
            try_y = (cy + 0.5) * cell_px + sy_off
            # Mappa il punto in cella della griglia
            tcy = int(try_y / cell_px)
            tcx = int(try_x / cell_px)
            if 0 <= tcy < bg.cell_h and 0 <= tcx < bg.cell_w:
                ts = float(score[tcy, tcx])
                if ts > best_local_score:
                    best_local_score = ts
                    best_local_x = try_x
                    best_local_y = try_y
        center_x = best_local_x + random.uniform(-cell_px / 6, cell_px / 6)
        center_y = best_local_y + random.uniform(-cell_px / 6, cell_px / 6)
        # Refresh cy,cx for downstream usage (orientation, semantic, etc)
        cy = int(min(bg.cell_h - 1, max(0, center_y / cell_px)))
        cx = int(min(bg.cell_w - 1, max(0, center_x / cell_px)))

        # ── SCALA PER PROFONDITA' (v3, tier>=1): lontano = piu' piccolo ────
        # depth_grid e' NEARNESS 0..1 (1 = vicino alla camera). Applicata PRIMA
        # del region-fit cosi' il prior fisico (clamp per size_class) include
        # gia' la prospettiva. Deterministica (no RNG).
        if bg.depth_grid is not None:
            nearness = float(bg.depth_grid[cy, cx])
            scale *= DEPTH_SCALE_MIN + (DEPTH_SCALE_MAX - DEPTH_SCALE_MIN) * nearness
            eff_w = ref_w * scale
            eff_h = ref_h * scale
            eff_size = max(eff_w, eff_h)
            eff_radius = ref_radius * scale

        # ── REGION-FIT: dimensiona/orienta l'oggetto sulla porzione di sfondo ─
        # (Fase 1: scala dalla regione cromatica omogenea sotto la cella;
        #  Fase 2: orientamento + lieve adattamento aspect; Fase 5: prior fisici.)
        # Sostituisce il vecchio, debole, blend da solo contour: ora quasi sempre
        # disponibile e con influenza forte pesata sulla confidence della regione.
        contour_rot_deg = None
        default_scale = scale  # scala "fisica" di partenza (prior per-categoria)
        region_fitted = False
        if dt != "circle":
            win_px = min(eff_size * 3.0, 0.22 * min(bg.bg_w, bg.bg_h))
            win_px = max(48.0, win_px)
            region = _region_extent_for_cell(bg, center_x, center_y, win_px)
            if region is not None and region[3] >= 0.30:
                r_w, r_h, r_angle, r_conf = region
                r_major = max(r_w, r_h); r_minor = max(1.0, min(r_w, r_h))
                # target_fill per difficolta': hard nasconde meglio (oggetto piu'
                # piccolo nella regione), easy lascia oggetti piu' grandi/leggibili.
                tf = {"easy": 0.85, "medium": 0.70, "hard": 0.55}.get(difficulty, 0.70)
                obj_long_ref = max(ref_w, ref_h)
                obj_short_ref = max(1.0, min(ref_w, ref_h))
                # Lato lungo obj ~ tf * lato lungo regione, ma il lato corto non
                # deve sforare il lato corto della regione.
                target_scale_long = (tf * r_major) / obj_long_ref
                target_scale_short = r_minor / obj_short_ref
                target_scale = min(target_scale_long, target_scale_short)
                # Fase 5: prior fisici -> clamp relativo alla scala di default per
                # categoria (impedisce taglie irrealistiche, es. stampante-portiera).
                if obj_an.size_class == "small":
                    rel_min, rel_max = 0.5, 3.0
                elif obj_an.size_class == "big":
                    rel_min, rel_max = 0.6, 1.8
                else:
                    rel_min, rel_max = 0.5, 2.2
                target_scale = max(default_scale * rel_min,
                                   min(default_scale * rel_max, target_scale))
                # Blend forte pesato sulla confidence della regione.
                blend = r_conf * 0.85
                new_scale = default_scale * (1.0 - blend) + target_scale * blend
                if new_scale > 1e-4 and abs(new_scale - scale) > 1e-3:
                    scale = new_scale
                    eff_w = ref_w * scale
                    eff_h = ref_h * scale
                    eff_size = max(eff_w, eff_h)
                    eff_radius = ref_radius * scale
                    region_fitted = True
                # Fase 2: orienta verso il lato lungo della regione (se allungata)
                # e adatta lievemente l'aspect (max +/-15%) alla forma della regione.
                if r_major / r_minor > 1.25 and r_conf >= 0.45:
                    obj_axis_deg = (math.degrees(float(obj_an.shape.get("axis_angle", 0.0)))
                                    if obj_an.shape else 0.0)
                    contour_rot_deg = (r_angle - obj_axis_deg + random.uniform(-4, 4)) % 360
                    region_aspect = r_major / r_minor
                    obj_aspect_now = max(eff_w, eff_h) / max(1.0, min(eff_w, eff_h))
                    if region_aspect > obj_aspect_now:
                        f = min(1.15, region_aspect / obj_aspect_now)
                        # Modifica ref_w/ref_h (NON solo eff_*): sono i valori salvati
                        # nella scena, lo stretch deve persistere oltre i check locali.
                        if ref_w >= ref_h:
                            ref_w *= f
                        else:
                            ref_h *= f
                        eff_w = ref_w * scale
                        eff_h = ref_h * scale
                        eff_size = max(eff_w, eff_h)
                if region_fitted:
                    log.debug(f"[SCATTER] region-fit {cid}: conf={r_conf:.2f} "
                              f"region=({r_w:.0f}x{r_h:.0f}) scale={scale:.3f}")

        # ── TROMPE-L'OEIL (fallback orientamento): se la regione non ha orientato
        # e c'e' un contorno BG con forma (Hu) simile, usa il suo angolo. La scala
        # e' gia' gestita dal region-fit, qui si tocca solo la rotazione.
        if (contour_rot_deg is None
                and obj_an.shape is not None
                and obj_an.shape.get("hu") is not None
                and bg.contours
                and weights.get("w_shape_match", 0.0) > 0.0):
            aspect_real = obj_an.shape.get("aspect_real")
            matched_c, c_score = _best_contour_for_cell(
                bg, obj_an.shape["hu"], center_x, center_y,
                obj_aspect_real=aspect_real,
            )
            if matched_c is not None and c_score > 0.50:
                obj_axis_deg = math.degrees(float(obj_an.shape.get("axis_angle", 0.0)))
                contour_rot_deg = (matched_c["angle_deg"] - obj_axis_deg
                                   + random.uniform(-4, 4)) % 360
                # Se il region-fit NON ha agito, consenti un blend di scala dal
                # contour (come prima) per non perdere quel comportamento utile.
                if not region_fitted:
                    obj_long_ref = max(ref_w, ref_h)
                    c_long = max(matched_c["w"], matched_c["h"])
                    if obj_long_ref > 0 and c_long > 0:
                        target_scale = c_long / obj_long_ref
                        blend = min(1.0, (c_score - 0.50) / 0.50) * 0.5
                        new_scale = scale * (1.0 - blend) + target_scale * blend
                        new_scale = max(scale * 0.60, min(scale * 1.50, new_scale))
                        if abs(new_scale - scale) > 1e-3:
                            scale = new_scale
                            eff_w = ref_w * scale
                            eff_h = ref_h * scale
                            eff_size = max(eff_w, eff_h)
                            eff_radius = ref_radius * scale

        # ── ROTAZIONE prima del clipping (il bbox ruotato e' piu' grande!) ──
        # Priorita': CONTOUR-MATCH (se forte) -> SHAPE-AWARE SNAP
        #         -> normal_orient (depth-based) -> grad_orient (edge-based)
        rot_deg = contour_rot_deg
        # SHAPE-AWARE: se oggetto allungato (aspect_real basso) E BG ha una linea
        # strutturale locale, allinea l'asse principale dell'oggetto con quella linea.
        if (obj_an.shape is not None
                and bg.structural_orient is not None
                and float(obj_an.shape.get("aspect_real", 1.0)) < 0.65):
            so_local = float(bg.structural_orient[cy, cx])
            if not math.isnan(so_local):
                obj_axis = float(obj_an.shape.get("axis_angle", 0.0))  # rad
                # Rotazione richiesta per allineare obj_axis a so_local (entrambi -pi/2..pi/2)
                delta_rad = so_local - obj_axis
                # Normalize to [-pi/2, pi/2]
                delta_rad = ((delta_rad + math.pi / 2) % math.pi) - math.pi / 2
                rot_deg = (math.degrees(delta_rad) + random.uniform(-6, 6)) % 360

        if rot_deg is None:
            if bg.normal_orient is not None and abs(float(bg.normal_orient[cy, cx])) > 0.05:
                orient_local = float(bg.normal_orient[cy, cx])
                rot_deg = (math.degrees(orient_local) + 90 + random.uniform(-10, 10)) % 360
            else:
                grad_local = float(bg.grad_orient[cy, cx])
                if abs(grad_local) > 0.05:
                    rot_deg = (math.degrees(grad_local) + random.uniform(-15, 15)) % 360
                else:
                    rot_deg = random.uniform(0, 360) if random.random() < 0.3 else 0
                if abs(grad_local) < 0.05 and random.random() < 0.5:
                    rot_deg = random.choice([0, 90, 180, 270])

        # Flip H casuale 30%, flip V mai
        flip_x = random.random() < 0.30
        flip_y = False

        # ── BBOX ROTATION-AWARE: il bounding box del rect ruotato e' piu' grande ──
        # Per CIRCLE: la rotazione non cambia il bbox (cerchio).
        # Per RECT: |w·cos(θ)| + |h·sin(θ)|, |w·sin(θ)| + |h·cos(θ)|.
        rot_rad = math.radians(rot_deg)
        cos_r = abs(math.cos(rot_rad))
        sin_r = abs(math.sin(rot_rad))

        if dt == "circle":
            # Clamp del centro per non far uscire il cerchio
            center_x = max(eff_radius + edge_margin_px,
                           min(bg.bg_w - eff_radius - edge_margin_px, center_x))
            center_y = max(eff_radius + edge_margin_px,
                           min(bg.bg_h - eff_radius - edge_margin_px, center_y))
            x_min = center_x - eff_radius
            y_min = center_y - eff_radius
            x_max = center_x + eff_radius
            y_max = center_y + eff_radius
            obj_x, obj_y = center_x, center_y
            # Per overlap check usa bbox circle (no rotation effect)
        else:
            # Rect: bbox rotato
            rotated_w = eff_w * cos_r + eff_h * sin_r
            rotated_h = eff_w * sin_r + eff_h * cos_r
            # center clamp (consideriamo l'oggetto centrato in center_x, center_y)
            half_rw = rotated_w / 2
            half_rh = rotated_h / 2
            center_x = max(half_rw + edge_margin_px,
                           min(bg.bg_w - half_rw - edge_margin_px, center_x))
            center_y = max(half_rh + edge_margin_px,
                           min(bg.bg_h - half_rh - edge_margin_px, center_y))
            # x_min/y_min per rect e' top-left dell'oggetto NON ruotato (e' come lo salviamo nella scena)
            x_min = center_x - eff_w / 2
            y_min = center_y - eff_h / 2
            x_max = center_x + eff_w / 2
            y_max = center_y + eff_h / 2
            obj_x, obj_y = x_min, y_min  # rect stores top-left
            # Bbox per overlap check: usa quello rotato (piu' largo)
            x_min_check = center_x - half_rw
            y_min_check = center_y - half_rh
            x_max_check = center_x + half_rw
            y_max_check = center_y + half_rh

        # Sanita': se l'oggetto (anche ruotato) e' piu' grande del BG, skip
        bbox_w_check = (eff_radius * 2) if dt == "circle" else (eff_w * cos_r + eff_h * sin_r)
        bbox_h_check = (eff_radius * 2) if dt == "circle" else (eff_w * sin_r + eff_h * cos_r)
        if bbox_w_check >= bg.bg_w - 2 * edge_margin_px or bbox_h_check >= bg.bg_h - 2 * edge_margin_px:
            reject_reasons["too_big"] += 1
            continue

        # Overlap check (usa bbox rotato per rect, margine adaptive per density)
        if dt == "circle":
            if _overlaps_any(x_min, y_min, x_max, y_max, placed, existing_bboxes,
                             eff_size, overlap_margin_factor=overlap_margin_factor):
                reject_reasons["overlap"] += 1
                continue
        else:
            if _overlaps_any(x_min_check, y_min_check, x_max_check, y_max_check,
                             placed, existing_bboxes, eff_size,
                             overlap_margin_factor=overlap_margin_factor):
                reject_reasons["overlap"] += 1
                continue

        # Alpha: 255 di default, ridotto per vetro/cristallo
        alpha = 255
        tags = entry.get("tags", [])
        if "vetro" in tags or "cristallo" in tags or "bottiglia" in tags:
            alpha = random.randint(180, 215)

        # Tint di CAMOUFLAGE (v3, Lab): avvicina il colore dell'oggetto a quello
        # REALE dello sfondo coperto dal footprint. Mix per DIFFICOLTA' (hard
        # fonde di piu'), clamp su L e guard sulle zone grigie dentro
        # _lab_harmonize_tint. Applicato ANCHE agli oggetti translucidi (vetro/
        # cristallo): si mimetizzano meglio adottando il colore del fondo.
        # Disabilitato per line_art: lo stile e' B/N, il colore del BG e' rumore.
        color_filter = (255, 255, 255)
        if style != "line_art":
            tint = _lab_harmonize_tint(bg, x_min, y_min, x_max, y_max, difficulty)
            if tint is not None:
                color_filter = tint
            elif obj_an.palette_ext or obj_an.palette:
                # Fallback HSV storico (lab_full/cv2 assenti): mix dal delta hue.
                loc = _sample_footprint_hsv(bg, x_min, y_min, x_max, y_max)
                if loc is not None:
                    bg_h, bg_s, bg_v = loc
                    if obj_an.palette_ext:
                        _dom = obj_an.palette_ext[0]
                        obj_h, obj_s, obj_v = _dom["h"], _dom["s"], _dom["v"]
                    else:
                        obj_h, obj_s, obj_v = obj_an.palette[0]
                    delta = _hue_distance(obj_h, bg_h)  # 0..0.5
                    mix = min(0.35, 0.12 + delta * 0.9)
                    # Su zone quasi grigie l'hue e' rumore: no colore falso.
                    tint_s = bg_s if bg_s > 0.12 else min(obj_s * 0.4, bg_s)
                    color_filter = _hsv_to_tint_rgb(bg_h, min(1.0, tint_s),
                                                    max(0.30, bg_v), mix=mix)

        # ── VERIFICA FOOTPRINT in Lab (Delta-E 76) POST-TINT (v3.2) ────────
        # La cella 48px e' una media: puo' dire "marrone" su un patch a
        # scacchi. Qui controlliamo i PIXEL REALI sotto il footprint contro il
        # colore EFFETTIVO dell'oggetto (dominanti moltiplicati per il
        # color_filter, come li rendera' l'engine): e' il look finale che deve
        # fondersi, non la palette grezza. Cap rilassato con attempts_frac.
        # Skip per line_art. RNG del tentativo gia' consumato: il reject non
        # altera la sequenza del seed.
        if style != "line_art":
            dom_rgb = dominant_rgb_cache.get(cid)
            if dom_rgb is None:
                dom_rgb = _obj_dominant_rgb(obj_an)
                dominant_rgb_cache[cid] = dom_rgb
            if dom_rgb:
                if tuple(color_filter) != (255, 255, 255):
                    cf_r, cf_g, cf_b = color_filter
                    tinted = [(r * cf_r // 255, g * cf_g // 255, b * cf_b // 255)
                              for (r, g, b) in dom_rgb]
                else:
                    tinted = dom_rgb
                obj_labs = _rgb_list_to_lab(tinted)
                de = _footprint_delta_e(bg, obj_labs, x_min, y_min, x_max, y_max)
                if de is not None:
                    attempts_frac = total_attempts / max(1, max_total_attempts)
                    de_cap = (DELTAE_MAX.get(difficulty, DELTAE_MAX["medium"])
                              * (1.0 + DELTAE_RELAX_GAIN * attempts_frac))
                    if de > de_cap:
                        reject_reasons["color_deltaE"] += 1
                        continue

        # Layer: round-robin dei layer ammessi (l'utente puo' escludere alcuni)
        layer = layer_rot[len(placed) % len(layer_rot)]

        # Visibility score (qualita' del nascondiglio) + ENFORCEMENT banda (v3).
        vs = _visibility_score(bg, obj_an, cy, cx, float(anchor_below[cy, cx]), style)
        # Banda [min, max] per difficolta': il max e' il floor di risolvibilita'
        # (nessun oggetto introvabile), il min scarta i piazzamenti banali.
        # Allargata linearmente con attempts_frac per garantire il completamento.
        band_lo, band_hi = VISIBILITY_BAND.get(difficulty, VISIBILITY_BAND["medium"])
        band_relax = VIS_BAND_RELAX_GAIN * (total_attempts / max(1, max_total_attempts))
        if not (band_lo - band_relax <= vs <= band_hi + band_relax):
            reject_reasons["vis_band"] += 1
            continue

        placed.append(PlacedObject(
            catalog_id=cid,
            x=obj_x, y=obj_y,
            scale=scale, rotation=rot_deg,
            flip_x=flip_x, flip_y=flip_y,
            alpha=alpha, color_filter=color_filter,
            detection_type=dt,
            width=ref_w,        # Dimensione REF nel JSON (lo scale e' applicato a runtime)
            height=ref_h,
            radius=ref_radius,
            layer=layer,
            visibility_score=vs,
        ))

        # Aggiorna occupied: HARD ZERO sul bbox + buffer adaptive
        cx_world = (x_min + x_max) / 2
        cy_world = (y_min + y_max) / 2
        cell_px = bg.cell_px
        # Buffer di hard-zero: dipende da density. Bassa density = buffer ampio
        # per spaziare oggetti; alta density = buffer minimale per consentire fitting.
        if count <= 30:
            buf_frac = 0.5  # raddoppia l'esclusione attorno all'oggetto
        elif count <= 100:
            buf_frac = 0.25
        elif count <= 200:
            buf_frac = 0.10
        else:
            buf_frac = 0.0  # solo bbox
        buf_x = (x_max - x_min) * buf_frac
        buf_y = (y_max - y_min) * buf_frac
        cx0 = max(0, int((x_min - buf_x) / cell_px))
        cy0 = max(0, int((y_min - buf_y) / cell_px))
        cx1 = min(bg.cell_w, int((x_max + buf_x) / cell_px) + 1)
        cy1 = min(bg.cell_h, int((y_max + buf_y) / cell_px) + 1)
        occupied[cy0:cy1, cx0:cx1] = 0.0
        # 2. Gaussian buffer attorno per anti-cluster smooth
        _mark_occupied_gaussian(occupied, bg, cx_world, cy_world,
                                eff_size=eff_size, strength=anti_cluster_strength,
                                sigma_scale=gauss_sigma_scale)

    log.info(f"[SCATTER] placed {len(placed)}/{count} after {total_attempts} attempts "
             f"(layer={allowed_layers[0] if len(allowed_layers)==1 else 'multi'}) "
             f"rejects: {reject_reasons}")

    # ── SWAP OPTIMIZATION PASS (v2.0) ────────────────────────────────────
    # Hill-climbing: scambia catalog_id tra posizioni se aumenta lo score.
    # Solo se siamo NEL pass single-layer (lo swap globale lo fa il caller multi-layer).
    if len(placed) >= 2 and len(allowed_layers) == 1:
        placed = _swap_optimize(placed, bg, catalog_analyses, weights, max_iters=2,
                                color_gates=color_gate_cache,
                                forbidden_mask=forbidden_mask)
    return placed


def _swap_optimize(placed: list[PlacedObject], bg: BGAnalysis,
                   catalog_analyses: dict, weights: dict,
                   max_iters: int = 2,
                   color_gates: Optional[dict[str, Optional[np.ndarray]]] = None,
                   forbidden_mask: Optional[np.ndarray] = None) -> list[PlacedObject]:
    """Hill-climbing: scambia oggetti tra posizioni per massimizzare visibility totale.

    Greedy: per ogni coppia (i, j), valuta lo score se gli oggetti i e j si
    scambiassero di posizione (x, y, rotation, scale, layer restano alla posizione).
    Se lo swap aumenta la somma dei visibility score, tienilo.

    color_gates/forbidden_mask (v3, default None = comportamento storico): uno
    swap e' ammesso solo se la cella di destinazione NON e' vetata per l'oggetto
    entrante (gate colore per-catalog_id) ne' vietata in assoluto (volti/manuale).
    """
    def _swap_dest_allowed(cid_key: str, cy_: int, cx_: int) -> bool:
        if forbidden_mask is not None and bool(forbidden_mask[cy_, cx_]):
            return False
        if color_gates:
            g = color_gates.get(cid_key)
            if g is not None and bool(g[cy_, cx_]):
                return False
        return True

    # Memoizzazione: lo score di (catalog_id, cella) e' una funzione PURA del BG e
    # della palette dell'oggetto, quindi NON cambia durante gli swap (gli oggetti
    # cambiano cella ma lo score di "catalogo X alla cella (cy,cx)" e' invariante).
    # Nel doppio loop le stesse coppie (oggetto, cella) vengono valutate molte volte
    # (es. _score_at(an_i, cyi, cxi) per ogni j): memoizzare elimina le ricomputazioni
    # ridondanti di _color_similarity restituendo float identici -> swap identici.
    _score_cache: dict[tuple, float] = {}

    def _score_at(obj_an, cy, cx):
        key = (obj_an.catalog_id, cy, cx)
        cached = _score_cache.get(key)
        if cached is not None:
            return cached
        s = 0.30 * float(bg.edge_density[cy, cx])
        s += 0.30 * float(1.0 - bg.saliency[cy, cx])
        s += 0.15 * _color_similarity(obj_an.palette,
                                       float(bg.hue[cy, cx]),
                                       float(bg.sat[cy, cx]),
                                       float(bg.val[cy, cx]))
        if bg.horizontal_score is not None:
            s += 0.15 * float(bg.horizontal_score[cy, cx])
        if bg.semantic_score is not None:
            s += 0.10 * max(0.0, float(bg.semantic_score[cy, cx]))
        _score_cache[key] = s
        return s

    improved_total = 0
    for it in range(max_iters):
        improved_this_iter = 0
        for i in range(len(placed)):
            for j in range(i + 1, len(placed)):
                obj_i = placed[i]
                obj_j = placed[j]
                cell_px = bg.cell_px
                cyi = int(min(bg.cell_h - 1, max(0, obj_i.y / cell_px)))
                cxi = int(min(bg.cell_w - 1, max(0, obj_i.x / cell_px)))
                cyj = int(min(bg.cell_h - 1, max(0, obj_j.y / cell_px)))
                cxj = int(min(bg.cell_w - 1, max(0, obj_j.x / cell_px)))
                an_i = catalog_analyses.get(obj_i.catalog_id)
                an_j = catalog_analyses.get(obj_j.catalog_id)
                if an_i is None or an_j is None:
                    continue
                # Gate-aware: destinazioni vetate per l'oggetto entrante = no swap.
                if not (_swap_dest_allowed(obj_j.catalog_id, cyi, cxi)
                        and _swap_dest_allowed(obj_i.catalog_id, cyj, cxj)):
                    continue
                # Score corrente
                cur = _score_at(an_i, cyi, cxi) + _score_at(an_j, cyj, cxj)
                # Score se scambiati
                swap = _score_at(an_j, cyi, cxi) + _score_at(an_i, cyj, cxj)
                if swap > cur + 0.02:  # margine per evitare swap insignificanti
                    # Effettua swap: scambio catalog_id e tutto cio' che dipende dal modello
                    placed[i] = PlacedObject(
                        catalog_id=obj_j.catalog_id,
                        x=obj_i.x, y=obj_i.y,
                        scale=obj_j.scale, rotation=obj_i.rotation,
                        flip_x=obj_j.flip_x, flip_y=obj_j.flip_y,
                        alpha=obj_j.alpha, color_filter=obj_j.color_filter,
                        detection_type=obj_j.detection_type,
                        width=obj_j.width, height=obj_j.height,
                        radius=obj_j.radius,
                        layer=obj_i.layer,
                        visibility_score=_score_at(an_j, cyi, cxi),
                    )
                    placed[j] = PlacedObject(
                        catalog_id=obj_i.catalog_id,
                        x=obj_j.x, y=obj_j.y,
                        scale=obj_i.scale, rotation=obj_j.rotation,
                        flip_x=obj_i.flip_x, flip_y=obj_i.flip_y,
                        alpha=obj_i.alpha, color_filter=obj_i.color_filter,
                        detection_type=obj_i.detection_type,
                        width=obj_i.width, height=obj_i.height,
                        radius=obj_i.radius,
                        layer=obj_j.layer,
                        visibility_score=_score_at(an_i, cyj, cxj),
                    )
                    improved_this_iter += 1
        improved_total += improved_this_iter
        if improved_this_iter == 0:
            break
    if improved_total > 0:
        log.info(f"[SCATTER] swap optimization: {improved_total} swap migliorativi")
    return placed


def _hsv_to_tint_rgb(hue: float, sat: float, val: float, mix: float = 0.15) -> tuple[int, int, int]:
    """HSV (0..1 each) → RGB int per applicare come color_filter. Mix con bianco per leggerezza."""
    if _HAS_CV2:
        h = int(hue * 180) % 180
        s = int(sat * 255)
        v = int(val * 255)
        rgb = cv2.cvtColor(np.uint8([[[h, s, v]]]), cv2.COLOR_HSV2RGB)[0, 0]
        r, g, b = int(rgb[0]), int(rgb[1]), int(rgb[2])
    else:
        r, g, b = 200, 200, 200
    # Mix con bianco (255,255,255) per leggerezza: result = mix*color + (1-mix)*white
    wr = int(mix * r + (1 - mix) * 255)
    wg = int(mix * g + (1 - mix) * 255)
    wb = int(mix * b + (1 - mix) * 255)
    return (max(0, min(255, wr)), max(0, min(255, wg)), max(0, min(255, wb)))


def _mark_occupied(occ: np.ndarray, bg: BGAnalysis,
                   x_min: float, y_min: float, x_max: float, y_max: float,
                   value: float = 0.1, radius_factor: float = 1.5):
    """Decrementa lo score delle celle coperte (+ buffer) per anti-cluster (versione netta, legacy)."""
    cell_px = bg.cell_px
    cx0 = max(0, int(x_min // cell_px) - 1)
    cy0 = max(0, int(y_min // cell_px) - 1)
    cx1 = min(bg.cell_w, int(x_max // cell_px) + 2)
    cy1 = min(bg.cell_h, int(y_max // cell_px) + 2)
    occ[cy0:cy1, cx0:cx1] *= value


def _mark_occupied_gaussian(occ: np.ndarray, bg: BGAnalysis,
                            cx_world: float, cy_world: float,
                            eff_size: float, strength: float = 0.85,
                            sigma_scale: float = 0.9):
    """Decay gaussiano dell'occupied grid attorno al centro dell'oggetto.

    sigma_scale: piu' basso = decay piu' stretto (oggetti possono stare piu' vicini)
    strength: piu' basso = repulsione piu' debole
    """
    cell_px = bg.cell_px
    ccx = cx_world / cell_px
    ccy = cy_world / cell_px
    sigma = max(1.0, eff_size / cell_px * sigma_scale)
    # Calcola gaussiana solo nell'area che la influenza significativamente (±3σ)
    radius = int(3 * sigma) + 1
    x0 = max(0, int(ccx) - radius)
    x1 = min(bg.cell_w, int(ccx) + radius + 1)
    y0 = max(0, int(ccy) - radius)
    y1 = min(bg.cell_h, int(ccy) + radius + 1)
    if x1 <= x0 or y1 <= y0:
        return
    yy, xx = np.mgrid[y0:y1, x0:x1].astype(np.float32)
    dist2 = (xx - ccx) ** 2 + (yy - ccy) ** 2
    gauss = np.exp(-dist2 / (2 * sigma * sigma))
    # Reduce occupied by strength * gaussian. occ rimane ∈ [0, 1]
    occ[y0:y1, x0:x1] *= (1.0 - strength * gauss)
    np.maximum(occ[y0:y1, x0:x1], 0.0, out=occ[y0:y1, x0:x1])


def _overlaps_any(x_min: float, y_min: float, x_max: float, y_max: float,
                  placed: list[PlacedObject],
                  existing_bboxes: Optional[list[tuple[float, float, float, float]]],
                  eff_size: float, overlap_margin_factor: float = 0.20) -> bool:
    """Controlla se la nuova bbox si sovrappone troppo con i piazzati o gli esistenti.

    overlap_margin_factor: % di overlap accettato (0.20 = 20% di compenetrazione).
    Piu' alto = piu' tollerante (utile per density alta).
    """
    # Margine POSITIVO: restringe la bbox dei piazzati cosi' da TOLLERARE una
    # compenetrazione pari a overlap_margin_factor. Un fattore piu' alto rende il
    # piazzamento piu' permissivo (come da docstring), non piu' restrittivo.
    margin = eff_size * overlap_margin_factor
    for p in placed:
        if p.detection_type == "circle":
            r = p.radius * p.scale
            px_min, py_min = p.x - r, p.y - r
            px_max, py_max = p.x + r, p.y + r
        else:
            w = p.width * p.scale
            h = p.height * p.scale
            px_min, py_min = p.x, p.y
            px_max, py_max = p.x + w, p.y + h
        if _rects_overlap(x_min, y_min, x_max, y_max,
                          px_min + margin, py_min + margin,
                          px_max - margin, py_max - margin):
            return True
    if existing_bboxes:
        for (ex0, ey0, ex1, ey1) in existing_bboxes:
            if _rects_overlap(x_min, y_min, x_max, y_max, ex0, ey0, ex1, ey1):
                return True
    return False


def _rects_overlap(ax0, ay0, ax1, ay1, bx0, by0, bx1, by1) -> bool:
    return not (ax1 < bx0 or ax0 > bx1 or ay1 < by0 or ay0 > by1)
