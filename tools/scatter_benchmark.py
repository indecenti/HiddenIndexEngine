"""Benchmark A/B dell'auto-scatter: piazza su scene reali con seed fissi e
misura la qualita' del camuffamento con la metrica unica di scatter_metrics
(pop_score render-based) + la validazione storica (verdetti ok/warn/fail).

Serve a rendere MISURABILE ogni modifica all'algoritmo: si genera una baseline
prima della modifica e un run dopo, e si confrontano i numeri.

Uso:
    # run completo (auto-discovery scene) e salvataggio report
    python tools/scatter_benchmark.py --out scratch/scatter_bench/baseline.json

    # scene esplicite, con contact sheet PNG
    python tools/scatter_benchmark.py --scenes games/Malonno_Survivors/levels/L1/S1 \
        --out scratch/scatter_bench/after.json --sheet

    # confronto fra due report
    python tools/scatter_benchmark.py --compare scratch/scatter_bench/baseline.json \
        scratch/scatter_bench/after.json

Note:
  - Tier 0 (classico, nessun modello IA): il benchmark misura il percorso
    default. La BG analysis usa la cache SQLite (secondo run molto piu' veloce).
  - Le zone vietate manuali della scena (scatter_forbidden.json) e i volti
    auto-rilevati sono attivi come nell'editor.
  - Per ogni oggetto TENUTO (post filter_failed) registra pop_score e
    componenti: i dati per-oggetto permettono la calibrazione delle soglie.
"""
import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
import argparse
import json
import logging
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import numpy as np
import pygame

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from editor.tools import scatter_engine as se
from editor.tools import scatter_metrics as sm
from editor.tools.scatter_engine import build_forbidden_mask
from editor.tools.scatter_validate import (
    annotate, run_scatter_with_repair, summarize,
)

log = logging.getLogger("scatter_benchmark")

DEFAULT_COUNT = 40
DEFAULT_SEEDS = "7,23"
DEFAULT_DIFFICULTIES = "easy,medium,hard"
# Scene per gioco nell'auto-discovery (deterministico: ordinamento per path)
MAX_SCENES_PER_GAME = 3
# Larghezza thumb del contact sheet
SHEET_THUMB_W = 420
SHEET_PAD = 8


def _git_rev(repo_root: Path) -> str:
    try:
        out = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                             cwd=repo_root, capture_output=True, text=True,
                             timeout=10)
        return out.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def discover_scenes(repo_root: Path, max_per_game: int) -> list[Path]:
    """Scene con background risolvibile, ordinate, cap per gioco."""
    scenes: list[Path] = []
    games_dir = repo_root / "games"
    for game_dir in sorted(games_dir.iterdir()):
        if not game_dir.is_dir():
            continue
        found = 0
        for sj in sorted(game_dir.glob("levels/*/*/scene.json")):
            if found >= max_per_game:
                break
            try:
                sd = json.loads(sj.read_text(encoding="utf-8"))
            except Exception:
                continue
            bg = sj.parent / sd.get("background", "background.png")
            if bg.exists():
                scenes.append(sj.parent)
                found += 1
    return scenes


def game_id_of(scene_dir: Path) -> str:
    parts = scene_dir.resolve().parts
    return parts[parts.index("games") + 1]


def load_game_catalog(game_id: str) -> list[dict]:
    from engine.catalog_manager import load_catalog
    return load_catalog(game_id).get("objects", [])


def majority_style(catalog: list[dict]) -> str:
    counts: dict[str, int] = {}
    for c in catalog:
        s = c.get("style", "real")
        counts[s] = counts.get(s, 0) + 1
    return max(counts, key=counts.get) if counts else "real"


def scene_style(scene_dir: Path, catalog: list[dict]) -> str:
    """Stile dominante fra gli oggetti GIA' piazzati nella scena (come
    l'auto-detect dell'editor); fallback: maggioranza del catalogo."""
    by_id = {c["id"]: c.get("style", "real") for c in catalog}
    counts: dict[str, int] = {}
    try:
        sd = json.loads((scene_dir / "scene.json").read_text(encoding="utf-8"))
        objs = sd.get("objects") or []
        if isinstance(objs, dict):  # formato legacy per-layer
            objs = [o for lst in objs.values() for o in (lst or [])]
        for o in objs:
            s = by_id.get(o.get("catalog_id"))
            if s:
                counts[s] = counts.get(s, 0) + 1
    except Exception:
        pass
    if counts:
        return max(counts, key=counts.get)
    return majority_style(catalog)


