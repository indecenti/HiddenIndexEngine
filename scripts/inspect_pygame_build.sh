#!/bin/bash
# Ispeziona la build di pygame ARM per capire perché manca il symbol
# alphablit_alpha_sse2_argb_surf_alpha
set -e

BD=/root/apk_lineventure/.buildozer/android/platform/build-arm64-v8a_armeabi-v7a/build/other_builds/pygame/arm64-v8a__ndk_target_24/pygame

echo "=== pygame build dir: $BD ==="
ls -d "$BD" 2>&1

echo
echo "=== SIMD source files ==="
ls "$BD/src_c/simd_blitters"* 2>&1

echo
echo "=== Setup.Android.SDL2.in ==="
cat "$BD/buildconfig/Setup.Android.SDL2.in" 2>&1 | head -50

echo
echo "=== Where is alphablit_alpha_sse2_argb_surf_alpha defined? ==="
grep -rn "alphablit_alpha_sse2_argb_surf_alpha" "$BD/src_c/" 2>&1 | head -10

echo
echo "=== build/lib*.so files ==="
find "$BD/build" -name '*.so' 2>&1 | head -10

echo
echo "=== Built object files for simd ==="
find "$BD/build" -name '*simd*' 2>&1 | head -10
