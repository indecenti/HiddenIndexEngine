"""
editor/mixins/scene_stats.py

SceneStatsMixin — pannello "Statistiche scena": conteggi, densita'/copertura,
distribuzione dimensioni e stima della difficolta' (camouflage) per gli oggetti
goal della scena corrente.

La stima di difficolta' riusa le funzioni di scoring di
editor/tools/scatter_engine.py (via "classic", nessun modello IA):
  - analyze_background(...)  -> BGAnalysis (edge density, saliency, HSV per cella)
  - precompute_catalog(...)  -> ObjAnalysis per oggetto (palette, orient)
  - _visibility_score(...)   -> qualita' del nascondiglio 0..~1 per cella
  - _color_similarity(...)   -> match cromatico palette oggetto vs zona BG

Il mixin e' autocontenuto: tutto lo stato e' letto con getattr(self, ..., default),
nessuna inizializzazione richiesta in editor_base. Interfaccia esposta:
  _stats_open / _stats_close / _stats_modal_click / _stats_modal_wheel /
  _stats_modal_key / _r_stats_modal (+ flag booleano self._stats_modal).

Il calcolo avviene UNA volta in _stats_open (cache in self._stats_data);
il bottone "Ricalcola" lo ripete. Nessuna scrittura su disco.
"""

from __future__ import annotations

import time
from typing import Any, Callable, Optional

import pygame

from editor.constants import (
    ACCENT, BORDER, CANVAS, PANEL,
    TXT, TXT_DIM, TXT_HI,
    OK_C, WARN_C, ERR_C,
    DEFAULT_LAYERS,
)
from editor.ui.draw import (
    _button, _draw_text, _in_rect, _rect, _scrollbar, _text_wh,
)
from engine.utils import get_logger

logger = get_logger(__name__)

# ─── Costanti layout modale ───────────────────────────────────────────────────
_MODAL_W: int = 880
_MODAL_H: int = 620
_HDR_H: int = 56
_FOOTER_H: int = 30
_PAD: int = 16
_LEFT_W: int = 380              # colonna sinistra (conteggi/copertura/dimensioni)
_LINE_H: int = 18               # interlinea testo statistiche
_SECTION_GAP: int = 12          # spazio verticale fra sezioni
_LIST_ROW_H: int = 44           # altezza riga lista difficolta'
_LIST_TOP_OFFSET: int = 52      # spazio per titolo + media sopra la lista
_SCROLL_BTN: int = 22           # lato bottoni scroll su/giu

# ─── Costanti griglia quadranti (densita' spaziale) ───────────────────────────
_GRID_ROWS: int = 3
_GRID_COLS: int = 3
_GRID_CELL_W: int = 56
_GRID_CELL_H: int = 30
_GRID_CROWD_MIN: int = 3        # minimo assoluto per considerare una cella affollata
_GRID_CROWD_FACTOR: float = 2.0  # cella affollata se count >= factor * media

# ─── Costanti dati scena (allineate a engine/scene_loader) ────────────────────
_DEFAULT_RADIUS: float = 30.0   # default engine per detection circle
_SMALL_AREA_FRAC: float = 0.001  # bbox sotto 0.1% dell'area BG = oggetto "piccolo"

# ─── Soglie qualitative sul visibility score (alto = ben nascosto) ────────────
_SCORE_EASY_MAX: float = 0.35
_SCORE_MEDIUM_MAX: float = 0.55
_LBL_EASY: str = "Facile"
_LBL_MEDIUM: str = "Media"
_LBL_HARD: str = "Difficile"
_LBL_NA: str = "n/d"
# Offset celle sotto l'oggetto per l'anchor anti-floating (come place_objects)
_ANCHOR_BELOW_OFFSETS: tuple[int, ...] = (1, 2)


def _as_bool(v: object) -> bool:
    """Replica _to_bool di engine/scene_loader (bool, stringhe 'true'/'1'/'yes')."""
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        return v.lower() in ("true", "1", "yes")
    return bool(v)


def _object_bbox(obj: dict) -> Optional[tuple[float, float, float, float]]:
    """
    Bounding box (left, top, w, h) in spazio pixel nativo del background.
    Convenzione ancore: rect (x,y)=top-left; circle/mask (x,y)=centro con
    dimensione width|radius*2 (come engine/scene_loader).
    """
    try:
        x = float(obj.get("x", 0))
        y = float(obj.get("y", 0))
        width = float(obj.get("width", 0) or 0)
        height = float(obj.get("height", 0) or 0)
        radius = float(obj.get("radius", _DEFAULT_RADIUS) or _DEFAULT_RADIUS)
    except (TypeError, ValueError):
        return None
    dt = str(obj.get("detection_type", ""))
    if dt == "rect":
        if width <= 0 or height <= 0:
            return None  # dimensioni assenti: bbox non calcolabile
        return (x, y, width, height)
    w = width if width > 0 else radius * 2.0
    h = height if height > 0 else radius * 2.0
    return (x - w / 2.0, y - h / 2.0, w, h)


