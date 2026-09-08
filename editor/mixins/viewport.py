"""
editor/mixins/viewport.py

ViewportMixin — zoom, pan, trasformazioni coordinate, layout pannelli.
"""

import math
import pygame
from editor.constants import (
    TOP_BAR_H, STATUS_H, PANEL_MIN_W, PANEL_MAX_W,
    REF_W, REF_H, GRID_SIZES, ACCENT, TAB_LAYERS, TAB_PROPS,
    MIN_EDITOR_WIDTH, MIN_EDITOR_HEIGHT, WIN_W, WIN_H,
)


class ViewportMixin:
    """Gestione viewport: coordinate screen↔reference, zoom, pan, layout."""

    # ─────────────────────────────────────────────────────────────────────────
    # TOGGLE DI VISTA
    # ─────────────────────────────────────────────────────────────────────────
    # One method per toggle, so the canvas toolbar, the keyboard and the
    # command palette all drive the same code instead of three copies.

    def _toggle_overlay(self) -> None:
        """Show or hide the coloured hit areas over the background."""
        self.show_overlay = not self.show_overlay
        self._mark_dirty()

    def _toggle_grid(self) -> None:
        """Show or hide the grid."""
        self.show_grid = not self.show_grid
        self._mark_dirty()

    def _toggle_icons(self) -> None:
        """Show or hide the PNG icons of the placed objects."""
        self.show_icons = not self.show_icons
        self._mark_dirty()

    def _cycle_grid_size(self) -> None:
        """Next grid size, persisted. Turns the grid on if it was off."""
        try:
            index = GRID_SIZES.index(self.grid_size)
        except ValueError:
            index = -1
        self.grid_size = GRID_SIZES[(index + 1) % len(GRID_SIZES)]
        self._save_editor_setting("grid_size", self.grid_size)
        self.show_grid = True
        self._mark_dirty()
        self._status(self._TR("ih_grid", "Grid: {0}px").format(self.grid_size),
                     ACCENT, 2)

    def _toggle_obj_snap(self) -> None:
        """Snap to the edges of the other objects, persisted."""
        self.obj_snap = not getattr(self, "obj_snap", True)
        self._save_editor_setting("obj_snap", self.obj_snap)
        self._status(
            self._TR("ih_snap_objects", "Snap to objects: {0}").format(
                "ON" if self.obj_snap else "OFF"), ACCENT, 2)

    def _toggle_panels(self) -> None:
        """Hide the side panels to give the canvas the whole window."""
        self.panels_visible = not self.panels_visible
        self._update_layout()
        self._mark_dirty()

    def _toggle_layers_tab(self) -> None:
        """Swap the right panel between the layers and the properties."""
        self.r_tab = TAB_LAYERS if self.r_tab != TAB_LAYERS else TAB_PROPS

    def _zoom_in(self) -> None:
        self._zoom_by(1.2)

    def _zoom_out(self) -> None:
        self._zoom_by(1 / 1.2)

    def _toggle_fullscreen(self) -> None:
        """Fullscreen on and off, keeping the window above its minimum size."""
        self.fullscreen = not self.fullscreen
        if self.fullscreen:
            self.screen = pygame.display.set_mode(
                (0, 0), pygame.FULLSCREEN | pygame.RESIZABLE)
        else:
            self.screen = pygame.display.set_mode((WIN_W, WIN_H), pygame.RESIZABLE)
        self.screen_size = self.screen.get_size()

        if not self.fullscreen:
            w, h = self.screen_size
            if w < MIN_EDITOR_WIDTH or h < MIN_EDITOR_HEIGHT:
                w = max(w, MIN_EDITOR_WIDTH)
                h = max(h, MIN_EDITOR_HEIGHT)
                self.screen = pygame.display.set_mode((w, h), pygame.RESIZABLE)
                self.screen_size = (w, h)

        self._update_layout()
        self._mark_dirty()
        self._status(self._TR("ih_fullscreen", "Fullscreen: {0}").format(
            "ON" if self.fullscreen else "OFF"), ACCENT, 2)

    # ─────────────────────────────────────────────────────────────────────────
    # LAYOUT
    # ─────────────────────────────────────────────────────────────────────────

    def _update_layout(self):
        """Calcola dimensioni pannelli di default se non inizializzati."""
        w, h = self.screen.get_size()
        if not self.panels_visible:
            self.panel_l_w = 0
            self.panel_r_w = 0
            return
            
        if not getattr(self, "_layout_init", False):
            # Carica dimensioni salvate se disponibili
            settings = self._load_editor_settings()
            self.panel_l_w = settings.get("panel_l_w", 360)
            self.panel_r_w = settings.get("panel_r_w", 260)
            self._layout_init = True
            
        # Clamp di sicurezza se lo schermo è troppo piccolo
        if self.panel_l_w + self.panel_r_w > w - 100:
            scale = (w - 100) / (self.panel_l_w + self.panel_r_w)
            self.panel_l_w = int(self.panel_l_w * scale)
            self.panel_r_w = int(self.panel_r_w * scale)

    def _canvas_rect(self) -> pygame.Rect:
        self._update_layout()
        w, h = self.screen.get_size()
        l_w = self.panel_l_w
        r_w = self.panel_r_w
        if l_w + r_w > w - 100:
            l_w = r_w = max(50, (w - 100) // 2)
        return pygame.Rect(l_w, TOP_BAR_H, max(100, w - l_w - r_w),
                           h - TOP_BAR_H - STATUS_H)

    # ─────────────────────────────────────────────────────────────────────────
    # COORDINATE (screen_x = ref_x * zoom + origin_x)
    # ─────────────────────────────────────────────────────────────────────────

    def _s2r(self, sx, sy):
        """Screen → reference coords."""
        return (sx - self.origin_x) / self.zoom, (sy - self.origin_y) / self.zoom

    def _r2s(self, rx, ry):
        """Reference → screen coords con arrotondamento per prevenire jittering."""
        return int(round(rx * self.zoom + self.origin_x)), int(round(ry * self.zoom + self.origin_y))

    def _scale(self, v: float) -> float:
        """Scala un valore reference-space in pixel schermo con arrotondamento."""
        return int(round(v * self.zoom))

    def _snap(self, v: float) -> float:
        """Applica snap alla griglia se attiva."""
        if self.show_grid and self.grid_snap:
            return round(v / self.grid_size) * self.grid_size
        return round(v)

    def _pan_by(self, dx, dy):
        """Sposta l'origine della telecamera."""
        if dx != 0 or dy != 0:
            self.origin_x += dx
            self.origin_y += dy
            self._mark_dirty()

    def _rotate_pt(self, px, py, cx, cy, angle_deg):
        """Ruota (px, py) attorno a (cx, cy) di angle_deg gradi."""
        if angle_deg == 0:
            return px, py
        rad = math.radians(angle_deg)
        tx, ty = px - cx, py - cy
        nx = tx * math.cos(rad) + ty * math.sin(rad)
        ny = -tx * math.sin(rad) + ty * math.cos(rad)
        return nx + cx, ny + cy

    # ─────────────────────────────────────────────────────────────────────────
    # FIT / ZOOM
    # ─────────────────────────────────────────────────────────────────────────

    def _fit_canvas(self):
        """Fit background (o reference area) al canvas con margine 5%."""
        cr = self._canvas_rect()
        if cr.width <= 0 or cr.height <= 0:
            return
        if self.bg_surf:
            bw, bh = self.bg_surf.get_size()
            self.zoom = min(cr.width / bw, cr.height / bh) * 0.95
            self.origin_x = cr.left + (cr.width  - bw * self.zoom) / 2
            self.origin_y = cr.top  + (cr.height - bh * self.zoom) / 2
        else:
            self.zoom = min(cr.width / REF_W, cr.height / REF_H) * 0.95
            self.origin_x = cr.left + (cr.width  - REF_W * self.zoom) / 2
            self.origin_y = cr.top  + (cr.height - REF_H * self.zoom) / 2
        self._mark_dirty()

    def _zoom_by(self, factor):
        cr = self._canvas_rect()
        cx, cy = cr.centerx, cr.centery
        self._zoom_toward(cx, cy, factor)

    def _zoom_to_selection(self):
        """Inquadra la selezione corrente nel canvas (tasto Z)."""
        from editor.ui.draw import _clamp
        from editor.constants import ZOOM_MIN, ZOOM_MAX, ZOOM_SEL_MARGIN
        objs = (self.scene_data or {}).get("objects", [])
        idxs = list(getattr(self, "selected_indices", []))
        if self.selected_idx is not None and self.selected_idx not in idxs:
            idxs.append(self.selected_idx)
        idxs = [i for i in idxs if 0 <= i < len(objs)]
        if not idxs:
            return
        boxes = [self._get_obj_bbox(objs[i]) for i in idxs]
        x_min = min(b[0] for b in boxes)
        y_min = min(b[1] for b in boxes)
        x_max = max(b[2] for b in boxes)
        y_max = max(b[3] for b in boxes)
        bw = max(1.0, x_max - x_min)
        bh = max(1.0, y_max - y_min)
        cr = self._canvas_rect()
        if cr.width <= 0 or cr.height <= 0:
            return
        self.zoom = _clamp(min(cr.width / bw, cr.height / bh) * ZOOM_SEL_MARGIN,
                           ZOOM_MIN, ZOOM_MAX)
        self.origin_x = cr.left + (cr.width - bw * self.zoom) / 2 - x_min * self.zoom
        self.origin_y = cr.top + (cr.height - bh * self.zoom) / 2 - y_min * self.zoom
        self._mark_dirty()

    def _reveal_selection(self, margin: int = 40) -> None:
        """Bring the selection into view WITHOUT touching the zoom.

        Picking an object from the outline must not re-frame the canvas at a
        different scale on every click (that is what _zoom_to_selection and the
        Z shortcut are for): pan only, and only when the selection is not
        already comfortably inside the canvas.
        """
        objs = (self.scene_data or {}).get("objects", [])
        idxs = list(getattr(self, "selected_indices", []) or [])
        if self.selected_idx is not None and self.selected_idx not in idxs:
            idxs.append(self.selected_idx)
        idxs = [i for i in idxs if 0 <= i < len(objs)]
        if not idxs:
            return
        boxes = [self._get_obj_bbox(objs[i]) for i in idxs]
        x_min = min(b[0] for b in boxes)
        y_min = min(b[1] for b in boxes)
        x_max = max(b[2] for b in boxes)
        y_max = max(b[3] for b in boxes)
        cr = self._canvas_rect()
        if cr.width <= 0 or cr.height <= 0:
            return
        sx0, sy0 = self._r2s(x_min, y_min)
        sx1, sy1 = self._r2s(x_max, y_max)
        inner = cr.inflate(-margin * 2, -margin * 2)
        if (inner.left <= sx0 and inner.top <= sy0
                and sx1 <= inner.right and sy1 <= inner.bottom):
            return                      # already visible: do not move the view
        cx = (x_min + x_max) / 2.0
        cy = (y_min + y_max) / 2.0
        self.origin_x = cr.centerx - cx * self.zoom
        self.origin_y = cr.centery - cy * self.zoom
        self._mark_dirty()

    def _zoom_toward(self, sx, sy, factor):
        from editor.ui.draw import _clamp
        old = self.zoom
        self.zoom = _clamp(self.zoom * factor, 0.04, 10.0)
        self.origin_x = sx - (sx - self.origin_x) * (self.zoom / old)
        self.origin_y = sy - (sy - self.origin_y) * (self.zoom / old)
        self._mark_dirty()
