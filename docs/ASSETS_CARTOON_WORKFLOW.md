# 🎨 Workflow Creazione Assets Adventure Cartoon

Questa documentazione descrive il processo per generare, processare e integrare oggetti in stile **Cartoon (Cell Shaded)** all'interno dell'engine, garantendo la coerenza visiva con la serie "Adventure Family".

## 1. Generazione Immagine (AI)
Il processo utilizza una "Master Sheet" 3x3. A differenza del Line Art, qui i colori sono fondamentali, quindi lo sfondo deve essere neutro rispetto alla palette degli oggetti.

### Specifiche Tecniche
- **Sfondo**: **Pure Neon Green (#00FF00)**. Questo permette di utilizzare l'algoritmo di Chroma Key standard ottimizzato per lo stile cartoon.
- **Composizione**: Griglia 3x3 con almeno 150px di margine tra gli oggetti. Niente ombre proiettate (drop shadows) sullo sfondo verde.

### Strategia di Prompting (Adventure Cartoon)
Per mantenere lo stile delle immagini di riferimento, il prompt deve includere:
- **Stile Visivo**: "Adventure book illustration style, clean black outlines, cell shaded, vibrant but natural colors, flat shading with sharp shadows".
- **Dettaglio**: "Moderate detail, no gradients, no textures, bold lines".
- **Soggetti**: "Individual objects, isolated, front view or 3/4 isometric view".
- **Keyword di riferimento**: "Ligne claire, comic book style, high readability".

## 2. Elaborazione Digitale (Python)
L'estrazione viene eseguita tramite `tools/process_assets.py` con il flag `--style cartoon`.

### Logica di Processing
L'algoritmo esegue le seguenti operazioni:
1. **Chroma Key**: Isola lo sfondo verde puro.
2. **Spill Suppression (Hard)**: Dato che lo stile cartoon ha colori piatti, la soppressione del verde deve essere netta per evitare "aloni" sui contorni neri.
3. **Alpha Clipping**: La trasparenza non è sfumata (AA morbido) ma decisa, per mantenere l'estetica "tagliata a mano" del cartoon.

## 3. Automazione con Tool
Esegui il comando passando il file della griglia e la cartella di destinazione:
```bash
python tools/process_assets.py --style cartoon assets_grid.png engine/assets/objects_cartoon/
```

## 4. Registrazione Catalogo
Dopo il processamento, gli oggetti devono essere registrati in `engine/data/global_cartoon_catalog.json`.

### Esempio Entry JSON
```json
{
  "id": "ca_backpack_adv",
  "label_key": "obj_ca_backpack_adv",
  "icon": "objects_cartoon/ca_backpack_adv.png",
  "default_detection": "rect",
  "default_width": 60,
  "default_height": 75,
  "tags": ["EQUIPAGGIAMENTO", "VIAGGIO"],
  "style": "cartoon"
}
```

- **Tassonomia**: Utilizzare rigorosamente i tag definiti in `tools/tag_taxonomy.json`. Non creare tag descrittivi dello stile (es. "disegnato"), poiché lo stile è già definito dalla proprietà `style`.

## 6. Regole Tassative di Qualità
- **Divieto Nuovi TAG**: È severamente proibito introdurre nuovi tag non presenti nella tassonomia ufficiale (`tools/tag_taxonomy.json`). Se un oggetto non ha un tag specifico, utilizzare il dominio più vicino (es. `tecnologia` per gadget futuristici).
- **Localizzazione Obbligatoria**: Ogni asset registrato nel catalogo cartoon DEVE essere accompagnato dalle traduzioni per il suo `label_key` in tutte le 5 lingue ufficiali del motore: Italiano (IT), Inglese (EN), Francese (FR), Spagnolo (ES) e Tedesco (DE).
- **Green Screen**: Gli asset devono essere consegnati su sfondo Pure Green (#00FF00) per garantire un'estrazione perfetta e uniforme tramite il tool di processing.
