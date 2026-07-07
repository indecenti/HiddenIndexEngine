"""
editor/mixins/video_modal.py

VideoModalMixin — Dialogo selezione video (.mp4) con icone dedicate,
rinomina file, gestione tag, suggerimenti e ricerca evoluta.
Basato sulla struttura di BackgroundModalMixin ma filtrato solo per video.
"""

import logging
import pygame
import cv2
import numpy as np
from pathlib import Path
from editor.constants import (
    ACCENT, BORDER, BTN, BTN_HO, BTN_AC,
    TXT, TXT_DIM, TXT_HI, OK_C, ERR_C, WARN_C,
)
from editor.core.asset_catalog import AssetCatalog
from editor.ui.draw import (
    _draw_text, _rect, _button, _in_rect, _scrollbar, _draw_shape_icon, _clamp, _text_wh
)

# Estensioni gestite dal modale video
VIDEO_EXTENSIONS = (".mp4", ".mov", ".mkv")
# File distinto da quello degli sfondi: condividere backgrounds_catalog.json
# (stessa cartella, schemi tag incompatibili) faceva sovrascrivere a vicenda
# i due modali. I video usano il proprio catalogo.
VIDEO_CATALOG_FILENAME = "videos_catalog.json"
# Dimensione delle miniature nella lista
VIDEO_THUMB_SIZE = (200, 112)

