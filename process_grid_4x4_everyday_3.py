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

def atomic_write(data, filepath):
    backup_path = filepath + ".bak"
    with open(filepath, "r", encoding="utf-8") as f:
        with open(backup_path, "w", encoding="utf-8") as b:
            b.write(f.read())
            
    tmp_path = filepath + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp_path, filepath)


def process_4x4_everyday_grid_3():
    img_path = r"C:\Users\indecenti\.gemini\antigravity\brain\b73debb8-7344-44ca-b1f5-8f706190a190\everyday_objects_4x4_batch3_1782732158990.png"
    
    ROWS = 4
    COLS = 4
    TOTAL_ITEMS = 16

    base_dir = Path(r"g:\HIE git")
    engine_assets_dir = base_dir / "engine" / "assets" / "objects_cartoon"
    engine_assets_dir.mkdir(parents=True, exist_ok=True)
    
    objects_def = [
        {"id": "ca_toilet_brush_white", "en": "Toilet Brush", "it": "Scopino WC", "fr": "Brosse de Toilette", "es": "Escobilla de Baño", "de": "Klobürste"},
        {"id": "ca_shampoo_bottle_green", "en": "Shampoo Bottle", "it": "Bottiglia di Shampoo", "fr": "Bouteille de Shampoing", "es": "Botella de Champú", "de": "Shampooflasche"},
        {"id": "ca_hand_soap_dispenser", "en": "Hand Soap", "it": "Dispenser Sapone", "fr": "Savon pour les Mains", "es": "Jabón de Manos", "de": "Handseife"},
        {"id": "ca_bath_towel_folded", "en": "Bath Towel", "it": "Asciugamano", "fr": "Serviette de Bain", "es": "Toalla de Baño", "de": "Badetuch"},
        {"id": "ca_kitchen_spatula_silicone", "en": "Kitchen Spatula", "it": "Spatola da Cucina", "fr": "Spatule de Cuisine", "es": "Espátula de Cocina", "de": "Küchenspatel"},
        {"id": "ca_rolling_pin_wood", "en": "Rolling Pin", "it": "Mattarello", "fr": "Rouleau à Pâtisserie", "es": "Rodillo", "de": "Nudelholz"},
        {"id": "ca_cutting_board_wood", "en": "Cutting Board", "it": "Tagliere", "fr": "Planche à Découper", "es": "Tabla de Cortar", "de": "Schneidebrett"},
        {"id": "ca_oven_mitt_red", "en": "Oven Mitt", "it": "Guanto da Forno", "fr": "Gant de Cuisine", "es": "Guante de Horno", "de": "Ofenhandschuh"},
        {"id": "ca_measuring_cup_glass", "en": "Measuring Cup", "it": "Misurino", "fr": "Verre Doseur", "es": "Taza Medidora", "de": "Messbecher"},
        {"id": "ca_dustpan_and_brush", "en": "Dustpan", "it": "Paletta e Scopino", "fr": "Pelle à Poussière", "es": "Recogedor", "de": "Kehrblech"},
        {"id": "ca_feather_duster", "en": "Feather Duster", "it": "Piumino", "fr": "Plumeau", "es": "Plumero", "de": "Staubwedel"},
        {"id": "ca_coat_hanger_wood", "en": "Coat Hanger", "it": "Gruccia", "fr": "Cintre", "es": "Percha", "de": "Kleiderbügel"},
        {"id": "ca_umbrella_closed_black", "en": "Umbrella", "it": "Ombrello", "fr": "Parapluie", "es": "Paraguas", "de": "Regenschirm"},
        {"id": "ca_shoe_horn_metal", "en": "Shoe Horn", "it": "Calzascarpe", "fr": "Chausse-pied", "es": "Calzador", "de": "Schuhanzieher"},
        {"id": "ca_tv_remote_control", "en": "TV Remote", "it": "Telecomando", "fr": "Télécommande TV", "es": "Mando de TV", "de": "TV-Fernbedienung"},
        {"id": "ca_wall_calendar_paper", "en": "Wall Calendar", "it": "Calendario da Muro", "fr": "Calendrier Mural", "es": "Calendario de Pared", "de": "Wandkalender"}
    ]

    img = Image.open(img_path)
    w, h = img.size
    cell_w = w // COLS
    cell_h = h // ROWS
    
    temp_dir = base_dir / "scratch"
    temp_dir.mkdir(exist_ok=True)
    
    catalog_entries = []
    translations = {"en": {}, "it": {}, "fr": {}, "es": {}, "de": {}}
    
    idx = 0
    for r in range(ROWS):
        for c in range(COLS):
            if idx >= TOTAL_ITEMS: break
            left = c * cell_w
            top = r * cell_h
            right = left + cell_w
            bottom = top + cell_h
            
            cell_img = img.crop((left, top, right, bottom))
            
            obj_info = objects_def[idx]
            obj_id = obj_info["id"]
            label_key = f"obj_{obj_id}"
            
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
                "style": "cartoon"
            })
            
            for lang in ["en", "it", "fr", "es", "de"]:
                translations[lang][label_key] = obj_info[lang]
            
            idx += 1

    catalog_path = str(base_dir / "engine" / "data" / "global_cartoon_catalog.json")
    with open(catalog_path, "r", encoding="utf-8") as f:
        catalog = json.load(f)
        
    catalog["objects"].extend(catalog_entries)
    atomic_write(catalog, catalog_path)
        
    for lang in ["en", "it", "fr", "es", "de"]:
        lang_path = str(base_dir / "engine" / "assets" / "strings" / f"{lang}.json")
        with open(lang_path, "r", encoding="utf-8") as f:
            lang_data = json.load(f)
        lang_data.update(translations[lang])
        atomic_write(lang_data, lang_path)
    
    print(f"Elaborazione completata. {TOTAL_ITEMS} nuovi oggetti aggiunti al catalogo e 5 lingue aggiornate (Batch 3)!")

if __name__ == "__main__":
    process_4x4_everyday_grid_3()
