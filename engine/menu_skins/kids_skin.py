"""
engine/menu_skins/kids_skin.py

KidsSkin - "Playground" direction: sunny and playful. It replaces the background
with a gradient sky + a sun with rays, puts a white "sticker" plate with a toy
shadow behind every button/card, bounces the round title and rains confetti.
Confetti and bounce switch off under reduced-motion; sky, sun and plates stay
(they are cheap) so the identity survives on mobile too.
"""

import math
import random
import pygame

from .base import SurfaceCache, as_float, as_int, as_rgb, cached_title
from .default_skin import DefaultSkin
from engine.utils import is_android_runtime

_ANDROID = is_android_runtime()

# Confetti bounds: density comes from theme.json (authored data), so it is
# clamped instead of being trusted as a particle count.
CONFETTI_MAX = 120
CONFETTI_SIZE_MIN = 5
CONFETTI_SIZE_MAX = 9

_CONFETTI_PALETTE = [
    (255, 122, 162),
    (255, 215, 68),
    (88, 214, 141),
    (255, 255, 255),
    (120, 200, 246),
]


class KidsSkin(DefaultSkin):
    id = "kids"

    def __init__(self, theme) -> None:
        super().__init__(theme)
        self._confetti: list[dict] = []
        # Cache of the static sun elements (halo + unrotated base rays), rebuilt
        # only when size/colour change. Avoids an SRCALPHA allocation plus many
        # draws every frame in the background draw path.
        self._sun_cache_key = None
        self._sun_halo = None
        self._sun_ray_base = None
        # (colour, size) -> confetto chip. The chips are static: only their
        # position and rotation change, so the surface is built once per look.
        self._chip_cache = SurfaceCache()

    # -- Background: sky + sun ------------------------------------------------
    def draw_background_pre(self, ms, screen, sw, sh) -> None:
        theme = self.theme
        if theme.background("mode", "image") != "sky":
            return
        self._draw_sky(screen, sw, sh,
                       as_rgb(theme.background("sky_top", None), (98, 192, 246)),
                       as_rgb(theme.background("sky_bottom", None), (116, 207, 154)))
        if theme.background("sun", False):
            self._draw_sun(screen, sw, sh,
                           as_rgb(theme.background("sun_color", None), (255, 215, 68)))

    def _draw_sky(self, screen, sw, sh, top, bot) -> None:
        bands = 24
        for i in range(bands):
            t = i / (bands - 1)
            c = (int(top[0] + (bot[0] - top[0]) * t),
                 int(top[1] + (bot[1] - top[1]) * t),
                 int(top[2] + (bot[2] - top[2]) * t))
            y = int(sh * i / bands)
            pygame.draw.rect(screen, c, (0, y, sw, int(sh / bands) + 1))

    def _draw_sun(self, screen, sw, sh, col) -> None:
        cx, cy = int(sw * 0.86), int(sh * 0.15)
        r = max(8, int(min(sw, sh) * 0.09))
        self._ensure_sun_cache(r, col)
        ang = self._t * 0.4
        if _ANDROID:
            # On mobile the r*5 SRCALPHA allocation + 8 lines per frame is costly:
            # rotate the ready-made ray surface instead (a single transform). Line
            # rasterisation differs a hair from the original, so this branch is
            # gated; the desktop look stays identical.
            ray = pygame.transform.rotate(self._sun_ray_base, -math.degrees(ang))
            rrect = ray.get_rect(center=(cx, cy))
            screen.blit(ray, rrect.topleft)
        else:
            # Desktop: original behaviour, rays redrawn per frame.
            ray = pygame.Surface((r * 5, r * 5), pygame.SRCALPHA)
            cc = (r * 2.5, r * 2.5)
            for i in range(8):
                a = ang + i * (math.pi / 4)
                pygame.draw.line(ray, (col[0], col[1], col[2], 110), cc,
                                 (cc[0] + math.cos(a) * r * 2.3, cc[1] + math.sin(a) * r * 2.3), 5)
            screen.blit(ray, (cx - int(r * 2.5), cy - int(r * 2.5)))
        # The halo is a static circle: pure cache, pixel identical everywhere.
        screen.blit(self._sun_halo, (cx - int(r * 1.5), cy - int(r * 1.5)))
        pygame.draw.circle(screen, tuple(col), (cx, cy), r)

    def _ensure_sun_cache(self, r, col) -> None:
        # Rebuild halo and base rays only when size or colour change.
        key = (r, col[0], col[1], col[2])
        if key == self._sun_cache_key:
            return
        self._sun_cache_key = key
        # Static halo (soft circle), identical every frame -> pure cache.
        halo = pygame.Surface((r * 3, r * 3), pygame.SRCALPHA)
        pygame.draw.circle(halo, (col[0], col[1], col[2], 60),
                           (int(r * 1.5), int(r * 1.5)), int(r * 1.4))
        self._sun_halo = halo
        # Base rays at angle 0: the per-frame rotation works on this copy.
        ray = pygame.Surface((r * 5, r * 5), pygame.SRCALPHA)
        cc = (r * 2.5, r * 2.5)
        for i in range(8):
            a = i * (math.pi / 4)
            pygame.draw.line(ray, (col[0], col[1], col[2], 110), cc,
                             (cc[0] + math.cos(a) * r * 2.3, cc[1] + math.sin(a) * r * 2.3), 5)
        self._sun_ray_base = ray

    _ARRANGE_STATES = ("main", "pause")

    def arrange(self, ms) -> None:
        # Cheerful arc composition (only where title/cards stay clear).
        if ms.state not in self._ARRANGE_STATES:
            return
        carousel = [b for b in ms.buttons
                    if not (b.ref_rect.x < 100 and b.ref_rect.y < 120)]
        n = max(1, len(carousel))
        for i, b in enumerate(carousel):
            t = (i + 0.5) / n
            b.ref_rect.y -= int(math.sin(t * math.pi) * 26)

    # -- "Sticker" plate behind icon buttons / settings rows -------------------
    def behind_button(self, ms, screen, b, draw_rect, is_locked) -> None:
        # Preview cards (levels/scenes) already have their look: no plate.
        if b.image:
            return
        # Plate only on icon buttons or settings rows, not on wide cards (it
        # would cover the content and the title).
        if ms.state != "settings" and draw_rect.w > 260:
            return
        rad = as_int(self.theme.decor("card_radius", 24), 24)
        border = as_rgb(self.theme.decor("card_border", None), (255, 255, 255))
        shadow = as_rgb(self.theme.decor("toy_shadow", None), (42, 126, 192))
        pad = int(min(draw_rect.w, draw_rect.h) * 0.10)
        plate = draw_rect.inflate(pad, pad)
        sh_off = max(3, int(draw_rect.h * 0.06))
        pygame.draw.rect(screen, shadow, plate.move(0, sh_off), border_radius=rad)
        pygame.draw.rect(screen, border, plate, border_radius=rad)

    # -- Round bouncing title --------------------------------------------------
    def draw_title(self, ms, screen) -> None:
        theme = self.theme
        sm = ms.scaling_manager
        text = ms._state_title_text()
        if not text:
            return
        size = as_int(theme.layout("title_font_size", 46), 46)
        col = theme.color3("text_normal")
        sh_col = as_rgb(theme.decor("toy_shadow", None), (42, 126, 192))
        # The two font.render calls (text + shadow) used to run EVERY frame while
        # only the bounce offset changes. Cache both surfaces keyed on the SCALED
        # size, so a resize/fullscreen switch still rebuilds them.
        key = (text, sm.scale_value(size), col, sh_col)

        def _build():
            font = theme.get_font_role("title", size, sm)
            return (font.render(text, True, col), font.render(text, True, sh_col))

        surf, sh_surf = cached_title(self, key, _build)
        bounce = 0
        if self.fx_on(ms, "bounce") and not self.reduced(ms):
            bounce = int(sm.scale_value(6) * (0.5 + 0.5 * math.sin(self._t * 3.2)))
        tx = (screen.get_width() - surf.get_width()) // 2
        ty = sm.scale_value(as_int(theme.layout("title_y_offset", 100), 100)) - bounce
        screen.blit(sh_surf, (tx, ty + max(2, sm.scale_value(3))))
        screen.blit(surf, (tx, ty))

    # -- Confetti --------------------------------------------------------------
    def update(self, ms, dt) -> None:
        super().update(ms, dt)
        if not (self.fx_on(ms, "confetti") and not self.reduced(ms)):
            if self._confetti:
                self._confetti = []
            return
        target = max(0, min(CONFETTI_MAX, as_int(self.theme.particles_cfg("density", 22), 22)))
        while len(self._confetti) < target:
            self._confetti.append(self._new_confetto())
        del self._confetti[target:]   # a lowered density must shed the extras
        dt = as_float(dt, 0.0)
        for p in self._confetti:
            p["x"] += p["vx"] * dt
            p["y"] += p["vy"] * dt
            p["rot"] += p["vr"] * dt
            if p["y"] > 1.15:
                self._reset_confetto(p)

    def _new_confetto(self) -> dict:
        p = {"color": random.choice(_CONFETTI_PALETTE),
             "size": random.randint(CONFETTI_SIZE_MIN, CONFETTI_SIZE_MAX),
             "vx": (random.random() - 0.5) * 0.06,
             "vy": 0.10 + random.random() * 0.18,
             "vr": (random.random() - 0.5) * 4.0,
             "rot": random.random() * math.pi}
        self._reset_confetto(p)
        p["y"] = random.random()  # first fill spread over the whole height
        return p

    def _reset_confetto(self, p: dict) -> None:
        p["x"] = random.random()
        p["y"] = -0.05 - random.random() * 0.2

    def draw_overlay(self, ms, screen, sw, sh) -> None:
        if not self._confetti:
            return
        for p in self._confetti:
            # Only the rotation changes per frame: the flat chip is cached by
            # (colour, size) instead of being allocated and filled every frame
            # for every confetto.
            base = self._chip_cache.get_or_build(
                (p["color"], p["size"]), lambda p=p: self._build_chip(p))
            chip = pygame.transform.rotate(base, math.degrees(p["rot"]))
            screen.blit(chip, (int(p["x"] * sw), int(p["y"] * sh)))

    @staticmethod
    def _build_chip(p: dict) -> pygame.Surface:
        s = p["size"]
        chip = pygame.Surface((s * 2, s), pygame.SRCALPHA)
        chip.fill(p["color"])
        return chip
