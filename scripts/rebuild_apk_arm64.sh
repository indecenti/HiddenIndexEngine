#!/bin/bash
# scripts/rebuild_apk_arm64.sh
#
# Build di RELEASE/distribuzione: SOLO arm64-v8a (device reali) → APK più leggero.
# Poiché il set di arch cambia (niente x86_64), p4a usa una NUOVA dir di build
# (build-arm64-v8a) e ricompila le librerie native da zero (~30-45 min), poi
# applica la patch SIMD di pygame e ricompila pygame (~10-15 min). 2 passaggi.
#
# Icona/presplash app DINAMICI: presi dal gioco indicato da $GAME (default
# LineVenture). Il presplash viene generato dall'icona se assente.

set -e

GAME="${GAME:-LineVenture}"
WORKSPACE=/root/apk_lineventure
LOG=/tmp/buildozer_arm64.log
SRC="/mnt/g/HIE git"

echo "=== 1) buildozer.spec game-aware per: $GAME ==="
cp "$SRC/scripts/android_proto/buildozer.spec" "$WORKSPACE/buildozer.spec"
sed -i 's/\r$//' "$WORKSPACE/buildozer.spec"
SPEC="$WORKSPACE/buildozer.spec"

# Metadati app per-gioco (così ogni gioco è un'app distinta e coesistono):
#   package.name = nome gioco minuscolo senza caratteri non alfanumerici
#   title        = nome gioco con spazi
PKG=$(echo "$GAME" | tr '[:upper:]' '[:lower:]' | tr -cd '[:alnum:]')
TITLE=$(echo "$GAME" | tr '_' ' ')
# Versione: override via env VERSION, altrimenti dal game_config del gioco.
if [ -z "$VERSION" ]; then
    VERSION=$(grep -oE '"version"[[:space:]]*:[[:space:]]*"[^"]+"' "$SRC/games/$GAME/game_config.json" | head -1 | sed -E 's/.*"([^"]+)"$/\1/')
fi
VERSION="${VERSION:-1.0}"

sed -i "s#games/LineVenture/assets#games/$GAME/assets#g" "$SPEC"
sed -i "s/^title = .*/title = $TITLE/" "$SPEC"
sed -i "s/^package.name = .*/package.name = $PKG/" "$SPEC"
sed -i "s/^version = .*/version = $VERSION/" "$SPEC"

# Gioco attivo: config.ini packagizzato (l'app legge default_game).
cat > "$WORKSPACE/config.ini" <<CFG
[engine]
default_game = $GAME
resolution_w = 1920
resolution_h = 1080
fullscreen = 1
language = it
CFG

echo "  GAME=$GAME PKG=$PKG TITLE='$TITLE' VERSION=$VERSION"
grep -E "^title|^package.name|^version|archs|icon.filename" "$SPEC"
echo

echo "=== 2) Re-sync source (engine + games + main.py) ==="
rsync -a --delete-excluded \
  --exclude='__pycache__' --exclude='*.pyc' --exclude='*.pyo' \
  "$SRC/engine/" "$WORKSPACE/engine/"
rsync -a --delete-excluded \
  --exclude='__pycache__' --exclude='*.pyc' --exclude='*.pyo' --exclude='*.mp4' \
  "$SRC/games/" "$WORKSPACE/games/"
cp "$SRC/main.py" "$WORKSPACE/main.py"
echo "  source files updated"
echo

echo "=== 3) Optimize assets (scene-bg + generico) ==="
source /root/venv_p4a/bin/activate
python -m pip show pillow >/dev/null 2>&1 || python -m pip install --quiet pillow || true
python "$SRC/scripts/optimize_scene_backgrounds.py" "$WORKSPACE/games" --max-dim 1280 || echo "WARN: scene-bg saltato"
python "$SRC/scripts/optimize_assets_mobile.py" "$WORKSPACE/engine/assets" --max-dim 1280 || echo "WARN: asset saltato"
python "$SRC/scripts/optimize_assets_mobile.py" "$WORKSPACE/games" --max-dim 1280 || echo "WARN: games saltato"
# Presplash dinamico: genera dall'icona se manca per il gioco selezionato.
PRESPLASH="$WORKSPACE/games/$GAME/assets/presplash.png"
ICON="$WORKSPACE/games/$GAME/assets/icon.png"
if [ ! -f "$PRESPLASH" ] && [ -f "$ICON" ]; then
    python - "$ICON" "$PRESPLASH" <<'PY'
import sys
from PIL import Image
icon, out = sys.argv[1], sys.argv[2]
W, H = 1280, 720
bg = Image.new('RGB', (W, H), (10, 12, 18))
ic = Image.open(icon).convert('RGBA')
s = int(H * 0.42); ic = ic.resize((s, s), Image.LANCZOS)
bg.paste(ic, ((W - s) // 2, (H - s) // 2), ic)
bg.save(out)
print('presplash generato per', out)
PY
fi
echo

echo "=== 4) Pulizia dist (nuovo set arch → build-arm64-v8a) ==="
rm -rf "$WORKSPACE"/.buildozer/android/platform/build-*/dists/ 2>/dev/null || true
rm -f "$WORKSPACE/bin/"*.apk 2>/dev/null || true
echo

echo "=== 5) Toolchain (NDK 28) ==="
export ANDROID_HOME=/root/android-sdk
export ANDROID_SDK_ROOT=/root/android-sdk
export ANDROID_NDK_HOME=/root/android-sdk/ndk/28.2.13676358
export JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64
export PATH=$ANDROID_HOME/cmdline-tools/latest/bin:$ANDROID_HOME/platform-tools:$PATH
cd "$WORKSPACE"

echo "=== 6) PASS 1: buildozer android debug (compila tutto per arm64) ==="
buildozer android debug 2>&1 | tee "$LOG" || true

echo "=== 7) Patch SIMD pygame (definisce i simboli alphablit) ==="
sed "s/\r$//" "$SRC/scripts/fix_pygame_simd_x86.sh" > /tmp/fix_simd.sh
bash /tmp/fix_simd.sh || echo "WARN: patch SIMD non applicata"
echo

echo "=== 8) PASS 2: buildozer android debug (ricompila pygame patchato + packaging) ==="
buildozer android debug 2>&1 | tee -a "$LOG"
BUILD_EXIT=${PIPESTATUS[0]}

echo
echo "=== BUILD FINISHED — exit: $BUILD_EXIT ==="
if [ "$BUILD_EXIT" = "0" ]; then
    ls -lh "$WORKSPACE/bin/"
    OUTDIR="$SRC/build/$GAME/$VERSION/android"
    mkdir -p "$OUTDIR"
    for apk in "$WORKSPACE/bin/"*.apk; do
        cp "$apk" "$OUTDIR/"
    done
    echo "APK copiati in build/$GAME/$VERSION/android/"
    ls -lh "$OUTDIR"/*.apk
    echo "BUILD_OK"
else
    echo "BUILD_FAILED"; tail -50 "$LOG"
fi
exit $BUILD_EXIT