def load_manual_forbidden(scene_dir: Path) -> set[tuple[int, int]]:
    fp = scene_dir / "scatter_forbidden.json"
    if not fp.exists():
        return set()
    try:
        data = json.loads(fp.read_text(encoding="utf-8"))
        return {(int(c[0]), int(c[1])) for c in data.get("cells", [])
                if isinstance(c, (list, tuple)) and len(c) == 2}
    except Exception as e:
        log.warning(f"scatter_forbidden.json illeggibile in {scene_dir}: {e}")
        return set()


def render_placed(canvas: pygame.Surface, placed, entries: dict,
                  game_path: Path, repo_root: Path) -> None:
    """Disegna i piazzati con la pipeline visiva del gioco (per il sheet)."""
    icon_cache: dict = {}
    for p in placed:
        entry = entries.get(p.catalog_id)
        if not entry:
            continue
        rendered = sm.render_sprite(p, entry, game_path, repo_root, icon_cache)
        if rendered is None:
            continue
        img, cx, cy = rendered
        canvas.blit(img, img.get_rect(center=(int(cx), int(cy))))


def run_one(scene_dir: Path, repo_root: Path, style: str, difficulty: str,
            seed: int, count: int, with_saliency: bool,
            bg_analysis_cache: dict) -> tuple[dict, Optional[pygame.Surface]]:
    """Esegue un run scena x difficolta' x seed. Ritorna (record, canvas)."""
    sd = json.loads((scene_dir / "scene.json").read_text(encoding="utf-8"))
    game_id = game_id_of(scene_dir)
    game_path = repo_root / "games" / game_id
    bg_path = scene_dir / sd.get("background", "background.png")

    key = str(bg_path)
    if key in bg_analysis_cache:
        surf, bg, t_analyze = bg_analysis_cache[key]
    else:
        surf = pygame.image.load(str(bg_path)).convert()
        t0 = time.time()
        bg = se.analyze_background(surf, ia_model=None, base_path=repo_root,
                                   use_cache=True)
        t_analyze = (time.time() - t0) * 1000
        bg_analysis_cache[key] = (surf, bg, t_analyze)

    catalog = [c for c in load_game_catalog(game_id)
               if c.get("style", "real") == style]
    analyses = se.precompute_catalog(catalog, style, repo_root)
    entries = {c["id"]: c for c in catalog}
    forbidden = build_forbidden_mask(bg, load_manual_forbidden(scene_dir))

    # Pipeline v4 ondata 2: best-of-M render-in-the-loop + repair dei fail.
    render_ctx = {"bg_surface": surf, "game_path": game_path,
                  "repo_root": repo_root}
    t0 = time.time()
    kept, results, repair = run_scatter_with_repair(
        bg, analyses, entries, bg_surface=surf, game_path=game_path,
        repo_root=repo_root, count=count, difficulty=difficulty,
        style=style, seed=seed, forbidden_mask=forbidden,
        allowed_layers=["objects_low", "objects_mid", "objects_high"],
        render_ctx=render_ctx,
    )
    t_place = (time.time() - t0) * 1000
    t_validate = 0.0  # incluso nel repair loop
    verdicts = summarize(results)
    verdicts["fail"] = verdicts.get("fail", 0) + repair["dropped_fail"]
    dropped = repair["dropped_fail"]

    t0 = time.time()
    metrics = sm.measure_placements(surf, kept, entries, game_path, repo_root,
                                    with_saliency=with_saliency)
    t_metrics = (time.time() - t0) * 1000

    # Join per-oggetto metrica nuova <-> verdetto storico (per calibrazione)
    verdict_by_key = {(r["catalog_id"], tuple(r["rect"])): r for r in results}
    objects = []
    for m in metrics:
        old = verdict_by_key.get((m.catalog_id, m.rect))
        objects.append({
            "id": m.catalog_id,
            "pop": m.pop_score,
            "rim": m.rim_delta_e,
            "interior": m.interior_delta_e,
            "boundary": m.boundary_contrast,
            "texture": m.texture_mismatch,
            "saliency": m.saliency_delta,
            "clutter": m.clutter,
            "old_score": old["score"] if old else None,
            "old_verdict": old["verdict"] if old else None,
        })

    record = {
        "scene": os.path.relpath(scene_dir.resolve(), repo_root),
        "game": game_id,
        "style": style,
        "difficulty": difficulty,
        "seed": seed,
        "requested": count,
        "placed": len(kept),        # consegnati (post repair): fill onesto
        "dropped_fail": dropped,
        "kept": len(kept),
        "repair_rounds": repair["repair_rounds"],
        "verdicts": verdicts,
        "camo": sm.summarize_camouflage(metrics),
        "objects": objects,
        "timing_ms": {
            "analyze": round(t_analyze),
            "place": round(t_place),
            "validate": round(t_validate),
            "metrics": round(t_metrics),
        },
    }

    canvas = surf.copy()
    render_placed(canvas, kept, entries, game_path, repo_root)
    annotate(canvas, [r for r in results if r["verdict"] != "fail"])
    return record, canvas


