"""
main.py

Punto di ingresso principale per l'HiddenEngine.
Legge la configurazione, gli argomenti da riga di comando e avvia il core del gioco.
"""

import sys
import argparse
import configparser

from engine.utils import setup_logging, get_base_path, get_logger
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
    
    # Lettura config.ini
    config_path = get_base_path() / "config.ini"
    config = configparser.ConfigParser()
    
    if config_path.exists():
        config.read(config_path, encoding="utf-8")
    else:
        logger.warning(f"File {config_path} non trovato. Fallback sui default integrati.")
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
