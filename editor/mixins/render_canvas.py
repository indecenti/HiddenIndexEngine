"""
editor/mixins/render_canvas.py

RenderCanvasMixin — disegno canvas: griglia, background, overlay oggetti,
                    placement preview, toolbar.
"""

import math
import pygame

from editor.constants import (
    MODE_SELECT, MODE_CIRCLE, MODE_RECT, MODE_EFFECT_PLACE, MODE_SCATTER,
    ACCENT, BORDER, CANVAS, GRID_C, SEL_C, FX_C, ERR_C,
    TXT, TXT_DIM, TXT_HI, OK_C, WARN_C, ALWAYS_C, BTN_AC, BTN_HO, STATUS,
    HANDLE_R, REF_W, REF_H,
    layer_color,
)
from editor.ui.draw import _txt, _draw_text, _rect, _button, _in_rect, _text_wh, _draw_shape_icon
from engine.utils import warp_surface, apply_grayscale
from engine.effect_renderer import (
    draw_smoke_effect, draw_flies_effect, draw_glint_effect, 
    draw_bubble_tip_effect, update_effect_state
)


class RenderCanvasMixin:
    """Rendering del canvas centrale e della toolbar."""

    # ─────────────────────────────────────────────────────────────────────────
    # CANVAS
    # ─────────────────────────────────────────────────────────────────────────

    def _r_canvas(self, w, h):
        cr = self._canvas_rect()
        _rect(self.screen, CANVAS, cr)
        self.screen.set_clip(cr)

        if self.show_grid:
            self._r_grid(cr)

        self._r_background(cr)
        self._r_overlays()

        self._r_effect_overlays()

        if self._rect_placing and self.mode == MODE_RECT:
            self._r_placing_rect()
        if self._circle_placing and self.mode == MODE_CIRCLE:
            self._r_placing_circle()
        if self.mode == MODE_CIRCLE:
            self._r_circle_cursor(cr)
        if self.mode == MODE_EFFECT_PLACE:
            self._r_effect_place_cursor(cr)
        if self.mode == MODE_SCATTER:
            self._r_scatter_cursor(cr)
        
        if self._sel_box_active:
            self._r_selection_box()

        self.screen.set_clip(None)
        _rect(self.screen, BORDER, cr, 1)
        self._r_drag_tooltip()  # coordinate live durante drag/resize

        # Scrollbar visuali
        if self.bg_surf:
            bw, bh = self.bg_surf.get_size()
            vw, vh = bw * self.zoom, bh * self.zoom
            # Scrollbar visuali
            if vw > cr.width + 1:
                bar_w = max(20, int(cr.width * (cr.width / vw)))
                diff_x = vw - cr.width
                rel_x = max(0.0, min(1.0, (cr.left - self.origin_x) / diff_x))
                bx    = cr.left + rel_x * (cr.width - bar_w)
                _rect(self.screen, (*ACCENT, 100), (int(bx), cr.bottom - 6, bar_w, 4), radius=2)
            if vh > cr.height + 1:
                bar_h = max(20, int(cr.height * (cr.height / vh)))
                diff_y = vh - cr.height
                rel_y = max(0.0, min(1.0, (cr.top - self.origin_y) / diff_y))
                by    = cr.top + rel_y * (cr.height - bar_h)
                _rect(self.screen, (*ACCENT, 100), (cr.right - 6, int(by), 4, bar_h), radius=2)

        self._r_toolbar(cr)

    # ─────────────────────────────────────────────────────────────────────────
    # GRID
    # ─────────────────────────────────────────────────────────────────────────

    def _r_grid(self, cr):
        rx0, ry0 = self._s2r(cr.left,  cr.top)
        rx1, ry1 = self._s2r(cr.right, cr.bottom)
        gs = self.grid_size
        xi = int(rx0 // gs) * gs
        while xi <= rx1:
            sx, _ = self._r2s(xi, 0)
            pygame.draw.line(self.screen, GRID_C,
                             (int(sx), cr.top), (int(sx), cr.bottom))
            xi += gs
        yi = int(ry0 // gs) * gs
        while yi <= ry1:
            _, sy = self._r2s(0, yi)
            pygame.draw.line(self.screen, GRID_C,
                             (cr.left, int(sy)), (cr.right, int(sy)))
            yi += gs

    # ─────────────────────────────────────────────────────────────────────────
    # BACKGROUND
    # ─────────────────────────────────────────────────────────────────────────

    def _r_background(self, cr):
        if self.bg_surf:
            bw, bh = self.bg_surf.get_size()
            zoom = self.zoom
            if self._bg_cache_surf is None or self._bg_cache_zoom != zoom:
                dw, dh = max(1, int(bw * zoom)), max(1, int(bh * zoom))
                self._bg_cache_surf = pygame.transform.scale(self.bg_surf, (dw, dh))
                self._bg_cache_zoom = zoom
            
            ox, oy = self._r2s(0, 0)
            self.screen.blit(self._bg_cache_surf, (int(ox), int(oy)))
        else:
            x1, y1 = self._r2s(0,     0)
            x2, y2 = self._r2s(REF_W, REF_H)
            _rect(self.screen, BORDER,
                  (int(x1), int(y1), int(x2-x1), int(y2-y1)), 1)
            s = _txt(self._TR("canvas_no_bg"), "sm", TXT_DIM)
            self.screen.blit(s, (int((x1+x2)/2 - s.get_width()//2),
                                 int((y1+y2)//2)))

    # ─────────────────────────────────────────────────────────────────────────
    # OVERLAYS OGGETTI
    # ─────────────────────────────────────────────────────────────────────────

    def _r_overlays(self):
        from editor.constants import layer_z
        alpha = 180 if self.show_overlay else 50
        objs  = self.scene_data.get("objects", [])

        # Ordinamento indici per Z-index crescente per gestire correttamente la sovrapposizione in editor
        sorted_indices = sorted(range(len(objs)), key=lambda idx: layer_z(objs[idx].get("layer", "objects_mid")))

        # ── Primo passaggio: icone PNG ────────────────────────────────────────
        if self.show_icons:
            for i in sorted_indices:
                obj = objs[i]
                lid = obj.get("layer", "objects_mid")
                if not self.layer_vis.get(lid, True): continue
                cat_id = obj.get("catalog_id", "")
                cat_e  = next((c for c in self.catalog if c["id"] == cat_id), None)
                if not cat_e or not self.game_path: continue
                ip = self.game_path / cat_e.get("icon", "")
                dt = obj.get("detection_type", "circle")
                ox, oy = obj.get("x", 0), obj.get("y", 0)
                if dt == "circle":
                    rw = obj.get("width", obj.get("radius", 30) * 2)
                    rh = obj.get("height", obj.get("radius", 30) * 2)
                    cx_, cy_ = ox, oy
                else:
                    rw = obj.get("width", 60)
                    rh = obj.get("height", 60)
                    cx_, cy_ = ox + rw/2, oy + rh/2

                MAX_SCREEN_DIM = 2000
                scr_w = max(8, min(MAX_SCREEN_DIM, int(rw * self.zoom)))
                scr_h = max(8, min(MAX_SCREEN_DIM, int(rh * self.zoom)))
                rot = obj.get("rotation", 0)
                flip_x = obj.get("flip_x", False)
                flip_y = obj.get("flip_y", False)
                alpha_val = obj.get("alpha", 255)
                color = tuple(obj.get("color_filter", (255, 255, 255)))
                coff = obj.get("corners", [[0,0], [0,0], [0,0], [0,0]])
                has_warp = any(c[0] != 0 or c[1] != 0 for c in coff)

                ck_coff = tuple(tuple(c) for c in coff)
                gs = obj.get("grayscale", False)
                gs_f = obj.get("grayscale_factor", 1.0)
                
                # Filtro Bianco e Nero applicato via apply_grayscale

                cache_key = (cat_id, scr_w, scr_h, rot, flip_x, flip_y, alpha_val, color, ck_coff, gs, gs_f)
                if cache_key in self._obj_draw_cache:
                    ic_data = self._obj_draw_cache[cache_key]
                    ic, ic_meta = (ic_data if isinstance(ic_data, tuple) else (ic_data, None))
                else:
                    ic = self._load_img(ip, (scr_w, scr_h))
                    if not ic: continue

                    ic_meta = None
                    if has_warp:
                        sx_scale = scr_w / rw if rw > 0 else 1.0
                        sy_scale = scr_h / rh if rh > 0 else 1.0
                        q = [
                            (coff[0][0]*sx_scale, coff[0][1]*sy_scale),                           # NW
                            (scr_w + coff[1][0]*sx_scale, coff[1][1]*sy_scale),                  # NE
                            (scr_w + coff[2][0]*sx_scale, scr_h + coff[2][1]*sy_scale),          # SE
                            (coff[3][0]*sx_scale, scr_h + coff[3][1]*sy_scale)                   # SW
                        ]
                        min_xq = min(p[0] for p in q)
                        min_yq = min(p[1] for p in q)
                        ic = warp_surface(ic, q)
                        ic_meta = (min_xq, min_yq)

                    if flip_x or flip_y:
                        ic = pygame.transform.flip(ic, flip_x, flip_y)
                    if rot != 0:
                        ic = pygame.transform.rotate(ic, rot)
                    # 4. Filtro Bianco e Nero (Trasformazione Pixel)
                    if gs:
                        ic = apply_grayscale(ic, gs_f)

                    # 5. Filtro Colore (Pixel-level)
                    if color != (255, 255, 255):
                        ic = ic.copy()
                        tint = pygame.Surface(ic.get_size(), pygame.SRCALPHA)
                        tint.fill((*color, 255))
                        ic.blit(tint, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)

                    # 6. Opacità (Surface-level) - SEMPRE PER ULTIMA
                    if alpha_val < 255:
                        ic = ic.copy()
                        ic.set_alpha(alpha_val)
                    
                    if len(self._obj_draw_cache) > 200:
                        self._obj_draw_cache.clear()
                    self._obj_draw_cache[cache_key] = (ic, ic_meta)

                if not ic: continue
                sx, sy = self._r2s(cx_, cy_)
                
                if ic_meta and rot == 0:
                    mxq, myq = ic_meta
                    final_x = sx - scr_w / 2 + mxq
                    final_y = sy - scr_h / 2 + myq
                    self.screen.blit(ic, (int(final_x), int(final_y)))
                else:
                    rect = ic.get_rect(center=(int(sx), int(sy)))
                    self.screen.blit(ic, rect)

        # ── Secondo passaggio: hit-area shapes ───────────────────────────────
        for i in sorted_indices:
            obj = objs[i]
            lid = obj.get("layer", "objects_mid")
            if not self.layer_vis.get(lid, True): continue

            is_primary = (i == self.selected_idx)
            is_sel     = (i in self.selected_indices or is_primary)
            always  = obj.get("always_show", False)
            is_goal = obj.get("is_goal", True)
            dt      = obj.get("detection_type", "circle")
            bc      = layer_color(lid)

            # Colori bordi
            is_auto_scene = self.scene_data.get("auto_random_finds", False)
            m_trigger = obj.get("minigame_trigger")

            if is_sel:          border = SEL_C
            elif m_trigger:     border = ERR_C    # ROSSO per minigiochi
            elif always:        border = ALWAYS_C # AZZURRO per obiettivi fissi (Priorità alta)
            elif is_auto_scene: border = TXT_DIM  # Grigio per i candidati random
            elif is_goal:       border = OK_C     # VERDE per obiettivi manuali
            else:               border = TXT_DIM

            ox, oy = obj.get("x", 0), obj.get("y", 0)
            rw = obj.get("width", obj.get("radius", 30) * 2)
            rh = obj.get("height", obj.get("radius", 30) * 2)
            rot = obj.get("rotation", 0)
            coff = obj.get("corners", [[0,0], [0,0], [0,0], [0,0]])
            
            bx, by = (ox, oy) if dt == "rect" else (ox - rw/2, oy - rh/2)
            rcx, rcy = (ox + rw/2, oy + rh/2) if dt == "rect" else (ox, oy)
            
            sc_pts = [
                (bx + coff[0][0],      by + coff[0][1]),      # NW
                (bx + rw + coff[1][0], by + coff[1][1]),      # NE
                (bx + rw + coff[2][0], by + rh + coff[2][1]), # SE
                (bx + coff[3][0],      by + rh + coff[3][1])  # SW
            ]
            
            poly_pts = []
            for px, py in sc_pts:
                rrx, rry = self._rotate_pt(px, py, rcx, rcy, rot)
                poly_pts.append(self._r2s(rrx, rry))

            if self.show_overlay:
                min_px = min(p[0] for p in poly_pts)
                max_px = max(p[0] for p in poly_pts)
                min_py = min(p[1] for p in poly_pts)
                max_py = max(p[1] for p in poly_pts)
                tw, th = int(max_px - min_px) + 2, int(max_py - min_py) + 2
                if tw > 0 and th > 0:
                    tsurf = pygame.Surface((tw, th), pygame.SRCALPHA)
                    tpts = [(p[0] - min_px, p[1] - min_py) for p in poly_pts]
                    pygame.draw.polygon(tsurf, (*bc, 80), tpts)
                    self.screen.blit(tsurf, (int(min_px), int(min_py)))
            
            pygame.draw.polygon(self.screen, border, poly_pts, 2)
            sx, sy = self._r2s(rcx, rcy)
            pygame.draw.line(self.screen, border, (int(sx)-5, int(sy)), (int(sx)+5, int(sy)), 1)
            pygame.draw.line(self.screen, border, (int(sx), int(sy)-5), (int(sx), int(sy)+5), 1)

            sw = int(rw * self.zoom)
            sh = int(rh * self.zoom)

            if self.show_overlay:
                cid2   = obj.get("catalog_id", "?")
                is_auto_scene = self.scene_data.get("auto_random_finds", False)
                
                if is_auto_scene:
                    # In modalità auto mostriamo solo l'ID in grigio
                    label = cid2
                    lcol  = TXT_DIM
                else:
                    label  = (f"★ {cid2}" if always else cid2)
                    if m_trigger: label += " 🕹️"
                    if not is_goal: label += " [DECO]"
                    lcol   = ALWAYS_C if always else (TXT_HI if is_goal else TXT_DIM)
                
                _draw_text(self.screen, label, "sm", lcol, int(sx)+sw//2+4, int(sy)-7, 120)

            if is_sel:
                pygame.draw.polygon(self.screen, SEL_C, poly_pts, 3 if is_primary else 2)
                
            if is_primary:
                for hid, hx, hy in self._obj_handles(obj):
                    if hid == "rot":
                        h_col = (100, 255, 100)
                        pygame.draw.circle(self.screen, h_col, (int(hx), int(hy)), HANDLE_R + 2)
                        pygame.draw.circle(self.screen, (0,0,0), (int(hx), int(hy)), HANDLE_R + 2, 2)
                        sx_c, sy_c = self._r2s(ox, oy)
                        if dt == "rect": sx_c, sy_c = self._r2s(ox+rw/2, oy+rh/2)
                        pygame.draw.line(self.screen, h_col, (int(sx_c), int(sy_c)), (int(hx), int(hy)), 2)
                        rot_label = _txt(self._TR("canvas_label_rot"), "sm", h_col)
                        self.screen.blit(rot_label, (int(hx) + HANDLE_R + 4, int(hy) - 8))
                    else:
                        h_col = (255, 255, 255)
                        pygame.draw.circle(self.screen, h_col, (int(hx), int(hy)), HANDLE_R)
                        pygame.draw.circle(self.screen, (0,0,0), (int(hx), int(hy)), HANDLE_R, 1)

                has_warp = any(c[0] != 0 or c[1] != 0 for c in coff)
                if has_warp:
                    for corner_idx in range(4):
                        cp_x = bx + (rw if corner_idx in (1, 2) else 0) + coff[corner_idx][0]
                        cp_y = by + (rh if corner_idx in (2, 3) else 0) + coff[corner_idx][1]
                        cp_x_rot, cp_y_rot = self._rotate_pt(cp_x, cp_y, rcx, rcy, rot)
                        cp_sx, cp_sy = self._r2s(cp_x_rot, cp_y_rot)
                        pygame.draw.circle(self.screen, (255, 150, 150), (int(cp_sx), int(cp_sy)), 4)
                        pygame.draw.circle(self.screen, (255, 255, 255), (int(cp_sx), int(cp_sy)), 4, 1)
                
                if self._handle_id == "rot":
                    rot_val = obj.get("rotation", 0)
                    _draw_text(self.screen, self._TR("canvas_rot_preview").format(rot_val), "sm", (100, 255, 100), int(sx)+sw//2+4, int(sy)-20)
                elif self._handle_id and self._handle_id != "move":
                    cur_w, cur_h = obj.get("width", rw), obj.get("height", rh)
                    _draw_text(self.screen, f"{int(cur_w)}x{int(cur_h)}", "sm", (255,255,255), int(sx)+sw//2+4, int(sy)+sh//2+4)
                


    # ─────────────────────────────────────────────────────────────────────────
    # EFFECT OVERLAYS
    # ─────────────────────────────────────────────────────────────────────────

    def _r_effect_overlays(self):
        """Disegna tutti gli effetti della scena nel canvas editor usando le funzioni engine."""
        effects = self.scene_data.get("effects", [])
        dt = 1/60.0 
        t_global = getattr(self, "_fx_editor_time", 0.0)
        sel_idx = getattr(self, "sel_effect_idx", None)

        for i, fx in enumerate(effects):
            if "_t_accum" not in fx:
                fx["_t_accum"] = 0.0
            
            t_type = fx.get("type", "glint")
            # Semplificato: usa il layer indicato nell'effetto (ora sempre "effects" via sanitizzazione)
            lid = fx.get("layer", "effects")

            if not self.layer_vis.get(lid, True):
                continue
            
            ex, ey = fx.get("x", 0), fx.get("y", 0)
            er = fx.get("radius", 50)
            color = tuple(fx.get("color", [255, 215, 60]))
            intensity = fx.get("intensity", 0.85)
            period = max(0.01, fx.get("pulse_period", 2.0))
            phase = fx.get("phase", 0.0)

            # Aggiorna lo stato temporale (LOGICA CENTRALIZZATA)
            update_effect_state(fx, dt)

            sx, sy = self._r2s(ex, ey)
            sr_f = er * self.zoom 
            sr_ui = max(4, int(sr_f)) 

            # Rendering Effetto (Unificato)
            if t_type == "flies":
                draw_flies_effect(self.screen, sx, sy, sr_f, color, intensity, 
                                  fx["_t_accum"], t_global, fx.get("pulse_min", 1.0))
            elif t_type == "smoke":
                draw_smoke_effect(self.screen, sx, sy, sr_f, color, intensity, 
                                  fx["_t_accum"], phase)
            elif t_type == "glint":
                draw_glint_effect(self.screen, sx, sy, sr_f, color, intensity, 
                                  fx["_t_accum"], phase, fx.get("pulse_min", 0.1))
            elif t_type == "bubble_tip":
                tk = fx.get("text_key", "NEW_TIP")
                display_text = self._TR(tk)
                
                fw = fx.get("width", 300) * self.zoom
                fh = fx.get("height", 180) * self.zoom
                draw_bubble_tip_effect(self.screen, sx, sy, display_text, fx.get("trigger", "start_scene"), 
                                        is_editor=True, width=fw, height=fh, zoom=self.zoom,
                                        color=fx.get("color", (252, 252, 255)),
                                        alpha=fx.get("alpha", 255),
                                        font_size=fx.get("font_size", 22),
                                        font_color=fx.get("font_color", (40, 40, 40)))
            
            is_sel = (i == sel_idx)
            border_col = SEL_C if is_sel else FX_C

            if t_type == "bubble_tip":
                # Selezione rettangolare per il fumetto
                bw_s = fx.get("width", 300) * self.zoom
                bh_s = fx.get("height", 180) * self.zoom
                bx_s = sx - bw_s // 2
                by_s = sy - bh_s - 35 * self.zoom
                rect_s = pygame.Rect(bx_s, by_s, bw_s, bh_s)
                pygame.draw.rect(self.screen, border_col, rect_s, 2 if is_sel else 1, border_radius=8)
                # Punto di ancoraggio (punta)
                pygame.draw.circle(self.screen, border_col, (int(sx), int(sy)), 4)
                pygame.draw.line(self.screen, border_col, (int(sx), int(sy)), (int(sx), int(by_s + bh_s)), 1)
            else:
                pygame.draw.circle(self.screen, border_col, (int(sx), int(sy)), sr_ui, 2 if is_sel else 1)
                pygame.draw.line(self.screen, border_col, (int(sx)-6, int(sy)), (int(sx)+6, int(sy)), 1)
                pygame.draw.line(self.screen, border_col, (int(sx), int(sy)-6), (int(sx), int(sy)+6), 1)

            if is_sel:
                for hid, hx, hy in self._fx_handles(fx):
                    if hid == "move":
                        pygame.draw.circle(self.screen, (255, 255, 255), (int(hx), int(hy)), HANDLE_R + 1)
                        pygame.draw.circle(self.screen, (0, 0, 0), (int(hx), int(hy)), HANDLE_R + 1, 1)
                    else:
                        h_col = FX_C if hid == "radius" else SEL_C
                        pygame.draw.circle(self.screen, h_col, (int(hx), int(hy)), HANDLE_R)
                        pygame.draw.circle(self.screen, (0, 0, 0), (int(hx), int(hy)), HANDLE_R, 1)
                        # Linea guida per il raggio
                        if hid == "radius":
                            pygame.draw.line(self.screen, FX_C, (int(sx), int(sy)), (int(hx), int(hy)), 1)

            fx_id = fx.get("effect_id", "?")
            _draw_text(self.screen, fx_id, "sm", FX_C if not is_sel else SEL_C,
                       int(sx) + sr_ui + 4, int(sy) - 7, 120)

    # ─────────────────────────────────────────────────────────────────────────
    # REST OF THE CLASS
    # ─────────────────────────────────────────────────────────────────────────

    def _r_effect_place_cursor(self, cr):
        """Preview cursore durante piazzamento effetto."""
        fx_cat = None
        eid = getattr(self, "effects_catalog_sel", None)
        if eid:
            fx_cat = next((c for c in getattr(self, "effects_catalog", [])
                           if c["id"] == eid), None)
        if not fx_cat:
            return
        mx, my_raw = pygame.mouse.get_pos()
        if not _in_rect((mx, my_raw), cr):
            return
        r = max(4, int(self._scale(fx_cat.get("default_radius", 55))))
        color = tuple(fx_cat.get("default_color", [255, 215, 60]))
        
        surf = pygame.Surface((r * 4, r * 4), pygame.SRCALPHA)
        for ring in range(12, 0, -1):
            ratio = ring / 12
            ring_r = max(1, int(r * ratio))
            alpha = int(80 * (1.0 - ratio)**2)
            pygame.draw.circle(surf, (*color, alpha), (r * 2, r * 2), ring_r)
        
        pygame.draw.circle(surf, (*color, 200), (r * 2, r * 2), r, 1)
        self.screen.blit(surf, (mx - r * 2, my_raw - r * 2))
        
        s = _txt(f"r:{fx_cat.get('default_radius', 55)}  Click={self._TR('fx_hint_click')}", "sm", FX_C)
        self.screen.blit(s, (mx + r + 6, my_raw - 8))

    def _r_drag_tooltip(self):
        """Mostra coordinate X,Y vicino al cursore."""
        active = (
            (self._drag_active and self.selected_idx is not None) or
            (self._handle_id is not None and self.selected_idx is not None)
        )
        if not active: return
        objs = self.scene_data.get("objects", [])
        if self.selected_idx >= len(objs): return
        obj = objs[self.selected_idx]
        dt  = obj.get("detection_type", "circle")
        x, y = int(obj["x"]), int(obj["y"])
        rot = obj.get("rotation", 0)
        rot_str = f"  rot:{rot}°" if self._handle_id == "rot" or rot != 0 else ""

        if dt == "rect":
            w_o, h_o = int(obj.get("width", 60)), int(obj.get("height", 60))
            label = f"x:{x}  y:{y}    {w_o} × {h_o} px{rot_str}"
        else:
            label = f"x:{x}  y:{y}    r:{int(obj.get('radius', 30))} px{rot_str}"
        
        txt_surf = _txt(label, "sm", TXT_HI)
        pad = 7
        tip_w, tip_h = txt_surf.get_width() + pad*2, txt_surf.get_height() + pad*2
        bg = pygame.Surface((tip_w, tip_h), pygame.SRCALPHA)
        bg.fill((14, 14, 22, 210))
        mx, my_raw = pygame.mouse.get_pos()
        w_win, h_win = self.screen.get_size()
        tx, ty = mx + 18, my_raw - tip_h - 10
        if tx + tip_w > w_win: tx = mx - tip_w - 10
        if ty < 0: ty = my_raw + 18
        self.screen.blit(bg, (tx, ty))
        pygame.draw.rect(self.screen, ACCENT, (tx, ty, tip_w, tip_h), 1)
        self.screen.blit(txt_surf, (tx + pad, ty + pad))

    def _r_placing_rect(self):
        rx1, ry1 = self._rect_ref_start
        rx2, ry2 = self._rect_ref_cur
        sx1, sy1 = self._r2s(min(rx1, rx2), min(ry1, ry2))
        sx2, sy2 = self._r2s(max(rx1, rx2), max(ry1, ry2))
        sw, sh   = max(2, int(sx2-sx1)), max(2, int(sy2-sy1))
        surf = pygame.Surface((sw+2, sh+2), pygame.SRCALPHA)
        pygame.draw.rect(surf, (*ACCENT, 50),  (0, 0, sw, sh))
        pygame.draw.rect(surf, (*ACCENT, 200), (0, 0, sw, sh), 2)
        self.screen.blit(surf, (int(sx1), int(sy1)))
        dim = f"{round(abs(rx2-rx1))}×{round(abs(ry2-ry1))} px"
        s = _txt(dim, "sm", TXT_HI)
        self.screen.blit(s, (int(sx2)+4, int((sy1+sy2)//2)))

    def _r_placing_circle(self):
        cx, cy = self._circle_ref_center
        r  = self._circle_ref_radius
        sx, sy = self._r2s(cx, cy)
        sr = max(2, int(self._scale(r)))
        surf = pygame.Surface((sr*2+4, sr*2+4), pygame.SRCALPHA)
        pygame.draw.circle(surf, (*ACCENT, 50),  (sr+2, sr+2), sr)
        pygame.draw.circle(surf, (*ACCENT, 200), (sr+2, sr+2), sr, 2)
        self.screen.blit(surf, (int(sx)-sr-2, int(sy)-sr-2))
        s = _txt(f"r: {round(r)} px", "sm", TXT_HI)
        self.screen.blit(s, (int(sx)+sr+6, int(sy)-8))

    def _r_circle_cursor(self, cr):
        cat = self._sel_catalog()
        if not cat: return
        mx, my_raw = pygame.mouse.get_pos()
        if not _in_rect((mx, my_raw), cr): return
        sr = max(2, int(self._scale(cat.get("default_radius", 30))))
        surf = pygame.Surface((sr*2+4, sr*2+4), pygame.SRCALPHA)
        pygame.draw.circle(surf, (*ACCENT, 35),  (sr+2, sr+2), sr)
        pygame.draw.circle(surf, (*ACCENT, 160), (sr+2, sr+2), sr, 2)
        self.screen.blit(surf, (mx-sr-2, my_raw-sr-2))

    def _r_scatter_cursor(self, cr):
        """Anteprima visiva degli oggetti che verranno piazzati."""
        mx, my_raw = pygame.mouse.get_pos()
        if not _in_rect((mx, my_raw), cr): return
        # Mostra la disposizione spaziale dei 4 oggetti del cluster
        # Gli offset qui sono in pixel schermo (quindi fissi, non zoommati)
        # per dare un'idea immediata della densità.
        offsets = [(-40, -40), (40, -40), (-40, 40), (40, 40)]
        for ox, oy in offsets:
            pygame.draw.circle(self.screen, ACCENT, (mx + ox, my_raw + oy), 5)
            pygame.draw.circle(self.screen, (255, 255, 255), (mx + ox, my_raw + oy), 5, 1)
        
        hint = _txt(self._TR("canvas_scatter_hint"), "sm", ACCENT)
        self.screen.blit(hint, (mx + 50, my_raw - 8))

    def _r_selection_box(self):
        """Disegna il rettangolo di selezione (marquee)."""
        rx1, ry1 = self._sel_box_start
        rx2, ry2 = self._sel_box_cur
        sx1, sy1 = self._r2s(min(rx1, rx2), min(ry1, ry2))
        sx2, sy2 = self._r2s(max(rx1, rx2), max(ry1, ry2))
        sw, sh   = int(sx2-sx1), int(sy2-sy1)
        if sw <= 0 or sh <= 0: return
        surf = pygame.Surface((sw, sh), pygame.SRCALPHA)
        surf.fill((100, 200, 255, 40))
        pygame.draw.rect(surf, (150, 230, 255, 180), (0, 0, sw, sh), 1)
        self.screen.blit(surf, (int(sx1), int(sy1)))

    def _get_toolbar_layout(self):
        cr = self._canvas_rect()
        x, y = cr.left + 8, cr.top + 8
        tools = [
            (MODE_SELECT,       self._TR("tb_select_btn"),   115),
            (MODE_CIRCLE,       self._TR("tb_circle_btn"),   90),
            (MODE_RECT,         self._TR("tb_rect_btn"),  100),
            (MODE_EFFECT_PLACE, self._TR("tb_effect_btn"),      80),
            (MODE_SCATTER,      self._TR("tb_cluster_btn"),      80),
        ]
        toggles = [
            ("overlay", self.show_overlay, self._TR("tb_overlay_btn"), 80),
            ("grid",    self.show_grid,    self._TR("tb_grid_btn"), 80),
            ("icons",   self.show_icons,   self._TR("tb_icons_btn"),   70),
        ]
        items = []
        for mid, lbl, w in tools:
            items.append({'r': pygame.Rect(x, y, w, 24), 'id': mid, 'type': 'mode', 'lbl': lbl, 'active': (self.mode == mid)})
            x += w + 6
        x += 12
        for tid, active, lbl, w in toggles:
            items.append({'r': pygame.Rect(x, y, w, 24), 'id': tid, 'type': 'toggle', 'lbl': lbl, 'active': active})
            x += w + 6
        return items

    def _toolbar_click(self, mx, my_raw) -> bool:
        for item in self._get_toolbar_layout():
            if _in_rect((mx, my_raw), item['r']):
                if item['type'] == 'mode':
                    self.mode = item['id']
                    self._cancel_rect()
                elif item['id'] == 'overlay': self.show_overlay = not self.show_overlay
                elif item['id'] == 'grid':    self.show_grid = not self.show_grid
                elif item['id'] == 'icons':   self.show_icons = not self.show_icons
                return True
        return False

    def _r_toolbar(self, cr):
        from editor.constants import UI_TIPS
        mx, my_raw = pygame.mouse.get_pos()
        layout = self._get_toolbar_layout()
        for item in layout:
            r, active = item['r'], item['active']
            hov = _in_rect((mx, my_raw), r)
            if hov:
                tip_key = f"tip_{'mode_' if item['type'] == 'mode' else 'toggle_'}{item['id']}"
                self.active_tooltip = self._TR(tip_key)

            bg  = BTN_AC if active else (BTN_HO if hov else STATUS)
            bc  = ACCENT if active else (TXT_HI if hov else BORDER)
            _rect(self.screen, bg, r, radius=4)
            _rect(self.screen, bc, r, 1, radius=4)
            tc = TXT_HI if (active or hov) else TXT
            
            if item['id'] == MODE_SELECT:
                # Icona a sinistra + Scritta a destra
                icon_sz = 18
                iy = r.y + (r.h - icon_sz) // 2
                _draw_shape_icon(self.screen, (r.x + 8, iy, icon_sz, icon_sz), "select_rect", tc)
                tw, th = _text_wh(item['lbl'], "sm")
                # Offset correttivo per centratura visuale perfetta (-2px per compensare il font)
                ty = r.y + (r.h - th) // 2 - 2
                self.screen.blit(_txt(item['lbl'], "sm", tc), (r.x + icon_sz + 14, ty))
            else:
                tw, th = _text_wh(item['lbl'], "sm")
                self.screen.blit(_txt(item['lbl'], "sm", tc), (r.x + (r.w-tw)//2, r.y + (r.h-th)//2))

        zm = _txt(self._TR("canvas_zoom_info").format(self.zoom), "sm", TXT_DIM)
        self.screen.blit(zm, (cr.right - zm.get_width() - 8, cr.top + 8))
        hints = self._TR("canvas_hints")
        hs = _txt(hints, "sm", (60, 65, 75))
        self.screen.blit(hs, (cr.right - hs.get_width() - 8, cr.top + 24))
        if _in_rect((mx, my_raw), cr):
            rx, ry = self._s2r(mx, my_raw)
            coord  = _txt(f"({int(rx)}, {int(ry)})", "mono", TXT_DIM)
            self.screen.blit(coord, (cr.right - coord.get_width() - 8, cr.top + 40))
