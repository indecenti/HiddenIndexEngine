---
name: add-asset
description: Adds an object asset to the HiddenIndexEngine catalog end to end (image import, background removal with rembg, catalog registration, tags and i18n). Use it when the user wants to add new objects/assets, process raw images, or register PNGs in the cartoon/lineart catalog.
---

# add-asset

Object asset addition pipeline.

## Steps

1. **Import + crop**: start from the raw image (often a grid of assets).
   Reference scripts in `scratch/` (`crop_and_import*.py`, `process_grid*.py`)
   and `tools/process_assets.py`. Read the script header before using it.
2. **Background removal (rembg)**: produces PNGs with a clean alpha.
   See `scratch/import_scripts/fix_all_images_rembg.py` and `docs/assets/IMAGE_PROCESSING_GUIDELINES.md`.
   PNGs ALWAYS live on the filesystem (never inside JSON).
3. **File location**: shared assets in `engine/assets/objects_cartoon/` (or
   `objects_lineart/`); game-specific assets in `games/<game>/objects/`.
4. **Catalog registration**: add an entry to `engine/data/global_cartoon_catalog.json`
   (global) or `games/<game>/objects_catalog.json` (local). Schema in
   `engine/schemas/catalog_schema.json`. Required fields:
   - `id` (lowercase snake_case, unique), `label_key` (`obj_<id>`),
     `icon` (e.g. `objects_cartoon/<id>.png`), `style` (`cartoon`/`line art`/`real`),
     `default_detection` (`rect`/`circle`/`mask`/`poly`).
   - For `rect`/`poly`: `default_width` + `default_height`. For `circle`: `default_radius`.
   - `tags`: list of lowercase snake_case tags.
   - Write through `engine.utils.safe_write_json` (atomic), never by hand into the open file.
5. **i18n / tags**: normalize and translate tags and labels.
   `tools/normalize_catalog.py`, `tools/seed_taxonomy_translations.py`.
   Taxonomy in `docs/assets/TAGS_TAXONOMY.md`.

## Verification

- `python tools/audit_catalog.py` — duplicate ids / schema.
- MCP tool `check_missing_assets` — entries without a PNG on disk.
- MCP tool `render_asset <catalog_id>` — see the rendered asset.

## Rules

- No new dependencies without approval.
- Do not delete PNGs shared by several catalog entries (see `GEMINI.md`,
  Asset Lifecycle section).
