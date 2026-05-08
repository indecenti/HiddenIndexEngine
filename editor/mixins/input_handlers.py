"""
editor/mixins/input_handlers.py

InputHandlersMixin — gestione eventi pygame: keyboard, mouse (down/up/move/wheel),
                     pan/zoom, drag, handle resize, click pannelli.
"""

import copy
import math
import pygame
import logging

from editor.constants import (
    TOP_BAR_H, STATUS_H,
    MODE_SELECT, MODE_CIRCLE, MODE_RECT, MODE_EFFECT_PLACE, MODE_SCATTER,
    STATE_GAME_SELECT, STATE_MAIN,
    TAB_TREE, TAB_CATALOG, TAB_EFFECTS, TAB_LAYERS, TAB_PROPS,
    ACCENT, OK_C, ERR_C, WARN_C, TXT, TXT_DIM, FX_C, ALWAYS_C,
)
from editor.core.io import _discover_games, _default_effect
from editor.ui.draw import _in_rect, _clamp


class InputHandlersMixin:
    """Gestione completa input: keyboard, mouse, scroll."""

    # ─────────────────────────────────────────────────────────────────────────
    # LOOP EVENTI
    # ─────────────────────────────────────────────────────────────────────────

    def _handle_events(self):
        for ev in pygame.event.get():
            if self._img_editor_active:
                self._img_editor_handle_event(ev); continue
            if ev.type == pygame.QUIT:
                self.running = False
            elif ev.type == pygame.KEYDOWN:
                self._on_key(ev)
            elif ev.type == pygame.MOUSEBUTTONDOWN:
                self._on_mdown(ev)
            elif ev.type == pygame.MOUSEBUTTONUP:
                self._on_mup(ev)
            elif ev.type == pygame.VIDEORESIZE:
                self.screen = pygame.display.set_mode(ev.size, pygame.RESIZABLE)
                self.screen_size = ev.size
                self._fit_canvas()
                self._status(f"Resized: {ev.w}x{ev.h}", TXT_DIM, 1)
            elif ev.type == pygame.MOUSEMOTION:
                self._on_mmove(ev)
            elif ev.type == pygame.MOUSEWHEEL:
                self._on_wheel(ev)
            elif ev.type == pygame.DROPFILE:
                if getattr(self, "_bg_modal", False):
                    self._bg_handle_drop(ev.file)
                elif getattr(self, "_vid_modal", False):
                    self._vid_handle_drop(ev.file)
                elif getattr(self, "_music_modal", False):
                    self._music_handle_drop(ev.file)

    # ─────────────────────────────────────────────────────────────────────────
    # KEYBOARD
    # ─────────────────────────────────────────────────────────────────────────

    def _on_key(self, ev):
        mods = pygame.key.get_mods()
        ctrl = bool(mods & pygame.KMOD_CTRL)

        if self._newobj_modal:
            self._newobj_key(ev); return
        if self._lang_modal:
            self._lang_key(ev); return
        if getattr(self, "_music_modal", False):
            self._music_modal_key(ev); return
        if getattr(self, "_bg_modal", False):
            self._bg_modal_key(ev); return
        if getattr(self, "_vid_modal", False):
            self._vid_modal_key(ev); return
        if getattr(self, "_editing_preset_name", False):
            self._preset_key(ev); return
        if self._editing_prop:
            self._prop_key(ev); return
        if self._img_editor_active:
            # L'evento è già gestito in _handle_events, ma per sicurezza:
            return
        if self.catalog_searching:
            if ev.key in (pygame.K_ESCAPE, pygame.K_RETURN):
                self.catalog_searching = False
            elif ev.key == pygame.K_BACKSPACE:
                self.catalog_search = self.catalog_search[:-1]
                self.catalog_scroll = 0
            elif ev.unicode and ev.unicode.isprintable():
                self.catalog_search += ev.unicode.lower()
                self.catalog_scroll = 0
            return
        if getattr(self, "catalog_tag_searching", False):
            if ev.key in (pygame.K_ESCAPE, pygame.K_RETURN):
                self.catalog_tag_searching = False
            elif ev.key == pygame.K_BACKSPACE:
                ts = getattr(self, "catalog_tag_search", "")
                self.catalog_tag_search = ts[:-1]
            elif ev.unicode and ev.unicode.isprintable():
                self.catalog_tag_search = getattr(self, "catalog_tag_search", "") + ev.unicode.lower()
                # Deseleziona tag attivo se non più visibile dopo filtro
                self.catalog_tag_filters = set()
            return

        if self.state == STATE_GAME_SELECT:
            self._gs_key(ev); return

        # Rilevamento Ctrl esteso per miglior compatibilità Windows/Linux/Mac
        ctrl = bool(mods & pygame.KMOD_CTRL) or bool(mods & pygame.KMOD_META)
        
        # Shortcut con CTRL
        if ctrl:
            # S = Salva
            if ev.key == pygame.K_s or ev.unicode.lower() == 's':
                self._save(); return
            # Z = Undo
            if ev.key == pygame.K_z or ev.unicode.lower() == 'z':
                self._undo(); return
            # Y = Redo
            if ev.key == pygame.K_y or ev.unicode.lower() == 'y':
                self._redo(); return
            # C = Copia
            if ev.key == pygame.K_c or ev.unicode.lower() == 'c':
                self._copy_sel(); return
            # X = Taglia
            if ev.key == pygame.K_x or ev.unicode.lower() == 'x':
                self._cut_sel(); return
            # V = Incolla
            if ev.key == pygame.K_v or ev.unicode.lower() == 'v':
                self._paste_sel(); return
            # D = Duplica
            if ev.key == pygame.K_d or ev.unicode.lower() == 'd':
                self._duplicate(); return
            # A = Seleziona Tutti
            if ev.key == pygame.K_a or ev.unicode.lower() == 'a':
                self._select_all(); return
            
            # Layer change (Ctrl+1, Ctrl+2...)
            if ev.key == pygame.K_1: self._set_layer("objects_low");  return
            if ev.key == pygame.K_2: self._set_layer("objects_mid");  return
            if ev.key == pygame.K_3: self._set_layer("objects_high"); return
            if ev.key == pygame.K_4: self._set_layer("overlay");      return

        if not ctrl:
            if ev.key == pygame.K_HOME:
                self.state    = STATE_GAME_SELECT
                self.gs_games = _discover_games(self.base_path)
                return
            if ev.key == pygame.K_s:
                self.mode = MODE_SELECT; self._cancel_rect()
                self.sel_effect_idx = None; return
            if ev.key == pygame.K_1:
                self.mode = MODE_CIRCLE; self._cancel_rect()
                self.selected_idx = None; self.selected_indices = []
                self.sel_effect_idx = None; return
            if ev.key == pygame.K_2:
                self.mode = MODE_RECT; self._cancel_rect()
                self.selected_idx = None; self.selected_indices = []
                self.sel_effect_idx = None; return
            if ev.key == pygame.K_4:
                self.mode = MODE_SCATTER; self._cancel_rect()
                self.selected_idx = None; self.selected_indices = []
                self.sel_effect_idx = None
                self._status("Piazza Cluster (4 oggetti random)", ACCENT, 2)
                return
            if ev.key == pygame.K_3:
                # Passa a piazzamento effetto solo se tab EFFETTI attivo e un effetto selezionato
                if self.effects_catalog_sel:
                    self.mode = MODE_EFFECT_PLACE; self._cancel_rect()
                    self.selected_idx = None; self.selected_indices = []
                    self.sel_effect_idx = None
                    self._status(f"Piazza effetto: {self.effects_catalog_sel}", FX_C, 2)
                return
            if ev.key == pygame.K_ESCAPE:  self._escape();                                return
            if ev.key in (pygame.K_DELETE, pygame.K_BACKSPACE):
                if getattr(self, "sel_effect_idx", None) is not None:
                    self._delete_effect_sel()
                else:
                    self._delete_sel()
                return
            if ev.key == pygame.K_TAB:     self._tab_cycle();                             return
            if ev.key == pygame.K_SLASH:   self._focus_catalog_search();                  return
            if ev.key == pygame.K_o:  self.show_overlay = not self.show_overlay; return
            if ev.key == pygame.K_g:  self.show_grid    = not self.show_grid;    return
            if ev.key == pygame.K_i:  self.show_icons   = not self.show_icons;   return
            if ev.key == pygame.K_f:  self._fit_canvas();                         return
            if ev.key == pygame.K_l:
                self.r_tab = TAB_LAYERS if self.r_tab != TAB_LAYERS else TAB_PROPS
                return
            if ev.key in (pygame.K_PLUS, pygame.K_EQUALS, pygame.K_KP_PLUS):
                self._zoom_by(1.2);  return
            if ev.key in (pygame.K_MINUS, pygame.K_KP_MINUS):
                self._zoom_by(1/1.2); return
            if ev.key == pygame.K_LEFT:  self._pan_by( self._pan_speed, 0); return
            if ev.key == pygame.K_RIGHT: self._pan_by(-self._pan_speed, 0); return
            if ev.key == pygame.K_UP:    self._pan_by( 0,  self._pan_speed); return
            if ev.key == pygame.K_DOWN:  self._pan_by( 0, -self._pan_speed); return
            if ev.key == pygame.K_a:     self._pan_by( self._pan_speed, 0); return
            if ev.key == pygame.K_d:     self._pan_by(-self._pan_speed, 0); return
            if ev.key == pygame.K_w:     self._pan_by( 0,  self._pan_speed); return

            if self.selected_idx is not None:
                obj = self.scene_data["objects"][self.selected_idx]
                if ev.key == pygame.K_r:
                    self._push_undo()
                    # Rotazione incrementale con granularità variabile:
                    # R: +1 grado (normale)
                    # R+Shift: +15 gradi (veloce)
                    # R+Ctrl: +0.1 gradi (super preciso)
                    if mods & pygame.KMOD_CTRL:
                        step = 0.1  # Super preciso
                    elif mods & pygame.KMOD_SHIFT:
                        step = 15   # Veloce
                    else:
                        step = 1    # Normale
                    obj["rotation"] = round((obj.get("rotation", 0) + step) % 360, 1)
                    self._status(f"Rotazione: {obj['rotation']}°", ACCENT, 1)
                    self.scene_dirty = True
                    return
                if ev.key == pygame.K_q:  # Rotazione inversa
                    self._push_undo()
                    # Q: -1 grado (normale)
                    # Q+Shift: -15 gradi (veloce)
                    # Q+Ctrl: -0.1 gradi (super preciso)
                    if mods & pygame.KMOD_CTRL:
                        step = -0.1
                    elif mods & pygame.KMOD_SHIFT:
                        step = -15
                    else:
                        step = -1
                    obj["rotation"] = round((obj.get("rotation", 0) + step) % 360, 1)
                    self._status(f"Rotazione: {obj['rotation']}°", ACCENT, 1)
                    self.scene_dirty = True
                    return
                if ev.key == pygame.K_h:
                    self._push_undo()
                    obj["flip_x"] = not obj.get("flip_x", False)
                    return
                if ev.key == pygame.K_v:
                    self._push_undo()
                    obj["flip_y"] = not obj.get("flip_y", False)
                    return

            if ev.key == pygame.K_h:
                self.panels_visible = not self.panels_visible
                self._update_layout()
                return

            if ev.key == pygame.K_F11:
                self.fullscreen = not self.fullscreen
                if self.fullscreen:
                    self.screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN | pygame.RESIZABLE)
                else:
                    self.screen = pygame.display.set_mode((1280, 720), pygame.RESIZABLE)
                self.screen_size = self.screen.get_size()
                self._update_layout()
                self._status(f"Fullscreen: {'ON' if self.fullscreen else 'OFF'}", ACCENT, 2)
                return

    # ─────────────────────────────────────────────────────────────────────────
    # SHORTCUT HELPERS
    # ─────────────────────────────────────────────────────────────────────────

    def _select_next_all(self):
        """Ctrl+A — cicla la selezione su tutti gli oggetti della scena."""
        objs = self.scene_data.get("objects", [])
        if not objs:
            self._status("Nessun oggetto in scena", WARN_C, 2)
            return
        if self.selected_idx is None:
            self.selected_idx = 0
        else:
            self.selected_idx = (self.selected_idx + 1) % len(objs)
        name = objs[self.selected_idx].get("catalog_id", "?")
        self._status(
            f"[{self.selected_idx + 1}/{len(objs)}]  {name}", ACCENT, 2
        )

    def _focus_catalog_search(self):
        """/ — porta il focus sulla barra di ricerca del catalogo."""
        if not self.scene_path:
            return
        self.l_tab             = TAB_CATALOG
        self.catalog_searching = True
        self.catalog_search    = ""
        self.catalog_scroll    = 0
        self.panels_visible    = True
        self._status("Cerca nel catalogo…", TXT_DIM, 0)


    def _preset_key(self, ev):
        if ev.key == pygame.K_RETURN:
            self._preset_commit()
        elif ev.key == pygame.K_ESCAPE:
            self._editing_preset_name = False
        elif ev.key == pygame.K_BACKSPACE:
            self._preset_name_buf = self._preset_name_buf[:-1]
        elif ev.unicode.isprintable():
            self._preset_name_buf += ev.unicode

    def _preset_commit(self):
        name = self._preset_name_buf.strip()
        if name and getattr(self, "sel_effect_idx", None) is not None:
            fx = self.scene_data["effects"][self.sel_effect_idx]
            preset_data = {}
            for k in ["width", "height", "alpha", "color", "font_size", "font_color"]:
                if k in fx: preset_data[k] = fx[k]
            self.bubble_presets[name] = preset_data
            self._save_bubble_presets()
            self._preset_selected = name
            self._status(f"Preset salvato: {name}", OK_C, 2)
        self._editing_preset_name = False

    def _prop_key(self, ev):
        if ev.key == pygame.K_RETURN:
            self._prop_commit()
        elif ev.key == pygame.K_ESCAPE:
            self._editing_prop = None
            self._prop_buf = ""
        elif ev.key == pygame.K_BACKSPACE:
            self._prop_buf = self._prop_buf[:-1]
        elif ev.unicode and (ev.unicode.isdigit() or ev.unicode in ('.', ',')):
            char = ev.unicode.replace(',', '.')
            if char == '.' and '.' in self._prop_buf: return
            self._prop_buf += char

    def _prop_commit(self):
        if not self._editing_prop or not self._prop_buf: 
            self._editing_prop = None; return
        owner, idx, key = self._editing_prop
        try:
            val = float(self._prop_buf) if ('.' in self._prop_buf) else int(self._prop_buf)
            self._push_undo()
            if owner == 'effect':
                self.scene_data["effects"][idx][key] = val
            elif owner == 'object':
                if key == 'grayscale_factor':
                    # Converte da scala 0-100 (utente) a 0.0-1.0 (engine)
                    val = _clamp(float(val) / 100.0, 0.0, 1.0)
                self.scene_data["objects"][idx][key] = val
            self.scene_dirty = True
            self._status(f"Impostato {key}: {val}", OK_C, 1)

        except ValueError:
            self._status("Errore: inserire un numero", ERR_C, 2)
        self._editing_prop = None
        self._prop_buf = ""

    def _escape(self):
        if self.mode == MODE_EFFECT_PLACE:
            self.mode = MODE_SELECT
            self.sel_effect_idx = None
        elif self._rect_placing:
            self._cancel_rect()
        elif getattr(self, "sel_effect_idx", None) is not None:
            self.sel_effect_idx = None
        elif self.selected_idx is not None:
            self.selected_idx = None

    def _cancel_rect(self):
        self._rect_placing   = False
        self._rect_ref_start = (0.0, 0.0)
        self._rect_ref_cur   = (0.0, 0.0)
        self._circle_placing = False

    # ─────────────────────────────────────────────────────────────────────────
    # MOUSE DOWN
    # ─────────────────────────────────────────────────────────────────────────

    def _on_mdown(self, ev):
        self._play_click()
        mx, my_raw = ev.pos
        btn = ev.button
        w, h = self.screen.get_size()

        # 1. STATUS BAR (In fondo, ma sopra tutto tranne tooltip)
        status_btn_r = (10, h - STATUS_H, 150, STATUS_H)
        if btn == 1 and _in_rect((mx, my_raw), status_btn_r):
            self.state    = STATE_GAME_SELECT
            self.gs_games = _discover_games(self.base_path)
            return

        if hasattr(self, "scene_path") and self.scene_path:
            save_btn_r = (170, h - STATUS_H, 120, STATUS_H)
            if btn == 1 and _in_rect((mx, my_raw), save_btn_r):
                self._save(); return

        # 2. CONTEXT MENU & MODALS (Massima priorità al centro/area di lavoro)
        if btn == 1:
            # IL CONTEXT MENU è disegnato sopra i modali, quindi controlliamo prima lui
            if self._ctx_menu:
                items = self._get_ctx_items()
                m_w, m_h, mx_m, my_m = self._get_ctx_menu_info(items)
                menu_rect = pygame.Rect(mx_m, my_m, m_w, m_h)
                
                if _in_rect((mx, my_raw), menu_rect):
                    keep_open = self._ctx_menu_click(mx, my_raw)
                    if not keep_open:
                        self._ctx_menu = None
                    return # Intercettato dal menu contestuale
                else:
                    # Click fuori: chiudi e lascia passare (pass-through)
                    self._ctx_menu = None

            if self._newobj_modal:
                self._newobj_click(mx, my_raw, w, h); return
            if self._lang_modal:
                self._lang_click(mx, my_raw, w, h); return
            if getattr(self, "_music_modal", False):
                self._music_modal_click(mx, my_raw, w, h); return
            if getattr(self, "_bg_modal", False):
                self._bg_modal_click(mx, my_raw, w, h); return
            if getattr(self, "_vid_modal", False):
                self._vid_modal_click(mx, my_raw, w, h); return
            if getattr(self, "_minigame_modal", False):
                self._minigame_click(mx, my_raw); return
            if self._img_editor_active:
                return 

        # 3. TOP BAR MENUS
        if my_raw < TOP_BAR_H:
            self._menu_click(mx, my_raw)
            return

        # Se clicchiamo fuori da un menu a tendina Top Bar aperto, lo chiudiamo
        if self._active_menu:
            root_r = self._menu_bounds.get(self._active_menu)
            if root_r:
                from editor.constants import MENU_W
                items = self._get_menu_items(self._active_menu)
                drop_r = pygame.Rect(root_r.x, TOP_BAR_H, MENU_W, len(items) * 26)
                if not _in_rect((mx, my_raw), drop_r):
                    self._active_menu = None
                else:
                    self._menu_click(mx, my_raw)
                    return

        # 4. SIDEBAR RESIZING (Edge Detection)
        EDGE = 10
        if btn == 1 and self.panels_visible:
            if abs(mx - self.panel_l_w) <= EDGE:
                self._resizing_l = True; return
            if abs(mx - (w - self.panel_r_w)) <= EDGE:
                self._resizing_r = True; return

        # 5. DASHBOARD (STATE_GAME_SELECT)
        if self.state == STATE_GAME_SELECT:
            self._gs_click(mx, my_raw); return

        # 6. NUMERIC PROP EDITING COMMIT
        if self._editing_prop and btn == 1:
            self._prop_commit()

        # 7. SIDEBAR CONTENT
        if self.panels_visible and mx < self.panel_l_w:
            if btn == 1: self._left_click(mx, my_raw)
            return

        if self.panels_visible and mx > w - self.panel_r_w:
            if btn == 1: self._right_click(mx - (w - self.panel_r_w), my_raw)
            elif btn == 3: self._pan_moved = False
            return

        # 8. CANVAS CONTENT
        cr = self._canvas_rect()
        if _in_rect((mx, my_raw), cr):
            if btn == 1:
                if self._toolbar_click(mx, my_raw):
                    return
                self._canvas_ldown(mx, my_raw)
            elif btn in (2, 3):
                self._start_pan(mx, my_raw)
                self._pan_moved = False


    def _on_mup(self, ev):
        if getattr(self, "_resizing_l", False) or getattr(self, "_resizing_r", False):
            self._resizing_l = False
            self._resizing_r = False
            pygame.mouse.set_cursor(pygame.SYSTEM_CURSOR_ARROW)
            return
            
        mx, my_raw = ev.pos
        w, h = self.screen.get_size()
        btn = ev.button
        self._dragging_slider = None # Reset dragging slider
        self._dragging_catalog_scroll = False
        self._dragging_ctx_slider = None # Reset dragging context menu slider
        if getattr(self, "_music_modal", False):
            self._music_modal_mup()
        if btn in (2, 3):
            self._panning = False
            if btn == 3 and not self._pan_moved:
                # Controlla se siamo sui pannelli
                if self.panels_visible:
                    if mx < self.panel_l_w:
                        self._left_panel_ctx_open(mx, my_raw)
                        return
                    if mx > w - self.panel_r_w:
                        # Eventuale menu contestuale pannello destro (non richiesto ora)
                        pass
                self._ctx_open(mx, my_raw)
        if btn == 1:
            if getattr(self, "_dragging_effect_idx", None) is not None:
                self._drag_active = False
                self._dragging_effect_idx = None
            self._canvas_lup(mx, my_raw)

    def _on_mmove(self, ev):
        mx, my_raw = ev.pos
        w, h = self.screen.get_size()

        if getattr(self, "_music_modal", False):
            self._music_modal_mmove(mx, my_raw, w, h); return
        
        # --- LOGICA RESIZE INTERATTIVO ---
        from editor.constants import PANEL_MIN_W, PANEL_MAX_W
        if getattr(self, "_resizing_l", False):
            self.panel_l_w = _clamp(mx, PANEL_MIN_W, PANEL_MAX_W)
            return
        if getattr(self, "_resizing_r", False):
            self.panel_r_w = _clamp(w - mx, PANEL_MIN_W, PANEL_MAX_W)
            return

        # Feedback cursore sui bordi
        EDGE = 10
        near_l = abs(mx - self.panel_l_w) <= EDGE and self.panels_visible
        near_r = abs(mx - (w - self.panel_r_w)) <= EDGE and self.panels_visible
        if near_l or near_r:
            pygame.mouse.set_cursor(pygame.SYSTEM_CURSOR_SIZEWE)
        else:
            pygame.mouse.set_cursor(pygame.SYSTEM_CURSOR_ARROW)

        if self._panning:
            dx = mx     - self._pan_start_mx
            dy = my_raw - self._pan_start_my
            if abs(dx) > 3 or abs(dy) > 3:
                self._pan_moved = True
            self.origin_x = self._pan_start_ox + dx
            self.origin_y = self._pan_start_oy + dy
            return
        if self._drag_active and self.selected_idx is not None:
            self._do_drag(mx, my_raw)
        if self._drag_active and getattr(self, "_dragging_effect_idx", None) is not None:
            self._do_drag_effect(mx, my_raw)
            self.scene_dirty = True
        if self._handle_id:
            self._do_handle(mx, my_raw)
        
        if getattr(self, "_dragging_slider", None):
            self._do_drag_slider(mx, my_raw)

        if getattr(self, "_dragging_ctx_slider", None):
            self._do_drag_ctx_slider(mx, my_raw)
            
        if getattr(self, "_dragging_catalog_scroll", False):
            si = getattr(self, "_catalog_scroll_info", None)
            if si and si.get("max_scroll", 0) > 0:
                ratio = _clamp((my_raw - si["y_start"]) / si["bar_h"], 0, 1)
                self.catalog_scroll = ratio * si["max_scroll"]
            return
        
        # Box Selection Drag
        if self._sel_box_active:
            self._sel_box_cur = self._s2r(mx, my_raw)
            return

        if self._rect_placing and self.mode == MODE_RECT:
            self._rect_ref_cur = self._s2r(mx, my_raw)
        if self._circle_placing and self.mode == MODE_CIRCLE:
            rx, ry = self._s2r(mx, my_raw)
            cx, cy = self._circle_ref_center
            self._circle_ref_radius = math.hypot(rx - cx, ry - cy)

    def _on_wheel(self, ev):
        mx, my_raw = pygame.mouse.get_pos()
        w, h = self.screen.get_size()
        mods = pygame.key.get_mods()

        if self._lang_modal:
            max_scroll = max(0, len(self._lang_keys) - 8)
            self._lang_scroll = _clamp(self._lang_scroll - ev.y, 0, max_scroll)
            return

        if getattr(self, "_music_modal", False):
            self._music_wheel(ev.y)
            return

        if getattr(self, "_bg_modal", False):
            self._bg_modal_wheel(ev.y)
            return
        if getattr(self, "_vid_modal", False):
            self._vid_modal_wheel(ev.y)
            return

        if getattr(self, "_minigame_modal", False):
            self._minigame_wheel(ev.y)
            return

        if self.state == STATE_GAME_SELECT:
            self._gs_wheel(ev); return

        cr = self._canvas_rect()

        if self.panels_visible:
            if mx < self.panel_l_w:
                if self.l_tab == TAB_CATALOG:
                    tsi = getattr(self, "_tag_scroll_info", None)
                    if tsi and _in_rect((mx, my_raw), tsi["rect"]):
                        self.catalog_tags_scroll = _clamp(
                            self.catalog_tags_scroll - ev.y, 0, tsi["max"])
                        return
                    
                    si = getattr(self, "_catalog_scroll_info", None)
                    if si:
                        self.catalog_scroll = _clamp(
                            self.catalog_scroll - ev.y, 0, si["max_scroll"])
                elif self.l_tab == TAB_EFFECTS:
                    # Ricalcolo dinamico max_scroll per effetti (item_h=64)
                    list_y_start = 58
                    add_btn_h = 32
                    available_h = self.screen_size[1] - STATUS_H - list_y_start - add_btn_h
                    visible_items = available_h // (64 + 2)
                    max_scr = max(0, len(getattr(self, "effects_catalog", [])) - visible_items)
                    self.effects_catalog_scroll = _clamp(
                        self.effects_catalog_scroll - ev.y, 0, max_scr)
                else:
                    self.tree_scroll = _clamp(self.tree_scroll - ev.y, 0, 100)
                return
            
            if mx > w - self.panel_r_w:
                # Scroll pannello proprietà (in pixel)
                self.prop_scroll = max(0, self.prop_scroll - ev.y * 30)
                return

        if not _in_rect((mx, my_raw), cr):
            return

        if self.selected_idx is not None and self.mode == MODE_SELECT:
            obj = self.scene_data["objects"][self.selected_idx]
            if obj.get("detection_type") == "circle" and (mods & pygame.KMOD_ALT):
                delta = 5 if (mods & pygame.KMOD_SHIFT) else 1
                delta *= (1 if ev.y > 0 else -1)
                self._push_undo()
                obj["radius"] = max(5, obj.get("radius", 30) + delta)
                return

        if mods & pygame.KMOD_CTRL:
            factor = 1.15 if ev.y > 0 else (1/1.15)
            self._zoom_toward(mx, my_raw, factor)
        elif mods & pygame.KMOD_SHIFT:
            self.origin_x += ev.y * 80
        else:
            self.origin_y += ev.y * 80

    # ─────────────────────────────────────────────────────────────────────────
    # PAN / ZOOM
    # ─────────────────────────────────────────────────────────────────────────

    def _start_pan(self, mx, my):
        self._panning      = True
        self._pan_start_mx = mx
        self._pan_start_my = my
        self._pan_start_ox = self.origin_x
        self._pan_start_oy = self.origin_y

    # ─────────────────────────────────────────────────────────────────────────
    # CANVAS MOUSE
    # ─────────────────────────────────────────────────────────────────────────

    def _canvas_ldown(self, mx, my_raw):
        keys = pygame.key.get_pressed()
        if keys[pygame.K_SPACE]:
            self._start_pan(mx, my_raw); return

        if self.mode == MODE_EFFECT_PLACE:
            self._place_effect(mx, my_raw)
            return

        if self.mode == MODE_SCATTER:
            self._scatter_click(mx, my_raw)
            return

        if self.mode == MODE_SELECT:
            # 0. Handle Effetti (Priorità massima se un effetto è selezionato)
            sel_fx_idx = getattr(self, "sel_effect_idx", None)
            if sel_fx_idx is not None:
                fx = self.scene_data["effects"][sel_fx_idx]
                from editor.constants import HANDLE_R
                for hid, hx, hy in self._fx_handles(fx):
                    if math.hypot(mx - hx, my_raw - hy) <= HANDLE_R + 3:
                        self._push_undo()
                        if hid == "move":
                            self._dragging_effect_idx = sel_fx_idx
                            self._drag_active = True
                            self._drag_start_mx = mx
                            self._drag_start_my = my_raw
                            self._drag_start_x = fx["x"]
                            self._drag_start_y = fx["y"]
                        elif hid == "radius":
                            self._dragging_slider = ('effect', sel_fx_idx, 'radius', 5, 800, hx, 100)
                        else:
                            self._handle_id = f"fx_{hid}"
                            self._handle_snap = copy.copy(fx)
                            self._drag_start_mx = mx
                            self._drag_start_my = my_raw
                        return

            # 1. Selezione Effetti
            if self._try_select_effect(mx, my_raw):
                self.selected_idx = None
                self.selected_indices = []
                return
            self._sel_down(mx, my_raw)
        elif self.mode == MODE_CIRCLE:
            if not self._circle_placing:
                rx, ry = self._s2r(mx, my_raw)
                self._circle_placing    = True
                self._circle_ref_center = (self._snap(rx), self._snap(ry))
                self._circle_ref_radius = 5.0
        elif self.mode == MODE_RECT:
            if not self._rect_placing:
                rx, ry = self._s2r(mx, my_raw)
                self._rect_placing   = True
                self._rect_ref_start = (self._snap(rx), self._snap(ry))
                self._rect_ref_cur   = (self._snap(rx), self._snap(ry))

    def _canvas_lup(self, mx, my_raw):
        if self._panning:
            self._panning = False; return
        if self._drag_active:
            self._drag_active = False
            self._dragging_effect_idx = None
            return
        if self._handle_id:
            self._handle_id   = None
            self._handle_snap = None; return
        if self._circle_placing and self.mode == MODE_CIRCLE:
            self._confirm_circle(mx, my_raw)
        if self._sel_box_active:
            self._do_box_selection()
            self._sel_box_active = False
        if self._rect_placing and self.mode == MODE_RECT:
            self._confirm_rect(mx, my_raw)

    def _sel_down(self, mx, my_raw):
        mods = pygame.key.get_mods()
        if self.selected_idx is not None:
            obj = self.scene_data["objects"][self.selected_idx]
            hid = self._hit_handle(obj, (mx, my_raw))
            if hid:
                if hid == "move":
                    self._push_undo()
                    self._drag_active   = True
                    self.r_tab = TAB_PROPS  # Torna alle proprietà se eravamo in layer
                    self._drag_start_mx = mx
                    self._drag_start_my = my_raw
                    # Sincronizza il drag di gruppo (risolve il bug del vecchio oggetto che resta agganciato)
                    self._drag_group_starts = {}
                    for idx in self.selected_indices:
                        o = self.scene_data["objects"][idx]
                        self._drag_group_starts[idx] = (o["x"], o["y"])
                else:
                    self._push_undo()
                    self._handle_id   = hid
                    self._handle_snap = copy.copy(obj)
                    self._drag_start_mx = mx
                    self._drag_start_my = my_raw
                return

        rx, ry = self._s2r(mx, my_raw)
        hits = self._objs_at(rx, ry)

        if hits:
            idx = hits[0]
            self.selected_idx    = idx
            obj = self.scene_data["objects"][idx]
            
            # Sincronizza layer attivo in base all'oggetto colpito
            self.active_layer = obj.get("layer", "objects_mid")
            self.r_tab = TAB_PROPS # Passaggio automatico al pannello proprietà
            self.sel_effect_idx = None # Reset selezione effetti quando clicchi un PNG
            
            # Se premiamo Shift, aggiungiamo alla selezione esistente
            if mods & pygame.KMOD_SHIFT:
                if idx not in self.selected_indices:
                    self.selected_indices.append(idx)
            else:
                self.selected_indices = [idx]
                
            self._tab_cycle_hits = hits
            self._tab_cycle_pos  = 0
            self._push_undo()
            
            # Prepariamo il drag di gruppo
            self._drag_active   = True
            self._drag_start_mx = mx
            self._drag_start_my = my_raw
            self._drag_group_starts = {}
            for idx in self.selected_indices:
                o = self.scene_data["objects"][idx]
                self._drag_group_starts[idx] = (o["x"], o["y"])
        else:
            # Inizio Box Selection
            self._sel_box_active = True
            self._sel_box_start  = self._s2r(mx, my_raw)
            self._sel_box_cur    = self._s2r(mx, my_raw)
            if not (mods & pygame.KMOD_SHIFT):
                self.selected_idx    = None
                self.selected_indices = []
            self._tab_cycle_hits = []

    def _tab_cycle(self):
        if len(self._tab_cycle_hits) < 2:
            return
        self._tab_cycle_pos = (self._tab_cycle_pos + 1) % len(self._tab_cycle_hits)
        self.selected_idx   = self._tab_cycle_hits[self._tab_cycle_pos]
        self.r_tab = TAB_PROPS


    # ─────────────────────────────────────────────────────────────────────────
    # DRAG / HANDLE
    # ─────────────────────────────────────────────────────────────────────────

    def _do_drag(self, mx, my):
        dx  = (mx - self._drag_start_mx) / self.zoom
        dy  = (my - self._drag_start_my) / self.zoom
        
        for idx, (base_x, base_y) in self._drag_group_starts.items():
            obj = self.scene_data["objects"][idx]
            obj["x"] = self._snap(base_x + dx)
            obj["y"] = self._snap(base_y + dy)
        self.scene_dirty = True

    def _do_handle(self, mx, my):
        h = self._handle_id
        
        # --- GESTIONE HANDLE EFFETTI ( Bubble Tips ) ---
        if h.startswith("fx_"):
            fx_idx = getattr(self, "sel_effect_idx", None)
            if fx_idx is None: return
            fx = self.scene_data["effects"][fx_idx]
            hid = h[3:] # rimuove 'fx_'
            orig = self._handle_snap
            ox, oy = orig["x"], orig["y"]
            ow, oh = orig.get("width", 300), orig.get("height", 180)
            
            rx, ry = self._s2r(mx, my)
            res_w, res_h = ow, oh
            
            # Calcolo basato su simmetria rispetto all'ancora (x, y)
            # in modo che l'ancora resti FISSA.
            if   "n" in hid: res_h = (oy - ry) - 35
            elif "s" in hid:
                # 's' handle è sul bordo inferiore del corpo.
                # In realtà 's' handle in object_ops è cx, by+h.
                # Per ora lo manteniamo fisso per evitare che copra l'ancora
                res_h = 30 

            if   "w" in hid: res_w = (ox - rx) * 2
            elif "e" in hid: res_w = (rx - ox) * 2

            # Se è un lato verticale/orizzontale puro, usiamo il mouse direttamente
            if hid == "n": res_h = (oy - ry) - 35
            if hid == "s": pass # Non ha molto senso far crescere il fumetto verso il basso coprendo l'ancora
            
            # Applichiamo i limiti e lo snap
            fx["width"]  = max(40, self._snap(res_w))
            fx["height"] = max(30, self._snap(res_h))
            # x ed y NON vengono modificati: l'ancora è sovrana.
            self.scene_dirty = True
            return

        if self.selected_idx is None: return
        obj  = self.scene_data["objects"][self.selected_idx]
        orig = self._handle_snap
        dt   = obj.get("detection_type", "circle")
        rx, ry = self._s2r(mx, my)
        rot = obj.get("rotation", 0)
        
        # Modifiers
        mods  = pygame.key.get_mods()
        ctrl  = bool(mods & pygame.KMOD_CTRL)
        shift = bool(mods & pygame.KMOD_SHIFT)

        # ── Setup Bounding Box Virtuale ──────────────────
        if dt == "circle":
            ow = orig.get("width", orig.get("radius", 30)*2)
            oh = orig.get("height", orig.get("radius", 30)*2)
            ox, oy = orig["x"] - ow/2, orig["y"] - oh/2
        else:
            ox, oy = orig["x"], orig["y"]
            ow, oh = orig.get("width", 60), orig.get("height", 60)
        
        cx, cy = ox + ow/2, oy + oh/2
        lrx, lry = self._rotate_pt(rx, ry, cx, cy, -rot)
        ratio = ow / oh if oh != 0 else 1.0

        if h == "rot":
            dy2, dx2 = ry - cy, rx - cx
            angle = -(math.degrees(math.atan2(dy2, dx2)) + 90)
            # Rotazione precisa al decimo di grado (0.1°)
            obj["rotation"] = round(angle, 1) % 360
            self.scene_dirty = True
            return

        # ── WARP PROSPETTICO ─────────────────────
        if h in ("nw", "ne", "se", "sw"):
            if "corners" not in obj: obj["corners"] = [[0,0], [0,0], [0,0], [0,0]]
            c_idx = {"nw": 0, "ne": 1, "se": 2, "sw": 3}[h]
            std_x = (ox if "w" in h else ox+ow)
            std_y = (oy if "n" in h else oy+oh)
            dx_warp = lrx - std_x
            dy_warp = lry - std_y
            obj["corners"][c_idx] = [int(dx_warp), int(dy_warp)]
            self.scene_dirty = True
            return

        # ── Logica Resize Progressiva ────────────────────
        res_w, res_h = ow, oh
        res_x, res_y = ox, oy

        if shift:
            ratio = self._get_asset_ratio(obj.get("catalog_id", ""))
            if h in ("nw", "w", "sw"):
                res_w = ox + ow - lrx
                res_x = ox + ow - res_w
                res_h = res_w / ratio
                if "n" in h: res_y = oy + oh - res_h
            elif h in ("ne", "e", "se"):
                res_w = lrx - ox
                res_h = res_w / ratio
                if "n" in h: res_y = oy + oh - res_h
            elif h == "s":
                res_h = lry - oy
                res_w = res_h * ratio
            elif h == "n":
                res_h = oy + oh - lry
                res_y = oy + oh - res_h
                res_w = res_h * ratio
        else:
            if h in ("nw", "n", "ne"): res_y = lry; res_h = oy + oh - lry
            elif h in ("sw", "s", "se"): res_h = lry - oy
            if h in ("nw", "w", "sw"): res_x = lrx; res_w = ox + ow - lrx
            elif h in ("ne", "e", "se"): res_w = lrx - ox
        
        # Limita dimensioni massime ragionevoli (evita artefatti da over-scaling)
        # Max 4000px per dimensione è un buon limite per evitare memory leak
        MAX_DIM = 4000
        clamped_w = min(MAX_DIM, self._snap(res_w))
        clamped_h = min(MAX_DIM, self._snap(res_h))

        # Avvisa se l'utente ha tirato troppo
        if res_w != clamped_w or res_h != clamped_h:
            self._status(
                f"⚠️ Dimensione max raggiunta ({MAX_DIM}px) - evita artefatti",
                WARN_C, 2
            )

        res_w = max(10, clamped_w)
        res_h = max(10, clamped_h)
        res_x = self._snap(res_x)
        res_y = self._snap(res_y)

        if dt == "circle":
            obj["x"] = res_x + res_w/2
            obj["y"] = res_y + res_h/2
            obj["width"]  = res_w
            obj["height"] = res_h
            obj["radius"] = (res_w + res_h) / 4
        else:
            obj["x"], obj["y"] = res_x, res_y
            obj["width"], obj["height"] = res_w, res_h
        
        self.scene_dirty = True

    # ─────────────────────────────────────────────────────────────────────────
    # CLICK PANNELLI
    # ─────────────────────────────────────────────────────────────────────────

    def _left_click(self, mx, my_raw):
        logging.info(f"  [_left_click] Dispatching at ({mx}, {my_raw}) | Tab: {self.l_tab}")
        my = my_raw - TOP_BAR_H
        
        # 1. Gestione Tab (Area superiore 32px)
        if my < 32:
            tw = self.panel_l_w // 3
            new_tab = self.l_tab
            if mx < tw:     new_tab = TAB_TREE
            elif mx < tw*2: new_tab = TAB_CATALOG
            else:           new_tab = TAB_EFFECTS
            
            is_disabled = (self.active_layer == "effects" and new_tab in (TAB_TREE, TAB_CATALOG))
            if not is_disabled:
                self.l_tab = new_tab
                self.catalog_searching = False
                self._status(f"Tab: {self.l_tab.upper()}", ACCENT, 1)
            else:
                self._status("Tab disabilitata in modalità Effetti", (255, 100, 100), 2)
            return True
        if self.l_tab == TAB_CATALOG:
            self._catalog_click(mx, my_raw)
            return True
        if self.l_tab == TAB_TREE:
            self._tree_click(mx, my)
            return True
        if self.l_tab == TAB_EFFECTS:
            self._effects_catalog_click(mx, my_raw)
            return True
        return False

    def _right_click(self, rx, my_raw):
        if not self.panels_visible: return True
        my = my_raw - TOP_BAR_H
        
        if my < 32:
            self.r_tab = TAB_LAYERS if rx < self.panel_r_w // 2 else TAB_PROPS
            return True

        if self.r_tab == TAB_LAYERS:
            self._layers_click(rx, my); return True

        # Proprietà con Scroll
        self._props_click(rx, my + self.prop_scroll); return True

    def _tree_click(self, mx, my):
        # Sincronizzato con _r_tree: TOP_BAR_H + 36 nel render, 
        # qui my è già privo di TOP_BAR_H (quindi 0-30 = 0). Pertanto usiamo 36 base.
        y = 36 - self.tree_scroll * 28
        for level in self.levels:
            r = (8, y, self.panel_l_w - 24, 26)
            if _in_rect((mx, my), r):
                lid = level["id"]
                self.tree_expanded[lid] = not self.tree_expanded.get(lid, False)
                return
            y += 28
            if self.tree_expanded.get(level["id"], False):
                for sdir in level["scenes"]:
                    r2 = (24, y, self.panel_l_w - 40, 22)
                    if _in_rect((mx, my), r2):
                        self._load_scene(sdir); return
                    y += 24

    def _catalog_click(self, mx, my_raw):
        logging.info(f"  [CATALOG] _catalog_click called at ({mx}, {my_raw})")
        
        # 1. Search Bar Principale
        MARGIN = 12
        INNER_W = self.panel_l_w - MARGIN * 2
        search_r = pygame.Rect(MARGIN, TOP_BAR_H + 38, INNER_W, 32)
        if _in_rect((mx, my_raw), search_r):
            logging.info("  [CATALOG] HIT: Main Search Bar")
            sx_r = getattr(self, "_search_x_rect", None)
            if sx_r and _in_rect((mx, my_raw), sx_r):
                self.catalog_search = ""; self.catalog_scroll = 0
            else:
                self.catalog_searching = True; self.catalog_tag_searching = False
            return

        # 2. Tag Search Bar
        tag_search_r = getattr(self, "_tag_search_rect", None)
        if tag_search_r and _in_rect((mx, my_raw), tag_search_r):
            logging.info("  [CATALOG] HIT: Tag Search Bar")
            tx_r = getattr(self, "_tag_search_x_rect", None)
            if tx_r and _in_rect((mx, my_raw), tx_r):
                self.catalog_tag_search = ""
            else:
                self.catalog_tag_searching = True; self.catalog_searching = False
            return

        # 3. Chip Tags
        chip_rects = getattr(self, "_catalog_chip_rects", [])
        for tag_id, chip_r in chip_rects:
            if _in_rect((mx, my_raw), chip_r):
                logging.info(f"  [CATALOG] HIT: Tag Chip '{tag_id}'")
                if tag_id == "__toggle__":
                    self.catalog_chips_expanded = not getattr(self, "catalog_chips_expanded", False)
                else:
                    current = getattr(self, "catalog_tag_filters", set())
                    if tag_id == "tutti": self.catalog_tag_filters = set()
                    else: self.catalog_tag_filters = {tag_id} if tag_id not in current else set()
                # Reset scroll per vedere subito i tag selezionati balzati in cima
                self.catalog_tags_scroll = 0
                self.catalog_scroll = 0; self._play_click(); return

        # 4. Pulsante "Nuovo Oggetto" (Fondo fisso)
        h = self.screen.get_height()
        add_btn_h = 36
        by = h - STATUS_H - add_btn_h + 3
        if _in_rect((mx, my_raw), (MARGIN, by, INNER_W, add_btn_h - 6)):
            logging.info("  [CATALOG] HIT: New Object Button")
            self._newobj_open(); return

        # 5. Lista oggetti e Scrollbar (Utilizzo Hitbox dinamiche dal Render)
        si = getattr(self, "_catalog_scroll_info", None)
        if si:
            list_y = si["list_y"]
            available_h = si["bar_h"]
            
            # PRIORITÀ SCROLLBAR: zona destra del pannello
            if mx >= self.panel_l_w - 22 and my_raw >= list_y:
                if si["max_scroll"] > 0:
                    self._dragging_catalog_scroll = True
                    ratio = _clamp((my_raw - list_y) / available_h, 0, 1)
                    self.catalog_scroll = ratio * si["max_scroll"]
                    logging.info(f"  [CATALOG] HIT: Scrollbar (Scroll: {self.catalog_scroll:.2f})")
                    return

        # SELEZIONE OGGETTI (Hitbox precise esportate da render_panels.py)
        hitboxes = getattr(self, "_catalog_item_hitboxes", [])
        for cat_id, hr in hitboxes:
            if _in_rect((mx, my_raw), hr):
                logging.info(f"  [CATALOG] HIT: Object Item '{cat_id}' at {hr}")
                self.catalog_sel = cat_id
                
                # Trova i dati del catalogo per il detection type
                cat_item = next((c for c in self.catalog if c["id"] == cat_id), None)
                det = cat_item.get("default_detection", "circle") if cat_item else "circle"
                
                self.mode = MODE_CIRCLE if det == "circle" else MODE_RECT
                self.selected_idx = None
                self.selected_indices = []
                self._play_click()
                return
        
        logging.debug(f"  [CATALOG] No hit found at ({mx}, {my_raw})")


    def _left_panel_ctx_open(self, mx, my_raw):
        if self.l_tab != TAB_CATALOG: return
        # Utilizza Hitbox dal Render per precisione millimetrica
        hitboxes = getattr(self, "_catalog_item_hitboxes", [])
        for cat_id, hr in hitboxes:
            if _in_rect((mx, my_raw), hr):
                self._ctx_menu = {
                    "pos": (mx, my_raw),
                    "cat_id": cat_id,
                    "type": "catalog"
                }
                return
        
    def _layers_click(self, rx, my):
        # Allineamento millimetrico: 36 (start) + 18 (testo) + 4 (margine) = 58
        y = 58 
        all_layers = self._get_all_layers()
        for layer in all_layers:
            lid = layer["id"]
            is_scn = layer.get("is_scene", False)
            is_fx  = layer.get("is_fx", False)
            
            row_h = 40
            # Centratura hitbox icone (Occhio/Lucchetto) nell'altezza di 40px
            if not is_scn:
                # Occhio (VIS)
                if _in_rect((rx, my), (self.panel_r_w - 80, y + 8, 24, 24)):
                    self.layer_vis[lid] = not self.layer_vis.get(lid, True)
                    return
            
            if not is_scn and not is_fx:
                # Lucchetto (LOCK)
                if _in_rect((rx, my), (self.panel_r_w - 50, y + 8, 24, 24)):
                    self.layer_locked[lid] = not self.layer_locked.get(lid, False)
                    return

            # Selezione del layer
            if _in_rect((rx, my), (8, y, self.panel_r_w - 24, row_h)):
                if layer.get("is_scene"):
                    self.active_layer = lid # "scene_global"
                    self.selected_idx = None
                    self.selected_indices = []
                    self.sel_effect_idx = None
                    self.l_tab = TAB_TREE
                    self.r_tab = TAB_PROPS
                else:
                    self.active_layer = lid
                    if lid == "effects":
                        self.l_tab = TAB_EFFECTS
                return
            y += row_h + 4

    def _props_click(self, rx, my):
        # Se c'è un effetto selezionato, gestiamo i suoi click
        if getattr(self, "sel_effect_idx", None) is not None:
            self._effects_props_click(rx, my)
            return

        if self.selected_idx is None or self.selected_idx >= len(self.scene_data.get("objects", [])):
            if not self.scene_path: return
            
            hboxes = getattr(self, "_scene_props_hitboxes", {})
            mx, my = rx, my # rx e my sono già coordinati relativi al pannello e allo scroll
            
            # 1. Background
            if _in_rect((mx, my), hboxes.get("bg_btn", pygame.Rect(0,0,0,0))):
                self._load_background(); return
            
            # 2. Objects To Show
            if _in_rect((mx, my), hboxes.get("ots_box", pygame.Rect(0,0,0,0))):
                self._editing_prop = ('scene', 0, 'objects_to_show')
                self._prop_buf = str(self.scene_data.get("objects_to_show", 0))
                return
            ots_sl = hboxes.get("ots_slider")
            if ots_sl and _in_rect((mx, my), ots_sl):
                self._push_undo()
                rel_x = mx - ots_sl.x
                ratio = _clamp(rel_x / ots_sl.w, 0.0, 1.0)
                max_obj = len(self.scene_data.get("objects", []))
                val = int(ratio * max_obj)
                self.scene_data["objects_to_show"] = max(1, val)
                self.scene_dirty = True
                self._dragging_slider = ('scene', 0, 'objects_to_show', 1, max_obj, ots_sl.x, ots_sl.w)
                return

            # 3. Rotazione Automatica Toggle
            if _in_rect((mx, my), hboxes.get("auto_btn", pygame.Rect(0,0,0,0))):
                self._push_undo()
                val = not self.scene_data.get("auto_random_finds", False)
                self.scene_data["auto_random_finds"] = val
                self.scene_dirty = True
                self._status(f"Rotazione auto: {'ON' if val else 'OFF'}", OK_C, 2)
                return

            # 3.5 Selezione Layer Casuale Toggle
            if _in_rect((mx, my), hboxes.get("rand_l_btn", pygame.Rect(0,0,0,0))):
                self._push_undo()
                val = not self.scene_data.get("random_layer_selection", False)
                self.scene_data["random_layer_selection"] = val
                self.scene_dirty = True
                self._status(f"Random Layer Mode: {'ON' if val else 'OFF'}", ALWAYS_C, 2)
                return

            # 4. Num Random Finds (se attivo)
            if self.scene_data.get("auto_random_finds", False):
                if _in_rect((mx, my), hboxes.get("nr_box", pygame.Rect(0,0,0,0))):
                    self._editing_prop = ('scene', 0, 'num_random_finds')
                    self._prop_buf = str(self.scene_data.get("num_random_finds", 1))
                    return
                nr_sl = hboxes.get("nr_slider")
                if nr_sl and _in_rect((mx, my), nr_sl):
                    self._push_undo()
                    rel_x = mx - nr_sl.x
                    ratio = _clamp(rel_x / nr_sl.w, 0.0, 1.0)
                    max_obj = len(self.scene_data.get("objects", []))
                    val = max(1, int(ratio * max_obj))
                    self.scene_data["num_random_finds"] = val
                    self.scene_dirty = True
                    self._dragging_slider = ('scene', 0, 'num_random_finds', 1, max_obj, nr_sl.x, nr_sl.w)
                    return

            # 5. Modifica Traduzioni
            if _in_rect((mx, my), hboxes.get("lang_btn", pygame.Rect(0,0,0,0))):
                self._lang_modal = False if self._lang_modal else None
                if not self._lang_modal: self._lang_open()
                return

            # 6. Icone Canvas Toggle
            if _in_rect((mx, my), hboxes.get("ico_btn", pygame.Rect(0,0,0,0))):
                self.show_icons = not self.show_icons; return

            # 7. Torcia Toggle
            if _in_rect((mx, my), hboxes.get("fl_btn", pygame.Rect(0,0,0,0))):
                self._push_undo()
                val = not self.scene_data.get("flashlight", False)
                self.scene_data["flashlight"] = val
                self.scene_dirty = True
                self._status(f"Torcia: {'ON' if val else 'OFF'}", FX_C, 2)
                return
            
            if self.scene_data.get("flashlight", False):
                if _in_rect((mx, my), hboxes.get("fl_rad_box", pygame.Rect(0,0,0,0))):
                    self._editing_prop = ('scene', 0, 'flashlight_radius')
                    self._prop_buf = f"{self.scene_data.get('flashlight_radius', 150.0):.1f}"
                    return
                fl_sl = hboxes.get("fl_rad_slider")
                if fl_sl and _in_rect((mx, my), fl_sl):
                    self._push_undo()
                    rel_x = mx - fl_sl.x
                    ratio = _clamp(rel_x / fl_sl.w, 0.0, 1.0)
                    val = 50.0 + ratio * 450.0
                    self.scene_data["flashlight_radius"] = round(val, 1)
                    self.scene_dirty = True
                    self._dragging_slider = ('scene', 0, 'flashlight_radius', 50, 500, fl_sl.x, fl_sl.w)
                    return

            # 8. Salva Scena
            if _in_rect((mx, my), hboxes.get("save_btn", pygame.Rect(0,0,0,0))):
                self._save(); return

            # 9. Musica
            if _in_rect((mx, my), hboxes.get("mus_add_btn", pygame.Rect(0,0,0,0))):
                self._add_music_dialog(); return
            if _in_rect((mx, my), hboxes.get("mus_clr_btn", pygame.Rect(0,0,0,0))):
                self._push_undo()
                self.scene_data["music"] = []
                self.scene_dirty = True
                self._status("Musiche della scena rimosse", WARN_C, 3)
                return
            
            # 10. Svuota Scena (con conferma)
            if _in_rect((mx, my), hboxes.get("clear_scene_btn", pygame.Rect(0,0,0,0))):
                if getattr(self, "_confirm_clear", False):
                    self._clear_scene()
                    self._confirm_clear = False
                else:
                    self._confirm_clear = True
                return
            
            self._confirm_clear = False
            return

        # Recupero oggetto selezionato per evitare NameError
        if self.selected_idx is None or self.selected_idx >= len(self.scene_data["objects"]):
            return
            
        obj = self.scene_data["objects"][self.selected_idx]

        # --- COORDINATE RELATIVE PER HITBOX DYNAMICHE ---
        # my è già (my_raw - TOP_BAR_H + self.prop_scroll) passato dal chiamante
        # Useremo le hitbox esportate dal render per evitare disallineamenti
        hboxes = getattr(self, "_obj_props_hitboxes", {})

        # Pulsante "Torna alla Scena"
        back_r = hboxes.get("back_btn")
        if back_r and _in_rect((rx, my), back_r):
            self.selected_idx = None
            self.selected_indices = []
            self.active_layer = "scene_global"
            return

        # Grayscale Slider/Box
        gs_box_r = hboxes.get("gs_box")
        if gs_box_r and _in_rect((rx, my), gs_box_r):
            self._editing_prop = ('object', self.selected_idx, 'grayscale_factor')
            # Mostriamo come percentuale intera per comodità
            self._prop_buf = str(int(obj.get("grayscale_factor", 1.0) * 100))
            return
        
        gs_slider_r = hboxes.get("gs_slider")
        if gs_slider_r and _in_rect((rx, my), gs_slider_r):
            self._push_undo()
            rel_x = rx - gs_slider_r.x
            val = _clamp(rel_x / gs_slider_r.w, 0.0, 1.0)
            obj["grayscale_factor"] = round(val, 2)
            self.scene_dirty = True
            # Avvia dragging
            self._dragging_slider = ('object', self.selected_idx, 'grayscale_factor', 0.0, 1.0, gs_slider_r.x, gs_slider_r.w)
            return

        # Obiettivo Fisso (Toggle)
        always_r = hboxes.get("always_btn")
        if always_r and _in_rect((rx, my), always_r):
            self._push_undo()
            obj["always_show"] = not obj.get("always_show", False)
            self.scene_dirty = True
            return


        # Goal Toggle
        goal_r = hboxes.get("goal_btn")
        if goal_r and _in_rect((rx, my), goal_r):
            self._push_undo()
            obj["is_goal"] = not obj.get("is_goal", True)
            self.scene_dirty = True
            return

        # Minigame Trigger
        mg_btn = hboxes.get("minigame_btn")
        if mg_btn and _in_rect((rx, my), mg_btn):
            self._minigame_open(); return
            
        mg_clr = hboxes.get("minigame_clear_btn")
        if mg_clr and _in_rect((rx, my), mg_clr):
            self._push_undo()
            if "minigame_trigger" in obj:
                del obj["minigame_trigger"]
            self.scene_dirty = True
            self._status("Trigger minigioco rimosso.", WARN_C, 2)
            return

        # Duplica
        dup_r = hboxes.get("dup_btn")
        if dup_r and _in_rect((rx, my), dup_r):
            self._duplicate(); return

        # Elimina
        del_r = hboxes.get("del_btn")
        if del_r and _in_rect((rx, my), del_r):
            self._delete_sel(); return

    def _effects_catalog_click(self, mx, my_raw):
        """Seleziona un effetto dal catalogo a sinistra."""
        hitboxes = getattr(self, "_effects_item_hitboxes", [])
        for fx_id, hr in hitboxes:
            if _in_rect((mx, my_raw), hr):
                self.effects_catalog_sel = fx_id
                self.mode = MODE_EFFECT_PLACE
                self.selected_idx = None
                self.selected_indices = []
                self.sel_effect_idx = None
                self._status(f"Piazza effetto: {fx_id}", FX_C, 2)
                self._play_click(); return

    def _effects_props_click(self, rx, my):
        """Gestore click per il pannello proprietà degli effetti (destra)."""
        idx = self.sel_effect_idx
        if idx is None or idx >= len(self.scene_data["effects"]): return
        
        fx = self.scene_data["effects"][idx]
        hboxes = getattr(self, "_fx_props_hitboxes", {})
        self._editing_prop = None # Reset focus

        # Pulsante Torna
        if _in_rect((rx, my), hboxes.get("back_btn", pygame.Rect(0,0,0,0))):
            self.sel_effect_idx = None
            self._play_click(); return

        is_bt = (fx.get("type") == "bubble_tip")
        
        if is_bt:
            # --- LOGICA BUBBLE TIP ---
            if getattr(self, "_editing_preset_name", False):
                if _in_rect((rx, my), hboxes.get("preset_name_box", pygame.Rect(0,0,0,0))): return
            else:
                if _in_rect((rx, my), hboxes.get("preset_drop", pygame.Rect(0,0,0,0))):
                    self._preset_dropdown_open = not getattr(self, "_preset_dropdown_open", False)
                    return
                if _in_rect((rx, my), hboxes.get("preset_load", pygame.Rect(0,0,0,0))):
                    p_key = getattr(self, "_preset_selected", "")
                    if p_key in self.bubble_presets:
                        self._push_undo()
                        p_data = self.bubble_presets[p_key]
                        for k in ["width", "height", "alpha", "color", "font_size", "font_color"]:
                            if k in p_data: fx[k] = p_data[k]
                        self.scene_dirty = True
                        self._status(f"Preset caricato: {p_key}", OK_C, 2)
                    return
                if _in_rect((rx, my), hboxes.get("preset_save", pygame.Rect(0,0,0,0))):
                    self._editing_preset_name = True
                    self._preset_name_buf = getattr(self, "_preset_selected", "")
                    return
                
                if getattr(self, "_preset_dropdown_open", False):
                    for p_key in self.bubble_presets.keys():
                        if _in_rect((rx, my), hboxes.get(f"pitem_{p_key}", pygame.Rect(0,0,0,0))):
                            self._preset_selected = p_key
                            self._preset_dropdown_open = False
                            return

            if _in_rect((rx, my), hboxes.get("tkey_box", pygame.Rect(0,0,0,0))):
                self._editing_prop = ('effect', idx, 'text_key')
                self._prop_buf = fx.get("text_key", "NEW_TIP")
                return
            if _in_rect((rx, my), hboxes.get("translations_btn", pygame.Rect(0,0,0,0))):
                self._lang_open("fx", fx.get("text_key", "NEW_TIP"))
                return
            for tid in ["start_scene", "end_scene"]:
                if _in_rect((rx, my), hboxes.get(f"trigger_{tid}", pygame.Rect(0,0,0,0))):
                    self._push_undo(); fx["trigger"] = tid
                    self.scene_dirty = True; return

            if _in_rect((rx, my), hboxes.get("color_body", pygame.Rect(0,0,0,0))):
                self._pick_color_for_effect(idx, "color", "Colore Corpo"); return
            if _in_rect((rx, my), hboxes.get("color_font", pygame.Rect(0,0,0,0))):
                self._pick_color_for_effect(idx, "font_color", "Colore Testo"); return

        else:
            # --- LOGICA EFFETTI STANDARD ---
            if _in_rect((rx, my), hboxes.get("color_effect", pygame.Rect(0,0,0,0))):
                self._pick_color_for_effect(idx); return

        # --- LOGICA SLIDERS & BOXES (COMUNE) ---
        keys = ["radius", "intensity", "pulse_period", "pulse_min", "phase"]
        if is_bt: keys = ["width", "height", "alpha", "font_size"]
        
        for k in keys:
            br = hboxes.get(f"box_{k}")
            if br and _in_rect((rx, my), br):
                self._editing_prop = ('effect', idx, k)
                self._prop_buf = str(fx.get(k, 0)); return
            
            sr = hboxes.get(f"slider_{k}")
            if sr and _in_rect((rx, my), sr):
                self._push_undo()
                ftype = fx.get("type", "")
                mn, mx_v = 0.0, 1.0
                if k == "radius": mn, mx_v = (0.2, 100.0) if ftype=="smoke" else (5, 2000)
                elif k == "intensity": mn, mx_v = 0.01, 2.0
                elif k == "pulse_period": mn, mx_v = 0.05, (3.5 if ftype=="smoke" else 10.0)
                elif k == "pulse_min": mn, mx_v = (0.0, 10.0) if ftype=="smoke" else (0.0, 2.0)
                elif k == "phase": mn, mx_v = 0.0, 1.0
                elif k == "width": mn, mx_v = 40, 800
                elif k == "height": mn, mx_v = 30, 600
                elif k == "alpha": mn, mx_v = 0, 255
                elif k == "font_size": mn, mx_v = 10, 80
                
                ratio = _clamp((rx - sr.x) / sr.w, 0.0, 1.0)
                if k in ("pulse_period", "pulse_min"):
                    fx[k] = round(mn + (ratio**2) * (mx_v - mn), 2)
                else:
                    fx[k] = round(mn + ratio * (mx_v - mn), 2)
                
                self.scene_dirty = True
                self._dragging_slider = ('effect', idx, k, mn, mx_v, sr.x, sr.w); return

        # Bottoni Duplica/Elimina
        if _in_rect((rx, my), hboxes.get("dup_btn", pygame.Rect(0,0,0,0))):
            import copy
            self._push_undo()
            new_fx = copy.deepcopy(fx)
            if new_fx.get("type") == "bubble_tip":
                new_fx["text_key"] += "_COPY"
            self.scene_data["effects"].append(new_fx)
            self.sel_effect_idx = len(self.scene_data["effects"]) - 1
            self.scene_dirty = True; return

        if _in_rect((rx, my), hboxes.get("del_btn", pygame.Rect(0,0,0,0))):
            self._push_undo()
            # Rimuove la chiave dal file lingua se è un bubble_tip
            if fx.get("type") == "bubble_tip":
                tkey = fx.get("text_key", "")
                if tkey and tkey.startswith("TIP_"):
                    self._cleanup_translation_key(tkey)
            self.scene_data["effects"].pop(idx)
            self.sel_effect_idx = None
            self.scene_dirty = True; return

    def _place_effect(self, mx, my):
        if not self.effects_catalog_sel: return
        rx, ry = self._s2r(mx, my)
        cat = next((c for c in self.effects_catalog if c["id"] == self.effects_catalog_sel), None)
        if not cat: return
        
        self._push_undo()
        from editor.core.io import _default_effect

        # Controllo Lock
        if self.layer_locked.get("effects", False):
            self._status("Layer EFFETTI bloccato!", ERR_C, 2)
            return

        # Nuovo sistema: tutti gli effetti vanno nel layer "effects"
        lyr_id = "effects"
        lyr_z  = 100
        
        if cat["type"] == "bubble_tip":
            import uuid, re
            scene_str = str(self.scene_data.get("id", getattr(self.scene_path, "stem", "scene")))
            scene_str = re.sub(r'[^a-zA-Z0-9]', '', scene_str)
            uid = uuid.uuid4().hex[:5].upper()
            t_key = f"TIP_{scene_str}_{uid}"
            # Crea segnaposto vuoto in tutti i file lingua del gioco
            missing = self._ensure_translation_key(t_key)
            if missing:
                self._status(f"Traduci '{t_key}' in: {', '.join(missing)}", WARN_C, 4)
        else:
            t_key = ""

        new_fx = _default_effect(
            effect_id=cat["id"],
            effect_type=cat["type"],
            x=self._snap(rx),
            y=self._snap(ry),
            radius=cat.get("default_radius", 55),
            color=cat.get("default_color", [255, 215, 60]),
            intensity=cat.get("default_intensity", 0.85),
            pulse_period=cat.get("default_pulse_period", 2.0),
            pulse_min=cat.get("default_pulse_min", 0.1),
            width=cat.get("default_width", 300),
            height=cat.get("default_height", 180),
            text_key=t_key,
            layer=lyr_id,
            layer_z=lyr_z
        )
        if "effects" not in self.scene_data: self.scene_data["effects"] = []
        self.scene_data["effects"].append(new_fx)
        self.sel_effect_idx = len(self.scene_data["effects"]) - 1
        # Pulisci selezione oggetti quando piazzi un effetto
        self.selected_idx = None
        self.selected_indices = []
        
        self.scene_dirty = True
        self.mode = MODE_SELECT
        self._status(f"Effetto aggiunto: {cat['id']}", OK_C, 2)

    def _try_select_effect(self, mx, my) -> bool:
        rx, ry = self._s2r(mx, my)
        effects = self.scene_data.get("effects", [])
        for i, fx in enumerate(reversed(effects)):
            lid = fx.get("layer", "effects")
            if not self.layer_vis.get(lid, True):
                continue
            
            t_type = fx.get("type", "glint")
            hit = False
            
            if t_type == "bubble_tip":
                bw, bh = fx.get("width", 300), fx.get("height", 180)
                bx, by = fx["x"] - bw//2, fx["y"] - bh - 35
                if bx <= rx <= bx + bw and by <= ry <= by + bh:
                    hit = True
                # Hit test anche sulla punta
                elif math.hypot(rx - fx["x"], ry - fx["y"]) < 15:
                    hit = True
            else:
                dist = math.hypot(rx - fx["x"], ry - fx["y"])
                hit_dist = 20
                if t_type == "smoke":
                    # Il fumo è alto, permettiamo di cliccare anche un po' sopra l'origine
                    # Area rettangolare sopra l'origine + cerchio base
                    if abs(rx - fx["x"]) < 40 and fx["y"]-150 < ry < fx["y"]+20:
                        hit = True
                    hit_dist = 30
                
                if not hit and dist < hit_dist: 
                    hit = True
            
            if hit:
                self._push_undo()
                self.sel_effect_idx = len(effects) - 1 - i
                self.selected_idx = None
                self.selected_indices = []
                self.r_tab = TAB_PROPS
                self.active_layer = "effects" # Passa al layer effetti
                self.l_tab = TAB_EFFECTS      # Passa alla tab catalogo effetti
                self._dragging_effect_idx = self.sel_effect_idx
                self._drag_active = True
                self._drag_start_mx = mx
                self._drag_start_my = my
                self._drag_start_x  = fx["x"]
                self._drag_start_y  = fx["y"]
                self.scene_dirty = True
                return True
        return False

    def _do_drag_effect(self, mx, my):
        idx = getattr(self, "_dragging_effect_idx", None)
        if idx is None: return
        dx = (mx - self._drag_start_mx) / self.zoom
        dy = (my - self._drag_start_my) / self.zoom
        fx = self.scene_data["effects"][idx]
        fx["x"] = self._snap(self._drag_start_x + dx)
        fx["y"] = self._snap(self._drag_start_y + dy)
        self.scene_dirty = True
        self.scene_dirty = True

    def _do_drag_slider(self, mx, my):
        ds = getattr(self, "_dragging_slider", None)
        if not ds: return
        owner, idx, key, min_v, max_v, sx, sw = ds
        # Offset relativo al pannello destro
        w, h = self.screen.get_size()
        rx = mx - (w - self.panel_r_w)
        rel_x = rx - sx
        ratio = _clamp(rel_x / sw, 0.0, 1.0)
        
        if key in ("pulse_period", "pulse_min") and owner == 'effect':
            val = min_v + (ratio**2) * (max_v - min_v)
        else:
            val = min_v + ratio * (max_v - min_v)
            
        if isinstance(min_v, int) and isinstance(max_v, int):
            val = int(val)
        else:
            val = round(val, 2)

        if owner == 'effect':
            fx = self.scene_data["effects"][idx]
            if key == "radius" and fx.get("type") == "smoke":
                val = round(val * 5) / 5.0
            fx[key] = val
        elif owner == 'object':
            self.scene_data["objects"][idx][key] = val
        elif owner == 'scene':
            self.scene_data[key] = val
        
        self.scene_dirty = True
        return True

    def _delete_effect_sel(self):
        idx = getattr(self, "sel_effect_idx", None)
        if idx is not None and idx < len(self.scene_data.get("effects", [])):
            self._push_undo()
            self.scene_data["effects"].pop(idx)
            self.sel_effect_idx = None
            self.scene_dirty = True
            self._status("Effetto rimosso", WARN_C, 2)
    # ─────────────────────────────────────────────────────────────────────────
    # MENU ACTIONS
    # ─────────────────────────────────────────────────────────────────────────

    def _menu_click(self, mx, my):
        """Gestisce i click sui pulsanti della top bar e sui dropdown."""
        # Check pulsanti principali (Top Bar)
        for name, rect in self._menu_bounds.items():
            if _in_rect((mx, my), rect):
                if self._active_menu == name:
                    self._active_menu = None
                else:
                    self._active_menu = name
                return

        # Check dropdown items (Sotto la Top Bar)
        if self._active_menu:
            root_r = self._menu_bounds[self._active_menu]
            items = self._get_menu_items(self._active_menu)
            
            ITEM_H = 26
            from editor.constants import MENU_W
            drop_r = pygame.Rect(root_r.x, TOP_BAR_H, MENU_W, len(items) * ITEM_H)
            
            if _in_rect((mx, my), drop_r):
                idx = (my - TOP_BAR_H) // ITEM_H
                if 0 <= idx < len(items) and items[idx] is not None:
                    # items[idx] è una tupla (label, cmd)
                    label, cmd = items[idx]
                    self._exec_menu_cmd(cmd)
                self._active_menu = None
                return

    def _exec_menu_cmd(self, cmd: str):
        """Esegue il comando logico del menu."""
        logging.info(f"[MENU] Esecuzione comando: {cmd}")
        
        # FILE
        if cmd == "file_new_game":
            self.state = STATE_GAME_SELECT
            self._gs_new_mode = "game"
            self._gs_new_buf = ""
        elif cmd == "file_open_game" or cmd == "file_exit_to_gs":
            self.state = STATE_GAME_SELECT
        elif cmd == "file_save_scene":
            self._save()
        elif cmd == "file_quit":
            self.running = False
            
        # EDIT
        elif cmd == "edit_undo": self._undo()
        elif cmd == "edit_redo": self._redo()
        elif cmd == "edit_cut":  self._cut_sel()
        elif cmd == "edit_copy": self._copy_sel()
        elif cmd == "edit_paste": self._paste_sel()
        elif cmd == "edit_lang_modal": self._lang_open()
        
        # LANG SWITCH
        elif cmd.startswith("lang_switch_"):
            new_lang = cmd.replace("lang_switch_", "")
            self.current_lang = new_lang
            self._save_editor_setting("language", new_lang)
            # Ricarichiamo le stringhe nel manager
            # Se siamo in un gioco, ricarichiamo per quel gioco
            g_id = self.game_path.name if self.game_path else "engine"
            self.lang_manager.load_for_game(g_id, new_lang)
            
            # Reset cache labels per il Game Selector se siamo lì
            if self.state == STATE_GAME_SELECT:
                self._gs_refresh_cache()
                
            self._status(f"Lingua impostata: {new_lang.upper()}", OK_C, 2)
