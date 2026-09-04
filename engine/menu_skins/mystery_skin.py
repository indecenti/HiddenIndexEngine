"""
engine/menu_skins/mystery_skin.py

MysterySkin - "The Detective" direction: investigative noir, warm desaturated
tones, strong vignette, dust floating in the light, spaced serif title. Inherits
from DefaultSkin (which already applies the sepia to the mystery cards through
the sepia_overlay flag).
"""

import math
import random
import pygame

from .base import SurfaceCache, as_float, as_int, as_rgb, cached_title
from .default_skin import DefaultSkin

# Dust bounds: density comes from theme.json (authored data).
DUST_MAX = 120


class MysterySkin(DefaultSkin):
    id = "mystery"

    def __init__(self, theme) -> None:
        super().__init__(theme)
        self._dust: list[dict] = []
        self._vig = None
        # Dust glow cache, keyed by (radius, colour). Avoids allocating + drawing
        # a new SRCALPHA surface for every mote every frame (it used to rebuild
        # ~density surfaces per frame in the draw path). Bounded LRU: a plain
        # dict would keep one entry per colour a theme ever asks for.
        self._mote_cache = SurfaceCache()

    def draw_background_pre(self, ms, screen, sw, sh) -> None:
        if self.fx_on(ms, "vignette"):
            self._vignette(screen, sw, sh)

    def _vignette(self, screen, sw, sh) -> None:
        amt = as_float(self.theme.decor("vignette", 0.7), 0.7)
        if amt <= 0:
            return
        v = self._vig
        if v is None or v.get_width() != sw or v.get_height() != sh:
            v = pygame.Surface((sw, sh), pygame.SRCALPHA)
            cx, cy = sw // 2, int(sh * 0.45)
            maxr = int((sw * sw + sh * sh) ** 0.5 * 0.5)
            for r in range(maxr, 0, -6):
                t = r / maxr
                a = int(205 * amt * (t ** 2.2))
                if a > 0:
                    pygame.draw.circle(v, (8, 5, 2, a), (cx, cy), r)
            self._vig = v
        screen.blit(v, (0, 0))

    def update(self, ms, dt) -> None:
        super().update(ms, dt)
        if not (self.fx_on(ms, "dust") and not self.reduced(ms)):
            if self._dust:
                self._dust = []
            return
        target = max(0, min(DUST_MAX, as_int(self.theme.particles_cfg("density", 22), 22)))
        while len(self._dust) < target:
            self._dust.append(self._new_mote())
        del self._dust[target:]   # a lowered density must shed the extras
        dt = as_float(dt, 0.0)
        for p in self._dust:
            p["x"] += p["vx"] * dt
            p["y"] += p["vy"] * dt
            p["ph"] += dt
            if p["y"] > 1.05:
                self._reset_mote(p)

    def _new_mote(self) -> dict:
        p = {"vx": (random.random() - 0.5) * 0.02, "vy": 0.01 + random.random() * 0.03,
             "r": random.randint(1, 2), "ph": random.random() * 6.28}
        self._reset_mote(p)
        p["y"] = random.random()
        return p

    def _reset_mote(self, p: dict) -> None:
        p["x"] = random.random()
        p["y"] = -0.02

    def _mote_glow(self, rr, col):
        # Mote glow pre-rendered at full alpha (255). The per-frame alpha is
        # applied with set_alpha on the blit -> same pixels as drawing it
        # directly, without an allocation + draw every frame.
        def _build():
            g = pygame.Surface((rr * 4, rr * 4), pygame.SRCALPHA)
            pygame.draw.circle(g, (col[0], col[1], col[2], 255), (rr * 2, rr * 2), rr)
            return g

        return self._mote_cache.get_or_build((rr, col[0], col[1], col[2]), _build)

    def draw_overlay(self, ms, screen, sw, sh) -> None:
        if not self._dust:
            return
        col = as_rgb(self.theme.particles_cfg("color", None), (185, 150, 92))
        for p in self._dust:
            a = int(60 + 55 * math.sin(p["ph"] * 1.5))
            a = max(0, min(120, a))
            if a <= 0:
                continue
            rr = p["r"]
            g = self._mote_glow(rr, col)
            g.set_alpha(a)
            screen.blit(g, (int(p["x"] * sw), int(p["y"] * sh)))

    def draw_title(self, ms, screen) -> None:
        theme = self.theme
        sm = ms.scaling_manager
        text = ms._state_title_text()
        if not text:
            return
        size = as_int(theme.layout("title_font_size", 44), 44)
        spacing = sm.scale_value(
            as_int((theme._typography.get("title", {}) or {}).get("spacing", 2), 2))
        col = theme.color3("text_hover")
        # render_spaced is one font.render PER CHARACTER, and the title was
        # composed twice (text + shadow) EVERY frame although nothing about it
        # animates. Cache both, keyed on the SCALED size so a resize rebuilds.
        key = (text, sm.scale_value(size), spacing, col)

        def _build():
            font = theme.get_font_role("title", size, sm)
            shadow = theme.render_spaced(font, text, (10, 6, 2), spacing)
            shadow.set_alpha(185)
            return (theme.render_spaced(font, text, col, spacing), shadow)

        surf, shadow = cached_title(self, key, _build)
        tx = (screen.get_width() - surf.get_width()) // 2
        ty = sm.scale_value(as_int(theme.layout("title_y_offset", 105), 105))
        screen.blit(shadow, (tx + 2, ty + 2))
        screen.blit(surf, (tx, ty))
