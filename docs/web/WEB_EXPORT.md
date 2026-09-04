# Web Export (HTML/JS/Canvas)

Export of a HiddenEngine game as a **static site** in HTML/JS/CSS, ready to publish
online or to open locally (even with a double-click).

> To keep the engine and the web aligned through future changes, see
> **[WEB_EXPORT_SYNC.md](WEB_EXPORT_SYNC.md)** (synchronization contract).
> This is the critical part: the web runtime **replicates** the engine logic.

---

## 1. Usage

```bash
# Export a game. VERSIONED build: build_web/<game>/v<X.Y>/
# + index.html (redirect to the latest version) + builds.json (history).
python -m editor.web_exporter LineVenture

# Force a version, or a 'flat' output without versioning:
python -m editor.web_exporter LineVenture --version 2.0
python -m editor.web_exporter LineVenture --out build_web/test_flat
```

The version starts from `game_config.version`; if `v<version>` already exists, the
minor is auto-incremented (1.0 -> 1.1 -> ...). Every build writes `version.json`
(game, version, runtime_version, timestamp). `build_web/<game>/index.html` always
redirects to the most recent version.

To try it:
- **Double-click** `build_web/<game>/index.html` (it works from `file://`), or
- **Double-click** `build_web/<game>/avvia_server.bat` (local server + browser), or
- publish the `build_web/<game>/` folder on any static host.

---

## 2. Founding principle: a self-contained package

The exporter resolves the source assets from `engine/` and `games/` **at build time**,
but **copies/transcodes/embeds everything** into `build_web/<game>/`. At **runtime**
the site NEVER reads from `engine/` or `games/`: every path points to `assets/...`
and the data (manifest) is embedded.

Quick check (must report 0 paths towards engine/games):
```bash
python3 -c "import json,re; m=open('build_web/LineVenture/manifest.json',encoding='utf-8').read(); \
print('bad:', [p for p in re.findall(r'\"((?:assets|engine|games)/[^\"]+)\"', m) if not p.startswith('assets/')])"
```

---

## 3. Output structure

```
build_web/
├── index.json                  # aggregated CATALOG of all games (for the portal)
└── <game>/
    ├── index.html              # landing: social/SEO meta + redirect to the latest version
    ├── game.json               # game metadata (for the portal)
    ├── builds.json             # version history (latest + list)
    ├── avvia_server.bat        # local server launcher (Windows)
    └── v<X.Y>/                 # versioned build
        ├── index.html          # shell: SEO/OG/PWA meta + canvas + loading screen
        ├── style.css           # full-viewport canvas + loading screen
        ├── runtime.js          # THE WEB ENGINE (replica of the engine) — bundle generated from runtime/
        ├── manifest.js         # window.__MANIFEST__ = {...}  (for file://, no fetch)
        ├── manifest.json       # same content (for http setups)
        ├── manifest.webmanifest# PWA (installable)
        ├── sw.js               # service worker: offline + cache (cache <game>-v<X.Y>)
        ├── version.json        # game, version, runtime_version, timestamp
        └── assets/
            ├── scenes/<level>__<scene>/<bg>.webp|.mp4  # backgrounds (WebP q82, cap 1920px) or video
            ├── thumbs/<level>__<scene>.jpg             # menu previews (480px)
            ├── icons/<obj>.webp                         # object icons (lossless WebP, full resolution)
            ├── icon.<ext>, menu_poster.<ext>            # favicon/OG + menu poster
            ├── video/<menu>.mp4                         # menu background video
            ├── audio/sfx/*.mp3                          # global SFX (96k mono)
            ├── audio/music/*.mp3                        # scene/menu music (112k stereo)
            └── minigames/<id>/...                       # assets ONLY of the triggered minigames (+ dependencies)
```

---

## 4. Components

### Exporter — `editor/web_exporter.py`
- `export_web_game(game_id, output_dir)`: entry point.
- Builds the **manifest** (see section 5) mirroring `engine/scene_loader.py` 1:1.
- Resolves icons (first `games/<id>/`, then `engine/assets/`), copies backgrounds, generates thumbnails.
- Transcodes audio with **ffmpeg** (engine SFX + scene/menu music); falls back to a raw copy if ffmpeg is missing.
- Embeds the **strings** (engine + game merged) and the UI **theme** in the manifest.
- Copies the assets of the **minigames** in use (+ dependencies, see `MINIGAME_ASSET_DEPS`).
- Generates `runtime.js` by concatenating the `runtime/` modules (see below), including
  **only the minigames triggered** in the scenes (`_bundle_runtime`).

### Runtime — `editor/web_template/{index.html,style.css}` + `editor/web_template/runtime/`
- `index.html`/`style.css`: static templates copied into every export.
- `runtime/`: modular sources (classic scripts, no ES modules -> they work from `file://`):
  - `core.js`: `ScalingManager`, hit test, object rendering, `AudioEngine`, `Theme`,
    `Save`, `RULES_DEFAULTS`, effects; initializes `window.MINIGAME_CLASSES`.
  - `game.js`: `Game` class (state machine, scenes, HUD, hints, pause, settings, results).
  - `minigames/<id>.js`: one file per minigame; each **self-registers** in
    `window.MINIGAME_CLASSES["<id>"]`. Adding a minigame = creating the file.
  - `bootstrap.js`: `main()` (loads the manifest, instantiates `Game`).
- The exporter concatenates them into a single `runtime.js` (bundle), including only
  the minigames actually used by the game.

---

## 5. Manifest (data format)

