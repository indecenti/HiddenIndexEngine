"""Turn the Qwen renders in scratch/gen_assets/raw/ into Malonno catalog objects.

rembg -> crop to the alpha bounding box -> longest side ASSET_MAX_SIDE (like the
objects already in games/Malonno_Survivors/objects/) -> PNG in the game folder,
entry in objects_catalog.json and obj_<id> names in the five game language files.
Only the given ids are touched; an existing id is never overwritten.
"""
import json
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(r"G:\HIE git")
sys.path.insert(0, str(ROOT))
from engine.utils import safe_write_json  # noqa: E402

RAW = Path(__file__).resolve().parents[4] / "scratch" / "gen_assets" / "raw"
def _arg(name: str, default: str) -> str:
    """--name=value from the command line (the rest are object ids)."""
    for a in sys.argv[1:]:
        if a.startswith(f"--{name}="):
            return a.split("=", 1)[1]
    return default


GAME = ROOT / "games" / _arg("game", "Malonno_Survivors")
ASSET_MAX_SIDE = 260
ALPHA_PAD = 2

# id: (detection, size, hint_delay, tags, names en/it/de/es/fr)
ENTRIES = {
    "rosary": ("rect", (55, 55), 30, ["religione", "legno", "accessorio", "vintage", "medio"],
               ["Rosary", "Rosario", "Rosenkranz", "Rosario", "Chapelet"]),
    "old_postcard": ("rect", (55, 38), 30, ["carta", "viaggio", "foto", "vintage", "medio"],
                     ["Old Postcard", "Cartolina d'Epoca", "Alte Postkarte", "Postal Antigua",
                      "Vieille Carte Postale"]),
    "hip_flask": ("rect", (30, 45), 30, ["metallo", "bevanda", "contenitore", "vintage", "medio"],
                  ["Hip Flask", "Fiaschetta", "Flachmann", "Petaca", "Flasque"]),
    "cowbell": ("rect", (40, 55), 30, ["ottone", "cuoio", "montagna", "antico", "medio"],
                ["Cowbell", "Campanaccio", "Kuhglocke", "Cencerro", "Cloche de Vache"]),
    "rusty_padlock": ("rect", (30, 38), 25, ["ferro", "metallo", "sicurezza", "antico", "piccolo"],
                      ["Rusty Padlock", "Lucchetto Arrugginito", "Rostiges Vorhängeschloss",
                       "Candado Oxidado", "Cadenas Rouillé"]),
    "crampons": ("rect", (60, 45), 35, ["metallo", "cuoio", "montagna", "attrezzatura", "sport",
                                        "vintage", "medio"],
                 ["Crampons", "Ramponi", "Steigeisen", "Crampones", "Crampons"]),
    "vintage_thermos": ("rect", (25, 70), 30, ["metallo", "bevanda", "contenitore", "militare",
                                               "vintage", "medio"],
                        ["Vintage Thermos", "Thermos d'Epoca", "Alte Thermoskanne",
                         "Termo Antiguo", "Thermos Ancien"]),
    "wooden_crucifix": ("rect", (30, 50), 30, ["legno", "religione", "horror", "antico", "medio"],
                        ["Wooden Crucifix", "Crocifisso di Legno", "Holzkruzifix",
                         "Crucifijo de Madera", "Crucifix en Bois"]),
    "brass_door_knocker": ("rect", (45, 55), 30, ["ottone", "metallo", "decorazione", "antico", "medio"],
                           ["Brass Door Knocker", "Battiporta in Ottone", "Messing-Türklopfer",
                            "Aldaba de Latón", "Heurtoir en Laiton"]),
    "wire_spectacles": ("rect", (60, 25), 35, ["metallo", "vetro", "accessorio", "vintage", "medio"],
                        ["Wire Spectacles", "Occhiali d'Epoca", "Alte Drahtbrille",
                         "Gafas Antiguas", "Lunettes Anciennes"]),
    "hand_sickle": ("rect", (60, 40), 30, ["metallo", "legno", "attrezzo", "antico", "medio"],
                    ["Sickle", "Falcetto", "Sichel", "Hoz", "Faucille"]),
    "tobacco_tin": ("rect", (45, 30), 30, ["metallo", "contenitore", "vintage", "medio"],
                    ["Tobacco Tin", "Scatola di Tabacco", "Tabakdose", "Lata de Tabaco",
                     "Boîte à Tabac"]),
    "war_medal": ("rect", (22, 40), 25, ["metallo", "militare", "decorazione", "vintage", "piccolo"],
                  ["War Medal", "Medaglia al Valore", "Tapferkeitsmedaille", "Medalla al Valor",
                   "Médaille de Guerre"]),
}
LANGS = ("en", "it", "de", "es", "fr")

