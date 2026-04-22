#!/usr/bin/env python3
"""
tag_migrate.py — Migrazione sicura dei tag di global_objects_catalog.json

Uso:
  python tools/tag_migrate.py --dry-run   # mostra differenze senza scrivere
  python tools/tag_migrate.py             # applica le migrazioni e salva backup
  python tools/tag_migrate.py --audit     # genera report post-migrazione
"""

import json
import sys
import shutil
import argparse
from pathlib import Path
from datetime import datetime
from collections import Counter, defaultdict

CATALOG_PATH = Path(__file__).parent.parent / "engine" / "data" / "global_objects_catalog.json"

# ─────────────────────────────────────────────────────────────────────────────
# MAPPA DI MIGRAZIONE: old_tag → new_tag
# None = rimuovi il tag senza sostituto
# ─────────────────────────────────────────────────────────────────────────────
MERGE_MAP: dict[str, str | None] = {

    # ── ENCODING CORROTTO ──────────────────────────────────────────────────
    "casin\ufffd": "casino",

    # ── NORMALIZZAZIONE LINGUA (EN→IT) ─────────────────────────────────────
    "game":   "gioco",
    "nature": "natura",

    # ── SINONIMI ESATTI ─────────────────────────────────────────────────────
    "vestiti":    "abbigliamento",
    "soldi":      "denaro",
    "quotidiano": "giornale",
    "accetta":    "ascia",
    "scrivere":   "scrittura",
    "meccanismo": "meccanico",
    "calza":      "calzino",
    "piuma":      "piume",

    # ── MATERIALI ───────────────────────────────────────────────────────────
    "porcellana": "ceramica",
    "marmo":      "pietra",
    "ferro":      "metallo",   # ferro generico → metallo

    # ── TECH CONSOLIDATION ──────────────────────────────────────────────────
    "tech":           "elettronica",
    "nvidia":         "elettronica",
    "scheda_video":   "elettronica",
    "gpu":            "elettronica",
    "alimentatore":   "elettronica",

    # ── SALUMI → salume ─────────────────────────────────────────────────────
    "prosciutto_cotto": "salume",
    "prosciutto_crudo": "salume",
    "mortadella":       "salume",
    "salame":           "salume",
    "pancetta":         "salume",
    "speck":            "salume",
    "bresaola":         "salume",
    "coppa":            "salume",
    "culatello":        "salume",

    # ── PAESI EUROPEI → europa ──────────────────────────────────────────────
    "italia":    "europa",
    "francia":   "europa",
    "germania":  "europa",
    "spagna":    "europa",
    "uk":        "europa",
    "grecia":    "europa",
    "svizzera":  "europa",
    "svezia":    "europa",

    # ── NATURA ORGANICA → biologico ─────────────────────────────────────────
    "foglia":  "biologico",
    "fungo":   "biologico",
    "seme":    "biologico",
    "pigna":   "biologico",
    "bacche":  "biologico",
    "nido":    "biologico",

    # ── ARTE ────────────────────────────────────────────────────────────────
    "pop_art":    "arte",
    "pennellessa":"pennello",
    "colorato":   "colore",

    # ── CALZATURE → calzatura ───────────────────────────────────────────────
    "scarpa":    "calzatura",
    "stivale":   "calzatura",
    "ciabatta":  "calzatura",
    "pattini":   "calzatura",
    "infradito": "calzatura",
    "pantofola": "calzatura",
    "tacco":     "calzatura",

    # ── CAPPELLI SPECIFICI → cappello ───────────────────────────────────────
    # (cappuccio ESCLUSO: usato per "tappo di penna", non copricapo)
    "fedora":   "cappello",
    "giullare": "cappello",
    "cowboy":   "cappello",
    "pompieri": "cappello",
    "panama":   "cappello",
    "sherlock": "cappello",
    "bombetta": "cappello",
    "polizia":  "cappello",
    "berretto": "cappello",

    # ── ERA ─────────────────────────────────────────────────────────────────
    "2000s": "retro",

    # ── TAG DA RIMUOVERE (None = elimina) ───────────────────────────────────
    "oggetto":   None,   # tag privo di significato, tutto è un oggetto
    "parole":    None,   # troppo vago, già coperto da carta/ufficio/studio
    "culturale": None,   # troppo generico

    # ── STRUMENTI DUPLICATI ─────────────────────────────────────────────────
    "saldatore":  "officina",
    "saldatrice": "officina",
    "trapano":    "officina",
    "pala":       "officina",

    # ── PC GENERICO → elettronica ───────────────────────────────────────────
    "pc": "elettronica",
}

