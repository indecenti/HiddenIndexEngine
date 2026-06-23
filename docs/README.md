# Documentazione HiddenIndexEngine

Indice della documentazione di progetto, organizzata per area. Per le regole
operative quotidiane vedi `CLAUDE.md` nella root. Per lo stato e il lavoro
residuo vedi [ROADMAP.md](ROADMAP.md).

## Specifica

- [spec/HiddenEngine_Specifica_Completa.md](spec/HiddenEngine_Specifica_Completa.md) — specifica funzionale completa del motore.

## Engine

- [engine/COORDINATE_SYSTEM.md](engine/COORDINATE_SYSTEM.md) — sistema di coordinate (reference space 1280x720, bg-space, trasformazioni).
- [engine/RESOLUTION_SCALING_FIX.md](engine/RESOLUTION_SCALING_FIX.md) — scaling per risoluzione e note di rendering.
- [engine/HINT_SYSTEM.md](engine/HINT_SYSTEM.md) — sistema di hint/aiuti per oggetto e per layer.
- [engine/MINIGAMES_DEVELOPMENT.md](engine/MINIGAMES_DEVELOPMENT.md) — come sviluppare e integrare un minigioco (architettura a plugin).

## Asset

- [assets/ASSETS_WORKFLOW.md](assets/ASSETS_WORKFLOW.md) — workflow generale di produzione asset.
- [assets/ASSETS_CARTOON_WORKFLOW.md](assets/ASSETS_CARTOON_WORKFLOW.md) — pipeline asset stile cartoon.
- [assets/ASSETS_LINEART_WORKFLOW.md](assets/ASSETS_LINEART_WORKFLOW.md) — pipeline asset stile line art.
- [assets/ASSET_GENERATION_GUIDE.md](assets/ASSET_GENERATION_GUIDE.md) — guida alla generazione asset.
- [assets/ASSETS_INTEGRATION_LOG.md](assets/ASSETS_INTEGRATION_LOG.md) — log di integrazione batch asset.
- [assets/IMAGE_PROCESSING_GUIDELINES.md](assets/IMAGE_PROCESSING_GUIDELINES.md) — linee guida elaborazione immagini (rembg, ritaglio, alpha).
- [assets/TAGS_TAXONOMY.md](assets/TAGS_TAXONOMY.md) — tassonomia dei tag del catalogo.

## Build (desktop / sistema)

- [build/BUILD_SYSTEM_ANALYSIS.md](build/BUILD_SYSTEM_ANALYSIS.md) — architettura del sistema di build.
- [build/BUILD_SYSTEM_CHANGELOG.md](build/BUILD_SYSTEM_CHANGELOG.md) — changelog del sistema di build.
- [build/DEBUG_GUIDE.md](build/DEBUG_GUIDE.md) — guida al debug di build bloccate / timeout.
- [build/VALIDATION_CHECKLIST.md](build/VALIDATION_CHECKLIST.md) — checklist di validazione pre-release.

## Android

- [android/ANDROID_PORTING_PLAN.md](android/ANDROID_PORTING_PLAN.md) — piano di porting su Android.
- [android/ANDROID_MOBILE_UX_AUDIT.md](android/ANDROID_MOBILE_UX_AUDIT.md) — audit UX mobile e roadmap a fasi.
- [android/SMART_ASSET_PACKAGING.md](android/SMART_ASSET_PACKAGING.md) — packaging intelligente degli asset (riduzione peso APK).
- [android/PACKAGE_SIZE_FIX.md](android/PACKAGE_SIZE_FIX.md) — strategia di riduzione dimensione pacchetto.

## Web

- [web/WEB_EXPORT.md](web/WEB_EXPORT.md) — export web (architettura del runtime JS).
- [web/WEB_EXPORT_SYNC.md](web/WEB_EXPORT_SYNC.md) — **contratto BLINDATO** engine <-> web. Da aggiornare a ogni modifica della logica engine replicata sul web.

## Editor

- [editor/EDITOR_AUDIT_REPORT.md](editor/EDITOR_AUDIT_REPORT.md) — audit dell'editor (273 rilievi) e stato dei fix.
