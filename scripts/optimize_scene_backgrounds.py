#!/usr/bin/env python3
"""Downscaling degli sfondi delle SCENE + riscalatura delle coordinate oggetti.

Le coordinate degli oggetti nelle scene (x, y, width, height, radius, corners)
sono in pixel dello sfondo ORIGINALE. Se si ridimensiona lo sfondo senza toccare
le coordinate, gli oggetti finiscono fuori posto e di dimensione errata.
Questo script ridimensiona lo sfondo di ogni scena e scala TUTTE le coordinate
degli oggetti dello stesso fattore, mantenendo il gioco corretto su mobile.

Va eseguito sulla COPIA di build (workspace), PRIMA dell'ottimizzatore generico,
così quest'ultimo trova gli sfondi già a dimensione finale e li salta.
Idempotente per build: il rsync ripristina ogni volta gli originali dal repo.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    print("[scene_bg] ERRORE: Pillow non installato", file=sys.stderr)
    sys.exit(1)

RASTER_EXTS = {".png", ".jpg", ".jpeg"}
SCALAR_KEYS = ("x", "y", "width", "height", "radius")


def scale_obj(obj: dict, f: float) -> None:
    for k in SCALAR_KEYS:
        v = obj.get(k)
        if isinstance(v, (int, float)):
            obj[k] = round(v * f, 2)
    # corners: lista di coppie [dx, dy] (offset di warp) in pixel
    corners = obj.get("corners")
    if isinstance(corners, list):
        new = []
        for c in corners:
            if isinstance(c, (list, tuple)) and len(c) == 2:
                new.append([round(c[0] * f, 2), round(c[1] * f, 2)])
            else:
                new.append(c)
        obj["corners"] = new


def process_scene(scene_json: Path, max_dim: int) -> tuple[int, int]:
    """Ritorna (bytes_prima, bytes_dopo) dello sfondo, (0,0) se saltato."""
    try:
        data = json.loads(scene_json.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"[scene_bg] SKIP {scene_json}: JSON non valido ({exc})", file=sys.stderr)
        return 0, 0

    bg = data.get("background", "")
    if not bg or Path(bg).suffix.lower() not in RASTER_EXTS:
        return 0, 0  # video o nessuno sfondo

    img_path = scene_json.parent / bg
    if not img_path.exists():
        return 0, 0

    try:
        before = img_path.stat().st_size
        with Image.open(img_path) as im:
            w, h = im.size
            long_side = max(w, h)
            if long_side <= max_dim:
                return 0, 0  # già piccolo: niente da fare
            f = max_dim / float(long_side)
            new_size = (max(1, round(w * f)), max(1, round(h * f)))
            mode = im.mode
            if mode in ("P", "LA"):
                im = im.convert("RGBA")
            resized = im.resize(new_size, Image.LANCZOS)

        ext = img_path.suffix.lower()
        if ext in (".jpg", ".jpeg"):
            if resized.mode in ("RGBA", "P", "LA"):
                resized = resized.convert("RGB")
            resized.save(img_path, format="JPEG", quality=88, optimize=True)
        else:
            resized.save(img_path, format="PNG", optimize=True)
        after = img_path.stat().st_size

        # Scala TUTTE le coordinate (oggetti E effetti/fumetti) dello stesso
        # fattore: anche gli effetti (bubble_tip, glint, smoke) sono in bg-space.
        n_obj = n_fx = 0
        for obj in data.get("objects", []):
            if isinstance(obj, dict):
                scale_obj(obj, f); n_obj += 1
        for fx in data.get("effects", []):
            if isinstance(fx, dict):
                scale_obj(fx, f); n_fx += 1
        scene_json.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

        print(f"  {img_path.name}: {w}x{h} -> {new_size[0]}x{new_size[1]} (f={f:.3f}), "
              f"{n_obj} oggetti + {n_fx} effetti riscalati")
        return before, after
    except Exception as exc:
        print(f"[scene_bg] SKIP {scene_json}: {exc}", file=sys.stderr)
        return 0, 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("games_root")
    ap.add_argument("--max-dim", type=int, default=1280)
    args = ap.parse_args()

    root = Path(args.games_root)
    if not root.is_dir():
        print(f"[scene_bg] ERRORE: {root} non è una cartella", file=sys.stderr)
        return 1

    tb = ta = n = 0
    for sj in sorted(root.rglob("scene.json")):
        b, a = process_scene(sj, args.max_dim)
        if b:
            n += 1; tb += b; ta += a
    saved = (tb - ta) / (1024 * 1024)
    print(f"[scene_bg] {n} scene ottimizzate, sfondi -{saved:.1f}MB "
          f"({tb/1024/1024:.1f}MB -> {ta/1024/1024:.1f}MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
