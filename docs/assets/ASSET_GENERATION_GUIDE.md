# Guida Generazione Asset: Background Horror

Questo documento descrive il metodo e i prompt necessari per generare background coerenti con lo stile visuale di **Malonno Survivors**.

## 1. Il "Dizionario Visivo" del Gioco
Per mantenere la coerenza tra le scene (es. `Welcome` -> `Brescia_Edolo`), ogni prompt deve contenere questi pilastri:

- **Style (Estetica):** "Hyper-detailed gritty horror illustration", "Over-emphasized decayed textures", "Avoid clean photography".
- **Lighting (Illuminazione):** "Cinematic high-contrast lighting", "Deeply crushed black shadows", "Dramatic spotlighting".
- **Color Palette:** "Desaturated teal and indigo atmosphere", "Harsh warm yellow sources".
- **Textures:** "Hyper-textured surfaces", "Heavy rust", "Deep cracks", "Peeling paint", "Grime and moss".

## 2. Esempio di Prompt Replicabile (Iper-Gritty)
Ecco il prompt definitivo per ottenere lo stile corretto:

```text
Hyper-detailed gritty horror illustration of [SOGGETTO]. 
Nighttime with extreme high-contrast lighting and deeply crushed black shadows. 
The style is dark and atmospheric, matching an iper-detailed survival horror aesthetic. 
[DETTAGLI SOGGETTO: es. rusted signs, flickering traffic light]. 
Jagged, dark silhouettes in the background shrouded in thick, volumetric fog. 
The overall look is hyper-textured, moody, and stylized horror, avoiding clean photography. 
Desaturated teal and warm yellow color palette. 16:9 ratio.
```

## 3. Workflow di Integrazione
1. **Generazione:** Usare il prompt di base modificando solo il *Soggetto* (es. cambiare "crossroad" con "interior of a bar" o "dark forest road").
2. **Crop/Aspect Ratio:** Assicurarsi che l'immagine sia in **16:9** (1920x1080).
3. **Targeting:** Salvare il file come `background.png` nella cartella specifica della scena:
   `games/[GIOCO]/levels/[LIVELLO]/[SCENA]/background.png`

## 4. Note Tecniche
- **No People:** Evitare sempre l'inserimento di figure umane per enfatizzare il senso di isolamento.
- **Reference Locale:** Inserire sempre riferimenti geografici (es. "Italian mountain", "Alpine") per mantenere l'identità del gioco.
