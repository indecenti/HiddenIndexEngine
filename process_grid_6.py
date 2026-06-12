import json
import os
import rembg
from pathlib import Path
from PIL import Image

def process_grid(img_path, objects_list, engine_assets_dir):
    img = Image.open(img_path)
    w, h = img.size
    cell_w = w // 4
    cell_h = h // 4
    
    idx = 0
    for r in range(4):
        for c in range(4):
            if idx >= len(objects_list): break
            left = c * cell_w
            top = r * cell_h
            right = left + cell_w
            bottom = top + cell_h
            
            cell_img = img.crop((left, top, right, bottom))
            obj_id = objects_list[idx][0]
            
            final_path = str(engine_assets_dir / f"{obj_id}.png")
            
            # Perfect background removal using AI (rembg)
            out = rembg.remove(cell_img)
            out.save(final_path)
            print(f"Processed: {obj_id}")
            idx += 1

def main():
    img_path = r"C:\Users\indecenti\.gemini\antigravity\brain\54e1b99a-4397-4fea-b7bb-124218366c1c\weird_cartoon_objects_grid_6_1781218741468.png"
    engine_assets_dir = Path(r"g:\HIE git\engine\assets\objects_cartoon")
    
    objects = [
        ("ca_loom_weaving_wooden", "obj_ca_loom_weaving_wooden", ["legno", "strumento", "antico"]),
        ("ca_chandelier_crystal", "obj_ca_chandelier_crystal", ["vetro", "luce", "decorazione"]),
        ("ca_iron_maiden_torture", "obj_ca_iron_maiden_torture", ["metallo", "macabro", "antico"]),
        ("ca_phonograph_horn", "obj_ca_phonograph_horn", ["musica", "audio", "antico"]),
        ("ca_banjo_instrument", "obj_ca_banjo_instrument", ["musica", "strumento", "legno"]),
        ("ca_kazoo_plastic", "obj_ca_kazoo_plastic", ["musica", "strumento", "plastica"]),
        ("ca_cowbell_metal", "obj_ca_cowbell_metal", ["musica", "strumento", "metallo"]),
        ("ca_cymbals_brass", "obj_ca_cymbals_brass", ["musica", "strumento", "ottone"]),
        ("ca_panflute_bamboo", "obj_ca_panflute_bamboo", ["musica", "strumento", "legno"]),
        ("ca_tricycle_red", "obj_ca_tricycle_red", ["veicolo", "gioco", "plastica"]),
        ("ca_pennyfarthing_vintage", "obj_ca_pennyfarthing_vintage", ["veicolo", "antico", "metallo"]),
        ("ca_submarine_yellow", "obj_ca_submarine_yellow", ["veicolo", "mare", "metallo"]),
        ("ca_radar_dish_green", "obj_ca_radar_dish_green", ["tecnologia", "tech", "elettronica"]),
        ("ca_seismograph_paper", "obj_ca_seismograph_paper", ["scienza", "misura", "carta"]),
        ("ca_enigma_machine_code", "obj_ca_enigma_machine_code", ["tecnologia", "mistero", "vintage"]),
        ("ca_blowtorch_blue_flame", "obj_ca_blowtorch_blue_flame", ["attrezzo", "fuoco", "metallo"])
    ]
    
    translations = {
        "ca_loom_weaving_wooden": {"en": "Wooden Loom", "it": "Telaio di Legno"},
        "ca_chandelier_crystal": {"en": "Crystal Chandelier", "it": "Lampadario di Cristallo"},
        "ca_iron_maiden_torture": {"en": "Iron Maiden", "it": "Vergine di Norimberga"},
        "ca_phonograph_horn": {"en": "Antique Phonograph", "it": "Fonografo Antico"},
        "ca_banjo_instrument": {"en": "Banjo", "it": "Banjo"},
        "ca_kazoo_plastic": {"en": "Plastic Kazoo", "it": "Kazoo di Plastica"},
        "ca_cowbell_metal": {"en": "Metal Cowbell", "it": "Campanaccio"},
        "ca_cymbals_brass": {"en": "Brass Cymbals", "it": "Piatti Musicali"},
        "ca_panflute_bamboo": {"en": "Bamboo Panflute", "it": "Flauto di Pan"},
        "ca_tricycle_red": {"en": "Red Tricycle", "it": "Triciclo Rosso"},
        "ca_pennyfarthing_vintage": {"en": "Penny-farthing Bicycle", "it": "Velocipede"},
        "ca_submarine_yellow": {"en": "Yellow Submarine", "it": "Sottomarino Giallo"},
        "ca_radar_dish_green": {"en": "Radar Dish", "it": "Antenna Radar"},
        "ca_seismograph_paper": {"en": "Seismograph", "it": "Sismografo"},
        "ca_enigma_machine_code": {"en": "Enigma Machine", "it": "Macchina Enigma"},
        "ca_blowtorch_blue_flame": {"en": "Blowtorch", "it": "Fiamma Ossidrica"}
    }
    
    print("Elaborazione griglia tramite rembg...")
    process_grid(img_path, objects, engine_assets_dir)
    
    catalog_entries = []
    for obj_id, label_key, tags in objects:
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
    
    print(f"Completato. {added} oggetti aggiunti!")

if __name__ == "__main__":
    main()
