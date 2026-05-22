#!/bin/bash
# scripts/rebuild_apk_x86_verify.sh
#
# Build di VERIFICA per emulatore Android Studio (AVD x86_64).
# buildozer.spec ora include arch x86_64 oltre ad arm64-v8a: l'arch arm64 gia`
# compilato viene riusato, x86_64 viene compilato da zero (~30-45 min la prima
# volta: python, SDL2, numpy, pygame, pyjnius per x86_64).
# Usa NDK 28 (richiesto dall'immagine emulatore con page size 16 KB).

set -e

WORKSPACE=/root/apk_lineventure
LOG=/tmp/buildozer_x86_verify.log
SRC="/mnt/g/HIE git"

echo "=== 1) Update buildozer.spec (arm64 + x86_64) ==="
cp "$SRC/scripts/android_proto/buildozer.spec" "$WORKSPACE/buildozer.spec"
sed -i 's/\r$//' "$WORKSPACE/buildozer.spec"
grep -E "archs|ndk|minapi" "$WORKSPACE/buildozer.spec"
echo

echo "=== 2) Re-sync source (engine + games + main.py) ==="
rsync -a --delete-excluded \
  --exclude='__pycache__' --exclude='*.pyc' --exclude='*.pyo' \
  "$SRC/engine/" "$WORKSPACE/engine/"
# games/: config, temi, poster e stringhe del gioco (esclude i .mp4 grossi,
# non riproducibili su Android e comunque esclusi dall'APK).
rsync -a --delete-excluded \
  --exclude='__pycache__' --exclude='*.pyc' --exclude='*.pyo' --exclude='*.mp4' \
  "$SRC/games/" "$WORKSPACE/games/"
cp "$SRC/main.py" "$WORKSPACE/main.py"
echo "  source files updated"
echo

echo "=== 3) Optimize assets (SOLO mobile — originali repo intatti) ==="
source /root/venv_p4a/bin/activate
python -m pip show pillow >/dev/null 2>&1 || python -m pip install --quiet pillow || true
# 3a) PRIMA gli sfondi delle scene: ridimensiona E riscala le coordinate oggetti
#     (le coord sono in pixel dello sfondo originale: vanno scalate insieme).
python "$SRC/scripts/optimize_scene_backgrounds.py" "$WORKSPACE/games" --max-dim 1280 || echo "WARN: scene-bg optimize saltato"
# 3b) Poi l'ottimizzatore generico (icone, ecc.). Gli sfondi scena sono già a
#     dimensione finale e vengono saltati.
python "$SRC/scripts/optimize_assets_mobile.py" "$WORKSPACE/engine/assets" --max-dim 1280 || echo "WARN: asset optimize saltato"
python "$SRC/scripts/optimize_assets_mobile.py" "$WORKSPACE/games" --max-dim 1280 || echo "WARN: games optimize saltato"
echo

echo "=== 4) Force dist regen per il nuovo set di arch ==="
# Rimuove solo le dist (forza ricostruzione del bundle per arm64+x86_64);
# i build delle librerie restano in cache e vengono riusati dove gia` presenti.
rm -rf "$WORKSPACE"/.buildozer/android/platform/build-*/dists/ 2>/dev/null || true
rm -f "$WORKSPACE/bin/"*.apk 2>/dev/null || true
echo "  dists pulite"
echo

echo "=== 5) Activate toolchain (NDK 28) ==="
export ANDROID_HOME=/root/android-sdk
export ANDROID_SDK_ROOT=/root/android-sdk
export ANDROID_NDK_HOME=/root/android-sdk/ndk/28.2.13676358
export JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64
export PATH=$ANDROID_HOME/cmdline-tools/latest/bin:$ANDROID_HOME/platform-tools:$PATH

cd "$WORKSPACE"

echo "=== 6) Launching buildozer android debug ==="
echo "Log: $LOG"
buildozer android debug 2>&1 | tee "$LOG"
BUILD_EXIT=${PIPESTATUS[0]}

echo
echo "=== BUILD FINISHED — exit: $BUILD_EXIT ==="
if [ "$BUILD_EXIT" = "0" ]; then
    ls -lh "$WORKSPACE/bin/"
    mkdir -p "$SRC/build/LineVenture/1.0/android/"
    for apk in "$WORKSPACE/bin/"*.apk; do
        cp "$apk" "$SRC/build/LineVenture/1.0/android/"
    done
    echo "APK copiati in build/LineVenture/1.0/android/"
    echo "BUILD_OK"
else
    echo "BUILD_FAILED"
    tail -50 "$LOG"
fi
exit $BUILD_EXIT
