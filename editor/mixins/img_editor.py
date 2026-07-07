"""
editor/mixins/img_editor.py

ImgEditorMixin — Editor di immagini professionale per gli oggetti del catalogo.
Include: gomma, ripristina, magic wand, chroma destroyer, zoom/pan,
trim evoluto, ritaglio manuale con maniglie, undo/redo, rimozione sfondo AI
(rembg), ridimensionamento numerico, filtri colore e contorno silhouette.
"""

import pygame
import logging
import math
import copy
import json
import hashlib
import threading
from pathlib import Path
from editor.constants import (
    ACCENT, BORDER, BTN, BTN_HO, BTN_AC, PANEL,
    TXT, TXT_DIM, TXT_HI, OK_C, ERR_C, WARN_C,
)
from editor.ui.draw import (
    _txt, _draw_text, _rect, _button, _in_rect, _slider, _input_box, _text_wh,
)
from editor.mixins.img_editor_logic import (
    evolved_trim, brush_power_map, restore_stamp,
    apply_color_adjust_surface, outline_ring, aspect_resize_dims,
)

# Costanti Studio Asset
UNDO_STACK_CAP = 20              # Profondita' massima di undo e redo
TOOL_BTN_SIZE = 48               # Lato dei bottoni strumento (3 per riga)
TOOL_BTN_STEP = 53               # Passo orizzontale tra i bottoni strumento
CROP_HANDLE_SIZE = 12            # Lato visivo delle maniglie di ritaglio
CROP_HANDLE_HIT = 22             # Lato dell'area cliccabile delle maniglie
CROP_MIN_KEEP = 1                # Pixel minimi che il ritaglio deve lasciare
CROP_OVERLAY_ALPHA = 150         # Opacita' dell'overlay sulle zone escluse
CROP_HANDLE_FILL = (25, 25, 30)  # Riempimento maniglie (sfondo modal)
SIDEBAR_W = 480                  # Larghezza sidebar strumenti (3 colonne)
COL3_X_OFF = 320                 # Offset X della colonna 3 dentro la sidebar
FILTER_MIN = -100                # Estremo inferiore slider filtri colore
FILTER_MAX = 100                 # Estremo superiore slider filtri colore
OUTLINE_MIN_PX = 1               # Spessore minimo del contorno
OUTLINE_MAX_PX = 8               # Spessore massimo del contorno
OUTLINE_DEFAULT_PX = 2           # Spessore contorno di default
OUTLINE_COLORS = {"white": (255, 255, 255), "black": (0, 0, 0)}
RESIZE_FIELD_MAX_CHARS = 4       # Cifre massime nei campi W/H
BUSY_OVERLAY_ALPHA = 130         # Opacita' overlay canvas durante l'AI
BUSY_DOT_MS = 350                # Periodo animazione puntini "Elaborazione"


