#!/usr/bin/env python3
"""
Analizza il size di un pacchetto build per individuare file grandi o non necessari.

Uso:
    python analyze_package_size.py <game_id> [--show-all]

Esempio:
    python analyze_package_size.py villa_segreta
    python analyze_package_size.py villa_segreta --show-all
"""

import sys
import os
import argparse
from pathlib import Path
from collections import defaultdict

def format_size(size_bytes):
    """Formatta size in modo leggibile."""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


def analyze_directory(path: Path, show_all=False):
    """Analizza una directory e mostra file/cartelle grandi."""
    print(f"\n{'='*70}")
    print(f"Analisi: {path}")
    print(f"{'='*70}\n")

    if not path.exists():
        print(f"❌ Path non esiste: {path}")
        return

    # Raccogli informazioni
    file_types = defaultdict(int)  # ext -> count
    file_sizes = defaultdict(int)  # ext -> total size
    large_files = []  # (size, path)
    unused_files = []  # file patterns non necessari
    total_size = 0

    for fpath in path.rglob("*"):
        if not fpath.is_file():
            continue

        fsize = fpath.stat().st_size
        total_size += fsize
        large_files.append((fsize, fpath))

        # Estensione
        ext = fpath.suffix.lower() if fpath.suffix else "[no ext]"
        file_types[ext] += 1
        file_sizes[ext] += fsize

        # Rilevare file non necessari
        if any(pattern in fpath.name.lower() for pattern in [
            ".autosave", ".bak", ".tmp", ".log", ".pyc", ".pyo", "__pycache__",
            ".git", ".pytest_cache", "~", ".swp"
        ]):
            unused_files.append((fsize, fpath))

    # Ordinare large_files per size
    large_files.sort(reverse=True)

    # ── Report ──
    print(f"📊 SUMMARY")
    print(f"{'─'*70}")
    print(f"Total Size:    {format_size(total_size)}")
    print(f"Total Files:   {sum(file_types.values())}")
    print(f"Unused Files:  {len(unused_files)}")

    if unused_files:
        unused_size = sum(s for s, _ in unused_files)
        print(f"⚠️  Unused Size: {format_size(unused_size)} ({'REMOVE THIS!' if unused_size > 1024*1024 else 'minor'})")

    # ── File types ──
    print(f"\n📋 FILE TYPES (top 10)")
    print(f"{'─'*70}")
    print(f"{'Type':<15} {'Count':>8} {'Total Size':>15} {'%':>6}")
    print(f"{'-'*70}")

    sorted_ext = sorted(file_sizes.items(), key=lambda x: x[1], reverse=True)[:10]
    for ext, size in sorted_ext:
        count = file_types[ext]
        pct = 100 * size / total_size if total_size > 0 else 0
        print(f"{ext:<15} {count:>8} {format_size(size):>15} {pct:>5.1f}%")

    # ── Large files ──
    print(f"\n📦 LARGEST FILES (top 20)")
    print(f"{'─'*70}")
    print(f"{'Size':>12} {'Path':<55}")
    print(f"{'-'*70}")

    shown = 0
    for fsize, fpath in large_files[:20]:
        rel_path = fpath.relative_to(path)
        size_str = format_size(fsize)
        print(f"{size_str:>12} {str(rel_path):<55}")
        shown += 1

    # ── Unused files ──
    if unused_files:
        print(f"\n⚠️  UNUSED/TEMP FILES ({len(unused_files)} found)")
        print(f"{'─'*70}")
        print(f"{'Size':>12} {'Path':<55}")
        print(f"{'-'*70}")

        for fsize, fpath in unused_files[:20]:
            rel_path = fpath.relative_to(path)
            size_str = format_size(fsize)
            pattern = [p for p in [".autosave", ".bak", ".tmp", ".log", ".pyc", ".pyo", ".git", "~", ".swp"]
                       if p in fpath.name.lower()]
            marker = f"[{pattern[0] if pattern else '?'}]"
            print(f"{size_str:>12} {str(rel_path):<50} {marker}")

    # ── Directory breakdown ──
    print(f"\n📂 DIRECTORY BREAKDOWN (top 10)")
    print(f"{'─'*70}")
    print(f"{'Size':>12} {'Path':<55}")
    print(f"{'-'*70}")

    dir_sizes = defaultdict(int)
    for fpath in path.rglob("*"):
        if fpath.is_file():
            # Add to parent dir
            for parent in fpath.parents:
                if parent == path or parent.parent == path:
                    dir_sizes[parent.name] += fpath.stat().st_size

    sorted_dirs = sorted(dir_sizes.items(), key=lambda x: x[1], reverse=True)[:10]
    for dname, dsize in sorted_dirs:
        size_str = format_size(dsize)
        pct = 100 * dsize / total_size if total_size > 0 else 0
        print(f"{size_str:>12} {dname:<40} {pct:>5.1f}%")

    # ── Recommendations ──
    print(f"\n💡 RECOMMENDATIONS")
    print(f"{'─'*70}")

    issues = []

    if total_size > 500 * 1024 * 1024:
        issues.append(f"❌ Total size {format_size(total_size)} is too large (>500MB)")
        issues.append("   Likely cause: PyInstaller included assets as resources")
        issues.append("   Solution: Remove '-p temp_dir' from PyInstaller args")

    if unused_files:
        unused_size = sum(s for s, _ in unused_files)
        if unused_size > 1024 * 1024:
            issues.append(f"❌ {len(unused_files)} unused files totaling {format_size(unused_size)}")
            issues.append("   These should be excluded before packaging:")
            for _, fpath in unused_files[:5]:
                issues.append(f"     - {fpath.name}")
            if len(unused_files) > 5:
                issues.append(f"     ... and {len(unused_files)-5} more")

    # Check specific dangerous directories
    dangerous_dirs = ["build", "dist", ".git", "__pycache__", ".pytest_cache"]
    for ddir in dangerous_dirs:
        dpath = path / ddir
        if dpath.exists():
            dsize = sum(f.stat().st_size for f in dpath.rglob("*") if f.is_file())
            if dsize > 0:
                issues.append(f"❌ Directory '{ddir}' should not be in package: {format_size(dsize)}")

    if not issues:
        issues.append("✅ Package looks good!")
        issues.append(f"   Total size: {format_size(total_size)} (reasonable)")
        if unused_files:
            issues.append(f"   Note: {len(unused_files)} minor unused files (autosave, etc)")

    for issue in issues:
        print(issue)

    return total_size


