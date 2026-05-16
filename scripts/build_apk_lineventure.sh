#!/bin/bash
# scripts/build_apk_lineventure.sh
#
# Lancia Buildozer per generare l'APK debug di LineVenture.
# Va eseguito dentro WSL Ubuntu 24.04 come root.

set -e

WORKSPACE=/root/apk_lineventure
LOG=/tmp/buildozer_lineventure.log

# Attiva toolchain (env vars + venv Buildozer)
source /root/venv_p4a/bin/activate
export ANDROID_HOME=/root/android-sdk
export ANDROID_SDK_ROOT=/root/android-sdk
export ANDROID_NDK_HOME=/root/android-sdk/ndk/27.2.12479018
export JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64
export PATH=$ANDROID_HOME/cmdline-tools/latest/bin:$ANDROID_HOME/platform-tools:$PATH

cd "$WORKSPACE"

echo "=== Toolchain check ==="
buildozer --version
java -version 2>&1 | head -1
echo

echo "=== Workspace contents ==="
ls -la
echo

echo "=== Launching buildozer android debug ==="
echo "Log written to: $LOG"
echo

# Pipe stdout+stderr a tee per avere il log e mostrare a video
buildozer android debug 2>&1 | tee "$LOG"
BUILD_EXIT=${PIPESTATUS[0]}

echo
echo "=== BUILD FINISHED ==="
echo "buildozer exit code: $BUILD_EXIT"
echo

if [ "$BUILD_EXIT" = "0" ]; then
    echo "=== APK output ==="
    ls -la "$WORKSPACE/bin/" 2>&1 || echo "WARN: bin/ not found"
    echo "BUILD_OK"
else
    echo "BUILD_FAILED"
    echo
    echo "=== Last 30 lines of log ==="
    tail -30 "$LOG"
fi

exit $BUILD_EXIT
