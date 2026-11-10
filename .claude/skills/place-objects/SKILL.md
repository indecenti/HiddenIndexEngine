---
name: place-objects
description: Place the hidden objects of a HiddenIndexEngine scene so they are believable and well hidden - every object resting on a real surface, at real size in perspective, in a natural pose, lit like its spot, findable but not obvious - with alternative spots for replay. Use when populating or repopulating a scene, when objects "float", look pasted, are too big, too small, too dark or too obvious, when the auto-scatter gives bad results, or when the user says "piazza/nascondi gli oggetti", "popola la scena", "rifai gli oggetti".
---

# place-objects

Tool: `tools/place_on_surfaces.py` (surfaces + support map + camouflage audit). The older
camouflage auto-scatter (`editor/tools/scatter_engine.py`, `tools/populate_scene.py`)
picks spots by colour and edges only: objects end up floating, on walls, in the sky, at
odd sizes. Do not use it for final placement.

## What makes a placement believable (non-negotiable)

1. **It rests on something.** The lowest point of the object's real shape (not its box)
   touches a surface: a shelf board, a table top, a sill, a crate rim, the floor. Never on
   a wall, on glass, in the air, on a painted object's side. Living animals are not placed
   (they need a perch the painting rarely has).
2. **Natural pose.** Bottles, jars, lamps, candles, containers stand. Tools, cutlery,
   knives, keys, bulbs, flasks, rolling pins lie along the surface (the tool lays the
   shape's principal axis horizontal, so diagonal product shots work). Paper (letters,
   newspapers, photos, maps, cards) lies flat, foreshortened with the 4-corner warp.
   Standing objects do not lean (a leaning bottle reads as falling).
3. **Real size, in perspective.** Relative real size comes from the catalog's default
   detection size (a hammer 85, a newspaper 70, a pebble 40); each surface says how big a
   50-unit object is there; areas grow from far to near. On a 1280 px wide screen an
   object stays between 26 and 110 px.
4. **Lit like its spot.** `color_filter` (a per-pixel multiplier in both runtimes) comes
   from the background around the object, plus a little desaturation in low light. Balance
   tested with the user: `LIGHT = {"min": 0.62, "gamma": 0.4, "mix": 0.35, "desat": 0.3}`.
   Darker than that and objects vanish ("troppo scuri non si vedono").
5. **Hidden by colour and value, not by darkness.** No bright outlier (a white newspaper
   or a pale spoon on a dark floor is spotted at once): the lit object's luminance may not
   exceed 1.35x its surroundings; a saturated colour flare is refused. Each spot takes,
   among the free objects, one whose colour is close to the spot.
6. **No rows, no piles.** Objects keep a side gap proportional to their width; each
   surface holds a share of its length. Few, spread groups.
7. **Clear of the HUD.** The bottom 15% of the screen (HUD bar) and the frame margins stay
   empty.
8. **Inside its surface.** The whole visible width sits within the line's ends (nothing
   sticking past a shelf end into the void); an object wider than the board does not go
   there. Side shelves seen at a slant and narrow ledges: leave them out.
9. **Upright only where the eye is level.** The icons are shot near eye level: an upright
   object on a floor or table top seen from above looks lifted. On areas, upright objects
   stand only on the far band (`STAND_AREA_SHARE`); the near part takes lying and flat
   things.
10. **Tucked, not in the open.** On areas the contact point must be close to an edge of the
    support map (wall, foot of a cabinet, crate): `TUCK_MAX` object sizes. Alone in the
    middle of a floor = spotted at once.
11. **Contact shadow** under every object (`"shadow"`, drawn by both runtimes), weaker in
    dark spots, softer under flat things.
12. **Real sizes in cm** from `engine/data/real_sizes_cm.json`; an object missing there is
    not placed (curation). Things that hang (garlic braids, salami, dried fish) and
    duplicates of a painted object (a second slicer next to the painted one) stay out.
13. **Findable.** A lit object darker than `LUM_MIN` is refused: hidden is not invisible.

## Steps

1. **Read the scene at game scale.** `python tools/surface_grid.py <scene_dir> [step]`
   writes `scratch/placement/<scene>_grid.jpg` (labelled background px). Note the shelves,
   tables, sills, floor.
2. **Measure every line surface on a zoomed crop**, never on the full view (an estimate off
   by 20 px makes objects float): `python tools/surface_grid.py <scene_dir> 50 x0,y0,x1,y1`
   shows the crop 1:1 with a 50 px grid. Read the y where painted objects rest on the board.
