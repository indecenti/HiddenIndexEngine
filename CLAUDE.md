# CLAUDE.md — HiddenIndexEngine (HIE)

Operating guide for Claude Code on this repository. The rules here are binding.
Global preferences shared with other tools live in `GEMINI.md`.

## What HIE is

A modular engine in **Python 3.12 + pygame 2.6.1** for **Hidden Object Games (HOG)**.
Three distribution targets from the same project:

- **Desktop** (Windows): EXE via PyInstaller.
- **Web**: an export that *replicates* the engine logic in JavaScript (it does not import it).
- **Android**: APK/AAB via python-for-android / buildozer (WSL).

It ships a complete **visual editor** (`editor/`) to create scenes, place objects, manage
the catalog, tags and languages, and launch the builds.

## Repository layout

| Path | Contents |
|------|----------|
| `engine/` | Game runtime: `core.py`, `scene_loader.py`, `catalog_manager.py`, `menu_system.py`, `menu_skins/`, `minigames/`, `hud_manager.py`, `scaling_manager.py`, `haptics.py`. |
| `engine/data/` | Global catalogs `global_*_catalog.json` (cartoon, lineart, ...). |
| `engine/assets/` | Shared assets: `objects_cartoon/`, `objects_lineart/`, `strings/`. |
| `engine/schemas/` | JSON Schemas (`scene_schema.json`, `catalog_schema.json`). |
| `editor/` | Level editor (mixins, desktop/Android builds, web exporter). |
| `games/<id>/` | Games: `game_config.json`, `objects_catalog.json`, `levels/<level>/<scene>/scene.json`, `strings/`. |
| `tools/` | Development utilities (catalog audit, tag normalization, preview). |
| `tools/hie_mcp_server.py` | **Project MCP server** (headless render, scene validation, catalog search). |
| `.claude/skills/` | Project skills (build-apk, run-game, add-asset, validate-scene). |
| `scripts/` | Shell scripts for Android builds (WSL). |
| `docs/` | Documentation organized by area (see `docs/README.md`). |
| `scratch/` | Throwaway scripts and temporary PNGs. NOT production code. |

## Commands

```powershell
# Game (uses default_game from config.ini, or --game)
python main.py
python main.py --game Malonno_Survivors --lang it
python main.py --minigame sudoku        # start a minigame directly

# Level editor
python run_editor.py

# Tests
pytest                                   # full suite
pytest tests/test_web_sync.py            # engine <-> web contract (see below)

# Dependencies
pip install -r requirements.txt -r requirements-dev.txt
```

Desktop/web/Android builds are launched from the editor; the Android scripts live in
`scripts/` (they require WSL). See `docs/build/` and `docs/android/`.

## Data model (scenes + catalog)

- A **scene** is `games/<id>/levels/<level>/<scene>/scene.json`, validated against
  `engine/schemas/scene_schema.json`. Object coordinates live in the **native pixel space
  of the background** (`background.png` next to `scene.json`).
- Every object has `catalog_id` + `x,y` + `detection_type` (`circle`/`rect`/`mask`).
  Anchor convention: for **rect** `(x,y)` is the **top-left** (center = `x+w/2, y+h/2`);
  for **circle/mask** `(x,y)` is the **center** (size = `width|radius*2`).
- The `catalog_id` resolves against the **merged catalog**: `catalog_manager.load_catalog(game_id)`
  merges global (`engine/data/global_*_catalog.json`) + local (`games/<id>/objects_catalog.json`),
  with the local entry overriding the global one on equal `id`.
- An object's image (`icon` in the catalog) is looked up first in
  `games/<id>/<icon>`, then in `engine/assets/<icon>`.

## Binding conventions

- **Language**: everything committed to the repository is in **English** — documentation,
  code comments, docstrings, log messages, commit messages. Legacy Italian comments are
  migrated when the surrounding code is touched. Reply to the user in the language they
  write in (the maintainer writes in Italian). Direct tone, no filler.
- **Never emoji** in code, docs, UI or output.
- **Never `print()`** — use `logging` via `engine.utils.get_logger(__name__)`.
- **Never magic numbers** — constants or config.
- **Resource paths**: use `engine.utils.get_resource_path(...)`; writes via `get_writable_path(...)`.
- **JSON writes**: always `engine.utils.safe_write_json` (atomic). Deletions: `safe_delete` (`.editor_trash/` bin + audit log).
- **Type hints required**, PEP 8, ~100 chars per line max, complete code (no `# ...` snippets).
- **No new dependencies** without explicit approval. Versions in `requirements*.txt` are pinned.
- **Rendering**: never `pygame.SCALED` on `set_mode` (it conflicts with `ScalingManager`); use `DOUBLEBUF`/`FULLSCREEN`. LRU render caches with gradual eviction via `popitem(last=False)`. Positioning with `int(round(float))`.

## HARD rule: engine <-> web sync

The web export (`editor/web_exporter.py` + `editor/web_template/runtime/`) **replicates** in
JavaScript the logic of `engine/{scaling_manager,click_detector,level_manager,hint_system,
scene_loader,effect_renderer,save_manager}` and of `engine/minigames/*`. If you change any of
these, you MUST read and update **`docs/web/WEB_EXPORT_SYNC.md`** and propagate the change to
the web runtime in the same change. Shared constants have a single source of truth in
`editor/web_rules.py::engine_rules()`. Mandatory check: `pytest tests/test_web_sync.py`.

## i18n

**EN is the default language and the ONLY fallback** (`engine.language_manager.DEFAULT_LANG` /
`FALLBACK_LANG`, `editor.constants.DEFAULT_LANG`). `LanguageManager` resolves:
`games/<id>/strings/` -> `engine/assets/strings/` -> EN fallback -> inline default -> key.

No hardcoded UI text: use `self._TR("key", "English default")` (or `tr(...)` from
`engine.language_manager` in standalone modals) and `str.format` with named placeholders.
Every new key goes into **all 5** languages in `engine/assets/strings/`.
Mandatory check: `pytest tests/test_editor_i18n.py`. Details in `docs/engine/I18N.md`.

On scene save the editor performs **harvesting**: it copies into the game's local `.json`
the strings it needs (objects, HUD, menus) so the game can be shipped standalone.

## Tooling for Claude

- **MCP** (`tools/hie_mcp_server.py`): registered in `.mcp.json`. Exposes `render_scene`,
  `render_asset` (headless PNG through the engine), `validate_scene`, `search_catalog`,
  `check_missing_assets`, `list_games`, `build_status`. Reloads when the client restarts.
- **Skills** (`.claude/skills/`): `build-apk`, `run-game`, `add-asset`, `validate-scene`.

## Status and next steps

See `docs/ROADMAP.md` for the per-area status and the remaining work.
