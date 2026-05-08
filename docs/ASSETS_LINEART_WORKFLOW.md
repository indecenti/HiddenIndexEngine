Questa documentazione descrive il processo professionale utilizzato per generare, pulire e integrare oggetti in stile **Line Art (Bianco e Nero)** all'interno dell'engine.

## 1. Generazione Immagine (AI)
Il primo passo consiste nel generare una "Master Sheet" contenente 9 oggetti disposti in una griglia 3x3.
Per facilitare l'estrazione mantenendo l'interno degli oggetti bianco puro, è fondamentale richiedere uno **sfondo grigio medio (#808080)**. **IMPORTANTE: Non devono essere presenti griglie grafiche, linee di divisione, cornici o separatori; lo sfondo deve essere un colore solido uniforme.**

### Strategia di Prompting (Line Art)
Per garantire asset pronti all'uso e stilisticamente coerenti, il prompt deve includere:
- **Stile Grafico Rigoroso**: Line art vettoriale o a inchiostro, nero puro (#000000) per i contorni e bianco puro (#FFFFFF) per i riempimenti interni. **Assolutamente nessuna sfumatura di grigio, gradienti, ombreggiature, o tratteggi (no cross-hatching)**.
- **Tratto Uniforme**: Le linee devono avere uno spessore costante e definito. Non ci deve essere "sketching" disordinato. Tutte le forme devono essere chiuse (per non far penetrare lo sfondo grigio nell'oggetto).
- **Sfondo Grigio Medio**: "Medium gray background (#808080)" per garantire che l'AI differenzi nettamente il bianco interno e le linee nere dall'ambiente circostante.
- **Margini di Sicurezza**: Almeno 120-150px di spazio grigio tra gli oggetti e i bordi della griglia per evitare tagli.
- **Orientamento Rigoroso**: Visuale frontale, laterale o isometrica, evitando prospettive deformate o posizioni oblique complesse.
- **Semplicità Descrittiva**: Essendo line art, limitare le indicazioni sui materiali (il vetro sarà semplicemente uno spazio delineato di bianco, niente distorsioni ottiche o trasparenze AI, poiché gestiremo la trasparenza tramite engine se necessario).

## 2. Elaborazione Digitale (Python)
L'immagine generata viene processata tramite script Python (`process_batch_objects.py` o simili) utilizzando **Pillow** e **Numpy**. A differenza del materiale realistico, l'estrazione del line art è estrema e binaria.

### Estrazione e Binarizzazione (Thresholding)
L'algoritmo deve compiere due azioni distinte:
1. **Riconoscimento dello Sfondo**: Identifica i pixel grigi (quelli con valori R, G e B intermedi e molto simili tra loro).
2. **Forzatura Monocromatica**: Tutto ciò che NON è sfondo grigio deve essere spinto forzatamente a bianco o nero puro, azzerando le eventuali sbavature antialiasing grigiastre dell'AI attorno alle linee.
```python
# Pseudo-logica di binarizzazione Line Art su Sfondo Grigio
# Identifica il grigio medio (#808080)
is_gray_bg = (abs(r - 128) < 40) & (abs(g - 128) < 40) & (abs(b - 128) < 40)
is_dark_line = (r + g + b) / 3 < 100

# Applica trasparenza allo sfondo grigio
alpha[is_gray_bg] = 0

# Forza il nero puro sulle linee
r[~is_gray_bg & is_dark_line] = 0
g[~is_gray_bg & is_dark_line] = 0
b[~is_gray_bg & is_dark_line] = 0

# Forza il bianco puro sui riempimenti interni
r[~is_gray_bg & ~is_dark_line] = 255
g[~is_gray_bg & ~is_dark_line] = 255
b[~is_gray_bg & ~is_dark_line] = 255
```
*In questo modo, lo sfondo neutro scompare in trasparenza e l'oggetto diventa puro inchiostro nero su riempimento bianco.*

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
- **Hard Alpha**: La trasparenza non usa interpolazione morbida (per evitare bordi sfumati fantasma), ma un taglio netto vettoriale.
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
