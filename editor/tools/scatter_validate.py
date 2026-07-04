"""
editor/tools/scatter_validate.py

Validazione POST-RENDER del camouflage: compone ogni oggetto piazzato sul
background con la stessa pipeline visiva del gioco e misura quanto stacca
dall'intorno nell'immagine finale (quella che vede il giocatore).

Metrica per oggetto:
  - delta_e  : distanza Lab (CIE76) fra la media dei pixel COMPOSITATI
               dell'oggetto e la media dell'anello di sfondo circostante.
  - delta_l  : componente di sola luminanza (l'occhio e' piu' sensibile al
               contrasto di luminosita' che di tinta).
  - clutter  : deviazione std Lab dell'anello. Un intorno variegato maschera
               il contrasto: la severita' viene ridotta di conseguenza.
  - score    : (delta_e + peso*delta_l) / (1 + soften*clutter_norm)
  - verdict  : "ok" (mimetizzato), "warn" (visibile), "fail" (in evidenza).

API:
    results = validate_placements(bg_surface, placed, entries, game_path, repo_root)
    stats   = summarize(results)
    annotate(canvas_surface, results)   # bordi verde/arancio/rosso sul render
"""

from __future__ import annotations

import logging
import math
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
VALIDATE_ALPHA_MIN = 40
# Espansione del bbox sprite per l'anello di contesto (frazione per lato)
RING_EXPAND_FRAC = 0.30
# Soglie del verdetto sullo score effettivo (Delta-E adattato)
SCORE_OK_MAX = 22.0
SCORE_WARN_MAX = 38.0
# Peso extra della differenza di sola luminanza nel punteggio
LUMA_CONTRAST_WEIGHT = 0.5
# Riduzione severita' su intorni variegati (clutter maschera il contrasto)
CLUTTER_SOFTEN = 0.8
# Normalizzazione della std Lab dell'anello (oltre = clutter pieno)
CLUTTER_STD_REF = 40.0


def _lab_true(rgb_u8: np.ndarray) -> np.ndarray:
    """RGB uint8 (N, 3) -> Lab vero float32 (L 0..100, a/b ~-128..127)."""
    lab = cv2.cvtColor(rgb_u8.reshape(1, -1, 3), cv2.COLOR_RGB2LAB)[0].astype(np.float32)
    lab[:, 0] *= (100.0 / 255.0)
    lab[:, 1] -= 128.0
    lab[:, 2] -= 128.0
    return lab


