#!/bin/bash
# scripts/inspect_apk.sh — Ispeziona l'APK di LineVenture

set -e

APK=$(ls /root/apk_lineventure/bin/*.apk 2>/dev/null | head -1)
if [ -z "$APK" ]; then
    echo "Nessun APK trovato in /root/apk_lineventure/bin/"
    exit 1
fi

AAPT=/root/android-sdk/build-tools/35.0.0/aapt2

echo "=== APK FILE ==="
ls -lh "$APK"
echo

echo "=== AAPT2 BADGING ==="
"$AAPT" dump badging "$APK" 2>&1 | head -25
echo

echo "=== ARCH-SPECIFIC .so libs ==="
unzip -l "$APK" | grep -E '\.so$' | awk '{printf "%10d  %s\n", $1, $4}' | sort -k1 -n -r | head -15
echo

echo "=== ASSETS SIZE BREAKDOWN ==="
unzip -l "$APK" | awk '
$4 ~ /^assets\// {
    sum += $1; count++
    # Categorizza per top-level dir
    split($4, parts, "/")
    if (length(parts) >= 3) {
        key = parts[2] "/" parts[3]
    } else {
        key = parts[2]
    }
    by_cat[key] += $1
}
END {
    printf "TOTAL: %d files, %.1f MB\n\n", count, sum/1024/1024
    printf "By category (>1MB):\n"
    for (k in by_cat) {
        mb = by_cat[k] / 1024 / 1024
        if (mb > 1.0) {
            printf "  %8.1f MB  %s\n", mb, k
        }
    }
}' | sort -k1 -n -r
echo

echo "=== APK TOTAL BREAKDOWN ==="
unzip -l "$APK" | tail -1
echo

echo "=== TOP 20 LARGEST FILES IN APK ==="
unzip -l "$APK" | awk '{printf "%10d  %s\n", $1, $4}' | sort -n -r | head -20