def main():
    parser = argparse.ArgumentParser(description="Analizza size del pacchetto build")
    parser.add_argument("game_id", help="ID del gioco (es. villa_segreta)")
    parser.add_argument("--show-all", action="store_true", help="Mostra anche file piccoli")
    parser.add_argument("--build-dir", default="build", help="Cartella build (default: build/)")

    args = parser.parse_args()

    # Trova il build directory
    build_path = Path(args.build_dir) / args.game_id / "1.0"

    # Analizza EXE
    exe_path = build_path / "main.exe"
    if exe_path.exists():
        exe_size = exe_path.stat().st_size
        print(f"\n🔍 EXE Analysis")
        print(f"{'='*70}")
        print(f"main.exe: {format_size(exe_size)}")
        if exe_size > 500 * 1024 * 1024:
            print(f"❌ EXE TOO LARGE! (>500MB)")
            print(f"   This means PyInstaller included assets as resources!")
            print(f"   Check that '-p temp_dir' is removed from PyInstaller args")
        else:
            print(f"✅ EXE size OK")

    # Analizza ZIP
    zip_files = list(build_path.glob("*.zip"))
    if zip_files:
        for zpath in zip_files:
            zsize = zpath.stat().st_size
            print(f"\n🔍 ZIP Analysis")
            print(f"{'='*70}")
            print(f"{zpath.name}: {format_size(zsize)}")
            if zsize > 500 * 1024 * 1024:
                print(f"❌ ZIP TOO LARGE! (>500MB)")
                print(f"   Extract and analyze contents:")
                print(f"   unzip -l {zpath}")
            else:
                print(f"✅ ZIP size OK")

    # Analizza output_dir completo
    analyze_directory(build_path, show_all=args.show_all)


if __name__ == "__main__":
    main()
