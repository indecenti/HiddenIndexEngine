# Asset Workflow - REAL style

Operating document to generate, process and integrate objects in the
**realistic/photographic** style into the engine.

> **Quick references**
> - Catalog: [engine/data/global_real_catalog.json](../../engine/data/global_real_catalog.json)
> - Asset folder: `engine/assets/objects/`
> - `style` value in the catalog: `"real"`
> - Recommended ID prefix: none (e.g. `kitchen_knife`, `80s_lamp`)
> - Processing tool: [tools/process_assets.py](../../tools/process_assets.py) `--style real`

---

## 1. Generation specs (AI)

### 1.1 Background and composition
- **Background**: **Pure Neon Green** `#00FF00`
- **Grid**: standard 3x3 (9 objects) or 4x4 (16 objects)
- **Margin**: >= 120-150 px of green space between the objects and the grid edges
- **Forbidden**: drawn grids, division lines, frames, separators, drop shadows on the green

### 1.2 Prompting strategy
- **Orientation**: front, side or isometric — never oblique
- **Ambiguous materials**: explicit instructions for glass (e.g. "frosted glass" or "filled with a dark liquid") so the green does not leak through by refraction
- **Lighting**: cinematic and crisp, **without drop shadows** on the green background
- **Photographic style**: hyper-realistic details, authentic textures, no "cartoonish" rendering

### 1.3 Universal constraints
- No human figures (unless explicitly required by the asset)
- No text or watermarks on the image
- Recommended resolution for a 3x3 grid: 2048x2048; 4x4: 2560x2560

---

## 2. Processing pipeline

### 2.1 Algorithm
**Advanced chroma key with Green Score** + **Spill Suppression** + **Auto-Trim**.

```python
# Green Score: distinguishes the background green from natural green (leaves, emeralds)
green_score = g - (r + b) / 2
# -> alpha mask with linear interpolation (soft edges, no jaggies)
```

```python
# Spill Suppression: neutralizes the green reflection on glossy surfaces
condition = g > (r + b) / 2
g[condition] = np.maximum(r[condition], b[condition])
# -> green reflections -> natural gray/white
```

### 2.2 Output
- Format: **32-bit RGBA PNG** (soft alpha for clean edges)
- Auto-trim: every object cropped to its actual pixels via `getbbox()`
- Files saved in: `engine/assets/objects/`

---

## 3. Tool usage

```bash
python tools/process_assets.py --style real <grid.png> engine/assets/objects/ "name1,name2,name3,name4,name5,name6,name7,name8,name9"
```

Notes:
- `--style real` is the default (it can be omitted).
- The number of names in the list determines the grid size (9 = 3x3, 16 = 4x4) through **dynamic detection**.
- Files are saved as `<name>.png` in the destination folder.

---

## 4. Catalog integration

Add every object to [engine/data/global_real_catalog.json](../../engine/data/global_real_catalog.json):

```json
{
  "id": "skull_candle",
  "label_key": "obj_skull_candle",
  "icon": "objects/skull_candle.png",
  "default_detection": "circle",
  "default_radius": 35,
  "default_hint_delay": 12,
  "tags": ["cera", "decorazione", "horror", "luce", "medio", "osso"],
  "style": "real"
}
```

**Required fields**:
- `id` — unique snake_case identifier
- `label_key` — translation key (convention: `obj_<id>`)
- `icon` — path relative to `engine/assets/`
- `default_detection` — `"circle"` or `"rect"`
- `default_radius` (if circle) **or** `default_width` + `default_height` (if rect)
- `tags` — list of tags from the [canonical taxonomy](TAGS_TAXONOMY.md)
- `style` — always `"real"` for this catalog

**Optional**:
- `default_hint_delay` — seconds before the hint becomes clickable

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
"obj_skull_candle": "Skull-shaped candle"
```

---

## 6. Tags

**Canonical source**: [TAGS_TAXONOMY.md](TAGS_TAXONOMY.md) -> [engine/data/tags_taxonomy.json](../../engine/data/tags_taxonomy.json).

Strict rules (see the dedicated document for details):
- **Required**: at least one SIZE + MATERIAL + DOMAIN tag per object
- **Forbidden** to create new tags without changing the official taxonomy
- **Forbidden** to use generic tags (`strumento`, `contenitore`, `equipaggiamento`) — always map to valid physical tags of the taxonomy

---

## 7. Quality checklist (pre-merge)

- [ ] All icons exist in `engine/assets/objects/`
- [ ] Every object has its `label_key` translated in IT/EN/FR/ES/DE
- [ ] All tags exist in `engine/data/tags_taxonomy.json`
- [ ] `style: "real"` present on every entry
- [ ] Auto-trim applied (no residual transparent space)
- [ ] No residual green pixels on the edges (clean chroma key)
- [ ] The catalog audit passes: `python -X utf8 tools/audit_catalog.py`
