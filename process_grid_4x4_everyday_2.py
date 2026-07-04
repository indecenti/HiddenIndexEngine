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


def process_4x4_everyday_grid_2():
    img_path = r"C:\Users\indecenti\.gemini\antigravity\brain\b73debb8-7344-44ca-b1f5-8f706190a190\everyday_objects_4x4_batch2_1782732068895.png"
    
    ROWS = 4
    COLS = 4
    TOTAL_ITEMS = 16

    base_dir = Path(r"g:\HIE git")
    engine_assets_dir = base_dir / "engine" / "assets" / "objects_cartoon"
    engine_assets_dir.mkdir(parents=True, exist_ok=True)
    
    objects_def = [
        {"id": "ca_toilet_paper_roll", "en": "Toilet Paper", "it": "Carta Igienica", "fr": "Papier Toilette", "es": "Papel Higiénico", "de": "Toilettenpapier"},
        {"id": "ca_hair_dryer_yellow", "en": "Hair Dryer", "it": "Asciugacapelli", "fr": "Sèche-cheveux", "es": "Secador de Pelo", "de": "Haartrockner"},
        {"id": "ca_ironing_board_striped", "en": "Ironing Board", "it": "Asse da Stiro", "fr": "Planche à Repasser", "es": "Tabla de Planchar", "de": "Bügelbrett"},
        {"id": "ca_clothes_iron_blue", "en": "Clothes Iron", "it": "Ferro da Stiro", "fr": "Fer à Repasser", "es": "Plancha de Ropa", "de": "Bügeleisen"},
        {"id": "ca_laundry_basket_plastic", "en": "Laundry Basket", "it": "Cesto della Biancheria", "fr": "Panier à Linge", "es": "Cesto de Ropa", "de": "Wäschekorb"},
        {"id": "ca_desk_fan_white", "en": "Desk Fan", "it": "Ventilatore da Tavolo", "fr": "Ventilateur de Bureau", "es": "Ventilador de Mesa", "de": "Tischventilator"},
        {"id": "ca_coffee_maker_black", "en": "Coffee Maker", "it": "Macchina da Caffè", "fr": "Machine à Café", "es": "Cafetera", "de": "Kaffeemaschine"},
        {"id": "ca_table_lamp_green", "en": "Table Lamp", "it": "Lampada da Tavolo", "fr": "Lampe de Table", "es": "Lámpara de Mesa", "de": "Tischlampe"},
        {"id": "ca_wall_clock_analog", "en": "Wall Clock", "it": "Orologio da Parete", "fr": "Horloge Murale", "es": "Reloj de Pared", "de": "Wanduhr"},
        {"id": "ca_kitchen_sponge_yellow", "en": "Kitchen Sponge", "it": "Spugna da Cucina", "fr": "Éponge de Cuisine", "es": "Esponja de Cocina", "de": "Küchenschwamm"},
        {"id": "ca_dish_soap_bottle", "en": "Dish Soap", "it": "Detersivo Piatti", "fr": "Liquide Vaisselle", "es": "Jabón para Platos", "de": "Spülmittel"},
        {"id": "ca_paper_towel_dispenser", "en": "Paper Towel", "it": "Carta Assorbente", "fr": "Essuie-tout", "es": "Toallas de Papel", "de": "Papierhandtuch"},
        {"id": "ca_trash_can_silver", "en": "Trash Can", "it": "Pattumiera", "fr": "Poubelle", "es": "Basurero", "de": "Mülleimer"},
        {"id": "ca_tape_dispenser_office", "en": "Tape Dispenser", "it": "Dispenser Nastro Adesivo", "fr": "Dérouleur de Ruban", "es": "Dispensador de Cinta", "de": "Klebebandspender"},
        {"id": "ca_computer_mouse_wireless", "en": "Computer Mouse", "it": "Mouse", "fr": "Souris d'Ordinateur", "es": "Ratón de Computadora", "de": "Computermaus"},
        {"id": "ca_power_strip_plug", "en": "Power Strip", "it": "Ciabatta Elettrica", "fr": "Multiprise", "es": "Regleta", "de": "Mehrfachsteckdose"}
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
    
    print(f"Elaborazione completata. {TOTAL_ITEMS} nuovi oggetti aggiunti al catalogo e 5 lingue aggiornate!")

if __name__ == "__main__":
    process_4x4_everyday_grid_2()
