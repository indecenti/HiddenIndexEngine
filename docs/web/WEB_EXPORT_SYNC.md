# Web Export — Engine <-> Web Synchronization Contract

> SET IN STONE. Read this before changing the engine.

The web runtime (modular sources in `editor/web_template/runtime/`: `core.js`,
`game.js`, `minigames/<id>.js`, `bootstrap.js` — concatenated into `runtime.js` by
`web_exporter._bundle_runtime`) **does not import** Python code:
it **replicates** the engine logic in JavaScript. Therefore every change to a formula,
constant or data structure listed below **MUST** be propagated to the web, otherwise
the exported game silently diverges (invisible bugs: misplaced objects, wrong scores,
clicks that miss).

## Golden rule
If you touch one of the files/values in the "ENGINE" column, update the corresponding
"WEB" one in the same PR and re-run the verification (see the end). **Data structures**
flow through `editor/web_exporter.py` (manifest); **formulas** are duplicated in
`runtime.js`.

## Automatic enforcement (already active)
- **Numeric constants** (scoring, hints, ref): single source `editor/web_rules.py::engine_rules()`,
  which READS the values from the engine and injects them into `manifest.rules`. The runtime uses
  `this.R` = `{RULES_DEFAULTS, ...manifest.rules}`. Changing the constant in the engine propagates
  it to the web at the next export, automatically.
- **Anti-drift test (constants)**: `pytest tests/test_web_sync.py::test_runtime_defaults_match_engine`
  verifies that the engine and `RULES_DEFAULTS` (fallback in `runtime/core.js`) are aligned
  (including `miss_penalty_curve` and `miss_combo_window`); it fails on drift.
- **BEHAVIORAL parity test** (beyond constants): runs the REAL JS formulas through
  `node` (harness `tests/js/score_parity_harness.js`) and compares them with the engine on golden
  vectors — `test_scene_score_parity_python_vs_js` (end-of-scene bonus/stars/score) and
  `test_miss_penalty_parity_python_vs_js` (miss penalty curve). A divergence in a FORMULA,
  not only in a constant, becomes a test failure.
- **Real scene smoke tests**: `tests/test_scene_smoke.py` loads every `scene.json` through the real
  `SceneLoader` (validation + catalog join) and verifies that the goals are hittable.
- What remains **manual** (not automatable as values): the projection, hit-test, effect and
  flashlight **formulas** — listed below. Touching them in the engine requires updating the
  modules in `editor/web_template/runtime/` by hand.

---

## A. Coordinates and rendering (CRITICAL — the mission)

| ENGINE | WEB | What must match |
|---|---|---|
| `engine/scaling_manager.py` `set_background`, `bg_to_screen`, `screen_to_bg`, `REF_W/REF_H=1280/720` | `runtime.js` class `ScalingManager` | Letter for letter: letterbox `fit=min(sw/(bw*s),sh/(bh*s))`, `display_scale=fit*s`, centering. |
| `engine/core.py` object rendering (center/size, transform order) | `runtime.js` `objCenterAndSize`, `drawObject` | rect: center = x+w/2; circle: center = x,y. Order: scale -> warp -> flip -> **rotate** -> alpha. |
| Rotation: Pygame `rotozoom` = CCW for a positive angle | `runtime.js` `ctx.rotate(-rotation*PI/180)` | Canvas has Y pointing down: rotate by **-angle**. DO NOT change the sign. |
| `engine/click_detector.py` `_hit_circle/_hit_rect/_rotate_point/_is_point_in_poly`, warp, flip | `runtime.js` `hitCircle/hitRect/rotatePoint/pointInPoly/warpPoly` | Same formulas (ellipse, point rotation by -angle, ray casting). |
| `engine/effect_renderer.py` corner warp | `runtime.js` `warpPoly` + `drawImageQuad` (2 triangles) | The hit polygon and the render polygon use the same `warpPoly`. |
| **Stretch**: icon scaled to `width` x `height` (hitbox), not to the native aspect | `drawObject` (`iconW/iconH = w/h * bg_display_scale * scale`) | exact |
| **Opacity**: `surface.set_alpha(obj.alpha)` | `drawObject` `globalAlpha = alpha/255` | exact |
| **Grayscale**: `engine/utils.py:apply_grayscale` (Rec.601 luma 0.299/0.587/0.114, `out=c*(1-f)+luma*f`, sRGB) | `processedIcon` + `_grayFilterUrl` (SVG feColorMatrix sRGB) | **exact** (delta 0). If you change the coefficients/formula in `apply_grayscale`, update `_grayFilterUrl`. |
| **color_filter (tint)**: `BLEND_RGBA_MULT` (multiplication) | `processedIcon` (composite `multiply` + `destination-in`) | per-channel multiplication |
| **flip_x/flip_y**: `pygame.transform.flip` | `drawObject` `ctx.scale(+-1,+-1)` | exact |
| Engine filter order: scale->warp->flip->rotate->grayscale->color_filter->alpha | web: grayscale/tint in `processedIcon`, then flip/rotate/alpha in `drawObject` | equivalent (per-pixel operations commute with the geometric ones) |

