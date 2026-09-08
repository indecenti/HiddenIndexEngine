# HiddenIndexEngine ROADMAP

Status per area and remaining work. This file replaces the old `NEXT_STEPS.md` and the
`*_STATUS`/`*_SUMMARY` files that used to sit in the root (removed as obsolete).
Update it whenever an area changes status.

Legend: [x] done · [~] in progress/partial · [ ] to do.

## Engine foundations (remediation)

- [x] Foundation tier (steps 1-10): scaling, coordinates, click detection, hints, saves, validation.
- [ ] "Later" tier (steps 11-14): non-blocking improvements.
- [x] miss penalty: the progressive curve is replicated in `game.js::_missPenalty` and
  exported by `editor/web_rules.py` (was listed as an open decision, it is aligned).
- [ ] Open decision: glow indicator, define the behavior of the visual indicator.
- Permanent constraint: the runtime is duplicated in Python (engine) and JS (web). Every
  change to shared logic must be propagated to both (see `docs/web/WEB_EXPORT_SYNC.md`).

## Editor

- [x] Audit P1-P4 (273 findings): critical, high, medium bugs, dead code. See `docs/archive/editor/EDITOR_AUDIT_REPORT.md`.
- [x] Improvement plan (5 phases, `docs/archive/editor/EDITOR_IMPROVEMENT_PLAN.md`) COMPLETED:
  - UI foundations: widget layer (`ui/widgets.py`), unified modal stack,
    centralized text editing, DPI awareness + UI scale, dynamic menubar hitboxes.
  - Canvas UX: arrow-key nudge, zoom-to-selection, configurable grid, object snapping
    with guides, undo with labels/coalescing/preserved selection.
  - Asset studio (PNG): crop with handles, redo, restore brush, AI background removal
    (rembg), resize, color filters, outline; import with processing and batch import
    with catalog registration + i18n.
  - Level design: scene playtest (`main.py --scene`, status bar button), scene
    statistics with difficulty estimate (scatter_engine scoring), as-in-game preview
    (F5), object group presets, extended auditor (6 new checks).
  - Dashboard: duplicate scene/level, move scene between levels, reorder games.
  - Refactor: unified EXE/APK build pipeline (`build_common.py`), shared `AssetCatalog`
    for backgrounds/music/video, web export with progress+cancel, unified clipboard.
- [x] Crash resilience: the main loop survives an isolated exception (emergency autosave,
  message to the user, circuit breaker after `MAIN_LOOP_MAX_CRASHES`), the autosave never
  propagates and backs off on failure, autosave recovery restores the scene in place, the
  theme harvest is a staged swap with rollback. Verified by `pytest tests/test_editor_robustness.py`.
- [x] Scene outline (`editor/mixins/outline.py`, plan item P3): Outline tab with the list
  of the placed objects (layer, goal, minigame, hidden/locked), search and filters, click
  to select and reveal, double click to frame, ctrl/shift multi-selection feeding the bulk
  edit of the properties panel. Verified by `pytest tests/test_editor_outline.py`.
- [x] Chrome layout hardening (`docs/editor/EDITOR_UI.md`): button and row widths
  measured on the rendered label instead of per-widget constants, hitboxes published
  by the renderer instead of recomputed next to it, canvas toolbar that wraps instead
  of overflowing over the zoom readout, zoom/coordinates HUD moved to its own pill,
  F1 shortcuts panel replacing the two unreadable always-on hint lines, catalog rows
  that follow the UI scale, outline rows and header that follow it too, localized
  tooltips (the hardcoded Italian `UI_TIPS` table is gone). Verified by
  `pytest tests/test_editor_ui_layout.py`.
- [x] Catalog tag localization: `slugify_tag()` as the single normalizer of a tag id
  (the ids `citt`/`casin`, truncated by an old ASCII-stripping pass, are repaired),
  and every tag the catalogs use translated in all five languages instead of falling
  back to the raw Italian id. Verified by `pytest tests/test_catalog_tags.py`.
- [x] Modal dialogs: each one computes its layout once and publishes the rects it
  drew (new object, tag picker, translation editor, icon picker, project auditor,
  playlist seek bar), sizes follow the UI scale and are clamped to the window, and
  the whole project auditor report is localized instead of hardcoded Italian.
  Verified by `pytest tests/test_editor_modal_geometry.py` and
  `pytest tests/test_string_glyphs.py` (no UI string may use a character the font
  cannot draw).