# The 100-object batch (generate_batch.py): all rendered on chroma green.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import importlib  # noqa: E402
_BATCH = importlib.import_module(_arg("list", "candidates_100")).C
for _id, _what, _size, _tags, _names in _BATCH:
    ENTRIES.setdefault(_id, ("rect", _size, 30, _tags, _names))
BATCH_IDS = {row[0] for row in _BATCH}


KEY_FULL = 9.0      # colour distance to the background below which a pixel is background
KEY_SOFT = 22.0     # ... and above which it is fully object (soft ramp in between)
OPAQUE_FROM = 250   # rembg leaves the object at alpha 254: snap it to 255


def background_key(img: Image.Image, alpha: Image.Image) -> Image.Image:
    """rembg keeps the background enclosed by the object (inside the loops of a
    rosary, between the arms of a crampon). The render has a flat known
    background, so every pixel of (almost exactly) its colour is made
    transparent too, with a soft ramp; the result never makes a pixel more
    opaque than rembg did."""
    import numpy as np
    rgb = np.asarray(img, dtype=np.float32)
    border = np.concatenate([rgb[:8].reshape(-1, 3), rgb[-8:].reshape(-1, 3),
                             rgb[:, :8].reshape(-1, 3), rgb[:, -8:].reshape(-1, 3)])
    bg = np.median(border, axis=0)
    dist = np.sqrt(((rgb - bg) ** 2).sum(axis=2))
    key = np.clip((dist - KEY_FULL) / (KEY_SOFT - KEY_FULL), 0.0, 1.0) * 255.0
    a = np.asarray(alpha, dtype=np.float32)
    a = np.minimum(a, key)
    a[a >= OPAQUE_FROM] = 255.0
    return Image.fromarray(a.astype(np.uint8), "L")


GREEN_BG = {"rosary", "crampons",   # rendered on chroma green (see generate_qwen21.py)
            "brass_door_knocker", "wire_spectacles", "hand_sickle", "tobacco_tin"}  # 2x2 grid
GREEN_FULL = 40.0   # green excess above which a pixel is background
GREEN_SOFT = 12.0   # ... below which it is object
DESPILL_MARGIN = 6.0
SHADOW_MAX_RGB = 26      # a contact shadow is darker than this ...
SHADOW_MAX_ALPHA = 200   # ... and less opaque than this
GREEN_FULL_SHARE = 0.75  # of the backdrop's green excess: fully transparent
GREEN_SOFT_SHARE = 0.45  # ... and fully opaque below this share


def green_key(img: Image.Image) -> Image.Image:
    """Chroma key: alpha from the green excess g - max(r, b), and despill (the
    green cast on the edges is clamped to the other two channels)."""
    import numpy as np
    rgb = np.asarray(img, dtype=np.float32).copy()
    excess = rgb[..., 1] - np.maximum(rgb[..., 0], rgb[..., 2])
    # Thresholds relative to the backdrop's own green (median of the border):
    # a green reflection on metal (the side of a tin, the ball of a knocker)
    # is far less green than the backdrop and must stay opaque.
    border = np.concatenate([excess[:8].ravel(), excess[-8:].ravel(),
                             excess[:, :8].ravel(), excess[:, -8:].ravel()])
    bg_excess = max(GREEN_FULL, float(np.median(border)))
    full, soft = bg_excess * GREEN_FULL_SHARE, bg_excess * GREEN_SOFT_SHARE
    alpha = 1.0 - np.clip((excess - soft) / (full - soft), 0.0, 1.0)
    # Despill: the green light the backdrop throws on glossy parts (the rosary
    # beads came out olive) - green may not exceed the mean of red and blue.
    rgb[..., 1] = np.minimum(rgb[..., 1], (rgb[..., 0] + rgb[..., 2]) / 2.0 + DESPILL_MARGIN)
    a = alpha * 255.0
    # Contact shadow the render paints on the backdrop: near black and only
    # partly covering (after the key). Object edges are never both.
    shadow = (rgb.max(axis=2) < SHADOW_MAX_RGB) & (a < SHADOW_MAX_ALPHA)
    a[shadow] = 0.0
    a[a >= OPAQUE_FROM] = 255.0
    out = np.dstack([rgb, a]).astype(np.uint8)
    return Image.fromarray(out, "RGBA")


REF_GREY = Path(__file__).resolve().parents[4] / "scratch" / "gen_assets" / "raw_grey"
# Objects whose colour is taken back from their grey render (glossy wood picks up
# the green; the crampons' steel does not need it and turns bluish with it).
COLOUR_FROM_GREY = {"rosary"}
QUADRANT_TRIM = 14   # px cut from each side of a grid quadrant
GRID_IDS = {"brass_door_knocker", "wire_spectacles", "hand_sickle", "tobacco_tin"}
REF_DARK_LUM = 120   # object pixels of the grey reference (its kept background is lighter)


