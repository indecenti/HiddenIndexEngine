# Web Export (HTML/JS/Canvas)

Esportazione di un gioco HiddenEngine in un **sito statico** HTML/JS/CSS, pronto
alla pubblicazione online o all'apertura locale (anche con doppio clic).

> Per mantenere allineati engine e web a fronte di modifiche future, vedi
> **[WEB_EXPORT_SYNC.md](WEB_EXPORT_SYNC.md)** (contratto di sincronizzazione).
> Questa e' la parte critica: il runtime web **replica** la logica dell'engine.

---

## 1. Come si usa

```bash
# Esporta un gioco. Build VERSIONATO: build_web/<game>/v<X.Y>/
# + index.html (redirect all'ultima versione) + builds.json (storico).
python -m editor.web_exporter LineVenture

# Forza una versione, oppure output 'flat' senza versionamento:
python -m editor.web_exporter LineVenture --version 2.0
python -m editor.web_exporter LineVenture --out build_web/test_flat
```

La versione parte da `game_config.version`; se `v<version>` esiste gia', il minor
viene auto-incrementato (1.0 -> 1.1 -> ...). Ogni build scrive `version.json`
(gioco, versione, runtime_version, timestamp). `build_web/<game>/index.html`
reindirizza sempre alla versione piu' recente.

Per provarlo:
- **Doppio clic** su `build_web/<game>/index.html` (funziona da `file://`), oppure
- **Doppio clic** su `build_web/<game>/avvia_server.bat` (server locale + browser), oppure
- pubblica la cartella `build_web/<game>/` su qualsiasi hosting statico.

---

## 2. Principio fondante: pacchetto autosufficiente

L'exporter risolve gli asset sorgente da `engine/` e `games/` **in fase di build**,
ma **copia/transcodifica/incorpora tutto** dentro `build_web/<game>/`. A **runtime**
il sito non legge MAI da `engine/` o `games/`: tutti i path puntano a `assets/...`
e i dati (manifest) sono incorporati.

Verifica rapida (deve dare 0 path verso engine/games):
```bash
python3 -c "import json,re; m=open('build_web/LineVenture/manifest.json',encoding='utf-8').read(); \
print('bad:', [p for p in re.findall(r'\"((?:assets|engine|games)/[^\"]+)\"', m) if not p.startswith('assets/')])"
```

---

## 3. Struttura dell'output

```
build_web/
├── index.json                  # CATALOGO aggregato di tutti i giochi (per il portale)
└── <game>/
    ├── index.html              # landing: meta social/SEO + redirect alla versione latest
    ├── game.json               # metadati del gioco (per il portale)
    ├── builds.json             # storico versioni (latest + lista)
    ├── avvia_server.bat        # avvio server locale (Windows)
    └── v<X.Y>/                 # build versionato
        ├── index.html          # shell: meta SEO/OG/PWA + canvas + loading screen
        ├── style.css           # canvas full-viewport + loading screen
        ├── runtime.js          # IL MOTORE WEB (replica dell'engine) — bundle generato da runtime/
        ├── manifest.js         # window.__MANIFEST__ = {...}  (per file://, senza fetch)
        ├── manifest.json       # stesso contenuto (per setup http)
        ├── manifest.webmanifest# PWA (installabile)
        ├── sw.js               # service worker: offline + cache (cache <game>-v<X.Y>)
        ├── version.json        # gioco, versione, runtime_version, timestamp
        └── assets/
            ├── scenes/<level>__<scene>/<bg>.webp|.mp4  # sfondi (WebP q82, cap 1920px) o video
            ├── thumbs/<level>__<scene>.jpg             # anteprime menu (480px)
            ├── icons/<obj>.webp                         # icone oggetti (WebP lossless, piena risoluzione)
            ├── icon.<ext>, menu_poster.<ext>            # favicon/OG + poster menu
            ├── video/<menu>.mp4                         # video di sfondo del menu
            ├── audio/sfx/*.mp3                          # SFX globali (96k mono)
            ├── audio/music/*.mp3                        # musica scene/menu (112k stereo)
            └── minigames/<id>/...                       # asset SOLO dei minigiochi triggerati (+ dipendenze)
```

