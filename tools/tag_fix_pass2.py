#!/usr/bin/env python3
"""
tag_fix_pass2.py — Seconda passata: aggiunge tag mancanti agli oggetti sotto-taggati.

Usa: python -X utf8 tools/tag_fix_pass2.py [--dry-run]
"""

import json
import shutil
import argparse
from pathlib import Path
from datetime import datetime

CATALOG_PATH = Path(__file__).parent.parent / "engine" / "data" / "global_objects_catalog.json"

# ─────────────────────────────────────────────────────────────────────────────
# TAG DA AGGIUNGERE PER OGGETTO
# Format: { "object_id": ["tag_da_aggiungere", ...] }
# ─────────────────────────────────────────────────────────────────────────────
ADD_TAGS: dict[str, list[str]] = {

    # ── DIMENSIONE MANCANTE ──────────────────────────────────────────────────
    "precision_caliper":    ["piccolo"],
    "desiderius_cross":     ["medio"],

    # ── UFFICIO/ARTE: strumenti da scrivania ─────────────────────────────────
    "worn_pencil":          ["arte", "ufficio"],
    "dried_marker":         ["arte", "ufficio"],
    "rusted_paperclip":     ["ufficio", "rotto"],
    "rusty_stapler":        ["ufficio", "rotto"],
    "wooden_ruler":         ["ufficio", "attrezzo"],
    "fountain_pen":         ["arte", "ufficio"],
    "old_book":             ["studio"],
    "faded_letter":         ["studio"],
    "stained_papers":       ["studio"],

    # ── OFFICINA/ATTREZZO ────────────────────────────────────────────────────
    "precision_caliper":    ["piccolo", "officina"],
    "rusty_scissors":       ["attrezzo"],
    "straight_razor":       ["bagno", "attrezzo"],
    "vintage_lighter":      ["attrezzo"],
    "matchbox":             ["attrezzo"],
    "eyestalk_compass":     ["attrezzo"],
    "cigar_cutter":         ["attrezzo"],
    "ether_siphon":         ["attrezzo"],
    "dimensional_key":      ["attrezzo"],

    # ── LUCE / DECORAZIONE ───────────────────────────────────────────────────
    "unlit_candle":         ["luce", "decorazione"],
    "ornate_candelabra":    ["luce", "decorazione"],
    "occult_bell":          ["decorazione"],
    "bird_skull":           ["decorazione"],
    "runed_skull":          ["decorazione"],
    "anatomical_heart":     ["decorazione"],
    "mummified_hand":       ["decorazione"],
    "pirate_symbol":        ["decorazione"],
    "anarchy_slab":         ["decorazione"],
    "thorn_crown":          ["decorazione"],
    "om_stone":             ["decorazione"],
    "cthulhu_idol":         ["decorazione", "horror"],
    "ocean_rune_stone":     ["decorazione"],
    "abyssal_crystal":      ["decorazione"],
    "sunken_skull":         ["decorazione"],
    "black_coral":          ["decorazione"],
    "fractal_relic":        ["decorazione"],
    "crystal_anomaly":      ["decorazione"],
    "obj_alien_skull":      ["decorazione"],
    "obj_crystal_eye":      ["decorazione"],
    "obj_runic_cube":       ["decorazione"],
    "obj_meteorite_fragment":["decorazione"],
    "quartz_crystal":       ["decorazione"],
    "fossil_shell":         ["decorazione"],
    "bird_nest":            ["decorazione"],

    # ── SPORT / TROFEI ───────────────────────────────────────────────────────
    "tarnished_trophy":     ["sport", "decorazione", "rotto"],
    "basketball_alt":       ["gomma"],
    "skateboard_alt":       ["legno", "plastica"],
    "electric_guitar_alt":  ["legno", "metallo"],
    "wireless_headphones_alt": ["elettronica", "plastica", "tecnologia"],

    # ── DOMESTICO: varianti mancanti ─────────────────────────────────────────
    "photo_frame_alt":      ["decorazione", "arredamento"],
    "piggy_bank_alt":       ["decorazione", "arredamento", "denaro"],
    "alarm_clock_alt":      ["orologio", "elettronica"],
    "smart_speaker_alt":    ["elettronica", "tecnologia"],

    # ── PULIZIA: materiali mancanti ──────────────────────────────────────────
    "mop":                  ["attrezzo", "legno", "stoffa"],
    "sponge":               ["bagno", "gomma"],

    # ── CIRCO: domini mancanti ───────────────────────────────────────────────
    "clown_nose":           ["abbigliamento"],
    "juggling_club":        ["attrezzo"],
    "circus_ticket":        ["gioco"],
    "golden_bell":          ["decorazione"],
    "tamer_whip":           ["arma", "attrezzo"],
    "unicycle_wheel":       ["veicolo"],
    "magician_wand":        ["attrezzo"],

    # ── CHIAVI: attrezzo mancante ────────────────────────────────────────────
    "ancient_key":          ["attrezzo"],
    "bloody_key":           ["attrezzo"],
    "heart_key":            ["attrezzo"],

    # ── SIMBOLI: accessori/gioielli ──────────────────────────────────────────
    "peace_pendant":        ["accessorio", "gioiello"],
    "yinyang_charm":        ["accessorio", "gioiello"],
    "smiley_pin":           ["accessorio"],

    # ── MEDICO ───────────────────────────────────────────────────────────────
    "stained_gauze":        ["medico", "stoffa"],
    "lacerated_doll_mask":  ["giocattolo"],

    # ── GAS MASK ─────────────────────────────────────────────────────────────
    "obj_gas_mask_retro":   ["medico", "abbigliamento"],

    # ── OUIJA: è un gioco da tavolo ──────────────────────────────────────────
    "ouija_planchette":     ["gioco"],

    # ── VHS TAPE: media ──────────────────────────────────────────────────────
    "vhs_tape":             ["cinema", "dati"],

    # ── MODELLINI: giocattoli da collezione ──────────────────────────────────
    "speedboat_model":      ["giocattolo"],
    "fighter_jet_model":    ["giocattolo"],
    "locomotive_model":     ["giocattolo"],
    "classic_car_model":    ["giocattolo"],
    "sailing_ship_model":   ["giocattolo"],
    "tank_model":           ["giocattolo"],
    "motorcycle_model":     ["giocattolo"],
    "ship_model":           ["giocattolo", "collezione"],
    "excavator_model":      ["giocattolo", "collezione"],

    # ── TABACCO/FUMATORI ─────────────────────────────────────────────────────
    "cuban_cigar":          ["biologico"],
    "marlboro_pack":        ["biologico"],

    # ── HORROR PROPS con materiale mancante ──────────────────────────────────
    "severed_finger":       ["decorazione"],
    "severed_ear":          ["decorazione"],
    "porcelain_mask_shard": ["decorazione"],
    "iron_shackles":        ["arma"],

    # ── NATURA: biologico mancante ───────────────────────────────────────────
    "dried_sage":           ["biologico"],
    "message_bottle":       ["viaggio"],

    # ── OPERA GLASSES: accessorio ────────────────────────────────────────────
    "opera_glasses":        ["accessorio", "attrezzo"],

    # ── DESIDERIUS CROSS: gioiello storico ───────────────────────────────────
    "desiderius_cross":     ["medio", "gioiello", "vintage"],
}


