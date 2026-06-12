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
    img_path = r"C:\Users\indecenti\.gemini\antigravity\brain\54e1b99a-4397-4fea-b7bb-124218366c1c\weird_cartoon_objects_grid_4_1781215664298.png"
    engine_assets_dir = Path(r"g:\HIE git\engine\assets\objects_cartoon")
    
    objects = [
        ("ca_xylophone_rainbow", "obj_ca_xylophone_rainbow", ["musica", "strumento", "legno"]),
        ("ca_abacus_wooden", "obj_ca_abacus_wooden", ["studio", "legno", "antico"]),
        ("ca_vuvuzela_horn_plastic", "obj_ca_vuvuzela_horn_plastic", ["musica", "strumento", "plastica"]),
        ("ca_didgeridoo_australian", "obj_ca_didgeridoo_australian", ["musica", "strumento", "legno"]),
        ("ca_bonsai_tree_potted", "obj_ca_bonsai_tree_potted", ["pianta", "natura", "arte"]),
        ("ca_treadmill_machine", "obj_ca_treadmill_machine", ["sport", "elettronico", "salute"]),
        ("ca_periscope_submarine", "obj_ca_periscope_submarine", ["ottica", "esplorazione", "metallo"]),
        ("ca_gong_golden", "obj_ca_gong_golden", ["musica", "strumento", "ottone"]),
        ("ca_snowboard_freestyle", "obj_ca_snowboard_freestyle", ["sport", "inverno", "plastica"]),
        ("ca_billiards_triangle", "obj_ca_billiards_triangle", ["gioco", "legno", "sport"]),
        ("ca_pinball_machine_retro", "obj_ca_pinball_machine_retro", ["gioco", "retro", "elettronico"]),
        ("ca_theremin_instrument", "obj_ca_theremin_instrument", ["musica", "strumento", "elettronico"]),
        ("ca_weather_vane_rooster", "obj_ca_weather_vane_rooster", ["esterno", "misura", "metallo"]),
        ("ca_bellows_fireplace", "obj_ca_bellows_fireplace", ["attrezzo", "fuoco", "cuoio"]),
        ("ca_kendama_toy", "obj_ca_kendama_toy", ["giocattolo", "gioco", "legno"]),
        ("ca_jukebox_neon", "obj_ca_jukebox_neon", ["musica", "retro", "luce"])
    ]
    
    translations = {
        "ca_xylophone_rainbow": {"en": "Rainbow Xylophone", "it": "Xilofono Arcobaleno"},
        "ca_abacus_wooden": {"en": "Wooden Abacus", "it": "Pallottoliere di Legno"},
        "ca_vuvuzela_horn_plastic": {"en": "Plastic Vuvuzela", "it": "Vuvuzela di Plastica"},
        "ca_didgeridoo_australian": {"en": "Australian Didgeridoo", "it": "Didgeridoo Australiano"},
        "ca_bonsai_tree_potted": {"en": "Potted Bonsai", "it": "Bonsai in Vaso"},
        "ca_treadmill_machine": {"en": "Treadmill", "it": "Tapis Roulant"},
        "ca_periscope_submarine": {"en": "Submarine Periscope", "it": "Periscopio da Sottomarino"},
        "ca_gong_golden": {"en": "Golden Gong", "it": "Gong Dorato"},
        "ca_snowboard_freestyle": {"en": "Freestyle Snowboard", "it": "Snowboard"},
        "ca_billiards_triangle": {"en": "Billiards Triangle", "it": "Triangolo da Biliardo"},
        "ca_pinball_machine_retro": {"en": "Retro Pinball Machine", "it": "Flipper Retro"},
        "ca_theremin_instrument": {"en": "Theremin", "it": "Theremin Elettronico"},
        "ca_weather_vane_rooster": {"en": "Rooster Weather Vane", "it": "Banderuola a Gallo"},
        "ca_bellows_fireplace": {"en": "Fireplace Bellows", "it": "Mantice da Camino"},
        "ca_kendama_toy": {"en": "Kendama Toy", "it": "Giocattolo Kendama"},
        "ca_jukebox_neon": {"en": "Neon Jukebox", "it": "Jukebox al Neon"}
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
