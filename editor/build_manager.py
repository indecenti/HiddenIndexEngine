"""
editor/build_manager.py

Entry point per il subprocess di compilazione.
Lancia PyInstaller e gestisce il progresso via file JSON condiviso.

Uso:
    python editor/build_manager.py <game_id> <version> <build_dir> <status_file>
"""

import json
import sys
import threading
import time
import atexit
from pathlib import Path
from typing import Optional

# Assicura che la root del progetto sia nel PYTHONPATH se eseguito da riga di comando
_local_root = Path(__file__).resolve().parent.parent
if str(_local_root) not in sys.path:
    sys.path.insert(0, str(_local_root))

from engine.utils import setup_logging, get_logger, get_base_path
_project_root = get_base_path()

from editor.build_system import build_game, PYINSTALLER_TIMEOUT

logger = get_logger("build_manager")

# Timeout globale (30% più del PYINSTALLER_TIMEOUT per permettere cleanup)
GLOBAL_BUILD_TIMEOUT = int(PYINSTALLER_TIMEOUT * 1.5)


def update_status(
    status_file: Path,
    progress: int,
    step: str,
    log_lines: list,
    success: Optional[bool] = None,
    error_msg: Optional[str] = None,
    zip_path: Optional[str] = None,
):
    """Aggiorna il file di stato JSON."""
    status = {
        "progress": progress,
        "step": step,
        "log": log_lines,
        "success": success,
        "error_msg": error_msg,
        "zip_path": zip_path,
        "timestamp": time.time(),  # Per rilevare blocchi nel polling
    }
    try:
        with open(status_file, "w", encoding="utf-8") as f:
            json.dump(status, f, indent=2)
    except Exception as e:
        logger.error(f"Errore aggiornamento status file: {e}")


class BuildWatchdog(threading.Thread):
    """
    Thread che monitora se il build è in progresso.
    Se il progresso non avanza per troppo tempo, segnala il blocco.
    """

    def __init__(self, status_file: Path, timeout: int, check_interval: int = 10):
        """
        Args:
            status_file: File JSON di stato
            timeout: Secondi di inattività prima di considerare il build bloccato
            check_interval: Secondi tra i controlli
        """
        super().__init__(daemon=True)
        self.status_file = status_file
        self.timeout = timeout
        self.check_interval = check_interval
        self.last_progress = 0
        self.last_update_time = time.time()
        self.should_stop = False

    def run(self):
        """Monitora il file di stato."""
        logger.info(f"[Watchdog] Avviato (timeout inattività: {self.timeout}s)")

        while not self.should_stop:
            try:
                if not self.status_file.exists():
                    time.sleep(self.check_interval)
                    continue

                with open(self.status_file, "r", encoding="utf-8") as f:
                    status = json.load(f)

                current_progress = status.get("progress", 0)
                timestamp = status.get("timestamp", 0)
                current_time = time.time()

                # Se il progresso è cambiato, reset il timer
                if current_progress != self.last_progress:
                    self.last_progress = current_progress
                    self.last_update_time = current_time
                    logger.debug(f"[Watchdog] Progresso aggiornato a {current_progress}%")

                # Verifica inattività
                inactive_time = current_time - self.last_update_time
                if inactive_time > self.timeout and status.get("success") is None:
                    logger.error(
                        f"✗ [Watchdog] Build bloccato! "
                        f"Progresso fermo a {current_progress}% per {inactive_time:.0f}s"
                    )
                    # Segnala il blocco nel status
                    status["error_msg"] = (
                        f"Build bloccato: progresso fermo a {current_progress}% "
                        f"per {inactive_time:.0f}s (timeout: {self.timeout}s)"
                    )
                    # Finalizza il fallimento, altrimenti la UI resta in attesa
                    # (si sblocca solo al proprio timeout) ignorando lo stallo.
                    status["success"] = False
                    with open(self.status_file, "w", encoding="utf-8") as f:
                        json.dump(status, f, indent=2)

            except Exception as e:
                logger.debug(f"[Watchdog] Errore monitoraggio: {e}")

            time.sleep(self.check_interval)

    def stop(self):
        """Ferma il watchdog."""
        self.should_stop = True


