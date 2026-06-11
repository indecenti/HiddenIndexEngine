"""
engine/menu_skins/kids_skin.py

KidsSkin — direzione "Playground": solare e giocoso. Sostituisce lo sfondo con
un cielo a gradiente + sole coi raggi, mette una placca bianca "sticker" con
ombra-giocattolo dietro ogni bottone/card, fa rimbalzare il titolo tondo e fa
piovere coriandoli. I coriandoli/bounce si spengono in reduced-motion; cielo,
sole e placche restano (sono leggeri) per mantenere l'identita' anche su mobile.
"""

import math
import random
import pygame

from .default_skin import DefaultSkin

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

    # ── Sfondo: cielo + sole ─────────────────────────────────────────────────
    def draw_background_pre(self, ms, screen, sw, sh) -> None:
        theme = self.theme
        if theme.background("mode", "image") != "sky":
            return
        self._draw_sky(screen, sw, sh,
                       theme.background("sky_top", [98, 192, 246]),
                       theme.background("sky_bottom", [116, 207, 154]))
        if theme.background("sun", False):
            self._draw_sun(screen, sw, sh, theme.background("sun_color", [255, 215, 68]))

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
        ray = pygame.Surface((r * 5, r * 5), pygame.SRCALPHA)
        ang = self._t * 0.4
        cc = (r * 2.5, r * 2.5)
        for i in range(8):
            a = ang + i * (math.pi / 4)
            pygame.draw.line(ray, (col[0], col[1], col[2], 110), cc,
                             (cc[0] + math.cos(a) * r * 2.3, cc[1] + math.sin(a) * r * 2.3), 5)
        screen.blit(ray, (cx - int(r * 2.5), cy - int(r * 2.5)))
        halo = pygame.Surface((r * 3, r * 3), pygame.SRCALPHA)
        pygame.draw.circle(halo, (col[0], col[1], col[2], 60), (int(r * 1.5), int(r * 1.5)), int(r * 1.4))
        screen.blit(halo, (cx - int(r * 1.5), cy - int(r * 1.5)))
        pygame.draw.circle(screen, tuple(col), (cx, cy), r)

    _ARRANGE_STATES = ("main", "pause")

    def arrange(self, ms) -> None:
        # Composizione ad arco allegro (solo dove non collide col titolo/card).
        if ms.state not in self._ARRANGE_STATES:
            return
        carousel = [b for b in ms.buttons
                    if not (b.ref_rect.x < 100 and b.ref_rect.y < 120)]
        n = max(1, len(carousel))
        for i, b in enumerate(carousel):
            t = (i + 0.5) / n
            b.ref_rect.y -= int(math.sin(t * math.pi) * 26)

    # ── Placca "sticker" dietro i bottoni icona / righe impostazioni ─────────
    def behind_button(self, ms, screen, b, draw_rect, is_locked) -> None:
        # Le card con anteprima (livelli/scene) hanno gia' il loro look: niente placca.
        if b.image:
            return
        # Placca solo su bottoni icona o righe impostazioni, non su card larghe
        # (eviterebbe di coprire contenuto e titolo).
        if ms.state != "settings" and draw_rect.w > 260:
            return
        rad = int(self.theme.decor("card_radius", 24))
        border = tuple(self.theme.decor("card_border", [255, 255, 255]))
        shadow = tuple(self.theme.decor("toy_shadow", [42, 126, 192]))
        pad = int(min(draw_rect.w, draw_rect.h) * 0.10)
        plate = draw_rect.inflate(pad, pad)
        sh_off = max(3, int(draw_rect.h * 0.06))
        pygame.draw.rect(screen, shadow, plate.move(0, sh_off), border_radius=rad)
        pygame.draw.rect(screen, border, plate, border_radius=rad)

    # ── Titolo tondo che rimbalza ────────────────────────────────────────────
    def draw_title(self, ms, screen) -> None:
        theme = self.theme
        sm = ms.scaling_manager
        text = ms._state_title_text()
        if not text:
            return
        size = theme.layout("title_font_size", 46)
        font = theme.get_font_role("title", size, sm)
        surf = font.render(text, True, theme.color3("text_normal"))
        bounce = 0
        if self.fx_on(ms, "bounce") and not self.reduced(ms):
            bounce = int(sm.scale_value(6) * (0.5 + 0.5 * math.sin(self._t * 3.2)))
        tx = (screen.get_width() - surf.get_width()) // 2
        ty = sm.scale_value(theme.layout("title_y_offset", 100)) - bounce
        sh_surf = font.render(text, True, tuple(theme.decor("toy_shadow", [42, 126, 192])))
        screen.blit(sh_surf, (tx, ty + max(2, sm.scale_value(3))))
        screen.blit(surf, (tx, ty))

    # ── Coriandoli ───────────────────────────────────────────────────────────
    def update(self, ms, dt) -> None:
        super().update(ms, dt)
        if not (self.fx_on(ms, "confetti") and not self.reduced(ms)):
            if self._confetti:
                self._confetti = []
            return
        target = int(self.theme.particles_cfg("density", 22))
        while len(self._confetti) < target:
            self._confetti.append(self._new_confetto())
        for p in self._confetti:
            p["x"] += p["vx"] * dt
            p["y"] += p["vy"] * dt
            p["rot"] += p["vr"] * dt
            if p["y"] > 1.15:
                self._reset_confetto(p)

    def _new_confetto(self) -> dict:
        p = {"color": random.choice(_CONFETTI_PALETTE),
             "size": random.randint(5, 9),
             "vx": (random.random() - 0.5) * 0.06,
             "vy": 0.10 + random.random() * 0.18,
             "vr": (random.random() - 0.5) * 4.0,
             "rot": random.random() * math.pi}
        self._reset_confetto(p)
        p["y"] = random.random()  # primo riempimento sparso su tutta l'altezza
        return p

    def _reset_confetto(self, p: dict) -> None:
        p["x"] = random.random()
        p["y"] = -0.05 - random.random() * 0.2

    def draw_overlay(self, ms, screen, sw, sh) -> None:
        if not self._confetti:
            return
        for p in self._confetti:
            s = p["size"]
            chip = pygame.Surface((s * 2, s), pygame.SRCALPHA)
            chip.fill(p["color"])
            chip = pygame.transform.rotate(chip, math.degrees(p["rot"]))
            screen.blit(chip, (int(p["x"] * sw), int(p["y"] * sh)))
