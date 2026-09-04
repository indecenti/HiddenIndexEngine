"""
editor/build_common.py

Infrastruttura CONDIVISA tra la pipeline di build desktop (EXE via PyInstaller:
build_ui.py + build_manager.py + build_system.py) e quella Android (APK via
Buildozer/WSL: android_build_ui.py + android_build_manager.py +
android_build_system.py). Prima di questo modulo le due pipeline duplicavano
~90% del codice (audit editor, rilievo "grandi refactor").

Contenuto:
  - update_status():             scrittura del file JSON di stato UI <-> manager.
  - BuildWatchdog:               thread che rileva stalli di progresso e finalizza
                                 il fallimento nel file di stato.
  - run_subprocess_with_timeout(): esecuzione di un sottoprocesso di build
                                 (PyInstaller o Buildozer) con streaming output,
                                 marker di progresso, heartbeat, rilevamento
                                 stallo, timeout globale e cancel opzionale.
  - run_managed_build():         skeleton comune dei build manager (watchdog +
                                 progress callback con timeout globale + stato
                                 finale + exit code).
  - BaseBuildProgressWindow:     finestra Tkinter di progresso parametrizzata
                                 (polling status JSON, progress bar, log,
                                 annulla, apri cartella).

Contratto ESTERNO invariato rispetto ai moduli storici:
  - stesso schema del file di stato JSON (progress/step/log/success/error_msg/
    timestamp + campi extra specifici per pipeline: zip_path oppure
    apk_path/apk_size_mb);
  - stessi argomenti CLI dei manager e delle UI;
  - stessi output path.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from tkinter import Tk, Frame, Label, Button, IntVar, messagebox
from tkinter import ttk
from tkinter import scrolledtext
from typing import Callable, ClassVar, Optional

# Root del progetto nel PYTHONPATH: le UI vengono lanciate come script
# (sys.path[0] = editor/), senza questo fix gli import engine.* falliscono.
_local_root = Path(__file__).resolve().parent.parent
if str(_local_root) not in sys.path:
    sys.path.insert(0, str(_local_root))

from engine.utils import get_logger

logger = get_logger("build_common")

# ---------------------------------------------------------------------------
# Costanti condivise
# ---------------------------------------------------------------------------

# Return code del runner subprocess (convenzione GNU timeout per il 124).
RC_TIMEOUT = 124        # processo ucciso per timeout o stallo output
RC_CANCELED = 125       # processo ucciso su richiesta (cancel_event)
RC_EXCEPTION = 1        # eccezione interna durante l'esecuzione

SUBPROCESS_CHECK_INTERVAL = 2   # secondi tra i check del monitor subprocess
HEARTBEAT_INTERVAL = 30         # secondi tra gli heartbeat log/progress
GRACEFUL_WAIT = 30              # secondi di attesa terminazione dopo EOF stdout
KILL_WAIT = 5                   # secondi di attesa dopo un kill forzato
STAGE_LABEL_MAX_CHARS = 60      # troncamento etichetta stage derivata dalla linea
LOG_LINE_MAX_CHARS = 120        # troncamento linee di output nel log di debug

WATCHDOG_CHECK_INTERVAL = 10    # secondi default tra i check del watchdog
WATCHDOG_JOIN_TIMEOUT = 2       # secondi di attesa allo stop del watchdog

POLL_FIRST_DELAY_MS = 100       # ritardo del primo polling della UI
POLL_INTERVAL_MS = 500          # intervallo polling del file di stato nella UI
PROC_TERMINATE_WAIT = 5         # secondi di attesa terminate() prima di kill()
PROGRESS_MAX = 100              # fondo scala progress bar / percentuale


# ---------------------------------------------------------------------------
# Legal notices shipped with a build
# ---------------------------------------------------------------------------

# Every distributed build carries third-party code (pygame is LGPL-2.1-or-later)
# and engine code under the project license, and both require their terms to
# travel with the binary. The bundle below is written next to the game files.
LICENSE_DIR_NAME = "licenses"

# repo file -> name inside the build. Everything is written as .txt because the
# Android packaging drops *.md (source.exclude_patterns in buildozer.spec).
LICENSE_SOURCES: tuple[tuple[str, str], ...] = (
    ("LICENSE", "ENGINE-LICENSE.txt"),
    ("NOTICE", "NOTICE.txt"),
    ("THIRD_PARTY_NOTICES.md", "THIRD-PARTY-NOTICES.txt"),
    ("LICENSE-ASSETS.md", "ASSETS-LICENSE.txt"),
)

# A game shipped under a commercial license carries its own engine terms: drop
# the signed license in games/<id>/LICENSE-ENGINE.txt and it replaces the
# repository default in that game's builds.
GAME_LICENSE_OVERRIDE = "LICENSE-ENGINE.txt"

LICENSE_INDEX_NAME = "README.txt"
LICENSE_INDEX_TEXT = """Licenses and notices
====================

This game was built with HiddenIndexEngine.
https://github.com/indecenti/HiddenIndexEngine

ENGINE-LICENSE.txt        Terms covering the engine code included in this build.
NOTICE.txt                Copyright notice required with the engine code.
THIRD-PARTY-NOTICES.txt   Third-party components bundled here and their licenses.
ASSETS-LICENSE.txt        Terms of the images, music and sounds that come from
                          the engine's shared library. Assets created by the
                          author of this game are not covered by it.

