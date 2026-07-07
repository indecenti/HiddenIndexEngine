"""
editor/build_manager.py

Entry point per il subprocess di compilazione EXE desktop.
Lancia build_game() (PyInstaller) e gestisce il progresso via file JSON
condiviso con la UI (editor/build_ui.py).

Wrapper sottile su editor/build_common.run_managed_build: watchdog, callback
di progresso con timeout globale e scrittura dello stato finale sono comuni
alla pipeline Android (editor/android_build_manager.py).

Uso:
    python editor/build_manager.py <game_id> <version> <build_dir> [<status_file>] [--no-zip]
"""

import sys
from pathlib import Path
from typing import Callable

# Assicura che la root del progetto sia nel PYTHONPATH se eseguito da riga di comando
_local_root = Path(__file__).resolve().parent.parent
if str(_local_root) not in sys.path:
    sys.path.insert(0, str(_local_root))

from engine.utils import setup_logging, get_logger

# Re-export di compatibilita': storicamente definiti in questo modulo.
from editor.build_common import BuildWatchdog, update_status, run_managed_build  # noqa: F401
from editor.build_system import build_game, PYINSTALLER_TIMEOUT

logger = get_logger("build_manager")

# Timeout globale (50% in piu' del PYINSTALLER_TIMEOUT per permettere cleanup)
GLOBAL_TIMEOUT_FACTOR = 1.5
GLOBAL_BUILD_TIMEOUT = int(PYINSTALLER_TIMEOUT * GLOBAL_TIMEOUT_FACTOR)

# Inattivita' massima prima che il watchdog dichiari il build bloccato.
WATCHDOG_INACTIVITY_TIMEOUT = 120  # 2 minuti
WATCHDOG_CHECK_INTERVAL = 5


def run_build(
    game_id: str,
    version: str,
    build_dir: str,
    status_file: str,
    create_zip: bool = True,
) -> int:
    """
    Esegue il build del gioco con timeout globale e watchdog.

    Args:
        game_id: ID del gioco
        version: Versione del gioco
        build_dir: Directory di output
        status_file: File JSON per lo stato del build
        create_zip: Se creare o meno l'archivio ZIP finale

    Returns:
        Exit code (0 = successo, 1 = errore/timeout).
    """
    setup_logging()
    logger.debug(f"[Raw Args] {sys.argv}")
    logger.info(
        f"[Build Manager Start] game_id={game_id}, version={version}, "
        f"timeout={GLOBAL_BUILD_TIMEOUT}s"
    )
    logger.info(f"[Paths] build_dir={build_dir}, status_file={status_file}")
    logger.info(f"[Options] Creazione ZIP finale: {'ABILITATA' if create_zip else 'DISABILITATA'}")

    def build_fn(progress_callback: Callable[[float, str], None]) -> dict:
        return build_game(
            game_id,
            Path(build_dir),
            version,
            progress_callback=progress_callback,
            create_zip=create_zip,
        )

    return run_managed_build(
        build_fn=build_fn,
        status_file=Path(status_file),
        global_timeout=GLOBAL_BUILD_TIMEOUT,
        watchdog_timeout=WATCHDOG_INACTIVITY_TIMEOUT,
        watchdog_check_interval=WATCHDOG_CHECK_INTERVAL,
        timeout_error_fmt=(
            "TIMEOUT GLOBALE: Build superato {timeout}s. Progresso fermo a {progress}%"
        ),
        success_step_fn=lambda result: "✓ Build completato!",
        failure_step="✗ Errore build",
        timeout_step="✗ TIMEOUT Build",
        extra_defaults={"zip_path": None},
        result_extra_fn=lambda result: {"zip_path": result.get("zip_path")},
        log=logger,
    )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Hidden Index Engine Build Manager")
    parser.add_argument("game_id", help="ID del gioco")
    parser.add_argument("version", help="Versione del gioco")
    parser.add_argument("build_dir", help="Directory di output")
    parser.add_argument("status_file", nargs="?", help="File di stato JSON")
    parser.add_argument("--no-zip", action="store_true", help="Salta la creazione dello ZIP")

    args = parser.parse_args()

    # Se status_file non e' fornito, usa il default
    status_file = args.status_file or str(Path(args.build_dir) / "status.json")

    exit_code = run_build(
        args.game_id, args.version, args.build_dir, status_file,
        create_zip=not args.no_zip,
    )
    sys.exit(exit_code)
