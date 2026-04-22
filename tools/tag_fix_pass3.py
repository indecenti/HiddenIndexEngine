#!/usr/bin/env python3
"""
tag_fix_pass3.py — Terza passata: correzione errori logici di categorizzazione.

Uso: python -X utf8 tools/tag_fix_pass3.py [--dry-run]
"""

import json, shutil, argparse
from pathlib import Path
from datetime import datetime
from collections import defaultdict

CATALOG_PATH = Path(__file__).parent.parent / "engine" / "data" / "global_objects_catalog.json"

# ─────────────────────────────────────────────────────────────────────────────
# FIX GLOBALI PER OGGETTO: (id, tags_da_aggiungere, tags_da_rimuovere)
# ─────────────────────────────────────────────────────────────────────────────
FIXES = [

    # ── 1. VIDEOGAME MANCANTE ──────────────────────────────────────────────
    # Tetramini (da Tetris = videogame)
    ("obj_tetrimino_i",          ["videogame"], []),
    ("obj_tetrimino_o",          ["videogame"], []),
    ("obj_tetrimino_t",          ["videogame"], []),
    ("obj_tetrimino_s",          ["videogame"], []),
    ("obj_tetrimino_z",          ["videogame"], []),
    ("obj_tetrimino_j",          ["videogame"], []),
    ("obj_tetrimino_l",          ["videogame"], []),
    ("obj_tetrimino_block_red",  ["videogame"], []),
    ("obj_tetrimino_block_cyan", ["videogame"], []),
    # Controller/console senza videogame
    ("ps2_controller",   ["videogame"], []),
    ("gameboy",          ["videogame"], ["vintage"]),   # gameboy = retro, non vintage (pre-1960)
    ("tamagotchi",       ["videogame"], ["vintage"]),   # 1996 = retro, non vintage
    ("console_pin",      ["videogame"], []),
    # Modern console ha VINTAGE per errore (una console moderna non è vintage)
    ("modern_console",     ["videogame"], ["vintage"]),
    ("modern_console_alt", ["videogame"], ["vintage"]),

    # ── 2. ABBIGLIAMENTO SU OGGETTI NON-INDOSSABILI ────────────────────────
    # Annaffiatoio: non è abbigliamento né cibo
    ("watering_can",   ["attrezzo"], ["abbigliamento", "cibo"]),
    # Lampadina rotta: non è abbigliamento né cucina
    ("shattered_bulb", ["luce", "rotto"], ["abbigliamento", "cucina"]),
    # Siringa: non è abbigliamento
    ("old_syringe",    [], ["abbigliamento"]),
    # Tastiere PC: non è abbigliamento
    ("pc_keyboard",     [], ["abbigliamento"]),
    ("pc_keyboard_iso", [], ["abbigliamento"]),
    # Smartwatch: è un accessorio indossabile, non un capo di abbigliamento
    ("smartwatch_tech",     ["accessorio"], ["abbigliamento"]),
    ("smartwatch_tech_iso", ["accessorio"], ["abbigliamento"]),
    # Pipa: non è abbigliamento
    ("smoking_pipe", [], ["abbigliamento"]),
    # Lima per unghie: è attrezzo da bagno, non abbigliamento
    ("nail_file", ["bagno"], ["abbigliamento"]),
    # Specchio trucco: è accessorio/bagno, non abbigliamento
    ("makeup_mirror", ["bagno", "accessorio"], ["abbigliamento"]),
    # Spazzola e pettine: strumenti bagno, non abbigliamento
    ("hair_brush", ["bagno"], ["abbigliamento"]),
    ("hair_comb",  ["bagno"], ["abbigliamento"]),

    # ── 3. CUCINA SU OGGETTI NON DA CUCINA ────────────────────────────────
    # Barattolo con occhi horror: non è cucina (è contenitore horror)
    ("eyeball_jar",   [], ["cucina"]),
    # Pozione magica: non è cucina (è oggetto fantasy)
    ("mana_potion",   [], ["cucina"]),
    # Occhiali da sole: non sono cucina
    ("sunglasses",    [], ["cucina"]),
    # Lampadina normale: non è cucina
    ("light_bulb",    [], ["cucina"]),
    # Mannaia insanguinata arrugginita: horror prop, non cucina
    ("rust_cleaver_blood", [], ["cucina"]),

    # ── 4. ARREDAMENTO SU OGGETTI NON-ARREDI ──────────────────────────────
    # Tablet: non è arredamento
    ("tablet_device",     [], ["arredamento"]),
    ("tablet_device_iso", [], ["arredamento"]),
    # Orologio da polso: non è arredamento (è accessorio)
    ("wristwatch", [], ["arredamento"]),
    # Portable DVD: non è arredamento
    ("portable_dvd", [], ["arredamento"]),
    # Tablet non è arredamento
    ("portable_dvd", ["cinema", "video"], ["arredamento"]),

    # ── 5. biologico SU PACKAGING NON-ORGANICO ────────────────────────────
    # Pacchetti sigarette: sono carta, il tabacco dentro è biologico
    # ma il pacchetto in sé non è un oggetto "biologico"
    ("marlboro_pack",    [], ["biologico"]),
    ("cigarette_pack",   [], ["biologico"]),
    # Bustine snack: materiale principale è la plastica/carta, non il contenuto
    ("chips_bag",    ["plastica"], ["biologico"]),
    ("pretzels_bag", ["plastica"], ["biologico"]),
    # Gomme da masticare: già ha plastica, biologico fuorviante
    ("chewing_gum_pack", [], ["biologico"]),

    # ── 6. TAG CONTRADDITTORI vintage+retro su oggetti anni 70-90 ─────────
    # Cabinati arcade: anni '70-'80 = retro, NON vintage (pre-1960)
    # (rimuoviamo solo vintage, manteniamo retro che è più preciso)
    ("arcade_joystick",           [], ["vintage"]),
    ("gameboy",                   [], []),   # già gestito sopra
    ("tamagotchi",                [], []),   # già gestito sopra
    ("vintage_camcorder_90s",     [], ["vintage"]),  # anni '90 = retro
    ("obj_gramophone_horn",       [], ["retro"]),    # grammofono = pre-1960, solo vintage
    ("obj_accordion_camera",      [], ["retro"]),    # camera fisarmonica anni '30-'50 = solo vintage

    # ── 7. ALTRI ERRORI SPECIFICI ─────────────────────────────────────────
    # Orologio da polso: aggiungere accessorio (già rimosso arredamento sopra)
    ("wristwatch", ["accessorio"], []),
    # Rust cleaver blood: aggiungere horror che manca
    ("rust_cleaver_blood", ["horror", "pericolo"], []),
    # Eyeball jar: NON è cucina, è horror/decorazione
    ("eyeball_jar", ["decorazione"], []),
    # Mana potion: aggiungere decorazione (è un oggetto fantasy decorativo)
    ("mana_potion", ["decorazione"], []),
    # Light bulb: sistemare (rimuovere cucina già fatto sopra)
    ("light_bulb", [], []),
]

