"""
editor/mixins/command_center.py

CommandCenterMixin - running a declared command, and the command palette.

`editor/commands.py` says what the editor can do; this turns one of those
entries into the call that performs it, and offers them all in a palette
(Ctrl+P) that searches the labels in the language the editor is set to. It is
the answer to the editor's real discoverability problem: most of its features
had a letter and nothing else.

The palette lives on the unified modal stack, so it is app modal and Esc
closes it like every other dialog.
"""

from typing import List, Optional

import pygame

from editor.commands import COMMANDS_BY_ID, Command, runnable_commands
from editor.constants import (
    ACCENT, BORDER, BTN_AC, PANEL, TXT, TXT_DIM, TXT_HI,
    MODE_CIRCLE, MODE_EFFECT_PLACE, MODE_RECT, MODE_SCATTER, MODE_SELECT,
    PALETTE_W, PALETTE_MAX_ROWS, PALETTE_PAD, PALETTE_SCRIM, PALETTE_TOP,
)
from editor.ui.draw import (
    _draw_text, _in_rect, _input_box, _rect, _text_wh, _txt,
)

# Command id of a tool -> editor mode. The table stores the short name so it
# does not have to import the constants.
_MODES = {
    "select": MODE_SELECT,
    "circle": MODE_CIRCLE,
    "rect": MODE_RECT,
    "effect_place": MODE_EFFECT_PLACE,
    "scatter": MODE_SCATTER,
}


def _matches(query: str, text: str) -> bool:
    """True when every word of the query appears in the text, in any order."""
    lowered = text.casefold()
    return all(word in lowered for word in query.casefold().split())


class CommandCenterMixin:
    """Availability, execution and search of the declared commands."""

    # ── Esecuzione ──────────────────────────────────────────────────────────

    def _command_label(self, command: Command) -> str:
        """The label of a command in the current language."""
        return self._TR(command.label_key, command.label)

    def _command_available(self, command: Command) -> bool:
        """False when the editor has nothing for the command to act on."""
        if command.needs == "scene":
            return bool(getattr(self, "scene_path", None))
        if command.needs == "selection":
            if not getattr(self, "scene_path", None):
                return False
            return bool(getattr(self, "selected_indices", None)
                        or getattr(self, "selected_idx", None) is not None)
        return True

    def _command_run(self, command: Command) -> bool:
        """Perform a command. Returns False when it had nothing to run."""
        if command.run is None:
            return False
        kind, target = command.run
        if kind == "call":
            getattr(self, target)()
            return True
        if kind == "menu":
            self._exec_menu_cmd(target)
            return True
        if kind == "mode":
            self.mode = _MODES[target]
            self._cancel_rect()
            self._mark_dirty()
            return True
        return False

    def _command_run_by_id(self, command_id: str) -> bool:
        """Run a command by id, ignoring one that is not available now."""
        command = COMMANDS_BY_ID.get(command_id)
        if command is None or not self._command_available(command):
            return False
        return self._command_run(command)

    # ── Palette ─────────────────────────────────────────────────────────────

    def _palette_open(self) -> None:
        """Open the command palette on the modal stack."""
        if any(isinstance(m, CommandPalette) for m in self.modal_stack):
            return
        self._modal_push(CommandPalette())
        self._mark_dirty()

    def _palette_commands(self, query: str) -> List[Command]:
        """The commands offered for `query`, available ones first."""
        found = []
        for command in runnable_commands():
            label = self._command_label(command)
            if query and not (_matches(query, label)
                              or _matches(query, command.id.replace("_", " "))):
                continue
            found.append(command)
        found.sort(key=lambda c: not self._command_available(c))
        return found


