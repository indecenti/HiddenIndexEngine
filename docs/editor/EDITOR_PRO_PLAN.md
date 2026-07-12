# Piano "Editor Pro" — mimetizzazione auto-scatter + completezza editor

Data: 2026-07-12. Segue `EDITOR_IMPROVEMENT_PLAN.md` (completato) e l'audit scatter
(51 rilievi, dump in `scratch/scatter_audit_dump.json`). Tre parti:

- **S** — algoritmo di camuffamento dell'auto-scatter (`editor/tools/scatter_engine.py`).
- **U** — UX dell'auto-scatter nell'editor (`editor/mixins/scatter_modal.py`).
- **P** — completezza/professionalita' generale dell'editor.

Vincoli fissi:

- Nessuna nuova dipendenza: tutto con numpy/cv2/pygame/PIL gia' pinned.
- Modelli AI (tier 1-3) restano RINVIATI per decisione presa: il piano lavora al
  tier 0 (classico). I rilievi model-usage dell'audit (#39-49) restano congelati.
- Zero modifiche a engine/web: il contratto `PlacedObject` (x, y, scale, rotation,
  flip, alpha, color_filter) e' invariato, quindi `WEB_EXPORT_SYNC.md` non e' toccato.

## Diagnosi mimetizzazione (stato attuale, verificato nel codice)

