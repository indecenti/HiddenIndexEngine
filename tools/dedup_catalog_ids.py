"""
tools/dedup_catalog_ids.py

Fonde gli ID duplicati nei cataloghi globali in un'unica entry pulita.

Strategia di merge (deterministica e safe):

  1. **Schema cleanup**: scarta campi non standard (es. `radius` invece di
     `default_radius`). I cataloghi seguono lo schema in
     engine/schemas/catalog_schema.json.

  2. **Icon path**: se i duplicati hanno icon diversi, preferisce quello che:
       a) NON contiene il prefisso 'obj_' (bug di refactoring documentato);
       b) corrisponde a un PNG realmente esistente sul filesystem.

  3. **Tags**: unione di tutti i tag dei duplicati, normalizzati + dedup.
     Conserva TUTTE le informazioni — un tag è additivo, mai distruttivo.

  4. **Detection**: se discordante (rect vs circle), tiene la prima occorrenza
     ma logga warning esplicito — è una scelta semantica che merita revisione.

  5. **Numerici** (default_width/height/radius/hint_delay): media arrotondata
     dei valori non-nulli, oppure il primo valido se non ha senso mediare
     (es. detection cambia -> tieni il primo).

  6. **label_key, style, id**: devono essere identici tra duplicati. Se non lo
     sono, è un caso anomalo: log warning + tieni la prima occorrenza.

Sicurezza:
  - DRY-RUN per default. Solo con --apply scrive.
  - Backup atomico via shutil.copy2 + safe_write_json.
  - Report dettagliato per ogni merge effettuato.
  - Verifica che il PNG referenziato dall'icon scelto esista, se non esiste
    fallback al primo path con PNG reale; se nessun PNG esiste, lascia
    il path della prima occorrenza e segnala come PNG_MISSING.

Uso:
    python tools/dedup_catalog_ids.py                # dry-run, report dettagliato
    python tools/dedup_catalog_ids.py --apply
    python tools/dedup_catalog_ids.py --catalog global_real_catalog.json
"""

from __future__ import annotations

import argparse
import datetime
import json
import shutil
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.utils import safe_write_json  # noqa: E402


