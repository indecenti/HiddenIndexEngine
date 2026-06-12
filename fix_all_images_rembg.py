import os
import rembg
from PIL import Image
from pathlib import Path

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
            obj_id = objects_list[idx]
            
            final_path = str(engine_assets_dir / f"{obj_id}.png")
            
            # Perfect background removal using AI (rembg)
            out = rembg.remove(cell_img)
            out.save(final_path)
            print(f"Processed: {obj_id}")
            idx += 1

def main():
    engine_assets_dir = Path(r"g:\HIE git\engine\assets\objects_cartoon")
    
    # Grid 1
    img1 = r"C:\Users\indecenti\.gemini\antigravity\brain\54e1b99a-4397-4fea-b7bb-124218366c1c\cartoon_objects_grid_1781213358500.png"
    objs1 = [
        "ca_magic_potion_blue", "ca_cyberpunk_goggles", "ca_steampunk_pocket_watch", "ca_alien_blaster_toy",
        "ca_viking_drinking_horn", "ca_ninja_shuriken_gold", "ca_pirate_treasure_map_rolled", "ca_retro_cassette_tape_pink",
        "ca_crystal_ball_glowing", "ca_dragon_egg_purple", "ca_robot_dog_toy", "ca_voodoo_doll_patched",
        "ca_wizard_spellbook_ancient", "ca_ufo_mini_model", "ca_excalibur_sword_stone", "ca_magic_lamp_genie"
    ]
    
    # Grid 2
    img2 = r"C:\Users\indecenti\.gemini\antigravity\brain\54e1b99a-4397-4fea-b7bb-124218366c1c\weird_cartoon_objects_grid_1781214577314.png"
    objs2 = [
        "ca_plunger_red", "ca_rubber_chicken_toy", "ca_garden_gnome_classic", "ca_pinata_donkey",
        "ca_hula_hoop_stripes", "ca_whoopee_cushion_pink", "ca_cactus_potted_prickly", "ca_chainsaw_lumberjack",
        "ca_horseshoe_lucky", "ca_mousetrap_cheese", "ca_sombrero_colorful", "ca_origami_crane_paper",
        "ca_matryoshka_doll_red", "ca_flyswatter_green", "ca_dentures_chattering", "ca_fez_hat_tassel"
    ]
    
    # Grid 3
    img3 = r"C:\Users\indecenti\.gemini\antigravity\brain\54e1b99a-4397-4fea-b7bb-124218366c1c\weird_cartoon_objects_grid_3_1781214867423.png"
    objs3 = [
        "ca_cotton_candy_pink", "ca_saxophone_golden", "ca_gargoyle_stone_statue", "ca_pogo_stick_red",
        "ca_clown_wig_rainbow", "ca_dreamcatcher_feathers", "ca_waffle_iron_open", "ca_stoplight_red",
        "ca_kaleidoscope_toy", "ca_bagpipes_tartan", "ca_unicycle_red", "ca_slingshot_wooden",
        "ca_metronome_wooden", "ca_maracas_colorful", "ca_ouija_board_planchette", "ca_disco_ball_shiny"
    ]
    
    # Grid 4
    img4 = r"C:\Users\indecenti\.gemini\antigravity\brain\54e1b99a-4397-4fea-b7bb-124218366c1c\weird_cartoon_objects_grid_5_1781215765715.png"
    objs4 = [
        "ca_tuba_brass", "ca_ukulele_wooden", "ca_castanets_wooden", "ca_stilts_wooden",
        "ca_cleaver_butcher", "ca_mortar_and_pestle_stone", "ca_whisk_metal", "ca_pommel_horse_gymnastics",
        "ca_trampoline_round", "ca_monocle_golden", "ca_ocarina_blue", "ca_obelisk_stone",
        "ca_sarcophagus_golden", "ca_nunchaku_wooden", "ca_hoverboard_electric", "ca_plasma_globe_electric"
    ]
    
    print("Processing Grid 1...")
    process_grid(img1, objs1, engine_assets_dir)
    print("Processing Grid 2...")
    process_grid(img2, objs2, engine_assets_dir)
    print("Processing Grid 3...")
    process_grid(img3, objs3, engine_assets_dir)
    print("Processing Grid 4...")
    process_grid(img4, objs4, engine_assets_dir)
    
    print("All 64 objects perfectly isolated using AI!")

if __name__ == "__main__":
    main()
