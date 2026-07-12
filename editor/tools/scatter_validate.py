"""
editor/tools/scatter_validate.py

Validazione POST-RENDER del camouflage: compone ogni oggetto piazzato sul
background con la stessa pipeline visiva del gioco e misura quanto stacca
dall'intorno nell'immagine finale (quella che vede il giocatore).

v4 (ondata 1): la misura e' la metrica unica di scatter_metrics
(CamouflageScore): rim Delta-E, interior Delta-E, boundary contrast, texture
mismatch, saliency delta, aggregati nel pop_score. Questo modulo mantiene
l'API storica (results/summarize/annotate/filter_failed) e la mappa sulle
nuove misure:
  - delta_e / delta_l : componente interior (media oggetto vs anello, storica)
  - score             : pop_score aggregato (scala ~1.45x della vecchia:
                        soglie ricalibrate sotto)
  - verdict           : "ok" (mimetizzato), "warn" (visibile), "fail" (in
                        evidenza)
  + rim_delta_e, boundary_contrast, texture_mismatch, saliency_delta, clutter.

API:
    results = validate_placements(bg_surface, placed, entries, game_path, repo_root)
    stats   = summarize(results)
    annotate(canvas_surface, results)   # bordi verde/arancio/rosso sul render
"""

from __future__ import annotations

import logging
from pathlib import Path

log = logging.getLogger(__name__)

try:
    import cv2  # type: ignore
    _HAS_CV2 = True
except Exception:
    _HAS_CV2 = False

# render_sprite e' canonico in scatter_metrics (re-export per compatibilita':
# preview tool e filter_failed lo usano da qui).
from editor.tools.scatter_metrics import measure_placements, render_sprite

# Pixel dello sprite considerati "oggetto" (alpha oltre questa soglia)
VALIDATE_ALPHA_MIN = 40
# Soglie del verdetto sul pop_score (scala v4 ~1.45x della vecchia scala
# interior-only: 22/38 -> 32/55, ricalibrate sul benchmark baseline con
# corr(pop, old_score) = 0.785 su 1331 oggetti reali).
SCORE_OK_MAX = 32.0
SCORE_WARN_MAX = 55.0


