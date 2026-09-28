"""Scene background (no findable objects) with Qwen-Image 2.1, 16:9 at 3840x2160.

Native render GEN_W x GEN_H at BG_STEPS, then in PIL: light gaussian blur, Lanczos
2x, unsharp mask, centre crop to exactly 16:9. No model upscaler: 4x-UltraSharp
re-creates a fine grid pattern on dark smooth surfaces (checked at 100%), even from
a softened input. Output: scratch/gen_assets/backgrounds/<name>.png
Usage: python generate_background.py <name> "<scene description>" [seed] [--painted | --hog] [--hq]
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
# Painted variant: classic hidden object art - hand painted, slightly stylised, rich
# warm colour - but with the same material rendering and soft light as the library
# objects, so they do not look pasted on.
STYLE_PAINTED = ("{what}. Classic hidden object game background, semi-realistic "
                 "digital art: realistic shapes, materials and lighting with a light painted "
                 "finish and subtle brush texture, polished and clean like a premium hidden "
                 "object game, rich warm colours, soft glow from lamps, cosy mysterious "
                 "atmosphere, calm composition with a few large elements and free surfaces - "
                 "tables, shelves, counters and floor left mostly empty so objects can be "
                 "placed later - finely detailed, crisp high resolution rendering of wood grain, "
                 "brass and fabric, balanced warm lighting with readable mid tones, "
                 "cinematic wide view, bare walls with no pictures, no frames, "
                 "no posters, no people, no readable text, no watermark, no logo")
# Hidden object photographic variant (--hog): the same photographic rendering as the
# library objects (real style) - no painted finish - but staged like a premium hidden
# object scene: a clear focal point, depth layers, warm practical lights, rich but
# tidy set dressing and many free surfaces at different heights.
STYLE_HOG = ("{what}. Premium hidden object game scene, photorealistic cinematic "
             "interior photography style, real materials with natural texture (aged wood, "
             "brass, stone, fabric, glass), rich warm practical lighting from lamps and "
             "windows with gentle falloff into soft shadows, inviting mysterious mood, "
             "clear focal point and three depth layers, tidy set dressing with free "
             "surfaces at different heights - tables, shelves, counters, window sills, "
             "floor - left mostly empty so objects can be placed later, crisp fine detail, "
             "wide angle eye level view, balanced exposure with readable mid tones, bare "
             "walls with no posters, no people, no readable text, no watermark, no logo")
NEGATIVE = ("people, characters, clutter, crowded, chaotic, too many details, piles of objects, many posters, signs, billboards, wall covered in pictures, "
            "readable text, watermark, logo, blurry, frame, border")
BG_STEPS = 35          # more than the 25 of the objects: backgrounds live on detail
SOFTEN = 0.5           # gaussian radius before the 2x resize (kills the model's grid)
SHARPEN = dict(radius=2.2, percent=70, threshold=2)
# --hq: maximum quality. Larger native render (less upscale, more real detail) and
# more sampling steps; the upscale factor drops from 2x to 1.5x.
HQ_W, HQ_H = 2560, 1440
HQ_STEPS = 50
HQ_SHARPEN = dict(radius=1.6, percent=60, threshold=2)


def graph(prompt: str, seed: int, hq: bool = False) -> dict:
    g = gen.graph(prompt, seed, "hie_bg")
    w, h = (HQ_W, HQ_H) if hq else (GEN_W, GEN_H)
    g["474"]["inputs"].update({"width": w, "height": h})
    g["471"]["inputs"]["negative_prompt"] = NEGATIVE
    g["476"]["inputs"]["steps"] = HQ_STEPS if hq else BG_STEPS
    return g


def main() -> None:
    painted = "--painted" in sys.argv
    hq = "--hq" in sys.argv
    hog = "--hog" in sys.argv
    args = [a for a in sys.argv[1:] if a not in ("--painted", "--hq", "--hog")]
    name, what = args[0], args[1]
    seed = int(args[2]) if len(args) > 2 else 2026
    style = STYLE_PAINTED if painted else STYLE_HOG if hog else STYLE
    OUT.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    pid = gen.post("/prompt", {"prompt": graph(style.format(what=what), seed, hq)})["prompt_id"]
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
    im = im.resize((OUT_W, h2), Image.LANCZOS).filter(
        ImageFilter.UnsharpMask(**(HQ_SHARPEN if hq else SHARPEN)))
    top = (h2 - OUT_H) // 2
    im.crop((0, top, OUT_W, top + OUT_H)).save(dest)
    print(f"{dest} {OUT_W}x{OUT_H} in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
