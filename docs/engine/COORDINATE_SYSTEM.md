# HiddenEngine Coordinate System Specification

**Version**: 1.0.0  
**Last Updated**: 2026-04-15  
**Status**: Production

---

## Executive Summary

This document defines the **authoritative coordinate system** for HiddenEngine, ensuring perfect alignment between:
- **Editor** (Pygame level editor with pan/zoom viewport)
- **Game Engine** (Runtime scene rendering and hit detection)
- **JSON scene data** (Persistent object definitions)

There are **two distinct coordinate spaces**, and they must not be confused:

1. **Scene object data space = background-image pixels.** Every `x`, `y`,
   `radius`, `width`, `height` of objects and effects in `scene.json` is an
   absolute pixel coordinate in the scene background's **native resolution**
   (per-scene and variable — e.g. 1920x1080, 5120x2880). It is **not** a fixed
   reference space. See `engine/click_detector.py` (`screen_to_bg_scenic`) and
   `engine/scaling_manager.py`.
2. **UI / menu / HUD space = 1280x720 reference space** (`REF_W x REF_H`). Menu,
   HUD and results-screen layout coordinates use this fixed reference, mapped to
   screen via letterbox scaling.

Both spaces are independent of screen resolution, zoom level and pan/scroll
offset; `ScalingManager` exposes a separate conversion pipeline for each.

---

## 1. Coordinate Spaces

### 1.1 Reference Space (1280x720)
**The UI/menu/HUD coordinate system** — menu, HUD and results-screen layout use this fixed reference space.

- Origin **(0, 0)** at top-left
- X increases to the right
- Y increases downward
- **Applies to UI/HUD only — NOT to `scene.json` object/effect coordinates** (those are in background-image pixels, see 1.1b)

### 1.1b Background-Image Pixel Space (scene object data)
**The "truth" for saved scene data** — every object/effect `x`, `y`, `radius`, `width`, `height` in `scene.json` is an absolute pixel in the background image's native resolution (per-scene, variable).

- Origin **(0, 0)** at the top-left of the background image
- Hit detection converts a screen click into this space via `ScalingManager.screen_to_bg_scenic` before testing against object geometry (`engine/click_detector.py`)
- **This is the only space that matters for saved scene object/effect data**

### 1.2 Screen Space
**The viewport** — varies with device and window size.

The mapping is:
```
screen_x = ref_x * scale_manager.scale + scale_manager.offset_x
screen_y = ref_y * scale_manager.scale + scale_manager.offset_y
```

Where:
- `scale_manager.scale` = min(screen_w / 1280, screen_h / 720)  [letterbox scaling]
- `scale_manager.offset_x/y` = centering offsets for letterbox

### 1.3 Editor Viewport Space (Editor Only)
**The editor's pan/zoom coordinate system** — local to the level editor.

The mapping is:
```
screen_x = ref_x * zoom + origin_x
screen_y = ref_y * zoom + origin_y
```

Where:
- `zoom` = 0.04 to 10.0 (user-controlled)
- `origin_x/y` = pan offset (user-controlled)

**Important**: The editor's `zoom` and `origin` are **not** visible to the game engine.

---

## 2. Object Coordinate Conventions

### 2.1 Circle Objects

| Property | Meaning | Space | Example |
|----------|---------|-------|---------|
| `x` | Center X | Background pixels | 640 |
| `y` | Center Y | Background pixels | 360 |
| `radius` | Distance from center to edge | Background pixels | 30 |

**Hit detection**:
```python
distance = sqrt((click_x - obj.x)**2 + (click_y - obj.y)**2)
is_hit = distance <= obj.radius
```

**Rendering** (game):
```python
center_screen = bg_to_screen(obj.x, obj.y)
radius_screen = obj.radius * scale_manager.bg_display_scale
draw_circle(center_screen, radius_screen)
```

**Rendering** (editor):
```python
center_screen = _r2s(obj.x, obj.y)
radius_screen = obj.radius * editor.zoom
draw_circle(center_screen, radius_screen)
```

### 2.2 Rect Objects

| Property | Meaning | Space | Example |
|----------|---------|-------|---------|
| `x` | **Top-left corner X** | Background pixels | 600 |
| `y` | **Top-left corner Y** | Background pixels | 330 |
| `width` | Width (x increases rightward) | Background pixels | 80 |
| `height` | Height (y increases downward) | Background pixels | 60 |

**Bounds** (always in background pixel space):
```
left   = x
top    = y
right  = x + width
bottom = y + height
center_x = x + width / 2
center_y = y + height / 2
```