def validate_placements(bg_surface, placed: list, entries: dict,
                        game_path: Path, repo_root: Path) -> list[dict]:
    """Analizza il render finale e da' un verdetto di camouflage per oggetto.

    Ritorna una lista di dict:
      {catalog_id, rect (x0,y0,x1,y1 px BG), delta_e, delta_l, clutter,
       score, verdict, rim_delta_e, boundary_contrast, texture_mismatch,
       saliency_delta}
    Oggetti con icona mancante o area degenere vengono saltati (verdict
    assente dalla lista). Senza cv2 ritorna [].
    """
    if not _HAS_CV2:
        log.warning("[VALIDATE] cv2 assente: validazione non disponibile")
        return []
    metrics = measure_placements(bg_surface, placed, entries,
                                 game_path, repo_root)
    results: list[dict] = []
    for m in metrics:
        if m.pop_score <= SCORE_OK_MAX:
            verdict = "ok"
        elif m.pop_score <= SCORE_WARN_MAX:
            verdict = "warn"
        else:
            verdict = "fail"
        results.append({
            "catalog_id": m.catalog_id,
            "rect": m.rect,
            "delta_e": m.interior_delta_e,
            "delta_l": m.delta_l,
            "clutter": m.clutter,
            "score": m.pop_score,
            "verdict": verdict,
            "rim_delta_e": m.rim_delta_e,
            "boundary_contrast": m.boundary_contrast,
            "texture_mismatch": m.texture_mismatch,
            "saliency_delta": m.saliency_delta,
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


def results_by_placed(placed: list, results: list[dict], entries: dict,
                      game_path: Path, repo_root: Path) -> list:
    """Lista PARALLELA a placed col risultato di validate di ciascun oggetto
    (o None se non validato). Stesso key-match di filter_failed: serve alla
    UI per mostrare verdetto/metriche del singolo ghost (U4)."""
    by_key = {(r["catalog_id"], r["rect"][0], r["rect"][1]): r
              for r in results}
    icon_cache: dict = {}
    out: list = []
    for p in placed:
        entry = entries.get(p.catalog_id)
        rendered = render_sprite(p, entry, game_path, repo_root,
                                 icon_cache) if entry else None
        if rendered is None:
            out.append(None)
            continue
        img, cx, cy = rendered
        sw, sh = img.get_size()
        key = (p.catalog_id,
               max(0, int(round(cx - sw / 2))),
               max(0, int(round(cy - sh / 2))))
        out.append(by_key.get(key))
    return out


def _placed_bboxes(placed: list) -> list[tuple[float, float, float, float]]:
    """Bbox (x0, y0, x1, y1) in px BG dei piazzati, per existing_bboxes."""
    out: list[tuple[float, float, float, float]] = []
    for p in placed:
        if p.detection_type == "circle":
            r = p.radius * p.scale
            out.append((p.x - r, p.y - r, p.x + r, p.y + r))
        else:
            w = p.width * p.scale
            h = p.height * p.scale
            out.append((p.x, p.y, p.x + w, p.y + h))
    return out


def run_scatter_with_repair(bg_analysis, catalog_analyses: dict, entries: dict,
                            *, bg_surface, game_path: Path, repo_root: Path,
                            count: int, difficulty: str = "medium",
                            style: str = "real", tag_filter=None,
                            existing_bboxes=None, seed=None,
                            allowed_layers=None, forbidden_mask=None,
                            render_ctx: dict | None = None,
                            max_repair_rounds: int = 2,
                            progress_cb=None, cancel_event=None
                            ) -> tuple[list, list[dict], dict]:
    """Pipeline completa S6: place -> validate -> scarta i fail -> RIPIAZZA.

    filter_failed da solo lascia la scena sotto il count richiesto in
    silenzio; qui i bocciati vengono rimpiazzati con nuovi pass di
    place_objects (existing_bboxes aggiornate coi tenuti), fino a
    max_repair_rounds giri. Report onesto alla fine.

    Ritorna (kept, results, report):
      kept    : PlacedObject finali (validati, fail rimossi).
      results : verdetti di validate_placements ALLINEATI a kept.
      report  : {"requested", "delivered", "repair_rounds", "dropped_fail",
                 "ok", "warn"}.
    Deterministica dato seed: i giri di repair proseguono lo stream RNG
    seedato dal primo place_objects. progress_cb/cancel_event propagati
    (ScatterCancelled propaga al chiamante).
    """
    from editor.tools.scatter_engine import place_objects

    base_existing = list(existing_bboxes or [])
    placed = place_objects(
        bg_analysis, catalog_analyses, entries, count=count,
        difficulty=difficulty, style=style, tag_filter=tag_filter,
        existing_bboxes=base_existing, seed=seed,
        allowed_layers=allowed_layers, forbidden_mask=forbidden_mask,
        render_ctx=render_ctx, progress_cb=progress_cb,
        cancel_event=cancel_event,
    )
    rounds = 0
    dropped_total = 0
    while True:
        if cancel_event is not None and cancel_event.is_set():
            from editor.tools.scatter_engine import ScatterCancelled
            raise ScatterCancelled()
        results = validate_placements(bg_surface, placed, entries,
                                      game_path, repo_root)
        kept, dropped = filter_failed(placed, results, entries,
                                      game_path, repo_root)
        dropped_total += dropped
        missing = count - len(kept)
        if missing <= 0 or rounds >= max_repair_rounds:
            placed = kept
            break
        rounds += 1
        log.info(f"[REPAIR] giro {rounds}: {dropped} scartati, "
                 f"ripiazzo {missing} oggetti")
        refill = place_objects(
            bg_analysis, catalog_analyses, entries, count=missing,
            difficulty=difficulty, style=style, tag_filter=tag_filter,
            existing_bboxes=base_existing + _placed_bboxes(kept),
            seed=None,  # prosegue lo stream RNG del run seedato
            allowed_layers=allowed_layers, forbidden_mask=forbidden_mask,
            render_ctx=render_ctx, progress_cb=None,
            cancel_event=cancel_event,
        )
        if not refill:
            placed = kept
            break
        placed = kept + refill

    # Allinea i results ai tenuti (dopo un refill l'ultimo validate copre
    # anche oggetti poi scartati: ricalcola solo se disallineato).
    if len(results) != len(placed) or any(r["verdict"] == "fail" for r in results):
        results = validate_placements(bg_surface, placed, entries,
                                      game_path, repo_root)
    stats = summarize(results)
    report = {
        "requested": count,
        "delivered": len(placed),
        "repair_rounds": rounds,
        "dropped_fail": dropped_total,
        "ok": stats["ok"],
        "warn": stats["warn"],
    }
    if len(placed) < count:
        log.info(f"[REPAIR] richiesti {count}, consegnati {len(placed)} "
                 f"dopo {rounds} giri di repair")
    return placed, results, report
