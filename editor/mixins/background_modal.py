"""
editor/mixins/background_modal.py

BackgroundModalMixin — Dialogo selezione background con anteprime grandi, 
rinomina file, gestione tag, suggerimenti e ricerca evoluta.
Supporto avanzato per editing testo (cursore, scorciatoie, key repeat).
"""

import logging
import pygame
import shutil
from collections import OrderedDict
from pathlib import Path
from editor.constants import (
    ACCENT, BORDER, BTN, BTN_HO, BTN_AC,
    TXT, TXT_DIM, TXT_HI, OK_C, ERR_C, WARN_C,
)
from editor.core.asset_catalog import AssetCatalog
from editor.ui.draw import (
    _draw_text, _rect, _button, _in_rect, _scrollbar, _draw_shape_icon, _clamp, _text_wh
)

# Estensioni gestite dal modale background (immagini + video full-screen)
BG_EXTENSIONS = (".jpg", ".jpeg", ".png", ".bmp", ".mp4")
# Nome del catalogo tag persistente nella cartella backgrounds
BG_CATALOG_FILENAME = "backgrounds_catalog.json"
# Dimensione delle miniature nella griglia
BG_THUMB_SIZE = (250, 140)

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
        self._bg_suggestions = []

        self._bg_dir = self.base_path / "engine" / "assets" / "backgrounds"
        # Strato dati condiviso: scansione, tag, rename, delete, import, miniature.
        # L'istanza persiste tra le aperture (miniature in RAM riutilizzate).
        if getattr(self, "_bg_cat", None) is None:
            self._bg_cat = AssetCatalog(self._bg_dir, BG_EXTENSIONS,
                                        BG_CATALOG_FILENAME, thumb_size=BG_THUMB_SIZE)
        self._bg_cat.load()
        self._bg_all_files = self._bg_cat.refresh()
        self._bg_files = list(self._bg_all_files)
        self._bg_start_thumbnails()

    def _bg_start_thumbnails(self):
        """Avvia il caricamento asincrono delle miniature (cache disco .thumbs)."""
        self._bg_cat.start_thumbnail_thread(
            should_continue=lambda: getattr(self, "_bg_modal", False),
            # Invalida la cache di rendering per mostrare la nuova immagine
            on_thumbnail=lambda _name: self._bg_row_cache.clear(),
        )

    def _bg_modal_close(self):
        self._bg_modal = False
        self._bg_search_active = False
        self._bg_editing_name = None
        self._bg_editing_tags = None

    def _bg_update_filter(self, force=False):
        # force=True: la lista file e' cambiata (rename/delete/import) e va
        # ricalcolata anche a query invariata (il vecchio early-return lasciava
        # la griglia stale dopo queste operazioni).
        query = self._bg_search.lower().strip()
        query_changed = query != getattr(self, "_bg_last_query", None)
        if not force and not query_changed: return
        self._bg_last_query = query
        self._bg_files = self._bg_cat.search(query, tag_label_fn=self.tag_manager.get_label)
        if query_changed:
            self._bg_scroll = self._bg_scroll_target = 0
        self._bg_row_cache.clear() # Invalida solo al cambio query o lista

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
            elif active_field == "tags":
                if self._bg_tags_buffer:
                    new_tag = self.tag_manager.ensure_tag(self._bg_tags_buffer)
                    if new_tag:
                        self._bg_cat.add_tag(self._bg_editing_tags, new_tag)
                        self._bg_tags_buffer = ""
                        self._bg_cursor = 0
                        self._bg_update_suggestions()
                else:
                    self._bg_confirm_tags()
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
        self._bg_suggestions = self.tag_manager.get_suggestions(self._bg_tags_buffer, limit=5)

    def _bg_apply_suggestion(self, tag):
        if not self._bg_editing_tags: return
        self._bg_cat.add_tag(self._bg_editing_tags, tag)
        self._bg_tags_buffer = ""
        self._bg_cursor = 0
        self._bg_suggestions = []

    def _set_clipboard(self, text):
        try:
            import tkinter as tk
            r = tk.Tk(); r.withdraw()
            r.clipboard_clear(); r.clipboard_append(text)
            r.update(); r.destroy()
        except Exception: pass

    def _get_clipboard(self):
        try:
            import tkinter as tk
            r = tk.Tk(); r.withdraw()
            res = r.clipboard_get()
            r.destroy(); return res
        except Exception: return ""

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

                    # Edit Tags (il box e' renderizzato a iy + 245, vedi _r_background_modal)
                    if _in_rect((mx, my), (ix + 10, iy + 245, item_w - 20, 30)):
                        self._bg_confirm_rename(); self._bg_confirm_tags()
                        self._bg_editing_tags = name
                        self._bg_tags_buffer = "" # Ora è solo il campo di ricerca
                        self._bg_cursor = 0
                        self._bg_update_suggestions()
                        return

        self._bg_confirm_rename(); self._bg_confirm_tags()
        self._bg_search_active = False; self._bg_delete_pending = None

    def _bg_confirm_rename(self):
        if not self._bg_editing_name: return
        old_name, buf = self._bg_editing_name, self._bg_name_buffer.strip()
        # Rename validata (file + catalogo + miniature) delegata al catalogo
        if self._bg_cat.rename(old_name, buf):
            self._bg_update_filter(force=True)
        self._bg_editing_name = None

    def _bg_confirm_tags(self):
        # I tag sono salvati in tempo reale ad ogni aggiunta/rimozione ora, 
        # quindi questo serve solo a chiudere l'editing
        self._bg_editing_tags = None
        self._bg_suggestions = []
        self._bg_tags_buffer = ""
        self._bg_cursor = 0
        self._bg_update_filter()

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
                except Exception: pass
            else:
                self.bg_surf = None 
                self._fit_canvas(); self.scene_dirty = True
        self._bg_modal_close()

    def _bg_delete_file(self, name):
        # Soft-delete: sposta nel cestino .editor_trash/ invece di unlink diretto.
        # Recuperabile per 7 giorni e tracciato in .editor_audit.log.
        if not self._bg_cat.delete(name, reason="user_delete_background"):
            logging.warning(f"[BG] Delete fallita per '{name}'")
        self._bg_update_filter(force=True)
        self._bg_delete_pending = None

    def _bg_handle_drop(self, path_str: str):
        if not self._bg_modal: return
        t_name = self._bg_cat.import_file(Path(path_str))
        if not t_name: return
        self._bg_update_filter(force=True)
        self._bg_start_thumbnails()
        self._status(self._TR("modal_status_loaded").format(t_name), OK_C, 3)

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
                    thumb_surf = self._bg_cat.get_thumbnail(name)
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
                    
                    tags = self._bg_cat.get_tags(name)
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
                    # Rendering dell'interfaccia tag avanzata sopra la cella
                    # 1. Barra di ricerca
                    ir = pygame.Rect(ix + 10, iy + 245, item_w - 20, 30)
                    _input_box(self.screen, ir, self._bg_tags_buffer, focused=True, hint="Cerca o aggiungi...")
                    self._last_tags_x, self._last_tags_y = ix + 10, iy + 245
                    
                    # 2. Chip dei tag esistenti (rimovibili)
                    tags = self._bg_cat.get_tags(name)
                    for i, t_id in enumerate(tags):
                        # Disegniamo i chip in riga sopra l'input se c'è spazio, o gestiamo una riga extra
                        # Per ora, mostriamoli semplicemente come chip cliccabili per rimuoverli
                        # NOTA: qui potremmo aggiungere logica di rimozione al click
                        pass
                
                # Se non stiamo editando, mostriamo i chip statici (già fatto in cell_surf)

        self.screen.set_clip(None)
        _scrollbar(self.screen, list_x + list_w - 12, list_y + 15, 6, list_h - 30, self._bg_scroll, total_h_px, list_h)
        _draw_text(self.screen, self._TR("modal_drag_drop"), "sm", ACCENT, dx + dw - 280, dy + dh - 35)

