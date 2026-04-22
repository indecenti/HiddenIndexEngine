"""
editor/mixins/viewport.py

ViewportMixin — zoom, pan, trasformazioni coordinate, layout pannelli.
"""

import math
import pygame
from editor.constants import (
    TOP_BAR_H, STATUS_H, PANEL_MIN_W, PANEL_MAX_W,
    REF_W, REF_H,
)
from editor.ui.draw import _clamp


class ViewportMixin:
    """Gestione viewport: coordinate screen↔reference, zoom, pan, layout."""

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
            # Default al primo avvio
            self.panel_l_w = 360
            self.panel_r_w = 260
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
        """Reference → screen coords."""
        return rx * self.zoom + self.origin_x, ry * self.zoom + self.origin_y

    def _scale(self, v: float) -> float:
        """Scala un valore reference-space in pixel schermo."""
        return v * self.zoom

    def _snap(self, v: float) -> float:
        """Applica snap alla griglia se attiva."""
        if self.show_grid and self.grid_snap:
            return round(v / self.grid_size) * self.grid_size
        return round(v)

    def _pan_by(self, dx, dy):
        """Sposta l'origine della telecamera."""
        self.origin_x += dx
        self.origin_y += dy

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

    def _zoom_by(self, factor):
        cr = self._canvas_rect()
        cx, cy = cr.centerx, cr.centery
        self._zoom_toward(cx, cy, factor)

    def _zoom_toward(self, sx, sy, factor):
        old = self.zoom
        self.zoom = _clamp(self.zoom * factor, 0.04, 10.0)
        self.origin_x = sx - (sx - self.origin_x) * (self.zoom / old)
        self.origin_y = sy - (sy - self.origin_y) * (self.zoom / old)
