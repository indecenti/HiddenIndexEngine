# Workflow Assets - Stile CARTOON

Documento operativo per generare, processare e integrare oggetti in stile
**cartoon cell-shaded** (Adventure Family) nel motore.

> **Riferimenti rapidi**
> - Catalogo: [engine/data/global_cartoon_catalog.json](../engine/data/global_cartoon_catalog.json)
> - Cartella asset: [engine/assets/objects_cartoon/](../engine/assets/objects_cartoon/)
> - Valore `style` nel catalogo: `"cartoon"`
> - Prefisso ID obbligatorio: `ca_` (es. `ca_backpack_adv`)
> - Tool di processing: [tools/process_assets.py](../tools/process_assets.py) `--style cartoon`

---

## 1. Specifiche di generazione (AI)

### 1.1 Sfondo e composizione
- **Sfondo**: **Pure Neon Green** `#00FF00`
- **Griglia**: 3×3 standard (9 oggetti) o 4×4 (16 oggetti)
- **Margine**: ≥ 150 px di spazio verde tra oggetti e bordi
- **Vietato**: griglie grafiche, linee di divisione, cornici, separatori, ombre proiettate (drop shadows) sul verde

### 1.2 Strategia di prompting
- **Stile visivo**: "Adventure book illustration style, clean black outlines, cell shaded, vibrant but natural colors, flat shading with sharp shadows"
- **Dettaglio**: "Moderate detail, no gradients, no textures, bold lines"
- **Composizione singolo oggetto**: "Individual objects, isolated, front view or 3/4 isometric view"
- **Keyword di riferimento**: "Ligne claire, comic book style, high readability"

### 1.3 Vincoli universali
- Niente figure umane (se non esplicitamente richieste)
- Niente testo o watermark sull'immagine
- Outline neri costanti, riempimenti a colori piatti
- Risoluzione consigliata griglia 3×3: 2048×2048; 4×4: 2560×2560

---

## 2. Pipeline di processing

### 2.1 Algoritmo
**Chroma Key** + **Hard Spill Suppression** + **Alpha Clipping** + **Auto-Trim**.

Lo stile cartoon ha colori piatti, quindi:
1. **Chroma Key**: isola lo sfondo verde puro `#00FF00`.
2. **Spill Suppression (Hard)**: neutralizza ogni alone verde sui contorni neri, dato che lo stile non tollera sfumature.
3. **Alpha Clipping**: la trasparenza è **decisa**, non sfumata (niente AA morbido), per mantenere l'estetica "tagliata a mano".

### 2.2 Output
- Formato: **PNG RGBA 32-bit** con alpha binaria
- Auto-trim: ogni oggetto ritagliato ai pixel effettivi via `getbbox()`
- File salvati in: `engine/assets/objects_cartoon/`

---

## 3. Uso del tool

```bash
python tools/process_assets.py --style cartoon <grid.png> engine/assets/objects_cartoon/ "ca_nome1,ca_nome2,ca_nome3,ca_nome4,ca_nome5,ca_nome6,ca_nome7,ca_nome8,ca_nome9"
```

Note:
- Il flag `--style cartoon` è obbligatorio.
- I nomi **devono** iniziare con prefisso `ca_`.
- Il numero di nomi nella lista determina la dimensione della griglia (9 = 3×3, 16 = 4×4) tramite **rilevamento dinamico**.

---

## 4. Integrazione nel catalogo

Aggiungere ogni oggetto a [engine/data/global_cartoon_catalog.json](../engine/data/global_cartoon_catalog.json):

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

**Campi obbligatori**:
- `id` — identificativo univoco snake_case, **prefisso `ca_` obbligatorio**
- `label_key` — chiave traduzione (convenzione: `obj_<id>`)
- `icon` — path relativo a `engine/assets/`, in `objects_cartoon/`
- `default_detection` — `"circle"` o `"rect"`
- `default_radius` (se circle) **oppure** `default_width` + `default_height` (se rect)
- `tags` — lista di tag dalla [tassonomia canonica](TAGS_TAXONOMY.md)
- `style` — sempre `"cartoon"` per questo catalogo

---

## 5. Localizzazione

Ogni `label_key` **deve** essere presente in tutti i 5 file lingua ufficiali:

| File                                     | Lingua    |
|------------------------------------------|-----------|
| `engine/assets/strings/it.json`          | Italiano  |
| `engine/assets/strings/en.json`          | Inglese   |
| `engine/assets/strings/fr.json`          | Francese  |
| `engine/assets/strings/es.json`          | Spagnolo  |
| `engine/assets/strings/de.json`          | Tedesco   |

Override per gioco (opzionale): `games/<gioco>/strings/{it,en,fr,es,de}.json`.

Esempio entry:
```json
"obj_ca_backpack_adv": "Zaino da avventuriero"
```

---

## 6. Tag

**Fonte canonica**: [docs/TAGS_TAXONOMY.md](TAGS_TAXONOMY.md) → [engine/data/tags_taxonomy.json](../engine/data/tags_taxonomy.json).

Regole tassative (vedi documento dedicato per dettagli):
- **Obbligo**: almeno un tag DIMENSIONE + MATERIALE + DOMINIO per oggetto
- **Vietato** creare nuovi tag senza modificare la tassonomia ufficiale
- **Vietato** creare tag descrittivi dello stile (`disegnato`, `cartoon`, `ligne_claire`): lo stile è già nel campo `style`
- **Vietato** usare tag generici (`strumento`, `contenitore`, `equipaggiamento`) — mappare sempre su tag fisici validi

---

## 7. Quality checklist (pre-merge)

- [ ] Tutte le icone esistono in `engine/assets/objects_cartoon/`
- [ ] Tutti gli ID hanno prefisso `ca_`
- [ ] Ogni oggetto ha `label_key` tradotta in IT/EN/FR/ES/DE
- [ ] Tutti i tag esistono in `engine/data/tags_taxonomy.json`
- [ ] Campo `style: "cartoon"` presente su tutte le entry
- [ ] Auto-trim applicato (nessuno spazio trasparente residuo)
- [ ] Nessun pixel verde residuo sui bordi neri (spill suppression hard)
- [ ] Audit catalogo passa: `python -X utf8 tools/audit_catalog.py`
