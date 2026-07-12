"""
editor/mixins/input_handlers.py

InputHandlersMixin — gestione eventi pygame: keyboard, mouse (down/up/move/wheel),
                     pan/zoom, drag, handle resize, click pannelli.
"""

import copy
import math
import time
import pygame
import logging

from editor.constants import (
    TOP_BAR_H, STATUS_H,
    MIN_EDITOR_WIDTH, MIN_EDITOR_HEIGHT, WIN_W, WIN_H,
    REF_W, REF_H,
    MODE_SELECT, MODE_CIRCLE, MODE_RECT, MODE_EFFECT_PLACE, MODE_SCATTER,
    STATE_GAME_SELECT, STATE_MAIN,
    TAB_TREE, TAB_CATALOG, TAB_EFFECTS, TAB_LAYERS, TAB_PROPS,
    ACCENT, OK_C, ERR_C, WARN_C, TXT, TXT_DIM, FX_C, ALWAYS_C,
    GRID_SIZES, NUDGE_STEP, NUDGE_STEP_FAST, NUDGE_UNDO_GAP_S, OBJ_SNAP_PX,
    UI_SCALE_STEP,
)
from editor.core.io import _discover_games, _default_effect
from editor.ui.draw import _in_rect, _clamp


class InputHandlersMixin:
    """Gestione completa input: keyboard, mouse, scroll."""

    # ─────────────────────────────────────────────────────────────────────────
    # LOOP EVENTI
    # ─────────────────────────────────────────────────────────────────────────

    def _handle_events(self):
        # Eventi di input utente catturati dal top dello stack modale unificato
        _MODAL_INPUT_EVENTS = (
            pygame.KEYDOWN, pygame.KEYUP, pygame.TEXTINPUT,
            pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP,
            pygame.MOUSEMOTION, pygame.MOUSEWHEEL,
        )
        for ev in pygame.event.get():
            # QUIT ha priorità assoluta — non può essere bloccato da nessun modale
            if ev.type == pygame.QUIT:
                self._request_nav("file_quit")
                continue
            # Stack modale unificato: il top e' app-modal e consuma l'input utente
            if self.modal_stack and ev.type in _MODAL_INPUT_EVENTS:
                self.modal_stack[-1].handle_event(self, ev)
                continue
            if self._img_editor_active:
                self._img_editor_handle_event(ev); continue
            # Auditor modale ha priorità dopo img_editor e prima degli altri
            if getattr(self, "_auditor_active", False):
                self._auditor_handle_event(ev); continue
            elif ev.type == pygame.KEYDOWN:
                self._on_key(ev)
            elif ev.type == pygame.MOUSEBUTTONDOWN:
                self._on_mdown(ev)
            elif ev.type == pygame.MOUSEBUTTONUP:
                self._on_mup(ev)
            elif ev.type == pygame.VIDEORESIZE or (hasattr(pygame, "WINDOWSIZECHANGED") and ev.type == pygame.WINDOWSIZECHANGED) or (hasattr(pygame, "WINDOWRESIZED") and ev.type == pygame.WINDOWRESIZED):
                # Estrazione robusta dimensioni
                if hasattr(ev, "size"):
                    w_raw, h_raw = ev.size
                elif hasattr(ev, "w"):
                    w_raw, h_raw = ev.w, ev.h
                else:
                    w_raw, h_raw = getattr(ev, "x", MIN_EDITOR_WIDTH), getattr(ev, "y", MIN_EDITOR_HEIGHT)
                
                w = max(w_raw, MIN_EDITOR_WIDTH)
                h = max(h_raw, MIN_EDITOR_HEIGHT)
                
                # Se le dimensioni sono sotto il limite, forziamo il ripristino
                is_under_limit = (w_raw < MIN_EDITOR_WIDTH or h_raw < MIN_EDITOR_HEIGHT)
                
                if self.screen.get_width() != w or self.screen.get_height() != h:
                    # Chiamiamo set_mode solo se la finestra fisica è diversa dal target calcolato
                    self.screen = pygame.display.set_mode((w, h), pygame.RESIZABLE)
                    self.screen_size = (w, h)
                    self._fit_canvas()
                    
                    if is_under_limit:
                        # Messaggio di feedback "cura" l'esperienza utente
                        self._status(f"Limite UI raggiunto: {w}x{h} (HD)", WARN_C, 2)
                    else:
                        self._status(f"Resized: {w}x{h}", TXT_DIM, 1)
                else:
                    # Aggiorna layout interno anche se non c'è stato set_mode (dimensioni valide)
                    self.screen_size = (w, h)
                    self._fit_canvas()
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
                elif getattr(self, "_icon_modal", False):
                    self._icon_handle_drop(ev.file)

    # ─────────────────────────────────────────────────────────────────────────
    # KEYBOARD
    # ─────────────────────────────────────────────────────────────────────────

    def _on_key(self, ev):
        mods = pygame.key.get_mods()
        # Rilevamento Ctrl esteso per miglior compatibilità Windows/Linux/Mac
        ctrl = bool(mods & pygame.KMOD_CTRL) or bool(mods & pygame.KMOD_META)

        # ── 1. MODALI (Priorità assoluta: catturano tutto l'input) ────────────────
        if self._newobj_modal:
            self._newobj_key(ev); return
        if self._tag_modal_active:
            self._tag_modal_key(ev); return
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
        if self._img_editor_active:
            return
        # Modali senza editing di testo: assorbono comunque l'input affinche' le
        # scorciatoie globali (mode 1/2/3/4, Canc, Esc, Ctrl+...) non raggiungano
        # la scena sottostante mentre il modale e' aperto.
        if getattr(self, "_minigame_modal", False):
            if ev.key == pygame.K_ESCAPE:
                self._minigame_modal = False
            return
        if getattr(self, "_stats_modal", False):
            self._stats_modal_key(ev)
            return
        if getattr(self, "_scatter_modal_open", False):
            # ESC con priorita' brush -> seed -> annulla run -> chiudi, piu'
            # editing del campo seed: tutto in _scatter_modal_key (U1/U2).
            self._scatter_modal_key(ev)
            return
        if getattr(self, "_confirm_leave_modal", False):
            if ev.key == pygame.K_ESCAPE:
                self._confirm_leave_modal = False
                self._pending_action = None
            return

        # ── 2. SHORTCUT GLOBALI (Ctrl+S, Ctrl+Z, ...) ─────────────────────────────
        # Funzionano anche se siamo in modalità ricerca o editing proprietà,
        # a meno che non siamo in un modale (gestito sopra).
        if ctrl:
            # S = Salva
            if ev.key == pygame.K_s or ev.unicode.lower() == 's':
                if self.state == STATE_MAIN:
                    self._with_loading(self._save); return
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

            # Ctrl+Piu'/Meno = scala UI (font e icone della chrome editor)
            if ev.key in (pygame.K_PLUS, pygame.K_EQUALS, pygame.K_KP_PLUS):
                self._set_ui_scale(UI_SCALE_STEP); return
            if ev.key in (pygame.K_MINUS, pygame.K_KP_MINUS):
                self._set_ui_scale(-UI_SCALE_STEP); return

            # G = snap a oggetti on/off (persistito)
            if ev.key == pygame.K_g:
                self.obj_snap = not getattr(self, "obj_snap", True)
                self._save_editor_setting("obj_snap", self.obj_snap)
                self._status(
                    f"Snap a oggetti: {'ON' if self.obj_snap else 'OFF'}", ACCENT, 2)
                return

        # ── 3. MODALITÀ EDITING TESTO (Search bars, Numeric props) ────────────────
        # Se siamo in queste modalità e NON è premuto Ctrl, catturiamo l'input.
        if self._editing_prop:
            self._prop_key(ev); return

        if self.catalog_searching:
            if ev.key in (pygame.K_ESCAPE, pygame.K_RETURN):
                self.catalog_searching = False
            elif ev.key in (pygame.K_BACKSPACE, pygame.K_DELETE):
                self.catalog_search = self.catalog_search[:-1]
                self.catalog_scroll = 0
            elif ev.unicode and ev.unicode.isprintable():
                self.catalog_search += ev.unicode.lower()
                self.catalog_scroll = 0
            return

        if getattr(self, "catalog_tag_searching", False):
            if ev.key in (pygame.K_ESCAPE, pygame.K_RETURN):
                self.catalog_tag_searching = False
            elif ev.key in (pygame.K_BACKSPACE, pygame.K_DELETE):
                ts = getattr(self, "catalog_tag_search", "")
                self.catalog_tag_search = ts[:-1]
            elif ev.unicode and ev.unicode.isprintable():
                self.catalog_tag_search = getattr(self, "catalog_tag_search", "") + ev.unicode.lower()
                self.catalog_tag_filters = set()
            return

        # ── 4. DASHBOARD (GS) ───────────────────────────────────────────────────
        if self.state == STATE_GAME_SELECT:
            self._gs_key(ev); return

        # Anteprima come-in-gioco: F5/Esc escono, il resto e' bloccato
        if getattr(self, "_preview_mode", False):
            if ev.key in (pygame.K_F5, pygame.K_ESCAPE):
                self._preview_toggle()
            return

        if not ctrl:
            if ev.key == pygame.K_F5:
                self._preview_toggle(); return
            if ev.key == pygame.K_HOME:
                def go_home():
                    self.state = STATE_GAME_SELECT
                    self.gs_games = _discover_games(self.base_path)
                self._request_nav(go_home)
                return
            if ev.key == pygame.K_s:
                self.mode = MODE_SELECT; self._cancel_rect()
                self.sel_effect_idx = None; self._editing_prop = None; return
            if ev.key == pygame.K_1:
                self.mode = MODE_CIRCLE; self._cancel_rect()
                self.selected_idx = None; self.selected_indices = []
                self.sel_effect_idx = None; self._editing_prop = None
                self._mark_dirty(); return
            if ev.key == pygame.K_2:
                self.mode = MODE_RECT; self._cancel_rect()
                self.selected_idx = None; self.selected_indices = []
                self.sel_effect_idx = None; self._editing_prop = None
                self._mark_dirty(); return
            if ev.key == pygame.K_4:
                self.mode = MODE_SCATTER; self._cancel_rect()
                self.selected_idx = None; self.selected_indices = []
                self.sel_effect_idx = None; self._editing_prop = None
                self._status("Piazza Cluster (4 oggetti random)", ACCENT, 2)
                self._mark_dirty(); return
            if ev.key == pygame.K_3:
                if self.effects_catalog_sel:
                    self.mode = MODE_EFFECT_PLACE; self._cancel_rect()
                    self.selected_idx = None; self.selected_indices = []
                    self.sel_effect_idx = None; self._editing_prop = None
                    self._mark_dirty()
                    self._status(f"Piazza effetto: {self.effects_catalog_sel}", FX_C, 2)
                else:
                    # Se non c'è selezione, apri la tab effetti per facilitare l'utente
                    from editor.constants import TAB_EFFECTS
                    self.l_tab = TAB_EFFECTS
                    self.panels_visible = True
                    self._status("Seleziona un effetto dal catalogo", FX_C, 2)
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
            if ev.key == pygame.K_g:
                if mods & pygame.KMOD_SHIFT:
                    # Shift+G: cicla la dimensione della griglia (persistita)
                    try:
                        gi = GRID_SIZES.index(self.grid_size)
                    except ValueError:
                        gi = -1
                    self.grid_size = GRID_SIZES[(gi + 1) % len(GRID_SIZES)]
                    self._save_editor_setting("grid_size", self.grid_size)
                    self.show_grid = True
                    self._status(f"Griglia: {self.grid_size}px", ACCENT, 2)
                else:
                    self.show_grid = not self.show_grid
                self._mark_dirty()
                return
            if ev.key == pygame.K_i:
                self.show_icons = not self.show_icons
                self._mark_dirty()
                return
            if ev.key == pygame.K_f:  self._fit_canvas();                         return
            if ev.key == pygame.K_z:  self._zoom_to_selection();                  return
            if ev.key == pygame.K_l:
                self.r_tab = TAB_LAYERS if self.r_tab != TAB_LAYERS else TAB_PROPS
                return
            if ev.key in (pygame.K_PLUS, pygame.K_EQUALS, pygame.K_KP_PLUS):
                self._zoom_by(1.2);  return
            if ev.key in (pygame.K_MINUS, pygame.K_KP_MINUS):
                self._zoom_by(1/1.2); return
            if ev.key in (pygame.K_LEFT, pygame.K_RIGHT, pygame.K_UP, pygame.K_DOWN):
                # Frecce: nudge della selezione (Shift = passo grande);
                # senza selezione mantengono il pan del canvas.
                ndx = int(ev.key == pygame.K_RIGHT) - int(ev.key == pygame.K_LEFT)
                ndy = int(ev.key == pygame.K_DOWN) - int(ev.key == pygame.K_UP)
                step = NUDGE_STEP_FAST if (mods & pygame.KMOD_SHIFT) else NUDGE_STEP
                if not self._nudge_sel(ndx * step, ndy * step):
                    self._pan_by(-ndx * self._pan_speed, -ndy * self._pan_speed)
                return
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
                    self._mark_dirty()
                    return
                if ev.key == pygame.K_v:
                    self._push_undo()
                    obj["flip_y"] = not obj.get("flip_y", False)
                    self._mark_dirty()
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
                    self.screen = pygame.display.set_mode((WIN_W, WIN_H), pygame.RESIZABLE)
                self.screen_size = self.screen.get_size()
                
                # Applica limiti minimi se siamo tornati in windowed
                if not self.fullscreen:
                    w, h = self.screen_size
                    if w < MIN_EDITOR_WIDTH or h < MIN_EDITOR_HEIGHT:
                        w = max(w, MIN_EDITOR_WIDTH)
                        h = max(h, MIN_EDITOR_HEIGHT)
                        self.screen = pygame.display.set_mode((w, h), pygame.RESIZABLE)
                        self.screen_size = (w, h)

                self._update_layout()
                self._status(f"Fullscreen: {'ON' if self.fullscreen else 'OFF'}", ACCENT, 2)
                return

    # ─────────────────────────────────────────────────────────────────────────
    # SHORTCUT HELPERS
    # ─────────────────────────────────────────────────────────────────────────

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
        elif ev.key in (pygame.K_BACKSPACE, pygame.K_DELETE):
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
        elif ev.key in (pygame.K_BACKSPACE, pygame.K_DELETE):
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
                effects = self.scene_data.get("effects", [])
                if 0 <= idx < len(effects):
                    effects[idx][key] = val
            elif owner == 'object':
                objs = self.scene_data.get("objects", [])
                idxs = self.selected_indices if len(self.selected_indices) > 1 else [idx]
                if key == 'grayscale_factor':
                    val = _clamp(float(val) / 100.0, 0.0, 1.0)
                # Coerce a int per campi tipicamente interi
                if key in ('x', 'y', 'rotation', 'alpha', 'layer_z',
                           'radius', 'width', 'height', 'mg_max_levels'):
                    val = int(val)
                for i in idxs:
                    if 0 <= i < len(objs):
                        if key == 'mg_max_levels':
                            if "minigame_trigger" in objs[i]:
                                objs[i]["minigame_trigger"]["max_levels"] = int(val)
                        else:
                            objs[i][key] = val
            self.scene_dirty = True
            self._mark_dirty()
            self._status(f"Impostato {key}: {val}", OK_C, 1)

        except ValueError:
            self._status("Errore: inserire un numero", ERR_C, 2)
        self._editing_prop = None
        self._prop_buf = ""

    def _escape(self):
        if self.mode == MODE_EFFECT_PLACE:
            self.mode = MODE_SELECT
            self.sel_effect_idx = None
        elif self._rect_placing or getattr(self, "_circle_placing", False):
            self._cancel_rect()
        elif getattr(self, "sel_effect_idx", None) is not None:
            self.sel_effect_idx = None
        elif self.selected_idx is not None:
            self.selected_idx = None
            self._mark_dirty()
        
        self._editing_prop = None
        self._editing_preset_name = False
        self._confirm_clear = False
        self._layer_dropdown_open = False

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
        
        # Ignora bottoni 4 e 5 (scroll legacy) per evitare selezioni accidentali
        if btn in (4, 5):
            return
            
        w, h = self.screen.get_size()

        # 1. STATUS BAR (In fondo, ma sopra tutto tranne tooltip)
        status_btn_r = (10, h - STATUS_H, 150, STATUS_H)
        if btn == 1 and _in_rect((mx, my_raw), status_btn_r):
            def back_to_gs():
                self.state    = STATE_GAME_SELECT
                self.gs_games = _discover_games(self.base_path)
            self._request_nav(back_to_gs)
            return

        if hasattr(self, "scene_path") and self.scene_path:
            save_btn_r = (170, h - STATUS_H, 120, STATUS_H)
            if btn == 1 and _in_rect((mx, my_raw), save_btn_r):
                self._with_loading(self._save); return
            play_btn_r = (300, h - STATUS_H, 120, STATUS_H)
            if btn == 1 and _in_rect((mx, my_raw), play_btn_r):
                self._playtest_scene(); return

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

            # Conferma uscita/salvataggio: priorità massima — sopra ogni altra modale
            if self._confirm_leave_modal:
                self._confirm_leave_click(mx, my_raw); return
            # Scatter modal
            if getattr(self, "_scatter_modal_open", False):
                if self._scatter_modal_click(mx, my_raw, w, h):
                    return
            if self._newobj_modal:
                self._newobj_click(mx, my_raw, w, h); return
            if self._tag_modal_active:
                self._tag_modal_click(mx, my_raw, w, h); return
            if self._lang_modal:
                self._lang_click(mx, my_raw, w, h); return
            if getattr(self, "_music_modal", False):
                self._music_modal_click(mx, my_raw, w, h); return
            if getattr(self, "_bg_modal", False):
                self._bg_modal_click(mx, my_raw, w, h); return
            if getattr(self, "_vid_modal", False):
                self._vid_modal_click(mx, my_raw, w, h); return
            if self._minigame_modal:
                self._minigame_click(mx, my_raw); return
            if getattr(self, "_stats_modal", False):
                self._stats_modal_click(mx, my_raw, w, h); return
            if getattr(self, "_icon_modal", False):
                if self._icon_click(mx, my_raw, w, h): return
            if self._img_editor_active:
                return 

            # Dashboard Modals (Nuovo, Modifica, Elimina) in primo piano
            if self.state == STATE_GAME_SELECT and (
                getattr(self, '_gs_del_mode', None) or 
                getattr(self, '_gs_new_mode', None) or 
                getattr(self, '_gs_edit_mode', None)
            ):
                self._gs_dblclick(mx, my_raw, w, h)
                self._gs_click(mx, my_raw)
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
            self._gs_dblclick(mx, my_raw, w, h)
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
            # Reset stati di ricerca/editing al click sul canvas
            self.catalog_searching = False
            self.catalog_tag_searching = False
            
            if btn == 1:
                if self._toolbar_click(mx, my_raw):
                    return
                self._canvas_ldown(mx, my_raw)
            elif btn in (2, 3):
                self._start_pan(mx, my_raw)
                self._pan_moved = False


    def _on_mup(self, ev):
        mx, my_raw = ev.pos
        if self.state == STATE_GAME_SELECT:
            self._gs_mup(mx, my_raw)

        if getattr(self, "_resizing_l", False) or getattr(self, "_resizing_r", False):
            if getattr(self, "_resizing_l", False):
                self._save_editor_setting("panel_l_w", self.panel_l_w)
            if getattr(self, "_resizing_r", False):
                self._save_editor_setting("panel_r_w", self.panel_r_w)
                
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
                # In anteprima niente context menu
                if getattr(self, "_preview_mode", False):
                    return
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
        
        if self.state == STATE_GAME_SELECT:
            self._gs_mmove(mx, my_raw); return

        if getattr(self, "_music_modal", False):
            self._music_modal_mmove(mx, my_raw, w, h); return

        # Brush zone vietate dello scatter: drag-paint col tasto sinistro.
        # Return solo mentre si dipinge: pan (tasto centrale/destro) resta attivo.
        if getattr(self, "_scatter_brush_active", False):
            if pygame.mouse.get_pressed(num_buttons=3)[0]:
                self._scatter_brush_motion(mx, my_raw)
                return

        # --- LOGICA RESIZE INTERATTIVO ---
        from editor.constants import PANEL_MIN_W, PANEL_MAX_W
        # Auto-heal: se il tasto sinistro non è più premuto (mouseup perso fuori
        # dalla finestra), annulla un resize pannello rimasto "appiccicato".
        if (getattr(self, "_resizing_l", False) or getattr(self, "_resizing_r", False)) \
                and not pygame.mouse.get_pressed(num_buttons=3)[0]:
            self._resizing_l = False
            self._resizing_r = False
        if getattr(self, "_resizing_l", False):
            self.panel_l_w = _clamp(mx, PANEL_MIN_W, PANEL_MAX_W)
            return
        if getattr(self, "_resizing_r", False):
            self.panel_r_w = _clamp(w - mx, PANEL_MIN_W, PANEL_MAX_W)
            return

        # --- AUTO-HEAL STATI "APPICCICATI" ---------------------------------
        # Riconcilia gli stati di trascinamento con i tasti realmente premuti.
        # Se un mouseup è andato perso (es. rilascio fuori dalla finestra), un
        # drag/pan poteva restare attivo facendo "seguire" gli oggetti al mouse
        # o spostandoli durante il pan col tasto destro. Qui lo annulliamo.
        pressed = pygame.mouse.get_pressed(num_buttons=3)
        if self._panning and not (pressed[1] or pressed[2]):
            self._panning = False
        if not pressed[0]:
            if (self._drag_active or self._handle_id or self._sel_box_active
                    or getattr(self, "_dragging_effect_idx", None) is not None
                    or getattr(self, "_dragging_slider", None)
                    or getattr(self, "_dragging_ctx_slider", None)
                    or getattr(self, "_dragging_catalog_scroll", False)):
                self._drag_active = False
                self._handle_id = None
                self._handle_snap = None
                self._dragging_effect_idx = None
                self._sel_box_active = False
                self._dragging_slider = None
                self._dragging_ctx_slider = None
                self._dragging_catalog_scroll = False

        # --- FEEDBACK CURSORE (Solo se NON stiamo già operando) ---
        # Disabilita se una modale è aperta (copre il canvas/pannelli)
        is_modal = (
            getattr(self, "_icon_modal", False) or 
            getattr(self, "_gs_edit_mode", None) is not None or
            getattr(self, "_newobj_modal", False) or
            getattr(self, "_tag_modal_active", False) or
            getattr(self, "_lang_modal", False) or
            getattr(self, "_music_modal", False) or
            getattr(self, "_bg_modal", False) or
            getattr(self, "_vid_modal", False)
        )
        
        if not is_modal and not self._panning and not self._handle_id and not self._drag_active:
            # 1. Bordi pannelli
            EDGE = 10
            near_l = abs(mx - self.panel_l_w) <= EDGE and self.panels_visible
            near_r = abs(mx - (w - self.panel_r_w)) <= EDGE and self.panels_visible
            
            if near_l or near_r:
                pygame.mouse.set_cursor(pygame.SYSTEM_CURSOR_SIZEWE)
            else:
                has_cursor_override = False
                # 2. Handles oggetti
                if self.selected_idx is not None:
                    objs = self.scene_data.get("objects", [])
                    if self.selected_idx < len(objs):
                        obj = objs[self.selected_idx]
                        from editor.constants import HANDLE_R
                        for hid, hx, hy in self._obj_handles(obj):
                            if math.hypot(mx - hx, my_raw - hy) <= HANDLE_R + 3:
                                cursor_map = {
                                    "nw": pygame.SYSTEM_CURSOR_SIZENWSE, "se": pygame.SYSTEM_CURSOR_SIZENWSE,
                                    "ne": pygame.SYSTEM_CURSOR_SIZENESW, "sw": pygame.SYSTEM_CURSOR_SIZENESW,
                                    "n":  pygame.SYSTEM_CURSOR_SIZENS,   "s":  pygame.SYSTEM_CURSOR_SIZENS,
                                    "e":  pygame.SYSTEM_CURSOR_SIZEWE,   "w":  pygame.SYSTEM_CURSOR_SIZEWE,
                                    "rot": pygame.SYSTEM_CURSOR_HAND,    "move": pygame.SYSTEM_CURSOR_SIZEALL
                                }
                                pygame.mouse.set_cursor(cursor_map.get(hid, pygame.SYSTEM_CURSOR_CROSSHAIR))
                                has_cursor_override = True
                                break

                # 3. Handles effetti (se non già gestito da oggetti)
                if not has_cursor_override:
                    sel_fx = getattr(self, "sel_effect_idx", None)
                    if sel_fx is not None:
                        effects = self.scene_data.get("effects", [])
                        if sel_fx < len(effects):
                            from editor.constants import HANDLE_R
                            for hid, hx, hy in self._fx_handles(effects[sel_fx]):
                                if math.hypot(mx - hx, my_raw - hy) <= HANDLE_R + 3:
                                    if hid == "move": pygame.mouse.set_cursor(pygame.SYSTEM_CURSOR_SIZEALL)
                                    else: pygame.mouse.set_cursor(pygame.SYSTEM_CURSOR_HAND)
                                    has_cursor_override = True
                                    break
                
                if not has_cursor_override:
                    pygame.mouse.set_cursor(pygame.SYSTEM_CURSOR_ARROW)

        # --- LOGICA DI MOVIMENTO (Sempre eseguita se gli stati sono attivi) ---
        if self._panning:
            dx = mx     - self._pan_start_mx
            dy = my_raw - self._pan_start_my
            if abs(dx) > 3 or abs(dy) > 3:
                self._pan_moved = True
            self.origin_x = self._pan_start_ox + dx
            self.origin_y = self._pan_start_oy + dy
            # Il pan sposta l'origine: invalida la cache statica del canvas
            # (grid + background + overlay oggetti) così segue il movimento,
            # altrimenti restavano fermi mentre solo gli overlay live scorrevano.
            self._mark_dirty()
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
            is_fx = (getattr(self, "_lang_context", "global") == "fx")
            if is_fx: return
            
            # Calcolo dinamico righe visibili in base al nuovo layout (HEADER_H=118, Footer=48)
            dh = int(h * 0.88)
            visible_h = dh - 118 - 48
            visible_rows = max(1, visible_h // 28)
            
            keys_to_scroll = getattr(self, "_lang_filtered_keys", self._lang_keys)
            max_scroll = max(0, len(keys_to_scroll) - visible_rows)
            self._lang_scroll = _clamp(self._lang_scroll - ev.y, 0, max_scroll)
            return

        if self._tag_modal_active:
            self._tag_modal_scroll = _clamp(self._tag_modal_scroll - ev.y, 0, getattr(self, "_tag_modal_max_scroll", 0))
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

        if getattr(self, "_stats_modal", False):
            self._stats_modal_wheel(ev)
            return

        if getattr(self, "_scatter_modal_open", False):
            if self._scatter_modal_wheel(mx, my_raw, ev.y):
                return

        if self.state == STATE_GAME_SELECT:
            self._gs_wheel(ev); return

        cr = self._canvas_rect()

        # PRIORITÀ CANVAS: Se siamo sul canvas, gestiamo prima Panning e Zoom
        if _in_rect((mx, my_raw), cr):
            # Se stiamo modificando il raggio di un cerchio con ALT
            if self.selected_idx is not None and self.mode == MODE_SELECT:
                obj = self.scene_data["objects"][self.selected_idx]
                if obj.get("detection_type") == "circle" and (mods & pygame.KMOD_ALT):
                    delta = 5 if (mods & pygame.KMOD_SHIFT) else 1
                    delta *= (1 if ev.y > 0 else -1)
                    # Coalescing: la raffica di wheel produce un solo snapshot
                    self._push_undo("Modifica raggio", coalesce_key="radius_wheel")
                    obj["radius"] = max(5, obj.get("radius", 30) + delta)
                    return

            # Zoom con CTRL
            if mods & pygame.KMOD_CTRL:
                factor = 1.15 if ev.y > 0 else (1/1.15)
                self._zoom_toward(mx, my_raw, factor)
                return
            
            # Pan orizzontale con SHIFT
            if mods & pygame.KMOD_SHIFT:
                self.origin_x += ev.y * 80
            # Pan verticale standard
            else:
                self.origin_y += ev.y * 80
            
            self._mark_dirty()
            return

        # LOGICA PANNELLI (Se non siamo sul canvas)
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
                    list_y_start = 58
                    add_btn_h = 32
                    available_h = self.screen_size[1] - STATUS_H - list_y_start - add_btn_h
                    visible_items = available_h // (64 + 2)
                    max_scr = max(0, len(getattr(self, "effects_catalog", [])) - visible_items)
                    self.effects_catalog_scroll = _clamp(
                        self.effects_catalog_scroll - ev.y, 0, max_scr)
                else:
                    # Scroll Albero Scena
                    self.tree_scroll = _clamp(self.tree_scroll - ev.y, 0, 100)
                return
            
            if mx > w - self.panel_r_w:
                # Scroll pannello proprietà (in pixel)
                self.prop_scroll = max(0, self.prop_scroll - ev.y * 30)
                return

    # ─────────────────────────────────────────────────────────────────────────
    # PAN / ZOOM
    # ─────────────────────────────────────────────────────────────────────────

    def _start_pan(self, mx, my):
        # Entrando in pan annulliamo qualsiasi drag/handle armato: il pan (tasto
        # destro/centrale) non deve mai spostare oggetti o effetti.
        self._drag_active = False
        self._handle_id = None
        self._handle_snap = None
        self._dragging_effect_idx = None
        self._sel_box_active = False
        self._snap_guides  = []
        self._panning      = True
        self._pan_start_mx = mx
        self._pan_start_my = my
        self._pan_start_ox = self.origin_x
        self._pan_start_oy = self.origin_y

    # ─────────────────────────────────────────────────────────────────────────
    # CANVAS MOUSE
    # ─────────────────────────────────────────────────────────────────────────

    def _canvas_ldown(self, mx, my_raw):
        # In anteprima il canvas non e' editabile
        if getattr(self, "_preview_mode", False):
            return
        # Reset stati pendenti del panel destro (es: conferma svuota scena)
        if getattr(self, "_confirm_clear", False):
            self._confirm_clear = False
        if getattr(self, "_layer_dropdown_open", False):
            self._layer_dropdown_open = False

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
            effects = self.scene_data.get("effects", [])
            if sel_fx_idx is not None and 0 <= sel_fx_idx < len(effects):
                fx = effects[sel_fx_idx]
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
                            self._handle_id = "fx_radius"
                            self._handle_snap = copy.copy(fx)
                            self._drag_start_mx = mx
                            self._drag_start_my = my_raw
                            logging.info(f"[FX_RESIZE] Start dragging radius for {fx.get('effect_id', '?')}")
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
            self._snap_guides = []
            self._mark_dirty()
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
            self._editing_prop = None # Reset editing se stiamo selezionando un nuovo oggetto
            
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
            self._mark_dirty()
        else:
            # Inizio Box Selection
            self._sel_box_active = True
            self._sel_box_start  = self._s2r(mx, my_raw)
            self._sel_box_cur    = self._s2r(mx, my_raw)
            if not (mods & pygame.KMOD_SHIFT):
                self.selected_idx    = None
                self.selected_indices = []
            self._tab_cycle_hits = []
            self._mark_dirty()

    def _tab_cycle(self):
        if len(self._tab_cycle_hits) < 2:
            return
        self._tab_cycle_pos = (self._tab_cycle_pos + 1) % len(self._tab_cycle_hits)
        self.selected_idx   = self._tab_cycle_hits[self._tab_cycle_pos]
        self.r_tab = TAB_PROPS
        # La cache statica del canvas salta gli oggetti selezionati: cambiando
        # selezione va invalidata, altrimenti il precedente oggetto deselezionato
        # sparisce dal canvas (assente sia dalla cache che dal passaggio dinamico).
        self._mark_dirty()


    # ─────────────────────────────────────────────────────────────────────────
    # DRAG / HANDLE
    # ─────────────────────────────────────────────────────────────────────────

    def _nudge_sel(self, dx: int, dy: int) -> bool:
        """Sposta la selezione di (dx, dy) px scena. Ritorna False se non c'e'
        selezione. Snapshot undo coalescente: pressioni ravvicinate = un solo undo."""
        objs = (self.scene_data or {}).get("objects", [])
        idxs = [i for i in self.selected_indices if 0 <= i < len(objs)]
        if (self.selected_idx is not None and self.selected_idx not in idxs
                and 0 <= self.selected_idx < len(objs)):
            idxs.append(self.selected_idx)
        if not idxs:
            return False
        now = time.time()
        if now - getattr(self, "_last_nudge_ts", 0.0) > NUDGE_UNDO_GAP_S:
            self._push_undo()
        self._last_nudge_ts = now
        for i in idxs:
            obj = objs[i]
            obj["x"] = round(obj.get("x", 0) + dx)
            obj["y"] = round(obj.get("y", 0) + dy)
        self.scene_dirty = True
        self._mark_dirty()
        return True

    def _obj_snap_offset(self, dx: float, dy: float) -> tuple:
        """Correzione di snap del drag verso bordi/centri degli altri oggetti.

        Usa l'oggetto guida (selected_idx se nel gruppo, altrimenti il primo)
        alla posizione proposta e cerca il bordo/centro piu' vicino tra gli
        oggetti visibili fuori dal gruppo. Ritorna (snap_dx | None, snap_dy | None)
        e aggiorna self._snap_guides per il rendering delle guide.
        """
        self._snap_guides = []
        if not getattr(self, "obj_snap", True):
            return None, None
        objs = (self.scene_data or {}).get("objects", [])
        group = self._drag_group_starts
        if not group:
            return None, None
        lead = self.selected_idx if self.selected_idx in group else next(iter(group))
        if not (0 <= lead < len(objs)):
            return None, None
        base_x, base_y = group[lead]
        tmp = dict(objs[lead])
        tmp["x"] = base_x + dx
        tmp["y"] = base_y + dy
        lx_min, ly_min, lx_max, ly_max = self._get_obj_bbox(tmp)
        lead_xs = (lx_min, (lx_min + lx_max) / 2, lx_max)
        lead_ys = (ly_min, (ly_min + ly_max) / 2, ly_max)
        thr = OBJ_SNAP_PX / max(self.zoom, 1e-6)
        best_dx = best_dy = None
        best_ax = best_ay = thr
        guide_v = guide_h = None
        for j, other in enumerate(objs):
            if j in group:
                continue
            if not self.layer_vis.get(other.get("layer", "objects_mid"), True):
                continue
            bx_min, by_min, bx_max, by_max = self._get_obj_bbox(other)
            for tx in (bx_min, (bx_min + bx_max) / 2, bx_max):
                for lx in lead_xs:
                    d = tx - lx
                    if abs(d) < best_ax:
                        best_ax, best_dx, guide_v = abs(d), d, tx
            for ty in (by_min, (by_min + by_max) / 2, by_max):
                for ly in lead_ys:
                    d = ty - ly
                    if abs(d) < best_ay:
                        best_ay, best_dy, guide_h = abs(d), d, ty
        if best_dx is not None:
            self._snap_guides.append(("v", guide_v))
        if best_dy is not None:
            self._snap_guides.append(("h", guide_h))
        return best_dx, best_dy

    def _do_drag(self, mx, my):
        dx  = (mx - self._drag_start_mx) / self.zoom
        dy  = (my - self._drag_start_my) / self.zoom

        # Lo snap a oggetti, se aggancia, prevale sullo snap a griglia
        snap_dx, snap_dy = self._obj_snap_offset(dx, dy)
        for idx, (base_x, base_y) in self._drag_group_starts.items():
            obj = self.scene_data["objects"][idx]
            nx, ny = base_x + dx, base_y + dy
            obj["x"] = round(nx + snap_dx) if snap_dx is not None else self._snap(nx)
            obj["y"] = round(ny + snap_dy) if snap_dy is not None else self._snap(ny)
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
            # L'area del testo è centrata orizzontalmente rispetto a x.
            # Quindi |rx - ox| è metà larghezza.
            if "w" in hid or "e" in hid:
                res_w = abs(rx - ox) * 2
            
            # L'area del testo è sopra y con un offset di 35px.
            # Quindi (oy - ry) - 35 è l'altezza.
            if "n" in hid:
                res_h = (oy - ry) - 35
            
            # Applichiamo i limiti e lo snap
            fx["width"]  = max(40, self._snap(res_w))
            fx["height"] = max(30, self._snap(res_h))
            self.scene_dirty = True
            return

        if h == "fx_radius":
            fx_idx = getattr(self, "sel_effect_idx", None)
            if fx_idx is None: return
            fx = self.scene_data["effects"][fx_idx]
            rx, ry = self._s2r(mx, my)
            # Calcolo raggio come distanza euclidea tra mouse e centro effetto
            new_r = math.hypot(rx - fx["x"], ry - fx["y"])
            fx["radius"] = max(5.0, self._snap(new_r))
            
            if pygame.time.get_ticks() % 10 == 0: # Log limitato per non floodare
                logging.info(f"[FX_RESIZE] New Radius: {fx['radius']:.1f} (mx:{mx}, my:{my})")
            
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
                f"Dimensione max raggiunta ({MAX_DIM}px) - evita artefatti",
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
        # Reset stati pendenti del panel destro
        if getattr(self, "_confirm_clear", False):
            self._confirm_clear = False
        if getattr(self, "_layer_dropdown_open", False):
            self._layer_dropdown_open = False
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
                    # Altezza aumentata a 46-50 per matchare il rendering
                    r2 = (24, y, self.panel_l_w - 40, 46)
                    if _in_rect((mx, my), r2):
                        self._request_nav(lambda: self._load_scene(sdir)); return
                    y += 50

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

        # 2.5 Style Filter (NUOVO Dropdown)
        sel_r = getattr(self, "_catalog_style_sel_rect", None)
        if sel_r and _in_rect((mx, my_raw), sel_r):
            logging.info("  [CATALOG] HIT: Style Dropdown Toggle")
            self.catalog_style_open = not getattr(self, "catalog_style_open", False)
            self._play_click(); return
            
        if getattr(self, "catalog_style_open", False):
            opt_rects = getattr(self, "_catalog_style_opt_rects", [])
            for s_id, opt_r in opt_rects:
                if _in_rect((mx, my_raw), opt_r):
                    logging.info(f"  [CATALOG] HIT: Style Option '{s_id}'")
                    self.catalog_style_filter = s_id
                    self.catalog_style_open = False
                    self.catalog_tag_filters = set()
                    self.catalog_tag_search = ""
                    self.catalog_scroll = 0
                    self.catalog_tags_scroll = 0
                    self._status(f"Filtro: {s_id.upper()}", ACCENT, 1)
                    self._play_click(); return

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
                    self._mark_dirty()
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

            # 3. Rotazione Automatica Toggle
            if _in_rect((mx, my), hboxes.get("auto_btn", pygame.Rect(0,0,0,0))):
                self._push_undo()
                val = not self.scene_data.get("auto_random_finds", False)
                self.scene_data["auto_random_finds"] = val
                self.scene_dirty = True
                self._mark_dirty()
                self._status(f"Rotazione auto: {'ON' if val else 'OFF'}", OK_C, 2)
                return

            # 3.5 Selezione Layer Casuale Toggle
            if _in_rect((mx, my), hboxes.get("rand_l_btn", pygame.Rect(0,0,0,0))):
                self._push_undo()
                val = not self.scene_data.get("random_layer_selection", False)
                self.scene_data["random_layer_selection"] = val
                self.scene_dirty = True
                self._mark_dirty()
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
                    self._mark_dirty()
                    self._dragging_slider = ('scene', 0, 'num_random_finds', 1, max_obj, nr_sl.x, nr_sl.w)
                    return

            # 5. Modifica Traduzioni
            if _in_rect((mx, my), hboxes.get("lang_btn", pygame.Rect(0,0,0,0))):
                self._lang_modal = False if self._lang_modal else None
                if not self._lang_modal: self._lang_open()
                return

            # 6. Icone Canvas Toggle
            if _in_rect((mx, my), hboxes.get("ico_btn", pygame.Rect(0,0,0,0))):
                self.show_icons = not self.show_icons
                self._mark_dirty()
                return

            # 7. Torcia Toggle
            if _in_rect((mx, my), hboxes.get("fl_btn", pygame.Rect(0,0,0,0))):
                self._push_undo()
                val = not self.scene_data.get("flashlight", False)
                self.scene_data["flashlight"] = val
                self.scene_dirty = True
                self._mark_dirty()
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
                    self._mark_dirty()
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
                self._mark_dirty()
                self._status("Musiche della scena rimosse", WARN_C, 3)
                return
            # Rimozione singola traccia (cliccando ×)
            for hb_key, hb_r in list(hboxes.items()):
                if hb_key.startswith("mus_del_") and _in_rect((mx, my), hb_r):
                    try:
                        track_idx = int(hb_key[len("mus_del_"):])
                    except ValueError:
                        continue
                    music = self.scene_data.get("music", [])
                    if 0 <= track_idx < len(music):
                        self._push_undo()
                        removed = music.pop(track_idx)
                        self.scene_dirty = True
                        self._mark_dirty()
                        self._status(f"Rimossa: {removed}", WARN_C, 2)
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

        # Recupero oggetti selezionati
        idxs = self.selected_indices if len(self.selected_indices) > 1 else [self.selected_idx]
        objs_sel = [self.scene_data["objects"][i] for i in idxs if i < len(self.scene_data["objects"])]
        if not objs_sel: return
        obj = objs_sel[0] # Riferimento (primo oggetto)

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

        # Obiettivo Fisso (Toggle)
        always_r = hboxes.get("always_btn")
        if always_r and _in_rect((rx, my), always_r):
            self._push_undo()
            new_val = not obj.get("always_show", False)
            for o in objs_sel:
                o["always_show"] = new_val
            self.scene_dirty = True
            self._mark_dirty()
            return


        # Goal Toggle
        goal_r = hboxes.get("goal_btn")
        if goal_r and _in_rect((rx, my), goal_r):
            self._push_undo()
            new_val = not obj.get("is_goal", True)
            for o in objs_sel:
                o["is_goal"] = new_val
            self.scene_dirty = True
            self._mark_dirty()
            return

        # Hide / Lock toggle (editor-only)
        if _in_rect((rx, my), hboxes.get("hide_btn", pygame.Rect(0,0,0,0))):
            self._push_undo()
            new_val = not all(o.get("editor_hidden", False) for o in objs_sel)
            for o in objs_sel: o["editor_hidden"] = new_val
            self.scene_dirty = True; self._mark_dirty()
            self._status(f"Hide editor: {'ON' if new_val else 'OFF'}", WARN_C, 2)
            return
        if _in_rect((rx, my), hboxes.get("lock_btn", pygame.Rect(0,0,0,0))):
            self._push_undo()
            new_val = not all(o.get("editor_locked", False) for o in objs_sel)
            for o in objs_sel: o["editor_locked"] = new_val
            self.scene_dirty = True; self._mark_dirty()
            self._status(f"Lock editor: {'ON' if new_val else 'OFF'}", ERR_C, 2)
            return

        # Reset transform / reset tint
        if _in_rect((rx, my), hboxes.get("reset_transform_btn", pygame.Rect(0,0,0,0))):
            self._reset_transform_for_selection(); return
        if _in_rect((rx, my), hboxes.get("tint_reset_btn", pygame.Rect(0,0,0,0))):
            self._reset_tint_for_selection(); return

        # Multi-sel: Align / Distribute / Copy props
        for aid in ("left","right","top","bottom","h_center","v_center"):
            if _in_rect((rx, my), hboxes.get(f"align_{aid}", pygame.Rect(0,0,0,0))):
                self._align_selection(aid); return
        if _in_rect((rx, my), hboxes.get("distr_h", pygame.Rect(0,0,0,0))):
            self._distribute_selection("h"); return
        if _in_rect((rx, my), hboxes.get("distr_v", pygame.Rect(0,0,0,0))):
            self._distribute_selection("v"); return
        if _in_rect((rx, my), hboxes.get("copy_props_btn", pygame.Rect(0,0,0,0))):
            self._copy_props_from_primary(transform=True, visual=True, gameplay=False); return

        # Hit-detection type selector
        if _in_rect((rx, my), hboxes.get("hit_type_circle", pygame.Rect(0,0,0,0))):
            self._push_undo()
            obj["detection_type"] = "circle"
            if "radius" not in obj or obj.get("radius", 0) <= 0:
                obj["radius"] = max(30, int(min(obj.get("width", 60), obj.get("height", 60)) / 2))
            self.scene_dirty = True; self._mark_dirty(); return
        if _in_rect((rx, my), hboxes.get("hit_type_rect", pygame.Rect(0,0,0,0))):
            self._push_undo()
            obj["detection_type"] = "rect"
            if obj.get("width", 0) <= 0: obj["width"] = obj.get("radius", 30) * 2
            if obj.get("height", 0) <= 0: obj["height"] = obj.get("radius", 30) * 2
            self.scene_dirty = True; self._mark_dirty(); return

        # Warp toggle
        if _in_rect((rx, my), hboxes.get("warp_toggle", pygame.Rect(0,0,0,0))):
            self._push_undo()
            coff = obj.get("corners", [[0,0],[0,0],[0,0],[0,0]])
            has_warp = any(c[0] != 0 or c[1] != 0 for c in coff)
            if has_warp:
                obj["corners"] = [[0,0],[0,0],[0,0],[0,0]]
                self._status("Warp mesh disattivato", FX_C, 2)
            else:
                # Inizializzo piccolo offset per rendere visibili le maniglie
                obj["corners"] = [[-8,-8],[8,-8],[8,8],[-8,8]]
                self._status("Warp mesh attivato — trascina gli angoli", FX_C, 3)
            self.scene_dirty = True; self._mark_dirty(); return

        # --- LOGICA SLIDERS & BOXES PER OGGETTI (BATCH) ---
        # Range slider X/Y: dimensioni reali del BG se disponibili (allineato al render)
        bg_surf = getattr(self, "bg_surf", None)
        if bg_surf is not None:
            try:
                _x_max, _y_max = bg_surf.get_size()
            except Exception:
                _x_max, _y_max = REF_W, REF_H
        else:
            _x_max, _y_max = REF_W, REF_H

        keys = ["x", "y", "scale", "rotation", "alpha",
                "layer_z", "radius", "width", "height", "grayscale_factor"]
        fmts = {"scale": "{:.2f}", "x": "{:.0f}", "y": "{:.0f}",
                "rotation": "{:.0f}", "alpha": "{:.0f}",
                "layer_z": "{:.0f}", "radius": "{:.0f}",
                "width": "{:.0f}", "height": "{:.0f}",
                "grayscale_factor": "{:.2f}"}
        mins = {"x": 0, "y": 0, "scale": 0.1, "rotation": 0, "alpha": 0,
                "layer_z": 0, "radius": 5, "width": 5, "height": 5, "grayscale_factor": 0.0}
        maxs = {"x": _x_max, "y": _y_max, "scale": 3.0, "rotation": 360, "alpha": 255,
                "layer_z": 100, "radius": 500, "width": 1000, "height": 1000, "grayscale_factor": 1.0}
        int_keys = {"x", "y", "rotation", "alpha", "layer_z", "radius", "width", "height"}

        for k in keys:
            br = hboxes.get(f"box_{k}")
            if br and _in_rect((rx, my), br):
                self._editing_prop = ('object', self.selected_idx, k)
                if k == "grayscale_factor":
                    self._prop_buf = str(int(round(obj.get(k, 1.0) * 100)))
                elif k == "layer_z":
                    from editor.constants import layer_z as _lzd
                    lz = obj.get("layer_z")
                    self._prop_buf = str(int(lz) if lz is not None else _lzd(obj.get("layer", "objects_mid")))
                else:
                    val = obj.get(k, 0)
                    self._prop_buf = fmts[k].format(val)
                return

            sr = hboxes.get(f"slider_{k}")
            if sr and _in_rect((rx, my), sr):
                self._push_undo()
                mn, mx_v = mins[k], maxs[k]
                ratio = _clamp((rx - sr.x) / sr.w, 0.0, 1.0)
                val = mn + ratio * (mx_v - mn)
                if k in int_keys: val = int(val)
                else: val = round(val, 2)

                for o in objs_sel:
                    o[k] = val

                self.scene_dirty = True
                self._mark_dirty()
                self._dragging_slider = ('object', self.selected_idx, k, mn, mx_v, sr.x, sr.w)
                return

        # Opzioni Visive (Flip / Grayscale)
        if _in_rect((rx, my), hboxes.get("flip_h", pygame.Rect(0,0,0,0))):
            self._push_undo()
            nv = not obj.get("flip_x", False)
            for o in objs_sel: o["flip_x"] = nv
            self.scene_dirty = True; self._mark_dirty(); return
        
        if _in_rect((rx, my), hboxes.get("flip_v", pygame.Rect(0,0,0,0))):
            self._push_undo()
            nv = not obj.get("flip_y", False)
            for o in objs_sel: o["flip_y"] = nv
            self.scene_dirty = True; self._mark_dirty(); return

        if _in_rect((rx, my), hboxes.get("grayscale", pygame.Rect(0,0,0,0))):
            self._push_undo()
            nv = not obj.get("grayscale", False)
            for o in objs_sel: o["grayscale"] = nv
            self.scene_dirty = True; self._mark_dirty(); return
        
        if _in_rect((rx, my), hboxes.get("tint_color", pygame.Rect(0,0,0,0))):
            self._pick_color_for_selection(objs_sel); return

        # Layer Selection (dropdown)
        if _in_rect((rx, my), hboxes.get("layer_sel", pygame.Rect(0,0,0,0))):
            self._layer_dropdown_open = not getattr(self, "_layer_dropdown_open", False)
            return

        if getattr(self, "_layer_dropdown_open", False):
            for k, hr in hboxes.items():
                if k.startswith("layer_opt_") and _in_rect((rx, my), hr):
                    lid = k[len("layer_opt_"):]
                    self._push_undo()
                    for o in objs_sel:
                        o["layer"] = lid
                    self.scene_dirty = True
                    self._mark_dirty()
                    self._layer_dropdown_open = False
                    self._status(f"Layer: {lid.replace('objects_','').upper()}", ACCENT, 2)
                    return
            # Click fuori dalle opzioni e fuori dal bottone → chiudi
            self._layer_dropdown_open = False

        # Minigame Trigger (Solo se singola selezione o non implementato batch per ora)
        mg_btn = hboxes.get("minigame_btn")
        if mg_btn and _in_rect((rx, my), mg_btn):
            self._minigame_open(); return
            
        mg_clr = hboxes.get("minigame_clear_btn")
        if mg_clr and _in_rect((rx, my), mg_clr):
            self._push_undo()
            if "minigame_trigger" in obj:
                del obj["minigame_trigger"]
            self.scene_dirty = True
            self._mark_dirty()
            self._status("Trigger minigioco rimosso.", WARN_C, 2)
            return

        # --- LOGICA LIVELLI MINIGIOCO (Spot Differences) ---
        ml_box = hboxes.get("mg_levels_box")
        if ml_box and _in_rect((rx, my), ml_box):
            self._editing_prop = ('object', self.selected_idx, 'mg_max_levels')
            self._prop_buf = str(obj.get("minigame_trigger", {}).get("max_levels", 5))
            return
            
        ml_slider = hboxes.get("mg_levels_slider")
        if ml_slider and _in_rect((rx, my), ml_slider):
            self._push_undo()
            ratio = _clamp((rx - ml_slider.x) / ml_slider.w, 0.0, 1.0)
            val = int(1 + ratio * 14) # 1 a 15
            if "minigame_trigger" in obj:
                obj["minigame_trigger"]["max_levels"] = val
            self.scene_dirty = True; self._mark_dirty()
            self._dragging_slider = ('object', self.selected_idx, 'mg_max_levels', 1, 15, ml_slider.x, ml_slider.w)
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
                # Forza visibilità layer effetti
                if not self.layer_vis.get("effects", True):
                    self.layer_vis["effects"] = True
                    self._status(f"Piazza effetto: {fx_id} (Layer attivato)", FX_C, 2)
                else:
                    self._status(f"Piazza effetto: {fx_id}", FX_C, 2)
                
                self.selected_idx = None
                self.selected_indices = []
                self.sel_effect_idx = None
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
                        self._mark_dirty()
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
                    self.scene_dirty = True; self._mark_dirty(); return

            if _in_rect((rx, my), hboxes.get("color_body", pygame.Rect(0,0,0,0))):
                self._pick_color_for_effect(idx, "color", "Colore Corpo"); return
            if _in_rect((rx, my), hboxes.get("color_font", pygame.Rect(0,0,0,0))):
                self._pick_color_for_effect(idx, "font_color", "Colore Testo"); return

        else:
            # --- LOGICA EFFETTI STANDARD ---
            if _in_rect((rx, my), hboxes.get("color_effect", pygame.Rect(0,0,0,0))):
                self._pick_color_for_effect(idx); return

        # --- POSIZIONE X / Y (solo box, no slider) ---
        for pkey in ("x", "y"):
            br_xy = hboxes.get(f"box_{pkey}")
            if br_xy and _in_rect((rx, my), br_xy):
                self._editing_prop = ('effect', idx, pkey)
                self._prop_buf = str(round(fx.get(pkey, 0)))
                return

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
                self._mark_dirty()
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
            self.scene_dirty = True; self._mark_dirty(); return

        if _in_rect((rx, my), hboxes.get("del_btn", pygame.Rect(0,0,0,0))):
            self._push_undo()
            # Rimuove la chiave dal file lingua se è un bubble_tip
            if fx.get("type") == "bubble_tip":
                tkey = fx.get("text_key", "")
                if tkey and tkey.startswith("TIP_"):
                    self._cleanup_translation_key(tkey)
            self.scene_data["effects"].pop(idx)
            self.sel_effect_idx = None
            self.scene_dirty = True; self._mark_dirty(); return

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
        self._mark_dirty()
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
                self._mark_dirty()
                return True
        return False

    def _do_drag_effect(self, mx, my):
        idx = getattr(self, "_dragging_effect_idx", None)
        if idx is None: return
        dx = (mx - self._drag_start_mx) / self.zoom
        dy = (my - self._drag_start_my) / self.zoom
        effects = self.scene_data.get("effects", [])
        if 0 <= idx < len(effects):
            fx = effects[idx]
            fx["x"] = self._snap(self._drag_start_x + dx)
            fx["y"] = self._snap(self._drag_start_y + dy)
            self.scene_dirty = True
            self._mark_dirty()

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
            effects = self.scene_data.get("effects", [])
            if 0 <= idx < len(effects):
                fx = effects[idx]
                if key == "radius" and fx.get("type") == "smoke":
                    val = round(val * 5) / 5.0
                fx[key] = val
        elif owner == 'object':
            objs = self.scene_data.get("objects", [])
            idxs = self.selected_indices if len(self.selected_indices) > 1 else [idx]
            for i in idxs:
                if 0 <= i < len(objs):
                    if key == 'mg_max_levels':
                        if "minigame_trigger" in objs[i]:
                            objs[i]["minigame_trigger"]["max_levels"] = int(val)
                    else:
                        objs[i][key] = val
        elif owner == 'scene':
            self.scene_data[key] = val
        
        self.scene_dirty = True
        self._mark_dirty()
        return True

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
                    # Comandi che richiedono conferma se dirty
                    if cmd in ("file_new_game", "file_open_game", "file_exit_to_gs", "file_quit"):
                        self._request_nav(cmd)
                    else:
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
        elif cmd == "edit_preset_save": self._preset_open_save()
        elif cmd == "edit_preset_insert": self._preset_open_insert()
        
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
        
        # STATISTICHE SCENA
        elif cmd == "file_scene_stats":
            self._stats_open()

        # IMPORT BATCH OGGETTI
        elif cmd == "file_batch_import":
            self._batch_import_open()

        # AUDITOR
        elif cmd == "file_auditor":
            game_id = ""
            if self.gs_sel_game is not None and self.gs_sel_game < len(self.gs_games):
                game_id = self.gs_games[self.gs_sel_game]
            elif getattr(self, "game_path", None):
                game_id = self.game_path.name
            self._auditor_open(game_id)

    def _request_nav(self, action):
        """Intercetta azioni di navigazione per controllare se ci sono modifiche non salvate."""
        if not getattr(self, "scene_dirty", False):
            # Se la scena non è sporca, eseguiamo subito con overlay
            if callable(action):
                self._with_loading(action)
            else:
                self._with_loading(self._exec_menu_cmd, action)
            return

        self._confirm_leave_modal = True
        self._pending_action = action

    def _confirm_leave_click(self, mx, my):
        """Gestisce i click sul modale di conferma salvataggio."""
        hboxes = getattr(self, "_leave_modal_hitboxes", {})
        if not hboxes: return

        if _in_rect((mx, my), hboxes.get("save")):
            # Salvataggio + Azione pendente (tutto sotto overlay)
            def _save_and_nav():
                self._save()
                if callable(self._pending_action): 
                    self._pending_action()
                else: 
                    self._exec_menu_cmd(self._pending_action)
            
            self._confirm_leave_modal = False
            self._with_loading(_save_and_nav)
            self._pending_action = None
            
        elif _in_rect((mx, my), hboxes.get("discard")):
            self.scene_dirty = False # Forza pulizia per evitare loop
            self._confirm_leave_modal = False
            
            if callable(self._pending_action):
                self._with_loading(self._pending_action)
            else:
                self._with_loading(self._exec_menu_cmd, self._pending_action)
            
            self._pending_action = None
        elif _in_rect((mx, my), hboxes.get("cancel")):
            self._confirm_leave_modal = False
            self._pending_action = None
