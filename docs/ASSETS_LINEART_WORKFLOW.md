Questa documentazione descrive il processo professionale utilizzato per generare, pulire e integrare oggetti in stile **Line Art (Bianco e Nero)** all'interno dell'engine.

## 1. Generazione Immagine (AI)
Il primo passo consiste nel generare una "Master Sheet" contenente 9 oggetti disposti in una griglia 3x3.
Per facilitare l'estrazione mantenendo l'interno degli oggetti bianco puro, è fondamentale richiedere uno **sfondo grigio azzurrato (#788088)**. Questo colore, pur apparendo neutro all'AI, permette allo script di distinguerlo matematicamente dai pixel grigi di transizione dell'oggetto. **IMPORTANTE: Non devono essere presenti griglie grafiche, linee di divisione, cornici o separatori; lo sfondo deve essere un colore solido uniforme.**

### Strategia di Prompting (Line Art)
Per garantire asset pronti all'uso e stilisticamente coerenti, il prompt deve includere:
- **Stile Grafico Rigoroso**: Line art vettoriale o a inchiostro, nero puro (#000000) per i contorni e bianco puro (#FFFFFF) per i riempimenti interni. **Assolutamente nessuna sfumatura di grigio, gradienti, ombreggiature, o tratteggi (no cross-hatching)**.
- **Tratto Uniforme**: Le linee devono avere uno spessore costante e definito. Non ci deve essere "sketching" disordinato. Tutte le forme devono essere chiuse (per non far penetrare lo sfondo grigio nell'oggetto).
- **Sfondo Grigio Azzurrato**: "Cool gray background (#788088)" per garantire che l'AI differenzi nettamente il bianco interno e le linee nere dall'ambiente circostante.
- **Margini di Sicurezza**: Almeno 120-150px di spazio grigio tra gli oggetti e i bordi della griglia per evitare tagli.
- **Orientamento Rigoroso**: Visuale frontale, laterale o isometrica, evitando prospettive deformate o posizioni oblique complesse.
- **Semplicità Descrittiva**: Essendo line art, limitare le indicazioni sui materiali (il vetro sarà semplicemente uno spazio delineato di bianco, niente distorsioni ottiche o trasparenze AI, poiché gestiremo la trasparenza tramite engine se necessario).

## 2. Elaborazione Digitale (Python)
L'immagine generata viene processata tramite script Python (`process_batch_objects.py` o simili) utilizzando **Pillow** e **Numpy**. A differenza del materiale realistico, l'estrazione del line art è estrema e binaria.

### Estrazione e Binarizzazione (Chrominance Offset)
L'algoritmo deve compiere due azioni distinte:
1. **Riconoscimento dello Sfondo**: Identifica i pixel dello sfondo sfruttando lo sbilanciamento del canale Blu rispetto al Rosso (caratteristica del #788088).
2. **Forzatura Monocromatica**: Tutto ciò che NON è sfondo deve essere spinto forzatamente a bianco o nero puro, azzerando le eventuali sbavature antialiasing grigiastre.
```python
# Pseudo-logica di binarizzazione Line Art su Grigio Azzurrato (#788088)
# Identifica lo sfondo tramite offset cromatico (Blu > Rosso)
is_cool_gray_bg = (b > r + 5) & (abs(g - 128) < 40)
is_dark_line = (r + g + b) / 3 < 100

# Applica trasparenza allo sfondo
alpha[is_cool_gray_bg] = 0

# Forza il nero puro sulle linee
r[~is_cool_gray_bg & is_dark_line] = 0
g[~is_cool_gray_bg & is_dark_line] = 0
b[~is_cool_gray_bg & is_dark_line] = 0

# Forza il bianco puro sui riempimenti interni
r[~is_cool_gray_bg & ~is_dark_line] = 255
g[~is_cool_gray_bg & ~is_dark_line] = 255
b[~is_cool_gray_bg & ~is_dark_line] = 255
```
*In questo modo, la leggera componente blu dello sfondo lo rende unico, salvaguardando i pixel grigio-bianchi dell'oggetto.*

### Auto-Trim
Ogni oggetto viene automaticamente ritagliato sui suoi pixel effettivi (`getbbox()`), eliminando lo spazio trasparente vuoto attorno per ottimizzare le bounding box nell'editor.

## 3. Automazione con Tool Corretto
Per processare questi fogli master, si utilizzerà un flag apposito (es. `--lineart`) sul tool permanente o uno script dedicato per questa modalità binaria.

### Come usare il Tool
Esegui il comando da terminale passando il file della griglia 3x3 e la cartella di destinazione:
```bash
python tools/process_assets.py --style lineart assets_grid.png engine/assets/objects_lineart/
```

### Caratteristiche del Tool (Modalità Line Art)
- **Chrominance Detection**: Isola lo sfondo #788088 rilevando la firma Blu > Rosso, evitando falsi positivi sui grigi di antialiasing.
- **Hard Alpha**: La trasparenza non usa interpolazione morbida, ma un taglio netto vettoriale.
- **Binarizzazione Interna**: Garantisce l'assenza di compression artifacts, salvando i file con palette a 2 colori + trasparenza.
- **Auto-Trim**: Taglio chirurgico dei bounding box.

## 4. Integrazione nell'Editor e nel Gioco
Gli asset finali vengono salvati come `.png` (idealmente PNG-8 con palette ottimizzata data la natura a 2 colori) nella cartella `engine/assets/objects_lineart/`.
Nel catalogo specifico dell'engine (`global_lineart_catalog.json`), questi oggetti dovranno avere la proprietà:
```json
"style": "line art",
"icon": "objects_lineart/nome_oggetto.png"
```
Ciò permette al livello o all'editor di filtrare gli asset corretti, garantendo che una scena "Line Art" non si mescoli involontariamente con oggetti in stile fotografico/realistico.
