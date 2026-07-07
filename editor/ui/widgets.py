"""
editor/ui/widgets.py

Widget layer minimale per l'editor: unisce disegno, hitbox e stato in oggetti
riusabili, eliminando la doppia manutenzione layout render <-> input dei mixin
immediate-mode. Adozione incrementale: i nuovi sviluppi usano questi widget,
il codice esistente migra pannello per pannello.

Componenti:
- clipboard_get / clipboard_set: appunti di sistema (unica implementazione,
  sostituisce gli helper Tkinter duplicati nei modali).
- TextEditState: stato+logica editing testo (cursore, selezione, Ctrl-A/C/V/X,
  frecce, Home/End) indipendente dal disegno. E' l'editing testo centralizzato.
- Button, Slider, InputBox, ScrollList: widget con rect, draw() e handle_event().
- WidgetGroup: contenitore che smista eventi e disegna in blocco.
"""

import logging
from typing import Callable, Optional, Sequence

import pygame

from editor.ui.draw import (
    _button, _slider, _input_box, _scrollbar, _in_rect, _clamp, _text_wh,
)

logger = logging.getLogger(__name__)

# Passo di scroll di default per rotella nelle liste (px)
SCROLL_WHEEL_STEP = 30


# ─────────────────────────────────────────────────────────────────────────────
# CLIPBOARD (unica implementazione per tutto l'editor)
# ─────────────────────────────────────────────────────────────────────────────

def clipboard_set(text: str) -> bool:
    """Copia testo negli appunti di sistema. Ritorna False su errore."""
    try:
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        root.clipboard_clear()
        root.clipboard_append(text)
        root.update()
        root.destroy()
        return True
    except Exception:
        logger.debug("clipboard_set non disponibile", exc_info=True)
        return False


def clipboard_get() -> str:
    """Legge testo dagli appunti di sistema. Ritorna stringa vuota su errore."""
    try:
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        clipped = root.clipboard_get()
        root.destroy()
        return clipped or ""
    except Exception:
        logger.debug("clipboard_get non disponibile", exc_info=True)
        return ""


# ─────────────────────────────────────────────────────────────────────────────
# TEXT EDIT STATE (editing testo centralizzato)
# ─────────────────────────────────────────────────────────────────────────────

class TextEditState:
    """Stato e logica di editing di una riga di testo.

    Gestisce cursore, selezione totale, Ctrl-A/C/V/X, frecce, Home/End,
    Backspace/Delete e inserimento caratteri stampabili. Nessun disegno:
    i chiamanti leggono text/cursor/all_selected per il rendering.
    """

    def __init__(self, text: str = "", max_len: int = 0,
                 allowed: Optional[Callable[[str], bool]] = None) -> None:
        self.text = text
        self.cursor = len(text)
        self.all_selected = False
        self.max_len = max_len          # 0 = illimitato
        self.allowed = allowed          # filtro per carattere (es. solo cifre)

    def set_text(self, text: str) -> None:
        self.text = text
        self.cursor = len(text)
        self.all_selected = False

    def _insert(self, chunk: str) -> None:
        if self.allowed:
            chunk = "".join(c for c in chunk if self.allowed(c))
        if not chunk:
            return
        if self.all_selected:
            self.text = ""
            self.cursor = 0
            self.all_selected = False
        if self.max_len:
            room = self.max_len - len(self.text)
            chunk = chunk[:max(0, room)]
        self.text = self.text[:self.cursor] + chunk + self.text[self.cursor:]
        self.cursor += len(chunk)

    def _delete_selection(self) -> bool:
        if self.all_selected:
            self.text = ""
            self.cursor = 0
            self.all_selected = False
            return True
        return False

    def handle_key(self, ev) -> bool:
        """Gestisce un KEYDOWN. Ritorna True se l'evento e' stato consumato."""
        mods = pygame.key.get_mods()
        ctrl = bool(mods & pygame.KMOD_CTRL) or bool(mods & pygame.KMOD_META)

        if ctrl and ev.key == pygame.K_a:
            self.all_selected = bool(self.text)
            self.cursor = len(self.text)
            return True
        if ctrl and ev.key == pygame.K_c:
            # Campo a riga singola: copia l'intero contenuto
            clipboard_set(self.text)
            return True
        if ctrl and ev.key == pygame.K_x:
            clipboard_set(self.text)
            self.set_text("")
            return True
        if ctrl and ev.key == pygame.K_v:
            self._insert(clipboard_get())
            return True

        if ev.key == pygame.K_BACKSPACE:
            if not self._delete_selection() and self.cursor > 0:
                self.text = self.text[:self.cursor - 1] + self.text[self.cursor:]
                self.cursor -= 1
            return True
        if ev.key == pygame.K_DELETE:
            if not self._delete_selection() and self.cursor < len(self.text):
                self.text = self.text[:self.cursor] + self.text[self.cursor + 1:]
            return True
        if ev.key == pygame.K_LEFT:
            self.all_selected = False
            self.cursor = max(0, self.cursor - 1)
            return True
        if ev.key == pygame.K_RIGHT:
            self.all_selected = False
            self.cursor = min(len(self.text), self.cursor + 1)
            return True
        if ev.key == pygame.K_HOME:
            self.all_selected = False
            self.cursor = 0
            return True
        if ev.key == pygame.K_END:
            self.all_selected = False
            self.cursor = len(self.text)
            return True
        if ev.unicode and ev.unicode.isprintable() and not ctrl:
            self._insert(ev.unicode)
            return True
        return False


