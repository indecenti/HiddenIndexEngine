"""
engine/minigames/touch_controls.py

Controlli touch on-screen riutilizzabili per i minigiochi.
Attivi solo su Android (touch); su desktop restano nascosti e inerti, così la
giocabilità da tastiera/mouse resta invariata.

Uso tipico in un minigioco:

    from engine.minigames.touch_controls import TouchControls

    # in start()/__init__:
    self.touch = TouchControls(self.scaling_manager)
    self.touch.add("left",  rect, glyph="left")
    self.touch.add("rotate", rect, glyph="rotate")

    # in handle_event(event):
    bid = self.touch.handle_event(event)
    if bid == "rotate": self.rotate_piece()
    if bid == "left":   self._move_horizontal(-1)   # azione immediata

    # in update(dt) per azioni continue (tenere premuto):
    if self.touch.is_held("down"): self.soft_drop()

    # in draw():
    self.touch.draw(self.screen)

Gestisce input a singolo puntatore tramite gli eventi MOUSEBUTTON* che SDL
sintetizza dal tocco primario su Android (semplice e affidabile).
"""

from __future__ import annotations

import pygame
from engine.utils import is_android_runtime


class _Button:
    __slots__ = ("bid", "rect", "glyph", "label", "color")

    def __init__(self, bid, rect, glyph, label, color):
        self.bid = bid
        self.rect = rect
        self.glyph = glyph
        self.label = label
        self.color = color