def _score_label(score: Optional[float]) -> str:
    """Etichetta qualitativa dal visibility score (alto = piu' nascosto)."""
    if score is None:
        return _LBL_NA
    if score < _SCORE_EASY_MAX:
        return _LBL_EASY
    if score < _SCORE_MEDIUM_MAX:
        return _LBL_MEDIUM
    return _LBL_HARD


def _label_color(label: str) -> tuple[int, int, int]:
    """Colore associato all'etichetta qualitativa."""
    return {
        _LBL_EASY: OK_C,
        _LBL_MEDIUM: WARN_C,
        _LBL_HARD: ERR_C,
    }.get(label, TXT_DIM)


class SceneStatsMixin:
    """
    Mixin che aggiunge il pannello "Statistiche scena" all'editor.

    Stato gestito (tutto via getattr, nessun init richiesto):
        _stats_modal        : bool  — modale aperto/chiuso
        _stats_data         : dict | None — statistiche calcolate (cache)
        _stats_scroll       : int   — scroll lista difficolta' (in righe)
        _stats_hitboxes     : dict  — hitbox bottoni per il click handler
        _stats_visible_rows : int   — righe visibili lista (settato dal render)
        _stats_bg_cache     : tuple | None — (key, BGAnalysis) cache analisi BG
    """

    # ─────────────────────────────────────────────────────────────────────────
    # APERTURA / CHIUSURA
    # ─────────────────────────────────────────────────────────────────────────

    def _stats_open(self) -> None:
        """Apre il modale e calcola/ricalcola le statistiche della scena corrente."""
        scene_data = getattr(self, "scene_data", None)
        if not getattr(self, "scene_path", None) or not isinstance(scene_data, dict):
            self._stats_status("Apri prima una scena per vedere le statistiche", WARN_C)
            return
        self._stats_modal = True
        self._stats_scroll = 0
        self._stats_hitboxes = {}
        self._stats_data = None  # il render mostra "Calcolo..." finche' non c'e' data
        self._stats_status("Calcolo statistiche scena...", TXT_DIM)

        with_loading = getattr(self, "_with_loading", None)
        if callable(with_loading):
            data = with_loading(self._stats_compute)
        else:
            try:
                data = self._stats_compute()
            except Exception as e:  # difesa totale: mai crashare l'editor
                logger.error(f"[STATS] Calcolo statistiche fallito: {e}", exc_info=True)
                data = None
        if not isinstance(data, dict):
            data = {"error": "Calcolo statistiche fallito (vedi log)"}
        self._stats_data = data
        elapsed = data.get("elapsed_s")
        if elapsed is not None:
            self._stats_status(f"Statistiche calcolate in {elapsed:.2f}s", OK_C)

    def _stats_close(self) -> None:
        """Chiude il modale statistiche (i dati restano in cache)."""
        self._stats_modal = False

    def _stats_status(self, msg: str, color: tuple = TXT_DIM) -> None:
        """Messaggio in status bar, se il metodo dell'editor e' disponibile."""
        status = getattr(self, "_status", None)
        if callable(status):
            status(msg, color, 3)

    # ─────────────────────────────────────────────────────────────────────────
    # CALCOLO STATISTICHE
    # ─────────────────────────────────────────────────────────────────────────

    def _stats_compute(self) -> dict:
        """
        Calcola tutte le statistiche da self.scene_data / self.bg_surf / self.catalog.
        Non solleva mai: ogni sezione fallita viene marcata nel dict risultato.
        """
        t0 = time.time()
        scene_data = getattr(self, "scene_data", None)
        scene_data = scene_data if isinstance(scene_data, dict) else {}
        objects = [o for o in scene_data.get("objects", []) if isinstance(o, dict)]
        effects = [e for e in scene_data.get("effects", []) if isinstance(e, dict)]

        bg_surf = getattr(self, "bg_surf", None)
        bg_size: Optional[tuple[int, int]] = None
        if bg_surf is not None:
            try:
                bg_size = bg_surf.get_size()
            except Exception as e:
                logger.warning(f"[STATS] Dimensioni background non lette: {e}")

        data: dict[str, Any] = {
            "scene_id": str(scene_data.get("id", "")),
            "bg_size": bg_size,
            "error": None,
        }
        for key, fn in (
            ("counts", lambda: self._stats_counts(objects, effects, scene_data)),
            ("coverage", lambda: self._stats_coverage(objects, bg_size)),
            ("sizes", lambda: self._stats_sizes(objects, bg_size)),
            ("difficulty", lambda: self._stats_difficulty(objects, scene_data)),
        ):
            try:
                data[key] = fn()
            except Exception as e:
                logger.error(f"[STATS] Sezione '{key}' fallita: {e}", exc_info=True)
                data[key] = None
        data["elapsed_s"] = time.time() - t0
        return data

    @staticmethod
    def _stats_counts(objects: list, effects: list, scene_data: dict) -> dict:
        """Conteggi: totale, per layer, goal (con auto_random_finds), effetti, fissi."""
        known_ids = [lyr["id"] for lyr in DEFAULT_LAYERS]
        per_layer: dict[str, int] = {lid: 0 for lid in known_ids}
        other = 0
        for obj in objects:
            lid = str(obj.get("layer", "objects_mid"))
            if lid in per_layer:
                per_layer[lid] += 1
            else:
                other += 1

        auto_random = _as_bool(scene_data.get("auto_random_finds", False))
        if auto_random and objects:
            # I goal sono assegnati a runtime dallo shuffle dell'engine.
            try:
                num_goals = int(scene_data.get("num_random_finds", len(objects)))
            except (TypeError, ValueError):
                num_goals = len(objects)
            goals = min(max(num_goals, 0), len(objects))
            goals_note = f"shuffle runtime: {goals} pescati su {len(objects)}"
        else:
            # Default engine: is_goal=True se assente.
            goals = sum(1 for o in objects if _as_bool(o.get("is_goal", True)))
            goals_note = ""

        return {
            "total": len(objects),
            "per_layer": per_layer,
            "other_layers": other,
            "effects": len(effects),
            "goals": goals,
            "goals_note": goals_note,
            "auto_random": auto_random,
            "always_show": sum(1 for o in objects if _as_bool(o.get("always_show", False))),
        }

    @staticmethod
    def _stats_coverage(objects: list, bg_size: Optional[tuple[int, int]]) -> dict:
        """Copertura: area bbox totale / area BG (%) + conteggio per quadrante 3x3."""
        out: dict[str, Any] = {
            "pct": None,
            "grid": None,
            "empty_cells": None,
            "invalid": 0,
        }
        boxes = []
        for obj in objects:
            box = _object_bbox(obj)
            if box is None:
                out["invalid"] += 1
            else:
                boxes.append(box)
        if bg_size is None or bg_size[0] <= 0 or bg_size[1] <= 0:
            return out
        bg_w, bg_h = bg_size
        bg_area = float(bg_w * bg_h)

        # Somma delle aree bbox (le sovrapposizioni non vengono deduplicate:
        # e' una stima di ingombro, non un'area di unione esatta).
        total_area = sum(w * h for (_l, _t, w, h) in boxes)
        out["pct"] = total_area / bg_area * 100.0

        grid = [[0 for _ in range(_GRID_COLS)] for _ in range(_GRID_ROWS)]
        for left, top, w, h in boxes:
            cx = left + w / 2.0
            cy = top + h / 2.0
            col = min(max(int(cx / bg_w * _GRID_COLS), 0), _GRID_COLS - 1)
            row = min(max(int(cy / bg_h * _GRID_ROWS), 0), _GRID_ROWS - 1)
            grid[row][col] += 1
        out["grid"] = grid
        out["empty_cells"] = sum(1 for r in grid for n in r if n == 0)
        return out

    @staticmethod
    def _stats_sizes(objects: list, bg_size: Optional[tuple[int, int]]) -> dict:
        """Distribuzione dimensioni: min/media/max area bbox (px e % BG) + piccoli."""
        areas = []
        for obj in objects:
            box = _object_bbox(obj)
            if box is not None and box[2] > 0 and box[3] > 0:
                areas.append(box[2] * box[3])
        out: dict[str, Any] = {
            "n": len(areas),
            "min_px": None, "avg_px": None, "max_px": None,
            "min_pct": None, "avg_pct": None, "max_pct": None,
            "small": None, "small_thr_px": None,
        }
        if not areas:
            return out
        out["min_px"] = min(areas)
        out["avg_px"] = sum(areas) / len(areas)
        out["max_px"] = max(areas)
        if bg_size and bg_size[0] > 0 and bg_size[1] > 0:
            bg_area = float(bg_size[0] * bg_size[1])
            out["min_pct"] = out["min_px"] / bg_area * 100.0
            out["avg_pct"] = out["avg_px"] / bg_area * 100.0
            out["max_pct"] = out["max_px"] / bg_area * 100.0
            thr = _SMALL_AREA_FRAC * bg_area
            out["small_thr_px"] = thr
            out["small"] = sum(1 for a in areas if a < thr)
        return out

    # ── Difficolta' / camouflage (riuso scoring di scatter_engine) ────────────

    def _stats_difficulty(self, objects: list, scene_data: dict) -> dict:
        """
        Stima di difficolta' per ogni oggetto goal: visibility score del
        nascondiglio nella posizione attuale (via classic, nessun modello IA).
        """
        out: dict[str, Any] = {
            "items": [], "avg": None, "label": _LBL_NA,
            "note": "", "error": None, "failed": 0,
        }
        bg_surf = getattr(self, "bg_surf", None)
        if bg_surf is None:
            out["error"] = "Background non disponibile"
            return out
        try:
            from editor.tools.scatter_engine import (
                analyze_background, precompute_catalog,
                _visibility_score, _color_similarity,
            )
        except Exception as e:
            logger.error(f"[STATS] scatter_engine non importabile: {e}")
            out["error"] = "Modulo scatter_engine non disponibile"
            return out

        auto_random = _as_bool(scene_data.get("auto_random_finds", False))
        if auto_random and objects:
            goal_idx = list(range(len(objects)))
            out["note"] = "auto_random_finds attivo: valutati tutti gli oggetti del pool"
        else:
            goal_idx = [
                i for i, o in enumerate(objects)
                if _as_bool(o.get("is_goal", True))
            ]
        if not goal_idx:
            out["error"] = "Nessun oggetto goal nella scena"
            return out

        try:
            bg_an = self._stats_bg_analysis(analyze_background, bg_surf)
        except Exception as e:
            logger.error(f"[STATS] Analisi background fallita: {e}", exc_info=True)
            bg_an = None
        if bg_an is None:
            out["error"] = "Analisi background fallita"
            return out

        catalog = getattr(self, "catalog", []) or []
        cat_index = {
            str(c.get("id")): c for c in catalog
            if isinstance(c, dict) and c.get("id")
        }
        analyses = self._stats_catalog_analyses(
            precompute_catalog, catalog, cat_index, objects, goal_idx,
        )

        cell_h, cell_w = bg_an.edge_density.shape
        cell_px = int(bg_an.cell_px)
        for i in goal_idx:
            obj = objects[i]
            cid = str(obj.get("catalog_id", "?"))
            entry = cat_index.get(cid)
            style = str(entry.get("style", "real")) if entry else "real"
            item: dict[str, Any] = {
                "idx": i, "catalog_id": cid, "score": None,
                "color": None, "edge": None, "label": _LBL_NA, "err": None,
            }
            try:
                obj_an = (analyses.get(style) or {}).get(cid)
                box = _object_bbox(obj)
                if obj_an is None:
                    item["err"] = "oggetto non analizzabile (icona/catalogo)"
                elif box is None:
                    item["err"] = "bbox non calcolabile"
                else:
                    left, top, bw, bh = box
                    cx = min(max(int((left + bw / 2.0) // cell_px), 0), cell_w - 1)
                    cy = min(max(int((top + bh / 2.0) // cell_px), 0), cell_h - 1)
                    # Anchor anti-floating: edge density delle celle sotto
                    # (fuori griglia = 0, come lo shift con zero-fill dell'engine).
                    anchor = 0.0
                    for off in _ANCHOR_BELOW_OFFSETS:
                        if cy + off < cell_h:
                            anchor += float(bg_an.edge_density[cy + off, cx])
                    anchor /= float(len(_ANCHOR_BELOW_OFFSETS))
                    vs = _visibility_score(bg_an, obj_an, cy, cx, anchor, style)
                    item["score"] = float(vs)
                    item["label"] = _score_label(item["score"])
                    item["edge"] = float(bg_an.edge_density[cy, cx])
                    item["color"] = float(_color_similarity(
                        obj_an.palette,
                        float(bg_an.hue[cy, cx]),
                        float(bg_an.sat[cy, cx]),
                        float(bg_an.val[cy, cx]),
                    ))
            except Exception as e:
                logger.warning(f"[STATS] Score oggetto #{i} ({cid}) fallito: {e}")
                item["err"] = "calcolo fallito"
            out["items"].append(item)

        # Ordina dal piu' facile (score basso) al piu' difficile; n/d in coda.
        out["items"].sort(key=lambda it: (it["score"] is None, it["score"] or 0.0))
        valid = [it["score"] for it in out["items"] if it["score"] is not None]
        out["failed"] = len(out["items"]) - len(valid)
        if valid:
            out["avg"] = sum(valid) / len(valid)
            out["label"] = _score_label(out["avg"])
        return out

    def _stats_bg_analysis(self, analyze_fn: Callable, bg_surf: pygame.Surface):
        """
        BGAnalysis della scena corrente con cache di sessione. Riusa l'analisi
        del modulo scatter se gia' presente e coerente col BG attuale, altrimenti
        analizza via classic (ia_model=None; la cache SQLite dell'engine resta attiva).
        """
        size = bg_surf.get_size()
        key = (str(getattr(self, "scene_path", "")), size)
        cached = getattr(self, "_stats_bg_cache", None)
        if cached and cached[0] == key:
            return cached[1]

        bg_an = None
        scatter_an = getattr(self, "_scatter_bg_analysis", None)
        if scatter_an is not None and (scatter_an.bg_w, scatter_an.bg_h) == size:
            bg_an = scatter_an  # riuso: stessi campi richiesti dallo scoring
        if bg_an is None:
            bg_an = analyze_fn(
                bg_surf, ia_model=None,
                base_path=getattr(self, "base_path", None), use_cache=True,
            )
        self._stats_bg_cache = (key, bg_an)
        return bg_an

    def _stats_catalog_analyses(
        self,
        precompute_fn: Callable,
        catalog: list,
        cat_index: dict,
        objects: list,
        goal_idx: list,
    ) -> dict[str, dict]:
        """
        ObjAnalysis per stile, solo per gli stili degli oggetti goal.
        Riusa la cache del modulo scatter quando presente; altrimenti
        precompute_catalog (che ha la sua cache su disco). Stili falliti -> {}.
        """
        styles: set[str] = set()
        for i in goal_idx:
            cid = str(objects[i].get("catalog_id", ""))
            entry = cat_index.get(cid)
            styles.add(str(entry.get("style", "real")) if entry else "real")

        scatter_cache = getattr(self, "_scatter_catalog_cache", None) or {}
        base_path = getattr(self, "base_path", None)
        analyses: dict[str, dict] = {}
        for style in styles:
            cached = scatter_cache.get(style)
            if isinstance(cached, dict) and cached:
                analyses[style] = cached
                continue
            try:
                analyses[style] = precompute_fn(catalog, style, base_path)
            except Exception as e:
                logger.warning(f"[STATS] precompute_catalog '{style}' fallito: {e}")
                analyses[style] = {}
        return analyses

    # ─────────────────────────────────────────────────────────────────────────
    # INPUT
    # ─────────────────────────────────────────────────────────────────────────

    def _stats_modal_click(self, mx: int, my: int, w: int, h: int) -> None:
        """Gestione click: chiusura su X/fuori box, Ricalcola, bottoni scroll."""
        if not getattr(self, "_stats_modal", False):
            return
        hb = getattr(self, "_stats_hitboxes", {}) or {}
        dx = (w - _MODAL_W) // 2
        dy = (h - _MODAL_H) // 2
        modal_rect = hb.get("modal", pygame.Rect(dx, dy, _MODAL_W, _MODAL_H))

        if not _in_rect((mx, my), modal_rect):
            self._stats_close()
            return
        close_r = hb.get("close")
        if close_r and _in_rect((mx, my), close_r):
            self._stats_close()
            return
        recalc_r = hb.get("recalc")
        if recalc_r and _in_rect((mx, my), recalc_r):
            self._stats_open()  # ricalcola e resta aperto
            return
        up_r = hb.get("scroll_up")
        if up_r and _in_rect((mx, my), up_r):
            self._stats_scroll_by(-1)
            return
        down_r = hb.get("scroll_down")
        if down_r and _in_rect((mx, my), down_r):
            self._stats_scroll_by(1)
            return

    def _stats_modal_wheel(self, ev: pygame.event.Event) -> None:
        """Scroll della lista difficolta' con la rotella."""
        if not getattr(self, "_stats_modal", False):
            return
        self._stats_scroll_by(-int(getattr(ev, "y", 0)))

    def _stats_modal_key(self, ev: pygame.event.Event) -> None:
        """Esc chiude; frecce su/giu scorrono la lista."""
        if not getattr(self, "_stats_modal", False):
            return
        if ev.key == pygame.K_ESCAPE:
            self._stats_close()
        elif ev.key == pygame.K_DOWN:
            self._stats_scroll_by(1)
        elif ev.key == pygame.K_UP:
            self._stats_scroll_by(-1)

    def _stats_scroll_by(self, delta: int) -> None:
        """Applica delta allo scroll clampando sul numero di righe visibili."""
        data = getattr(self, "_stats_data", None) or {}
        diff = data.get("difficulty") or {}
        n_items = len(diff.get("items", []))
        visible = max(1, int(getattr(self, "_stats_visible_rows", 1)))
        max_scroll = max(0, n_items - visible)
        cur = int(getattr(self, "_stats_scroll", 0))
        self._stats_scroll = max(0, min(max_scroll, cur + delta))

    # ─────────────────────────────────────────────────────────────────────────
    # RENDERING
    # ─────────────────────────────────────────────────────────────────────────

    def _r_stats_modal(self, w: int, h: int) -> None:
        """Disegna il modale statistiche. Da chiamare solo se _stats_modal e' True."""
        mx, my = pygame.mouse.get_pos()
        dx = (w - _MODAL_W) // 2
        dy = (h - _MODAL_H) // 2
        self._stats_hitboxes = {}

        # Overlay scuro
        overlay = pygame.Surface((w, h), pygame.SRCALPHA)
        overlay.fill((10, 10, 15, 180))
        self.screen.blit(overlay, (0, 0))

        # Corpo modale
        modal_rect = pygame.Rect(dx, dy, _MODAL_W, _MODAL_H)
        _rect(self.screen, (10, 10, 15), (dx + 5, dy + 5, _MODAL_W, _MODAL_H), radius=12)
        _rect(self.screen, PANEL, modal_rect, radius=12)
        _rect(self.screen, ACCENT, modal_rect, 2, radius=12)
        self._stats_hitboxes["modal"] = modal_rect

        # Header
        _rect(self.screen, (38, 40, 55), (dx, dy, _MODAL_W, _HDR_H), radius=12)
        pygame.draw.line(self.screen, BORDER,
                         (dx + 1, dy + _HDR_H), (dx + _MODAL_W - 1, dy + _HDR_H))
        _draw_text(self.screen, "STATISTICHE SCENA", "lg", ACCENT, dx + 20, dy + 10)
        data = getattr(self, "_stats_data", None)
        scene_id = (data or {}).get("scene_id", "") or ""
        bg_size = (data or {}).get("bg_size")
        sub = f"Scena: {scene_id}" if scene_id else "Scena corrente"
        if bg_size:
            sub += f"  |  BG {bg_size[0]}x{bg_size[1]} px"
        _draw_text(self.screen, sub, "sm", TXT_DIM, dx + 20, dy + 34, max_w=_MODAL_W - 260)

        recalc_r = pygame.Rect(dx + _MODAL_W - 172, dy + 12, 118, 32)
        _button(self.screen, recalc_r, "Ricalcola", _in_rect((mx, my), recalc_r), font="sm")
        self._stats_hitboxes["recalc"] = recalc_r
        close_r = pygame.Rect(dx + _MODAL_W - 42, dy + 12, 28, 28)
        _button(self.screen, close_r, "X", _in_rect((mx, my), close_r),
                danger=True, font="sm")
        self._stats_hitboxes["close"] = close_r

        # Footer
        footer_y = dy + _MODAL_H - _FOOTER_H + 6
        pygame.draw.line(self.screen, BORDER,
                         (dx + 1, footer_y - 8), (dx + _MODAL_W - 1, footer_y - 8))
        _draw_text(self.screen, "ESC o click fuori per chiudere  |  rotella per scorrere",
                   "xs", TXT_DIM, dx + 20, footer_y)

        body_y = dy + _HDR_H + _PAD
        body_h = _MODAL_H - _HDR_H - _FOOTER_H - 2 * _PAD

        if not isinstance(data, dict):
            _draw_text(self.screen, "Calcolo statistiche in corso...", "md", TXT_DIM,
                       dx + _PAD + 4, body_y + 8)
            return
        if data.get("error"):
            _draw_text(self.screen, str(data["error"]), "md", ERR_C,
                       dx + _PAD + 4, body_y + 8)
            return

        left_x = dx + _PAD
        self._r_stats_left_column(left_x, body_y, _LEFT_W, data)

        sep_x = left_x + _LEFT_W + _PAD // 2
        pygame.draw.line(self.screen, BORDER, (sep_x, body_y), (sep_x, body_y + body_h))
        right_x = sep_x + _PAD
        right_w = dx + _MODAL_W - _PAD - right_x
        self._r_stats_difficulty(right_x, body_y, right_w, body_h,
                                 data.get("difficulty") or {}, mx, my)

        elapsed = data.get("elapsed_s")
        if elapsed is not None:
            info = f"calcolo: {elapsed:.2f}s"
            tw, _th = _text_wh(info, "xs")
            _draw_text(self.screen, info, "xs", TXT_DIM,
                       dx + _MODAL_W - tw - 20, footer_y)

    # ── Colonna sinistra: conteggi / copertura / dimensioni ──────────────────

    def _r_stats_left_column(self, x: int, y: int, w: int, data: dict) -> None:
        """Disegna conteggi, copertura per quadrante e distribuzione dimensioni."""
        cur_y = y
        cur_y = self._r_stats_counts(x, cur_y, w, data.get("counts"))
        cur_y += _SECTION_GAP
        cur_y = self._r_stats_coverage(x, cur_y, w, data.get("coverage"))
        cur_y += _SECTION_GAP
        self._r_stats_sizes(x, cur_y, w, data.get("sizes"))

    def _r_stats_section_title(self, x: int, y: int, w: int, title: str) -> int:
        """Titolo sezione con linea separatrice. Ritorna la y successiva."""
        _draw_text(self.screen, title, "sm", ACCENT, x, y)
        pygame.draw.line(self.screen, BORDER, (x, y + _LINE_H), (x + w - 8, y + _LINE_H))
        return y + _LINE_H + 6

    def _r_stats_line(self, x: int, y: int, w: int, label: str, value: str,
                      value_col: tuple = TXT_HI) -> int:
        """Riga 'label: value'. Ritorna la y successiva."""
        used = _draw_text(self.screen, f"{label}: ", "sm", TXT, x, y, max_w=w - 40)
        _draw_text(self.screen, value, "sm", value_col, x + used, y,
                   max_w=w - used - 8)
        return y + _LINE_H

    def _r_stats_counts(self, x: int, y: int, w: int, counts: Optional[dict]) -> int:
        """Sezione conteggi. Ritorna la y successiva."""
        cur_y = self._r_stats_section_title(x, y, w, "CONTEGGI")
        if not counts:
            return self._r_stats_line(x, cur_y, w, "Conteggi", _LBL_NA, TXT_DIM)
        cur_y = self._r_stats_line(x, cur_y, w, "Oggetti totali", str(counts["total"]))
        for lyr in DEFAULT_LAYERS:
            n = counts["per_layer"].get(lyr["id"], 0)
            col = TXT_HI if n else TXT_DIM
            cur_y = self._r_stats_line(x + 14, cur_y, w - 14, lyr["label"], str(n), col)
        if counts.get("other_layers"):
            cur_y = self._r_stats_line(x + 14, cur_y, w - 14, "Altri layer",
                                       str(counts["other_layers"]), WARN_C)
        cur_y = self._r_stats_line(x + 14, cur_y, w - 14, "Effetti",
                                   str(counts["effects"]),
                                   TXT_HI if counts["effects"] else TXT_DIM)
        goals_val = str(counts["goals"])
        if counts.get("goals_note"):
            goals_val += f"  ({counts['goals_note']})"
        goals_col = OK_C if counts["goals"] else ERR_C
        cur_y = self._r_stats_line(x, cur_y, w, "Oggetti goal", goals_val, goals_col)
        cur_y = self._r_stats_line(x, cur_y, w, "Sempre visibili (always_show)",
                                   str(counts["always_show"]))
        return cur_y

    def _r_stats_coverage(self, x: int, y: int, w: int,
                          coverage: Optional[dict]) -> int:
        """Sezione densita'/copertura con mini-griglia 3x3. Ritorna la y successiva."""
        cur_y = self._r_stats_section_title(x, y, w, "DENSITA' / COPERTURA")
        if not coverage:
            return self._r_stats_line(x, cur_y, w, "Copertura", _LBL_NA, TXT_DIM)
        pct = coverage.get("pct")
        pct_txt = f"{pct:.2f}% del background" if pct is not None else _LBL_NA
        cur_y = self._r_stats_line(x, cur_y, w, "Area bbox totale", pct_txt,
                                   TXT_HI if pct is not None else TXT_DIM)
        if coverage.get("invalid"):
            cur_y = self._r_stats_line(x, cur_y, w, "Oggetti senza bbox",
                                       str(coverage["invalid"]), WARN_C)

        grid = coverage.get("grid")
        if grid is None:
            return self._r_stats_line(x, cur_y, w, "Quadranti", _LBL_NA, TXT_DIM)

        # Mini-griglia: celle vuote in grigio, celle affollate evidenziate.
        total = sum(n for row in grid for n in row)
        avg = total / float(_GRID_ROWS * _GRID_COLS) if total else 0.0
        crowd_thr = max(_GRID_CROWD_MIN, avg * _GRID_CROWD_FACTOR)
        grid_y = cur_y + 2
        for row in range(_GRID_ROWS):
            for col in range(_GRID_COLS):
                n = grid[row][col]
                cell = pygame.Rect(x + col * (_GRID_CELL_W + 2),
                                   grid_y + row * (_GRID_CELL_H + 2),
                                   _GRID_CELL_W, _GRID_CELL_H)
                _rect(self.screen, CANVAS, cell, radius=4)
                border_col = BORDER
                txt_col = TXT_DIM
                if n and n >= crowd_thr:
                    border_col = WARN_C
                    txt_col = WARN_C
                elif n:
                    txt_col = TXT_HI
                _rect(self.screen, border_col, cell, 1, radius=4)
                label = str(n)
                tw, th = _text_wh(label, "sm")
                _draw_text(self.screen, label, "sm", txt_col,
                           cell.x + (cell.w - tw) // 2, cell.y + (cell.h - th) // 2)
        cur_y = grid_y + _GRID_ROWS * (_GRID_CELL_H + 2) + 4
        legend_x = x + _GRID_COLS * (_GRID_CELL_W + 2) + 10
        legend_y = grid_y
        empty = coverage.get("empty_cells")
        if empty is not None:
            _draw_text(self.screen, f"Zone vuote: {empty}/{_GRID_ROWS * _GRID_COLS}",
                       "xs", TXT_DIM, legend_x, legend_y)
            _draw_text(self.screen, f"Affollate: >= {crowd_thr:.0f} ogg.",
                       "xs", TXT_DIM, legend_x, legend_y + _LINE_H - 4)
        return cur_y

    def _r_stats_sizes(self, x: int, y: int, w: int, sizes: Optional[dict]) -> int:
        """Sezione distribuzione dimensioni. Ritorna la y successiva."""
        cur_y = self._r_stats_section_title(x, y, w, "DIMENSIONI (area bbox)")
        if not sizes or not sizes.get("n"):
            return self._r_stats_line(x, cur_y, w, "Dimensioni", _LBL_NA, TXT_DIM)

        def _fmt(px: Optional[float], pct: Optional[float]) -> str:
            if px is None:
                return _LBL_NA
            txt = f"{px:,.0f} px2".replace(",", ".")
            if pct is not None:
                txt += f"  ({pct:.3f}%)"
            return txt

        cur_y = self._r_stats_line(x, cur_y, w, "Min",
                                   _fmt(sizes["min_px"], sizes["min_pct"]))
        cur_y = self._r_stats_line(x, cur_y, w, "Media",
                                   _fmt(sizes["avg_px"], sizes["avg_pct"]))
        cur_y = self._r_stats_line(x, cur_y, w, "Max",
                                   _fmt(sizes["max_px"], sizes["max_pct"]))
        small = sizes.get("small")
        if small is not None:
            label = f"Piccoli (< {_SMALL_AREA_FRAC * 100:.1f}% BG)"
            col = WARN_C if small else TXT_HI
            cur_y = self._r_stats_line(x, cur_y, w, label, str(small), col)
        return cur_y

    # ── Colonna destra: difficolta' per oggetto goal ──────────────────────────

    def _r_stats_difficulty(self, x: int, y: int, w: int, h: int,
                            diff: dict, mx: int, my: int) -> None:
        """Lista scrollabile dei punteggi di camouflage per oggetto goal."""
        cur_y = self._r_stats_section_title(x, y, w, "DIFFICOLTA' OGGETTI GOAL")

        if diff.get("error"):
            _draw_text(self.screen, str(diff["error"]), "sm", WARN_C, x, cur_y,
                       max_w=w - 8)
            return

        avg = diff.get("avg")
        label = diff.get("label", _LBL_NA)
        if avg is not None:
            used = _draw_text(self.screen, f"Media scena: {avg:.2f}  ", "sm", TXT_HI,
                              x, cur_y)
            _draw_text(self.screen, label, "sm", _label_color(label), x + used, cur_y)
        else:
            _draw_text(self.screen, "Media scena: " + _LBL_NA, "sm", TXT_DIM, x, cur_y)
        if diff.get("note"):
            _draw_text(self.screen, diff["note"], "xs", TXT_DIM, x, cur_y + _LINE_H,
                       max_w=w - 8)

        items = diff.get("items", [])
        list_y = y + _LIST_TOP_OFFSET
        list_h = h - _LIST_TOP_OFFSET
        visible = max(1, list_h // _LIST_ROW_H)
        self._stats_visible_rows = visible
        scroll = max(0, min(int(getattr(self, "_stats_scroll", 0)),
                            max(0, len(items) - visible)))
        self._stats_scroll = scroll

        if not items:
            _draw_text(self.screen, "Nessun oggetto da valutare", "sm", TXT_DIM,
                       x, list_y)
            return

        list_w = w - 14  # spazio per scrollbar/bottoni a destra
        self.screen.set_clip(pygame.Rect(x, list_y, list_w, visible * _LIST_ROW_H))
        for rel_i in range(visible):
            abs_i = rel_i + scroll
            if abs_i >= len(items):
                break
            self._r_stats_diff_row(x, list_y + rel_i * _LIST_ROW_H, list_w,
                                   abs_i, items[abs_i])
        self.screen.set_clip(None)

        # Scrollbar + bottoni scroll
        if len(items) > visible:
            _scrollbar(self.screen, x + w - 8, list_y, 6,
                       visible * _LIST_ROW_H - _SCROLL_BTN * 2 - 8,
                       scroll, len(items), visible)
            up_r = pygame.Rect(x + w - _SCROLL_BTN - 1,
                               list_y + visible * _LIST_ROW_H - _SCROLL_BTN * 2 - 4,
                               _SCROLL_BTN, _SCROLL_BTN)
            down_r = pygame.Rect(x + w - _SCROLL_BTN - 1,
                                 list_y + visible * _LIST_ROW_H - _SCROLL_BTN,
                                 _SCROLL_BTN, _SCROLL_BTN)
            _button(self.screen, up_r, "^", _in_rect((mx, my), up_r), font="xs")
            _button(self.screen, down_r, "v", _in_rect((mx, my), down_r), font="xs")
            self._stats_hitboxes["scroll_up"] = up_r
            self._stats_hitboxes["scroll_down"] = down_r

    def _r_stats_diff_row(self, x: int, y: int, w: int, rank: int, item: dict) -> None:
        """Singola riga della lista difficolta' (score, barra, dettaglio)."""
        row_bg = (36, 37, 48) if rank % 2 == 0 else (32, 33, 42)
        _rect(self.screen, row_bg, (x, y, w, _LIST_ROW_H - 2), radius=6)

        score = item.get("score")
        label = item.get("label", _LBL_NA)
        lab_col = _label_color(label)

        _draw_text(self.screen, f"{rank + 1}.", "sm", TXT_DIM, x + 6, y + 5)
        _draw_text(self.screen, item.get("catalog_id", "?"), "sm", TXT_HI,
                   x + 32, y + 5, max_w=w - 170)
        score_txt = f"{score:.2f}" if score is not None else _LBL_NA
        _draw_text(self.screen, score_txt, "mono",
                   TXT_HI if score is not None else TXT_DIM, x + w - 116, y + 5)
        lw, _lh = _text_wh(label, "sm")
        _draw_text(self.screen, label, "sm", lab_col, x + w - lw - 8, y + 5)

        if score is not None:
            # Barra proporzionale al punteggio (clamp 0..1)
            bar_w = int(max(0.0, min(1.0, score)) * (w - 16))
            _rect(self.screen, CANVAS, (x + 8, y + 24, w - 16, 5), radius=2)
            if bar_w > 0:
                _rect(self.screen, lab_col, (x + 8, y + 24, bar_w, 5), radius=2)
            color = item.get("color")
            edge = item.get("edge")
            det = []
            if color is not None:
                det.append(f"colore {color:.2f}")
            if edge is not None:
                det.append(f"edge {edge:.2f}")
            det.append(f"oggetto #{item.get('idx', '?')}")
            _draw_text(self.screen, "  |  ".join(det), "xs", TXT_DIM,
                       x + 8, y + 31, max_w=w - 16)
        else:
            err = item.get("err") or "non calcolato"
            _draw_text(self.screen, err, "xs", WARN_C, x + 8, y + 26, max_w=w - 16)
