"""
editor/build_system.py

Sistema di compilazione e packaging dei giochi con PyInstaller.
Gestisce:
  - Preparazione asset e file di configurazione
  - Lancio di PyInstaller con timeout e monitoraggio
  - Creazione del pacchetto ZIP distribuibile
  - Logging robusto e reporting progressi
"""

import sys
import json
import shutil
import tempfile
import subprocess
import threading
import time
from pathlib import Path
from typing import Callable, Optional
from zipfile import ZipFile

from engine.utils import get_base_path, get_logger
from editor.core.io import _load_json, _save_json

logger = get_logger("build_system")

# Timeout globali (in secondi)
PYINSTALLER_TIMEOUT = 600  # 10 minuti max per PyInstaller
SUBPROCESS_CHECK_INTERVAL = 2  # Check ogni 2 secondi se il processo è vivo


def _analyze_game_usage(game_path: Path) -> dict:
    """
    Analizza tutti i file del gioco per determinare le risorse strettamente necessarie.

    Returns:
        Dict con: 'objects' (set), 'minigames' (set), 'music' (set)
    """
    usage = {
        "objects": set(),
        "minigames": set(),
        "music": set()
    }

    # 1. Analisi game_config.json (Musica del menu)
    config_path = game_path / "game_config.json"
    if config_path.exists():
        try:
            config_data = _load_json(config_path)
            menu_music = config_data.get("menu", {}).get("music", [])
            for track in menu_music:
                usage["music"].add(str(track).replace("\\", "/"))
        except Exception as e:
            logger.warning(f"Errore lettura config per musica: {e}")

    # 2. Analisi Scene nei Livelli
    levels_dir = game_path / "levels"
    if not levels_dir.exists():
        return usage

    for scene_file in levels_dir.rglob("scene.json"):
        try:
            scene_data = _load_json(scene_file)
            
            # Musica della scena
            scene_music = scene_data.get("music", [])
            if isinstance(scene_music, str):
                usage["music"].add(scene_music.replace("\\", "/"))
            elif isinstance(scene_music, list):
                for track in scene_music:
                    usage["music"].add(str(track).replace("\\", "/"))

            # Oggetti e Minigiochi
            if "objects" in scene_data:
                for obj in scene_data["objects"]:
                    # Tracking Oggetti
                    cid = obj.get("catalog_id") or obj.get("object_id") or obj.get("id")
                    if cid:
                        usage["objects"].add(cid)
                    
                    # Tracking Minigiochi
                    trigger = obj.get("minigame_trigger")
                    if trigger and "minigame_id" in trigger:
                        mg_id = trigger["minigame_id"]
                        usage["minigames"].add(mg_id)
                        if mg_id == "arcade_eleven":
                            usage["minigames"].add("ciapel")
                            
        except Exception as e:
            logger.warning(f"Errore lettura {scene_file}: {e}")

    return usage


def _copy_smart_assets(
    games_src: Path,
    games_dst: Path,
    catalog_id_to_icon: dict,
) -> tuple[int, int]:
    """
    Copia SOLO gli asset usati dalla cartella di gioco (smart packaging).

    L'editor ha già pre-copiato i PNG usati in games/{game}/objects/ tramite
    _harvest_asset(). Qui copiamo tutto ciò che è presente in quella cartella:
    se il file è lì è perché è usato — nessuna ridondanza con engine/assets/.

    catalog_id_to_icon: dict[catalog_id -> icon_filename] per logging accurato.

    Returns:
        (file_count, total_size_bytes)
    """
    file_count = 0
    total_size = 0

    # Copia tutti i file del gioco tranne la cartella objects/ (la gestiamo separatamente)
    ignore_patterns = shutil.ignore_patterns(
        "__pycache__", "*.pyc", "*.pyo", "*.autosave",
        ".git*", "*.bak", "*.tmp", "*.log", ".DS_Store",
        "objects",
    )
    shutil.copytree(games_src, games_dst, ignore=ignore_patterns, dirs_exist_ok=True)

    # Copia i PNG dalla cartella objects/ del gioco.
    # L'editor li ha già filtrati: se il file esiste qui, è necessario.
    objects_src = games_src / "objects"
    if objects_src.exists():
        objects_dst = games_dst / "objects"
        objects_dst.mkdir(parents=True, exist_ok=True)

        for obj_file in objects_src.iterdir():
            if obj_file.is_file():
                shutil.copy2(obj_file, objects_dst / obj_file.name)
                file_count += 1
                total_size += obj_file.stat().st_size

        logger.info(f"[Smart Pack] Game objects: {file_count} PNG copiati da games/{games_src.name}/objects/")

    return file_count, total_size


