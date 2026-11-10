"""Background with a labelled coordinate grid, to read surface lines for place_on_surfaces.

Usage: python tools/surface_grid.py <scene_dir> [step_px] [crop x0,y0,x1,y1]
Output: scratch/placement/<scene>_grid.jpg (1920 wide, or the crop at native size).
"""
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

REPO = Path(__file__).resolve().parent.parent
OUT_W = 1920
LINE = (255, 255, 0)
DEFAULT_STEP = 200


def main() -> None:
    scene_dir = Path(sys.argv[1])
    step = int(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_STEP
    crop = [int(v) for v in sys.argv[3].split(",")] if len(sys.argv) > 3 else None
    data = json.loads((scene_dir / "scene.json").read_text(encoding="utf-8"))
    im = Image.open(scene_dir / data["background"]).convert("RGB")
    x0, y0, x1, y1 = crop or (0, 0, im.width, im.height)
    im = im.crop((x0, y0, x1, y1))
    k = min(1.0, OUT_W / im.width)
    im = im.resize((round(im.width * k), round(im.height * k)), Image.LANCZOS)
    d = ImageDraw.Draw(im)
    font = ImageFont.load_default(size=18)
    for gx in range((x0 // step) * step, x1 + 1, step):
        if gx < x0:
            continue
        sx = (gx - x0) * k
        d.line([sx, 0, sx, im.height], fill=LINE, width=1)
        d.text((sx + 3, 3), str(gx), fill=LINE, font=font, stroke_width=2, stroke_fill=(0, 0, 0))
    for gy in range((y0 // step) * step, y1 + 1, step):
        if gy < y0:
            continue
        sy = (gy - y0) * k
        d.line([0, sy, im.width, sy], fill=LINE, width=1)
        d.text((3, sy + 3), str(gy), fill=LINE, font=font, stroke_width=2, stroke_fill=(0, 0, 0))
    out = REPO / "scratch" / "placement"
    out.mkdir(parents=True, exist_ok=True)
    suffix = "_grid" if not crop else f"_grid_{x0}_{y0}"
    im.save(out / f"{scene_dir.name}{suffix}.jpg", quality=88)
    print(out / f"{scene_dir.name}{suffix}.jpg")


if __name__ == "__main__":
    main()
