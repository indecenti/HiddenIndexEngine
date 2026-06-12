import os
import shutil
import subprocess
from pathlib import Path

base_path = Path(__file__).resolve().parent

print("Esecuzione PyInstaller...")
cmd = ["pyinstaller", "HiddenEditor.spec", "--noconfirm"]
subprocess.run(cmd, check=True)

print("Copia dei file esterni...")
dist_dir = base_path / "dist" / "HiddenEditor"
engine_dest = dist_dir / "engine"

if engine_dest.exists():
    shutil.rmtree(engine_dest)

print("Copia cartella engine (sorgenti inclusi)...")
shutil.copytree(
    base_path / "engine", engine_dest,
    ignore=shutil.ignore_patterns("__pycache__", "*.pyc")
)

main_src = base_path / "main.py"
if main_src.exists():
    shutil.copy2(main_src, dist_dir / "main.py")

(dist_dir / "games").mkdir(exist_ok=True)
(dist_dir / "saves").mkdir(exist_ok=True)

config_src = base_path / "config.ini"
if config_src.exists():
    shutil.copy2(config_src, dist_dir / "config.ini")

print("Build completata.")
