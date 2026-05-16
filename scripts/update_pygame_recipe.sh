#!/bin/bash
# scripts/update_pygame_recipe.sh
#
# Aggiorna la recipe pygame di p4a da 2.1.0 → 2.6.1.
# pygame 2.1.0 usa `longintrepr.h` rimosso in Python 3.12+. p4a master usa
# Python 3.14, quindi la build fallisce con "longintrepr.h not found".
# pygame 2.6.x è compatibile con Python 3.12-3.14.

set -e

RECIPE=/root/apk_lineventure/.buildozer/android/platform/python-for-android/pythonforandroid/recipes/pygame/__init__.py

echo "=== Current pygame recipe version ==="
grep "version =" "$RECIPE" | head -1

# Backup + patch
cp -n "$RECIPE" "$RECIPE.bak" 2>/dev/null || true
sed -i "s/version = '2.1.0'/version = '2.6.1'/" "$RECIPE"

echo "=== New pygame recipe version ==="
grep "version =" "$RECIPE" | head -1

echo
echo "=== Clean pygame build artifacts (force rebuild) ==="
rm -rf /root/apk_lineventure/.buildozer/android/platform/build-arm64-v8a_armeabi-v7a/build/other_builds/pygame 2>/dev/null || true
rm -rf /root/apk_lineventure/.buildozer/android/platform/build-arm64-v8a_armeabi-v7a/build/python-installs/lineventure/arm64-v8a/pygame 2>/dev/null || true
rm -rf /root/apk_lineventure/.buildozer/android/platform/build-arm64-v8a_armeabi-v7a/build/python-installs/lineventure/armeabi-v7a/pygame 2>/dev/null || true
# anche la tar cache del download di pygame, per forzare download della nuova versione
rm -f /root/.buildozer/android/packages/pygame/2.1.0.tar.gz 2>/dev/null || true
echo "  cleaned"

echo
echo "RECIPE_UPDATED"
