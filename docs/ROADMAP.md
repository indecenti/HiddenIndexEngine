# ROADMAP HiddenIndexEngine

Stato per area e lavoro residuo. Questo file sostituisce i vecchi `NEXT_STEPS.md`
e gli `*_STATUS`/`*_SUMMARY` sparsi nella root (rimossi perche' obsoleti).
Aggiornare quando un'area cambia stato.

Legenda: [x] completo · [~] in corso/parziale · [ ] da fare.

## Fondamenta engine (remediation)

- [x] Tier fondamenta (step 1-10): scaling, coordinate, click detection, hint, save, validazione.
- [ ] Tier "dopo" (step 11-14): miglioramenti non bloccanti.
- [ ] Decisioni aperte:
  - miss penalty: allineare la formula Python e quella JS del runtime web.
  - glow indicator: definire il comportamento dell'indicatore visivo.
- Vincolo permanente: il runtime e' duplicato Python (engine) e JS (web). Ogni
  modifica alla logica condivisa va propagata su entrambi (vedi `docs/web/WEB_EXPORT_SYNC.md`).

## Editor

- [x] Audit P1-P4 (273 rilievi): critici, alti, bug medi, codice morto. Vedi `docs/editor/EDITOR_AUDIT_REPORT.md`.
- [x] Piano di miglioramento (5 fasi, `docs/editor/EDITOR_IMPROVEMENT_PLAN.md`) COMPLETATO:
  - Fondamenta UI: widget layer (`ui/widgets.py`), stack modale unificato,
    editing testo centralizzato, DPI awareness + scala UI, hitbox menubar dinamiche.
  - UX canvas: nudge frecce, zoom-to-selection, griglia configurabile, snap a
    oggetti con guide, undo con etichette/coalescing/selezione preservata.
  - Studio asset (PNG): crop con maniglie, redo, pennello restore, rimozione
    sfondo AI (rembg), resize, filtri colore, contorno; import con processing e
    import batch con registrazione catalogo + i18n.
  - Level design: playtest scena (`main.py --scene`, bottone in status bar),
    statistiche scena con stima difficolta' (scoring scatter_engine), anteprima
    come-in-gioco (F5), preset gruppi oggetti, auditor esteso (6 nuovi check).
  - Dashboard: duplica scena/livello, sposta scena tra livelli, riordino giochi.
  - Refactor: pipeline build EXE/APK unificata (`build_common.py`),
    `AssetCatalog` condiviso bg/musica/video, export web con progress+cancel,
    open scena asincrono, clipboard unico.

## Sistema menu (skin)

- [x] Architettura a skin (core + skin pluggabile) lato Python: `default`, `horror`, `kids`, `cyber_neon`, `mystery`.
- [ ] Skin web (hybrid DOM/CSS): approccio approvato, ancora da implementare nel runtime web.

## Android / mobile UX

Dettaglio in `docs/android/ANDROID_MOBILE_UX_AUDIT.md`. Decisioni prese: landscape,
pinch-zoom + pan, target mid-range. Validato su emulatore (boot, menu, scena HOG,
lista oggetti, find, minigioco).

- [x] Fase 0/1/3 (input, scena, lista oggetti) + asset pruning (APK 558 -> 135 MB).
- [x] Fix build pygame SIMD a livello recipe + persistenza config su path scrivibile.
- [ ] Fase 2: nitidezza a 720p.
- [ ] Fase 4: navigazione e integrazione col sistema (back, lifecycle).
- [ ] Fase 5: packaging finale (icone, splash, store).
- [ ] Fase 6: performance e minigiochi su mid-range.

## Contenuti (evergreen)

- [ ] Achievements: `engine/achievements_manager.py` + valutazione a fine livello.
- [ ] Leaderboard: best score / best time per livello con trend.
- [ ] Profili qualita' rendering (high/medium/low) con auto-downgrade sotto soglia FPS.
- [ ] Nuovi livelli/scene e completamento traduzioni (it/en/es/fr/de) per i giochi attivi.

## Tooling sviluppo

- [x] MCP server di progetto (`tools/hie_mcp_server.py`): render headless, validazione scene, ricerca catalogo.
- [x] Skill di progetto (`.claude/skills/`): `build-apk`, `run-game`, `add-asset`, `validate-scene`.
- [ ] Eventuale pulizia di `scratch/` (decine di script usa-e-getta e PNG temporanei tracciati da git).