pygame is LGPL-2.1-or-later. Its source code is available at
https://github.com/pygame/pygame, and you may replace the copy bundled with this
build with your own compatible build of the library.
"""


def build_license_bundle(base_path: Path, game_path: Path | None = None) -> dict[str, str]:
    """File name -> text of the notices a distributed build must carry.

    A missing source file is skipped rather than failing the build: shipping an
    incomplete set of notices is bad, shipping nothing because the build broke
    is worse.
    """
    bundle: dict[str, str] = {LICENSE_INDEX_NAME: LICENSE_INDEX_TEXT}
    for src_name, out_name in LICENSE_SOURCES:
        src = Path(base_path) / src_name
        try:
            bundle[out_name] = src.read_text(encoding="utf-8")
        except OSError as e:
            logger.warning("[LICENSES] %s not readable (%s): skipped", src_name, e)
    if game_path:
        override = Path(game_path) / GAME_LICENSE_OVERRIDE
        try:
            if override.is_file():
                bundle["ENGINE-LICENSE.txt"] = override.read_text(encoding="utf-8")
                logger.info("[LICENSES] Engine terms taken from %s", override)
        except OSError as e:
            logger.warning("[LICENSES] Override %s not readable (%s)", override, e)
    return bundle


def write_license_bundle(base_path: Path, out_dir: Path,
                         game_path: Path | None = None) -> Path:
    """Write the notices into <out_dir>/licenses/ and return that folder."""
    dest = Path(out_dir) / LICENSE_DIR_NAME
    dest.mkdir(parents=True, exist_ok=True)
    for name, text in build_license_bundle(base_path, game_path).items():
        (dest / name).write_text(text, encoding="utf-8")
    logger.info("[LICENSES] Notices written to %s", dest)
    return dest

# Palette Tkinter condivisa dalle finestre di progresso.
HEADER_BG = "#2c3e50"
HEADER_FG = "#ecf0f1"
HEADER_HEIGHT = 60
STATUS_FG = "#34495e"
PERCENT_FG = "#7f8c8d"
LOG_BG = "#ecf0f1"
LOG_FG = "#2c3e50"
BTN_START_BG = "#27ae60"
BTN_CANCEL_BG = "#e74c3c"
BTN_FOLDER_BG = "#3498db"
BTN_CLOSE_BG = "#95a5a6"
OK_FG = "#27ae60"
ERR_FG = "#e74c3c"
WARN_FG = "#f39c12"
RUN_FG = "#e67e22"
INFO_BANNER_BG = "#fef9e7"
INFO_BANNER_FG = "#7d6608"
FONT_UI = "Segoe UI"
FONT_MONO = "Courier New"
LOG_AREA_HEIGHT = 12


# ---------------------------------------------------------------------------
# Stato condiviso su file JSON
# ---------------------------------------------------------------------------

def update_status(
    status_file: Path,
    progress: int,
    step: str,
    log_lines: list[str],
    success: Optional[bool] = None,
    error_msg: Optional[str] = None,
    extra_fields: Optional[dict] = None,
    log: Optional[logging.Logger] = None,
) -> None:
    """
    Scrive il file di stato JSON condiviso tra build manager e finestra UI.

    extra_fields: campi specifici della pipeline (es. zip_path per l'EXE,
    apk_path/apk_size_mb per Android), inseriti prima del timestamp per
    mantenere lo stesso layout dei file storici.
    """
    status: dict = {
        "progress": progress,
        "step": step,
        "log": log_lines,
        "success": success,
        "error_msg": error_msg,
    }
    if extra_fields:
        status.update(extra_fields)
    status["timestamp"] = time.time()  # per rilevare blocchi nel polling
    try:
        with open(status_file, "w", encoding="utf-8") as f:
            json.dump(status, f, indent=2)
    except Exception as e:
        (log or logger).error(f"Errore aggiornamento status file: {e}")


# ---------------------------------------------------------------------------
# Watchdog
# ---------------------------------------------------------------------------

class BuildWatchdog(threading.Thread):
    """
    Thread che monitora il file di stato: se il progresso non avanza entro
    `timeout` secondi, segnala il blocco scrivendo error_msg e finalizza il
    fallimento (success=False). Senza la finalizzazione la UI resterebbe in
    attesa fino al proprio polling timeout ignorando lo stallo.

    Unico per entrambe le pipeline; cambia solo il timeout (EXE: stallo dopo
    2 min; APK: 6 min, la cross-compile ha fasi lunghe senza update).
    """

    def __init__(
        self,
        status_file: Path,
        timeout: int,
        check_interval: int = WATCHDOG_CHECK_INTERVAL,
        log: Optional[logging.Logger] = None,
    ) -> None:
        super().__init__(daemon=True)
        self.status_file = status_file
        self.timeout = timeout
        self.check_interval = check_interval
        self.log = log or logger
        self.last_progress = 0
        self.last_update_time = time.time()
        self.should_stop = False

    def run(self) -> None:
        self.log.info(f"[Watchdog] Avviato (timeout inattivita': {self.timeout}s)")
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
                    self.log.debug(f"[Watchdog] Progresso aggiornato a {current_progress}%")

                inactive = now - self.last_update_time
                if inactive > self.timeout and status.get("success") is None:
                    self.log.error(
                        f"[Watchdog] Build bloccato! "
                        f"Progresso fermo a {current_progress}% per {inactive:.0f}s"
                    )
                    status["error_msg"] = (
                        f"Build bloccato: progresso fermo a {current_progress}% "
                        f"per {inactive:.0f}s (timeout: {self.timeout}s)"
                    )
                    # Finalizza il fallimento, altrimenti la UI resta in attesa
                    # (si sblocca solo al proprio timeout) ignorando lo stallo.
                    status["success"] = False
                    with open(self.status_file, "w", encoding="utf-8") as f:
                        json.dump(status, f, indent=2)
            except Exception as e:
                self.log.debug(f"[Watchdog] Errore monitoraggio: {e}")
            time.sleep(self.check_interval)

    def stop(self) -> None:
        """Ferma il watchdog al prossimo ciclo."""
        self.should_stop = True


# ---------------------------------------------------------------------------
# Runner subprocess con timeout, stall detection e progress
# ---------------------------------------------------------------------------

def run_subprocess_with_timeout(
    cmd: list[str],
    *,
    timeout: int,
    stall_timeout: int,
    log_tag: str,
    cwd: Optional[str] = None,
    encoding: Optional[str] = None,
    errors: Optional[str] = None,
    stages: Optional[list[tuple[str, int, Optional[str]]]] = None,
    stage_match_lower: bool = False,
    stage_line_label_prefix: str = "",
    initial_progress: int = 0,
    progress_callback: Optional[Callable[[float, str], None]] = None,
    heartbeat_progress: Optional[int] = None,
    heartbeat_label_fn: Optional[Callable[[float, int], str]] = None,
    log_every_n_lines: int = 1,
    cancel_event: Optional[threading.Event] = None,
    check_interval: float = SUBPROCESS_CHECK_INTERVAL,
    log: Optional[logging.Logger] = None,
) -> tuple[int, list[str]]:
    """
    Esegue un sottoprocesso di build con streaming dell'output e monitoraggio.

    Unifica _run_pyinstaller_with_timeout (build_system) e
    _run_buildozer_with_timeout (android_build_system).

    Args:
        cmd: comando come lista di argomenti per subprocess.Popen.
        timeout: timeout globale in secondi (scaduto -> kill, RC_TIMEOUT).
        stall_timeout: secondi senza NUOVO output prima di dichiarare lo stallo
            (PyInstaller: 120; Buildozer: 300) -> kill, RC_TIMEOUT.
        log_tag: etichetta usata nei messaggi di log (es. "PyInstaller").
        cwd: working directory del processo (None = eredita).
        encoding/errors: decodifica dell'output (None = default di sistema).
        stages: lista (marker, percentuale, label). Quando il marker compare in
            una linea di output e la percentuale supera quella corrente, viene
            invocato progress_callback. label=None -> etichetta derivata dalla
            linea corrente, prefissata con stage_line_label_prefix.
        stage_match_lower: se True il match dei marker e' case-insensitive.
        initial_progress: percentuale di partenza della fase subprocess.
        progress_callback: funzione(progress 0-100, step: str).
        heartbeat_progress: percentuale fissa da riportare negli heartbeat
            (None = percentuale corrente).
        heartbeat_label_fn: funzione(elapsed_s, n_linee) -> etichetta heartbeat;
            None = nessuna callback di heartbeat (solo log).
        log_every_n_lines: logga a debug una linea ogni N ricevute.
        cancel_event: se settato durante l'esecuzione, il processo viene ucciso
            e la funzione ritorna RC_CANCELED.
        check_interval: secondi tra i cicli di monitoraggio.
        log: logger da usare (None = logger di modulo).

    Returns:
        (return_code, output_lines) — return_code e' quello del processo,
        oppure RC_TIMEOUT / RC_CANCELED / RC_EXCEPTION.
    """
    lg = log or logger
    output_lines: list[str] = []
    proc: Optional[subprocess.Popen] = None
    exception_occurred: Optional[BaseException] = None
    last_line_time = time.time()
    current_progress = initial_progress
    line_count = 0

    popen_kwargs: dict = {
        "stdout": subprocess.PIPE,
        "stderr": subprocess.STDOUT,
        "text": True,
        "bufsize": 1,
    }
    if cwd is not None:
        popen_kwargs["cwd"] = cwd
    if encoding is not None:
        popen_kwargs["encoding"] = encoding
        popen_kwargs["errors"] = errors

    def run_process() -> None:
        """Esegue il processo in un thread separato e ne consuma l'output."""
        nonlocal proc, exception_occurred, last_line_time, current_progress, line_count
        try:
            proc = subprocess.Popen(cmd, **popen_kwargs)
            lg.debug(f"[{log_tag} PID] {proc.pid}")

            for line in proc.stdout:
                line = line.rstrip()
                line_count += 1
                last_line_time = time.time()
                if not line:
                    continue
                output_lines.append(line)
                if line_count % log_every_n_lines == 0:
                    lg.debug(f"[{log_tag} #{line_count}] {line[:LOG_LINE_MAX_CHARS]}")

                # Avanza il progresso sui marker noti.
                for marker, pct, label in (stages or []):
                    matched = (
                        marker.lower() in line.lower() if stage_match_lower
                        else marker in line
                    )
                    if matched and pct > current_progress:
                        current_progress = pct
                        shown = (
                            label if label is not None
                            else f"{stage_line_label_prefix}{line[:STAGE_LABEL_MAX_CHARS]}"
                        )
                        if progress_callback:
                            progress_callback(current_progress, shown)
                        lg.info(f"[Progress] {current_progress}% - {shown}")
                        break

            # Attende la terminazione dopo la chiusura dello stdout.
            try:
                proc.wait(timeout=GRACEFUL_WAIT)
            except subprocess.TimeoutExpired:
                lg.warning(f"[{log_tag}] Processo non termina dopo EOF, kill forzato")
                proc.kill()
                proc.wait()
        except Exception as e:
            exception_occurred = e
            if proc:
                try:
                    proc.kill()
                except Exception:
                    pass

    proc_thread = threading.Thread(target=run_process, daemon=False)
    proc_thread.start()

    def _kill_proc() -> None:
        """Kill best-effort del processo monitorato."""
        if proc:
            try:
                lg.warning(f"[{log_tag}] Kill processo {proc.pid}")
                proc.kill()
                proc.wait(timeout=KILL_WAIT)
            except Exception as e:
                lg.error(f"[{log_tag}] Errore kill processo: {e}")

    start = time.time()
    last_heartbeat = start

    while proc_thread.is_alive() and (time.time() - start) < timeout:
        # Cancel esplicito (usato dai test e da eventuali chiamanti futuri;
        # le UI storiche annullano uccidendo direttamente il manager).
        if cancel_event is not None and cancel_event.is_set():
            lg.warning(f"[{log_tag}] Cancel richiesto: termino il processo")
            _kill_proc()
            proc_thread.join(timeout=KILL_WAIT)
            return RC_CANCELED, output_lines

        # Rilevamento stallo: nessun output per troppo tempo.
        idle = time.time() - last_line_time
        if idle > stall_timeout:
            lg.error(
                f"BLOCCO RILEVATO: {log_tag} non emette output da {idle:.0f}s "
                f"(linee ricevute: {line_count})"
            )
            _kill_proc()
            proc_thread.join(timeout=WATCHDOG_JOIN_TIMEOUT)
            return RC_TIMEOUT, output_lines

        # Heartbeat periodico: segno di vita nel log e (opzionale) nella UI.
        if (time.time() - last_heartbeat) > HEARTBEAT_INTERVAL:
            elapsed = time.time() - start
            if progress_callback and heartbeat_label_fn:
                hb_pct = heartbeat_progress if heartbeat_progress is not None else current_progress
                progress_callback(hb_pct, heartbeat_label_fn(elapsed, len(output_lines)))
            lg.info(
                f"[Heartbeat] {log_tag} in corso ({elapsed:.0f}s, {len(output_lines)} linee, "
                f"ultima linea: {idle:.0f}s fa)"
            )
            last_heartbeat = time.time()

        time.sleep(check_interval)

    # Timeout globale scaduto.
    if proc_thread.is_alive():
        lg.error(f"TIMEOUT {log_tag} dopo {timeout}s")
        if progress_callback:
            progress_callback(PROGRESS_MAX, f"TIMEOUT {log_tag} dopo {timeout}s!")
        _kill_proc()
        proc_thread.join(timeout=KILL_WAIT)
        return RC_TIMEOUT, output_lines

    if exception_occurred:
        lg.error(f"Eccezione in {log_tag}: {exception_occurred}")
        return RC_EXCEPTION, output_lines

    rc = proc.returncode if proc else RC_EXCEPTION
    lg.info(f"[{log_tag}] completato, rc={rc}, {len(output_lines)} linee di output")
    return rc, output_lines


