"""Anteprima REALE dell'auto-scatter su una scena: piazza oggetti del vero
catalogo del gioco e li disegna come in game (icona PNG, scala, rotazione,
flip, alpha, color_filter moltiplicativo) + metriche di dispersione.

Uso:
    python tools/preview_scatter_real.py --scene games/LineVenture/levels/One/scene_nuova
    python tools/preview_scatter_real.py --scene <dir> --style cartoon --count 80 \
        --difficulty hard --seed 7 --tier auto --out scratch/scatter_real.png

Note:
  - --scene: directory della scena (scene.json + background). Il catalogo e' il
    merge globale+locale del gioco (engine.catalog_manager).
  - Se esiste <scene>/scatter_forbidden.json (brush zone vietate dell'editor)
    viene caricato e unito ai volti auto-rilevati.
  - --tier 0 = classic (default, veloce); "auto" usa il miglior modello ONNX
    disponibile su disco.
  - Metriche: istogramma per macro-zona 4x3 e "coppie ammassate" (distanza
    centri < 45% della taglia media della coppia) — la metrica anti-pile v3.1.
"""
import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
import argparse
import json
import logging
import sys
from pathlib import Path

import numpy as np
import pygame

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from editor.tools import scatter_engine as se
from editor.tools.scatter_engine import build_forbidden_mask, place_objects

log = logging.getLogger("preview_scatter_real")

# Soglia della metrica "coppie ammassate": distanza centri sotto questa
# frazione della taglia media della coppia = oggetti impilati.
CROWDED_PAIR_DIST_FRAC = 0.45


def load_scene(scene_dir: Path) -> tuple[dict, str, Path]:
    """Ritorna (scene_data, game_id, bg_path)."""
    sd = json.loads((scene_dir / "scene.json").read_text(encoding="utf-8"))
    # game_id = componente subito sotto "games/"
    parts = scene_dir.resolve().parts
    game_id = parts[parts.index("games") + 1]
    bg_path = scene_dir / sd.get("background", "background.png")
    return sd, game_id, bg_path


def load_game_catalog(game_id: str) -> list[dict]:
    """Catalogo unito globale+locale del gioco (stessa via dell'editor)."""
    from engine.catalog_manager import load_catalog
    return load_catalog(game_id).get("objects", [])


def load_manual_forbidden(scene_dir: Path) -> set[tuple[int, int]]:
    """Celle vietate dipinte a mano nell'editor (scatter_forbidden.json)."""
    fp = scene_dir / "scatter_forbidden.json"
    if not fp.exists():
        return set()
    try:
        data = json.loads(fp.read_text(encoding="utf-8"))
        return {(int(c[0]), int(c[1])) for c in data.get("cells", [])
                if isinstance(c, (list, tuple)) and len(c) == 2}
    except Exception as e:
        log.warning(f"scatter_forbidden.json illeggibile: {e}")
        return set()


def resolve_icon(icon_rel: str, game_path: Path, repo_root: Path) -> Path | None:
    """Risoluzione icona come da convenzione: games/<id>/<icon> poi engine/assets/<icon>."""
    if not icon_rel:
        return None
    for cand in (game_path / icon_rel, repo_root / "engine" / "assets" / icon_rel):
        if cand.exists():
            return cand
    return None