def match_colour(out: Image.Image, ref_path: Path) -> Image.Image:
    """Per-channel gain that brings the object's mean colour to the one of its
    grey-backdrop render (the green light tints glossy materials: the rosary
    beads came out olive)."""
    import numpy as np
    import rembg
    ref = np.asarray(rembg.remove(Image.open(ref_path).convert("RGB"))).astype(np.float32)
    ref_px = ref[(ref[..., 3] > 250) & (ref[..., :3].mean(axis=2) < REF_DARK_LUM)][:, :3]
    cur = np.asarray(out).astype(np.float32)
    cur_px = cur[(cur[..., 3] > 250) & (cur[..., :3].mean(axis=2) < REF_DARK_LUM)][:, :3]
    if not len(ref_px) or not len(cur_px):
        return out
    gain = ref_px.mean(0) / np.maximum(1.0, cur_px.mean(0))
    cur[..., :3] = np.clip(cur[..., :3] * gain, 0, 255)
    return Image.fromarray(cur.astype(np.uint8), "RGBA")


def cut_out(src: Path, dest: Path) -> tuple[int, int]:
    img = Image.open(src).convert("RGB")
    if src.stem in BATCH_IDS or src.stem in GRID_IDS:
        # A quadrant of a grid: the model often draws the gutter as a thin light
        # line on the quadrant border, which the key keeps. Trim it off.
        m = QUADRANT_TRIM
        img = img.crop((m, m, img.width - m, img.height - m))
    if src.stem in GREEN_BG or src.stem in BATCH_IDS:
        out = green_key(img)
        if src.stem in COLOUR_FROM_GREY and (REF_GREY / src.name).exists():
            out = match_colour(out, REF_GREY / src.name)
    else:
        import rembg
        out = rembg.remove(img)
        out.putalpha(background_key(img, out.getchannel("A")))
    box = out.getchannel("A").point(lambda a: 255 if a > 8 else 0).getbbox()
    if not box:
        raise RuntimeError(f"{src.name}: nothing left after background removal")
    l, t, r, b = box
    out = out.crop((max(0, l - ALPHA_PAD), max(0, t - ALPHA_PAD),
                    min(out.width, r + ALPHA_PAD), min(out.height, b + ALPHA_PAD)))
    k = ASSET_MAX_SIDE / max(out.size)
    if k < 1:
        out = out.resize((max(1, round(out.width * k)), max(1, round(out.height * k))),
                         Image.LANCZOS)
    out.save(dest)
    return out.size


def main(ids: list[str]) -> None:
    cat_path = GAME / "objects_catalog.json"
    catalog = json.loads(cat_path.read_text(encoding="utf-8"))
    existing = {o["id"] for o in catalog["objects"]}
    added = []
    for obj_id in ids:
        det, size, hint, tags, names = ENTRIES[obj_id]
        if obj_id in existing:
            if "--redo" in sys.argv:
                print(f"{obj_id}: {cut_out(RAW / f'{obj_id}.png', GAME / 'objects' / f'{obj_id}.png')} (image redone)")
            else:
                print(f"{obj_id}: already in the catalog, skipped")
            continue
        src = RAW / f"{obj_id}.png"
        dest = GAME / "objects" / f"{obj_id}.png"
        if dest.exists() and "--redo" not in sys.argv:
            print(f"{obj_id}: {dest.name} already exists, skipped")
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        wh = cut_out(src, dest)
        entry = {"id": obj_id, "label_key": f"obj_{obj_id}", "icon": f"objects/{obj_id}.png",
                 "default_detection": det, "default_width": size[0], "default_height": size[1],
                 "default_hint_delay": hint, "tags": sorted(tags), "style": "real"}
        catalog["objects"].append(entry)
        added.append((obj_id, names))
        print(f"{obj_id}: {wh[0]}x{wh[1]} px")
    if not added:
        return
    assert safe_write_json(cat_path, catalog)
    for i, lang in enumerate(LANGS):
        p = GAME / "strings" / f"{lang}.json"
        table = json.loads(p.read_text(encoding="utf-8"))
        for obj_id, names in added:
            table.setdefault(f"obj_{obj_id}", names[i])
        assert safe_write_json(p, table)
        with open(p, "a", encoding="utf-8") as fh:
            fh.write("\n")
    print(f"registered {len(added)} objects")


if __name__ == "__main__":
    ids = [a for a in sys.argv[1:] if not a.startswith("--")]
    main(ids or list(ENTRIES))
