"""QA visiva del camouflage v3: dumpa le heatmap di debug (score, forbidden,
saliency, color_gate) come PNG colormap + un overlay dei piazzamenti sul BG.

Uso:
    python tools/preview_scatter_debug.py --bg <path> [--style real]
        [--difficulty medium] [--seed 7] [--count 30] [--out scratch]

Serve a tarare le costanti (EDGE_DENSITY_ABS_REF, COLOR_GATE_MIN, bande) su
background reali senza aprire l'editor.
"""
import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
import argparse
import sys
from pathlib import Path

import numpy as np
import pygame

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from editor.tools import scatter_engine as se
from editor.tools.scatter_engine import (
    ObjAnalysis, place_objects, compute_debug_maps, build_forbidden_mask,
    _get_weights,
)

try:
    import cv2
    _HAS_CV2 = True
except Exception:
    _HAS_CV2 = False

DEFAULT_BG = "games/Malonno_Survivors/levels/Welcome_To_Malonno/Brescia_Edolo/background.png"


def make_obj(cid: str, aspect: float, size_class: str,
             hsv: tuple[float, float, float]) -> ObjAnalysis:
    return ObjAnalysis(
        catalog_id=cid,
        palette=[hsv, (hsv[0], hsv[1] * 0.7, min(1.0, hsv[2] * 1.2)), (0.0, 0.0, 0.5)],
        edge_orient=0.0,
        aspect=aspect,
        size_class=size_class,
        shape={"axis_angle": 0.0,
               "aspect_real": 1.0 / aspect if aspect > 1 else aspect, "hu": None},
        palette_ext=[
            {"h": hsv[0], "s": hsv[1], "v": hsv[2], "w": 0.6, "var": 0.02},
            {"h": hsv[0], "s": hsv[1] * 0.7, "v": min(1.0, hsv[2] * 1.2),
             "w": 0.4, "var": 0.03},
        ],
    )


def save_heatmap(m: np.ndarray, out_path: Path) -> None:
    """Salva la mappa 0..1 come PNG colormap (JET se cv2, gradiente blu-rosso se no)."""
    v = np.clip(m, 0.0, 1.0)
    u8 = (v * 255).astype(np.uint8)
    if _HAS_CV2:
        img = cv2.applyColorMap(u8, cv2.COLORMAP_JET)
        cv2.imwrite(str(out_path), img)
    else:
        rgb = np.stack([u8, np.zeros_like(u8), 255 - u8], axis=-1)
        surf = pygame.surfarray.make_surface(rgb.swapaxes(0, 1))
        pygame.image.save(surf, str(out_path))


def main() -> None:
    ap = argparse.ArgumentParser(description="Dump heatmap debug scatter v3")
    ap.add_argument("--bg", default=DEFAULT_BG)
    ap.add_argument("--style", default="real")
    ap.add_argument("--difficulty", default="medium",
                    choices=["easy", "medium", "hard"])
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--count", type=int, default=30)
    ap.add_argument("--out", default="scratch")
    args = ap.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    pygame.init()
    pygame.display.set_mode((64, 64))
    surf = pygame.image.load(args.bg).convert()
    print("BG", surf.get_size())

    # base_path = repo root, cosi' face detection trova l'eventuale YuNet
    base_path = Path(__file__).resolve().parent.parent
    bg = se.analyze_background(surf, base_path=base_path, use_cache=False)
    print(f"grid {bg.cell_w}x{bg.cell_h} @ {bg.cell_px}px | "
          f"volti: {0 if bg.face_mask is None else int(bg.face_mask.sum())} celle")

    objs = {
        "verde":  make_obj("verde",  1.4, "mid",   (0.33, 0.5, 0.4)),
        "marrone": make_obj("marrone", 1.0, "mid",  (0.08, 0.4, 0.5)),
        "azzurro": make_obj("azzurro", 1.0, "small", (0.60, 0.3, 0.6)),
    }
    entries = {cid: {"default_width": 120, "default_height": int(120 / o.aspect),
                     "default_detection": "rect", "tags": []}
               for cid, o in objs.items()}

    weights = _get_weights(args.difficulty, args.style)
    forbidden = build_forbidden_mask(bg)

    for cid, obj in objs.items():
        maps = compute_debug_maps(bg, obj, weights, forbidden, args.difficulty)
        save_heatmap(maps["score"], out_dir / f"score_{cid}.png")
        save_heatmap(maps["color_gate"], out_dir / f"color_gate_{cid}.png")
        gate_pct = float(maps["color_gate"].mean()) * 100
        print(f"  {cid}: gate colore veta {gate_pct:.0f}% celle")
    any_maps = compute_debug_maps(bg, None, weights, forbidden, args.difficulty)
    save_heatmap(any_maps["forbidden"], out_dir / "forbidden.png")
    save_heatmap(any_maps["saliency"], out_dir / "saliency.png")

    placed = place_objects(bg, objs, entries, count=args.count,
                           difficulty=args.difficulty, style=args.style,
                           seed=args.seed, forbidden_mask=forbidden)
    print("piazzati:", len(placed))

    canvas = surf.copy()
    cols = {"verde": (0, 255, 0), "marrone": (255, 160, 0), "azzurro": (0, 200, 255)}
    for p in placed:
        w = p.width * p.scale
        h = p.height * p.scale
        cx = p.x + (w / 2 if p.detection_type != "circle" else 0)
        cy = p.y + (h / 2 if p.detection_type != "circle" else 0)
        box = pygame.Surface((max(2, int(w)), max(2, int(h))), pygame.SRCALPHA)
        pygame.draw.rect(box, (*cols[p.catalog_id], 255), box.get_rect(), 4)
        box = pygame.transform.rotate(box, -p.rotation)
        canvas.blit(box, box.get_rect(center=(int(cx), int(cy))))
    # Celle vietate in rosso sull'overlay
    if forbidden is not None:
        cpx = bg.cell_px
        red = pygame.Surface((cpx, cpx), pygame.SRCALPHA)
        red.fill((255, 0, 0, 90))
        ys, xs = forbidden.nonzero()
        for ccy, ccx in zip(ys.tolist(), xs.tolist()):
            canvas.blit(red, (ccx * cpx, ccy * cpx))
    out = out_dir / "scatter_debug_placements.png"
    pygame.image.save(canvas, str(out))
    print("saved", out_dir.resolve())


if __name__ == "__main__":
    main()