class VideoModalMixin:
    """Modale premium avanzata per la gestione dei video per il background dei giochi."""

    def _vid_modal_open(self, context="scene", autoplay_path=None):
        self._vid_modal = True
        self._vid_modal_context = context
        self._vid_dir = self.base_path / "engine" / "assets" / "backgrounds"

        # Inizializzazione stati
        self._vid_scroll = 0
        self._vid_search = ""
        self._vid_search_active = False
        self._vid_show_favorites = False
        self._vid_delete_pending = None
        self._vid_editing_name = None
        self._vid_name_buffer = ""
        self._vid_editing_tags = None
        self._vid_tags_buffer = ""
        self._vid_cursor = 0

        # Player
        self._vid_playing = None
        self._vid_preview_cap = None
        self._vid_preview_surf = None
        self._vid_suggestions = []

        # Strato dati condiviso: scansione ricorsiva (sottocartelle es. video/),
        # tag, rename, delete, import, miniature con cache disco .thumbs.
        # L'istanza persiste tra le aperture (miniature in RAM riutilizzate).
        if getattr(self, "_vid_cat", None) is None:
            self._vid_cat = AssetCatalog(self._vid_dir, VIDEO_EXTENSIONS,
                                         VIDEO_CATALOG_FILENAME, recursive=True,
                                         thumb_size=VIDEO_THUMB_SIZE)
        self._vid_cat.load()
        self._vid_all_files = self._vid_cat.refresh()
        self._vid_files = list(self._vid_all_files)

        # Autoplay se richiesto
        if autoplay_path:
            p = Path(autoplay_path)
            if p.exists():
                self._vid_playing = p.name
                self._vid_start_preview(p.name)

        # Caricamento miniature in thread (sidecar jpg/png o frame OpenCV)
        self._vid_cat.start_thumbnail_thread(
            generator=self._vid_thumb_generator,
            # Modale chiuso: non continuare a decodificare i video (CPU/IO leak)
            should_continue=lambda: getattr(self, "_vid_modal", False),
        )

    def _vid_thumb_generator(self, name):
        """Miniatura per un video: sidecar jpg/png se presente, altrimenti primo frame."""
        # Prova varianti: nome intero + .jpg, o stem + .jpg
        p = Path(name)
        candidates = [
            self._vid_dir / f"{name}.jpg",
            self._vid_dir / f"{name}.png",
            self._vid_dir / f"{p.stem}.jpg",
            self._vid_dir / f"{p.stem}.png"
        ]
        for c in candidates:
            if c.exists():
                try:
                    raw = pygame.image.load(str(c))
                    return pygame.transform.smoothscale(raw, VIDEO_THUMB_SIZE)
                except Exception: pass

        # Fallback: Estrazione frame con OpenCV
        try:
            cap = cv2.VideoCapture(str(self._vid_dir / name))
            try:
                ret, frame = cap.read()
            finally:
                cap.release()
            if ret:
                frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                frame = np.transpose(frame, (1, 0, 2))
                surf = pygame.surfarray.make_surface(frame)
                return pygame.transform.smoothscale(surf, VIDEO_THUMB_SIZE)
        except Exception: pass
        return None

    def _vid_modal_close(self):
        self._vid_modal = False
        self._vid_search_active = False
        self._vid_editing_name = None
        self._vid_editing_tags = None
        self._vid_stop_preview()
        self._vid_playing = None


    def _vid_update_filter(self):
        self._vid_files = self._vid_cat.search(self._vid_search)
        self._vid_scroll = 0

    def _vid_modal_key(self, ev):
        if not getattr(self, "_vid_modal", False): return
        
        mods = pygame.key.get_mods()
        ctrl = bool(mods & pygame.KMOD_CTRL)
        
        if ev.key == pygame.K_ESCAPE:
            if self._vid_editing_name or self._vid_editing_tags:
                self._vid_editing_name = self._vid_editing_tags = None
            elif self._vid_search_active:
                self._vid_search_active = False
            else:
                self._vid_modal_close()
            return

        active_field = None
        if self._vid_editing_name: active_field = "name"
        elif self._vid_editing_tags: active_field = "tags"
        elif self._vid_search_active: active_field = "search"
        
        if not active_field: return

        if ctrl:
            if ev.key == pygame.K_a:
                buf = self._vid_get_buf(active_field)
                self._vid_cursor = len(buf); return
            if ev.key == pygame.K_c:
                buf = self._vid_get_buf(active_field)
                self._set_clipboard(buf); return # Hereditary from mixin composition
            if ev.key == pygame.K_v:
                pst = self._get_clipboard()
                if pst: self._vid_insert_text(active_field, pst); return

        if ev.key == pygame.K_RETURN:
            if active_field == "name": self._vid_confirm_rename()
            elif active_field == "tags": self._vid_confirm_tags()
            elif active_field == "search": self._vid_search_active = False
        elif ev.key == pygame.K_BACKSPACE:
            self._vid_delete_char(active_field)
        elif ev.key == pygame.K_LEFT:
            self._vid_cursor = max(0, self._vid_cursor - 1)
        elif ev.key == pygame.K_RIGHT:
            buf = self._vid_get_buf(active_field)
            self._vid_cursor = min(len(buf), self._vid_cursor + 1)
        elif ev.unicode.isprintable():
            if active_field == "name" and ev.unicode in r'/\:*?"<>|': return
            self._vid_insert_text(active_field, ev.unicode)

    def _vid_get_buf(self, field):
        if field == "name": return self._vid_name_buffer
        if field == "tags": return self._vid_tags_buffer
        return self._vid_search

    def _vid_insert_text(self, field, text):
        if field == "name":
            self._vid_name_buffer = self._vid_name_buffer[:self._vid_cursor] + text + self._vid_name_buffer[self._vid_cursor:]
        elif field == "tags":
            self._vid_tags_buffer = self._vid_tags_buffer[:self._vid_cursor] + text + self._vid_tags_buffer[self._vid_cursor:]
            self._vid_update_suggestions()
        else:
            self._vid_search = self._vid_search[:self._vid_cursor] + text + self._vid_search[self._vid_cursor:]
            self._vid_update_filter()
        self._vid_cursor += len(text)

    def _vid_delete_char(self, field):
        if self._vid_cursor <= 0: return
        if field == "name":
            self._vid_name_buffer = self._vid_name_buffer[:self._vid_cursor-1] + self._vid_name_buffer[self._vid_cursor:]
        elif field == "tags":
            self._vid_tags_buffer = self._vid_tags_buffer[:self._vid_cursor-1] + self._vid_tags_buffer[self._vid_cursor:]
            self._vid_update_suggestions()
        else:
            self._vid_search = self._vid_search[:self._vid_cursor-1] + self._vid_search[self._vid_cursor:]
            self._vid_update_filter()
        self._vid_cursor -= 1

    def _vid_update_suggestions(self):
        parts = [p.strip().lower() for p in self._vid_tags_buffer.split(",")]
        curr = parts[-1] if parts else ""
        if not curr: self._vid_suggestions = []; return
        self._vid_suggestions = self._vid_cat.suggest_tags(curr, exclude=parts)

    def _vid_apply_suggestion(self, tag):
        parts = [p.strip() for p in self._vid_tags_buffer.split(",")]
        if parts: parts[-1] = tag
        else: parts = [tag]
        self._vid_tags_buffer = ", ".join(parts) + ", "
        self._vid_cursor = len(self._vid_tags_buffer)
        self._vid_suggestions = []

    def _vid_modal_click(self, mx, my, w, h):
        if not getattr(self, "_vid_modal", False): return
        dw, dh = 1100, 800
        dx, dy = (w - dw) // 2, (h - dh) // 2
        
        if not _in_rect((mx, my), (dx, dy, dw, dh)): self._vid_modal_close(); return

        if self._vid_editing_tags and self._vid_suggestions:
            for i, sug in enumerate(self._vid_suggestions):
                s_r = pygame.Rect(self._last_vtags_x + i*130, self._last_vtags_y + 40, 120, 28)
                if _in_rect((mx, my), s_r):
                    self._vid_apply_suggestion(sug); return

        xr = pygame.Rect(dx + dw - 42, dy + 15, 26, 26)
        if _in_rect((mx, my), xr): self._vid_modal_close(); return

        search_r = pygame.Rect(dx + 25, dy + 60, dw - 50, 36)
        if _in_rect((mx, my), search_r):
            self._vid_confirm_rename(); self._vid_confirm_tags()
            self._vid_search_active = True; self._vid_cursor = len(self._vid_search)
            return
        
        list_x, list_y = dx + 25, dy + 130
        list_w, list_h = dw - 50, dh - 240
        row_h = 140 
        
        if _in_rect((mx, my), (list_x, list_y, list_w, list_h)):
            rel_y = my - list_y
            idx = int(rel_y // row_h + self._vid_scroll)
            if idx < len(self._vid_files):
                name = self._vid_files[idx]
                ry = list_y + (idx - self._vid_scroll) * row_h
                
                # Detect click on THUMBNAIL AREA (Play/Stop Preview Inline)
                if _in_rect((mx, my), (list_x + 28, ry + 14, 200, 112)):
                    if self._vid_playing == name:
                        self._vid_stop_preview()
                    else:
                        self._vid_confirm_rename(); self._vid_confirm_tags()
                        self._vid_start_preview(name)
                    return

                if _in_rect((mx, my), (list_x + list_w - 120, ry + 50, 100, 40)):
                    self._vid_confirm_rename(); self._vid_confirm_tags(); self._vid_select(name); return
                if _in_rect((mx, my), (list_x + list_w - 170, ry + 50, 40, 40)):
                    if self._vid_delete_pending == name: self._vid_delete_file(name)
                    else: self._vid_confirm_rename(); self._vid_confirm_tags(); self._vid_delete_pending = name
                    return
                
                if _in_rect((mx, my), (list_x + 240, ry + 20, 400, 30)):
                    self._vid_confirm_rename(); self._vid_confirm_tags()
                    self._vid_editing_name = name; self._vid_name_buffer = Path(name).stem
                    self._vid_cursor = len(self._vid_name_buffer)
                    return
                
                if _in_rect((mx, my), (list_x + 240, ry + 60, 500, 60)):
                    self._vid_confirm_rename(); self._vid_confirm_tags()
                    self._vid_editing_tags = name
                    tags = self._vid_cat.get_tags(name)
                    self._vid_tags_buffer = ", ".join(tags) + (", " if tags else "")
                    self._vid_cursor = len(self._vid_tags_buffer)
                    return

        self._vid_confirm_rename(); self._vid_confirm_tags()
        self._vid_search_active = False; self._vid_delete_pending = None

    def _vid_start_preview(self, name):
        """Inizia la riproduzione dell'anteprima inline."""
        self._vid_stop_preview()
        p = self._vid_dir / name
        if not p.exists(): return
        
        self._vid_preview_cap = cv2.VideoCapture(str(p))
        self._vid_playing = name

    def _vid_stop_preview(self):
        """Ferma il player."""
        if hasattr(self, "_vid_preview_cap") and self._vid_preview_cap:
            self._vid_preview_cap.release()
        self._vid_preview_cap = None
        self._vid_preview_surf = None
        self._vid_playing = None

    def _vid_update_preview(self):
        """Legge il frame successivo e calcola il ratio di avanzamento."""
        if not self._vid_preview_cap: return 0.0
        ret, frame = self._vid_preview_cap.read()
        if not ret:
            self._vid_preview_cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ret, frame = self._vid_preview_cap.read()
        
        ratio = 0.0
        if ret:
            # Calcolo avanzamento
            total = self._vid_preview_cap.get(cv2.CAP_PROP_FRAME_COUNT)
            curr = self._vid_preview_cap.get(cv2.CAP_PROP_POS_FRAMES)
            if total > 0: ratio = curr / total

            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            frame = np.rot90(frame)
            frame = np.flipud(frame)
            self._vid_preview_surf = pygame.surfarray.make_surface(frame)
        return ratio

    def _vid_confirm_rename(self):
        if not self._vid_editing_name: return
        old_name, buf = self._vid_editing_name, self._vid_name_buffer.strip()
        # Rename validata (file + catalogo + miniature, sottocartella preservata)
        if self._vid_cat.rename(old_name, buf):
            self._vid_update_filter()
        self._vid_editing_name = None

    def _vid_confirm_tags(self):
        if not self._vid_editing_tags: return
        name = self._vid_editing_tags
        tags = [t.strip().lower() for t in self._vid_tags_buffer.split(",") if t.strip()]
        self._vid_cat.set_tags(name, tags)
        self._vid_update_filter()
        self._vid_editing_tags = None; self._vid_suggestions = []

    def _vid_select(self, name):
        src = self._vid_dir / name
        # Per ora la logica è la stessa di BG ma con variabili separate
        ctx = getattr(self, "_vid_modal_context", "scene")
        if ctx.startswith("game") or ctx.startswith("scene_"):
            prefix = "new" if "new" in ctx else "edit"
            setattr(self, f"_gs_{prefix}_vid_path", str(src))
            setattr(self, f"_gs_{prefix}_bg_path", "") # ESCLUSIVITÀ
            
            # Aggiorna anteprime nella dashboard
            self._gs_update_previews(prefix)
        else:
            # Scena: Non supportato in questa modale dedicata che è "solo lì" (game select)
            pass
        self._vid_modal_close()

    def _vid_delete_file(self, name):
        # Soft-delete nel cestino .editor_trash (recuperabile 7gg), come musica/sfondi.
        if not self._vid_cat.delete(name, reason="user_delete_video"):
            logging.warning(f"[VIDEO] Delete fallita per '{name}'")
        self._vid_update_filter()
        self._vid_delete_pending = None

    def _vid_handle_drop(self, path_str: str):
        if not getattr(self, "_vid_modal", False): return
        t_name = self._vid_cat.import_file(Path(path_str))
        if not t_name: return
        self._vid_update_filter()
        self._vid_cat.start_thumbnail_thread(
            generator=self._vid_thumb_generator,
            should_continue=lambda: getattr(self, "_vid_modal", False),
        )
        v_rows = (800 - 190) // 140
        self._vid_scroll = max(0, len(self._vid_files) - v_rows)
        self._status(self._TR("modal_status_loaded").format(t_name), OK_C, 3)

    def _vid_modal_wheel(self, dy):
        if not getattr(self, "_vid_modal", False): return
        v_rows = (800 - 160) // 140
        max_scroll = max(0, len(self._vid_files) - v_rows)
        self._vid_scroll = _clamp(self._vid_scroll - dy * 0.5, 0, max_scroll)

    def _r_video_modal(self, w, h):
        if not getattr(self, "_vid_modal", False): return
        overlay = pygame.Surface((w, h), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 235)); self.screen.blit(overlay, (0, 0))

        dw, dh = 1100, 800
        dx, dy = (w - dw) // 2, (h - dh) // 2
        _rect(self.screen, (25, 30, 45), (dx, dy, dw, dh), radius=24)
        _rect(self.screen, (100, 100, 255), (dx, dy, dw, dh), 2, radius=24)
        _draw_text(self.screen, self._TR("modal_vid_title"), "lg", TXT_HI, dx + 30, dy + 25)
        
        mx, my = pygame.mouse.get_pos()
        xr = pygame.Rect(dx + dw - 45, dy + 20, 30, 30)
        _rect(self.screen, (200, 50, 50) if _in_rect((mx, my), xr) else (50, 55, 75), xr, radius=8)
        _draw_text(self.screen, "x", "md", TXT_HI, xr.x + 10, xr.y + 2)

        search_r = pygame.Rect(dx + 30, dy + 70, dw - 60, 38)
        s_bg = (20, 22, 32) if self._vid_search_active else (25, 27, 38)
        _rect(self.screen, s_bg, search_r, radius=12)
        _rect(self.screen, (100, 100, 250) if self._vid_search_active else BORDER, search_r, 1, radius=12)
        _draw_text(self.screen, self._vid_search or self._TR("modal_search_placeholder"), "md", 
                  TXT_HI if self._vid_search or self._vid_search_active else TXT_DIM, search_r.x + 15, search_r.y + 8)
        
        if self._vid_search_active and (pygame.time.get_ticks() // 500) % 2:
            tw, _ = _text_wh(self._vid_search[:self._vid_cursor], "md")
            pygame.draw.line(self.screen, (100, 100, 255), (search_r.x + 15 + tw, search_r.y + 10), (search_r.x + 15 + tw, search_r.y + 28), 2)

        list_x, list_y, list_w, list_h = dx + 25, dy + 130, dw - 50, dh - 240
        _rect(self.screen, (15, 17, 26), (list_x, list_y, list_w, list_h), radius=16)
        _rect(self.screen, (40, 45, 75), (list_x, list_y, list_w, list_h), 1, radius=16) 

        self.screen.set_clip(pygame.Rect(list_x, list_y, list_w, list_h))
        row_h = 140
        for i, name in enumerate(self._vid_files):
            ry = int(list_y + (i - self._vid_scroll) * row_h)
            if ry + row_h < list_y or ry > list_y + list_h: continue
            
            row_r = pygame.Rect(list_x + 12, ry + 10, list_w - 24, row_h - 20)
            hov = _in_rect((mx, my), row_r)
            _rect(self.screen, (35, 40, 65) if hov else (22, 25, 42), row_r, radius=15)

            # ANTEPRIMA VIDEO (Thumbnail / Player Inline)
            thumb_r = pygame.Rect(list_x + 28, ry + 14, 200, 112)
            _rect(self.screen, (10, 10, 20), thumb_r, radius=8)
            
            is_playing = (self._vid_playing == name)
            vid_ratio = 0.0
            if is_playing:
                vid_ratio = self._vid_update_preview()
                if self._vid_preview_surf:
                    scaled = pygame.transform.smoothscale(self._vid_preview_surf, (200, 112))
                    self.screen.blit(scaled, thumb_r.topleft)
            else:
                thumb = self._vid_cat.get_thumbnail(name)
                if thumb is not None:
                    self.screen.blit(thumb, thumb_r.topleft)
                else:
                    _rect(self.screen, (25, 27, 45), thumb_r, radius=8)
                    _draw_text(self.screen, self._TR("modal_no_preview"), "sm", (60, 65, 90), thumb_r.centerx - 45, thumb_r.centery - 10)

            # PROGRESS BAR (Sotto il video, se in play)
            if is_playing:
                bar_h = 4
                pygame.draw.rect(self.screen, (50, 55, 80), (thumb_r.x, thumb_r.bottom - bar_h, thumb_r.w, bar_h))
                pygame.draw.rect(self.screen, ACCENT, (thumb_r.x, thumb_r.bottom - bar_h, int(thumb_r.w * vid_ratio), bar_h))

            # PLAY/STOP BUTTON OVERLAY (Premium)
            c_p = thumb_r.center
            play_hov = _in_rect((mx, my), thumb_r)
            
            # Durante il play l'overlay è più discreto
            c_bg = (50, 60, 100, 210) if play_hov else ((30, 35, 60, 100) if is_playing else (25, 30, 50, 180))
            pygame.draw.circle(self.screen, c_bg, c_p, 28)
            pygame.draw.circle(self.screen, (150, 150, 255) if play_hov else (100, 100, 255), c_p, 28, 2)
            
            p_size = 22
            p_r = pygame.Rect(0, 0, p_size, p_size); p_r.center = (c_p[0] + (2 if not is_playing else 0), c_p[1])
            _draw_shape_icon(self.screen, p_r, "play" if not is_playing else "stop", (255, 255, 255) if play_hov else (200, 200, 200))
            
            _draw_text(self.screen, self._TR("modal_video_label"), "xs", (100, 120, 255), thumb_r.x + 8, thumb_r.y + 8)

            text_x = list_x + 250
            if self._vid_editing_name == name:
                _rect(self.screen, (10, 10, 20), (text_x, ry+20, 400, 34), radius=6)
                _rect(self.screen, OK_C, (text_x, ry+20, 400, 34), 1, radius=6)
                _draw_text(self.screen, self._vid_name_buffer, "md", TXT_HI, text_x + 10, ry+26)
            else:
                _draw_text(self.screen, name, "md", TXT_HI, text_x, ry+20, 400)
                _draw_shape_icon(self.screen, (text_x+_text_wh(name, "md")[0]+12, ry+20, 24, 24), "edit", (100, 100, 255))

            tags = self._vid_cat.get_tags(name)
            tag_y = ry + 62
            if self._vid_editing_tags == name:
                self._last_vtags_x, self._last_vtags_y = text_x, tag_y
                _rect(self.screen, (10, 10, 20), (text_x, tag_y, 500, 34), radius=6)
                _rect(self.screen, ACCENT, (text_x, tag_y, 500, 34), 1, radius=6)
                _draw_text(self.screen, self._vid_tags_buffer, "sm", TXT_HI, text_x + 10, tag_y + 8)
                if self._vid_suggestions:
                    for j, sug in enumerate(self._vid_suggestions):
                        s_r = pygame.Rect(text_x + j*130, tag_y + 40, 120, 28)
                        _rect(self.screen, BTN_AC if _in_rect((mx, my), s_r) else (40, 45, 65), s_r, radius=14)
                        _draw_text(self.screen, sug, "sm", TXT_HI, s_r.x + 10, s_r.y + 4)
            else:
                if not tags: _draw_text(self.screen, self._TR("modal_add_tag"), "sm", TXT_DIM, text_x, tag_y)
                else:
                    curr_x = text_x
                    for t in tags:
                        tw, _ = _text_wh(t, "sm"); tr = pygame.Rect(curr_x, tag_y, tw+20, 24)
                        _rect(self.screen, (45, 50, 90), tr, radius=12)
                        _draw_text(self.screen, t, "sm", TXT_HI, tr.x+10, tr.y+3)
                        curr_x += tw + 30
                        if curr_x > list_x + 750: break

            sel_r = pygame.Rect(list_x + list_w - 130, ry + 50, 100, 40)
            _button(self.screen, sel_r, self._TR("modal_btn_select"), _in_rect((mx, my), sel_r))
            del_r = pygame.Rect(list_x + list_w - 180, ry+50, 40, 40); is_pending = (self._vid_delete_pending == name)
            _button(self.screen, del_r, "X" if not is_pending else "!", _in_rect((mx, my), del_r), danger=True)

        self.screen.set_clip(None)
        v_rows = list_h // row_h
        if len(self._vid_files) > v_rows:
            _scrollbar(self.screen, list_x + list_w - 12, list_y + 10, 4, list_h - 20, self._vid_scroll, len(self._vid_files), v_rows)
        _draw_text(self.screen, self._TR("modal_drag_drop"), "sm", (100, 100, 255), dx + dw - 280, dy + dh - 35)
        _draw_text(self.screen, self._TR("modal_tip_thumbnail"), "xs", (120, 125, 150), dx + 30, dy + dh - 35)

