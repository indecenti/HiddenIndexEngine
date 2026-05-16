r"""
editor/android_build_system.py

Sistema di compilazione APK Android, simmetrico a editor/build_system.py.
A differenza del builder EXE (PyInstaller, gira nativo su Windows), questo
builder lancia Buildozer dentro WSL Ubuntu — è l'unico modo praticabile su
Windows per usare python-for-android.

Architettura:
  - L'editor gira su Windows.
  - I sorgenti del progetto stanno su G:\HIE git\ (filesystem Windows).
  - Lo workspace di build vive dentro WSL in /root/.hie_android_build/<game_id>/
    (filesystem ext4: build veloce, niente cross-fs lentezza di /mnt/g/).
  - rsync sincronizza solo i file necessari (motore + un singolo gioco), escludendo
    editor/, tests/, scratch/, build/, dist/, docs/, saves/, .git/, .claude/.
  - buildozer.spec è generato dinamicamente per ogni gioco (package.name unico).
  - Buildozer lancia python-for-android, che cross-compila Python + pygame-ce
    per arm64-v8a e armeabi-v7a, poi confeziona l'APK.

Convenzioni:
  - Riusa _analyze_game_usage() e next_build_version() da build_system.py.
  - Stesso pattern di progress_callback(progress: 0-100, step: str).
  - Stesso contratto di ritorno (dict con success/apk_path/error_msg/steps_log).

Requisiti host (Windows):
  - WSL2 con distribuzione Ubuntu-24.04 (verificare con _verify_wsl_toolchain).
  - Dentro WSL: /root/venv_p4a con Buildozer 1.6+, JDK 17, Android SDK API 35,
    NDK 27c, sdkmanager symlink (legacy path).
  - Verificare con scripts/setup_android_wsl.sh.
"""

import sys
import shutil
import logging
import subprocess
import threading
import time
import re
import hashlib
from pathlib import Path
from typing import Callable, Optional

from engine.utils import get_base_path, get_logger
from editor.build_system import _analyze_game_usage, next_build_version
from editor.core.io import _load_json

logger = get_logger("android_build_system")

# ---------------------------------------------------------------------------
# Costanti
# ---------------------------------------------------------------------------

# Distribuzione WSL attesa
WSL_DISTRO = "Ubuntu-24.04"

# Workspace dentro WSL, indipendente per ogni gioco (cache .buildozer/ riusabile)
WSL_WORKSPACE_ROOT = "/root/.hie_android_build"

# Path al venv Buildozer e alla toolchain Android dentro WSL
WSL_VENV_ACTIVATE = "/root/venv_p4a/bin/activate"
WSL_ANDROID_HOME = "/root/android-sdk"
# NDK 28.2: richiesto per 16 KB ELF alignment (Android 15+ Pixel 9+).
# NDK 27 e precedenti allineano a 4 KB → dlopen fallisce su device 16 KB.
WSL_ANDROID_NDK = "/root/android-sdk/ndk/28.2.13676358"
WSL_JAVA_HOME = "/usr/lib/jvm/java-17-openjdk-amd64"

# Timeout build (prima volta può richiedere ~50 min; build incrementali ~5 min)
BUILDOZER_FIRST_BUILD_TIMEOUT = 4200   # 70 minuti
BUILDOZER_INCREMENTAL_TIMEOUT = 1200   # 20 minuti (alzato per sicurezza su shared platform)
SUBPROCESS_CHECK_INTERVAL = 2

# Cache globali condivise per accelerare le build
WSL_GRADLE_HOME = "/root/.gradle_cache"
WSL_SHARED_PLATFORM = f"{WSL_WORKSPACE_ROOT}/shared_platform"
WSL_MASTER_ENGINE = f"{WSL_WORKSPACE_ROOT}/master_engine"

# Configurazione target Android 2026 (allineata a ANDROID_PORTING_PLAN.md)
ANDROID_API = 35       # Android 15 (target Play Store 2026)
ANDROID_MINAPI = 24    # Android 7.0+ (Python 3.14 di p4a richiede API 24+ per preadv/pwritev)
ANDROID_NDK_VERSION = "28b"  # NDK 28.2.x: default 16 KB ELF alignment, richiesto da Android 15+


# ---------------------------------------------------------------------------
# Helper WSL
# ---------------------------------------------------------------------------

def _wsl_run(
    command: str,
    capture: bool = True,
    timeout: Optional[int] = None,
    as_user: str = "root",
) -> subprocess.CompletedProcess:
    """
    Esegue un comando bash dentro WSL e ritorna il CompletedProcess.

    NOTA: il comando viene incapsulato come argomento di `bash -c`, quindi va
    passato come singola stringa. Per script complessi, scrivere uno .sh
    sul filesystem Windows e copiarlo in WSL (evita escape hell).
    """
    wsl_cmd = ["wsl", "-d", WSL_DISTRO, "-u", as_user, "-e", "bash", "-c", command]
    return subprocess.run(
        wsl_cmd,
        capture_output=capture,
        text=True,
        timeout=timeout,
        encoding="utf-8",
        errors="replace",
    )