3. **Write `<scene_dir>/surfaces.json`** (or draw it in the editor: Surfaces mode, key 5,
   with the size gizmo, the HUD band and the support map on the canvas; "Place on
   surfaces" then runs this tool with ghosts, audit sheet, Apply and undo):
   ```json
   {"surfaces": [
     {"p": [1090, 592, 1445, 592], "h": 62, "kind": "shelf"},
     {"p": [2430, 440, 2740, 405], "h": 86, "kind": "shelf"},
     {"p": [240, 1045, 345, 1045], "h": 70, "kind": "sill"},
     {"p": [430, 1110, 1500, 1300], "h": [78, 120], "kind": "area"},
     {"p": [1560, 980, 2450, 1200], "h": [88, 100], "kind": "area"}],
    "h_mul": 1.0}
   ```
   - Lines (`shelf`, `sill`, `ledge`, `table`, `floor`): `p` = resting line left to right,
     for boards seen from the front (eye level), where the model cannot see the top.
     The line snaps to the strongest painted edge within a few px.
   - Areas (`kind: "area"`): `p` = rectangle `[x0, y0, x1, y1]`, `h` = `[far, near]`.
     Objects go only where the **support map** (Metric3D normals pointing up, computed once
     per background and cached in `.editor_cache/geometry/`) holds under the whole base and
     10 px below it. Use areas for floors, table and counter tops, crate tops: anything
     seen from above.
   - `h` = on-screen size, in background px, of a 50-unit object at that line. Calibrate on
     painted objects nearby (a painted bottle on that shelf is about 60 units).
   - Optional `"max"` per surface, `"snap": false` to keep a line exactly where drawn,
     `"light"` per scene to override the balance.
4. **Plan the objects** in `games/<game>/placement_plan.json` (per scene: `level`, `scene`,
   `seed`, `pool` of themed catalog ids - more than `count` -, `clue`, optional
   `minigames`; defaults: `count`, `goals`, `alt_spots`, `collectible`). Themed pools only:
   no modern/branded items in an old village, no cinema posters, no arcade marquees.
5. **Preview** (writes nothing in the game):
   `python tools/place_on_surfaces.py games/<game>/placement_plan.json --preview <scene>`
   -> `scratch/placement/<scene>_v0.jpg` (surfaces drawn, support map tinted green),
   `_v1/_v2.jpg` (alternative spots), `_audit.jpg` (every object cropped with its
   surroundings at twice game size, labelled with its on-screen size).
6. **Review the audit sheet object by object.** Reject and fix: floating (base not on the
   board -> re-measure the line), wrong pose, too small/too big, obvious (bright, saturated,
   alone on an empty patch), half off a shelf end (shorten the line). Re-run until clean.
   Then look at the clean full view at game resolution.
7. **Write**: same command without `--preview`. It rewrites the scene's `objects` (clue
   with `clue_key`, collectible, minigame triggers as fixed goals, `alt_spots`,
   `color_filter`, `grayscale_factor`, flat `corners`) and sets `auto_random_finds` with
   `num_random_finds = goals`.
8. Validate: `pytest tests/test_scene_smoke.py`, then play the scene (desktop
   `python main.py --game <game>`, web export: see the web-export notes in CLAUDE.md).

## Mistakes already made (do not repeat)

- Auto-scatter for final placement: floating hammers, newspapers standing in the road.
- Surfaces read on the full view instead of a 1:1 crop: pails and eggs in mid air.
- Size by "piccolo/medio/grande" tags: tiny shears, tiny bottles. Use the catalog size.
- Light too dark (min 0.30): objects invisible. Too bright: obvious. Keep the balance above.
- Standing every product shot upright: a hammer on its head, a spoon on its tip.
- Rotation sign: both runtimes turn a positive `rotation` counter-clockwise.
- Rows of objects on a wall top: shop-window look.
- Checking only the object's centre on the line: a rolling pin sticking out of a shelf side,
  a sieve half off the board.
- Upright barrel in the near part of the floor: floats, whatever the contact maths says.
- Calibrating `h` by guess: measure it on painted objects of the same surface (a cheese
  wheel ~30 cm, a cup ~12 cm, a bottle ~30 cm) on the 1:1 crop.
- Reviewing at full-view scale only: look at the four full-resolution quadrants too.