- [x] Command registry (`editor/commands.py`): one declaration per feature feeding
  the F1 panel (all 40 bindings, grouped, instead of the 9 two hint strings named),
  a command palette on Ctrl+P that searches the localized labels, and the zoom
  controls in the canvas HUD. Every view toggle became a method, so keyboard,
  toolbar and palette share one implementation. It also surfaced a dead menu entry:
  "Save scene as..." was offered and never wired, and is now implemented (copy the
  folder, keep the unsaved edits, register the copy in level_config.json). Verified
  by `pytest tests/test_editor_commands.py` and `pytest tests/test_editor_save_as.py`.
- [x] Recently placed objects offered as a strip above the catalog list, per project
  and across sessions: placing is the repetitive action of the editor and the catalog
  holds over a thousand entries. Verified by `pytest tests/test_editor_recent_objects.py`.
- [x] Translation editor: one geometry (`_lang_geometry`) instead of three that
  disagreed, plus what a translation editor needs - completion per language, empty
  cells marked, an "only incomplete" filter, and a name for a key when it is created.
  Every dialog is now clamped to the window (`dialog_rect`): the playlist and the
  video picker were taller than the minimum 1280x720 editor window, so their title
  and footer buttons were off screen. Verified by
  `pytest tests/test_editor_lang_modal.py` and `pytest tests/test_editor_modal_geometry.py`.
- [ ] "Editor Pro" plan (`docs/archive/editor/EDITOR_PRO_PLAN.md`, 2026-07-12): remaining
  items - auto-scatter camouflage (single render-based metric, best-of-M, Lab color, repair
  loop), scatter UX (progress/cancel, seed, interactive ghosts), editor completeness
  (translation workbench, publishing checklist).

## Menu system (skins)

- [x] Skin architecture (core + pluggable skin) on the Python side: `default`, `horror`, `kids`, `cyber_neon`, `mystery`.
- [x] Robustness: fail-soft hook dispatch (`skin_call`), coercion of the theme values,
  capped particle densities, shared caches (`SurfaceCache`, `cached_title`).
  Contract in `docs/engine/MENU_SKINS.md`, verified by `pytest tests/test_menu_skins.py`.
- [ ] Web skins (hybrid DOM/CSS): approach approved, still to implement in the web runtime.

## Android / mobile UX

Details in `docs/android/ANDROID_MOBILE_UX_AUDIT.md`. Decisions taken: landscape,
pinch-zoom + pan, mid-range target. Validated on the emulator (boot, menu, HOG scene,
object list, find, minigame).

- [x] Phases 0/1/3 (input, scene, object list) + asset pruning (APK 558 -> 135 MB).
- [x] pygame SIMD build fix at recipe level + config persistence on a writable path.
- [ ] Phase 2: sharpness at 720p.
- [ ] Phase 4: navigation and system integration (back, lifecycle).
- [ ] Phase 5: final packaging (icons, splash, store).
- [ ] Phase 6: performance and minigames on mid-range devices.

## Content (evergreen)

- [ ] Achievements: `engine/achievements_manager.py` + end-of-level evaluation.
- [ ] Leaderboard: best score / best time per level with trend.
- [ ] Render quality profiles (high/medium/low) with auto-downgrade below an FPS threshold.
- [ ] New levels/scenes and completion of the translations (it/en/es/fr/de) for the active games.

## Stability

Measured findings and the priority order are in [STABILITY_PLAN.md](STABILITY_PLAN.md):
runtime test coverage (11 engine modules and 8 of 9 minigames untested), blocking lint
(196 pyflakes findings, 2 real defects), 79 silently swallowed exceptions, publishing
checklist, Android phases 2 and 4.

## Development tooling

- [x] Project MCP server (`tools/hie_mcp_server.py`): headless render, scene validation, catalog search.
- [x] Project skills (`.claude/skills/`): `build-apk`, `run-game`, `add-asset`, `validate-scene`.
- [ ] Possible cleanup of `scratch/` (dozens of throwaway scripts and temporary PNGs tracked by git).
