# Workflow Assets - Stile REAL

Documento operativo per generare, processare e integrare oggetti in stile
**realistico/fotografico** nel motore.

> **Riferimenti rapidi**
> - Catalogo: [engine/data/global_real_catalog.json](../engine/data/global_real_catalog.json)
> - Cartella asset: [engine/assets/objects/](../engine/assets/objects/)
> - Valore `style` nel catalogo: `"real"`
> - Prefisso ID consigliato: nessuno (es. `coltello_cucina`, `80s_lamp`)
> - Tool di processing: [tools/process_assets.py](../tools/process_assets.py) `--style real`

---

## 1. Specifiche di generazione (AI)

### 1.1 Sfondo e composizione
- **Sfondo**: **Pure Neon Green** `#00FF00`
- **Griglia**: 3×3 standard (9 oggetti) o 4×4 (16 oggetti)
- **Margine**: ≥ 120-150 px di spazio verde tra oggetti e bordi della griglia
- **Vietato**: griglie grafiche, linee di divisione, cornici, separatori, ombre proiettate (drop shadows) sul verde

### 1.2 Strategia di prompting
- **Orientamento**: frontale, laterale o isometrico — mai obliquo
- **Materiali ambigui**: istruzioni esplicite per vetro (es. "vetro opaco" o "riempito di liquido scuro") per evitare che il verde trapeli per rifrazione
- **Illuminazione**: cinematografica e nitida, **senza ombre proiettate** sullo sfondo verde
- **Stile fotografico**: dettagli iperrealistici, texture autentiche, niente rendering "cartoonish"

### 1.3 Vincoli universali
- Niente figure umane (se non esplicitamente richieste dall'asset)
- Niente testo o watermark sull'immagine
- Risoluzione consigliata griglia 3×3: 2048×2048; 4×4: 2560×2560

---

## 2. Pipeline di processing

### 2.1 Algoritmo
**Chroma Key avanzato con Green Score** + **Spill Suppression** + **Auto-Trim**.

```python
# Green Score: distingue il verde dello sfondo dal verde naturale (foglie, smeraldi)
green_score = g - (r + b) / 2
# → alpha mask con interpolazione lineare (bordi morbidi, niente seghettature)
```

```python
# Spill Suppression: neutralizza il riflesso verde su superfici lucide
condition = g > (r + b) / 2
g[condition] = np.maximum(r[condition], b[condition])
# → riflessi verdi → grigio/bianco naturale
```

### 2.2 Output
- Formato: **PNG RGBA 32-bit** (alpha morbida per bordi puliti)
- Auto-trim: ogni oggetto ritagliato ai pixel effettivi via `getbbox()`
- File salvati in: `engine/assets/objects/`

---

## 3. Uso del tool

```bash
python tools/process_assets.py --style real <grid.png> engine/assets/objects/ "nome1,nome2,nome3,nome4,nome5,nome6,nome7,nome8,nome9"
```

Note:
- `--style real` è il default (può essere omesso).
- Il numero di nomi nella lista determina la dimensione della griglia (9 = 3×3, 16 = 4×4) tramite **rilevamento dinamico**.
- I file vengono salvati come `<nome>.png` nella cartella destinazione.

---

## 4. Integrazione nel catalogo

Aggiungere ogni oggetto a [engine/data/global_real_catalog.json](../engine/data/global_real_catalog.json):

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

**Campi obbligatori**:
- `id` — identificativo univoco snake_case
- `label_key` — chiave traduzione (convenzione: `obj_<id>`)
- `icon` — path relativo a `engine/assets/`
- `default_detection` — `"circle"` o `"rect"`
- `default_radius` (se circle) **oppure** `default_width` + `default_height` (se rect)
- `tags` — lista di tag dalla [tassonomia canonica](TAGS_TAXONOMY.md)
- `style` — sempre `"real"` per questo catalogo

**Opzionale**:
- `default_hint_delay` — secondi prima che l'hint diventi cliccabile

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
"obj_skull_candle": "Candela a forma di teschio"
```

---

## 6. Tag

**Fonte canonica**: [docs/TAGS_TAXONOMY.md](TAGS_TAXONOMY.md) → [engine/data/tags_taxonomy.json](../engine/data/tags_taxonomy.json).

Regole tassative (vedi documento dedicato per dettagli):
- **Obbligo**: almeno un tag DIMENSIONE + MATERIALE + DOMINIO per oggetto
- **Vietato** creare nuovi tag senza modificare la tassonomia ufficiale
- **Vietato** usare tag generici (`strumento`, `contenitore`, `equipaggiamento`) — mappare sempre su tag fisici validi della tassonomia

---

## 7. Quality checklist (pre-merge)

- [ ] Tutte le icone esistono in `engine/assets/objects/`
- [ ] Ogni oggetto ha `label_key` tradotta in IT/EN/FR/ES/DE
- [ ] Tutti i tag esistono in `engine/data/tags_taxonomy.json`
- [ ] Campo `style: "real"` presente su tutte le entry
- [ ] Auto-trim applicato (nessuno spazio trasparente residuo)
- [ ] Nessun pixel verde residuo nei bordi (chroma key clean)
- [ ] Audit catalogo passa: `python -X utf8 tools/audit_catalog.py`
