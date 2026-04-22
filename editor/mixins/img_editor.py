"""
editor/mixins/img_editor.py

ImgEditorMixin — Semplice editor di immagini per gli oggetti del catalogo.
Include: gomma tonda ridimensionabile, crop manuale sui lati, salvataggio.
"""

import pygame
import logging
import math
from pathlib import Path
from editor.constants import (
    ACCENT, BORDER, BTN, BTN_HO, BTN_AC, PANEL,
    TXT, TXT_DIM, TXT_HI, OK_C, ERR_C, WARN_C,
)
from editor.ui.draw import _txt, _draw_text, _rect, _button, _in_rect, _slider


class ImgEditorMixin:
    """Editor semplice per PNG del catalogo."""

    def _img_editor_init_state(self):
        self._img_editor_active = False
        self._img_editor_id = ""
        self._img_editor_path = None
        self._img_editor_surf = None
        self._img_editor_view_surf = None # Superficie di lavoro
        self._img_editor_last_m = None    # Per interpolazione gomma
        self._img_editor_eraser_r = 20
        self._img_editor_tool = "eraser"  # "eraser", "soft"
        self._img_editor_shape = "round"  # "round", "square"
        self._img_editor_crop = {"l": 0, "r": 0, "t": 0, "b": 0}
        self._img_editor_dragging = None # "eraser" | "crop_l" | "crop_r" ...
        self._img_editor_dirty = False
        self._img_editor_undo_stack = []
        self._img_editor_save_confirm = False # Nuova conferma salvataggio

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
        logging.info(f"[IMG_EDITOR] Checking path: {self._img_editor_path}")
        
        if not self._img_editor_path.exists():
            # Fallback a engine/assets/objects
            master_p = self.base_path / "engine" / "assets" / "objects" / Path(img_rel).name
            logging.info(f"[IMG_EDITOR] Game-specific not found, checking master: {master_p}")
            if master_p.exists():
                self._img_editor_path = master_p
            else:
                logging.error(f"[IMG_EDITOR] Resource NOT FOUND: {img_rel}")
                self._status(f"File non trovato: {img_rel}", ERR_C, 3)
                return

        logging.info(f"[IMG_EDITOR] Final path to use: {self._img_editor_path}")
        try:
            # Carica l'immagine originale
            orig = pygame.image.load(str(self._img_editor_path)).convert_alpha()
            self._img_editor_surf = orig
            # Crea una copia per l'editing
            self._img_editor_view_surf = orig.copy()
            self._img_editor_id = cat_id
            self._img_editor_active = True
            self._img_editor_crop = {"l": 0, "r": 0, "t": 0, "b": 0}
            self._img_editor_dirty = False
            self._img_editor_undo_stack = []
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
            logging.info(f"[IMG_EDITOR] Saving. Target name for global sync: {target_name}")
            
            # 1. Salva il file principale
            pygame.image.save(final_surf, str(self._img_editor_path))
            
            # 2. Cerca e sovrascrivi tutti i duplicati nel progetto
            # Scansioniamo engine/assets e la cartella games per sicurezza
            overwritten_paths = [self._img_editor_path]
            
            search_roots = [
                self.base_path / "engine" / "assets" / "objects",
                self.base_path / "games"
            ]
            
            for root in search_roots:
                if not root.exists(): continue
                for p in root.rglob(target_name):
                    if p.resolve() != self._img_editor_path.resolve():
                        try:
                            pygame.image.save(final_surf, str(p))
                            overwritten_paths.append(p)
                            # Invalida cache per questo specifico path
                            if p in self._img_cache: del self._img_cache[p]
                        except Exception as e:
                            logging.error(f"[IMG_EDITOR] Failed to overwrite duplicate at {p}: {e}")

            logging.info(f"[IMG_EDITOR] Save complete. Overwritten {len(overwritten_paths)} instances: {overwritten_paths}")

            # Invalida cache immagini nell'editor per il path principale
            if self._img_editor_path in self._img_cache:
                del self._img_cache[self._img_editor_path]
            
            # Invalida cache ratio (molto importante per il catalogo)
            if self._img_editor_id in self._asset_ratios_cache:
                del self._asset_ratios_cache[self._img_editor_id]
                
            self._obj_draw_cache.clear()
            
            self._img_editor_active = False
            self._status(f"Immagine salvata ({len(overwritten_paths)} file aggiornati)", OK_C, 3)
            self.scene_dirty = True
        except Exception as e:
            logging.error(f"[IMG_EDITOR] Save error: {e}")
            self._status(f"Errore salvataggio: {e}", ERR_C, 3)

    # ─────────────────────────────────────────────────────────────────────────
    # INPUT
    # ─────────────────────────────────────────────────────────────────────────

    def _img_editor_handle_event(self, ev):
        if not self._img_editor_active: return
        
        if ev.type == pygame.KEYDOWN:
            if ev.key == pygame.K_ESCAPE:
                self._img_editor_active = False
            elif ev.key == pygame.K_s and (pygame.key.get_mods() & pygame.KMOD_CTRL):
                self._img_editor_save()
            elif ev.key == pygame.K_z and (pygame.key.get_mods() & pygame.KMOD_CTRL):
                self._img_editor_undo()
        
        elif ev.type == pygame.MOUSEBUTTONDOWN:
            mx, my = ev.pos
            self._img_editor_click(mx, my, ev.button)
            
        elif ev.type == pygame.MOUSEBUTTONUP:
            self._img_editor_dragging = None
            self._img_editor_last_m = None
            
        elif ev.type == pygame.MOUSEMOTION:
            if ev.buttons[0]: # Sinistro premuto
                mx, my = ev.pos
                self._img_editor_drag(mx, my)

    def _img_editor_get_img_layout(self, ew, eh, ex, ey):
        iw, ih = self._img_editor_view_surf.get_size()
        # Lasciamo 140px in basso per la bottom bar (Salva/Esci)
        work_w, work_h = ew - 220, eh - 140
        scale = min(work_w / iw, work_h / ih)
        scaled_w, scaled_h = int(iw * scale), int(ih * scale)
        ix = ex + 20 + (work_w - scaled_w) // 2
        iy = ey + 60 + (work_h - scaled_h) // 2
        return ix, iy, scaled_w, scaled_h, scale

    def _img_editor_click(self, mx, my, btn):
        w, h = self.screen.get_size()
        ew, eh = 850, 650
        ex, ey = (w - ew) // 2, (h - eh) // 2
        ix, iy, sw, sh, scale = self._img_editor_get_img_layout(ew, eh, ex, ey)
        
        reset_confirm = True
        bx = ex + ew - 190

        # --- 1. BARRA INFERIORE (Priorità assoluta) ---
        by_bot = ey + eh - 60
        bx_bot = ex + (ew - 260) // 2
        bw_act = 125
        if _in_rect((mx, my), (bx_bot, by_bot, bw_act, 40)): # SALVA
            if not self._img_editor_save_confirm:
                self._img_editor_save_confirm = True
                reset_confirm = False
            else:
                self._img_editor_save()
                return
            return
        if _in_rect((mx, my), (bx_bot + bw_act + 10, by_bot, bw_act, 40)): # ANNULLA
            self._img_editor_active = False
            return

        # --- 2. AREA DI LAVORO (DISEGNO) ---
        # Si ferma prima della barra inferiore
        work_rect = pygame.Rect(ex + 10, ey + 40, ew - 210, eh - 100)
        if _in_rect((mx, my), work_rect):
            self._img_editor_dragging = "eraser"
            self._img_editor_erase(mx, my, ix, iy, scale)
            return

        # --- 3. BARRA LATERALE ---
        # Strumenti
        ty, bw_t = ey + 75, 40
        if _in_rect((mx, my), (bx, ty, bw_t, bw_t)):
            self._img_editor_tool = "eraser"
        elif _in_rect((mx, my), (bx + bw_t + 10, ty, bw_t, bw_t)):
            self._img_editor_tool = "soft"
        
        # Forme
        elif _in_rect((mx, my), (bx, fy := ty + 55, bw_f := 40, bw_f)):
            self._img_editor_shape = "round"
        elif _in_rect((mx, my), (bx + bw_f + 10, fy, bw_f, bw_f)):
            self._img_editor_shape = "square"

        # Raggio
        elif _in_rect((mx, my), (slider_r := pygame.Rect(bx, fy + 78, 170, 20))):
            rel = max(0, min(1, (mx - slider_r.x) / slider_r.w))
            self._img_editor_eraser_r = int(5 + rel * 95)
            self._img_editor_dragging = "eraser_size"

        # Crop & Rotazione
        else:
            y_c = fy + 118
            y_c += 24
            for side in ["l", "r", "t", "b"]:
                y_c += 18
                sr = pygame.Rect(bx, y_c, 170, 16)
                if _in_rect((mx, my), sr):
                    self._img_editor_dragging = f"crop_{side}"
                    self._img_editor_update_crop(mx, sr.x, sr.w, side)
                    return
                y_c += 32
            
            y_rot = y_c + 15
            bw_rot = 170 // 2 - 5
            if _in_rect((mx, my), (bx, y_rot, bw_rot, 40)):
                self._img_editor_apply_rotation(90)
            elif _in_rect((mx, my), (bx + bw_rot + 10, y_rot, bw_rot, 40)):
                self._img_editor_apply_rotation(-90)
            elif _in_rect((mx, my), (bx, y_rot + 50, 170, 36)):
                self._img_editor_auto_crop()

        if reset_confirm:
            self._img_editor_save_confirm = False

    def _img_editor_auto_crop(self):
        """Algoritmo di Trim Ultra-Robust: Scansione densità bordi su tutti i 4 lati."""
        logging.info("[IMG_EDITOR] ================= ROBUST EDGE SCANNER =================")
        try:
            surf = self._img_editor_view_surf
            w, h = surf.get_size()
            logging.info(f"[IMG_EDITOR] Screening immagine {w}x{h}...")
            
            # Parametri di tolleranza
            # Usiamo soglia 80 per ignorare il rumore (visto prima a 58)
            # Richiediamo almeno 2 pixel solidi o l'1% della riga per considerare "contenuto"
            THR = 80
            MIN_D = max(2, int(min(w, h) * 0.01))
            
            new_t, new_b = 0, h
            new_l, new_r = 0, w
            
            # 1. Scan TOP
            for y in range(h):
                row_solid = sum(1 for x in range(w) if surf.get_at((x, y))[3] >= THR)
                if row_solid >= MIN_D:
                    new_t = y
                    logging.info(f"[IMG_EDITOR] Top Edge trovato a y={y} (densità={row_solid})")
                    break
            
            # 2. Scan BOTTOM
            for y in range(h - 1, new_t, -1):
                row_solid = sum(1 for x in range(w) if surf.get_at((x, y))[3] >= THR)
                if row_solid >= MIN_D:
                    new_b = y + 1
                    logging.info(f"[IMG_EDITOR] Bottom Edge trovato a y={y} (densità={row_solid})")
                    break
                    
            # 3. Scan LEFT
            for x in range(w):
                col_solid = sum(1 for y in range(new_t, new_b) if surf.get_at((x, y))[3] >= THR)
                if col_solid >= MIN_D:
                    new_l = x
                    logging.info(f"[IMG_EDITOR] Left Edge trovato a x={x} (densità={col_solid})")
                    break
            
            # 4. Scan RIGHT
            for x in range(w - 1, new_l, -1):
                col_solid = sum(1 for y in range(new_t, new_b) if surf.get_at((x, y))[3] >= THR)
                if col_solid >= MIN_D:
                    new_r = x + 1
                    logging.info(f"[IMG_EDITOR] Right Edge trovato a x={x} (densità={col_solid})")
                    break

            # Verifica se c'è stato un vero cambiamento
            if new_l == 0 and new_r == w and new_t == 0 and new_b == h:
                logging.info("[IMG_EDITOR] Nessun bordo trimmabile trovato con i parametri attuali.")
                self._status("L'asset è già ottimizzato", TXT_DIM, 2)
                return

            # Calcolo Bbox finale
            final_w = new_r - new_l
            final_h = new_b - new_t
            
            if final_w <= 0 or final_h <= 0:
                logging.warning("[IMG_EDITOR] Errore logico nel calcolo del ritaglio.")
                return

            # ESECUZIONE
            self._img_editor_push_undo()
            new_surf = pygame.Surface((final_w, final_h), pygame.SRCALPHA)
            new_surf.blit(self._img_editor_view_surf, (0, 0), (new_l, new_t, final_w, final_h))
            
            self._img_editor_view_surf = new_surf
            self._img_editor_crop = {"l": 0, "r": 0, "t": 0, "b": 0}
            self._img_editor_dirty = True
            
            logging.info(f"[IMG_EDITOR] Trim completato: {w}x{h} -> {final_w}x{final_h}")
            self._status(f"Trim: {final_w}x{final_h}", OK_C, 2)
                
        except Exception as e:
            logging.error(f"[IMG_EDITOR] Errore nel Robust Scanner: {e}", exc_info=True)
            self._status("Errore algoritmo Trim", ERR_C, 2)

    def _img_editor_apply_rotation(self, angle):
        """Ruota la superficie di lavoro e resetta i crop (per semplicità)."""
        try:
            self._img_editor_push_undo()
            self._img_editor_view_surf = pygame.transform.rotate(self._img_editor_view_surf, angle)
            # Reset crop perché le dimensioni sono cambiate
            self._img_editor_crop = {"l": 0, "r": 0, "t": 0, "b": 0}
            self._img_editor_dirty = True
            logging.info(f"[IMG_EDITOR] Rotated by {angle}deg. New size: {self._img_editor_view_surf.get_size()}")
        except Exception as e:
            logging.error(f"[IMG_EDITOR] Rotation failed: {e}")

    def _img_editor_drag(self, mx, my):
        w, h = self.screen.get_size()
        ew, eh = 850, 650
        ex, ey = (w - ew) // 2, (h - eh) // 2
        bx = ex + ew - 190
        
        if self._img_editor_dragging and self._img_editor_dragging.startswith("eraser"):
            ix, iy, sw, sh, scale = self._img_editor_get_img_layout(ew, eh, ex, ey)
            self._img_editor_erase(mx, my, ix, iy, scale)
            
        elif self._img_editor_dragging == "eraser_size":
            fy_sl = ey + 75 + 55 # ty + 55
            sr = pygame.Rect(bx, fy_sl + 78, 170, 20) # Sinc con click
            rel = max(0, min(1, (mx - sr.x) / sr.w))
            self._img_editor_eraser_r = int(5 + max(0.01, rel) * 95)
            
        elif self._img_editor_dragging and self._img_editor_dragging.startswith("crop_"):
            side = self._img_editor_dragging.split("_")[1]
            y_map = {"l": 0, "r": 1, "t": 2, "b": 3}
            # Ricalcola y come in click (fy + 142)
            fy_sl = ey + 75 + 55
            y_c = fy_sl + 118 + 24
            for _ in range(y_map[side]):
                y_c += (18 + 32) # Passo crop completo (Label + Slider)
            y_c += 18 # Per arrivare esattamente allo slider
            sr = pygame.Rect(bx, y_c, 170, 16)
            self._img_editor_update_crop(mx, sr.x, sr.w, side)

    def _img_editor_update_crop(self, mx, sx, sw, side):
        rel = max(0, min(1, (mx - sx) / sw))
        iw, ih = self._img_editor_view_surf.get_size()
        max_base = iw if side in ("l", "r") else ih
        self._img_editor_crop[side] = int(rel * max_base)

    def _img_editor_erase(self, mx, my, ix, iy, scale):
        # Transforma mouse in coordinate immagine
        rx = (mx - ix) / scale
        ry = (my - iy) / scale
        r = self._img_editor_eraser_r / scale
        
        # Gestione Undo e Stato
        if not (self._img_editor_dragging and self._img_editor_dragging == "eraser_active"):
            self._img_editor_push_undo()
            self._img_editor_dragging = "eraser_active"

        # Interpolazione tra l'ultimo punto e quello attuale per un tratto fluido
        points = [(rx, ry)]
        if self._img_editor_last_m:
            lx, ly = self._img_editor_last_m
            dist = math.hypot(rx - lx, ry - ly)
            if dist > r / 3: # Più denso per sfumatura
                steps = int(dist / (r / 3))
                for i in range(1, steps):
                    f = i / steps
                    points.append((lx + (rx - lx) * f, ly + (ry - ly) * f))
        
        self._img_editor_last_m = (rx, ry)

        iw, ih = self._img_editor_view_surf.get_size()
        tool, shape = self._img_editor_tool, self._img_editor_shape

        # Pre-calcolo o recupero pennello dalla cache (per fluidità)
        brush_key = (tool, shape, int(r))
        if not hasattr(self, "_img_editor_brush_cache"): self._img_editor_brush_cache = {}
        
        if brush_key not in self._img_editor_brush_cache:
            size = int(r * 2) + 2
            bs = pygame.Surface((size, size), pygame.SRCALPHA)
            center = size // 2
            
            # Disegno a livello di pixel per gradiente perfetto
            for y in range(size):
                for x in range(size):
                    dx, dy = x - center, y - center
                    dist = math.hypot(dx, dy)
                    
                    if shape == "round":
                        if dist > r: alpha = 255
                        elif tool == "soft":
                            # Decadimento professionale (stile Photoshop)
                            # Usiamo una curva di potenza per un bordo molto morbido
                            alpha = int(255 * math.pow(dist / r, 1.2))
                        else: # Hard Eraser
                            alpha = 0 if dist < r - 1 else 255
                    else: # Square
                        dist_sq = max(abs(dx), abs(dy))
                        if dist_sq > r: alpha = 255
                        elif tool == "soft":
                            alpha = int(255 * math.pow(dist_sq / r, 1.2))
                        else:
                            alpha = 0 if dist_sq < r - 1 else 255
                    
                    bs.set_at((x, y), (255, 255, 255, max(0, min(255, alpha))))
            
            self._img_editor_brush_cache[brush_key] = bs

        brush_surf = self._img_editor_brush_cache[brush_key]
        size = brush_surf.get_width()

        for px, py in points:
            if px + r < 0 or px - r > iw or py + r < 0 or py - r > ih:
                continue
            p_rect = (int(px - r), int(py - r), size, size)
            self._img_editor_view_surf.blit(brush_surf, (p_rect[0], p_rect[1]), special_flags=pygame.BLEND_RGBA_MIN)
        
        self._img_editor_dirty = True

    def _img_editor_push_undo(self):
        # Limita lo stack a 20 passi per memoria
        self._img_editor_undo_stack.append(self._img_editor_view_surf.copy())
        if len(self._img_editor_undo_stack) > 20:
            self._img_editor_undo_stack.pop(0)

    def _img_editor_undo(self):
        if not self._img_editor_undo_stack:
            self._status("Nulla da annullare", WARN_C, 1)
            return
        self._img_editor_view_surf = self._img_editor_undo_stack.pop()
        self._img_editor_dirty = True
        self._status("Undo effettuato", ACCENT, 1)

    # ─────────────────────────────────────────────────────────────────────────
    # RENDERING
    # ─────────────────────────────────────────────────────────────────────────

    def _r_img_editor_modal(self, w, h):
        if not self._img_editor_active: return
        
        # Sfondo scuro
        dim = pygame.Surface((w, h), pygame.SRCALPHA)
        dim.fill((0, 0, 0, 180))
        self.screen.blit(dim, (0, 0))
        
        ew, eh = 850, 650
        ex, ey = (w - ew) // 2, (h - eh) // 2
        box = pygame.Rect(ex, ey, ew, eh)
        _rect(self.screen, PANEL, box, radius=12)
        _rect(self.screen, ACCENT, box, 2, radius=12)
        
        mx, my = pygame.mouse.get_pos()
        
        # Header
        title = _txt(f"Edit Image: {self._img_editor_id}", "lg", TXT_HI)
        self.screen.blit(title, (ex + 20, ey + 15))
        
        # Area Lavoro Immagine
        iw, ih = self._img_editor_view_surf.get_size()
        # Riserva spazio in basso (corrispondente a _img_editor_get_img_layout)
        work_w, work_h = ew - 220, eh - 140
        scale = min(work_w / iw, work_h / ih)
        scaled_w, scaled_h = int(iw * scale), int(ih * scale)
        ix = ex + 20 + (work_w - scaled_w) // 2
        iy = ey + 60 + (work_h - scaled_h) // 2
        
        # Scacchiera trasparenza
        chess_size = 16
        for cx in range(ix, ix + scaled_w, chess_size):
            for cy in range(iy, iy + scaled_h, chess_size):
                if ((cx-ix)//chess_size + (cy-iy)//chess_size) % 2 == 0:
                    cw = min(chess_size, ix + scaled_w - cx)
                    ch = min(chess_size, iy + scaled_h - cy)
                    pygame.draw.rect(self.screen, (30, 30, 35), (cx, cy, cw, ch))
                else:
                    cw = min(chess_size, ix + scaled_w - cx)
                    ch = min(chess_size, iy + scaled_h - cy)
                    pygame.draw.rect(self.screen, (45, 45, 50), (cx, cy, cw, ch))

        # Immagine scalata
        scaled_img = pygame.transform.smoothscale(self._img_editor_view_surf, (scaled_w, scaled_h))
        self.screen.blit(scaled_img, (ix, iy))
        
        # Rettangolo Crop Overlay
        cl, cr = int(self._img_editor_crop["l"] * scale), int(self._img_editor_crop["r"] * scale)
        ct, cb = int(self._img_editor_crop["t"] * scale), int(self._img_editor_crop["b"] * scale)
        
        # Rettangolo Crop Overlay Professionale
        cl, cr = int(self._img_editor_crop["l"] * scale), int(self._img_editor_crop["r"] * scale)
        ct, cb = int(self._img_editor_crop["t"] * scale), int(self._img_editor_crop["b"] * scale)
        
        if any([cl, cr, ct, cb]):
            # Oscuramento delle aree fuori dal crop (Photoshop Style)
            overlay = pygame.Surface((scaled_w, scaled_h), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 160)) # Tutto scuro
            # Sfondiamo l'area centrale (quella che rimane)
            r_keep = pygame.Rect(cl, ct, scaled_w - cl - cr, scaled_h - ct - cb)
            pygame.draw.rect(overlay, (0, 0, 0, 0), r_keep)
            self.screen.blit(overlay, (ix, iy))
            
            # Cornice gialla vivida sull'area attiva
            r_final = pygame.Rect(ix + cl, iy + ct, r_keep.w, r_keep.h)
            pygame.draw.rect(self.screen, (255, 230, 0), r_final, 2)
            # Angoli rinforzati bianchi
            d = 12
            pygame.draw.lines(self.screen, (255, 255, 255), False, [(r_final.x, r_final.y+d), (r_final.x, r_final.y), (r_final.x+d, r_final.y)], 2)
            pygame.draw.lines(self.screen, (255, 255, 255), False, [(r_final.right-d, r_final.y), (r_final.right, r_final.y), (r_final.right, r_final.y+d)], 2)
            pygame.draw.lines(self.screen, (255, 255, 255), False, [(r_final.x, r_final.bottom-d), (r_final.x, r_final.bottom), (r_final.x+d, r_final.bottom)], 2)
            pygame.draw.lines(self.screen, (255, 255, 255), False, [(r_final.right-d, r_final.bottom), (r_final.right, r_final.bottom), (r_final.right, r_final.bottom-d)], 2)
        
        # Toolbar laterale
        bx = ex + ew - 190
        
        # Selezione Strumenti
        _draw_text(self.screen, "Strumenti:", "sm", TXT_DIM, bx, ey + 55)
        ty, bw_t = ey + 75, 40
        tools = [("eraser", "eraser", "Gomma: cancella pixel in modo netto"), ("soft", "blur", "Sfuma: cancella con bordi morbidi")]
        for i, (tid, ico, tip) in enumerate(tools):
            tx, act = bx + i*(bw_t+10), (self._img_editor_tool == tid)
            tr = pygame.Rect(tx, ty, bw_t, bw_t)
            _button(self.screen, tr, "", _in_rect((mx, my), tr), active=act)
            self._r_vector_icon(ico, tr.inflate(-12, -12), active=act)
            if _in_rect((mx, my), tr): self._img_editor_tip = tip

        # Selezione Forme
        _draw_text(self.screen, "Forma:", "sm", TXT_DIM, bx, ty + 55)
        fy, bw_f = ty + 55, 40
        shapes = [("round", "circle_p", "Pennello tondo"), ("square", "square_p", "Pennello quadrato")]
        for i, (sid, ico, tip) in enumerate(shapes):
            fx, act = bx + i*(bw_f+10), (self._img_editor_shape == sid)
            fr = pygame.Rect(fx, fy, bw_f, bw_f)
            _button(self.screen, fr, "", _in_rect((mx, my), fr), active=act)
            self._r_vector_icon(ico, fr.inflate(-16, -16), active=act)
            if _in_rect((mx, my), fr): self._img_editor_tip = tip

        # Gomma
        _draw_text(self.screen, f"Raggio: {self._img_editor_eraser_r}px", "sm", TXT_HI, bx, fy + 55)
        y_sl = fy + 78
        _slider(self.screen, (bx, y_sl, 170, 20), (self._img_editor_eraser_r - 5) / 95, 0, 1)
        
        # Crop Sliders
        y_c = y_sl + 40
        _draw_text(self.screen, "Ritaglio Manuale:", "sm", TXT_DIM, bx, y_c)
        y_c += 24
        crop_labels = [("L", "l"), ("R", "r"), ("T", "t"), ("B", "b")]
        for i, (lbl, side) in enumerate(crop_labels):
            _draw_text(self.screen, f"{lbl}: {self._img_editor_crop[side]}px", "sm", TXT_DIM, bx, y_c)
            y_c += 18
            max_val = iw if side in ("l", "r") else ih
            val_p = self._img_editor_crop[side] / max_val if max_val > 0 else 0
            _slider(self.screen, (bx, y_c, 170, 16), val_p, 0, 1) # Leggermente più sottili
            y_c += 32
            
        # Pulsanti Rotazione (Con L/R labels come richiesto)
        y_rot = y_c + 15
        bw_rot  = 170 // 2 - 5
        rot_l = pygame.Rect(bx, y_rot, bw_rot, 40)
        rot_r = pygame.Rect(bx + bw_rot + 10, y_rot, bw_rot, 40)
        _button(self.screen, rot_l, "L", _in_rect((mx, my), rot_l))
        _button(self.screen, rot_r, "R", _in_rect((mx, my), rot_r))
        self._r_vector_icon("rot_ccw", rot_l.inflate(-12, -12), active=_in_rect((mx, my), rot_l), text_offset=-5)
        self._r_vector_icon("rot_cw", rot_r.inflate(-12, -12), active=_in_rect((mx, my), rot_r), text_offset=-5)
        if _in_rect((mx, my), rot_l): self._img_editor_tip = "Ruota 90° antioraria (L)"
        if _in_rect((mx, my), rot_r): self._img_editor_tip = "Ruota 90° oraria (R)"

        # Pulsante Auto-Crop
        ac_r = pygame.Rect(bx, y_rot + 50, 170, 36)
        _button(self.screen, ac_r, "", _in_rect((mx, my), ac_r))
        self._r_vector_icon("crop", ac_r.inflate(-16, -16), active=_in_rect((mx, my), ac_r))
        _draw_text(self.screen, "AUTO TRIM", "sm", TXT_HI, ac_r.x + 55, ac_r.y + 9)
        if _in_rect((mx, my), ac_r): self._img_editor_tip = "Elimina bordi trasparenti in eccesso"
            
        # Bottoni finali su unica riga centrata a fondo modale (SOTTO Tutto)
        by_bot = ey + eh - 60
        bx_bot = ex + (ew - 260) // 2 # Centrato in 850px
        bw_act = 125
        save_r = pygame.Rect(bx_bot, by_bot, bw_act, 40)
        canc_r = pygame.Rect(bx_bot + bw_act + 10, by_bot, bw_act, 40)
        
        # Logica Conferma Salvataggio
        s_lbl = "CONFERMI?" if self._img_editor_save_confirm else "SALVA PNG"
        s_act = self._img_editor_dirty or any(self._img_editor_crop.values())
        
        if self._img_editor_save_confirm:
            # Colore di conferma (Ambra/Giallo) alternativo
            confirm_bg = (200, 150, 0)
            _rect(self.screen, confirm_bg, save_r, radius=4)
            _draw_text(self.screen, s_lbl, "sm", (255, 255, 255), save_r.x + 30, save_r.y + 11)
        else:
            _button(self.screen, save_r, s_lbl, _in_rect((mx, my), save_r), active=s_act)
            
        _button(self.screen, canc_r, "Esci", _in_rect((mx, my), canc_r), danger=True)
        
        # Mirino gomma se sopra immagine
        # Mirino pennello se nell'area di lavoro
        work_rect = pygame.Rect(ex + 10, ey + 40, ew - 210, eh - 60)
        if _in_rect((mx, my), work_rect):
            r = self._img_editor_eraser_r
            if self._img_editor_shape == "round":
                pygame.draw.circle(self.screen, TXT_HI, (mx, my), int(r), 1)
            else:
                pygame.draw.rect(self.screen, TXT_HI, (mx - int(r), my - int(r), int(r*2), int(r*2)), 1)

        # Tooltip finale sopra a tutto
        if hasattr(self, "_img_editor_tip") and self._img_editor_tip:
             from editor.ui.draw import _draw_tooltip
             _draw_tooltip(self.screen, self._img_editor_tip, (mx, my))
             self._img_editor_tip = ""

    def _r_vector_icon(self, name, rect, text_offset=0, active=False):
        """Disegna icone vettoriali semplici."""
        c = (255, 255, 255) if active else (180, 180, 190)
        if name == "rot_ccw":
            # Freccia rotazione antioraria
            pygame.draw.arc(self.screen, c, (rect.x+2, rect.y+5, 12, 12), 0.5, 4.5, 2)
            pygame.draw.polygon(self.screen, c, [(rect.x+2, rect.y+11), (rect.x+6, rect.y+11), (rect.x+4, rect.y+15)])
        elif name == "rot_cw":
            # Freccia rotazione oraria
            pygame.draw.arc(self.screen, c, (rect.x+2, rect.y+5, 12, 12), -1.5, 2.5, 2)
            pygame.draw.polygon(self.screen, c, [(rect.x+10, rect.y+11), (rect.x+14, rect.y+11), (rect.x+12, rect.y+15)])
        elif name == "crop":
            # Icona ritaglio (cornici)
            r = pygame.Rect(rect.x + 5, rect.y + 5, 14, 14)
            pygame.draw.lines(self.screen, c, False, [(r.x, r.y+5), (r.x, r.y), (r.x+5, r.y)], 2)
            pygame.draw.lines(self.screen, c, False, [(r.right-5, r.y), (r.right, r.y), (r.right, r.y+5)], 2)
            pygame.draw.lines(self.screen, c, False, [(r.right, r.bottom-5), (r.right, r.bottom), (r.right-5, r.bottom)], 2)
            pygame.draw.lines(self.screen, c, False, [(r.x+5, r.bottom), (r.x, r.bottom), (r.x, r.bottom-5)], 2)
        elif name == "eraser":
            # Icona gomma realistica (con parte che cancella e impugnatura)
            r = rect.inflate(-4, -4)
            # Parte superiore (impugnatura)
            pygame.draw.rect(self.screen, c, (r.x, r.y, r.w, r.h//2), border_radius=2)
            # Parte inferiore (gomma)
            pygame.draw.rect(self.screen, c, (r.x+2, r.y+r.h//2, r.w-4, r.h//2), 1, border_radius=1)
        elif name == "blur":
            # Icona sfumatura (cerchio con aura)
            cx, cy = rect.center
            for r_a in range(12, 0, -3):
                alpha = 255 - (r_a * 15)
                # Simuliamo sfumatura con cerchi multipli se possibile, o solo simbolico
                pygame.draw.circle(self.screen, c, (cx, cy), r_a, 1)
            pygame.draw.circle(self.screen, c, (cx, cy), 3)
        elif name == "circle_p":
            pygame.draw.circle(self.screen, c, rect.center, 12)
        elif name == "square_p":
            pygame.draw.rect(self.screen, c, rect.inflate(-14, -14), border_radius=2)