# ---------------------------------------------------------------------------
# Skeleton comune dei build manager
# ---------------------------------------------------------------------------

def run_managed_build(
    *,
    build_fn: Callable[[Callable[[float, str], None]], dict],
    status_file: Path,
    global_timeout: int,
    watchdog_timeout: int,
    watchdog_check_interval: int,
    timeout_error_fmt: str,
    success_step_fn: Callable[[dict], str],
    failure_step: str,
    timeout_step: str,
    extra_defaults: Optional[dict] = None,
    result_extra_fn: Optional[Callable[[dict], dict]] = None,
    log: Optional[logging.Logger] = None,
) -> int:
    """
    Skeleton comune di build_manager.run_build e android_build_manager.
    run_apk_build: watchdog + progress callback con timeout globale + stato
    finale nel file JSON + exit code (0 successo, 1 errore/timeout).

    Args:
        build_fn: funzione che esegue la build vera e propria; riceve il
            progress_callback e ritorna il dict di risultato del build system
            (chiavi: success, error_msg, steps_log + extra per pipeline).
        status_file: file JSON di stato condiviso con la UI.
        global_timeout: secondi oltre i quali il progress_callback solleva
            RuntimeError (timeout globale).
        watchdog_timeout: secondi di inattivita' prima che il watchdog
            dichiari lo stallo.
        watchdog_check_interval: secondi tra i check del watchdog.
        timeout_error_fmt: messaggio del timeout globale; placeholder
            {timeout} e {progress}.
        success_step_fn: funzione(result) -> testo dello step finale di successo.
        failure_step / timeout_step: testi dello step finale di errore/timeout.
        extra_defaults: campi extra sempre presenti nel file di stato
            (es. {"zip_path": None}) per mantenere lo schema storico.
        result_extra_fn: funzione(result) -> campi extra valorizzati al successo.
        log: logger del manager chiamante.

    Returns:
        Exit code del processo manager (0 = successo, 1 = errore).
    """
    import atexit

    lg = log or logger
    build_start = time.time()

    watchdog = BuildWatchdog(
        status_file,
        timeout=watchdog_timeout,
        check_interval=watchdog_check_interval,
        log=lg,
    )
    watchdog.start()

    def stop_watchdog() -> None:
        watchdog.stop()
        watchdog.join(timeout=WATCHDOG_JOIN_TIMEOUT)

    atexit.register(stop_watchdog)

    steps_log: list[str] = []

    def progress_callback(progress: float, step: str) -> None:
        """Callback dal build system: verifica timeout globale e scrive lo stato."""
        elapsed = time.time() - build_start
        if elapsed > global_timeout:
            raise RuntimeError(
                timeout_error_fmt.format(timeout=global_timeout, progress=progress)
            )
        steps_log.append(f"[{progress:.0f}%] {step}")
        update_status(
            status_file,
            progress=int(progress),
            step=step,
            log_lines=steps_log,
            extra_fields=extra_defaults,
            log=lg,
        )
        lg.debug(f"[Progress] {progress:.0f}% ({elapsed:.1f}s) - {step}")

    try:
        result = build_fn(progress_callback)
        elapsed = time.time() - build_start

        if result["success"]:
            extra = dict(extra_defaults or {})
            if result_extra_fn:
                extra.update(result_extra_fn(result))
            lg.info(f"[Build Success] Completato in {elapsed:.1f}s")
            update_status(
                status_file,
                progress=PROGRESS_MAX,
                step=success_step_fn(result),
                log_lines=result["steps_log"],
                success=True,
                extra_fields=extra,
                log=lg,
            )
            return 0

        lg.error(f"[Build Failure] Fallito dopo {elapsed:.1f}s: {result['error_msg']}")
        update_status(
            status_file,
            progress=PROGRESS_MAX,
            step=failure_step,
            log_lines=result["steps_log"],
            success=False,
            error_msg=result["error_msg"],
            extra_fields=extra_defaults,
            log=lg,
        )
        return 1

    except RuntimeError as e:
        elapsed = time.time() - build_start
        lg.error(f"[Build Timeout] {e} (elapsed: {elapsed:.1f}s)")
        update_status(
            status_file,
            progress=PROGRESS_MAX,
            step=timeout_step,
            log_lines=steps_log,
            success=False,
            error_msg=str(e),
            extra_fields=extra_defaults,
            log=lg,
        )
        return 1

    finally:
        stop_watchdog()