class ImgEditorMixin:
    """Editor professionale per PNG del catalogo."""

    def _img_editor_init_state(self):
        self._img_editor_active = False
        self._img_editor_id = ""
        self._img_editor_path = None
        self._img_editor_zoom = 1.0
        self._img_editor_pan = [0, 0]
        self._img_editor_surf = None
        self._img_editor_view_surf = None # Superficie di lavoro
        self._img_editor_orig_surf = None # Copia originale per lo strumento Ripristina
        self._img_editor_last_m = None    # Per interpolazione gomma
        self._img_editor_eraser_r = 4
        self._img_editor_eraser_hardness = 1.0
        self._img_editor_eraser_opacity = 1.0
        self._img_editor_wand_tol = 32
        self._img_editor_wand_feather = 4
        self._img_editor_chroma_intensity = 1.0
        self._img_editor_tool = "eraser"  # "eraser", "restore", "wand"
        self._img_editor_shape = "round"  # "round", "square"
        self._img_editor_crop = {"l": 0, "r": 0, "t": 0, "b": 0}
        self._img_editor_crop_mode = False  # Toggle strumento Ritaglia
        self._img_editor_dragging = None # "eraser" | "pan" | "crop_l/r/t/b" | "sl_*"
        self._img_editor_dirty = False
        self._img_editor_undo_stack = []
        self._img_editor_redo_stack = []
        self._img_editor_brush_cache = {}
        self._img_editor_restore_cache = {}
        self._img_editor_save_confirm = False
        self._img_editor_copy_confirm = False
        self._img_editor_exit_confirm = False
        self._img_editor_bg_mode = "check"
        # Rimozione sfondo AI (rembg) in thread separato
        self._img_editor_busy = False
        self._img_editor_ai_result = None   # (token, bytes RGBA, (w, h)) dal worker
        self._img_editor_ai_error = None    # (token, messaggio) dal worker
        self._img_editor_ai_token = 0       # Scarta risultati di sessioni precedenti
        # Ridimensionamento numerico (campi W/H con aspect ratio bloccato)
        self._img_editor_resize_edit = False
        self._img_editor_resize_w = ""
        self._img_editor_resize_h = ""
        self._img_editor_resize_focus = "w"
        # Filtri colore in anteprima live (b/c/s in -100..+100)
        self._img_editor_filters = {"b": 0, "c": 0, "s": 0}
        # Contorno silhouette
        self._img_editor_outline_px = OUTLINE_DEFAULT_PX
        self._img_editor_outline_color = "white"
        self._img_editor_icons = {}
        self._img_editor_load_assets()

    def _img_editor_load_assets(self):
        """Carica le icone professionali dalla cartella engine con logging robusto."""
        # Proviamo diversi percorsi comuni per robustezza
        search_paths = [
            self.base_path / "engine" / "assets" / "icons" / "img_editor",
            Path("engine/assets/icons/img_editor"),
            Path("assets/icons/img_editor")
        ]
        
        icon_dir = None
        for sp in search_paths:
            if sp.exists():
                icon_dir = sp; break
        
        if not icon_dir:
            logging.error(f"[IMG_EDITOR] Nessuna cartella icone trovata! Base: {self.base_path}")
            return
            
        logging.info(f"[IMG_EDITOR] Caricamento icone da: {icon_dir.absolute()}")
        
        # Carichiamo sia dalla sottocartella che dalla cartella padre (per circle/square)
        parent_dir = icon_dir.parent
        
        load_count = 0
        for folder in [icon_dir, parent_dir]:
            for p in folder.glob("*.png"):
                try:
                    img = pygame.image.load(str(p)).convert_alpha()
                    img_32 = pygame.transform.smoothscale(img, (32, 32))
                    stem = p.stem
                    # Mappatura nomi per coerenza interna
                    if stem == "circle": stem = "circle_p"
                    if stem == "square": stem = "square_p"
                    
                    self._img_editor_icons[stem] = img_32
                    load_count += 1
                except Exception as e:
                    logging.error(f"[IMG_EDITOR] Errore caricamento {p.name}: {e}")
        
        logging.info(f"[IMG_EDITOR] Caricate {load_count} icone PNG.")

    def _img_editor_open(self, cat_id: str):
        logging.info(f"[IMG_EDITOR] Opening for cat_id: {cat_id}")
        cat_item = next((c for c in self.catalog if c["id"] == cat_id), None)
        if not cat_item:
            logging.error(f"[IMG_EDITOR] Item {cat_id} not found in catalog")
            return
        
        img_rel = cat_item.get("image", cat_item.get("icon", ""))
        if not img_rel:
            logging.error(f"[IMG_EDITOR] Item {cat_id} has no image/icon")
            self._status("Nessuna immagine trovata per l'oggetto", ERR_C, 3)
            return

        self._img_editor_path = self.game_path / img_rel
        if not self._img_editor_path.exists():
            master_p = self.base_path / "engine" / "assets" / img_rel
            if master_p.exists():
                self._img_editor_path = master_p
            else:
                self._status(f"File non trovato: {img_rel}", ERR_C, 3)
                return

        try:
            # Hash dei byte del file ORIGINALE: serve a riconoscere i duplicati
            # reali (stesso contenuto) in fase di salvataggio, evitando di
            # sovrascrivere file omonimi ma diversi appartenenti ad altri giochi.
            try:
                self._img_editor_orig_hash = hashlib.sha256(
                    self._img_editor_path.read_bytes()
                ).hexdigest()
            except Exception:
                self._img_editor_orig_hash = None

            orig = pygame.image.load(str(self._img_editor_path)).convert_alpha()
            self._img_editor_surf = orig
            self._img_editor_view_surf = orig.copy()
            # Copia dell'originale: sorgente pixel per lo strumento Ripristina
            self._img_editor_orig_surf = orig.copy()
            self._img_editor_id = cat_id
            self._img_editor_active = True
            self._img_editor_asset_shape = cat_item.get("shape", "rect")
            self._img_editor_crop = {"l": 0, "r": 0, "t": 0, "b": 0}
            self._img_editor_crop_mode = False
            self._img_editor_dirty = False
            self._img_editor_undo_stack = []
            self._img_editor_redo_stack = []
            self._img_editor_save_confirm = False
            self._img_editor_copy_confirm = False
            self._img_editor_exit_confirm = False
            # Reset stato AI / resize / filtri della sessione precedente
            self._img_editor_busy = False
            self._img_editor_ai_result = None
            self._img_editor_ai_error = None
            self._img_editor_ai_token += 1
            self._img_editor_resize_edit = False
            self._img_editor_filters = {"b": 0, "c": 0, "s": 0}
            # Forza Auto-Fit al primo frame
            self._img_editor_zoom = 0.0
            self._img_editor_pan = [0, 0]
            self._status(f"Editor Immagine: {cat_id}", ACCENT, 2)
        except Exception as e:
            self._status(f"Errore caricamento: {e}", ERR_C, 3)

    def _img_editor_compose_final_surf(self) -> pygame.Surface:
        """Superficie finale con il crop corrente applicato (save, copia, applica)."""
        w, h = self._img_editor_view_surf.get_size()
        cl, cr = self._img_editor_crop["l"], self._img_editor_crop["r"]
        ct, cb = self._img_editor_crop["t"], self._img_editor_crop["b"]
        new_w = max(1, w - cl - cr)
        new_h = max(1, h - ct - cb)
        final_surf = pygame.Surface((new_w, new_h), pygame.SRCALPHA)
        final_surf.blit(self._img_editor_view_surf, (0, 0), (cl, ct, new_w, new_h))
        return final_surf

    def _img_editor_save(self):
        if not self._img_editor_active or not self._img_editor_path: return

        try:
            # Applica il crop finale
            final_surf = self._img_editor_compose_final_surf()

            target_name = self._img_editor_path.name
            
            # 0. Aggiorna metadati nel catalogo in memoria
            cat_item = next((c for c in self.catalog if c["id"] == self._img_editor_id), None)
            if cat_item:
                cat_item["shape"] = self._img_editor_asset_shape

            # 1. Salva il file principale
            pygame.image.save(final_surf, str(self._img_editor_path))
            
            # 2. Sincronizzazione duplicati REALI: sovrascrive solo i file omonimi
            #    il cui contenuto e' byte-identico all'originale pre-modifica.
            #    Senza questo controllo, file con lo stesso nome ma appartenenti ad
            #    altri giochi (es. icon.png, bg.png) verrebbero distrutti.
            overwritten_paths = [self._img_editor_path]
            orig_hash = getattr(self, "_img_editor_orig_hash", None)
            self_resolved = self._img_editor_path.resolve()
            if orig_hash:
                search_roots = [self.base_path / "engine" / "assets", self.base_path / "games"]
                for root in search_roots:
                    if not root.exists(): continue
                    for p in root.rglob(target_name):
                        try:
                            if p.resolve() == self_resolved:
                                continue
                            if hashlib.sha256(p.read_bytes()).hexdigest() != orig_hash:
                                continue  # file omonimo ma diverso: NON toccare
                            pygame.image.save(final_surf, str(p))
                            overwritten_paths.append(p)
                        except Exception:
                            pass

            # 2b. Sincronizza Metadati nel Catalogo Globale Engine
            style = cat_item.get("style", "cartoon").replace(" ", "")
            catalog_file = f"global_{style}_catalog.json"
            global_path = self.base_path / "engine" / "data" / catalog_file
            
            if global_path.exists():
                try:
                    with open(global_path, "r", encoding="utf-8") as f:
                        g_cat = json.load(f)
                    for g_obj in g_cat["objects"]:
                        if g_obj["id"] == self._img_editor_id:
                            g_obj["shape"] = self._img_editor_asset_shape
                            break
                    with open(global_path, "w", encoding="utf-8") as f:
                        json.dump(g_cat, f, indent=2, ensure_ascii=False)
                except Exception: pass

            # 3. Pulizia Cache
            self._img_cache.clear()
            self._obj_draw_cache.clear()
            self._asset_ratios_cache.clear()
            if hasattr(self, "_filter_cache"): self._filter_cache.clear()
            self._canvas_cache_dirty = True
            
            self._img_editor_dirty = False
            self._img_editor_save_confirm = False
            self._img_editor_copy_confirm = False
            self._img_editor_exit_confirm = False
            self._img_editor_active = False
            self._status(f"Asset '{self._img_editor_id}' aggiornato globalmente", OK_C, 3)
            self.scene_dirty = True
        except Exception as e:
            self._status(f"Errore salvataggio: {e}", ERR_C, 3)

    def _img_editor_save_copy(self):
        """Salva l'immagine come nuovo asset nel catalogo (Copia)."""
        if not self._img_editor_active or not self._img_editor_path: return
        try:
            orig_id = self._img_editor_id
            orig_idx = -1
            orig_item = None
            for i, item in enumerate(self.catalog):
                if item["id"] == orig_id:
                    orig_idx = i; orig_item = item; break
            
            if not orig_item: return
            
            import re
            match = re.match(r"(.+)_v(\d+)$", orig_id)
            if match:
                base_name = match.group(1); counter = int(match.group(2)) + 1
            else:
                base_name = orig_id; counter = 1
            
            new_id = f"{base_name}_v{counter}"
            while any(c["id"] == new_id for c in self.catalog):
                counter += 1; new_id = f"{base_name}_v{counter}"
            
            # Prepara Superficie Finale
            final_surf = self._img_editor_compose_final_surf()

            orig_rel_path = orig_item.get("image") or orig_item.get("icon")
            p = Path(orig_rel_path)
            clean_stem = re.sub(r"_v\d+$", "", p.stem)
            new_rel_path = str(p.parent / f"{clean_stem}_v{counter}{p.suffix}").replace("\\", "/")
            # Risolvi il path assoluto contro game_path (la radice a cui il path
            # relativo registrato nel catalogo fa riferimento). Usare la cartella di
            # apertura sarebbe errato in fallback master (engine/assets): il file
            # finirebbe nell'engine mentre il catalogo punta al gioco.
            new_abs_path = self.game_path / new_rel_path
            new_abs_path.parent.mkdir(parents=True, exist_ok=True)
            
            new_item = copy.deepcopy(orig_item)
            new_item["id"] = new_id
            if "image" in new_item: new_item["image"] = new_rel_path
            if "icon" in new_item: new_item["icon"] = new_rel_path
            new_item["shape"] = self._img_editor_asset_shape
            
            pygame.image.save(final_surf, str(new_abs_path))
            
            if orig_idx != -1: self.catalog.insert(orig_idx + 1, new_item)
            else: self.catalog.append(new_item)
            
            if hasattr(self, "_sync_game_catalog_entry"): self._sync_game_catalog_entry(new_item)
            
            self._img_cache.clear()
            self._obj_draw_cache.clear()
            self._img_editor_save_confirm = False
            self._img_editor_copy_confirm = False
            self._img_editor_exit_confirm = False
            self._img_editor_active = False
            self._status(f"Copia creata: {new_id}", OK_C, 3)
            self.scene_dirty = True
        except Exception as e:
            self._status(f"Errore copia: {e}", ERR_C, 3)

    def _img_editor_handle_event(self, ev):
        if not self._img_editor_active: return
        
        if ev.type == pygame.KEYDOWN:
            # Editing campi W/H: la tastiera e' catturata dal mini-prompt
            if self._img_editor_resize_edit:
                self._img_editor_resize_keydown(ev)
                return
            # Elaborazione AI in corso: accettiamo solo l'uscita dal modale
            if self._img_editor_busy:
                if ev.key == pygame.K_ESCAPE:
                    self._img_editor_active = False
                return
            mods = pygame.key.get_mods()
            if ev.key == pygame.K_ESCAPE:
                # In modalita' ritaglio, Esc annulla il ritaglio senza chiudere
                if self._img_editor_crop_mode: self._img_editor_cancel_crop()
                else: self._img_editor_active = False
            elif ev.key == pygame.K_s and (mods & pygame.KMOD_CTRL): self._img_editor_save()
            elif ev.key == pygame.K_z and (mods & pygame.KMOD_CTRL):
                if mods & pygame.KMOD_SHIFT: self._img_editor_redo()
                else: self._img_editor_undo()
            elif ev.key == pygame.K_y and (mods & pygame.KMOD_CTRL): self._img_editor_redo()
            elif ev.key == pygame.K_r and (mods & pygame.KMOD_CTRL):
                self._img_editor_zoom = 1.0; self._img_editor_pan = [0, 0]
        
        elif ev.type == pygame.MOUSEWHEEL:
            mx, my = pygame.mouse.get_pos()
            ex, ey, ew, eh = self._img_editor_get_modal_rect()

            # Layout corrente prima dello zoom
            ix, iy, sw, sh, old_scale = self._img_editor_get_img_layout(ew, eh, ex, ey)
            
            # Calcolo posizione immagine-space sotto il mouse
            px = (mx - ix) / old_scale
            py = (my - iy) / old_scale
            
            # Applicazione zoom
            zoom_speed = 0.15 if pygame.key.get_mods() & pygame.KMOD_LSHIFT else 0.08
            old_zoom = self._img_editor_zoom
            if ev.y > 0: self._img_editor_zoom *= (1.0 + zoom_speed)
            else: self._img_editor_zoom /= (1.0 + zoom_speed)
            self._img_editor_zoom = max(0.1, min(40.0, self._img_editor_zoom))
            
            # Calcolo nuovo layout e aggiustamento pan per mantenere il punto fisso
            # Il nuovo pan deve compensare lo spostamento del pixel sotto il mouse
            new_scale = old_scale * (self._img_editor_zoom / old_zoom)
            
            # iw/2 è il centro dell'immagine. px è la distanza dal bordo sinistro.
            # (px - iw/2) è l'offset dal centro in image-pixels.
            iw, ih = self._img_editor_view_surf.get_size()
            cx, cy = iw / 2.0, ih / 2.0
            
            # Formula Photoshop: new_pan = (cx - px) + (old_scale / new_scale) * (old_pan + px - cx)
            self._img_editor_pan[0] = (cx - px) + (old_scale / new_scale) * (self._img_editor_pan[0] + px - cx)
            self._img_editor_pan[1] = (cy - py) + (old_scale / new_scale) * (self._img_editor_pan[1] + py - cy)
            
        elif ev.type == pygame.MOUSEBUTTONDOWN:
            mx, my = ev.pos
            if ev.button == 2 or (ev.button == 1 and pygame.key.get_pressed()[pygame.K_SPACE]):
                self._img_editor_dragging = "pan"; self._img_editor_last_m = ev.pos
            else:
                self._img_editor_click(mx, my, ev.button)
            
        elif ev.type == pygame.MOUSEBUTTONUP:
            self._img_editor_dragging = None; self._img_editor_last_m = None
            
        elif ev.type == pygame.MOUSEMOTION:
            mx, my = ev.pos
            if self._img_editor_dragging == "pan":
                if self._img_editor_last_m:
                    lx, ly = self._img_editor_last_m
                    dx, dy = mx - lx, my - ly
                    ex, ey, ew, eh = self._img_editor_get_modal_rect()
                    _, _, _, _, scale = self._img_editor_get_img_layout(ew, eh, ex, ey)
                    self._img_editor_pan[0] += dx / scale
                    self._img_editor_pan[1] += dy / scale
                    self._img_editor_last_m = (mx, my)
            elif ev.buttons[0]:
                if not pygame.key.get_pressed()[pygame.K_SPACE]:
                    self._img_editor_drag(mx, my)

    def _img_editor_get_img_layout(self, ew, eh, ex, ey):
        iw, ih = self._img_editor_view_surf.get_size()
        # Responsive: sidebar a 3 colonne, resto alla tela
        sb_w = SIDEBAR_W
        work_w = ew - sb_w - 60
        work_h = eh - 150
        
        base_scale = min(work_w / iw, work_h / ih)
        total_scale = base_scale * self._img_editor_zoom
        scaled_w, scaled_h = int(iw * total_scale), int(ih * total_scale)
        
        work_area_x = ex + 25
        work_area_y = ey + 70
        work_cx = work_area_x + work_w // 2
        work_cy = work_area_y + work_h // 2
        
        ix = work_cx - (scaled_w // 2) + int(self._img_editor_pan[0] * total_scale)
        iy = work_cy - (scaled_h // 2) + int(self._img_editor_pan[1] * total_scale)
        return ix, iy, scaled_w, scaled_h, total_scale

    def _img_editor_get_modal_rect(self):
        """Sorgente unica per dimensioni e posizione del modal."""
        w, h = self.screen.get_size()
        ew = int(min(w * 0.94, 1280))
        eh = int(min(h * 0.90, 820))
        ex, ey = (w - ew) // 2, (h - eh) // 2
        return ex, ey, ew, eh

    def _img_editor_click(self, mx, my, btn):
        if not self._img_editor_active: return
        ex, ey, ew, eh = self._img_editor_get_modal_rect()
        ix, iy, sw, sh, scale = self._img_editor_get_img_layout(ew, eh, ex, ey)

        reset_confirm = True
        sb_w = SIDEBAR_W
        sb_x = ex + ew - sb_w - 15
        # ALLINEATO al render: col1_x = sb_x + 10, col2_x = sb_x + 165
        col1_x = sb_x + 10
        col2_x = sb_x + 165
        sl_w = 145
        bw2 = (sl_w // 2) - 3

        # Footer rects (uguale al render)
        fy = ey + eh - 65
        bw, bh = 150, 42
        total_footer_w = bw * 3 + 40
        fb_start_x = ex + (ew - sb_w) // 2 - total_footer_w // 2
        fb_rects = [pygame.Rect(fb_start_x + i * (bw + 20), fy, bw, bh) for i in range(3)]

        # Toggle background nel top-right
        bg_r = pygame.Rect(ex + ew - 110, ey + 25, 80, 32)
        if _in_rect((mx, my), bg_r):
            modes = ["check", "black", "white"]
            self._img_editor_bg_mode = modes[(modes.index(self._img_editor_bg_mode) + 1) % 3]
            return

        # Elaborazione AI in corso: input bloccato, e' consentita solo l'uscita
        # (il risultato del thread verra' scartato tramite il token di sessione)
        if self._img_editor_busy:
            if _in_rect((mx, my), fb_rects[2]):
                if self._img_editor_dirty and not self._img_editor_exit_confirm:
                    self._img_editor_exit_confirm = True
                else:
                    self._img_editor_active = False
            return

        # Editing W/H attivo: un click fuori dai campi/bottone chiude il prompt
        # e viene consumato (evita pennellate accidentali sul canvas)
        if self._img_editor_resize_edit:
            r3 = self._img_editor_col3_rects(ex, ey, sb_x)
            on_prompt = (_in_rect((mx, my), r3["dim_w"]) or _in_rect((mx, my), r3["dim_h"])
                         or _in_rect((mx, my), r3["dim_btn"]))
            if not on_prompt:
                self._img_editor_resize_edit = False
                return

        # Determina se il click cade su un elemento UI (sidebar / header / footer)
        is_ui = (mx > sb_x) or (my < ey + 60) or (my >= fy - 5)

        if not is_ui:
            if self._img_editor_crop_mode:
                # In modalita' ritaglio il canvas serve solo alle maniglie
                handle = self._img_editor_crop_handle_at(mx, my, ix, iy, scale)
                if handle is not None:
                    self._img_editor_dragging = "crop_" + handle
                return
            if self._img_editor_tool == "wand":
                self._img_editor_apply_wand(mx, my, ix, iy, scale)
            else:
                self._img_editor_dragging = "eraser"
                self._img_editor_last_m = None
                self._img_editor_erase(mx, my, ix, iy, scale)
            return

        # ---------- FOOTER ----------
        if _in_rect((mx, my), fb_rects[0]):
            if self._img_editor_dirty or any(self._img_editor_crop.values()):
                if not self._img_editor_save_confirm:
                    self._img_editor_save_confirm = True; reset_confirm = False
                else:
                    self._img_editor_save()
            return
        if _in_rect((mx, my), fb_rects[1]):
            if not self._img_editor_copy_confirm:
                self._img_editor_copy_confirm = True; reset_confirm = False
            else:
                self._img_editor_save_copy()
            return
        if _in_rect((mx, my), fb_rects[2]):
            if self._img_editor_dirty and not self._img_editor_exit_confirm:
                self._img_editor_exit_confirm = True; reset_confirm = False
            else:
                self._img_editor_active = False
            return

        # ---------- COLONNA 1: PENNELLI ----------
        sy = ey + 85
        for i, tid in enumerate(["eraser", "restore", "wand"]):
            tool_r = (col1_x + i * TOOL_BTN_STEP, sy, TOOL_BTN_SIZE, TOOL_BTN_SIZE)
            if _in_rect((mx, my), tool_r):
                self._img_editor_tool = tid; return
        for i, sid in enumerate(["round", "square"]):
            if _in_rect((mx, my), (col1_x + i * 60, sy + 65, 52, 52)):
                self._img_editor_shape = sid; return

        # Sliders (ALLINEATO al render: sy_sl = ey + 255, offset +70 e +140)
        sy_sl = ey + 255
        if self._img_editor_tool in ("eraser", "restore"):
            if _in_rect((mx, my), (col1_x, sy_sl, sl_w, 20)):
                self._img_editor_dragging = "sl_radius"
                self._img_editor_eraser_r = int(1 + max(0, min(1, (mx - col1_x) / sl_w)) * 63); return
            if _in_rect((mx, my), (col1_x, sy_sl + 70, sl_w, 20)):
                self._img_editor_dragging = "sl_hardness"
                self._img_editor_eraser_hardness = max(0, min(1, (mx - col1_x) / sl_w)); return
            if _in_rect((mx, my), (col1_x, sy_sl + 140, sl_w, 20)):
                self._img_editor_dragging = "sl_opacity"
                self._img_editor_eraser_opacity = max(0, min(1, (mx - col1_x) / sl_w)); return
        else:
            if _in_rect((mx, my), (col1_x, sy_sl, sl_w, 20)):
                self._img_editor_dragging = "sl_tol"
                self._img_editor_wand_tol = int(max(0, min(1, (mx - col1_x) / sl_w)) * 128); return
            if _in_rect((mx, my), (col1_x, sy_sl + 70, sl_w, 20)):
                self._img_editor_dragging = "sl_feather"
                self._img_editor_wand_feather = int(max(0, min(1, (mx - col1_x) / sl_w)) * 32); return

        sy_ch = sy_sl + 195
        for i, mode in enumerate(["green", "white", "black"]):
            if _in_rect((mx, my), (col1_x + i * 50, sy_ch, 45, 40)):
                self._img_editor_apply_smart_chroma(mode); return
        if _in_rect((mx, my), (col1_x, sy_ch + 100, sl_w, 20)):
            self._img_editor_dragging = "sl_chroma"
            self._img_editor_chroma_intensity = 0.5 + max(0, min(1, (mx - col1_x) / sl_w)) * 3.5; return

        # ---------- COLONNA 2: NAVIGAZIONE/TRANS (ALLINEATO al render) ----------
        sy2 = ey + 85
        # FIT / 1:1
        if _in_rect((mx, my), (col2_x, sy2, bw2, 40)):
            self._img_editor_zoom = 1.0; self._img_editor_pan = [0, 0]; return
        if _in_rect((mx, my), (col2_x + bw2 + 6, sy2, bw2, 40)):
            self._img_editor_zoom = 2.0; return

        sy2 += 105  # ROTAZIONE
        if _in_rect((mx, my), (col2_x, sy2, bw2, 42)):
            self._img_editor_apply_rotation(90); return
        if _in_rect((mx, my), (col2_x + bw2 + 6, sy2, bw2, 42)):
            self._img_editor_apply_rotation(-90); return

        sy2 += 85  # AUTO TRIM
        if _in_rect((mx, my), (col2_x, sy2, 145, 40)):
            self._img_editor_auto_crop(); return

        sy2 += 75  # RIFLESSO
        if _in_rect((mx, my), (col2_x, sy2, bw2, 38)):
            self._img_editor_apply_flip(True, False); return
        if _in_rect((mx, my), (col2_x + bw2 + 6, sy2, bw2, 38)):
            self._img_editor_apply_flip(False, True); return

        sy2 += 75  # SMOOTH
        if _in_rect((mx, my), (col2_x, sy2, 145, 38)):
            self._img_editor_apply_smooth_edges(); return

        sy2 += 85  # HITBOX
        if _in_rect((mx, my), (col2_x, sy2, bw2, 38)):
            self._img_editor_asset_shape = "rect"; return
        if _in_rect((mx, my), (col2_x + bw2 + 6, sy2, bw2, 38)):
            self._img_editor_asset_shape = "circle"; return

        sy2 += 75  # RITAGLIO MANUALE
        if _in_rect((mx, my), (col2_x, sy2, bw2, 38)):
            # Toggle: ri-click sul bottone annulla il ritaglio in corso
            if self._img_editor_crop_mode: self._img_editor_cancel_crop()
            else: self._img_editor_crop_mode = True
            return
        if _in_rect((mx, my), (col2_x + bw2 + 6, sy2, bw2, 38)):
            if self._img_editor_crop_mode: self._img_editor_apply_crop()
            return

        # ---------- COLONNA 3: AI / DIMENSIONE / FILTRI / CONTORNO ----------
        # Geometria condivisa con il render tramite _img_editor_col3_rects
        r3 = self._img_editor_col3_rects(ex, ey, sb_x)
        if _in_rect((mx, my), r3["ai"]):
            self._img_editor_start_remove_bg(); return
        if self._img_editor_resize_edit:
            if _in_rect((mx, my), r3["dim_w"]):
                self._img_editor_resize_focus = "w"; return
            if _in_rect((mx, my), r3["dim_h"]):
                self._img_editor_resize_focus = "h"; return
        if _in_rect((mx, my), r3["dim_btn"]):
            if self._img_editor_resize_edit: self._img_editor_resize_apply()
            else: self._img_editor_resize_begin()
            return
        for f_key in ("sl_filt_b", "sl_filt_c", "sl_filt_s"):
            if _in_rect((mx, my), r3[f_key]):
                self._img_editor_dragging = f_key
                self._img_editor_filter_from_mouse(f_key, mx, r3[f_key])
                return
        if _in_rect((mx, my), r3["filt_apply"]):
            self._img_editor_apply_filters(); return
        if _in_rect((mx, my), r3["sl_outline"]):
            self._img_editor_dragging = "sl_outline"
            self._img_editor_outline_from_mouse(mx, r3["sl_outline"])
            return
        if _in_rect((mx, my), r3["out_white"]):
            self._img_editor_outline_color = "white"; return
        if _in_rect((mx, my), r3["out_black"]):
            self._img_editor_outline_color = "black"; return
        if _in_rect((mx, my), r3["out_apply"]):
            self._img_editor_apply_outline(); return

        if reset_confirm:
            self._img_editor_save_confirm = False
            self._img_editor_copy_confirm = False
            self._img_editor_exit_confirm = False

    def _img_editor_auto_crop(self):
        """Algoritmo di Trim Evoluto: Conservativo, ignora solo pixel isolati."""
        try:
            self._img_editor_push_undo()
            # Soglia molto bassa (2) come richiesto per essere meno aggressivo
            self._img_editor_view_surf = evolved_trim(self._img_editor_view_surf, noise_threshold=2)
            self._img_editor_crop = {"l": 0, "r": 0, "t": 0, "b": 0}
            self._img_editor_dirty = True
            self._img_editor_sync_orig_surf()
            final_w, final_h = self._img_editor_view_surf.get_size()
            self._status(f"Trim: {final_w}x{final_h}", OK_C, 2)
        except Exception as e:
            logging.error(f"[IMG_EDITOR] Trim failed: {e}"); self._status("Errore Trim", ERR_C, 2)

    def _img_editor_apply_smart_chroma(self, mode="green"):
        """Chroma Destroyer Pro v2."""
        self._img_editor_push_undo()
        surf = self._img_editor_view_surf
        w, h = surf.get_size()
        intensity = self._img_editor_chroma_intensity
        import pygame.surfarray as surfarray
        import numpy as np
        
        arr = surfarray.array3d(surf).astype(float)
        alpha = surfarray.array_alpha(surf).astype(float)
        r, g, b = arr[:,:,0], arr[:,:,1], arr[:,:,2]
        
        if mode == "green":
            score = g - (r * 0.6 + b * 0.4)
            threshold = 12 - (intensity * 10)
        elif mode == "white":
            score = (r + g + b) / 3.0
            threshold = 255 - (intensity * 40)
        elif mode == "black":
            score = 255 - ((r + g + b) / 3.0)
            threshold = 255 - (intensity * 40)
        else: score = np.zeros_like(r); threshold = 0

        mask_remove = score > threshold
        reduction = (score[mask_remove] - threshold) * (15.0 * intensity)
        alpha[mask_remove] -= reduction
        
        if mode == "green":
            spill_mask = (score > -5) & (alpha > 5)
            arr[spill_mask, 1] = np.minimum(arr[spill_mask, 1], np.maximum(r[spill_mask], b[spill_mask]))
        
        alpha = np.clip(alpha, 0, 255); arr = np.clip(arr, 0, 255)
        new_surf = pygame.Surface((w, h), pygame.SRCALPHA)
        surfarray.blit_array(new_surf, arr.astype(np.uint8))
        surfarray.pixels_alpha(new_surf)[:] = alpha.astype(np.uint8)
        self._img_editor_view_surf = new_surf; self._img_editor_dirty = True
        self._status(f"Rimosso {mode.upper()}", OK_C, 2)

    def _img_editor_apply_wand(self, mx, my, ix, iy, scale):
        rx = int((mx - ix) / scale); ry = int((my - iy) / scale)
        surf = self._img_editor_view_surf; w, h = surf.get_size()
        if not (0 <= rx < w and 0 <= ry < h): return
        target_color = surf.get_at((rx, ry))
        if target_color[3] < 5: return

        self._img_editor_push_undo()
        tol, feather = self._img_editor_wand_tol, self._img_editor_wand_feather
        to_process = []
        from collections import deque
        queue = deque([(rx, ry)]); visited = [False] * (w * h); visited[ry * w + rx] = True
        while queue:
            cx, cy = queue.popleft(); nc = surf.get_at((cx, cy))
            diff = max(abs(nc[0]-target_color[0]), abs(nc[1]-target_color[1]),
                       abs(nc[2]-target_color[2]))
            to_process.append((cx, cy, diff))
            for dx, dy in [(-1,0), (1,0), (0,-1), (0,1)]:
                nx, ny = cx + dx, cy + dy
                if 0 <= nx < w and 0 <= ny < h:
                    v_idx = ny * w + nx
                    if not visited[v_idx]:
                        nc_n = surf.get_at((nx, ny))
                        diff_n = max(abs(nc_n[0]-target_color[0]), abs(nc_n[1]-target_color[1]),
                                     abs(nc_n[2]-target_color[2]))
                        if diff_n <= tol + feather: visited[v_idx] = True; queue.append((nx, ny))

        for px, py, d in to_process:
            if d <= tol: surf.set_at((px, py), (0,0,0,0))
            else:
                f_ratio = (d - tol) / max(1, feather)
                orig_a = surf.get_at((px, py))[3]
                surf.set_at((px, py), (*surf.get_at((px, py))[:3], int(orig_a * f_ratio)))
        self._img_editor_dirty = True; self._status("Wand applicata", OK_C, 2)

    def _img_editor_apply_rotation(self, angle):
        self._img_editor_push_undo()
        self._img_editor_view_surf = pygame.transform.rotate(self._img_editor_view_surf, angle)
        self._img_editor_crop = {"l": 0, "r": 0, "t": 0, "b": 0}; self._img_editor_dirty = True
        self._img_editor_sync_orig_surf()

    def _img_editor_apply_flip(self, flip_h, flip_v):
        self._img_editor_push_undo()
        self._img_editor_view_surf = pygame.transform.flip(self._img_editor_view_surf, flip_h, flip_v)
        # Il ritaglio pendente segue il contenuto specchiato
        crop = self._img_editor_crop
        if flip_h: crop["l"], crop["r"] = crop["r"], crop["l"]
        if flip_v: crop["t"], crop["b"] = crop["b"], crop["t"]
        self._img_editor_dirty = True
        self._img_editor_sync_orig_surf()

    def _img_editor_sync_orig_surf(self) -> None:
        """
        Riallinea l'originale del Ripristina alla superficie corrente.
        Va chiamata dopo ogni operazione geometrica (rotate/flip/trim/crop):
        l'originale pre-operazione non sarebbe piu' allineato ai pixel.
        """
        self._img_editor_orig_surf = self._img_editor_view_surf.copy()

    def _img_editor_crop_handle_centers(
        self, ix: int, iy: int, scale: float
    ) -> dict[str, tuple[float, float]]:
        """Centri (in coordinate schermo) delle 4 maniglie di ritaglio."""
        iw, ih = self._img_editor_view_surf.get_size()
        crop = self._img_editor_crop
        x0 = ix + crop["l"] * scale
        x1 = ix + (iw - crop["r"]) * scale
        y0 = iy + crop["t"] * scale
        y1 = iy + (ih - crop["b"]) * scale
        cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
        return {"l": (x0, cy), "r": (x1, cy), "t": (cx, y0), "b": (cx, y1)}

    def _img_editor_crop_handle_at(
        self, mx: int, my: int, ix: int, iy: int, scale: float
    ) -> str | None:
        """
        Lato ("l"/"r"/"t"/"b") della maniglia sotto il mouse, se presente.
        Se piu' maniglie si sovrappongono (immagine piccola/zoom basso)
        vince quella con il centro piu' vicino al mouse.
        """
        half = CROP_HANDLE_HIT / 2.0
        best_side, best_d2 = None, None
        for side, (hx, hy) in self._img_editor_crop_handle_centers(ix, iy, scale).items():
            if abs(mx - hx) <= half and abs(my - hy) <= half:
                d2 = (mx - hx) ** 2 + (my - hy) ** 2
                if best_d2 is None or d2 < best_d2:
                    best_side, best_d2 = side, d2
        return best_side

    def _img_editor_crop_drag(self, mx: int, my: int, ix: int, iy: int, scale: float) -> None:
        """Aggiorna il crop trascinando una maniglia (schermo -> spazio immagine)."""
        iw, ih = self._img_editor_view_surf.get_size()
        crop = self._img_editor_crop
        px = (mx - ix) / scale
        py = (my - iy) / scale
        side = self._img_editor_dragging.rsplit("_", 1)[1]
        if side == "l":
            crop["l"] = max(0, min(int(round(px)), iw - crop["r"] - CROP_MIN_KEEP))
        elif side == "r":
            crop["r"] = max(0, min(int(round(iw - px)), iw - crop["l"] - CROP_MIN_KEEP))
        elif side == "t":
            crop["t"] = max(0, min(int(round(py)), ih - crop["b"] - CROP_MIN_KEEP))
        elif side == "b":
            crop["b"] = max(0, min(int(round(ih - py)), ih - crop["t"] - CROP_MIN_KEEP))

    def _img_editor_apply_crop(self) -> None:
        """Ritaglia subito la superficie con il crop corrente (con undo)."""
        if not any(self._img_editor_crop.values()):
            self._img_editor_crop_mode = False
            return
        self._img_editor_push_undo()
        self._img_editor_view_surf = self._img_editor_compose_final_surf()
        self._img_editor_crop = {"l": 0, "r": 0, "t": 0, "b": 0}
        self._img_editor_crop_mode = False
        self._img_editor_dirty = True
        self._img_editor_sync_orig_surf()
        w, h = self._img_editor_view_surf.get_size()
        self._status(f"Ritaglio applicato: {w}x{h}", OK_C, 2)

    def _img_editor_cancel_crop(self) -> None:
        """Annulla il ritaglio manuale in corso (maniglie e modalita')."""
        self._img_editor_crop = {"l": 0, "r": 0, "t": 0, "b": 0}
        self._img_editor_crop_mode = False

    def _img_editor_clamp_crop(self) -> None:
        """Riporta il crop nei limiti della superficie corrente (dopo undo/redo)."""
        iw, ih = self._img_editor_view_surf.get_size()
        crop = self._img_editor_crop
        crop["l"] = max(0, min(crop["l"], iw - CROP_MIN_KEEP))
        crop["r"] = max(0, min(crop["r"], iw - crop["l"] - CROP_MIN_KEEP))
        crop["t"] = max(0, min(crop["t"], ih - CROP_MIN_KEEP))
        crop["b"] = max(0, min(crop["b"], ih - crop["t"] - CROP_MIN_KEEP))

    def _img_editor_apply_smooth_edges(self):
        try:
            self._img_editor_push_undo()
            import pygame.surfarray as surfarray; import numpy as np; from scipy.ndimage import gaussian_filter
            alpha = surfarray.array_alpha(self._img_editor_view_surf).astype(float)
            alpha_smooth = gaussian_filter(alpha, sigma=0.6)
            surfarray.pixels_alpha(self._img_editor_view_surf)[:] = alpha_smooth.astype(np.uint8)
            self._img_editor_dirty = True; self._status("Bordi Ammorbiditi", OK_C, 2)
        except Exception: self._status("Smooth non disponibile", WARN_C, 2)

    def _img_editor_col3_rects(self, ex: int, ey: int, sb_x: int) -> dict[str, pygame.Rect]:
        """
        Geometria della colonna 3 della sidebar (AI, dimensione, filtri,
        contorno). Sorgente unica condivisa da click, drag e render: ogni
        controllo nuovo va aggiunto SOLO qui.
        """
        col3_x = sb_x + COL3_X_OFF
        sl_w = 145
        bw2 = (sl_w // 2) - 3
        return {
            # SFONDO AI
            "ai": pygame.Rect(col3_x, ey + 85, sl_w, 40),
            # DIMENSIONE: campi W/H (solo in edit) + bottone
            "dim_w": pygame.Rect(col3_x, ey + 160, bw2, 32),
            "dim_h": pygame.Rect(col3_x + bw2 + 6, ey + 160, bw2, 32),
            "dim_btn": pygame.Rect(col3_x, ey + 200, sl_w, 36),
            # FILTRI: 3 slider + applica
            "sl_filt_b": pygame.Rect(col3_x, ey + 292, sl_w, 18),
            "sl_filt_c": pygame.Rect(col3_x, ey + 334, sl_w, 18),
            "sl_filt_s": pygame.Rect(col3_x, ey + 376, sl_w, 18),
            "filt_apply": pygame.Rect(col3_x, ey + 404, sl_w, 34),
            # CONTORNO: spessore + colore + applica
            "sl_outline": pygame.Rect(col3_x, ey + 486, sl_w, 18),
            "out_white": pygame.Rect(col3_x, ey + 514, bw2, 30),
            "out_black": pygame.Rect(col3_x + bw2 + 6, ey + 514, bw2, 30),
            "out_apply": pygame.Rect(col3_x, ey + 550, sl_w, 34),
        }

    def _img_editor_start_remove_bg(self) -> None:
        """
        Avvia la rimozione sfondo AI (rembg, policy di progetto: vedi
        docs/assets/IMAGE_PROCESSING_GUIDELINES.md) in un thread separato.
        Il primo uso puo' scaricare i pesi U2-Net: il modale mostra lo stato
        di busy e il risultato viene applicato nel loop principale.
        """
        if self._img_editor_busy:
            return
        try:
            import rembg  # Lazy: dipendenza opzionale, non nei requirements
        except ImportError:
            self._status("rembg non installato", WARN_C, 3)
            return
        try:
            from PIL import Image  # Lazy: arriva con rembg ma verifichiamo
        except ImportError:
            self._status("Pillow non installato", WARN_C, 3)
            return

        raw = pygame.image.tobytes(self._img_editor_view_surf, "RGBA")
        size = self._img_editor_view_surf.get_size()
        token = self._img_editor_ai_token
        self._img_editor_busy = True
        self._img_editor_ai_result = None
        self._img_editor_ai_error = None
        self._status("Rimozione sfondo AI in corso...", ACCENT, 2)

        def worker() -> None:
            # Nel worker si toccano solo bytes: niente Surface fuori dal main loop
            try:
                pil_img = Image.frombytes("RGBA", size, raw)
                out = rembg.remove(pil_img).convert("RGBA")
                self._img_editor_ai_result = (token, out.tobytes(), out.size)
            except Exception as exc:
                logging.error(f"[IMG_EDITOR] rembg fallito: {exc}")
                self._img_editor_ai_error = (token, str(exc))

        threading.Thread(target=worker, daemon=True, name="img_editor_rembg").start()

    def _img_editor_poll_ai(self) -> None:
        """
        Applica nel loop principale (render) il risultato del thread rembg.
        I risultati con token diverso appartengono a sessioni chiuse: scartati.
        """
        err = self._img_editor_ai_error
        if err is not None:
            self._img_editor_ai_error = None
            if err[0] == self._img_editor_ai_token:
                self._img_editor_busy = False
                self._status(f"Errore rembg: {err[1]}", ERR_C, 4)
            return
        res = self._img_editor_ai_result
        if res is None:
            return
        self._img_editor_ai_result = None
        token, raw, size = res
        if token != self._img_editor_ai_token:
            return  # Risultato di una sessione precedente
        self._img_editor_busy = False
        new_surf = pygame.image.frombuffer(raw, size, "RGBA").convert_alpha()
        self._img_editor_push_undo()
        self._img_editor_view_surf = new_surf
        self._img_editor_dirty = True
        self._status("Sfondo rimosso (AI)", OK_C, 2)

    def _img_editor_resize_begin(self) -> None:
        """Apre il mini-prompt inline W/H precompilato con le dimensioni attuali."""
        w, h = self._img_editor_view_surf.get_size()
        self._img_editor_resize_edit = True
        self._img_editor_resize_w = str(w)
        self._img_editor_resize_h = str(h)
        self._img_editor_resize_focus = "w"

    def _img_editor_resize_sync(self, edited: str) -> None:
        """Ricalcola il campo complementare mantenendo l'aspect ratio."""
        w, h = self._img_editor_view_surf.get_size()
        src = self._img_editor_resize_w if edited == "w" else self._img_editor_resize_h
        if not src.isdigit():
            return
        if edited == "w":
            _, new_h = aspect_resize_dims(w, h, target_w=int(src))
            self._img_editor_resize_h = str(new_h)
        else:
            new_w, _ = aspect_resize_dims(w, h, target_h=int(src))
            self._img_editor_resize_w = str(new_w)

    def _img_editor_resize_keydown(self, ev: pygame.event.Event) -> None:
        """Editing da tastiera dei campi W/H: cifre, Backspace, Tab, Invio, Esc."""
        focus = self._img_editor_resize_focus
        attr = "_img_editor_resize_w" if focus == "w" else "_img_editor_resize_h"
        cur = getattr(self, attr)
        if ev.key == pygame.K_ESCAPE:
            self._img_editor_resize_edit = False
        elif ev.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            self._img_editor_resize_apply()
        elif ev.key == pygame.K_TAB:
            self._img_editor_resize_focus = "h" if focus == "w" else "w"
        elif ev.key == pygame.K_BACKSPACE:
            setattr(self, attr, cur[:-1])
            self._img_editor_resize_sync(focus)
        elif ev.unicode.isdigit() and len(cur) < RESIZE_FIELD_MAX_CHARS:
            setattr(self, attr, cur + ev.unicode)
            self._img_editor_resize_sync(focus)

    def _img_editor_resize_apply(self) -> None:
        """Applica il ridimensionamento numerico mantenendo l'aspect ratio."""
        w, h = self._img_editor_view_surf.get_size()
        if self._img_editor_resize_w.isdigit():
            new_w, new_h = aspect_resize_dims(w, h, target_w=int(self._img_editor_resize_w))
        elif self._img_editor_resize_h.isdigit():
            new_w, new_h = aspect_resize_dims(w, h, target_h=int(self._img_editor_resize_h))
        else:
            self._status("Dimensione non valida", WARN_C, 2)
            return
        self._img_editor_resize_edit = False
        if (new_w, new_h) == (w, h):
            return
        self._img_editor_push_undo()
        self._img_editor_view_surf = pygame.transform.smoothscale(
            self._img_editor_view_surf, (new_w, new_h))
        # Il crop pendente non e' piu' riferibile ai nuovi pixel
        self._img_editor_crop = {"l": 0, "r": 0, "t": 0, "b": 0}
        self._img_editor_dirty = True
        self._img_editor_sync_orig_surf()
        self._status(f"Ridimensionato: {new_w}x{new_h}", OK_C, 2)

    def _img_editor_filter_from_mouse(self, key: str, mx: int, sl_rect: pygame.Rect) -> None:
        """Aggiorna il filtro colore associato allo slider (key = sl_filt_b/c/s)."""
        ratio = max(0.0, min(1.0, (mx - sl_rect.x) / sl_rect.w))
        val = int(round(FILTER_MIN + ratio * (FILTER_MAX - FILTER_MIN)))
        self._img_editor_filters[key.rsplit("_", 1)[1]] = val

    def _img_editor_outline_from_mouse(self, mx: int, sl_rect: pygame.Rect) -> None:
        """Aggiorna lo spessore del contorno dallo slider dedicato."""
        ratio = max(0.0, min(1.0, (mx - sl_rect.x) / sl_rect.w))
        self._img_editor_outline_px = int(
            round(OUTLINE_MIN_PX + ratio * (OUTLINE_MAX_PX - OUTLINE_MIN_PX)))

    def _img_editor_apply_filters(self) -> None:
        """Rende permanenti i filtri colore in anteprima e azzera gli slider."""
        filt = self._img_editor_filters
        if not (filt["b"] or filt["c"] or filt["s"]):
            self._status("Filtri a zero: nulla da applicare", WARN_C, 2)
            return
        self._img_editor_push_undo()
        apply_color_adjust_surface(
            self._img_editor_view_surf, filt["b"], filt["c"], filt["s"])
        self._img_editor_filters = {"b": 0, "c": 0, "s": 0}
        self._img_editor_dirty = True
        self._status("Filtri applicati", OK_C, 2)

    def _img_editor_apply_outline(self) -> None:
        """Aggiunge un contorno uniforme attorno alla silhouette alpha."""
        surf = self._img_editor_view_surf
        alpha = pygame.surfarray.array_alpha(surf)
        ring = outline_ring(alpha, self._img_editor_outline_px)
        if not ring.any():
            self._status("Nessuna silhouette da contornare", WARN_C, 2)
            return
        self._img_editor_push_undo()
        color = OUTLINE_COLORS[self._img_editor_outline_color]
        rgb = pygame.surfarray.pixels3d(surf)
        rgb[ring] = color
        del rgb
        alpha_px = pygame.surfarray.pixels_alpha(surf)
        alpha_px[ring] = 255
        del alpha_px
        self._img_editor_dirty = True
        self._status(f"Contorno {self._img_editor_outline_px}px applicato", OK_C, 2)

    def _img_editor_drag(self, mx, my):
        ex, ey, ew, eh = self._img_editor_get_modal_rect()
        sb_w = SIDEBAR_W
        sb_x = ex + ew - sb_w - 15
        col1_x = sb_x + 10  # ALLINEATO al render
        sl_w = 145

        if self._img_editor_dragging in ("eraser_active", "eraser"):
            ix, iy, sw, sh, scale = self._img_editor_get_img_layout(ew, eh, ex, ey)
            self._img_editor_erase(mx, my, ix, iy, scale)
        elif self._img_editor_dragging in ("crop_l", "crop_r", "crop_t", "crop_b"):
            ix, iy, sw, sh, scale = self._img_editor_get_img_layout(ew, eh, ex, ey)
            self._img_editor_crop_drag(mx, my, ix, iy, scale)
        elif self._img_editor_dragging == "sl_radius":
            self._img_editor_eraser_r = int(1 + max(0, min(1, (mx - col1_x) / sl_w)) * 63)
        elif self._img_editor_dragging == "sl_hardness":
            self._img_editor_eraser_hardness = max(0, min(1, (mx - col1_x) / sl_w))
        elif self._img_editor_dragging == "sl_opacity":
            self._img_editor_eraser_opacity = max(0, min(1, (mx - col1_x) / sl_w))
        elif self._img_editor_dragging == "sl_tol":
            self._img_editor_wand_tol = int(max(0, min(1, (mx - col1_x) / sl_w)) * 128)
        elif self._img_editor_dragging == "sl_feather":
            self._img_editor_wand_feather = int(max(0, min(1, (mx - col1_x) / sl_w)) * 32)
        elif self._img_editor_dragging == "sl_chroma":
            self._img_editor_chroma_intensity = 0.5 + max(0, min(1, (mx - col1_x) / sl_w)) * 3.5
        elif self._img_editor_dragging in ("sl_filt_b", "sl_filt_c", "sl_filt_s"):
            r3 = self._img_editor_col3_rects(ex, ey, sb_x)
            self._img_editor_filter_from_mouse(
                self._img_editor_dragging, mx, r3[self._img_editor_dragging])
        elif self._img_editor_dragging == "sl_outline":
            r3 = self._img_editor_col3_rects(ex, ey, sb_x)
            self._img_editor_outline_from_mouse(mx, r3["sl_outline"])

    def _img_editor_erase(self, mx: int, my: int, ix: int, iy: int, scale: float) -> None:
        """Pennello morbido interpolato: gomma (cancella alpha) o Ripristina."""
        if self._img_editor_dragging != "eraser_active":
            self._img_editor_push_undo()
            self._img_editor_dragging = "eraser_active"

        rx = (mx - ix) / scale
        ry = (my - iy) / scale
        r = float(self._img_editor_eraser_r)
        hardness = self._img_editor_eraser_hardness
        opacity = self._img_editor_eraser_opacity
        shape = self._img_editor_shape

        # Interpolazione tra l'ultima posizione e quella attuale
        points = [(rx, ry)]
        if self._img_editor_last_m is not None:
            lx, ly = self._img_editor_last_m
            dist = math.hypot(rx - lx, ry - ly)
            step_dist = max(0.5, r / 4.0)
            if dist > step_dist:
                steps = int(dist / step_dist)
                for i in range(1, steps + 1):
                    f = i / steps
                    points.append((lx + (rx - lx) * f, ly + (ry - ly) * f))
        self._img_editor_last_m = (rx, ry)

        # Cache del pennello per i parametri correnti
        ri = max(1, int(round(r)))
        brush_key = (shape, ri, int(hardness * 100), int(opacity * 100))

        if self._img_editor_tool == "restore":
            # Il pennello ricopia i pixel RGBA dall'immagine originale.
            if (self._img_editor_orig_surf is None
                    or self._img_editor_orig_surf.get_size()
                    != self._img_editor_view_surf.get_size()):
                # Undo/redo possono disallineare le dimensioni: risincronizza
                self._img_editor_sync_orig_surf()
            if brush_key not in self._img_editor_restore_cache:
                strength = brush_power_map(shape, ri, hardness) * opacity
                self._img_editor_restore_cache[brush_key] = strength
            strength = self._img_editor_restore_cache[brush_key]
            for px, py in points:
                restore_stamp(
                    self._img_editor_view_surf, self._img_editor_orig_surf,
                    (int(round(px)) - ri, int(round(py)) - ri), strength,
                )
            self._img_editor_dirty = True
            return

        if brush_key not in self._img_editor_brush_cache:
            import numpy as np
            size = ri * 2 + 1
            erase_power = brush_power_map(shape, ri, hardness)
            alpha_brush = (255.0 * (1.0 - erase_power * opacity)).astype(np.uint8)

            # Brush con RGB=255 (per non sporcare i canali RGB con BLEND_RGBA_MIN)
            bs_surf = pygame.Surface((size, size), pygame.SRCALPHA)
            bs_surf.fill((255, 255, 255, 255))
            arr_a = pygame.surfarray.pixels_alpha(bs_surf)
            arr_a[:] = alpha_brush
            del arr_a
            self._img_editor_brush_cache[brush_key] = bs_surf

        brush_surf = self._img_editor_brush_cache[brush_key]
        for px, py in points:
            bx = int(round(px)) - ri
            by = int(round(py)) - ri
            self._img_editor_view_surf.blit(brush_surf, (bx, by), special_flags=pygame.BLEND_RGBA_MIN)

        self._img_editor_dirty = True

    def _img_editor_push_undo(self) -> None:
        self._img_editor_undo_stack.append(self._img_editor_view_surf.copy())
        if len(self._img_editor_undo_stack) > UNDO_STACK_CAP:
            self._img_editor_undo_stack.pop(0)
        # Ogni nuova operazione invalida la cronologia di redo
        self._img_editor_redo_stack.clear()

    def _img_editor_undo(self) -> None:
        if not self._img_editor_undo_stack: return
        self._img_editor_redo_stack.append(self._img_editor_view_surf)
        if len(self._img_editor_redo_stack) > UNDO_STACK_CAP:
            self._img_editor_redo_stack.pop(0)
        self._img_editor_view_surf = self._img_editor_undo_stack.pop()
        self._img_editor_clamp_crop()
        self._img_editor_dirty = True

    def _img_editor_redo(self) -> None:
        if not self._img_editor_redo_stack: return
        self._img_editor_undo_stack.append(self._img_editor_view_surf)
        if len(self._img_editor_undo_stack) > UNDO_STACK_CAP:
            self._img_editor_undo_stack.pop(0)
        self._img_editor_view_surf = self._img_editor_redo_stack.pop()
        self._img_editor_clamp_crop()
        self._img_editor_dirty = True

    def _r_img_editor_modal(self, w, h):
        if not self._img_editor_active: return
        # Applica eventuale risultato del thread rembg nel loop principale
        self._img_editor_poll_ai()
        dim = pygame.Surface((w, h), pygame.SRCALPHA); dim.fill((0, 0, 0, 215)); self.screen.blit(dim, (0, 0))
        
        # Responsive Modal Size (Liquida & Studio-Grade)
        ew = int(min(w * 0.94, 1280))
        eh = int(min(h * 0.90, 820))
        ex, ey = (w - ew) // 2, (h - eh) // 2
        
        box = pygame.Rect(ex, ey, ew, eh)
        _rect(self.screen, (25, 25, 30), box, radius=18)
        _rect(self.screen, ACCENT, box, 1, radius=18)
        
        mx, my = pygame.mouse.get_pos()
        _draw_text(self.screen, f"STUDIO ASSET: {self._img_editor_id}", "lg", TXT_HI, ex + 30, ey + 25)
        
        # Calcolo layout base con supporto Auto-Fit
        ix, iy, sw, sh, scale = self._img_editor_get_img_layout(ew, eh, ex, ey)
        if self._img_editor_zoom == 0.0:
            self._img_editor_zoom = 1.0
            self._img_editor_pan = [0, 0]
            ix, iy, sw, sh, scale = self._img_editor_get_img_layout(ew, eh, ex, ey)
        
        # Area Lavoro
        pygame.draw.rect(self.screen, (10, 10, 15), (ix-2, iy-2, sw+4, sh+4), border_radius=6)
        if self._img_editor_bg_mode == "check":
            cs = 20
            for cx in range(ix, ix + sw, cs):
                for cy in range(iy, iy + sh, cs):
                    col = (32, 32, 38) if ((cx-ix)//cs + (cy-iy)//cs) % 2 == 0 else (48, 48, 54)
                    pygame.draw.rect(self.screen, col, (cx, cy, min(cs, ix+sw-cx), min(cs, iy+sh-cy)))
        elif self._img_editor_bg_mode == "black": pygame.draw.rect(self.screen, (5, 5, 5), (ix, iy, sw, sh))
        else: pygame.draw.rect(self.screen, (248, 248, 248), (ix, iy, sw, sh))

        # Tasto Background (Spostato per non sovrapporre la tela)
        bg_r = pygame.Rect(ex + ew - 110, ey + 25, 80, 32)
        _button(self.screen, bg_r, f" {self._img_editor_bg_mode.upper()}", _in_rect((mx, my), bg_r))

        # Anteprima live dei filtri colore: applicata sul lato piu' economico
        # (nativo o scalato), senza mai toccare la superficie di lavoro.
        filt = self._img_editor_filters
        filt_on = bool(filt["b"] or filt["c"] or filt["s"])
        src_surf = self._img_editor_view_surf
        nat_w, nat_h = src_surf.get_size()
        if filt_on and nat_w * nat_h <= sw * sh:
            src_surf = src_surf.copy()
            apply_color_adjust_surface(src_surf, filt["b"], filt["c"], filt["s"])
        if scale >= 1.0: scaled_img = pygame.transform.scale(src_surf, (sw, sh))
        else: scaled_img = pygame.transform.smoothscale(src_surf, (sw, sh))
        if filt_on and nat_w * nat_h > sw * sh:
            apply_color_adjust_surface(scaled_img, filt["b"], filt["c"], filt["s"])
        self.screen.blit(scaled_img, (ix, iy))
        
        # Overlay Hitbox (per precisione chirurgica)
        hb_col = (0, 255, 255, 120)
        if self._img_editor_asset_shape == "rect":
            pygame.draw.rect(self.screen, hb_col, (ix, iy, sw, sh), 2)
        else:
            pygame.draw.circle(self.screen, hb_col, (ix + sw//2, iy + sh//2), min(sw, sh)//2, 2)

        if scale > 8.0:
            gs = pygame.Surface((sw, sh), pygame.SRCALPHA)
            for gx in range(0, sw+1, int(scale)): pygame.draw.line(gs, (100,100,100,50), (gx,0), (gx,sh))
            for gy in range(0, sh+1, int(scale)): pygame.draw.line(gs, (100,100,100,50), (0,gy), (sw,gy))
            self.screen.blit(gs, (ix, iy))

        # Ritaglio manuale: overlay zone escluse + maniglie
        if self._img_editor_crop_mode:
            self._r_img_editor_crop_overlay(ix, iy, sw, sh, scale)

        # Indicatore di busy AI: overlay sul canvas (clippato all'area di lavoro)
        if self._img_editor_busy:
            work_r = pygame.Rect(ex + 25, ey + 70, ew - SIDEBAR_W - 60, eh - 150)
            clip_r = pygame.Rect(ix, iy, sw, sh).clip(work_r)
            if clip_r.w > 0 and clip_r.h > 0:
                busy_ov = pygame.Surface(clip_r.size, pygame.SRCALPHA)
                busy_ov.fill((0, 0, 0, BUSY_OVERLAY_ALPHA))
                self.screen.blit(busy_ov, clip_r.topleft)
                dots = "." * (1 + (pygame.time.get_ticks() // BUSY_DOT_MS) % 3)
                b_msg = "Elaborazione" + dots
                b_w, b_h = _text_wh(b_msg, "lg")
                _draw_text(self.screen, b_msg, "lg", TXT_HI,
                           clip_r.x + (clip_r.w - b_w) // 2,
                           clip_r.y + (clip_r.h - b_h) // 2)

        # HUD Technical Data — collocato nell'header per non sovrapporsi MAI al footer.
        if _in_rect((mx, my), (ix, iy, sw, sh)):
            rx = int((mx - ix) / scale); ry = int((my - iy) / scale)
            iw, ih = self._img_editor_view_surf.get_size()
            if 0 <= rx < iw and 0 <= ry < ih:
                c = self._img_editor_view_surf.get_at((rx, ry))
                hud_txt = f"X:{rx}  Y:{ry}  |  RGBA: {c[0]},{c[1]},{c[2]},{c[3]}"
                # ancorato a destra della title bar, a sinistra del toggle BG
                _draw_text(self.screen, hud_txt, "sm", TXT_DIM, ex + 320, ey + 32)

        # SIDEBAR (3 colonne)
        sb_w = SIDEBAR_W
        sb_x = ex + ew - sb_w - 15
        col1_x, col2_x = sb_x + 10, sb_x + 165
        
        # Strumenti (gomma, ripristina dall'originale, bacchetta)
        _draw_text(self.screen, "PENNELLI", "sm", TXT_DIM, col1_x, ey + 60)
        sy = ey + 85
        tools = [("eraser", "eraser"), ("restore", "brush"), ("wand", "wand")]
        for i, (tid, ico) in enumerate(tools):
            tr = pygame.Rect(col1_x + i * TOOL_BTN_STEP, sy, TOOL_BTN_SIZE, TOOL_BTN_SIZE)
            act = (self._img_editor_tool == tid)
            _button(self.screen, tr, "", _in_rect((mx, my), tr), active=act)
            self._r_blit_icon(ico, tr, active=act)
            
        for i, (sid, ico) in enumerate([("round", "circle_p"), ("square", "square_p")]):
            fr = pygame.Rect(col1_x + i*60, sy + 65, 52, 52); act = (self._img_editor_shape == sid)
            _button(self.screen, fr, "", _in_rect((mx, my), fr), active=act)
            self._r_blit_icon(ico, fr, active=act)
                  
        # Pennello (impostazioni condivise da gomma e ripristina)
        sy_sl = ey + 255
        sl_w = 145
        if self._img_editor_tool in ("eraser", "restore"):
            _draw_text(self.screen, f"RAGGIO: {self._img_editor_eraser_r}px", "sm", TXT_HI, col1_x, sy_sl - 25)
            _slider(self.screen, (col1_x, sy_sl, sl_w, 20), (self._img_editor_eraser_r - 1) / 63, 0, 1)
            _draw_text(self.screen, f"DUREZZA: {int(self._img_editor_eraser_hardness*100)}%", "sm", TXT_DIM, col1_x, sy_sl + 45)
            _slider(self.screen, (col1_x, sy_sl + 70, sl_w, 20), self._img_editor_eraser_hardness, 0, 1)
            _draw_text(self.screen, f"OPACITÀ: {int(self._img_editor_eraser_opacity*100)}%", "sm", TXT_DIM, col1_x, sy_sl + 115)
            _slider(self.screen, (col1_x, sy_sl + 140, sl_w, 20), self._img_editor_eraser_opacity, 0, 1)
            sy_ch = sy_sl + 195
        else:
            _draw_text(self.screen, f"TOLLERANZA: {self._img_editor_wand_tol}", "sm", TXT_HI, col1_x, sy_sl - 25)
            _slider(self.screen, (col1_x, sy_sl, sl_w, 20), self._img_editor_wand_tol / 128, 0, 1)
            _draw_text(self.screen, f"SFUMATURA: {self._img_editor_wand_feather}", "sm", TXT_HI, col1_x, sy_sl + 45)
            _slider(self.screen, (col1_x, sy_sl + 70, sl_w, 20), self._img_editor_wand_feather / 32, 0, 1)
            sy_ch = sy_sl + 195
            
        _draw_text(self.screen, "CHROMA REMOVER", "sm", TXT_DIM, col1_x, sy_ch - 25)
        for i, (m, c) in enumerate([("G", (0, 200, 0)), ("W", (230, 230, 230)), ("B", (40, 40, 40))]):
            tr_c = pygame.Rect(col1_x + i*50, sy_ch, 45, 40)
            _button(self.screen, tr_c, m, _in_rect((mx, my), tr_c))
        _draw_text(self.screen, f"INTENSITÀ: {self._img_editor_chroma_intensity:.1f}", "sm", TXT_DIM, col1_x, sy_ch + 75)
        _slider(self.screen, (col1_x, sy_ch + 100, sl_w, 20), (self._img_editor_chroma_intensity - 0.5) / 3.5, 0, 1)

        # Colonna 2 (Zoom & Trans)
        _draw_text(self.screen, "NAVIGAZIONE", "sm", TXT_DIM, col2_x, ey + 60)
        sy2 = ey + 85; bw2 = (sl_w // 2) - 3
        r_f, r_1 = pygame.Rect(col2_x, sy2, bw2, 40), pygame.Rect(col2_x + bw2 + 6, sy2, bw2, 40)
        _button(self.screen, r_f, "    FIT", _in_rect((mx, my), r_f))
        self._r_blit_icon("zoom_fit", pygame.Rect(r_f.x+4, r_f.y, 25, 40), active=_in_rect((mx, my), r_f))
        _button(self.screen, r_1, "    1:1", _in_rect((mx, my), r_1))
        self._r_blit_icon("zoom_100", pygame.Rect(r_1.x+4, r_1.y, 25, 40), active=_in_rect((mx, my), r_1))
        
        sy2 += 105; _draw_text(self.screen, "ROTAZIONE", "sm", TXT_DIM, col2_x, sy2 - 25)
        r_l, r_r = pygame.Rect(col2_x, sy2, bw2, 42), pygame.Rect(col2_x + bw2 + 6, sy2, bw2, 42)
        _button(self.screen, r_l, "", _in_rect((mx, my), r_l)); self._r_blit_icon("undo", r_l, active=_in_rect((mx, my), r_l))
        _button(self.screen, r_r, "", _in_rect((mx, my), r_r)); self._r_blit_icon("rotate_cw", r_r, active=_in_rect((mx, my), r_r))
        
        sy2 += 85; _draw_text(self.screen, "AUTOMAZIONE", "sm", TXT_DIM, col2_x, sy2 - 25)
        r_at = pygame.Rect(col2_x, sy2, 145, 40)
        _button(self.screen, r_at, "      AUTO TRIM", _in_rect((mx, my), r_at))
        self._r_blit_icon("crop", pygame.Rect(r_at.x+6, r_at.y, 25, 40), active=_in_rect((mx, my), r_at))
        
        sy2 += 75; _draw_text(self.screen, "RIFLESSO", "sm", TXT_DIM, col2_x, sy2 - 25)
        r_fh, r_fv = pygame.Rect(col2_x, sy2, bw2, 38), pygame.Rect(col2_x + bw2 + 6, sy2, bw2, 38)
        _button(self.screen, r_fh, "   HORZ", _in_rect((mx, my), r_fh))
        self._r_blit_icon("flip_h", pygame.Rect(r_fh.x+3, r_fh.y, 25, 38), active=_in_rect((mx, my), r_fh))
        _button(self.screen, r_fv, "   VRT", _in_rect((mx, my), r_fv))
        self._r_blit_icon("flip_v", pygame.Rect(r_fv.x+3, r_fv.y, 25, 38), active=_in_rect((mx, my), r_fv))
        
        sy2 += 75; r_sm = pygame.Rect(col2_x, sy2, 145, 38)
        _button(self.screen, r_sm, "      SMOOTH", _in_rect((mx, my), r_sm))
        self._r_blit_icon("smooth", pygame.Rect(r_sm.x+6, r_sm.y, 25, 38), active=_in_rect((mx, my), r_sm))
        
        sy2 += 85; _draw_text(self.screen, "HITBOX", "sm", TXT_DIM, col2_x, sy2 - 25)
        r_re, r_ci = pygame.Rect(col2_x, sy2, bw2, 38), pygame.Rect(col2_x + bw2 + 6, sy2, bw2, 38)
        _button(self.screen, r_re, "RECT", _in_rect((mx, my), r_re), active=(self._img_editor_asset_shape=="rect"))
        _button(self.screen, r_ci, "CIRC", _in_rect((mx, my), r_ci), active=(self._img_editor_asset_shape=="circle"))

        # Ritaglio manuale (ALLINEATO al click: sy2 += 75)
        sy2 += 75; _draw_text(self.screen, "RITAGLIO", "sm", TXT_DIM, col2_x, sy2 - 25)
        r_cm = pygame.Rect(col2_x, sy2, bw2, 38)
        r_ca = pygame.Rect(col2_x + bw2 + 6, sy2, bw2, 38)
        _button(self.screen, r_cm, "RITAGLIA", _in_rect((mx, my), r_cm),
                active=self._img_editor_crop_mode)
        can_apply = self._img_editor_crop_mode and any(self._img_editor_crop.values())
        _button(self.screen, r_ca, "APPLICA", _in_rect((mx, my), r_ca) and can_apply)

        # Colonna 3 (AI / Dimensione / Filtri / Contorno)
        # Geometria condivisa con il click tramite _img_editor_col3_rects
        r3 = self._img_editor_col3_rects(ex, ey, sb_x)
        col3_x = r3["ai"].x
        busy = self._img_editor_busy

        _draw_text(self.screen, "SFONDO AI", "sm", TXT_DIM, col3_x, ey + 60)
        ai_label = "ELABORAZIONE..." if busy else "RIMUOVI SFONDO"
        _button(self.screen, r3["ai"], ai_label,
                _in_rect((mx, my), r3["ai"]) and not busy, active=busy)

        _draw_text(self.screen, "DIMENSIONE", "sm", TXT_DIM, col3_x, r3["dim_w"].y - 25)
        if self._img_editor_resize_edit:
            _input_box(self.screen, r3["dim_w"], self._img_editor_resize_w,
                       focused=(self._img_editor_resize_focus == "w"), hint="W", font="sm")
            _input_box(self.screen, r3["dim_h"], self._img_editor_resize_h,
                       focused=(self._img_editor_resize_focus == "h"), hint="H", font="sm")
            _button(self.screen, r3["dim_btn"], "APPLICA", _in_rect((mx, my), r3["dim_btn"]))
        else:
            vw, vh = self._img_editor_view_surf.get_size()
            _draw_text(self.screen, f"{vw} x {vh} px", "sm", TXT_HI,
                       col3_x, r3["dim_w"].y + 8)
            _button(self.screen, r3["dim_btn"], "RIDIMENSIONA",
                    _in_rect((mx, my), r3["dim_btn"]))

        _draw_text(self.screen, "FILTRI", "sm", TXT_DIM, col3_x, r3["sl_filt_b"].y - 42)
        f_range = FILTER_MAX - FILTER_MIN
        filt3 = self._img_editor_filters
        for f_name, f_key in (("LUMINOSITÀ", "b"), ("CONTRASTO", "c"), ("SATURAZIONE", "s")):
            f_rect = r3["sl_filt_" + f_key]
            _draw_text(self.screen, f"{f_name}: {filt3[f_key]:+d}", "xs", TXT_DIM,
                       col3_x, f_rect.y - 16)
            _slider(self.screen, f_rect, (filt3[f_key] - FILTER_MIN) / f_range, 0, 1)
        filt3_on = bool(filt3["b"] or filt3["c"] or filt3["s"])
        _button(self.screen, r3["filt_apply"], "APPLICA FILTRI",
                _in_rect((mx, my), r3["filt_apply"]), active=filt3_on)

        _draw_text(self.screen, "CONTORNO", "sm", TXT_DIM, col3_x, r3["sl_outline"].y - 42)
        _draw_text(self.screen, f"SPESSORE: {self._img_editor_outline_px}px", "xs", TXT_DIM,
                   col3_x, r3["sl_outline"].y - 16)
        o_range = OUTLINE_MAX_PX - OUTLINE_MIN_PX
        _slider(self.screen, r3["sl_outline"],
                (self._img_editor_outline_px - OUTLINE_MIN_PX) / o_range, 0, 1)
        _button(self.screen, r3["out_white"], "BIANCO", _in_rect((mx, my), r3["out_white"]),
                active=(self._img_editor_outline_color == "white"))
        _button(self.screen, r3["out_black"], "NERO", _in_rect((mx, my), r3["out_black"]),
                active=(self._img_editor_outline_color == "black"))
        _button(self.screen, r3["out_apply"], "APPLICA CONTORNO",
                _in_rect((mx, my), r3["out_apply"]))

        # Footer (Compattato e Corretto)
        fy = ey + eh - 65; bw, bh = 150, 42
        total_footer_w = bw * 3 + 40
        fb_start_x = ex + (ew - sb_w) // 2 - total_footer_w // 2
        fb_rects = [pygame.Rect(fb_start_x + i*(bw + 20), fy, bw, bh) for i in range(3)]
        is_d = self._img_editor_dirty or any(self._img_editor_crop.values())
        sl = "      SALVA" if not self._img_editor_save_confirm else "      CONF?"
        cl = "      COPIA" if not self._img_editor_copy_confirm else "      CONF?"
        el = "      ESCI" if not self._img_editor_exit_confirm else "      CONF?"
        
        h0 = _in_rect((mx, my), fb_rects[0])
        _button(self.screen, fb_rects[0], sl, h0 and is_d, active=self._img_editor_save_confirm)
        self._r_blit_icon("save", pygame.Rect(fb_rects[0].x+8, fb_rects[0].y, 25, 42), active=h0)
        h1 = _in_rect((mx, my), fb_rects[1])
        _button(self.screen, fb_rects[1], cl, h1, active=self._img_editor_copy_confirm)
        self._r_blit_icon("copy", pygame.Rect(fb_rects[1].x+8, fb_rects[1].y, 25, 42), active=h1)
        h2 = _in_rect((mx, my), fb_rects[2])
        _button(self.screen, fb_rects[2], el, h2, danger=True, active=self._img_editor_exit_confirm)
        self._r_blit_icon("exit", pygame.Rect(fb_rects[2].x+12, fb_rects[2].y, 25, 42), active=h2)

        # Cursore Strumento (Workspace Wide, non in ritaglio ne' durante l'AI)
        is_in_work = mx < sb_x and my < fy - 10 and my > ey + 60
        if is_in_work and not self._img_editor_crop_mode and not self._img_editor_busy:
            r_vis = self._img_editor_eraser_r * scale
            if self._img_editor_shape == "round": pygame.draw.circle(self.screen, TXT_HI, (mx, my), int(round(r_vis)), 1)
            else: rv = int(round(r_vis)); pygame.draw.rect(self.screen, TXT_HI, (mx-rv, my-rv, rv*2, rv*2), 1)

    def _r_img_editor_crop_overlay(
        self, ix: int, iy: int, sw: int, sh: int, scale: float
    ) -> None:
        """Overlay scuro sulle zone escluse dal ritaglio e maniglie trascinabili."""
        iw, ih = self._img_editor_view_surf.get_size()
        crop = self._img_editor_crop
        x0 = max(0, min(sw, int(round(crop["l"] * scale))))
        x1 = max(x0, min(sw, int(round((iw - crop["r"]) * scale))))
        y0 = max(0, min(sh, int(round(crop["t"] * scale))))
        y1 = max(y0, min(sh, int(round((ih - crop["b"]) * scale))))
        overlay = pygame.Surface((sw, sh), pygame.SRCALPHA)
        dark = (0, 0, 0, CROP_OVERLAY_ALPHA)
        if x0 > 0: overlay.fill(dark, (0, 0, x0, sh))
        if x1 < sw: overlay.fill(dark, (x1, 0, sw - x1, sh))
        if y0 > 0: overlay.fill(dark, (x0, 0, x1 - x0, y0))
        if y1 < sh: overlay.fill(dark, (x0, y1, x1 - x0, sh - y1))
        self.screen.blit(overlay, (ix, iy))
        pygame.draw.rect(self.screen, ACCENT, (ix + x0, iy + y0, x1 - x0, y1 - y0), 1)
        half = CROP_HANDLE_SIZE // 2
        for hx, hy in self._img_editor_crop_handle_centers(ix, iy, scale).values():
            hr = pygame.Rect(int(hx) - half, int(hy) - half,
                             CROP_HANDLE_SIZE, CROP_HANDLE_SIZE)
            pygame.draw.rect(self.screen, CROP_HANDLE_FILL, hr)
            pygame.draw.rect(self.screen, ACCENT, hr, 2)

    def _r_blit_icon(self, name: str, rect: pygame.Rect, active: bool = False):
        """Blit di un'icona PNG caricata, con fallback a cerchio se mancante."""
        icon = self._img_editor_icons.get(name)
        if icon:
            # Centra l'icona nel rect
            ix = rect.x + (rect.w - icon.get_width()) // 2
            iy = rect.y + (rect.h - icon.get_height()) // 2
            # Se attiva, facciamo un piccolo effetto "glow" o tinta
            if active:
                # Disegna un piccolo cerchio di sfondo per evidenziare
                pygame.draw.circle(self.screen, ACCENT, (ix+16, iy+16), 18, 1)
            self.screen.blit(icon, (ix, iy))
        else:
            # Fallback vector
            self._r_vector_icon(name, rect, active=active)

    def _r_vector_icon(self, name, rect, text_offset=0, active=False):
        c = (255, 255, 255) if active else (180, 180, 190)
        cx, cy = rect.center
        if name == "rot_ccw" or name == "undo":
            pygame.draw.arc(self.screen, c, (cx-8, cy-8, 16, 16), 0.5, 4.5, 2)
            pygame.draw.polygon(self.screen, c, [(cx-8, cy), (cx-4, cy), (cx-6, cy+4)])
        elif name == "rot_cw" or name == "rotate_cw":
            pygame.draw.arc(self.screen, c, (cx-8, cy-8, 16, 16), -1.5, 2.5, 2)
            pygame.draw.polygon(self.screen, c, [(cx+4, cy), (cx+8, cy), (cx+6, cy+4)])
        elif name == "eraser":
            r = rect.inflate(-24, -24)
            pygame.draw.rect(self.screen, c, (r.x, r.y, r.w, r.h//2), border_radius=2)
            pygame.draw.rect(self.screen, c, (r.x+2, r.y+r.h//2, r.w-4, r.h//2), 1, border_radius=1)
        elif name == "wand":
            pygame.draw.line(self.screen, c, (cx-6, cy+6), (cx+6, cy-6), 3)
            pygame.draw.circle(self.screen, c, (cx+6, cy-6), 3)
        elif name == "brush" or name == "restore":
            # Pennello: manico obliquo + punta piena (strumento Ripristina)
            pygame.draw.line(self.screen, c, (cx+2, cy-2), (cx+7, cy-7), 3)
            pygame.draw.polygon(self.screen, c,
                                [(cx-7, cy+7), (cx-2, cy+7), (cx+3, cy-1), (cx-1, cy-5)])
        elif name == "save":
            r = rect.inflate(-34, -34)
            pygame.draw.rect(self.screen, c, r, 2, border_radius=2)
            pygame.draw.rect(self.screen, c, (r.x+4, r.y, r.w-8, r.h//3), 1)
        elif name == "copy":
            r = rect.inflate(-36, -36)
            pygame.draw.rect(self.screen, c, (r.x+4, r.y+4, r.w-4, r.h-4), 1)
            pygame.draw.rect(self.screen, c, (r.x, r.y, r.w-4, r.h-4), 2, border_radius=1)
        elif name == "exit":
            pygame.draw.line(self.screen, c, (cx-6, cy-6), (cx+6, cy+6), 2)
            pygame.draw.line(self.screen, c, (cx+6, cy-6), (cx-6, cy+6), 2)
        elif name == "zoom_fit":
            pygame.draw.rect(self.screen, c, (cx-7, cy-7, 14, 14), 1)
            pygame.draw.line(self.screen, c, (cx-9, cy), (cx-5, cy)); pygame.draw.line(self.screen, c, (cx+5, cy), (cx+9, cy))
        elif name == "zoom_100":
            pygame.draw.circle(self.screen, c, (cx, cy), 8, 1)
            _draw_text(self.screen, "1", "sm", c, cx-3, cy-7)
        elif name == "crop":
            pygame.draw.rect(self.screen, c, (cx-6, cy-6, 12, 12), 2)
            pygame.draw.line(self.screen, c, (cx-9, cy-9), (cx-4, cy-4), 1)
        elif name == "flip_h":
            pygame.draw.polygon(self.screen, c, [(cx-8, cy), (cx-2, cy-6), (cx-2, cy+6)])
            pygame.draw.polygon(self.screen, c, [(cx+8, cy), (cx+2, cy-6), (cx+2, cy+6)])
        elif name == "flip_v":
            pygame.draw.polygon(self.screen, c, [(cx, cy-8), (cx-6, cy-2), (cx+6, cy-2)])
            pygame.draw.polygon(self.screen, c, [(cx, cy+8), (cx-6, cy+2), (cx+6, cy+2)])
        elif name == "smooth":
            pygame.draw.circle(self.screen, c, (cx, cy), 6, 2)
            pygame.draw.circle(self.screen, c, (cx+4, cy-4), 2)
        elif name == "circle_p": pygame.draw.circle(self.screen, c, rect.center, 12)
        elif name == "square_p": pygame.draw.rect(self.screen, c, rect.inflate(-32, -32), border_radius=2)
