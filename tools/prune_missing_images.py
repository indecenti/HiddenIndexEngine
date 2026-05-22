"""
tools/prune_missing_images.py

Rimuove dal CATALOGO (globale o per-gioco) gli oggetti il cui PNG `icon`
NON esiste in nessuna posizione plausibile del filesystem. Le immagini
RIMANGONO su filesystem — qui si toccano SOLO i JSON di catalogo.

Sicurezza (PRIORITA' #1: non fare danni):

  1. **DRY-RUN per default**. Solo con --apply scrive.
  2. **Verifica triplice** del PNG prima di considerarlo missing:
       - engine/assets/<icon>                     (master globale)
       - games/<game>/<icon>                      (path-as-is nel game folder)
       - games/<game>/<subfolder>/<filename>      (harvested in subfolder)
     Se UNA SOLA delle 3 esiste, l'oggetto è SALVO.
  3. **Protezione scene**: se l'oggetto è referenziato da qualsiasi scena di
     qualsiasi gioco, NON viene rimosso. Viene riportato in modalità "blocked"
     così tu puoi decidere caso per caso.
  4. **Backup automatici**: ogni file modificato viene copiato in
     <file>.bak.<timestamp>.
  5. **Scrittura atomica**: via engine.utils.safe_write_json.

Cosa NON fa (a posta):
  - NON modifica file strings/*.json (no cleanup label_key).
  - NON modifica scene.json (no cleanup ID orfani nelle scene).
  - NON cancella PNG dal filesystem.
  - NON crea immagini placeholder.
  Per il cleanup transitivo dopo la potatura, usa l'editor che ha già la
  logica di `_cleanup_orphaned_assets` e `_audit_translations`.

Uso:
    python tools/prune_missing_images.py                  # dry-run
    python tools/prune_missing_images.py --apply
    python tools/prune_missing_images.py --catalog global_real_catalog.json
    python tools/prune_missing_images.py --game LineVenture
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


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def load_json(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


def discover_games(root: Path) -> list[str]:
    g = root / "games"
    if not g.exists():
        return []
    return sorted(d.name for d in g.iterdir() if d.is_dir() and not d.name.startswith("."))


def discover_global_catalogs(root: Path) -> list[Path]:
    out = []
    for p in sorted((root / "engine" / "data").glob("global_*_catalog.json")):
        if "backup" in p.name.lower() or p.suffix == ".bak":
            continue
        out.append(p)
    return out


def find_icon(root: Path, icon: str, games: list[str]) -> list[Path]:
    """
    Restituisce la lista di PERCORSI dove il PNG esiste realmente.
    Vuoto se non esiste da nessuna parte.

    Verifica:
      1. engine/assets/<icon>
      2. per ogni gioco G:
           games/G/<icon>                            (path completo)
           games/G/<parent_dir(icon)>/<filename>     (subfolder match)
    """
    found: list[Path] = []
    if not icon:
        return found

    # Master engine
    master = root / "engine" / "assets" / icon
    if master.exists():
        found.append(master)

    icon_p = Path(icon)
    filename = icon_p.name
    parent = icon_p.parent.name  # es. 'objects', 'objects_cartoon'

    for g in games:
        gpath = root / "games" / g
        if not gpath.exists():
            continue
        # Path-as-is
        p1 = gpath / icon
        if p1.exists():
            found.append(p1)
            continue  # già provato, non serve testare subfolder
        # Subfolder match: games/G/objects/<filename>
        if parent:
            p2 = gpath / parent / filename
            if p2 != p1 and p2.exists():
                found.append(p2)
    return found


def collect_scene_refs(root: Path, games: list[str]) -> dict[str, list[str]]:
    """
    catalog_id -> lista di "game/level/scene" che lo referenziano.
    Scansiona tutte le scene di tutti i giochi.
    """
    refs: dict[str, list[str]] = {}
    for g in games:
        gpath = root / "games" / g
        if not gpath.exists():
            continue
        for s in gpath.rglob("scene.json"):
            try:
                sd = load_json(s)
            except Exception:
                continue
            rel = str(s.relative_to(root)).replace("\\", "/")
            for o in sd.get("objects", []):
                cid = o.get("catalog_id") or o.get("id")
                if cid:
                    refs.setdefault(cid, []).append(rel)
    return refs


# ---------------------------------------------------------------------------
# Pruning logic
# ---------------------------------------------------------------------------

def analyze_catalog(cat_path: Path, root: Path, games: list[str],
                    scene_refs: dict[str, list[str]]) -> dict:
    """
    Restituisce un'analisi del catalogo:
      - to_remove:  lista di entry SICURE da rimuovere (PNG missing + no scene ref)
      - blocked:    lista di entry che sarebbero da rimuovere MA sono usate in scene
      - kept:       conteggio entry sane
    """
    data = load_json(cat_path)
    objects = data.get("objects", [])
    if not isinstance(objects, list):
        return {"to_remove": [], "blocked": [], "kept": 0, "data": data}

    to_remove: list[dict] = []
    blocked: list[dict] = []
    kept = 0

    for o in objects:
        icon = o.get("icon", "")
        cid = o.get("id", "")
        if not icon:
            kept += 1
            continue
        found = find_icon(root, icon, games)
        if found:
            kept += 1
            continue
        # Missing dovunque. Vedi se usato in qualche scena
        used_by = scene_refs.get(cid, [])
        record = {"id": cid, "icon": icon, "used_by_scenes": used_by}
        if used_by:
            blocked.append(record)
        else:
            to_remove.append(record)

    return {"to_remove": to_remove, "blocked": blocked, "kept": kept, "data": data}


def backup(p: Path) -> Path:
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    bak = p.with_suffix(p.suffix + f".bak.{ts}")
    shutil.copy2(p, bak)
    return bak


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true",
                    help="Applica le modifiche (default: dry-run).")
    ap.add_argument("--catalog", type=str, default=None,
                    help="Solo questo catalogo globale (es. global_real_catalog.json).")
    ap.add_argument("--game", type=str, default=None,
                    help="Solo questo gioco (objects_catalog.json di <game>).")
    ap.add_argument("--no-backup", action="store_true",
                    help="Non creare backup .bak.* (sconsigliato).")
    ap.add_argument("--include-blocked", action="store_true",
                    help="ATTENZIONE: rimuove anche entry referenziate da scene. "
                         "Pericoloso: lascia ID orfani nelle scene.")
    args = ap.parse_args()

    games = discover_games(ROOT)
    print(f"=== prune_missing_images [{'APPLY' if args.apply else 'DRY-RUN'}] ===")
    print(f"Giochi rilevati: {games}\n")
    print("Scansione scene per riferimenti catalog_id...")
    scene_refs = collect_scene_refs(ROOT, games)
    print(f"  -> {len(scene_refs)} catalog_id referenziati nelle scene\n")

    # Discovery dei file da analizzare
    targets: list[Path] = []
    if args.catalog:
        cp = ROOT / "engine" / "data" / args.catalog
        if not cp.exists():
            print(f"[ERROR] Catalogo non trovato: {cp}", file=sys.stderr)
            return 2
        targets.append(cp)
    elif args.game:
        gp = ROOT / "games" / args.game / "objects_catalog.json"
        if not gp.exists():
            print(f"[ERROR] Catalogo gioco non trovato: {gp}", file=sys.stderr)
            return 2
        targets.append(gp)
    else:
        targets = discover_global_catalogs(ROOT)
        for g in games:
            gp = ROOT / "games" / g / "objects_catalog.json"
            if gp.exists():
                targets.append(gp)

    total_removed = 0
    total_blocked = 0

    for p in targets:
        rel = p.relative_to(ROOT)
        print(f"\n--- {rel} ---")
        analysis = analyze_catalog(p, ROOT, games, scene_refs)
        tr = analysis["to_remove"]
        bk = analysis["blocked"]
        kept = analysis["kept"]
        print(f"  oggetti sani: {kept}")
        print(f"  candidati SICURI da rimuovere (PNG missing + no scene ref): {len(tr)}")
        print(f"  BLOCCATI (PNG missing ma usato da scene): {len(bk)}")

        if tr:
            print(f"\n  esempi da rimuovere (primi 8):")
            for r in tr[:8]:
                print(f"    - {r['id']:<40s}  icon={r['icon']}")
            if len(tr) > 8:
                print(f"    ... e altri {len(tr) - 8}")

        if bk:
            print(f"\n  BLOCCATI (NON rimossi automaticamente, usati in scena):")
            for r in bk[:10]:
                scenes = r["used_by_scenes"]
                print(f"    - {r['id']:<40s}  icon={r['icon']}")
                for s in scenes[:3]:
                    print(f"        usato in: {s}")
                if len(scenes) > 3:
                    print(f"        ... e altre {len(scenes) - 3} scene")
            if len(bk) > 10:
                print(f"    ... e altri {len(bk) - 10} bloccati")

        # Decide cosa rimuovere
        ids_to_remove = {r["id"] for r in tr}
        if args.include_blocked:
            print(f"\n  [WARN] --include-blocked attivo: aggiungo {len(bk)} entry bloccate")
            ids_to_remove |= {r["id"] for r in bk}

        if not ids_to_remove:
            print(f"  nessuna modifica necessaria.")
            total_blocked += len(bk)
            continue

        # Filtra in memoria
        data = analysis["data"]
        new_objs = [o for o in data["objects"] if o.get("id") not in ids_to_remove]
        removed_n = len(data["objects"]) - len(new_objs)
        data["objects"] = new_objs

        total_removed += removed_n
        total_blocked += len(bk)

        if not args.apply:
            print(f"  [DRY-RUN] rimuoverei {removed_n} entry. Esegui --apply per applicare.")
            continue

        if not args.no_backup:
            b = backup(p)
            print(f"  backup: {b.name}")

        if safe_write_json(p, data, indent=2, ensure_ascii=False):
            print(f"  [OK] scritto {p.relative_to(ROOT)}: rimosse {removed_n} entry")
        else:
            print(f"  [ERR] scrittura fallita: {p}", file=sys.stderr)
            return 1

    print("\n" + "=" * 70)
    print(f"Riepilogo: {total_removed} entry {'rimosse' if args.apply else 'da rimuovere'}, "
          f"{total_blocked} bloccate (usate in scene).")
    if not args.apply and total_removed > 0:
        print("Esegui di nuovo con --apply per applicare.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
