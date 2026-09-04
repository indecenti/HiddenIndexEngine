"""
engine/menu_skins/default_skin.py

DefaultSkin - "Clean" direction: sober and elegant. It only adds a soft aurora
at the top and a few fireflies when the theme asks for them (background.aurora /
particles.type == 'fireflies'). Everything else stays with the core renderer:
this is the guaranteed fallback and introduces no regression on themes that do
not declare the newer sections.
"""

import math
import pygame

from .base import MenuSkin, SurfaceCache, as_float, as_int, as_rgb
from engine.utils import is_android_runtime

# Runtime flag: the caching below is visually neutral (same pixels) and stays
# active on both platforms; the flag is available for gated branches, but this
# skin does not alter the desktop look.
_ANDROID = is_android_runtime()


class DefaultSkin(MenuSkin):
    id = "default"

    def __init__(self, theme) -> None:
        super().__init__(theme)
        # Cache of the large/expensive SRCALPHA surfaces that would otherwise be
        # rebuilt per frame: the aurora (fullscreen width, static) and the blurred
        # shadows of the glass chips (expensive blur, static per size). Blitting a
        # large SRCALPHA every frame is costly on a mobile GPU; rebuilding it with
        # many draws + blur is worse. Build once, re-blit, invalidate on resize.
        self._aurora_cache = None      # tuple(key) -> Surface
        self._aurora_key = None
        # (w, h, rad) -> blurred surface. Bounded LRU with gradual eviction: a
        # plain dict cleared when full rebuilt every chip on the same frame.
        self._chip_shadow_cache = SurfaceCache()

    def draw_background_pre(self, ms, screen, sw, sh) -> None:
        theme = self.theme
        if theme.background("aurora", False) and self.fx_on(ms, "aurora"):
            self._draw_aurora(screen, sw, sh,
                              as_rgb(theme.background("aurora_color", None), (96, 166, 240)))
        if theme.particles_cfg("type", "none") == "fireflies" \
                and self.fx_on(ms, "particles") and not self.reduced(ms):
            self._draw_fireflies(screen, sw, sh)

    def _draw_aurora(self, screen, sw, sh, col) -> None:
        h = int(sh * 0.42)
        if h <= 0 or sw <= 0:
            return
        # The aurora is STATIC (it only depends on size + colour): it used to be
        # rebuilt from scratch every frame (fullscreen-width SRCALPHA surface +
        # 14 draw.circle). Build it once and re-blit; invalidate on resize/colour.
        # It stays SRCALPHA (an additive veil over the background) but the cached
        # blit is visually identical on desktop and Android.
        key = (sw, h, int(col[0]), int(col[1]), int(col[2]))
        if self._aurora_key != key or self._aurora_cache is None:
            surf = pygame.Surface((sw, h), pygame.SRCALPHA)
            cx = sw // 2
            # Many low-alpha layers: soft falloff, no visible banding.
            layers = 14
            for i in range(layers):
                t = i / (layers - 1)
                r = int((sw * 0.62) * (0.18 + 0.82 * t))
                a = int(11 * (1.0 - t))
                if a <= 0 or r <= 0:
                    continue
                pygame.draw.circle(surf, (col[0], col[1], col[2], a), (cx, 0), r)
            self._aurora_cache = surf
            self._aurora_key = key
        screen.blit(self._aurora_cache, (0, 0))

    def _draw_fireflies(self, screen, sw, sh) -> None:
        col = as_rgb(self.theme.particles_cfg("color", None), (188, 212, 245))
        n = max(0, as_int(self.theme.particles_cfg("density", 7), 7))
        t = self._t
        for i in range(n):
            phi = i * 2.39996323  # golden angle: non repeating distribution
            x = (0.5 + 0.45 * math.sin(t * 0.25 + phi)) * sw
            y = (0.18 + 0.62 * (0.5 + 0.5 * math.sin(t * 0.17 + phi * 1.7))) * sh
            tw = 0.5 + 0.5 * math.sin(t * 2.0 + phi * 3.0)  # twinkle 0..1
            r = max(1, int(2 + 1.5 * tw))
            a = int(90 + 130 * tw)
            g = pygame.Surface((r * 6, r * 6), pygame.SRCALPHA)
            c = (r * 3, r * 3)
            pygame.draw.circle(g, (col[0], col[1], col[2], a // 4), c, r * 3)  # alone morbido
            pygame.draw.circle(g, (col[0], col[1], col[2], a), c, r)            # nucleo
            pygame.draw.circle(g, (255, 255, 255, min(255, a + 40)), c, max(1, r - 1))  # luce
            screen.blit(g, (int(x) - r * 3, int(y) - r * 3))

    def behind_button(self, ms, screen, b, draw_rect, is_locked) -> None:
        # Soft "glass" chip behind the icons: it gives a surface to the thin
        # line-art icons (e.g. the system set), keeping them readable and elegant.
        # Active only when the theme asks for it (decor.icon_chip).
        if b.image or not self.theme.decor("icon_chip", False):
            return
        # Square tiles only (icons): no chip behind the wide rows (Settings).
        if draw_rect.w > draw_rect.h * 1.5 or draw_rect.h > draw_rect.w * 1.5:
            return
        theme = self.theme
        ht = as_float(getattr(b, "hover_time", 0.0), 0.0)
        pad = int(min(draw_rect.w, draw_rect.h) * 0.10)
        chip = draw_rect.inflate(pad * 2, pad * 2)
        rad = max(14, int(min(chip.w, chip.h) * 0.30))
        if _ANDROID:
            # Android: OPAQUE chip (one filled draw.rect + border). The blurred
            # shadow and the glass were TWO SRCALPHA surfaces per button EVERY
            # frame: per-pixel-alpha blits are very costly on a mobile GPU. Here
            # no alpha, just two direct draw.rect -> readable and very fast.
            pygame.draw.rect(screen, (24, 28, 38), chip, border_radius=rad)
            bc = theme.color3("btn_border_hover") if ht > 0.01 else theme.color3("btn_border_normal")
            pygame.draw.rect(screen, bc, chip, width=2, border_radius=rad)
            return
        # Soft chip shadow (blurred silhouette). It is STATIC per size (it does
        # not depend on hover): it used to be rebuilt + blurred (theme.blur = two
        # smoothscale) for every button EVERY frame. Cached by (w, h, rad); same
        # blur, same blit. Small cache (a handful of chip sizes).
        m = 16

        def _build_shadow():
            shadow = pygame.Surface((chip.w + m * 2, chip.h + m * 2), pygame.SRCALPHA)
            pygame.draw.rect(shadow, (0, 0, 0, 85), (m, m, chip.w, chip.h), border_radius=rad)
            return theme.blur(shadow, 0.22)

        sh = self._chip_shadow_cache.get_or_build((chip.w, chip.h, rad), _build_shadow)
        screen.blit(sh, (chip.x - m, chip.y - m + 6))
        # Glass body + border (accented on hover) + top highlight
        glass = pygame.Surface((chip.w, chip.h), pygame.SRCALPHA)
        pygame.draw.rect(glass, (255, 255, 255, int(20 + 30 * ht)), (0, 0, chip.w, chip.h), border_radius=rad)
        bc = theme.color3("btn_border_hover") if ht > 0.01 else theme.color3("btn_border_normal")
        pygame.draw.rect(glass, (bc[0], bc[1], bc[2], int(55 + 130 * ht)), (0, 0, chip.w, chip.h), width=2, border_radius=rad)
        pygame.draw.line(glass, (255, 255, 255, int(45 + 45 * ht)), (rad, 2), (chip.w - rad, 2), 1)
        screen.blit(glass, chip.topleft)
