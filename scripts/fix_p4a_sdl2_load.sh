#!/bin/bash
# scripts/fix_p4a_sdl2_load.sh
#
# Patcha PythonActivity.java di p4a (bootstrap SDL2) per fixare il crash
#   java.lang.UnsatisfiedLinkError: SDLActivity.nativeSetenv
# causato dal fatto che SDL2 2.30+ ha rimosso loadLibraries() da onCreate()
# spostandolo in finishLoad() — flusso che viene eseguito DOPO il
# UnpackFilesTask di p4a che però chiama già nativeSetenv.
#
# Fix: aggiungere loadLibraries() esplicito in PythonActivity.onCreate()
# prima di lanciare UnpackFilesTask.

set -e

DIST_PA="/root/apk_lineventure/.buildozer/android/platform/build-arm64-v8a_armeabi-v7a/dists/lineventure/src/main/java/org/kivy/android/PythonActivity.java"
TEMPLATE_PA="/root/apk_lineventure/.buildozer/android/platform/python-for-android/pythonforandroid/bootstraps/sdl2/build/src/main/java/org/kivy/android/PythonActivity.java"

apply_patch() {
    local FILE="$1"
    if [ ! -f "$FILE" ]; then
        echo "  SKIP: $FILE non esiste"
        return 0
    fi

    # Idempotenza: se già patchato, skip
    if grep -q "// p4a fix: force loadLibraries before UnpackFilesTask" "$FILE"; then
        echo "  OK: $FILE già patchato"
        return 0
    fi

    # Patch: insert loadLibraries() before "new UnpackFilesTask().execute"
    # Uso sed con marker testuale specifico
    sed -i '/this\.mActivity = this;/a\
\
        // p4a fix: force loadLibraries before UnpackFilesTask\
        // (SDL2 2.30+ moved loadLibraries from onCreate to finishLoad,\
        //  but UnpackFilesTask.onPostExecute calls nativeSetenv which\
        //  requires libSDL2.so already loaded).\
        loadLibraries();' "$FILE"

    echo "  PATCHED: $FILE"
}

echo "=== Applying p4a SDL2 load fix ==="
echo
echo "--- 1) Dist file (immediate effect on next build) ---"
apply_patch "$DIST_PA"
echo
echo "--- 2) Template p4a (persistent across rebuilds) ---"
apply_patch "$TEMPLATE_PA"
echo
echo "=== Verification ==="
echo "  dist file context after patch:"
grep -n -B1 -A1 "loadLibraries()" "$DIST_PA" | head -20 || true

echo
echo "PATCH_OK"