Object coordinate space: **pixels of the original background** (`bg_w` x `bg_h`).
rect -> x/y top-left; circle -> x/y center. Exported 1:1 in the manifest.

---

## B. Scoring and stars

| ENGINE (`engine/level_manager.py`) | Value | WEB (`runtime.js`) |
|---|---|---|
| `POINTS_PER_OBJECT` | 100 | `POINTS_PER_OBJECT` |
| `BONUS_TIME_MAX` | 500 | `BONUS_TIME_MAX` |
| `STAR_MULTIPLIER` | `{1:1, 2:1, 3:2}` | `STAR_MULTIPLIER` |
| `MISS_PENALTY_TIME` | 5.0 s | `miss_time_penalty` |
| `MISS_PENALTY_CURVE` progressive on consecutive misses (window `MISS_COMBO_WINDOW`=1.5 s) | `[25,50,100,150,300,500]` | `miss_penalty_curve` + `_missPenalty`/consecutive state in `_onPointer`; **the score can go NEGATIVE** (no floor), like the engine |
| `bonus = int(time_ratio * BONUS_TIME_MAX)` — **truncation** towards zero | — | `Math.trunc(...)` in `_doFinish` (NOT `Math.round`) |
| Stars: 3 if all found and `bonus/BONUS_TIME_MAX >= 0.66`; 2 if all found; 1 otherwise | — | `_doFinish` + `bonus_ratio_3star=0.66` |
| `score = (scene_score + bonus) * STAR_MULTIPLIER[stars]` — integer arithmetic, **no rounding** | — | `_doFinish` (no external `Math.round`) |
| Single testable source: `LevelManager.compute_scene_score` / `LevelManager.miss_penalty` | — | pinned by `test_scene_score_parity_*` / `test_miss_penalty_parity_*` |

---

## C. Hints (`engine/hint_system.py` + `level_manager.RewardTracker`)

| ENGINE | Value | WEB |
|---|---|---|
| `initial_hints` | 2 | `HINT_FREE` |
| `manual_hint_cooldown_max` | 20.0 s | `HINT_COOLDOWN` |
| `hint_penalties` | `[0,-50,-75,-100]` | `HINT_PENALTIES=[50,75,100]` |
| `max_hints_before_disable` | 3 | `HINT_MAX_USES` |
| Earned-hint increments | 0.20 / 0.143 / 0.112 / 0.05 | `_awardHintProgress` |
| Per-object `hint_delay` (default) | 30 | `HINT_AUTO_DEFAULT_DELAY` (and the `hint_delay` field) |

Note: the engine uses `combo_thresholds` (normally empty) for an extra bonus on the
increments; the web replicates the no-combo case. If the engine starts using combos,
update `_awardHintProgress`.

---

## D. HUD object names (`engine/hud_manager.py`)

| ENGINE | WEB |
|---|---|
| `max_visible_goals` = 7 | `HUD_MAX_VISIBLE` |
| Name color palette | `HUD_NAME_COLORS` (6 colors) |
| Layout: left block `[0:4]`, right block `[4:7]`, 2 rows each | `_renderHud` |
| Found -> removed from the list | `goals.filter(!found)` |

---

## E. Ambient effects (`engine/effect_renderer.py`)

| ENGINE | WEB | Notes |
|---|---|---|
| `update_effect_state`: glint `t+=dt/period`, others `t+=dt*period` (period default 2.0) | `_updateAndDrawEffects` | |
| `draw_glint_effect` (pulse, additive glow, core>0.3) | `drawGlint` | additive blending = `globalCompositeOperation="lighter"` |
| `draw_smoke_effect` (12 puffs x 5 blobs x 3 layers) | `drawSmoke` | direct port of the loop |
| `draw_flies_effect` (intensity*40 particles) | `drawFlies` | |
| Position: bg space -> screen via `bg_to_screen` | same | radius scaled by `bg_display_scale` |

---

## F. Flashlight (`engine/core.py` `_draw_flashlight_effect`)

