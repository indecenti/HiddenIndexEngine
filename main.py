"""
main.py

Punto di ingresso principale per l'HiddenEngine.
Legge la configurazione, gli argomenti da riga di comando e avvia il core del gioco.
"""

import sys
import os
import traceback
import argparse
import configparser


# ─────────────────────────────────────────────────────────────────────────────
# Global crash handler — Android-only behavior
# ─────────────────────────────────────────────────────────────────────────────
# Su Android non abbiamo una console: senza questo hook un crash al boot
# (ModuleNotFoundError, SyntaxError, init pygame fallito, ecc.) chiude l'app
# senza lasciare tracce visibili all'utente. Scriviamo lo stack trace su file
# in PIÙ posti (tentativi a cascata) così è recuperabile via:
#   - adb pull /sdcard/Download/lineventure-crash.log    (USB)
#   - file manager → Android/data/<package>/files/saves/crash.log
# Su Windows/desktop questo hook NON scrive niente (is_android è False) e
# il flow esistente di sys.__excepthook__ resta invariato.

def _is_android() -> bool:
    return 'ANDROID_ARGUMENT' in os.environ or 'P4A_BOOTSTRAP' in os.environ


def _android_crash_handler(exc_type, exc_value, exc_tb):
    # 1) tenta di scrivere su file (best-effort, mai re-raise)
    tb_text = ''.join(traceback.format_exception(exc_type, exc_value, exc_tb))
    env_dump = '\n'.join(f'{k}={v}' for k, v in sorted(os.environ.items()))
    path_dump = '\n'.join(sys.path)
    payload = (
        f"=== HiddenEngine CRASH ===\n"
        f"Python: {sys.version}\n\n"
        f"--- TRACEBACK ---\n{tb_text}\n"
        f"--- sys.path ---\n{path_dump}\n\n"
        f"--- ENVIRONMENT ---\n{env_dump}\n"
    )

    candidates = []
    # /sdcard/Download è il path più comodo da raggiungere col file manager
    candidates.append('/sdcard/Download/lineventure-crash.log')
    # internal storage dell'app (sempre scrivibile, raggiungibile via adb o
    # file manager → Android/data/<package>/files/saves/)
    ap = os.environ.get('ANDROID_PRIVATE')
    if ap:
        candidates.append(os.path.join(ap, 'saves', 'crash.log'))
        candidates.append(os.path.join(ap, 'crash.log'))

    for path in candidates:
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, 'w', encoding='utf-8') as f:
                f.write(payload)
            print(f'[CRASH] Saved to {path}', file=sys.stderr)
        except Exception:
            continue

    # 2) delega all'hook standard (stampa anche su logcat via stderr)
    sys.__excepthook__(exc_type, exc_value, exc_tb)


if _is_android():
    sys.excepthook = _android_crash_handler


from engine.utils import setup_logging, get_base_path, get_user_config_path, get_logger
from engine.core import EngineCore

def main() -> None:
    """Entry point principale."""
    setup_logging()
    logger = get_logger("main")
    logger.info("Avvio di HiddenEngine...")
    
    # Argomenti CLI
    parser = argparse.ArgumentParser(description="Avvia HiddenEngine.")
    parser.add_argument("--game", type=str, help="Forza il gioco da caricare (es. villa_segreta)")
    parser.add_argument("--fullscreen", action="store_true", help="Avvia in fullscreen")
    parser.add_argument("--minigame", type=str, help="Avvia un minigioco specifico subito")
    parser.add_argument("--lang", type=str, help="Forza la lingua (it, en, es, fr, de)")
    args = parser.parse_args()
    
    # Lettura config.ini: prima i DEFAULT bundlati (get_base_path, read-only su
    # Android), poi gli OVERRIDE utente dal path scrivibile (get_user_config_path)
    # che li sovrascrive. Su desktop i due path coincidono (un unico file in root).
    base_config_path = get_base_path() / "config.ini"
    user_config_path = get_user_config_path()
    config = configparser.ConfigParser()

    read_targets, seen = [], set()
    for p in (base_config_path, user_config_path):
        try:
            key = p.resolve()
        except Exception:
            key = p
        if p.exists() and key not in seen:
            seen.add(key)
            read_targets.append(p)

    if read_targets:
        config.read(read_targets, encoding="utf-8")  # l'ultimo (utente) ha precedenza
        logger.info(f"Config letta da: {[str(p) for p in read_targets]}")
    else:
        logger.warning(f"Nessun config.ini trovato ({base_config_path}). Default integrati.")

    if not config.has_section("engine"):
        config.add_section("engine")
        config.set("engine", "default_game", "")
        
    # Risoluzione Gioco
    game_id = args.game or config.get("engine", "default_game", fallback="")
    if not game_id:
        logger.error("Nessun gioco specificato (né in CLI né in config.ini).")
        sys.exit(1)
        
    # Avvio vero e proprio
    try:
        engine = EngineCore(game_id=game_id, config=config, cli_args=args)
        engine.run()
    except Exception as e:
        logger.exception(f"Errore fatale: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