# Campi ammessi dallo schema catalog_schema.json
ALLOWED_FIELDS: set[str] = {
    "id", "label_key", "icon", "style",
    "default_detection", "default_width", "default_height",
    "default_radius", "default_hint_delay", "tags",
}


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def load_json(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


def discover_global_catalogs(root: Path) -> list[Path]:
    out = []
    for p in sorted((root / "engine" / "data").glob("global_*_catalog.json")):
        if "backup" in p.name.lower() or p.suffix == ".bak":
            continue
        out.append(p)
    return out


def png_exists_anywhere(root: Path, icon: str, games: list[str]) -> bool:
    """Riusa la logica di prune_missing_images: cerca in engine + game folder."""
    if not icon:
        return False
    if (root / "engine" / "assets" / icon).exists():
        return True
    icon_p = Path(icon)
    filename = icon_p.name
    parent = icon_p.parent.name
    for g in games:
        gpath = root / "games" / g
        if not gpath.exists():
            continue
        if (gpath / icon).exists():
            return True
        if parent and (gpath / parent / filename).exists():
            return True
    return False


def discover_games(root: Path) -> list[str]:
    g = root / "games"
    if not g.exists():
        return []
    return sorted(d.name for d in g.iterdir() if d.is_dir() and not d.name.startswith("."))


# ---------------------------------------------------------------------------
# Merge core
# ---------------------------------------------------------------------------

def _clean_entry(obj: dict) -> tuple[dict, list[str]]:
    """
    Rimuove campi non-schema (es. 'radius' invece di 'default_radius').
    Returns (cleaned_entry, dropped_fields).
    """
    dropped = [k for k in obj if k not in ALLOWED_FIELDS]
    cleaned = {k: v for k, v in obj.items() if k in ALLOWED_FIELDS}
    return cleaned, dropped


def _pick_icon(entries: list[dict], root: Path, games: list[str]) -> tuple[str, str]:
    """
    Sceglie il path icon migliore tra i duplicati.
    Priorità:
      1. Path senza prefisso 'obj_' dopo l'ultimo '/' (bug documentato)
      2. Path il cui PNG esiste fisicamente
      3. Primo path non vuoto
    Returns (icon, reason).
    """
    icons = [e.get("icon", "") for e in entries if e.get("icon")]
    if not icons:
        return "", "no_icon"

    # Filtra quelli senza 'obj_' nel filename
    def has_obj_prefix(p: str) -> bool:
        return Path(p).name.startswith("obj_")

    no_prefix = [i for i in icons if not has_obj_prefix(i)]
    candidates = no_prefix if no_prefix else icons

    # Preferisci uno il cui PNG esiste davvero
    real = [i for i in candidates if png_exists_anywhere(root, i, games)]
    if real:
        return real[0], "exists_no_prefix" if no_prefix else "exists"

    # Nessun PNG reale, tieni il primo no-prefix se esiste
    return candidates[0], "no_prefix_no_png" if no_prefix else "first_fallback"


def _merge_tags(entries: list[dict]) -> list[str]:
    """Union di tutti i tag, preservando ordine di prima apparizione."""
    seen: set[str] = set()
    out: list[str] = []
    for e in entries:
        for t in e.get("tags", []) or []:
            if not isinstance(t, str):
                continue
            t = t.strip().lower()
            if t and t not in seen:
                seen.add(t)
                out.append(t)
    return out


def _pick_numeric(entries: list[dict], field: str) -> tuple[Any, str]:
    """
    Per campi numerici (default_width, default_height, default_radius,
    default_hint_delay): media arrotondata dei valori validi, oppure
    primo valido se solo uno è presente.
    """
    vals = [e[field] for e in entries if field in e and isinstance(e[field], (int, float))]
    if not vals:
        return None, "none"
    if len(set(vals)) == 1:
        return vals[0], "identical"
    avg = round(sum(vals) / len(vals))
    return avg, f"averaged({vals}->{avg})"


def _pick_detection(entries: list[dict]) -> tuple[str, str, bool]:
    """
    Per default_detection: se concordano, ok. Se discordano, è un CONFLITTO
    semantico — tiene la prima occorrenza e segnala.
    Returns (detection, reason, conflict).
    """
    dets = [e.get("default_detection") for e in entries if e.get("default_detection")]
    if not dets:
        return "rect", "default_no_match", False
    unique = list(dict.fromkeys(dets))  # preserva ordine
    if len(unique) == 1:
        return unique[0], "agreed", False
    return unique[0], f"CONFLICT({unique})->first", True


def merge_duplicates(entries: list[dict], root: Path, games: list[str]) -> dict:
    """
    Fonde N entry con stesso ID in un'unica entry pulita.
    Returns un dict con la entry mergiata e i metadata di merge.
    """
    # Step 1: clean ogni entry dai campi non-schema
    cleaned: list[dict] = []
    drops: list[list[str]] = []
    for e in entries:
        c, d = _clean_entry(e)
        cleaned.append(c)
        drops.append(d)

    # Step 2: identifica conflitti su campi che devono essere identici
    invariants = {}
    for field in ("id", "label_key", "style"):
        vals = [c[field] for c in cleaned if field in c]
        unique = list(dict.fromkeys(vals))
        if len(unique) > 1:
            invariants[field] = unique  # conflitto
        elif unique:
            invariants[field] = unique[0]

    # Step 3: icon
    icon, icon_reason = _pick_icon(cleaned, root, games)

    # Step 4: detection
    det, det_reason, det_conflict = _pick_detection(cleaned)

    # Step 5: numerici (solo i pertinenti alla detection scelta)
    numeric_fields = []
    if det == "circle":
        numeric_fields = ["default_radius", "default_hint_delay"]
    else:  # rect, poly, mask, ...
        numeric_fields = ["default_width", "default_height", "default_hint_delay"]

    merged: dict = {
        "id": invariants.get("id") if isinstance(invariants.get("id"), str)
              else (invariants.get("id") or [None])[0],
        "label_key": invariants.get("label_key") if isinstance(invariants.get("label_key"), str)
                     else (invariants.get("label_key") or [None])[0],
        "icon": icon,
        "default_detection": det,
        "style": invariants.get("style") if isinstance(invariants.get("style"), str)
                 else (invariants.get("style") or [None])[0],
    }

    numeric_picks: dict[str, str] = {}
    for nf in numeric_fields:
        v, reason = _pick_numeric(cleaned, nf)
        if v is not None:
            merged[nf] = v
        numeric_picks[nf] = reason

    merged["tags"] = _merge_tags(cleaned)

    # Riordina i campi seguendo l'ordine convenzionale dello schema
    field_order = ["id", "label_key", "icon", "default_detection",
                   "default_width", "default_height", "default_radius",
                   "default_hint_delay", "tags", "style"]
    merged_ordered = {k: merged[k] for k in field_order if k in merged}

    return {
        "merged": merged_ordered,
        "icon_reason": icon_reason,
        "detection_reason": det_reason,
        "detection_conflict": det_conflict,
        "numeric_picks": numeric_picks,
        "invariant_conflicts": {k: v for k, v in invariants.items() if isinstance(v, list)},
        "fields_dropped": [d for d in drops if d],
    }


# ---------------------------------------------------------------------------
# Processing
# ---------------------------------------------------------------------------

def process_catalog(cat_path: Path, root: Path, games: list[str]) -> dict:
    data = load_json(cat_path)
    objects = data.get("objects", [])

    # Raggruppa per id mantenendo ordine
    by_id: dict[str, list[tuple[int, dict]]] = defaultdict(list)
    for i, o in enumerate(objects):
        oid = o.get("id")
        if oid:
            by_id[oid].append((i, o))

    dup_groups = {oid: occ for oid, occ in by_id.items() if len(occ) > 1}

    merges: list[dict] = []
    if not dup_groups:
        return {"data": data, "merges": [], "changed": False}

    # Costruisci nuovo array oggetti: per ogni id duplicato, prima occorrenza
    # diventa la mergiata; le altre vengono droppate.
    new_objects: list[dict] = []
    handled: set[str] = set()
    for o in objects:
        oid = o.get("id")
        if oid in dup_groups:
            if oid in handled:
                continue  # skip subsequent dup
            entries = [obj for _, obj in dup_groups[oid]]
            result = merge_duplicates(entries, root, games)
            new_objects.append(result["merged"])
            merges.append({"id": oid, **result, "occurrences": len(entries)})
            handled.add(oid)
        else:
            new_objects.append(o)

    data["objects"] = new_objects
    return {"data": data, "merges": merges, "changed": True}


def backup(p: Path) -> Path:
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    bak = p.with_suffix(p.suffix + f".bak.{ts}")
    shutil.copy2(p, bak)
    return bak


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def print_merge_report(cat_name: str, merges: list[dict]) -> None:
    print(f"\n--- {cat_name}: {len(merges)} ID duplicati da fondere ---")
    for m in merges:
        oid = m["id"]
        merged = m["merged"]
        print(f"\n  [{oid}] ({m['occurrences']} occorrenze -> 1)")
        print(f"    icon:      {merged.get('icon')}  ({m['icon_reason']})")
        det_flag = "  [CONFLICT]" if m["detection_conflict"] else ""
        print(f"    detection: {merged.get('default_detection')}  ({m['detection_reason']}){det_flag}")
        for nf, reason in m["numeric_picks"].items():
            if nf in merged:
                print(f"    {nf}: {merged[nf]}  ({reason})")
        print(f"    tags ({len(merged.get('tags', []))}): {merged.get('tags')}")
        if m["fields_dropped"]:
            print(f"    [WARN] campi non-schema rimossi: {m['fields_dropped']}")
        if m["invariant_conflicts"]:
            print(f"    [WARN] invarianti in conflitto: {m['invariant_conflicts']}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true",
                    help="Applica le modifiche (default: dry-run).")
    ap.add_argument("--catalog", type=str, default=None,
                    help="Solo questo file (es. global_real_catalog.json).")
    ap.add_argument("--no-backup", action="store_true",
                    help="Non creare backup .bak.* (sconsigliato).")
    args = ap.parse_args()

    games = discover_games(ROOT)
    print(f"=== dedup_catalog_ids [{'APPLY' if args.apply else 'DRY-RUN'}] ===")
    print(f"Giochi rilevati: {games}")

    targets: list[Path]
    if args.catalog:
        cp = ROOT / "engine" / "data" / args.catalog
        if not cp.exists():
            print(f"[ERROR] Catalogo non trovato: {cp}", file=sys.stderr)
            return 2
        targets = [cp]
    else:
        targets = discover_global_catalogs(ROOT)

    total_merges = 0
    total_files_changed = 0

    for p in targets:
        result = process_catalog(p, ROOT, games)
        if not result["merges"]:
            continue
        print_merge_report(str(p.relative_to(ROOT)), result["merges"])
        total_merges += len(result["merges"])

        if not args.apply:
            continue

        # Apply
        if not args.no_backup:
            b = backup(p)
            print(f"\n  backup: {b.name}")
        if safe_write_json(p, result["data"], indent=2, ensure_ascii=False):
            print(f"  [OK] scritto {p.relative_to(ROOT)}: -{len(result['merges'])} duplicati")
            total_files_changed += 1
        else:
            print(f"  [ERR] scrittura fallita: {p}", file=sys.stderr)
            return 1

    print("\n" + "=" * 70)
    if total_merges == 0:
        print("Nessun ID duplicato. Niente da fondere.")
    elif args.apply:
        print(f"FATTO: {total_merges} merge applicati su {total_files_changed} file.")
    else:
        print(f"{total_merges} merge da applicare. Esegui di nuovo con --apply.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
