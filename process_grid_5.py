import json
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
    diff = (10, 10, 10) 
    
    img_ff = img.copy()
    
    for x in range(w):
        cv2.floodFill(img_ff, mask, (x, 0), (0, 255, 0), diff, diff, cv2.FLOODFILL_FIXED_RANGE)
        cv2.floodFill(img_ff, mask, (x, h-1), (0, 255, 0), diff, diff, cv2.FLOODFILL_FIXED_RANGE)
    for y in range(h):
        cv2.floodFill(img_ff, mask, (0, y), (0, 255, 0), diff, diff, cv2.FLOODFILL_FIXED_RANGE)
        cv2.floodFill(img_ff, mask, (w-1, y), (0, 255, 0), diff, diff, cv2.FLOODFILL_FIXED_RANGE)
        
    rgba = cv2.cvtColor(img, cv2.COLOR_BGR2BGRA)
    bg_mask = mask[1:-1, 1:-1]
    
    rgba[bg_mask == 1, 3] = 0
    
    cv2.imwrite(out_path, rgba)

def main():
    img_path = r"C:\Users\indecenti\.gemini\antigravity\brain\54e1b99a-4397-4fea-b7bb-124218366c1c\weird_cartoon_objects_grid_5_1781215765715.png"
    engine_assets_dir = Path(r"g:\HIE git\engine\assets\objects_cartoon")
    
    objects = [
        ("ca_tuba_brass", "obj_ca_tuba_brass", ["musica", "strumento", "ottone"]),
        ("ca_ukulele_wooden", "obj_ca_ukulele_wooden", ["musica", "strumento", "legno"]),
        ("ca_castanets_wooden", "obj_ca_castanets_wooden", ["musica", "strumento", "legno"]),
        ("ca_stilts_wooden", "obj_ca_stilts_wooden", ["gioco", "sport", "legno"]),
        ("ca_cleaver_butcher", "obj_ca_cleaver_butcher", ["attrezzo", "metallo", "pericolo"]),
        ("ca_mortar_and_pestle_stone", "obj_ca_mortar_and_pestle_stone", ["cucina", "pietra", "alchimia"]),
        ("ca_whisk_metal", "obj_ca_whisk_metal", ["cucina", "attrezzo", "metallo"]),
        ("ca_pommel_horse_gymnastics", "obj_ca_pommel_horse_gymnastics", ["sport", "legno", "pelle"]),
        ("ca_trampoline_round", "obj_ca_trampoline_round", ["sport", "gioco", "metallo"]),
        ("ca_monocle_golden", "obj_ca_monocle_golden", ["ottica", "accessorio", "ottone"]),
        ("ca_ocarina_blue", "obj_ca_ocarina_blue", ["musica", "strumento", "ceramica"]),
        ("ca_obelisk_stone", "obj_ca_obelisk_stone", ["pietra", "arte", "antico"]),
        ("ca_sarcophagus_golden", "obj_ca_sarcophagus_golden", ["antico", "macabro", "metallo"]),
        ("ca_nunchaku_wooden", "obj_ca_nunchaku_wooden", ["arma", "pericolo", "legno"]),
        ("ca_hoverboard_electric", "obj_ca_hoverboard_electric", ["veicolo", "elettronico", "tech"]),
        ("ca_plasma_globe_electric", "obj_ca_plasma_globe_electric", ["scienza", "luce", "vetro"])
    ]
    
    translations = {
        "ca_tuba_brass": {"en": "Brass Tuba", "it": "Tuba"},
        "ca_ukulele_wooden": {"en": "Wooden Ukulele", "it": "Ukulele"},
        "ca_castanets_wooden": {"en": "Wooden Castanets", "it": "Nacchere"},
        "ca_stilts_wooden": {"en": "Wooden Stilts", "it": "Trampoli"},
        "ca_cleaver_butcher": {"en": "Butcher Cleaver", "it": "Mannaia"},
        "ca_mortar_and_pestle_stone": {"en": "Stone Mortar", "it": "Mortaio"},
        "ca_whisk_metal": {"en": "Metal Whisk", "it": "Frusta da Cucina"},
        "ca_pommel_horse_gymnastics": {"en": "Pommel Horse", "it": "Cavallo con Maniglie"},
        "ca_trampoline_round": {"en": "Round Trampoline", "it": "Trampolino"},
        "ca_monocle_golden": {"en": "Golden Monocle", "it": "Monocolo"},
        "ca_ocarina_blue": {"en": "Ceramic Ocarina", "it": "Ocarina"},
        "ca_obelisk_stone": {"en": "Stone Obelisk", "it": "Obelisco"},
        "ca_sarcophagus_golden": {"en": "Golden Sarcophagus", "it": "Sarcofago"},
        "ca_nunchaku_wooden": {"en": "Wooden Nunchaku", "it": "Nunchaku"},
        "ca_hoverboard_electric": {"en": "Hoverboard", "it": "Hoverboard"},
        "ca_plasma_globe_electric": {"en": "Plasma Globe", "it": "Sfera al Plasma"}
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
            
            remove_background_cv2_safe(temp_path, final_path)
            
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
    
    print(f"Elaborazione completata. {added} nuovi oggetti EXTRA aggiunti al catalogo e stringhe aggiornate!")

if __name__ == "__main__":
    main()
