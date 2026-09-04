# Report di analisi approfondita - Editor di gioco HiddenEngine

Data: 2026-06-13
Ambito: pacchetto `editor/` (~29.000 righe Python + runtime web JS) e relative pipeline di build/export.

## Metodologia

L'editor e' stato partizionato in 23 sottosistemi e analizzato da revisori indipendenti
(uno per sottosistema, piu' tre "cacciatori" trasversali per duplicazioni, codice morto e
stabilita'). Ogni segnalazione e' poi passata da un verificatore avversariale che ha riletto
il codice reale e fatto grep sull'intero albero per evitare falsi positivi dovuti
all'architettura a mixin (la classe `LevelEditor` e' composta da ~20 mixin, quindi un metodo
referenziato in un file puo' essere definito in un altro).

Risultato: 275 segnalazioni grezze, 273 confermate, 2 respinte. Dopo deduplica delle
sovrapposizioni tra cacciatori trasversali: 4 critici, ~18 alti, 27 bug medi, 37 voci di
codice morto, 36 cluster di ridondanza, piu' miglioramenti di stabilita'.

Tutte le voci sotto sono confermate con evidenza diretta su file e riga.

---

## 1. Bug critici (da correggere per primi)

### C1 - `_with_loading` distrugge l'intera applicazione su qualsiasi errore recuperabile
File: [editor/editor_base.py:516](editor/editor_base.py:516)

`_with_loading` avvolge un'azione in `try/except/finally`. Sul percorso di successo la
funzione esce con `return action(...)`; quindi le righe finali `self._cleanup_processes()` e
`pygame.quit()` vengono eseguite SOLO quando un'eccezione viene catturata. Ogni operazione
fallita avvolta dall'overlay di caricamento (salvataggio, export HTML, apertura scena, comandi
di menu instradati via `_with_loading`) chiude pygame; al frame successivo `run()` chiama
`pygame.event.get()` su un sistema video non inizializzato e l'editor crasha.

Fix: rimuovere le due righe finali da `_with_loading`. Spostare `_cleanup_processes()` +
`pygame.quit()` nel vero percorso di chiusura (dopo il ritorno di `run()` in `main()`).

### C2 - Le build Android sono completamente non funzionanti nell'EXE distribuito
File: [editor/editor_base.py:667](editor/editor_base.py:667), [editor/mixins/game_select.py:214](editor/mixins/game_select.py:214), [editor/android_build_ui.py:325](editor/android_build_ui.py:325)

In build congelata (PyInstaller) il flusso Android lancia sottoprocessi con
`--android-build-ui` e `--android-build-manager`, ma `main()` dichiara solo `--build-ui` e
`--build-manager`. `argparse` rifiuta gli argomenti sconosciuti e fa `sys.exit(2)`: la finestra
di build APK non si apre mai e il manager non parte. Funziona solo in sviluppo (dove vengono
invocati gli script `.py`), non nel prodotto distribuito.

Fix: aggiungere in `main()` i rami `--android-build-ui` e `--android-build-manager`
(simmetrici a quelli desktop), gestendo anche il flag opzionale `--release` che
`android_build_ui.py` accoda.

### C3 - Il salvataggio dell'editor immagini sovrascrive ogni file omonimo in tutti i giochi
File: [editor/mixins/img_editor.py:162](editor/mixins/img_editor.py:162)

Al salvataggio, dopo aver scritto la superficie modificata sul percorso dell'asset, il codice
fa `rglob` ricorsivo per QUALSIASI file con lo stesso nome base sotto `engine/assets` e sotto
l'intero albero `games/`, e li sovrascrive tutti con l'immagine corrente. Nomi come `icon.png`,
`tree.png`, `bg.png` ricorrono in giochi diversi: un singolo salvataggio distrugge in modo
irreversibile fino a una dozzina di asset non correlati (sfondi di altri livelli, icone tema,
asset di altri giochi). Nessun backup: l'originale viene scartato alla chiusura.

Fix: non abbinare per solo nome base. Sovrascrivere solo i duplicati byte-identici
all'originale pre-modifica (confronto hash), oppure limitare la sincronizzazione a una mappa
nota `asset-id -> path` (gioco corrente + copia master del motore per QUESTO asset).

