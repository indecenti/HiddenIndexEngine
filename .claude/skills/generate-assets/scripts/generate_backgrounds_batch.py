"""Render every scene of a scenes module (default scenes_ultimo_treno) with
generate_background.py, skipping the ones already in scratch/gen_assets/backgrounds/."""
import importlib
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
OUT = HERE.parents[3] / "scratch" / "gen_assets" / "backgrounds"

mod = importlib.import_module(sys.argv[1] if len(sys.argv) > 1 else "scenes_ultimo_treno")
for i, (_level, scene_id, what, _names) in enumerate(mod.SCENES):
    if (OUT / f"{scene_id}.png").exists():
        continue
    subprocess.run([sys.executable, str(HERE / "generate_background.py"), scene_id, what,
                    str(5000 + i)], check=False)
print("backgrounds done")
