"""Export the object libraries (real, cartoon) as WebP for the IndexHub CDN.

The three global catalogs become one shared library that any web game can use:
https://cdn.indexhub.it/libreria/<style>-<stem>.avif (and .webp for old browsers), plus `libreria.json` with ids,
names in the five platform languages, tags, real size in cm (when known) and pixel size.

- Objects listed in engine/data/cdn_library_exclude.json (ids or fnmatch patterns) stay out: real brands, logos,
  licensed characters, film posters, faces of real people, broken sprites (checked on
  contact sheets before every publication; reasons are kept in the file).
- Same pixel size as the PNG (the libraries are already at game resolution).
- Formats chosen on measurements (126 sprites, PSNR/SSIM on grey and white, 3x zoom of the
  worst case): AVIF q85 keeps the paper grain of the PNG at ~14% of its weight; WebP q94
  (~26%) is the fallback for browsers without AVIF; WebP below q90 visibly smooths texture.
- Upload from the IndexHub repo: bash deploy/installa_store.sh media-gioco <out> libreria

Usage: python tools/export_cdn_library.py [out_dir]   (default scratch/cdn_library)
"""
from __future__ import annotations

import json
import logging
import fnmatch
import re
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from engine.utils import safe_write_json  # noqa: E402

log = logging.getLogger("export_cdn_library")

ENGINE = ROOT / "engine"
ASSETS = ENGINE / "assets"
DATA = ENGINE / "data"
# Line art stays off the CDN (owner's choice): it is only used inside the games.
CATALOGS = {  # CDN style prefix -> catalog file
    "reale": DATA / "global_real_catalog.json",
    "cartoon": DATA / "global_cartoon_catalog.json",
}
EXCLUDE = DATA / "cdn_library_exclude.json"
SIZES_CM = DATA / "real_sizes_cm.json"          # curated by hand (Malonno placement): wins
LIBRARY_SIZES_CM = DATA / "library_sizes_cm.json"  # estimated longest real side of every object
LANGS = ("it", "en", "de", "es", "fr")  # the IndexHub platform languages
CDN_DIR = "libreria"
CDN_BASE = f"https://cdn.indexhub.it/{CDN_DIR}/"
LIBRARY_VERSION = 1
AVIF_QUALITY = 85
AVIF_SPEED = 4           # encoder effort (0 slowest .. 10 fastest)
WEBP_QUALITY = 94
WEBP_ALPHA_QUALITY = 100
WEBP_METHOD = 6          # slowest, smallest
FORMATS = ("avif", "webp")
CDN_NAME = re.compile(r"^[A-Za-z0-9._-]+$")  # what the CDN nginx location accepts
DETECTION_KEYS = ("default_detection", "default_width", "default_height", "default_radius",
                  "default_hint_delay", "shape")


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def encode(src: Path, dest_stem: Path) -> None:
    """Write <dest_stem>.avif and .webp when missing or older than the PNG."""
    im = Image.open(src).convert("RGBA")
    for fmt in FORMATS:
        dest = dest_stem.parent / f"{dest_stem.name}.{fmt}"
        if dest.exists() and dest.stat().st_mtime >= src.stat().st_mtime:
            continue
        if fmt == "avif":
            im.save(dest, "AVIF", quality=AVIF_QUALITY, speed=AVIF_SPEED)
        else:
            im.save(dest, "WEBP", quality=WEBP_QUALITY, alpha_quality=WEBP_ALPHA_QUALITY,
                    method=WEBP_METHOD)


def export(out: Path) -> dict:
    lib_dir = out / CDN_DIR
    lib_dir.mkdir(parents=True, exist_ok=True)
    strings = {lang: load_json(ASSETS / "strings" / f"{lang}.json") for lang in LANGS}
    sizes = {k: v for k, v in load_json(LIBRARY_SIZES_CM).items() if not k.startswith("_")} if LIBRARY_SIZES_CM.exists() else {}
    sizes.update({k: v for k, v in load_json(SIZES_CM).items() if not k.startswith("_")})
    patterns = load_json(EXCLUDE)["ids"]
    entries: list[dict] = []
    seen_files: set[str] = set()
    skipped = 0
    jobs: list[tuple[Path, Path]] = []
    for style, catalog in CATALOGS.items():
        for obj in load_json(catalog)["objects"]:
            src = ASSETS / obj["icon"]
            stem = src.stem
            if any(fnmatch.fnmatchcase(n, p) for p in patterns for n in (obj["id"], stem)):
                skipped += 1
                continue
            name = f"{style}-{stem}"
            if name in seen_files or not src.exists():
                continue  # same image listed twice in a catalog
            if not CDN_NAME.match(name + ".avif"):
                log.warning("name not accepted by the CDN, skipped: %s", name)
                continue
            seen_files.add(name)
            jobs.append((src, lib_dir / name))
            with Image.open(src) as im:
                width, height = im.size
            key = obj["label_key"]
            entry = {"id": obj["id"], "file": name, "style": style, "w": width,
                     "h": height, "tags": obj.get("tags", []),
                     "names": {lang: strings[lang].get(key, obj["id"]) for lang in LANGS}}
            if obj["id"] in sizes:
                entry["cm"] = sizes[obj["id"]]
            entry.update({k: obj[k] for k in DETECTION_KEYS if k in obj})
            entries.append(entry)
    with ProcessPoolExecutor() as pool:
        list(pool.map(encode, *zip(*jobs), chunksize=16))
    # files from an earlier export that are no longer in the library (now excluded)
    for old in lib_dir.iterdir():
        if old.stem not in seen_files:
            old.unlink()
    library = {"version": LIBRARY_VERSION, "base": CDN_BASE, "formats": list(FORMATS),
               "langs": list(LANGS),
               "count": len(entries), "objects": entries}
    safe_write_json(out / "libreria.json", library, indent=None)
    log.info("%d objects exported, %d excluded -> %s", len(entries), skipped, lib_dir)
    return library


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "scratch" / "cdn_library"
    export(out)


if __name__ == "__main__":
    main()