def _windows_path_to_wsl(p: Path) -> str:
    """
    Converte G:\\HIE git\\foo in /mnt/g/HIE git/foo (path WSL).
    """
    s = str(p.resolve())
    # G:\HIE git\foo -> /mnt/g/HIE git/foo
    drive, rest = s[0].lower(), s[2:].replace("\\", "/")
    return f"/mnt/{drive}/{rest}"


def _verify_wsl_toolchain() -> tuple[bool, str]:
    """
    Verifica che WSL Ubuntu-24.04 sia presente e che Buildozer + JDK 17 +
    Android SDK + NDK 27 siano installati. Ritorna (ok, msg).
    """
    # 1) WSL distro
    try:
        result = subprocess.run(
            ["wsl", "--list", "--quiet"],
            capture_output=True, text=True, encoding="utf-16-le", timeout=10,
        )
        # wsl --list --quiet stampa una distro per riga in UTF-16
        distros = [d.strip() for d in result.stdout.replace("\x00", "").splitlines() if d.strip()]
        if WSL_DISTRO not in distros:
            return False, (
                f"WSL distribuzione '{WSL_DISTRO}' non installata. "
                f"Eseguire: wsl --install -d {WSL_DISTRO}\n"
                f"Trovate: {distros}"
            )
    except Exception as e:
        return False, f"WSL non disponibile o non avviabile: {e}"

    # 2) Buildozer + Java + sdkmanager dentro WSL
    check_cmd = (
        "source /root/venv_p4a/bin/activate 2>/dev/null && "
        "echo BV=$(buildozer --version 2>&1 | head -1) && "
        f"echo JV=$({WSL_JAVA_HOME}/bin/java -version 2>&1 | head -1) && "
        f"test -d {WSL_ANDROID_NDK} && echo NDK=OK || echo NDK=MISSING && "
        f"test -x {WSL_ANDROID_HOME}/tools/bin/sdkmanager && echo SDKMGR=OK || echo SDKMGR=MISSING"
    )
    try:
        result = _wsl_run(check_cmd, timeout=15)
        out = result.stdout
        if "Buildozer" not in out:
            return False, f"Buildozer non trovato in /root/venv_p4a. Output:\n{out}"
        if "NDK=OK" not in out:
            return False, (
                f"Android NDK 28.2 non installato in {WSL_ANDROID_NDK}.\n"
                f"NDK 28 è richiesto per 16 KB ELF page-size alignment "
                f"(Android 15+ Pixel 9+).\nInstalla con: "
                f"sdkmanager 'ndk;28.2.13676358'\nOutput:\n{out}"
            )
        if "SDKMGR=OK" not in out:
            return False, (
                f"sdkmanager non trovato in path legacy {WSL_ANDROID_HOME}/tools/bin/.\n"
                f"Buildozer 1.6 lo richiede lì: eseguire "
                f"`ln -sf {WSL_ANDROID_HOME}/cmdline-tools/latest {WSL_ANDROID_HOME}/tools`\n"
                f"Output:\n{out}"
            )
        return True, f"Toolchain OK.\n{out}"
    except subprocess.TimeoutExpired:
        return False, "Timeout verifica toolchain WSL (15s)"
    except Exception as e:
        return False, f"Errore verifica WSL: {e}"


# ---------------------------------------------------------------------------
# Generazione buildozer.spec
# ---------------------------------------------------------------------------

def _normalize_package_name(game_id: str) -> str:
    """
    Converte game_id in package.name valido per Android:
    lowercase, solo [a-z0-9], niente underscore in `package.name`
    (buildozer accetta underscore, ma evitiamo per compatibilità Play Store).
    """
    s = re.sub(r"[^a-zA-Z0-9]", "", game_id).lower()
    if not s or not s[0].isalpha():
        s = "game" + s
    return s


