# HiddenEngine Coordinate Debug Guide

**Last Updated**: 2026-04-15

---

## Quick Start

### Enabling the Coordinate Inspector

Press **'D'** in the level editor to toggle the coordinate inspector overlay.

The inspector displays:
- **Screen**: current mouse position in screen pixels
- **Ref**: mouse position in background pixel space — **this is what matters**
- **Zoom/Pan**: current editor zoom level and pan offset
- **Grid**: snapped coordinates when the grid is enabled
- **Object Info**: details about any object under the cursor

### Understanding the Display

```
Screen:  (1024,  768) px          <- varies by window size
Ref:     (640.0, 360.0)           <- CONSTANT (background space)
Zoom: 1.50x | Pan: (100, 50)
```

When you move the mouse around, notice:
- **Screen coordinates change** (affected by window position)
- **Ref coordinates change** (cursor position in background space)
- **Zoom and Pan show the editor's view transform**

---

## Testing Coordinate Consistency

### Test 1: Editor -> JSON -> Game

1. **Place an object in the editor at background coordinates (640, 360)**
   - Open the level editor: `python run_editor.py --game Malonno_Survivors`
   - Select a shape (circle or rect) from the catalog
   - Click at the center of the canvas (should show `Ref: (640.0, 360.0)`)
   - Press 'D' to verify the coordinates in the inspector
   - Save the scene (Ctrl+S)

2. **Verify the JSON**
   - Open the saved JSON file: `games/Malonno_Survivors/levels/Welcome_To_Malonno/Villa_Rosa/scene.json`
   - Search for the object you just placed
   - Confirm it has `"x": 640.0, "y": 360.0` (or close to it)

3. **Test in game**
   - Run the game: `python main.py --game Malonno_Survivors --scene Welcome_To_Malonno/Villa_Rosa`
   - The object should appear at the same position
   - Click on it — it should register as a hit

### Test 2: Zoom Independence

1. **Place an object at (640, 360) with zoom = 1.0**
2. **Zoom in to 2.0 (scroll wheel up)**
3. **Notice:**
   - Screen coordinates change significantly
   - Background coordinates stay the same
   - JSON remains unchanged

This verifies that editor zoom is purely visual.

### Test 3: Hit Detection Accuracy

1. **Place a circle at (640, 360) with radius 30**
2. **Enable the coordinate inspector (press 'D')**
3. **Move the cursor to (640, 360)** — should show "OBJECT UNDER CURSOR"
4. **Move the cursor to (670, 360)** — should still show the object (inside the radius)
5. **Move the cursor to (671, 360)** — should NOT show the object (outside the radius)

This verifies that hit detection uses background space correctly.

### Test 4: Rect Top-Left Convention

1. **Place a rect at (600, 330) with size 80x60**
2. **Move the cursor to (600, 330)** — object detected (top-left)
3. **Move the cursor to (680, 330)** — object detected (top-right = 600+80)
4. **Move the cursor to (600, 390)** — object detected (bottom-left = 330+60)
5. **Move the cursor to (681, 390)** — object NOT detected (outside)

This verifies the top-left corner convention.

---

## Debugging Coordinate Issues

### Issue: "Object appears in the wrong place in the game"

**Diagnosis**:
1. Place the object in the editor at position X
2. Note the background coordinates in the inspector
3. Save and check the JSON — do the coordinates match?
4. Load in the game — are the coordinates loaded correctly?

**Common causes**:
- The editor saved wrong coordinates (check the JSON)
- The game did not load correctly (check console errors)
- Screen resolution mismatch (the game scales differently)

### Issue: "Clicks don't register on objects"

**Diagnosis**:
1. Place an object and enable the inspector (D)
2. Move the cursor exactly over the object
3. Check whether "OBJECT UNDER CURSOR" appears
4. If not, the coordinates are misaligned

**Common causes**:
- The object hit area is too small (`radius` or `width`/`height`)
- The coordinates are in the wrong space (they must always be background pixels)
- The object is on a hidden layer

### Issue: "Zoom makes objects shift visually"

**This should NOT happen.** Objects sit at fixed background coordinates.

**If it does happen:**
1. Check the `_s2r` and `_r2s` transforms in `editor/mixins/viewport.py`
2. Verify that `origin_x/y` and `zoom` are applied correctly
3. Compare with `engine/scaling_manager.py` (should be similar but different)

---

## Coordinate Spaces

### The "truth" space for scene data: background pixels

All objects are defined in the native pixel space of the scene background,
regardless of screen size or zoom. UI, menus and HUD use a separate fixed
1280x720 reference space. See `../engine/COORDINATE_SYSTEM.md`.

```
Origin (0, 0) ------- X increases ->
     |
     |
     Y
   increases
     v

    (bg_w, bg_h)
```

### Transformation Pipeline

**Editor Display**:
```
Mouse clicks (screen)
        |
    _s2r() transform
        |
Background space (the truth)
        |
    _r2s() transform
        |
Display on screen
```

**Game Display**:
```
Mouse clicks (screen)
        |
    screen_to_bg_scenic() transform
        |
Background space (the truth)
        |
    bg_to_screen() transform + sprites
        |
Display on screen
```

---

## JSON Validation

### Checking for Errors

Run the validation tests:
```bash
python -m pytest tests/test_coordinate_system.py -v
```

### Manual JSON Check

Open any scene file (e.g. `games/Malonno_Survivors/levels/Welcome_To_Malonno/Villa_Rosa/scene.json`):

For **circles**:
```json
{
  "catalog_id": "old_key",
  "x": 640.0,           // Center X in background pixels
  "y": 360.0,           // Center Y in background pixels
  "detection_type": "circle",
  "radius": 30.0        // Radius in background pixels
}
```

For **rects**:
```json
{
  "catalog_id": "old_book",
  "x": 600.0,           // Top-left X in background pixels
  "y": 330.0,           // Top-left Y in background pixels
  "detection_type": "rect",
  "width": 80.0,        // Width in background pixels
  "height": 60.0        // Height in background pixels
}
```

**Rules**:
- All numeric coordinates are in background pixel space
- Circle `(x, y)` = center point
- Rect `(x, y)` = top-left corner
- No screen pixels anywhere
- No editor zoom/pan applied

---

## Performance Notes

### Coordinate Inspector Overhead

The inspector runs in real time and has minimal overhead:
- ~1-2 ms per frame on modern hardware
- Uses alpha blending for the overlay
- Disabled by default (toggle with 'D')

### Disabling for Production

In a shipped game the inspector would be compiled out. In the editor it is always available.

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

- `../engine/COORDINATE_SYSTEM.md` — complete specification
- `engine/scaling_manager.py` — game coordinate transforms
- `editor/mixins/viewport.py` — editor coordinate transforms
- `editor/debug/coordinate_inspector.py` — inspector implementation
- `tests/test_coordinate_system.py` — test suite
- `games/Malonno_Survivors/levels/Welcome_To_Malonno/Villa_Rosa/scene.json` — example scene
