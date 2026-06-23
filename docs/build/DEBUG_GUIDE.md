# HiddenEngine Coordinate Debug Guide

**Last Updated**: 2026-04-15

---

## Quick Start

### Enabling the Coordinate Inspector

Press **'D'** in the level editor to toggle the coordinate inspector overlay.

The inspector displays:
- **Screen**: Current mouse position in screen pixels
- **Ref**: Mouse position in reference space (1280×720) — **this is what matters**
- **Zoom/Pan**: Current editor zoom level and pan offset
- **Grid**: Snapped coordinates when grid is enabled
- **Object Info**: Details about any object under the cursor

### Understanding the Display

```
Screen:  (1024,  768) px          ← Varies by window size
Ref:     (640.0, 360.0)           ← CONSTANT (reference space)
Zoom: 1.50x | Pan: (100, 50)
```

When you move the mouse around, notice:
- **Screen coordinates change** (affected by window position)
- **Ref coordinates change** (cursor position in reference space)
- **Zoom and Pan show the editor's view transform**

---

## Testing Coordinate Consistency

### Test 1: Editor → JSON → Game

1. **Place an object in the editor at reference coordinates (640, 360)**
   - Open the level editor: `python -m editor.editor_base --game villa_segreta`
   - Select a shape (circle or rect) from the catalog
   - Click at the center of the screen (should show `Ref: (640.0, 360.0)`)
   - Press 'D' to verify the coordinates in the inspector
   - Save the scene (Ctrl+S)

2. **Verify the JSON**
   - Open the saved JSON file: `games/villa_segreta/levels/level1_giardino/scene1/scene.json`
   - Search for the object you just placed
   - Confirm it has `"x": 640.0, "y": 360.0` (or close to it)

3. **Test in game**
   - Run the game: `python main.py --game villa_segreta`
   - Load the level and scene
   - The object should appear at the same position
   - Click on it — it should be registered as a hit

### Test 2: Zoom Independence

1. **Place an object at (640, 360) with zoom = 1.0**
2. **Zoom in to 2.0 (Scroll wheel up)**
3. **Notice:**
   - Screen coordinates change significantly
   - Reference coordinates stay the same
   - JSON remains unchanged

This verifies that editor zoom is purely visual.

### Test 3: Hit Detection Accuracy

1. **Place a circle at (640, 360) with radius 30**
2. **Enable the coordinate inspector (press 'D')**
3. **Move cursor to (640, 360)** — should show "OBJECT UNDER CURSOR"
4. **Move cursor to (670, 360)** — should still show the object (inside radius)
5. **Move cursor to (671, 360)** — should NOT show the object (outside radius)

This verifies that hit detection uses reference space correctly.

### Test 4: Rect Top-Left Convention

1. **Place a rect at (600, 330) with size 80×60**
2. **Move cursor to (600, 330)** — object detected (top-left)
3. **Move cursor to (680, 330)** — object detected (top-right = 600+80)
4. **Move cursor to (600, 390)** — object detected (bottom-left = 330+60)
5. **Move cursor to (681, 390)** — object NOT detected (outside)

This verifies the top-left corner convention.

---

## Debugging Coordinate Issues

### Issue: "Object appears in wrong place in game"

**Diagnosis**:
1. Place the object in the editor at position X
2. Note the reference coordinates in the inspector
3. Save and check the JSON — do coordinates match?
4. Load in game — are coordinates loaded correctly?

**Common causes**:
- Editor saved wrong coordinates (check JSON)
- Game didn't load correctly (check console errors)
- Screen resolution mismatch (game scales differently)

### Issue: "Clicks don't register on objects"

**Diagnosis**:
1. Place an object and enable the inspector (D)
2. Move cursor exactly over the object
3. Check if "OBJECT UNDER CURSOR" appears
4. If not, coordinates are misaligned

**Common causes**:
- Object hit area is too small (`radius` or `width`/`height`)
- Coordinates are in wrong space (should always be reference)
- Object is on a hidden layer

### Issue: "Zoom makes objects shift visually"

**This should NOT happen.** Objects are at fixed reference coordinates.

**If it does happen:**
1. Check the `_s2r` and `_r2s` transformations in `editor/mixins/viewport.py`
2. Verify that `origin_x/y` and `zoom` are applied correctly
3. Compare with `engine/scaling_manager.py` (should be similar but different)

---

## Reference Coordinate System

### The "Truth" Space: 1280×720

All objects are defined in this space, regardless of screen size or zoom.

```
Origin (0, 0) ─────── X increases →
     │
     │
     Y
   increases
     ↓

    (1280, 720)
```

### Transformation Pipeline

**Editor Display**:
```
Mouse clicks (screen)
        ↓
    _s2r() transform
        ↓
Reference space (the truth)
        ↓
    _r2s() transform
        ↓
Display on screen
```

**Game Display**:
```
Mouse clicks (screen)
        ↓
    screen_to_scene() transform
        ↓
Reference/scene space (the truth)
        ↓
    ref_to_screen() transform + sprites
        ↓
Display on screen
```

---

## JSON Validation

### Checking for Errors

Run the validation tests:
```bash
python -m pytest tests/test_coordinate_system.py -v
```

Expected output: **21 passed**

### Manual JSON Check

Open any scene file (e.g., `games/villa_segreta/levels/level1_giardino/scene1/scene.json`):

For **circles**:
```json
{
  "catalog_id": "chiave",
  "x": 640.0,           // Center X in reference space
  "y": 360.0,           // Center Y in reference space
  "detection_type": "circle",
  "radius": 30.0        // Radius in reference space
}
```

For **rects**:
```json
{
  "catalog_id": "libro",
  "x": 600.0,           // Top-left X in reference space
  "y": 330.0,           // Top-left Y in reference space
  "detection_type": "rect",
  "width": 80.0,        // Width in reference space
  "height": 60.0        // Height in reference space
}
```

**Rules**:
- All numeric coordinates are in reference space (1280×720)
- Circle `(x, y)` = center point
- Rect `(x, y)` = top-left corner
- No screen pixels anywhere
- No editor zoom/pan applied

---

## Performance Notes

### Coordinate Inspector Overhead

The inspector runs in real-time and has minimal overhead:
- ~1-2ms per frame on modern hardware
- Uses alpha blending for the overlay
- Disabled by default (toggle with 'D')

### Disabling for Production

In a shipping game, the inspector would be compiled out. For the editor, it's always available.

---

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| **D** | Toggle coordinate inspector |
| **G** | Toggle grid |
| **Scroll** | Zoom in/out |
| **Middle Mouse** | Pan (drag to scroll) |
| **Ctrl+Z** | Undo |
| **Ctrl+S** | Save scene |

---

## Files Referenced

- `COORDINATE_SYSTEM.md` — Complete specification
- `engine/scaling_manager.py` — Game coordinate transforms
- `editor/mixins/viewport.py` — Editor coordinate transforms
- `editor/debug/coordinate_inspector.py` — Inspector implementation
- `tests/test_coordinate_system.py` — Test suite
- `games/villa_segreta/levels/level1_giardino/scene1/scene.json` — Example scene
