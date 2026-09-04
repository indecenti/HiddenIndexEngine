# Asset Workflow - CARTOON style

Operating document to generate, process and integrate objects in the
**cel-shaded cartoon** style (Adventure Family) into the engine.

> **Quick references**
> - Catalog: [engine/data/global_cartoon_catalog.json](../../engine/data/global_cartoon_catalog.json)
> - Asset folder: [engine/assets/objects_cartoon/](../../engine/assets/objects_cartoon/)
> - `style` value in the catalog: `"cartoon"`
> - Mandatory ID prefix: `ca_` (e.g. `ca_backpack_adv`)
> - Processing tool: [tools/process_assets.py](../../tools/process_assets.py) `--style cartoon`

---

## 1. Generation specs (AI)

### 1.1 Background and composition
- **Background**: **Pure Neon Green** `#00FF00`
- **Grid**: standard 3x3 (9 objects) or 4x4 (16 objects) laid out neatly
- **Margin**: >= 150 px of green space between the objects and the edges
- **STRICTLY FORBIDDEN**: drawn grids, division lines (horizontal or vertical separators), frames, boxes, separators, drop shadows on the green.

### 1.2 Prompting strategy
- **Visual style**: "Adventure book illustration style, clean black outlines, cel shaded, vibrant but natural colors, flat shading with sharp shadows"
- **Detail**: "Moderate detail, no gradients, no textures, bold lines"
- **Single-object composition**: "Individual objects, isolated, front view or 3/4 isometric view"
- **Reference keywords**: "Ligne claire, comic book style, high readability"

### 1.3 Universal constraints
- No human figures (unless explicitly required)
- **ABSOLUTE BAN ON TEXT**: no words, letters, numbers, labels, captions, subtitles or watermarks on the image (not even fake AI text / gibberish under the objects)
- Constant black outlines, flat color fills
- Recommended resolution for a 3x3 grid: 2048x2048; 4x4: 2560x2560

---

## 2. Processing pipeline

### 2.1 Algorithm
**Chroma Key** + **Hard Spill Suppression** + **Alpha Clipping** + **Auto-Trim**.

The cartoon style has flat colors and thick black outlines, so:
1. **Chroma Key**: isolates the pure green background `#00FF00`.
2. **Spill Suppression (hard)**: neutralizes every green halo on the outer black outlines, fully preserving the black of the outline.
3. **Outline preservation (MANDATORY)**: the alpha cut must happen **exactly along the outer black outline of the object**. Eroding or thinning the black outline is strictly forbidden (no outline erosion); the object image must remain graphically and aesthetically 100% intact.
4. **Alpha Clipping**: transparency is **hard**, not feathered (no soft AA that creates halos), to keep the "hand-cut" look along the outer outline.

### 2.2 Output
- Format: **32-bit RGBA PNG** with a clean binary alpha on the outer outline
- Auto-trim: every object cropped to the actual pixels of the outer edge via `getbbox()`
- Files saved in: `engine/assets/objects_cartoon/`

---

## 3. Tool usage

```bash
python tools/process_assets.py --style cartoon <grid.png> engine/assets/objects_cartoon/ "ca_name1,ca_name2,ca_name3,ca_name4,ca_name5,ca_name6,ca_name7,ca_name8,ca_name9"
```

Notes:
- The `--style cartoon` flag is mandatory.
- Names **must** start with the `ca_` prefix.
- The number of names in the list determines the grid size (9 = 3x3, 16 = 4x4) through **dynamic detection**.

---

## 4. Catalog integration

Add every object to [engine/data/global_cartoon_catalog.json](../../engine/data/global_cartoon_catalog.json):

```json
{
  "id": "ca_backpack_adv",
  "label_key": "obj_ca_backpack_adv",
  "icon": "objects_cartoon/ca_backpack_adv.png",
  "default_detection": "rect",
  "default_width": 60,
  "default_height": 75,
  "tags": ["accessorio", "viaggio", "stoffa", "medio"],
  "style": "cartoon"
}
```

**Required fields**:
- `id` — unique snake_case identifier, **`ca_` prefix mandatory**
- `label_key` — translation key (convention: `obj_<id>`)
- `icon` — path relative to `engine/assets/`, inside `objects_cartoon/`
- `default_detection` — `"circle"` or `"rect"`
- `default_radius` (if circle) **or** `default_width` + `default_height` (if rect)
- `tags` — list of tags from the [canonical taxonomy](TAGS_TAXONOMY.md)
- `style` — always `"cartoon"` for this catalog

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
"obj_ca_backpack_adv": "Adventurer's backpack"
```

---

## 6. Tags

**Canonical source**: [TAGS_TAXONOMY.md](TAGS_TAXONOMY.md) -> [engine/data/tags_taxonomy.json](../../engine/data/tags_taxonomy.json).

Strict rules (see the dedicated document for details):
- **Required**: at least one SIZE + MATERIAL + DOMAIN tag per object
- **Forbidden** to create new tags without changing the official taxonomy
- **Forbidden** to create tags describing the style (`disegnato`, `cartoon`, `ligne_claire`): the style is already in the `style` field
- **Forbidden** to use generic tags (`strumento`, `contenitore`, `equipaggiamento`) — always map to valid physical tags

---

## 7. Quality checklist (pre-merge)

- [ ] All icons exist in `engine/assets/objects_cartoon/`
- [ ] All IDs have the `ca_` prefix
- [ ] Every object has its `label_key` translated in IT/EN/FR/ES/DE
- [ ] All tags exist in `engine/data/tags_taxonomy.json`
- [ ] `style: "cartoon"` present on every entry
- [ ] Auto-trim applied (no residual transparent space)
- [ ] No residual green pixels on the black edges (hard spill suppression)
- [ ] The catalog audit passes: `python -X utf8 tools/audit_catalog.py`