def aggregate(runs: list[dict]) -> dict:
    """Aggregati per difficolta' su tutti i run (per-oggetto, non per-run)."""
    out: dict[str, dict] = {}
    for diff in sorted({r["difficulty"] for r in runs}):
        rs = [r for r in runs if r["difficulty"] == diff]
        pops = np.array([o["pop"] for r in rs for o in r["objects"]],
                        dtype=np.float32)
        rims = np.array([o["rim"] for r in rs for o in r["objects"]
                         if o["rim"] is not None], dtype=np.float32)
        n_ok = sum(r["verdicts"].get("ok", 0) for r in rs)
        n_warn = sum(r["verdicts"].get("warn", 0) for r in rs)
        n_fail = sum(r["verdicts"].get("fail", 0) for r in rs)
        n_tot = max(1, n_ok + n_warn + n_fail)
        req = sum(r["requested"] for r in rs)
        out[diff] = {
            "runs": len(rs),
            "objects": int(pops.size),
            "pop_mean": round(float(pops.mean()), 1) if pops.size else None,
            "pop_median": round(float(np.median(pops)), 1) if pops.size else None,
            "pop_p90": round(float(np.quantile(pops, 0.9)), 1) if pops.size else None,
            "rim_mean": round(float(rims.mean()), 1) if rims.size else None,
            "ok_pct": round(100.0 * n_ok / n_tot, 1),
            "warn_pct": round(100.0 * n_warn / n_tot, 1),
            "fail_pct": round(100.0 * n_fail / n_tot, 1),
            "fill_rate": round(sum(r["placed"] for r in rs) / max(1, req), 3),
            "dropped_fail": sum(r["dropped_fail"] for r in rs),
            "place_ms_mean": round(float(np.mean(
                [r["timing_ms"]["place"] for r in rs]))),
        }
    return out


def build_sheet(canvases: list[tuple[str, pygame.Surface]], out_path: Path) -> None:
    """Contact sheet verticale: thumb per run (prima seed di ogni combo)."""
    if not canvases:
        return
    pygame.font.init()
    font = pygame.font.SysFont("consolas,menlo,monospace", 16)
    thumbs = []
    for label, canvas in canvases:
        w, h = canvas.get_size()
        th = max(1, int(h * SHEET_THUMB_W / w))
        thumb = pygame.transform.smoothscale(canvas, (SHEET_THUMB_W, th))
        thumbs.append((label, thumb))
    total_h = sum(t.get_height() + 24 + SHEET_PAD for _, t in thumbs) + SHEET_PAD
    sheet = pygame.Surface((SHEET_THUMB_W + 2 * SHEET_PAD, total_h))
    sheet.fill((24, 24, 28))
    y = SHEET_PAD
    for label, thumb in thumbs:
        sheet.blit(font.render(label, True, (230, 230, 230)), (SHEET_PAD, y))
        y += 24
        sheet.blit(thumb, (SHEET_PAD, y))
        y += thumb.get_height() + SHEET_PAD
    out_path.parent.mkdir(parents=True, exist_ok=True)
    pygame.image.save(sheet, str(out_path))
    log.info(f"contact sheet: {out_path}")


