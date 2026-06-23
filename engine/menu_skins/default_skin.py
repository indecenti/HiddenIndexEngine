"""
engine/menu_skins/default_skin.py

DefaultSkin — direzione "Clean": sobrio ed elegante. Aggiunge SOLO un'aurora
soffusa in alto e poche lucciole, se il tema le richiede (background.aurora /
particles.type == 'fireflies'). Tutto il resto del rendering resta quello del
core: e' il fallback garantito e non introduce regressioni sui temi che non
dichiarano le nuove sezioni.
"""

import math
import pygame

from .base import MenuSkin
from engine.utils import is_android_runtime

# Flag runtime: il caching qui sotto e' visivamente neutro (stessi pixel) e resta
# attivo su entrambe le piattaforme; il flag e' disponibile per eventuali rami
# gated, ma su questo skin non alteriamo l'aspetto desktop.
_ANDROID = is_android_runtime()


class DefaultSkin(MenuSkin):
    id = "default"

    def __init__(self, theme) -> None:
        super().__init__(theme)
        # Cache surface SRCALPHA grandi/costose ricostruite per-frame: l'aurora
        # (fullscreen-width, statica) e le ombre sfocate dei chip vetro (blur
        # costoso ma statico per dimensione). Il blit di una SRCALPHA grande ogni
        # frame e' caro su GPU mobile; ricostruirla con molte draw + blur lo e'
        # ancora di piu'. Cachiamo una volta e ri-blittiamo, invalidando su resize.
        self._aurora_cache = None      # tuple(key) -> Surface
        self._aurora_key = None
        self._chip_shadow_cache = {}   # (w, h, rad) -> Surface sfocata (statica)

    def draw_background_pre(self, ms, screen, sw, sh) -> None:
        theme = self.theme
        if theme.background("aurora", False) and self.fx_on(ms, "aurora"):
            self._draw_aurora(screen, sw, sh, theme.background("aurora_color", [96, 166, 240]))
        if theme.particles_cfg("type", "none") == "fireflies" \
                and self.fx_on(ms, "particles") and not self.reduced(ms):
            self._draw_fireflies(screen, sw, sh)

    def _draw_aurora(self, screen, sw, sh, col) -> None:
        h = int(sh * 0.42)
        if h <= 0 or sw <= 0:
            return
        # L'aurora e' STATICA (dipende solo da dimensione + colore): la costruivamo
        # da zero ogni frame (Surface SRCALPHA fullscreen-width + 14 draw.circle).
        # La cachiamo una volta e ri-blittiamo; invalida su resize/colore. Resta
        # SRCALPHA (e' un velo additivo sul fondo) ma il blit cachato e' visivamente
        # identico su desktop e Android.
        key = (sw, h, int(col[0]), int(col[1]), int(col[2]))
        if self._aurora_key != key or self._aurora_cache is None:
            surf = pygame.Surface((sw, h), pygame.SRCALPHA)
            cx = sw // 2
            # Molti strati a alpha basso: falloff morbido, niente anelli visibili.
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
        col = self.theme.particles_cfg("color", [188, 212, 245])
        n = int(self.theme.particles_cfg("density", 7))
        t = self._t
        for i in range(n):
            phi = i * 2.39996323  # angolo aureo: distribuzione non ripetitiva
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
        # Chip "vetro" morbido dietro le icone: dà una superficie alle icone
        # line-art sottili (es. set di sistema) rendendole leggibili ed eleganti.
        # Attivo solo se il tema lo richiede (decor.icon_chip).
        if b.image or not self.theme.decor("icon_chip", False):
            return
        # Solo tile quadrate (icone): niente chip dietro le righe larghe (Impostazioni).
        if draw_rect.w > draw_rect.h * 1.5 or draw_rect.h > draw_rect.w * 1.5:
            return
        theme = self.theme
        ht = getattr(b, "hover_time", 0.0)
        pad = int(min(draw_rect.w, draw_rect.h) * 0.10)
        chip = draw_rect.inflate(pad * 2, pad * 2)
        rad = max(14, int(min(chip.w, chip.h) * 0.30))
        if _ANDROID:
            # Android: chip OPACO (un draw.rect pieno + bordo). L'ombra sfocata e il
            # vetro erano DUE Surface SRCALPHA per bottone OGNI frame: il blit
            # per-pixel-alpha e' molto caro su GPU mobile. Qui niente alpha, solo
            # due draw.rect diretti -> leggibile e rapidissimo.
            pygame.draw.rect(screen, (24, 28, 38), chip, border_radius=rad)
            bc = theme.color3("btn_border_hover") if ht > 0.01 else theme.color3("btn_border_normal")
            pygame.draw.rect(screen, bc, chip, width=2, border_radius=rad)
            return
        # Ombra morbida del chip (silhouette sfocata). E' STATICA per dimensione
        # (non dipende da hover): la ricostruivamo + sfocavamo (theme.blur = due
        # smoothscale) per ogni bottone OGNI frame. La cachiamo per (w, h, rad);
        # blur identico, blit invariato. Cache piccola (poche taglie di chip).
        m = 16
        skey = (chip.w, chip.h, rad)
        sh = self._chip_shadow_cache.get(skey)
        if sh is None:
            shadow = pygame.Surface((chip.w + m * 2, chip.h + m * 2), pygame.SRCALPHA)
            pygame.draw.rect(shadow, (0, 0, 0, 85), (m, m, chip.w, chip.h), border_radius=rad)
            sh = theme.blur(shadow, 0.22)
            if len(self._chip_shadow_cache) > 32:
                self._chip_shadow_cache.clear()  # guardia: evita crescita illimitata
            self._chip_shadow_cache[skey] = sh
        screen.blit(sh, (chip.x - m, chip.y - m + 6))
        # Fondo vetro + bordo (accentato in hover) + riflesso superiore
        glass = pygame.Surface((chip.w, chip.h), pygame.SRCALPHA)
        pygame.draw.rect(glass, (255, 255, 255, int(20 + 30 * ht)), (0, 0, chip.w, chip.h), border_radius=rad)
        bc = theme.color3("btn_border_hover") if ht > 0.01 else theme.color3("btn_border_normal")
        pygame.draw.rect(glass, (bc[0], bc[1], bc[2], int(55 + 130 * ht)), (0, 0, chip.w, chip.h), width=2, border_radius=rad)
        pygame.draw.line(glass, (255, 255, 255, int(45 + 45 * ht)), (rad, 2), (chip.w - rad, 2), 1)
        screen.blit(glass, chip.topleft)
