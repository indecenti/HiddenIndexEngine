"""
editor/mixins/scatter_modal.py

ScatterModalMixin - popover per auto-scatter intelligente.
UI:
  - Dropdown Stile (real / cartoon / line art)
  - Dropdown Tag tema (filtra il pool)
  - Slider Quantita (1-300)
  - Radio Difficolta (Facile / Medio / Difficile)
  - Bottoni: Genera Anteprima, Ripesca, Applica alla Scena, Chiudi

Ghost preview: gli oggetti pendenti vengono mostrati semi-trasparenti sulla
canvas (overlay disegnato da render_canvas) finche l'utente non clicca Applica.
"""

import logging
import time
from collections import Counter

import pygame

from editor.constants import (
    ACCENT, BORDER, BTN, BTN_AC, BTN_HO, PANEL, BG,
    TXT, TXT_HI, TXT_DIM, OK_C, ERR_C, WARN_C, FX_C,
)
from editor.ui.draw import _rect, _draw_text, _button, _in_rect, _slider, _txt, _clamp

log = logging.getLogger("scatter_modal")

# Tag esclusi dal filtro tema (dimensione/colore puro: non sono temi semantici)
_TAG_BLACKLIST = {
    "piccolo", "medio", "grande",
    "rosso", "verde", "blu", "giallo", "nero", "bianco",
    "arancione", "viola", "cyan", "rosa", "marrone",
    "argento", "oro",
}

# ── Brush zone vietate ───────────────────────────────────────────────────────
# Raggio del pennello in celle: 1 = blocco 3x3 attorno alla cella cliccata.
BRUSH_RADIUS_CELLS = 1
# Nome del file di persistenza per-scena delle celle vietate a mano.
FORBIDDEN_CELLS_FILENAME = "scatter_forbidden.json"
FORBIDDEN_CELLS_VERSION = 1


