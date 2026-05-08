"""
editor/mixins/background_modal.py

BackgroundModalMixin — Dialogo selezione background con anteprime grandi, 
rinomina file, gestione tag, suggerimenti e ricerca evoluta.
Supporto avanzato per editing testo (cursore, scorciatoie, key repeat).
"""

import logging
import pygame
import shutil
import threading
import json
from collections import OrderedDict
from pathlib import Path
from editor.constants import (
    ACCENT, BORDER, BTN, BTN_HO, BTN_AC,
    TXT, TXT_DIM, TXT_HI, OK_C, ERR_C, WARN_C,
)
from editor.ui.draw import (
    _draw_text, _rect, _button, _in_rect, _scrollbar, _draw_shape_icon, _clamp, _text_wh
)

class BackgroundModalMixin:
    """Modale premium avanzata per la gestione dei background con UX testo migliorata."""

    def _bg_modal_open(self, context="scene"):
        self._bg_modal = True
        self._bg_modal_context = context
        self._bg_all_files = []
        self._bg_files = []
        # Stati Scrolling e Cache (Caching Intelligente)
        self._bg_scroll = 0.0
        self._bg_scroll_target = 0.0
        self._bg_scroll_vel = 0.0
        self._bg_is_dragging = False
        # La cache delle superfici delle celle viene mantenuta tra le aperture per velocità istantanea
        self._bg_row_cache = getattr(self, "_bg_row_cache", OrderedDict())
        self._bg_cache_max = 120 
        self._bg_overlay_surf = getattr(self, "_bg_overlay_surf", None)
        
        # Miniature e Ricerca
        self._bg_thumbnails = getattr(self, "_bg_thumbnails", {})
        self._bg_thumb_lock = getattr(self, "_bg_thumb_lock", threading.Lock())
        self._bg_search = ""
        self._bg_last_query = None
        self._bg_search_active = False
        self._bg_delete_pending = None
        
        # Stati Editing e suggerimenti
        self._bg_editing_name = None 
        self._bg_name_buffer = ""
        self._bg_editing_tags = None 
        self._bg_tags_buffer = ""
        self._bg_cursor = 0
        self._bg_all_library_tags = []
        self._bg_suggestions = []
        
        # Stato thread
        self._bg_loading_thumbs = getattr(self, "_bg_loading_thumbs", False)
        
        # Abilita ripetizione tasti
        pygame.key.set_repeat(500, 30)
        
        self._bg_dir = self.base_path / "engine" / "assets" / "backgrounds"
        self._bg_load_catalog()
        self._bg_refresh_library_tags()
        
        if self._bg_dir.exists():
            self._bg_all_files = sorted([f.name for f in self._bg_dir.glob("*") 
                                       if f.suffix.lower() in [".jpg", ".jpeg", ".png", ".bmp", ".mp4"] 
                                       and f.name != "backgrounds_catalog.json"])
            self._bg_files = list(self._bg_all_files)
            if not self._bg_loading_thumbs:
                threading.Thread(target=self._bg_load_thumbnails_task, daemon=True).start()
        else:
            logging.error(f"Cartella background non trovata: {self._bg_dir}")

    def _bg_load_catalog(self):
        cat_path = self._bg_dir / "backgrounds_catalog.json"
        if cat_path.exists():
            try:
                with open(cat_path, "r", encoding="utf-8") as f:
                    self._bg_catalog = json.load(f)
            except: self._bg_catalog = {}
        else: self._bg_catalog = {}

    def _bg_save_catalog(self):
        cat_path = self._bg_dir / "backgrounds_catalog.json"
        try:
            self._bg_dir.mkdir(parents=True, exist_ok=True)
            with open(cat_path, "w", encoding="utf-8") as f:
                json.dump(self._bg_catalog, f, indent=2)
            self._bg_refresh_library_tags()
        except Exception as e:
            logging.error(f"Errore salvataggio catalogo BG: {e}")

    def _bg_refresh_library_tags(self):
        """Raccoglie tutti i tag unici esistenti per i suggerimenti."""
        tags = set()
        for data in self._bg_catalog.values():
            tags.update(data.get("tags", []))
        self._bg_all_library_tags = sorted(list(tags))

    def _bg_modal_close(self):
        self._bg_modal = False
        self._bg_search_active = False
        self._bg_editing_name = None
        self._bg_editing_tags = None
        pygame.key.set_repeat(0, 0) # Disabilita

    def _bg_load_thumbnails_task(self):
        """Carica le miniature con Disk Caching (PNG) per massima compatibilità."""
        self._bg_loading_thumbs = True
        cache_dir = self._bg_dir / ".thumbs"
        try:
            cache_dir.mkdir(parents=True, exist_ok=True)
            for name in self._bg_all_files:
                if not self._bg_modal: break
                if name in self._bg_thumbnails: continue
                if name.lower().endswith((".mp4", ".mov", ".mkv")): continue
                
                try:
                    # Usiamo .png esplicito per la cache per evitare errori di formato
                    thumb_path = cache_dir / f"{name}.png"
                    thumb = None
                    
                    if thumb_path.exists():
                        try:
                            # Caricamento da cache disco
                            thumb = pygame.image.load(str(thumb_path)).convert_alpha()
                        except:
                            # Se la cache è corrotta, la eliminiamo per rigenerarla
                            thumb_path.unlink(missing_ok=True)
                    
                    if not thumb:
                        # Generazione o rigenerazione dall'originale
                        path = self._bg_dir / name
                        raw = pygame.image.load(str(path))
                        tw, th = 250, 140
                        thumb = pygame.transform.smoothscale(raw, (tw, th))
                        # Salvataggio con estensione standard
                        pygame.image.save(thumb, str(thumb_path))
                    
                    if thumb:
                        with self._bg_thumb_lock:
                            self._bg_thumbnails[name] = thumb
                        # Invalida cache rendering per mostrare la nuova immagine
                        if hasattr(self, "_bg_row_cache"): self._bg_row_cache.clear()
                except Exception as e:
                    logging.debug(f"Errore caricamento miniatura {name}: {e}")
        finally:
            self._bg_loading_thumbs = False

    def _bg_update_filter(self):
        query = self._bg_search.lower().strip()
        if query == getattr(self, "_bg_last_query", None): return 
        self._bg_last_query = query
        
        if not query:
            self._bg_files = list(self._bg_all_files)
        else:
            self._bg_files = []
            for f in self._bg_all_files:
                tags = self._bg_catalog.get(f, {}).get("tags", [])
                tags_str = " ".join(tags).lower()
                if query in f.lower() or query in tags_str:
                    self._bg_files.append(f)
        
        self._bg_scroll = self._bg_scroll_target = 0
        self._bg_row_cache.clear() # Invalida solo al cambio query

    def _bg_modal_key(self, ev):
        if not self._bg_modal: return
        
        mods = pygame.key.get_mods()
        ctrl = bool(mods & pygame.KMOD_CTRL)
        
        if ev.key == pygame.K_ESCAPE:
            if self._bg_editing_name or self._bg_editing_tags:
                self._bg_editing_name = self._bg_editing_tags = None
            elif self._bg_search_active:
                self._bg_search_active = False
            else:
                self._bg_modal_close()
            return

        active_field = None
        if self._bg_editing_name: active_field = "name"
        elif self._bg_editing_tags: active_field = "tags"
        elif self._bg_search_active: active_field = "search"
        
        if not active_field: return

        # ── SCORCIATOIE ──
        if ctrl:
            if ev.key == pygame.K_a: # Seleziona tutto
                buf = self._bg_get_buf(active_field)
                self._bg_cursor = len(buf); return
            if ev.key == pygame.K_c: # Copia
                buf = self._bg_get_buf(active_field)
                self._set_clipboard(buf); return
            if ev.key == pygame.K_v: # Incolla
                pst = self._get_clipboard()
                if pst: self._bg_insert_text(active_field, pst); return

        # ── EDITING STANDARD ──
        if ev.key == pygame.K_RETURN:
            if active_field == "name": self._bg_confirm_rename()
            elif active_field == "tags": self._bg_confirm_tags()
            elif active_field == "search": self._bg_search_active = False
        elif ev.key == pygame.K_BACKSPACE:
            self._bg_delete_char(active_field)
        elif ev.key == pygame.K_LEFT:
            self._bg_cursor = max(0, self._bg_cursor - 1)
        elif ev.key == pygame.K_RIGHT:
            buf = self._bg_get_buf(active_field)
            self._bg_cursor = min(len(buf), self._bg_cursor + 1)
        elif ev.unicode.isprintable():
            if active_field == "name" and ev.unicode in r'/\:*?"<>|': return
            self._bg_insert_text(active_field, ev.unicode)

    def _bg_get_buf(self, field):
        if field == "name": return self._bg_name_buffer
        if field == "tags": return self._bg_tags_buffer
        return self._bg_search

    def _bg_insert_text(self, field, text):
        if field == "name":
            self._bg_name_buffer = self._bg_name_buffer[:self._bg_cursor] + text + self._bg_name_buffer[self._bg_cursor:]
        elif field == "tags":
            self._bg_tags_buffer = self._bg_tags_buffer[:self._bg_cursor] + text + self._bg_tags_buffer[self._bg_cursor:]
            self._bg_update_suggestions()
        else:
            self._bg_search = self._bg_search[:self._bg_cursor] + text + self._bg_search[self._bg_cursor:]
            self._bg_update_filter()
        self._bg_cursor += len(text)

    def _bg_delete_char(self, field):
        if self._bg_cursor <= 0: return
        if field == "name":
            self._bg_name_buffer = self._bg_name_buffer[:self._bg_cursor-1] + self._bg_name_buffer[self._bg_cursor:]
        elif field == "tags":
            self._bg_tags_buffer = self._bg_tags_buffer[:self._bg_cursor-1] + self._bg_tags_buffer[self._bg_cursor:]
            self._bg_update_suggestions()
        else:
            self._bg_search = self._bg_search[:self._bg_cursor-1] + self._bg_search[self._bg_cursor:]
            self._bg_update_filter()
        self._bg_cursor -= 1

    def _bg_update_suggestions(self):
        parts = [p.strip().lower() for p in self._bg_tags_buffer.split(",")]
        curr = parts[-1] if parts else ""
        if not curr: self._bg_suggestions = []; return
        self._bg_suggestions = [t for t in self._bg_all_library_tags if t.startswith(curr) and t not in parts][:5]

    def _bg_apply_suggestion(self, tag):
        parts = [p.strip() for p in self._bg_tags_buffer.split(",")]
        if parts: parts[-1] = tag
        else: parts = [tag]
        self._bg_tags_buffer = ", ".join(parts) + ", "
        self._bg_cursor = len(self._bg_tags_buffer)
        self._bg_suggestions = []

    def _set_clipboard(self, text):
        try:
            import tkinter as tk
            r = tk.Tk(); r.withdraw()
            r.clipboard_clear(); r.clipboard_append(text)
            r.update(); r.destroy()
        except: pass

    def _get_clipboard(self):
        try:
            import tkinter as tk
            r = tk.Tk(); r.withdraw()
            res = r.clipboard_get()
            r.destroy(); return res
        except: return ""

    def _bg_modal_click(self, mx, my, w, h):
        if not self._bg_modal: return
        # Dimensioni dinamiche bilanciate
        dw, dh = int(w * 0.88), int(h * 0.84)
        dw = _clamp(dw, 1100, 2000)
        dh = _clamp(dh, 700, 1200)
        dx, dy = (w - dw) // 2, (h - dh) // 2
        
        if not _in_rect((mx, my), (dx, dy, dw, dh)): 
            self._bg_confirm_rename(); self._bg_confirm_tags()
            self._bg_modal_close(); return

        # Pulsante suggerimenti
        if self._bg_editing_tags and self._bg_suggestions:
            for i, sug in enumerate(self._bg_suggestions):
                s_r = pygame.Rect(self._last_tags_x + i*130, self._last_tags_y + 40, 120, 28)
                if _in_rect((mx, my), s_r):
                    self._bg_apply_suggestion(sug); return

        xr = pygame.Rect(dx + dw - 42, dy + 15, 26, 26)
        if _in_rect((mx, my), xr): self._bg_modal_close(); return

        search_r = pygame.Rect(dx + 30, dy + 65, dw - 60, 38)
        if _in_rect((mx, my), search_r):
            self._bg_confirm_rename(); self._bg_confirm_tags()
            self._bg_search_active = True; self._bg_cursor = len(self._bg_search)
            return
        
        list_x, list_y = dx + 30, dy + 130
        list_w, list_h = dw - 60, dh - 240
        
        # Logica Griglia
        item_w, item_h = 280, 300 
        padding = 20
        cols = max(1, (list_w - padding) // (item_w + padding))
        
        if _in_rect((mx, my), (list_x, list_y, list_w, list_h)):
            rel_y = my - list_y + self._bg_scroll
            rel_x = mx - list_x - padding
            
            row = int(rel_y // item_h)
            col = int(rel_x // (item_w + padding))
            
            if 0 <= col < cols:
                idx = row * cols + col
                if idx < len(self._bg_files):
                    name = self._bg_files[idx]
                    ix = list_x + padding + col * (item_w + padding)
                    iy = list_y + padding + row * item_h - self._bg_scroll
                    
                    # Hit Buttons
                    if _in_rect((mx, my), (ix + 15, iy + 155, 120, 38)):
                        self._bg_confirm_rename(); self._bg_confirm_tags(); self._bg_select(name); return
                    if _in_rect((mx, my), (ix + item_w - 55, iy + 155, 40, 38)):
                        if self._bg_delete_pending == name: self._bg_delete_file(name)
                        else: self._bg_confirm_rename(); self._bg_confirm_tags(); self._bg_delete_pending = name
                        return
                    
                    # Edit Nome
                    if _in_rect((mx, my), (ix + 10, iy + 205, item_w - 20, 30)):
                        self._bg_confirm_rename(); self._bg_confirm_tags()
                        self._bg_editing_name = name; self._bg_name_buffer = Path(name).stem
                        self._bg_cursor = len(self._bg_name_buffer)
                        return
                    
                    # Edit Tags
                    if _in_rect((mx, my), (ix + 10, iy + 245, item_w - 20, 30)):
                        self._bg_confirm_rename(); self._bg_confirm_tags()
                        self._bg_editing_tags = name
                        tags = self._bg_catalog.get(name, {}).get("tags", [])
                        self._bg_tags_buffer = ", ".join(tags) + (", " if tags else "")
                        self._bg_cursor = len(self._bg_tags_buffer)
                        return

        self._bg_confirm_rename(); self._bg_confirm_tags()
        self._bg_search_active = False; self._bg_delete_pending = None

    def _bg_confirm_rename(self):
        if not self._bg_editing_name: return
        old_name, buf = self._bg_editing_name, self._bg_name_buffer.strip()
        new_name = buf + Path(old_name).suffix
        if new_name != old_name and buf:
            try:
                (self._bg_dir/old_name).rename(self._bg_dir/new_name)
                if old_name in self._bg_catalog: self._bg_catalog[new_name] = self._bg_catalog.pop(old_name)
                self._bg_save_catalog()
                idx = self._bg_all_files.index(old_name); self._bg_all_files[idx] = new_name
                with self._bg_thumb_lock:
                    if old_name in self._bg_thumbnails: self._bg_thumbnails[new_name] = self._bg_thumbnails.pop(old_name)
                self._bg_update_filter()
            except: pass
        self._bg_editing_name = None

    def _bg_confirm_tags(self):
        if not self._bg_editing_tags: return
        name = self._bg_editing_tags
        tags = sorted(list(set([t.strip().lower() for t in self._bg_tags_buffer.split(",") if t.strip()])))
        if name not in self._bg_catalog: self._bg_catalog[name] = {}
        self._bg_catalog[name]["tags"] = tags
        self._bg_save_catalog(); self._bg_update_filter()
        self._bg_editing_tags = None; self._bg_suggestions = []

    def _bg_select(self, name):
        src = self._bg_dir / name
        is_vid = name.lower().endswith((".mp4", ".mov", ".mkv"))
        ctx = getattr(self, "_bg_modal_context", "scene")
        if ctx.startswith("game") or ctx.startswith("scene_"):
            prefix = "new" if "new" in ctx else "edit"
            if is_vid:
                setattr(self, f"_gs_{prefix}_vid_path", str(src))
                setattr(self, f"_gs_{prefix}_bg_path", "")
            else:
                setattr(self, f"_gs_{prefix}_bg_path", str(src))
                setattr(self, f"_gs_{prefix}_vid_path", "")
            self._gs_update_previews(prefix)
        else:
            if not getattr(self, "scene_path", None): return
            self._push_undo(); dest = self.scene_path / name
            if src.exists() and not dest.exists(): shutil.copy2(str(src), str(dest))
            self.scene_data["background"] = name
            if not is_vid:
                try:
                    self.bg_surf = pygame.image.load(str(dest)).convert()
                    self._bg_cache_surf = None; self._fit_canvas(); self.scene_dirty = True
                except: pass
            else:
                self.bg_surf = None 
                self._fit_canvas(); self.scene_dirty = True
        self._bg_modal_close()

    def _bg_delete_file(self, name):
        try:
            p = self._bg_dir / name
            if p.exists():
                import os; os.remove(str(p))
                if name in self._bg_all_files: self._bg_all_files.remove(name)
                with self._bg_thumb_lock:
                    if name in self._bg_thumbnails: del self._bg_thumbnails[name]
                if name in self._bg_catalog: del self._bg_catalog[name]
                self._bg_save_catalog(); self._bg_update_filter()
        except: pass
        self._bg_delete_pending = None

    def _bg_handle_drop(self, path_str: str):
        if not self._bg_modal: return
        src = Path(path_str)
        if not src.exists() or src.suffix.lower() not in [".jpg", ".jpeg", ".png", ".bmp", ".mp4"]: return
        t_name, c = src.name, 1
        while (self._bg_dir / t_name).exists(): t_name = f"{src.stem}_{c}{src.suffix}"; c += 1
        try:
            self._bg_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(src), str(self._bg_dir / t_name))
            if t_name not in self._bg_all_files:
                self._bg_all_files.append(t_name); self._bg_all_files.sort(); self._bg_update_filter()
            if t_name.lower().endswith((".jpg", ".jpeg", ".png", ".bmp")):
                threading.Thread(target=self._bg_load_thumbnails_task, daemon=True).start()
            self._status(self._TR("modal_status_loaded").format(t_name), OK_C, 3)
        except: pass

    def _bg_modal_wheel(self, dy):
        if not self._bg_modal: return
        self._bg_scroll_target -= dy * 180.0
        self._bg_scroll_vel = 0

    def _r_background_modal(self, w, h):
        if not getattr(self, "_bg_modal", False): return
        
        # Overlay Sfondo
        if not self._bg_overlay_surf or self._bg_overlay_surf.get_size() != (w, h):
            self._bg_overlay_surf = pygame.Surface((w, h), pygame.SRCALPHA)
            self._bg_overlay_surf.fill((0, 0, 0, 240))
        self.screen.blit(self._bg_overlay_surf, (0, 0))

        # Dimensioni Dinamiche Bilanciate
        dw, dh = int(w * 0.88), int(h * 0.84)
        dw = _clamp(dw, 1100, 2000)
        dh = _clamp(dh, 700, 1200)
        dx, dy = (w - dw) // 2, (h - dh) // 2
        
        _rect(self.screen, (32, 34, 48), (dx, dy, dw, dh), radius=28)
        _rect(self.screen, ACCENT, (dx, dy, dw, dh), 2, radius=28)
        _draw_text(self.screen, self._TR("modal_bg_title"), "lg", TXT_HI, dx + 35, dy + 25)
        
        mx, my = pygame.mouse.get_pos()
        xr = pygame.Rect(dx + dw - 48, dy + 20, 32, 32)
        _button(self.screen, xr, "X", _in_rect((mx, my), xr), danger=True)

        # Barra di ricerca evoluta
        search_r = pygame.Rect(dx + 35, dy + 70, dw - 70, 42)
        s_bg = (22, 24, 34) if self._bg_search_active else (28, 30, 42)
        _rect(self.screen, s_bg, search_r, radius=14)
        _rect(self.screen, ACCENT if self._bg_search_active else BORDER, search_r, 1, radius=14)
        _draw_text(self.screen, self._bg_search or self._TR("modal_search_placeholder"), "md", 
                  TXT_HI if self._bg_search or self._bg_search_active else TXT_DIM, search_r.x + 18, search_r.y + 10)
        
        if self._bg_search_active and (pygame.time.get_ticks() // 500) % 2:
            tw, _ = _text_wh(self._bg_search[:self._bg_cursor], "md")
            pygame.draw.line(self.screen, ACCENT, (search_r.x + 18 + tw, search_r.y + 12), (search_r.x + 18 + tw, search_r.y + 30), 2)

        # LIST CONTAINER (GRIGLIA)
        list_x, list_y, list_w, list_h = dx + 30, dy + 130, dw - 60, dh - 240
        _rect(self.screen, (18, 20, 28), (list_x, list_y, list_w, list_h), radius=20)
        _rect(self.screen, (45, 48, 70), (list_x, list_y, list_w, list_h), 1, radius=20) 

        item_w, item_h = 280, 300 # Altezza aggiornata
        padding = 20
        cols = max(1, (list_w - padding) // (item_w + padding))
        total_items = len(self._bg_files)
        rows = (total_items + cols - 1) // cols
        total_h_px = rows * item_h + padding * 2
        max_scroll_px = max(0, total_h_px - list_h)

        # Scrolling Fisico
        self._bg_scroll_target += self._bg_scroll_vel
        self._bg_scroll_vel *= 0.90
        self._bg_scroll_target = _clamp(self._bg_scroll_target, 0, max_scroll_px)
        self._bg_scroll += (self._bg_scroll_target - self._bg_scroll) * 0.18

        self.screen.set_clip(pygame.Rect(list_x, list_y, list_w, list_h))
        
        start_row = int(self._bg_scroll // item_h)
        end_row = start_row + (list_h // item_h) + 2

        for r in range(start_row, end_row):
            for c in range(cols):
                idx = r * cols + c
                if idx >= total_items: continue
                
                name = self._bg_files[idx]
                ix = list_x + padding + c * (item_w + padding)
                iy = int(round(list_y + padding + r * item_h - self._bg_scroll))
                
                if iy + item_h < list_y or iy > list_y + list_h: continue

                item_r = pygame.Rect(ix, iy, item_w, item_h - 10)
                hov = _in_rect((mx, my), item_r)
                is_del = (self._bg_delete_pending == name)
                is_ed_n = (self._bg_editing_name == name)
                is_ed_t = (self._bg_editing_tags == name)
                
                # Cache Cell
                cache_key = (name, hov, is_del, is_ed_n, is_ed_t)
                if cache_key in self._bg_row_cache:
                    cell_surf = self._bg_row_cache[cache_key]
                    self._bg_row_cache.move_to_end(cache_key)
                else:
                    cell_surf = pygame.Surface((item_w, item_h), pygame.SRCALPHA)
                    _rect(cell_surf, (48, 52, 75) if hov else (28, 30, 42), (0, 0, item_w, item_h - 10), radius=18)
                    if hov: _rect(cell_surf, ACCENT, (0, 0, item_w, item_h - 10), 1, radius=18)

                    # Thumbnail
                    thumb_r = pygame.Rect(15, 12, 250, 140)
                    _rect(cell_surf, (12, 14, 20), thumb_r, radius=10)
                    with self._bg_thumb_lock: thumb_surf = self._bg_thumbnails.get(name)
                    if thumb_surf: cell_surf.blit(thumb_surf, thumb_r.topleft)
                    else: _draw_shape_icon(cell_surf, thumb_r.inflate(-180, -80), "camera", (60, 65, 85))

                    # Pulsanti centrati
                    sel_r = pygame.Rect(15, 155, 120, 38)
                    _button(cell_surf, sel_r, self._TR("modal_btn_select"), _in_rect((mx-ix, my-iy), sel_r))
                    
                    del_r = pygame.Rect(item_w - 55, 155, 40, 38)
                    _button(cell_surf, del_r, "X" if not is_del else "!", _in_rect((mx-ix, my-iy), del_r), danger=True)
                    
                    # Nome e Tag con più spazio
                    if not is_ed_n:
                        _draw_text(cell_surf, name, "sm", TXT_HI, 15, 208, item_w - 30)
                    
                    tags = self._bg_catalog.get(name, {}).get("tags", [])
                    if not is_ed_t:
                        if tags:
                            t_str = ", ".join(tags)
                            _draw_text(cell_surf, t_str, "xs", TXT_DIM, 15, 248, item_w - 30)
                        else:
                            _draw_text(cell_surf, self._TR("modal_add_tag"), "xs", (80, 85, 105), 15, 248)

                    if len(self._bg_row_cache) >= self._bg_cache_max: self._bg_row_cache.popitem(last=False)
                    self._bg_row_cache[cache_key] = cell_surf

                self.screen.blit(cell_surf, (ix, iy))
                
                # Input dinamici (usando primitiva _input_box per coerenza e cursore)
                from editor.ui.draw import _input_box
                if is_ed_n:
                    ir = pygame.Rect(ix + 10, iy + 205, item_w - 20, 30)
                    _input_box(self.screen, ir, self._bg_name_buffer, focused=True)
                if is_ed_t:
                    ir = pygame.Rect(ix + 10, iy + 245, item_w - 20, 30)
                    # Gestione scrolling orizzontale simulato: mostra la parte finale del buffer se lungo
                    disp_tags = self._bg_tags_buffer
                    if _text_wh(disp_tags, "mono")[0] > ir.w - 15:
                        while _text_wh(disp_tags, "mono")[0] > ir.w - 25:
                            disp_tags = disp_tags[1:]
                    _input_box(self.screen, ir, disp_tags, focused=True)
                    self._last_tags_x, self._last_tags_y = ix + 10, iy + 245

        self.screen.set_clip(None)
        _scrollbar(self.screen, list_x + list_w - 12, list_y + 15, 6, list_h - 30, self._bg_scroll, total_h_px, list_h)
        _draw_text(self.screen, self._TR("modal_drag_drop"), "sm", ACCENT, dx + dw - 280, dy + dh - 35)

