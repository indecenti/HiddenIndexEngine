"""
engine/menu_skins/horror_skin.py

HorrorSkin - "Nightmare" direction: dark and tense. Reddish fog drifting under
the flashlight (already handled by the core via flashlight_fx), fine grain,
candle halo behind the icons, button micro-jitter and a broken, spaced serif
title with flicker. Every heavy effect degrades under reduced-motion.
"""

import math
import random
import pygame

from engine.utils import is_android_runtime
from .base import as_float, as_int, as_rgb, cached_title
from .default_skin import DefaultSkin

_ANDROID = is_android_runtime()


class HorrorSkin(DefaultSkin):
    id = "horror"

    def __init__(self, theme) -> None:
        super().__init__(theme)
        self._grain = None        # cached noise tile
        self._halo = None         # cached soft radial halo (candle)
        self._fog_scratch = None  # reused fullscreen SRCALPHA layer for the fog

    # No aurora/fireflies: fog only.
    def draw_background_pre(self, ms, screen, sw, sh) -> None:
        if self.fx_on(ms, "fog") and not self.reduced(ms):
            self._draw_fog(screen, sw, sh)

    def _draw_fog(self, screen, sw, sh) -> None:
        col = as_rgb(self.theme.background("fog_color", None), (70, 40, 40))
        t = self._t
        # The blobs move, so the layer cannot be cached as pixels - but the
        # SURFACE can be reused: allocating a fullscreen SRCALPHA every frame is
        # the expensive part. Same drawing, same pixels, one allocation.
        surf = self._fog_scratch
        if surf is None or surf.get_size() != (sw, sh):
            surf = pygame.Surface((sw, sh), pygame.SRCALPHA)
            self._fog_scratch = surf
        else:
            surf.fill((0, 0, 0, 0))
        for i in range(3):
            phi = i * 2.1
            cx = int((0.30 + 0.40 * math.sin(t * 0.06 + phi) + 0.12 * i) * sw)
            cy = int((0.52 + 0.18 * math.cos(t * 0.05 + phi)) * sh)
            rad = int(sw * (0.28 + 0.06 * math.sin(t * 0.10 + phi)))
            layers = 5
            for k in range(layers):
                tt = k / (layers - 1)
                r = int(rad * (0.4 + 0.6 * tt))
                a = int(16 * (1.0 - tt))
                if a <= 0 or r <= 0:
                    continue
                pygame.draw.circle(surf, (col[0], col[1], col[2], a), (cx, cy), r)
        screen.blit(surf, (0, 0))

    _ARRANGE_STATES = ("main", "pause")

    def arrange(self, ms) -> None:
        # "Sparse" composition: irregular heights (only where the title is clear).
        if ms.state not in self._ARRANGE_STATES:
            return
        i = 0
        for b in ms.buttons:
            if b.ref_rect.x < 100 and b.ref_rect.y < 120:  # fixed buttons (back/quit)
                continue
            b.ref_rect.y += int(math.sin(i * 1.7) * 22 + math.sin(i * 0.5) * 10)
            i += 1

    def draw_title(self, ms, screen) -> None:
        theme = self.theme
        sm = ms.scaling_manager
        text = ms._state_title_text()
        if not text:
            return
        size = as_int(theme.layout("title_font_size", 48), 48)
        spacing = sm.scale_value(
            as_int((theme._typography.get("title", {}) or {}).get("spacing", 4), 4))
        up = text.upper()
        col = theme.color3("text_hover")
        glow_col = (90, 0, 0)
        # Title surface cache: render_spaced does one font.render PER CHARACTER
        # (x2: text + glow), rebuilt every frame in the draw path. The only inputs
        # that change the look are text/size/spacing/colour; the flicker is just a
        # set_alpha (below). Compose the glyphs once and re-apply the alpha per
        # frame: same pixels on both platforms, no re-render.
        # NB: the key must include the SCALED size (sm.scale_value(size)), not only
        # the 'size' constant: the real font is scaled by get_font_role, so without
        # it the title would stay at the old resolution after a resize/fullscreen.
        key = (up, sm.scale_value(size), spacing, col, glow_col)

        def _build():
            font = theme.get_font_role("title", size, sm)
            return (theme.render_spaced(font, up, col, spacing),
                    theme.render_spaced(font, up, glow_col, spacing))

        surf, glow = cached_title(self, key, _build)
        mod = as_float(theme.flicker_alpha_mod(), 1.0) if self.fx_on(ms, "flicker") else 1.0
        alpha = max(0, min(255, int(255 * mod)))
        surf.set_alpha(alpha)
        glow.set_alpha(min(alpha, 130))
        tx = (screen.get_width() - surf.get_width()) // 2
        ty = sm.scale_value(as_int(theme.layout("title_y_offset", 100), 100))
        screen.blit(glow, (tx + 2, ty + 2))
        screen.blit(surf, (tx, ty))

    def button_jitter(self, ms, b):
        if not (self.fx_on(ms, "jitter") and not self.reduced(ms)):
            return (0.0, 0.0)
        amp = as_float(self.theme.motion("jitter", 1.0), 1.0)
        if not getattr(b, "hovered", False):
            amp *= 0.4
        t = self._t * 30.0
        return (math.sin(t + b.ref_rect.x) * amp, math.cos(t * 0.9 + b.ref_rect.y) * amp)

    def behind_button(self, ms, screen, b, draw_rect, is_locked) -> None:
        # Warm "candle" halo behind the icons (not on image/locked cards).
        if b.image or is_locked or self.reduced(ms):
            return
        if not self.theme.decor("candle_glow", False):
            return
        breath = 0.5 + 0.5 * math.sin(self._t * 4.0)
        hov = as_float(getattr(b, "hover_time", 0.0), 0.0)
        peak = int(34 + 28 * breath + 55 * hov)
        # Radius based on the SHORT side: wide rows (Settings) do not produce huge
        # blobs, while square icons keep a full halo.
        base = min(draw_rect.w, draw_rect.h)
        size = int(base * (1.7 + 0.2 * breath))
        if size <= 0:
            return
        # Cached soft radial halo, warm tinted and modulated in intensity.
        halo = self._get_halo().copy()
        halo.fill((225, 90, 35, 255), special_flags=pygame.BLEND_RGBA_MULT)            # tint
        halo.fill((255, 255, 255, max(0, min(255, peak))), special_flags=pygame.BLEND_RGBA_MULT)  # intensity
        halo = pygame.transform.smoothscale(halo, (size, size))
        screen.blit(halo, halo.get_rect(center=draw_rect.center))

    def _get_halo(self) -> pygame.Surface:
        """Radial white halo (solid centre, transparent rim), built once."""
        if self._halo is None:
            s = 128
            h = pygame.Surface((s, s), pygame.SRCALPHA)
            cx = s // 2
            for rr in range(cx, 0, -1):
                t = rr / cx  # 1 at the rim .. 0 at the centre
                a = int(110 * (1.0 - t) ** 2)
                if a > 0:
                    pygame.draw.circle(h, (255, 255, 255, a), (cx, cx), rr)
            self._halo = h
        return self._halo

    def draw_overlay(self, ms, screen, sw, sh) -> None:
        if not (self.fx_on(ms, "grain") and not self.reduced(ms)):
            return
        amt = as_float(self.theme.decor("grain", 0.0), 0.0)
        if amt <= 0:
            return
        tile = self._grain
        if tile is None:
            tile = pygame.Surface((128, 128), pygame.SRCALPHA)
            rnd = random.Random(20260611)
            a_max = max(1, int(70 * amt))
            for _ in range(900):
                tile.set_at((rnd.randint(0, 127), rnd.randint(0, 127)),
                            (255, 255, 255, rnd.randint(0, a_max)))
            self._grain = tile
        ox = int((self._t * 23) % 128)
        oy = int((self._t * 17) % 128)
        for x in range(-ox, sw, 128):
            for y in range(-oy, sh, 128):
                screen.blit(tile, (x, y))