class ScatterModalMixin:
    """Popover per auto-scatter intelligente di oggetti sulla scena."""

    # ── state init ────────────────────────────────────────────────────────
    def _scatter_modal_init(self):
        self._scatter_modal_open = False
        self._scatter_style = "real"
        self._scatter_tag = None
        self._scatter_count = 12
        self._scatter_difficulty = "medium"
        self._scatter_ghosts = []          # list[PlacedObject]
        self._scatter_bg_cache_key = None  # path scena per cui ho calcolato BGAnalysis
        self._scatter_bg_analysis = None
        self._scatter_catalog_cache = {}   # style -> dict[catalog_id -> ObjAnalysis]
        self._scatter_drop_open = None     # "style" | "tag" | "tier" | None
        self._scatter_tag_scroll = 0
        self._scatter_busy = False
        self._scatter_status_msg = ""
        self._scatter_status_color = TXT_DIM
        self._scatter_hitboxes = {}
        self._scatter_panel_rect = None
        self._scatter_tags_cache = {}      # style -> list[(tag, count)]
        # ── IA tier state ─────────────────────────────────────────────────
        # Carica preferenze persistite da .editor_settings.json
        try:
            _settings = self._load_editor_settings()
            scatter_pref = _settings.get("scatter", {}) or {}
        except Exception:
            scatter_pref = {}
        self._scatter_tier_choice = scatter_pref.get("tier_choice", "auto")
        if self._scatter_tier_choice not in ("auto", "classic", "light", "pro", "ultra"):
            self._scatter_tier_choice = "auto"
        self._scatter_model = None
        self._scatter_model_tier_active = 0
        self._scatter_status_cache = None
        # Layer selection (checkbox). Carica preferenza utente o default tutti attivi.
        saved_layers = scatter_pref.get("layers", {})
        self._scatter_layers = {
            "objects_low":  bool(saved_layers.get("objects_low",  True)),
            "objects_mid":  bool(saved_layers.get("objects_mid",  True)),
            "objects_high": bool(saved_layers.get("objects_high", True)),
        }
        # Almeno uno attivo (sicurezza)
        if not any(self._scatter_layers.values()):
            self._scatter_layers["objects_mid"] = True
        # ── Zone vietate manuali (brush) ──────────────────────────────────
        self._scatter_forbidden_cells = set()   # set[(cx, cy)] in celle griglia
        self._scatter_brush_active = False
        self._scatter_brush_tool = "paint"      # "paint" | "erase"
        self._scatter_forbidden_dirty = False   # da salvare su disco
        # ── Debug overlay (heatmap QA) ────────────────────────────────────
        self._scatter_debug_mode = "off"        # off | score | forbidden | saliency
        self._scatter_debug_map = None          # ndarray (cell_h, cell_w) 0..1
        self._scatter_debug_surf = None         # surface cache per il render
        self._scatter_debug_surf_key = None
        # ── Seed (U2): riproducibilita' delle run ─────────────────────────
        self._scatter_seed_text = ""            # campo numerico (vuoto = random)
        self._scatter_seed_locked = False       # lucchetto: GENERA riusa il seed
        self._scatter_last_seed = None          # seed dell'ultima run
        self._scatter_seed_editing = False      # focus tastiera sul campo
        # ── Worker thread (U1): progress + cancel ─────────────────────────
        self._scatter_progress = None           # (fase, done, total) dal worker
        self._scatter_cancel_event = None       # threading.Event della run attiva
        self._scatter_result = None             # payload worker, consumato dal main
        self._scatter_report = None             # report repair ultima run
        self._scatter_run_token = 0             # invalida risultati di run vecchie

    def _scatter_save_prefs(self):
        """Salva le preferenze scatter (tier + layer) nei settings dell'editor."""
        try:
            self._save_editor_setting("scatter", {
                "tier_choice": self._scatter_tier_choice,
                "layers": dict(self._scatter_layers),
            })
        except Exception as e:
            log.warning(f"[SCATTER] save prefs failed: {e}")

    def _scatter_preload_async(self):
        """Pre-carica il modello in un thread di background al boot dell'editor.

        Non blocca la UI. Se il modello e' gia' caricato o l'utente ha scelto
        'classic', no-op. Errori silenziati (graceful degradation).
        """
        import threading
        if self._scatter_model is not None:
            return
        if self._scatter_tier_choice == "classic":
            return

        # Verifica che il modello richiesto sia presente su disco
        try:
            from editor.tools.scatter_models import is_model_available
        except Exception:
            return
        tier_map = {"light": 1, "pro": 2, "auto": None}
        wanted = tier_map.get(self._scatter_tier_choice)
        if wanted is not None and not is_model_available(wanted, self.base_path):
            log.info(f"[SCATTER] preload skip: modello tier{wanted} non scaricato")
            return
        # Per 'auto' carico il migliore disponibile
        if wanted is None:
            if not (is_model_available(1, self.base_path) or is_model_available(2, self.base_path)):
                return

        def _worker():
            try:
                t0 = time.time()
                self._scatter_load_model()
                dt = time.time() - t0
                if self._scatter_model is not None:
                    log.info(f"[SCATTER] preload OK tier={self._scatter_model.tier} ({self._scatter_model.name}) in {dt:.2f}s")
            except Exception as e:
                log.warning(f"[SCATTER] preload fallito: {e}")

        t = threading.Thread(target=_worker, daemon=True, name="ScatterPreload")
        t.start()

    # ── apri/chiudi ───────────────────────────────────────────────────────
    def _scatter_open(self):
        if not self.scene_path:
            self._status("Apri una scena prima di usare lo scatter", WARN_C, 2)
            return
        if getattr(self, "bg_surf", None) is None:
            self._status("Carica un background per usare lo scatter", WARN_C, 3)
            return
        # Auto-detect stile dominante dalla scena: se >=90% degli oggetti
        # presenti sono di uno stesso stile, pre-selezionalo (utente puo' poi cambiarlo).
        self._scatter_auto_detect_style()
        self._scatter_modal_open = True
        self._scatter_drop_open = None
        self._scatter_tag_scroll = 0
        self._scatter_brush_active = False
        self._scatter_forbidden_load()
        self._scatter_status_msg = "Pronto. Premi GENERA ANTEPRIMA"
        self._scatter_status_color = TXT_DIM

    def _scatter_auto_detect_style(self):
        """Se >=90% degli oggetti scena sono dello stesso stile, pre-seleziona quello."""
        scene_objs = self.scene_data.get("objects", [])
        if not scene_objs:
            return
        # Mappa catalog_id -> style
        cat_style = {c["id"]: c.get("style", "real") for c in self.catalog}
        styles_count = {}
        for o in scene_objs:
            st = cat_style.get(o.get("catalog_id", ""), None)
            if st:
                styles_count[st] = styles_count.get(st, 0) + 1
        if not styles_count:
            return
        total = sum(styles_count.values())
        dominant_style, dominant_n = max(styles_count.items(), key=lambda kv: kv[1])
        ratio = dominant_n / total
        if ratio >= 0.9 and dominant_style != self._scatter_style:
            old = self._scatter_style
            self._scatter_style = dominant_style
            # Reset filtri tag (potrebbero non esistere nel nuovo stile)
            self._scatter_tag = None
            self._scatter_ghosts = []
            log.info(f"[SCATTER] auto-style '{old}' -> '{dominant_style}' ({dominant_n}/{total} = {ratio:.0%})")

    def _scatter_cancel_run(self):
        """Annulla la run in corso (worker thread): best-effort, idempotente."""
        ev = self._scatter_cancel_event
        if ev is not None:
            ev.set()
        self._scatter_run_token += 1   # i risultati della run vecchia si buttano
        self._scatter_busy = False
        self._scatter_progress = None

    def _scatter_close(self):
        self._scatter_cancel_run()
        self._scatter_modal_open = False
        self._scatter_drop_open = None
        self._scatter_ghosts = []
        self._scatter_seed_editing = False
        self._scatter_brush_active = False
        self._scatter_forbidden_save()

    def _scatter_reset(self):
        """Reset stato su cambio scena."""
        self._scatter_cancel_run()
        self._scatter_forbidden_save()
        self._scatter_modal_open = False
        self._scatter_drop_open = None
        self._scatter_ghosts = []
        self._scatter_bg_cache_key = None
        self._scatter_bg_analysis = None
        self._scatter_tag_scroll = 0
        self._scatter_brush_active = False
        self._scatter_forbidden_cells = set()
        self._scatter_forbidden_dirty = False
        self._scatter_seed_editing = False

    # ── zone vietate manuali: persistenza + brush ─────────────────────────
    def _scatter_forbidden_file(self):
        """Path del file per-scena delle celle vietate (None se nessuna scena)."""
        if not self.scene_path:
            return None
        return self.scene_path / FORBIDDEN_CELLS_FILENAME

    def _scatter_cell_px(self) -> int:
        """Dimensione cella della griglia scatter (coerente con l'engine)."""
        from editor.tools.scatter_engine import CELL_PX
        if self._scatter_bg_analysis is not None:
            return int(self._scatter_bg_analysis.cell_px)
        return CELL_PX

    def _scatter_forbidden_load(self):
        """Carica le celle vietate della scena corrente (se il file esiste).

        Se le dimensioni BG registrate non combaciano col BG attuale (sfondo
        sostituito), la maschera viene scartata con un warning.
        """
        self._scatter_forbidden_cells = set()
        self._scatter_forbidden_dirty = False
        fpath = self._scatter_forbidden_file()
        if fpath is None or not fpath.exists():
            return
        try:
            import json
            data = json.loads(fpath.read_text(encoding="utf-8"))
            bg = getattr(self, "bg_surf", None)
            if bg is not None:
                bw, bh = bg.get_size()
                if data.get("bg_w") != bw or data.get("bg_h") != bh:
                    log.warning(f"[SCATTER] {FORBIDDEN_CELLS_FILENAME}: dimensioni BG "
                                f"diverse ({data.get('bg_w')}x{data.get('bg_h')} vs "
                                f"{bw}x{bh}), maschera scartata")
                    self._scatter_status_msg = "Zone vietate scartate: sfondo cambiato"
                    self._scatter_status_color = WARN_C
                    return
            self._scatter_forbidden_cells = {
                (int(c[0]), int(c[1])) for c in data.get("cells", [])
                if isinstance(c, (list, tuple)) and len(c) == 2
            }
            if self._scatter_forbidden_cells:
                log.info(f"[SCATTER] caricate {len(self._scatter_forbidden_cells)} "
                         f"celle vietate da {fpath.name}")
        except Exception as e:
            log.warning(f"[SCATTER] load zone vietate fallito: {e}")

    def _scatter_forbidden_save(self):
        """Salva le celle vietate su disco (solo se modificate)."""
        if not getattr(self, "_scatter_forbidden_dirty", False):
            return
        fpath = self._scatter_forbidden_file()
        if fpath is None:
            return
        try:
            from engine.utils import safe_write_json, safe_delete
            if not self._scatter_forbidden_cells and fpath.exists():
                # Maschera svuotata: rimuovi il file (via cestino editor)
                safe_delete(fpath)
                self._scatter_forbidden_dirty = False
                return
            bg = getattr(self, "bg_surf", None)
            bw, bh = bg.get_size() if bg is not None else (0, 0)
            payload = {
                "version": FORBIDDEN_CELLS_VERSION,
                "bg_w": bw, "bg_h": bh,
                "cell_px": self._scatter_cell_px(),
                "cells": sorted([list(c) for c in self._scatter_forbidden_cells]),
            }
            safe_write_json(fpath, payload)
            self._scatter_forbidden_dirty = False
            log.info(f"[SCATTER] salvate {len(self._scatter_forbidden_cells)} "
                     f"celle vietate in {fpath.name}")
        except Exception as e:
            log.warning(f"[SCATTER] save zone vietate fallito: {e}")

    def _scatter_brush_paint_at(self, mx, my):
        """Dipinge/cancella il blocco di celle attorno al punto schermo (mx, my)."""
        bg = getattr(self, "bg_surf", None)
        if bg is None:
            return
        rx, ry = self._s2r(mx, my)
        bw, bh = bg.get_size()
        if not (0 <= rx < bw and 0 <= ry < bh):
            return
        cpx = self._scatter_cell_px()
        cell_w = max(1, bw // cpx)
        cell_h = max(1, bh // cpx)
        ccx = int(rx // cpx)
        ccy = int(ry // cpx)
        r = BRUSH_RADIUS_CELLS
        changed = False
        for dy in range(-r, r + 1):
            for dx in range(-r, r + 1):
                tx, ty = ccx + dx, ccy + dy
                if not (0 <= tx < cell_w and 0 <= ty < cell_h):
                    continue
                if self._scatter_brush_tool == "paint":
                    if (tx, ty) not in self._scatter_forbidden_cells:
                        self._scatter_forbidden_cells.add((tx, ty))
                        changed = True
                else:
                    if (tx, ty) in self._scatter_forbidden_cells:
                        self._scatter_forbidden_cells.discard((tx, ty))
                        changed = True
        if changed:
            self._scatter_forbidden_dirty = True
            # I ghost calcolati con la maschera vecchia non sono piu' validi
            self._scatter_ghosts = []

    def _scatter_brush_motion(self, mx, my):
        """Drag-paint: chiamato da input_handlers su MOUSEMOTION con tasto premuto."""
        if not self._scatter_brush_active:
            return
        # Non dipingere sopra la toolbar del brush
        tb = self._scatter_hitboxes.get("brush_toolbar")
        if tb is not None and _in_rect((mx, my), tb):
            return
        self._scatter_brush_paint_at(mx, my)

    def _scatter_brush_exit(self):
        """Esce dal brush mode tornando al modal, salvando la maschera."""
        self._scatter_brush_active = False
        self._scatter_forbidden_save()
        n = len(self._scatter_forbidden_cells)
        self._scatter_status_msg = f"Zone vietate: {n} celle"
        self._scatter_status_color = OK_C if n else TXT_DIM

    # ── debug overlay (heatmap QA) ────────────────────────────────────────
    def _scatter_debug_cycle(self):
        """Cicla off -> score -> forbidden -> saliency e ricalcola la mappa."""
        modes = ["off", "score", "forbidden", "saliency"]
        try:
            i = modes.index(self._scatter_debug_mode)
        except ValueError:
            i = 0
        self._scatter_debug_mode = modes[(i + 1) % len(modes)]
        self._scatter_debug_map = None
        self._scatter_debug_surf = None
        self._scatter_debug_surf_key = None
        if self._scatter_debug_mode == "off":
            self._scatter_status_msg = "Debug overlay disattivato"
            self._scatter_status_color = TXT_DIM
            return
        if self._scatter_bg_analysis is None:
            self._scatter_status_msg = "Debug: genera prima un'anteprima (serve analisi BG)"
            self._scatter_status_color = WARN_C
            return
        self._scatter_debug_refresh()

    def _scatter_debug_refresh(self):
        """Ricalcola la mappa debug corrente (mode != off, bg analysis presente)."""
        try:
            from editor.tools.scatter_engine import (
                compute_debug_maps, build_forbidden_mask, _get_weights,
            )
            bg_an = self._scatter_bg_analysis
            # Primo oggetto del pool corrente (stile+tag) come riferimento
            analyses = self._scatter_catalog_cache.get(self._scatter_style) or {}
            entries = {c["id"]: c for c in self.catalog
                       if c.get("style", "real") == self._scatter_style}
            obj = None
            for cid, an in analyses.items():
                if cid not in entries:
                    continue
                if self._scatter_tag and self._scatter_tag not in entries[cid].get("tags", []):
                    continue
                obj = an
                break
            weights = _get_weights(self._scatter_difficulty, self._scatter_style)
            forbidden = build_forbidden_mask(bg_an, self._scatter_forbidden_cells)
            maps = compute_debug_maps(bg_an, obj, weights, forbidden,
                                      self._scatter_difficulty)
            self._scatter_debug_map = maps.get(self._scatter_debug_mode)
            ref = f" (rif: {obj.catalog_id})" if obj is not None else ""
            self._scatter_status_msg = f"Debug: {self._scatter_debug_mode}{ref}"
            self._scatter_status_color = ACCENT
        except Exception as e:
            log.warning(f"[SCATTER] debug refresh fallito: {e}")
            self._scatter_debug_map = None

    def _scatter_tier_needs_download(self, status) -> bool:
        """True se la scelta tier richiede un download non ancora fatto."""
        choice = self._scatter_tier_choice
        if choice == "light":
            return not status["tier1_model_present"]
        if choice == "pro":
            return not status["tier2_model_present"]
        if choice == "ultra":
            return not status.get("tier3_model_present", False)
        return False

    def _scatter_tier_badge(self, status):
        """Restituisce (text, color, bg) per il badge a fianco del dropdown tier."""
        choice = self._scatter_tier_choice
        if not status["ort_installed"]:
            return ("NO ONNX", ERR_C, (50, 25, 25))
        if choice == "classic":
            return ("OK", TXT_DIM, (35, 38, 44))
        if choice == "auto":
            if status["has_cuda"]:
                lbl = "GPU CUDA"
            elif status["has_directml"]:
                lbl = "GPU DML"
            else:
                lbl = "CPU"
            return (lbl, ACCENT, (28, 40, 55))
        if choice == "light":
            if not status["tier1_model_present"]:
                return ("SCARICA", WARN_C, (55, 40, 20))
            return ("OK", OK_C, (25, 50, 30))
        if choice == "pro":
            if not status["tier2_model_present"]:
                return ("SCARICA", WARN_C, (55, 40, 20))
            return ("OK", OK_C, (25, 50, 30))
        if choice == "ultra":
            if not status.get("tier3_model_present", False):
                return ("SCARICA", WARN_C, (55, 40, 20))
            return ("OK", OK_C, (25, 50, 30))
        return ("?", TXT_DIM, BTN)

    # ── tier IA ───────────────────────────────────────────────────────────
    def _scatter_get_status(self, refresh: bool = False):
        if self._scatter_status_cache is None or refresh:
            from editor.tools.scatter_models import get_status_summary
            self._scatter_status_cache = get_status_summary(self.base_path)
        return self._scatter_status_cache

    def _scatter_force_tier_int(self):
        """Mappa la scelta UI a force_tier per get_best_model."""
        m = {"auto": None, "classic": 0, "light": 1, "pro": 2, "ultra": 3}
        return m.get(self._scatter_tier_choice, None)

    def _scatter_load_model(self):
        """Carica/sostituisce il modello in base alla scelta tier corrente."""
        import threading
        from editor.tools.scatter_models import get_best_model
        if getattr(self, "_scatter_model_lock", None) is None:
            self._scatter_model_lock = threading.Lock()
        # Serializza il thread di preload e il caricamento on-demand: evita due build
        # ONNX concorrenti e l'assegnazione incoerente di self._scatter_model.
        with self._scatter_model_lock:
            force = self._scatter_force_tier_int()
            try:
                self._scatter_model = get_best_model(self.base_path,
                                                      force_tier=force,
                                                      quick_benchmark=False)
                self._scatter_model_tier_active = self._scatter_model.tier
                log.info(f"[SCATTER] Modello attivo: tier={self._scatter_model.tier} ({self._scatter_model.name})")
            except FileNotFoundError as e:
                # Modello richiesto manca: notifica + fallback
                self._scatter_status_msg = f"Modello mancante: scaricalo dal pulsante"
                self._scatter_status_color = WARN_C
                self._scatter_model = None
                self._scatter_model_tier_active = 0
            except Exception as e:
                log.exception("Caricamento modello fallito")
                self._scatter_status_msg = f"Errore modello: {e}"
                self._scatter_status_color = ERR_C
                self._scatter_model = None
                self._scatter_model_tier_active = 0

    def _scatter_download_model(self, tier: int):
        """Scarica il modello del tier richiesto (blocking, con status messages).

        Per tier 3 ULTRA scarica i 3 modelli necessari in sequenza.
        """
        from editor.tools.download_models import download_model, download_ultra, model_meta

        last_pct = -1
        def cb_single(d, total, label):
            nonlocal last_pct
            if total > 0:
                pct = int(d / total * 100)
                if pct != last_pct and pct % 5 == 0:
                    last_pct = pct
                    self._scatter_status_msg = f"Download {label}: {pct}% ({d/1024/1024:.0f}/{total/1024/1024:.0f} MB)"
                    try:
                        w, h = self.screen.get_size()
                        self._r_scatter_modal(w, h); pygame.display.flip()
                    except Exception:
                        pass

        if tier == 3:
            # ULTRA = 3 modelli
            self._scatter_status_msg = "Scarico ULTRA (3 modelli, ~267MB totali)..."
            self._scatter_status_color = ACCENT
            try:
                w, h = self.screen.get_size()
                self._r_scatter_modal(w, h); pygame.display.flip()
            except Exception:
                pass

            def cb_multi(name, d, total):
                cb_single(d, total, name)

            ok = download_ultra(self.base_path, progress_cb=cb_multi)
            if ok:
                self._scatter_status_msg = "ULTRA pronto: depth + semantic + CLIP"
                self._scatter_status_color = OK_C
            else:
                self._scatter_status_msg = "Download ULTRA fallito (vedi log)"
                self._scatter_status_color = ERR_C
            self._scatter_get_status(refresh=True)
            return

        meta = model_meta(tier)
        self._scatter_status_msg = f"Scarico {meta['display_name']} (~{meta['size_mb_approx']} MB)..."
        self._scatter_status_color = ACCENT
        w, h = self.screen.get_size()
        self._r_scatter_modal(w, h); pygame.display.flip()

        def cb(d, total):
            cb_single(d, total, meta['display_name'])

        path = download_model(tier, self.base_path, progress_cb=cb)
        if path:
            self._scatter_status_msg = f"Modello scaricato. Riselezionalo dal dropdown."
            self._scatter_status_color = OK_C
            self._scatter_get_status(refresh=True)
        else:
            self._scatter_status_msg = "Download fallito (vedi log)"
            self._scatter_status_color = ERR_C

    # ── tag pool calculator ──────────────────────────────────────────────
    def _scatter_available_tags(self):
        """Lista [(tag, count)] presenti nel catalogo dello stile selezionato.

        Esclude la blacklist di tag tecnici (dimensione/colore). Ordinata per
        frequenza decrescente. Cache per stile.
        """
        cached = self._scatter_tags_cache.get(self._scatter_style)
        if cached is not None:
            return cached
        counter = Counter()
        for c in self.catalog:
            if c.get("style", "real") != self._scatter_style:
                continue
            for t in c.get("tags", []):
                if t in _TAG_BLACKLIST:
                    continue
                counter[t] += 1
        out = counter.most_common(60)
        self._scatter_tags_cache[self._scatter_style] = out
        return out

    def _scatter_filtered_count(self):
        """Quanti oggetti del catalogo passano il filtro stile+tag corrente."""
        n = 0
        for c in self.catalog:
            if c.get("style", "real") != self._scatter_style:
                continue
            if self._scatter_tag and self._scatter_tag not in c.get("tags", []):
                continue
            n += 1
        return n

    # ── algoritmo: genera anteprima (worker thread, U1) ───────────────────
    def _scatter_pick_seed(self, reroll: bool) -> int:
        """Seed della run (U2). RIPESCA: sempre nuovo random. GENERA: campo
        numerico se compilato, altrimenti ultimo seed se lucchetto attivo,
        altrimenti random. Il seed usato finisce sempre nel campo."""
        import random as _random
        seed = None
        if not reroll:
            txt = self._scatter_seed_text.strip()
            if txt:
                try:
                    seed = int(txt)
                except ValueError:
                    seed = None
            if seed is None and self._scatter_seed_locked and self._scatter_last_seed:
                seed = self._scatter_last_seed
        if seed is None:
            seed = _random.randint(1, 999999)
        self._scatter_last_seed = seed
        self._scatter_seed_text = str(seed)
        return seed

    def _scatter_run(self, reroll: bool = False):
        """Avvia la pipeline in un worker thread: la UI resta reattiva, con
        progress (fase + barra) e ANNULLA. Risultato consumato dal render
        (_scatter_consume_result)."""
        import threading

        if self._scatter_busy:
            return
        if not self.catalog:
            self._scatter_status_msg = "Catalogo vuoto"
            self._scatter_status_color = ERR_C
            return
        if self._scatter_filtered_count() == 0:
            self._scatter_status_msg = "Nessun oggetto disponibile con questi filtri"
            self._scatter_status_color = WARN_C
            return

        seed = self._scatter_pick_seed(reroll)
        self._scatter_busy = True
        self._scatter_ghosts = []
        self._scatter_result = None
        self._scatter_progress = ("Preparazione", 0, int(self._scatter_count))
        self._scatter_status_msg = f"Elaborazione (seed {seed})..."
        self._scatter_status_color = ACCENT
        self._scatter_cancel_event = threading.Event()
        self._scatter_run_token += 1
        token = self._scatter_run_token
        cancel_ev = self._scatter_cancel_event

        # Snapshot dei parametri e COPIA del BG sul main thread: il worker non
        # tocca surface condivise col render (pygame non e' thread-safe).
        params = {
            "style": self._scatter_style,
            "tag": self._scatter_tag,
            "count": int(self._scatter_count),
            "difficulty": self._scatter_difficulty,
            "layers": [lid for lid, v in self._scatter_layers.items() if v]
                      or list(self._scatter_layers.keys()),
            "forbidden_cells": set(self._scatter_forbidden_cells),
            "existing": self._scatter_existing_bboxes(),
            "scene_key": str(self.scene_path),
            "seed": seed,
            "bg_copy": self.bg_surf.copy(),
        }

        t = threading.Thread(target=self._scatter_worker_main,
                             args=(params, token, cancel_ev),
                             daemon=True, name="ScatterRun")
        t.start()

    def _scatter_worker_main(self, params: dict, token: int, cancel_ev):
        """Corpo del worker: NIENTE accessi a self.screen o repaint qui."""
        from editor.tools.scatter_engine import (
            ScatterCancelled, analyze_background, precompute_catalog,
            build_forbidden_mask,
        )
        from editor.tools.scatter_validate import run_scatter_with_repair

        def _phase(label, done=0, total=None):
            if token == self._scatter_run_token:
                self._scatter_progress = (label, done,
                                          total or params["count"])

        try:
            # Carica modello secondo la scelta tier (lazy/cached, lock interno)
            if self._scatter_model is None:
                _phase("Carico modello IA")
                self._scatter_load_model()

            # YuNet face detector (~0.3MB): tentativo silente una volta per
            # sessione; fallback Haar senza bloccare nulla.
            if not getattr(self, "_scatter_yunet_tried", False):
                self._scatter_yunet_tried = True
                try:
                    from editor.tools.scatter_models import yunet_path
                    if not yunet_path(self.base_path).exists():
                        from editor.tools.download_models import download_face_model
                        if download_face_model(self.base_path) is None:
                            log.info("[SCATTER] YuNet non scaricato, uso Haar fallback")
                except Exception as e:
                    log.debug(f"[SCATTER] download YuNet fallito: {e}")

            if cancel_ev.is_set():
                raise ScatterCancelled()

            # Invalida cache BG anche se il tier attivo e' cambiato
            bg_cache_invalid = (
                self._scatter_bg_cache_key != params["scene_key"]
                or self._scatter_bg_analysis is None
                or (self._scatter_bg_analysis is not None
                    and self._scatter_bg_analysis.model_tier != self._scatter_model_tier_active)
            )
            if bg_cache_invalid:
                _phase("Analisi background")
                bg_an = analyze_background(
                    params["bg_copy"], ia_model=self._scatter_model,
                    base_path=self.base_path, use_cache=True,
                )
                self._scatter_bg_analysis = bg_an
                self._scatter_bg_cache_key = params["scene_key"]

            if cancel_ev.is_set():
                raise ScatterCancelled()

            # Se ULTRA, passa anche il clip_model per pre-compute embedding
            clip_for_catalog = None
            if self._scatter_model is not None and self._scatter_model.tier == 3:
                clip_for_catalog = getattr(self._scatter_model, "clip", None)

            cache_key = (params["style"], clip_for_catalog is not None)
            if cache_key not in self._scatter_catalog_cache:
                _phase(f"Pre-calcolo catalogo {params['style']}")
                analyses = precompute_catalog(
                    self.catalog, params["style"], self.base_path,
                    clip_model=clip_for_catalog,
                )
                self._scatter_catalog_cache[cache_key] = analyses
            self._scatter_catalog_cache[params["style"]] = \
                self._scatter_catalog_cache[cache_key]
            analyses = self._scatter_catalog_cache[params["style"]]
            if not analyses:
                raise RuntimeError(
                    f"Nessun oggetto per stile '{params['style']}'")

            entries = {c["id"]: c for c in self.catalog
                       if c.get("style", "real") == params["style"]}
            forbidden = build_forbidden_mask(
                self._scatter_bg_analysis, params["forbidden_cells"])

            _phase("Piazzamento", 0)

            def _cb(done, total):
                _phase("Piazzamento", done, total)

            # Best-of-M render-in-the-loop + repair dei fail (S2 + S6). Il
            # render_ctx usa la COPIA del BG: nessuna surface condivisa.
            render_ctx = {"bg_surface": params["bg_copy"],
                          "game_path": self.game_path,
                          "repo_root": self.base_path}
            kept, results, report = run_scatter_with_repair(
                self._scatter_bg_analysis, analyses, entries,
                bg_surface=params["bg_copy"],
                game_path=self.game_path, repo_root=self.base_path,
                count=params["count"],
                difficulty=params["difficulty"],
                style=params["style"],
                tag_filter=params["tag"],
                existing_bboxes=params["existing"],
                seed=params["seed"],
                allowed_layers=params["layers"],
                forbidden_mask=forbidden,
                render_ctx=render_ctx,
                progress_cb=_cb,
                cancel_event=cancel_ev,
            )
            if token == self._scatter_run_token:
                self._scatter_result = {"ghosts": kept, "report": report,
                                        "seed": params["seed"],
                                        "cancelled": False, "error": None}
        except ScatterCancelled:
            if token == self._scatter_run_token:
                self._scatter_result = {"ghosts": [], "report": None,
                                        "seed": params["seed"],
                                        "cancelled": True, "error": None}
        except Exception as e:
            log.exception("Scatter worker failed")
            if token == self._scatter_run_token:
                self._scatter_result = {"ghosts": [], "report": None,
                                        "seed": params["seed"],
                                        "cancelled": False, "error": str(e)}

    def _scatter_consume_result(self):
        """Consuma il payload del worker (chiamata dal render, main thread)."""
        res = self._scatter_result
        if res is None:
            return
        self._scatter_result = None
        self._scatter_busy = False
        self._scatter_progress = None
        self._scatter_report = res.get("report")
        if res.get("cancelled"):
            self._scatter_status_msg = "Elaborazione annullata"
            self._scatter_status_color = WARN_C
            return
        if res.get("error"):
            self._scatter_status_msg = f"Errore: {res['error']}"
            self._scatter_status_color = ERR_C
            return
        placed = res.get("ghosts") or []
        self._scatter_ghosts = placed
        report = res.get("report") or {}
        if placed:
            avg_vs = sum(p.visibility_score for p in placed) / len(placed)
            msg = (f"{len(placed)}/{report.get('requested', len(placed))} pronti"
                   f" | seed {res.get('seed')}"
                   f" | nascondiglio medio {avg_vs:.2f}")
            if report.get("dropped_fail"):
                msg += f" | {report['dropped_fail']} rimpiazzati (in evidenza)"
            if report.get("warn"):
                msg += f" | {report['warn']} ben visibili"
            self._scatter_status_msg = msg
            self._scatter_status_color = OK_C
        else:
            self._scatter_status_msg = "Nessun oggetto piazzato (pool/spazio insufficiente)"
            self._scatter_status_color = WARN_C

    def _scatter_apply(self):
        """Aggiunge i ghost alla scena come oggetti reali."""
        if not self._scatter_ghosts:
            self._scatter_status_msg = "Niente da applicare. Genera prima l'anteprima"
            self._scatter_status_color = WARN_C
            return
        self._push_undo()
        added = 0
        for g in self._scatter_ghosts:
            entry = {
                "catalog_id": g.catalog_id,
                "x": round(g.x), "y": round(g.y),
                "detection_type": g.detection_type,
                "scale": round(g.scale, 2),
                "rotation": round(g.rotation, 1),
                "flip_x": g.flip_x, "flip_y": g.flip_y,
                "alpha": int(g.alpha),
                "layer": g.layer,
                "is_goal": True,
                "always_show": False,
                "hint_delay": 30,
            }
            # USA g.width e g.height direttamente (proporzionati all'aspect PNG)
            # invece di forzare 2*radius (che produrrebbe quadrati distorti).
            entry["width"]  = round(g.width)
            entry["height"] = round(g.height)
            if g.detection_type == "circle":
                entry["radius"] = round(g.radius)
            if g.color_filter != (255, 255, 255):
                entry["color_filter"] = list(g.color_filter)
            self.scene_data.setdefault("objects", []).append(entry)
            added += 1
        self.scene_dirty = True
        self._mark_dirty()
        self._status(f"Scatter applicato: {added} oggetti aggiunti", OK_C, 3)
        self._scatter_ghosts = []
        self._scatter_modal_open = False
        self._scatter_forbidden_save()

    def _scatter_existing_bboxes(self):
        out = []
        for o in self.scene_data.get("objects", []):
            dt = o.get("detection_type", "circle")
            scale = o.get("scale", 1.0)
            x, y = o.get("x", 0), o.get("y", 0)
            if dt == "circle":
                r = o.get("radius", 30) * scale
                out.append((x - r, y - r, x + r, y + r))
            else:
                w = o.get("width", 60) * scale
                h = o.get("height", 60) * scale
                out.append((x, y, x + w, y + h))
        return out

    # ── render ────────────────────────────────────────────────────────────
    def _r_scatter_modal(self, w, h):
        if not self._scatter_modal_open:
            return

        # Risultati del worker (U1): consumati sul main thread, ogni frame.
        self._scatter_consume_result()

        # Brush mode: niente panel ne' overlay scuro, solo toolbar compatta
        # (il canvas resta visibile per dipingere le zone vietate).
        if self._scatter_brush_active:
            self._r_scatter_brush_toolbar(w, h)
            return

        # Overlay scuro
        dim = pygame.Surface((w, h), pygame.SRCALPHA)
        dim.fill((0, 0, 0, 170))
        self.screen.blit(dim, (0, 0))

        # Panel piu' alto (riga checkbox layer + zone vietate + seed)
        pw, ph = 520, 800
        px, py = (w - pw) // 2, (h - ph) // 2
        panel_r = pygame.Rect(px, py, pw, ph)
        self._scatter_panel_rect = panel_r
        _rect(self.screen, (24, 26, 32), panel_r, radius=10)
        _rect(self.screen, ACCENT, panel_r, 2, radius=10)

        mx, my = pygame.mouse.get_pos()
        self._scatter_hitboxes = {}

        # ─── HEADER ────────────────────────────────────────────────────
        hdr_h = 56
        hdr_r = pygame.Rect(px, py, pw, hdr_h)
        _rect(self.screen, (32, 36, 46), hdr_r, radius=10)
        # taglio sotto: linea sotto header
        pygame.draw.line(self.screen, ACCENT, (px + 1, py + hdr_h), (px + pw - 1, py + hdr_h))
        _draw_text(self.screen, "AUTO-SCATTER INTELLIGENTE", "md", TXT_HI, px + 20, py + 12)
        _draw_text(self.screen, "Distribuzione con camuffamento basato su edge + saliency + colore",
                   "xs", TXT_DIM, px + 20, py + 34, pw - 80)

        # Bottone DEBUG (heatmap QA) a sinistra della X
        dbg_lbls = {"off": "DEBUG: OFF", "score": "DEBUG: SCORE",
                    "forbidden": "DEBUG: VIETATE", "saliency": "DEBUG: SALIENCY"}
        dbg_r = pygame.Rect(px + pw - 36 - 128, py + 14, 118, 24)
        dbg_on = self._scatter_debug_mode != "off"
        hov_dbg = _in_rect((mx, my), dbg_r)
        _rect(self.screen, (30, 45, 60) if (dbg_on or hov_dbg) else (35, 38, 44), dbg_r, radius=4)
        _rect(self.screen, ACCENT if dbg_on else BORDER, dbg_r, 1, radius=4)
        dts = _txt(dbg_lbls.get(self._scatter_debug_mode, "DEBUG"), "xs",
                   ACCENT if dbg_on else TXT_DIM)
        self.screen.blit(dts, (dbg_r.centerx - dts.get_width()//2,
                               dbg_r.centery - dts.get_height()//2))
        self._scatter_hitboxes["debug_btn"] = dbg_r

        close_r = pygame.Rect(px + pw - 36, py + 14, 24, 24)
        hov_close = _in_rect((mx, my), close_r)
        _rect(self.screen, (60, 30, 30) if hov_close else (40, 25, 25), close_r, radius=4)
        _rect(self.screen, ERR_C if hov_close else BORDER, close_r, 1, radius=4)
        xs = _txt("X", "sm", ERR_C if hov_close else TXT_DIM)
        self.screen.blit(xs, (close_r.centerx - xs.get_width()//2, close_r.centery - xs.get_height()//2 - 1))
        self._scatter_hitboxes["close"] = close_r

        # ─── BODY ──────────────────────────────────────────────────────
        y = py + hdr_h + 18
        LBL_X = px + 20
        CTRL_X = px + 160
        CTRL_W = pw - 180
        ROW_H = 40

        # STILE
        _draw_text(self.screen, "Stile catalogo", "sm", TXT_DIM, LBL_X, y + 8)
        style_r = pygame.Rect(CTRL_X, y, CTRL_W, 30)
        is_style_open = self._scatter_drop_open == "style"
        hov = _in_rect((mx, my), style_r)
        _rect(self.screen, BTN_AC if is_style_open else (BTN_HO if hov else BTN), style_r, radius=4)
        _rect(self.screen, ACCENT if (is_style_open or hov) else BORDER, style_r, 1, radius=4)
        _draw_text(self.screen, self._scatter_style.upper(), "sm", TXT_HI, style_r.x + 12, style_r.y + 8, style_r.w - 30)
        cx, cy = style_r.right - 16, style_r.centery
        pygame.draw.polygon(self.screen, ACCENT, [(cx-5, cy-3), (cx+5, cy-3), (cx, cy+3)])
        self._scatter_hitboxes["style_btn"] = style_r
        y += ROW_H

        # TAG TEMA
        tags = self._scatter_available_tags()
        _draw_text(self.screen, "Filtro tag tema", "sm", TXT_DIM, LBL_X, y + 8)
        tag_r = pygame.Rect(CTRL_X, y, CTRL_W, 30)
        is_tag_open = self._scatter_drop_open == "tag"
        hov = _in_rect((mx, my), tag_r)
        _rect(self.screen, BTN_AC if is_tag_open else (BTN_HO if hov else BTN), tag_r, radius=4)
        _rect(self.screen, ACCENT if (is_tag_open or hov) else BORDER, tag_r, 1, radius=4)
        tag_lbl = self._scatter_tag.upper() if self._scatter_tag else f"(TUTTI - {len(tags)} disponibili)"
        _draw_text(self.screen, tag_lbl, "sm", TXT_HI, tag_r.x + 12, tag_r.y + 8, tag_r.w - 30)
        cx, cy = tag_r.right - 16, tag_r.centery
        pygame.draw.polygon(self.screen, ACCENT, [(cx-5, cy-3), (cx+5, cy-3), (cx, cy+3)])
        self._scatter_hitboxes["tag_btn"] = tag_r
        y += ROW_H

        # MODALITA IA (TIER)
        status = self._scatter_get_status()
        _draw_text(self.screen, "Modalita IA", "sm", TXT_DIM, LBL_X, y + 8)
        # Layout: dropdown su sinistra (largo 60%), badge stato a destra
        tier_dd_w = int(CTRL_W * 0.62)
        tier_r = pygame.Rect(CTRL_X, y, tier_dd_w, 30)
        is_tier_open = self._scatter_drop_open == "tier"
        hov = _in_rect((mx, my), tier_r)
        _rect(self.screen, BTN_AC if is_tier_open else (BTN_HO if hov else BTN), tier_r, radius=4)
        _rect(self.screen, ACCENT if (is_tier_open or hov) else BORDER, tier_r, 1, radius=4)
        tier_label_map = {
            "auto": "AUTO (rileva GPU)",
            "classic": "CLASSICO (no IA)",
            "light": "LIGHT (Depth)",
            "pro": "PRO (Depth+Normals)",
            "ultra": "ULTRA (Depth+Sem+CLIP)",
        }
        _draw_text(self.screen, tier_label_map.get(self._scatter_tier_choice, "?"),
                   "sm", TXT_HI, tier_r.x + 12, tier_r.y + 8, tier_r.w - 30)
        cx, cy = tier_r.right - 16, tier_r.centery
        pygame.draw.polygon(self.screen, ACCENT, [(cx-5, cy-3), (cx+5, cy-3), (cx, cy+3)])
        self._scatter_hitboxes["tier_btn"] = tier_r

        # Badge stato (a destra del dropdown tier)
        active_tier = self._scatter_model_tier_active
        badge_x = tier_r.right + 8
        badge_w = CTRL_W - tier_dd_w - 8
        badge_r = pygame.Rect(badge_x, y, badge_w, 30)
        badge_text, badge_color, badge_bg = self._scatter_tier_badge(status)
        _rect(self.screen, badge_bg, badge_r, radius=4)
        _rect(self.screen, badge_color, badge_r, 1, radius=4)
        bt = _txt(badge_text, "xs", badge_color)
        self.screen.blit(bt, (badge_r.centerx - bt.get_width()//2, badge_r.centery - bt.get_height()//2))

        # Se la scelta richiede download, hitbox sul badge per scaricare
        need_dl = self._scatter_tier_needs_download(status)
        if need_dl:
            self._scatter_hitboxes["download_model"] = badge_r
        y += ROW_H

        # QUANTITA
        _draw_text(self.screen, "Quantita", "sm", TXT_DIM, LBL_X, y + 8)
        cnt_box = pygame.Rect(CTRL_X, y + 4, 56, 24)
        _rect(self.screen, (45, 48, 56), cnt_box, radius=4)
        _rect(self.screen, BORDER, cnt_box, 1, radius=4)
        cnts = _txt(str(int(self._scatter_count)), "sm", TXT_HI)
        self.screen.blit(cnts, (cnt_box.centerx - cnts.get_width()//2, cnt_box.centery - cnts.get_height()//2))
        sl_r = pygame.Rect(CTRL_X + 70, y + 6, CTRL_W - 70, 20)
        _slider(self.screen, sl_r, self._scatter_count, 1, 300)
        self._scatter_hitboxes["count_slider"] = sl_r
        y += ROW_H

        # DIFFICOLTA
        _draw_text(self.screen, "Difficolta", "sm", TXT_DIM, LBL_X, y + 8)
        diff_opts = [
            ("easy", "FACILE", "Posizionamento evidente"),
            ("medium", "MEDIO", "Bilanciato"),
            ("hard", "DIFFICILE", "Camuffamento chirurgico"),
        ]
        btn_gap = 4
        btn_w = (CTRL_W - btn_gap * 2) // 3
        for i, (val, lbl, _hint) in enumerate(diff_opts):
            br = pygame.Rect(CTRL_X + i * (btn_w + btn_gap), y, btn_w, 30)
            active = (self._scatter_difficulty == val)
            hov = _in_rect((mx, my), br)
            _rect(self.screen, BTN_AC if active else (BTN_HO if hov else BTN), br, radius=4)
            _rect(self.screen, ACCENT if active else BORDER, br, 2 if (hov or active) else 1, radius=4)
            ts = _txt(lbl, "xs", TXT_HI if active else TXT)
            self.screen.blit(ts, (br.centerx - ts.get_width()//2, br.centery - ts.get_height()//2))
            self._scatter_hitboxes[f"diff_{val}"] = br
        y += ROW_H + 4

        # Hint per difficolta corrente (sotto i bottoni)
        hint = next(d[2] for d in diff_opts if d[0] == self._scatter_difficulty)
        _draw_text(self.screen, hint, "xs", TXT_DIM, CTRL_X, y, CTRL_W)
        y += 22

        # ── SEED (U2): riproducibilita' ────────────────────────────────
        _draw_text(self.screen, "Seed", "sm", TXT_DIM, LBL_X, y + 8)
        seed_box = pygame.Rect(CTRL_X, y + 2, 130, 26)
        editing = self._scatter_seed_editing
        _rect(self.screen, (50, 54, 64) if editing else (45, 48, 56),
              seed_box, radius=4)
        _rect(self.screen, ACCENT if editing else BORDER, seed_box, 1, radius=4)
        seed_shown = self._scatter_seed_text or "(random)"
        seed_col = TXT_HI if self._scatter_seed_text else TXT_DIM
        stxt = _txt(seed_shown + ("_" if editing else ""), "sm", seed_col)
        self.screen.blit(stxt, (seed_box.x + 8,
                                seed_box.centery - stxt.get_height() // 2))
        self._scatter_hitboxes["seed_box"] = seed_box
        # Lucchetto: GENERA riusa lo stesso seed (per iterare i parametri a
        # parita' di estrazione). RIPESCA forza comunque un seed nuovo.
        lock_r = pygame.Rect(seed_box.right + 8, y + 2, 110, 26)
        locked = self._scatter_seed_locked
        hov_lk = _in_rect((mx, my), lock_r)
        _rect(self.screen, (30, 50, 40) if locked else (BTN_HO if hov_lk else BTN),
              lock_r, radius=4)
        _rect(self.screen, OK_C if locked else BORDER, lock_r, 1, radius=4)
        lk = _txt("SEED FISSO" if locked else "SEED LIBERO", "xs",
                  TXT_HI if locked else TXT_DIM)
        self.screen.blit(lk, (lock_r.centerx - lk.get_width() // 2,
                              lock_r.centery - lk.get_height() // 2))
        self._scatter_hitboxes["seed_lock"] = lock_r
        if self._scatter_last_seed is not None:
            _draw_text(self.screen, f"ultimo: {self._scatter_last_seed}", "xs",
                       TXT_DIM, lock_r.right + 10, y + 8,
                       CTRL_X + CTRL_W - lock_r.right - 12)
        y += ROW_H

        # ── LAYER CHECKBOX ─────────────────────────────────────────────
        _draw_text(self.screen, "Distribuisci su layer", "sm", TXT_DIM, LBL_X, y + 8)
        # 3 checkbox: LOW / MID / HIGH
        layer_opts = [
            ("objects_low", "LOW", (160, 110, 80)),
            ("objects_mid", "MID", (110, 160, 110)),
            ("objects_high", "HIGH", (110, 130, 200)),
        ]
        cb_gap = 6
        cb_w = (CTRL_W - cb_gap * 2) // 3
        for i, (lid, lbl, swatch) in enumerate(layer_opts):
            br = pygame.Rect(CTRL_X + i * (cb_w + cb_gap), y, cb_w, 30)
            active = bool(self._scatter_layers.get(lid, True))
            hov = _in_rect((mx, my), br)
            _rect(self.screen, (30, 50, 40) if active else (38, 38, 44), br, radius=4)
            _rect(self.screen, OK_C if active else BORDER, br, 2 if hov else 1, radius=4)
            # Checkbox quadratino
            cb_box = pygame.Rect(br.x + 8, br.centery - 8, 16, 16)
            _rect(self.screen, OK_C if active else (50, 50, 60), cb_box, radius=2)
            _rect(self.screen, BORDER, cb_box, 1, radius=2)
            if active:
                # Tick "X" stile
                pygame.draw.line(self.screen, (10, 30, 10), (cb_box.x + 3, cb_box.y + 8), (cb_box.x + 7, cb_box.y + 12), 2)
                pygame.draw.line(self.screen, (10, 30, 10), (cb_box.x + 7, cb_box.y + 12), (cb_box.x + 13, cb_box.y + 4), 2)
            # Pallino colore layer + label
            pygame.draw.circle(self.screen, swatch, (br.x + 32, br.centery), 5)
            ts = _txt(lbl, "xs", TXT_HI if active else TXT_DIM)
            self.screen.blit(ts, (br.x + 42, br.centery - ts.get_height()//2))
            self._scatter_hitboxes[f"layer_{lid}"] = br
        y += ROW_H + 4

        # ── ZONE VIETATE (brush manuale) ───────────────────────────────
        _draw_text(self.screen, "Zone vietate", "sm", TXT_DIM, LBL_X, y + 8)
        n_forb = len(self._scatter_forbidden_cells)
        gap_z = 6
        zw = (CTRL_W - gap_z) * 2 // 3
        cw_z = CTRL_W - gap_z - zw
        zbrush_r = pygame.Rect(CTRL_X, y, zw, 30)
        zclear_r = pygame.Rect(CTRL_X + zw + gap_z, y, cw_z, 30)
        hov_zb = _in_rect((mx, my), zbrush_r)
        _rect(self.screen, (70, 35, 35) if hov_zb else (55, 28, 28), zbrush_r, radius=4)
        _rect(self.screen, ERR_C if hov_zb else BORDER, zbrush_r, 1, radius=4)
        zlbl = f"DIPINGI ZONE VIETATE ({n_forb})" if n_forb else "DIPINGI ZONE VIETATE"
        ts = _txt(zlbl, "xs", TXT_HI)
        self.screen.blit(ts, (zbrush_r.centerx - ts.get_width()//2,
                              zbrush_r.centery - ts.get_height()//2))
        self._scatter_hitboxes["brush_enter"] = zbrush_r
        hov_zc = _in_rect((mx, my), zclear_r)
        can_clear = n_forb > 0
        _rect(self.screen, (BTN_HO if hov_zc else BTN) if can_clear else (38, 38, 44),
              zclear_r, radius=4)
        _rect(self.screen, BORDER, zclear_r, 1, radius=4)
        ts = _txt("PULISCI", "xs", TXT_HI if can_clear else TXT_DIM)
        self.screen.blit(ts, (zclear_r.centerx - ts.get_width()//2,
                              zclear_r.centery - ts.get_height()//2))
        if can_clear:
            self._scatter_hitboxes["brush_clear"] = zclear_r
        y += ROW_H + 4

        pygame.draw.line(self.screen, BORDER, (px + 16, y), (px + pw - 16, y))
        y += 14

        # ─── INFO BOX ────────────────────────────────────────────────
        info_y = y
        scene_n = len(self.scene_data.get("objects", []))
        ghost_n = len(self._scatter_ghosts)
        filtered_n = self._scatter_filtered_count()
        bg_lbl = "non caricato"
        if getattr(self, "bg_surf", None):
            bw, bh = self.bg_surf.get_size()
            bg_lbl = f"{bw}x{bh} px"

        info_lines = [
            (f"Pool oggetti disponibili: {filtered_n}", OK_C if filtered_n > 0 else ERR_C),
            (f"Scena corrente: {scene_n} oggetti", TXT_DIM),
            (f"Background: {bg_lbl}", TXT_DIM),
        ]
        if ghost_n:
            info_lines.append((f"Anteprima attiva: {ghost_n} ghost", OK_C))
        info_box_h = 18 * len(info_lines) + 12
        info_r = pygame.Rect(px + 16, info_y, pw - 32, info_box_h)
        _rect(self.screen, (30, 32, 38), info_r, radius=4)
        _rect(self.screen, BORDER, info_r, 1, radius=4)
        for i, (txt, col) in enumerate(info_lines):
            _draw_text(self.screen, txt, "xs", col, info_r.x + 12, info_r.y + 8 + i * 18, info_r.w - 20)
        y = info_r.bottom + 16

        # ─── BOTTONI AZIONE ──────────────────────────────────────────
        btn_h = 36
        if self._scatter_busy:
            # U1: barra di progresso (fase + done/total) + bottone ANNULLA.
            prog = self._scatter_progress or ("Elaborazione", 0, 1)
            phase_lbl, done, total = prog
            bar_w = pw - 32 - 110 - 8
            bar_r = pygame.Rect(px + 16, y, bar_w, btn_h)
            _rect(self.screen, (25, 40, 55), bar_r, radius=5)
            frac = max(0.0, min(1.0, done / max(1, total)))
            if frac > 0:
                fill_r = pygame.Rect(bar_r.x, bar_r.y,
                                     max(6, int(bar_r.w * frac)), bar_r.h)
                _rect(self.screen, (35, 90, 130), fill_r, radius=5)
            _rect(self.screen, ACCENT, bar_r, 1, radius=5)
            plbl = f"{phase_lbl}... {done}/{total}" if total > 1 else f"{phase_lbl}..."
            ts = _txt(plbl, "sm", TXT_HI)
            self.screen.blit(ts, (bar_r.centerx - ts.get_width() // 2,
                                  bar_r.centery - ts.get_height() // 2))
            # ANNULLA
            cancel_r = pygame.Rect(bar_r.right + 8, y, 110, btn_h)
            hov_c = _in_rect((mx, my), cancel_r)
            _rect(self.screen, (70, 35, 35) if hov_c else (55, 28, 28),
                  cancel_r, radius=5)
            _rect(self.screen, ERR_C, cancel_r, 2 if hov_c else 1, radius=5)
            ts = _txt("ANNULLA", "sm", TXT_HI)
            self.screen.blit(ts, (cancel_r.centerx - ts.get_width() // 2,
                                  cancel_r.centery - ts.get_height() // 2))
            self._scatter_hitboxes["cancel_run"] = cancel_r
            y += btn_h + 8
        else:
            gen_disabled = filtered_n == 0
            gen_r = pygame.Rect(px + 16, y, pw - 32, btn_h)
            hov = _in_rect((mx, my), gen_r) and not gen_disabled
            if gen_disabled:
                bg_c, border_c, txt_c = (40, 40, 44), TXT_DIM, TXT_DIM
            elif hov:
                bg_c, border_c, txt_c = (40, 80, 110), ACCENT, TXT_HI
            else:
                bg_c, border_c, txt_c = (30, 60, 85), ACCENT, TXT_HI
            _rect(self.screen, bg_c, gen_r, radius=5)
            _rect(self.screen, border_c, gen_r, 2 if hov else 1, radius=5)
            ts = _txt("GENERA ANTEPRIMA", "sm", txt_c)
            self.screen.blit(ts, (gen_r.centerx - ts.get_width()//2, gen_r.centery - ts.get_height()//2))
            if not gen_disabled:
                self._scatter_hitboxes["generate"] = gen_r
            y += btn_h + 8

        if ghost_n > 0 and not self._scatter_busy:
            gap = 8
            half = (pw - 32 - gap) // 2
            rr_r = pygame.Rect(px + 16, y, half, btn_h)
            ap_r = pygame.Rect(px + 16 + half + gap, y, half, btn_h)
            hov_rr = _in_rect((mx, my), rr_r)
            hov_ap = _in_rect((mx, my), ap_r)
            # Ripesca
            _rect(self.screen, (60, 48, 24) if hov_rr else (45, 36, 18), rr_r, radius=5)
            _rect(self.screen, WARN_C, rr_r, 2 if hov_rr else 1, radius=5)
            ts = _txt("RIPESCA", "sm", TXT_HI)
            self.screen.blit(ts, (rr_r.centerx - ts.get_width()//2, rr_r.centery - ts.get_height()//2))
            self._scatter_hitboxes["reroll"] = rr_r
            # Applica
            _rect(self.screen, (30, 90, 45) if hov_ap else (25, 70, 35), ap_r, radius=5)
            _rect(self.screen, OK_C, ap_r, 2 if hov_ap else 1, radius=5)
            ts = _txt("APPLICA ALLA SCENA", "sm", TXT_HI)
            self.screen.blit(ts, (ap_r.centerx - ts.get_width()//2, ap_r.centery - ts.get_height()//2))
            self._scatter_hitboxes["apply"] = ap_r
            y += btn_h + 8

        # ─── STATUS BAR ──────────────────────────────────────────────
        status_y = py + ph - 38
        pygame.draw.line(self.screen, BORDER, (px + 12, status_y), (px + pw - 12, status_y))
        # Dot colorato + testo
        dot_r = pygame.Rect(px + 18, status_y + 13, 8, 8)
        pygame.draw.circle(self.screen, self._scatter_status_color, dot_r.center, 5)
        _draw_text(self.screen, self._scatter_status_msg, "xs", self._scatter_status_color,
                   px + 32, status_y + 12, pw - 48)

        # ─── DROPDOWN OVERLAY (sempre per ultimi) ─────────────────────
        if self._scatter_drop_open == "style":
            self._r_scatter_dropdown_style(px, py, pw, ph)
        elif self._scatter_drop_open == "tag":
            self._r_scatter_dropdown_tag(px, py, pw, ph, tags)
        elif self._scatter_drop_open == "tier":
            self._r_scatter_dropdown_tier(px, py, pw, ph, status)

    def _r_scatter_brush_toolbar(self, w, h):
        """Toolbar compatta top-center in brush mode (canvas visibile sotto)."""
        self._scatter_hitboxes = {}
        tb_w, tb_h = 460, 46
        tx = (w - tb_w) // 2
        ty = 52  # sotto la top bar
        tb_r = pygame.Rect(tx, ty, tb_w, tb_h)
        _rect(self.screen, (24, 26, 32), tb_r, radius=8)
        _rect(self.screen, ERR_C, tb_r, 2, radius=8)
        self._scatter_hitboxes["brush_toolbar"] = tb_r

        mx, my = pygame.mouse.get_pos()
        n_forb = len(self._scatter_forbidden_cells)
        bx = tx + 10
        bw, bh, bgap = 90, 30, 8
        by = ty + 8
        buttons = [
            ("brush_paint", "PITTURA", self._scatter_brush_tool == "paint"),
            ("brush_erase", "GOMMA", self._scatter_brush_tool == "erase"),
            ("brush_clear", f"PULISCI ({n_forb})", False),
            ("brush_done", "FATTO", False),
        ]
        for key, lbl, active in buttons:
            br = pygame.Rect(bx, by, bw, bh)
            hov = _in_rect((mx, my), br)
            if key == "brush_done":
                _rect(self.screen, (30, 90, 45) if hov else (25, 70, 35), br, radius=4)
                _rect(self.screen, OK_C, br, 2 if hov else 1, radius=4)
            else:
                _rect(self.screen, BTN_AC if active else (BTN_HO if hov else BTN), br, radius=4)
                _rect(self.screen, ACCENT if (active or hov) else BORDER, br,
                      2 if active else 1, radius=4)
            ts = _txt(lbl, "xs", TXT_HI)
            self.screen.blit(ts, (br.centerx - ts.get_width()//2,
                                  br.centery - ts.get_height()//2))
            self._scatter_hitboxes[key] = br
            bx += bw + bgap
        # Hint sotto la toolbar
        hint = "Clicca/trascina sul canvas per vietare celle allo scatter. ESC o FATTO per uscire."
        hs = _txt(hint, "xs", TXT_DIM)
        hint_bg = pygame.Rect(tx, ty + tb_h + 4, tb_w, 20)
        _rect(self.screen, (24, 26, 32), hint_bg, radius=4)
        self.screen.blit(hs, (hint_bg.centerx - hs.get_width()//2, hint_bg.y + 4))

    def _r_scatter_dropdown_style(self, px, py, pw, ph):
        styles = ["real", "cartoon", "line art"]
        base_r = self._scatter_hitboxes["style_btn"]
        # Conta oggetti per stile
        counts = Counter(c.get("style", "real") for c in self.catalog)
        dy = base_r.bottom + 2
        dh = 28 * len(styles) + 6
        d_r = pygame.Rect(base_r.x, dy, base_r.w, dh)
        _rect(self.screen, (30, 32, 38), d_r, radius=4)
        _rect(self.screen, ACCENT, d_r, 1, radius=4)
        mx, my = pygame.mouse.get_pos()
        for i, st in enumerate(styles):
            r = pygame.Rect(d_r.x + 3, dy + 3 + i * 28, d_r.w - 6, 26)
            active = (st == self._scatter_style)
            hov = _in_rect((mx, my), r)
            _rect(self.screen, BTN_AC if active else (BTN_HO if hov else BTN), r, radius=3)
            _draw_text(self.screen, st.upper(), "sm",
                       TXT_HI if (active or hov) else TXT, r.x + 12, r.y + 6)
            # Conta a destra
            cnt_txt = _txt(f"{counts.get(st, 0)}", "xs", TXT_DIM)
            self.screen.blit(cnt_txt, (r.right - cnt_txt.get_width() - 10, r.centery - cnt_txt.get_height()//2))
            self._scatter_hitboxes[f"style_opt_{st}"] = r

    def _r_scatter_dropdown_tier(self, px, py, pw, ph, status):
        """Dropdown per scelta del tier IA."""
        base_r = self._scatter_hitboxes["tier_btn"]
        choices = [
            ("auto",    "AUTO (rileva GPU)",      None),
            ("classic", "CLASSICO (no IA)",       None),
            ("light",   "LIGHT (Depth)",          1),
            ("pro",     "PRO (Depth+Normals)",    2),
            ("ultra",   "ULTRA (D+N+Seg+CLIP)",   3),
        ]
        dy = base_r.bottom + 2
        row_h = 28
        dh = row_h * len(choices) + 6
        d_r = pygame.Rect(base_r.x, dy, base_r.w, dh)
        _rect(self.screen, (30, 32, 38), d_r, radius=4)
        _rect(self.screen, ACCENT, d_r, 1, radius=4)
        mx, my = pygame.mouse.get_pos()
        # Aumenta dh per le 5 opzioni
        new_dh = row_h * len(choices) + 6
        d_r2 = pygame.Rect(base_r.x, dy, base_r.w, new_dh)
        # Re-disegna sfondo (potrebbe sforare)
        _rect(self.screen, (30, 32, 38), d_r2, radius=4)
        _rect(self.screen, ACCENT, d_r2, 1, radius=4)
        for i, (val, lbl, tier) in enumerate(choices):
            r = pygame.Rect(d_r2.x + 3, dy + 3 + i * row_h, d_r2.w - 6, row_h - 2)
            active = (val == self._scatter_tier_choice)
            hov = _in_rect((mx, my), r)
            _rect(self.screen, BTN_AC if active else (BTN_HO if hov else BTN), r, radius=3)
            _draw_text(self.screen, lbl, "xs",
                       TXT_HI if (active or hov) else TXT, r.x + 12, r.y + 6, r.w - 90)
            if tier == 1:
                ok = status["tier1_model_present"]
            elif tier == 2:
                ok = status["tier2_model_present"]
            elif tier == 3:
                ok = status.get("tier3_model_present", False)
            else:
                ok = True
            stat_lbl = "OK" if ok else "MANCA"
            stat_col = OK_C if ok else WARN_C
            st = _txt(stat_lbl, "xs", stat_col)
            self.screen.blit(st, (r.right - st.get_width() - 8, r.centery - st.get_height()//2))
            self._scatter_hitboxes[f"tier_opt_{val}"] = r

    def _r_scatter_dropdown_tag(self, px, py, pw, ph, tags):
        """Dropdown tag con scroll se molti, riga (TUTTI) sempre in cima."""
        base_r = self._scatter_hitboxes["tag_btn"]
        items = [(None, "(TUTTI)", sum(c for _, c in tags))]
        items += [(t, t.upper(), c) for t, c in tags]

        dy = base_r.bottom + 2
        # Cap altezza al panel (lascia 16px in basso)
        row_h = 24
        max_dh = py + ph - dy - 16
        # Mostro fino a tutti gli item se ci stanno
        visible_count = min(len(items), max(3, max_dh // row_h))
        dh = visible_count * row_h + 6

        d_r = pygame.Rect(base_r.x, dy, base_r.w, dh)
        _rect(self.screen, (30, 32, 38), d_r, radius=4)
        _rect(self.screen, ACCENT, d_r, 1, radius=4)

        # Clamp scroll
        max_scroll = max(0, len(items) - visible_count)
        if self._scatter_tag_scroll > max_scroll:
            self._scatter_tag_scroll = max_scroll
        if self._scatter_tag_scroll < 0:
            self._scatter_tag_scroll = 0

        self.screen.set_clip(d_r)
        mx, my = pygame.mouse.get_pos()
        start_idx = self._scatter_tag_scroll
        end_idx = min(len(items), start_idx + visible_count)
        for vi, idx in enumerate(range(start_idx, end_idx)):
            tval, tlbl, cnt = items[idx]
            r = pygame.Rect(d_r.x + 3, dy + 3 + vi * row_h, d_r.w - 6 - (8 if max_scroll > 0 else 0), row_h - 2)
            active = (tval == self._scatter_tag)
            hov = _in_rect((mx, my), r)
            _rect(self.screen, BTN_AC if active else (BTN_HO if hov else BTN), r, radius=3)
            # Label a sinistra
            label_color = TXT_HI if (active or hov) else TXT
            _draw_text(self.screen, tlbl, "xs", label_color, r.x + 10, r.y + 5, r.w - 50)
            # Count a destra
            cnt_txt = _txt(str(cnt), "xs", TXT_DIM)
            self.screen.blit(cnt_txt, (r.right - cnt_txt.get_width() - 8, r.centery - cnt_txt.get_height()//2))
            key = "tag_opt_NONE" if tval is None else f"tag_opt_{tval}"
            self._scatter_hitboxes[key] = r
        self.screen.set_clip(None)

        # Scrollbar visiva se serve
        if max_scroll > 0:
            sb_x = d_r.right - 6
            sb_track = pygame.Rect(sb_x, d_r.y + 3, 4, d_r.h - 6)
            pygame.draw.rect(self.screen, BORDER, sb_track, border_radius=2)
            thumb_h = max(20, int(sb_track.h * visible_count / len(items)))
            thumb_y = int(sb_track.y + (sb_track.h - thumb_h) * (start_idx / max_scroll))
            thumb_r = pygame.Rect(sb_x, thumb_y, 4, thumb_h)
            pygame.draw.rect(self.screen, ACCENT, thumb_r, border_radius=2)

    # ── click / wheel ─────────────────────────────────────────────────────
    def _scatter_modal_click(self, mx, my, w, h):
        """Click handler. Restituisce True se gestito."""
        if not self._scatter_modal_open:
            return False

        # ── BRUSH MODE: toolbar oppure pittura sul canvas ────────────────
        if self._scatter_brush_active:
            hb = self._scatter_hitboxes
            if _in_rect((mx, my), hb.get("brush_paint", pygame.Rect(0, 0, 0, 0))):
                self._scatter_brush_tool = "paint"
                return True
            if _in_rect((mx, my), hb.get("brush_erase", pygame.Rect(0, 0, 0, 0))):
                self._scatter_brush_tool = "erase"
                return True
            if _in_rect((mx, my), hb.get("brush_clear", pygame.Rect(0, 0, 0, 0))):
                if self._scatter_forbidden_cells:
                    self._scatter_forbidden_cells = set()
                    self._scatter_forbidden_dirty = True
                    self._scatter_ghosts = []
                return True
            if _in_rect((mx, my), hb.get("brush_done", pygame.Rect(0, 0, 0, 0))):
                self._scatter_brush_exit()
                return True
            if _in_rect((mx, my), hb.get("brush_toolbar", pygame.Rect(0, 0, 0, 0))):
                return True
            # Click sul canvas: dipingi/cancella (il drag continua in _on_mmove)
            self._scatter_brush_paint_at(mx, my)
            return True

        # Dropdown options (priority)
        if self._scatter_drop_open:
            for key, r in self._scatter_hitboxes.items():
                if not _in_rect((mx, my), r):
                    continue
                if key.startswith("style_opt_"):
                    new_style = key[len("style_opt_"):]
                    if new_style != self._scatter_style:
                        self._scatter_style = new_style
                        self._scatter_tag = None
                        self._scatter_ghosts = []
                        self._scatter_tag_scroll = 0
                    self._scatter_drop_open = None
                    return True
                if key.startswith("tag_opt_"):
                    val = key[len("tag_opt_"):]
                    self._scatter_tag = None if val == "NONE" else val
                    self._scatter_drop_open = None
                    self._scatter_ghosts = []
                    return True
                if key.startswith("tier_opt_"):
                    val = key[len("tier_opt_"):]
                    self._scatter_tier_choice = val
                    self._scatter_drop_open = None
                    self._scatter_model = None
                    self._scatter_model_tier_active = 0
                    self._scatter_bg_analysis = None
                    self._scatter_bg_cache_key = None
                    self._scatter_ghosts = []
                    self._scatter_status_msg = f"Modalita IA: {val.upper()}"
                    self._scatter_status_color = ACCENT
                    self._scatter_save_prefs()
                    return True
            self._scatter_drop_open = None
            return True

        hb = self._scatter_hitboxes

        # Campo seed: il focus si prende cliccandoci, si perde altrove (U2)
        if _in_rect((mx, my), hb.get("seed_box", pygame.Rect(0, 0, 0, 0))):
            self._scatter_seed_editing = True
            return True
        self._scatter_seed_editing = False
        if _in_rect((mx, my), hb.get("seed_lock", pygame.Rect(0, 0, 0, 0))):
            self._scatter_seed_locked = not self._scatter_seed_locked
            self._scatter_status_msg = ("Seed fisso: GENERA riusa lo stesso seed"
                                        if self._scatter_seed_locked
                                        else "Seed libero: ogni GENERA e' random")
            self._scatter_status_color = ACCENT
            return True

        # ANNULLA della run in corso (U1)
        if _in_rect((mx, my), hb.get("cancel_run", pygame.Rect(0, 0, 0, 0))):
            self._scatter_cancel_run()
            self._scatter_status_msg = "Elaborazione annullata"
            self._scatter_status_color = WARN_C
            return True

        if _in_rect((mx, my), hb.get("close", pygame.Rect(0,0,0,0))):
            self._scatter_close(); return True

        if _in_rect((mx, my), hb.get("debug_btn", pygame.Rect(0,0,0,0))):
            self._scatter_debug_cycle(); return True

        if _in_rect((mx, my), hb.get("style_btn", pygame.Rect(0,0,0,0))):
            self._scatter_drop_open = "style"; return True

        if _in_rect((mx, my), hb.get("tag_btn", pygame.Rect(0,0,0,0))):
            self._scatter_drop_open = "tag"
            self._scatter_tag_scroll = 0
            return True

        if _in_rect((mx, my), hb.get("tier_btn", pygame.Rect(0,0,0,0))):
            self._scatter_drop_open = "tier"; return True

        # Click sul badge "SCARICA" per scaricare il modello del tier scelto
        if _in_rect((mx, my), hb.get("download_model", pygame.Rect(0,0,0,0))):
            tier_int = {"light": 1, "pro": 2, "ultra": 3}.get(self._scatter_tier_choice)
            if tier_int:
                self._scatter_download_model(tier_int)
            return True

        for d in ("easy", "medium", "hard"):
            if _in_rect((mx, my), hb.get(f"diff_{d}", pygame.Rect(0,0,0,0))):
                self._scatter_difficulty = d
                self._scatter_ghosts = []
                self._scatter_status_msg = f"Difficolta: {d.upper()}"
                self._scatter_status_color = ACCENT
                return True

        # Layer checkboxes
        for lid in ("objects_low", "objects_mid", "objects_high"):
            if _in_rect((mx, my), hb.get(f"layer_{lid}", pygame.Rect(0,0,0,0))):
                cur = self._scatter_layers.get(lid, True)
                # Almeno uno deve restare attivo
                active_count = sum(1 for v in self._scatter_layers.values() if v)
                if cur and active_count <= 1:
                    self._scatter_status_msg = "Almeno un layer deve restare attivo"
                    self._scatter_status_color = WARN_C
                    return True
                self._scatter_layers[lid] = not cur
                self._scatter_ghosts = []
                act = [k.replace("objects_", "").upper()
                       for k, v in self._scatter_layers.items() if v]
                self._scatter_status_msg = f"Layer attivi: {', '.join(act)}"
                self._scatter_status_color = ACCENT
                self._scatter_save_prefs()
                return True

        # Brush zone vietate: entra in modalita' pittura / pulisci tutto
        if _in_rect((mx, my), hb.get("brush_enter", pygame.Rect(0, 0, 0, 0))):
            self._scatter_brush_active = True
            self._scatter_brush_tool = "paint"
            self._scatter_drop_open = None
            self._scatter_status_msg = "Brush zone vietate attivo"
            self._scatter_status_color = ACCENT
            return True
        if _in_rect((mx, my), hb.get("brush_clear", pygame.Rect(0, 0, 0, 0))):
            if self._scatter_forbidden_cells:
                self._scatter_forbidden_cells = set()
                self._scatter_forbidden_dirty = True
                self._scatter_ghosts = []
                self._scatter_forbidden_save()
                self._scatter_status_msg = "Zone vietate azzerate"
                self._scatter_status_color = ACCENT
            return True

        sl = hb.get("count_slider")
        if sl and _in_rect((mx, my), sl):
            ratio = _clamp((mx - sl.x) / sl.w, 0.0, 1.0)
            self._scatter_count = max(1, int(round(1 + ratio * 299)))
            return True

        if _in_rect((mx, my), hb.get("generate", pygame.Rect(0,0,0,0))):
            self._scatter_run(); return True
        if _in_rect((mx, my), hb.get("reroll", pygame.Rect(0,0,0,0))):
            self._scatter_run(reroll=True); return True
        if _in_rect((mx, my), hb.get("apply", pygame.Rect(0,0,0,0))):
            self._scatter_apply(); return True

        if self._scatter_panel_rect and _in_rect((mx, my), self._scatter_panel_rect):
            return True

        self._scatter_close()
        return True

    def _scatter_modal_key(self, ev) -> bool:
        """Tastiera nel modal scatter (chiamata da input_handlers): ESC con
        priorita' brush -> campo seed -> run in corso -> chiudi; cifre e
        backspace quando il campo seed ha il focus. Consuma sempre l'evento
        finche' il modal e' aperto (comportamento storico)."""
        if not self._scatter_modal_open:
            return False
        if ev.key == pygame.K_ESCAPE:
            if self._scatter_brush_active:
                self._scatter_brush_exit()
            elif self._scatter_seed_editing:
                self._scatter_seed_editing = False
            elif self._scatter_busy:
                self._scatter_cancel_run()
                self._scatter_status_msg = "Elaborazione annullata"
                self._scatter_status_color = WARN_C
            else:
                self._scatter_close()
            return True
        if self._scatter_seed_editing:
            if ev.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                self._scatter_seed_editing = False
            elif ev.key == pygame.K_BACKSPACE:
                self._scatter_seed_text = self._scatter_seed_text[:-1]
            elif ev.key == pygame.K_DELETE:
                self._scatter_seed_text = ""
            elif getattr(ev, "unicode", "").isdigit() \
                    and len(self._scatter_seed_text) < 9:
                self._scatter_seed_text += ev.unicode
        return True

    def _scatter_modal_wheel(self, mx, my, dy):
        """Gestisce scroll nella modal (solo dropdown tag). Restituisce True se gestito."""
        if not self._scatter_modal_open:
            return False
        if self._scatter_drop_open == "tag":
            base_r = self._scatter_hitboxes.get("tag_btn")
            if base_r:
                # Se il cursore e' sopra il dropdown area, gestisci scroll
                # (semplificazione: gestisci sempre quando il tag dropdown e' aperto)
                self._scatter_tag_scroll -= dy
                return True
        return False
