"""
engine/menu_skins/cyber_neon_skin.py

CyberNeonSkin — direzione "Cyber Neon": griglia retrofuturista in prospettiva,
alone neon all'orizzonte, scanline, particellari digitali, titolo monospace con
aberrazione cromatica e micro-glitch. Eredita da DefaultSkin (gestione bottoni/
icone con glow quadrato gia' presente via le flag del tema).
"""

import math
import pygame

from .default_skin import DefaultSkin


class CyberNeonSkin(DefaultSkin):
    id = "cyber_neon"

    def __init__(self, theme) -> None:
        super().__init__(theme)
        self._scan = None

    def draw_background_pre(self, ms, screen, sw, sh) -> None:
        if self.fx_on(ms, "grid") and not self.reduced(ms):
            self._draw_grid(screen, sw, sh)

    def _draw_grid(self, screen, sw, sh) -> None:
        col = self.theme.background("grid_color", [0, 170, 200])
        glow = self.theme.background("glow_color", [255, 0, 255])
        surf = pygame.Surface((sw, sh), pygame.SRCALPHA)
        horizon = int(sh * 0.46)
        # Alone neon all'orizzonte
        for i in range(6):
            t = i / 5
            r = int(sw * 0.5 * (0.3 + 0.7 * t))
            a = int(20 * (1.0 - t))
            if a > 0 and r > 0:
                pygame.draw.circle(surf, (glow[0], glow[1], glow[2], a), (sw // 2, horizon), r)
        c = (col[0], col[1], col[2])
        # Orizzontali che si infittiscono verso il basso (prospettiva)
        rows = 16
        for i in range(rows + 1):
            t = i / rows
            y = horizon + int((sh - horizon) * (t * t))
            a = int(80 * (0.25 + 0.75 * t))
            pygame.draw.line(surf, (c[0], c[1], c[2], a), (0, y), (sw, y), 1)
        # Verticali a ventaglio verso il punto di fuga
        cols = 16
        for i in range(cols + 1):
            bx = sw * i / cols
            pygame.draw.line(surf, (c[0], c[1], c[2], 45), (bx, sh), (sw / 2, horizon), 1)
        screen.blit(surf, (0, 0))

    def draw_overlay(self, ms, screen, sw, sh) -> None:
        if self.fx_on(ms, "scanline") and not self.reduced(ms):
            amt = float(self.theme.decor("scanline", 0.0))
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
        col = self.theme.particles_cfg("color", [0, 255, 255])
        n = int(self.theme.particles_cfg("density", 16))
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
        size = theme.layout("title_font_size", 48)
        font = theme.get_font_role("title", size, sm)
        spacing = sm.scale_value(int((theme._typography.get("title", {}) or {}).get("spacing", 3)))
        up = text.upper()
        white = theme.render_spaced(font, up, (255, 255, 255), spacing)
        cx = screen.get_width() // 2 - white.get_width() // 2
        ty = sm.scale_value(theme.layout("title_y_offset", 100))
        off = sm.scale_value(2)
        # Aberrazione cromatica: ciano e magenta sfalsati + nucleo bianco
        cyan = theme.render_spaced(font, up, (0, 255, 255), spacing)
        mag = theme.render_spaced(font, up, (255, 0, 255), spacing)
        cyan.set_alpha(160)
        mag.set_alpha(160)
        screen.blit(cyan, (cx - off, ty))
        screen.blit(mag, (cx + off, ty))
        screen.blit(white, (cx, ty))

    def button_jitter(self, ms, b):
        if not (self.fx_on(ms, "glitch") and not self.reduced(ms)):
            return (0.0, 0.0)
        # Glitch a scatti: fermo quasi sempre, ogni tanto uno scatto orizzontale.
        phase = (self._t * 3.0 + b.ref_rect.x * 0.012) % 1.0
        if phase > 0.93:
            return (((b.ref_rect.x * 7) % 5) - 2.0, 0.0)
        return (0.0, 0.0)
