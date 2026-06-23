"""
editor/android_build_manager.py

Entry point per il subprocess di compilazione APK Android.
Lancia build_game_apk() e gestisce lo stato via file JSON condiviso.

Simmetrico a editor/build_manager.py (che fa lo stesso per la build EXE PyInstaller).

Uso:
    python editor/android_build_manager.py <game_id> <version> <build_dir> [<status_file>] [--release]
"""

import json
import sys
import time
import atexit
import threading
from pathlib import Path
from typing import Optional

# Aggiungi la root del progetto al PYTHONPATH se eseguito da CLI
_local_root = Path(__file__).resolve().parent.parent
if str(_local_root) not in sys.path:
    sys.path.insert(0, str(_local_root))

from engine.utils import setup_logging, get_logger
from editor.android_build_system import (
    build_game_apk,
    BUILDOZER_FIRST_BUILD_TIMEOUT,
)

logger = get_logger("android_build_manager")

# Timeout globale = first-build * 1.3 per cleanup
GLOBAL_BUILD_TIMEOUT = int(BUILDOZER_FIRST_BUILD_TIMEOUT * 1.3)

# Inattività massima prima di considerare la build bloccata (cross-compile può
# essere lento in certi punti del Python core, soprattutto su HDD)
WATCHDOG_INACTIVITY_TIMEOUT = 360  # 6 minuti


def update_status(
    status_file: Path,
    progress: int,
    step: str,
    log_lines: list,
    success: Optional[bool] = None,
    error_msg: Optional[str] = None,
    apk_path: Optional[str] = None,
    apk_size_mb: Optional[float] = None,
) -> None:
    status = {
        "progress": progress,
        "step": step,
        "log": log_lines,
        "success": success,
        "error_msg": error_msg,
        "apk_path": apk_path,
        "apk_size_mb": apk_size_mb,
        "timestamp": time.time(),
    }
    try:
        with open(status_file, "w", encoding="utf-8") as f:
            json.dump(status, f, indent=2)
    except Exception as e:
        logger.error(f"Errore aggiornamento status file: {e}")


class BuildWatchdog(threading.Thread):
    """
    Monitora il file di stato. Se il progress non avanza per troppo tempo,
    segnala il blocco scrivendo error_msg.

    Identico in spirito a quello di build_manager.py, ma con timeout più lungo
    (la cross-compile di Python ARM ha fasi lunghe senza progress updates).
    """

    def __init__(self, status_file: Path, timeout: int, check_interval: int = 10):
        super().__init__(daemon=True)
        self.status_file = status_file
        self.timeout = timeout
        self.check_interval = check_interval
        self.last_progress = 0
        self.last_update_time = time.time()
        self.should_stop = False

    def run(self) -> None:
        logger.info(f"[Watchdog] Avviato (timeout inattività: {self.timeout}s)")
        while not self.should_stop:
            try:
                if not self.status_file.exists():
                    time.sleep(self.check_interval)
                    continue
                with open(self.status_file, "r", encoding="utf-8") as f:
                    status = json.load(f)
                current_progress = status.get("progress", 0)
                now = time.time()

                if current_progress != self.last_progress:
                    self.last_progress = current_progress
                    self.last_update_time = now
                    logger.debug(f"[Watchdog] Progresso aggiornato a {current_progress}%")

                inactive = now - self.last_update_time
                if inactive > self.timeout and status.get("success") is None:
                    logger.error(
                        f"✗ [Watchdog] Build bloccato! "
                        f"Progresso fermo a {current_progress}% per {inactive:.0f}s"
                    )
                    status["error_msg"] = (
                        f"Build bloccato: progresso fermo a {current_progress}% "
                        f"per {inactive:.0f}s (timeout: {self.timeout}s)"
                    )
                    # Finalizza il fallimento, altrimenti la UI resta in attesa fino
                    # al proprio POLLING_TIMEOUT (90 min) ignorando lo stallo.
                    status["success"] = False
                    with open(self.status_file, "w", encoding="utf-8") as f:
                        json.dump(status, f, indent=2)
            except Exception as e:
                logger.debug(f"[Watchdog] Errore monitoraggio: {e}")
            time.sleep(self.check_interval)

    def stop(self) -> None:
        self.should_stop = True


def run_apk_build(
    game_id: str,
    version: str,
    build_dir: str,
    status_file: str,
    release: bool = False,
) -> int:
    setup_logging()
    logger.info(
        f"[Android Build Manager] game_id={game_id}, version={version}, "
        f"release={release}, timeout={GLOBAL_BUILD_TIMEOUT}s"
    )
    logger.info(f"[Paths] build_dir={build_dir}, status_file={status_file}")

    build_dir_path = Path(build_dir)
    status_file_path = Path(status_file)
    build_start = time.time()

    watchdog = BuildWatchdog(
        status_file_path,
        timeout=WATCHDOG_INACTIVITY_TIMEOUT,
        check_interval=5,
    )
    watchdog.start()

    def stop_watchdog() -> None:
        watchdog.stop()
        watchdog.join(timeout=2)

    atexit.register(stop_watchdog)

    steps_log: list[str] = []

    def progress_callback(progress: float, step: str) -> None:
        elapsed = time.time() - build_start
        if elapsed > GLOBAL_BUILD_TIMEOUT:
            raise RuntimeError(
                f"TIMEOUT GLOBALE: build APK superato {GLOBAL_BUILD_TIMEOUT}s. "
                f"Progresso a {progress}%"
            )
        steps_log.append(f"[{progress:.0f}%] {step}")
        update_status(
            status_file_path,
            progress=int(progress),
            step=step,
            log_lines=steps_log,
        )

    try:
        result = build_game_apk(
            game_id=game_id,
            output_dir=build_dir_path,
            version=version,
            progress_callback=progress_callback,
            release=release,
        )
        elapsed = time.time() - build_start

        if result["success"]:
            logger.info(f"[Build Success] ✓ APK in {elapsed/60:.1f} min: {result['apk_path']}")
            update_status(
                status_file_path,
                progress=100,
                step=f"✓ APK pronto ({result['apk_size_mb']:.1f} MB)",
                log_lines=result["steps_log"],
                success=True,
                apk_path=result["apk_path"],
                apk_size_mb=result["apk_size_mb"],
            )
            return 0
        else:
            logger.error(f"[Build Failure] ✗ {elapsed/60:.1f} min: {result['error_msg']}")
            update_status(
                status_file_path,
                progress=100,
                step="✗ Errore build APK",
                log_lines=result["steps_log"],
                success=False,
                error_msg=result["error_msg"],
            )
            return 1

    except RuntimeError as e:
        elapsed = time.time() - build_start
        logger.error(f"[Build Timeout] ✗ {e} ({elapsed/60:.1f} min)")
        update_status(
            status_file_path,
            progress=100,
            step="✗ TIMEOUT Build APK",
            log_lines=steps_log,
            success=False,
            error_msg=str(e),
        )
        return 1
    finally:
        stop_watchdog()


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
