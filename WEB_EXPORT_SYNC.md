# Web Export — Contratto di Sincronizzazione Engine ↔ Web

> SCOLPITO NELLA PIETRA. Leggi questo prima di modificare l'engine.

Il runtime web (sorgenti modulari in `editor/web_template/runtime/`: `core.js`,
`game.js`, `minigames/<id>.js`, `bootstrap.js` — concatenati in `runtime.js` da
`web_exporter._bundle_runtime`) **non importa** codice Python:
**replica** la logica dell'engine in JavaScript. Quindi ogni modifica a una formula,
costante o struttura dati elencata qui sotto **DEVE** essere propagata al web,
altrimenti il gioco esportato diverge in silenzio (bug invisibili: oggetti fuori
posto, punteggi sbagliati, click che non centrano).

## Regola d'oro
Se tocchi uno dei file/valori nella colonna "ENGINE", aggiorna il corrispondente
"WEB" nella stessa PR e ri-esegui la verifica (vedi in fondo). Le **strutture dati**
fluiscono via `editor/web_exporter.py` (manifest); le **formule** sono duplicate in
`runtime.js`.

## Enforcement automatico (gia' attivo)
- **Costanti numeriche** (scoring, hint, ref): fonte unica `editor/web_rules.py::engine_rules()`,
  che LEGGE i valori dall'engine e li inietta in `manifest.rules`. Il runtime usa
  `this.R` = `{RULES_DEFAULTS, ...manifest.rules}`. Cambiare la costante nell'engine la
  propaga al web al prossimo export, automaticamente.
- **Test anti-drift (costanti)**: `pytest tests/test_web_sync.py::test_runtime_defaults_match_engine`
  verifica che engine e `RULES_DEFAULTS` (fallback in `runtime/core.js`) siano allineati
  (incluse `miss_penalty_curve` e `miss_combo_window`); fallisce in caso di drift.