def _generate_buildozer_spec(
    game_id: str,
    game_title: str,
    version: str,
    icon_relpath: Optional[str] = None,
    presplash_relpath: Optional[str] = None,
) -> str:
    """
    Produce il contenuto di buildozer.spec per il gioco specifico.

    NOTA: include esplicitamente `source.exclude_dirs = editor,...` per
    garantire che l'editor non finisca mai nell'APK, anche se il workspace
    fosse popolato per errore.
    """
    pkg_name = _normalize_package_name(game_id)
    icon_line = f"icon.filename = {icon_relpath}" if icon_relpath else "# icon.filename ="
    splash_line = (
        f"presplash.filename = {presplash_relpath}" if presplash_relpath else "presplash.filename ="
    )

    return f"""[app]
title = {game_title}
package.name = {pkg_name}
package.domain = org.hiddenindex
version = {version}

source.dir = .
source.include_exts = py,json,png,jpg,jpeg,ogg,wav,mp3,ttf,ini,txt,xml
source.exclude_dirs = editor,tests,scratch,docs,saves,.git,.claude,__pycache__,bin,.buildozer
source.exclude_patterns = *.pyc,*.pyo,*.autosave,*.bak,*.tmp,*.log,*.spec,*.md,run.bat,*.mp4

# Requirements:
#   - pygame (NON pygame-ce): p4a ha recipe per `pygame` che cross-compila per ARM.
#     `pygame-ce` non ha recipe in p4a master → pip ha installato wheel host x86_64
#     erroneamente copiata in arm64/ → ImportError EM_X86_64 vs EM_AARCH64 al boot.
#     I due esportano lo stesso namespace `pygame`, quindi il codice è invariato.
#   - numpy: REQUIRED — eager import in scene_loader.py:13 propagato in cascata
#     a core/click_detector/hud_manager/level_manager/hint_system.
#   - scipy: opzionale, solo se warp_surface (utils.py) viene chiamato.
#   - jsonschema, cv2, PIL: lazy/optional, non bloccanti al boot.
requirements = python3,pygame,android,pyjnius,numpy

orientation = landscape
fullscreen = 1

android.api = {ANDROID_API}
android.minapi = {ANDROID_MINAPI}
android.ndk = {ANDROID_NDK_VERSION}
# archs: solo arm64-v8a per il 2026. armeabi-v7a è obsoleto (Android pre-2017),
# rimuoverlo riduce APK di ~30 MB e velocizza le build incrementali.
android.archs = arm64-v8a
android.accept_sdk_license = True
android.allow_backup = False
android.release_artifact = aab
android.debug_artifact = apk

android.sdk_path = {WSL_ANDROID_HOME}
android.ndk_path = {WSL_ANDROID_NDK}

# WAKE_LOCK: richiesto dal motore per pygame.display.set_allow_screensaver(False)
# che mantiene lo schermo acceso durante il gameplay.
android.permissions = android.permission.WAKE_LOCK

{icon_line}
{splash_line}

[buildozer]
log_level = 2
warn_on_root = 0
"""


# ---------------------------------------------------------------------------
# Patch p4a — workaround per bug noti scoperti durante porting iniziale.
# Applicate automaticamente prima di lanciare buildozer per ogni build.
# Idempotenti: rilanciabili senza effetti collaterali.
# ---------------------------------------------------------------------------

# Script bash che applica tutte e tre le patch p4a in modo idempotente.
# Documentazione completa dei bug fixati: vedi ANDROID_PORTING_PLAN.md.
_P4A_PATCHES_SCRIPT = r"""#!/bin/bash
# Auto-generated by editor/android_build_system.py — applica patch p4a note.
set -e

WORKSPACE="$1"
PKG_NAME="$2"
P4A_ROOT="$WORKSPACE/.buildozer/android/platform/python-for-android"

# ── Patch 1: pygame recipe 2.1.0 → 2.6.1 ─────────────────────────────────
# pygame 2.1.0 usa `longintrepr.h` rimosso in Python 3.12+.
# Patchiamo la recipe per usare 2.6.1 che è compatibile con NDK 28 e Python 3.12-3.14.
PYGAME_RECIPE="$P4A_ROOT/pythonforandroid/recipes/pygame/__init__.py"
if [ -f "$PYGAME_RECIPE" ] && grep -q "version = '2.1.0'" "$PYGAME_RECIPE"; then
    sed -i "s/version = '2.1.0'/version = '2.6.1'/" "$PYGAME_RECIPE"
    echo "[p4a-patch] pygame recipe 2.1.0 -> 2.6.1"
    
    # Forza rebuild pulendo cache specifica se la versione è cambiata.
    # Se non lo facciamo, p4a potrebbe provare a riusare .o vecchi incompatibili.
    rm -rf "$WORKSPACE/.buildozer/android/platform/build-arm64-v8a_armeabi-v7a/build/other_builds/pygame" 2>/dev/null || true
    rm -f "/root/.buildozer/android/packages/pygame/2.1.0.tar.gz" 2>/dev/null || true
fi

# ── Patch 2: PythonActivity.java: loadLibraries() esplicito ───────────────
# SDL2 2.30+ ha spostato loadLibraries() in finishLoad, ma p4a UnpackFilesTask
# chiama nativeSetenv() prima, fallendo se libSDL2.so non è caricata.
TEMPLATE_PA="$P4A_ROOT/pythonforandroid/bootstraps/sdl2/build/src/main/java/org/kivy/android/PythonActivity.java"
DIST_PA="$WORKSPACE/.buildozer/android/platform/build-arm64-v8a_armeabi-v7a/dists/$PKG_NAME/src/main/java/org/kivy/android/PythonActivity.java"
for FILE in "$TEMPLATE_PA" "$DIST_PA"; do
    if [ -f "$FILE" ]; then
        if ! grep -q "p4a fix: force loadLibraries before UnpackFilesTask" "$FILE"; then
            sed -i '/this\.mActivity = this;/a\
\
        // p4a fix: force loadLibraries before UnpackFilesTask\
        // (SDL2 2.30+ moved loadLibraries from onCreate to finishLoad,\
        //  but UnpackFilesTask.onPostExecute calls nativeSetenv which\
        //  requires libSDL2.so already loaded).\
        loadLibraries();' "$FILE"
            echo "[p4a-patch] PythonActivity.java loadLibraries: $FILE"
        fi
    fi
done

# ── Patch 3: pygame Setup.Android.SDL2.in SIMD include ────────────────────
# Bug: pygame surface.c referenzia symbol da simd_blitters_sse2.c, ma il
# build template non include il file → ImportError "alphablit_alpha_sse2_*
# symbol not found" su ARM.
for ARCH_DIR in "$WORKSPACE/.buildozer/android/platform/build-arm64-v8a_armeabi-v7a/build/other_builds/pygame/"*__ndk_target_*; do
    SETUP="$ARCH_DIR/pygame/buildconfig/Setup.Android.SDL2.in"
    if [ -f "$SETUP" ] && ! grep -q "simd_blitters_sse2.c" "$SETUP"; then
        sed -i 's|^surface src_c/surface.c src_c/alphablit.c src_c/surface_fill.c|surface src_c/surface.c src_c/alphablit.c src_c/surface_fill.c src_c/simd_blitters_sse2.c src_c/simd_blitters_avx2.c|' "$SETUP"
        echo "[p4a-patch] Setup.Android.SDL2.in SIMD: $SETUP"
    fi
done

echo "[p4a-patch] OK (idempotente, rilanciabile)"
"""