# ─────────────────────────────────────────────────────────────────────────────
# FIX PER-OGGETTO: tag da rimuovere da oggetti specifici
# { object_id: [tag_da_rimuovere, ...] }
# ─────────────────────────────────────────────────────────────────────────────
OBJECT_TAG_REMOVALS: dict[str, list[str]] = {
    # tecnologia su armi/utensili non-elettronici è chiaramente errato
    "ritual_dagger": ["tecnologia"],
    "chef_knife":    ["tecnologia"],
    "cleaver":       ["tecnologia"],
    "pipe_wrench":   ["tecnologia"],
    "hammer":        ["tecnologia"],

    # pelle è ridondante su oggetti che hanno già cuoio
    "horse_saddle":        ["pelle"],
    "whip_rolled":         ["pelle"],
    "obj_business_briefcase": ["pelle"],
}


# ─────────────────────────────────────────────────────────────────────────────
def load_catalog(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_catalog(data: dict, path: Path) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def make_backup(path: Path) -> Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = path.with_name(f"{path.stem}_backup_{ts}{path.suffix}")
    shutil.copy2(path, backup)
    return backup


def migrate_tags(tags: list[str], obj_id: str) -> tuple[list[str], list[str]]:
    """Applica merge map + per-object removals. Ritorna (new_tags, change_log)."""
    changes = []
    result = []
    seen = set()

    per_obj_remove = set(OBJECT_TAG_REMOVALS.get(obj_id, []))

    for tag in tags:
        # rimozione per-oggetto
        if tag in per_obj_remove:
            changes.append(f"REMOVE[per-obj] {tag!r}")
            continue

        # merge map
        if tag in MERGE_MAP:
            new = MERGE_MAP[tag]
            if new is None:
                changes.append(f"REMOVE {tag!r}")
                continue
            if new != tag:
                changes.append(f"RENAME {tag!r} → {new!r}")
            tag = new

        # deduplicazione
        if tag in seen:
            changes.append(f"DEDUP {tag!r}")
            continue

        seen.add(tag)
        result.append(tag)

    return result, changes


def run_migration(dry_run: bool = False) -> dict:
    data = load_catalog(CATALOG_PATH)
    objects = data["objects"]

    stats = {
        "objects_changed": 0,
        "tag_renames": Counter(),
        "tag_removals": Counter(),
        "tag_dedups": 0,
        "change_log": [],
    }

    for obj in objects:
        original_tags = obj.get("tags", [])
        new_tags, changes = migrate_tags(original_tags, obj["id"])

        if changes:
            stats["objects_changed"] += 1
            stats["change_log"].append({
                "id": obj["id"],
                "before": original_tags,
                "after": new_tags,
                "changes": changes,
            })
            for c in changes:
                if c.startswith("RENAME"):
                    _, rest = c.split(" ", 1)
                    stats["tag_renames"][rest] += 1
                elif c.startswith("REMOVE"):
                    stats["tag_removals"][c] += 1
                elif c.startswith("DEDUP"):
                    stats["tag_dedups"] += 1

            if not dry_run:
                obj["tags"] = sorted(new_tags)

    if not dry_run:
        backup = make_backup(CATALOG_PATH)
        save_catalog(data, CATALOG_PATH)
        print(f"✓ Backup salvato: {backup.name}")
        print(f"✓ Catalogo aggiornato: {CATALOG_PATH.name}")
    else:
        print("─── DRY RUN ─── (nessun file modificato)\n")

    return stats


def print_stats(stats: dict, verbose: bool = False) -> None:
    print(f"\n{'═'*60}")
    print(f"  Oggetti modificati : {stats['objects_changed']}")
    print(f"  Tag rinominati     : {sum(stats['tag_renames'].values())}")
    print(f"  Tag rimossi        : {sum(stats['tag_removals'].values())}")
    print(f"  Duplicati rimossi  : {stats['tag_dedups']}")
    print(f"{'═'*60}\n")

    if stats["tag_renames"]:
        print("Rinominazioni più frequenti:")
        for rename, count in stats["tag_renames"].most_common(20):
            print(f"  {count:4d}×  {rename}")

    if verbose and stats["change_log"]:
        print("\nDettaglio per oggetto:")
        for entry in stats["change_log"]:
            print(f"\n  [{entry['id']}]")
            print(f"    PRIMA:  {entry['before']}")
            print(f"    DOPO:   {entry['after']}")
            for c in entry["changes"]:
                print(f"    → {c}")


def run_audit(data: dict | None = None) -> None:
    """Analisi del catalogo post-migrazione: trova problemi residui."""
    if data is None:
        data = load_catalog(CATALOG_PATH)

    objects = data["objects"]
    all_tags = []
    for obj in objects:
        all_tags.extend(obj.get("tags", []))

    tag_counts = Counter(all_tags)
    unique = len(tag_counts)
    total = len(all_tags)

    print(f"\n{'═'*60}")
    print(f"  Oggetti nel catalogo : {len(objects)}")
    print(f"  Tag totali istanze   : {total}")
    print(f"  Tag unici            : {unique}")
    print(f"  Media tag/oggetto    : {total/len(objects):.2f}")
    print(f"{'═'*60}\n")

    # Tag usati una sola volta (candidati alla rimozione/merge)
    singletons = [t for t, c in tag_counts.items() if c == 1]
    print(f"Tag usati 1 sola volta ({len(singletons)}) → candidati a merge o rimozione:")
    for t in sorted(singletons):
        objs = [o["id"] for o in objects if t in o.get("tags", [])]
        print(f"  {t!r:30s}  → {objs}")

    print()
    doublets = [t for t, c in tag_counts.items() if c == 2]
    print(f"Tag usati 2 volte ({len(doublets)}) → verificare se vanno consolidati:")
    for t in sorted(doublets):
        objs = [o["id"] for o in objects if t in o.get("tags", [])]
        print(f"  {t!r:30s}  → {objs}")

    # Oggetti con troppo pochi o troppi tag
    print()
    sparse = [(o["id"], len(o.get("tags", []))) for o in objects if len(o.get("tags", [])) <= 1]
    if sparse:
        print(f"Oggetti con ≤1 tag ({len(sparse)}) → probabilmente sotto-taggati:")
        for oid, cnt in sparse:
            obj = next(o for o in objects if o["id"] == oid)
            print(f"  {oid:40s} tags={obj.get('tags', [])}")

    fat = [(o["id"], len(o.get("tags", []))) for o in objects if len(o.get("tags", [])) >= 10]
    if fat:
        print(f"\nOggetti con ≥10 tag ({len(fat)}) → verificare se coerenti:")
        for oid, cnt in fat:
            obj = next(o for o in objects if o["id"] == oid)
            print(f"  {oid:40s} ({cnt}) tags={obj.get('tags', [])}")


def main():
    parser = argparse.ArgumentParser(description="Migrazione tag catalogo oggetti")
    parser.add_argument("--dry-run", action="store_true", help="Mostra diff senza scrivere")
    parser.add_argument("--audit",   action="store_true", help="Analisi post-migrazione")
    parser.add_argument("--verbose", action="store_true", help="Dettaglio per oggetto")
    args = parser.parse_args()

    if args.audit:
        run_audit()
        return

    stats = run_migration(dry_run=args.dry_run)
    print_stats(stats, verbose=args.verbose)

    if not args.dry_run:
        print("Analisi residuale post-migrazione:")
        run_audit()


if __name__ == "__main__":
    main()