### C4 - Il modale Minigame crasha se la selezione viene azzerata/eliminata mentre e' aperto
File: [editor/mixins/minigame_modal.py:104](editor/mixins/minigame_modal.py:104)

Il modale Minigame non e' registrato nella catena di priorita' tastiera in `_on_key`, quindi i
tasti passano all'editor sottostante. Premere Esc chiama `_escape()` (imposta
`selected_idx=None`) e Canc/Backspace chiama `_delete_sel()`. Al frame successivo
`_r_minigame_modal` esegue `self.scene_data['objects'][self.selected_idx]` con `selected_idx`
None -> `TypeError` (o `IndexError` se l'oggetto e' stato eliminato).

Fix: guardia su render e click (`idx None o fuori range -> chiudi il modale e return`) e
registrare il modale nella catena tasti di `_on_key` per assorbire i tasti.

---

## 2. Bug ad alta severita'

### Integrita' dati e impostazioni

- B-H1 - `_load_json` restituisce `{}` per file corrotti: una `scene.json` danneggiata e'
  indistinguibile da una mancante, viene caricata come scena vuota e il salvataggio successivo
  la sovrascrive, distruggendo l'originale recuperabile.
  [editor/core/io.py:19](editor/core/io.py:19)
  Fix: distinguere mancante da corrotto; su errore di parsing loggare, avvisare e NON
  sostituire/sovrascrivere (o fare backup in `scene.json.corrupt`).

