"""Four objects in one Qwen-Image 2.1 render: a 2x2 grid on chroma green.

Same graph as generate_qwen21.py, at GRID_SIZE (each quadrant GRID_SIZE / 2).
The raw grid goes to scratch/gen_assets/raw_grid/<name>.png and each quadrant to
scratch/gen_assets/raw/<id>.png, ready for import_generated.py (listed there in
GREEN_BG so they are cut with the green key).
"""
import sys
import time
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import generate_qwen21 as gen  # noqa: E402

GRID_SIZE = 1536
HERE = Path(__file__).resolve().parents[4] / "scratch" / "gen_assets"
RAW_GRID = HERE / "raw_grid"

GRID = {
    "top-left": ("brass_door_knocker", "antique brass lion-head door knocker with its ring, tarnished"),
    "top-right": ("wire_spectacles", "old round wire-rimmed spectacles with thin metal frame and "
                  "clear glass lenses, folded arms"),
    "bottom-left": ("hand_sickle", "old hand sickle with a curved rusty blade and a worn wooden handle"),
    "bottom-right": ("tobacco_tin", "small vintage rectangular tobacco tin, scratched lithographed "
                     "metal lid with faded colours, closed"),
}

PROMPT = (
    "a 2x2 grid of four separate studio product photographs, divided into four equal square "
    "quadrants by wide gutters. {cells}. In every quadrant exactly one complete object, whole and "
    "centered, small enough to leave a wide empty margin so it never touches the quadrant edges. "
    "Every quadrant has the same solid pure chroma key green (#00FF00) flat background, soft even "
    "diffuse lighting, photorealistic, sharp focus, highly detailed realistic aged textures, "
    "no text, no labels, no numbers, no hands, no other objects")


def main() -> None:
    RAW_GRID.mkdir(parents=True, exist_ok=True)
    gen.OUT.mkdir(parents=True, exist_ok=True)
    cells = "; ".join(f"{pos} quadrant: {what}" for pos, (_id, what) in GRID.items())
    prompt = PROMPT.format(cells=cells)
    gen.SIZE = GRID_SIZE
    t0 = time.time()
    graph = gen.graph(prompt, seed=777, prefix="hie_grid")
    pid = gen.post("/prompt", {"prompt": graph})["prompt_id"]
    while True:
        import json
        import urllib.parse
        hist = json.loads(gen.get(f"/history/{pid}"))
        if pid in hist:
            img = next(im for node in hist[pid]["outputs"].values() for im in node.get("images", []))
            q = urllib.parse.urlencode({"filename": img["filename"], "subfolder": img.get("subfolder", ""),
                                        "type": img.get("type", "output")})
            grid_path = RAW_GRID / "grid_1.png"
            grid_path.write_bytes(gen.get(f"/view?{q}"))
            break
        time.sleep(gen.POLL_S)
    print(f"grid in {time.time() - t0:.0f}s")
    im = Image.open(grid_path).convert("RGB")
    half = im.width // 2, im.height // 2
    boxes = {"top-left": (0, 0), "top-right": (half[0], 0),
             "bottom-left": (0, half[1]), "bottom-right": half}
    for pos, (obj_id, _what) in GRID.items():
        x, y = boxes[pos]
        im.crop((x, y, x + half[0], y + half[1])).save(gen.OUT / f"{obj_id}.png")
        print(obj_id, "->", gen.OUT / f"{obj_id}.png")


if __name__ == "__main__":
    main()
