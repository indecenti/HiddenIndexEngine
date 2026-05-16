#!/bin/bash
# scripts/rebuild_apk_with_numpy.sh
#
# Rigenera l'APK del prototipo LineVenture dopo aver aggiunto numpy ai requirements.
# - Aggiorna buildozer.spec
# - Pulisce solo la cartella dist/ (necessario perché i requirements sono cambiati)
# - Lascia intatta la cache di python3/SDL2/openssl/etc (saving ~30 min)
# - Rilancia buildozer android debug

set -e

WORKSPACE=/root/apk_lineventure
LOG=/tmp/buildozer_rebuild.log

echo "=== 1) Update buildozer.spec with numpy in requirements ==="
cp "/mnt/g/HIE git/scripts/android_proto/buildozer.spec" "$WORKSPACE/buildozer.spec"
sed -i 's/\r$//' "$WORKSPACE/buildozer.spec"
grep -E "requirements|minapi" "$WORKSPACE/buildozer.spec"
echo

echo "=== 2) Clean dist (forces regen for new requirements) ==="
# I dist sono nominati per requirements; cambiando reqs serve nuovo dist.
# Cancelliamo SOLO la cartella dists/ (non l'intera build-arm64-v8a_armeabi-v7a/
# perché conterrebbe le librerie già compilate da non ricostruire).
rm -rf "$WORKSPACE/.buildozer/android/platform/build-arm64-v8a_armeabi-v7a/dists/"
echo "  Removed: dists/"

# Pulisci anche eventuali bin/ vecchi per non confondere
rm -f "$WORKSPACE/bin/"*.apk 2>/dev/null || true
echo

echo "=== 3) Activate toolchain ==="
source /root/venv_p4a/bin/activate
export ANDROID_HOME=/root/android-sdk
export ANDROID_SDK_ROOT=/root/android-sdk
export ANDROID_NDK_HOME=/root/android-sdk/ndk/27.2.12479018
export JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64
export PATH=$ANDROID_HOME/cmdline-tools/latest/bin:$ANDROID_HOME/platform-tools:$PATH

cd "$WORKSPACE"

echo "=== 4) Launching buildozer android debug ==="
echo "Log: $LOG"
echo "Expected: ~10-15 min (numpy ARM compile + dist regen + gradle)"
echo

buildozer android debug 2>&1 | tee "$LOG"
BUILD_EXIT=${PIPESTATUS[0]}

echo
echo "=== BUILD FINISHED ==="
echo "exit code: $BUILD_EXIT"
echo

if [ "$BUILD_EXIT" = "0" ]; then
    echo "=== APK output ==="
    ls -lh "$WORKSPACE/bin/" 2>&1 || echo "WARN: bin/ not found"
    echo "BUILD_OK"
else
    echo "BUILD_FAILED"
    echo "=== Last 30 lines of log ==="
    tail -30 "$LOG"
fi

exit $BUILD_EXIT
