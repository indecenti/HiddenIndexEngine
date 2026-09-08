"""
tests/test_editor_commands.py

The command registry (`editor/commands.py`) and the command palette.

The registry is the single description of what the editor can do: the F1 panel
and the palette are both rendered from it. That only holds if every entry is
real - the method it names exists, the menu command it names is dispatched, its
label is translated in all five languages - so this pins exactly that, plus the
behaviour of the palette itself.

Before the registry, most of the editor could only be reached by knowing a
letter: 57 keyboard bindings, of which the two shortcut hint strings named 9.
"""

from __future__ import annotations

import ast
import json
import os
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pytest

pygame = pytest.importorskip("pygame")

from editor.commands import (
    COMMANDS, COMMANDS_BY_ID, GROUPS, commands_of, runnable_commands,
)
from editor.constants import LANGS, MODE_CIRCLE, MODE_SELECT
from editor.editor_base import LevelEditor
from editor.mixins.command_center import CommandCenterMixin, CommandPalette
from editor.ui.draw import _init_fonts
from engine.language_manager import LanguageManager

ROOT = Path(__file__).resolve().parents[1]
STRINGS_DIR = ROOT / "engine" / "assets" / "strings"


@pytest.fixture(scope="module", autouse=True)
def _pygame_init():
    pygame.init()
    pygame.display.set_mode((64, 64))
    _init_fonts(1.0)
    yield
    _init_fonts(1.0)
    pygame.quit()


class FakeEditor(CommandCenterMixin):
    """Enough editor for the command center: it records what it was asked to do."""

    def __init__(self, lang="en", scene=True, selection=True):
        self.screen = pygame.Surface((1280, 720))
        self.lang_manager = LanguageManager()
        self.lang_manager.load_for_game("engine", lang)
        self.scene_path = Path("scene") if scene else None
        self.selected_idx = 0 if selection else None
        self.selected_indices = [0] if selection else []
        self.modal_stack: list = []
        self.mode = MODE_SELECT
        self.called: list = []
        self.menu_called: list = []

    def _TR(self, key, *args):
        return self.lang_manager.get(key, *args)

    def _mark_dirty(self):
        pass

    def _modal_push(self, modal):
        self.modal_stack.append(modal)

    def _modal_pop(self, modal=None):
        if modal is None:
            self.modal_stack.pop()
        elif modal in self.modal_stack:
            self.modal_stack.remove(modal)

    def _exec_menu_cmd(self, cmd):
        self.menu_called.append(cmd)

    def _cancel_rect(self):
        pass

    def __getattr__(self, name):
        # Any _method a command names resolves to a recorder, so the test can
        # run every command without a real editor behind it.
        if name.startswith("_") and not name.startswith("__"):
            def recorder(*args, **kwargs):
                self.called.append(name)
            return recorder
        raise AttributeError(name)


# ─────────────────────────────────────────────────────────────────────────────
# 1. IL REGISTRO E' REALE
# ─────────────────────────────────────────────────────────────────────────────

def test_command_ids_are_unique():
    ids = [c.id for c in COMMANDS]
    assert len(ids) == len(set(ids))


def test_every_command_is_in_a_declared_group():
    known = {g for g, _ in GROUPS}
    assert {c.group for c in COMMANDS} <= known


def test_every_group_has_commands():
    for group_id, _ in GROUPS:
        assert commands_of(group_id), group_id


def test_every_called_method_exists_on_the_editor():
    missing = [c.id for c in COMMANDS
               if c.run and c.run[0] == "call" and not hasattr(LevelEditor, c.run[1])]
    assert not missing, f"commands calling a method that does not exist: {missing}"


def test_every_menu_command_is_dispatched():
    """_exec_menu_cmd must have a branch for each menu target."""
    source = (ROOT / "editor" / "mixins" / "input_handlers.py").read_text(
        encoding="utf-8")
    tree = ast.parse(source)
    handled: set = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_exec_menu_cmd":
            for cmp_node in ast.walk(node):
                if isinstance(cmp_node, ast.Compare):
                    for operand in cmp_node.comparators:
                        if isinstance(operand, ast.Constant) and isinstance(
                                operand.value, str):
                            handled.add(operand.value)
    targets = {c.run[1] for c in COMMANDS if c.run and c.run[0] == "menu"}
    assert targets <= handled, f"menu commands with no branch: {targets - handled}"


def test_every_tool_mode_is_known():
    from editor.mixins.command_center import _MODES
    targets = {c.run[1] for c in COMMANDS if c.run and c.run[0] == "mode"}
    assert targets <= set(_MODES)


def test_no_two_commands_of_a_group_share_a_shortcut():
    for group_id, _ in GROUPS:
        keys = [c.keys for c in commands_of(group_id) if c.keys]
        assert len(keys) == len(set(keys)), group_id


@pytest.mark.parametrize("lang", LANGS)
def test_every_command_label_is_translated(lang):
    strings = json.loads((STRINGS_DIR / f"{lang}.json").read_text(encoding="utf-8"))
    missing = [c.id for c in COMMANDS if c.label_key not in strings]
    assert not missing, f"{lang}: labels without a key: {missing}"


@pytest.mark.parametrize("lang", LANGS)
def test_every_group_header_is_translated(lang):
    strings = json.loads((STRINGS_DIR / f"{lang}.json").read_text(encoding="utf-8"))
    missing = [g for g, _ in GROUPS if f"cmd_group_{g}" not in strings]
    assert not missing, f"{lang}: group headers without a key: {missing}"


# ─────────────────────────────────────────────────────────────────────────────
# 2. ESECUZIONE
# ─────────────────────────────────────────────────────────────────────────────

def test_a_call_command_calls_its_method():
    editor = FakeEditor()
    editor._command_run(COMMANDS_BY_ID["fit"])
    assert "_fit_canvas" in editor.called


