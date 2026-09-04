"""
engine/menu_skins/cyber_neon_skin.py

CyberNeonSkin - "Cyber Neon" direction: retro-futuristic grid in perspective,
neon glow on the horizon, scanlines, digital particles, monospace title with
chromatic aberration and micro-glitch. Inherits from DefaultSkin (button/icon
handling with a square glow already comes from the theme flags).
"""

import math
import pygame

from .base import as_float, as_int, as_rgb, cached_title
from .default_skin import DefaultSkin

# Digital particle bound: density comes from theme.json (authored data).
DIGITAL_MAX = 120


class CyberNeonSkin(DefaultSkin):
    id = "cyber_neon"

    def __init__(self, theme) -> None:
        super().__init__(theme)
        self._scan = None
        self._grid = None

    def draw_background_pre(self, ms, screen, sw, sh) -> None:
        if self.fx_on(ms, "grid") and not self.reduced(ms):
            self._draw_grid(screen, sw, sh)

    def _draw_grid(self, screen, sw, sh) -> None:
        col = as_rgb(self.theme.background("grid_color", None), (0, 170, 200))
        glow = as_rgb(self.theme.background("glow_color", None), (255, 0, 255))
        # CACHE: the grid (neon glow + ~33 perspective lines) is STATIC per
        # size/colour, but without a cache it allocated a FULLSCREEN SRCALPHA
        # surface and ran ~40 draws EVERY frame -> heavy alloc/blit cost on a
        # mobile GPU. It is a semi-transparent overlay by nature (alpha glow over
        # the background), so it stays SRCALPHA but is composed ONCE and blitted.
        key = (sw, sh, col, glow)
        cached = self._grid
        if cached is None or cached[0] != key:
            surf = pygame.Surface((sw, sh), pygame.SRCALPHA)
            horizon = int(sh * 0.46)
            # Neon glow on the horizon
            for i in range(6):
                t = i / 5
                r = int(sw * 0.5 * (0.3 + 0.7 * t))
                a = int(20 * (1.0 - t))
                if a > 0 and r > 0:
                    pygame.draw.circle(surf, (glow[0], glow[1], glow[2], a), (sw // 2, horizon), r)
            c = (col[0], col[1], col[2])
            # Horizontals getting denser towards the bottom (perspective)
            rows = 16
            for i in range(rows + 1):
                t = i / rows
                y = horizon + int((sh - horizon) * (t * t))
                a = int(80 * (0.25 + 0.75 * t))
                pygame.draw.line(surf, (c[0], c[1], c[2], a), (0, y), (sw, y), 1)
            # Verticals fanning out towards the vanishing point
            cols = 16
            for i in range(cols + 1):
                bx = sw * i / cols
                pygame.draw.line(surf, (c[0], c[1], c[2], 45), (bx, sh), (sw / 2, horizon), 1)
            self._grid = (key, surf)
            cached = self._grid
        screen.blit(cached[1], (0, 0))

    def draw_overlay(self, ms, screen, sw, sh) -> None:
        if self.fx_on(ms, "scanline") and not self.reduced(ms):
            amt = as_float(self.theme.decor("scanline", 0.0), 0.0)
            if amt > 0:
                self._scanlines(screen, sw, sh, amt)
        if self.theme.particles_cfg("type", "none") == "digital" \
                and self.fx_on(ms, "particles") and not self.reduced(ms):
            self._digital(screen, sw, sh)

    def _scanlines(self, screen, sw, sh, amt) -> None:
        tile = self._scan
        if tile is None or tile.get_width() != sw or tile.get_height() != sh:
            tile = pygame.Surface((sw, sh), pygame.SRCALPHA)
            a = int(110 * amt)
            for y in range(0, sh, 3):
                pygame.draw.line(tile, (0, 0, 0, a), (0, y), (sw, y), 1)
            self._scan = tile
        screen.blit(tile, (0, 0))

    def _digital(self, screen, sw, sh) -> None:
        col = as_rgb(self.theme.particles_cfg("color", None), (0, 255, 255))
        n = max(0, min(DIGITAL_MAX, as_int(self.theme.particles_cfg("density", 16), 16)))
        t = self._t
        for i in range(n):
            phi = i * 2.39996
            x = int((0.5 + 0.5 * math.sin(t * 0.7 + phi)) * sw)
            y = int(((t * 0.16 + i / max(1, n)) % 1.0) * sh)
            w = 2 + (i % 3)
            pygame.draw.rect(screen, (col[0], col[1], col[2]), (x, y, w, 2))

    def draw_title(self, ms, screen) -> None:
        theme = self.theme
        sm = ms.scaling_manager
        text = ms._state_title_text()
        if not text:
            return
        size = as_int(theme.layout("title_font_size", 48), 48)
        spacing = sm.scale_value(
            as_int((theme._typography.get("title", {}) or {}).get("spacing", 3), 3))
        up = text.upper()
        off = sm.scale_value(2)

        # CACHE: the title (cyan+magenta+white chromatic aberration) is static per
        # state/size. Without a cache it ran ~45-51 font.render PER FRAME
        # (per-glyph render_spaced x3) -> a large share of the 30-68 ms spent in
        # menu_sys. Composed ONCE, keyed on the SCALED size so a resize rebuilds.
        key = (up, sm.scale_value(size), spacing, off)

        def _build():
            font = theme.get_font_role("title", size, sm)
            white = theme.render_spaced(font, up, (255, 255, 255), spacing)
            cyan = theme.render_spaced(font, up, (0, 255, 255), spacing)
            mag = theme.render_spaced(font, up, (255, 0, 255), spacing)
            cyan.set_alpha(160)
            mag.set_alpha(160)
            comp = pygame.Surface((max(1, white.get_width() + 2 * off),
                                   max(1, white.get_height())), pygame.SRCALPHA)
            comp.blit(cyan, (0, 0))
            comp.blit(mag, (2 * off, 0))
            comp.blit(white, (off, 0))
            return comp

        comp = cached_title(self, key, _build)
        cx = screen.get_width() // 2 - comp.get_width() // 2
        ty = sm.scale_value(as_int(theme.layout("title_y_offset", 100), 100))
        screen.blit(comp, (cx, ty))

    def button_jitter(self, ms, b):
        if not (self.fx_on(ms, "glitch") and not self.reduced(ms)):
            return (0.0, 0.0)
        # Snappy glitch: still most of the time, an occasional horizontal jump.
        phase = (self._t * 3.0 + b.ref_rect.x * 0.012) % 1.0
        if phase > 0.93:
            return (((b.ref_rect.x * 7) % 5) - 2.0, 0.0)
        return (0.0, 0.0)
