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
        # Stati Scrolling e Cache
        self._bg_scroll = 0.0
        self._bg_scroll_target = 0.0
        self._bg_scroll_vel = 0.0
        self._bg_is_dragging = False
        self._bg_row_cache = OrderedDict()
        self._bg_cache_max = 40
        self._bg_overlay_surf = getattr(self, "_bg_overlay_surf", None)
        
        # Miniature e Ricerca
        self._bg_thumbnails = getattr(self, "_bg_thumbnails", {})
        self._bg_thumb_lock = getattr(self, "_bg_thumb_lock", threading.Lock())
        self._bg_search = ""
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
        """Carica le miniature in background con protezione thread."""
        self._bg_loading_thumbs = True
        try:
            for name in self._bg_all_files:
                if not self._bg_modal: break
                if name in self._bg_thumbnails: continue
                if name.lower().endswith(".mp4"): continue
                try:
                    path = self._bg_dir / name
                    raw = pygame.image.load(str(path))
                    tw, th = 200, 112
                    thumb = pygame.transform.smoothscale(raw, (tw, th))
                    with self._bg_thumb_lock:
                        self._bg_thumbnails[name] = thumb
                    self._bg_row_cache.clear() # Invalida cache per mostrare la miniatura carica
                except: pass
        finally:
            self._bg_loading_thumbs = False

    def _bg_update_filter(self):
        query = self._bg_search.lower().strip()
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
        self._bg_row_cache.clear()

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
            if ev.key == pygame.K_a: # Seleziona tutto (sposta cursore a fine)
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
            # Filtro caratteri per il nome file
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
        """Analizza l'ultimo tag inserito e suggerisce match."""
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
        dw, dh = 1100, 800
        dx, dy = (w - dw) // 2, (h - dh) // 2
        if not _in_rect((mx, my), (dx, dy, dw, dh)): self._bg_modal_close(); return

        # Pulsante suggerimenti
        if self._bg_editing_tags and self._bg_suggestions:
            for i, sug in enumerate(self._bg_suggestions):
                s_r = pygame.Rect(self._last_tags_x + i*130, self._last_tags_y + 40, 120, 28)
                if _in_rect((mx, my), s_r):
                    self._bg_apply_suggestion(sug); return

        xr = pygame.Rect(dx + dw - 42, dy + 15, 26, 26)
        if _in_rect((mx, my), xr): self._bg_modal_close(); return

        search_r = pygame.Rect(dx + 25, dy + 60, dw - 50, 36)
        if _in_rect((mx, my), search_r):
            self._bg_confirm_rename(); self._bg_confirm_tags()
            self._bg_search_active = True; self._bg_cursor = len(self._bg_search)
            return
        
        list_x, list_y = dx + 25, dy + 130
        list_w, list_h = dw - 50, dh - 240
        row_h = 140 
        
        if _in_rect((mx, my), (list_x, list_y, list_w, list_h)):
            rel_y = my - list_y
            idx = int(rel_y // row_h + self._bg_scroll)
            if idx < len(self._bg_files):
                name = self._bg_files[idx]
                ry = list_y + (idx - self._bg_scroll) * row_h
                
                if _in_rect((mx, my), (list_x + list_w - 120, ry + 50, 100, 40)): # SCEGLI
                    self._bg_confirm_rename(); self._bg_confirm_tags(); self._bg_select(name); return
                if _in_rect((mx, my), (list_x + list_w - 170, ry + 50, 40, 40)): # ELIMINA
                    if self._bg_delete_pending == name: self._bg_delete_file(name)
                    else: self._bg_confirm_rename(); self._bg_confirm_tags(); self._bg_delete_pending = name
                    return
                
                # Hit EDIT NOME
                if _in_rect((mx, my), (list_x + 240, ry + 20, 400, 30)):
                    self._bg_confirm_rename(); self._bg_confirm_tags()
                    self._bg_editing_name = name; self._bg_name_buffer = Path(name).stem
                    self._bg_cursor = len(self._bg_name_buffer)
                    return
                
                # Hit EDIT TAGS
                if _in_rect((mx, my), (list_x + 240, ry + 60, 500, 60)):
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
            
            # Se è un'immagine, carica la surface per l'anteprima canvas
            if not is_vid:
                try:
                    self.bg_surf = pygame.image.load(str(dest)).convert()
                    self._bg_cache_surf = None; self._fit_canvas(); self.scene_dirty = True
                except: pass
            else:
                self.bg_surf = None # Il video verrà renderizzato dal core se supportato
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
            
            # Scorrimento automatico a fine lista
            v_rows = (800 - 190) // 140
            self._bg_scroll = max(0, len(self._bg_files) - v_rows)
            
            self._status(self._TR("modal_status_loaded").format(t_name), OK_C, 3)
        except: pass

    def _bg_modal_wheel(self, dy):
        if not self._bg_modal: return
        self._bg_scroll_target -= dy * 120.0
        self._bg_scroll_vel = 0

    def _r_background_modal(self, w, h):
        if not getattr(self, "_bg_modal", False): return
        
        if not self._bg_overlay_surf or self._bg_overlay_surf.get_size() != (w, h):
            self._bg_overlay_surf = pygame.Surface((w, h), pygame.SRCALPHA)
            self._bg_overlay_surf.fill((0, 0, 0, 235))
        self.screen.blit(self._bg_overlay_surf, (0, 0))

        dw, dh = 1100, 800
        dx, dy = (w - dw) // 2, (h - dh) // 2
        _rect(self.screen, (30, 32, 45), (dx, dy, dw, dh), radius=24)
        _rect(self.screen, ACCENT, (dx, dy, dw, dh), 2, radius=24)
        _draw_text(self.screen, self._TR("modal_bg_title"), "lg", TXT_HI, dx + 30, dy + 25)
        
        mx, my = pygame.mouse.get_pos()
        xr = pygame.Rect(dx + dw - 45, dy + 20, 30, 30)
        _button(self.screen, xr, "X", _in_rect((mx, my), xr), danger=True)

        # Barra di ricerca
        search_r = pygame.Rect(dx + 30, dy + 70, dw - 60, 38)
        s_bg = (20, 22, 32) if self._bg_search_active else (25, 27, 38)
        _rect(self.screen, s_bg, search_r, radius=12)
        _rect(self.screen, ACCENT if self._bg_search_active else BORDER, search_r, 1, radius=12)
        _draw_text(self.screen, self._bg_search or self._TR("modal_search_placeholder"), "md", 
                  TXT_HI if self._bg_search or self._bg_search_active else TXT_DIM, search_r.x + 15, search_r.y + 8)
        
        if self._bg_search_active and (pygame.time.get_ticks() // 500) % 2:
            tw, _ = _text_wh(self._bg_search[:self._bg_cursor], "md")
            pygame.draw.line(self.screen, ACCENT, (search_r.x + 15 + tw, search_r.y + 10), (search_r.x + 15 + tw, search_r.y + 28), 2)

        # LIST CONTAINER
        list_x, list_y, list_w, list_h = dx + 25, dy + 130, dw - 50, dh - 240
        _rect(self.screen, (15, 17, 26), (list_x, list_y, list_w, list_h), radius=16)
        _rect(self.screen, (40, 42, 65), (list_x, list_y, list_w, list_h), 1, radius=16) 

        row_h = 140
        total_items = len(self._bg_files)
        total_h = total_items * row_h
        max_scroll_px = max(0, total_h - list_h)

        # Scrolling Fisico
        self._bg_scroll_target += self._bg_scroll_vel
        self._bg_scroll_vel *= 0.92
        if abs(self._bg_scroll_vel) < 0.1: self._bg_scroll_vel = 0.0
        self._bg_scroll_target = _clamp(self._bg_scroll_target, 0, max_scroll_px)
        
        self._bg_scroll += (self._bg_scroll_target - self._bg_scroll) * 0.15
        if abs(self._bg_scroll - self._bg_scroll_target) < 0.5: self._bg_scroll = self._bg_scroll_target

        start_idx = max(0, int(self._bg_scroll // row_h))
        end_idx = min(total_items, start_idx + (list_h // row_h) + 2)

        self.screen.set_clip(pygame.Rect(list_x, list_y, list_w, list_h))
        
        for i in range(start_idx, end_idx):
            name = self._bg_files[i]
            ry = int(round(list_y + i * row_h - self._bg_scroll))
            
            row_r = pygame.Rect(list_x + 12, ry + 10, list_w - 24, row_h - 20)
            hov = _in_rect((mx, my), row_r)
            is_del = (self._bg_delete_pending == name)
            is_ed_n = (self._bg_editing_name == name)
            is_ed_t = (self._bg_editing_tags == name)
            
            # Cache Key
            cache_key = (name, hov, is_del, is_ed_n, is_ed_t)
            
            if cache_key in self._bg_row_cache:
                row_surf = self._bg_row_cache[cache_key]
                self._bg_row_cache.move_to_end(cache_key)
            else:
                row_surf = pygame.Surface((list_w - 24, row_h - 20), pygame.SRCALPHA)
                _rect(row_surf, (40, 43, 60) if hov else (24, 26, 38), (0, 0, list_w - 24, row_h - 20), radius=15)
                if hov: _rect(row_surf, (60, 65, 90), (0, 0, list_w - 24, row_h - 20), 1, radius=15)

                # 1. THUMBNAIL
                thumb_r = pygame.Rect(16, 4, 200, 112)
                _rect(row_surf, (10, 12, 18), thumb_r, radius=8)
                with self._bg_thumb_lock: thumb_surf = self._bg_thumbnails.get(name)
                if thumb_surf: row_surf.blit(thumb_surf, thumb_r.topleft)
                else: _draw_shape_icon(row_surf, thumb_r.inflate(-100, -50), "camera", (50, 55, 75))

                # 2. NOME
                text_x = 238
                if not is_ed_n:
                    _draw_text(row_surf, name, "md", TXT_HI, text_x, 10, 400)
                    _draw_shape_icon(row_surf, (text_x+_text_wh(name, "md")[0]+12, 10, 24, 24), "edit", ACCENT)

                # 3. TAGS
                tags = self._bg_catalog.get(name, {}).get("tags", [])
                tag_y = 52
                if not is_ed_t:
                    if not tags: _draw_text(row_surf, self._TR("modal_add_tag"), "sm", TXT_DIM, text_x, tag_y)
                    else:
                        curr_x = text_x
                        for t in tags:
                            tw, _ = _text_wh(t, "sm"); tr = pygame.Rect(curr_x, tag_y, tw+20, 24)
                            _rect(row_surf, (45, 55, 80), (curr_x, tag_y, tw+20, 24), radius=12)
                            _draw_text(row_surf, t, "sm", TXT_HI, curr_x+10, tag_y+3)
                            curr_x += tw + 30
                            if curr_x > 700: break

                # 4. AZIONI
                sel_r = pygame.Rect(list_w - 24 - 110, 40, 100, 40)
                _button(row_surf, sel_r, self._TR("modal_btn_select"), _in_rect((mx - list_x - 12, my - ry - 10), sel_r))
                del_r = pygame.Rect(list_w - 24 - 160, 40, 40, 40)
                _button(row_surf, del_r, "X" if not is_del else "!", _in_rect((mx - list_x - 12, my - ry - 10), del_r), danger=True)
                if is_del: _draw_text(row_surf, self._TR("modal_confirm_delete"), "sm", (255,100,100), del_r[0] - 70, del_r[1] + 12)

                if len(self._bg_row_cache) >= self._bg_cache_max: self._bg_row_cache.popitem(last=False)
                self._bg_row_cache[cache_key] = row_surf

            self.screen.blit(row_surf, (list_x + 12, ry + 10))
            
            # Interactive parts outside row cache
            text_x = list_x + 250
            if is_ed_n:
                _rect(self.screen, (15, 15, 25), (text_x, ry+20, 400, 34), radius=6)
                _rect(self.screen, OK_C, (text_x, ry+20, 400, 34), 1, radius=6)
                _draw_text(self.screen, self._bg_name_buffer, "md", TXT_HI, text_x + 10, ry+26)
            if is_ed_t:
                _rect(self.screen, (15, 15, 25), (text_x, ry+62, 500, 34), radius=6)
                _rect(self.screen, ACCENT, (text_x, ry+62, 500, 34), 1, radius=6)
                _draw_text(self.screen, self._bg_tags_buffer, "sm", TXT_HI, text_x + 10, ry+70)

        self.screen.set_clip(None)
        _scrollbar(self.screen, list_x + list_w - 12, list_y + 10, 4, list_h - 20, self._bg_scroll, total_items, list_h // row_h)
        _draw_text(self.screen, self._TR("modal_drag_drop"), "sm", ACCENT, dx + dw - 250, dy + dh - 35)