def render_placed_real(canvas: pygame.Surface, placed, entries: dict,
                       game_path: Path, repo_root: Path) -> int:
    """Disegna i piazzati con la pipeline visiva del gioco. Ritorna n disegnati."""
    drawn = 0
    icon_cache: dict[str, pygame.Surface] = {}
    for p in placed:
        entry = entries.get(p.catalog_id)
        if not entry:
            continue
        icon_rel = entry.get("icon", "")
        base = icon_cache.get(icon_rel)
        if base is None:
            ip = resolve_icon(icon_rel, game_path, repo_root)
            if ip is None:
                log.warning(f"icona mancante per '{p.catalog_id}': {icon_rel}")
                continue
            base = pygame.image.load(str(ip)).convert_alpha()
            icon_cache[icon_rel] = base
        w = max(1, int(round(p.width * p.scale)))
        h = max(1, int(round(p.height * p.scale)))
        img = pygame.transform.smoothscale(base, (w, h))
        if p.flip_x or p.flip_y:
            img = pygame.transform.flip(img, p.flip_x, p.flip_y)
        # Filtro colore: multiply RGBA, come engine/core.py (render oggetti)
        if tuple(p.color_filter) != (255, 255, 255):
            tint = pygame.Surface(img.get_size(), pygame.SRCALPHA)
            tint.fill((*p.color_filter, 255))
            img.blit(tint, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        if p.rotation:
            img = pygame.transform.rotozoom(img, -p.rotation, 1.0)
        if p.alpha < 255:
            img.set_alpha(int(p.alpha))
        if p.detection_type == "circle":
            cx, cy = p.x, p.y
        else:
            cx = p.x + p.width * p.scale / 2
            cy = p.y + p.height * p.scale / 2
        canvas.blit(img, img.get_rect(center=(int(cx), int(cy))))
        drawn += 1
    return drawn


def print_metrics(placed, bg, count: int) -> None:
    if not placed:
        log.warning("zero oggetti piazzati")
        return
    cts = []
    for p in placed:
        w = p.width * p.scale
        h = p.height * p.scale
        cx = p.x + (w / 2 if p.detection_type != "circle" else 0)
        cy = p.y + (h / 2 if p.detection_type != "circle" else 0)
        cts.append((cx, cy, max(w, h)))
    zc = np.zeros((3, 4), dtype=int)
    for cx, cy, _ in cts:
        zx = min(3, int(cx / bg.bg_w * 4))
        zy = min(2, int(cy / bg.bg_h * 3))
        zc[zy, zx] += 1
    crowded = 0
    for i in range(len(cts)):
        for j in range(i + 1, len(cts)):
            d = ((cts[i][0] - cts[j][0]) ** 2 + (cts[i][1] - cts[j][1]) ** 2) ** 0.5
            if d < CROWDED_PAIR_DIST_FRAC * (cts[i][2] + cts[j][2]) / 2:
                crowded += 1
    log.info(f"piazzati {len(placed)}/{count} | zona max/mediana: "
             f"{zc.max()}/{np.median(zc):.1f}")
    log.info(f"istogramma zone 4x3:\n{zc}")
    log.info(f"coppie ammassate (d < {CROWDED_PAIR_DIST_FRAC:.0%} taglia): {crowded}")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description="Anteprima scatter con oggetti reali")
    ap.add_argument("--scene", required=True,
                    help="directory della scena (contiene scene.json)")
    ap.add_argument("--style", default="cartoon",
                    choices=["real", "cartoon", "line_art"])
    ap.add_argument("--count", type=int, default=80)
    ap.add_argument("--difficulty", default="medium",
                    choices=["easy", "medium", "hard"])
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--tier", default="0",
                    help="0 = classic (default), auto = miglior modello su disco")
    ap.add_argument("--tag", default=None, help="filtro tag tema opzionale")
    ap.add_argument("--out", default="scratch/scatter_real.png")
    ap.add_argument("--no-validate", action="store_true",
                    help="salta la validazione post-render del camouflage")
    ap.add_argument("--keep-fails", action="store_true",
                    help="tieni nel risultato anche gli oggetti bocciati dalla validazione")
    args = ap.parse_args()

    repo_root = Path(__file__).resolve().parent.parent
    scene_dir = Path(args.scene)
    sd, game_id, bg_path = load_scene(scene_dir)
    game_path = repo_root / "games" / game_id
    log.info(f"scena: {scene_dir.name} | gioco: {game_id} | bg: {bg_path.name}")

    pygame.init()
    pygame.display.set_mode((64, 64))
    surf = pygame.image.load(str(bg_path)).convert()
    log.info(f"BG {surf.get_size()}")

    # Modello IA opzionale
    ia_model = None
    if args.tier == "auto":
        from editor.tools.scatter_models import get_best_model
        ia_model = get_best_model(repo_root, quick_benchmark=False)
        log.info(f"modello: tier {ia_model.tier} ({ia_model.name})")

    bg = se.analyze_background(surf, ia_model=ia_model, base_path=repo_root,
                               use_cache=True)
    n_face = 0 if bg.face_mask is None else int(bg.face_mask.sum())
    log.info(f"grid {bg.cell_w}x{bg.cell_h} | volti: {n_face} celle")

    catalog = load_game_catalog(game_id)
    catalog = [c for c in catalog if c.get("style", "real") == args.style]
    if not catalog:
        log.error(f"nessun oggetto stile '{args.style}' nel catalogo di {game_id}")
        sys.exit(1)
    log.info(f"catalogo {args.style}: {len(catalog)} oggetti")

    analyses = se.precompute_catalog(catalog, args.style, repo_root)
    entries = {c["id"]: c for c in catalog}

    manual = load_manual_forbidden(scene_dir)
    if manual:
        log.info(f"zone vietate manuali: {len(manual)} celle")
    forbidden = build_forbidden_mask(bg, manual)

    placed = place_objects(
        bg, analyses, entries,
        count=args.count, difficulty=args.difficulty, style=args.style,
        tag_filter=args.tag, seed=args.seed, forbidden_mask=forbidden,
        allowed_layers=["objects_low", "objects_mid", "objects_high"],
    )
    print_metrics(placed, bg, args.count)

    canvas = surf.copy()
    drawn = render_placed_real(canvas, placed, entries, game_path, repo_root)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    pygame.image.save(canvas, str(out))
    log.info(f"disegnati {drawn}/{len(placed)} | salvato {out}")

    # ── VALIDAZIONE POST-RENDER: l'oggetto composito stacca dall'intorno? ──
    if not args.no_validate:
        from editor.tools.scatter_validate import (
            validate_placements, summarize, annotate,
        )
        results = validate_placements(surf, placed, entries, game_path, repo_root)
        stats = summarize(results)
        log.info(f"VALIDAZIONE: {stats['ok']} ok / {stats['warn']} warn / "
                 f"{stats['fail']} fail su {stats['total']} "
                 f"(score medio {stats['avg_score']})")
        for r in sorted(results, key=lambda r: -r["score"]):
            if r["verdict"] != "ok":
                log.info(f"  [{r['verdict'].upper()}] {r['catalog_id']}: "
                         f"score={r['score']} dE={r['delta_e']} "
                         f"dL={r['delta_l']} clutter={r['clutter']} @ {r['rect'][:2]}")
        annotated = canvas.copy()
        annotate(annotated, results)
        out_val = out.with_name(out.stem + "_validated" + out.suffix)
        pygame.image.save(annotated, str(out_val))
        log.info(f"annotato: {out_val}")

        # Chiusura del loop: gli oggetti BOCCIATI (fail) vengono scartati dal
        # risultato finale — meglio N-k oggetti coerenti che k in evidenza.
        if stats["fail"] > 0 and not args.keep_fails:
            from editor.tools.scatter_validate import filter_failed
            kept, dropped = filter_failed(placed, results, entries,
                                          game_path, repo_root)
            if dropped:
                log.info(f"scartati {dropped} oggetti bocciati -> {len(kept)} finali")
                canvas2 = surf.copy()
                render_placed_real(canvas2, kept, entries, game_path, repo_root)
                pygame.image.save(canvas2, str(out))
                log.info(f"risultato finale (senza fail) risalvato in {out}")


if __name__ == "__main__":
    main()
