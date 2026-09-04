---
name: build-apk
description: Builds or rebuilds the HiddenIndexEngine Android APK/AAB applying the known pygame recipes (recipe-level SIMD fix, NDK 28, arm64, asset pruning). Use it when the user wants to build for Android, regenerate the APK, diagnose a failed Android build, or inspect an APK.
---

# build-apk

Android build (python-for-android / buildozer) of HiddenIndexEngine.

## Prerequisites

- Android toolchain in **WSL** (the build scripts are `.sh`). Setup:
  `scripts/setup_android_wsl.sh`.
- Known constraints already solved at recipe level: pygame **SIMD** fix, **NDK 28**,
  **arm64** target, **asset pruning** (APK 558 -> 135 MB).

## Scripts (in `scripts/`)

Always read the script header before running it. Main ones:

- `rebuild_apk_quick.sh` — fast incremental rebuild.
- `rebuild_apk_arm64.sh` / `rebuild_apk_ndk28.sh` — toolchain/target variants.
- `rebuild_apk_pygame.sh` / `rebuild_apk_with_numpy.sh` — native recipe handling.
- `rebuild_apk_x86_verify.sh` — x86 build for emulator verification.
- `fix_pygame_simd.sh` / `update_pygame_recipe.sh` — pygame recipe patches.
- `inspect_apk.sh` — inspects the content/size of an APK.

Alternatively, build from the editor: `editor/android_build_system.py`
(UI: `editor/android_build_ui.py`).

## Diagnosing stuck builds

- Guide: `docs/build/DEBUG_GUIDE.md`.
- Android context: `docs/android/` (porting plan, packaging, mobile UX, package size).
- For the APK size: `docs/android/SMART_ASSET_PACKAGING.md` and `optimize_assets_mobile.py`.

## Post-build verification

- `inspect_apk.sh` for content and size.
- MCP tool `build_status` to list the artifacts (apk/aab) present in the repo.
- Emulator test with the x86 build (`rebuild_apk_x86_verify.sh`).

## Rules

- Do not bypass hooks/signing unless explicitly requested.
- Native dependency versions are pinned: do not change them without approval.
