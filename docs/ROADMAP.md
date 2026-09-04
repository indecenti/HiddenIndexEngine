# HiddenIndexEngine ROADMAP

Status per area and remaining work. This file replaces the old `NEXT_STEPS.md` and the
`*_STATUS`/`*_SUMMARY` files that used to sit in the root (removed as obsolete).
Update it whenever an area changes status.

Legend: [x] done · [~] in progress/partial · [ ] to do.

## Engine foundations (remediation)

- [x] Foundation tier (steps 1-10): scaling, coordinates, click detection, hints, saves, validation.
- [ ] "Later" tier (steps 11-14): non-blocking improvements.
- [ ] Open decisions:
  - miss penalty: align the Python formula with the JS one in the web runtime.
  - glow indicator: define the behavior of the visual indicator.
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

## Development tooling

- [x] Project MCP server (`tools/hie_mcp_server.py`): headless render, scene validation, catalog search.
- [x] Project skills (`.claude/skills/`): `build-apk`, `run-game`, `add-asset`, `validate-scene`.
- [ ] Possible cleanup of `scratch/` (dozens of throwaway scripts and temporary PNGs tracked by git).
