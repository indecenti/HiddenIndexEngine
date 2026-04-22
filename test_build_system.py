#!/usr/bin/env python3
"""
Test script per validare il sistema di build con timeout e logging.

Uso:
    python test_build_system.py <game_id> [--dry-run]

Esempio:
    python test_build_system.py villa_segreta
    python test_build_system.py villa_segreta --dry-run
"""

import sys
import argparse
import json
import time
from pathlib import Path

# Assicura PYTHONPATH
sys.path.insert(0, str(Path(__file__).parent))

from engine.utils import setup_logging, get_logger, get_base_path
from editor.build_system import build_game, _verify_pyinstaller_available

logger = get_logger("test_build_system")


def test_pyinstaller_available():
    """Test 1: Verifica che PyInstaller sia disponibile."""
    print("\n" + "=" * 60)
    print("TEST 1: Verifica PyInstaller disponibilità")
    print("=" * 60)
    try:
        pyinstaller_cmd = _verify_pyinstaller_available()
        print(f"✅ PASS: PyInstaller trovato: {pyinstaller_cmd}")
        return True
    except RuntimeError as e:
        print(f"❌ FAIL: {e}")
        return False


def test_game_exists(game_id: str):
    """Test 2: Verifica che il gioco esista."""
    print("\n" + "=" * 60)
    print(f"TEST 2: Verifica gioco '{game_id}' esiste")
    print("=" * 60)
    base_path = get_base_path()
    game_path = base_path / "games" / game_id
    game_config = game_path / "game_config.json"

    if game_path.exists() and game_config.exists():
        try:
            with open(game_config) as f:
                cfg = json.load(f)
            print(f"✅ PASS: Gioco trovato")
            print(f"   - Path: {game_path}")
            print(f"   - Title: {cfg.get('title_key', 'N/A')}")
            print(f"   - Version: {cfg.get('version', '1.0')}")
            return True
        except Exception as e:
            print(f"❌ FAIL: Errore parsing config: {e}")
            return False
    else:
        print(f"❌ FAIL: Gioco non trovato")
        print(f"   - Path atteso: {game_path}")
        print(f"   - Config atteso: {game_config}")
        return False


def test_build(game_id: str, output_dir: Path, dry_run: bool = False):
    """Test 3: Esegui il build completo."""
    print("\n" + "=" * 60)
    print(f"TEST 3: Build completo di '{game_id}'")
    print("=" * 60)

    if dry_run:
        print("⚠️  DRY RUN: Non eseguirò il build effettivo")
        print(f"   - Output dir: {output_dir}")
        print(f"   - Log file: saves/engine.log")
        print("   - Per eseguire realmente: python test_build_system.py {game_id}")
        return True

    output_dir.mkdir(parents=True, exist_ok=True)

    # Progress callback
    progress_data = {"start": time.time(), "last_update": time.time()}

    def progress_callback(progress: float, step: str):
        elapsed = time.time() - progress_data["start"]
        print(f"[{progress:5.0f}%] [{elapsed:6.1f}s] {step[:70]}")
        progress_data["last_update"] = time.time()

    try:
        print(f"Inizio build... (logging in saves/engine.log)")
        result = build_game(game_id, output_dir, progress_callback=progress_callback)

        if result["success"]:
            elapsed = time.time() - progress_data["start"]
            print(f"\n✅ PASS: Build completato in {elapsed:.1f}s")
            print(f"   - EXE: {result['exe_path']}")
            print(f"   - ZIP: {result['zip_path']}")
            print(f"   - Step totali: {len(result['steps_log'])}")
            return True
        else:
            print(f"\n❌ FAIL: Build fallito")
            print(f"   - Errore: {result['error_msg']}")
            print(f"   - Step completati: {len(result['steps_log'])}")
            if result["steps_log"]:
                print(f"\n   Log ultimi step:")
                for line in result["steps_log"][-5:]:
                    print(f"     {line}")
            return False

    except Exception as e:
        print(f"\n❌ FAIL: Eccezione durante build")
        print(f"   - {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Test sistema di build con timeout e logging"
    )
    parser.add_argument("game_id", help="ID del gioco (es. villa_segreta)")
    parser.add_argument("--dry-run", action="store_true", help="Simula il build senza eseguirlo")

    args = parser.parse_args()

    # Setup logging
    setup_logging()

    print("\n" + "=" * 60)
    print("TEST SUITE: Sistema Build PyInstaller")
    print("=" * 60)
    print(f"Data: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Game ID: {args.game_id}")
    print(f"Dry Run: {'SÌ' if args.dry_run else 'NO'}")

    # Esegui test
    results = {}

    results["pyinstaller"] = test_pyinstaller_available()
    results["game"] = test_game_exists(args.game_id)

    if results["game"]:  # Solo se il gioco esiste
        base_path = get_base_path()
        output_dir = base_path / "build_test" / args.game_id / "1.0"
        results["build"] = test_build(args.game_id, output_dir, dry_run=args.dry_run)
    else:
        print("\n⏭️  Saltando TEST 3 (gioco non esiste)")
        results["build"] = False

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    for test_name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status}: {test_name}")

    all_passed = all(results.values())
    print("\n" + ("✅ TUTTI I TEST PASSATI" if all_passed else "❌ ALCUNI TEST FALLITI"))

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
