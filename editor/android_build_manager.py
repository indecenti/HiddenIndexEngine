"""
editor/android_build_manager.py

Entry point per il subprocess di compilazione APK Android.
Lancia build_game_apk() (Buildozer via WSL) e gestisce lo stato via file JSON
condiviso con la UI (editor/android_build_ui.py).

Wrapper sottile su editor/build_common.run_managed_build, simmetrico a
editor/build_manager.py (pipeline EXE). Differenze parametrizzate: timeout
globale piu' lungo, watchdog a 6 minuti (la cross-compile ha fasi lente senza
progress update), campi extra apk_path/apk_size_mb nel file di stato.

Uso:
    python editor/android_build_manager.py <game_id> <version> <build_dir> \
        [<status_file>] [--release]
"""

import sys
from pathlib import Path
from typing import Callable

# Aggiungi la root del progetto al PYTHONPATH se eseguito da CLI
_local_root = Path(__file__).resolve().parent.parent
if str(_local_root) not in sys.path:
    sys.path.insert(0, str(_local_root))

from engine.utils import setup_logging, get_logger

# Re-export di compatibilita': storicamente definiti in questo modulo.
from editor.build_common import BuildWatchdog, update_status, run_managed_build  # noqa: F401
from editor.android_build_system import (
    build_game_apk,
    BUILDOZER_FIRST_BUILD_TIMEOUT,
)

logger = get_logger("android_build_manager")

# Timeout globale = first-build * 1.3 per cleanup
GLOBAL_TIMEOUT_FACTOR = 1.3
GLOBAL_BUILD_TIMEOUT = int(BUILDOZER_FIRST_BUILD_TIMEOUT * GLOBAL_TIMEOUT_FACTOR)

# Inattivita' massima prima di considerare la build bloccata (la cross-compile
# puo' essere lenta in certi punti del Python core, soprattutto su HDD)
WATCHDOG_INACTIVITY_TIMEOUT = 360  # 6 minuti
WATCHDOG_CHECK_INTERVAL = 5


def run_apk_build(
    game_id: str,
    version: str,
    build_dir: str,
    status_file: str,
    release: bool = False,
) -> int:
    """
    Esegue la build APK con timeout globale e watchdog.

    Args:
        game_id: ID del gioco
        version: Versione del gioco
        build_dir: Directory di output
        status_file: File JSON per lo stato del build
        release: Se True, build release firmata (default: debug)

    Returns:
        Exit code (0 = successo, 1 = errore/timeout).
    """
    setup_logging()
    logger.info(
        f"[Android Build Manager] game_id={game_id}, version={version}, "
        f"release={release}, timeout={GLOBAL_BUILD_TIMEOUT}s"
    )
    logger.info(f"[Paths] build_dir={build_dir}, status_file={status_file}")

    def build_fn(progress_callback: Callable[[float, str], None]) -> dict:
        return build_game_apk(
            game_id=game_id,
            output_dir=Path(build_dir),
            version=version,
            progress_callback=progress_callback,
            release=release,
        )

    return run_managed_build(
        build_fn=build_fn,
        status_file=Path(status_file),
        global_timeout=GLOBAL_BUILD_TIMEOUT,
        watchdog_timeout=WATCHDOG_INACTIVITY_TIMEOUT,
        watchdog_check_interval=WATCHDOG_CHECK_INTERVAL,
        timeout_error_fmt=(
            "TIMEOUT GLOBALE: build APK superato {timeout}s. Progresso a {progress}%"
        ),
        success_step_fn=lambda result: f"✓ APK pronto ({result['apk_size_mb']:.1f} MB)",
        failure_step="✗ Errore build APK",
        timeout_step="✗ TIMEOUT Build APK",
        extra_defaults={"apk_path": None, "apk_size_mb": None},
        result_extra_fn=lambda result: {
            "apk_path": result.get("apk_path"),
            "apk_size_mb": result.get("apk_size_mb"),
        },
        log=logger,
    )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Hidden Index Engine - Android APK Build Manager")
    parser.add_argument("game_id", help="ID del gioco (es. LineVenture)")
    parser.add_argument("version", help="Versione del gioco (es. 1.0)")
    parser.add_argument("build_dir", help="Directory di output (es. build/LineVenture/1.0/)")
    parser.add_argument("status_file", nargs="?", help="File di stato JSON (opzionale)")
    parser.add_argument(
        "--release", action="store_true",
        help="Build release firmata (default: debug)",
    )

    args = parser.parse_args()
    status_file = args.status_file or str(Path(args.build_dir) / "status.json")

    exit_code = run_apk_build(
        game_id=args.game_id,
        version=args.version,
        build_dir=args.build_dir,
        status_file=status_file,
        release=args.release,
    )
    sys.exit(exit_code)
