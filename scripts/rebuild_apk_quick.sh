#!/bin/bash
# scripts/rebuild_apk_quick.sh
#
# Rebuild rapido dell'APK dopo modifica al solo codice Python (main.py, engine/*).
# Riusa l'intera cache libraries di /root/apk_lineventure/.buildozer/ — il bytecode
# viene ricompilato e il packaging Gradle rifatto, ~3-5 minuti totali.

set -e

WORKSPACE=/root/apk_lineventure
LOG=/tmp/buildozer_quick.log
SRC="/mnt/g/HIE git"

echo "=== 1) Sync source files Python (engine + main.py + games) ==="
rsync -a --delete-excluded \
  --exclude='__pycache__' --exclude='*.pyc' --exclude='*.pyo' \
  "$SRC/engine/" "$WORKSPACE/engine/"
cp "$SRC/main.py" "$WORKSPACE/main.py"
echo "  source files updated"
echo

echo "=== 2) Toolchain env ==="
source /root/venv_p4a/bin/activate
export ANDROID_HOME=/root/android-sdk
export ANDROID_SDK_ROOT=/root/android-sdk
export ANDROID_NDK_HOME=/root/android-sdk/ndk/27.2.12479018
export JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64
export PATH=$ANDROID_HOME/cmdline-tools/latest/bin:$ANDROID_HOME/platform-tools:$PATH

cd "$WORKSPACE"

echo "=== 3) Launching buildozer android debug (quick) ==="
echo "Log: $LOG"
echo

buildozer android debug 2>&1 | tee "$LOG"
BUILD_EXIT=${PIPESTATUS[0]}

echo
echo "=== BUILD FINISHED — exit code: $BUILD_EXIT ==="

if [ "$BUILD_EXIT" = "0" ]; then
    ls -lh "$WORKSPACE/bin/"
    # Copia anche su Windows
    cp "$WORKSPACE/bin/"*.apk "/mnt/g/HIE git/build/LineVenture/1.0/android/lineventure-1.0-debug.apk"
    echo
    echo "APK copiato in: G:\\HIE git\\build\\LineVenture\\1.0\\android\\lineventure-1.0-debug.apk"
    echo "BUILD_OK"
else
    echo "BUILD_FAILED"
    tail -30 "$LOG"
fi

exit $BUILD_EXIT
