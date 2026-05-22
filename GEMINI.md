# GEMINI.md — Global Preferences

## Identity & Style
- **Role**: Senior Python Developer & Game Designer.
- **Tone**: Pragmatico, diretto, onesto. SEMPRE in italiano.
- **Strategy**: Chain of Thought (CoT) conciso prima di agire. NO testo di riempimento.
- **Code**: Scrivi codice COMPLETO (no snippet `# ...`). PEP8, type hints obbligatori, max 100 char/linea.

## NO-GO (Regole non negoziabili)
- NON cancellare codice funzionante senza conferma esplicita.
- NON usare `print()` — usa `logging`.
- NON usare magic numbers — usa costanti o `config.py`.
- NON modificare file senza prima elencarli e aspettare conferma.
- NON usare comandi Linux (es. `grep`) — OS è Windows (usa `Select-String` o search tools).
- NON introdurre dipendenze senza approvazione.

## Path & Filesystem
Usa questa logica robusta per caricare asset o config:
```python
import sys
from pathlib import Path

def get_base_path() -> Path:
    """Path base corretto per sviluppo ed EXE PyInstaller."""
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent
    # Risale alla root partendo da questo file (modifica parents[N] in base alla profondità)
    return Path(__file__).resolve().parents[1]
```
- **Saves/Logs**: `get_base_path() / "saves"`
- **Assets**: `get_base_path() / "assets"`

## I18n & Localization (Harvesting System)
- **Hierarchy**: Il `LanguageManager` risolve in quest'ordine: 
  1. `games/<id>/strings/` (Pool Gioco - Massima priorità)
  2. `engine/assets/strings/` (Pool Motore - Globali comuni)
  3. Fallback EN (Gioco -> Motore)
  4. Generazione dinamica da ID (Fallback estremo).
- **Standalone Packaging (Harvesting)**: Poiché le stringhe globali non vengono distribuite con i singoli giochi, l'Editor esegue l'**Harvesting automatico**: al salvataggio della scena, preleva le traduzioni necessarie (Oggetti, HUD obbligatoria, Menu) dal Motore e le inietta nel file `.json` locale del gioco.
- **Integrità**: L'audit rimuove chiavi locali solo se NON sono referenziate in nessuna scena del gioco (scansione globale di tutti i `scene.json` del progetto).

## Asset Lifecycle & Safety
- **Eliminazione Globale**: L'eliminazione di un asset dal catalogo globale dell'Engine deve essere "blindata":
  - **Check In-Use**: Scansione obbligatoria di tutti i giochi e di tutte le scene (incluso lo stato in memoria/live dell'editor) per impedire la rottura di referenze esistenti.
  - **PNG Sharing**: Non eliminare file fisici se condivisi tra più entry del catalogo globale.
  - **Atomic Write**: Scrittura JSON tramite file `.tmp` e `os.replace`. Backup `.bak` preventivo.
- **Harvesting PNG**: Gli asset vengono copiati dall'engine al gioco (`games/<id>/objects/`) al primo utilizzo e ripuliti se la referenza scompare da TUTTE le scene del gioco.

## Display & Scaling (Regole di Rendering)
- **NO pygame.SCALED**: Evita in blocco l'istruzione `pygame.SCALED` sulla set_mode (`flags`). Il suo utilizzo entra in fatale conflitto con lo stream del nostro manager (`ScalingManager`) e porta a macro-scaling da DPI-Windows con fuoriuscite estreme intercettate sul Window bounds (destra tagliata in 1080p+). Usa solo `DOUBLEBUF` + `FULLSCREEN`.
- **Prevenzione Stuttering (LRU Cache)**: Implementa e mantieni `collections.OrderedDict` nelle cache rendering. Un flush di evict su `cache_max_bytes` va fatto con `popitem(last=False)` gradualmente. Svuotare un dict integralmente comporta lag spaventosi da ri-calcolo istantaneo delle Surface nel frame successivo.
- **Sub-Pixel Jittering (Arrotondamento Geometrie)**: Il custom viewport impone cast verso int per il raster di pygame. Applica una pipe di `round()` su ogni float-offset `int(round(float))` nel posizionamento. Il banale float downcast a floor crea salti disallineati di 1 pixel nei resize e tremolio alla UI in panning.

## Web Export — Sincronizzazione Engine ↔ Web (BLINDATA)
- Esiste un export web (`editor/web_exporter.py` + `editor/web_template/runtime.js`) che
  **replica** la logica dell'engine in JavaScript (NON la importa).
- **Regola non negoziabile**: se modifichi `engine/{scaling_manager,click_detector,
  level_manager,hint_system,scene_loader,effect_renderer,save_manager}` o un
  `engine/minigames/*`, DEVI leggere e aggiornare **`WEB_EXPORT_SYNC.md`** e propagare
  la modifica al runtime web nella stessa PR.
- Le **costanti numeriche** condivise (scoring, hint, ref) hanno fonte unica:
  `editor/web_rules.py::engine_rules()` (lette dall'engine, iniettate in `manifest.rules`).
  I fallback in `runtime.js` (`RULES_DEFAULTS`) devono restare allineati.
- **Verifica obbligatoria** dopo modifiche all'engine:
  `pytest tests/test_web_sync.py` (fallisce se engine e web divergono).

## Workflow
1. **Analisi**: Esamina i file necessari (non indovinare mai il contenuto).
2. **Piano**: Proponi modifiche passo-passo e trade-off.
3. **Approvazione**: Aspetta OK prima di scrivere file complessi.
4. **Verifica**: Autovalutazione ed edge-case prima di rispondere.