- **Test di parita' COMPORTAMENTALE** (oltre alle costanti): esegue le VERE formule JS via
  `node` (harness `tests/js/score_parity_harness.js`) e le confronta con l'engine su golden
  vector — `test_scene_score_parity_python_vs_js` (bonus/stelle/score di fine scena) e
  `test_miss_penalty_parity_python_vs_js` (curva penalita' miss). Una divergenza di FORMULA,
  non solo di costante, diventa un fallimento di test.
- **Smoke scene reali**: `tests/test_scene_smoke.py` carica ogni `scene.json` tramite il vero
  `SceneLoader` (validazione + join catalogo) e verifica che i goal siano colpibili.
- Restano **manuali** (non automatizzabili come valori): le **formule** di proiezione,
  hit-test, effetti, torcia — elencate qui sotto. Toccarle nell'engine richiede di
  aggiornare a mano i moduli in `editor/web_template/runtime/`.

---

## A. Coordinate e rendering (CRITICO — la missione)

| ENGINE | WEB | Cosa deve combaciare |
|---|---|---|
| `engine/scaling_manager.py` `set_background`, `bg_to_screen`, `screen_to_bg`, `REF_W/REF_H=1280/720` | `runtime.js` class `ScalingManager` | Lettera per lettera: letterbox `fit=min(sw/(bw*s),sh/(bh*s))`, `display_scale=fit*s`, centratura. |
| `engine/core.py` rendering oggetti (centro/size, ordine trasformazioni) | `runtime.js` `objCenterAndSize`, `drawObject` | rect: centro = x+w/2; cerchio: centro = x,y. Ordine: scale → warp → flip → **rotate** → alpha. |
| Rotazione: Pygame `rotozoom` = CCW per angolo positivo | `runtime.js` `ctx.rotate(-rotation*PI/180)` | Canvas ha Y in giu': si ruota di **-angolo**. NON cambiare il segno. |
| `engine/click_detector.py` `_hit_circle/_hit_rect/_rotate_point/_is_point_in_poly`, warp, flip | `runtime.js` `hitCircle/hitRect/rotatePoint/pointInPoly/warpPoly` | Stesse formule (ellisse, rotazione punto di -angolo, ray casting). |
| `engine/effect_renderer.py` warp dei corners | `runtime.js` `warpPoly` + `drawImageQuad` (2 triangoli) | Il poligono di hit e quello di render usano lo stesso `warpPoly`. |
| **Stretch**: icona scalata a `width`×`height` (hitbox), non all'aspect nativo | `drawObject` (`iconW/iconH = w/h * bg_display_scale * scale`) | esatto |
| **Opacità**: `surface.set_alpha(obj.alpha)` | `drawObject` `globalAlpha = alpha/255` | esatto |
| **Grayscale**: `engine/utils.py:apply_grayscale` (luma Rec.601 0.299/0.587/0.114, `out=c*(1-f)+luma*f`, sRGB) | `processedIcon` + `_grayFilterUrl` (feColorMatrix SVG sRGB) | **esatto** (delta 0). Se cambi le coefficienti/formula in `apply_grayscale`, aggiorna `_grayFilterUrl`. |
| **color_filter (tinta)**: `BLEND_RGBA_MULT` (moltiplicazione) | `processedIcon` (composite `multiply` + `destination-in`) | moltiplicazione per canale |
| **flip_x/flip_y**: `pygame.transform.flip` | `drawObject` `ctx.scale(±1,±1)` | esatto |
| Ordine filtri engine: scale→warp→flip→rotate→grayscale→color_filter→alpha | web: grayscale/tint in `processedIcon`, poi flip/rotate/alpha in `drawObject` | equivalente (operazioni per-pixel commutano con le geometriche) |

Spazio coordinate oggetti: **pixel del background originale** (`bg_w`×`bg_h`).
rect → x/y top-left; circle → x/y centro. Esportati 1:1 nel manifest.

---

## B. Scoring e stelle

| ENGINE (`engine/level_manager.py`) | Valore | WEB (`runtime.js`) |
|---|---|---|
| `POINTS_PER_OBJECT` | 100 | `POINTS_PER_OBJECT` |
| `BONUS_TIME_MAX` | 500 | `BONUS_TIME_MAX` |
| `STAR_MULTIPLIER` | `{1:1, 2:1, 3:2}` | `STAR_MULTIPLIER` |
| `MISS_PENALTY_TIME` | 5.0 s | `miss_time_penalty` |
| `MISS_PENALTY_CURVE` progressiva sui miss consecutivi (finestra `MISS_COMBO_WINDOW`=1.5s) | `[25,50,100,150,300,500]` | `miss_penalty_curve` + `_missPenalty`/stato consecutivo in `_onPointer`; **lo score puo' andare NEGATIVO** (niente floor), come l'engine |
| `bonus = int(time_ratio * BONUS_TIME_MAX)` — **troncamento** verso zero | — | `Math.trunc(...)` in `_doFinish` (NON `Math.round`) |
| Stelle: 3 se all-found e `bonus/BONUS_TIME_MAX >= 0.66`; 2 se all-found; 1 altrimenti | — | `_doFinish` + `bonus_ratio_3star=0.66` |
| `score = (scene_score + bonus) * STAR_MULTIPLIER[stars]` — aritmetica intera, **nessun arrotondamento** | — | `_doFinish` (nessun `Math.round` esterno) |
| Sorgente unica testabile: `LevelManager.compute_scene_score` / `LevelManager.miss_penalty` | — | pinnati da `test_scene_score_parity_*` / `test_miss_penalty_parity_*` |

---

## C. Hint (`engine/hint_system.py` + `level_manager.RewardTracker`)

| ENGINE | Valore | WEB |
|---|---|---|
| `initial_hints` | 2 | `HINT_FREE` |
| `manual_hint_cooldown_max` | 20.0 s | `HINT_COOLDOWN` |
| `hint_penalties` | `[0,-50,-75,-100]` | `HINT_PENALTIES=[50,75,100]` |
| `max_hints_before_disable` | 3 | `HINT_MAX_USES` |
| Increment hint guadagnati | 0.20 / 0.143 / 0.112 / 0.05 | `_awardHintProgress` |
| `hint_delay` per oggetto (default) | 30 | `HINT_AUTO_DEFAULT_DELAY` (e campo `hint_delay`) |

Nota: l'engine usa `combo_thresholds` (di norma vuoto) per un bonus extra agli
increment; il web replica il caso senza combo. Se l'engine inizia a usare combo,
aggiornare `_awardHintProgress`.

---

## D. HUD nomi oggetti (`engine/hud_manager.py`)

| ENGINE | WEB |
|---|---|
| `max_visible_goals` = 7 | `HUD_MAX_VISIBLE` |
| Palette colori nomi | `HUD_NAME_COLORS` (6 colori) |
| Layout: blocco sinistro `[0:4]`, destro `[4:7]`, 2 righe ciascuno | `_renderHud` |
| Found → rimosso dalla lista | `goals.filter(!found)` |

---

## E. Effetti ambientali (`engine/effect_renderer.py`)

| ENGINE | WEB | Note |
|---|---|---|
| `update_effect_state`: glint `t+=dt/period`, altri `t+=dt*period` (period default 2.0) | `_updateAndDrawEffects` | |
| `draw_glint_effect` (pulse, glow additivo, core>0.3) | `drawGlint` | blending additivo = `globalCompositeOperation="lighter"` |
| `draw_smoke_effect` (12 puff × 5 blob × 3 layer) | `drawSmoke` | port diretto del loop |
| `draw_flies_effect` (intensity*40 particelle) | `drawFlies` | |
| Posizione: bg-space → screen via `bg_to_screen` | idem | scala raggio per `bg_display_scale` |

---

## F. Torcia (`engine/core.py` `_draw_flashlight_effect`)

| ENGINE | WEB |
|---|---|
| `alpha = clip(dist^1.4 * 255)`, fuori cerchio = nero pieno | `_renderFlashlight` (gradiente destination-out su canvas **offscreen**) |
| `radius = flashlight_radius * 1.15` | idem (scalato per coerenza visiva su canvas variabile) |
| Hint in scena torcia = flash 5s che illumina tutto | `hintFlashUntil = now + 5000` |

---

## G. Caricamento scena e selezione casuale (`engine/scene_loader.py`)

| ENGINE | WEB | Critico |
|---|---|---|
| `LAYER_Z` (mappa layer→z) | exporter `LAYER_Z` | usato per `layer_z` |
| Default `SceneObject` (radius 30, detection "circle", width/height 0, ...) | exporter `_build_object` | **non** applicare default di catalogo a runtime |
| `random_layer_selection`: sceglie low/mid/high a caso, filtra | `_buildSceneObjects` | a OGNI avvio scena |
| `auto_random_finds` + `num_random_finds`: ridisegna `is_goal` casuale | `_buildSceneObjects` | shuffle, fixed=`always_show` |

Questi flag sono nel manifest per scena; la logica casuale gira nel web.

---

## H. Salvataggio e lock (`engine/save_manager.py`)

| ENGINE | WEB (`runtime.js` `Save`, localStorage) |
|---|---|
| Struttura: `scores/stars/unlocked_scenes/unlocked_levels` | identica |
| Tiene il punteggio/stelle migliori | `Save.record` |
| Sblocco scena successiva al completamento; ultima scena → sblocca livello | `Save.record` |
| Primo livello/scena sbloccati di default | `Save.isLevelUnlocked` (idx 0) |

---

## I. Minigiochi (`engine/minigames/*`)

Interfaccia engine `BaseMinigame` (`start/handle_event/update/draw/finish`) →
interfaccia web `start()/pointer()/key()/update(dt)/draw(ctx,W,H)` + `host._minigameDone({success,score})`.

| ENGINE | WEB | Asset |
|---|---|---|
| `tetran/tetran_game.py` | `runtime.js` `TetranGame` | `assets/minigames/tetran/` (PNG reali) |
| `arcade_eleven/arcade_eleven_game.py` | `ArcadeEleven` | carte da **tower** (dipendenza) |
| `asteroids/asteroids_game.py` + `asteroids_config.py` | `AsteroidsGame` | suoni `assets/minigames/asteroids/` |

`_on_minigame_complete` (core.py) → `host._minigameDone`: l'oggetto-trigger viene
SEMPRE segnato `found`, si aggiunge lo score, sfx victory/neutro.

**Dipendenze asset tra minigiochi**: `editor/web_exporter.py` `MINIGAME_ASSET_DEPS`
(es. `arcade_eleven` → `tower`). Se un minigioco inizia a usare asset di un altro,
aggiungere la voce qui.

Costanti minigiochi (es. `asteroids_config.py`: velocita', punti, vite) sono
duplicate nelle rispettive classi JS (`AST`, `TET_*`, `AE_*`). Se cambiano, aggiornare.

---

## J. Stringhe / lingue

- 5 lingue: it, en, de, es, fr (`engine/language_manager.py`).
- Stringhe engine + gioco unite nel manifest (`_collect_strings`). Il gioco vince.
- Stringhe minigiochi **namespaced** per id (`minigame_strings`) per evitare collisioni.
- Chrome UI tradotto da `UI_STRINGS` (in `runtime.js`) come fallback.

---

## Checklist quando modifichi l'engine

1. La modifica tocca una riga in questo documento? Se sì, aggiorna il WEB corrispondente.
2. Hai cambiato una **struttura dati** di scena/oggetto/salvataggio? Aggiorna
   `editor/web_exporter.py` (manifest) e i lettori in `runtime/game.js` (o `core.js`).
3. Hai cambiato una **costante/formula**? Aggiorna il valore in `runtime/core.js`
   (`RULES_DEFAULTS`/formule) o nel modulo `runtime/minigames/<id>.js` interessato.
4. Hai aggiunto un nuovo tipo di effetto / detection / campo oggetto? Esportalo e
   gestiscilo nel runtime (o documentane l'esclusione in WEB_EXPORT.md §7).
5. Ri-esporta e verifica:
   ```bash
   python -m editor.web_exporter <game>
   node --check build_web/<game>/runtime.js     # sintassi JS
   # parita' coordinate (esempio): confronta ScalingManager Python vs JS su una scena
   ```
6. Aggiorna la tabella in **WEB_EXPORT.md §6/§7** se cambia lo stato delle feature.

---

## Verifica di parita' coordinate (riferimento)

Confronto numerico `bg_to_screen` Python vs JS a 1280×720 su una scena: il delta
deve essere ~0 (solo arrotondamento di stampa). Hit-test ruotato: la griglia di
campionamento deve essere identica tra `ClickDetector` Python e `hitTest` JS.
Questi controlli hanno gia' dato delta < 0.005px e 961/961 celle identiche.
