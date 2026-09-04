# Asset Workflow - LINE ART style

Operating document to generate, process and integrate objects in the
**line art (black/white vector)** style into the engine.

> **Quick references**
> - Catalog: [engine/data/global_lineart_catalog.json](../../engine/data/global_lineart_catalog.json)
> - Asset folder: [engine/assets/objects_lineart/](../../engine/assets/objects_lineart/)
> - `style` value in the catalog: `"line art"` (with a space)
> - Mandatory ID prefix: `la_` (e.g. `la_corona`, `la_telescopio`)
> - Processing tool: [tools/process_assets.py](../../tools/process_assets.py) `--style lineart`
> - Batch history: [ASSETS_INTEGRATION_LOG.md](ASSETS_INTEGRATION_LOG.md)

---

## 1. Generation specs (AI)

### 1.1 Background and composition
- **Background**: **Cool Gray** `#788088` (bluish gray — NOT green)
- **Reason**: the dominant blue component (B > R) makes it possible to
  mathematically distinguish the background from the object's gray
  anti-aliasing pixels, preserving the pure white interior
- **Grid**: standard 3x3 (9 objects) or 4x4 (16 objects)
- **Margin**: >= 120-150 px of gray space between the objects and the edges
- **Forbidden**: drawn grids, division lines, frames, separators

### 1.2 Prompting strategy
- **Strict graphic style**: "Vector or ink line art, pure black (#000000) for
  the outlines and pure white (#FFFFFF) for the inner fills.
  **Absolutely no gray shades, gradients, shading or hatching (no cross-hatching)**"
- **Uniform stroke**: constant, well-defined thickness, no messy sketching.
  **All shapes must be closed** (so the gray background cannot leak into the object)
- **Background**: "Cool gray background `#788088`"
- **Material simplicity**: being line art, glass is an outlined white space
  (no optical distortion or AI transparency)

### 1.3 Universal constraints
- Front, side or isometric view — never oblique
- No human figures (unless explicitly required)
- No text or watermarks
- Recommended resolution for a 3x3 grid: 2048x2048; 4x4: 2560x2560

---

## 2. Processing pipeline

### 2.1 Algorithm
**Chrominance Offset** + **Monochrome Forcing** + **Auto-Trim**.

Unlike the color styles, line art extraction is **binary**:

```python
# 1. Background recognition via chromatic offset (blue > red)
is_cool_gray_bg = (b > r + 5) & (abs(g - 128) < 40)
is_dark_line   = (r + g + b) / 3 < 100

# 2. Transparency on the background
alpha[is_cool_gray_bg] = 0

# 3. Force pure black on the lines
r[~is_cool_gray_bg & is_dark_line] = 0
g[~is_cool_gray_bg & is_dark_line] = 0
b[~is_cool_gray_bg & is_dark_line] = 0

# 4. Force pure white on the fills
r[~is_cool_gray_bg & ~is_dark_line] = 255
g[~is_cool_gray_bg & ~is_dark_line] = 255
b[~is_cool_gray_bg & ~is_dark_line] = 255
```

The blue component of the background is the signature that makes it unique,
protecting the object's gray-white pixels from anti-aliasing smears.

### 2.2 Output
- Format: **PNG with an optimized palette** (2 colors + transparency)
- Alpha: **hard clipping**, a clean vector-like cut (no soft AA)
- Auto-trim: every object cropped to its actual pixels via `getbbox()`
- Files saved in: `engine/assets/objects_lineart/`

---

## 3. Tool usage

```bash
python tools/process_assets.py --style lineart <grid.png> engine/assets/objects_lineart/ "la_name1,la_name2,la_name3,la_name4,la_name5,la_name6,la_name7,la_name8,la_name9"
```

Notes:
- The `--style lineart` flag is mandatory.
- Names **must** start with the `la_` prefix.
- The number of names in the list determines the grid size
  (9 = 3x3, 16 = 4x4) through **dynamic detection**.

---

## 4. Catalog integration

Add every object to [engine/data/global_lineart_catalog.json](../../engine/data/global_lineart_catalog.json):

```json
{
  "id": "la_corona",
  "label_key": "obj_la_corona",
  "icon": "objects_lineart/la_corona.png",
  "default_detection": "rect",
  "default_width": 80,
  "default_height": 60,
  "default_hint_delay": 12,
  "tags": ["accessorio", "metallo", "vintage", "medio"],
  "style": "line art"
}
```

**Required fields**:
- `id` — unique snake_case identifier, **`la_` prefix mandatory**
- `label_key` — translation key (convention: `obj_<id>`)
- `icon` — path relative to `engine/assets/`, inside `objects_lineart/`
- `default_detection` — `"circle"` or `"rect"`
- `default_radius` (if circle) **or** `default_width` + `default_height` (if rect)
- `tags` — list of tags from the [canonical taxonomy](TAGS_TAXONOMY.md)
- `style` — always `"line art"` (with a space) for this catalog

> **Mind the `style` value**: for historical reasons it is `"line art"` with
> a space, NOT `"lineart"`. Verified in [engine/data/global_lineart_catalog.json](../../engine/data/global_lineart_catalog.json).

---

## 5. Localization

Every `label_key` **must** be present in all 5 official language files:

| File                                     | Language  |
|------------------------------------------|-----------|
| `engine/assets/strings/it.json`          | Italian   |
| `engine/assets/strings/en.json`          | English   |
| `engine/assets/strings/fr.json`          | French    |
| `engine/assets/strings/es.json`          | Spanish   |
| `engine/assets/strings/de.json`          | German    |

Per-game override (optional): `games/<game>/strings/{it,en,fr,es,de}.json`.

Example entry:
```json
"obj_la_corona": "Crown"
```

---

## 6. Tags

**Canonical source**: [TAGS_TAXONOMY.md](TAGS_TAXONOMY.md) -> [engine/data/tags_taxonomy.json](../../engine/data/tags_taxonomy.json).

Strict rules (see the dedicated document for details):
- **Required**: at least one SIZE + MATERIAL + DOMAIN tag per object
- **Forbidden** to create new tags without changing the official taxonomy
- **Forbidden** to use generic tags (`strumento`, `contenitore`, `equipaggiamento`) — always map to valid physical tags (e.g. `attrezzo`, `scatola`, `viaggio`)

Adding orphan tags fragments the database and breaks the display of the
UI chips in the editor.

---

## 7. Quality checklist (pre-merge)

- [ ] All icons exist in `engine/assets/objects_lineart/`
- [ ] All IDs have the `la_` prefix
- [ ] Every object has its `label_key` translated in IT/EN/FR/ES/DE
- [ ] All tags exist in `engine/data/tags_taxonomy.json`
- [ ] `style: "line art"` (with the space) present on every entry
- [ ] Only pure black `#000000` and pure white `#FFFFFF` in the non-transparent pixels
- [ ] No residual gray shades
- [ ] Auto-trim applied (no residual transparent space)
- [ ] The catalog audit passes: `python -X utf8 tools/audit_catalog.py`