class CommandPalette:
    """Modal of the command palette: one search box and a list of commands."""

    def __init__(self) -> None:
        self.query: str = ""
        self.index: int = 0
        self.scroll: int = 0
        self._rows: List[Command] = []
        self._row_rects: List[pygame.Rect] = []

    # ── Input ───────────────────────────────────────────────────────────────

    def handle_event(self, editor, ev) -> None:
        if ev.type == pygame.KEYDOWN:
            self._on_key(editor, ev)
        elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
            self._on_click(editor, ev.pos)
        elif ev.type == pygame.MOUSEWHEEL:
            self._move(-ev.y)
        editor._mark_dirty()

    def _on_key(self, editor, ev) -> None:
        if ev.key == pygame.K_ESCAPE:
            editor._modal_pop(self)
            return
        if ev.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            self._run(editor)
            return
        if ev.key == pygame.K_DOWN:
            self._move(1)
            return
        if ev.key == pygame.K_UP:
            self._move(-1)
            return
        if ev.key == pygame.K_BACKSPACE:
            self.query = self.query[:-1]
            self.index = self.scroll = 0
            return
        if ev.unicode and ev.unicode.isprintable():
            self.query += ev.unicode
            self.index = self.scroll = 0

    def _on_click(self, editor, pos) -> None:
        for i, rect in enumerate(self._row_rects):
            if _in_rect(pos, rect):
                self.index = self.scroll + i
                self._run(editor)
                return
        if not _in_rect(pos, getattr(self, "_box", pygame.Rect(0, 0, 0, 0))):
            editor._modal_pop(self)

    def _move(self, delta: int) -> None:
        """Move the selection, keeping it inside the visible window."""
        if not self._rows:
            return
        self.index = max(0, min(len(self._rows) - 1, self.index + delta))
        self.scroll = min(self.scroll, self.index)
        self.scroll = max(self.scroll, self.index - PALETTE_MAX_ROWS + 1)
        self.scroll = max(0, min(self.scroll,
                                 max(0, len(self._rows) - PALETTE_MAX_ROWS)))

    def _run(self, editor) -> None:
        command = self._selected()
        if command is None or not editor._command_available(command):
            return
        editor._modal_pop(self)
        editor._command_run(command)

    def _selected(self) -> Optional[Command]:
        if not self._rows:
            return None
        return self._rows[min(self.index, len(self._rows) - 1)]

    # ── Rendering ───────────────────────────────────────────────────────────

    def render(self, editor) -> None:
        screen = editor.screen
        w, h = screen.get_size()
        self._rows = editor._palette_commands(self.query)
        self.index = max(0, min(self.index, max(0, len(self._rows) - 1)))

        line_h = _text_wh("Ag", "sm")[1]
        row_h = line_h + 12
        field_h = _text_wh("Ag", "md")[1] + 14
        self.scroll = max(0, min(self.scroll,
                                 max(0, len(self._rows) - PALETTE_MAX_ROWS)))
        shown = self._rows[self.scroll:self.scroll + PALETTE_MAX_ROWS]
        hidden = len(self._rows) - len(shown) - self.scroll
        more_h = (_text_wh("Ag", "xs")[1] + 6) if hidden > 0 else 0
        box_w = min(PALETTE_W, w - 60)
        box_h = (PALETTE_PAD * 2 + field_h + 8
                 + max(row_h, len(shown) * row_h) + more_h)
        box = pygame.Rect((w - box_w) // 2, min(PALETTE_TOP, max(20, h // 8)),
                          box_w, box_h)
        self._box = box

        scrim = pygame.Surface((w, h), pygame.SRCALPHA)
        scrim.fill(PALETTE_SCRIM)
        screen.blit(scrim, (0, 0))
        _rect(screen, PANEL, box, radius=10)
        _rect(screen, ACCENT, box, 2, radius=10)

        field = pygame.Rect(box.x + PALETTE_PAD, box.y + PALETTE_PAD,
                            box.w - PALETTE_PAD * 2, field_h)
        _input_box(screen, field, self.query, focused=True,
                   hint=editor._TR("palette_hint", "Type a command..."),
                   icon="search", font="md")

        y = field.bottom + 8
        self._row_rects = []
        if not shown:
            _draw_text(screen, editor._TR("palette_empty", "No command matches"),
                       "sm", TXT_DIM, field.x + 4, y + 6, field.w - 8)
            return

        for i, command in enumerate(shown):
            row = pygame.Rect(box.x + PALETTE_PAD, y, box.w - PALETTE_PAD * 2, row_h)
            self._row_rects.append(row)
            available = editor._command_available(command)
            if self.scroll + i == self.index:
                _rect(screen, BTN_AC, row, radius=5)
            label_colour = (TXT_HI if self.scroll + i == self.index
                            else (TXT if available else (90, 92, 110)))
            keys = command.keys
            keys_w = _text_wh(keys, "mono")[0] if keys else 0
            _draw_text(screen, editor._command_label(command), "sm", label_colour,
                       row.x + 10, row.y + (row_h - line_h) // 2,
                       row.w - 24 - keys_w)
            if keys:
                chip = _txt(keys, "mono", TXT_DIM if available else (80, 82, 96))
                screen.blit(chip, (row.right - keys_w - 10,
                                   row.y + (row_h - chip.get_height()) // 2))
            y += row_h

        if hidden > 0:
            _draw_text(screen,
                       editor._TR("palette_more", "+{n} more").format(n=hidden),
                       "xs", TXT_DIM, box.x + PALETTE_PAD, y + 2)
            pygame.draw.line(screen, BORDER, (box.x, y), (box.right, y), 1)
