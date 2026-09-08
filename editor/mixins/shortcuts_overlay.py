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

from typing import List

import pygame

from editor.commands import COMMANDS, GROUPS
from editor.constants import (
    ACCENT, BORDER, PANEL, TXT, TXT_DIM, TXT_HI,
    SHORTCUTS_COL_GAP, SHORTCUTS_KEY_COL_W, SHORTCUTS_PAD, SHORTCUTS_PANEL_W,
    SHORTCUTS_ROW_H, SHORTCUTS_SCRIM,
)
from editor.ui.draw import _draw_text, _rect, _text_wh


def _pack(blocks: list, sizes: list, columns: int):
    """Split `blocks` into `columns` contiguous parts, shortest tallest part.

    Returns the parts as lists of indices, or None when there are fewer blocks
    than columns.
    """
    if columns > len(blocks):
        return None

    def fits(limit: int):
        parts, current, used = [], [], 0
        for i, size in enumerate(sizes):
            if current and used + size > limit:
                parts.append(current)
                current, used = [], 0
            current.append(i)
            used += size
        parts.append(current)
        return parts if len(parts) <= columns else None

    low, high = max(sizes), sum(sizes)
    best = None
    while low <= high:
        middle = (low + high) // 2
        parts = fits(middle)
        if parts is None:
            low = middle + 1
        else:
            best = parts
            high = middle - 1
    return best


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

    def _shortcuts_blocks(self) -> List[list]:
        """One block per group: a ("group", label) header then its rows."""
        blocks: List[list] = []
        for group_id, group_label in GROUPS:
            rows = [c for c in COMMANDS if c.group == group_id and c.keys]
            if not rows:
                continue
            block = [("group", self._TR(f"cmd_group_{group_id}", group_label))]
            block += [("row", c.keys, self._TR(c.label_key, c.label)) for c in rows]
            blocks.append(block)
        return blocks

    def _shortcuts_columns(self, max_rows: int = 0) -> List[List[list]]:
        """The groups laid out in the fewest columns that fit the height.

        `max_rows` is how many entries fit in the space available; 0 means no
        limit, which is two columns. The panel used to clamp its box to the
        window but lay the content out in two columns regardless, so a short
        window drew the last rows outside the panel. A group is never split
        across two columns.
        """
        blocks = self._shortcuts_blocks()
        if not blocks:
            return [[]]
        sizes = [len(b) for b in blocks]
        budget = max_rows if max_rows else sum(sizes)

        for columns_wanted in range(2, len(blocks) + 1):
            packed = _pack(blocks, sizes, columns_wanted)
            if packed is None:
                continue
            if max(sum(sizes[i] for i in column) for column in packed) <= budget:
                return [[blocks[i] for i in column] for column in packed]

        # Nothing fits the budget: one column per group is the shortest we can
        # be without splitting one.
        return [[block] for block in blocks]

    def _shortcuts_geometry(self, w: int, h: int) -> dict:
        """Box, columns and column metrics of the panel, derived once.

        Keys: box, columns, column_w, key_col, body_top, footer_y, rows.
        """
        title = self._TR("shortcuts_title", "Keyboard shortcuts")
        footer = self._TR("shortcuts_close", "F1 or Esc to close")
        title_h = _text_wh(title, "lg")[1]
        footer_h = _text_wh(footer, "xs")[1]

        chrome_h = SHORTCUTS_PAD * 3 + title_h + footer_h
        max_rows = max(1, (h - 40 - chrome_h) // SHORTCUTS_ROW_H)
        columns = self._shortcuts_columns(max_rows)

        # The chip column and the panel follow the content: fixed, a longer
        # key ("Space+drag") or a translated label was cut with an ellipsis.
        rows = [entry for column in columns for block in column for entry in block
                if entry[0] == "row"]
        key_col = max([_text_wh(keys, "mono")[0] for _, keys, _ in rows] or [0]) + 12
        key_col = max(SHORTCUTS_KEY_COL_W, key_col)
        label_w = max([_text_wh(label, "sm")[0] for _, _, label in rows] or [0])
        content_w = key_col + SHORTCUTS_COL_GAP + label_w

        n = len(columns)
        panel_w = min(w - 40, max(SHORTCUTS_PANEL_W,
                                  content_w * n + SHORTCUTS_PAD * (n + 1)))
        body_rows = max(sum(len(b) for b in column) for column in columns)
        panel_h = min(chrome_h + body_rows * SHORTCUTS_ROW_H, h - 40)
        box = pygame.Rect((w - panel_w) // 2, max(20, (h - panel_h) // 2),
                          panel_w, panel_h)
        return {
            "box": box,
            "columns": columns,
            "column_w": (panel_w - SHORTCUTS_PAD * (n + 1)) // n,
            "key_col": key_col,
            "title": title,
            "title_h": title_h,
            "footer": footer,
            "footer_h": footer_h,
            "body_top": box.y + SHORTCUTS_PAD + title_h + SHORTCUTS_PAD,
            "rows": body_rows,
        }

    def _r_shortcuts_overlay(self, w: int, h: int) -> None:
        if not getattr(self, "_shortcuts_open", False):
            return

        geo = self._shortcuts_geometry(w, h)
        box = geo["box"]
        columns = geo["columns"]
        key_col = geo["key_col"]
        column_w = geo["column_w"]

        scrim = pygame.Surface((w, h), pygame.SRCALPHA)
        scrim.fill(SHORTCUTS_SCRIM)
        self.screen.blit(scrim, (0, 0))
        _rect(self.screen, PANEL, box, radius=10)
        _rect(self.screen, BORDER, box, 1, radius=10)

        _draw_text(self.screen, geo["title"], "lg", TXT_HI,
                   box.x + SHORTCUTS_PAD, box.y + SHORTCUTS_PAD)
        line_y = geo["body_top"] - SHORTCUTS_PAD // 2
        pygame.draw.line(self.screen, BORDER, (box.x + SHORTCUTS_PAD, line_y),
                         (box.right - SHORTCUTS_PAD, line_y), 1)

        for index, blocks in enumerate(columns):
            x = box.x + SHORTCUTS_PAD + index * (column_w + SHORTCUTS_PAD)
            cy = geo["body_top"]
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

        fw = _text_wh(geo["footer"], "xs")[0]
        _draw_text(self.screen, geo["footer"], "xs", TXT_DIM,
                   box.centerx - fw // 2, box.bottom - geo["footer_h"] - 8)

        self._shortcuts_box = box
