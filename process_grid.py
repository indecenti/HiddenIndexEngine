import json
import os
import cv2
import numpy as np
from pathlib import Path
from PIL import Image

def remove_background_cv2(image_path, out_path):
    img = cv2.imread(image_path, cv2.IMREAD_COLOR)
    if img is None: return
    
    # We will floodfill from the corners to find the background
    h, w = img.shape[:2]
    mask = np.zeros((h + 2, w + 2), np.uint8)
    
    # Floodfill with a specific color (e.g. pure green) on the image, or just fill the mask directly
    # To use mask, we use flags=cv2.FLOODFILL_MASK_ONLY or similar.
    diff = (15, 15, 15)
    
    # We create a copy for floodfilling
    img_ff = img.copy()
    cv2.floodFill(img_ff, mask, (0,0), (0, 255, 0), diff, diff, cv2.FLOODFILL_FIXED_RANGE)
    cv2.floodFill(img_ff, mask, (w-1,0), (0, 255, 0), diff, diff, cv2.FLOODFILL_FIXED_RANGE)
    cv2.floodFill(img_ff, mask, (0,h-1), (0, 255, 0), diff, diff, cv2.FLOODFILL_FIXED_RANGE)
    cv2.floodFill(img_ff, mask, (w-1,h-1), (0, 255, 0), diff, diff, cv2.FLOODFILL_FIXED_RANGE)
    
    # Now mask has 1 where the background was flooded. Wait, floodFill updates mask with 1s.
    
    # Add alpha channel
    rgba = cv2.cvtColor(img, cv2.COLOR_BGR2BGRA)
    
    # The mask from floodFill is expanded by 1 pixel on each side.
    bg_mask = mask[1:-1, 1:-1]
    
    # Set alpha to 0 for background pixels
    rgba[bg_mask == 1, 3] = 0
    
    # Additional pass for pure/almost white
    lower_white = np.array([245, 245, 245, 255])
    upper_white = np.array([255, 255, 255, 255])
    mask_white = cv2.inRange(rgba, lower_white, upper_white)
    rgba[mask_white > 0, 3] = 0
    
    cv2.imwrite(out_path, rgba)

def main():
    img_path = r"C:\Users\indecenti\.gemini\antigravity\brain\54e1b99a-4397-4fea-b7bb-124218366c1c\cartoon_objects_grid_1781213358500.png"
    engine_assets_dir = Path(r"g:\HIE git\engine\assets\objects_cartoon")
    
    objects = [
        ("ca_magic_potion_blue", "obj_ca_magic_potion_blue", ["magia", "vetro", "scienza"]),
        ("ca_cyberpunk_goggles", "obj_ca_cyberpunk_goggles", ["tecnologia", "plastica", "ottica"]),
        ("ca_steampunk_pocket_watch", "obj_ca_steampunk_pocket_watch", ["antico", "metallo", "tempo"]),
        ("ca_alien_blaster_toy", "obj_ca_alien_blaster_toy", ["giocattolo", "plastica", "tecnologia"]),
        ("ca_viking_drinking_horn", "obj_ca_viking_drinking_horn", ["antico", "natura", "cibo"]),
        ("ca_ninja_shuriken_gold", "obj_ca_ninja_shuriken_gold", ["metallo", "pericolo", "antico"]),
        ("ca_pirate_treasure_map_rolled", "obj_ca_pirate_treasure_map_rolled", ["carta", "antico", "mistero"]),
        ("ca_retro_cassette_tape_pink", "obj_ca_retro_cassette_tape_pink", ["retro", "plastica", "musica"]),
        ("ca_crystal_ball_glowing", "obj_ca_crystal_ball_glowing", ["magia", "mistero", "vetro"]),
        ("ca_dragon_egg_purple", "obj_ca_dragon_egg_purple", ["magia", "natura", "mistero"]),
        ("ca_robot_dog_toy", "obj_ca_robot_dog_toy", ["giocattolo", "tecnologia", "metallo"]),
        ("ca_voodoo_doll_patched", "obj_ca_voodoo_doll_patched", ["stoffa", "magia", "mistero"]),
        ("ca_wizard_spellbook_ancient", "obj_ca_wizard_spellbook_ancient", ["carta", "magia", "antico"]),
        ("ca_ufo_mini_model", "obj_ca_ufo_mini_model", ["giocattolo", "metallo", "scienza"]),
        ("ca_excalibur_sword_stone", "obj_ca_excalibur_sword_stone", ["antico", "metallo", "magia"]),
        ("ca_magic_lamp_genie", "obj_ca_magic_lamp_genie", ["antico", "metallo", "magia"])
    ]
    
    translations = {
        "ca_magic_potion_blue": {"en": "Blue Magic Potion", "it": "Pozione Magica Blu"},
        "ca_cyberpunk_goggles": {"en": "Cyberpunk Goggles", "it": "Occhiali Cyberpunk"},
        "ca_steampunk_pocket_watch": {"en": "Steampunk Pocket Watch", "it": "Orologio da Taschino Steampunk"},
        "ca_alien_blaster_toy": {"en": "Alien Blaster Toy", "it": "Pistola Giocattolo Aliena"},
        "ca_viking_drinking_horn": {"en": "Viking Drinking Horn", "it": "Corno Potorio Vichingo"},
        "ca_ninja_shuriken_gold": {"en": "Golden Shuriken", "it": "Shuriken d'Oro"},
        "ca_pirate_treasure_map_rolled": {"en": "Rolled Treasure Map", "it": "Mappa del Tesoro Arrotolata"},
        "ca_retro_cassette_tape_pink": {"en": "Pink Retro Cassette", "it": "Musicassetta Rosa Retro"},
        "ca_crystal_ball_glowing": {"en": "Glowing Crystal Ball", "it": "Sfera di Cristallo Luminosa"},
        "ca_dragon_egg_purple": {"en": "Purple Dragon Egg", "it": "Uovo di Drago Viola"},
        "ca_robot_dog_toy": {"en": "Robot Dog Toy", "it": "Cane Robot Giocattolo"},
        "ca_voodoo_doll_patched": {"en": "Patched Voodoo Doll", "it": "Bambola Voodoo"},
        "ca_wizard_spellbook_ancient": {"en": "Ancient Spellbook", "it": "Libro di Incantesimi Antico"},
        "ca_ufo_mini_model": {"en": "Mini UFO Model", "it": "Modellino UFO"},
        "ca_excalibur_sword_stone": {"en": "Sword in the Stone", "it": "Spada nella Roccia"},
        "ca_magic_lamp_genie": {"en": "Magic Genie Lamp", "it": "Lampada Magica"}
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
            
            remove_background_cv2(temp_path, final_path)
            
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
        
    catalog["objects"].extend(catalog_entries)
    
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
    
    print("Elaborazione completata. 16 oggetti aggiunti al catalogo e stringhe aggiornate!")

if __name__ == "__main__":
    main()
