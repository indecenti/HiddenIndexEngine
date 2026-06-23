---
name: add-asset
description: Aggiunge un asset oggetto al catalogo di HiddenIndexEngine end-to-end (import immagine, rimozione sfondo con rembg, registrazione nel catalogo, tag e i18n). Usala quando l'utente vuole aggiungere nuovi oggetti/asset, processare immagini grezze, o registrare PNG nel catalogo cartoon/lineart.
---

# add-asset

Pipeline di aggiunta asset oggetto.

## Passi

1. **Import + ritaglio**: parti dall'immagine grezza (spesso una griglia di asset).
   Script di riferimento in `scratch/` (`crop_and_import*.py`, `process_grid*.py`)
   e `tools/process_assets.py`. Leggi l'header dello script prima di usarlo.
2. **Rimozione sfondo (rembg)**: produce PNG con alpha pulito.
   Vedi `fix_all_images_rembg.py` (root) e `docs/assets/IMAGE_PROCESSING_GUIDELINES.md`.
   I PNG vivono SEMPRE su filesystem (mai in-JSON).
3. **Posizione file**: asset condivisi in `engine/assets/objects_cartoon/` (o
   `objects_lineart/`); asset specifici di un gioco in `games/<game>/objects/`.
4. **Registrazione catalogo**: aggiungi una entry in `engine/data/global_cartoon_catalog.json`
   (globale) o `games/<game>/objects_catalog.json` (locale). Schema in
   `engine/schemas/catalog_schema.json`. Campi richiesti:
   - `id` (lowercase snake_case, univoco), `label_key` (`obj_<id>`),
     `icon` (es. `objects_cartoon/<id>.png`), `style` (`cartoon`/`line art`/`real`),
     `default_detection` (`rect`/`circle`/`mask`/`poly`).
   - Per `rect`/`poly`: `default_width` + `default_height`. Per `circle`: `default_radius`.
   - `tags`: lista lowercase snake_case.
   - Scrivi via `engine.utils.safe_write_json` (atomico), mai a mano nel file aperto.
5. **i18n / tag**: normalizza e traduci tag e label.
   `tools/normalize_catalog.py`, `tools/seed_taxonomy_translations.py`.
   Tassonomia in `docs/assets/TAGS_TAXONOMY.md`.

## Verifica

- `python tools/audit_catalog.py` — id duplicati / schema.
- Tool MCP `check_missing_assets` — entry senza PNG su disco.
- Tool MCP `render_asset <catalog_id>` — vedi l'asset renderizzato.

## Regole

- Niente nuove dipendenze senza approvazione.
- Non cancellare PNG condivisi tra piu' entry del catalogo (vedi `GEMINI.md`,
  sezione Asset Lifecycle).
