import os
import json
import logging
from pathlib import Path
from PIL import Image
from rembg import remove, new_session

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

def process_grid():
    grid_path = r"C:\Users\indecenti\.gemini\antigravity\brain\54e1b99a-4397-4fea-b7bb-124218366c1c\weird_cartoon_objects_grid_8_1781220580413.png"
    output_dir = r"g:\HIE git\engine\assets\objects"
    cat_path = r"g:\HIE git\engine\data\global_cartoon_catalog.json"
    en_path = r"g:\HIE git\engine\assets\strings\en.json"
    it_path = r"g:\HIE git\engine\assets\strings\it.json"

    ids = [
        "ca_geiger_counter_yellow",
        "ca_cuckoo_clock_wooden",
        "ca_tesla_coil_electric",
        "ca_hourglass_sand_timer",
        "ca_divining_rod_wooden",
        "ca_cryptex_code_cylinder",
        "ca_astrolabe_brass",
        "ca_rubber_stamp_wooden",
        "ca_accordion_instrument",
        "ca_diving_helmet_brass",
        "ca_battering_ram_log",
        "ca_hookah_water_pipe",
        "ca_magic_8_ball_black",
        "ca_dowsing_pendulum_crystal",
        "ca_ant_farm_glass",
        "ca_bear_trap_metal"
    ]

    translations = {
        "ca_geiger_counter_yellow": {"en": "Yellow Geiger Counter", "it": "Contatore Geiger Giallo"},
        "ca_cuckoo_clock_wooden": {"en": "Wooden Cuckoo Clock", "it": "Orologio a Cucù in Legno"},
        "ca_tesla_coil_electric": {"en": "Electric Tesla Coil", "it": "Bobina di Tesla Elettrica"},
        "ca_hourglass_sand_timer": {"en": "Sand Hourglass", "it": "Clessidra a Sabbia"},
        "ca_divining_rod_wooden": {"en": "Wooden Divining Rod", "it": "Verga da Rabdomante"},
        "ca_cryptex_code_cylinder": {"en": "Cryptex Code Cylinder", "it": "Cilindro Criptex"},
        "ca_astrolabe_brass": {"en": "Brass Astrolabe", "it": "Astrolabio in Ottone"},
        "ca_rubber_stamp_wooden": {"en": "Wooden Rubber Stamp", "it": "Timbro di Gomma"},
        "ca_accordion_instrument": {"en": "Red Accordion", "it": "Fisarmonica Rossa"},
        "ca_diving_helmet_brass": {"en": "Brass Diving Helmet", "it": "Casco da Palombaro in Ottone"},
        "ca_battering_ram_log": {"en": "Battering Ram Log", "it": "Ariete da Sfondamento"},
        "ca_hookah_water_pipe": {"en": "Glass Hookah Water Pipe", "it": "Narghilè in Vetro"},
        "ca_magic_8_ball_black": {"en": "Black Magic 8-Ball", "it": "Palla 8 Magica Nera"},
        "ca_dowsing_pendulum_crystal": {"en": "Crystal Dowsing Pendulum", "it": "Pendolo da Rabdomante"},
        "ca_ant_farm_glass": {"en": "Glass Ant Farm", "it": "Formicaio Artificiale"},
        "ca_bear_trap_metal": {"en": "Metal Bear Trap", "it": "Trappola per Orsi in Metallo"}
    }

    tags = {
        "ca_geiger_counter_yellow": ["tech", "weird", "yellow", "radiation", "tool"],
        "ca_cuckoo_clock_wooden": ["wood", "clock", "time", "bird", "vintage"],
        "ca_tesla_coil_electric": ["electric", "weird", "science", "tech", "lightning"],
        "ca_hourglass_sand_timer": ["time", "glass", "weird", "magic", "ancient"],
        "ca_divining_rod_wooden": ["wood", "weird", "magic", "stick", "tool"],
        "ca_cryptex_code_cylinder": ["code", "weird", "puzzle", "mystery", "brass"],
        "ca_astrolabe_brass": ["brass", "weird", "ancient", "space", "instrument"],
        "ca_rubber_stamp_wooden": ["wood", "stamp", "tool", "weird", "office"],
        "ca_accordion_instrument": ["instrument", "music", "red", "weird"],
        "ca_diving_helmet_brass": ["brass", "underwater", "weird", "helmet", "vintage"],
        "ca_battering_ram_log": ["wood", "weapon", "weird", "medieval"],
        "ca_hookah_water_pipe": ["glass", "smoke", "weird", "oriental"],
        "ca_magic_8_ball_black": ["magic", "black", "game", "weird", "ball"],
        "ca_dowsing_pendulum_crystal": ["magic", "crystal", "weird", "tool"],
        "ca_ant_farm_glass": ["glass", "animal", "weird", "nature", "box"],
        "ca_bear_trap_metal": ["metal", "trap", "weird", "weapon", "danger"]
    }

    try:
        img = Image.open(grid_path).convert("RGBA")
    except Exception as e:
        logging.error(f"Errore caricamento griglia: {e}")
        return

    w, h = img.size
    cell_w, cell_h = w // 4, h // 4
    session = new_session("u2net")

    for i, obj_id in enumerate(ids):
        col, row = i % 4, i // 4
        box = (col * cell_w, row * cell_h, (col + 1) * cell_w, (row + 1) * cell_h)
        cell = img.crop(box)
        
        # Tolleranza colore mantenuta (alpha matting)
        processed = remove(cell, session=session, alpha_matting=True, alpha_matting_foreground_threshold=240, alpha_matting_background_threshold=10, alpha_matting_erode_size=10)
        
        bbox = processed.getbbox()
        if bbox:
            processed = processed.crop(bbox)
        
        out_path = os.path.join(output_dir, f"{obj_id}.png")
        processed.save(out_path)
        logging.info(f"Salvato: {obj_id}.png")

    # Aggiornamento JSON
    with open(cat_path, 'r', encoding='utf-8') as f:
        catalog = json.load(f)

    existing_ids = {obj["id"] for obj in catalog.get("objects", [])}
    for obj_id in ids:
        if obj_id not in existing_ids:
            entry = {
                "id": obj_id,
                "name_key": f"{obj_id}_name",
                "image": f"{obj_id}.png",
                "detection_type": "rect",
                "tags": tags[obj_id]
            }
            catalog["objects"].append(entry)

    with open(cat_path, 'w', encoding='utf-8') as f:
        json.dump(catalog, f, indent=4)
        
    for lang_path, lang_code in [(en_path, "en"), (it_path, "it")]:
        with open(lang_path, 'r', encoding='utf-8') as f:
            lang_data = json.load(f)
        for obj_id in ids:
            lang_data[f"{obj_id}_name"] = translations[obj_id][lang_code]
        with open(lang_path, 'w', encoding='utf-8') as f:
            json.dump(lang_data, f, indent=2, ensure_ascii=False)
            
    logging.info("Catalogo e traduzioni aggiornati!")

if __name__ == '__main__':
    process_grid()
