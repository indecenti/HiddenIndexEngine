"""
editor/mixins/img_editor.py

ImgEditorMixin — Editor di immagini professionale per gli oggetti del catalogo.
Include: gomma, magic wand, chroma destroyer, zoom/pan e trim evoluto.
"""

import pygame
import logging
import math
import copy
import json
from pathlib import Path
from editor.constants import (
    ACCENT, BORDER, BTN, BTN_HO, BTN_AC, PANEL,
    TXT, TXT_DIM, TXT_HI, OK_C, ERR_C, WARN_C,
)
from editor.ui.draw import _txt, _draw_text, _rect, _button, _in_rect, _slider
from editor.mixins.img_editor_logic import evolved_trim


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
        self._img_editor_last_m = None    # Per interpolazione gomma
        self._img_editor_eraser_r = 4
        self._img_editor_eraser_hardness = 1.0
        self._img_editor_eraser_opacity = 1.0
        self._img_editor_wand_tol = 32
        self._img_editor_wand_feather = 4
        self._img_editor_wand_global = False
        self._img_editor_chroma_intensity = 1.0
        self._img_editor_tool = "eraser"  # "eraser", "soft", "wand"
        self._img_editor_shape = "round"  # "round", "square"
        self._img_editor_crop = {"l": 0, "r": 0, "t": 0, "b": 0}
        self._img_editor_dragging = None # "eraser" | "crop_l" | "crop_r" ...
        self._img_editor_dirty = False
        self._img_editor_undo_stack = []
        self._img_editor_save_confirm = False 
        self._img_editor_copy_confirm = False
        self._img_editor_exit_confirm = False
        self._img_editor_bg_mode = "check" 
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
            orig = pygame.image.load(str(self._img_editor_path)).convert_alpha()
            self._img_editor_surf = orig
            self._img_editor_view_surf = orig.copy()
            self._img_editor_id = cat_id
            self._img_editor_active = True
            self._img_editor_asset_shape = cat_item.get("shape", "rect")
            self._img_editor_crop = {"l": 0, "r": 0, "t": 0, "b": 0}
            self._img_editor_dirty = False
            self._img_editor_undo_stack = []
            self._img_editor_save_confirm = False
            self._img_editor_copy_confirm = False
            self._img_editor_exit_confirm = False
            # Forza Auto-Fit al primo frame
            self._img_editor_zoom = 0.0 
            self._img_editor_pan = [0, 0]
            self._status(f"Editor Immagine: {cat_id}", ACCENT, 2)
        except Exception as e:
            self._status(f"Errore caricamento: {e}", ERR_C, 3)

    def _img_editor_save(self):
        if not self._img_editor_active or not self._img_editor_path: return
        
        try:
            # Applica il crop finale
            w, h = self._img_editor_view_surf.get_size()
            cl, cr = self._img_editor_crop["l"], self._img_editor_crop["r"]
            ct, cb = self._img_editor_crop["t"], self._img_editor_crop["b"]
            
            new_w = max(1, w - cl - cr)
            new_h = max(1, h - ct - cb)
            
            final_surf = pygame.Surface((new_w, new_h), pygame.SRCALPHA)
            final_surf.blit(self._img_editor_view_surf, (0, 0), (cl, ct, new_w, new_h))
            
            target_name = self._img_editor_path.name
            
            # 0. Aggiorna metadati nel catalogo in memoria
            cat_item = next((c for c in self.catalog if c["id"] == self._img_editor_id), None)
            if cat_item:
                cat_item["shape"] = self._img_editor_asset_shape

            # 1. Salva il file principale
            pygame.image.save(final_surf, str(self._img_editor_path))
            
            # 2. Sincronizzazione globale (duplicati)
            overwritten_paths = [self._img_editor_path]
            search_roots = [self.base_path / "engine" / "assets", self.base_path / "games"]
            for root in search_roots:
                if not root.exists(): continue
                for p in root.rglob(target_name):
                    if p.resolve() != self._img_editor_path.resolve():
                        try:
                            pygame.image.save(final_surf, str(p))
                            overwritten_paths.append(p)
                        except: pass

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
                except: pass

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
            w, h = self._img_editor_view_surf.get_size()
            cl, cr = self._img_editor_crop["l"], self._img_editor_crop["r"]
            ct, cb = self._img_editor_crop["t"], self._img_editor_crop["b"]
            new_w, new_h = max(1, w - cl - cr), max(1, h - ct - cb)
            final_surf = pygame.Surface((new_w, new_h), pygame.SRCALPHA)
            final_surf.blit(self._img_editor_view_surf, (0, 0), (cl, ct, new_w, new_h))
            
            orig_rel_path = orig_item.get("image") or orig_item.get("icon")
            p = Path(orig_rel_path)
            clean_stem = re.sub(r"_v\d+$", "", p.stem)
            new_rel_path = str(p.parent / f"{clean_stem}_v{counter}{p.suffix}").replace("\\", "/")
            new_abs_path = self._img_editor_path.parent / f"{clean_stem}_v{counter}{p.suffix}"
            
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
            if ev.key == pygame.K_ESCAPE: self._img_editor_active = False
            elif ev.key == pygame.K_s and (pygame.key.get_mods() & pygame.KMOD_CTRL): self._img_editor_save()
            elif ev.key == pygame.K_z and (pygame.key.get_mods() & pygame.KMOD_CTRL): self._img_editor_undo()
            elif ev.key == pygame.K_r and (pygame.key.get_mods() & pygame.KMOD_CTRL):
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
        # Responsive: Sidebar compatta (320), resto alla tela
        sb_w = 320
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
        sb_w = 320
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

        # Determina se il click cade su un elemento UI (sidebar / header / footer)
        is_ui = (mx > sb_x) or (my < ey + 60) or (my >= fy - 5)

        if not is_ui:
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
        for i, tid in enumerate(["eraser", "wand"]):
            if _in_rect((mx, my), (col1_x + i * 60, sy, 52, 52)):
                self._img_editor_tool = tid; return
        for i, sid in enumerate(["round", "square"]):
            if _in_rect((mx, my), (col1_x + i * 60, sy + 65, 52, 52)):
                self._img_editor_shape = sid; return

        # Sliders (ALLINEATO al render: sy_sl = ey + 255, offset +70 e +140)
        sy_sl = ey + 255
        if self._img_editor_tool == "eraser":
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
        if self._img_editor_wand_global:
            for y in range(h):
                for x in range(w):
                    nc = surf.get_at((x, y))
                    diff = max(abs(nc[0]-target_color[0]), abs(nc[1]-target_color[1]), abs(nc[2]-target_color[2]))
                    if diff <= tol + feather: to_process.append((x, y, diff))
        else:
            from collections import deque
            queue = deque([(rx, ry)]); visited = [False] * (w * h); visited[ry * w + rx] = True
            while queue:
                cx, cy = queue.popleft(); nc = surf.get_at((cx, cy))
                diff = max(abs(nc[0]-target_color[0]), abs(nc[1]-target_color[1]), abs(nc[2]-target_color[2]))
                to_process.append((cx, cy, diff))
                for dx, dy in [(-1,0), (1,0), (0,-1), (0,1)]:
                    nx, ny = cx + dx, cy + dy
                    if 0 <= nx < w and 0 <= ny < h:
                        v_idx = ny * w + nx
                        if not visited[v_idx]:
                            nc_n = surf.get_at((nx, ny))
                            diff_n = max(abs(nc_n[0]-target_color[0]), abs(nc_n[1]-target_color[1]), abs(nc_n[2]-target_color[2]))
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

    def _img_editor_apply_flip(self, flip_h, flip_v):
        self._img_editor_push_undo()
        self._img_editor_view_surf = pygame.transform.flip(self._img_editor_view_surf, flip_h, flip_v)
        self._img_editor_dirty = True

    def _img_editor_apply_smooth_edges(self):
        try:
            self._img_editor_push_undo()
            import pygame.surfarray as surfarray; import numpy as np; from scipy.ndimage import gaussian_filter
            alpha = surfarray.array_alpha(self._img_editor_view_surf).astype(float)
            alpha_smooth = gaussian_filter(alpha, sigma=0.6)
            surfarray.pixels_alpha(self._img_editor_view_surf)[:] = alpha_smooth.astype(np.uint8)
            self._img_editor_dirty = True; self._status("Bordi Ammorbiditi", OK_C, 2)
        except: self._status("Smooth non disponibile", WARN_C, 2)

    def _img_editor_drag(self, mx, my):
        ex, ey, ew, eh = self._img_editor_get_modal_rect()
        sb_w = 320
        sb_x = ex + ew - sb_w - 15
        col1_x = sb_x + 10  # ALLINEATO al render
        sl_w = 145

        if self._img_editor_dragging in ("eraser_active", "eraser"):
            ix, iy, sw, sh, scale = self._img_editor_get_img_layout(ew, eh, ex, ey)
            self._img_editor_erase(mx, my, ix, iy, scale)
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




    def _img_editor_erase(self, mx, my, ix, iy, scale):
        """Gomma a pennello morbido con interpolazione tra frame."""
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
        if not hasattr(self, "_img_editor_brush_cache"):
            self._img_editor_brush_cache = {}

        if brush_key not in self._img_editor_brush_cache:
            import numpy as np
            size = ri * 2 + 1
            center = float(ri)
            y_arr, x_arr = np.ogrid[0:size, 0:size]
            if shape == "round":
                dist_arr = np.sqrt((x_arr - center) ** 2 + (y_arr - center) ** 2)
            else:
                dist_arr = np.maximum(np.abs(x_arr - center), np.abs(y_arr - center))
            h_boundary = ri * hardness
            erase_power = np.zeros((size, size), dtype=float)
            erase_power[dist_arr <= h_boundary] = 1.0
            gradient_mask = (dist_arr > h_boundary) & (dist_arr <= ri)
            if ri > h_boundary:
                erase_power[gradient_mask] = 1.0 - (dist_arr[gradient_mask] - h_boundary) / (ri - h_boundary)
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

    def _img_editor_push_undo(self):
        self._img_editor_undo_stack.append(self._img_editor_view_surf.copy())
        if len(self._img_editor_undo_stack) > 20: self._img_editor_undo_stack.pop(0)

    def _img_editor_undo(self):
        if not self._img_editor_undo_stack: return
        self._img_editor_view_surf = self._img_editor_undo_stack.pop(); self._img_editor_dirty = True

    def _r_img_editor_modal(self, w, h):
        if not self._img_editor_active: return
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

        if scale >= 1.0: scaled_img = pygame.transform.scale(self._img_editor_view_surf, (sw, sh))
        else: scaled_img = pygame.transform.smoothscale(self._img_editor_view_surf, (sw, sh))
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

        # HUD Technical Data — collocato nell'header per non sovrapporsi MAI al footer.
        if _in_rect((mx, my), (ix, iy, sw, sh)):
            rx = int((mx - ix) / scale); ry = int((my - iy) / scale)
            iw, ih = self._img_editor_view_surf.get_size()
            if 0 <= rx < iw and 0 <= ry < ih:
                c = self._img_editor_view_surf.get_at((rx, ry))
                hud_txt = f"X:{rx}  Y:{ry}  |  RGBA: {c[0]},{c[1]},{c[2]},{c[3]}"
                # ancorato a destra della title bar, a sinistra del toggle BG
                _draw_text(self.screen, hud_txt, "sm", TXT_DIM, ex + 320, ey + 32)

        # SIDEBAR (Compatta)
        sb_w = 320
        sb_x = ex + ew - sb_w - 15
        col1_x, col2_x = sb_x + 10, sb_x + 165
        
        # Strumenti
        _draw_text(self.screen, "PENNELLI", "sm", TXT_DIM, col1_x, ey + 60)
        sy = ey + 85
        for i, (tid, ico) in enumerate([("eraser", "eraser"), ("wand", "wand")]):
            tr = pygame.Rect(col1_x + i*60, sy, 52, 52); act = (self._img_editor_tool == tid)
            _button(self.screen, tr, "", _in_rect((mx, my), tr), active=act)
            self._r_blit_icon(ico, tr, active=act)
            
        for i, (sid, ico) in enumerate([("round", "circle_p"), ("square", "square_p")]):
            fr = pygame.Rect(col1_x + i*60, sy + 65, 52, 52); act = (self._img_editor_shape == sid)
            _button(self.screen, fr, "", _in_rect((mx, my), fr), active=act)
            self._r_blit_icon(ico, fr, active=act)
                  
        # Pennello
        sy_sl = ey + 255
        sl_w = 145
        if self._img_editor_tool == "eraser":
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

        # Cursore Strumento (Workspace Wide)
        is_in_work = mx < sb_x and my < fy - 10 and my > ey + 60
        if is_in_work:
            r_vis = self._img_editor_eraser_r * scale
            if self._img_editor_shape == "round": pygame.draw.circle(self.screen, TXT_HI, (mx, my), int(round(r_vis)), 1)
            else: rv = int(round(r_vis)); pygame.draw.rect(self.screen, TXT_HI, (mx-rv, my-rv, rv*2, rv*2), 1)

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