# ─────────────────────────────────────────────────────────────────────────────
# FIX PER TUTTE LE ARCADE MACHINES (batch)
# Rimuovere vintage, mantenere retro (arcade = anni '70-'80 = retro non vintage)
# ─────────────────────────────────────────────────────────────────────────────
ARCADE_IDS = [
    "arcade_pong", "arcade_asteroids", "arcade_defender", "arcade_pacman",
    "arcade_space_invaders", "arcade_donkey_kong", "arcade_galaga",
    "arcade_centipede", "arcade_frogger",
    "arcade_pong_front", "arcade_asteroids_front", "arcade_defender_front",
    "arcade_pacman_front", "arcade_space_invaders_front", "arcade_donkey_kong_front",
    "arcade_galaga_front", "arcade_centipede_front", "arcade_frogger_front",
    "marquee_pacman", "marquee_spaceinvaders", "marquee_donkeykong",
    "marquee_galaga", "marquee_streetfighter", "marquee_tetris",
    "marquee_asteroids", "marquee_defender", "marquee_centipede",
    "marquee_pong", "marquee_mspacman", "marquee_frogger", "marquee_digdug",
    "marquee_qbert", "marquee_gyruss", "marquee_zaxxon", "marquee_burgertime",
    "marquee_tron",
]
for aid in ARCADE_IDS:
    FIXES.append((aid, [], ["vintage"]))


def apply_fixes(dry_run: bool = False) -> None:
    with open(CATALOG_PATH, encoding="utf-8") as f:
        data = json.load(f)

    objects = data["objects"]
    obj_map = {o["id"]: o for o in objects}

    # Raggruppa tutti i fix per oggetto
    combined: dict[str, tuple[set, set]] = defaultdict(lambda: (set(), set()))
    for obj_id, add, remove in FIXES:
        combined[obj_id][0].update(add)
        combined[obj_id][1].update(remove)

    changed = []
    for obj_id, (to_add, to_remove) in combined.items():
        obj = obj_map.get(obj_id)
        if not obj:
            print(f"  [WARN] non trovato: {obj_id}")
            continue
        existing = set(obj.get("tags", []))
        new_set = (existing | to_add) - to_remove
        if new_set == existing:
            continue
        new_tags = sorted(new_set)
        added = to_add - existing
        removed = to_remove & existing
        changed.append((obj_id, added, removed, new_tags))
        if not dry_run:
            obj["tags"] = new_tags

    mode = "DRY RUN" if dry_run else "APPLICATO"
    print(f"\n[{mode}] {len(changed)} oggetti modificati\n")

    for obj_id, added, removed, final in changed:
        parts = []
        if added:   parts.append(f"+{sorted(added)}")
        if removed: parts.append(f"-{sorted(removed)}")
        print(f"  [{obj_id}]  {'  '.join(parts)}")
        if not dry_run:
            print(f"    → {final}")

    if not dry_run:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = CATALOG_PATH.with_name(
            f"{CATALOG_PATH.stem}_backup_{ts}{CATALOG_PATH.suffix}"
        )
        shutil.copy2(CATALOG_PATH, backup)
        with open(CATALOG_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"\nBackup: {backup.name}")
        print(f"Salvato: {CATALOG_PATH.name}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    apply_fixes(dry_run=ap.parse_args().dry_run)