def run_build(game_id: str, version: str, build_dir: str, status_file: str, create_zip: bool = True):
    """
    Esegue il build del gioco con timeout globale e watchdog.

    Args:
        game_id: ID del gioco
        version: Versione del gioco
        build_dir: Directory di output
        status_file: File JSON per lo stato del build
        create_zip: Se creare o meno l'archivio ZIP finale
    """
    setup_logging()
    logger.debug(f"[Raw Args] {sys.argv}")
    build_start_time = time.time()
    logger.info(f"[Build Manager Start] game_id={game_id}, version={version}, timeout={GLOBAL_BUILD_TIMEOUT}s")
    logger.info(f"[Paths] build_dir={build_dir}, status_file={status_file}")
    logger.info(f"[Options] Creazione ZIP finale: {'ABILITATA' if create_zip else 'DISABILITATA'}")

    build_dir_path = Path(build_dir)
    status_file_path = Path(status_file)
    build_start_timestamp = time.time()

    # Avvia watchdog
    watchdog = BuildWatchdog(
        status_file_path,
        timeout=120,  # 2 minuti di inattività = blocco
        check_interval=5
    )
    watchdog.start()

    # Cleanup per il watchdog
    def stop_watchdog():
        watchdog.stop()
        watchdog.join(timeout=2)

    atexit.register(stop_watchdog)

    # Callback per aggiornare il progresso
    steps_log = []

    def progress_callback(progress: float, step: str):
        """Callback dalla build_system per aggiornare il progresso."""
        # Verifica timeout globale
        elapsed = time.time() - build_start_timestamp
        if elapsed > GLOBAL_BUILD_TIMEOUT:
            raise RuntimeError(
                f"TIMEOUT GLOBALE: Build superato {GLOBAL_BUILD_TIMEOUT}s. "
                f"Progresso fermo a {progress}%"
            )

        steps_log.append(f"[{progress:.0f}%] {step}")
        update_status(
            status_file_path,
            progress=int(progress),
            step=step,
            log_lines=steps_log,
        )
        logger.debug(f"[Progress] {progress:.0f}% ({elapsed:.1f}s) - {step}")

    # Esegue il build
    try:
        logger.info("[Build] Avvio build_game()...")
        result = build_game(
            game_id, build_dir_path, version, 
            progress_callback=progress_callback,
            create_zip=create_zip
        )
        elapsed = time.time() - build_start_time

        # Aggiorna status file con risultato finale
        if result["success"]:
            logger.info(f"[Build Success] ✓ Build completato in {elapsed:.1f}s!")
            if result['zip_path']:
                logger.info(f"[Build Success] ZIP: {result['zip_path']}")
            
            update_status(
                status_file_path,
                progress=100,
                step="✓ Build completato!",
                log_lines=result["steps_log"],
                success=True,
                zip_path=result["zip_path"],
            )
            return 0
        else:
            logger.error(f"[Build Failure] ✗ Build fallito in {elapsed:.1f}s: {result['error_msg']}")
            update_status(
                status_file_path,
                progress=100,
                step="✗ Errore build",
                log_lines=result["steps_log"],
                success=False,
                error_msg=result["error_msg"],
            )
            return 1

    except RuntimeError as e:
        elapsed = time.time() - build_start_time
        logger.error(f"[Build Timeout] ✗ {e} (elapsed: {elapsed:.1f}s)")
        update_status(
            status_file_path,
            progress=100,
            step="✗ TIMEOUT Build",
            log_lines=steps_log,
            success=False,
            error_msg=str(e),
        )
        return 1

    finally:
        stop_watchdog()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Hidden Index Engine Build Manager")
    parser.add_argument("game_id", help="ID del gioco")
    parser.add_argument("version", help="Versione del gioco")
    parser.add_argument("build_dir", help="Directory di output")
    parser.add_argument("status_file", nargs="?", help="File di stato JSON")
    parser.add_argument("--no-zip", action="store_true", help="Salta la creazione dello ZIP")
    
    args = parser.parse_args()
    
    # Se status_file non è fornito, usa il default
    status_file = args.status_file or str(Path(args.build_dir) / "status.json")

    exit_code = run_build(
        args.game_id, args.version, args.build_dir, status_file, 
        create_zip=not args.no_zip
    )
    sys.exit(exit_code)