| ENGINE | WEB |
|---|---|
| `alpha = clip(dist^1.4 * 255)`, outside the circle = solid black | `_renderFlashlight` (destination-out gradient on an **offscreen** canvas) |
| `radius = flashlight_radius * 1.15` | same (scaled for visual consistency on a variable canvas) |
| Hint in a flashlight scene = 5 s flash that lights everything | `hintFlashUntil = now + 5000` |

---

## G. Scene loading and random selection (`engine/scene_loader.py`)

| ENGINE | WEB | Critical |
|---|---|---|
| `LAYER_Z` (layer -> z map) | exporter `LAYER_Z` | used for `layer_z` |
| `SceneObject` defaults (radius 30, detection "circle", width/height 0, ...) | exporter `_build_object` | do **not** apply catalog defaults at runtime |
| `random_layer_selection`: picks low/mid/high at random, filters | `_buildSceneObjects` | on EVERY scene start |
| `auto_random_finds` + `num_random_finds`: redraws `is_goal` at random | `_buildSceneObjects` | shuffle, fixed=`always_show` |

These flags are in the manifest per scene; the random logic runs on the web.

---

## H. Save and locks (`engine/save_manager.py`)

| ENGINE | WEB (`runtime.js` `Save`, localStorage) |
|---|---|
| Structure: `scores/stars/unlocked_scenes/unlocked_levels` | identical |
| Keeps the best score/stars | `Save.record` |
| Unlocks the next scene on completion; last scene -> unlocks the level | `Save.record` |
| First level/scene unlocked by default | `Save.isLevelUnlocked` (idx 0) |

---

## I. Minigames (`engine/minigames/*`)

Engine interface `BaseMinigame` (`start/handle_event/update/draw/finish`) ->
web interface `start()/pointer()/key()/update(dt)/draw(ctx,W,H)` + `host._minigameDone({success,score})`.

| ENGINE | WEB | Assets |
|---|---|---|
| `tetran/tetran_game.py` | `runtime.js` `TetranGame` | `assets/minigames/tetran/` (real PNGs) |
| `arcade_eleven/arcade_eleven_game.py` | `ArcadeEleven` | cards from **tower** (dependency) |
| `asteroids/asteroids_game.py` + `asteroids_config.py` | `AsteroidsGame` | sounds `assets/minigames/asteroids/` |

`_on_minigame_complete` (core.py) -> `host._minigameDone`: the trigger object is
ALWAYS marked `found`, the score is added, victory/neutral sfx.

**Asset dependencies between minigames**: `editor/web_exporter.py` `MINIGAME_ASSET_DEPS`
(e.g. `arcade_eleven` -> `tower`). If a minigame starts using another one's assets,
add the entry there.

Minigame constants (e.g. `asteroids_config.py`: speeds, points, lives) are
duplicated in the respective JS classes (`AST`, `TET_*`, `AE_*`). If they change, update them.

---

## J. Strings / languages

- 5 languages: it, en, de, es, fr (`engine/language_manager.py`).
- Engine + game strings merged in the manifest (`_collect_strings`). The game wins.
- Minigame strings **namespaced** by id (`minigame_strings`) to avoid collisions.
- UI chrome translated by `UI_STRINGS` (in `runtime.js`) as a fallback.

---

## Checklist when you change the engine

1. Does the change touch a line in this document? If so, update the corresponding WEB side.
2. Did you change a scene/object/save **data structure**? Update
   `editor/web_exporter.py` (manifest) and the readers in `runtime/game.js` (or `core.js`).
3. Did you change a **constant/formula**? Update the value in `runtime/core.js`
   (`RULES_DEFAULTS`/formulas) or in the affected `runtime/minigames/<id>.js` module.
4. Did you add a new effect type / detection type / object field? Export it and
   handle it in the runtime (or document its exclusion in WEB_EXPORT.md section 7).
5. Re-export and verify:
   ```bash
   python -m editor.web_exporter <game>
   node --check build_web/<game>/runtime.js     # JS syntax
   # coordinate parity (example): compare Python vs JS ScalingManager on a scene
   ```
6. Update the table in **WEB_EXPORT.md sections 6/7** if the feature status changes.

---

## Coordinate parity verification (reference)

Numeric comparison of `bg_to_screen` Python vs JS at 1280x720 on a scene: the delta
must be ~0 (print rounding only). Rotated hit test: the sampling grid must be identical
between Python `ClickDetector` and JS `hitTest`. These checks already gave
delta < 0.005 px and 961/961 identical cells.