**Hit detection** (with rotation):
1. Rotate the click point backward around the center by `-rotation`
2. Check whether the rotated point is within [x, x+width] x [y, y+height]

**Rendering** (game):
```python
center_bg = (x + width/2, y + height/2)
center_screen = bg_to_screen(*center_bg)
# Render the icon at center_screen, apply rotation
```

---

## 3. Pan and Zoom Handling

### 3.1 Editor Pan/Zoom (Does NOT affect JSON)

The editor allows pan and zoom. These transformations are **purely visual** and do NOT change saved coordinates.

**Coordinate pipeline (editor)**:
```
Mouse (screen) -> _s2r() -> background pixels -> scene coordinates
                                                    |
                                              (unchanged in JSON)
```

Code:
```python
def _s2r(self, sx, sy):
    """Screen -> background coords (inverse of pan/zoom)."""
    return (sx - self.origin_x) / self.zoom, (sy - self.origin_y) / self.zoom

def _r2s(self, rx, ry):
    """Background -> screen coords."""
    return rx * self.zoom + self.origin_x, ry * self.zoom + self.origin_y
```

### 3.2 Game Pan/Zoom (Affects Only Display, NOT Hit Detection)

During gameplay, the engine may apply pan/zoom (e.g. a smooth camera). These are stored in `ScalingManager`:

```python
def screen_to_scene(self, sx: int, sy: int) -> tuple[float, float]:
    """
    Screen -> reference space, accounting for game pan/zoom.
    Pipeline: screen -> viewport (ref) -> scene
    """
    rx, ry = self.screen_to_ref(sx, sy)
    # Invert game zoom and pan
    scene_x = (rx - self._pan_x) / self._zoom
    scene_y = (ry - self._pan_y) / self._zoom
    return scene_x, scene_y
```

**Important**: All hit detection uses coordinates in **scene space** (with pan/zoom applied). All JSON and editor coordinates are in **background pixel space**.

---

## 4. Data Flow: Editor -> Game

### 4.1 Save Pipeline

**Editor** (background pixels) -> **JSON file** (background pixels) -> **Game** (background pixels)

1. The user places an object in the editor (coordinates in background pixel space)
2. The editor stores it in memory:
   ```json
   {
     "catalog_id": "old_key",
     "x": 640.0,
     "y": 360.0,
     "detection_type": "circle",
     "radius": 30.0,
     ...
   }
   ```
3. The editor saves the JSON (exact same coordinates)
4. The game loads the JSON (exact same coordinates)
5. The game uses the coordinates for rendering and hit detection

### 4.2 No Transformation at Any Step

```
Editor position (640, 360)
  | (no change)
JSON: "x": 640, "y": 360
  | (no change)
Game: SceneObject.x = 640.0, SceneObject.y = 360.0
  | (scaled for display only)
Rendered on screen based on screen resolution
```

---

## 5. Critical Invariants

### Invariant 1: Data Space Integrity
**All JSON coordinates are in background pixel space, never in screen space or zoomed space.**

**Verification**:
```python
# CORRECT - storing background coordinates
obj["x"] = self._snap(self._drag_start_x + dx)  # dx is in background space

# WRONG - storing screen coordinates
obj["x"] = screen_x  # NEVER do this
```

### Invariant 2: Coordinate Type Consistency
**Circle**: (x, y) = **center**  
**Rect**: (x, y) = **top-left**

**Verification**:
```python
# CIRCLE hit test
distance = sqrt((sx - obj.x)**2 + (sy - obj.y)**2)
# assumes (x,y) is the center

# RECT hit test
is_hit = (obj.x <= sx <= obj.x + obj.width and
          obj.y <= sy <= obj.y + obj.height)
# assumes (x,y) is the top-left
```

### Invariant 3: Rotation Center Consistency
**Circle**: center of rotation = (x, y)  
**Rect**: center of rotation = (x + width/2, y + height/2)

**Verification**:
```python
# CIRCLE
cx, cy = ox, oy
rotated = rotate_point(point, cx, cy, rotation)

# RECT
cx, cy = ox + ow/2, oy + oh/2
rotated = rotate_point(point, cx, cy, rotation)
```

### Invariant 4: Screen Space Never Leaks into JSON
**All display operations work in screen/pixel space, but JSON always stays in background pixel space.**

```python
# CORRECT
bg_x, bg_y = (640.0, 360.0)
screen_x, screen_y = bg_to_screen(bg_x, bg_y)
display(screen_x, screen_y)
save(bg_x, bg_y)  # JSON sees background space

# WRONG
screen_x, screen_y = (1920, 1080)
save(screen_x, screen_y)  # JSON sees screen space (BROKEN)
```

