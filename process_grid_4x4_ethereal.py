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
    # Backup
    backup_path = filepath + ".bak"
    with open(filepath, "r", encoding="utf-8") as f:
        with open(backup_path, "w", encoding="utf-8") as b:
            b.write(f.read())
            
    # Write to tmp and replace
    tmp_path = filepath + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp_path, filepath)


def process_4x4_grid():
    img_path = r"C:\Users\indecenti\.gemini\antigravity\brain\b73debb8-7344-44ca-b1f5-8f706190a190\ethereal_objects_4x4_1782728816686.png"
    
    ROWS = 4
    COLS = 4
    TOTAL_ITEMS = 16

    base_dir = Path(r"g:\HIE git")
    engine_assets_dir = base_dir / "engine" / "assets" / "objects_cartoon"
    engine_assets_dir.mkdir(parents=True, exist_ok=True)
    
    objects_def = [
        {"id": "ca_astral_projector_orb", "en": "Astral Orb", "it": "Sfera Astrale", "fr": "Orbe Astral", "es": "Orbe Astral", "de": "Astralkugel"},
        {"id": "ca_ethereal_dreamcatcher", "en": "Ethereal Dreamcatcher", "it": "Acchiappasogni Etereo", "fr": "Attrape-rêves Éthéré", "es": "Atrapasueños Etéreo", "de": "Ätherischer Traumfänger"},
        {"id": "ca_starlight_hourglass", "en": "Starlight Hourglass", "it": "Clessidra Stellare", "fr": "Sablier Stellaire", "es": "Reloj de Arena Estelar", "de": "Sternenlicht-Sanduhr"},
        {"id": "ca_nebula_in_a_bottle", "en": "Nebula Bottle", "it": "Bottiglia Nebulosa", "fr": "Bouteille de Nébuleuse", "es": "Botella de Nebulosa", "de": "Nebel in einer Flasche"},
        {"id": "ca_lunar_moth_lantern", "en": "Lunar Lantern", "it": "Lanterna Lunare", "fr": "Lanterne Lunaire", "es": "Linterna Lunar", "de": "Mondlaterne"},
        {"id": "ca_celestial_tuning_fork", "en": "Celestial Tuning Fork", "it": "Diapason Celeste", "fr": "Diapason Céleste", "es": "Diapasón Celestial", "de": "Himmlische Stimmgabel"},
        {"id": "ca_void_crystal_shard", "en": "Void Crystal", "it": "Cristallo del Vuoto", "fr": "Cristal du Vide", "es": "Cristal del Vacío", "de": "Leerenkristall"},
        {"id": "ca_spirit_whisper_conch", "en": "Spirit Conch", "it": "Conchiglia degli Spiriti", "fr": "Conque Spirituelle", "es": "Caracola Espiritual", "de": "Geistermuschel"},
        {"id": "ca_dreamweaver_spindle", "en": "Dreamweaver Spindle", "it": "Fuso dei Sogni", "fr": "Fuseau des Rêves", "es": "Huso de los Sueños", "de": "Traumweber-Spindel"},
        {"id": "ca_aurora_borealis_prism", "en": "Aurora Prism", "it": "Prisma dell'Aurora", "fr": "Prisme d'Aurore", "es": "Prisma de Aurora", "de": "Aurora-Prisma"},
        {"id": "ca_galaxy_marbles_pouch", "en": "Galaxy Pouch", "it": "Borsetta Galattica", "fr": "Pochette Galactique", "es": "Bolsa Galáctica", "de": "Galaktischer Beutel"},
        {"id": "ca_comet_tail_feather", "en": "Comet Feather", "it": "Piuma di Cometa", "fr": "Plume de Comète", "es": "Pluma de Cometa", "de": "Kometenfeder"},
        {"id": "ca_zodiac_compass_gold", "en": "Zodiac Compass", "it": "Bussola dello Zodiaco", "fr": "Boussole du Zodiaque", "es": "Brújula del Zodíaco", "de": "Tierkreis-Kompass"},
        {"id": "ca_phantom_lotus_flower", "en": "Phantom Lotus", "it": "Loto Fantasma", "fr": "Lotus Fantôme", "es": "Loto Fantasma", "de": "Phantom-Lotus"},
        {"id": "ca_eclipse_mirror_silver", "en": "Eclipse Mirror", "it": "Specchio dell'Eclissi", "fr": "Miroir d'Éclipse", "es": "Eclipse-Spiegel", "de": "Finsternis-Spiegel"},
        {"id": "ca_twilight_music_box", "en": "Twilight Music Box", "it": "Carillon del Crepuscolo", "fr": "Boîte à Musique du Crépuscule", "es": "Caja de Música del Crepúsculo", "de": "Zwielicht-Spieldose"}
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
                # NIENTE TAGS
            })
            
            for lang in ["en", "it", "fr", "es", "de"]:
                translations[lang][label_key] = obj_info[lang]
            
            idx += 1

    # Update Catalog
    catalog_path = str(base_dir / "engine" / "data" / "global_cartoon_catalog.json")
    with open(catalog_path, "r", encoding="utf-8") as f:
        catalog = json.load(f)
        
    catalog["objects"].extend(catalog_entries)
    atomic_write(catalog, catalog_path)
        
    # Update Languages
    for lang in ["en", "it", "fr", "es", "de"]:
        lang_path = str(base_dir / "engine" / "assets" / "strings" / f"{lang}.json")
        with open(lang_path, "r", encoding="utf-8") as f:
            lang_data = json.load(f)
        lang_data.update(translations[lang])
        atomic_write(lang_data, lang_path)
    
    print(f"Elaborazione completata. {TOTAL_ITEMS} oggetti ASTRALI aggiunti al catalogo e 5 lingue aggiornate!")

if __name__ == "__main__":
    process_4x4_grid()
