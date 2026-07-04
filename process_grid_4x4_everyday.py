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


def process_4x4_everyday_grid():
    img_path = r"C:\Users\indecenti\.gemini\antigravity\brain\b73debb8-7344-44ca-b1f5-8f706190a190\everyday_objects_4x4_1782728994756.png"
    
    ROWS = 4
    COLS = 4
    TOTAL_ITEMS = 16

    base_dir = Path(r"g:\HIE git")
    engine_assets_dir = base_dir / "engine" / "assets" / "objects_cartoon"
    engine_assets_dir.mkdir(parents=True, exist_ok=True)
    
    objects_def = [
        {"id": "ca_office_stapler_red", "en": "Red Stapler", "it": "Cucitrice Rossa", "fr": "Agrafeuse Rouge", "es": "Grapadora Roja", "de": "Roter Hefter"},
        {"id": "ca_kitchen_blender_glass", "en": "Glass Blender", "it": "Frullatore di Vetro", "fr": "Mixeur en Verre", "es": "Licuadora de Vidrio", "de": "Glasmixer"},
        {"id": "ca_chrome_toaster", "en": "Chrome Toaster", "it": "Tostapane Cromato", "fr": "Grille-pain Chromé", "es": "Tostadora Cromada", "de": "Chrom-Toaster"},
        {"id": "ca_vacuum_cleaner_upright", "en": "Upright Vacuum", "it": "Aspirapolvere Verticale", "fr": "Aspirateur Vertical", "es": "Aspiradora Vertical", "de": "Standstaubsauger"},
        {"id": "ca_microwave_oven_white", "en": "White Microwave", "it": "Microonde Bianco", "fr": "Micro-ondes Blanc", "es": "Microondas Blanco", "de": "Weiße Mikrowelle"},
        {"id": "ca_rubber_plunger_red", "en": "Red Plunger", "it": "Sturalavandini Rosso", "fr": "Ventouse Rouge", "es": "Desatascador Rojo", "de": "Roter Pümpel"},
        {"id": "ca_suburban_mailbox_blue", "en": "Blue Mailbox", "it": "Cassetta Postale Blu", "fr": "Boîte aux Lettres Bleue", "es": "Buzón Azul", "de": "Blauer Briefkasten"},
        {"id": "ca_steel_thermos_flask", "en": "Steel Thermos", "it": "Thermos in Acciaio", "fr": "Thermos en Acier", "es": "Termo de Acero", "de": "Stahlthermoskanne"},
        {"id": "ca_electric_toothbrush_blue", "en": "Electric Toothbrush", "it": "Spazzolino Elettrico", "fr": "Brosse à Dents Électrique", "es": "Cepillo de Dientes Eléctrico", "de": "Elektrische Zahnbürste"},
        {"id": "ca_shaving_razor_silver", "en": "Silver Razor", "it": "Rasoio d'Argento", "fr": "Rasoir en Argent", "es": "Navaja de Plata", "de": "Silberner Rasierer"},
        {"id": "ca_wooden_hairbrush", "en": "Wooden Hairbrush", "it": "Spazzola di Legno", "fr": "Brosse en Bois", "es": "Cepillo de Madera", "de": "Holzhaarbürste"},
        {"id": "ca_garden_gnome_statue", "en": "Garden Gnome", "it": "Gnomo da Giardino", "fr": "Nain de Jardin", "es": "Gnomo de Jardín", "de": "Gartenzwerg"},
        {"id": "ca_metal_watering_can", "en": "Metal Watering Can", "it": "Annaffiatoio di Metallo", "fr": "Arrosoir en Métal", "es": "Regadera de Metal", "de": "Metallgießkanne"},
        {"id": "ca_fire_extinguisher_red", "en": "Red Fire Extinguisher", "it": "Estintore Rosso", "fr": "Extincteur Rouge", "es": "Extintor Rojo", "de": "Roter Feuerlöscher"},
        {"id": "ca_nail_clipper_steel", "en": "Steel Nail Clipper", "it": "Tagliaunghie in Acciaio", "fr": "Coupe-ongles en Acier", "es": "Cortaúñas de Acero", "de": "Stahlnagelknipser"},
        {"id": "ca_traffic_cone_orange", "en": "Orange Traffic Cone", "it": "Cono Stradale Arancione", "fr": "Cône de Signalisation", "es": "Cono de Tráfico Naranja", "de": "Orangefarbener Leitkegel"}
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
                # Niente tag
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
    
    print(f"Elaborazione completata. {TOTAL_ITEMS} oggetti di uso comune aggiunti al catalogo e 5 lingue aggiornate!")

if __name__ == "__main__":
    process_4x4_everyday_grid()
