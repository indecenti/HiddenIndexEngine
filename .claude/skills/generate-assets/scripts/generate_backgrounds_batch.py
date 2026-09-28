"""Render every scene of a scenes module (default scenes_ultimo_treno) with
generate_background.py, skipping the ones already in scratch/gen_assets/backgrounds/.

Usage: python generate_backgrounds_batch.py [module] [--painted | --hog] [--hq] [--prefix=<p>]
Output name is <prefix><scene_id>.png, so a restyled pass never overwrites the
previous renders.
"""
import importlib
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
OUT = HERE.parents[3] / "scratch" / "gen_assets" / "backgrounds"
SEED_BASE = 5000

flags = [a for a in sys.argv[1:] if a in ("--painted", "--hog", "--hq")]
prefix = next((a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--prefix=")), "")
positional = [a for a in sys.argv[1:] if not a.startswith("--")]
mod = importlib.import_module(positional[0] if positional else "scenes_ultimo_treno")
for i, (_level, scene_id, what, _names) in enumerate(mod.SCENES):
    name = f"{prefix}{scene_id}"
    if (OUT / f"{name}.png").exists():
        continue
    subprocess.run([sys.executable, str(HERE / "generate_background.py"), name, what,
                    str(SEED_BASE + i), *flags], check=False)
print("backgrounds done")
