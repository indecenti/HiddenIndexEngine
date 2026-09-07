"""
tests/test_editor_props_panel.py

Properties panel: the panel draws the controls and registers a hitbox for each
one, the click handler looks those hitboxes up by name. The two halves are
written apart, so this pins what every control does when it is clicked, and
that no control is drawn without an answer behind it.

Real editor, real game, real scene: the coordinates come from the render.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pytest

pygame = pytest.importorskip("pygame")

from editor.constants import STATE_MAIN, TAB_PROPS, TAB_TREE


def _largest_scene() -> Path:
    """The scene with the most objects, so every control has something to act on."""
    scenes = list(Path("games").glob("*/levels/*/*/scene.json"))
    if not scenes:
        pytest.skip("no game in the repository")
    return max(scenes, key=lambda p: len(json.loads(
        p.read_text(encoding="utf-8")).get("objects", [])))


@pytest.fixture(scope="module")
def editor():
    from editor.editor_base import LevelEditor
    pygame.init()
    ed = LevelEditor(Path(os.getcwd()))
    scene = _largest_scene()
    ed._load_game(scene.parts[1])
    ed._load_scene(scene.parent)
    ed.state = STATE_MAIN
    ed.r_tab = TAB_PROPS
    ed.l_tab = TAB_TREE
    if not ed.scene_data.get("objects"):
        pytest.skip("the scene has no objects")
    yield ed
    ed.running = False
    pygame.quit()


@pytest.fixture
def panel(editor):
    """An object selected, the panel drawn, its hitboxes fresh."""
    editor.selected_idx = 0
    editor.selected_indices = [0]
    editor.prop_scroll = 0
    editor.sel_effect_idx = None
    editor._editing_prop = None
    editor._dragging_slider = None
    editor._layer_dropdown_open = False
    editor.undo_stack.clear()
    editor._render()
    return editor


def obj(editor):
    return editor.scene_data["objects"][editor.selected_idx]


def hitbox(editor, name):
    box = editor._obj_props_hitboxes.get(name)
    assert box is not None, f"the panel did not register the hitbox {name!r}"
    return box


def click(editor, name):
    """Click the middle of a control, in the space the handler compares against."""
    box = hitbox(editor, name)
    editor._props_click(box.centerx, box.centery)


def scene_click(editor, name):
    box = editor._scene_props_hitboxes.get(name)
    assert box is not None, f"the panel did not register the scene hitbox {name!r}"
    editor._props_click(box.centerx, box.centery)


# -----------------------------------------------------------------------------
# NUMERIC FIELDS: THE BOX EDITS, THE SLIDER SETS
# -----------------------------------------------------------------------------

NUMERIC = ["x", "y", "scale", "rotation", "alpha"]


@pytest.mark.parametrize("key", NUMERIC)
def test_the_box_of_a_number_starts_editing_it(panel, key):
    click(panel, f"box_{key}")
    assert panel._editing_prop == ("object", panel.selected_idx, key)
    assert panel._prop_buf != ""


@pytest.mark.parametrize("key", NUMERIC)
def test_the_slider_of_a_number_sets_it_and_starts_a_drag(panel, key):
    before = obj(panel).get(key)
    click(panel, f"slider_{key}")
    after = obj(panel).get(key)
    assert after is not None
    assert panel._dragging_slider is not None
    assert panel._dragging_slider[2] == key
    lo, hi = panel._dragging_slider[3], panel._dragging_slider[4]
    assert lo <= after <= hi, f"{key}={after} outside the slider range {lo}..{hi}"
    assert panel.undo_stack, "a slider must be undoable"
    assert (after != before) or (lo == hi)


def test_the_layer_depth_has_a_box_and_a_slider(panel):
    click(panel, "box_layer_z")
    assert panel._editing_prop == ("object", panel.selected_idx, "layer_z")
    click(panel, "slider_layer_z")
    assert 0 <= obj(panel)["layer_z"] <= 100


def test_the_hit_shape_size_has_a_box_and_a_slider(panel):
    """Circle shows a radius, rectangle a width and a height."""
    if obj(panel).get("detection_type") == "circle":
        keys = ["radius"]
    else:
        keys = ["width", "height"]
    for key in keys:
        panel._render()
        click(panel, f"box_{key}")
        assert panel._editing_prop == ("object", panel.selected_idx, key)
        panel._editing_prop = None
        click(panel, f"slider_{key}")
        assert obj(panel)[key] >= 5


# -----------------------------------------------------------------------------
# GREYSCALE INTENSITY: DRAWN BUT UNREACHABLE
# -----------------------------------------------------------------------------

@pytest.fixture
def grey_panel(panel):
    """An object with greyscale on, so the intensity row is drawn."""
    target = obj(panel)
    target["grayscale"] = True
    target.setdefault("grayscale_factor", 0.5)
    panel._render()
    return panel


def test_the_greyscale_slider_sets_the_intensity(grey_panel):
    target = obj(grey_panel)
    target["grayscale_factor"] = 1.0
    click(grey_panel, "slider_grayscale_factor")
    assert 0.0 <= target["grayscale_factor"] <= 1.0
    assert target["grayscale_factor"] != 1.0, "the slider did nothing"


def test_the_greyscale_box_starts_editing_the_intensity(grey_panel):
    click(grey_panel, "box_grayscale_factor")
    assert grey_panel._editing_prop == ("object", grey_panel.selected_idx,
                                        "grayscale_factor")


# -----------------------------------------------------------------------------
# TOGGLES: THEY FLIP EVERY SELECTED OBJECT AND ARE UNDOABLE
# -----------------------------------------------------------------------------

# The goal toggle and the fixed-goal toggle share the same slot: which one is
# drawn depends on whether the scene randomizes the objects to find.
OBJECT_TOGGLES = [
    ("goal_btn", "is_goal", False),
    ("always_btn", "always_show", True),
    ("hide_btn", "editor_hidden", None),
    ("lock_btn", "editor_locked", None),
    ("flip_h", "flip_x", None),
    ("flip_v", "flip_y", None),
    ("grayscale", "grayscale", None),
]


def _set_auto_random(editor, value):
    if value is not None:
        editor.scene_data["auto_random_finds"] = value
    editor._render()


@pytest.mark.parametrize("name, field, auto_random", OBJECT_TOGGLES)
def test_a_toggle_flips_the_field_and_can_be_undone(panel, name, field, auto_random):
    _set_auto_random(panel, auto_random)
    default = True if field == "is_goal" else False
    before = obj(panel).get(field, default)
    click(panel, name)
    assert obj(panel).get(field, default) is not before
    assert panel.undo_stack, f"{name} must be undoable"


@pytest.mark.parametrize("name, field, auto_random", OBJECT_TOGGLES)
def test_a_toggle_applies_to_the_whole_selection(editor, name, field, auto_random):
    editor.selected_idx = 0
    editor.selected_indices = [0, 1]
    editor.prop_scroll = 0
    editor.sel_effect_idx = None
    objs = [editor.scene_data["objects"][i] for i in (0, 1)]
    default = True if field == "is_goal" else False
    for o in objs:
        o[field] = default
    _set_auto_random(editor, auto_random)
    click(editor, name)
    assert all(o.get(field, default) is not default for o in objs)


def test_the_hit_shape_can_be_switched(panel):
    click(panel, "hit_type_rect")
    assert obj(panel)["detection_type"] == "rect"
    assert obj(panel)["width"] > 0 and obj(panel)["height"] > 0
    panel._render()
    click(panel, "hit_type_circle")
    assert obj(panel)["detection_type"] == "circle"
    assert obj(panel)["radius"] > 0


def test_back_clears_the_selection(panel):
    click(panel, "back_btn")
    assert panel.selected_idx is None
    assert panel.selected_indices == []


# -----------------------------------------------------------------------------
# SCENE PANEL: SAME SHAPE, NO OBJECT SELECTED
# -----------------------------------------------------------------------------

@pytest.fixture
def scene_panel(editor):
    editor.selected_idx = None
    editor.selected_indices = []
    editor.sel_effect_idx = None
    editor.prop_scroll = 0
    editor._editing_prop = None
    editor._dragging_slider = None
    editor.undo_stack.clear()
    editor._render()
    return editor


SCENE_TOGGLES = [
    ("auto_btn", "auto_random_finds"),
    ("rand_l_btn", "random_layer_selection"),
    ("fl_btn", "flashlight"),
]


@pytest.mark.parametrize("name, field", SCENE_TOGGLES)
def test_a_scene_toggle_flips_the_field(scene_panel, name, field):
    before = scene_panel.scene_data.get(field, False)
    scene_click(scene_panel, name)
    assert scene_panel.scene_data.get(field, False) is not before
    assert scene_panel.undo_stack


def test_the_random_finds_slider_stays_in_range(scene_panel):
    scene_panel.scene_data["auto_random_finds"] = True
    scene_panel._render()
    scene_click(scene_panel, "slider_num_random_finds")
    n_objects = len(scene_panel.scene_data.get("objects", []))
    assert 1 <= scene_panel.scene_data["num_random_finds"] <= n_objects


def test_the_torch_radius_slider_stays_in_range(scene_panel):
    scene_panel.scene_data["flashlight"] = True
    scene_panel._render()
    scene_click(scene_panel, "slider_flashlight_radius")
    assert 50.0 <= scene_panel.scene_data["flashlight_radius"] <= 500.0


def test_the_scene_boxes_start_editing_their_number(scene_panel):
    scene_panel.scene_data["auto_random_finds"] = True
    scene_panel.scene_data["flashlight"] = True
    scene_panel._render()
    for key in ("num_random_finds", "flashlight_radius"):
        scene_click(scene_panel, f"box_{key}")
        assert scene_panel._editing_prop == ("scene", 0, key)
        assert scene_panel._prop_buf != ""


# -----------------------------------------------------------------------------
# THE TWO HALVES CANNOT DRIFT APART AGAIN
# -----------------------------------------------------------------------------

def test_every_control_the_panel_draws_has_an_answer(panel):
    """A hitbox nobody reads is a control that looks alive and is not.

    That is what happened to the greyscale intensity: the panel registered
    gs_box and gs_slider, the click looked for box_grayscale_factor and
    slider_grayscale_factor, and the row did nothing for as long as it existed.
    """
    from editor.mixins import prop_fields as pf

    target = obj(panel)
    target["grayscale"] = True
    target["detection_type"] = "circle"
    panel.scene_data["auto_random_finds"] = False
    panel._render()

    spec_names = {f.box for f in pf.OBJECT_NUM_FIELDS}
    spec_names |= {f.slider for f in pf.OBJECT_NUM_FIELDS}
    spec_names |= {t.hitbox for t in pf.OBJECT_TOGGLES}

    drawn_numeric = {n for n in panel._obj_props_hitboxes
                     if n.startswith(("box_", "slider_"))}
    assert drawn_numeric <= spec_names, (
        f"the panel draws numbers no spec declares: {drawn_numeric - spec_names}")


def test_the_names_of_a_control_come_from_its_key():
    """One key, two names: they cannot be spelled apart on the two sides."""
    from editor.mixins.prop_fields import NumField

    field = NumField("alpha", 0, 255)
    assert field.box == "box_alpha"
    assert field.slider == "slider_alpha"


def test_a_slider_reaches_both_ends_of_its_range(panel):
    """The click maps the far left to the minimum and the far right to the max."""
    from editor.mixins import prop_fields as pf

    spec = next(f for f in pf.OBJECT_NUM_FIELDS if f.key == "alpha")
    lo, hi = panel._prop_range(spec)
    assert panel._prop_value_from_ratio(spec, 0.0) == lo
    assert panel._prop_value_from_ratio(spec, 1.0) == hi
