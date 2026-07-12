"""
editor/tools/scatter_metrics.py

Metrica unica di camuffamento render-based ("CamouflageScore"). Misura quanto
un oggetto COMPOSITATO sul background stacca visivamente, guardando cio' che
guarda davvero un giocatore: il bordo (rim), l'interno rispetto all'intorno,
il contrasto di silhouette, il mismatch di texture e quanto il piazzamento
attira l'attenzione. E' la fonte unica per validazione, benchmark, swap e
(in seguito) piazzamento best-of-M: un solo obiettivo, niente proxy divergenti.

Componenti per oggetto (scala Delta-E-like, 0 = invisibile):
  rim_delta_e       : Delta-E fra banda interna al contorno alpha e banda
                      esterna adiacente sul composito (il "melt" del bordo e'
                      il segnale n.1: e' la silhouette che tradisce l'oggetto).
  interior_delta_e  : Delta-E fra media Lab dell'oggetto composito e media
                      dell'anello BG (metrica storica di scatter_validate).
  delta_l           : componente di sola luminanza dell'interior (l'occhio e'
                      piu' sensibile al contrasto di luminosita').
  boundary_contrast : energia di gradiente AGGIUNTA dal contorno dell'oggetto
                      rispetto allo stesso percorso nel BG puro (>= 0).
  texture_mismatch  : differenza di energia in alta frequenza (varianza del
                      Laplaciano) fra l'oggetto a scala finale e l'intorno
                      (liscio-su-busy e busy-su-liscio staccano entrambi).
  saliency_delta    : aumento di saliency locale causato dal composito (>= 0),
                      0 se cv2.saliency non e' disponibile.
  clutter           : std Lab dell'anello, 0..1 (un intorno variegato maschera
                      il contrasto: riduce la severita').

Aggregato:
  pop_score = (W_RIM*rim + W_INTERIOR*interior + W_DELTA_L*delta_l
               + W_BOUNDARY*boundary + W_TEXTURE*texture + W_SALIENCY*saliency)
              / (1 + CLUTTER_SOFTEN*clutter)
  0 = perfettamente fuso; la scala resta confrontabile con le soglie storiche
  di scatter_validate (SCORE_OK_MAX / SCORE_WARN_MAX).

Tutte le misure lavorano su un patch con lato massimo PATCH_MAX_SIDE (costo
costante anche per oggetti enormi). Senza cv2 il modulo non e' operativo
(measure_placements ritorna lista vuota, come scatter_validate).
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np

log = logging.getLogger(__name__)

try:
    import cv2  # type: ignore
    _HAS_CV2 = True
except Exception:
    _HAS_CV2 = False

# Pixel dello sprite considerati "oggetto" (alpha oltre questa soglia)
ALPHA_MIN = 40
# Lato massimo del patch di lavoro: sopra, downscale INTER_AREA (costo costante)
PATCH_MAX_SIDE = 192
# Spessore in px (alla scala di lavoro) delle bande rim interna/esterna
RIM_PX = 3
# Espansione del bbox sprite per l'anello di contesto (frazione per lato)
RING_EXPAND_FRAC = 0.30
# Minimo numero di pixel per considerare valida una banda/regione
MIN_REGION_PX = 16
# Normalizzazioni verso la scala Delta-E-like (calibrate sul benchmark S0:
# portano i valori tipici dei termini nella stessa banda 0..40 dell'interior)
BOUNDARY_NORM = 12.0
TEXTURE_SCALE = 3.0
SALIENCY_SCALE = 40.0
# Lato massimo del patch per la saliency (e' il termine piu' costoso)
SALIENCY_MAX_SIDE = 128
# Pesi dell'aggregato pop_score
W_RIM = 0.80
W_INTERIOR = 0.50
W_DELTA_L = 0.30
W_BOUNDARY = 1.00
W_TEXTURE = 1.00
W_SALIENCY = 1.00
# Riduzione severita' su intorni variegati (il clutter maschera il contrasto)
CLUTTER_SOFTEN = 0.8
# Normalizzazione della std Lab dell'anello (oltre = clutter pieno)
CLUTTER_STD_REF = 40.0


@dataclass
class ObjectCamouflage:
    """Misure di camuffamento di un singolo oggetto compositato."""
    catalog_id: str
    rect: tuple[int, int, int, int]      # bbox sprite clippato al BG (px)
    interior_delta_e: float
    delta_l: float
    rim_delta_e: Optional[float]         # None se le bande rim sono degeneri
    boundary_contrast: float
    texture_mismatch: float
    saliency_delta: float
    clutter: float
    pop_score: float


def render_sprite(placed_obj, entry: dict, game_path: Path,
                  repo_root: Path, icon_cache: Optional[dict] = None):
    """Sprite renderizzato con la pipeline visiva del gioco.

    Ritorna (surface, center_x, center_y) o None se l'icona manca.
    Pipeline identica a engine/core.py: scale -> flip -> color_filter
    (BLEND_RGBA_MULT) -> rotazione -> alpha. Canonica qui: scatter_validate
    la importa da questo modulo.
    """
    import pygame
    icon_rel = entry.get("icon", "")
    base = icon_cache.get(icon_rel) if icon_cache is not None else None
    if base is None:
        ip = None
        for cand in (game_path / icon_rel, repo_root / "engine" / "assets" / icon_rel):
            if icon_rel and cand.exists():
                ip = cand
                break
        if ip is None:
            return None
        base = pygame.image.load(str(ip)).convert_alpha()
        if icon_cache is not None:
            icon_cache[icon_rel] = base
    p = placed_obj
    w = max(1, int(round(p.width * p.scale)))
    h = max(1, int(round(p.height * p.scale)))
    img = pygame.transform.smoothscale(base, (w, h))
    if p.flip_x or p.flip_y:
        img = pygame.transform.flip(img, p.flip_x, p.flip_y)
    if tuple(p.color_filter) != (255, 255, 255):
        tint = pygame.Surface(img.get_size(), pygame.SRCALPHA)
        tint.fill((*p.color_filter, 255))
        img.blit(tint, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    if p.rotation:
        img = pygame.transform.rotozoom(img, -p.rotation, 1.0)
    if p.alpha < 255:
        img.set_alpha(int(p.alpha))
    if p.detection_type == "circle":
        cx, cy = p.x, p.y
    else:
        cx = p.x + p.width * p.scale / 2
        cy = p.y + p.height * p.scale / 2
    return img, cx, cy


def _lab_true(rgb_u8: np.ndarray) -> np.ndarray:
    """RGB uint8 (N, 3) -> Lab vero float32 (L 0..100, a/b ~-128..127)."""
    lab = cv2.cvtColor(rgb_u8.reshape(1, -1, 3), cv2.COLOR_RGB2LAB)[0].astype(np.float32)
    lab[:, 0] *= (100.0 / 255.0)
    lab[:, 1] -= 128.0
    lab[:, 2] -= 128.0
    return lab


def _lab_mean(rgb_pixels: np.ndarray) -> Optional[np.ndarray]:
    """Media Lab (3,) dei pixel RGB uint8 (N, 3); None se vuoto."""
    if rgb_pixels.shape[0] < 1:
        return None
    return _lab_true(rgb_pixels.astype(np.uint8)).mean(axis=0)


def _saliency_mean(rgb: np.ndarray, mask: np.ndarray) -> Optional[float]:
    """Saliency media (0..1) dei pixel in mask; None se cv2.saliency assente.

    Il patch viene ridotto a SALIENCY_MAX_SIDE per costo costante.
    """
    if not hasattr(cv2, "saliency"):
        return None
    h, w = rgb.shape[:2]
    scale = min(1.0, SALIENCY_MAX_SIDE / max(h, w))
    if scale < 1.0:
        sw, sh = max(8, int(w * scale)), max(8, int(h * scale))
        small = cv2.resize(rgb, (sw, sh), interpolation=cv2.INTER_AREA)
        m_small = cv2.resize(mask.astype(np.uint8), (sw, sh),
                             interpolation=cv2.INTER_NEAREST).astype(bool)
    else:
        small, m_small = rgb, mask
    if int(m_small.sum()) < MIN_REGION_PX:
        return None
    try:
        engine = cv2.saliency.StaticSaliencyFineGrained_create()
        ok, sal = engine.computeSaliency(small)
        if not ok:
            return None
        return float(sal[m_small].mean())
    except Exception as e:
        log.debug(f"[METRICS] saliency fallita: {e}")
        return None


def aggregate_pop(interior_delta_e: float, delta_l: float,
                  rim_delta_e: Optional[float], boundary_contrast: float,
                  texture_mismatch: float, saliency_delta: float,
                  clutter: float) -> float:
    """Aggregato pop_score (0 = fuso). Se il rim e' degenere (None) il suo
    peso ricade sull'interior: approssimazione conservativa, mai gratis."""
    rim_term = rim_delta_e if rim_delta_e is not None else interior_delta_e
    num = (W_RIM * rim_term
           + W_INTERIOR * interior_delta_e
           + W_DELTA_L * delta_l
           + W_BOUNDARY * boundary_contrast
           + W_TEXTURE * texture_mismatch
           + W_SALIENCY * saliency_delta)
    return float(num / (1.0 + CLUTTER_SOFTEN * clutter))


