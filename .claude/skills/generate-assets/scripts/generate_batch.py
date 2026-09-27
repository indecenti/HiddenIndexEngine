"""The 100-object batch: 25 renders of 2x2 grids with Qwen-Image 2.1 on chroma green.

Objects come from candidates_100.C, four per grid, in order. A grid whose four
quadrants are already in raw/ is skipped, so the batch resumes after a stop.
Progress is appended to raw_grid/batch.log.
"""
import json
import sys
import time
import urllib.parse
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parents[4] / "scratch" / "gen_assets"
sys.path.insert(0, str(Path(__file__).resolve().parent))
import generate_qwen21 as gen  # noqa: E402
import importlib  # noqa: E402
LIST = next((a.split('=', 1)[1] for a in sys.argv[1:] if a.startswith('--list=')),
            'candidates_100')
C = importlib.import_module(LIST).C
from generate_grid import GRID_SIZE, PROMPT  # noqa: E402

RAW_GRID = HERE / "raw_grid"
POSITIONS = ("top-left", "top-right", "bottom-left", "bottom-right")
SEED_BASE = 1000


def render(prompt: str, seed: int, dest: Path) -> None:
    gen.SIZE = GRID_SIZE
    pid = gen.post("/prompt", {"prompt": gen.graph(prompt, seed, "hie_batch")})["prompt_id"]
    t0 = time.time()
    while time.time() - t0 < gen.TIMEOUT_S:
        hist = json.loads(gen.get(f"/history/{pid}"))
        if pid in hist:
            status = hist[pid].get("status", {})
            if status.get("status_str") == "error":
                raise RuntimeError(json.dumps(status)[:600])
            imgs = [im for node in hist[pid].get("outputs", {}).values()
                    for im in node.get("images", [])]
            if imgs:
                q = urllib.parse.urlencode({"filename": imgs[0]["filename"],
                                            "subfolder": imgs[0].get("subfolder", ""),
                                            "type": imgs[0].get("type", "output")})
                dest.write_bytes(gen.get(f"/view?{q}"))
                return
        time.sleep(gen.POLL_S)
    raise TimeoutError(dest.name)


def main() -> None:
    RAW_GRID.mkdir(parents=True, exist_ok=True)
    gen.OUT.mkdir(parents=True, exist_ok=True)
    log = RAW_GRID / f"batch_{LIST}.log"
    groups = [C[i:i + 4] for i in range(0, len(C), 4)]
    for g, group in enumerate(groups):
        if all((gen.OUT / f"{row[0]}.png").exists() for row in group):
            continue
        cells = "; ".join(f"{pos} quadrant: {row[1]}" for pos, row in zip(POSITIONS, group))
        grid_path = RAW_GRID / f"{LIST}_{g:02d}.png"
        t0 = time.time()
        try:
            render(PROMPT.format(cells=cells), SEED_BASE + g + (0 if LIST == 'candidates_100' else 5000), grid_path)
        except Exception as exc:  # keep going: one failed grid must not stop 24 others
            with open(log, "a", encoding="utf-8") as fh:
                fh.write(f"grid {g:02d} FAILED: {exc}\n")
            continue
        im = Image.open(grid_path).convert("RGB")
        hw, hh = im.width // 2, im.height // 2
        origins = [(0, 0), (hw, 0), (0, hh), (hw, hh)]
        for (x, y), row in zip(origins, group):
            im.crop((x, y, x + hw, y + hh)).save(gen.OUT / f"{row[0]}.png")
        with open(log, "a", encoding="utf-8") as fh:
            fh.write(f"grid {g:02d} ok in {time.time() - t0:.0f}s: "
                     + ", ".join(r[0] for r in group) + "\n")
    print("batch done")


if __name__ == "__main__":
    main()