def next_build_version(game_id: str) -> str:
    """
    Calcola la versione da usare per il prossimo build.

    Logica:
      - Legge la versione corrente da game_config.json
      - Se esiste già una build di quella versione in build/<game_id>/<version>/,
        incrementa il minor (1.0 → 1.1 → 1.2 …)
      - Altrimenti usa la versione corrente (primo build)

    Returns:
        Stringa versione da usare, es. "1.2"
    """
    base_path = get_base_path()
    game_config_path = base_path / "games" / game_id / "game_config.json"
    game_config = _load_json(game_config_path)
    current = game_config.get("version", "1.0")

    build_dir = base_path / "build" / game_id / current
    if not build_dir.exists():
        return current          # Nessuna build esistente: usa la versione corrente

    # Incrementa il minor finché non troviamo una versione libera
    try:
        major, minor = current.split(".", 1)
        minor_int = int(minor)
    except ValueError:
        major, minor_int = current, 0

    while True:
        minor_int += 1
        candidate = f"{major}.{minor_int}"
        if not (base_path / "build" / game_id / candidate).exists():
            return candidate


def _verify_pyinstaller_available():
    """
    Verifica che PyInstaller sia disponibile e loggable.
    Restituisce il path assoluto di pyinstaller.
    """
    try:
        result = subprocess.run(
            ["pyinstaller", "--version"],
            capture_output=True,
            text=True,
            timeout=5
        )
        version = result.stdout.strip() if result.returncode == 0 else "sconosciuta"
        logger.info(f"✓ PyInstaller disponibile (versione: {version})")
        return "pyinstaller"
    except FileNotFoundError:
        logger.error("✗ PyInstaller non trovato in PATH")
        raise RuntimeError(
            "PyInstaller non trovato. Installa con: pip install pyinstaller"
        )
    except Exception as e:
        logger.error(f"✗ Errore verifica PyInstaller: {e}")
        raise


def _run_pyinstaller_with_timeout(
    pyinstaller_args: list,
    cwd: str,
    timeout: int,
    progress_callback: Optional[Callable[[float, str], None]] = None
) -> tuple[int, list[str]]:
    """
    Esegue PyInstaller con timeout e monitoraggio.

    Monitora PyInstaller per stage e killa il processo se rimane bloccato.

    Returns:
        (return_code, output_lines)
    """
    pyinstaller_output = []
    proc = None  # Riferimento al processo per killarlo se necessario
    exception_occurred = None
    last_line_time = time.time()
    last_line_count = 0

    def run_process():
        """Esegue il processo in un thread separato."""
        nonlocal proc, exception_occurred, last_line_time, last_line_count

        try:
            proc = subprocess.Popen(
                pyinstaller_args,
                cwd=cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )

            logger.debug(f"[PyInstaller PID] {proc.pid}")

            # Leggi output riga per riga (non bloccante)
            pyinstaller_steps = [
                ("Analysis", 72),
                ("Building", 75),
                ("Checking", 78),
                ("Linking", 80),
                ("Building EXE", 82),
                ("Appending", 83),
            ]
            current_progress = 70
            line_count = 0

            for line in proc.stdout:
                line = line.rstrip()
                line_count += 1
                last_line_count = line_count
                last_line_time = time.time()

                if not line:
                    continue

                pyinstaller_output.append(line)
                logger.debug(f"[PyInstaller #{line_count}] {line[:100]}")

                # Avanza il progresso basato su keywords
                for keyword, pct in pyinstaller_steps:
                    if keyword.lower() in line.lower() and pct > current_progress:
                        current_progress = pct
                        if progress_callback:
                            progress_callback(current_progress, f"PyInstaller: {line[:60]}")
                        logger.info(f"[Progress] {current_progress}% - {keyword}")
                        break

            # Attendi che il processo termini (con timeout interno)
            try:
                proc.wait(timeout=30)  # 30 secondi per terminare gracefully
            except subprocess.TimeoutExpired:
                logger.warning(f"[PyInstaller] Processo non termina, killing...")
                proc.kill()
                proc.wait()

            return proc.returncode

        except Exception as e:
            exception_occurred = e
            if proc:
                try:
                    proc.kill()
                except Exception:
                    pass
            return 1

    # Lancia il processo in un thread
    proc_thread = threading.Thread(target=run_process, daemon=False)
    proc_thread.start()

    # Attendi con timeout e monitoraggio attivo
    start_time = time.time()
    last_update = start_time
    stuck_warning_time = None

    while proc_thread.is_alive() and (time.time() - start_time) < timeout:
        elapsed = time.time() - start_time

        # Rilevamento di blocco: nessun output per troppo tempo
        time_since_last_line = time.time() - last_line_time
        if time_since_last_line > 120:  # 2 minuti senza output = bloccato
            logger.error(
                f"✗ BLOCCO RILEVATO: PyInstaller non emette output da {time_since_last_line:.0f}s "
                f"(ultima linea #{last_line_count})"
            )
            if proc:
                try:
                    logger.warning(f"[Kill] Killing PyInstaller process {proc.pid}")
                    proc.kill()
                    proc.wait(timeout=5)
                except Exception as e:
                    logger.error(f"Errore killing processo: {e}")
            proc_thread.join(timeout=2)
            return 124, pyinstaller_output

        # Log di heartbeat ogni 30 secondi
        if (time.time() - last_update) > 30:
            logger.info(f"[Heartbeat] PyInstaller in corso ({elapsed:.0f}s, {len(pyinstaller_output)} linee, ultima linea: {time_since_last_line:.0f}s fa)")
            if progress_callback:
                progress_callback(75, f"PyInstaller in corso ({elapsed:.0f}s)...")
            last_update = time.time()

        time.sleep(SUBPROCESS_CHECK_INTERVAL)

    # Thread terminato
    if not proc_thread.is_alive():
        if exception_occurred:
            logger.error(f"✗ Eccezione in PyInstaller: {exception_occurred}")
            return 1, pyinstaller_output
        logger.info(f"[PyInstaller completato] {len(pyinstaller_output)} linee di output")
        return 0, pyinstaller_output

    # Timeout scaduto
    if proc_thread.is_alive():
        logger.error(f"✗ TIMEOUT PyInstaller dopo {timeout}s!")
        if progress_callback:
            progress_callback(100, f"✗ TIMEOUT PyInstaller dopo {timeout}s!")

        # Forza kill del processo
        if proc:
            try:
                logger.warning(f"[Timeout Kill] Killing PyInstaller process {proc.pid}")
                proc.kill()
                proc.wait(timeout=5)
            except Exception as e:
                logger.error(f"Errore killing processo on timeout: {e}")

        proc_thread.join(timeout=5)
        return 124, pyinstaller_output

    return 0, pyinstaller_output


