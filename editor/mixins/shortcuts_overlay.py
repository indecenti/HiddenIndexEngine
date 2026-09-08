"""
editor/mixins/shortcuts_overlay.py

ShortcutsOverlayMixin - the F1 keyboard shortcuts panel.

The editor used to advertise its shortcuts as two permanent one-line strings:
one centred in the status bar, one blitted on the canvas in (60, 65, 75) on
top of the toolbar. Neither was readable, and between them they named 9 of the
57 bindings the editor actually has.

The panel now lists the whole of `editor/commands.py`, grouped, in the
language the editor is set to. Adding a command to that table adds it here.
"""

from typing import List, Tuple

import pygame

from editor.commands import COMMANDS, GROUPS
from editor.constants import (
    ACCENT, BORDER, PANEL, TXT, TXT_DIM, TXT_HI,
    SHORTCUTS_COL_GAP, SHORTCUTS_KEY_COL_W, SHORTCUTS_PAD, SHORTCUTS_PANEL_W,
    SHORTCUTS_ROW_H, SHORTCUTS_SCRIM,
)
from editor.ui.draw import _draw_text, _rect, _text_wh


class ShortcutsOverlayMixin:
    """F1 shortcuts panel: toggle and rendering."""

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

    def _shortcuts_columns(self) -> Tuple[List[list], List[list]]:
        """The groups split into two columns of roughly equal height.

        An entry is a ("group", label) header or a ("row", keys, label).
        """
        blocks: List[list] = []
        for group_id, group_label in GROUPS:
            rows = [c for c in COMMANDS if c.group == group_id and c.keys]
            if not rows:
                continue
            block = [("group", self._TR(f"cmd_group_{group_id}", group_label))]
            block += [("row", c.keys, self._TR(c.label_key, c.label)) for c in rows]
            blocks.append(block)

        total = sum(len(b) for b in blocks)
        left: List[list] = []
        right: List[list] = []
        used = 0
        for block in blocks:
            if used + len(block) <= (total + 1) // 2 or not left:
                left.append(block)
                used += len(block)
            else:
                right.append(block)
        return left, right

    def _r_shortcuts_overlay(self, w: int, h: int) -> None:
        if not getattr(self, "_shortcuts_open", False):
            return

        left, right = self._shortcuts_columns()
        rows_left = sum(len(b) for b in left)
        rows_right = sum(len(b) for b in right)

        title = self._TR("shortcuts_title", "Keyboard shortcuts")
        footer = self._TR("shortcuts_close", "F1 or Esc to close")
        title_h = _text_wh(title, "lg")[1]
        footer_h = _text_wh(footer, "xs")[1]

        # The chip column and the panel follow the content: fixed, a longer
        # key ("Space+drag") or a translated label was cut with an ellipsis.
        rows = [entry for block in left + right for entry in block
                if entry[0] == "row"]
        key_col = max([_text_wh(keys, "mono")[0] for _, keys, _ in rows] or [0]) + 12
        key_col = max(SHORTCUTS_KEY_COL_W, key_col)
        label_w = max([_text_wh(label, "sm")[0] for _, _, label in rows] or [0])
        column_content = key_col + SHORTCUTS_COL_GAP + label_w
        panel_w = min(w - 40, max(SHORTCUTS_PANEL_W,
                                  column_content * 2 + SHORTCUTS_PAD * 3))
        body_h = max(rows_left, rows_right) * SHORTCUTS_ROW_H
        panel_h = SHORTCUTS_PAD * 3 + title_h + body_h + footer_h
        panel_h = min(panel_h, h - 40)
        box = pygame.Rect((w - panel_w) // 2, max(20, (h - panel_h) // 2),
                          panel_w, panel_h)

        scrim = pygame.Surface((w, h), pygame.SRCALPHA)
        scrim.fill(SHORTCUTS_SCRIM)
        self.screen.blit(scrim, (0, 0))
        _rect(self.screen, PANEL, box, radius=10)
        _rect(self.screen, BORDER, box, 1, radius=10)

        y = box.y + SHORTCUTS_PAD
        _draw_text(self.screen, title, "lg", TXT_HI, box.x + SHORTCUTS_PAD, y)
        y += title_h + SHORTCUTS_PAD // 2
        pygame.draw.line(self.screen, BORDER, (box.x + SHORTCUTS_PAD, y),
                         (box.right - SHORTCUTS_PAD, y), 1)
        y += SHORTCUTS_PAD // 2

        column_w = (box.w - SHORTCUTS_PAD * 3) // 2
        for column, blocks in ((0, left), (1, right)):
            x = box.x + SHORTCUTS_PAD + column * (column_w + SHORTCUTS_PAD)
            cy = y
            for block in blocks:
                for entry in block:
                    if entry[0] == "group":
                        _draw_text(self.screen, entry[1], "xs", ACCENT, x,
                                   cy + 4, column_w)
                    else:
                        _, keys, label = entry
                        kw, kh = _text_wh(keys, "mono")
                        chip = pygame.Rect(x, cy + (SHORTCUTS_ROW_H - kh) // 2 - 2,
                                           min(kw + 10, key_col), kh + 4)
                        _rect(self.screen, (46, 46, 58), chip, radius=3)
                        _rect(self.screen, (70, 74, 92), chip, 1, radius=3)
                        _draw_text(self.screen, keys, "mono", TXT_HI,
                                   chip.x + 5, chip.y + 2, chip.w - 10)
                        _draw_text(self.screen, label, "sm", TXT,
                                   x + key_col + SHORTCUTS_COL_GAP,
                                   cy + (SHORTCUTS_ROW_H - kh) // 2,
                                   column_w - key_col - SHORTCUTS_COL_GAP)
                    cy += SHORTCUTS_ROW_H

        fw = _text_wh(footer, "xs")[0]
        _draw_text(self.screen, footer, "xs", TXT_DIM,
                   box.centerx - fw // 2, box.bottom - footer_h - 8)

        self._shortcuts_box = box
