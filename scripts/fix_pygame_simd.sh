#!/bin/bash
# scripts/fix_pygame_simd.sh
#
# Fix pygame 2.6.1 cross-compile per ARM: aggiunge simd_blitters_sse2.c e
# simd_blitters_avx2.c come dipendenze di `surface` in Setup.Android.SDL2.in.
# I file SIMD usano #ifdef per generare stub vuoti su non-x86, ma il symbol
# `alphablit_alpha_sse2_argb_surf_alpha` DEVE essere definito comunque,
# altrimenti surface.so ha riferimenti non risolti → ImportError al boot.

set -e

PG_BUILD=/root/apk_lineventure/.buildozer/android/platform/build-arm64-v8a_armeabi-v7a/build/other_builds/pygame

echo "=== 1) Patch Setup.Android.SDL2.in for both archs ==="
for ARCH_DIR in $PG_BUILD/*__ndk_target_24; do
    SETUP="$ARCH_DIR/pygame/buildconfig/Setup.Android.SDL2.in"
    if [ -f "$SETUP" ]; then
        echo "  Patching: $SETUP"
        # Idempotente: solo se la linea attuale NON contiene simd_blitters
        if ! grep -q "simd_blitters" "$SETUP"; then
            sed -i 's|^surface src_c/surface.c src_c/alphablit.c src_c/surface_fill.c|surface src_c/surface.c src_c/alphablit.c src_c/surface_fill.c src_c/simd_blitters_sse2.c src_c/simd_blitters_avx2.c src_c/simd_surface_fill_avx2.c src_c/simd_surface_fill_sse2.c|' "$SETUP"
            echo "    PATCHED"
        else
            echo "    already patched, skip"
        fi
        # Show resulting line
        grep "^surface" "$SETUP"
    fi
done

echo
echo "=== 2) Clean previous bad build artifacts (force re-link) ==="
for ARCH_DIR in $PG_BUILD/*__ndk_target_24; do
    PYG="$ARCH_DIR/pygame"
    if [ -d "$PYG" ]; then
        # Cancella SO mal-linkati e oggetti, NON il source
        rm -rf "$PYG/build/temp.linux-"* 2>/dev/null || true
        rm -rf "$PYG/build/lib.linux-"* 2>/dev/null || true
        echo "  cleaned: $PYG/build/{temp,lib}.linux-*"
    fi
done

# Cancella anche pygame installato (forza reinstall dal build appena fatto)
rm -rf /root/apk_lineventure/.buildozer/android/platform/build-arm64-v8a_armeabi-v7a/build/python-installs/lineventure/arm64-v8a/pygame 2>/dev/null || true
rm -rf /root/apk_lineventure/.buildozer/android/platform/build-arm64-v8a_armeabi-v7a/build/python-installs/lineventure/armeabi-v7a/pygame 2>/dev/null || true
echo "  cleaned: python-installs/*/pygame"

echo
echo "PATCH_OK"
