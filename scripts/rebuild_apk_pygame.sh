#!/bin/bash
# scripts/rebuild_apk_pygame.sh
#
# Cambio requirements pygame-ce → pygame.
# p4a ha recipe per `pygame` (cross-compile pulita), nessuna per `pygame-ce`
# (pip prendeva wheel host x86_64 → ImportError EM_X86_64 al boot).
#
# Necessarie 4 azioni:
#  1. Aggiornare buildozer.spec
#  2. Cancellare la dist (cambio requirements forza regen)
#  3. Cancellare pip cache (evita reuso wheel pygame-ce host)
#  4. Cancellare il workspace pygame-ce eventualmente buildato
# Rebuild incrementale: numpy + tutte le altre lib restano in cache.

set -e

WORKSPACE=/root/apk_lineventure
LOG=/tmp/buildozer_pygame.log
SRC="/mnt/g/HIE git"

echo "=== 1) Update buildozer.spec (pygame-ce → pygame) ==="
cp "$SRC/scripts/android_proto/buildozer.spec" "$WORKSPACE/buildozer.spec"
sed -i 's/\r$//' "$WORKSPACE/buildozer.spec"
grep "requirements" "$WORKSPACE/buildozer.spec" | head -2
echo

echo "=== 2) Re-sync source (main.py + engine) ==="
rsync -a --delete-excluded \
  --exclude='__pycache__' --exclude='*.pyc' --exclude='*.pyo' \
  "$SRC/engine/" "$WORKSPACE/engine/"
cp "$SRC/main.py" "$WORKSPACE/main.py"
echo

echo "=== 3) Clean dist (requirements changed) ==="
rm -rf "$WORKSPACE/.buildozer/android/platform/build-arm64-v8a_armeabi-v7a/dists/"
echo "  dists/ removed"

echo "=== 4) Clean pip cache (avoid reusing pygame-ce host wheel) ==="
rm -rf /root/.cache/pip 2>/dev/null || true
rm -rf "$WORKSPACE/.buildozer/android/platform/build-arm64-v8a_armeabi-v7a/build/other_builds/pygame_ce" 2>/dev/null || true
rm -rf "$WORKSPACE/.buildozer/android/platform/build-arm64-v8a_armeabi-v7a/build/python-installs/lineventure/arm64-v8a/pygame" 2>/dev/null || true
rm -rf "$WORKSPACE/.buildozer/android/platform/build-arm64-v8a_armeabi-v7a/build/python-installs/lineventure/armeabi-v7a/pygame" 2>/dev/null || true
echo "  pip cache + pygame_ce build + bad pygame installs removed"

# Cancella anche eventuali bin/ vecchi
rm -f "$WORKSPACE/bin/"*.apk 2>/dev/null || true
echo

echo "=== 5) Verify p4a patch (loadLibraries fix) still in template ==="
TEMPLATE_PA="$WORKSPACE/.buildozer/android/platform/python-for-android/pythonforandroid/bootstraps/sdl2/build/src/main/java/org/kivy/android/PythonActivity.java"
if grep -q "p4a fix: force loadLibraries before UnpackFilesTask" "$TEMPLATE_PA"; then
    echo "  OK: patch present"
else
    echo "  REAPPLYING..."
    bash /root/fix_p4a_sdl2_load.sh || true
fi
echo

echo "=== 6) Activate toolchain (NDK 28) ==="
source /root/venv_p4a/bin/activate
export ANDROID_HOME=/root/android-sdk
export ANDROID_SDK_ROOT=/root/android-sdk
export ANDROID_NDK_HOME=/root/android-sdk/ndk/28.2.13676358
export JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64
export PATH=$ANDROID_HOME/cmdline-tools/latest/bin:$ANDROID_HOME/platform-tools:$PATH

echo "=== 6b) Optimize assets (SOLO mobile — originali repo intatti) ==="
python -m pip show pillow >/dev/null 2>&1 || python -m pip install --quiet pillow || true
python "$SRC/scripts/optimize_assets_mobile.py" "$WORKSPACE/engine/assets" --max-dim 1280 || echo "WARN: asset optimize saltato"
echo

cd "$WORKSPACE"

echo "=== 7) Launching buildozer android debug ==="
echo "Log: $LOG"
echo "Expected: 10-15 min (only pygame ARM cross-compile + dist regen + gradle)"
echo

buildozer android debug 2>&1 | tee "$LOG"
BUILD_EXIT=${PIPESTATUS[0]}

echo
echo "=== BUILD FINISHED — exit: $BUILD_EXIT ==="

if [ "$BUILD_EXIT" = "0" ]; then
    ls -lh "$WORKSPACE/bin/"
    cp "$WORKSPACE/bin/"*.apk "/mnt/g/HIE git/build/LineVenture/1.0/android/lineventure-1.0-debug.apk"
    echo
    echo "APK copied to: G:\\HIE git\\build\\LineVenture\\1.0\\android\\lineventure-1.0-debug.apk"
    echo
    echo "=== Verify pygame.so architecture ==="
    cd /tmp && rm -rf apk_check && mkdir apk_check && cd apk_check
    unzip -q -o "$WORKSPACE/bin/"*.apk 'assets/private.tar' 2>/dev/null
    if [ -f assets/private.tar ]; then
        tar -tzf assets/private.tar 2>/dev/null | grep 'pygame/base' | head -3
    fi
    NDK_READELF=/root/android-sdk/ndk/28.2.13676358/toolchains/llvm/prebuilt/linux-x86_64/bin/llvm-readelf
    # cerca pygame .so dentro python-installs
    PYG_SO=$(find "$WORKSPACE/.buildozer/android/platform/build-arm64-v8a_armeabi-v7a/build/python-installs/lineventure/arm64-v8a/pygame" -name '*.so' 2>/dev/null | head -1)
    if [ -n "$PYG_SO" ]; then
        echo "  pygame .so:  $(basename $PYG_SO)"
        echo "  arch:        $($NDK_READELF -h $PYG_SO 2>/dev/null | grep Machine | awk '{print $2,$3}')"
    fi
    echo "BUILD_OK"
else
    echo "BUILD_FAILED"
    tail -50 "$LOG"
fi

exit $BUILD_EXIT