def compare_reports(path_a: Path, path_b: Path) -> None:
    """Tabella delta per difficolta' fra due report (A = baseline, B = after)."""
    a = json.loads(path_a.read_text(encoding="utf-8"))
    b = json.loads(path_b.read_text(encoding="utf-8"))
    agg_a, agg_b = a["aggregates"], b["aggregates"]
    cols = ["pop_mean", "pop_median", "pop_p90", "rim_mean",
            "ok_pct", "warn_pct", "fail_pct", "fill_rate",
            "dropped_fail", "place_ms_mean"]
    log.info(f"A = {path_a.name} ({a['meta'].get('git_rev')}) | "
             f"B = {path_b.name} ({b['meta'].get('git_rev')})")
    for diff in sorted(set(agg_a) | set(agg_b)):
        log.info(f"[{diff}]")
        ra, rb = agg_a.get(diff, {}), agg_b.get(diff, {})
        for c in cols:
            va, vb = ra.get(c), rb.get(c)
            if va is None and vb is None:
                continue
            delta = ""
            if isinstance(va, (int, float)) and isinstance(vb, (int, float)):
                d = vb - va
                delta = f"  ({'+' if d >= 0 else ''}{round(d, 2)})"
            log.info(f"  {c:<14} {va!s:>8} -> {vb!s:>8}{delta}")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    logging.getLogger("editor.tools").setLevel(logging.WARNING)
    ap = argparse.ArgumentParser(description="Benchmark camouflage auto-scatter")
    ap.add_argument("--scenes", default=None,
                    help="directory scena separate da virgola (default: auto)")
    ap.add_argument("--out", default="scratch/scatter_bench/report.json")
    ap.add_argument("--count", type=int, default=DEFAULT_COUNT)
    ap.add_argument("--seeds", default=DEFAULT_SEEDS)
    ap.add_argument("--difficulties", default=DEFAULT_DIFFICULTIES)
    ap.add_argument("--style", default=None,
                    help="forza lo stile (default: maggioranza catalogo gioco)")
    ap.add_argument("--max-scenes", type=int, default=MAX_SCENES_PER_GAME)
    ap.add_argument("--no-saliency", action="store_true",
                    help="salta il termine saliency (piu' veloce)")
    ap.add_argument("--sheet", action="store_true",
                    help="salva contact sheet PNG accanto al JSON")
    ap.add_argument("--compare", nargs=2, metavar=("BASE", "AFTER"),
                    help="confronta due report e termina")
    args = ap.parse_args()

    if args.compare:
        compare_reports(Path(args.compare[0]), Path(args.compare[1]))
        return

    repo_root = Path(__file__).resolve().parent.parent
    pygame.init()
    pygame.display.set_mode((64, 64))

    if args.scenes:
        scene_dirs = [Path(s.strip()) for s in args.scenes.split(",") if s.strip()]
    else:
        scene_dirs = discover_scenes(repo_root, args.max_scenes)
    if not scene_dirs:
        log.error("nessuna scena con background trovata")
        sys.exit(1)

    seeds = [int(s) for s in args.seeds.split(",")]
    difficulties = [d.strip() for d in args.difficulties.split(",")]
    style_by_game: dict[str, str] = {}
    runs: list[dict] = []
    canvases: list[tuple[str, pygame.Surface]] = []
    bg_cache: dict = {}
    t_start = time.time()

    for scene_dir in scene_dirs:
        gid = game_id_of(scene_dir)
        if args.style:
            style = args.style
        else:
            if gid not in style_by_game:
                style_by_game[gid] = majority_style(load_game_catalog(gid))
            style = style_by_game[gid]
        for diff in difficulties:
            for i, seed in enumerate(seeds):
                label = f"{scene_dir.name} [{style}] {diff} seed={seed}"
                log.info(f"run: {label}")
                try:
                    rec, canvas = run_one(scene_dir, repo_root, style, diff,
                                          seed, args.count,
                                          not args.no_saliency, bg_cache)
                except Exception:
                    log.exception(f"run fallito: {label}")
                    continue
                runs.append(rec)
                v = rec["verdicts"]
                log.info(f"  piazzati {rec['placed']}/{rec['requested']} | "
                         f"ok/warn/fail {v['ok']}/{v['warn']}/{v['fail']} | "
                         f"pop_mean {rec['camo'].get('pop_mean')} | "
                         f"place {rec['timing_ms']['place']}ms")
                if i == 0:
                    canvases.append((label, canvas))

    if not runs:
        log.error("nessun run completato")
        sys.exit(1)

    report = {
        "meta": {
            "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "git_rev": _git_rev(repo_root),
            "count": args.count,
            "seeds": seeds,
            "difficulties": difficulties,
            "saliency": not args.no_saliency,
            "scenes": [str(s) for s in scene_dirs],
            "elapsed_s": round(time.time() - t_start, 1),
        },
        "runs": runs,
        "aggregates": aggregate(runs),
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False),
                   encoding="utf-8")
    log.info(f"report: {out} ({len(runs)} run in {report['meta']['elapsed_s']}s)")
    for diff, agg in report["aggregates"].items():
        log.info(f"[{diff}] pop_mean={agg['pop_mean']} p90={agg['pop_p90']} "
                 f"rim={agg['rim_mean']} ok/warn/fail% "
                 f"{agg['ok_pct']}/{agg['warn_pct']}/{agg['fail_pct']} "
                 f"fill={agg['fill_rate']}")

    if args.sheet:
        build_sheet(canvases, out.with_suffix(".png"))


if __name__ == "__main__":
    main()