def apply_fixes(dry_run: bool = False) -> None:
    with open(CATALOG_PATH, encoding="utf-8") as f:
        data = json.load(f)

    objects = data["objects"]
    obj_map = {o["id"]: o for o in objects}

    total_added = 0
    changed = []

    for obj_id, tags_to_add in ADD_TAGS.items():
        obj = obj_map.get(obj_id)
        if obj is None:
            print(f"  [WARN] oggetto non trovato: {obj_id}")
            continue

        existing = set(obj.get("tags", []))
        new_tags = [t for t in tags_to_add if t not in existing]
        if not new_tags:
            continue

        changed.append((obj_id, new_tags, sorted(existing | set(new_tags))))
        total_added += len(new_tags)

        if not dry_run:
            obj["tags"] = sorted(existing | set(new_tags))

    if dry_run:
        print(f"DRY RUN — {len(changed)} oggetti modificati, {total_added} tag aggiunti\n")
    else:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = CATALOG_PATH.with_name(f"{CATALOG_PATH.stem}_backup_{ts}{CATALOG_PATH.suffix}")
        shutil.copy2(CATALOG_PATH, backup)
        with open(CATALOG_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"Backup: {backup.name}")
        print(f"Applicati {total_added} tag aggiunti su {len(changed)} oggetti\n")

    for obj_id, added, final_tags in changed:
        print(f"  [{obj_id}]  +{added}  →  {final_tags}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    apply_fixes(dry_run=args.dry_run)
