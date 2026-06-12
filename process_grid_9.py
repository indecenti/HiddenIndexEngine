import json
import os
from pathlib import Path
from PIL import Image
from rembg import remove, new_session
import logging

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

def process_grid():
    # Sostituisci con il path dell'immagine pulita una volta aggirato il rate limit
    img_path = r"C:\Users\indecenti\.gemini\antigravity\brain\1c28f396-56a3-4ebf-945f-057201fad9d8\cartoon_grid_scifi_magic_1781263823124.png"
    engine_assets_dir = Path(r"g:\HIE git\engine\assets\objects_cartoon")
    cat_path = r"g:\HIE git\engine\data\global_cartoon_catalog.json"
    en_path = r"g:\HIE git\engine\assets\strings\en.json"
    it_path = r"g:\HIE git\engine\assets\strings\it.json"

    objects = [
        ("ca_quantum_toaster_neon", "obj_ca_quantum_toaster_neon", ["macchina", "scienza", "strano"]),
        ("ca_mecha_squirrel_toy", "obj_ca_mecha_squirrel_toy", ["giocattolo", "robot", "metallo"]),
        ("ca_haptic_cyber_glove", "obj_ca_haptic_cyber_glove", ["abbigliamento", "tecnologia", "futuro"]),
        ("ca_plasma_cutter_tool", "obj_ca_plasma_cutter_tool", ["attrezzo", "scienza", "arma"]),
        ("ca_steampunk_jetpack_brass", "obj_ca_steampunk_jetpack_brass", ["veicolo", "volo", "ottone"]),
        ("ca_crystal_skull_pink", "obj_ca_crystal_skull_pink", ["magia", "pietra", "macabro"]),
        ("ca_floating_bonsai_tree", "obj_ca_floating_bonsai_tree", ["pianta", "natura", "magia"]),
        ("ca_magic_carpet_rolled", "obj_ca_magic_carpet_rolled", ["tessuto", "magia", "veicolo"]),
        ("ca_clockwork_vampire_teeth", "obj_ca_clockwork_vampire_teeth", ["giocattolo", "macabro", "meccanismo"]),
        ("ca_glowing_alien_egg", "obj_ca_glowing_alien_egg", ["scienza", "strano", "natura"]),
        ("ca_fire_spell_scroll", "obj_ca_fire_spell_scroll", ["carta", "magia", "fuoco"]),
        ("ca_cybernetic_pirate_hook", "obj_ca_cybernetic_pirate_hook", ["metallo", "arma", "tecnologia"]),
        ("ca_green_brain_in_a_jar", "obj_ca_green_brain_in_a_jar", ["scienza", "macabro", "vetro"]),
        ("ca_golden_ticket_wonka", "obj_ca_golden_ticket_wonka", ["carta", "gioco", "oro"]),
        ("ca_radioactive_pizza_slice", "obj_ca_radioactive_pizza_slice", ["cibo", "strano", "pericolo"]),
        ("ca_laser_nunchaku_blue", "obj_ca_laser_nunchaku_blue", ["arma", "tecnologia", "luce"])
    ]

    translations = {
        "ca_quantum_toaster_neon": {"en": "Neon Quantum Toaster", "it": "Tostapane Quantico al Neon"},
        "ca_mecha_squirrel_toy": {"en": "Mecha Squirrel Toy", "it": "Scoiattolo Meccanico Giocattolo"},
        "ca_haptic_cyber_glove": {"en": "Haptic Cyber Glove", "it": "Guanto Cibernetico Aptico"},
        "ca_plasma_cutter_tool": {"en": "Plasma Cutter", "it": "Tagliatore al Plasma"},
        "ca_steampunk_jetpack_brass": {"en": "Steampunk Jetpack", "it": "Jetpack Steampunk"},
        "ca_crystal_skull_pink": {"en": "Pink Crystal Skull", "it": "Teschio di Cristallo Rosa"},
        "ca_floating_bonsai_tree": {"en": "Floating Bonsai", "it": "Bonsai Fluttuante"},
        "ca_magic_carpet_rolled": {"en": "Rolled Magic Carpet", "it": "Tappeto Volante Arrotolato"},
        "ca_clockwork_vampire_teeth": {"en": "Clockwork Vampire Teeth", "it": "Denti da Vampiro a Molla"},
        "ca_glowing_alien_egg": {"en": "Glowing Alien Egg", "it": "Uovo Alieno Luminescente"},
        "ca_fire_spell_scroll": {"en": "Fire Spell Scroll", "it": "Pergamena della Palla di Fuoco"},
        "ca_cybernetic_pirate_hook": {"en": "Cybernetic Pirate Hook", "it": "Uncino da Pirata Cibernetico"},
        "ca_green_brain_in_a_jar": {"en": "Green Brain in a Jar", "it": "Cervello in Barattolo Verde"},
        "ca_golden_ticket_wonka": {"en": "Golden Ticket", "it": "Biglietto d'Oro"},
        "ca_radioactive_pizza_slice": {"en": "Radioactive Pizza Slice", "it": "Fetta di Pizza Radioattiva"},
        "ca_laser_nunchaku_blue": {"en": "Blue Laser Nunchaku", "it": "Nunchaku Laser Blu"}
    }

    if not os.path.exists(img_path):
        logging.error(f"Immagine non trovata: {img_path}")
        return

    img = Image.open(img_path)
    w, h = img.size
    cell_w = w // 4
    cell_h = h // 4
    session = new_session()

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
            
            final_path = engine_assets_dir / f"{obj_id}.png"
            
            logging.info(f"Processando {obj_id} con Rembg...")
            out = remove(cell_img, session=session)
            out.save(final_path)
            
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

    # Atomic write per catalogo
    with open(cat_path, "r", encoding="utf-8") as f:
        catalog = json.load(f)
        
    catalog["objects"].extend(catalog_entries)
    
    tmp_cat = cat_path + ".tmp"
    with open(tmp_cat, "w", encoding="utf-8") as f:
        json.dump(catalog, f, indent=2, ensure_ascii=False)
    os.replace(tmp_cat, cat_path)
    
    # Aggiornamento Lingue
    with open(en_path, "r", encoding="utf-8") as f: en_data = json.load(f)
    with open(it_path, "r", encoding="utf-8") as f: it_data = json.load(f)
    
    for obj_id, label_key, _ in objects:
        en_data[label_key] = translations[obj_id]["en"]
        it_data[label_key] = translations[obj_id]["it"]
        
    tmp_en = en_path + ".tmp"
    with open(tmp_en, "w", encoding="utf-8") as f:
        json.dump(en_data, f, indent=2, ensure_ascii=False)
    os.replace(tmp_en, en_path)

    tmp_it = it_path + ".tmp"
    with open(tmp_it, "w", encoding="utf-8") as f:
        json.dump(it_data, f, indent=2, ensure_ascii=False)
    os.replace(tmp_it, it_path)

    logging.info("Elaborazione completata. 16 nuovi oggetti aggiunti al catalogo.")

if __name__ == "__main__":
    process_grid()
