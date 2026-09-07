"""
editor/mixins/shortcuts_overlay.py

ShortcutsOverlayMixin — the F1 keyboard shortcuts panel.

The editor used to advertise its shortcuts as two permanent one-line strings:
one centred in the status bar, one blitted on the canvas in (60, 65, 75) on
top of the toolbar. Neither was readable. Both strings are still the single
source of truth for the shortcut list, they are just parsed and laid out as a
proper panel that the user opens on demand.
"""

from typing import List, Tuple

import pygame

from editor.constants import (
    ACCENT, BORDER, PANEL, TXT, TXT_DIM, TXT_HI,
    SHORTCUTS_PANEL_W, SHORTCUTS_ROW_H, SHORTCUTS_PAD, SHORTCUTS_KEY_COL_W,
    SHORTCUTS_SCRIM,
)
from editor.ui.draw import _draw_text, _rect, _text_wh

# The shortcut strings are written as "KEYS=description" runs separated by
# spaces. A run without "=" belongs to the description of the previous one:
# a translator is free to write "Del=delete object" without breaking the list.
_SEP = "="


def _parse_shortcuts(text: str) -> List[Tuple[str, str]]:
    """Split a "Ctrl+S=Save Ctrl+Z=Undo" string into (keys, description)."""
    rows: List[Tuple[str, str]] = []
    for token in str(text).split(" "):
        if not token:
            continue
        if _SEP in token:
            keys, _, desc = token.partition(_SEP)
            rows.append((keys, desc))
        elif rows:
            keys, desc = rows[-1]
            rows[-1] = (keys, f"{desc} {token}".strip())
    return rows


class ShortcutsOverlayMixin:
    """F1 shortcuts panel: toggle, hit test and rendering."""

    def _shortcuts_toggle(self) -> None:
        self._shortcuts_open = not getattr(self, "_shortcuts_open", False)
        self._mark_dirty()

    def _shortcuts_close(self) -> bool:
        """Close the panel. Returns True when it actually was open."""
        if getattr(self, "_shortcuts_open", False):
            self._shortcuts_open = False
            self._mark_dirty()
            return True
        return False

    def _shortcuts_rows(self) -> List[Tuple[str, str]]:
        """Every shortcut the editor advertises, in display order.

        The two source strings overlap (both list Ctrl+Z/Y), and one writes
        its descriptions in lower case: the panel keeps the first spelling of
        each key combination and capitalises what it shows.
        """
        rows: List[Tuple[str, str]] = []
        seen: set = set()
        for text in (self._TR("tb_shortcuts"), self._TR("canvas_hints")):
            for keys, desc in _parse_shortcuts(text):
                folded = keys.casefold()
                if folded in seen:
                    continue
                seen.add(folded)
                rows.append((keys, desc[:1].upper() + desc[1:]))
        return rows

    def _r_shortcuts_overlay(self, w: int, h: int) -> None:
        if not getattr(self, "_shortcuts_open", False):
            return
        rows = self._shortcuts_rows()

        scrim = pygame.Surface((w, h), pygame.SRCALPHA)
        scrim.fill(SHORTCUTS_SCRIM)
        self.screen.blit(scrim, (0, 0))

        title = self._TR("shortcuts_title", "Keyboard shortcuts")
        footer = self._TR("shortcuts_close", "F1 or Esc to close")
        _, title_h = _text_wh(title, "lg")
        _, footer_h = _text_wh(footer, "xs")
        body_h = len(rows) * SHORTCUTS_ROW_H
        box_h = SHORTCUTS_PAD * 3 + title_h + body_h + footer_h
        box = pygame.Rect((w - SHORTCUTS_PANEL_W) // 2, max(20, (h - box_h) // 2),
                          SHORTCUTS_PANEL_W, box_h)

        _rect(self.screen, PANEL, box, radius=10)
        _rect(self.screen, BORDER, box, 1, radius=10)

        y = box.y + SHORTCUTS_PAD
        _draw_text(self.screen, title, "lg", TXT_HI, box.x + SHORTCUTS_PAD, y)
        y += title_h + SHORTCUTS_PAD // 2
        pygame.draw.line(self.screen, BORDER, (box.x + SHORTCUTS_PAD, y),
                         (box.right - SHORTCUTS_PAD, y), 1)
        y += SHORTCUTS_PAD // 2

        key_x = box.x + SHORTCUTS_PAD
        desc_x = key_x + SHORTCUTS_KEY_COL_W
        desc_w = box.right - SHORTCUTS_PAD - desc_x
        for keys, desc in rows:
            kw, kh = _text_wh(keys, "mono")
            chip = pygame.Rect(key_x, y + (SHORTCUTS_ROW_H - kh) // 2 - 2,
                               min(kw + 10, SHORTCUTS_KEY_COL_W - 10), kh + 4)
            _rect(self.screen, (46, 46, 58), chip, radius=3)
            _rect(self.screen, ACCENT, chip, 1, radius=3)
            _draw_text(self.screen, keys, "mono", TXT_HI, chip.x + 5,
                       chip.y + 2, chip.w - 10)
            _draw_text(self.screen, desc, "sm", TXT, desc_x,
                       y + (SHORTCUTS_ROW_H - kh) // 2, desc_w)
            y += SHORTCUTS_ROW_H

        y += SHORTCUTS_PAD // 2
        fw, _ = _text_wh(footer, "xs")
        _draw_text(self.screen, footer, "xs", TXT_DIM,
                   box.centerx - fw // 2, y)

        self._shortcuts_box = box
