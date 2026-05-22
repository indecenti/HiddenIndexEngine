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
        self._buttons: list[_Button] = []
        self._held: set[str] = set()       # bottoni attualmente tenuti premuti
        self._active: str | None = None     # bottone sotto il puntatore corrente
        self._font_cache: dict[int, pygame.font.Font] = {}

    # ------------------------------------------------------------------
    def add(self, bid: str, rect: pygame.Rect, glyph: str = "", label: str = "",
            color: tuple | None = None) -> None:
        self._buttons.append(_Button(bid, pygame.Rect(rect), glyph, label,
                                      color or (60, 200, 255)))

    def clear(self) -> None:
        self._buttons.clear()
        self._held.clear()
        self._active = None

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

    def draw(self, screen: pygame.Surface) -> None:
        if not self.enabled or not self._buttons:
            return
        for b in self._buttons:
            held = b.bid in self._held
            base_alpha = 150 if held else 90
            btn_surf = pygame.Surface((b.rect.w, b.rect.h), pygame.SRCALPHA)
            radius = min(b.rect.w, b.rect.h) // 4
            pygame.draw.rect(btn_surf, (15, 18, 28, base_alpha + 40),
                             (0, 0, b.rect.w, b.rect.h), border_radius=radius)
            border_col = (*b.color, 220 if held else 130)
            pygame.draw.rect(btn_surf, border_col, (0, 0, b.rect.w, b.rect.h),
                             width=max(2, b.rect.w // 40), border_radius=radius)
            screen.blit(btn_surf, b.rect.topleft)
            glyph_col = (*b.color, 255) if held else (*b.color, 200)
            if b.glyph:
                self._draw_glyph(screen, b.glyph, b.rect, b.color if held else tuple(int(c * 0.85) for c in b.color))
            if b.label:
                f = self._font(max(12, b.rect.h // 4))
                txt = f.render(b.label, True, b.color)
                screen.blit(txt, txt.get_rect(center=b.rect.center))
