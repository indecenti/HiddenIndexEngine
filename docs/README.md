# HiddenIndexEngine documentation

Index of the project documentation, organized by area. For the day-to-day operating
rules see `CLAUDE.md` in the root. For the status and the remaining work see
[ROADMAP.md](ROADMAP.md).

## Engine

- [engine/COORDINATE_SYSTEM.md](engine/COORDINATE_SYSTEM.md) — coordinate system (1280x720 reference space, background space, transforms).
- [engine/RESOLUTION_SCALING_FIX.md](engine/RESOLUTION_SCALING_FIX.md) — resolution scaling and rendering notes.
- [engine/HINT_SYSTEM.md](engine/HINT_SYSTEM.md) — hint system, per object and per layer.
- [engine/I18N.md](engine/I18N.md) — localization: EN as default and single fallback, keys, placeholders, the contract verified by the tests.
- [engine/MINIGAMES_DEVELOPMENT.md](engine/MINIGAMES_DEVELOPMENT.md) — how to develop and integrate a minigame (plugin architecture).

## Assets

- [assets/ASSETS_WORKFLOW.md](assets/ASSETS_WORKFLOW.md) — general asset production workflow.
- [assets/ASSETS_CARTOON_WORKFLOW.md](assets/ASSETS_CARTOON_WORKFLOW.md) — cartoon-style asset pipeline.
- [assets/ASSETS_LINEART_WORKFLOW.md](assets/ASSETS_LINEART_WORKFLOW.md) — line-art-style asset pipeline.
- [assets/ASSET_GENERATION_GUIDE.md](assets/ASSET_GENERATION_GUIDE.md) — asset generation guide.
- [assets/ASSETS_INTEGRATION_LOG.md](assets/ASSETS_INTEGRATION_LOG.md) — batch asset integration log.
- [assets/IMAGE_PROCESSING_GUIDELINES.md](assets/IMAGE_PROCESSING_GUIDELINES.md) — image processing guidelines (rembg, cropping, alpha).
- [assets/TAGS_TAXONOMY.md](assets/TAGS_TAXONOMY.md) — catalog tag taxonomy.

## Build (desktop)

- [build/DEBUG_GUIDE.md](build/DEBUG_GUIDE.md) — debugging stuck builds and timeouts.
- [build/VALIDATION_CHECKLIST.md](build/VALIDATION_CHECKLIST.md) — pre-release validation checklist.

## Android

- [android/ANDROID_PORTING_PLAN.md](android/ANDROID_PORTING_PLAN.md) — Android porting plan.
- [android/ANDROID_MOBILE_UX_AUDIT.md](android/ANDROID_MOBILE_UX_AUDIT.md) — mobile UX audit and phased roadmap.
- [android/SMART_ASSET_PACKAGING.md](android/SMART_ASSET_PACKAGING.md) — smart asset packaging (APK size reduction).
- [android/PACKAGE_SIZE_FIX.md](android/PACKAGE_SIZE_FIX.md) — package size reduction strategy.

## Web

- [web/WEB_EXPORT.md](web/WEB_EXPORT.md) — web export (JS runtime architecture).
- [web/WEB_EXPORT_SYNC.md](web/WEB_EXPORT_SYNC.md) — **HARD contract** engine <-> web. Update it on every change to engine logic replicated on the web.

## Archive

Working documents from the project's history, kept for reference and left in Italian:
the original full specification, the editor audit and improvement plans, the build system
analysis and changelog. See [archive/README.md](archive/README.md).