Pipeline v3.2: score additivo per cella 48px (edge, saliency, colore HSV, orient,
shape, physics) + veti duri (gate colore, volti, cielo/mezz'aria, zone dipinte) +
region-fit scala/rotazione + tint Lab + verifica Delta-E footprint + banda
visibilita' + swap. Buona base, ma i punti deboli concreti sono:

1. **Quattro obiettivi non allineati** (audit #16/#35 ancora aperti): lo score di
   piazzamento, il proxy dello swap (`_swap_optimize`, formula propria), il
   `visibility_score` e la validazione post-render (`scatter_validate`) misurano
   quattro cose diverse. Si ottimizza un proxy e si giudica con un altro.
2. **La metrica finale ignora il bordo**: `scatter_validate` confronta media Lab
   oggetto vs media anello. Un oggetto "stacca" soprattutto per il contrasto di
   SILHOUETTE e per il mismatch di texture/frequenza, non per la media interna.
   Oggi nessuna metrica guarda il rim.
3. **Colore in HSV con toppe**: `_cluster_color_score` pesa hue 0.6 e ha due
   penalita' ad hoc (grigio-su-saturo, saturo-su-grigio, v3.2). Lab per cella
   (grid L/a/b, `lab_full` gia' in RAM) le sostituisce con una metrica
   percettiva unica, con Delta-L pesato di piu' (l'occhio e' sensibile alla
   luminanza prima che alla tinta).
4. **Tint moltiplicativo asimmetrico non sfruttato**: `BLEND_RGBA_MULT`
   (engine/core.py:2278) puo' solo SCURIRE. Un oggetto piu' chiaro del fondo e'
   recuperabile col tint; uno piu' scuro no. Il gate colore non lo sa: boccia o
   promuove simmetricamente.
5. **Decisioni sulla sola cella centrale**: rotazione, depth-scale e
   visibility_score campionano una cella; un oggetto grande copre decine di
   celle (nessuna aggregazione footprint sullo score).
6. **Un candidato per tentativo**: si sceglie una cella dal softmax e si tiene;
   nessun best-of-M valutato sul render reale.
7. **`filter_failed` scarta senza rimpiazzare**: la scena finisce sotto il count
   richiesto in silenzio (niente repair loop).
8. **Leve morte**: `anchor_points`, `zone_palettes`, `hideability_map` calcolati
   e cachati (bg_cache) ma mai consumati dal piazzamento.
9. **Appoggio rozzo**: `anchor_below` = edge density delle 2 celle sotto (doppio
   conteggio con w_edge, audit #38); niente rilevamento di linee orizzontali di
   appoggio; rotazione libera anche per oggetti a orientamento canonico
   (bottiglia storta = occhio attirato).

## Parte S — Camuffamento auto-scatter

### S0. Benchmark harness (PRIMA di toccare l'algoritmo)

`tools/scatter_benchmark.py`: scene reali fisse x 3 difficolta' x seed fissi.
Metriche per run: distribuzione verdetti validate (ok/warn/fail), score medio,
rim Delta-E (da S1), reject reasons, tempo. Output: JSON + contact sheet PNG.
Modalita' `--compare baseline.json` con tabella delta. Test di regressione con
soglie aggregate (es. medium: >=70% ok post-filter). Senza questo, ogni
"miglioramento" e' a occhio.

### S1. Metrica unica render-based: `CamouflageScore`

Nuovo `editor/tools/scatter_metrics.py`, riusa `render_sprite` di
scatter_validate. Su patch composito (cap ~160px lato, subsample):

- `rim_delta_e`: Delta-E fra banda 3-5px interna al contorno alpha e banda
  esterna adiacente (il "melt" del bordo e' il segnale n.1).
- `interior_delta_e`: attuale media-vs-anello (mantieni).
- `boundary_contrast`: energia gradiente lungo il contorno alpha nel composito
  MENO la stessa lungo il percorso nel BG puro (quanto edge il bordo AGGIUNGE).
- `texture_mismatch`: |varianza Laplaciano sprite a scala finale - varianza
  Laplaciano patch BG| (liscio-su-busy e busy-su-liscio staccano entrambi).
- `saliency_delta`: saliency fine-grained del patch composito vs patch
  originale (quanto il piazzamento ATTIRA l'occhio).
- Aggregato 0..1 con pesi per difficolta'; clutter soften come oggi.

Consumatori: piazzamento (S2), swap, visibility_score, validate, benchmark,
tooltip "perche' qui" (U4). Chiude #16/#35 con un solo obiettivo.

### S2. Best-of-M render-in-the-loop

Nel loop di `place_objects`: campiona M=4-6 celle dal softmax top-K (oggi 1),
per ciascuna fai il composito rapido e calcola `CamouflageScore`; tieni la
migliore; reject se fuori banda difficolta'. Cache sprite scalato per
(catalog_id, bucket scala, bucket rotazione). Il local-refinement 3x3 attuale
resta come pre-filtro. Costo bounded dal cap patch; budget verificato in S0.

### S3. Colore in Lab + tint consapevole dell'asimmetria

- Grid per cella L/a/b (stessa `_aggregate_to_grid` su `lab_full`).
- `_color_similarity_map` -> `exp(-DeltaE/sigma)` per cluster palette (gia' in
  Lab via `_obj_dominant_lab`), Delta-L pesato ~1.5-2x. Rimuove le penalita'
  v3.2 (subsumed). Gate colore in soglie Delta-E per difficolta'.
- Asimmetria tint: se L_obj > L_bg il tint moltiplicativo puo' chiudere il gap
  (consenti, quota recuperabile stimata); se L_obj < L_bg penalita' piena.
- Tint ottimizzato per piazzamento: scegli il mix che minimizza `rim_delta_e`
  con clamp identita' (mix max per difficolta', TINT_MIN_L invariato).
- Alpha adattivo come leva extra di blending (hard: ~232-248, medium: ~245-252,
  easy: 255). Contratto engine gia' pronto (alpha esiste): zero touch web.

### S4. Footprint scoring esatto + penalita' straddle

- Integral image della score matrix: media sotto bbox in O(1); rotazione,
  depth-scale, visibility su aggregato footprint, non sulla cella centrale.
- Penalita' "a cavallo": conteggio di edge strutturali BG forti attraversati
  dal rim (meta' su muro meta' su pavimento = innaturale). Con S1 disponibile,
  boundary_contrast la copre in parte: qui e' il pre-filtro cheap in matrice.

### S5. Appoggio e orientamento naturale

- Sostituire `anchor_below` con rilevamento ridge orizzontale (Sobel-Y) in una
  finestra sotto il bottom dell'oggetto: bonus "bottom appoggiato a una linea"
  proporzionale a `support_bot` (object_shapes gia' lo fornisce). Elimina il
  doppio conteggio edge (#38).
- Riusare `anchor_points` (Harris, oggi morti) come candidati di snap per
  oggetti con `support_bot` alto.
- Vincoli di rotazione per categoria: tag `upright` (bottiglie, mobili,
  personaggi...) -> rotazione limitata a 0 +/-10; oggetti liberi invariati;
  line_art invariato. Tag da aggiungere alla tassonomia + default conservativo
  per style real/cartoon.

### S6. Repair loop (count garantito con qualita')

Dopo `filter_failed`: ripiazza gli scartati con un nuovo pass `place_objects`
(existing_bboxes aggiornate, stesso pool), max 2 giri, poi report onesto
("richiesti 100, piazzati 97"). Oggi il count cala in silenzio.

### S7. Pulizia e perf residua

- `zone_palettes`/`hideability_map`: consumarli (se utili dopo S1) o smettere
  di calcolarli/cacharli.
- `_swap_optimize` O(n^2) (#26): bucketing spaziale, valuta solo coppie entro
  raggio; obiettivo = CamouflageScore (S1), non piu' il proxy.

Ogni fase S chiude con: `pytest tests/test_scatter_*` verde + benchmark S0
prima/dopo con numeri nel commit.

## Parte U — UX scatter nell'editor

Rilievi audit UX ancora aperti: #2, #3, #4, #5, #6, #7, #9, #10 (il #0 heatmap
e il #8 paint zone sono GIA' fatti nel modal).

- **U1. Progress + cancel su `_scatter_run`**: oggi blocca l'editor (audit #4).
  Worker thread + callback progress (pattern `_WebExportProgressModal` e
  batch_import gia' esistenti). Fasi mostrate: analisi BG / precompute catalogo /
  piazzamento / validazione.
- **U2. Seed esposto**: campo numerico + lucchetto "seed fisso" (itera parametri
  a parita' di estrazione) + mostra/copia seed dell'ultima run. `place_objects`
  lo supporta gia'; RIPESCA = nuovo seed random visibile (#2).
- **U3. Ghost interattivi pre-APPLICA** (#3): click seleziona, drag sposta, DEL
  rimuove, R = reroll del singolo oggetto, lucchetto = proteggi dai reroll,
  bottone "rigenera solo warn/fail". Richiede S6 per il reroll singolo pulito.
- **U4. "Perche' qui"** (#7): tooltip su ghost selezionato con breakdown
  CamouflageScore (rim/interior/texture/saliency + verdict validate).
- **U5. Opzioni APPLICA**: `is_goal`, `hint_delay`, `always_show` configurabili
  (oggi forzati in `_scatter_apply`); slider "intensita' mimetizzazione" che
  scala tint mix e alpha entro i clamp.
- **U6. Micro-fix**: input numerico per la quantita' + header slider corretto
  (#9), navigazione tastiera/filtro nel dropdown tag (#10), tooltip costi tier
  (VRAM/dimensioni/tempo, #5), voce undo dedicata per GENERA (#6).

## Parte P — Editor completo e professionale

Dall'inventario 2026-07-12: zero TODO/stub reali; i gap sono robustezza dati,
flussi di contenuto e doppio sistema modale. Fuori scope confermati (decisione
gia' presa, non riaprire): port Qt/imgui, dark theme, pannelli dockable.

- **P1. Robustezza dati (primo: rischio perdita lavoro)**
  - Crash recovery: l'autosave e' scritto ma MAI riletto (`io_ops.py:732`).
    All'avvio scena: se autosave piu' recente del save, proponi ripristino.
  - Backup rotativi al save (ultimi N, accanto a `.editor_trash/`).
  - Bonifica dei ~56 `except:` nudi in 14 file editor: eccezioni tipizzate
    minime + log (oggi inghiottono anche KeyboardInterrupt/bug reali).
  - `_img_cache` senza eviction + negative-cache permanente (`io_ops.py:816,824`):
    LRU con evict graduale (pattern gia' in engine) + retry dei path falliti.
- **P2. Unificazione modale**: migrare i modali storici (lang, newobj, tag,
  minigame, icon, music/bg/video) su modal stack + widget layer. Elimina il
  doppio dispatch `if self._x_modal` in `editor_base._render` e i bug input da
  coesistenza dei due sistemi.
- **P3. Outline di scena**: pannello lista oggetti piazzati (id, layer, goal,
  minigame) con filtro/ricerca, click -> seleziona+zoom, edit bulk delle
  proprieta' sulla multi-selezione.
- **P4. Allinea/distribuisci**: l'inventario non ne conferma la presenza
  (previsto come 1.3 del piano precedente): verificare e completare.
- **P5. Operazioni cross-scena**: trova/sostituisci `catalog_id` su tutto il
  gioco; report "oggetti di catalogo mai usati"; conteggio usi per oggetto.
- **P6. Wizard "nuovo gioco"**: template completo (game_config, cartelle,
  strings 5 lingue, primo livello/scena) in un flusso unico dalla dashboard.
- **P7. Workbench traduzioni**: vista tabellare chiavi x 5 lingue con
  missing/extra evidenziati, completezza per gioco (l'auditor gia' conta),
  export/import CSV per traduttori esterni.
- **P8. Checklist di pubblicazione**: wizard pre-build che concatena auditor +
  asset mancanti + traduzioni + statistiche difficolta' per scena + stima
  dimensione pacchetto -> verdetto "pronto per build" con lista blocchi.
- **P9. Pannello preferenze + cheat-sheet**: settings oggi sparsi in
  `.editor_settings.json` esposti in un pannello unico; overlay F1 con le
  scorciatoie.

## Ordine di esecuzione consigliato

| Ondata | Item | Perche' |
|--------|------|---------|
| 1 | S0, S1, S3 | fondamenta misurabili + salto qualitativo colore/bordo |
| 2 | S2, S6, U1, U2 | best-of-M col render + count garantito + scatter non bloccante |
| 3 | U3, U4, S4, S5 | controllo fine del designer + naturalezza fisica |
| 4 | P1, U5, U6 | robustezza dati + rifiniture scatter |
| 5 | P3, P7, P8 | flussi contenuto pro |
| 6 | S7, P2, P4, P5, P6, P9 | pulizia, unificazione, wizard |

Criteri di successo (misurati con S0):

- hard: >=80% verdetti "ok", 0 "fail" dopo repair; rim Delta-E medio in calo
  documentato vs baseline.
- Tempo generazione 100 oggetti entro budget fissato alla baseline (+30% max
  per il render-in-the-loop).
- Suite completa verde (117 test attuali + nuovi scatter/benchmark).

## Stato

### Ondata 1 — FATTA (2026-07-12)

- S0: `tools/scatter_benchmark.py` (36 run: 6 scene reali x 3 difficolta' x
  2 seed, JSON + contact sheet + `--compare`). Baseline e after in
  `scratch/scatter_bench/`.
- S1: `editor/tools/scatter_metrics.py` (CamouflageScore: rim/interior
  Delta-E, boundary contrast, texture mismatch, saliency delta, pop_score);
  `scatter_validate` ricablato sulla metrica unica (API invariata, soglie
  ricalibrate 22/38 -> 32/55 sulla scala pop, corr 0.785 su 1331 oggetti).
- S3: `lab_grid` per cella, `_color_similarity_map` in Lab con Delta-L pesato
  1.5x e ASIMMETRIA tint (L_obj < L_bg non recuperabile: il filtro
  moltiplicativo non schiarisce); mix tint OTTIMIZZATO per piazzamento
  (candidati 0..TINT_MIX_MAX per difficolta'); alpha adattivo
  (hard 232-246, medium 244-252). Fallback HSV intatto (no-cv2 e test
  sintetici).
- Risultati benchmark (metro fisso, stessi seed): medium pop_mean 25.2 -> 21.7
  (-14%), rim 15.2 -> 12.4 (-18%), ok% 69.1 -> 81.9; hard pop 24.0 -> 21.0,
  rim 14.2 -> 11.8, ok% 71.6 -> 81.5, fill 0.954 -> 0.981; easy migliora poco
  DI PROPOSITO (la banda di visibilita' tiene gli oggetti leggibili).
  Costo: place_ms +5-12%.
- Suite: 130 pass / 0 fail (13 test nuovi: metrics, lab color).

### Ondata 2 — FATTA (2026-07-12)

- S2: best-of-M render-in-the-loop in `place_objects` (`render_ctx` opzionale:
  fino a 5 celle candidate per tentativo, vince il pop_score piu' basso sul
  composito reale, cap RENDER_POP_MAX con relax; percorso pygame-free
  invariato senza ctx). Fix: celle vetate filtrate dal top-K prima del
  softmax (il best-of-M senza replacement esplodeva con poche celle valide).
- S6: `run_scatter_with_repair` in scatter_validate: place -> validate ->
  scarta fail -> RIPIAZZA i mancanti (max 2 giri), report onesto
  delivered/requested. Usata da benchmark e modal.
- U1: `_scatter_run` del modal in worker thread: barra progresso per fase
  (modello/analisi BG/catalogo/piazzamento N su M) + bottone ANNULLA + ESC;
  `place_objects` ha `progress_cb`/`cancel_event` (ScatterCancelled). Il
  worker lavora su una COPIA del BG (nessuna surface condivisa col render).
- U2: seed esposto nel modal: campo numerico editabile, lucchetto "seed
  fisso" (GENERA riusa il seed per iterare i parametri), seed usato sempre
  mostrato; RIPESCA forza un seed nuovo.
- Risultati (stesse scene/seed, metro fisso) baseline -> ondata2:
  medium pop 25.2 -> 18.9 (-25%), rim 15.2 -> 10.6 (-30%), ok% 69.1 -> 89.2,
  fail% 5.3 -> 0.0, fill 1.0; hard ok% 71.6 -> 93.8, fail 0, fill 0.977.
  CRITERIO DEL PIANO (hard >=80% ok, 0 fail post-repair) SUPERATO.
  Costo: place_ms ~2x (5.8s -> 11.2s hard per 40 oggetti) — ora in thread
  con cancel; riduzione prevista in S7 (cache sprite, patch piu' piccoli).
- Suite: 136 pass / 0 fail (6 test nuovi: render loop, cancel, repair).

### Ondata 3 — FATTA (2026-07-13)

- S4: veto FOOTPRINT via integral image (l'intera area visiva dell'oggetto,
  bbox ruotato incluso, non copre celle vietate: prima bastava il centro
  libero e un oggetto grande finiva mezzo su un volto) + gate STRADDLE
  (std della L Lab sotto il footprint oltre soglia = oggetto a cavallo di
  due zone, rifiutato; relax con attempts_frac).
- S5: appoggio da edge ORIZZONTALI (edge_density * |sin(grad_orient)|,
  hoisted fuori dal loop; chiude il doppio conteggio audit #38) con peso
  scalato su support_bot; clamp UPRIGHT (+/-10 gradi) per oggetti con base
  d'appoggio forte o tag 'upright' (niente bottiglie coricate).
- U3: modalita' ANTEPRIMA INTERATTIVA nel modal (pattern brush): panel
  nascosto, ghost selezionabili (click), trascinabili (drag con rimisura al
  rilascio), CANC elimina, R rigenera il singolo, L blocca; toolbar con
  RIPESCA (preserva i bloccati), RIGENERA VISIBILI (solo warn/fail),
  APPLICA, TORNA. Bordi ghost per stato: verde bloccato, arancio warn,
  azzurro selezionato.
- U4: breakdown "perche' qui" del ghost selezionato nello status (pop,
  bordo, interno, texture, clutter + verdetto) da results_by_placed
  (scatter_validate); rimisura live dopo ogni spostamento.
- Benchmark ondata2 -> ondata3: hard pop 18.2->18.1, rim 10.3->10.2,
  ok 93.8->90.9; medium pop 18.9->20.1, ok 89.2->86.9 (+1 fail su 480).
  Peggioramento marginale ATTESO: footprint/straddle/upright vietano
  posizioni che il pop_score non penalizza (mezzo-su-volto, a cavallo di
  zone, rotazioni innaturali) — correttezza e naturalezza prima del punto
  di metrica. Vs baseline il totale resta: medium pop -20%, ok 69->87.
- Suite: 147 pass / 0 fail (11 test nuovi: footprint/straddle/upright,
  worker modal, preview interattiva).

Prossima: ondata 4 (P1 robustezza dati: crash recovery autosave, backup
rotativi, bonifica except nudi, LRU immagini; U5 opzioni APPLICA; U6
micro-fix UI).