class TouchControls:
    def __init__(self, scaling_manager, enabled: bool | None = None) -> None:
        self.sm = scaling_manager
        # Di default attivi solo su Android (touch). Forzabile per test.
        self.enabled = is_android_runtime() if enabled is None else enabled
        self._android = is_android_runtime()
        self._buttons: list[_Button] = []
        self._held: set[str] = set()       # bottoni attualmente tenuti premuti
        self._active: str | None = None     # bottone sotto il puntatore corrente
        self._font_cache: dict[int, pygame.font.Font] = {}
        # Cache del chrome statico del bottone (sfondo+bordo+glifo), keyed da
        # (w, h, glyph, held, color). Il chrome non cambia tra frame finche' lo
        # stato non cambia: lo renderizziamo una volta su una Surface convertita
        # e blittiamo quella, evitando una Surface SRCALPHA + draw per-frame.
        self._chrome_cache: dict[tuple, pygame.Surface] = {}
        # Cache delle label gia' renderizzate, keyed da (label, size, color).
        self._label_cache: dict[tuple, pygame.Surface] = {}

    # ------------------------------------------------------------------
    def add(self, bid: str, rect: pygame.Rect, glyph: str = "", label: str = "",
            color: tuple | None = None) -> None:
        self._buttons.append(_Button(bid, pygame.Rect(rect), glyph, label,
                                      color or (60, 200, 255)))

    def clear(self) -> None:
        self._buttons.clear()
        self._held.clear()
        self._active = None
        self._chrome_cache.clear()
        self._label_cache.clear()

    def _hit(self, pos) -> str | None:
        for b in self._buttons:
            if b.rect.collidepoint(pos):
                return b.bid
        return None

    # ------------------------------------------------------------------
    def handle_event(self, event: pygame.event.Event) -> str | None:
        """Ritorna il bid del bottone appena PREMUTO (per azioni immediate),
        altrimenti None. Aggiorna anche lo stato 'tenuto premuto'."""
        if not self.enabled:
            return None
        if event.type == pygame.MOUSEBUTTONDOWN:
            bid = self._hit(event.pos)
            if bid is not None:
                self._active = bid
                self._held.add(bid)
                return bid
        elif event.type == pygame.MOUSEBUTTONUP:
            if self._active is not None:
                self._held.discard(self._active)
                self._active = None
        elif event.type == pygame.MOUSEMOTION:
            # Se trascino fuori dal bottone attivo, rilascio lo stato 'held'
            if self._active is not None and (event.buttons and event.buttons[0]):
                if self._hit(event.pos) != self._active:
                    self._held.discard(self._active)
        return None

    def is_held(self, bid: str) -> bool:
        return bid in self._held

    def point_on_button(self, pos) -> bool:
        """True se il punto è sopra un qualsiasi bottone (per evitare che il
        tocco su un controllo venga interpretato anche come input di gioco)."""
        if not self.enabled:
            return False
        return self._hit(pos) is not None

    def reset_state(self) -> None:
        self._held.clear()
        self._active = None

    # ------------------------------------------------------------------
    def _font(self, size: int) -> pygame.font.Font:
        f = self._font_cache.get(size)
        if f is None:
            f = pygame.font.SysFont("Arial", size, bold=True)
            self._font_cache[size] = f
        return f

    def _draw_glyph(self, surf, glyph, rect, col):
        cx, cy = rect.center
        r = int(min(rect.w, rect.h) * 0.26)
        if glyph == "left":
            pygame.draw.polygon(surf, col, [(cx + r, cy - r), (cx + r, cy + r), (cx - r, cy)])
        elif glyph == "right":
            pygame.draw.polygon(surf, col, [(cx - r, cy - r), (cx - r, cy + r), (cx + r, cy)])
        elif glyph == "down":
            pygame.draw.polygon(surf, col, [(cx - r, cy - r), (cx + r, cy - r), (cx, cy + r)])
        elif glyph == "up":
            pygame.draw.polygon(surf, col, [(cx - r, cy + r), (cx + r, cy + r), (cx, cy - r)])
        elif glyph == "rotate":
            pygame.draw.arc(surf, col, (cx - r, cy - r, 2 * r, 2 * r), 0.6, 5.5, max(2, r // 4))
            pygame.draw.polygon(surf, col, [(cx + r, cy - r // 2), (cx + r + r // 2, cy), (cx + r - r // 3, cy + r // 3)])
        elif glyph == "drop":
            pygame.draw.polygon(surf, col, [(cx - r, cy - r), (cx + r, cy - r), (cx, cy + r)])
            pygame.draw.rect(surf, col, (cx - r, cy + r - max(2, r // 3), 2 * r, max(2, r // 3)))
        elif glyph == "fire":
            pygame.draw.circle(surf, col, (cx, cy), r)
        else:
            # nessun glifo: eventuale label testuale
            pass

    def _get_chrome(self, b, held: bool) -> pygame.Surface:
        """Surface composita (sfondo + bordo + glifo) cachata per bottone.
        Dipende solo da (w, h, glyph, held, color): finche' lo stato non cambia
        e' un cache-hit, quindi nessuna Surface SRCALPHA ne' pygame.draw per
        frame. Risultato identico al rendering diretto su entrambe le piattaforme."""
        key = (b.rect.w, b.rect.h, b.glyph, held, b.color)
        surf = self._chrome_cache.get(key)
        if surf is not None:
            return surf
        w, h = b.rect.w, b.rect.h
        base_alpha = 150 if held else 90
        btn_surf = pygame.Surface((w, h), pygame.SRCALPHA)
        radius = min(w, h) // 4
        pygame.draw.rect(btn_surf, (15, 18, 28, base_alpha + 40),
                         (0, 0, w, h), border_radius=radius)
        border_col = (*b.color, 220 if held else 130)
        pygame.draw.rect(btn_surf, border_col, (0, 0, w, h),
                         width=max(2, w // 40), border_radius=radius)
        if b.glyph:
            glyph_col = b.color if held else tuple(int(c * 0.85) for c in b.color)
            # _draw_glyph usa rect.center/rect.w: passiamo un rect locale.
            self._draw_glyph(btn_surf, b.glyph, pygame.Rect(0, 0, w, h), glyph_col)
        btn_surf = btn_surf.convert_alpha()
        self._chrome_cache[key] = btn_surf
        return btn_surf

    def _get_label(self, label: str, size: int, color: tuple) -> pygame.Surface:
        """font.render cachato per (label, size, color): evita di rendere lo
        stesso testo ogni frame (op cara su ARM)."""
        key = (label, size, color)
        surf = self._label_cache.get(key)
        if surf is None:
            surf = self._font(size).render(label, True, color).convert_alpha()
            self._label_cache[key] = surf
        return surf

    def draw(self, screen: pygame.Surface) -> None:
        if not self.enabled or not self._buttons:
            return
        for b in self._buttons:
            held = b.bid in self._held
            screen.blit(self._get_chrome(b, held), b.rect.topleft)
            if b.label:
                txt = self._get_label(b.label, max(12, b.rect.h // 4), b.color)
                screen.blit(txt, txt.get_rect(center=b.rect.center))