def render_sprite(placed_obj, entry: dict, game_path: Path,
                  repo_root: Path, icon_cache: Optional[dict] = None):
    """Sprite renderizzato con la pipeline visiva del gioco.

    Ritorna (surface, center_x, center_y) o None se l'icona manca.
    Pipeline identica a engine/core.py: scale -> flip -> color_filter
    (BLEND_RGBA_MULT) -> rotazione -> alpha.
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


def validate_placements(bg_surface, placed: list, entries: dict,
                        game_path: Path, repo_root: Path) -> list[dict]:
    """Analizza il render finale e da' un verdetto di camouflage per oggetto.

    Ritorna una lista di dict:
      {catalog_id, rect (x0,y0,x1,y1 px BG), delta_e, delta_l, clutter,
       score, verdict}
    Oggetti con icona mancante o area degenere vengono saltati (verdict
    assente dalla lista). Senza cv2 ritorna [].
    """
    if not _HAS_CV2:
        log.warning("[VALIDATE] cv2 assente: validazione non disponibile")
        return []
    import pygame
    bg_rgb = pygame.surfarray.array3d(bg_surface).swapaxes(0, 1)  # (H, W, 3)
    H, W = bg_rgb.shape[:2]
    icon_cache: dict = {}
    results: list[dict] = []

    for p in placed:
        entry = entries.get(p.catalog_id)
        if not entry:
            continue
        rendered = render_sprite(p, entry, game_path, repo_root, icon_cache)
        if rendered is None:
            continue
        img, cx, cy = rendered
        sw, sh = img.get_size()
        x0 = int(round(cx - sw / 2)); y0 = int(round(cy - sh / 2))
        x1, y1 = x0 + sw, y0 + sh
        # Clip al BG
        bx0, by0 = max(0, x0), max(0, y0)
        bx1, by1 = min(W, x1), min(H, y1)
        if bx1 - bx0 < 4 or by1 - by0 < 4:
            continue

        # Composita lo sprite su una copia del patch BG: e' ESATTAMENTE cio'
        # che vede il giocatore (tint/alpha/rotazione inclusi).
        patch_surf = pygame.Surface((bx1 - bx0, by1 - by0))
        patch_surf.blit(bg_surface, (0, 0), area=pygame.Rect(bx0, by0,
                                                             bx1 - bx0, by1 - by0))
        patch_surf.blit(img, (x0 - bx0, y0 - by0))
        comp = pygame.surfarray.array3d(patch_surf).swapaxes(0, 1)  # (h, w, 3)

        # Maschera oggetto dal canale alpha dello sprite, clippata al BG
        a = pygame.surfarray.array_alpha(img).swapaxes(0, 1)
        a = a[by0 - y0: by1 - y0, bx0 - x0: bx1 - x0]
        mask = a > VALIDATE_ALPHA_MIN
        if int(mask.sum()) < 16:
            continue

        obj_lab = _lab_true(comp[mask].astype(np.uint8))
        obj_mean = obj_lab.mean(axis=0)

        # Anello di contesto: bbox espanso, pixel BG ORIGINALI fuori dal bbox
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
            continue
        # Subsample deterministico dell'anello (costo costante)
        step = max(1, ring_px.shape[0] // 4096)
        ring_lab = _lab_true(ring_px[::step].astype(np.uint8))
        ring_mean = ring_lab.mean(axis=0)
        ring_std = float(np.linalg.norm(ring_lab.std(axis=0)))

        d = obj_mean - ring_mean
        delta_e = float(math.sqrt(float((d * d).sum())))
        delta_l = float(abs(d[0]))
        clutter = min(1.0, ring_std / CLUTTER_STD_REF)
        score = (delta_e + LUMA_CONTRAST_WEIGHT * delta_l) / (1.0 + CLUTTER_SOFTEN * clutter)
        if score <= SCORE_OK_MAX:
            verdict = "ok"
        elif score <= SCORE_WARN_MAX:
            verdict = "warn"
        else:
            verdict = "fail"
        results.append({
            "catalog_id": p.catalog_id,
            "rect": (bx0, by0, bx1, by1),
            "delta_e": round(delta_e, 1),
            "delta_l": round(delta_l, 1),
            "clutter": round(clutter, 2),
            "score": round(score, 1),
            "verdict": verdict,
        })
    return results


def summarize(results: list[dict]) -> dict:
    """Aggregato: conteggi per verdetto + score medio."""
    out = {"total": len(results), "ok": 0, "warn": 0, "fail": 0, "avg_score": 0.0}
    for r in results:
        out[r["verdict"]] += 1
    if results:
        out["avg_score"] = round(sum(r["score"] for r in results) / len(results), 1)
    return out


def filter_failed(placed: list, results: list[dict], entries: dict,
                  game_path: Path, repo_root: Path) -> tuple[list, int]:
    """Rimuove dai piazzati gli oggetti BOCCIATI dalla validazione.

    Match per (catalog_id, x0, y0 del rect sprite), ricostruito con la stessa
    pipeline di render del validatore. Ritorna (kept, n_scartati).
    """
    fail_keys = {(r["catalog_id"], r["rect"][0], r["rect"][1])
                 for r in results if r["verdict"] == "fail"}
    if not fail_keys:
        return list(placed), 0
    icon_cache: dict = {}
    kept: list = []
    dropped = 0
    for p in placed:
        entry = entries.get(p.catalog_id)
        rendered = render_sprite(p, entry, game_path, repo_root,
                                 icon_cache) if entry else None
        if rendered is not None:
            img, cx, cy = rendered
            sw, sh = img.get_size()
            key = (p.catalog_id,
                   max(0, int(round(cx - sw / 2))),
                   max(0, int(round(cy - sh / 2))))
            if key in fail_keys:
                dropped += 1
                continue
        kept.append(p)
    return kept, dropped


def annotate(canvas_surface, results: list[dict]) -> None:
    """Disegna il verdetto sul render: verde ok, arancio warn, rosso fail."""
    import pygame
    colors = {"ok": (60, 220, 60), "warn": (255, 170, 0), "fail": (255, 40, 40)}
    for r in results:
        x0, y0, x1, y1 = r["rect"]
        pygame.draw.rect(canvas_surface, colors[r["verdict"]],
                         pygame.Rect(x0, y0, x1 - x0, y1 - y0),
                         2 if r["verdict"] == "ok" else 5)