---

## 6. Testing and Validation

### 6.1 Unit Tests Required

```python
def test_circle_placement():
    """Verify circle placement in background space."""
    obj = {"x": 640, "y": 360, "radius": 30, "detection_type": "circle"}

    # Click exactly at the center
    assert hit_circle(obj, 640, 360) == True

    # Click at the radius boundary
    assert hit_circle(obj, 670, 360) == True

    # Click outside
    assert hit_circle(obj, 700, 360) == False

def test_rect_placement():
    """Verify rect placement in background space."""
    obj = {"x": 600, "y": 330, "width": 80, "height": 60, "detection_type": "rect"}

    # Click at the top-left
    assert hit_rect(obj, 600, 330) == True

    # Click at the center
    assert hit_rect(obj, 640, 360) == True

    # Click outside
    assert hit_rect(obj, 500, 250) == False

def test_coordinate_consistency():
    """Verify editor save == game load."""
    # The editor saves an object
    editor_obj = {
        "catalog_id": "old_key",
        "x": 640.0,
        "y": 360.0,
        "radius": 30.0,
    }

    # The game loads it
    game_obj = SceneObject(**editor_obj)

    # Coordinates must be identical
    assert game_obj.x == 640.0
    assert game_obj.y == 360.0
    assert game_obj.radius == 30.0
```

### 6.2 Integration Tests

- [ ] Place an object in the editor at (640, 360)
- [ ] Save the scene to JSON
- [ ] Load the scene in the game
- [ ] Verify the object renders at the same position
- [ ] Click on the object in the game — it must register as a hit
- [ ] Test with various zoom levels (editor)
- [ ] Test with various screen resolutions (game)

---

## 7. Common Mistakes to Avoid

| Mistake | Correct | Impact |
|---------|---------|--------|
| Storing screen coordinates in JSON | Always use background coordinates | Objects appear in the wrong places |
| Using screen space for hit detection | Always convert to background space first | Clicks miss or hit the wrong objects |
| Confusing circle center with rect top-left | Keep the types consistent | Hit detection completely broken |
| Applying editor zoom to JSON | Editor zoom is display-only | Objects shift when zooming |
| Forgetting that the rotation center differs by type | Circle: center, Rect: computed center | Rotation errors at the boundaries |
| Editor pan offset affecting JSON | Pan is display-only | Objects drift with camera pans |

---

## 8. Reference Implementation

### Editor (viewport.py)
```python
def _s2r(self, sx, sy):  # Screen -> Background
    return (sx - self.origin_x) / self.zoom, (sy - self.origin_y) / self.zoom

def _r2s(self, rx, ry):  # Background -> Screen
    return rx * self.zoom + self.origin_x, ry * self.zoom + self.origin_y
```

### Game (scaling_manager.py)
```python
def ref_to_screen(self, rx: float, ry: float):  # Reference -> Screen (UI/HUD)
    sx = int(rx * self._scale + self._offset_x)
    sy = int(ry * self._scale + self._offset_y)
    return sx, sy

def screen_to_ref(self, sx: int, sy: int):  # Screen -> Reference (UI/HUD)
    rx = (sx - self._offset_x) / self._scale
    ry = (sy - self._offset_y) / self._scale
    return rx, ry

def screen_to_scene(self, sx: int, sy: int):  # With game pan/zoom
    rx, ry = self.screen_to_ref(sx, sy)
    scene_x = (rx - self._pan_x) / self._zoom
    scene_y = (ry - self._pan_y) / self._zoom
    return scene_x, scene_y
```

---

## 9. Checklist for New Features

When adding new features that involve positioning:

- [ ] Objects are placed in background pixel space
- [ ] JSON stores background pixel coordinates
- [ ] Rendering converts background -> screen for display only
- [ ] Hit detection works in background pixel space
- [ ] Rotation uses the correct center (circle vs rect)
- [ ] Pan/zoom in the editor does not affect JSON
- [ ] Pan/zoom in the game does not affect hit detection
- [ ] Tested with multiple screen resolutions
- [ ] Tested with multiple zoom levels (editor)
- [ ] Coordinate assumptions documented

---

## 10. Contact & Updates

For questions or corrections, refer to:
- `engine/scaling_manager.py` — game coordinate transforms
- `editor/mixins/viewport.py` — editor coordinate transforms
- `engine/click_detector.py` — hit detection logic
- `games/Malonno_Survivors/levels/Welcome_To_Malonno/Villa_Rosa/scene.json` — example scene