# ─────────────────────────────────────────────────────────────────────────────
# WIDGET BASE
# ─────────────────────────────────────────────────────────────────────────────

class Widget:
    """Base: un rettangolo con draw() e handle_event()."""

    def __init__(self, rect) -> None:
        self.rect = pygame.Rect(rect)
        self.visible = True
        self.enabled = True

    def draw(self, surf) -> None:
        raise NotImplementedError

    def handle_event(self, ev) -> bool:
        """Ritorna True se l'evento e' stato consumato dal widget."""
        return False

    def hovered(self) -> bool:
        return _in_rect(pygame.mouse.get_pos(), self.rect)


class Button(Widget):
    """Bottone: disegno via ui.draw._button, click su MOUSEBUTTONDOWN sinistro."""

    def __init__(self, rect, label: str, on_click: Callable[[], None],
                 icon: Optional[str] = None, danger: bool = False,
                 custom_bg: Optional[tuple] = None, font: str = "sm",
                 tooltip: Optional[str] = None,
                 active_fn: Optional[Callable[[], bool]] = None) -> None:
        super().__init__(rect)
        self.label = label
        self.on_click = on_click
        self.icon = icon
        self.danger = danger
        self.custom_bg = custom_bg
        self.font = font
        self.tooltip = tooltip
        self.active_fn = active_fn

    def draw(self, surf) -> None:
        if not self.visible:
            return
        active = bool(self.active_fn()) if self.active_fn else False
        _button(surf, self.rect, self.label, hovered=self.enabled and self.hovered(),
                active=active, danger=self.danger, font=self.font,
                custom_bg=self.custom_bg, icon=self.icon)

    def handle_event(self, ev) -> bool:
        if not (self.visible and self.enabled):
            return False
        if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
            if _in_rect(ev.pos, self.rect):
                self.on_click()
                return True
        return False


class Slider(Widget):
    """Slider orizzontale: get/set del valore tramite callback (fonte unica)."""

    def __init__(self, rect, get_value: Callable[[], float],
                 set_value: Callable[[float], None], min_v: float, max_v: float,
                 color: tuple = (100, 100, 255), power: float = 1.0,
                 on_release: Optional[Callable[[], None]] = None) -> None:
        super().__init__(rect)
        self.get_value = get_value
        self.set_value = set_value
        self.min_v = min_v
        self.max_v = max_v
        self.color = color
        self.power = power
        self.on_release = on_release
        self._dragging = False

    def draw(self, surf) -> None:
        if not self.visible:
            return
        _slider(surf, self.rect, self.get_value(), self.min_v, self.max_v,
                color=self.color, power=self.power)

    def _apply_pos(self, mx: int) -> None:
        ratio = _clamp((mx - self.rect.x) / max(1, self.rect.w), 0.0, 1.0)
        if self.power != 1.0:
            ratio = ratio ** self.power
        self.set_value(self.min_v + ratio * (self.max_v - self.min_v))

    def handle_event(self, ev) -> bool:
        if not (self.visible and self.enabled):
            return False
        if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
            if _in_rect(ev.pos, self.rect):
                self._dragging = True
                self._apply_pos(ev.pos[0])
                return True
        elif ev.type == pygame.MOUSEMOTION and self._dragging:
            self._apply_pos(ev.pos[0])
            return True
        elif ev.type == pygame.MOUSEBUTTONUP and ev.button == 1 and self._dragging:
            self._dragging = False
            if self.on_release:
                self.on_release()
            return True
        return False


