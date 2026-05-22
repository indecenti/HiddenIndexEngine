"""
tools/audit_catalog.py

Audit dell'integrità referenziale catalogo ↔ scene ↔ asset ↔ traduzioni.

Cosa controlla (read-only, mai modifica nulla):

  [DUPS]   ID duplicati nel catalogo unificato (globale + per-gioco).
  [PNG]    PNG mancanti sul filesystem per gli oggetti del catalogo.
  [ORPHAN] Oggetti referenziati dalle scene con catalog_id non esistente.
  [UNUSED] Oggetti del catalogo mai usati in nessuna scena (info, non errore).
  [I18N]   label_key mancanti in una o più lingue (per ciascun gioco).
  [TAGS]   Tag presenti nei cataloghi ma assenti dalla taxonomy.
  [STYLE]  Stili non riconosciuti.

Exit code:
  0  audit pulito o solo warning informativi
  1  errori bloccanti (ID duplicati, PNG mancanti, ID orfani in scene)

Uso:
  python tools/audit_catalog.py
  python tools/audit_catalog.py --game LineVenture     # solo un gioco
  python tools/audit_catalog.py --json report.json     # output JSON
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


LANGS = ("it", "en", "fr", "es", "de")


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def load_json(p: Path) -> dict:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[ERROR] Impossibile leggere {p}: {e}", file=sys.stderr)
        return {}


def load_global_catalogs(root: Path) -> dict[str, list[dict]]:
    """Mappa nome_file -> lista oggetti. Esclude .bak / *_backup_*."""
    out: dict[str, list[dict]] = {}
    for p in sorted((root / "engine" / "data").glob("global_*_catalog.json")):
        if "backup" in p.name.lower() or p.suffix == ".bak":
            continue
        d = load_json(p)
        out[p.name] = d.get("objects", [])
    return out


def load_game_catalog(root: Path, game_id: str) -> list[dict]:
    p = root / "games" / game_id / "objects_catalog.json"
    if not p.exists():
        return []
    return load_json(p).get("objects", [])


def discover_games(root: Path) -> list[str]:
    games_dir = root / "games"
    if not games_dir.exists():
        return []
    return sorted(d.name for d in games_dir.iterdir() if d.is_dir() and not d.name.startswith("."))


def find_all_scenes(root: Path, game_id: str | None = None) -> list[Path]:
    base = root / "games" if game_id is None else root / "games" / game_id
    if not base.exists():
        return []
    return sorted(base.rglob("scene.json"))


def load_taxonomy(root: Path) -> set[str]:
    p = root / "engine" / "data" / "tags_taxonomy.json"
    if not p.exists():
        return set()
    return set(load_json(p).get("tags", {}).keys())


# ---------------------------------------------------------------------------
# Audit checks
# ---------------------------------------------------------------------------

VALID_STYLES = {"cartoon", "line art", "real"}


def audit_global(root: Path, report: dict) -> None:
    """Audit globale: dup ID cross-file, stili sconosciuti, tag fuori taxonomy."""
    catalogs = load_global_catalogs(root)
    taxonomy = load_taxonomy(root)

    id_seen: dict[str, list[str]] = defaultdict(list)
    style_violations: list[tuple[str, str, str]] = []  # (file, id, style)
    tags_seen_in_catalog: set[str] = set()

    for fname, objs in catalogs.items():
        for o in objs:
            oid = o.get("id")
            if oid:
                id_seen[oid].append(fname)
            style = o.get("style")
            if style and style not in VALID_STYLES:
                style_violations.append((fname, oid or "?", style))
            for t in o.get("tags", []):
                if isinstance(t, str) and t:
                    tags_seen_in_catalog.add(t)

    dup_ids = {k: v for k, v in id_seen.items() if len(v) > 1}
    orphan_tags = tags_seen_in_catalog - taxonomy if taxonomy else set()

    report["global_objects_total"] = sum(len(v) for v in catalogs.values())
    report["global_unique_ids"] = len(id_seen)
    report["dups"] = dup_ids
    report["styles_invalid"] = style_violations
    report["tags_not_in_taxonomy"] = sorted(orphan_tags)
    report["taxonomy_size"] = len(taxonomy)
    report["taxonomy_loaded"] = bool(taxonomy)


def _merged_catalog(root: Path, game_id: str) -> dict[str, dict]:
    """ID -> oggetto. Game catalog sovrascrive globale (come catalog_manager)."""
    merged: dict[str, dict] = {}
    for objs in load_global_catalogs(root).values():
        for o in objs:
            if "id" in o:
                merged[o["id"]] = o
    for o in load_game_catalog(root, game_id):
        if "id" in o:
            merged[o["id"]] = o
    return merged


def audit_game(root: Path, game_id: str, report: dict) -> None:
    catalog = _merged_catalog(root, game_id)
    game_path = root / "games" / game_id

    # 1. PNG mancanti
    missing_pngs: list[tuple[str, str]] = []  # (catalog_id, icon)
    for cid, obj in catalog.items():
        icon = obj.get("icon", "")
        if not icon:
            continue
        # L'icon è relativa a engine/assets/ oppure presente nel game folder
        engine_p = root / "engine" / "assets" / icon
        game_p = game_path / icon
        # Anche solo il nome file dentro game/objects/
        name_in_game = game_path / Path(icon).parent.name / Path(icon).name
        if not (engine_p.exists() or game_p.exists() or name_in_game.exists()):
            missing_pngs.append((cid, icon))

    # 2. ID orfani nelle scene
    orphan_refs: list[tuple[str, str]] = []  # (scene_path, catalog_id)
    used_ids: set[str] = set()
    scenes = find_all_scenes(root, game_id)
    for s in scenes:
        sd = load_json(s)
        for o in sd.get("objects", []):
            cid = o.get("catalog_id") or o.get("id")
            if not cid:
                continue
            used_ids.add(cid)
            if cid not in catalog:
                orphan_refs.append((str(s.relative_to(root)), cid))

    # 3. Oggetti del catalogo mai usati (informativo)
    unused_in_game = sorted(set(catalog.keys()) - used_ids)

    # 4. Label_key mancanti per lingua
    needed_label_keys: set[str] = set()
    for cid in used_ids:
        obj = catalog.get(cid)
        if obj:
            lk = obj.get("label_key") or f"obj_{cid}"
            needed_label_keys.add(lk)

    strings_dir = game_path / "strings"
    missing_by_lang: dict[str, list[str]] = {lang: [] for lang in LANGS}
    if strings_dir.exists():
        for lang in LANGS:
            f = strings_dir / f"{lang}.json"
            data = load_json(f) if f.exists() else {}
            for k in sorted(needed_label_keys):
                if k not in data:
                    missing_by_lang[lang].append(k)

    report["games"][game_id] = {
        "catalog_size":        len(catalog),
        "scenes":              len(scenes),
        "used_catalog_ids":    len(used_ids),
        "missing_pngs":        missing_pngs,
        "orphan_refs":         orphan_refs,
        "unused_in_game":      unused_in_game,
        "missing_label_keys":  {lang: ks for lang, ks in missing_by_lang.items() if ks},
        "needed_label_keys":   len(needed_label_keys),
    }


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def print_report(report: dict) -> int:
    """Stampa report leggibile. Returns exit code."""
    errors = 0

    print("=" * 70)
    print("AUDIT CATALOGO  —  read-only")
    print("=" * 70)

    print(f"\n[GLOBAL] {report['global_objects_total']} oggetti, "
          f"{report['global_unique_ids']} ID unici, "
          f"taxonomy={report['taxonomy_size']} tag "
          f"({'caricata' if report['taxonomy_loaded'] else 'NON TROVATA'})")

    # ID duplicati
    dups = report["dups"]
    if dups:
        errors += len(dups)
        print(f"\n[DUPS] {len(dups)} ID duplicati cross-file:")
        for oid, files in sorted(dups.items()):
            print(f"  - {oid}: presente in {', '.join(files)}")
    else:
        print("\n[DUPS] OK — nessun ID duplicato")

    # Stili invalidi
    sv = report["styles_invalid"]
    if sv:
        print(f"\n[STYLE] {len(sv)} oggetti con stile non riconosciuto:")
        for f, oid, st in sv[:20]:
            print(f"  - {f}::{oid}  style='{st}'")
        if len(sv) > 20:
            print(f"  ... e altri {len(sv) - 20}")
    else:
        print("[STYLE] OK — tutti gli stili validi")

    # Tag fuori taxonomy
    t_orph = report["tags_not_in_taxonomy"]
    if t_orph:
        print(f"\n[TAGS] {len(t_orph)} tag nei cataloghi ma non nella taxonomy:")
        print("  " + ", ".join(t_orph[:30]))
        if len(t_orph) > 30:
            print(f"  ... e altri {len(t_orph) - 30}")
        print("  -> aggiungili a engine/data/tags_taxonomy.json o esegui normalize_catalog")
    else:
        print("[TAGS] OK — tutti i tag sono nella taxonomy")

    # Per gioco
    for gid, g in report["games"].items():
        print("\n" + "-" * 70)
        print(f"GAME: {gid}")
        print(f"  scene={g['scenes']} catalog_size={g['catalog_size']} "
              f"used={g['used_catalog_ids']} needed_label_keys={g['needed_label_keys']}")

        if g["missing_pngs"]:
            errors += len(g["missing_pngs"])
            print(f"  [PNG] {len(g['missing_pngs'])} PNG mancanti sul filesystem:")
            for cid, icon in g["missing_pngs"][:10]:
                print(f"    - {cid}  icon='{icon}'")
            if len(g["missing_pngs"]) > 10:
                print(f"    ... e altri {len(g['missing_pngs']) - 10}")

        if g["orphan_refs"]:
            errors += len(g["orphan_refs"])
            print(f"  [ORPHAN] {len(g['orphan_refs'])} riferimenti scene -> catalog_id inesistente:")
            for spath, cid in g["orphan_refs"][:10]:
                print(f"    - {spath}  cid='{cid}'")
            if len(g["orphan_refs"]) > 10:
                print(f"    ... e altri {len(g['orphan_refs']) - 10}")

        if g["unused_in_game"]:
            print(f"  [UNUSED] {len(g['unused_in_game'])} oggetti nel catalogo mai usati nelle scene "
                  f"(informativo)")

        i18n = g["missing_label_keys"]
        if i18n:
            print(f"  [I18N] label_key mancanti per lingua:")
            for lang, keys in i18n.items():
                print(f"    {lang}: {len(keys)} mancanti  ({', '.join(keys[:5])}"
                      f"{'...' if len(keys) > 5 else ''})")

    print("\n" + "=" * 70)
    if errors == 0:
        print(f"AUDIT OK — nessun errore bloccante.")
        return 0
    print(f"AUDIT KO — {errors} errori bloccanti.")
    return 1


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--game", type=str, default=None,
                    help="Audita solo questo gioco (es. LineVenture).")
    ap.add_argument("--json", type=str, default=None,
                    help="Scrive il report come JSON nel path indicato.")
    args = ap.parse_args()

    root = ROOT
    report: dict = {"games": {}}

    audit_global(root, report)

    games = [args.game] if args.game else discover_games(root)
    for g in games:
        audit_game(root, g, report)

    if args.json:
        out_p = Path(args.json)
        out_p.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=list),
                         encoding="utf-8")
        print(f"Report JSON scritto in {out_p}")

    return print_report(report)


if __name__ == "__main__":
    sys.exit(main())
