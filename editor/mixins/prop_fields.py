"""
editor/mixins/prop_fields.py

The controls of the properties panel, declared once.

The panel is drawn by `RenderPanelsMixin._r_props` and answered by
`InputHandlersMixin._props_click`: the render registers a named hitbox for
every control, the click looks those names up. Nothing tied the two halves
together, so each side carried its own copy of the same facts: the range of
every slider was written in the render at the call site and again in a table
in the click, and the names were spelled by hand on both sides. They drifted.
The greyscale intensity registered `gs_box` and `gs_slider` while the click
looked for `box_grayscale_factor` and `slider_grayscale_factor`, so that box
and that slider were drawn, hovered and dragged, and did nothing at all.

Here the fields are data. `NumField` gives a control its key, its range and
how the value is written, and derives the two hitbox names from the key, so
they cannot be spelled differently on the two sides. `ToggleField` does the
same for the buttons that flip a boolean. The render reads the specs to draw,
the click reads them to act, and a control that is not drawn registers no
hitbox and therefore answers to nothing, which is what makes the conditional
rows (the torch radius, the greyscale intensity, the size of the hit shape)
work without a second copy of the condition in the click.
"""

from dataclasses import dataclass
from typing import Union

from editor.constants import ALWAYS_C, ERR_C, FX_C, OK_C, WARN_C

# Maxima that are only known while the editor runs. The render and the click
# both resolve them through PropFieldsMixin._prop_range.
MAX_BG_WIDTH = "bg_width"
MAX_BG_HEIGHT = "bg_height"
MAX_OBJECT_COUNT = "object_count"

# How long the status line of a toggle stays up.
TOGGLE_STATUS_SECS = 2


@dataclass(frozen=True)
class NumField:
    """A number edited by a text box and a slider side by side."""

    key: str                    # attribute on the object, or on the scene
    lo: float
    hi: Union[float, str]       # a number, or one of the MAX_* tokens
    fmt: str = "{:.0f}"         # how the value is written in the box
    integer: bool = True        # the slider yields whole numbers
    decimals: int = 2           # rounding when it does not

    @property
    def box(self) -> str:
        """Hitbox name of the text box."""
        return f"box_{self.key}"

    @property
    def slider(self) -> str:
        """Hitbox name of the slider."""
        return f"slider_{self.key}"


@dataclass(frozen=True)
class ToggleField:
    """A boolean flipped by a single button."""

    hitbox: str
    field: str
    default: bool = False
    # With more than one object selected, the new value is the negation of the
    # first object's, unless from_all is set: then it is the negation of "every
    # one of them is on", which turns a mixed selection all on. The panel has
    # always behaved both ways depending on the button; the difference is kept
    # as it was, and is at least visible here now.
    from_all: bool = False
    status_key: str = ""
    status_text: str = ""
    status_color: tuple = ()


# ─────────────────────────────────────────────────────────────────────────────
# OBJECT
# ─────────────────────────────────────────────────────────────────────────────

OBJECT_NUM_FIELDS = (
    NumField("x", 0, MAX_BG_WIDTH),
    NumField("y", 0, MAX_BG_HEIGHT),
    NumField("scale", 0.1, 3.0, "{:.2f}", integer=False),
    NumField("rotation", 0, 360),
    NumField("alpha", 0, 255),
    NumField("layer_z", 0, 100),
    NumField("radius", 5, 500),
    NumField("width", 5, 1000),
    NumField("height", 5, 1000),
    NumField("grayscale_factor", 0.0, 1.0, "{:.2f}", integer=False),
)

OBJECT_TOGGLES = (
    ToggleField("goal_btn", "is_goal", default=True),
    ToggleField("always_btn", "always_show"),
    ToggleField("hide_btn", "editor_hidden", from_all=True,
                status_key="ih_hide_editor", status_text="Hide editor: {0}",
                status_color=WARN_C),
    ToggleField("lock_btn", "editor_locked", from_all=True,
                status_key="ih_lock_editor", status_text="Lock editor: {0}",
                status_color=ERR_C),
    ToggleField("flip_h", "flip_x"),
    ToggleField("flip_v", "flip_y"),
    ToggleField("grayscale", "grayscale"),
)


# ─────────────────────────────────────────────────────────────────────────────
# SCENE
# ─────────────────────────────────────────────────────────────────────────────

SCENE_NUM_FIELDS = (
    NumField("num_random_finds", 1, MAX_OBJECT_COUNT),
    NumField("flashlight_radius", 50.0, 500.0, "{:.1f}", integer=False, decimals=1),
)

OBJECT_NUM_BY_KEY = {f.key: f for f in OBJECT_NUM_FIELDS}

SCENE_TOGGLES = (
    ToggleField("auto_btn", "auto_random_finds",
                status_key="ih_auto_rotation", status_text="Auto rotation: {0}",
                status_color=OK_C),
    ToggleField("rand_l_btn", "random_layer_selection",
                status_key="ih_random_layer", status_text="Random layer mode: {0}",
                status_color=ALWAYS_C),
    ToggleField("fl_btn", "flashlight",
                status_key="ih_torch", status_text="Torch: {0}",
                status_color=FX_C),
)


