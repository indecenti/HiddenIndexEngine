"""
editor/commands.py

The commands of the editor, declared once.

The editor had 57 keyboard bindings and a File/Edit menu, and no relationship
between the two: half its features could only be reached by knowing a letter,
the shortcut panel could only list the handful of them that happened to be
written into two hint strings, and the canvas toolbar reimplemented three
toggles the keyboard already had.

This table is the single description of what the editor can do. It feeds:

  * the F1 shortcut panel, which lists every binding, grouped;
  * the command palette (Ctrl+P), which searches the labels and runs them;
  * `pytest tests/test_editor_commands.py`, which checks every target exists
    and every label is translated.

It does not dispatch the keyboard: `InputHandlersMixin._on_key` stays the
authority on what a key does. `keys` here is the documentation of that, and
the test suite pins the two together where it can.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

# Groups, in the order the shortcut panel shows them.
GROUPS: Tuple[Tuple[str, str], ...] = (
    ("file", "File"),
    ("edit", "Edit"),
    ("tools", "Tools"),
    ("view", "View"),
    ("object", "Object"),
    ("nav", "Navigation"),
)


@dataclass(frozen=True)
class Command:
    """One thing the editor can do.

    `run` says how to perform it:
      ("call", "_fit_canvas")     -> editor._fit_canvas()
      ("menu", "file_auditor")    -> editor._exec_menu_cmd("file_auditor")
      ("mode", "circle")          -> editor sets the tool mode
      None                        -> documentation only (panning, nudging):
                                     it has a shortcut but nothing to invoke.

    `needs` gates the palette entry: "scene" hides it with no scene open,
    "selection" with nothing selected.
    """

    id: str
    group: str
    label: str                       # English, also the default of the key
    keys: str = ""                   # what the panel shows, "" when there is none
    run: Optional[Tuple[str, str]] = None
    needs: str = ""                  # "", "scene" or "selection"

    @property
    def label_key(self) -> str:
        return f"cmd_{self.id}"


COMMANDS: Tuple[Command, ...] = (
    # ── File ────────────────────────────────────────────────────────────────
    Command("save_scene", "file", "Save scene", "Ctrl+S",
            ("menu", "file_save_scene"), needs="scene"),
    Command("save_as", "file", "Save scene as...", "",
            ("menu", "file_save_as"), needs="scene"),
    Command("playtest", "file", "Playtest this scene", "",
            ("call", "_playtest_scene"), needs="scene"),
    Command("preview", "file", "Preview as in game", "F5",
            ("call", "_preview_toggle"), needs="scene"),
    Command("auditor", "file", "Project auditor...", "",
            ("menu", "file_auditor")),
    Command("scene_stats", "file", "Scene statistics...", "",
            ("menu", "file_scene_stats"), needs="scene"),
    Command("batch_import", "file", "Batch object import...", "",
            ("menu", "file_batch_import")),
    Command("new_project", "file", "New project...", "",
            ("menu", "file_new_game")),
    Command("open_project", "file", "Open project...", "",
            ("menu", "file_open_game")),
    Command("back_to_selector", "file", "Back to the selector", "Home",
            ("menu", "file_exit_to_gs")),
    Command("quit", "file", "Quit", "", ("menu", "file_quit")),

    # ── Edit ────────────────────────────────────────────────────────────────
    Command("undo", "edit", "Undo", "Ctrl+Z", ("call", "_undo")),
    Command("redo", "edit", "Redo", "Ctrl+Y", ("call", "_redo")),
    Command("cut", "edit", "Cut", "Ctrl+X", ("call", "_cut_sel"), needs="selection"),
    Command("copy", "edit", "Copy", "Ctrl+C", ("call", "_copy_sel"), needs="selection"),
    Command("paste", "edit", "Paste", "Ctrl+V", ("call", "_paste_sel"), needs="scene"),
    Command("duplicate", "edit", "Duplicate", "Ctrl+D",
            ("call", "_duplicate"), needs="selection"),
    Command("select_all", "edit", "Select all", "Ctrl+A",
            ("call", "_select_all"), needs="scene"),
    Command("delete", "edit", "Delete the selection", "Del",
            ("call", "_delete_sel"), needs="selection"),
    Command("preset_save", "edit", "Save the selection as a group...", "",
            ("menu", "edit_preset_save"), needs="selection"),
    Command("preset_insert", "edit", "Insert a group...", "",
            ("menu", "edit_preset_insert"), needs="scene"),
    Command("translations", "edit", "Translation editor...", "",
            ("menu", "edit_lang_modal")),

    # ── Tools ───────────────────────────────────────────────────────────────
    Command("tool_select", "tools", "Selection tool", "S", ("mode", "select")),
    Command("tool_circle", "tools", "Circle tool", "1", ("mode", "circle")),
    Command("tool_rect", "tools", "Rectangle tool", "2", ("mode", "rect")),
    Command("tool_effect", "tools", "Effect tool", "3", ("mode", "effect_place")),
    Command("tool_cluster", "tools", "Cluster tool", "4", ("mode", "scatter")),
    Command("autoscatter", "tools", "Auto-scatter...", "",
            ("call", "_scatter_open"), needs="scene"),

    # ── View ────────────────────────────────────────────────────────────────
    Command("toggle_overlay", "view", "Show the hit areas", "O",
            ("call", "_toggle_overlay")),
    Command("toggle_grid", "view", "Show the grid", "G",
            ("call", "_toggle_grid")),
    Command("cycle_grid_size", "view", "Next grid size", "Shift+G",
            ("call", "_cycle_grid_size")),
    Command("toggle_obj_snap", "view", "Snap to the other objects", "Ctrl+G",
            ("call", "_toggle_obj_snap")),
    Command("toggle_icons", "view", "Show the object icons", "I",
            ("call", "_toggle_icons")),
    Command("fit", "view", "Fit the scene in the canvas", "F",
            ("call", "_fit_canvas"), needs="scene"),
    Command("zoom_selection", "view", "Zoom to the selection", "Z",
            ("call", "_zoom_to_selection"), needs="selection"),
    Command("zoom_in", "view", "Zoom in", "+", ("call", "_zoom_in")),
    Command("zoom_out", "view", "Zoom out", "-", ("call", "_zoom_out")),
    Command("ui_scale_up", "view", "Larger interface", "Ctrl+Plus"),
    Command("ui_scale_down", "view", "Smaller interface", "Ctrl+Minus"),
    Command("toggle_panels", "view", "Hide the side panels", "H",
            ("call", "_toggle_panels")),
    Command("toggle_layers_tab", "view", "Layers / properties panel", "L",
            ("call", "_toggle_layers_tab")),
    Command("fullscreen", "view", "Fullscreen", "F11",
            ("call", "_toggle_fullscreen")),
    Command("shortcuts", "view", "Keyboard shortcuts", "F1",
            ("call", "_shortcuts_toggle")),
    Command("palette", "view", "Command palette", "Ctrl+P",
            ("call", "_palette_open")),

    # ── Object ──────────────────────────────────────────────────────────────
    Command("rotate_cw", "object", "Rotate clockwise", "R", needs="selection"),
    Command("rotate_ccw", "object", "Rotate counter-clockwise", "Q",
            needs="selection"),
    Command("flip_h", "object", "Flip horizontally", "H", needs="selection"),
    Command("flip_v", "object", "Flip vertically", "V", needs="selection"),
    Command("cycle_overlapping", "object", "Cycle the objects under the cursor",
            "Tab", ("call", "_tab_cycle"), needs="scene"),
    Command("layer_low", "object", "Move to the bottom layer", "Ctrl+1",
            needs="selection"),
    Command("layer_mid", "object", "Move to the middle layer", "Ctrl+2",
            needs="selection"),
    Command("layer_high", "object", "Move to the top layer", "Ctrl+3",
            needs="selection"),
    Command("layer_overlay", "object", "Move to the overlay layer", "Ctrl+4",
            needs="selection"),

    # ── Navigation ──────────────────────────────────────────────────────────
    Command("search_catalog", "nav", "Search the catalog", "/",
            ("call", "_focus_catalog_search"), needs="scene"),
    Command("pan", "nav", "Pan the canvas", "WASD"),
    Command("pan_drag", "nav", "Pan by dragging", "Space+drag"),
    Command("nudge", "nav", "Nudge the selection (Shift: 10 px)", "Arrows"),
)

COMMANDS_BY_ID = {c.id: c for c in COMMANDS}


def commands_of(group: str) -> list:
    """The commands of one group, in declaration order."""
    return [c for c in COMMANDS if c.group == group]


def runnable_commands() -> list:
    """The commands the palette can offer: the ones with something to run."""
    return [c for c in COMMANDS if c.run is not None]
