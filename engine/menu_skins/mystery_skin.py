"""
engine/menu_skins/mystery_skin.py

MysterySkin — direzione "The Detective": noir investigativo, toni caldi
desaturati, vignettatura forte, pulviscolo che fluttua nella luce, titolo serif
spaziato. Eredita da DefaultSkin (il quale applica gia' la seppia alle card del
tema mystery via la flag sepia_overlay).
"""

import math
import random
import pygame

from .default_skin import DefaultSkin


class MysterySkin(DefaultSkin):
    id = "mystery"

    def __init__(self, theme) -> None:
        super().__init__(theme)
        self._dust: list[dict] = []
        self._vig = None
        # Cache dei glow del pulviscolo, keyed da (raggio, colore). Evita di
        # allocare+disegnare una nuova Surface SRCALPHA per ogni mote ogni frame
        # (era ~density blit ricostruiti per-frame nel path di disegno).
        self._mote_cache: dict = {}

    def draw_background_pre(self, ms, screen, sw, sh) -> None:
        if self.fx_on(ms, "vignette"):
            self._vignette(screen, sw, sh)

    def _vignette(self, screen, sw, sh) -> None:
        amt = float(self.theme.decor("vignette", 0.7))
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
        target = int(self.theme.particles_cfg("density", 22))
        while len(self._dust) < target:
            self._dust.append(self._new_mote())
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
        # Glow del mote pre-renderizzato a alpha pieno (255). L'alpha variabile
        # per-frame viene applicato via set_alpha sul blit -> stessi pixel del
        # disegno diretto ma senza alloc+draw ogni frame.
        key = (rr, col[0], col[1], col[2])
        g = self._mote_cache.get(key)
        if g is None:
            g = pygame.Surface((rr * 4, rr * 4), pygame.SRCALPHA)
            pygame.draw.circle(g, (col[0], col[1], col[2], 255), (rr * 2, rr * 2), rr)
            self._mote_cache[key] = g
        return g

    def draw_overlay(self, ms, screen, sw, sh) -> None:
        if not self._dust:
            return
        col = self.theme.particles_cfg("color", [185, 150, 92])
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
        size = theme.layout("title_font_size", 44)
        font = theme.get_font_role("title", size, sm)
        spacing = sm.scale_value(int((theme._typography.get("title", {}) or {}).get("spacing", 2)))
        col = theme.color3("text_hover")
        surf = theme.render_spaced(font, text, col, spacing)
        tx = (screen.get_width() - surf.get_width()) // 2
        ty = sm.scale_value(theme.layout("title_y_offset", 105))
        shadow = theme.render_spaced(font, text, (10, 6, 2), spacing)
        shadow.set_alpha(185)
        screen.blit(shadow, (tx + 2, ty + 2))
        screen.blit(surf, (tx, ty))
