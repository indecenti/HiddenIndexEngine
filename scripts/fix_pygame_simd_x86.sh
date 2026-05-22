#!/bin/bash
# scripts/fix_pygame_simd_x86.sh
#
# Fix pygame 2.6.1 SIMD per build multi-arch (arm64-v8a + x86_64).
# Il modulo `surface` referenzia alphablit_alpha_sse2_argb_surf_alpha, definito
# in src_c/simd_blitters_sse2.c; senza aggiungerlo a Setup.Android.SDL2.in il
# surface.so resta con simboli non risolti -> ImportError al boot.
# Versione path-flessibile (trova la build-* dir corrente) e per TUTTE le arch.

set -e

PLATFORM=/root/apk_lineventure/.buildozer/android/platform
ADD="src_c/simd_blitters_sse2.c src_c/simd_blitters_avx2.c"

echo "=== 1) Patch Setup.Android.SDL2.in (tutte le arch) ==="
mapfile -t SETUPS < <(find "$PLATFORM"/build-*/build/other_builds/pygame -name Setup.Android.SDL2.in 2>/dev/null)
if [ "${#SETUPS[@]}" -eq 0 ]; then
    echo "  NESSUN Setup trovato — pygame non ancora estratto?"; exit 1
fi
for S in "${SETUPS[@]}"; do
    echo "  $S"
    if grep -q "simd_blitters" "$S"; then
        echo "    gia patchato"
    else
        sed -i "s|^surface src_c/surface.c src_c/alphablit.c src_c/surface_fill.c|surface src_c/surface.c src_c/alphablit.c src_c/surface_fill.c $ADD|" "$S"
        echo "    PATCHED"
    fi
    grep "^surface" "$S"
done

echo
echo "=== 2) Clean artefatti pygame mal-linkati (forza re-link) ==="
for d in "$PLATFORM"/build-*/build/other_builds/pygame/*__ndk_target_24/pygame; do
    [ -d "$d" ] || continue
    rm -rf "$d/build/temp.linux-"* "$d/build/lib.linux-"* 2>/dev/null || true
done
rm -rf "$PLATFORM"/build-*/build/python-installs/lineventure/*/pygame 2>/dev/null || true
echo "  cleaned"
echo
echo "PATCH_OK"