SCENE_NUM_BY_KEY = {f.key: f for f in SCENE_NUM_FIELDS}


class PropFieldsMixin:
    """Shared reading of the specs, used by both halves of the panel."""

    def _prop_range(self, spec: NumField) -> tuple:
        """The (low, high) of a field, resolving the runtime maxima."""
        hi = spec.hi
        if hi == MAX_BG_WIDTH or hi == MAX_BG_HEIGHT:
            size = self._get_bg_size()
            from editor.constants import REF_H, REF_W
            if hi == MAX_BG_WIDTH:
                hi = size[0] if size else REF_W
            else:
                hi = size[1] if size else REF_H
        elif hi == MAX_OBJECT_COUNT:
            hi = len(self.scene_data.get("objects", []))
        return spec.lo, hi

    def _prop_spec(self, key: str, scene: bool = False) -> tuple:
        """A field and its resolved range, in one call for the render."""
        table = SCENE_NUM_BY_KEY if scene else OBJECT_NUM_BY_KEY
        spec = table[key]
        lo, hi = self._prop_range(spec)
        return spec, lo, hi

    def _prop_value_from_ratio(self, spec: NumField, ratio: float):
        """Where a click at that fraction of the slider lands."""
        lo, hi = self._prop_range(spec)
        value = lo + ratio * (hi - lo)
        return int(value) if spec.integer else round(value, spec.decimals)

    # ─────────────────────────────────────────────────────────────────────────
    # ACTIONS
    # ─────────────────────────────────────────────────────────────────────────
    # What clicking a control does. One body per kind of control instead of one
    # per control: the panel had the same five lines written out fifteen times.

    def _prop_toggle(self, spec: ToggleField, targets: list) -> None:
        """Flip a boolean on every target, undoable, with its status line."""
        self._push_undo()
        if spec.from_all:
            new_val = not all(t.get(spec.field, spec.default) for t in targets)
        else:
            new_val = not targets[0].get(spec.field, spec.default)
        for target in targets:
            target[spec.field] = new_val
        self.scene_dirty = True
        self._mark_dirty()
        if spec.status_key:
            self._status(
                self._TR(spec.status_key, spec.status_text).format(
                    "ON" if new_val else "OFF"),
                spec.status_color, TOGGLE_STATUS_SECS)

    def _prop_edit_text(self, spec: NumField, source: dict) -> str:
        """What the box shows when it takes the focus."""
        if spec.key == "grayscale_factor":
            # The intensity is stored as a fraction and edited as a percentage.
            return str(int(round(source.get(spec.key, 1.0) * 100)))
        if spec.key == "layer_z":
            # Unset means the depth the object's layer gives it.
            from editor.constants import layer_z as default_layer_z
            value = source.get("layer_z")
            if value is None:
                value = default_layer_z(source.get("layer", "objects_mid"))
            return str(int(value))
        return spec.fmt.format(source.get(spec.key, 0))

    def _prop_begin_edit(self, spec: NumField, owner: str, index: int,
                         source: dict) -> None:
        """Give the box the keyboard, filled with the current value."""
        self._editing_prop = (owner, index, spec.key)
        self._prop_buf = self._prop_edit_text(spec, source)

    def _prop_slider_click(self, spec: NumField, rect, mx: int, targets: list,
                           owner: str, index: int) -> None:
        """Set the value where the slider was clicked and start dragging it."""
        from editor.ui.draw import _clamp
        self._push_undo()
        ratio = _clamp((mx - rect.x) / rect.w, 0.0, 1.0)
        value = self._prop_value_from_ratio(spec, ratio)
        for target in targets:
            target[spec.key] = value
        self.scene_dirty = True
        self._mark_dirty()
        lo, hi = self._prop_range(spec)
        self._dragging_slider = (owner, index, spec.key, lo, hi, rect.x, rect.w)

    def _prop_num_click(self, specs, hitboxes: dict, mx: int, my: int,
                        targets: list, owner: str, index: int) -> bool:
        """Route a click to the box or the slider of a number. True if taken.

        A control the panel did not draw registered no hitbox, so there is no
        second copy here of the conditions that decide what is on screen.
        """
        from editor.ui.draw import _in_rect
        for spec in specs:
            box = hitboxes.get(spec.box)
            if box is not None and _in_rect((mx, my), box):
                self._prop_begin_edit(spec, owner, index, targets[0])
                return True
            slider = hitboxes.get(spec.slider)
            if slider is not None and _in_rect((mx, my), slider):
                self._prop_slider_click(spec, slider, mx, targets, owner, index)
                return True
        return False

    def _prop_toggle_click(self, specs, hitboxes: dict, mx: int, my: int,
                           targets: list) -> bool:
        """Route a click to a toggle button. True if one took it."""
        from editor.ui.draw import _in_rect
        for spec in specs:
            box = hitboxes.get(spec.hitbox)
            if box is not None and _in_rect((mx, my), box):
                self._prop_toggle(spec, targets)
                return True
        return False