def _apply_p4a_patches(wsl_workspace: str, pkg_name: str) -> None:
    """
    Applica le tre patch p4a note (idempotenti):
      1. pygame recipe version 2.1.0 → 2.6.1 (compat Python 3.14)
      2. PythonActivity.java: loadLibraries() esplicito in onCreate (SDL2 2.30+ regression)
      3. pygame Setup.Android.SDL2.in: include simd_blitters_*.c per surface.so

    Va chiamata DOPO che p4a ha clonato il repo python-for-android.
    """
    # Scrivi lo script in /tmp dentro WSL e eseguilo
    import base64
    b64 = base64.b64encode(_P4A_PATCHES_SCRIPT.encode("utf-8")).decode("ascii")
    cmd = (
        f"echo '{b64}' | base64 -d > /tmp/_p4a_patches.sh && "
        f"chmod +x /tmp/_p4a_patches.sh && "
        f"bash /tmp/_p4a_patches.sh '{wsl_workspace}' '{pkg_name}'"
    )
    result = _wsl_run(cmd, timeout=30)
    if result.returncode != 0:
        logger.warning(f"[p4a-patches] non-zero exit: {result.stderr}")
    else:
        # Log ogni linea "[p4a-patch]" emessa
        for line in result.stdout.splitlines():
            if "[p4a-patch]" in line:
                logger.info(line.strip())


# ---------------------------------------------------------------------------
# Workspace WSL: rsync mirato del progetto in /root/.hie_android_build/<game_id>/
# ---------------------------------------------------------------------------

def _prepare_workspace(
    game_id: str,
    progress_callback: Optional[Callable[[float, str], None]] = None,
) -> str:
    """
    Crea o aggiorna il workspace di build dentro WSL.
    Ritorna il path WSL del workspace.

    Strategia di copia (riusa l'idea di smart packaging dal builder EXE):
      - rsync da /mnt/g/HIE git/ verso /root/.hie_android_build/<game_id>/
      - copia engine/, main.py, games/<game_id>/
      - esclude editor/, altri giochi, build artifacts, cache
    """
    base_path = get_base_path()
    wsl_src = _windows_path_to_wsl(base_path)
    wsl_workspace = f"{WSL_WORKSPACE_ROOT}/{game_id}"

    if progress_callback:
        progress_callback(5, "Ottimizzazione workspace (Master Cache)...")

    # 1) Aggiorna la Master Engine Cache (rsync Windows -> WSL Global)
    # Questo rsync avviene una sola volta o solo per file modificati.
    rsync_master_cmd = (
        f"mkdir -p '{WSL_MASTER_ENGINE}' && "
        f"rsync -a --delete "
        f"--exclude='editor/' --exclude='tests/' --exclude='scratch/' "
        f"--exclude='build/' --exclude='dist/' --exclude='saves/' "
        f"--exclude='.git/' --exclude='.claude/' --exclude='__pycache__/' "
        f"--exclude='*.pyc' --exclude='*.pyo' "
        f"'{wsl_src}/engine/' '{WSL_MASTER_ENGINE}/engine/'"
    )
    logger.info(f"[Master Cache] Sincronizzazione engine verso {WSL_MASTER_ENGINE}")
    _wsl_run(rsync_master_cmd, timeout=300)

    # 2) Preparazione Game Workspace con Asset Symlinking
    # Usiamo 'cp -as' per creare un albero di link simbolici: zero spazio disco, zero tempo di copia.
    if progress_callback:
        progress_callback(10, "Creazione symlink tree per asset engine...")

    # Puliamo il workspace ma preserviamo .buildozer (cache locale buildozer)
    prepare_cmd = (
        f"mkdir -p '{wsl_workspace}' && "
        f"cd '{wsl_workspace}' && "
        f"find . -maxdepth 1 ! -name '.buildozer' ! -name '.' -exec rm -rf {{}} + && "
        f"mkdir -p engine games && "
        f"cp -as '{WSL_MASTER_ENGINE}/engine/'* engine/ && "
        f"rsync -a --delete "
        f"--exclude='__pycache__/' --exclude='*.pyc' "
        f"'{wsl_src}/games/{game_id}/' 'games/{game_id}/' && "
        f"cp '{wsl_src}/main.py' . && "
        f"cp '{wsl_src}/config.ini' . 2>/dev/null || true"
    )
    
    logger.info(f"[Workspace] Setup rapido (symlinks) in {wsl_workspace}")
    result = _wsl_run(prepare_cmd, timeout=60)
    if result.returncode != 0:
        raise RuntimeError(f"Setup workspace fallito:\n{result.stderr}")

    if progress_callback:
        progress_callback(15, "Workspace ottimizzato pronto")
    return wsl_workspace


