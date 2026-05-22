"""
tools/normalize_catalog.py

Normalizza tag e categorie nei cataloghi oggetti del progetto.

Cosa fa (idempotente):
  1. Lowercase + snake_case di ogni tag in `tags` (es. "NATURA" -> "natura",
     "Anni 60" -> "anni_60").
  2. Dedup dei tag all'interno di ogni oggetto (preservando l'ordine).
  3. Rimuove stringhe vuote, spazi extra.
  4. Normalizza anche le chiavi di tags_taxonomy.json.

NON modifica:
  - id, label_key, icon, style, default_*
  - le immagini su filesystem
  - i file strings/*.json (mai toccati: nessuna ricaduta sulla localizzazione)

Sicurezza:
  - DRY RUN di default: stampa il diff senza modificare nulla.
  - Solo con --apply scrive i file (atomic via engine.utils.safe_write_json).
  - Crea un backup `<file>.bak.YYYYMMDD_HHMMSS` accanto a ogni file modificato.

Uso:
  python tools/normalize_catalog.py                 # dry-run, mostra diff
  python tools/normalize_catalog.py --apply         # applica modifiche
  python tools/normalize_catalog.py --path FILE     # solo un file specifico
"""

from __future__ import annotations

import argparse
import datetime
import json
import re
import shutil
import sys
from pathlib import Path
from typing import Iterable

# Permetti l'esecuzione sia da root che da tools/
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.utils import safe_write_json  # noqa: E402


# ---------------------------------------------------------------------------
# Normalizzazione tag
# ---------------------------------------------------------------------------

_INVALID_CHARS = re.compile(r"[^a-z0-9_]+")


def normalize_tag(tag: str) -> str:
    """
    Normalizza un singolo tag:
      - strip whitespace
      - lowercase
      - sostituisce caratteri non [a-z0-9_] con '_'
      - collassa più '_' consecutivi
      - rimuove '_' iniziali/finali
    """
    if not isinstance(tag, str):
        return ""
    t = tag.strip().lower()
    # Sostituisci tutto ciò che non è a-z0-9_ con _
    t = _INVALID_CHARS.sub("_", t)
    # Collassa _ multipli
    t = re.sub(r"_+", "_", t)
    return t.strip("_")


def normalize_tags(tags: Iterable[str]) -> tuple[list[str], bool]:
    """
    Normalizza una lista di tag preservando l'ordine e deduplicando.
    Returns (new_list, changed).
    """
    if not isinstance(tags, list):
        return [], False
    seen: set[str] = set()
    out: list[str] = []
    for raw in tags:
        norm = normalize_tag(raw)
        if not norm or norm in seen:
            continue
        seen.add(norm)
        out.append(norm)
    return out, out != list(tags)


# ---------------------------------------------------------------------------
# Processing dei file
# ---------------------------------------------------------------------------

def process_catalog_file(path: Path) -> tuple[dict | None, dict]:
    """
    Returns (new_data, stats). new_data=None se nessuna modifica.
    Stats: tag_changed, obj_changed, dup_removed.
    """
    stats = {"obj_total": 0, "obj_changed": 0, "tag_changed": 0, "dup_removed": 0}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[ERROR] Impossibile leggere {path}: {e}", file=sys.stderr)
        return None, stats

    objects = data.get("objects", [])
    if not isinstance(objects, list):
        return None, stats

    changed_any = False
    for obj in objects:
        stats["obj_total"] += 1
        tags = obj.get("tags", [])
        new_tags, changed = normalize_tags(tags)
        if changed:
            stats["obj_changed"] += 1
            stats["tag_changed"] += abs(len(new_tags) - len(tags))
            stats["dup_removed"] += max(0, len(tags) - len(set(normalize_tag(t) for t in tags if t)))
            obj["tags"] = new_tags
            changed_any = True

    if not changed_any:
        return None, stats
    return data, stats


def process_taxonomy_file(path: Path) -> tuple[dict | None, dict]:
    """Normalizza le CHIAVI di taxonomy.tags (lowercase snake_case)."""
    stats = {"tag_total": 0, "key_changed": 0, "merged": 0}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[ERROR] Impossibile leggere {path}: {e}", file=sys.stderr)
        return None, stats

    tags = data.get("tags", {})
    if not isinstance(tags, dict):
        return None, stats

    new_tags: dict[str, dict] = {}
    for key, defn in tags.items():
        stats["tag_total"] += 1
        norm = normalize_tag(key)
        if not norm:
            continue
        if norm != key:
            stats["key_changed"] += 1
        if norm in new_tags:
            # Conflitto post-normalizzazione: tieni la definizione che ha più campi
            existing = new_tags[norm]
            merged = {**defn, **{k: v for k, v in existing.items() if v}}
            new_tags[norm] = merged
            stats["merged"] += 1
        else:
            new_tags[norm] = defn

    if new_tags == tags:
        return None, stats
    data["tags"] = dict(sorted(new_tags.items()))
    return data, stats


