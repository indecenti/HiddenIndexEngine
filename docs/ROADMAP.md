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
- [ ] Grandi refactor di ridondanza (rimandati per rischio, non bug):
  - unificare la pipeline di build desktop e Android.
  - `AssetCatalog` condiviso per background / musica / video.
  - editing testo centralizzato tra i modali.

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
