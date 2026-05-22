"""QA visiva del region-fit: esegue place_objects su un background reale e
disegna i bounding box risultanti (taglia conformata alla regione) sul BG."""
import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
import sys, math, statistics
from pathlib import Path
import numpy as np
import pygame

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from editor.tools import scatter_engine as se
from editor.tools.scatter_engine import ObjAnalysis, place_objects

BG = Path("games/Malonno_Survivors/levels/Welcome_To_Malonno/Brescia_Edolo/background.png")


def make_obj(cid, aspect, size_class, hsv):
    return ObjAnalysis(
        catalog_id=cid,
        palette=[hsv, (hsv[0], hsv[1]*0.7, min(1.0, hsv[2]*1.2)), (0.0, 0.0, 0.5)],
        edge_orient=0.0,
        aspect=aspect,
        size_class=size_class,
        shape={"axis_angle": 0.0, "aspect_real": 1.0/aspect if aspect > 1 else aspect, "hu": None},
        palette_ext=None,
    )


def main():
    pygame.init(); pygame.display.set_mode((64, 64))
    surf = pygame.image.load(str(BG)).convert()
    print("BG", surf.get_size())
    bg = se.analyze_background(surf, use_cache=False)
    print("cells", bg.cell_w, "x", bg.cell_h, "cell_px", bg.cell_px, "hsv_full", None if bg.hsv_full is None else bg.hsv_full.shape)

    objs = {
        "wide":  make_obj("wide",  2.2, "mid",  (0.33, 0.5, 0.4)),   # verde, largo
        "square":make_obj("square",1.0, "mid",  (0.08, 0.4, 0.5)),   # marrone, quadrato
        "small": make_obj("small", 1.0, "small",(0.6, 0.3, 0.6)),    # azzurrino, piccolo
    }
    entries = {cid: {"default_width": 120, "default_height": int(120/o.aspect),
                     "default_detection": "rect", "tags": []}
               for cid, o in objs.items()}

    placed = place_objects(bg, objs, entries, count=30, difficulty="medium",
                           style="real", seed=7)
    print("piazzati:", len(placed))
    # Statistiche taglia per oggetto (spread = prova che il fit varia per regione)
    for cid in objs:
        sizes = [max(p.width, p.height) * p.scale for p in placed if p.catalog_id == cid]
        if sizes:
            print(f"  {cid}: n={len(sizes)} eff_long min/med/max = "
                  f"{min(sizes):.0f}/{statistics.median(sizes):.0f}/{max(sizes):.0f}px "
                  f"spread={max(sizes)/max(1,min(sizes)):.2f}x")

    # Render dei bounding box ruotati sul BG
    canvas = surf.copy()
    cols = {"wide": (0, 255, 0), "square": (255, 160, 0), "small": (0, 200, 255)}
    for p in placed:
        w = p.width * p.scale; h = p.height * p.scale
        cx = p.x + (w/2 if p.detection_type != "circle" else 0)
        cy = p.y + (h/2 if p.detection_type != "circle" else 0)
        box = pygame.Surface((int(w), int(h)), pygame.SRCALPHA)
        pygame.draw.rect(box, (*cols[p.catalog_id], 255), box.get_rect(), 4)
        box = pygame.transform.rotate(box, -p.rotation)
        canvas.blit(box, box.get_rect(center=(int(cx), int(cy))))
    out = Path("scatter_fit_preview.png")
    pygame.image.save(canvas, str(out))
    print("saved", out)


if __name__ == "__main__":
    main()