```jsonc
{
  "game_id": "LineVenture",
  "title_key": "game_title",
  "default_language": "it",
  "ref": { "w": 1280, "h": 720 },
  "theme": { "id": "cyber_neon", "colors": {...}, "effects": {...} },
  "languages": ["de","en","es","fr","it"],
  "strings": { "it": {...}, "en": {...}, ... },          // engine + game merged
  "sfx": { "found": "assets/audio/sfx/found.mp3", ... }, // found/complete/miss/click/levelup
  "menu_music": "assets/audio/music/..." | null,
  "minigames": ["tetran"],                                // implemented and used ids
  "minigame_strings": { "tetran": { "it": {...} } },      // namespaced per minigame
  "levels": [{
    "id": "One", "name_key": "One_name",
    "scenes": [{
      "id": "scene_nuova", "order": 1, "time_limit": 120,
      "background": "assets/scenes/One__scene_nuova/camping.png",
      "thumb": "assets/thumbs/One__scene_nuova.jpg",
      "background_scale": 1.0, "bg_w": 4096, "bg_h": 2304,
      "music": null,
      "effects": [{ "type":"glint", "x":..,"y":..,"radius":..,"color":[..],"intensity":..,"pulse_min":..,"pulse_period":.. }],
      "bubble_tips": [{ "x":..,"y":..,"text_key":"..","trigger":"start_scene","width":..,"height":..,"color":[..] }],
      "flashlight": false, "flashlight_radius": 150.0,
      "random_layer_selection": false, "auto_random_finds": true, "num_random_finds": 12,
      "objects": [{
        "instance_id":"ca_book_stack_adv", "catalog_id":"ca_book_stack_adv",
        "label_key":"obj_..", "icon":"assets/icons/..png",
        "x":64, "y":1793, "detection_type":"rect", "radius":0, "width":355, "height":290,
        "hint_delay":30, "layer":"objects_mid", "layer_z":20,
        "is_goal":true, "always_show":false,
        "rotation":0, "flip_x":false, "flip_y":false, "alpha":255,
        "grayscale":false, "grayscale_factor":1.0, "color_filter":[255,255,255],
        "corners":[[0,0],[0,0],[0,0],[0,0]], "scale":1.0,
        "minigame_trigger": null
      }]
    }]
  }]
}
```

The object fields mirror **exactly** the construction of `SceneObject` in
`engine/scene_loader.py` (same defaults; no catalog default applied at runtime).

---

## 6. Implemented features

| Area | Status | Notes |
|---|---|---|
| Object coordinates (rect/circle/rotation/flip/warp) | OK | pixel-perfect vs engine |
| Object filters (stretch/alpha/grayscale/color_filter) | OK | **pixel-exact** (grayscale+tint via sRGB feColorMatrix) |
| Hit detection (ellipse/rotated rect/warp polygon/ray casting) | OK | identical to `click_detector.py` |
| Backgrounds (image **and video**) + icons + thumbnails | OK | copied to `assets/`; video via looping `<video>` |
| Menu/scene background video (.mp4/.webm) | OK | dimensions via ffprobe, preview from the first frame |
| Compressed audio (SFX + music) | OK | `<audio>` (no fetch, file://-friendly) |
| HUD with object names | OK | bottom bar, color palette, max 7 |
| Hints (manual + auto-glow) | OK | 2 free, 20 s cooldown, penalties, max 3 |
| Pause + pause menu | OK | timer frozen |
| Glint/smoke/flies effects | OK | 1:1 math |
| Flashlight + hint-flash | OK | offscreen mask |
| bubble_tip speech bubbles (`start_scene` + `end_scene`) | OK | queue; end_scene before the results |
| Particles + score popup + screen shake | OK | discovery feedback |
| Build versioning (versions, version.json, builds.json, redirect) | OK | auto-increment |
| SEO/Open Graph/Twitter meta + favicon + theme-color | OK | per game, social previews |
| PWA (manifest.webmanifest, installable, landscape) | OK | icon + theme/bg color |
| Loading screen + fade transitions + menu hover cards | OK | modern UX |
| Portal catalog (game.json + build_web/index.json) | OK | platform metadata |
| Random layer/object selection | OK | `random_layer_selection`/`auto_random_finds` |
| Save + locks (localStorage) | OK | scenes/levels, autosave, stars |
| Settings (volume + 5 languages) | OK | persisted, live language switch |
| UI themes (cyber_neon/mystery/...) | OK | colors from the manifest |
| Curated level select (thumb/stars/lock) | OK | themed |
| Rewarding results (stars/confetti/score) | OK | 1:1 scoring |
| Minigames | tetran, arcade_eleven, asteroids | host + interface + real assets |

---

## 7. Known limits / not yet ported

- **Minigames**: the 3 used by the games are ported (tetran, arcade_eleven, asteroids).
  Missing: centipede, minipong, slot_classic, spot_differences, sudoku, tower.
- **detection_type `mask`** pixel-perfect: falls back to a circle (0 uses in the current games).
- **Intro zoom** and **fade transitions** between scenes: not ported (minor aesthetics).
- Multi-touch in minigames: one control at a time (full keyboard on desktop).

---

## 8. Verification (without screenshots)

Fidelity was validated through **state inspection** and **pixel sampling** on the
canvas (the preview screenshot tool was unreliable). Examples:
- JS `bg_to_screen` vs Python `ScalingManager`: delta < 0.005 px on every object.
- Rotated rect hit test (270.1 degrees): 961/961 cells identical to `ClickDetector`.
- Render -> click round trip: every object hit at its own rendered center.
