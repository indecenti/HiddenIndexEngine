# CLAUDE.md — HiddenIndexEngine (HIE)

Guida operativa per Claude Code su questo repository. Le regole qui sono vincolanti.
Per le preferenze globali condivise con altri tool vedi anche `GEMINI.md`.

## Cos'e' HIE

Motore modulare in **Python 3.12 + pygame 2.6.1** per **Hidden Object Games (HOG)**.
Tre target di distribuzione dallo stesso progetto:

- **Desktop** (Windows): EXE via PyInstaller.
- **Web**: export che *replica* la logica engine in JavaScript (non la importa).
- **Android**: APK/AAB via python-for-android / buildozer (WSL).

Include un **editor visuale** completo (`editor/`) per creare scene, posizionare
oggetti, gestire catalogo/tag/lingue e lanciare le build.

## Layout del repository

| Path | Contenuto |
|------|-----------|
| `engine/` | Runtime del gioco: `core.py`, `scene_loader.py`, `catalog_manager.py`, `menu_system.py`, `menu_skins/`, `minigames/`, `hud_manager.py`, `scaling_manager.py`, `haptics.py`. |
| `engine/data/` | Cataloghi globali `global_*_catalog.json` (cartoon, lineart, ...). |
| `engine/assets/` | Asset condivisi: `objects_cartoon/`, `objects_lineart/`, `strings/`. |
| `engine/schemas/` | JSON Schema (`scene_schema.json`, `catalog_schema.json`). |
| `editor/` | Editor di livelli (mixins, build desktop/android, web exporter). |
| `games/<id>/` | Giochi: `game_config.json`, `objects_catalog.json`, `levels/<level>/<scene>/scene.json`, `strings/`. |
| `tools/` | Utility di sviluppo (audit catalogo, normalizzazione tag, preview). |
| `tools/hie_mcp_server.py` | **MCP server del progetto** (render headless, validazione scene, ricerca catalogo). |
| `.claude/skills/` | Skill di progetto (build-apk, run-game, add-asset, validate-scene). |
| `scripts/` | Script shell per build Android (WSL). |
| `docs/` | Documentazione organizzata per area (vedi `docs/README.md`). |
| `scratch/` | Script usa-e-getta e PNG temporanei. NON e' codice di produzione. |

## Comandi

```powershell
# Gioco (usa default_game da config.ini, oppure --game)
python main.py
python main.py --game Malonno_Survivors --lang it
python main.py --minigame sudoku        # avvia un minigioco diretto

# Editor di livelli
python run_editor.py

# Test
pytest                                   # suite completa
pytest tests/test_web_sync.py            # contratto engine <-> web (vedi sotto)

# Dipendenze
pip install -r requirements.txt -r requirements-dev.txt
```

Build desktop/web/Android si lanciano dall'editor; gli script Android stanno in
`scripts/` (richiedono WSL). Vedi `docs/build/` e `docs/android/`.

## Modello dati (scene + catalogo)

- Una **scena** e' `games/<id>/levels/<level>/<scene>/scene.json`, validata contro
  `engine/schemas/scene_schema.json`. Le coordinate oggetti sono nello **spazio
  pixel nativo del background** (`background.png` accanto al `scene.json`).
- Ogni oggetto ha `catalog_id` + `x,y` + `detection_type` (`circle`/`rect`/`mask`).
  Convenzione ancora: per **rect** `(x,y)` e' il **top-left** (centro = `x+w/2, y+h/2`);
  per **circle/mask** `(x,y)` e' il **centro** (dimensione = `width|radius*2`).
- Il `catalog_id` si risolve nel **catalogo unito**: `catalog_manager.load_catalog(game_id)`
  fonde globale (`engine/data/global_*_catalog.json`) + locale (`games/<id>/objects_catalog.json`),
  con il locale che sovrascrive il globale a parita' di `id`.
- L'immagine di un oggetto (`icon` nel catalogo) si cerca prima in
  `games/<id>/<icon>`, poi in `engine/assets/<icon>`.

## Convenzioni vincolanti

- **Lingua**: italiano nelle risposte, nei commenti e nella doc. Tono diretto, niente filler.
- **Mai emoji** in codice, doc, UI o output verso l'utente. (Il `README.md` storico ne contiene: non e' un modello da seguire.)
- **Mai `print()`** — usa `logging` via `engine.utils.get_logger(__name__)`.
- **Mai magic number** — costanti o config.
- **Path risorse**: usa `engine.utils.get_resource_path(...)`; scritture via `get_writable_path(...)`.
- **Scritture JSON**: sempre `engine.utils.safe_write_json` (atomico). Cancellazioni: `safe_delete` (cestino `.editor_trash/` + audit log).
- **Type hints obbligatori**, PEP8, max ~100 char/linea, codice completo (no snippet con `# ...`).
- **Niente nuove dipendenze** senza approvazione esplicita. Le versioni in `requirements*.txt` sono pinned.
- **Rendering**: mai `pygame.SCALED` su `set_mode` (conflitto con `ScalingManager`); usa `DOUBLEBUF`/`FULLSCREEN`. Cache rendering LRU con evict graduale `popitem(last=False)`. Posizionamento con `int(round(float))`.

## Regola BLINDATA: sync engine <-> web

L'export web (`editor/web_exporter.py` + `editor/web_template/runtime/`) **replica** in
JavaScript la logica di `engine/{scaling_manager,click_detector,level_manager,hint_system,
scene_loader,effect_renderer,save_manager}` e di `engine/minigames/*`. Se modifichi uno di
questi, DEVI leggere e aggiornare **`docs/web/WEB_EXPORT_SYNC.md`** e propagare la modifica al
runtime web nella stessa change. Le costanti condivise hanno fonte unica in
`editor/web_rules.py::engine_rules()`. Verifica obbligatoria: `pytest tests/test_web_sync.py`.

## i18n

**EN e' la lingua di default e l'UNICO fallback** (`engine.language_manager.DEFAULT_LANG` /
`FALLBACK_LANG`, `editor.constants.DEFAULT_LANG`). `LanguageManager` risolve:
`games/<id>/strings/` -> `engine/assets/strings/` -> fallback EN -> default inline -> chiave.

Niente testo hardcoded nella UI: si usa `self._TR("chiave", "English default")` (o `tr(...)` da
`engine.language_manager` nei modali standalone) e `str.format` con placeholder nominali. Ogni
chiave nuova va aggiunta a **tutte e 5** le lingue in `engine/assets/strings/`.
Verifica obbligatoria: `pytest tests/test_editor_i18n.py`. Dettagli in `docs/engine/I18N.md`.

Al salvataggio scena l'editor fa **harvesting**: copia nel `.json` locale del gioco le stringhe
necessarie (oggetti, HUD, menu) cosi' il gioco e' distribuibile standalone.

## Tooling per Claude

- **MCP** (`tools/hie_mcp_server.py`): registrato in `.mcp.json`. Espone `render_scene`,
  `render_asset` (PNG headless via engine), `validate_scene`, `search_catalog`,
  `check_missing_assets`, `list_games`, `build_status`. Si ricarica al riavvio del client.
- **Skill** (`.claude/skills/`): `build-apk`, `run-game`, `add-asset`, `validate-scene`.

## Stato e prossimi passi

Vedi `docs/ROADMAP.md` per lo stato per area e il lavoro residuo.
