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
            
            # Rimuoviamo lo sfondo perfettamente con l'IA
            out = rembg.remove(cell_img)
            out.save(final_path)
            print(f"Processed: {obj_id}")
            idx += 1

def main():
    img_path = r"C:\Users\indecenti\.gemini\antigravity\brain\54e1b99a-4397-4fea-b7bb-124218366c1c\weird_cartoon_objects_grid_7_1781219438675.png"
    engine_assets_dir = Path(r"g:\HIE git\engine\assets\objects_cartoon")
    
    objects = [
        ("ca_guillotine_blade_sharp", "obj_ca_guillotine_blade_sharp", ["arma", "macabro", "legno"]),
        ("ca_carillon_ballerina_wooden", "obj_ca_carillon_ballerina_wooden", ["musica", "giocattolo", "meccanismo"]),
        ("ca_hurdy_gurdy_instrument", "obj_ca_hurdy_gurdy_instrument", ["musica", "strumento", "legno"]),
        ("ca_french_horn_brass", "obj_ca_french_horn_brass", ["musica", "strumento", "ottone"]),
        ("ca_synthesizer_keyboard", "obj_ca_synthesizer_keyboard", ["musica", "strumento", "elettronico"]),
        ("ca_polygraph_machine_test", "obj_ca_polygraph_machine_test", ["scienza", "misura", "tech"]),
        ("ca_telegraph_key_vintage", "obj_ca_telegraph_key_vintage", ["comunicazione", "antico", "tecnologia"]),
        ("ca_machete_jungle_blade", "obj_ca_machete_jungle_blade", ["arma", "bosco", "pericolo"]),
        ("ca_halberd_polearm", "obj_ca_halberd_polearm", ["arma", "antico", "metallo"]),
        ("ca_flail_medieval_weapon", "obj_ca_flail_medieval_weapon", ["arma", "antico", "pericolo"]),
        ("ca_crossbow_wooden", "obj_ca_crossbow_wooden", ["arma", "caccia", "legno"]),
        ("ca_trident_golden_pitchfork", "obj_ca_trident_golden_pitchfork", ["arma", "mare", "antico"]),
        ("ca_scythe_grim_reaper", "obj_ca_scythe_grim_reaper", ["attrezzo", "macabro", "natura"]),
        ("ca_pneumatic_drill_yellow", "obj_ca_pneumatic_drill_yellow", ["attrezzo", "officina", "metallo"]),
        ("ca_wrecking_ball_crane", "obj_ca_wrecking_ball_crane", ["veicolo", "metallo", "pericolo"]),
        ("ca_wheelbarrow_metal_garden", "obj_ca_wheelbarrow_metal_garden", ["attrezzo", "giardino", "metallo"])
    ]
    
    translations = {
        "ca_guillotine_blade_sharp": {"en": "Guillotine", "it": "Ghigliottina"},
        "ca_carillon_ballerina_wooden": {"en": "Music Box", "it": "Carillon"},
        "ca_hurdy_gurdy_instrument": {"en": "Hurdy-Gurdy", "it": "Ghironda"},
        "ca_french_horn_brass": {"en": "French Horn", "it": "Corno Francese"},
        "ca_synthesizer_keyboard": {"en": "Synthesizer", "it": "Sintetizzatore"},
        "ca_polygraph_machine_test": {"en": "Polygraph", "it": "Macchina della Verità"},
        "ca_telegraph_key_vintage": {"en": "Telegraph Key", "it": "Telegrafo"},
        "ca_machete_jungle_blade": {"en": "Machete", "it": "Machete"},
        "ca_halberd_polearm": {"en": "Halberd", "it": "Alabarda"},
        "ca_flail_medieval_weapon": {"en": "Flail", "it": "Mazzafrusto"},
        "ca_crossbow_wooden": {"en": "Crossbow", "it": "Balestra"},
        "ca_trident_golden_pitchfork": {"en": "Golden Trident", "it": "Tridente Dorato"},
        "ca_scythe_grim_reaper": {"en": "Scythe", "it": "Falce"},
        "ca_pneumatic_drill_yellow": {"en": "Pneumatic Drill", "it": "Martello Pneumatico"},
        "ca_wrecking_ball_crane": {"en": "Wrecking Ball", "it": "Palla da Demolizione"},
        "ca_wheelbarrow_metal_garden": {"en": "Wheelbarrow", "it": "Carriola"}
    }
    
    print("Elaborazione griglia tramite AI (rembg)...")
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
    
    print(f"Completato. {added} nuovi asset aggiunti!")

if __name__ == "__main__":
    main()
