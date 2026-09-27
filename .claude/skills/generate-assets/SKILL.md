---
name: generate-assets
description: Generates new photorealistic object assets and 16:9 scene backgrounds for a HiddenIndexEngine game with the local Qwen-Image 2.1 (ComfyUI), four per render in a 2x2 grid, cuts them out and registers them in the game catalog with tags and names in five languages. Use it when the user asks to create/generate new objects or assets with AI, Qwen, ComfyUI, or wants a batch of objects "we do not have yet".
---

# generate-assets

Local generation of object PNGs with Qwen-Image 2.1 through ComfyUI, then cut-out
and catalog registration. First batch: 113 objects for Malonno_Survivors
(2026-09-26). Scripts in `scripts/`, working files in `scratch/gen_assets/`
(`raw/` quadrants, `raw_grid/` grids and `batch.log`, `raw_grey/` references).

## Setup (check before generating)

- ComfyUI: `D:\ComfyUI`, API on `http://127.0.0.1:8188`. If it is off, start only the
  engine: `D:\ComfyUI\venv\Scripts\python.exe main.py --use-pytorch-cross-attention`
  (cwd `D:\ComfyUI`), wait for `/system_stats`. Do not run `avvia.bat`: it prompts.
- `llama-server.exe` (the user's local LLM) slows model loading from ~15 s to ~500 s.
  ASK the user before stopping it; remind at the end: `D:\Qwen3.8 27b\riavvia-llama.bat`.
- Models (already installed): `models/unet/qwen_image_2.1-Q8_0.gguf`,
  `text_encoders/qwen3vl_8b_fp8_scaled.safetensors`, `vae/qwen_image_2.1_vae_bf16.safetensors`,
  node `ComfyUI-GGUF`. Graph = the user's workflow `Qwen-Image-2.1.json` (euler/simple,
  25 steps, cfg 1). GPU: RTX 3070 Ti 8 GB.

## Steps

1. **Pick objects that do not exist.** Check the merged catalog
   (`engine.catalog_manager.load_catalog(game).all_ids()`), real-style ids (no `ca_`,
   `la_`, `ci_`, `ra_` prefix), by keyword AND by concept. Keep the game's style
   (Malonno: real, alpine village, abandoned, mystery). **No green objects** (the grid is
   keyed on chroma green and green disappears).
2. **Write the list** as rows `(id, prompt, (w, h), tags, [en, it, de, es, fr])` in
   `scripts/candidates_100.py` (or a new file following it). Tags ONLY from
   `engine/data/tags_taxonomy.json` (one DIMENSIONE + MATERIALE + DOMINIO); size as the
   default detection rect in background px (see existing entries). Validate tags and
   unique ids with a quick script before rendering.
3. **Render**: `python .claude/skills/generate-assets/scripts/generate_batch.py`
   (background task). 4 objects per 1536x1536 grid, ~200-250 s per grid (~56 s per object,
   vs ~90 s alone). Resumes: a grid whose four quadrants exist is skipped; failures are
   logged and skipped. Look at the first 2 grids before letting it run.
4. **Import**: `python .claude/skills/generate-assets/scripts/import_generated.py <ids>`
   (`--redo` redoes the image of an existing entry). Green key relative to the backdrop,
   despill, contact-shadow removal, crop, longest side 260 px (like the existing objects),
   PNG in `games/<game>/objects/`, entry in `objects_catalog.json` (`style: real`), names
   `obj_<id>` in the five game language files, all through `safe_write_json`.
   Never overwrites an existing id or PNG. `--global` registers in the engine catalog
   (`engine/data/global_real_catalog.json`, PNG in `engine/assets/objects/`) for objects
   meant for any game; otherwise `--game=<id>` (default Malonno_Survivors).
5. **Review**: `python .claude/skills/generate-assets/scripts/contact_sheet.py <ids>` ->
   `scratch/gen_assets/_sheet.png` on dark / light / red backdrops. Check holes (inside
   rings), glass, semi-transparent parts, shape vs description. List the misses and
   regenerate them in a new grid.
6. `python tools/audit_catalog.py`: the game must have no error.

## Scene backgrounds (new levels)

`python .claude/skills/generate-assets/scripts/generate_background.py <name> "<scene>" [seed]`
-> `scratch/gen_assets/backgrounds/<name>.png`, 3840x2160 (plus `<name>_native.png`).
Native 1920x1088 at 35 steps (~2-3 min), then soft blur + Lanczos 2x + unsharp.
- **User preference: FEW posters/signs** (at most one small faded one); detail from
  weathered materials and small props, not wall art. Kept in the prompt and negative.
- Do NOT use 4x-UltraSharp: it creates a fine grid pattern on dark smooth surfaces
  (boiler, walls), visible at 100% zoom, even from a softened input.
- Always check a 100% crop of a dark area before handing it over.
- No people, no readable text; the findable objects are placed later in the editor.

## Lessons (why the scripts are the way they are)

- rembg (only `u2net` is installed; do not download other models without asking) keeps
  the background ENCLOSED by the object (rosary loops, crampon frame): it is used only on
  grey-backdrop renders of solid objects (`generate_qwen21.py`, single object).
- Chroma green solves holes and even keeps glass (spectacle lenses). Fixed thresholds
  keyed green REFLECTIONS on metal (tin side, knocker ball): thresholds are shares of the
  backdrop's own green excess (`GREEN_FULL_SHARE`, `GREEN_SOFT_SHARE`).
- Glossy dark materials take a green tint; despill caps green at the mean of red and blue.
  For a strong cast use a grey reference render (`COLOUR_FROM_GREY`, `raw_grey/`) - not on
  neutral steel, which turns bluish.
- The model paints a contact shadow: near black and partly transparent after the key,
  removed (`SHADOW_MAX_RGB`, `SHADOW_MAX_ALPHA`).
- A quadrant can come out a bit off the description (bed warmer without its long handle,
  chestnut pan without holes): review every sheet.

## Rules

- **Objects are generic, always.** Ids, names and prompts describe the object, never
  a character, place or plot of a story ("opened telegram", not "Augusto's telegram";
  no readable messages or names on it). Every object must be reusable in any game.

- No new dependencies. No emoji. Assets are data of the game: the PNG and the catalog
  entries are committed only when the user asks (the game folder often has the user's own
  uncommitted work - stage only the new ids).
