"""Contact sheet of finished assets on a dark and a light backdrop (alpha check)."""
import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(r"G:\HIE git")
ids = sys.argv[1:]
CELL = 290
PAD = 15
BACKS = [(40, 44, 52), (225, 225, 225), (170, 60, 50)]
sheet = Image.new("RGB", (CELL * len(ids), CELL * len(BACKS) + 24), (20, 20, 24))
draw = ImageDraw.Draw(sheet)
for i, obj_id in enumerate(ids):
    im = Image.open(next(p for p in [*(ROOT / "games").glob(f"*/objects/{obj_id}.png"), ROOT / "engine" / "assets" / "objects" / f"{obj_id}.png"] if p.exists()))
    for row, back in enumerate(BACKS):
        cell = Image.new("RGBA", (CELL, CELL), (*back, 255))
        cell.alpha_composite(im, ((CELL - im.width) // 2, (CELL - im.height) // 2))
        sheet.paste(cell.convert("RGB"), (i * CELL, row * CELL))
    draw.text((i * CELL + 6, CELL * len(BACKS) + 6), obj_id, fill=(255, 220, 0))
out = ROOT / "scratch" / "gen_assets" / "_sheet.png"
sheet.save(out)
print(out)