# ---------------------------------------------------------------------------
# Finestra Tkinter di progresso (base parametrizzata)
# ---------------------------------------------------------------------------

class BaseBuildProgressWindow:
    """
    Finestra Tkinter di progresso build, parametrizzata per pipeline.

    Le sottoclassi (build_ui.BuildProgressWindow per l'EXE,
    android_build_ui.AndroidBuildProgressWindow per l'APK) specializzano
    etichette, timeout e opzioni via attributi di classe e hook:

      - _create_option_widgets(): widget opzione (checkbox ZIP / release);
      - _extra_manager_args():    argomenti CLI extra per il manager;
      - _disable_option_widgets(): disabilita le opzioni a build avviato;
      - _percent_label_text():    testo animato della label percentuale;
      - _success_status_text() / _success_message(): esito positivo;
      - _extra_cancel_cleanup():  pulizia aggiuntiva su annulla (es. pkill WSL).

    Il flusso e' identico per entrambe: la finestra lancia il build manager
    come subprocess e ne segue lo stato via polling del file JSON ogni 500 ms,
    con rilevamento timeout e (opzionale) avviso di stallo.
    """

    # ── Parametri di specializzazione (override nelle sottoclassi) ──────────
    window_title_fmt: ClassVar[str] = "Compilazione: {game_id} v{version}"
    header_text_fmt: ClassVar[str] = "Compilazione: {game_id} v{version}"
    header_font_size: ClassVar[int] = 14
    geometry: ClassVar[str] = "600x500"
    progressbar_length: ClassVar[int] = 550
    log_area_width: ClassVar[int] = 70
    polling_timeout: ClassVar[int] = 600
    initial_status_text: ClassVar[str] = "Inizializzazione..."
    info_banner_text: ClassVar[Optional[str]] = None
    log_label_text: ClassVar[str] = "Registro compilazione:"
    start_button_text: ClassVar[str] = "Avvia Build"
    open_folder_button_text: ClassVar[str] = "Apri Cartella"
    running_status_text: ClassVar[str] = "Build in corso..."
    start_error_prefix: ClassVar[str] = "Impossibile avviare build:"
    manager_script_name: ClassVar[str] = "build_manager.py"
    manager_frozen_flag: ClassVar[str] = "--build-manager"
    timeout_message_fmt: ClassVar[str] = (
        "Build in timeout dopo {timeout_s:.0f}s.\n"
        "Il processo potrebbe essere bloccato.\n"
        "Chiudere la finestra per terminare il build."
    )
    timeout_status_text: ClassVar[str] = "✗ TIMEOUT Build"
    failure_status_text: ClassVar[str] = "✗ Errore compilazione"
    failure_msg_prefix: ClassVar[str] = "Build fallito:"
    cancel_confirm_text: ClassVar[str] = "Annullare la compilazione?"
    close_confirm_text: ClassVar[str] = "La compilazione è ancora in corso. Chiudere comunque?"
    canceled_error_msg: ClassVar[str] = "Build annullato dall'utente"
    # True: su Windows uccide l'intero albero processi con taskkill /F /T
    # (necessario per PyInstaller e i suoi worker). False: terminate() semplice
    # (Android: l'albero reale vive dentro WSL, gestito da _extra_cancel_cleanup).
    kill_tree_on_cancel: ClassVar[bool] = True
    # Secondi di progresso fermo prima del popup di avviso stallo (None = mai).
    stall_warning_after_s: ClassVar[Optional[int]] = None

    def __init__(self, game_id: str, version: str, build_dir: str, status_file: str) -> None:
        self.game_id = game_id
        self.version = version
        self.build_dir = Path(build_dir)
        self.status_file = Path(status_file)
        self.build_process: Optional[subprocess.Popen] = None
        self.should_cancel = False
        self.build_started = False

        self.root = Tk()
        self.root.title(self.window_title_fmt.format(game_id=game_id, version=version))
        self.root.geometry(self.geometry)
        self.root.resizable(True, True)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        # Timing per timeout e rilevamento stallo del polling.
        self.poll_start_time = time.time()
        self.last_progress_change = time.time()
        self.last_progress = 0
        self.last_timestamp = 0.0
        self._anim_tick = 0
        self._stall_warned = False

        self._create_widgets()
        self._start_polling()

    # ── Hook di specializzazione ─────────────────────────────────────────────

    def _create_option_widgets(self, button_frame: Frame) -> None:
        """Hook: widget opzione della pipeline (checkbox ZIP / release)."""

    def _extra_manager_args(self) -> list[str]:
        """Hook: argomenti CLI aggiuntivi da passare al build manager."""
        return []

    def _disable_option_widgets(self) -> None:
        """Hook: disabilita i widget opzione una volta avviato il build."""

    def _percent_label_text(
        self, progress: int, status: dict, time_since_change: float
    ) -> Optional[str]:
        """
        Hook animazione: testo custom della label percentuale per le fasi
        lunghe e silenti (None = testo default "N%"). Puo' usare
        self._anim_tick, incrementato dalla base dopo ogni frame custom.
        """
        return None

    def _success_status_text(self, status: dict) -> str:
        """Hook: testo della status label in caso di successo."""
        return "✓ Compilazione completata!"

    def _success_message(self, status: dict) -> str:
        """Hook: testo del messagebox di successo."""
        return "Build completato!"

    def _extra_cancel_cleanup(self) -> None:
        """Hook: pulizia aggiuntiva dopo la terminazione del manager."""

    # ── Costruzione UI ───────────────────────────────────────────────────────

    def _create_widgets(self) -> None:
        """Crea gli elementi della UI."""
        # Header
        header = Frame(self.root, bg=HEADER_BG, height=HEADER_HEIGHT)
        header.pack(fill="x")
        header.pack_propagate(False)
        Label(
            header,
            text=self.header_text_fmt.format(game_id=self.game_id, version=self.version),
            font=(FONT_UI, self.header_font_size, "bold"),
            fg=HEADER_FG,
            bg=HEADER_BG,
        ).pack(pady=10)

        # Status
        status_frame = Frame(self.root)
        status_frame.pack(fill="x", padx=15, pady=10)
        self.status_label = Label(
            status_frame, text=self.initial_status_text, font=(FONT_UI, 10), fg=STATUS_FG
        )
        self.status_label.pack(anchor="w")

        # Progress bar
        progress_frame = Frame(self.root)
        progress_frame.pack(fill="x", padx=15, pady=5)
        self.progress_var = IntVar(value=0)
        self.progress_bar = ttk.Progressbar(
            progress_frame,
            length=self.progressbar_length,
            mode="determinate",
            variable=self.progress_var,
            maximum=PROGRESS_MAX,
        )
        self.progress_bar.pack(fill="x")
        self.percent_label = Label(progress_frame, text="0%", font=(FONT_UI, 9), fg=PERCENT_FG)
        self.percent_label.pack(anchor="e", pady=2)

        # Banner informativo opzionale (es. durata prima build APK)
        if self.info_banner_text:
            info_frame = Frame(self.root, bg=INFO_BANNER_BG)
            info_frame.pack(fill="x", padx=15, pady=5)
            Label(
                info_frame,
                text=self.info_banner_text,
                font=(FONT_UI, 9),
                bg=INFO_BANNER_BG,
                fg=INFO_BANNER_FG,
                justify="left",
            ).pack(anchor="w", padx=8, pady=5)

        # Log scrollabile
        log_frame = Frame(self.root)
        log_frame.pack(fill="both", expand=True, padx=15, pady=10)
        Label(log_frame, text=self.log_label_text, font=(FONT_UI, 10, "bold")).pack(anchor="w")
        self.log_text = scrolledtext.ScrolledText(
            log_frame,
            height=LOG_AREA_HEIGHT,
            width=self.log_area_width,
            font=(FONT_MONO, 9),
            bg=LOG_BG,
            fg=LOG_FG,
            state="disabled",
        )
        self.log_text.pack(fill="both", expand=True, pady=5)

        # Pulsanti
        button_frame = Frame(self.root)
        button_frame.pack(fill="x", padx=15, pady=10)

        self.start_btn = Button(
            button_frame,
            text=self.start_button_text,
            command=self.on_start_build,
            font=(FONT_UI, 10, "bold"),
            bg=BTN_START_BG,
            fg="white",
            padx=20,
            pady=5,
        )
        self.start_btn.pack(side="left", padx=5)

        self._create_option_widgets(button_frame)

        self.cancel_btn = Button(
            button_frame,
            text="Annulla",
            command=self.on_cancel,
            font=(FONT_UI, 10),
            bg=BTN_CANCEL_BG,
            fg="white",
            padx=15,
            pady=5,
            state="disabled",
        )
        self.cancel_btn.pack(side="left", padx=5)

        self.open_folder_btn = Button(
            button_frame,
            text=self.open_folder_button_text,
            command=self.on_open_folder,
            font=(FONT_UI, 10),
            bg=BTN_FOLDER_BG,
            fg="white",
            padx=15,
            pady=5,
            state="disabled",
        )
        self.open_folder_btn.pack(side="left", padx=5)

        self.close_btn = Button(
            button_frame,
            text="Chiudi",
            command=self.on_close,
            font=(FONT_UI, 10),
            bg=BTN_CLOSE_BG,
            fg="white",
            padx=15,
            pady=5,
            state="disabled",
        )
        self.close_btn.pack(side="right", padx=5)

    # ── Polling del file di stato ────────────────────────────────────────────

    def _start_polling(self) -> None:
        """Avvia il polling periodico del file di stato."""
        self.poll_start_time = time.time()
        self.root.after(POLL_FIRST_DELAY_MS, self._poll_status)

    def _poll_status(self) -> None:
        """Poll periodico del file di stato JSON scritto dal manager."""
        # Timeout globale del polling.
        elapsed_polling = time.time() - self.poll_start_time
        if self.build_started and elapsed_polling > self.polling_timeout and not self.should_cancel:
            messagebox.showerror(
                "Timeout",
                self.timeout_message_fmt.format(
                    timeout_s=float(self.polling_timeout),
                    timeout_min=self.polling_timeout / 60.0,
                ),
            )
            self.status_label.config(text=self.timeout_status_text, fg=ERR_FG)
            self.cancel_btn.config(state="normal")
            return

        if not self.build_started or not self.status_file.exists():
            self.root.after(POLL_INTERVAL_MS, self._poll_status)
            return

        try:
            with open(self.status_file, "r", encoding="utf-8") as f:
                status = json.load(f)

            progress = status.get("progress", 0)
            current_timestamp = status.get("timestamp", 0)
            self.progress_var.set(progress)

            # Rilevamento stallo: progresso fermo per troppo tempo.
            if progress != self.last_progress:
                self.last_progress = progress
                self.last_progress_change = time.time()
                self.last_timestamp = current_timestamp
                self._stall_warned = False

            time_since_change = time.time() - self.last_progress_change
            if (
                self.stall_warning_after_s is not None
                and time_since_change > self.stall_warning_after_s
                and status.get("success") is None
                and status.get("error_msg") is None
                and not self._stall_warned
            ):
                # Avvisa una sola volta per stallo (reset quando il progresso riparte).
                self._stall_warned = True
                messagebox.showwarning(
                    "Attenzione",
                    f"Build potrebbe essere bloccato:\n"
                    f"Progresso fermo a {progress}% per {time_since_change:.0f}s.\n\n"
                    f"Prova ad annullare o attendere ancora.",
                )

            # Label percentuale: animazione custom nelle fasi lunghe e silenti.
            custom_text: Optional[str] = None
            if self.build_started and status.get("success") is None:
                custom_text = self._percent_label_text(progress, status, time_since_change)
            if custom_text is not None:
                self._anim_tick += 1
                self.percent_label.config(text=custom_text)
            else:
                self._anim_tick = 0
                self.percent_label.config(text=f"{progress}%")

            self.status_label.config(text=status.get("step", ""))
            self._update_log(status.get("log", []))

            if status.get("success") is not None:
                self._on_build_complete(status)
                return

        except (json.JSONDecodeError, IOError):
            pass

        self.root.after(POLL_INTERVAL_MS, self._poll_status)

    def _update_log(self, log_lines: list[str]) -> None:
        """Aggiorna il testo del log se cambiato."""
        self.log_text.config(state="normal")
        current_text = self.log_text.get("1.0", "end-1c")
        new_lines = "\n".join(log_lines)
        if current_text != new_lines:
            self.log_text.delete("1.0", "end")
            self.log_text.insert("end", new_lines)
            self.log_text.see("end")
        self.log_text.config(state="disabled")

    def _on_build_complete(self, status: dict) -> None:
        """Chiamato quando il manager finalizza lo stato (success non-None)."""
        success = status.get("success", False)
        if success:
            self.status_label.config(text=self._success_status_text(status), fg=OK_FG)
            self.progress_var.set(PROGRESS_MAX)
            self.percent_label.config(text=f"{PROGRESS_MAX}%")
            self.cancel_btn.config(state="disabled")
            self.open_folder_btn.config(state="normal")
            self.close_btn.config(state="normal")
            messagebox.showinfo("Successo", self._success_message(status))
        else:
            self.status_label.config(text=self.failure_status_text, fg=ERR_FG)
            self.cancel_btn.config(state="disabled")
            self.close_btn.config(state="normal")
            error_msg = status.get("error_msg", "Errore sconosciuto")
            messagebox.showerror("Errore", f"{self.failure_msg_prefix}\n\n{error_msg}")

    # ── Azioni pulsanti ──────────────────────────────────────────────────────

    def on_start_build(self) -> None:
        """Lancia il build manager come subprocess."""
        if self.build_started:
            messagebox.showwarning("Attenzione", "Build già avviato!")
            return

        self.build_started = True
        self.start_btn.config(state="disabled")
        self.cancel_btn.config(state="normal")

        try:
            from engine.utils import get_base_path
            project_root = get_base_path()

            # PYTHONPATH sulla root del progetto per gli import engine.* / editor.*
            env = os.environ.copy()
            env["PYTHONPATH"] = str(project_root)

            if getattr(sys, "frozen", False):
                cmd = [
                    sys.executable,
                    self.manager_frozen_flag,
                    self.game_id,
                    self.version,
                    str(self.build_dir),
                    str(self.status_file),
                ]
            else:
                manager_script = project_root / "editor" / self.manager_script_name
                cmd = [
                    sys.executable,
                    str(manager_script),
                    self.game_id,
                    self.version,
                    str(self.build_dir),
                    str(self.status_file),
                ]
            cmd.extend(self._extra_manager_args())

            self.build_process = subprocess.Popen(cmd, cwd=str(project_root), env=env)
            self.status_label.config(text=self.running_status_text, fg=RUN_FG)
            self._disable_option_widgets()
        except Exception as e:
            messagebox.showerror("Errore", f"{self.start_error_prefix}\n{e}")
            self.start_btn.config(state="normal")
            self.build_started = False

    def on_cancel(self) -> None:
        """Annulla la compilazione terminando il manager (e il suo albero)."""
        if not messagebox.askyesno("Conferma", self.cancel_confirm_text):
            return
        self.should_cancel = True
        self.cancel_btn.config(state="disabled")
        self.status_label.config(text="Annullamento in corso...", fg=WARN_FG)

        if self.build_process:
            try:
                pid = self.build_process.pid
                logger.info(f"[Cancel] Terminazione processo {pid}")
                if self.kill_tree_on_cancel and sys.platform == "win32":
                    # Il manager lancia a sua volta sotto-processi (es. PyInstaller
                    # e i suoi worker): terminate() sul solo manager li lascerebbe
                    # orfani a girare e a tenere lock sui file temporanei.
                    # /T termina l'intero albero.
                    subprocess.run(
                        ["taskkill", "/F", "/T", "/PID", str(pid)],
                        capture_output=True,
                    )
                else:
                    self.build_process.terminate()
                    try:
                        self.build_process.wait(timeout=PROC_TERMINATE_WAIT)
                    except subprocess.TimeoutExpired:
                        self.build_process.kill()
            except Exception as e:
                logger.error(f"[Cancel] Errore termination: {e}")

        self._extra_cancel_cleanup()

        # Aggiorna il file di stato per segnalare la cancellazione.
        try:
            if self.status_file.exists():
                with open(self.status_file, "r", encoding="utf-8") as f:
                    status = json.load(f)
                status["canceled"] = True
                status["error_msg"] = self.canceled_error_msg
                with open(self.status_file, "w", encoding="utf-8") as f:
                    json.dump(status, f, indent=2)
        except Exception as e:
            logger.error(f"[Cancel] Errore aggiornamento status: {e}")

    def on_open_folder(self) -> None:
        """Apre la cartella di output nel file manager di sistema."""
        folder = self.build_dir.resolve()
        if not folder.exists():
            messagebox.showerror("Errore", f"Cartella non trovata:\n{folder}")
            return
        try:
            if sys.platform == "win32":
                subprocess.Popen(["explorer", str(folder)])
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(folder)])
            else:
                subprocess.Popen(["xdg-open", str(folder)])
        except Exception as e:
            messagebox.showerror("Errore", f"Impossibile aprire cartella:\n{e}")

    def on_close(self) -> None:
        """Chiude la finestra (con conferma se il build e' in corso)."""
        if self.should_cancel or self.progress_var.get() == PROGRESS_MAX:
            self.root.destroy()
        else:
            if messagebox.askyesno("Conferma", self.close_confirm_text):
                self.should_cancel = True
                self.root.destroy()

    def run(self) -> None:
        """Avvia il main loop Tkinter."""
        self.root.mainloop()
