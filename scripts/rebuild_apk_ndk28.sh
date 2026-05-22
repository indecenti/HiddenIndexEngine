#!/bin/bash
# scripts/rebuild_apk_ndk28.sh
#
# Rebuild completo dell'APK passando da NDK 27c → NDK 28.2.13676358.
# NDK 28 produce librerie con 16 KB ELF page-size alignment di default,
# richiesto da Android 15+ (emulatore Pixel_10 sdk_gphone16k_x86_64).
#
# Cancella tutto il build artifact target-specific (ma NON il sorgente
# p4a già scaricato) per forzare ricompilazione di:
#   - python3.14 ARM × 2 arch
#   - SDL2 (+ image, mixer, ttf) × 2 arch
#   - openssl, sqlite3, libffi, libpng × 2 arch
#   - numpy × 2 arch
#   - pyjnius × 2 arch
# Tempo previsto: 30-45 min.

set -e

WORKSPACE=/root/apk_lineventure
LOG=/tmp/buildozer_ndk28.log
SRC="/mnt/g/HIE git"

echo "=== 1) Verify NDK 28 installed ==="
ls -d /root/android-sdk/ndk/28.2.13676358 || (echo "FAIL: NDK 28 missing"; exit 1)
cat /root/android-sdk/ndk/28.2.13676358/source.properties | head -3
echo

echo "=== 2) Update buildozer.spec ==="
cp "$SRC/scripts/android_proto/buildozer.spec" "$WORKSPACE/buildozer.spec"
sed -i 's/\r$//' "$WORKSPACE/buildozer.spec"
grep -E "ndk|minapi" "$WORKSPACE/buildozer.spec"
echo

echo "=== 3) Re-sync source (engine + main.py with crash handler) ==="
rsync -a --delete-excluded \
  --exclude='__pycache__' --exclude='*.pyc' --exclude='*.pyo' \
  "$SRC/engine/" "$WORKSPACE/engine/"
cp "$SRC/main.py" "$WORKSPACE/main.py"
echo "  source files updated"
echo

echo "=== 4) Clean target build dir (KEEP p4a sources) ==="
# Rimuove SOLO il build dir target-specific:
#   build-arm64-v8a_armeabi-v7a/ contiene tutto il lavoro fatto con NDK 27,
#   va rifatto. La cartella python-for-android/ (sorgente p4a) resta.
rm -rf "$WORKSPACE/.buildozer/android/platform/build-arm64-v8a_armeabi-v7a/"
rm -f "$WORKSPACE/bin/"*.apk 2>/dev/null || true
echo "  build dir cleaned"
echo

echo "=== 5) Verify p4a patch (loadLibraries fix) is still in template ==="
TEMPLATE_PA="$WORKSPACE/.buildozer/android/platform/python-for-android/pythonforandroid/bootstraps/sdl2/build/src/main/java/org/kivy/android/PythonActivity.java"
if grep -q "p4a fix: force loadLibraries before UnpackFilesTask" "$TEMPLATE_PA"; then
    echo "  OK: patch present in template"
else
    echo "  REAPPLYING patch..."
    bash /root/fix_p4a_sdl2_load.sh || true
fi
echo

echo "=== 6) Activate toolchain (NDK 28!) ==="
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
echo "Expected: 30-45 min full rebuild with NDK 28"
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
    echo "=== Verify NDK 28 alignment ==="
    NDK_OBJDUMP=/root/android-sdk/ndk/28.2.13676358/toolchains/llvm/prebuilt/linux-x86_64/bin/llvm-readelf
    if [ -x "$NDK_OBJDUMP" ]; then
        # Check alignment of libsqlite3.so (the one that failed before)
        cd /tmp && rm -rf apk_check && mkdir apk_check && cd apk_check
        unzip -q "$WORKSPACE/bin/"*.apk lib/arm64-v8a/libsqlite3.so
        echo "  libsqlite3.so LOAD segment alignment:"
        $NDK_OBJDUMP -l lib/arm64-v8a/libsqlite3.so 2>/dev/null | grep -A1 "LOAD" | head -6
    fi
    echo "BUILD_OK"
else
    echo "BUILD_FAILED"
    tail -50 "$LOG"
fi

exit $BUILD_EXIT
