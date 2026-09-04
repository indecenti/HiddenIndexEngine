# Contribuire a HiddenIndexEngine

Grazie per l'interesse. Questo documento raccoglie le regole minime per aprire
una issue o una pull request.

## Lingua

Il progetto e' sviluppato in **italiano**: commenti, docstring, documentazione,
messaggi di commit e log. Le issue e le PR possono essere in italiano o in inglese.
Le stringhe rivolte al giocatore passano sempre dal sistema i18n, mai hardcoded.

## Setup

Serve **Python 3.12** su Windows 10/11 (piattaforma testata).

```bash
git clone https://github.com/indecenti/HiddenIndexEngine.git
cd HiddenIndexEngine
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt -r requirements-dev.txt
```

Verifica che tutto giri:

```bash
pytest
python main.py
python run_editor.py
```

## Regole di codice

Sono vincolanti, la CI e la review le applicano.

- **Type hints obbligatori** su tutte le firme pubbliche. PEP 8, righe ~100 caratteri.
- **Mai `print()`** — usa `logging` tramite `engine.utils.get_logger(__name__)`.
- **Mai magic number** — costanti a modulo o valori da configurazione.
- **Mai emoji** in codice, documentazione, UI o output. Il `README.md` storico ne
  contiene: non e' un modello da seguire.
- **Path risorse**: sempre `engine.utils.get_resource_path(...)`. Per le scritture
  `engine.utils.get_writable_path(...)`. Mai path assoluti o `os.getcwd()`.
- **Scritture JSON**: sempre `engine.utils.safe_write_json` (atomico).
  Cancellazioni: `engine.utils.safe_delete` (cestino `.editor_trash/` + audit log).
- **Rendering**: mai `pygame.SCALED` su `set_mode` (va in conflitto con
  `ScalingManager`); usa `DOUBLEBUF` / `FULLSCREEN`. Cache di rendering LRU con
  evict graduale `popitem(last=False)`. Posizionamento con `int(round(float))`.
- **Niente nuove dipendenze** senza discussione preventiva in una issue. Le versioni
  in `requirements*.txt` sono pinned di proposito.

## Regola vincolante: sincronia engine <-> web

L'export web (`editor/web_exporter.py` + `editor/web_template/runtime/`) **replica**
in JavaScript la logica di `engine/scaling_manager.py`, `click_detector.py`,
`level_manager.py`, `hint_system.py`, `scene_loader.py`, `effect_renderer.py`,
`save_manager.py` e di `engine/minigames/*`.

Se tocchi uno di questi file **devi**, nella stessa PR:

1. leggere e aggiornare `docs/web/WEB_EXPORT_SYNC.md`;
2. propagare la modifica al runtime JavaScript;
3. far passare `pytest tests/test_web_sync.py`.

Le costanti condivise hanno fonte unica in `editor/web_rules.py::engine_rules()`.
Una PR che desincronizza Python e JavaScript non viene accettata.

## Modello dati

- Una scena e' `games/<id>/levels/<level>/<scene>/scene.json`, validata contro
  `engine/schemas/scene_schema.json`.
- Le coordinate degli oggetti sono nello **spazio pixel nativo del background**.
- Convenzione ancora: per `rect` la coppia `(x, y)` e' il **top-left**;
  per `circle` e `mask` e' il **centro**.
- Il `catalog_id` si risolve nel catalogo unito globale + locale, con il locale
  che vince a parita' di `id`.

Prima di aprire una PR che tocca le scene: `python tools/audit_catalog.py`.

## Pull request

1. Fai un fork e lavora su un branch dedicato (`feat/...`, `fix/...`, `docs/...`).
2. Un argomento per PR. PR grandi e miste vengono rimandate indietro.
3. `pytest` deve passare in locale prima di aprire la PR.
4. Messaggi di commit in formato Conventional Commits:
   `feat(editor): ...`, `fix(engine): ...`, `docs: ...`, `test: ...`, `refactor: ...`.
5. Descrivi **cosa** cambia e **perche'**. Se e' un fix, indica come riprodurre il bug.
6. Se cambi il comportamento a schermo, allega uno screenshot o una GIF.

## Segnalare bug

Apri una issue con il template Bug report. Servono sempre:

- versione di Python e sistema operativo;
- comando esatto eseguito;
- traceback completo (non uno screenshot del traceback);
- se riguarda una scena: il `scene.json` o l'output di `tools/audit_catalog.py`.

## Asset

Gli asset grafici e audio del repository sono CC BY 4.0 (vedi
[LICENSE-ASSETS.md](LICENSE-ASSETS.md)). **Non aprire PR che aggiungono asset di
terze parti** di cui non puoi dimostrare la licenza: verranno rifiutate.

## Licenza dei contributi

Contribuendo accetti che il tuo codice sia rilasciato sotto **Apache License 2.0**,
la stessa del progetto (vedi [LICENSE](LICENSE)).
