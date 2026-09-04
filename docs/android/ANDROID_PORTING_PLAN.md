# Android APK Builder integrated in the editor — plan

**Status**: Approved — F1 completed, next step F0 (WSL setup) or F2 (manual prototype)
**Plan version**: 2.0
**Revision date**: 2026-05-13
**Replaces**: plan v1.0 (obsolete toolchain, misaligned with the editor architecture)

**Approved decisions (2026-05-13)**:
- Separate APKs per game (one for LineVenture, one for Malonno_Survivors)
- WSL setup handled by a wizard in the editor (shows instructions + verifies, does not install silently)
- Orientation: forced landscape (consistent with the engine's 1920x1080)

---

## 1. Goal

Extend the editor with an Android APK packaging procedure **parallel** to the one that produces the Windows EXE through PyInstaller today. The editor itself does **not** end up in the APK: APKs contain only `engine/` + `main.py` + `games/<id>/` of a single game. One APK per game (LineVenture, Malonno_Survivors).

Expected result: in the editor, next to the "Build game (Windows EXE)" button, a "Build Android APK" button that produces `bin/<game_id>-<version>-debug.apk` (or `-release.aab` for the Play Store).

---

## 2. Codebase status and runtime dependencies

Verified in this session:

| Aspect | Check | Result |
|--------|-------|--------|
| Does `engine/` import `editor/`? | `grep "from editor\|import editor" engine/` | no import — `engine` is standalone |
| Does `main.py` import `editor/`? | same grep | no import |
| Runtime networking | grep `requests/socket/urllib` | absent |
| `subprocess` in the runtime | grep `subprocess` in `engine/` | only `editor/build_system.py` (not runtime) |
| Threading | `engine/audio_manager.py:10-41` | daemon thread + Queue — supported on Android |
| File I/O | `engine/save_manager.py:57-63` open() on local paths | must be redirected to Android internal storage |
| Main loop | `engine/core.py:235-246` | standard synchronous Pygame |
| Input | `engine/core.py:265` MOUSEBUTTONDOWN | pygame maps touch -> mouse automatically |
| `get_base_path()` | `engine/utils.py:32-37` | to be extended with p4a detection |

**Current bundle**:
- `engine/` 398 MB, of which `engine/assets/` 383 MB (backgrounds 180 + objects 141 + music 37)
- `engine/*.py` < 300 KB (engine code)
- `games/LineVenture/` 55 MB, `games/Malonno_Survivors/` 102 MB

The existing editor **already** has a smart packaging that drastically reduces the output: `editor/build_system.py:34` `_analyze_game_usage()` tracks the assets actually referenced by the game's scenes and copies only those. The APK logic reuses these same functions.

---

## 3. Proposed architecture

Mirrors the already working EXE triad.

```
Windows EXE (existing)               Android APK (new)
─────────────────────────            ───────────────────────────
editor/build_ui.py            <-->   editor/android_build_ui.py
editor/build_manager.py       <-->   editor/android_build_manager.py
editor/build_system.py        <-->   editor/android_build_system.py
   └─ PyInstaller                      └─ Buildozer (via WSL)
```

Shared functions, no duplication:
- `_analyze_game_usage()` — reused 1:1
- `_copy_smart_assets()` — reused 1:1
- `next_build_version()` — reused 1:1

New functions in `android_build_system.py`:
- `_verify_wsl_toolchain()` — checks `wsl --status` and the presence of `buildozer` in the configured Linux venv
- `_generate_buildozer_spec(game_id, version, workspace)` — produces a `buildozer.spec` parameterized for the game
- `_run_buildozer_with_timeout()` — analogous to `_run_pyinstaller_with_timeout`, runs `wsl -e bash -lc "cd … && buildozer android debug"` and parses the output
- `build_game_apk()` — main orchestrator (signature symmetric to `build_game()`)

The APK button in the editor launches a subprocess `python editor/android_build_manager.py <game_id> <version> <build_dir> <status_file> [--release]`, which in turn opens the Android version of `BuildProgressWindow`. Same communication paradigm via `status.json` with a watchdog.

---

## 4. Target toolchain 2026

Stack updated to the Google Play 2026 requirements:

| Component | Version | Notes |
|-----------|---------|-------|
| WSL2 + Ubuntu | 24.04 LTS | Buildozer does not run on native Windows |
| JDK | 17 (Temurin) | Required by the current Android Gradle Plugin |
| Python (in WSL) | 3.12 | Compatible with p4a stable |
| Android SDK platform | `android-35` | targetSdk mandatory for new apps/updates from 2025 |
| Android SDK build-tools | `35.0.0` | |
| Android NDK | `28.2.13676358` (28b stable) | **Updated 2026-05-13 from 27c**: required for the 16 KB ELF page-size alignment demanded by Android 15+ on Pixel 9 and later (Pixel_10 emulators included, `sdk_gphone16k_x86_64`). NDK 27c aligns at 4 KB -> `dlopen` fails with `program alignment (4096) cannot be smaller than system page size (16384)` |
| minSdkVersion | `24` (Android 7 Nougat) | Initially planned 23, raised to 24 after F2: p4a's Python 3.14 uses bionic's `preadv()`/`pwritev()`, exposed only from API 24. >99% of active devices are >= API 24 anyway |
| Buildozer | `1.5.x` (stable PyPI) | No `develop` branch |
| python-for-android | `2024.x` (stable) | |
| pygame-ce | `2.5.x` | NOT the original pygame — pygame-ce is the modern drop-in used by p4a |
| Output | debug APK (testing) + release AAB (Play Store) | The Play Store accepts only AAB |

Correct Android detection (actual p4a env vars):

```python
def is_android_runtime() -> bool:
    return 'ANDROID_ARGUMENT' in os.environ or 'P4A_BOOTSTRAP' in os.environ
```

`ANDROID_APP_PATH`, mentioned in plan v1.0, **does not exist** in p4a.

---

## 5. Runtime fixes needed in the engine

Minimal, localized changes, no refactor.

### 5.1 `engine/utils.py` — `get_base_path()` and `get_writable_path()`

```python
import os

def is_android_runtime() -> bool:
    return 'ANDROID_ARGUMENT' in os.environ or 'P4A_BOOTSTRAP' in os.environ

def get_base_path() -> Path:
    if is_android_runtime():
        # p4a unpacks the app into /data/data/<package>/files/app
        return Path(os.environ.get('ANDROID_PRIVATE', '/data/data')) / 'app'
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parents[1]

def get_writable_path(*parts: str) -> Path:
    if is_android_runtime():
        # App-private storage, survives reboots, needs no runtime permission
        base = Path(os.environ['ANDROID_PRIVATE']) / 'saves'
    else:
        base = get_base_path() / 'saves'
    base.mkdir(parents=True, exist_ok=True)
    path = base
    for p in parts:
        path = path / p
    if path.parent != base:
        path.parent.mkdir(parents=True, exist_ok=True)
    return path
```

Impact: zero on Windows/desktop (the new branches sit behind `if is_android_runtime()`). `SaveManager` does not change: it calls `get_writable_path()` as it does today.

### 5.2 Touch input

Already working: pygame on Android automatically maps `FINGERDOWN` -> `MOUSEBUTTONDOWN` with `event.pos` in device pixels. The engine (`engine/core.py:265`) already uses `MOUSEBUTTONDOWN`. No change.

### 5.3 Pause/resume lifecycle

Not blocking for the MVP. On Android, when the app goes to the background, pygame receives `pygame.APP_WILLENTERBACKGROUND` / `APP_DIDENTERBACKGROUND`. For the first version the app can simply keep looping at a low frame rate. A proper hook (pyjnius) will be added in F6 if needed.

### 5.4 AudioManager

No change. Daemon thread + Queue are natively supported by p4a/Android.

---

## 6. Buildozer.spec template

Generated dynamically by `_generate_buildozer_spec()` for each game. Draft:

```ini
[app]
title = {game_title}
package.name = {game_id_normalized}
package.domain = org.hiddenindex
version = {version}

source.dir = .
source.include_exts = py,json,png,jpg,jpeg,ogg,ttf
source.exclude_dirs = editor,tests,scratch,build,dist,docs,saves,.git,.claude,__pycache__
source.exclude_patterns = *.pyc,*.pyo,*.autosave,*.bak,*.tmp,*.log,*.md,*.spec,*.ini

requirements = python3,pygame-ce,android,jnius

orientation = landscape
fullscreen = 1

android.api = 35
android.minapi = 24   # see the note in section 4: Python 3.14 requires API 24+
android.ndk = 27c
android.archs = arm64-v8a, armeabi-v7a
android.allow_backup = False
android.accept_sdk_license = True

android.permissions = 

# Game icon (taken from games/<id>/icon.png)
icon.filename = games/{game_id}/icon.png

# Splash
presplash.filename = games/{game_id}/splash.png

[buildozer]
log_level = 2
warn_on_root = 0
```

Notes:
- `requirements`: bare minimum, no editor library (cv2, numpy, scipy, PyInstaller). pygame-ce on p4a is already packaged for Android.
- `source.exclude_dirs = editor` explicitly excludes the editor folder from the APK.
- `arm64-v8a + armeabi-v7a`: covers 100% of modern devices.
- `orientation = landscape`: the games are designed for 1920x1080. The existing `scaling_manager` already adapts.
- The file is generated in a temporary workspace, not versioned.

---

## 7. APK build workflow (editor side)

Symmetric mirror of the EXE one. Step by step inside `build_game_apk()`:

1. **Validation** — `game_id` exists, `game_config.json` valid. (Identical to `build_game()`.)
2. **WSL toolchain check** — run `wsl -e bash -lc "buildozer --version"`. On failure -> error with setup instructions.
3. **Temporary workspace** in `<temp>/apk_<game_id>/`. On Windows it is a Windows path; Buildozer uses it through the WSL path `/mnt/g/...`.
4. **Smart copy of engine + game** — reuses `_analyze_game_usage()` and `_copy_smart_assets()`. **Excludes** `editor/`, `tests/`, `scratch/`, `build/`, `dist/`, `saves/`.
5. **Generation of `buildozer.spec`** parameterized for the game.
6. **Generation of the `main.py` shim** if needed (Buildozer looks for `main.py` as the entry point; the existing one is fine as is, as long as `config.ini` sits next to it).
7. **Asset compression** (optional, enabled by a UI checkbox):
   - PNG -> `oxipng -o4` (lossless, ~30%)
   - WAV/MP3 -> `ffmpeg -q:a 5 *.ogg` (lossy ~50%)
8. **Launch Buildozer**: `wsl -e bash -lc "cd <workspace_wsl_path> && source ~/venv_p4a/bin/activate && buildozer android debug"` with a 30-minute timeout and output parsing for progress.
9. **Copy the resulting APK** from `<workspace>/bin/*.apk` to `build/<game_id>/<version>/<game_id>-<version>-debug.apk`.
10. **APK check** (`aapt dump badging` to read package name, version, min/target SDK).
11. **Temporary workspace cleanup**.

For the release AAB: identical but `buildozer android release`, signed with `jarsigner` using configured keys (user config in `editor/android_signing.json`, outside the repo).

---

## 8. Editor UI

Minimal change to `editor/build_ui.py` (or a button in the main screen that invokes the build). To be designed in detail by looking at the current builder UI, but logically:

- Game selection dialog (already existing for the EXE)
- Two buttons: **"Build Windows EXE"** | **"Build Android APK"**
- For the APK, an optional "release (sign for the Play Store)" checkbox
- Same progress window, step labels adapted to Buildozer

The first time "Build APK" is pressed: the editor verifies WSL/Buildozer. If missing, it shows a wizard with the commands to run (see F0) and a "Check again" button.

---

## 9. Work phases

| Phase | Description | Output | Estimate |
|-------|-------------|--------|----------|
| **F0** | WSL2 + JDK17 + Android SDK + NDK 27c + Buildozer setup in a venv (one-time, user side with the editor's instructions) | Working WSL toolchain | 1 day (heavy downloads) |
| **F1** (done) | Engine runtime fixes: `engine/utils.py` `get_base_path()` + `get_writable_path()` + `is_android_runtime()` helper | Completed 2026-05-13. Windows smoke test: no regression. | — |
| **F2** | Standalone APK prototype: manually copy a minimal workspace into WSL and run `buildozer android debug` on LineVenture. Validate that the APK starts on an Android 15 emulator (API 35) | 1 hand-made working APK | 1-2 days |
| **F3** | `editor/android_build_system.py` + `editor/android_build_manager.py` (maximum reuse of `build_system.py`) | 2 new files | 1-2 days |
| **F4** | Editor UI extension: APK button + progress window | Change to `build_ui.py` (or equivalent) | 0.5-1 day |
| **F5** | Integrated asset compression (opt-in) + audit of the assets actually used per game | APKs reduced by 30-50% | 1 day |
| **F6** | Signed release AAB build + Play Console push (lifecycle hooks if needed) | Publishable app | 1-2 days |
| **TOTAL F0–F4 (testable MVP)** | | Debug APK buildable from the editor | **3-5 days** + F0 setup |

F5–F6 are later iterations.

---

## 10. F0 — WSL setup (one-time instructions)

To be done before the editor's APK builder can work. It will be included as a wizard in the editor (F4) but is documented here first for a manual first run.

### 10.1 WSL2 + Ubuntu 24.04 (admin PowerShell, from Windows)

```powershell
wsl --install -d Ubuntu-24.04
# Reboot required
```

### 10.2 Dependencies inside WSL Ubuntu (`wsl` session)

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3.12 python3.12-venv python3.12-dev \
  git wget curl unzip zip \
  openjdk-17-jdk \
  build-essential libffi-dev libssl-dev \
  autoconf libtool pkg-config zlib1g-dev libncurses-dev libtinfo-dev cmake \
  libltdl-dev

python3.12 -m venv ~/venv_p4a
source ~/venv_p4a/bin/activate
pip install --upgrade pip
pip install buildozer cython==3.0.11
echo 'source ~/venv_p4a/bin/activate' >> ~/.bashrc
```

### 10.3 Android SDK + NDK (in WSL)

```bash
mkdir -p ~/android-sdk/cmdline-tools && cd ~/android-sdk/cmdline-tools
wget https://dl.google.com/android/repository/commandlinetools-linux-11076708_latest.zip
unzip commandlinetools-linux-*.zip
mv cmdline-tools latest
rm commandlinetools-linux-*.zip

cat >> ~/.bashrc <<'EOF'
export ANDROID_HOME=$HOME/android-sdk
export ANDROID_SDK_ROOT=$ANDROID_HOME
export PATH=$ANDROID_HOME/cmdline-tools/latest/bin:$ANDROID_HOME/platform-tools:$PATH
export JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64
EOF
source ~/.bashrc

yes | sdkmanager --licenses
sdkmanager "platform-tools" "platforms;android-35" "build-tools;35.0.0" "ndk;27.2.12479018"
```

### 10.4 Verification

```bash
buildozer --version  # 1.5.x
java -version        # 17.x
sdkmanager --list_installed
```

This whole procedure will be re-runnable through a command from the editor; on error the editor shows exactly which step failed.

---

## 11. Known limits and mitigations

| Problem | Impact | Mitigation |
|---------|--------|------------|
| Game bundle still heavy (LineVenture ~55 MB, Malonno_Survivors ~102 MB + shared engine/assets) | The APK could exceed 150 MB | F5 asset compression + evaluate Play Asset Delivery for AAB > 200 MB |
| WSL latency between the Windows and Linux filesystems | APK build 2-3x slower than the EXE | Workspace cloned inside Linux `~/` (not `/mnt/g/`) — handled by the builder |
| The first build downloads 1-2 GB (NDK, SDK, p4a recipes) | Long F0 | Once only, persistent cache in `~/.buildozer/` |
| Fixed 1920x1080 resolution | Distortion on 18:9 or foldable screens | The existing `scaling_manager` already scales with letterboxing — verify in F2 |
| Licensed MP3 audio | Tracks from free sources? | To verify before the Play Store release (F6) |
| Saves on `ANDROID_PRIVATE` not shared between devices | Fine for now, possible future cloud save | Out of scope for the plan |

---

## 12. Open points requiring a decision

Before starting F1 I would like confirmation on:

1. **Separate APK per game vs a launcher APK with a game chooser** — the plan assumes separate APKs (one for LineVenture, one for Malonno_Survivors). Confirmed?
2. **Play Store signing configuration** — existing keystore or one to generate in F6?
3. **WSL setup wizard in the editor** — is it OK to have an editor screen that runs `wsl --install` for the user, or should the first time be manual with the editor only verifying?
4. **Tablet/orientation** — forced landscape OK, or do we also want portrait with auto-rotate?

---

## 13. MVP acceptance criteria (end of F4)

1. From the editor, on Windows, pressing "Build Android APK" on LineVenture:
   - The progress window opens
   - Buildozer starts inside WSL without user interaction
   - At the end it produces `build/LineVenture/<v>/LineVenture-<v>-debug.apk`
2. The APK installed on an Android 15 emulator (API 35) starts, shows the main menu, loads at least one game scene, plays audio, accepts taps.
3. The same procedure, repeated on Malonno_Survivors, produces a distinct APK (different package name).
4. The editor is not packaged in the APK (check with `unzip -l <apk> | grep editor` -> empty).
5. No regression on the existing EXE builder.

---

## 14. What we do NOT do in this iteration

To avoid scope creep:

- No iOS port (completely different toolchain)
- No in-app purchases / ads / Google Play Services
- No cloud save
- No native Android leaderboards / achievements
- No Android-specific multi-window / split-screen
- No engine refactor beyond the 2-3 methods in `engine/utils.py`

All of this is post-F6 territory, if ever needed.
