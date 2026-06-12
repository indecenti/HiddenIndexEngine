import json
import os
from pathlib import Path
from PIL import Image
from rembg import remove, new_session
import logging

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

def process_grid():
    # Sostituisci con il path della nuova immagine pulita senza griglie/testi
    img_path = r"C:\path\to\your\horror_cartoon_grid_4x4.png"
    engine_assets_dir = Path(r"g:\HIE git\engine\assets\objects_cartoon")
    cat_path = r"g:\HIE git\engine\data\global_cartoon_catalog.json"
    en_path = r"g:\HIE git\engine\assets\strings\en.json"
    it_path = r"g:\HIE git\engine\assets\strings\it.json"

    objects = [
        ("ca_necronomicon_book_flesh", "obj_ca_necronomicon_book_flesh", ["magia", "macabro", "libro"]),
        ("ca_guillotine_blade_bloody", "obj_ca_guillotine_blade_bloody", ["arma", "macabro", "metallo"]),
        ("ca_shrunken_head_voodoo", "obj_ca_shrunken_head_voodoo", ["magia", "macabro", "cultura"]),
        ("ca_severed_hand_crawling", "obj_ca_severed_hand_crawling", ["macabro", "mostro", "carne"]),
        ("ca_cursed_pendant_blood", "obj_ca_cursed_pendant_blood", ["magia", "gioiello", "macabro"]),
        ("ca_chainsaw_rusty_gore", "obj_ca_chainsaw_rusty_gore", ["arma", "macabro", "metallo"]),
        ("ca_brain_with_eyeballs", "obj_ca_brain_with_eyeballs", ["scienza", "macabro", "carne"]),
        ("ca_vampire_stake_wooden", "obj_ca_vampire_stake_wooden", ["arma", "legno", "macabro"]),
        ("ca_coffin_creepy_wood", "obj_ca_coffin_creepy_wood", ["macabro", "legno", "religione"]),
        ("ca_embalming_fluid_jar", "obj_ca_embalming_fluid_jar", ["scienza", "macabro", "vetro"]),
        ("ca_hangman_noose_rope", "obj_ca_hangman_noose_rope", ["macabro", "arma", "corda"]),
        ("ca_straightjacket_dirty", "obj_ca_straightjacket_dirty", ["abbigliamento", "macabro", "tessuto"]),
        ("ca_witch_cauldron_bubbling", "obj_ca_witch_cauldron_bubbling", ["magia", "macabro", "metallo"]),
        ("ca_butcher_cleaver_cursed", "obj_ca_butcher_cleaver_cursed", ["arma", "macabro", "metallo"]),
        ("ca_tarot_card_death", "obj_ca_tarot_card_death", ["magia", "macabro", "carta"]),
        ("ca_tombstone_rip_mossy", "obj_ca_tombstone_rip_mossy", ["macabro", "pietra", "religione"])
    ]

    translations = {
        "ca_necronomicon_book_flesh": {"en": "Flesh-bound Necronomicon", "it": "Necronomicon Rilegato in Pelle"},
        "ca_guillotine_blade_bloody": {"en": "Bloody Guillotine Blade", "it": "Lama di Ghigliottina Insanguinata"},
        "ca_shrunken_head_voodoo": {"en": "Voodoo Shrunken Head", "it": "Testa Rimpicciolita Voodoo"},
        "ca_severed_hand_crawling": {"en": "Crawling Severed Hand", "it": "Mano Mozzata Strisciante"},
        "ca_cursed_pendant_blood": {"en": "Cursed Blood Pendant", "it": "Pendente di Sangue Maledetto"},
        "ca_chainsaw_rusty_gore": {"en": "Rusty Chainsaw", "it": "Motosega Arrugginita"},
        "ca_brain_with_eyeballs": {"en": "Brain with Eyeballs", "it": "Cervello con Occhi"},
        "ca_vampire_stake_wooden": {"en": "Wooden Vampire Stake", "it": "Paletto di Legno per Vampiri"},
        "ca_coffin_creepy_wood": {"en": "Creepy Wooden Coffin", "it": "Bara di Legno Inquietante"},
        "ca_embalming_fluid_jar": {"en": "Embalming Fluid Jar", "it": "Barattolo di Fluido per Imbalsamazione"},
        "ca_hangman_noose_rope": {"en": "Hangman's Noose", "it": "Cappio da Impiccagione"},
        "ca_straightjacket_dirty": {"en": "Dirty Straightjacket", "it": "Camicia di Forza Sporca"},
        "ca_witch_cauldron_bubbling": {"en": "Bubbling Witch Cauldron", "it": "Calderone della Strega Ribollente"},
        "ca_butcher_cleaver_cursed": {"en": "Cursed Butcher Cleaver", "it": "Mannaia da Macellaio Maledetta"},
        "ca_tarot_card_death": {"en": "Death Tarot Card", "it": "Carta dei Tarocchi della Morte"},
        "ca_tombstone_rip_mossy": {"en": "Mossy RIP Tombstone", "it": "Lapide Muschiata"}
    }

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

    logging.info("Elaborazione completata. 16 nuovi oggetti HORROR aggiunti al catalogo.")

if __name__ == "__main__":
    process_grid()