---

## 4. Componenti

### Exporter — `editor/web_exporter.py`
- `export_web_game(game_id, output_dir)`: punto d'ingresso.
- Costruisce il **manifest** (vedi sezione 5) rispecchiando 1:1 `engine/scene_loader.py`.
- Risolve le icone (prima `games/<id>/`, poi `engine/assets/`), copia sfondi, genera thumbnail.
- Transcodifica audio con **ffmpeg** (SFX engine + musica scene/menu); fallback a copia raw se ffmpeg assente.
- Incorpora le **stringhe** (engine + gioco uniti) e il **tema** UI nel manifest.
- Copia gli asset dei **minigiochi** usati (+ dipendenze, vedi `MINIGAME_ASSET_DEPS`).
- Genera `runtime.js` concatenando i moduli di `runtime/` (vedi sotto), includendo
  **solo i minigiochi triggerati** nelle scene (`_bundle_runtime`).

### Runtime — `editor/web_template/{index.html,style.css}` + `editor/web_template/runtime/`
- `index.html`/`style.css`: template statici copiati in ogni export.
- `runtime/`: sorgenti modulari (script classici, niente ES module → funzionano da `file://`):
  - `core.js`: `ScalingManager`, hit-test, rendering oggetti, `AudioEngine`, `Theme`,
    `Save`, `RULES_DEFAULTS`, effetti; inizializza `window.MINIGAME_CLASSES`.
  - `game.js`: classe `Game` (state machine, scene, HUD, hint, pausa, impostazioni, results).
  - `minigames/<id>.js`: un file per minigioco; ognuno si **auto-registra** in
    `window.MINIGAME_CLASSES["<id>"]`. Aggiungere un minigioco = creare il file.
  - `bootstrap.js`: `main()` (carica manifest, istanzia `Game`).
- L'exporter li concatena in un unico `runtime.js` (bundle), includendo solo i
  minigiochi effettivamente usati dal gioco.

---

## 5. Manifest (formato dati)

```jsonc
{
  "game_id": "LineVenture",
  "title_key": "game_title",
  "default_language": "it",
  "ref": { "w": 1280, "h": 720 },
  "theme": { "id": "cyber_neon", "colors": {...}, "effects": {...} },
  "languages": ["de","en","es","fr","it"],
  "strings": { "it": {...}, "en": {...}, ... },          // engine + gioco uniti
  "sfx": { "found": "assets/audio/sfx/found.mp3", ... }, // found/complete/miss/click/levelup
  "menu_music": "assets/audio/music/..." | null,
  "minigames": ["tetran"],                                // id implementati e usati
  "minigame_strings": { "tetran": { "it": {...} } },      // namespaced per minigioco
  "levels": [{
    "id": "One", "name_key": "One_name",
    "scenes": [{
      "id": "scene_nuova", "order": 1, "time_limit": 120,
      "background": "assets/scenes/One__scene_nuova/camping.png",
      "thumb": "assets/thumbs/One__scene_nuova.jpg",
      "background_scale": 1.0, "bg_w": 4096, "bg_h": 2304,
      "music": null,
      "effects": [{ "type":"glint", "x":..,"y":..,"radius":..,"color":[..],"intensity":..,"pulse_min":..,"pulse_period":.. }],
      "bubble_tips": [{ "x":..,"y":..,"text_key":"..","trigger":"start_scene","width":..,"height":..,"color":[..] }],
      "flashlight": false, "flashlight_radius": 150.0,
      "random_layer_selection": false, "auto_random_finds": true, "num_random_finds": 12,
      "objects": [{
        "instance_id":"ca_book_stack_adv", "catalog_id":"ca_book_stack_adv",
        "label_key":"obj_..", "icon":"assets/icons/..png",
        "x":64, "y":1793, "detection_type":"rect", "radius":0, "width":355, "height":290,
        "hint_delay":30, "layer":"objects_mid", "layer_z":20,
        "is_goal":true, "always_show":false,
        "rotation":0, "flip_x":false, "flip_y":false, "alpha":255,
        "grayscale":false, "grayscale_factor":1.0, "color_filter":[255,255,255],
        "corners":[[0,0],[0,0],[0,0],[0,0]], "scale":1.0,
        "minigame_trigger": null
      }]
    }]
  }]
}
```

