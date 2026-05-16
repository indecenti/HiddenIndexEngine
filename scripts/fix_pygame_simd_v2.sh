#!/bin/bash
# scripts/fix_pygame_simd_v2.sh
#
# Corregge la patch precedente che aveva inventato due file inesistenti
# (simd_surface_fill_*.c). I file SIMD effettivi di pygame 2.6.1 sono
# solo simd_blitters_sse2.c e simd_blitters_avx2.c.

set -e

PG_BUILD=/root/apk_lineventure/.buildozer/android/platform/build-arm64-v8a_armeabi-v7a/build/other_builds/pygame

echo "=== 1) Rewriting surface line correctly ==="
for ARCH_DIR in $PG_BUILD/*__ndk_target_24; do
    SETUP="$ARCH_DIR/pygame/buildconfig/Setup.Android.SDL2.in"
    if [ -f "$SETUP" ]; then
        echo "  $SETUP"
        # Rimuove i file inesistenti che avevo erroneamente aggiunto
        sed -i 's| src_c/simd_surface_fill_avx2.c||g' "$SETUP"
        sed -i 's| src_c/simd_surface_fill_sse2.c||g' "$SETUP"
        # Mostra risultato
        grep "^surface" "$SETUP"
    fi
done

echo
echo "=== 2) Clean build artifacts again ==="
for ARCH_DIR in $PG_BUILD/*__ndk_target_24; do
    PYG="$ARCH_DIR/pygame"
    if [ -d "$PYG" ]; then
        rm -rf "$PYG/build/temp.linux-"* 2>/dev/null || true
        rm -rf "$PYG/build/lib.linux-"* 2>/dev/null || true
    fi
done
rm -rf /root/apk_lineventure/.buildozer/android/platform/build-arm64-v8a_armeabi-v7a/build/python-installs/lineventure/*/pygame 2>/dev/null || true
echo "  cleaned"

echo
echo "PATCH_OK"
