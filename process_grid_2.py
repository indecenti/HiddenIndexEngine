import json
import os
import cv2
import numpy as np
from pathlib import Path
from PIL import Image

def remove_background_cv2(image_path, out_path):
    img = cv2.imread(image_path, cv2.IMREAD_COLOR)
    if img is None: return
    
    h, w = img.shape[:2]
    mask = np.zeros((h + 2, w + 2), np.uint8)
    diff = (15, 15, 15)
    
    img_ff = img.copy()
    cv2.floodFill(img_ff, mask, (0,0), (0, 255, 0), diff, diff, cv2.FLOODFILL_FIXED_RANGE)
    cv2.floodFill(img_ff, mask, (w-1,0), (0, 255, 0), diff, diff, cv2.FLOODFILL_FIXED_RANGE)
    cv2.floodFill(img_ff, mask, (0,h-1), (0, 255, 0), diff, diff, cv2.FLOODFILL_FIXED_RANGE)
    cv2.floodFill(img_ff, mask, (w-1,h-1), (0, 255, 0), diff, diff, cv2.FLOODFILL_FIXED_RANGE)
    
    rgba = cv2.cvtColor(img, cv2.COLOR_BGR2BGRA)
    bg_mask = mask[1:-1, 1:-1]
    rgba[bg_mask == 1, 3] = 0
    
    lower_white = np.array([245, 245, 245, 255])
    upper_white = np.array([255, 255, 255, 255])
    mask_white = cv2.inRange(rgba, lower_white, upper_white)
    rgba[mask_white > 0, 3] = 0
    
    cv2.imwrite(out_path, rgba)