def build_game(
    game_id: str,
    output_dir: Path,
    version: str,
    progress_callback: Optional[Callable[[float, str], None]] = None,
    create_zip: bool = True
) -> dict:
    """
    Compila e pacchettizza un gioco.

    Args:
        game_id: ID del gioco da compilare (es. "villa_segreta")
        output_dir: Directory di output per il build (es. build/villa_segreta/1.0/)
        progress_callback: Funzione(progress: 0-100, step_label: str) per aggiornamenti

    Returns:
        {
            "success": bool,
            "exe_path": str (se success),
            "zip_path": str (se success),
            "error_msg": str (se error),
            "steps_log": list[str]
        }
    """
    base_path = get_base_path()
    steps_log = []
    build_start_time = time.time()

    def log_step(msg: str, progress: float = None):
        """Log un passaggio e aggiorna progress."""
        elapsed = time.time() - build_start_time
        formatted_msg = f"[{elapsed:6.1f}s] {msg}"
        steps_log.append(formatted_msg)
        logger.info(formatted_msg)
        if progress_callback:
            # Calcola percentuale se fornita, altrimenti incrementale
            pct = progress if progress is not None else (len(steps_log) / 12 * 100)
            progress_callback(min(pct, 99), msg)

    temp_dir = None
    try:
        # ── STEP 1: Validazione ──────────────────────────────────────────────
        log_step("Validazione gioco...", 5)

        game_path = base_path / "games" / game_id
        if not game_path.exists():
            raise FileNotFoundError(f"Gioco '{game_id}' non trovato in {game_path}")

        game_config_path = game_path / "game_config.json"
        if not game_config_path.exists():
            raise FileNotFoundError(f"game_config.json non trovato per '{game_id}'")

        game_config = _load_json(game_config_path)
        game_title = game_config.get("title_key", game_id)

        log_step(f"Gioco valido: {game_id} v{version}", 10)

        # ── STEP 2: Preparazione cartella temporanea ──────────────────────────
        log_step("Preparazione cartella temporanea...", 15)

        temp_dir = Path(tempfile.mkdtemp(prefix=f"build_{game_id}_"))
        log_step(f"Cartella temp creata: {temp_dir}", 20)

        # ── STEP 3: Copia dei file Python (engine) ───────────────────────────
        log_step("Copia moduli engine (smart filter)...", 25)

        usage = _analyze_game_usage(game_path)
        used_objects = usage["objects"]
        used_minigames = usage["minigames"]
        logger.info(f"[Smart Filter] Rilevati {len(used_objects)} oggetti e {len(used_minigames)} minigiochi")

        engine_src = base_path / "engine"
        engine_dst = temp_dir / "engine"
        if engine_src.exists():
            # Copiamo tutto l'engine escludendo solo i minigiochi non necessari
            shutil.copytree(engine_src, engine_dst, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
            
            # Pulizia minigiochi: rimuove le cartelle dei minigiochi inutilizzati
            mg_dst_root = engine_dst / "minigames"
            if mg_dst_root.exists():
                for sub in mg_dst_root.iterdir():
                    if sub.is_dir() and sub.name not in used_minigames and sub.name != "__pycache__":
                        logger.debug(f"[Smart Filter] Rimozione minigioco non usato: {sub.name}")
                        shutil.rmtree(sub)
            
            log_step(f"Engine copiato: {len(used_minigames)} minigiochi mantenuti", 30)
        else:
            raise FileNotFoundError(f"Cartella engine non trovata: {engine_src}")

        # ── STEP 4: Copia di main.py ─────────────────────────────────────────
        log_step("Copia entry point...", 35)

        main_src = base_path / "main.py"
        if main_src.exists():
            shutil.copy2(main_src, temp_dir / "main.py")
            log_step("main.py copiato", 40)
        else:
            raise FileNotFoundError(f"main.py non trovato: {main_src}")

        # ── STEP 5: Valida che il gioco esista ──────────────────────────────
        # NON copiamo games/ nel temp_dir: PyInstaller non importa da games/,
        # sono dati puri (JSON + immagini). Verranno copiati in pkg_dir al Step 9.
        games_src = base_path / "games" / game_id
        if not games_src.exists():
            raise FileNotFoundError(f"Cartella gioco non trovata: {games_src}")
        log_step(f"Assets gioco verificati: {game_id}", 50)

        # ── STEP 6: Creazione config.ini dal game_config del gioco ──────────
        log_step("Configurazione personalizzata...", 55)

        # Leggi valori dal game_config.json del gioco specifico
        language = game_config.get("default_language", "it")
        res_cfg  = game_config.get("resolution", {})
        res_w    = res_cfg.get("w", 1920)
        res_h    = res_cfg.get("h", 1080)
        fullscreen = int(game_config.get("fullscreen", 0))

        config_content = (
            "[engine]\n"
            f"default_game = {game_id}\n"
            f"resolution_w = {res_w}\n"
            f"resolution_h = {res_h}\n"
            f"fullscreen = {fullscreen}\n"
            f"language = {language}\n"
        )
        config_path = temp_dir / "config.ini"
        config_path.write_text(config_content, encoding="utf-8")
        logger.info(f"[config.ini] game={game_id}, res={res_w}x{res_h}, lang={language}, fs={fullscreen}")
        log_step(f"config.ini creato ({res_w}x{res_h}, lang={language})", 60)

        # ── STEP 7: Copia di background.jpg (se esiste) ──────────────────────
        # --- background-splash (BOOT) ---
        # Rimosso come da richiesta USER

        # ── STEP 8: PyInstaller ──────────────────────────────────────────────
        log_step("Verifica PyInstaller disponibile...", 68)

        # Verifica PyInstaller
        try:
            pyinstaller_cmd = _verify_pyinstaller_available()
        except RuntimeError as e:
            raise RuntimeError(str(e))

        log_step("Avvio PyInstaller (timeout: 10 minuti)...", 70)

        dist_dir = temp_dir / "dist"
        dist_dir.mkdir(exist_ok=True)

        # Argomenti PyInstaller
        # ⚠️  CRUCIALE: niente --collect-all né -p temp_dir!
        #     Quelli fanno includere l'intera env Python (torch 3.6GB, cv2, scipy…)
        # PyInstaller di default analizza gli import e raccoglie solo ciò che serve.

        pyinstaller_args = [
            pyinstaller_cmd,
            str(temp_dir / "main.py"),
            "-D",           # directory mode: più veloce, niente blocco "checking PYZ"
            "-w",           # no console window
            "--clean",      # no cache residua
            f"--distpath={dist_dir}",
            f"--workpath={temp_dir / 'build'}",
            f"--specpath={temp_dir}",
            f"--name={game_id}",
            "-y",           # no confirm prompt
            "--collect-all=jsonschema",
            "--collect-all=jsonschema_specifications",
            "--collect-all=rpds",

            # ── Esclude SOLO librerie ML/data science non usate dal gioco ─────
            # cv2, numpy, scipy, pygame, jsonschema → USATI, non escludere!
            "--exclude-module=torch",
            "--exclude-module=torchvision",
            "--exclude-module=torchaudio",
            "--exclude-module=onnxruntime",
            "--exclude-module=sklearn",
            "--exclude-module=matplotlib",
            "--exclude-module=pandas",
            "--exclude-module=pyarrow",
            "--exclude-module=transformers",
            "--exclude-module=tokenizers",
            "--exclude-module=llvmlite",
            "--exclude-module=numba",
            "--exclude-module=lxml",
            "--exclude-module=IPython",
            "--exclude-module=notebook",
            "--exclude-module=jupyter",
        ]

        # Hidden imports obbligatori (import dinamici invisibili all'analisi statica):
        # cv2 (background MP4), numpy, scipy.ndimage (warp prospettico). Stessa fonte
        # unica usata dalla build dell'editor, cosi' i giochi spediti li risolvono sempre.
        from editor.pyinstaller_common import BASE_HIDDEN_IMPORTS
        for h in BASE_HIDDEN_IMPORTS:
            pyinstaller_args.append(f"--hidden-import={h}")

        # Inserisce i minigiochi come hidden imports (import dinamici)
        for mg_id in used_minigames:
            pyinstaller_args.append(f"--hidden-import=engine.minigames.{mg_id}.{mg_id}_game")
            logger.debug(f"[PyInstaller] Aggiunto hidden-import: {mg_id}")

        log_step("Modalità PyInstaller: directory (-D), ML libs escluse", 70)

        # Aggiunge icona se presente nel gioco
        icon_path = games_src / "icon.ico"
        if icon_path.exists():
            pyinstaller_args.append(f"--icon={icon_path}")
            log_step(f"Icona trovata: {icon_path}", 69)

        logger.info(f"[PyInstaller Command] {' '.join(pyinstaller_args[:5])} ... (timeout={PYINSTALLER_TIMEOUT}s)")
        logger.debug(f"[PyInstaller Full Args] {pyinstaller_args}")
        logger.info(f"[PyInstaller PYTHONPATH] {temp_dir}")

        # Lancia PyInstaller con timeout e monitoraggio
        try:
            returncode, pyinstaller_output = _run_pyinstaller_with_timeout(
                pyinstaller_args,
                cwd=str(temp_dir),
                timeout=PYINSTALLER_TIMEOUT,
                progress_callback=progress_callback,
            )

            if returncode == 124:
                raise RuntimeError(
                    f"TIMEOUT: PyInstaller non ha terminato entro {PYINSTALLER_TIMEOUT} secondi.\n"
                    f"Possibili cause:\n"
                    f"  - File di progetto troppo grandi\n"
                    f"  - PyInstaller bloccato\n"
                    f"  - Memoria insufficiente\n"
                    f"Output prima del timeout:\n"
                    + "\n".join(pyinstaller_output[-20:])
                )
            elif returncode != 0:
                error_output = "\n".join(pyinstaller_output[-30:])
                raise RuntimeError(f"PyInstaller fallito (code {returncode}):\n{error_output}")

        except RuntimeError as e:
            raise e

        log_step("PyInstaller completato", 85)

        # Verifica che la directory del build esista
        app_dir = dist_dir / game_id
        if not app_dir.exists():
            # Fallback se PyInstaller ha usato il nome main nonostante la flag
            if (dist_dir / "main").exists():
                app_dir = dist_dir / "main"
            else:
                raise FileNotFoundError(
                    f"App directory non trovato: {app_dir}\n"
                    f"Contenuto dist_dir: {list(dist_dir.iterdir()) if dist_dir.exists() else 'assente'}"
                )

        app_size_mb = sum(f.stat().st_size for f in app_dir.rglob("*") if f.is_file()) / 1024 / 1024
        if app_size_mb > 500:
            raise RuntimeError(
                f"App directory troppo grande ({app_size_mb:.1f} MB). "
                f"PyInstaller ha incluso librerie non necessarie — controlla gli --exclude-module."
            )
        log_step(f"✓ App directory: {app_size_mb:.1f} MB", 88)

        # ── STEP 9: Preparazione cartella di distribuzione ─────────────────────
        # In directory mode l'EXE è in dist/{game_id}/{game_id}.exe.
        # get_base_path() in frozen mode ritorna Path(sys.executable).parent
        # cioè la stessa cartella dove si trova l'EXE.
        # → Tutti gli asset DEVONO stare accanto all'EXE.

        log_step("Preparazione pacchetto...", 90)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # 0. Tenta di chiudere processi del gioco aperti che bloccano le DLL
        if sys.platform == "win32":
            try:
                subprocess.run(["taskkill", "/F", "/IM", f"{game_id}.exe", "/T"], 
                               capture_output=True, timeout=2)
                logger.debug(f"[Cleanup] Chiusura eventuali istanze di {game_id}.exe")
            except Exception: pass
        
        # Cleanup AGGRESSIVO di residui di build precedenti
        # 1. Rimuove la vecchia sottocartella 'main/' se esiste
        old_main_dir = output_dir / "main"
        if old_main_dir.exists():
            shutil.rmtree(old_main_dir, ignore_errors=True)
        
        # 2. Rimuove TUTTI i file ZIP esistenti nella cartella di output
        #    Lo facciamo SEMPRE all'inizio del packaging per garantire che se lo ZIP viene creato
        #    sia quello nuovo, e se non viene creato non ne rimangano di vecchi.
        for z in output_dir.glob("*.zip"):
            try: 
                z.unlink()
                logger.info(f"[Cleanup] Rimosso vecchio archivio: {z.name}")
            except Exception as e: 
                logger.warning(f"[Cleanup] Impossibile rimuovere {z.name}: {e}")

        # app_dir = dist/{game_id}/ (contiene EXE + _internal)
        # pkg_dir = output_dir (root della versione)
        app_dir = dist_dir / game_id
        if not app_dir.exists():
             app_dir = dist_dir / "main" # Fallback per sicurezza
             
        pkg_dir = output_dir

        # Copia i contenuti della cartella dist direttamente nella root della versione
        for item in app_dir.iterdir():
            target = pkg_dir / item.name
            
            # Se è una directory, usiamo dirs_exist_ok=True per permettere il merge
            # se alcuni file sono bloccati e non sono stati cancellati da rmtree
            if item.is_dir():
                if target.exists():
                    shutil.rmtree(target, ignore_errors=True)
                shutil.copytree(item, target, dirs_exist_ok=True)
            else:
                # Se è un file, tentiamo la copia sovrascrivendo
                try:
                    if target.exists(): target.unlink()
                    shutil.copy2(item, target)
                except Exception as e:
                    logger.warning(f"[Copy] Impossibile sovrascrivere {target.name} (file bloccato): {e}")
        
        logger.info(f"[Copy] Asset PyInstaller ({game_id}.exe) copiati in {pkg_dir}")

        # ── Asset accanto all'EXE ──────────────────────────────────────────────
        ignore_dev = shutil.ignore_patterns(
            "__pycache__", "*.pyc", "*.pyo", "*.autosave",
            ".git*", "*.bak", "*.tmp", "*.log", ".DS_Store",
        )

        # config.ini
        shutil.copy2(temp_dir / "config.ini", pkg_dir / "config.ini")
        logger.info(f"[Copy] config.ini → {game_id}/")

        # ── Carica catalogo globale per costruire la mappa id→icona ──────────
        # Verrà usata sia per il catalogo slim che per il logging.
        global_cat_file = engine_src / "data" / "global_objects_catalog.json"
        global_catalog_entries: list[dict] = []
        catalog_id_to_icon: dict[str, str] = {}
        if global_cat_file.exists():
            try:
                cat_data = _load_json(global_cat_file)
                global_catalog_entries = cat_data.get("objects", [])
                for o in global_catalog_entries:
                    icon_rel = o.get("icon", "")
                    if icon_rel:
                        catalog_id_to_icon[o["id"]] = Path(icon_rel).name
            except Exception as e:
                logger.warning(f"[Build] Catalogo globale non leggibile: {e}")

        # games/<game_id>/ con SMART ASSET PACKAGING
        # L'editor ha già pre-copiato i PNG usati in games/{game}/objects/;
        # copiamo tutto quello che c'è (è già filtrato).
        games_dst = pkg_dir / "games" / game_id
        games_dst.parent.mkdir(parents=True, exist_ok=True)

        asset_count, asset_bytes = _copy_smart_assets(games_src, games_dst, catalog_id_to_icon)
        logger.info(f"[Smart Pack] Game objects copiati: {asset_count} file ({asset_bytes/1024/1024:.1f} MB)")

        games_size = sum(f.stat().st_size for f in games_dst.rglob("*") if f.is_file())
        logger.info(f"[Copy] games/{game_id}/ → root/ ({games_size/1024/1024:.1f} MB)")

        # ── engine/data — catalogo SLIM (solo oggetti usati nel gioco) ──────────
        # L'editor ha già costruito games/{game}/objects_catalog.json con le sole
        # entry usate. Qui generiamo un global_objects_catalog.json filtrato che
        # sostituisce quello completo (200+ voci) con le sole voci necessarie.
        # Il runtime lo cerca sempre in engine/data/global_objects_catalog.json:
        # il path rimane identico, ma il file è molto più leggero.
        data_dst = pkg_dir / "engine" / "data"
        data_dst.mkdir(parents=True, exist_ok=True)

        slim_entries = [
            o for o in global_catalog_entries
            if o.get("id") in used_objects
        ]
        slim_catalog = {"objects": slim_entries}
        slim_cat_path = data_dst / "global_objects_catalog.json"
        with open(slim_cat_path, "w", encoding="utf-8") as f:
            json.dump(slim_catalog, f, indent=2, ensure_ascii=False)
        logger.info(
            f"[Smart Pack] Catalogo slim: {len(slim_entries)}/{len(global_catalog_entries)} "
            f"voci ({len(slim_entries)} oggetti usati nel gioco)"
        )

        # Copia altri file in engine/data (es. effects_catalog.json, schemas)
        data_src = engine_src / "data"
        if data_src.exists():
            for f in data_src.iterdir():
                if f.name != "global_objects_catalog.json" and f.is_file():
                    shutil.copy2(f, data_dst / f.name)

        # engine/schemas
        schemas_src = engine_src / "schemas"
        if schemas_src.exists():
            schemas_dst = pkg_dir / "engine" / "schemas"
            if schemas_dst.exists():
                shutil.rmtree(schemas_dst, ignore_errors=True)
            shutil.copytree(schemas_src, schemas_dst, dirs_exist_ok=True)
            logger.info("[Copy] engine/schemas/ → root/")

        # ── engine/assets — suoni, stringhe, musica (NO oggetti PNG: già nel gioco) ──
        # I PNG degli oggetti NON vengono copiati dall'engine: l'editor li ha già
        # messi in games/{game}/objects/ e lo scene_loader li cerca lì prima.
        assets_src = engine_src / "assets"
        assets_dst = pkg_dir / "engine" / "assets"
        assets_dst.mkdir(parents=True, exist_ok=True)

        # 1. Suoni (sempre, sono piccoli)
        sounds_src = assets_src / "sounds"
        if sounds_src.exists():
            shutil.copytree(sounds_src, assets_dst / "sounds", dirs_exist_ok=True)
            logger.info("[Copy] engine/assets/sounds/ → root/")

        # 2. Stringhe globali (localizzazione)
        strings_src = assets_src / "strings"
        if strings_src.exists():
            shutil.copytree(strings_src, assets_dst / "strings", dirs_exist_ok=True)
            logger.info("[Copy] engine/assets/strings/ → root/")

        # 3. Musica globale (smart: solo le tracce referenziate nelle scene)
        mus_src = assets_src / "music"
        if mus_src.exists():
            mus_dst = assets_dst / "music"
            mus_dst.mkdir(parents=True, exist_ok=True)
            m_count = 0
            for track_path in usage["music"]:
                if "engine/assets/music/" in track_path:
                    track_name = track_path.split("/")[-1]
                    if (mus_src / track_name).exists():
                        shutil.copy2(mus_src / track_name, mus_dst / track_name)
                        m_count += 1
            logger.info(f"[Smart Pack] Engine Music: {m_count} tracce copiate")

        # engine/minigames con SMART ASSET PACKAGING
        log_step("Copia asset minigiochi...", 91)
        for mg_id in used_minigames:
            mg_src_folder = engine_src / "minigames" / mg_id
            if mg_src_folder.exists():
                mg_dst_folder = pkg_dir / "engine" / "minigames" / mg_id
                # Copia asset, manifest e localizzazioni escludendo il codice .py (già nel bundle)
                shutil.copytree(
                    mg_src_folder, mg_dst_folder, 
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.py"),
                    dirs_exist_ok=True
                )
                logger.debug(f"[Smart Pack] Asset minigioco copiati: {mg_id}")

        # ── Log contenuto finale ──────────────────────────────────────────────
        exe_in_pkg = pkg_dir / f"{game_id}.exe"
        if exe_in_pkg.exists():
            logger.info(f"[Package] {game_id}.exe : {exe_in_pkg.stat().st_size/1024/1024:.1f} MB")

        pkg_total = sum(f.stat().st_size for f in pkg_dir.rglob("*") if f.is_file())
        logger.info(f"[Package] Totale pkg: {pkg_total/1024/1024:.1f} MB")

        log_step(f"Pacchetto pronto ({pkg_total/1024/1024:.1f} MB)", 93)

        # ── STEP 10: Creazione ZIP ───────────────────────────────────────────
        zip_path = None
        if create_zip:
            # Zippa solo la cartella main/ (contiene EXE + tutti gli asset)
            log_step("Creazione archivio ZIP...", 95)

            zip_name = f"{game_id}_v{version}.zip"
            zip_path = output_dir / zip_name
            skip_suffixes = {".autosave", ".bak", ".tmp", ".log", ".pyc", ".pyo"}

            try:
                # Escludiamo file di servizio dal pacchetto ZIP finale
                exclude_from_zip = {"status.json", "build.log", "pyinstaller.log"}
                
                with ZipFile(zip_path, "w") as zf:
                    file_count = 0
                    total_uncompressed = 0
                    for f in pkg_dir.rglob("*"):
                        if not f.is_file():
                            continue
                        if f.suffix in skip_suffixes or f.name in exclude_from_zip:
                            continue
                        # Se il file è lo stesso zip che stiamo creando, saltalo
                        if f.resolve() == zip_path.resolve():
                            continue
                            
                        arcname = f.relative_to(pkg_dir)   # root del zip = contenuto della versione
                        zf.write(f, arcname=arcname)
                        file_count += 1
                        total_uncompressed += f.stat().st_size
                
                zip_size_mb = zip_path.stat().st_size / 1024 / 1024
                total_mb = total_uncompressed / 1024 / 1024
                ratio = 100 * (1 - zip_size_mb / total_mb) if total_mb > 0 else 0
                
                log_step(f"✓ ZIP creato: {zip_path.name} ({zip_size_mb:.1f} MB)", 98)
                logger.info(f"[ZIP] {zip_size_mb:.1f} MB ({file_count} file, compressione {ratio:.0f}%)")
            except Exception as e:
                logger.error(f"✗ Errore creazione ZIP: {e}")
                raise
        else:
            log_step("Build completata! (ZIP saltato)", 98)

        # ── STEP 11: Cleanup ─────────────────────────────────────────────────
        log_step("Pulizia file temporanei...", 99)

        if temp_dir and temp_dir.exists():
            try:
                shutil.rmtree(temp_dir, ignore_errors=True)
                logger.info(f"[Cleanup] ✓ Cartella temp rimossa: {temp_dir}")
            except Exception as cleanup_err:
                logger.warning(f"[Cleanup] ⚠ Errore pulizia: {cleanup_err}")

        elapsed = time.time() - build_start_time
        log_step(f"✓ Build completato! ({elapsed:.1f}s)", 100)
        logger.info(f"[Build Complete] Tempo totale: {elapsed:.1f}s")

        # Aggiorna la versione in game_config.json (per il prossimo build)
        game_config["version"] = version
        _save_json(game_config_path, game_config)
        logger.info(f"[Version] game_config.json aggiornato a v{version}")

        return {
            "success": True,
            "exe_path": str(pkg_dir / f"{game_id}.exe"),
            "zip_path": str(zip_path) if zip_path else None,
            "error_msg": None,
            "steps_log": steps_log,
        }

    except Exception as e:
        elapsed = time.time() - build_start_time
        logger.exception(f"✗ Errore durante build di '{game_id}' ({elapsed:.1f}s): {e}")
        log_step(f"✗ ERRORE: {str(e)[:100]}", 100)

        # Cleanup in caso di errore
        if temp_dir and temp_dir.exists():
            try:
                shutil.rmtree(temp_dir, ignore_errors=True)
                logger.info(f"[Cleanup Error] ✓ Cartella temp rimossa: {temp_dir}")
            except Exception as cleanup_err:
                logger.warning(f"[Cleanup Error] ⚠ Errore pulizia temp dir: {cleanup_err}")

        return {
            "success": False,
            "exe_path": None,
            "zip_path": None,
            "error_msg": str(e),
            "steps_log": steps_log,
        }
