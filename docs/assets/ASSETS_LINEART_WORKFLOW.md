# Workflow Assets - Stile LINE ART

Documento operativo per generare, processare e integrare oggetti in stile
**line art (bianco/nero vettoriale)** nel motore.

> **Riferimenti rapidi**
> - Catalogo: [engine/data/global_lineart_catalog.json](../engine/data/global_lineart_catalog.json)
> - Cartella asset: [engine/assets/objects_lineart/](../engine/assets/objects_lineart/)
> - Valore `style` nel catalogo: `"line art"` (con spazio)
> - Prefisso ID obbligatorio: `la_` (es. `la_corona`, `la_telescopio`)
> - Tool di processing: [tools/process_assets.py](../tools/process_assets.py) `--style lineart`
> - Storico batch: [ASSETS_INTEGRATION_LOG.md](ASSETS_INTEGRATION_LOG.md)

---

## 1. Specifiche di generazione (AI)

### 1.1 Sfondo e composizione
- **Sfondo**: **Cool Gray** `#788088` (grigio azzurrato — NON verde)
- **Motivazione**: la componente blu dominante (B > R) permette di distinguere
  matematicamente lo sfondo dai pixel grigi di antialiasing dell'oggetto,
  preservando l'interno bianco puro
- **Griglia**: 3×3 standard (9 oggetti) o 4×4 (16 oggetti)
- **Margine**: ≥ 120-150 px di spazio grigio tra oggetti e bordi
- **Vietato**: griglie grafiche, linee di divisione, cornici, separatori

### 1.2 Strategia di prompting
- **Stile grafico rigoroso**: "Line art vettoriale o a inchiostro, nero puro
  (#000000) per i contorni e bianco puro (#FFFFFF) per i riempimenti interni.
  **Assolutamente nessuna sfumatura di grigio, gradienti, ombreggiature o
  tratteggi (no cross-hatching)**"
- **Tratto uniforme**: spessore costante e definito, niente sketching
  disordinato. **Tutte le forme devono essere chiuse** (per non far penetrare
  lo sfondo grigio nell'oggetto)
- **Sfondo**: "Cool gray background `#788088`"
- **Semplicità materiale**: essendo line art, il vetro è uno spazio bianco
  delineato (niente distorsioni ottiche o trasparenze AI)

### 1.3 Vincoli universali
- Visuale frontale, laterale o isometrica — mai obliqua
- Niente figure umane (se non esplicitamente richieste)
- Niente testo o watermark
- Risoluzione consigliata griglia 3×3: 2048×2048; 4×4: 2560×2560

---

## 2. Pipeline di processing

### 2.1 Algoritmo
**Chrominance Offset** + **Forzatura Monocromatica** + **Auto-Trim**.

A differenza degli stili a colori, l'estrazione lineart è **binaria**:

```python
# 1. Riconoscimento sfondo via offset cromatico (Blu > Rosso)
is_cool_gray_bg = (b > r + 5) & (abs(g - 128) < 40)
is_dark_line   = (r + g + b) / 3 < 100

# 2. Trasparenza sullo sfondo
alpha[is_cool_gray_bg] = 0

# 3. Forza nero puro sulle linee
r[~is_cool_gray_bg & is_dark_line] = 0
g[~is_cool_gray_bg & is_dark_line] = 0
b[~is_cool_gray_bg & is_dark_line] = 0

# 4. Forza bianco puro sui riempimenti
r[~is_cool_gray_bg & ~is_dark_line] = 255
g[~is_cool_gray_bg & ~is_dark_line] = 255
b[~is_cool_gray_bg & ~is_dark_line] = 255
```

La componente blu dello sfondo è la firma che lo rende unico, salvaguardando
i pixel grigi-bianchi dell'oggetto da sbavature antialiasing.

### 2.2 Output
- Formato: **PNG con palette ottimizzata** (a 2 colori + trasparenza)
- Alpha: **hard clipping**, taglio netto vettoriale (no AA morbido)
- Auto-trim: ogni oggetto ritagliato ai pixel effettivi via `getbbox()`
- File salvati in: `engine/assets/objects_lineart/`

---

## 3. Uso del tool

```bash
python tools/process_assets.py --style lineart <grid.png> engine/assets/objects_lineart/ "la_nome1,la_nome2,la_nome3,la_nome4,la_nome5,la_nome6,la_nome7,la_nome8,la_nome9"
```

Note:
- Il flag `--style lineart` è obbligatorio.
- I nomi **devono** iniziare con prefisso `la_`.
- Il numero di nomi nella lista determina la dimensione della griglia
  (9 = 3×3, 16 = 4×4) tramite **rilevamento dinamico**.

---

## 4. Integrazione nel catalogo

Aggiungere ogni oggetto a [engine/data/global_lineart_catalog.json](../engine/data/global_lineart_catalog.json):

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

**Campi obbligatori**:
- `id` — identificativo univoco snake_case, **prefisso `la_` obbligatorio**
- `label_key` — chiave traduzione (convenzione: `obj_<id>`)
- `icon` — path relativo a `engine/assets/`, in `objects_lineart/`
- `default_detection` — `"circle"` o `"rect"`
- `default_radius` (se circle) **oppure** `default_width` + `default_height` (se rect)
- `tags` — lista di tag dalla [tassonomia canonica](TAGS_TAXONOMY.md)
- `style` — sempre `"line art"` (con spazio) per questo catalogo

> **Attenzione al valore `style`**: per ragioni storiche è `"line art"` con
> uno spazio, NON `"lineart"`. Verificato in [engine/data/global_lineart_catalog.json](../engine/data/global_lineart_catalog.json).

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
"obj_la_corona": "Corona"
```

---

## 6. Tag

**Fonte canonica**: [docs/TAGS_TAXONOMY.md](TAGS_TAXONOMY.md) → [engine/data/tags_taxonomy.json](../engine/data/tags_taxonomy.json).

Regole tassative (vedi documento dedicato per dettagli):
- **Obbligo**: almeno un tag DIMENSIONE + MATERIALE + DOMINIO per oggetto
- **Vietato** creare nuovi tag senza modificare la tassonomia ufficiale
- **Vietato** usare tag generici (`strumento`, `contenitore`, `equipaggiamento`) — mappare sempre su tag fisici validi (es. `attrezzo`, `scatola`, `viaggio`)

L'aggiunta di tag orfani frammenta il database e impedisce la visualizzazione
corretta nei chip UI dell'editor.

---

## 7. Quality checklist (pre-merge)

- [ ] Tutte le icone esistono in `engine/assets/objects_lineart/`
- [ ] Tutti gli ID hanno prefisso `la_`
- [ ] Ogni oggetto ha `label_key` tradotta in IT/EN/FR/ES/DE
- [ ] Tutti i tag esistono in `engine/data/tags_taxonomy.json`
- [ ] Campo `style: "line art"` (con spazio!) presente su tutte le entry
- [ ] Solo nero puro `#000000` e bianco puro `#FFFFFF` nei pixel non-trasparenti
- [ ] Nessuna sfumatura di grigio residua
- [ ] Auto-trim applicato (nessuno spazio trasparente residuo)
- [ ] Audit catalogo passa: `python -X utf8 tools/audit_catalog.py`