def test_a_menu_command_goes_through_the_menu_dispatcher():
    editor = FakeEditor()
    editor._command_run(COMMANDS_BY_ID["auditor"])
    assert editor.menu_called == ["file_auditor"]


def test_a_tool_command_switches_mode():
    editor = FakeEditor()
    editor._command_run(COMMANDS_BY_ID["tool_circle"])
    assert editor.mode == MODE_CIRCLE


def test_a_documentation_only_command_runs_nothing():
    editor = FakeEditor()
    assert editor._command_run(COMMANDS_BY_ID["pan"]) is False
    assert not editor.called


def test_every_runnable_command_can_be_run():
    editor = FakeEditor()
    for command in runnable_commands():
        assert editor._command_run(command) is True, command.id


# ─────────────────────────────────────────────────────────────────────────────
# 3. DISPONIBILITA'
# ─────────────────────────────────────────────────────────────────────────────

def test_a_scene_command_needs_a_scene():
    assert FakeEditor(scene=False)._command_available(
        COMMANDS_BY_ID["save_scene"]) is False
    assert FakeEditor(scene=True)._command_available(
        COMMANDS_BY_ID["save_scene"]) is True


def test_a_selection_command_needs_a_selection():
    assert FakeEditor(selection=False)._command_available(
        COMMANDS_BY_ID["duplicate"]) is False
    assert FakeEditor(selection=True)._command_available(
        COMMANDS_BY_ID["duplicate"]) is True


def test_a_plain_command_is_always_available():
    assert FakeEditor(scene=False, selection=False)._command_available(
        COMMANDS_BY_ID["fullscreen"]) is True


def test_run_by_id_ignores_an_unavailable_command():
    editor = FakeEditor(scene=False, selection=False)
    assert editor._command_run_by_id("duplicate") is False
    assert not editor.called


def test_run_by_id_ignores_an_unknown_command():
    assert FakeEditor()._command_run_by_id("does_not_exist") is False


# ─────────────────────────────────────────────────────────────────────────────
# 4. PALETTE
# ─────────────────────────────────────────────────────────────────────────────

def test_palette_offers_every_runnable_command_when_empty():
    editor = FakeEditor()
    assert len(editor._palette_commands("")) == len(runnable_commands())


def test_palette_filters_on_the_localized_label():
    editor = FakeEditor("it")
    found = [c.id for c in editor._palette_commands("annulla")]
    assert "undo" in found


def test_palette_matches_words_in_any_order():
    editor = FakeEditor("en")
    found = [c.id for c in editor._palette_commands("scene save")]
    assert "save_scene" in found


def test_palette_puts_the_unavailable_commands_last():
    editor = FakeEditor(selection=False)
    rows = editor._palette_commands("")
    available = [editor._command_available(c) for c in rows]
    assert available == sorted(available, reverse=True)


def test_palette_opens_once():
    editor = FakeEditor()
    editor._palette_open()
    editor._palette_open()
    assert sum(isinstance(m, CommandPalette) for m in editor.modal_stack) == 1


def test_palette_escape_closes_it():
    editor = FakeEditor()
    editor._palette_open()
    palette = editor.modal_stack[-1]
    palette.handle_event(editor, pygame.event.Event(
        pygame.KEYDOWN, {"key": pygame.K_ESCAPE, "unicode": ""}))
    assert not editor.modal_stack


def test_palette_typing_filters_and_enter_runs():
    editor = FakeEditor()
    editor._palette_open()
    palette = editor.modal_stack[-1]
    palette.render(editor)                       # fills the row list
    for ch in "fit":
        palette.handle_event(editor, pygame.event.Event(
            pygame.KEYDOWN, {"key": ord(ch), "unicode": ch}))
    palette.render(editor)
    palette.handle_event(editor, pygame.event.Event(
        pygame.KEYDOWN, {"key": pygame.K_RETURN, "unicode": "\\r"}))
    assert "_fit_canvas" in editor.called
    assert not editor.modal_stack, "running a command closes the palette"


def test_palette_arrow_keys_stay_in_range():
    editor = FakeEditor()
    editor._palette_open()
    palette = editor.modal_stack[-1]
    palette.render(editor)
    for _ in range(500):
        palette.handle_event(editor, pygame.event.Event(
            pygame.KEYDOWN, {"key": pygame.K_DOWN, "unicode": ""}))
    assert palette.index == len(palette._rows) - 1
    for _ in range(500):
        palette.handle_event(editor, pygame.event.Event(
            pygame.KEYDOWN, {"key": pygame.K_UP, "unicode": ""}))
    assert palette.index == 0


def test_palette_enter_on_an_unavailable_command_does_nothing():
    editor = FakeEditor(selection=False)
    editor._palette_open()
    palette = editor.modal_stack[-1]
    palette.query = "duplicate"
    palette.render(editor)
    palette.handle_event(editor, pygame.event.Event(
        pygame.KEYDOWN, {"key": pygame.K_RETURN, "unicode": "\\r"}))
    assert not editor.called
    assert editor.modal_stack, "the palette stays open"


def test_palette_backspace_edits_the_query():
    editor = FakeEditor()
    editor._palette_open()
    palette = editor.modal_stack[-1]
    palette.query = "abc"
    palette.handle_event(editor, pygame.event.Event(
        pygame.KEYDOWN, {"key": pygame.K_BACKSPACE, "unicode": ""}))
    assert palette.query == "ab"


@pytest.mark.parametrize("lang", LANGS)
def test_palette_renders_in_every_language(lang):
    editor = FakeEditor(lang)
    editor._palette_open()
    palette = editor.modal_stack[-1]
    palette.render(editor)                       # must not raise
    assert palette._box.width > 0