def _write_config_and_spec(
    wsl_workspace: str,
    game_id: str,
    game_config: dict,
    version: str,
) -> None:
    """
    Scrive config.ini e buildozer.spec dentro il workspace WSL.
    """
    game_title = game_config.get("title_key") or game_id
    res_cfg = game_config.get("resolution", {})
    res_w = res_cfg.get("w", 1920)
    res_h = res_cfg.get("h", 1080)
    language = game_config.get("default_language", "it")

    # config.ini
    config_content = (
        "[engine]\n"
        f"default_game = {game_id}\n"
        f"resolution_w = {res_w}\n"
        f"resolution_h = {res_h}\n"
        f"fullscreen = 1\n"
        f"language = {language}\n"
    )

    # buildozer.spec
    icon = None
    splash = None
    if (Path(get_base_path()) / "games" / game_id / "icon.png").exists():
        icon = f"games/{game_id}/icon.png"
    if (Path(get_base_path()) / "games" / game_id / "splash.png").exists():
        splash = f"games/{game_id}/splash.png"

    spec_content = _generate_buildozer_spec(
        game_id=game_id,
        game_title=game_title,
        version=version,
        icon_relpath=icon,
        presplash_relpath=splash,
    )

    # Scrivere via heredoc-safe: usiamo printf con escape
    def _write_file(path_wsl: str, content: str) -> None:
        # Encoding base64 evita problemi di escape multilivello
        import base64
        b64 = base64.b64encode(content.encode("utf-8")).decode("ascii")
        cmd = f"echo '{b64}' | base64 -d > '{path_wsl}'"
        r = _wsl_run(cmd, timeout=10)
        if r.returncode != 0:
            raise RuntimeError(f"Scrittura {path_wsl} fallita: {r.stderr}")

    _write_file(f"{wsl_workspace}/config.ini", config_content)
    _write_file(f"{wsl_workspace}/buildozer.spec", spec_content)
    logger.info(f"[Workspace] config.ini e buildozer.spec scritti in {wsl_workspace}")


# ---------------------------------------------------------------------------
# Lancio Buildozer con monitoraggio
# ---------------------------------------------------------------------------

# Tappe ad alto livello (per progress bar) — mappate sui marker p4a/buildozer.
# Aggiornati 2026-05-13 dopo audit log build prototipo: i marker generici come
# "APK " o "BUILD SUCCESSFUL" maturano troppo presto, portando la barra al 98%
# 10+ minuti prima della fine reale. Marker preferiti: quelli emessi da
# p4a/buildozer subito prima della copia del file APK nel bin/.
_BUILDOZER_STAGES = [
    ("# Check requirements",                          15, "Verifica requirements"),
    ("# Install platform",                            17, "Install platform p4a"),
    ("# Building all recipes for arch arm64-v8a",     20, "Build recipe arm64-v8a"),
    ("Building libffi for arm64-v8a",                 22, "libffi (arm64)"),
    ("Building openssl for arm64-v8a",                25, "openssl (arm64)"),
    ("Building sdl2_image for arm64-v8a",             28, "SDL2 image (arm64)"),
    ("Building sdl2_mixer for arm64-v8a",             30, "SDL2 mixer (arm64)"),
    ("Building sdl2_ttf for arm64-v8a",               32, "SDL2 ttf (arm64)"),
    ("Building sqlite3 for arm64-v8a",                34, "sqlite3 (arm64)"),
    ("Building python3 for arm64-v8a",                38, "Python 3.14 (arm64) — fase lunga"),
    ("Building numpy for arm64-v8a",                  50, "numpy (arm64) — fase lunga"),
    ("Building pyjnius for arm64-v8a",                55, "pyjnius (arm64)"),
    ("# Building all recipes for arch armeabi-v7a",   58, "Build recipe armv7"),
    ("Building openssl for armeabi-v7a",              60, "openssl (armv7)"),
    ("Building python3 for armeabi-v7a",              65, "Python 3.14 (armv7) — fase lunga"),
    ("Building numpy for armeabi-v7a",                75, "numpy (armv7) — fase lunga"),
    ("Building pyjnius for armeabi-v7a",              82, "pyjnius (armv7)"),
    ("# Going to compile bytecode",                   85, "Compile bytecode app"),
    ("# Build APK",                                   88, "Build bootstrap APK"),
    # Fasi finali Gradle/aapt2/d8/signing — il flow è:
    #   aapt2 → d8 dex → assembleDebug → zipalign → apksigner → copy
    ("# Android package renamed",                     92, "APK firmato debug pronto"),
    ("# Copy ",                                       95, "Copia APK nel bin/"),
    ("# Android packaging done",                      97, "Packaging completato"),
    ("available in the bin directory",                99, "APK pronto"),
]


