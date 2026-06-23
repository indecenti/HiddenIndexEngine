---
name: build-apk
description: Compila o ricompila l'APK/AAB Android di HiddenIndexEngine applicando le ricette pygame note (fix SIMD a livello recipe, NDK28, arm64, asset pruning). Usala quando l'utente vuole buildare per Android, rigenerare l'APK, diagnosticare un build Android fallito, o ispezionare un APK.
---

# build-apk

Build Android (python-for-android / buildozer) di HiddenIndexEngine.

## Prerequisiti

- Toolchain Android in **WSL** (gli script di build sono `.sh`). Setup:
  `scripts/setup_android_wsl.sh`.
- Vincoli noti gia' risolti a livello recipe: fix **SIMD** di pygame, **NDK 28**,
  target **arm64**, **asset pruning** (APK 558 -> 135 MB).

## Script (in `scripts/`)

Leggi sempre l'header dello script prima di lanciarlo. Principali:

- `rebuild_apk_quick.sh` — rebuild incrementale veloce.
- `rebuild_apk_arm64.sh` / `rebuild_apk_ndk28.sh` — varianti toolchain/target.
- `rebuild_apk_pygame.sh` / `rebuild_apk_with_numpy.sh` — gestione ricette native.
- `rebuild_apk_x86_verify.sh` — build x86 per verifica su emulatore.
- `fix_pygame_simd.sh` / `update_pygame_recipe.sh` — patch ricetta pygame.
- `inspect_apk.sh` — ispeziona contenuto/peso di un APK.

In alternativa, build dall'editor: `editor/android_build_system.py`
(UI: `editor/android_build_ui.py`).

## Diagnosi build bloccate

- Guida: `docs/build/DEBUG_GUIDE.md`.
- Contesto Android: `docs/android/` (porting plan, packaging, mobile UX, package size).
- Per il peso APK: `docs/android/SMART_ASSET_PACKAGING.md` e `optimize_assets_mobile.py`.

## Verifica post-build

- `inspect_apk.sh` per contenuto e dimensione.
- Tool MCP `build_status` per elencare gli artefatti (apk/aab) presenti nel repo.
- Test su emulatore con la build x86 (`rebuild_apk_x86_verify.sh`).

## Regole

- Non bypassare hook/firma se non richiesto esplicitamente.
- Le versioni delle dipendenze native sono pinned: non cambiarle senza approvazione.
