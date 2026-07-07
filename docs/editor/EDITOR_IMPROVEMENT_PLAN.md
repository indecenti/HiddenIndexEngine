# Piano di miglioramento editor — UI/UX, funzionalita', editor PNG

Data analisi: 2026-07-07. Basato su esplorazione completa di `editor/` (~24k righe),
`docs/editor/EDITOR_AUDIT_REPORT.md` e `docs/ROADMAP.md`.

## Stato dell'arte (sintesi)

### Punti di forza
- Editing scena maturo: multi-selezione (marquee, Shift+click), clipboard cross-scena,
  duplica, context menu ricchi, warp prospettico 4 angoli, rotazione, flip, opacita',
  filtro colore da palette BG.
- Undo/redo full-scene (50 livelli), autosave 60s, dirty-state in titolo/status.
- 5 layer con visibilita'/lock persistiti, grid+snap, zoom verso cursore, pan, fit.
- Scatter AI camouflage completo (6 leve, gate difficolta', ghost preview, heatmap QA)
  + scatter cluster procedurale rapido.
- i18n 5 lingue con editor traduzioni e audit al save; TagManager con tassonomia globale.
- Modali asset complete: background (thumbnails disk-cache, drag&drop file, soft-delete),
  video, musica, icone (genera .ico multi-size).
- Auditor progetto con repair non distruttivo (config, catalogo, scene, PNG mancanti).
- Build EXE/APK con progress window, log, deadlock detection, timeout, cancel.
  Web export PWA completo (service worker, WebP, ffmpeg audio, zip versionato).

### Debolezze strutturali
- **Immediate-mode senza widget system**: layout e hit-test calcolati due volte
  (render vs input) e tenuti in sync a mano. Esempi: scroll effetti hardcoded
  `input_handlers.py:904` vs `render_panels.py:584`; img_editor con commenti
  "ALLINEATO al render" in ~6 punti.
- **God-class**: `LevelEditor` = 20+ mixin, ~150 attributi piatti su `self`.
- **Modali gestiti da ~15 flag booleani** in catene if; color picker usa un event-loop
  bloccante separato (`ui/color_picker.py:111`) — inconsistenza architetturale.
- **Zero DPI awareness, font a pixel fissi** (xs=11..xl=30, mai riscalati): UI minuscola
  su 4K, sfocata con scaling Windows >100%.
- **Hitbox menubar a larghezza fissa** (`render_topbar.py:38`): si rompono con etichette
  tradotte lunghe.
- Operazioni pesanti (open/save/export) in `_with_loading` bloccante: freeze UI.
- Undo: deepcopy completo a ogni push, selezione persa dopo undo/redo, niente etichette,
  non copre catalogo/PNG/tag/traduzioni.

### Editor PNG (img_editor, "STUDIO ASSET")
Presente e buono: gomma con brush (size/hardness/opacity/shape), magic wand con
tolleranza+feather, chroma remover 3 preset con spill suppression, rotate/flip,
smooth edges, auto-trim a componenti connessi, zoom 0.1x-40x con pixel grid,
anteprima trasparenza, save con propagazione hash-based ai duplicati, save-copy `_v2+`.

Mancante o rotto:
- **Crop manuale con maniglie: dichiarato ma mai implementato** (drag states `crop_l/r`
  citati a `img_editor.py:45`, nessun handler li imposta) — dead code.
- **Nessun redo**; undo = snapshot full-surface cap 20.
- **Nessun rembg in UI**: la rimozione sfondo AI vive solo in script standalone con
  path hardcoded (`fix_all_images_rembg.py`, `tools/process_assets.py`).
- Niente resize/scale numerico, niente filtri (brightness/contrast/levels), niente
  outline/stroke, niente restore/unerase, wand "global" dead code (mai attivabile).
- `newobj_modal` copia il PNG as-is: zero processing all'import.

### Gap funzionali level-design
- **Nessun playtest scena in-editor**: si puo' solo lanciare il gioco intero e navigare.
- **Nessun duplica/clona scena o livello**, nessuno spostamento scena tra livelli/giochi,
  nessun riordino giochi.
- Nessuna statistica scena (n. goal, densita', copertura) ne' stima difficolta' esposta
  (lo scatter_engine la calcola internamente ma non e' riusata).
- Nessuna preview "come in gioco" (scaling/HUD/flashlight).
- Auditor non copre: coordinate fuori bounds, presenza `is_goal`, completezza traduzioni,
  manifest minigiochi, `catalog_id` duplicati/inesistenti, coerenza `levels` config.
- Export HTML senza progress window/log/cancel (a differenza di EXE/APK).
- Frecce fanno pan, non nudge dell'oggetto selezionato. Niente allineamento/distribuzione
  multi-selezione, niente zoom-to-selection, grid size fisso 32 senza UI.

### Residui audit (ROADMAP)
Tre refactor rimandati per rischio: unificazione pipeline build desktop/Android,
`AssetCatalog` condiviso bg/musica/video, editing testo centralizzato tra modali.
Piu' cleanup bassa priorita' (§5 report): `TagManager.save` senza `safe_write_json`,
triplo `rglob('scene.json')`, clipboard helper duplicato in 5 file, scaffolding modale
ricodificato per modale, costanti altezza riga duplicate.

## Piano

Ordine pensato per ridurre rischio: la Fase 0 (fondamenta UI) abbassa il costo di tutte
le fasi successive. Stime: S = ore, M = 1-3 giorni, L = settimana+.

### Fase 0 — Fondamenta UI (sblocca tutto il resto)

| # | Intervento | Stima | Note |
|---|-----------|-------|------|
| 0.1 | Widget layer minimale: classi `Button/Slider/InputBox/ScrollList` che uniscono draw + hitbox + stato. Adozione incrementale, pannello per pannello (prima i nuovi sviluppi, poi migrazione) | L | Elimina la duplicazione render/input, causa radice di meta' dei bug UI |
| 0.2 | Modal stack unico (push/pop) al posto dei ~15 flag; migrare color picker dall'event-loop bloccante | M | Prerequisito per nuovi modali senza moltiplicare flag |
| 0.3 | Editing testo centralizzato (cursore, Ctrl-A/C/V, frecce) dentro `InputBox` | M | Refactor gia' in ROADMAP; si fonde con 0.1 |
| 0.4 | UI scale + DPI: `SetProcessDpiAwareness` su Windows, fattore `ui_scale` (font e metriche derivate, persistito in settings) | M | Font attuali fissi 11-30px; su 4K illeggibile |
| 0.5 | Hitbox menubar dinamiche sulla larghezza del testo renderizzato | S | Bug i18n concreto |
| 0.6 | Word-wrap in `_text` per messaggi modali (oggi tronca con ellissi) | S | |

### Fase 1 — UX quick win (paralleli, indipendenti)

| # | Intervento | Stima |
|---|-----------|-------|
| 1.1 | Frecce = nudge oggetto selezionato (1px, Shift=10px); pan resta su WASD/wheel | S |
| 1.2 | Grid size configurabile da UI + snap a bordi/centri di altri oggetti | M |
| 1.3 | Allinea/distribuisci multi-selezione (context menu: sx/dx/centro/spaziatura uniforme) | M |
| 1.4 | Zoom-to-selection (tasto Z o doppio click su layer) | S |
| 1.5 | Duplica scena (clone completo: scene.json + riferimenti) e duplica livello | M |
| 1.6 | Sposta/copia scena tra livelli; riordino giochi in dashboard | M |
| 1.7 | Undo: preserva selezione, etichette azione ("Sposta 3 oggetti"), coalescing drag | M |
| 1.8 | Progress window per export HTML (riusa pattern `build_ui`: log, cancel) | M |
| 1.9 | Threading per open/save pesanti al posto di `_with_loading` bloccante | M |

### Fase 2 — Editor PNG

| # | Intervento | Stima | Note |
|---|-----------|-------|------|
| 2.1 | Crop manuale con maniglie (completare infrastruttura esistente `crop_l/r/t/b`) | M | Dead code da finire, non da inventare |
| 2.2 | Bottone "Rimuovi sfondo (AI)": rembg lazy-load con fallback se assente | M | rembg gia' usato negli script del repo; niente nuova dipendenza |
| 2.3 | Redo; undo a dirty-rect invece di snapshot full-surface | M | |
| 2.4 | Resize numerico a dimensione target (LANCZOS via PIL, gia' disponibile) | S | |
| 2.5 | Filtri base: brightness/contrast/saturazione/levels (numpy, gia' usato) | M | |
| 2.6 | Outline/stroke automatico su alpha (utile per leggibilita' icone HOG) | M | |
| 2.7 | Modalita' restore per la gomma (ripristina alpha dall'originale) | S | |
| 2.8 | Import con processing in `newobj_modal`: opzione rembg + auto-trim al volo | M | Porta la pipeline `add-asset` dentro l'editor |
| 2.9 | Batch processing UI: cartella → rembg → trim → registra nel catalogo con tag | L | Sostituisce gli script con path hardcoded |
| 2.10 | Rimuovere dead code: `_img_editor_wand_global`, unificare blocco save/save_copy | S | |

### Fase 3 — Level design pro

| # | Intervento | Stima | Note |
|---|-----------|-------|------|
| 3.1 | **Playtest scena in-editor**: flag `--scene <game>/<level>/<scene>` in `main.py` + bottone Play nell'editor (subprocess) | M | Attrito n.1 del workflow attuale |
| 3.2 | Pannello statistiche scena: n. oggetti/goal per layer, densita', copertura aree | M | |
| 3.3 | Esporre stima difficolta'/camouflage dallo scatter_engine come metrica della scena finita | M | Il calcolo esiste gia' (`scatter_engine.py`) |
| 3.4 | Preview "come in gioco": rendering con ScalingManager + HUD overlay simulato | L | |
| 3.5 | Preset/gruppi oggetti salvabili e riutilizzabili tra scene | M | Oggi solo clipboard di sessione |
| 3.6 | Auditor esteso: coordinate fuori bounds, `is_goal` presenti, `catalog_id` validi/duplicati, manifest minigiochi, completezza traduzioni, coerenza `levels` config | M | Riusare logica di `tools/hie_mcp_server.py::validate_scene` |

### Fase 4 — Refactor rimandati (dalla ROADMAP, invariati)

| # | Intervento | Stima |
|---|-----------|-------|
| 4.1 | Unificare pipeline build desktop/Android (watchdog, progress, timeout comuni) | L |
| 4.2 | `AssetCatalog` condiviso background/musica/video (modali oggi triplicate) | L |
| 4.3 | Cleanup §5 report: `safe_write_json` in TagManager, rglob unico, clipboard helper unico, scaffolding modale comune, costanti riga | M |

### Fuori scope (decisione esplicita)
- Port a toolkit UI nativo (Qt/imgui): riscrittura, non refactor. Il widget layer 0.1
  ottiene l'80% del beneficio senza buttare 24k righe.
- Temi/dark mode della chrome editor: valore basso finche' i colori restano centralizzati
  in `constants.py`.
- Pannelli dockable: complessita' alta, beneficio marginale con 2 pannelli ridimensionabili.

## Ordine consigliato di esecuzione

1. Quick win subito spendibili: 0.5, 0.6, 1.1, 1.4, 2.1, 2.7, 2.10 (una settimana, tutto S/M indipendente).
2. Fase 0 core (0.1-0.4) come binario parallelo: da qui in poi ogni nuova UI costa meta'.
3. Fase 2 PNG (2.2, 2.3, 2.8) + Fase 1 restante.
4. Fase 3 (playtest 3.1 per primo: massimo impatto sul workflow).
5. Fase 4 quando il resto e' stabile.
