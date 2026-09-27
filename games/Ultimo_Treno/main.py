import sys
import importlib.util
from pathlib import Path

# Trova la root del motore (2 livelli sopra)
root = Path(__file__).resolve().parents[2]
engine_main_p = root / "main.py"

if __name__ == "__main__":
    if not engine_main_p.exists():
        print(f"ERRORE: Motore non trovato in {engine_main_p}")
        sys.exit(1)

    spec = importlib.util.spec_from_file_location("engine_entry", engine_main_p)
    engine_module = importlib.util.module_from_spec(spec)
    
    # IMPORTANTE: Aggiunge la root al path per le dipendenze del motore (es. engine.utils)
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
        
    spec.loader.exec_module(engine_module)

    # Forza il gioco da caricare basandosi sul nome di questa cartella
    game_id = Path(__file__).parent.name
    print(f"[LAUNCHER] Avvio progetto: {game_id}")
    
    # Override degli argomenti CLI
    sys.argv = [sys.argv[0], "--game", game_id]
    
    # Avvia l'engine
    engine_module.main()
