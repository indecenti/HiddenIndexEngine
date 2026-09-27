"""Scene background (no findable objects) with Qwen-Image 2.1, 16:9 at 3840x2160.

Native render GEN_W x GEN_H at BG_STEPS, then in PIL: light gaussian blur, Lanczos
2x, unsharp mask, centre crop to exactly 16:9. No model upscaler: 4x-UltraSharp
re-creates a fine grid pattern on dark smooth surfaces (checked at 100%), even from
a softened input. Output: scratch/gen_assets/backgrounds/<name>.png
Usage: python generate_background.py <name> "<scene description>" [seed]
"""
import json
import sys
import time
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import generate_qwen21 as gen  # noqa: E402

GEN_W, GEN_H = 1920, 1088
OUT_W, OUT_H = 3840, 2160
OUT = Path(__file__).resolve().parents[4] / "scratch" / "gen_assets" / "backgrounds"

# User preferences: FEW posters / signs (at most one small, unreadable) and NOT too
# full of detail - the first station was almost chaotic. A hidden object background is
# a calm stage with free surfaces; the objects are placed later in the editor.
STYLE = ("{what}. Hidden object game background, photorealistic, calm uncluttered "
         "composition with few large elements, clean and mostly empty surfaces - tables, "
         "shelves, counters, benches and floor left free so objects can be placed on them "
         "later - well rendered weathered materials (worn wood, chipped paint, old plaster), "
         "restrained detail, soft atmospheric lighting, cinematic wide view, sharp focus, "
         "at most one small faded poster, bare walls otherwise, no people, no readable text, "
         "no watermark, no logo")
NEGATIVE = ("people, characters, clutter, crowded, chaotic, too many details, piles of objects, many posters, signs, billboards, wall covered in pictures, "
            "readable text, watermark, logo, blurry, frame, border")
BG_STEPS = 35          # more than the 25 of the objects: backgrounds live on detail
SOFTEN = 0.5           # gaussian radius before the 2x resize (kills the model's grid)
SHARPEN = dict(radius=2.2, percent=70, threshold=2)


def graph(prompt: str, seed: int) -> dict:
    g = gen.graph(prompt, seed, "hie_bg")
    g["474"]["inputs"].update({"width": GEN_W, "height": GEN_H})
    g["471"]["inputs"]["negative_prompt"] = NEGATIVE
    g["476"]["inputs"]["steps"] = BG_STEPS
    return g


def main() -> None:
    name, what = sys.argv[1], sys.argv[2]
    seed = int(sys.argv[3]) if len(sys.argv) > 3 else 2026
    OUT.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    pid = gen.post("/prompt", {"prompt": graph(STYLE.format(what=what), seed)})["prompt_id"]
    while True:
        hist = json.loads(gen.get(f"/history/{pid}"))
        if pid in hist:
            st = hist[pid].get("status", {})
            if st.get("status_str") == "error":
                raise RuntimeError(json.dumps(st)[:800])
            imgs = [i for n in hist[pid]["outputs"].values() for i in n.get("images", [])]
            if imgs:
                q = urllib.parse.urlencode({"filename": imgs[0]["filename"],
                                            "subfolder": imgs[0].get("subfolder", ""),
                                            "type": imgs[0].get("type", "output")})
                dest = OUT / f"{name}.png"
                dest.write_bytes(gen.get(f"/view?{q}"))
                break
        time.sleep(gen.POLL_S)
    from PIL import Image, ImageFilter
    native = dest.with_name(f"{name}_native.png")
    dest.replace(native)
    im = Image.open(native).convert("RGB").filter(ImageFilter.GaussianBlur(SOFTEN))
    h2 = round(OUT_W * im.height / im.width)
    im = im.resize((OUT_W, h2), Image.LANCZOS).filter(ImageFilter.UnsharpMask(**SHARPEN))
    top = (h2 - OUT_H) // 2
    im.crop((0, top, OUT_W, top + OUT_H)).save(dest)
    print(f"{dest} {OUT_W}x{OUT_H} in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
