"""
tools/seed_taxonomy_translations.py

Popola la taxonomy multilingua (en/fr/es/de) a partire da un file di
traduzioni semplice. Sicuro: dry-run di default, scrive solo con --apply.

Formato del file di traduzioni (JSON):

    {
      "legno":   { "en": "Wood",  "fr": "Bois",   "es": "Madera", "de": "Holz" },
      "metallo": { "en": "Metal", "fr": "Métal",  "es": "Metal",  "de": "Metall" },
      ...
    }

  - Le chiavi sono i tag-id già presenti in tags_taxonomy.json (lowercase).
  - I campi mancanti per una lingua restano vuoti e usano il fallback IT.
  - Tag inesistenti nel file di traduzioni vengono ignorati (warning).

Uso:
    python tools/seed_taxonomy_translations.py path/to/translations.json
    python tools/seed_taxonomy_translations.py path/to/translations.json --apply

In assenza di un file di traduzioni reale, lo script funziona anche con
--bootstrap che genera un template vuoto da riempire a mano:

    python tools/seed_taxonomy_translations.py --bootstrap > translations.json
"""

from __future__ import annotations

import argparse
import datetime
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.utils import safe_write_json  # noqa: E402

TAXONOMY_PATH = ROOT / "engine" / "data" / "tags_taxonomy.json"
SUPPORTED_LANGS = ("it", "en", "fr", "es", "de")


def load_taxonomy_raw() -> dict:
    if not TAXONOMY_PATH.exists():
        print(f"[ERROR] Taxonomy non trovata: {TAXONOMY_PATH}", file=sys.stderr)
        sys.exit(2)
    return json.loads(TAXONOMY_PATH.read_text(encoding="utf-8"))


def cmd_bootstrap() -> int:
    """Stampa su stdout un template di traduzioni vuoto."""
    raw = load_taxonomy_raw()
    template = {}
    for tid, defn in (raw.get("tags") or {}).items():
        template[tid] = {
            "en": defn.get("en", ""),
            "fr": defn.get("fr", ""),
            "es": defn.get("es", ""),
            "de": defn.get("de", ""),
        }
    print(json.dumps(template, indent=2, ensure_ascii=False, sort_keys=True))
    return 0


def cmd_apply(translations_path: Path, *, apply: bool, no_backup: bool) -> int:
    raw = load_taxonomy_raw()
    tags: dict = raw.get("tags") or {}

    try:
        translations = json.loads(translations_path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[ERROR] Impossibile leggere {translations_path}: {e}", file=sys.stderr)
        return 2

    if not isinstance(translations, dict):
        print(f"[ERROR] {translations_path} non è un dict.", file=sys.stderr)
        return 2

    stats = {"updated": 0, "ignored": 0, "fields_set": 0, "fields_skipped": 0}
    unknown_ids: list[str] = []
    for tid, fields in translations.items():
        if tid not in tags:
            unknown_ids.append(tid)
            stats["ignored"] += 1
            continue
        if not isinstance(fields, dict):
            continue
        entry = tags[tid]
        changed = False
        for lang in ("en", "fr", "es", "de"):
            v = fields.get(lang, "").strip() if isinstance(fields.get(lang), str) else ""
            if not v:
                stats["fields_skipped"] += 1
                continue
            if entry.get(lang) != v:
                entry[lang] = v
                stats["fields_set"] += 1
                changed = True
        if changed:
            stats["updated"] += 1

    if unknown_ids:
        print(f"[WARN] {len(unknown_ids)} tag nel file traduzioni NON sono nella taxonomy:")
        for t in unknown_ids[:10]:
            print(f"  - {t}")
        if len(unknown_ids) > 10:
            print(f"  ... e altri {len(unknown_ids) - 10}")

    print(f"\nstats: updated={stats['updated']} fields_set={stats['fields_set']} "
          f"fields_skipped={stats['fields_skipped']} unknown_ignored={stats['ignored']}")

    if stats["updated"] == 0:
        print("Nessuna modifica.")
        return 0

    if not apply:
        print("\nDRY-RUN: usa --apply per scrivere su disco.")
        return 0

    # Backup
    if not no_backup:
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        bak = TAXONOMY_PATH.with_suffix(f".json.bak.{ts}")
        shutil.copy2(TAXONOMY_PATH, bak)
        print(f"Backup: {bak.name}")

    raw["tags"] = dict(sorted(tags.items()))
    if safe_write_json(TAXONOMY_PATH, raw, indent=2, ensure_ascii=False):
        print(f"Scritto: {TAXONOMY_PATH}")
        return 0
    print(f"[ERROR] safe_write_json fallito per {TAXONOMY_PATH}", file=sys.stderr)
    return 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("translations", nargs="?", type=str,
                    help="File JSON di traduzioni (vedi formato in docstring).")
    ap.add_argument("--apply", action="store_true",
                    help="Applica le modifiche (default: dry-run).")
    ap.add_argument("--no-backup", action="store_true",
                    help="Non creare backup .bak.* (sconsigliato).")
    ap.add_argument("--bootstrap", action="store_true",
                    help="Stampa template di traduzioni vuoto su stdout.")
    args = ap.parse_args()

    if args.bootstrap:
        return cmd_bootstrap()

    if not args.translations:
        ap.print_help()
        return 2

    return cmd_apply(Path(args.translations), apply=args.apply, no_backup=args.no_backup)


if __name__ == "__main__":
    sys.exit(main())
