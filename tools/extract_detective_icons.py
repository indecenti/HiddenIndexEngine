"""
tools/extract_detective_icons.py

Estrae il set detective dallo sprite-sheet (3x3, fondo verde chroma-key),
rimuove il verde con de-spill dei bordi, autocrop e canvas quadrato uniforme.
Output: engine/assets/themes/mystery/icons/<action>.png  (RGBA trasparenti)
"""
from pathlib import Path
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SHEET = ROOT / "tools" / "icon_sources" / "detective_sheet.png"
OUT = ROOT / "engine" / "assets" / "themes" / "mystery" / "icons"
CANVAS = 320          # canvas finale quadrato
CONTENT = 280         # lato max del contenuto dentro il canvas

# mappatura tile (row-major) -> (azione, flip_orizzontale)
TILES = [
    ("play", False),       # lente d'ingrandimento
    ("settings", False),   # ingranaggi
    ("quit", False),       # porta (uscita)
    ("levels", False),     # fascicolo SECRET (casi)
    ("back", True),        # freccia legno (flip -> punta a sinistra)
    ("audio", False),      # grammofono
    ("fullscreen", False), # cornice
    ("language", False),   # mappamondo
    ("new_game", False),   # pergamena sigillata
]


def chroma_remove(rgb: np.ndarray) -> np.ndarray:
    """rgb: HxWx3 uint8 -> HxWx4 con verde reso trasparente + de-spill."""
    r = rgb[..., 0].astype(np.int16)
    g = rgb[..., 1].astype(np.int16)
    b = rgb[..., 2].astype(np.int16)
    # "greenness": quanto il verde domina sugli altri canali
    greenness = g - np.maximum(r, b)
    alpha = np.full(g.shape, 255, dtype=np.float32)
    # verde pieno -> trasparente
    full = (greenness > 60) & (g > 80)
    alpha[full] = 0.0
    # bordo semi-verde -> alpha proporzionale
    edge = (~full) & (greenness > 18) & (g > 70)
    alpha[edge] = np.clip(255.0 * (60 - greenness[edge]) / 42.0, 0, 255)
    out = np.dstack([rgb.astype(np.float32), alpha]).astype(np.float32)
    # de-spill: dove il verde sborda, abbassalo al livello di max(r,b)
    spill = greenness > 0
    cap = np.maximum(r, b).astype(np.float32)
    gout = out[..., 1]
    gout[spill] = np.minimum(gout[spill], cap[spill] + 10)
    out[..., 1] = gout
    return np.clip(out, 0, 255).astype(np.uint8)


def autocrop(img: Image.Image) -> Image.Image:
    arr = np.array(img)
    mask = arr[..., 3] > 16
    if not mask.any():
        return img
    ys, xs = np.where(mask)
    return img.crop((xs.min(), ys.min(), xs.max() + 1, ys.max() + 1))


def main():
    sheet = Image.open(SHEET).convert("RGB")
    W, H = sheet.size
    tw, th = W / 3, H / 3
    OUT.mkdir(parents=True, exist_ok=True)
    print(f"Estraggo da {SHEET.name} ({W}x{H})")

    for idx, (action, flip) in enumerate(TILES):
        cx, cy = idx % 3, idx // 3
        # margine interno per scartare le linee di griglia/bordo verde del tile
        m = int(tw * 0.04)
        box = (int(cx * tw) + m, int(cy * th) + m,
               int((cx + 1) * tw) - m, int((cy + 1) * th) - m)
        tile = sheet.crop(box)
        rgba = Image.fromarray(chroma_remove(np.array(tile)), "RGBA")
        rgba = autocrop(rgba)
        if flip:
            rgba = rgba.transpose(Image.FLIP_LEFT_RIGHT)
        # scala mantenendo aspect dentro CONTENT, centra in canvas quadrato
        rgba.thumbnail((CONTENT, CONTENT), Image.LANCZOS)
        canvas = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
        ox = (CANVAS - rgba.width) // 2
        oy = (CANVAS - rgba.height) // 2
        canvas.alpha_composite(rgba, (ox, oy))
        canvas.save(OUT / f"{action}.png")
        print(f"  + {action}.png  ({rgba.width}x{rgba.height})")
    print("Fatto.")


if __name__ == "__main__":
    main()
