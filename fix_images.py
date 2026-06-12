import os
import cv2
import numpy as np
from pathlib import Path
from PIL import Image

def remove_background_cv2_safe(image_path, out_path):
    img = cv2.imread(image_path, cv2.IMREAD_COLOR)
    if img is None: return
    
    h, w = img.shape[:2]
    mask = np.zeros((h + 2, w + 2), np.uint8)
    # Tolleranza minima per non invadere bordi chiari
    diff = (10, 10, 10) 
    
    img_ff = img.copy()
    
    # FloodFill solo partendo dal perimetro per trovare ESCLUSIVAMENTE lo sfondo esterno.
    # Non eliminiamo MAI il bianco globale per non distruggere occhi, riflessi o oggetti bianchi.
    for x in range(w):
        cv2.floodFill(img_ff, mask, (x, 0), (0, 255, 0), diff, diff, cv2.FLOODFILL_FIXED_RANGE)
        cv2.floodFill(img_ff, mask, (x, h-1), (0, 255, 0), diff, diff, cv2.FLOODFILL_FIXED_RANGE)
    for y in range(h):
        cv2.floodFill(img_ff, mask, (0, y), (0, 255, 0), diff, diff, cv2.FLOODFILL_FIXED_RANGE)
        cv2.floodFill(img_ff, mask, (w-1, y), (0, 255, 0), diff, diff, cv2.FLOODFILL_FIXED_RANGE)
        
    rgba = cv2.cvtColor(img, cv2.COLOR_BGR2BGRA)
    bg_mask = mask[1:-1, 1:-1]
    
    # Impostiamo l'alfa a 0 SOLO per i pixel invasi dal floodfill (il background reale)
    rgba[bg_mask == 1, 3] = 0
    
    cv2.imwrite(out_path, rgba)

def main():
    img_path = r"C:\Users\indecenti\.gemini\antigravity\brain\54e1b99a-4397-4fea-b7bb-124218366c1c\weird_cartoon_objects_grid_1781214577314.png"
    engine_assets_dir = Path(r"g:\HIE git\engine\assets\objects_cartoon")
    
    objects = [
        "ca_plunger_red",
        "ca_rubber_chicken_toy",
        "ca_garden_gnome_classic",
        "ca_pinata_donkey",
        "ca_hula_hoop_stripes",
        "ca_whoopee_cushion_pink",
        "ca_cactus_potted_prickly",
        "ca_chainsaw_lumberjack",
        "ca_horseshoe_lucky",
        "ca_mousetrap_cheese",
        "ca_sombrero_colorful",
        "ca_origami_crane_paper",
        "ca_matryoshka_doll_red",
        "ca_flyswatter_green",
        "ca_dentures_chattering",
        "ca_fez_hat_tassel"
    ]
    
    img = Image.open(img_path)
    w, h = img.size
    cell_w = w // 4
    cell_h = h // 4
    
    temp_dir = Path("scratch")
    temp_dir.mkdir(exist_ok=True)
    
    idx = 0
    for r in range(4):
        for c in range(4):
            if idx >= 16: break
            left = c * cell_w
            top = r * cell_h
            right = left + cell_w
            bottom = top + cell_h
            
            cell_img = img.crop((left, top, right, bottom))
            obj_id = objects[idx]
            
            temp_path = str(temp_dir / f"{obj_id}_temp.png")
            final_path = str(engine_assets_dir / f"{obj_id}.png")
            
            cell_img.save(temp_path)
            
            # Applica la versione corretta (Safe)
            remove_background_cv2_safe(temp_path, final_path)
            idx += 1

    print("Immagini processate di nuovo con successo senza danneggiare i colori interni.")

if __name__ == "__main__":
    main()
