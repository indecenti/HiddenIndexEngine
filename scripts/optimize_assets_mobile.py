#!/usr/bin/env python3
"""Downscaling degli asset immagine PER LA SOLA BUILD MOBILE.

Va eseguito sulla COPIA di build (es. il workspace WSL $WORKSPACE/engine),
mai sul repo sorgente: gli originali full-res restano intatti per la build
desktop. Gli script rebuild_apk_*.sh lo invocano subito dopo il rsync.

Cosa fa:
  - Cerca ricorsivamente i PNG/JPG nella cartella passata come argomento.
  - Se il lato più lungo supera --max-dim, ridimensiona con LANCZOS (alta
    qualità) mantenendo l'aspect ratio e il canale alpha.
  - Riscrive i PNG con optimize=True. Solo downscale, mai upscale.
  - Idempotente: i file già entro il limite vengono saltati.

Il rendering interno del gioco è a ~540px di altezza con upscale GPU, quindi
1280px sul lato lungo sono ampiamente sufficienti anche con lo zoom intro.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    print("[optimize_assets] ERRORE: Pillow non installato (pip install pillow)", file=sys.stderr)
    sys.exit(1)

EXTS = {".png", ".jpg", ".jpeg"}


def human(n: int) -> str:
    f = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if f < 1024.0:
            return f"{f:.1f}{unit}"
        f /= 1024.0
    return f"{f:.1f}TB"


def optimize_file(path: Path, max_dim: int) -> tuple[int, int]:
    """Ritorna (bytes_prima, bytes_dopo). (0, 0) se saltato."""
    try:
        before = path.stat().st_size
        with Image.open(path) as img:
            w, h = img.size
            if max(w, h) <= max_dim:
                return 0, 0  # già entro il limite

            scale = max_dim / float(max(w, h))
            new_size = (max(1, round(w * scale)), max(1, round(h * scale)))

            mode = img.mode
            # LANCZOS non lavora su immagini con palette: converti a RGBA/RGB.
            if mode in ("P", "LA"):
                img = img.convert("RGBA")
            elif mode == "1":
                img = img.convert("L")

            resized = img.resize(new_size, Image.LANCZOS)

        ext = path.suffix.lower()
        if ext in (".jpg", ".jpeg"):
            if resized.mode in ("RGBA", "P", "LA"):
                resized = resized.convert("RGB")
            resized.save(path, format="JPEG", quality=88, optimize=True, progressive=True)
        else:
            resized.save(path, format="PNG", optimize=True)

        after = path.stat().st_size
        return before, after
    except Exception as exc:  # noqa: BLE001 - logga e continua sugli altri file
        print(f"[optimize_assets] SKIP {path}: {exc}", file=sys.stderr)
        return 0, 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("root", help="Cartella asset da ottimizzare (in-place, copia di build)")
    ap.add_argument("--max-dim", type=int, default=1280, help="Lato lungo massimo in px (default 1280)")
    args = ap.parse_args()

    root = Path(args.root)
    if not root.is_dir():
        print(f"[optimize_assets] ERRORE: {root} non è una cartella", file=sys.stderr)
        return 1

    total_before = total_after = touched = 0
    for path in sorted(root.rglob("*")):
        if path.suffix.lower() not in EXTS or not path.is_file():
            continue
        before, after = optimize_file(path, args.max_dim)
        if before:
            touched += 1
            total_before += before
            total_after += after
            print(f"  {path.relative_to(root)}: {human(before)} -> {human(after)}")

    saved = total_before - total_after
    print(
        f"[optimize_assets] {touched} file ridimensionati (max {args.max_dim}px), "
        f"risparmiati {human(saved)} ({human(total_before)} -> {human(total_after)})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
