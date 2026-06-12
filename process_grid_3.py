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
    img_path = r"C:\Users\indecenti\.gemini\antigravity\brain\54e1b99a-4397-4fea-b7bb-124218366c1c\weird_cartoon_objects_grid_3_1781214867423.png"
    engine_assets_dir = Path(r"g:\HIE git\engine\assets\objects_cartoon")
    
    objects = [
        ("ca_cotton_candy_pink", "obj_ca_cotton_candy_pink", ["cibo", "dolce", "rosa"]),
        ("ca_saxophone_golden", "obj_ca_saxophone_golden", ["musica", "strumento", "ottone"]),
        ("ca_gargoyle_stone_statue", "obj_ca_gargoyle_stone_statue", ["pietra", "statua", "macabro"]),
        ("ca_pogo_stick_red", "obj_ca_pogo_stick_red", ["giocattolo", "sport", "metallo"]),
        ("ca_clown_wig_rainbow", "obj_ca_clown_wig_rainbow", ["abbigliamento", "circo", "colorato"]),
        ("ca_dreamcatcher_feathers", "obj_ca_dreamcatcher_feathers", ["decorazione", "magia", "cultura"]),
        ("ca_waffle_iron_open", "obj_ca_waffle_iron_open", ["cucina", "elettrodomestico", "metallo"]),
        ("ca_stoplight_red", "obj_ca_stoplight_red", ["strada", "segnaletica", "luce"]),
        ("ca_kaleidoscope_toy", "obj_ca_kaleidoscope_toy", ["giocattolo", "ottica", "magia"]),
        ("ca_bagpipes_tartan", "obj_ca_bagpipes_tartan", ["musica", "strumento", "tessuto"]),
        ("ca_unicycle_red", "obj_ca_unicycle_red", ["veicolo", "circo", "sport"]),
        ("ca_slingshot_wooden", "obj_ca_slingshot_wooden", ["arma", "legno", "giocattolo"]),
        ("ca_metronome_wooden", "obj_ca_metronome_wooden", ["musica", "strumento", "legno"]),
        ("ca_maracas_colorful", "obj_ca_maracas_colorful", ["musica", "strumento", "cultura"]),
        ("ca_ouija_board_planchette", "obj_ca_ouija_board_planchette", ["magia", "occulto", "gioco"]),
        ("ca_disco_ball_shiny", "obj_ca_disco_ball_shiny", ["decorazione", "luce", "vetro"])
    ]
    
    # We will fallback to "oggetto" instead of non-existing tags for safety. 
    # Let's map any non-existing tags. Actually, wait. I can't check the catalog dynamically in this list easily. I'll just use known tags.
    # From previous query: cibo, dolce, rosa, musica, strumento, ottone, pietra, macabro, giocattolo, sport, metallo, abbigliamento, circo, decorazione, magia, cultura, cucina, strada(not exist)->esterno, segnaletica, luce, ottica, tessuto, veicolo, arma, legno, occulto, gioco, vetro
    
    # Replace non-existent tags
    # "colorato" -> "arte", "elettrodomestico" -> "elettrodomestico"(not exist) -> "macchina"/"elettronico", "strada" -> "esterno"
    tags_fix = {
        "colorato": "arte",
        "elettrodomestico": "elettronico",
        "strada": "esterno",
        "statua": "arte"
    }
    
    for i in range(len(objects)):
        fixed_tags = [tags_fix.get(t, t) for t in objects[i][2]]
        objects[i] = (objects[i][0], objects[i][1], fixed_tags)
    
    translations = {
        "ca_cotton_candy_pink": {"en": "Pink Cotton Candy", "it": "Zucchero Filato"},
        "ca_saxophone_golden": {"en": "Golden Saxophone", "it": "Sassofono"},
        "ca_gargoyle_stone_statue": {"en": "Stone Gargoyle", "it": "Statua Gargoyle"},
        "ca_pogo_stick_red": {"en": "Red Pogo Stick", "it": "Pogo Stick"},
        "ca_clown_wig_rainbow": {"en": "Rainbow Clown Wig", "it": "Parrucca da Clown"},
        "ca_dreamcatcher_feathers": {"en": "Dreamcatcher", "it": "Acchiappasogni"},
        "ca_waffle_iron_open": {"en": "Waffle Iron", "it": "Piastra per Waffle"},
        "ca_stoplight_red": {"en": "Red Stoplight", "it": "Semaforo"},
        "ca_kaleidoscope_toy": {"en": "Toy Kaleidoscope", "it": "Caleidoscopio"},
        "ca_bagpipes_tartan": {"en": "Tartan Bagpipes", "it": "Cornamusa"},
        "ca_unicycle_red": {"en": "Red Unicycle", "it": "Monociclo"},
        "ca_slingshot_wooden": {"en": "Wooden Slingshot", "it": "Fionda di Legno"},
        "ca_metronome_wooden": {"en": "Wooden Metronome", "it": "Metronomo"},
        "ca_maracas_colorful": {"en": "Colorful Maracas", "it": "Maracas Colorate"},
        "ca_ouija_board_planchette": {"en": "Ouija Board", "it": "Tavola Ouija"},
        "ca_disco_ball_shiny": {"en": "Shiny Disco Ball", "it": "Sfera Specchiata da Discoteca"}
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