def _run_buildozer_with_timeout(
    cmd: str,
    timeout: int,
    progress_callback: Optional[Callable[[float, str], None]] = None,
) -> tuple[int, list[str]]:
    """
    Esegue `wsl ... bash -c "<cmd>"` con timeout e parsing stage per progress.
    """
    output_lines: list[str] = []
    wsl_cmd = ["wsl", "-d", WSL_DISTRO, "-u", "root", "-e", "bash", "-lc", cmd]

    proc: Optional[subprocess.Popen] = None
    exception_occurred: Optional[BaseException] = None
    last_line_time = time.time()
    current_progress = 18

    def run_process() -> None:
        nonlocal proc, exception_occurred, last_line_time, current_progress
        try:
            proc = subprocess.Popen(
                wsl_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )
            logger.debug(f"[Buildozer PID] {proc.pid}")

            for line in proc.stdout:
                line = line.rstrip()
                last_line_time = time.time()
                if not line:
                    continue
                output_lines.append(line)
                if len(output_lines) % 50 == 0:
                    logger.debug(f"[Buildozer #{len(output_lines)}] {line[:120]}")

                # Avanza progress su marker noti
                for marker, pct, label in _BUILDOZER_STAGES:
                    if marker in line and pct > current_progress:
                        current_progress = pct
                        if progress_callback:
                            progress_callback(current_progress, label)
                        logger.info(f"[Progress] {current_progress}% — {label}")
                        break

            try:
                proc.wait(timeout=30)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
        except Exception as e:
            exception_occurred = e
            if proc:
                try:
                    proc.kill()
                except Exception:
                    pass

    t = threading.Thread(target=run_process, daemon=False)
    t.start()

    start = time.time()
    last_heartbeat = start
    while t.is_alive() and (time.time() - start) < timeout:
        idle = time.time() - last_line_time
        if idle > 300:  # 5 minuti senza output = blocco
            logger.error(f"✗ Blocco rilevato: nessun output buildozer da {idle:.0f}s")
            if proc:
                try:
                    proc.kill()
                except Exception:
                    pass
            t.join(timeout=2)
            return 124, output_lines

        if (time.time() - last_heartbeat) > 30:
            elapsed = time.time() - start
            if progress_callback:
                progress_callback(
                    current_progress,
                    f"In corso ({elapsed/60:.1f} min, {len(output_lines)} linee)…",
                )
            logger.info(
                f"[Heartbeat] buildozer ({elapsed/60:.1f} min, {len(output_lines)} linee)"
            )
            last_heartbeat = time.time()

        time.sleep(SUBPROCESS_CHECK_INTERVAL)

    if t.is_alive():
        logger.error(f"✗ TIMEOUT buildozer dopo {timeout}s")
        if proc:
            try:
                proc.kill()
            except Exception:
                pass
        t.join(timeout=5)
        return 124, output_lines

    if exception_occurred:
        logger.error(f"✗ Eccezione buildozer: {exception_occurred}")
        return 1, output_lines

    rc = proc.returncode if proc else 1
    logger.info(f"[Buildozer] terminato, rc={rc}, {len(output_lines)} linee")
    return rc, output_lines


def _get_p4a_apk_command(
    game_id: str,
    game_config: dict,
    version: str,
    release: bool,
) -> str:
    """
    Genera il comando p4a diretto per il packaging rapido (Fast Path).
    Deve rispecchiare i parametri di _generate_buildozer_spec.
    """
    pkg_name = _normalize_package_name(game_id)
    title = game_config.get("title_key") or game_id

    # Mapping icone/splash (stessa logica del .spec)
    icon_arg = ""
    if (Path(get_base_path()) / "games" / game_id / "icon.png").exists():
        icon_arg = f"--icon 'games/{game_id}/icon.png'"

    splash_arg = ""
    if (Path(get_base_path()) / "games" / game_id / "splash.png").exists():
        splash_arg = f"--presplash 'games/{game_id}/splash.png'"

    # Requirements e permessi fissi (allineati al motore 2026)
    reqs = "python3,pygame,android,pyjnius,numpy"
    perms = "android.permission.WAKE_LOCK"

    cmd = (
        f"p4a apk --private . "
        f"--package org.hiddenindex.{pkg_name} "
        f"--name '{title}' "
        f"--version '{version}' "
        f"--bootstrap sdl2 "
        f"--requirements {reqs} "
        f"--arch arm64-v8a "
        f"--permission {perms} "
        f"{icon_arg} {splash_arg} "
        f"{'--release' if release else ''}"
    )
    return cmd


# ---------------------------------------------------------------------------
# Entry point principale: build_game_apk()
# ---------------------------------------------------------------------------