I campi degli oggetti rispecchiano **esattamente** la costruzione di
`SceneObject` in `engine/scene_loader.py` (stessi default; nessun default di
catalogo applicato a runtime).

---

## 6. Funzionalita' implementate

| Area | Stato | Note |
|---|---|---|
| Coordinate oggetti (rect/cerchio/rotazione/flip/warp) | OK | pixel-perfect vs engine |
| Filtri oggetto (stretch/alpha/grayscale/color_filter) | OK | **pixel-esatti** (grayscale+tint via feColorMatrix sRGB) |
| Hit detection (ellisse/rect ruotato/poligono warp/ray casting) | OK | identica a `click_detector.py` |
| Sfondi (immagine **e video**) + icone + thumbnail | OK | copiati in `assets/`; video via `<video>` in loop |
| Video di sfondo menu/scena (.mp4/.webm) | OK | dimensioni via ffprobe, anteprima dal primo frame |
| Audio (SFX + musica) compresso | OK | `<audio>` (no fetch, file://-friendly) |
| HUD con nomi oggetti | OK | barra inferiore, palette colori, max 7 |
| Hint (manuale + auto-glow) | OK | 2 gratis, cooldown 20s, penalita', max 3 |
| Pausa + menu pausa | OK | timer congelato |
| Effetti glint/smoke/flies | OK | matematica 1:1 |
| Torcia (flashlight) + hint-flash | OK | maschera offscreen |
| Fumetti bubble_tip (`start_scene` + `end_scene`) | OK | coda; end_scene prima dei results |
| Particelle + popup punteggio + screen shake | OK | feedback alla scoperta |
| Versionamento build (versioni, version.json, builds.json, redirect) | OK | auto-incremento |
| Meta SEO/Open Graph/Twitter + favicon + theme-color | OK | per gioco, anteprime social |
| PWA (manifest.webmanifest, installabile, landscape) | OK | icona + theme/bg color |
| Loading screen + transizioni fade + hover card menu | OK | UX moderna |
| Catalogo per portale (game.json + build_web/index.json) | OK | metadati per piattaforma |
| Selezione casuale layer/oggetti | OK | `random_layer_selection`/`auto_random_finds` |
| Salvataggio + lock (localStorage) | OK | scene/livelli, autosave, stelle |
| Impostazioni (volume + 5 lingue) | OK | persistite, cambio lingua live |
| Temi UI (cyber_neon/mystery/...) | OK | colori dal manifest |
| Level-select curata (thumb/stelle/lock) | OK | a tema |
| Results appaganti (stelle/coriandoli/score) | OK | scoring 1:1 |
| Minigiochi | tetran, arcade_eleven, asteroids | host + interfaccia + asset reali |

---

## 7. Limiti noti / non ancora portato

- **Minigiochi**: portati i 3 usati dai giochi (tetran, arcade_eleven, asteroids).
  Mancano: centipede, minipong, slot_classic, spot_differences, sudoku, tower.
- **detection_type `mask`** pixel-perfect: fallback a cerchio (0 usi nei giochi attuali).
- **intro zoom** e **transizioni fade** tra scene: non portati (estetica minore).
- Multi-touch nei minigiochi: un controllo alla volta (tastiera completa su desktop).

---

## 8. Verifica (in assenza di screenshot)

La fedelta' e' stata validata via **ispezione di stato** e **campionamento pixel**
sul canvas (lo strumento screenshot della preview era inaffidabile). Esempi:
- `bg_to_screen` JS vs `ScalingManager` Python: delta < 0.005px su tutti gli oggetti.
- Hit-test rect ruotato (270.1 gradi): 961/961 celle identiche a `ClickDetector`.
- Round-trip render→click: ogni oggetto colpito al proprio centro renderizzato.
