# Asset Generation Guide: Horror Backgrounds

This document describes the method and the prompts needed to generate backgrounds consistent with the visual style of **Malonno Survivors**.

## 1. The game's "visual dictionary"
To keep the scenes consistent (e.g. `Welcome` -> `Brescia_Edolo`), every prompt must contain these pillars:

- **Style (aesthetics):** "Hyper-detailed gritty horror illustration", "Over-emphasized decayed textures", "Avoid clean photography".
- **Lighting:** "Cinematic high-contrast lighting", "Deeply crushed black shadows", "Dramatic spotlighting".
- **Color palette:** "Desaturated teal and indigo atmosphere", "Harsh warm yellow sources".
- **Textures:** "Hyper-textured surfaces", "Heavy rust", "Deep cracks", "Peeling paint", "Grime and moss".

## 2. Reproducible prompt example (hyper-gritty)
The definitive prompt to obtain the right style:

```text
Hyper-detailed gritty horror illustration of [SUBJECT].
Nighttime with extreme high-contrast lighting and deeply crushed black shadows.
The style is dark and atmospheric, matching a hyper-detailed survival horror aesthetic.
[SUBJECT DETAILS: e.g. rusted signs, flickering traffic light].
Jagged, dark silhouettes in the background shrouded in thick, volumetric fog.
The overall look is hyper-textured, moody, and stylized horror, avoiding clean photography.
Desaturated teal and warm yellow color palette. 16:9 ratio.
```

## 3. Integration workflow
1. **Generation:** use the base prompt changing only the *subject* (e.g. replace "crossroad" with "interior of a bar" or "dark forest road").
2. **Crop/aspect ratio:** make sure the image is **16:9** (1920x1080).
3. **Targeting:** save the file as `background.png` in the scene's folder:
   `games/[GAME]/levels/[LEVEL]/[SCENE]/background.png`

## 4. Technical notes
- **No people:** always avoid human figures to emphasize the sense of isolation.
- **Local references:** always include geographic references (e.g. "Italian mountain", "Alpine") to keep the game's identity.