def build_game_apk(
    game_id: str,
    output_dir: Path,
    version: str,
    progress_callback: Optional[Callable[[float, str], None]] = None,
    release: bool = False,
) -> dict:
    """
    Compila e impacchetta un gioco come APK Android.

    Args:
        game_id: ID del gioco (es. "LineVenture")
        output_dir: Directory di output Windows (es. build/LineVenture/1.0/)
        version: Stringa di versione (es. "1.0")
        progress_callback: Funzione(progress: 0-100, step_label: str)
        release: Se True, build release (richiede firma). Default debug.

    Returns:
        {
            "success": bool,
            "apk_path": str (se success),
            "error_msg": str (se errore),
            "steps_log": list[str],
        }
    """
    base_path = get_base_path()
    steps_log: list[str] = []
    build_start = time.time()

    def log_step(msg: str, progress: Optional[float] = None) -> None:
        elapsed = time.time() - build_start
        formatted = f"[{elapsed:6.1f}s] {msg}"
        steps_log.append(formatted)
        logger.info(formatted)
        if progress_callback and progress is not None:
            progress_callback(min(progress, 99), msg)

    try:
        # ── 1) Verifica toolchain WSL ─────────────────────────────────────
        log_step("Verifica WSL + Buildozer + JDK17 + NDK 27c...", 2)
        ok, msg = _verify_wsl_toolchain()
        if not ok:
            raise RuntimeError(f"Toolchain WSL non pronta:\n{msg}")
        log_step("✓ Toolchain WSL pronta", 4)

        # ── 2) Validazione gioco ──────────────────────────────────────────
        game_path = base_path / "games" / game_id
        if not game_path.exists():
            raise FileNotFoundError(f"Gioco '{game_id}' non trovato in {game_path}")
        game_config_path = game_path / "game_config.json"
        if not game_config_path.exists():
            raise FileNotFoundError(f"game_config.json non trovato per '{game_id}'")
        game_config = _load_json(game_config_path)
        log_step(f"✓ Gioco validato: {game_id} v{version}", 6)

        # ── 3) Workspace WSL ──────────────────────────────────────────────
        wsl_workspace = _prepare_workspace(game_id, progress_callback)

        # ── 4) Genera config.ini + buildozer.spec ─────────────────────────
        log_step("Generazione config.ini e buildozer.spec...", 16)
        _write_config_and_spec(wsl_workspace, game_id, game_config, version)

        # ── 5) Lancio Buildozer o p4a (Fast Path) ─────────────────────────
        # Calcolo Hash per decidere se serve Buildozer (Full) o basta p4a (Fast)
        spec_content = _generate_buildozer_spec(
            game_id, game_config.get("title_key", game_id), version,
            icon_relpath=f"games/{game_id}/icon.png" if (Path(get_base_path()) / "games" / game_id / "icon.png").exists() else None,
            presplash_relpath=f"games/{game_id}/splash.png" if (Path(get_base_path()) / "games" / game_id / "splash.png").exists() else None
        )
        current_hash = hashlib.md5(spec_content.encode()).hexdigest()

        # Verifica cache e hash precedente
        cached_info = _wsl_run(
            f"test -d '{wsl_workspace}/.buildozer/android/platform' && echo CACHED || echo FRESH; "
            f"cat '{wsl_workspace}/.hie_build_hash' 2>/dev/null || echo 'none'",
            timeout=10,
        ).stdout.splitlines()
        
        is_cached = len(cached_info) > 0 and "CACHED" in cached_info[0]
        prev_hash = cached_info[1] if len(cached_info) > 1 else "none"
        
        # Possiamo usare il Fast Path se l'ambiente è già pronto e il .spec non è cambiato
        # NOTA: In release forziamo sempre Buildozer per sicurezza sulla firma finale.
        use_fast_path = is_cached and (current_hash == prev_hash) and not release
        
        timeout = BUILDOZER_INCREMENTAL_TIMEOUT if is_cached else BUILDOZER_FIRST_BUILD_TIMEOUT
        action = "release" if release else "debug"

        if use_fast_path:
            log_step("⚡ Avvio Fast Path (p4a bypass)...", 18)
            build_cmd = (
                f"set -o pipefail; "
                f"source {WSL_VENV_ACTIVATE} && "
                f"export ANDROID_HOME={WSL_ANDROID_HOME} && "
                f"export ANDROID_SDK_ROOT={WSL_ANDROID_HOME} && "
                f"export ANDROID_NDK_HOME={WSL_ANDROID_NDK} && "
                f"export JAVA_HOME={WSL_JAVA_HOME} && "
                f"export GRADLE_USER_HOME={WSL_GRADLE_HOME} && "
                f"export PATH={WSL_ANDROID_HOME}/cmdline-tools/latest/bin:"
                f"{WSL_ANDROID_HOME}/platform-tools:$PATH && "
                f"export PATH=$(echo $PATH | tr ':' '\\n' | grep -v \"/mnt/c/\" | tr '\\n' ':' | sed 's/:$//') && "
                f"cd '{wsl_workspace}' && "
                + _get_p4a_apk_command(game_id, game_config, version, release)
            )
        else:
            log_step(
                f"Lancio buildozer android {action} "
                f"({'cache presente' if is_cached else 'prima build, ~50 min'})",
                18,
            )
            # ── 5.1) Ottimizzazione: Shared Platform e Gradle Home ────────────
            # Creiamo il symlink alla piattaforma condivisa prima di lanciare buildozer.
            setup_opt_cmd = (
                f"mkdir -p '{WSL_SHARED_PLATFORM}' && "
                f"mkdir -p '{wsl_workspace}/.buildozer/android' && "
                f"ln -sf '{WSL_SHARED_PLATFORM}' '{wsl_workspace}/.buildozer/android/platform' && "
                f"mkdir -p '{WSL_GRADLE_HOME}'"
            )
            _wsl_run(setup_opt_cmd, timeout=30)

            # Applica le patch p4a prima della build (solo se non fast path)
            try:
                pkg_name = _normalize_package_name(game_id)
                if not is_cached:
                    log_step("Bootstrap p4a (download repo)...", 19)
                    bootstrap_cmd = (
                        f"source {WSL_VENV_ACTIVATE} && "
                        f"cd '{wsl_workspace}' && "
                        f"buildozer android p4a -- --help > /dev/null 2>&1"
                    )
                    _wsl_run(bootstrap_cmd, timeout=300)
                
                _apply_p4a_patches(wsl_workspace, pkg_name)
            except Exception as patch_err:
                logger.warning(f"[p4a-patches] Errore non critico: {patch_err}")

            build_cmd = (
                f"set -o pipefail; "
                f"source {WSL_VENV_ACTIVATE} && "
                f"export ANDROID_HOME={WSL_ANDROID_HOME} && "
                f"export ANDROID_SDK_ROOT={WSL_ANDROID_HOME} && "
                f"export ANDROID_NDK_HOME={WSL_ANDROID_NDK} && "
                f"export JAVA_HOME={WSL_JAVA_HOME} && "
                f"export GRADLE_USER_HOME={WSL_GRADLE_HOME} && "
                f"export PATH={WSL_ANDROID_HOME}/cmdline-tools/latest/bin:"
                f"{WSL_ANDROID_HOME}/platform-tools:$PATH && "
                f"export PATH=$(echo $PATH | tr ':' '\\n' | grep -v \"/mnt/c/\" | tr '\\n' ':' | sed 's/:$//') && "
                f"cd '{wsl_workspace}' && "
                f"buildozer android {action}"
            )

        rc, lines = _run_buildozer_with_timeout(build_cmd, timeout, progress_callback)
        if rc == 0:
            # Salva l'hash della build riuscita per il prossimo giro
            _wsl_run(f"echo '{current_hash}' > '{wsl_workspace}/.hie_build_hash'", timeout=5)
        elif rc == 124:
            tail = "\n".join(lines[-20:])
            raise RuntimeError(f"TIMEOUT build dopo {timeout}s.\nUltime righe:\n{tail}")
        else:
            tail = "\n".join(lines[-40:])
            raise RuntimeError(f"Build fallita (rc={rc}).\nOutput finale:\n{tail}")

        log_step(f"✓ {'Fast Path' if use_fast_path else 'Buildozer'} completato con successo", 95)

        # ── 6) Recupero APK ───────────────────────────────────────────────
        log_step("Recupero APK dal workspace...", 96)
        ls_cmd = f"ls -1 '{wsl_workspace}/bin/'*.apk 2>/dev/null | head -1"
        apk_wsl_path = _wsl_run(ls_cmd, timeout=10).stdout.strip()
        if not apk_wsl_path:
            raise FileNotFoundError(
                f"Nessun APK trovato in {wsl_workspace}/bin/ dopo build success"
            )

        output_dir.mkdir(parents=True, exist_ok=True)
        apk_name = Path(apk_wsl_path).name
        dst_apk = output_dir / apk_name
        # Copia da WSL a Windows via cat → file binario su filesystem montato
        wsl_out_path = _windows_path_to_wsl(dst_apk)
        cp_cmd = f"cp '{apk_wsl_path}' '{wsl_out_path}'"
        cp_result = _wsl_run(cp_cmd, timeout=120)
        if cp_result.returncode != 0:
            raise RuntimeError(f"Copia APK fallita: {cp_result.stderr}")

        if not dst_apk.exists():
            raise FileNotFoundError(f"APK non trovato dopo copia: {dst_apk}")

        apk_size_mb = dst_apk.stat().st_size / 1024 / 1024
        log_step(f"✓ APK copiato in {dst_apk} ({apk_size_mb:.1f} MB)", 99)

        elapsed = time.time() - build_start
        log_step(f"✓ Build APK completato ({elapsed/60:.1f} min)", 100)

        return {
            "success": True,
            "apk_path": str(dst_apk),
            "apk_size_mb": apk_size_mb,
            "error_msg": None,
            "steps_log": steps_log,
        }

    except Exception as e:
        elapsed = time.time() - build_start
        logger.exception(f"✗ Errore build APK '{game_id}' ({elapsed/60:.1f} min): {e}")
        log_step(f"✗ ERRORE: {str(e)[:200]}", 100)
        return {
            "success": False,
            "apk_path": None,
            "apk_size_mb": 0.0,
            "error_msg": str(e),
            "steps_log": steps_log,
        }
