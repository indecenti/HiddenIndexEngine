"""
engine/menu_skins/horror_skin.py

HorrorSkin — direzione "Nightmare": cupo e teso. Nebbia rossastra che scorre
sotto la torcia (gia' gestita dal core via flashlight_fx), grana fine, alone di
candela dietro le icone, micro-jitter dei bottoni e titolo serif spezzato,
spaziato e con flicker. Tutti gli effetti pesanti degradano in reduced-motion.
"""

import math
import random
import pygame

from engine.utils import is_android_runtime
from .default_skin import DefaultSkin

_ANDROID = is_android_runtime()


class HorrorSkin(DefaultSkin):
    id = "horror"

    def __init__(self, theme) -> None:
        super().__init__(theme)
        self._grain = None  # tile di rumore in cache
        self._halo = None   # alone radiale morbido in cache (candela)
        self._title_cache_key = None  # chiave (text, size, spacing, col, glow_col)
        self._title_surf = None       # superficie titolo renderizzata in cache
        self._title_glow = None       # superficie alone titolo in cache

    # Niente aurora/lucciole: solo nebbia.
    def draw_background_pre(self, ms, screen, sw, sh) -> None:
        if self.fx_on(ms, "fog") and not self.reduced(ms):
            self._draw_fog(screen, sw, sh)

    def _draw_fog(self, screen, sw, sh) -> None:
        col = self.theme.background("fog_color", [70, 40, 40])
        t = self._t
        surf = pygame.Surface((sw, sh), pygame.SRCALPHA)
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
        # Composizione "sparse": altezze irregolari (solo dove non collide col titolo).
        if ms.state not in self._ARRANGE_STATES:
            return
        i = 0
        for b in ms.buttons:
            if b.ref_rect.x < 100 and b.ref_rect.y < 120:  # bottoni fissi (back/quit)
                continue
            b.ref_rect.y += int(math.sin(i * 1.7) * 22 + math.sin(i * 0.5) * 10)
            i += 1

    def draw_title(self, ms, screen) -> None:
        theme = self.theme
        sm = ms.scaling_manager
        text = ms._state_title_text()
        if not text:
            return
        size = theme.layout("title_font_size", 48)
        spacing = sm.scale_value(int((theme._typography.get("title", {}) or {}).get("spacing", 4)))
        up = text.upper()
        col = theme.color3("text_hover")
        glow_col = (90, 0, 0)
        # Cache delle superfici titolo: render_spaced fa una font.render PER CARATTERE
        # (x2: testo + alone), ricostruita ogni frame nel path di disegno. Gli unici
        # input che cambiano l'aspetto sono testo/size/spacing/colore; il flicker e'
        # solo set_alpha (sotto). Cachiamo i glifi composti e ri-applichiamo l'alpha
        # per-frame: stessi pixel su entrambe le piattaforme, ma niente re-render.
        # NB: la key deve includere la dimensione SCALATA (sm.scale_value(size)),
        # non solo la costante 'size': il font reale e' scalato da get_font_role,
        # quindi senza di essa il titolo resterebbe alla vecchia risoluzione dopo
        # un resize/fullscreen.
        key = (up, sm.scale_value(size), spacing, col, glow_col)
        if key != self._title_cache_key:
            font = theme.get_font_role("title", size, sm)
            self._title_surf = theme.render_spaced(font, up, col, spacing)
            self._title_glow = theme.render_spaced(font, up, glow_col, spacing)
            self._title_cache_key = key
        surf = self._title_surf
        glow = self._title_glow
        alpha = int(255 * theme.flicker_alpha_mod()) if self.fx_on(ms, "flicker") else 255
        surf.set_alpha(alpha)
        glow.set_alpha(min(alpha, 130))
        tx = (screen.get_width() - surf.get_width()) // 2
        ty = sm.scale_value(theme.layout("title_y_offset", 100))
        screen.blit(glow, (tx + 2, ty + 2))
        screen.blit(surf, (tx, ty))

    def button_jitter(self, ms, b):
        if not (self.fx_on(ms, "jitter") and not self.reduced(ms)):
            return (0.0, 0.0)
        amp = float(self.theme.motion("jitter", 1.0))
        if not getattr(b, "hovered", False):
            amp *= 0.4
        t = self._t * 30.0
        return (math.sin(t + b.ref_rect.x) * amp, math.cos(t * 0.9 + b.ref_rect.y) * amp)

    def behind_button(self, ms, screen, b, draw_rect, is_locked) -> None:
        # Alone caldo "candela" dietro le icone (non sulle card immagine/locked).
        if b.image or is_locked or self.reduced(ms):
            return
        if not self.theme.decor("candle_glow", False):
            return
        breath = 0.5 + 0.5 * math.sin(self._t * 4.0)
        hov = getattr(b, "hover_time", 0.0)
        peak = int(34 + 28 * breath + 55 * hov)
        # Raggio basato sul lato CORTO: cosi' le righe larghe (Impostazioni) non
        # generano blob enormi, ma le icone quadrate mantengono un alone pieno.
        base = min(draw_rect.w, draw_rect.h)
        size = int(base * (1.7 + 0.2 * breath))
        if size <= 0:
            return
        # Alone radiale morbido in cache, tinto di caldo e modulato in intensita'.
        halo = self._get_halo().copy()
        halo.fill((225, 90, 35, 255), special_flags=pygame.BLEND_RGBA_MULT)            # tinta
        halo.fill((255, 255, 255, max(0, min(255, peak))), special_flags=pygame.BLEND_RGBA_MULT)  # intensita'
        halo = pygame.transform.smoothscale(halo, (size, size))
        screen.blit(halo, halo.get_rect(center=draw_rect.center))

    def _get_halo(self) -> pygame.Surface:
        """Alone bianco radiale (centro pieno, bordo trasparente), costruito una volta."""
        if self._halo is None:
            s = 128
            h = pygame.Surface((s, s), pygame.SRCALPHA)
            cx = s // 2
            for rr in range(cx, 0, -1):
                t = rr / cx  # 1 al bordo .. 0 al centro
                a = int(110 * (1.0 - t) ** 2)
                if a > 0:
                    pygame.draw.circle(h, (255, 255, 255, a), (cx, cx), rr)
            self._halo = h
        return self._halo

    def draw_overlay(self, ms, screen, sw, sh) -> None:
        if not (self.fx_on(ms, "grain") and not self.reduced(ms)):
            return
        amt = float(self.theme.decor("grain", 0.0))
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