def main():
    img_path = r"C:\Users\indecenti\.gemini\antigravity\brain\54e1b99a-4397-4fea-b7bb-124218366c1c\weird_cartoon_objects_grid_1781214577314.png"
    engine_assets_dir = Path(r"g:\HIE git\engine\assets\objects_cartoon")
    
    objects = [
        ("ca_plunger_red", "obj_ca_plunger_red", ["attrezzo", "igiene", "gomma"]),
        ("ca_rubber_chicken_toy", "obj_ca_rubber_chicken_toy", ["giocattolo", "gomma", "gioco"]),
        ("ca_garden_gnome_classic", "obj_ca_garden_gnome_classic", ["giardino", "decorazione", "esterno"]),
        ("ca_pinata_donkey", "obj_ca_pinata_donkey", ["carta", "gioco", "cultura"]),
        ("ca_hula_hoop_stripes", "obj_ca_hula_hoop_stripes", ["plastica", "gioco", "sport"]),
        ("ca_whoopee_cushion_pink", "obj_ca_whoopee_cushion_pink", ["gomma", "giocattolo", "rosa"]),
        ("ca_cactus_potted_prickly", "obj_ca_cactus_potted_prickly", ["pianta", "natura", "verde"]),
        ("ca_chainsaw_lumberjack", "obj_ca_chainsaw_lumberjack", ["attrezzo", "metallo", "pericolo"]),
        ("ca_horseshoe_lucky", "obj_ca_horseshoe_lucky", ["metallo", "ferro", "simbolo"]),
        ("ca_mousetrap_cheese", "obj_ca_mousetrap_cheese", ["legno", "metallo", "pericolo"]),
        ("ca_sombrero_colorful", "obj_ca_sombrero_colorful", ["cappello", "vestiario", "cultura"]),
        ("ca_origami_crane_paper", "obj_ca_origami_crane_paper", ["carta", "arte", "cultura"]),
        ("ca_matryoshka_doll_red", "obj_ca_matryoshka_doll_red", ["legno", "giocattolo", "collezione"]),
        ("ca_flyswatter_green", "obj_ca_flyswatter_green", ["plastica", "attrezzo", "insetto"]),
        ("ca_dentures_chattering", "obj_ca_dentures_chattering", ["giocattolo", "plastica", "meccanismo"]),
        ("ca_fez_hat_tassel", "obj_ca_fez_hat_tassel", ["cappello", "vestiario", "rosso"])
    ]
    
    translations = {
        "ca_plunger_red": {"en": "Red Plunger", "it": "Sturalavandini Rosso"},
        "ca_rubber_chicken_toy": {"en": "Rubber Chicken", "it": "Pollo di Gomma"},
        "ca_garden_gnome_classic": {"en": "Garden Gnome", "it": "Nano da Giardino"},
        "ca_pinata_donkey": {"en": "Donkey Piñata", "it": "Pignatta a Forma di Asino"},
        "ca_hula_hoop_stripes": {"en": "Striped Hula Hoop", "it": "Hula Hoop a Strisce"},
        "ca_whoopee_cushion_pink": {"en": "Whoopee Cushion", "it": "Cuscino Scorreggione"},
        "ca_cactus_potted_prickly": {"en": "Potted Cactus", "it": "Cactus in Vaso"},
        "ca_chainsaw_lumberjack": {"en": "Yellow Chainsaw", "it": "Motosega Gialla"},
        "ca_horseshoe_lucky": {"en": "Lucky Horseshoe", "it": "Ferro di Cavallo"},
        "ca_mousetrap_cheese": {"en": "Mousetrap", "it": "Trappola per Topi"},
        "ca_sombrero_colorful": {"en": "Colorful Sombrero", "it": "Sombrero Colorato"},
        "ca_origami_crane_paper": {"en": "Origami Crane", "it": "Gru Origami"},
        "ca_matryoshka_doll_red": {"en": "Matryoshka Doll", "it": "Matrioska Rossa"},
        "ca_flyswatter_green": {"en": "Green Flyswatter", "it": "Scacciamosche Verde"},
        "ca_dentures_chattering": {"en": "Chattering Dentures", "it": "Dentiera a Molla"},
        "ca_fez_hat_tassel": {"en": "Red Fez Hat", "it": "Cappello Fez"}
    }
    
    img = Image.open(img_path)
    w, h = img.size
    cell_w = w // 4
    cell_h = h // 4
    
    temp_dir = Path("scratch")
    temp_dir.mkdir(exist_ok=True)
    
    catalog_entries = []
    
    idx = 0
    for r in range(4):
        for c in range(4):
            if idx >= 16: break
            left = c * cell_w
            top = r * cell_h
            right = left + cell_w
            bottom = top + cell_h
            
            cell_img = img.crop((left, top, right, bottom))
            obj_id, label_key, tags = objects[idx]
            
            temp_path = str(temp_dir / f"{obj_id}_temp.png")
            final_path = str(engine_assets_dir / f"{obj_id}.png")
            
            cell_img.save(temp_path)
            
            remove_background_cv2(temp_path, final_path)
            
            catalog_entries.append({
                "id": obj_id,
                "label_key": label_key,
                "icon": f"objects_cartoon/{obj_id}.png",
                "default_detection": "rect",
                "default_width": 50,
                "default_height": 50,
                "tags": tags,
                "style": "cartoon"
            })
            idx += 1

    catalog_path = r"g:\HIE git\engine\data\global_cartoon_catalog.json"
    with open(catalog_path, "r", encoding="utf-8") as f:
        catalog = json.load(f)
        
    # Check if they are already in the catalog
    existing_ids = set(o["id"] for o in catalog["objects"])
    added = 0
    for entry in catalog_entries:
        if entry["id"] not in existing_ids:
            catalog["objects"].append(entry)
            added += 1
    
    with open(catalog_path, "w", encoding="utf-8") as f:
        json.dump(catalog, f, indent=2, ensure_ascii=False)
        
    en_path = r"g:\HIE git\engine\assets\strings\en.json"
    it_path = r"g:\HIE git\engine\assets\strings\it.json"
    
    with open(en_path, "r", encoding="utf-8") as f: en_data = json.load(f)
    with open(it_path, "r", encoding="utf-8") as f: it_data = json.load(f)
    
    for obj_id, label_key, _ in objects:
        en_data[label_key] = translations[obj_id]["en"]
        it_data[label_key] = translations[obj_id]["it"]
        
    with open(en_path, "w", encoding="utf-8") as f: json.dump(en_data, f, indent=2, ensure_ascii=False)
    with open(it_path, "w", encoding="utf-8") as f: json.dump(it_data, f, indent=2, ensure_ascii=False)
    
    print(f"Elaborazione completata. {added} nuovi oggetti strani aggiunti al catalogo e stringhe aggiornate!")

if __name__ == "__main__":
    main()