def measure_placement(bg_surface, bg_rgb: np.ndarray, placed_obj, entry: dict,
                      game_path: Path, repo_root: Path,
                      icon_cache: Optional[dict] = None,
                      with_saliency: bool = True) -> Optional[ObjectCamouflage]:
    """Misura completa di camuffamento per UN oggetto piazzato.

    bg_rgb: array (H, W, 3) uint8 del background (evita riconversioni per
    chiamate ripetute). Ritorna None se icona mancante o area degenere.
    """
    if not _HAS_CV2:
        return None
    import pygame
    H, W = bg_rgb.shape[:2]
    rendered = render_sprite(placed_obj, entry, game_path, repo_root, icon_cache)
    if rendered is None:
        return None
    img, cx, cy = rendered
    sw, sh = img.get_size()
    x0 = int(round(cx - sw / 2)); y0 = int(round(cy - sh / 2))
    x1, y1 = x0 + sw, y0 + sh
    bx0, by0 = max(0, x0), max(0, y0)
    bx1, by1 = min(W, x1), min(H, y1)
    if bx1 - bx0 < 4 or by1 - by0 < 4:
        return None

    # Patch ESPANSO oltre il bbox sprite: rim/boundary/texture hanno bisogno
    # di pixel BG di contesto ATTORNO all'oggetto (un patch = bbox esatto
    # renderebbe degeneri la banda esterna e il confronto texture).
    margin = int(math.ceil(max(8.0, 0.18 * max(sw, sh))))
    px0, py0 = max(0, x0 - margin), max(0, y0 - margin)
    px1, py1 = min(W, x1 + margin), min(H, y1 + margin)

    # Composito = esattamente cio' che vede il giocatore (tint/alpha inclusi)
    patch_surf = pygame.Surface((px1 - px0, py1 - py0))
    patch_surf.blit(bg_surface, (0, 0), area=pygame.Rect(px0, py0,
                                                         px1 - px0, py1 - py0))
    patch_surf.blit(img, (x0 - px0, y0 - py0))
    comp = pygame.surfarray.array3d(patch_surf).swapaxes(0, 1)  # (h, w, 3)
    bg_patch = bg_rgb[py0:py1, px0:px1]

    # Maschera oggetto collocata nel patch espanso (intersezione clippata)
    a = pygame.surfarray.array_alpha(img).swapaxes(0, 1)
    mask = np.zeros(comp.shape[:2], dtype=bool)
    sx0, sy0 = max(x0, px0), max(y0, py0)
    sx1, sy1 = min(x1, px1), min(y1, py1)
    if sx1 - sx0 < 2 or sy1 - sy0 < 2:
        return None
    mask[sy0 - py0: sy1 - py0, sx0 - px0: sx1 - px0] = (
        a[sy0 - y0: sy1 - y0, sx0 - x0: sx1 - x0] > ALPHA_MIN)
    if int(mask.sum()) < MIN_REGION_PX:
        return None

    # Downscale a costo costante (INTER_AREA; mask NEAREST per non sfumarla)
    ph, pw = comp.shape[:2]
    f = min(1.0, PATCH_MAX_SIDE / max(ph, pw))
    if f < 1.0:
        dw, dh = max(8, int(pw * f)), max(8, int(ph * f))
        comp = cv2.resize(comp, (dw, dh), interpolation=cv2.INTER_AREA)
        bg_patch = cv2.resize(bg_patch, (dw, dh), interpolation=cv2.INTER_AREA)
        mask = cv2.resize(mask.astype(np.uint8), (dw, dh),
                          interpolation=cv2.INTER_NEAREST).astype(bool)
        if int(mask.sum()) < MIN_REGION_PX:
            return None

    comp = np.ascontiguousarray(comp)
    bg_patch = np.ascontiguousarray(bg_patch)

    # ── ANELLO di contesto: pixel BG ORIGINALI fuori dal bbox (full-res) ──
    ex = int((bx1 - bx0) * RING_EXPAND_FRAC)
    ey = int((by1 - by0) * RING_EXPAND_FRAC)
    rx0, ry0 = max(0, bx0 - ex), max(0, by0 - ey)
    rx1, ry1 = min(W, bx1 + ex), min(H, by1 + ey)
    ring_region = bg_rgb[ry0:ry1, rx0:rx1]
    ring_mask = np.ones(ring_region.shape[:2], dtype=bool)
    ring_mask[by0 - ry0: ring_region.shape[0] - (ry1 - by1),
              bx0 - rx0: ring_region.shape[1] - (rx1 - bx1)] = False
    ring_px = ring_region[ring_mask]
    if ring_px.shape[0] < 32:
        return None
    step = max(1, ring_px.shape[0] // 4096)
    ring_lab = _lab_true(ring_px[::step].astype(np.uint8))
    ring_mean = ring_lab.mean(axis=0)
    ring_std = float(np.linalg.norm(ring_lab.std(axis=0)))
    clutter = min(1.0, ring_std / CLUTTER_STD_REF)

    # ── INTERIOR: media oggetto composito vs media anello (storica) ──────
    obj_mean = _lab_mean(comp[mask])
    if obj_mean is None:
        return None
    d = obj_mean - ring_mean
    interior_delta_e = float(math.sqrt(float((d * d).sum())))
    delta_l = float(abs(d[0]))

    # ── RIM: banda interna vs banda esterna adiacente sul composito ──────
    kernel = np.ones((3, 3), np.uint8)
    m_u8 = mask.astype(np.uint8)
    eroded = cv2.erode(m_u8, kernel, iterations=RIM_PX).astype(bool)
    dilated = cv2.dilate(m_u8, kernel, iterations=RIM_PX).astype(bool)
    inner_band = mask & ~eroded
    outer_band = dilated & ~mask
    rim_delta_e: Optional[float] = None
    if int(inner_band.sum()) >= MIN_REGION_PX and int(outer_band.sum()) >= MIN_REGION_PX:
        in_mean = _lab_mean(comp[inner_band])
        out_mean = _lab_mean(comp[outer_band])
        if in_mean is not None and out_mean is not None:
            rd = in_mean - out_mean
            rim_delta_e = float(math.sqrt(float((rd * rd).sum())))

    # ── BOUNDARY CONTRAST: gradiente aggiunto dal contorno ───────────────
    gray_comp = cv2.cvtColor(comp, cv2.COLOR_RGB2GRAY)
    gray_bg = cv2.cvtColor(bg_patch, cv2.COLOR_RGB2GRAY)
    contour = mask & ~cv2.erode(m_u8, kernel, iterations=1).astype(bool)
    boundary_contrast = 0.0
    if int(contour.sum()) >= MIN_REGION_PX:
        gx = cv2.Sobel(gray_comp, cv2.CV_32F, 1, 0, ksize=3)
        gy = cv2.Sobel(gray_comp, cv2.CV_32F, 0, 1, ksize=3)
        mag_comp = np.sqrt(gx * gx + gy * gy)
        bx = cv2.Sobel(gray_bg, cv2.CV_32F, 1, 0, ksize=3)
        by = cv2.Sobel(gray_bg, cv2.CV_32F, 0, 1, ksize=3)
        mag_bg = np.sqrt(bx * bx + by * by)
        added = float(mag_comp[contour].mean()) - float(mag_bg[contour].mean())
        boundary_contrast = max(0.0, added / BOUNDARY_NORM)

    # ── TEXTURE MISMATCH: alta frequenza oggetto vs intorno ──────────────
    lap = cv2.Laplacian(gray_comp, cv2.CV_32F, ksize=3)
    lap_bg = cv2.Laplacian(gray_bg, cv2.CV_32F, ksize=3)
    core = cv2.erode(m_u8, kernel, iterations=RIM_PX + 1).astype(bool)
    around = dilated & ~mask
    if int(around.sum()) < 32:
        around = ~mask
    texture_mismatch = 0.0
    if int(core.sum()) >= 32 and int(around.sum()) >= 32:
        var_obj = float(lap[core].var())
        var_bg = float(lap_bg[around].var())
        texture_mismatch = abs(math.log1p(var_obj) - math.log1p(var_bg)) * TEXTURE_SCALE

    # ── SALIENCY DELTA: quanto il composito attira di piu' l'occhio ──────
    saliency_delta = 0.0
    if with_saliency:
        sal_comp = _saliency_mean(comp, mask)
        sal_bg = _saliency_mean(bg_patch, mask)
        if sal_comp is not None and sal_bg is not None:
            saliency_delta = max(0.0, (sal_comp - sal_bg)) * SALIENCY_SCALE

    pop = aggregate_pop(interior_delta_e, delta_l, rim_delta_e,
                        boundary_contrast, texture_mismatch, saliency_delta,
                        clutter)
    return ObjectCamouflage(
        catalog_id=placed_obj.catalog_id,
        rect=(bx0, by0, bx1, by1),
        interior_delta_e=round(interior_delta_e, 1),
        delta_l=round(delta_l, 1),
        rim_delta_e=None if rim_delta_e is None else round(rim_delta_e, 1),
        boundary_contrast=round(boundary_contrast, 1),
        texture_mismatch=round(texture_mismatch, 1),
        saliency_delta=round(saliency_delta, 1),
        clutter=round(clutter, 2),
        pop_score=round(pop, 1),
    )


def measure_placements(bg_surface, placed: list, entries: dict,
                       game_path: Path, repo_root: Path,
                       with_saliency: bool = True) -> list[ObjectCamouflage]:
    """Misura tutti i piazzati. Senza cv2 ritorna []. Oggetti con icona
    mancante o area degenere vengono saltati."""
    if not _HAS_CV2:
        log.warning("[METRICS] cv2 assente: metriche camouflage non disponibili")
        return []
    import pygame
    bg_rgb = pygame.surfarray.array3d(bg_surface).swapaxes(0, 1)
    icon_cache: dict = {}
    out: list[ObjectCamouflage] = []
    for p in placed:
        entry = entries.get(p.catalog_id)
        if not entry:
            continue
        m = measure_placement(bg_surface, bg_rgb, p, entry, game_path,
                              repo_root, icon_cache, with_saliency=with_saliency)
        if m is not None:
            out.append(m)
    return out


def summarize_camouflage(metrics: list[ObjectCamouflage]) -> dict:
    """Aggregato per report/benchmark: medie e percentili dei componenti."""
    if not metrics:
        return {"total": 0}
    pops = np.array([m.pop_score for m in metrics], dtype=np.float32)
    rims = np.array([m.rim_delta_e for m in metrics
                     if m.rim_delta_e is not None], dtype=np.float32)
    out = {
        "total": len(metrics),
        "pop_mean": round(float(pops.mean()), 1),
        "pop_median": round(float(np.median(pops)), 1),
        "pop_p90": round(float(np.quantile(pops, 0.90)), 1),
        "interior_mean": round(float(np.mean(
            [m.interior_delta_e for m in metrics])), 1),
        "boundary_mean": round(float(np.mean(
            [m.boundary_contrast for m in metrics])), 1),
        "texture_mean": round(float(np.mean(
            [m.texture_mismatch for m in metrics])), 1),
        "saliency_mean": round(float(np.mean(
            [m.saliency_delta for m in metrics])), 1),
    }
    if rims.size:
        out["rim_mean"] = round(float(rims.mean()), 1)
        out["rim_p90"] = round(float(np.quantile(rims, 0.90)), 1)
    return out
