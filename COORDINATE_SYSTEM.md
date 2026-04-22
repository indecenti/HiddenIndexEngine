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

All coordinates are in a **reference space of 1280×720 pixels** (REF_W × REF_H), independent of:
- Screen resolution
- Zoom level (in editor and during gameplay)
- Pan/scroll offset (in editor and during gameplay)

---

## 1. Coordinate Spaces

### 1.1 Reference Space (1280×720)
**The "truth" coordinate system** — all JSON data, hit areas, and internal calculations use this space.

- Origin **(0, 0)** at top-left
- X increases to the right
- Y increases downward
- **This is the only space that matters for saved data**

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

| Property | Meaning | Reference Space | Example |
|----------|---------|-----------------|---------|
| `x` | Center X | Reference | 640 |
| `y` | Center Y | Reference | 360 |
| `radius` | Distance from center to edge | Reference | 30 |

**Hit detection**:
```python
distance = sqrt((click_x - obj.x)² + (click_y - obj.y)²)
is_hit = distance <= obj.radius
```

**Rendering** (game):
```python
center_screen = ref_to_screen(obj.x, obj.y)
radius_screen = obj.radius * scale_manager.scale
draw_circle(center_screen, radius_screen)
```

**Rendering** (editor):
```python
center_screen = ref_to_screen(obj.x, obj.y)
radius_screen = obj.radius * editor.zoom
draw_circle(center_screen, radius_screen)
```

### 2.2 Rect Objects

| Property | Meaning | Reference Space | Example |
|----------|---------|-----------------|---------|
| `x` | **Top-left corner X** | Reference | 600 |
| `y` | **Top-left corner Y** | Reference | 330 |
| `width` | Width (x increases rightward) | Reference | 80 |
| `height` | Height (y increases downward) | Reference | 60 |

**Bounds** (always in reference space):
```
left   = x
top    = y
right  = x + width
bottom = y + height
center_x = x + width / 2
center_y = y + height / 2
```

**Hit detection** (with rotation):
1. Rotate click point backward around center by `-rotation`
2. Check if rotated point is within [x, x+width] × [y, y+height]

**Rendering** (game):
```python
center_ref = (x + width/2, y + height/2)
center_screen = ref_to_screen(*center_ref)
# Render icon at center_screen, apply rotation
```

---

## 3. Pan and Zoom Handling

### 3.1 Editor Pan/Zoom (Does NOT affect JSON)

The editor allows pan and zoom. These transformations are **purely visual** and do NOT change saved coordinates.

**Coordinate pipeline (editor)**:
```
Mouse (screen) → _s2r() → Reference → scene coordinates
                                          ↓
                                    (unchanged in JSON)
```

Code:
```python
def _s2r(self, sx, sy):
    """Screen → reference coords (inverse of pan/zoom)."""
    return (sx - self.origin_x) / self.zoom, (sy - self.origin_y) / self.zoom

def _r2s(self, rx, ry):
    """Reference → screen coords."""
    return rx * self.zoom + self.origin_x, ry * self.zoom + self.origin_y
```

### 3.2 Game Pan/Zoom (Affects Only Display, NOT Hit Detection)

During gameplay, the engine may apply pan/zoom (e.g., smooth camera). These are stored in `ScalingManager`:

```python
def screen_to_scene(self, sx: int, sy: int) -> tuple[float, float]:
    """
    Screen → reference space, accounting for game pan/zoom.
    Pipeline: screen → viewport (ref) → scene
    """
    rx, ry = self.screen_to_ref(sx, sy)
    # Invert game zoom and pan
    scene_x = (rx - self._pan_x) / self._zoom
    scene_y = (ry - self._pan_y) / self._zoom
    return scene_x, scene_y
```

**Important**: All hit detection uses coordinates in **scene space** (with pan/zoom applied). All JSON and editor coordinates are **reference space**.

---

## 4. Data Flow: Editor → Game

### 4.1 Save Pipeline

**Editor** (reference space) → **JSON file** (reference space) → **Game** (reference space)

1. User places object in editor (coordinates in reference space)
2. Editor stores in memory:
   ```json
   {
     "catalog_id": "chiave",
     "x": 640.0,
     "y": 360.0,
     "detection_type": "circle",
     "radius": 30.0,
     ...
   }
   ```
3. Editor saves JSON (exact same coordinates)
4. Game loads JSON (exact same coordinates)
5. Game uses coordinates for rendering and hit detection

### 4.2 No Transformation at Any Step

```
Editor position (640, 360) 
  ↓ (no change)
JSON: "x": 640, "y": 360
  ↓ (no change)
Game: SceneObject.x = 640.0, SceneObject.y = 360.0
  ↓ (scaled for display only)
Rendered on screen based on screen resolution
```

---

## 5. Critical Invariants

### ✅ Invariant 1: Reference Space Integrity
**All JSON coordinates are in 1280×720 reference space, never in screen space or zoomed space.**

**Verification**:
```python
# ✅ CORRECT - storing reference coordinates
obj["x"] = self._snap(self._drag_start_x + dx)  # dx is in reference space

# ❌ WRONG - storing screen coordinates
obj["x"] = screen_x  # NEVER do this!
```

