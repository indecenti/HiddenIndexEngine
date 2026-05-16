#!/bin/bash
# scripts/setup_android_wsl.sh
#
# Completa il setup della toolchain Android dentro WSL Ubuntu 24.04.
# Eseguibile come root. Idempotente: rilanciabile in sicurezza.

set -e

ANDROID_HOME=/root/android-sdk
JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64
SDKMANAGER="$ANDROID_HOME/cmdline-tools/latest/bin/sdkmanager"

export ANDROID_HOME JAVA_HOME
export PATH="$ANDROID_HOME/cmdline-tools/latest/bin:$PATH"

echo "=== 1) Accept SDK licenses ==="
yes | "$SDKMANAGER" --licenses >/dev/null 2>&1 || true
echo "LICENSES_OK"

echo "=== 2) Install platform-tools, android-35, build-tools 35.0.0, NDK 27.2.12479018 ==="
"$SDKMANAGER" --install \
    "platform-tools" \
    "platforms;android-35" \
    "build-tools;35.0.0" \
    "ndk;27.2.12479018"
echo "SDK_INSTALL_OK"

echo "=== 3) Update /root/.bashrc with toolchain exports ==="
# Rimuove eventuali blocchi precedenti per idempotenza
sed -i '/# === Buildozer Android Toolchain ===/,/# === END Buildozer Toolchain ===/d' /root/.bashrc

cat >> /root/.bashrc << 'BRC_EOF'

# === Buildozer Android Toolchain ===
if [ -f /root/venv_p4a/bin/activate ]; then
    source /root/venv_p4a/bin/activate
fi
export ANDROID_HOME=$HOME/android-sdk
export ANDROID_SDK_ROOT=$ANDROID_HOME
export ANDROID_NDK_HOME=$ANDROID_HOME/ndk/27.2.12479018
export JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64
export PATH=$ANDROID_HOME/cmdline-tools/latest/bin:$ANDROID_HOME/platform-tools:$PATH
# === END Buildozer Toolchain ===
BRC_EOF
echo "BASHRC_OK"

echo "=== 4) Smoke test ==="
echo -n "buildozer: "; /root/venv_p4a/bin/buildozer --version
echo -n "java: "; java -version 2>&1 | head -1
echo -n "sdkmanager installed packages: "
"$SDKMANAGER" --list_installed 2>/dev/null | grep -E "(platform-tools|platforms;android-35|build-tools;35|ndk;27)" || echo "WARN: some packages may be missing"

echo
echo "==============================="
echo "SETUP_COMPLETE"
echo "==============================="