class InputBox(Widget):
    """Campo di testo: TextEditState + disegno via ui.draw._input_box.

    Focus su click dentro il rect; click fuori toglie il focus. Enter e Esc
    tolgono il focus e chiamano on_submit/on_cancel se presenti.
    """

    def __init__(self, rect, text: str = "", hint: str = "",
                 icon: Optional[str] = None, font: str = "md",
                 max_len: int = 0,
                 allowed: Optional[Callable[[str], bool]] = None,
                 on_change: Optional[Callable[[str], None]] = None,
                 on_submit: Optional[Callable[[str], None]] = None,
                 on_cancel: Optional[Callable[[], None]] = None) -> None:
        super().__init__(rect)
        self.state = TextEditState(text, max_len=max_len, allowed=allowed)
        self.hint = hint
        self.icon = icon
        self.font = font
        self.focused = False
        self.on_change = on_change
        self.on_submit = on_submit
        self.on_cancel = on_cancel

    @property
    def text(self) -> str:
        return self.state.text

    @text.setter
    def text(self, value: str) -> None:
        self.state.set_text(value)

    def draw(self, surf) -> None:
        if not self.visible:
            return
        _input_box(surf, self.rect, self.state.text, focused=self.focused,
                   hint=self.hint, icon=self.icon, font=self.font,
                   all_selected=self.state.all_selected,
                   cursor_pos=self.state.cursor)

    def handle_event(self, ev) -> bool:
        if not (self.visible and self.enabled):
            return False
        if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
            inside = _in_rect(ev.pos, self.rect)
            if inside and not self.focused:
                self.focused = True
                self.state.cursor = len(self.state.text)
                return True
            if not inside and self.focused:
                self.focused = False
            return inside
        if ev.type == pygame.KEYDOWN and self.focused:
            if ev.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                self.focused = False
                if self.on_submit:
                    self.on_submit(self.state.text)
                return True
            if ev.key == pygame.K_ESCAPE:
                self.focused = False
                if self.on_cancel:
                    self.on_cancel()
                return True
            before = self.state.text
            consumed = self.state.handle_key(ev)
            if consumed and self.on_change and self.state.text != before:
                self.on_change(self.state.text)
            return consumed
        return False


class ScrollList(Widget):
    """Lista verticale scrollabile a item di altezza fissa.

    Il chiamante fornisce items(), draw_item(surf, rect, item, index, hovered)
    e on_select(item, index). La lista gestisce scroll con rotella, clamp e
    scrollbar; il click seleziona l'item sotto il cursore.
    """

    def __init__(self, rect, items: Callable[[], Sequence],
                 draw_item: Callable, on_select: Optional[Callable] = None,
                 item_h: int = 28, gap: int = 2) -> None:
        super().__init__(rect)
        self.items = items
        self.draw_item = draw_item
        self.on_select = on_select
        self.item_h = item_h
        self.gap = gap
        self.scroll = 0

    def _row_h(self) -> int:
        return self.item_h + self.gap

    def _max_scroll(self) -> int:
        total_h = len(self.items()) * self._row_h()
        return max(0, total_h - self.rect.h)

    def draw(self, surf) -> None:
        if not self.visible:
            return
        self.scroll = int(_clamp(self.scroll, 0, self._max_scroll()))
        items = list(self.items())
        prev_clip = surf.get_clip()
        surf.set_clip(self.rect)
        mx, my = pygame.mouse.get_pos()
        y = self.rect.y - self.scroll
        for i, item in enumerate(items):
            row = pygame.Rect(self.rect.x, y, self.rect.w, self.item_h)
            if row.bottom >= self.rect.top and row.top <= self.rect.bottom:
                self.draw_item(surf, row, item, i, _in_rect((mx, my), row))
            y += self._row_h()
        surf.set_clip(prev_clip)
        rows_visible = max(1, self.rect.h // self._row_h())
        _scrollbar(surf, self.rect.right - 5, self.rect.y, 4, self.rect.h,
                   self.scroll // self._row_h(), len(items), rows_visible)

    def index_at(self, pos) -> Optional[int]:
        if not _in_rect(pos, self.rect):
            return None
        idx = (pos[1] - self.rect.y + self.scroll) // self._row_h()
        if 0 <= idx < len(self.items()):
            return int(idx)
        return None

    def handle_event(self, ev) -> bool:
        if not (self.visible and self.enabled):
            return False
        if ev.type == pygame.MOUSEWHEEL:
            if _in_rect(pygame.mouse.get_pos(), self.rect):
                self.scroll = int(_clamp(self.scroll - ev.y * SCROLL_WHEEL_STEP,
                                         0, self._max_scroll()))
                return True
        elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
            idx = self.index_at(ev.pos)
            if idx is not None:
                if self.on_select:
                    self.on_select(list(self.items())[idx], idx)
                return True
        return False


class WidgetGroup:
    """Contenitore: disegna i widget in ordine e smista gli eventi in ordine
    inverso (l'ultimo disegnato e' sopra e riceve l'evento per primo)."""

    def __init__(self, widgets: Optional[list] = None) -> None:
        self.widgets: list = list(widgets or [])

    def add(self, widget: Widget) -> Widget:
        self.widgets.append(widget)
        return widget

    def draw(self, surf) -> None:
        for w in self.widgets:
            w.draw(surf)

    def handle_event(self, ev) -> bool:
        for w in reversed(self.widgets):
            if w.handle_event(ev):
                return True
        return False