### ✅ Invariant 2: Coordinate Type Consistency
**Circle**: (x, y) = **center**  
**Rect**: (x, y) = **top-left**

**Verification**:
```python
# CIRCLE hit test
distance = sqrt((sx - obj.x)² + (sy - obj.y)²)
# ✅ assumes (x,y) is center

# RECT hit test
is_hit = (obj.x <= sx <= obj.x + obj.width and
          obj.y <= sy <= obj.y + obj.height)
# ✅ assumes (x,y) is top-left
```

### ✅ Invariant 3: Rotation Center Consistency
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

### ✅ Invariant 4: Screen Space Never Leaks into JSON
**All display operations work in screen/pixel space, but JSON always stays in reference space.**

```python
# ✅ CORRECT
ref_x, ref_y = (640.0, 360.0)
screen_x, screen_y = ref_to_screen(ref_x, ref_y)
display(screen_x, screen_y)
save(ref_x, ref_y)  # ← JSON sees reference space

# ❌ WRONG
screen_x, screen_y = (1920, 1080)
save(screen_x, screen_y)  # ← JSON sees screen space (BROKEN!)
```

---

## 6. Testing and Validation

### 6.1 Unit Tests Required

```python
def test_circle_placement():
    """Verify circle placement in reference space."""
    obj = {"x": 640, "y": 360, "radius": 30, "detection_type": "circle"}
    
    # Click exactly at center
    assert hit_circle(obj, 640, 360) == True
    
    # Click at radius boundary
    assert hit_circle(obj, 670, 360) == True
    
    # Click outside
    assert hit_circle(obj, 700, 360) == False

def test_rect_placement():
    """Verify rect placement in reference space."""
    obj = {"x": 600, "y": 330, "width": 80, "height": 60, "detection_type": "rect"}
    
    # Click at top-left
    assert hit_rect(obj, 600, 330) == True
    
    # Click at center
    assert hit_rect(obj, 640, 360) == True
    
    # Click outside
    assert hit_rect(obj, 500, 250) == False

def test_coordinate_consistency():
    """Verify editor save == game load."""
    # Editor saves object
    editor_obj = {
        "catalog_id": "chiave",
        "x": 640.0,
        "y": 360.0,
        "radius": 30.0,
    }
    
    # Game loads it
    game_obj = SceneObject(**editor_obj)
    
    # Coordinates must be identical
    assert game_obj.x == 640.0
    assert game_obj.y == 360.0
    assert game_obj.radius == 30.0
```

### 6.2 Integration Tests

- [ ] Place object in editor at (640, 360)
- [ ] Save scene to JSON
- [ ] Load scene in game
- [ ] Verify object renders at same position
- [ ] Click on object in game — must be registered as hit
- [ ] Test with various zoom levels (editor)
- [ ] Test with various screen resolutions (game)

---

## 7. Common Mistakes to Avoid

| ❌ Mistake | ✅ Correct | Impact |
|-----------|-----------|--------|
| Storing screen coordinates in JSON | Always use reference coordinates | Objects appear in wrong places |
| Using screen space for hit detection | Always convert to reference first | Clicks miss or hit wrong objects |
| Confusing circle center with rect top-left | Keep types consistent | Hit detection completely broken |
| Applying editor zoom to JSON | Editor zoom is display-only | Objects shift when zooming |
| Forgetting rotation center differs by type | Circle: center, Rect: computed center | Rotation errors at boundaries |
| Pan offset in editor affecting JSON | Pan is display-only | Objects drift with camera pans |

---

## 8. Reference Implementation

### Editor (viewport.py)
```python
def _s2r(self, sx, sy):  # Screen → Reference
    return (sx - self.origin_x) / self.zoom, (sy - self.origin_y) / self.zoom

def _r2s(self, rx, ry):  # Reference → Screen
    return rx * self.zoom + self.origin_x, ry * self.zoom + self.origin_y
```

### Game (scaling_manager.py)
```python
def ref_to_screen(self, rx: float, ry: float):  # Reference → Screen
    sx = int(rx * self._scale + self._offset_x)
    sy = int(ry * self._scale + self._offset_y)
    return sx, sy

def screen_to_ref(self, sx: int, sy: int):  # Screen → Reference
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

- [ ] Objects are placed in reference space
- [ ] JSON stores reference space coordinates
- [ ] Rendering converts reference → screen for display only
- [ ] Hit detection works in reference space
- [ ] Rotation uses correct center (circle vs rect)
- [ ] Pan/zoom in editor doesn't affect JSON
- [ ] Pan/zoom in game doesn't affect hit detection
- [ ] Test with multiple screen resolutions
- [ ] Test with multiple zoom levels (editor)
- [ ] Document coordinate assumptions

---

## 10. Contact & Updates

For questions or corrections, refer to:
- `engine/scaling_manager.py` — Game coordinate transforms
- `editor/mixins/viewport.py` — Editor coordinate transforms
- `engine/click_detector.py` — Hit detection logic
- `games/villa_segreta/levels/level1_giardino/scene1/scene.json` — Example scene
