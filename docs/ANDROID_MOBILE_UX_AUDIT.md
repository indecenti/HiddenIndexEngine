# Audit UX Mobile/Touch degli APK generati — Hidden Object Engine

Data: 2026-06-21. Branch: `fix/editor-critical-bugs`.
Obiettivo: portare gli APK generati dall'editor al livello di un Hidden Object Game (HOG)
mobile professionale (riferimenti di settore: June's Journey, Hidden City, Pearl's Peril,
Seekers Notes, The Secret Society).

## Architettura (accertata)

Gli APK NON impacchettano l'export web. `editor/android_build_system.py` usa
Buildozer / python-for-android dentro WSL per cross-compilare l'engine Python + pygame
(recipe `pygame`, non `pygame-ce`) per `arm64-v8a`. Quindi la "UI generata" su mobile e'
lo stesso engine `engine/` che gira nativo via SDL2. Coordinate di riferimento: 1280x720
(`engine/scaling_manager.py`). Su Android la risoluzione di rendering interna e' adattiva
con altezza fissa 540px, GPU-upscale via `pygame.SCALED`, vsync=0.

## Decisioni di prodotto (committente)

- Orientamento: **landscape** (coerente con REF 1280x720 e scene autorate orizzontali).
- Ispezione scena: **pinch-to-zoom + pan** (paradigma June's Journey/Hidden City).
- Device minimo: **mid-range** (~4GB RAM, 1080p) → budget 720p interni, cache adattiva.
- Avvio: **Fase 0 (quick wins) subito**, poi avanti per fasi.

## Cosa e' gia' buono (non rifare)

Safe-area/notch via display cutout; HUD a cassetto con maniglia/swipe e auto-chiusura;
distinzione tap-vs-swipe al rilascio; pulsante hint mobile nella barra; lifecycle
pause/resume su `APP_*BACKGROUND`; tasto Indietro `K_AC_BACK` contestuale; anti-spam click;
cursore nascosto + screensaver off; font HUD x1.5 su Android. Toolchain di build di livello
professionale (API 35, arm64, NDK 28.2, fast-path p4a, watchdog su stallo).

## Diagnosi: i gap che dominano

1. **Ispezione scena assente (critico).** `set_zoom`/`set_pan`/`screen_to_scene` esistono in
   `ScalingManager` ma sono codice morto; `MULTIGESTURE` e' bloccato (`core.py:133`). Su un
   telefono da 6" gli oggetti piccoli sono di fatto introvabili.
2. **Hit-test al pixel senza tolleranza (critico).** `ClickDetector.detect` richiede
   precisione esatta; un tap a pochi px e' un miss penalizzato.
3. **Rendering interno fisso a 540p + upscale nearest (carente).** UI pre-rimpicciolita a
   0.75x: oggetti e testo sgranati, difetto fatale per un genere "del guardare".
4. **Bug logico:** cliccare un goal corretto oltre il 7° visibile contava come errore
   (`core.py:590` + finestra `_max_visible=7`).
5. Mancano: haptics, micro-interazioni juicy sul find, lista a ICONE (oggi testo), onboarding,
   immersive sticky, audio focus, save-on-background, keystore release, adaptive icon/Splash API.

## Voti per dimensione

| Dimensione | Voto |
|---|---|
| Ispezione scena (zoom/lente/pan) | critico |
| Input touch & tap tolerance | critico |
| Feedback & juiciness (haptics/find) | critico |
| Rendering & scaling 540p | carente |
| HUD in-game mobile | carente |
| Menu & navigazione touch | carente |
| Build/packaging Play Store | carente |
| Integrazione sistema Android | carente |
| Performance & batteria | sufficiente |

## Roadmap

### Fase 0 — Quick wins di giocabilita' (COMPLETATA 2026-06-21)
- [x] Fat-finger tolerance: `ClickDetector.detect(slop_screen=...)` con fallback nearest-goal
  in bg-space (`_edge_distance`) + helper `ScalingManager.screen_dist_to_bg`.
- [x] Near-miss entro tolleranza: snap al goal (diventa un find), niente penalita'.
- [x] Fix penalita' su goal fuori dalla finestra di 7: rimosso il gate `is_target_active`
  in `core._process_scene_click` (ogni goal valido non trovato registra il find).
- [x] Hit-rect/visibilita' pausa a >=48dp equivalenti su Android (`hud_manager`).
- [x] `SDL_HINT_RENDER_SCALE_QUALITY=1` + texture filtering `linear` su Android.
- Test: `tests/test_coordinate_system.py::TestFatFingerTolerance` (6 test, verdi).
- Slop usato: `res_h * 0.045` (~7mm) solo su Android; mouse desktop invariato (slop 0).

### Fase 1 — Ispezione scena (COMPLETATA e VERIFICATA 2026-06-21)
Pinch-to-zoom + pan a due dita, piu' pan a una dita da ingranditi.
- Camera incorporata nella trasformazione affine background->schermo dello `ScalingManager`
  (`_base_bg_*` vs effettivi `_bg_*`, `_recompute_camera` con clamp pan ai bordi, `set_zoom`/
  `pan_by`/`zoom_at`/`reset_pan_zoom`): rendering BG, oggetti, effetti, glow e hit-test seguono
  la camera senza modifiche al codice di disegno. Zoom 1.0..3.0 (mid-range).
- Input via eventi `FINGER*` (multitouch reale) in `core._handle_finger_down/motion/up`;
  il tap a una dita resta sul mouse emulato (degrado grazioso se i FINGER non arrivano).
- Vincolo "nessun tap/penalità dai gesti" garantito da: flag `_gesture_seen` attivo finche'
  restano dita a contatto; azioni one-shot (hint/maniglia/pausa/oggetto) rinviate al RILASCIO
  filtrato; slop sul pan a una dita; blocco camera durante l'intro scenica; reset stato a
  inizio scena. Zoom dal BG originale per nitidezza.
- Test: `TestInteractiveCamera`, `TestGestureStateMachine` in `tests/test_coordinate_system.py`.
- Da fare in seguito: coachmark "pizzica per ingrandire" (con onboarding Fase 3); eventuale
  doppio-tap. NB: `screen_to_scene` (REF-space) resta orfano/dead-code, non usato dall'hit-test.

### Fase 2 — Nitidezza e leggibilita'
`internal_h` a 720 (REF-aligned, scale 1.0) con budget dinamico per device >=1080p; valutare
layer UI/testo a risoluzione nativa separato dal background; pre-resize asset in export; font
in dp reali via DisplayMetrics invece del fattore fisso 1.5x.

### Fase 3 — Feel da HOG premium (COMPLETATA e VERIFICATA 2026-06-21)
- Lista oggetti a ICONE: `hud_manager._draw_mobile_icons/_draw_icon_tile/_get_icon_thumb`
  (thumbnail cachate da `obj.icon_surface`, didascalia, fallback iniziale). Sostituisce le chip
  testuali. Found animato: scale-pop + spunta + dissolvenza (`_found_anim`), con auto-apertura
  breve del cassetto al ritrovamento per renderlo visibile. Cap tile per leggibilita'.
- Haptics: `engine/haptics.py` (no-op desktop, pyjnius Vibrator), chiamato in core su
  found/miss/success_strong. Permesso VIBRATE in `editor/android_build_system.py` (spec + p4a).
  Toggle "VIBRAZIONE" nelle impostazioni (solo Android), persistito via SaveManager (store
  scrivibile su Android, NON config.ini).
- Onboarding: coachmark first-run (`core._draw_coachmark`), gated `coach_seen` via SaveManager,
  Android+SCENE only; prima interazione lo CHIUDE e la consuma (no tap/penalità accidentale);
  non si sovrappone ai bubble intro; auto-dismiss 7s. Chiavi `coach_*` in it.json/en.json.
- Verifica: review avversariale (verdetto pronto-con-fix-minori); 2 must-fix risolti (tap di
  chiusura coach consumato; persistenza vibrazione via SaveManager). Test: `tests/test_haptics.py`.
- Non incluso (follow-up): fly-to-list scena->HUD; hint floating persistente in thumb-zone;
  centralizzazione persistenza config (audio/display hanno lo stesso limite read-only su Android).

### Fase 4 — Navigazione e sistema
Drag-to-scroll con inerzia nei menu + commit azione al rilascio; tap target ancorati a
safe-area e >=48dp; save snapshot su `APP_WILLENTERBACKGROUND`; immersive sticky via
`WindowInsetsController` ri-applicato al foreground; audio focus centralizzato in `AudioManager`.

### Build & test su device (2026-06-21)
- Asset-pruning per-gioco nel build Android (`_compute_kept_engine_assets` + prune in
  `_prepare_workspace`): rimuove la libreria condivisa `engine/assets` non usata a runtime
  (bg scene-local, icone game-local). APK LineVenture **558 -> 135 MB**.
- Fix build pygame: la "Patch 3" ora patcha la **recipe p4a** (`prebuild_arch` inietta i blitter
  SIMD nel template Setup prima della compilazione), risolvendo il bug
  "alphablit_alpha_sse2_* symbol not found" che crashava l'app a `pygame.display`.
- **Validato su emulatore** (Pixel_10 AVD, x86_64 + ARM translation): il gioco boota, menu,
  scena hidden-object (9 oggetti), input/tap, minigioco, oggetto trovato, e la lista a ICONE
  della Fase 3 con thumbnail + timer/score/progresso + HINT. Comando build:
  `python editor/android_build_manager.py <game> <ver> <dir> <status.json>`.
- Rifiniture: chiave i18n `hud_hint` aggiunta (5 lingue); `UI_Forbidden.wav` (mancante) ->
  `error4.mp3` in core.py.

### Ottimizzazioni performance (post-audit, 2026-06-21)
Audit perf multi-agente: su Android il costo erano operazioni NON cachate per-frame
(gli effetti "ricchi" erano gia' gated). Interventi (desktop invariato):
- Oggetti scena (core.py): chiave cache quantizzata (no invalidazione ad ogni pixel di
  pinch-zoom), `convert_alpha` una volta, MAX_ICON_DIM 1600 su Android, rimosso logger nel
  hot path.
- HUD (hud_manager.py): tile a icona composti CACHATI; scritte info-row memoizzate;
  DIRTY-FLAG sulla barra (`_hud_surf` ricomposto solo al cambio contenuto, altrimenti blit).
- Menu (menu_theme.py / cyber_neon_skin.py): titolo cyber_neon CACHATO (non piu' ~50
  font.render/frame); ombre/glow bottoni OFF su Android; riempimento "glass" dei bottoni
  CACHATO per dimensione/stato.
- Intro-zoom (core.py): render_target riusato (no alloc full-screen/frame) + `scale` invece
  di `smoothscale` su Android.
- Slot (slot_classic_game.py): sfondo (fill + raggiera) pre-renderizzato e cachato; glow
  radiale ambient e motion-blur dei simboli OFF su Android.
Risultati misurati su emulatore swiftshader: scn_hud 27->20ms, scn_obj 15-18->~6-10ms,
slot 10->14 FPS (poi sfondo cachato). NB: l'emulatore software cappa gli FPS; su device
reale con GPU HW i guadagni si traducono in frame rate molto piu' alti.

### Fase 5 — Packaging pubblicabile
`android.numeric_version` monotono; config keystore release (env `P4A_RELEASE_*`) + dialog
editor; adaptive icon (foreground/background) + Splash API/`presplash_color`; config packaging
unica condivisa tra `_generate_buildozer_spec` e `_get_p4a_apk_command`; esporre `orientation`
in `game_config.json`.

### Fase 6 — Performance e minigiochi
Rendering on-demand/dirty-frame + valutare vsync=1 al posto di `tick_busy_loop`; spostare
`convert()/convert_alpha()` sul main thread; cache surface adattiva alla RAM + `onTrimMemory`;
`TouchControls` come contratto in `BaseMinigame`; fix controlli touch di
asteroids/centipede/minipong/spot-differences.

## Decisioni aperte (da chiarire prima delle fasi relative)

- Near-miss: snap al goal (scelto per Fase 0) o solo non-penalizzato; sorte della miss penalty.
- Finestra di 7 oggetti: eliminata del tutto (lista scrollabile) o solo viewport visivo.
- Rendering: solo quick win (720 + linear) o layer UI a risoluzione nativa separato.
- Keystore: gestione manuale dall'editor o Play App Signing; dove conservare le credenziali.
- BG video su mobile (cv2 disabilitato): vietati o poster statico obbligatorio per scena.