# ---------------------------------------------------------------------------
# Backup + write
# ---------------------------------------------------------------------------

def backup_file(path: Path) -> Path:
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    bak = path.with_suffix(path.suffix + f".bak.{ts}")
    shutil.copy2(path, bak)
    return bak


# ---------------------------------------------------------------------------
# Discovery file da processare
# ---------------------------------------------------------------------------

def discover_catalogs(root: Path) -> list[Path]:
    paths: list[Path] = []
    # Cataloghi globali
    for p in (root / "engine" / "data").glob("global_*_catalog.json"):
        if "backup" in p.name.lower() or p.suffix == ".bak":
            continue
        paths.append(p)
    # Cataloghi per gioco
    games_dir = root / "games"
    if games_dir.exists():
        for g in games_dir.iterdir():
            if g.is_dir():
                p = g / "objects_catalog.json"
                if p.exists():
                    paths.append(p)
    return paths


def discover_taxonomies(root: Path) -> list[Path]:
    paths: list[Path] = []
    p = root / "engine" / "data" / "tags_taxonomy.json"
    if p.exists():
        paths.append(p)
    return paths


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true",
                    help="Scrive le modifiche su disco. Senza questo flag, solo dry-run.")
    ap.add_argument("--path", type=str, default=None,
                    help="Processa solo questo file (assoluto o relativo a root).")
    ap.add_argument("--no-backup", action="store_true",
                    help="Non creare backup .bak.* (sconsigliato).")
    args = ap.parse_args()

    root = ROOT
    if args.path:
        target = (Path(args.path) if Path(args.path).is_absolute() else root / args.path).resolve()
        if not target.exists():
            print(f"[ERROR] File non esistente: {target}", file=sys.stderr)
            return 2
        if target.name == "tags_taxonomy.json":
            catalogs, taxonomies = [], [target]
        else:
            catalogs, taxonomies = [target], []
    else:
        catalogs = discover_catalogs(root)
        taxonomies = discover_taxonomies(root)

    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"=== normalize_catalog [{mode}] ===")
    print(f"Cataloghi: {len(catalogs)}, Taxonomy: {len(taxonomies)}\n")

    total_changed = 0

    for p in catalogs:
        new_data, stats = process_catalog_file(p)
        rel = p.relative_to(root) if p.is_relative_to(root) else p
        if new_data is None:
            print(f"  [OK ] {rel}  (nessuna modifica, {stats['obj_total']} oggetti)")
            continue
        total_changed += 1
        print(f"  [MOD] {rel}: obj_modificati={stats['obj_changed']}/{stats['obj_total']} "
              f"tag_normalizzati={stats['tag_changed']} duplicati_rimossi={stats['dup_removed']}")
        if args.apply:
            if not args.no_backup:
                bak = backup_file(p)
                print(f"        backup -> {bak.name}")
            if safe_write_json(p, new_data, indent=2, ensure_ascii=False):
                print(f"        scritto.")
            else:
                print(f"        ERRORE scrittura {p}", file=sys.stderr)

    for p in taxonomies:
        new_data, stats = process_taxonomy_file(p)
        rel = p.relative_to(root) if p.is_relative_to(root) else p
        if new_data is None:
            print(f"  [OK ] {rel}  (taxonomy normalizzata, {stats['tag_total']} tag)")
            continue
        total_changed += 1
        print(f"  [MOD] {rel}: chiavi_normalizzate={stats['key_changed']} merged={stats['merged']}")
        if args.apply:
            if not args.no_backup:
                bak = backup_file(p)
                print(f"        backup -> {bak.name}")
            if safe_write_json(p, new_data, indent=2, ensure_ascii=False):
                print(f"        scritto.")
            else:
                print(f"        ERRORE scrittura {p}", file=sys.stderr)

    print()
    if total_changed == 0:
        print("Tutto già normalizzato. Niente da fare.")
        return 0

    if args.apply:
        print(f"Modificati {total_changed} file. Backup in <file>.bak.<timestamp>.")
    else:
        print(f"{total_changed} file da modificare. Esegui di nuovo con --apply per applicare.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
