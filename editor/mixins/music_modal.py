"""
editor/mixins/music_modal.py

MusicModalMixin — Dialogo selezione musica con gestione tag, rinomina inline,
anteprima audio avanzata e UX testo professionale.
"""

import logging
import pygame
import shutil
import threading
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

# Estensioni gestite dal modale musica
MUSIC_EXTENSIONS = (".mp3",)
# Nome del catalogo tag/durate persistente nella cartella music
MUSIC_CATALOG_FILENAME = "music_catalog.json"

class MusicModalMixin:
    """Modale avanzata per la gestione della musica con UX testo migliorata."""

    def _music_modal_open(self, context="scene"):
        self._music_modal = True
        self._music_row_cache = OrderedDict() # Cache superfici righe
        self._music_cache_max = 50            # Capacità massima cache righe
        self._music_modal_context = context
        self._music_files = []
        self._music_all_files = []
        self._music_scroll = 0.0      # Valore corrente (interpolato)
        self._music_scroll_target = 0.0 # Valore di destinazione
        self._music_scroll_vel = 0.0    # Velocità momentum
        self._music_is_dragging = False # Stato trascinamento
        self._music_drag_start_y = 0
        self._music_drag_offset = 0
        self._music_playing = None
        self._music_start_time = 0.0
        self._music_durations = getattr(self, "_music_durations", {})
        self._music_seeking = False
        
        # Overlay pre-rendering cache
        self._music_overlay_surf = getattr(self, "_music_overlay_surf", None)
        
        # Stato caricamento durate
        self._music_loading_durations = getattr(self, "_music_loading_durations", False)
        
        # UX Testo
        self._music_editing_name = None 
        self._music_name_buffer = ""
        self._music_editing_tags = None 
        self._music_tags_buffer = ""
        self._music_cursor = 0
        self._music_delete_pending = None
        
        # Ricerca e Suggerimenti
        self._music_search = ""
        self._music_search_active = False
        self._music_suggestions = []

        self._music_dir = self.base_path / "engine" / "assets" / "music"
        # Strato dati condiviso: scansione, tag, durate, rename, delete, import.
        if getattr(self, "_music_cat", None) is None:
            self._music_cat = AssetCatalog(self._music_dir, MUSIC_EXTENSIONS,
                                           MUSIC_CATALOG_FILENAME)
        self._music_cat.load()

        if self._music_dir.exists():
            self._music_all_files = self._music_cat.refresh()
            self._music_files = list(self._music_all_files)
            self._music_pre_cache_data()

            # Caricamento durate in background con protezione thread singolo
            if not self._music_loading_durations:
                # Sincronizza durate già presenti nel catalogo
                for name in self._music_all_files:
                    dur = self._music_cat.get_entry_value(name, "duration")
                    if dur is not None and name not in self._music_durations:
                        self._music_durations[name] = dur

                threading.Thread(target=self._music_load_durations_task, daemon=True).start()

        pygame.mixer.music.stop()

    def _music_modal_close(self):
        self._music_modal = False
        self._music_seeking = False
        self._music_editing_name = None
        self._music_editing_tags = None
        self._music_search_active = False
        pygame.mixer.music.stop()
        try: pygame.mixer.music.unload()
        except Exception: pass
        self._music_playing = None


    def _music_load_durations_task(self):
        self._music_loading_durations = True
        needs_save = False
        try:
            for name in self._music_all_files:
                # Se la modale viene chiusa, fermiamoci (opzionale)
                if not self._music_modal and not getattr(self, "_gs_edit_mode", None): break
                if name not in self._music_durations:
                    try:
                        # Caricamento temporaneo per estrarre la durata
                        s = pygame.mixer.Sound(str(self._music_dir / name))
                        dur = s.get_length()
                        self._music_durations[name] = dur
                        # Aggiorna catalogo per persistenza
                        self._music_cat.set_entry_value(name, "duration", dur)
                        needs_save = True
                        del s # Forza rilascio memoria
                    except Exception: self._music_durations[name] = 0.0
            if needs_save: self._music_cat.save()
        finally:
            self._music_loading_durations = False

    def _music_update_filter(self):
        self._music_files = self._music_cat.search(self._music_search)
        self._music_scroll = self._music_scroll_target = 0
        self._music_row_cache.clear()

    def _music_modal_key(self, ev):
        if not self._music_modal: return
        mods = pygame.key.get_mods()
        ctrl = bool(mods & pygame.KMOD_CTRL)
        
        if ev.key == pygame.K_ESCAPE:
            if self._music_editing_name or self._music_editing_tags:
                self._music_editing_name = self._music_editing_tags = None
            elif self._music_search_active:
                self._music_search_active = False
            else:
                self._music_modal_close()
            return

        active_field = None
        if self._music_editing_name: active_field = "name"
        elif self._music_editing_tags: active_field = "tags"
        elif self._music_search_active: active_field = "search"
        
        if not active_field: return

        if ctrl:
            if ev.key == pygame.K_a:
                buf = self._music_get_buf(active_field)
                self._music_cursor = len(buf); return
            if ev.key == pygame.K_c:
                buf = self._music_get_buf(active_field)
                self._set_clipboard(buf); return
            if ev.key == pygame.K_v:
                pst = self._get_clipboard()
                if pst: self._music_insert_text(active_field, pst); return

        if ev.key == pygame.K_RETURN:
            if active_field == "name": self._music_confirm_rename()
            elif active_field == "tags": self._music_confirm_tags()
            elif active_field == "search": self._music_search_active = False
        elif ev.key == pygame.K_BACKSPACE:
            self._music_delete_char(active_field)
        elif ev.key == pygame.K_LEFT:
            self._music_cursor = max(0, self._music_cursor - 1)
        elif ev.key == pygame.K_RIGHT:
            buf = self._music_get_buf(active_field)
            self._music_cursor = min(len(buf), self._music_cursor + 1)
        elif ev.unicode.isprintable():
            if active_field == "name" and ev.unicode in r'/\:*?"<>|': return
            self._music_insert_text(active_field, ev.unicode)

    def _music_get_buf(self, field):
        if field == "name": return self._music_name_buffer
        if field == "tags": return self._music_tags_buffer
        return self._music_search

    def _music_insert_text(self, field, text):
        if field == "name": self._music_name_buffer = self._music_name_buffer[:self._music_cursor] + text + self._music_name_buffer[self._music_cursor:]
        elif field == "tags":
            self._music_tags_buffer = self._music_tags_buffer[:self._music_cursor] + text + self._music_tags_buffer[self._music_cursor:]
            self._music_update_suggestions()
        else:
            self._music_search = self._music_search[:self._music_cursor] + text + self._music_search[self._music_cursor:]
            self._music_update_filter()
        self._music_cursor += len(text)

    def _music_delete_char(self, field):
        if self._music_cursor <= 0: return
        if field == "name": self._music_name_buffer = self._music_name_buffer[:self._music_cursor-1] + self._music_name_buffer[self._music_cursor:]
        elif field == "tags":
            self._music_tags_buffer = self._music_tags_buffer[:self._music_cursor-1] + self._music_tags_buffer[self._music_cursor:]
            self._music_update_suggestions()
        else:
            self._music_search = self._music_search[:self._music_cursor-1] + self._music_search[self._music_cursor:]
            self._music_update_filter()
        self._music_cursor -= 1

    def _music_update_suggestions(self):
        parts = [p.strip().lower() for p in self._music_tags_buffer.split(",")]
        curr = parts[-1] if parts else ""
        if not curr: self._music_suggestions = []; return
        self._music_suggestions = self._music_cat.suggest_tags(curr, exclude=parts)

    def _music_apply_suggestion(self, tag):
        parts = [p.strip() for p in self._music_tags_buffer.split(",")]
        if parts: parts[-1] = tag
        else: parts = [tag]
        self._music_tags_buffer = ", ".join(parts) + ", "
        self._music_cursor = len(self._music_tags_buffer)
        self._music_suggestions = []

    def _music_pre_cache_data(self):
        """Pre-calcola le stringhe visualizzate per evitare calcoli nel loop di rendering."""
        self._music_display_names = {}
        for name in self._music_all_files:
            stem = name.replace(".mp3", "")
            # Tronca se troppo lungo (approssimativo per velocità)
            if len(stem) > 35: stem = stem[:32] + "..."
            self._music_display_names[name] = stem
        
        self._music_display_tags = {}
        for name in self._music_all_files:
            tags = self._music_cat.get_tags(name)
            t_str = ", ".join(tags) if tags else self._TR("modal_no_tags")
            if len(t_str) > 60: t_str = t_str[:57] + "..."
            self._music_display_tags[name] = t_str

    def _music_modal_click(self, mx, my, w, h):
        if not getattr(self, "_music_modal", False): return
        dw, dh = 1100, 800
        dx, dy = (w - dw) // 2, (h - dh) // 2
        
        # Area lista
        list_x, list_y, list_w, list_h = dx + 25, dy + 130, dw - 50, dh - 240
        
        if not _in_rect((mx, my), (dx, dy, dw, dh)): self._music_modal_close(); return

        # Inizio trascinamento se clicchiamo nella lista
        if _in_rect((mx, my), (list_x, list_y, list_w, list_h)):
            self._music_is_dragging = True
            self._music_drag_start_y = my
            self._music_drag_offset = self._music_scroll_target
            # Non usciamo, potremmo voler cliccare un bottone

        if self._music_editing_tags and self._music_suggestions:
            for i, sug in enumerate(self._music_suggestions):
                s_r = pygame.Rect(self._last_t_x + i*130, self._last_t_y + 40, 120, 28)
                if _in_rect((mx, my), s_r): self._music_apply_suggestion(sug); return

        if _in_rect((mx, my), (dx + dw - 45, dy + 20, 30, 30)): self._music_modal_close(); return

        search_r = pygame.Rect(dx + 25, dy + 60, dw - 50, 36)
        if _in_rect((mx, my), search_r):
            self._music_confirm_rename(); self._music_confirm_tags()
            self._music_search_active = True; self._music_cursor = len(self._music_search)
            return

        list_x, list_y, list_w, list_h = dx + 25, dy + 130, dw - 50, dh - 240
        row_h = 125
        
        if _in_rect((mx, my), (list_x, list_y, list_w, list_h)):
            # Troviamo l'indice di partenza visibile
            start_idx = int(self._music_scroll // row_h)
            end_idx = start_idx + (list_h // row_h) + 2
            
            for i in range(start_idx, min(len(self._music_files), end_idx)):
                name = self._music_files[i]
                ry = list_y + i * row_h - int(self._music_scroll)
                
                # Check se la riga è effettivamente cliccabile (non fuori clipping)
                if ry + row_h < list_y or ry > list_y + list_h: continue

                # Hit Play/Pause (40x40, centrato verticalmente nel row)
                if _in_rect((mx, my), (list_x + 25, ry + 42, 40, 40)): 
                    self._music_preview(name); return
                
                # Hit SCEGLI / RIMUOVI
                if _in_rect((mx, my), (list_x + list_w - 130, ry + 42, 100, 40)): 
                    self._music_confirm_rename(); self._music_confirm_tags(); self._music_toggle(name); return

                # Hit ELIMINA (Cestino dalla libreria)
                if _in_rect((mx, my), (list_x + list_w - 180, ry + 42, 40, 40)):
                    if self._music_delete_pending == name: self._music_delete_file(name)
                    else: self._music_confirm_rename(); self._music_confirm_tags(); self._music_delete_pending = name
                    return
                
                # Hit EDIT NOME
                if _in_rect((mx, my), (list_x + 75, ry + 12, 400, 30)):
                    self._music_confirm_rename(); self._music_confirm_tags()
                    self._music_editing_name = name; self._music_name_buffer = Path(name).stem
                    self._music_cursor = len(self._music_name_buffer); return
                
                # Hit EDIT TAGS
                if _in_rect((mx, my), (list_x + 75, ry + 45, 500, 40)):
                    self._music_confirm_rename(); self._music_confirm_tags()
                    self._music_editing_tags = name
                    tags = self._music_cat.get_tags(name)
                    self._music_tags_buffer = ", ".join(tags) + (", " if tags else "")
                    self._music_cursor = len(self._music_tags_buffer); return
                
                # Seek Bar
                if self._music_playing == name:
                    if _in_rect((mx, my), (list_x + 75, ry + 90, 400, 20)):
                        self._music_seeking = True; self._music_modal_mmove(mx, my, w, h); return

        self._music_confirm_rename(); self._music_confirm_tags()
        self._music_search_active = False; self._music_delete_pending = None

    def _music_confirm_rename(self):
        if not self._music_editing_name: return
        old_name, buf = self._music_editing_name, self._music_name_buffer.strip()
        # Rename validata (file + catalogo) delegata al catalogo condiviso
        new_name = self._music_cat.rename(old_name, buf)
        if new_name:
            if old_name in self._music_durations:
                self._music_durations[new_name] = self._music_durations.pop(old_name)
            self._music_pre_cache_data()
            self._music_update_filter()
        self._music_editing_name = None

    def _music_confirm_tags(self):
        if not self._music_editing_tags: return
        name = self._music_editing_tags
        tags = [t.strip().lower() for t in self._music_tags_buffer.split(",") if t.strip()]
        self._music_cat.set_tags(name, tags)
        # Rigenera le stringhe pre-calcolate (i tag mostrati in riga)
        self._music_pre_cache_data()
        self._music_update_filter()
        self._music_editing_tags = None; self._music_suggestions = []

    def _music_preview(self, name):
        if self._music_playing == name:
            pygame.mixer.music.stop()
            self._music_playing = None
        else:
            try:
                p = self._music_dir / name
                pygame.mixer.music.load(str(p))
                pygame.mixer.music.play()
                self._music_playing = name
                self._music_start_time = 0.0
                logging.debug(f"Preview avviata: {name}")
            except Exception as e:
                logging.error(f"Errore preview musica {name}: {e}")
                self._status(self._TR("modal_error_audio").format(e), ERR_C, 3)

    def _music_toggle(self, name):
        ctx = getattr(self, "_music_modal_context", "scene")
        if ctx in ("game_edit", "game_new"):
            attr = "_gs_edit_music_paths" if getattr(self, "_gs_edit_mode", None) else "_gs_new_music_paths"
            if not hasattr(self, attr): setattr(self, attr, [])
            mlist = getattr(self, attr)
            
            abs_p = str(self._music_dir / name)
            found = -1
            for i, p in enumerate(mlist):
                # Match se è lo stesso file fisico o se ha lo stesso nome base (per quelli già in assets)
                if p == abs_p or Path(p).name == name:
                    found = i; break
            
            if found >= 0: mlist.pop(found)
            else: mlist.append(abs_p)
            return

        if not getattr(self, "game_path", None): return
        mlist = self.scene_data.setdefault("music", [])
        self._push_undo()
        if name in mlist: mlist.remove(name)
        else:
            mdir = self.game_path / "audio" / "music"; mdir.mkdir(parents=True, exist_ok=True)
            if not (mdir/name).exists():
                try: shutil.copy2(str(self._music_dir/name), str(mdir/name))
                except Exception: pass
            mlist.append(name)
        self.scene_dirty = True

    def _music_delete_file(self, name):
        # Soft-delete: sposta nel cestino. Recuperabile, audit log.
        if self._music_playing == name:
            pygame.mixer.music.stop()
            self._music_playing = None
        if not self._music_cat.delete(name, reason="user_delete_music"):
            logging.warning(f"[MUSIC] Delete fallita per '{name}'")
        self._music_durations.pop(name, None)
        self._music_update_filter()
        self._music_delete_pending = None

    def _music_handle_drop(self, path_str: str):
        if not self._music_modal: return
        t_name = self._music_cat.import_file(Path(path_str))
        if not t_name: return
        self._music_update_filter()
        try:
            s = pygame.mixer.Sound(str(self._music_dir / t_name))
            self._music_durations[t_name] = s.get_length()
        except Exception:
            self._music_durations[t_name] = 0.0
        # Rigenera i nomi/tag visualizzati, altrimenti la nuova traccia mostra valori grezzi.
        self._music_pre_cache_data()

        # Scorrimento automatico a fine lista
        v_rows = (800 - 160) // 125
        self._music_scroll = max(0, len(self._music_files) - v_rows)

    def _music_modal_mup(self):
        """Fine trascinamento o seek."""
        self._music_seeking = False
        self._music_is_dragging = False

    def _music_modal_mmove(self, mx, my, w, h):
        if not getattr(self, "_music_seeking", False) or not self._music_playing: return
        now = pygame.time.get_ticks()
        if now - getattr(self, "_last_seek_time", 0) < 100: return
        self._last_seek_time = now
        
        dx, dy = (w - 1100) // 2, (h - 800) // 2
        bar_x, bar_w = dx + 85, 400
        try:
            ratio = _clamp(mx - bar_x, 0, bar_w) / bar_w
            dur = self._music_durations.get(self._music_playing, 1.0)
            self._music_start_time = dur * ratio
            pygame.mixer.music.load(str(self._music_dir / self._music_playing))
            pygame.mixer.music.play(start=self._music_start_time)
        except Exception: self._music_seeking = False

    def _music_wheel(self, dy):
        if not getattr(self, "_music_modal", False): return
        # Incremento target con moltiplicatore per feeling naturale
        self._music_scroll_target -= dy * 120.0
        self._music_scroll_vel = 0 # Interrompi momentum se l'utente usa la rotella

    def _r_music_modal(self, w, h):
        if not getattr(self, "_music_modal", False): return
        
        # --- CACHING OVERLAY ---
        if not self._music_overlay_surf or self._music_overlay_surf.get_size() != (w, h):
            self._music_overlay_surf = pygame.Surface((w, h), pygame.SRCALPHA)
            self._music_overlay_surf.fill((0, 0, 0, 235))
        self.screen.blit(self._music_overlay_surf, (0, 0))

        dw, dh = 1100, 800
        dx, dy = (w - dw) // 2, (h - dh) // 2
        _rect(self.screen, (32, 28, 48), (dx, dy, dw, dh), radius=24)
        _rect(self.screen, ACCENT, (dx, dy, dw, dh), 2, radius=24)
        _draw_text(self.screen, self._TR("modal_music_title"), "lg", TXT_HI, dx + 30, dy + 25)
        
        mx, my = pygame.mouse.get_pos()
        xr = pygame.Rect(dx + dw - 45, dy + 20, 30, 30)
        _rect(self.screen, (200, 50, 50) if _in_rect((mx, my), xr) else (50, 55, 75), xr, radius=8)
        _draw_text(self.screen, "x", "md", TXT_HI, xr.x + 10, xr.y + 2)

        search_r = pygame.Rect(dx + 30, dy + 70, dw - 60, 38)
        s_bg = (20, 22, 32) if self._music_search_active else (25, 27, 38)
        _rect(self.screen, s_bg, search_r, radius=12)
        _rect(self.screen, ACCENT if self._music_search_active else BORDER, search_r, 1, radius=12)
        _draw_text(self.screen, self._music_search or self._TR("modal_search_placeholder"), "md", 
                  TXT_HI if self._music_search or self._music_search_active else TXT_DIM, search_r.x + 15, search_r.y + 8)
        
        if self._music_search_active and (pygame.time.get_ticks()//500)%2:
            tw, _ = _text_wh(self._music_search[:self._music_cursor], "md")
            pygame.draw.line(self.screen, ACCENT, (search_r.x + 15 + tw, search_r.y + 10), (search_r.x + 15 + tw, search_r.y + 28), 2)

        # LIST CONTAINER
        list_x, list_y, list_w, list_h = dx + 25, dy + 130, dw - 50, dh - 240
        _rect(self.screen, (15, 12, 26), (list_x, list_y, list_w, list_h), radius=16)
        _rect(self.screen, (40, 42, 65), (list_x, list_y, list_w, list_h), 1, radius=16) 
        
        # --- SISTEMA SCROLL FISICO (LERP + MOMENTUM) ---
        row_h = 125
        total_items = len(self._music_files)
        total_h = total_items * row_h
        max_scroll_px = max(0, total_h - list_h)

        if self._music_is_dragging:
            delta_y = self._music_drag_start_y - my
            self._music_scroll_target = _clamp(self._music_drag_offset + delta_y, 0, max_scroll_px)
            # Calcola velocità del trascinamento per momentum successivo
            self._music_scroll_vel = (self._music_scroll_target - self._music_scroll)
        else:
            # Attrito e Momentum
            self._music_scroll_target += self._music_scroll_vel
            self._music_scroll_vel *= 0.92
            if abs(self._music_scroll_vel) < 0.1: self._music_scroll_vel = 0.0
            # Clamp del target per evitare fuoriuscite
            self._music_scroll_target = _clamp(self._music_scroll_target, 0, max_scroll_px)

        # Interpolazione LERP per fluidità estrema
        self._music_scroll += (self._music_scroll_target - self._music_scroll) * 0.15
        if abs(self._music_scroll - self._music_scroll_target) < 0.5:
            self._music_scroll = self._music_scroll_target

        start_idx = max(0, int(self._music_scroll // row_h))
        end_idx = min(total_items, start_idx + (list_h // row_h) + 2)

        # Pre-calcolo stati outside loop
        ctx = getattr(self, "_music_modal_context", "scene")
        menu_names = set()
        if ctx in ("game_edit", "game_new"):
            attr = "_gs_edit_music_paths" if getattr(self, "_gs_edit_mode", None) else "_gs_new_music_paths"
            menu_names = {Path(p).name for p in getattr(self, attr, [])}
        else:
            menu_names = set(getattr(self, "scene_data", {}).get("music", []))

        self.screen.set_clip(pygame.Rect(list_x, list_y, list_w, list_h))

        # --- RENDERING OTTIMIZZATO CON CACHE (OrderedDict) ---
        for i in range(start_idx, end_idx):
            name = self._music_files[i]
            # --- SUB-PIXEL JITTERING PREVENTION ---
            ry = int(round(list_y + i * row_h - self._music_scroll))
            
            is_p = (self._music_playing == name)
            is_sel = (name in menu_names)
            is_del = (self._music_delete_pending == name)
            hov = _in_rect((mx, my), (list_x + 12, ry + 8, list_w - 24, row_h - 16))

            # Cache key basata sullo stato visuale della riga
            cache_key = (name, is_p, is_sel, is_del, hov, self._music_seeking if is_p else False)
            if is_p:
                # Se in playing, serve un refresh più frequente per la seek bar (ogni 500ms circa)
                cache_key = (cache_key, pygame.time.get_ticks() // 250)

            if cache_key in self._music_row_cache:
                row_surf = self._music_row_cache[cache_key]
                self._music_row_cache.move_to_end(cache_key)
            else:
                # Rendering della riga su superficie temporanea (Cache Miss)
                row_surf = pygame.Surface((list_w - 24, row_h - 16), pygame.SRCALPHA)
                bg_col = (55, 65, 100) if is_sel else ((35, 38, 55) if hov else (20, 22, 35))
                if is_p: bg_col = (70, 75, 120) if is_sel else (45, 48, 75)
                
                inner_r = (0, 0, list_w - 24, row_h - 16)
                _rect(row_surf, bg_col, inner_r, radius=12)
                if is_p: _rect(row_surf, ACCENT, inner_r, 1, radius=12)
                elif is_sel: _rect(row_surf, OK_C, inner_r, 2, radius=12)

                # Play Icon (coordinate relative alla superficie della riga)
                p_r = (16, 34, 40, 40)
                h_p = _in_rect((mx - list_x - 12, my - ry - 8), p_r)
                _rect(row_surf, BTN_AC if h_p else (ACCENT if is_p else (60, 65, 90)), p_r, radius=20)
                _draw_shape_icon(row_surf, (p_r[0]+12, p_r[1]+12, 16, 16), "play" if not is_p else "stop", (20,20,30) if h_p or is_p else TXT_HI)
                
                # Text Rendering con stringhe pre-calcolate
                tx = 73
                d_name = self._music_display_names.get(name, name)
                tw = _draw_text(row_surf, d_name, "md", TXT_HI if not (is_p or is_sel) else OK_C, tx, 17)
                _draw_shape_icon(row_surf, (tx + tw + 12, 20, 16, 16), "edit", (100, 110, 140))

                d_tags = self._music_display_tags.get(name, "")
                _draw_text(row_surf, d_tags, "sm", (110, 120, 150), tx, 54)
                
                dur = self._music_durations.get(name, 0.0)
                dur_s = f"{int(dur//60)}:{int(dur%60):02d}"
                _draw_text(row_surf, f"({dur_s})", "sm", (80, 90, 120), tx + tw + 45, 19)

                if is_p:
                    bar_x, bar_w, bar_y = tx, 400, 92
                    _rect(row_surf, (60, 65, 90), (bar_x, bar_y, bar_w, 4), radius=2)
                    pos = pygame.mixer.music.get_pos()
                    cur_s = self._music_start_time + (pos/1000.0) if pos>=0 else self._music_start_time
                    ratio = min(1.0, cur_s/dur) if dur > 0 else 0
                    _rect(row_surf, ACCENT, (bar_x, bar_y, int(bar_w*ratio), 4), radius=2)
                    pygame.draw.circle(row_surf, TXT_HI, (bar_x + int(bar_w*ratio), bar_y + 2), 6)

                # Buttons
                sel_r = (list_w - 24 - 118, 34, 100, 40)
                _button(row_surf, sel_r,
                        self._TR("modal_btn_remove") if is_sel
                        else self._TR("modal_btn_select"),
                        _in_rect((mx - list_x - 12, my - ry - 8), sel_r), danger=is_sel)
                
                del_r = (list_w - 24 - 168, 34, 40, 40)
                _button(row_surf, del_r, "X" if not is_del else "!", _in_rect((mx - list_x - 12, my - ry - 8), del_r), danger=True)
                if is_del: _draw_text(row_surf, self._TR("modal_confirm_delete"), "sm", ERR_C, del_r[0]-70, del_r[1]+10)

                # Eviction graduale LRU
                if len(self._music_row_cache) >= self._music_cache_max:
                    self._music_row_cache.popitem(last=False)
                self._music_row_cache[cache_key] = row_surf

            self.screen.blit(row_surf, (list_x + 12, ry + 8))

            # Overlay Inputs (fuori dalla cache perché sono interattivi puri)
            if self._music_editing_name == name:
                _rect(self.screen, (30,32,45), (list_x+85, ry+15, 450, 35), radius=8)
                _draw_text(self.screen, self._music_name_buffer, "md", OK_C, list_x+90, ry+22)
            if self._music_editing_tags == name:
                _rect(self.screen, (30,32,45), (list_x+85, ry+52, 550, 35), radius=8)
                _draw_text(self.screen, self._music_tags_buffer, "sm", ACCENT, list_x+90, ry+60)

        self.screen.set_clip(None)
        _scrollbar(self.screen, dx+dw-18, list_y + 10, 5, list_h - 20, self._music_scroll, total_h, list_h)
        _draw_text(self.screen, self._TR("modal_drag_drop"), "sm", (80, 90, 120), dx+dw-290, dy+dh-35)

    def _set_clipboard(self, text):
        from editor.ui.widgets import clipboard_set
        clipboard_set(text)

    def _get_clipboard(self):
        from editor.ui.widgets import clipboard_get
        return clipboard_get()