- B-H2 - Quattro scritture inline di `.editor_settings.json` con il solo `recent_scenes`
  azzerano tutte le altre chiavi (lingua, larghezze pannelli, preferenze scatter) a ogni
  creazione/eliminazione di gioco/livello/scena e a ogni rinomina gioco. Tre dei quattro siti
  usano anche un path relativo alla CWD invece di `base_path`.
  [editor/mixins/game_select.py:794](editor/mixins/game_select.py:794),
  [editor/mixins/game_select.py:1382](editor/mixins/game_select.py:1382),
  [editor/mixins/game_select.py:1408](editor/mixins/game_select.py:1408),
  [editor/mixins/game_select.py:1440](editor/mixins/game_select.py:1440)
  Fix: sostituire tutte e quattro con `self._save_editor_setting("recent_scenes", ...)`
  (load-merge-save gia' esistente, path corretto).

- B-H3 - La pulizia degli orfani in fase di salvataggio scandisce solo `games/<g>/objects/`,
  ignorando `objects_cartoon/` e `objects_lineart/`: gli asset cartoon/lineart non vengono mai
  rimossi e si accumulano; il controllo di recuperabilita' dal motore omette `objects_cartoon`.
  [editor/mixins/io_ops.py:429](editor/mixins/io_ops.py:429)
  Fix: iterare su tutte e tre le sottocartelle (costante condivisa).

### Crash e perdita di input

- B-H4 - I modali Scatter e Minigame e il dialog di conferma uscita (`_confirm_leave_modal`)
  non bloccano la tastiera: mentre sono aperti i tasti globali restano attivi (mode 1/2/3/4,
  Canc elimina l'oggetto selezionato, Esc agisce sulla scena, Ctrl+Z/Ctrl+S si attivano).
  [editor/mixins/input_handlers.py:98](editor/mixins/input_handlers.py:98)
  Fix: guardie di early-return in `_on_key` per questi tre stati.

- B-H5 - `_ctx_menu_click` dereferenzia `self._ctx_menu` dopo che `_get_ctx_items()` puo'
  averlo impostato a None (scena mutata mentre il menu e' aperto: undo, delete) ->
  `AttributeError: NoneType`.
  [editor/mixins/object_ops.py:937](editor/mixins/object_ops.py:937)
  Fix: ricontrollare `if not self._ctx_menu: return False` dopo il refresh degli item.

- B-H6 - Il color picker consuma `pygame.QUIT` nel suo loop bloccante: cliccare la X della
  finestra mentre il dialog e' aperto chiude solo il dialog, l'app non si chiude mai.
  [editor/ui/color_picker.py:116](editor/ui/color_picker.py:116)
  Fix: ri-postare l'evento QUIT prima di uscire dal loop.

### Rendering e usabilita'

- B-H7 - Il TAB-cycle cambia selezione senza invalidare la cache statica del canvas: l'oggetto
  deselezionato sparisce dalla scena (la cache salta gli oggetti selezionati, il passaggio
  dinamico salta i non selezionati).
  [editor/mixins/input_handlers.py:1076](editor/mixins/input_handlers.py:1076)
  Fix: `self._mark_dirty()` a fine `_tab_cycle()` (e centralizzare le mutazioni di selezione).
  Nota: stesso difetto sui tasti mode 1/2/3/4 e su alcuni click di pannello (bug medio).

- B-H8 - Lo scroll dell'albero scene e' clampato all'intervallo magico `[0, 100]` invece che
  al contenuto reale: con pochi livelli si scrolla l'albero fuori dal pannello senza ritorno.
  [editor/mixins/input_handlers.py:889](editor/mixins/input_handlers.py:889)
  Fix: calcolare il max reale dal contenuto e clampare in render e nel wheel handler.

### Funzionalita' "morte" lato UI (feature non raggiungibili)

- B-H9 - Il blocco "Edit Tags" del modale sfondi e' sovra-indentato dopo un `return`, quindi
  staticamente irraggiungibile: non si puo' MAI entrare in modifica tag di uno sfondo.
  [editor/mixins/background_modal.py:359](editor/mixins/background_modal.py:359)

- B-H10 - Nel modale tag, la creazione dinamica del tag su Invio e' codice morto (return
  anticipato): digitare un nuovo tag + Invio non chiama mai `ensure_tag`.
  [editor/mixins/tag_modal.py:48](editor/mixins/tag_modal.py:48)

- B-H11 - I suggerimenti tag sono limitati a 20 (limite di default non sovrascritto): qualsiasi
  catalogo con piu' di 20 tag non puo' mostrarne/assegnarne oltre il 20esimo; la scrollbar non
  si attiva mai.
  [editor/mixins/tag_modal.py:42](editor/mixins/tag_modal.py:42)

### Build, export e audit

- B-H12 - La build Android in modalita' Release produce un `.aab`, ma il recupero artefatto fa
  glob solo di `*.apk`: la build riesce ma la funzione solleva `FileNotFoundError`, quindi il
  percorso Release riporta sempre fallimento.
  [editor/android_build_system.py:841](editor/android_build_system.py:841)

- B-H13 - Annullare la build desktop termina solo il processo `build_manager`, non il nipote
  PyInstaller (nessun gruppo di processi): PyInstaller continua a girare, occupando CPU/disco e
  lock sui file temporanei.
  [editor/build_ui.py:346](editor/build_ui.py:346)

- B-H14 - L'auditor risolve le immagini dal catalogo del gioco ATTUALMENTE caricato, non da
  quello del gioco in audit (spesso diverso, o `[]` se nessun gioco caricato): il controllo
  PNG-mancanti viene saltato e l'audit non riporta nulla nel percorso tipico da dashboard.
  [editor/mixins/auditor.py:318](editor/mixins/auditor.py:318)

- B-H15 - L'export web mantiene gli oggetti con `catalog_id` assente come goal invisibili: il
  runtime non li disegna ma li conta nel check "tutti trovati", rendendo la scena non
  completabile (il motore Python invece li scarta).
  [editor/web_exporter.py:151](editor/web_exporter.py:151)

### Motore di scatter

- B-H16 - In `_overlaps_any` il segno del margine di tolleranza overlap e' invertito: un
  `overlap_margin_factor` piu' alto rende il piazzamento PIU' restrittivo invece che piu'
  tollerante (espande il bbox invece di restringerlo), affamando proprio le run ad alta densita'.
  [editor/tools/scatter_engine.py:2196](editor/tools/scatter_engine.py:2196)
  Fix: `margin = eff_size * overlap_margin_factor` (positivo).

### Ridondanza ad alto rischio

- B-H17 - I modali Video e Sfondi puntano alla STESSA directory
  (`engine/assets/backgrounds`) e leggono/scrivono lo STESSO file `backgrounds_catalog.json`
  con schemi tag incompatibili (video salva stringhe grezze, sfondi risolve via TagManager).
  [editor/mixins/video_modal.py:31](editor/mixins/video_modal.py:31),
  [editor/mixins/background_modal.py:65](editor/mixins/background_modal.py:65)
  Fix: dare al catalogo video un nome distinto (`videos_catalog.json`) ed estrarre un
  `AssetCatalog` condiviso.

---

## 3. Bug medi (raggruppati per tema)

Coordinate e stati di interazione
- Esc non annulla un piazzamento cerchio in corso. [editor/mixins/input_handlers.py:432](editor/mixins/input_handlers.py:432)
- Il resize dei pannelli (`_resizing_l/_resizing_r`) e' escluso dall'auto-heal del mouseup perso. [editor/mixins/input_handlers.py:640](editor/mixins/input_handlers.py:640)
- `_set_layer` puo' spostare oggetti sul layer `overlay` non cliccabile, rendendoli non selezionabili sul canvas. [editor/mixins/object_ops.py:770](editor/mixins/object_ops.py:770)
- Wheel della colonna Livelli usa altezza riga errata (34 invece di 50): non si scrolla agli ultimi livelli. [editor/mixins/game_select.py:2009](editor/mixins/game_select.py:2009)
- Esc sul dialog di eliminazione gioco lascia `_gs_del_stage` stantio, desincronizzando il dialog successivo. [editor/mixins/game_select.py:2027](editor/mixins/game_select.py:2027)
- Catalogo: `visible_items` usa stride (item_h+2) mentre il layout usa (item_h+4); il wheel effetti hardcoda `list_y_start=58` contro il render a 66. [editor/mixins/render_panels.py](editor/mixins/render_panels.py)

Cache e perdite di risorse
- `_img_cache` cresce senza limite (nessuna eviction) mentre le cache sorelle sono LRU-cap: leak di superfici durante sessioni lunghe con zoom. [editor/mixins/io_ops.py:816](editor/mixins/io_ops.py:816)
- `_load_img` mette in negative-cache `None` per file mancanti in modo permanente: un asset ripristinato resta invisibile fino al cambio gioco. [editor/mixins/io_ops.py:824](editor/mixins/io_ops.py:824)
- Il thread di anteprima video continua a decodificare frame dopo la chiusura del modale (manca il check `if not self._vid_modal`). [editor/mixins/video_modal.py:98](editor/mixins/video_modal.py:98)
- Sfondo scalato a `(bw*zoom, bh*zoom)` senza clamp: superficie da centinaia di MB a zoom massimo (il percorso icone clampa a 2000). [editor/mixins/render_canvas.py](editor/mixins/render_canvas.py)

Sicurezza dei dati e coerenza
- `_collect_used_assets` salta con bare-except le scene con JSON non valido: i loro asset vengono trattati come orfani e soft-eliminati. [editor/mixins/io_ops.py:149](editor/mixins/io_ops.py:149)
- Eliminazione video usa `os.remove` diretto, bypassando il cestino soft-delete usato da musica e sfondi. [editor/mixins/video_modal.py:409](editor/mixins/video_modal.py:409)
- Modifiche traduzioni scartate in silenzio su chiusura/annulla: `_lang_dirty` non e' coperto da alcuna guardia. [editor/mixins/lang_modal.py:228](editor/mixins/lang_modal.py:228)
- Campi numerici nuovo-oggetto accettano 0 e valori negativi, scrivendo voci di catalogo malformate. [editor/mixins/newobj_modal.py:56](editor/mixins/newobj_modal.py:56)
- L'editor immagini salva accanto al master ma registra un path relativo al gioco, rompendo il riferimento di catalogo. [editor/mixins/img_editor.py:108](editor/mixins/img_editor.py:108)
- Le riparazioni dell'auditor scrivono su disco ma non aggiornano lo stato in memoria: riparare il gioco aperto puo' essere silenziosamente annullato dal salvataggio successivo. [editor/mixins/auditor.py:351](editor/mixins/auditor.py:351)
- L'audit non ha confine di eccezione: un valore JSON malformato (es. `menu.music: null`) fa crashare l'intero scan. [editor/mixins/auditor.py:110](editor/mixins/auditor.py:110)

DB profili/forme e download modelli
- `object_palette` e `object_shapes` scrivono nella tabella `object_profile` senza mai crearla: se `build_profiles` non e' girato si ottiene un DB zombie e le palette/forme vengono perse in silenzio. [editor/tools/object_palette.py:190](editor/tools/object_palette.py:190), [editor/tools/object_shapes.py:185](editor/tools/object_shapes.py:185)
- I modelli scaricati non sono validati contro `Content-Length`: download troncati restano cachati come "completi". [editor/tools/download_models.py:62](editor/tools/download_models.py:62)

Build (desktop e Android)
- Il watchdog rileva una build bloccata ma non la termina mai (nessun handle al processo). [editor/build_manager.py:106](editor/build_manager.py:106), [editor/android_build_manager.py:104](editor/android_build_manager.py:104)
- La build gioco omette gli hidden import cv2/numpy/scipy.ndimage dichiarati obbligatori in `pyinstaller_common`. [editor/build_system.py:512](editor/build_system.py:512)
- I path delle patch p4a hardcodano `build-arm64-v8a_armeabi-v7a` ma lo spec compila solo arm64: le Patch 2 e 3 vengono saltate in silenzio. [editor/android_build_system.py:298](editor/android_build_system.py:298)
- Annulla Android termina solo il manager locale; il `buildozer` WSL resta orfano. [editor/android_build_ui.py:354](editor/android_build_ui.py:354)
- Scritture concorrenti non sincronizzate su `status.json` possono corromperlo. [editor/build_manager.py](editor/build_manager.py)

Scatter
- Race tra il thread di preload del modello e il caricamento on-demand (nessun lock/flag in-flight). [editor/mixins/scatter_modal.py:96](editor/mixins/scatter_modal.py:96)
- `_swap_optimize` mantiene x,y top-left scambiando width/height/scale, spostando i centri e rischiando nuovi overlap. [editor/tools/scatter_engine.py:2057](editor/tools/scatter_engine.py:2057)

---

## 4. Codice morto (37 voci confermate)

Moduli/feature interi
- `editor/debug/coordinate_inspector.py` (293 righe): mai importato/istanziato; inoltre confronta `state == 1` contro la stringa `STATE_MAIN = "main"`, quindi il corpo sarebbe comunque irraggiungibile. [editor/debug/coordinate_inspector.py](editor/debug/coordinate_inspector.py)
- Sottosistema crop dell'editor immagini inerte: il dict `crop` non viene mai popolato, la matematica di crop al salvataggio e' sempre no-op. [editor/mixins/img_editor.py:143](editor/mixins/img_editor.py:143)
- Modalita' "global" della bacchetta magica irraggiungibile (flag mai attivato). [editor/mixins/img_editor.py:39](editor/mixins/img_editor.py:39)
- Metriche BG costose (texture_entropy, local_complexity, hideability_map, anchor_points, zone_palettes) calcolate e cachate ma mai usate nel piazzamento. [editor/tools/scatter_engine.py:362](editor/tools/scatter_engine.py:362)

Metodi/funzioni mai chiamati
- `_select_next_all` [editor/mixins/input_handlers.py:333](editor/mixins/input_handlers.py:333)
- `_open_layer_selector_for_selection` [editor/mixins/object_ops.py:1238](editor/mixins/object_ops.py:1238)
- `get_viewport_render` [editor/mixins/img_editor_logic.py:79](editor/mixins/img_editor_logic.py:79)
- `has_cache()` [editor/tools/bg_cache.py:390](editor/tools/bg_cache.py:390)
- `download_clip_text()` (il modello CLIP text non ha percorso di download) [editor/tools/download_models.py:147](editor/tools/download_models.py:147)
- `spec_analysis_kwargs()` mai chiamata; `HiddenEditor.spec` riproduce la stessa logica a mano [editor/pyinstaller_common.py:242](editor/pyinstaller_common.py:242)
- `_delete_effect_sel` duplicato/oscurato: la copia in `input_handlers` e' morta per MRO (vince `object_ops`). [editor/mixins/input_handlers.py:2182](editor/mixins/input_handlers.py:2182)

Rami/variabili/branch morti
- Branch click chip `__toggle__`/`catalog_chips_expanded` irraggiungibile. [editor/mixins/input_handlers.py:1376](editor/mixins/input_handlers.py:1376)
- Espressione `layer_color(...) if False else (...)` con nome non importato. [editor/mixins/scatter_modal.py:673](editor/mixins/scatter_modal.py:673)
- `stats['duplicate']` mai incrementato; il docstring promette una deduplica non implementata. [editor/mixins/io_ops.py:622](editor/mixins/io_ops.py:622)
- `status['canceled']` scritto ma mai letto. [editor/build_ui.py:383](editor/build_ui.py:383)
- Scrittura morta su `_music_modal_modal_active`. [editor/editor_base.py:584](editor/editor_base.py:584)
- `local 'period'` calcolato per frame e mai usato. [editor/mixins/render_canvas.py:521](editor/mixins/render_canvas.py:521)

Import inutilizzati
- ~129 import inutilizzati segnalati da pyflakes nel pacchetto (esempi: `REF_W` e `import math` duplicato in editor_base; `layer_color` in object_ops; `time` in lang_modal; `math` in object_palette; `sys/shutil/logging` in android_build_system; vari in color_picker/render_topbar/scatter_modal).

L'autosave (`scene.json.autosave`) e' scritto ma mai riletto per il recupero ne' ripulito: una rete di sicurezza che non protegge nulla. [editor/mixins/io_ops.py:732](editor/mixins/io_ops.py:732)

---

## 5. Ridondanze (36 cluster)

Da unificare (priorita' media)
- Pipeline di build desktop e Android quasi identiche: `BuildWatchdog`, `update_status`,
  `progress_callback`, scaffolding `__main__`, e la finestra Tkinter di progresso
  (`AndroidBuildProgressWindow` duplica ~90% di `BuildProgressWindow`). Anche
  `_run_pyinstaller_with_timeout` vs `_run_buildozer_with_timeout`.
  [editor/android_build_manager.py](editor/android_build_manager.py), [editor/android_build_ui.py](editor/android_build_ui.py)
- `build_system.py` hardcoda i propri argomenti/exclude PyInstaller invece di usare
  `pyinstaller_common` (la "unica fonte di verita'" dichiarata). [editor/build_system.py](editor/build_system.py)
- Logica catalogo/tag/suggerimenti triplicata tra i modali sfondo/musica/video, con
  persistenza divergente (vedi B-H17). [editor/mixins/background_modal.py](editor/mixins/background_modal.py)
- Editing dei campi di testo (cursore, Ctrl-A/C/V, backspace/delete/frecce, insert)
  reimplementato in almeno quattro mixin. [editor/mixins/lang_modal.py](editor/mixins/lang_modal.py)
- Mappa ADE20K class-id -> contesto duplicata e incoerente tra `object_profiles.ADE_TO_CONTEXT`
  e `scatter_models`. [editor/tools/object_profiles.py](editor/tools/object_profiles.py)
- Il runtime web (`game.js`) ridisegna su canvas menu/risultati/impostazioni/pausa duplicando
  il `MenuSkinWeb` DOM (rischio di divergenza Python/JS gia' annotato come vincolo di progetto).
  [editor/web_template/runtime/game.js](editor/web_template/runtime/game.js)

Da semplificare (priorita' bassa, ma migliorano professionalita')
- `TagManager.save` reimplementa una scrittura atomica peggiore di `safe_write_json` (finestra
  di crash tra due rename, `load()` non recupera dal `.bak`). [editor/core/tags.py:41](editor/core/tags.py:41)
- `_save()` fa tre rglob('scene.json') indipendenti sull'albero del gioco. [editor/mixins/io_ops.py](editor/mixins/io_ops.py)
- `_confirm_circle` e `_confirm_rect` duplicano grossi blocchi di sanitizzazione layer/harvest/traduzioni. [editor/mixins/object_ops.py](editor/mixins/object_ops.py)
- Helper clipboard Tkinter get/set duplicato in cinque file; scaffolding modale (overlay +
  box centrato + bordo + X + search) ricodificato in ogni modale.
- `self.LANGS` assegnato due volte identico; `self.recent_scenes = []` poi subito sovrascritto;
  `_get_asset_ratio` carica due volte la stessa immagine. [editor/editor_base.py](editor/editor_base.py)
- Re-import locali ripetuti in hot path (`import pygame`/`re`/`uuid` dentro i loop di render e
  sanitizzazione).
- Backup `.json.bak` creati a ogni delete di catalogo e mai ripuliti. [editor/mixins/io_ops.py](editor/mixins/io_ops.py)
- Costante altezza riga (34/50/64) duplicata in quattro metodi del dashboard e gia' divergente.

---

## 6. Miglioramenti di stabilita' e professionalita'

- 56 clausole `except:`/`except: pass` nude in 14 file (game_select 18, music_modal 9,
  background_modal 7, video_modal 6, img_editor 3, ...) nascondono i fallimenti e catturano
  anche `KeyboardInterrupt`/`SystemExit`. Sostituire con `except Exception` mirate e logging.
- Il download del modello scatter gira bloccante sul thread UI con progress via `flip()`
  manuale: spostare su thread + coda di progresso. [editor/mixins/scatter_modal.py](editor/mixins/scatter_modal.py)
- `_r_tree` fa `Path.exists()` per ogni scena espansa a ogni frame (60 FPS): cachare l'esito.
  [editor/mixins/render_panels.py](editor/mixins/render_panels.py)
- Il color picker non gestisce il resize finestra (superficie stantia, hit-test rotti).
  [editor/ui/color_picker.py](editor/ui/color_picker.py)
- Le hit-box della barra menu sono cablate sulle larghezze delle etichette inglesi: con
  etichette localizzate i target di click/hover si disallineano. [editor/mixins/render_topbar.py](editor/mixins/render_topbar.py)
- La barra menu superiore (File/Edit/Lang) viene disegnata anche nella schermata di selezione
  gioco, dove non ha contesto. [editor/mixins/render_topbar.py](editor/mixins/render_topbar.py)
- `compute_zone_palettes` importa scikit-learn (dipendenza non dichiarata) e degrada in
  silenzio a 3 pixel casuali se assente. [editor/tools/bg_cache.py](editor/tools/bg_cache.py)
- Editing radius con ALT+wheel spinge uno snapshot di undo per ogni tick di scroll: raggruppare.
  [editor/mixins/input_handlers.py](editor/mixins/input_handlers.py)
- Il fallback minigame del motore lascia `_save()` scrivere in `engine/minigames`, violando
  l'invariante "non modificare mai il motore". [editor/mixins/io_ops.py](editor/mixins/io_ops.py)
- Esc/uscita dall'editor immagini scarta le modifiche non salvate senza conferma. [editor/mixins/img_editor.py](editor/mixins/img_editor.py)

---

## 7. Piano d'azione consigliato

Priorita' 1 (rischio di crash / perdita dati - intervenire subito)
1. C1 `_with_loading`/`pygame.quit()` - una riga, alto impatto.
2. C3 sovrascrittura globale editor immagini - perdita dati irreversibile.
3. B-H1 `_load_json` su scena corrotta - perdita dati.
4. B-H2 clobber di `.editor_settings.json` (4 siti) - reset preferenze.
5. C4 + B-H4 + B-H5 + B-H6 crash da modali/menu (guardie tastiera e null-check).

Priorita' 2 (feature distribuite rotte)
6. C2 flag Android nell'EXE; B-H12 glob `.aab`; B-H13 processi orfani al cancel.
7. B-H9/B-H10/B-H11 feature UI irraggiungibili (tag sfondo, creazione tag, cap 20).
8. B-H14 auditor su catalogo sbagliato; B-H15 goal invisibile nell'export web.

Priorita' 3 (correttezza/usabilita')
9. B-H7/B-H8 rendering selezione e scroll albero; B-H3 pulizia orfani cartoon/lineart.
10. B-H16 segno margine overlap scatter; bug medi su cache/leak.

Priorita' 4 (manutenibilita' - quick win a basso rischio)
11. Rimuovere codice morto (modulo coordinate_inspector, metodi mai chiamati, ~129 import).
12. Sostituire le 56 bare-except con eccezioni mirate + logging.
13. Unificare le pipeline di build e i modali asset; centralizzare l'editing testo e il
    clipboard; usare `safe_write_json`/`pyinstaller_common` ovunque.

Le 2 segnalazioni respinte dal verificatore (per trasparenza): il troncamento del titolo a
larghezza negativa nella topbar (irraggiungibile data la larghezza minima 1280) e la presunta
injection nel `manifest.js` dell'export web (e' un file `.js` esterno, non inline: nessun
breakout HTML possibile).
