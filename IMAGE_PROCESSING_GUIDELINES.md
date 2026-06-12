# 🖼️ Linee Guida per il Processamento Immagini (Background Removal)

## ❌ Il Problema: OpenCV FloodFill & Range Globale
In passato l'approccio prevedeva l'utilizzo di `cv2.inRange()` (che eliminava tutti i pixel bianchi, compresi gli occhi, i denti o i riflessi all'interno degli oggetti) oppure del `FloodFill` perimetrale (che salvaguardava gli interni, ma lasciava lo sfondo intatto dentro ai "buchi" chiusi, come l'interno di un hula hoop o di un nunchaku). Entrambi gli approcci classici basati sulle soglie si sono rivelati inadeguati per ottenere un **"lavoro pulito perfetto"**.

## ✅ La Soluzione Ufficiale Definitiva: Intelligenza Artificiale (Rembg)
Poiché il nostro ambiente dispone di `rembg` (modulo basato su rete neurale U2-Net), esso è diventato l'**unico standard accettato** per rimuovere lo sfondo dalle icone generate.

**Perché Rembg?**
- È un algoritmo di matting semantico: **riconosce il soggetto** rispetto allo sfondo.
- **Pulisce gli sfondi interni:** rimuove perfettamente il bianco dai "buchi" e dagli spazi vuoti chiusi degli oggetti.
- **Protegge i colori interni:** non cancellerà MAI i riflessi, i denti, o la sclera bianca degli occhi, poiché sa che fanno parte del soggetto.
- L'anti-aliasing sui bordi generato dalle maschere alpha è di qualità superiore rispetto a qualsiasi thresholding manuale.

### Esempio di Codice Python (Rembg) Sicuro
Per ogni griglia generata o singolo asset, utilizzare sempre la seguente logica:

```python
import rembg
from PIL import Image

def process_asset_with_ai(image_path, out_path):
    # Carica l'immagine originale (anche se ha bordi bianchi, sfondi complessi o buchi interni)
    img = Image.open(image_path)
    
    # Rimuovi lo sfondo magicamente con AI
    out = rembg.remove(img)
    
    # Salva il PNG pulito
    out.save(out_path)
```

### Regole d'Oro per Script Futuri:
1. **NON USARE PIÙ OPENCV PER LE TRASPARENZE:** Non tentare più di indovinare la tolleranza del floodfill. Scarta `cv2.floodFill` o `cv2.inRange` per il ritaglio.
2. **TAGLIO PRIMA, REMBG DOPO:** Se l'AI ha generato una griglia (es. 4x4), taglia prima le celle singole con `img.crop()`, dopodiché passa ogni singola cella a `rembg.remove()`. Passare l'intera griglia a Rembg confonderebbe la rete neurale su quale sia il "soggetto principale".
3. **VELOCITÀ:** Il primo avvio di `rembg` potrebbe impiegare qualche secondo in più per caricare i pesi del modello. Le elaborazioni successive saranno istantanee.
