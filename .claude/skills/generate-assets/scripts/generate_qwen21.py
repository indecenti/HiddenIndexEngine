"""Generate isolated object photos with Qwen-Image 2.1 through the local ComfyUI API.

Same graph as D:\\ComfyUI\\user\\default\\workflows\\Qwen-Image-2.1.json (GGUF Q8 unet,
qwen3vl text encoder, 2.1 VAE, euler/simple, 25 steps, cfg 1), with a SaveImage node.
Output: scratch/gen_assets/raw/<id>.png (1024x1024, neutral background, before rembg).
"""
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

SERVER = "http://127.0.0.1:8188"
OUT = Path(__file__).resolve().parents[4] / "scratch" / "gen_assets" / "raw"
STEPS = 25
SIZE = 1024
POLL_S = 2.0
TIMEOUT_S = 1800

STYLE = ("studio product photograph of a single {what}, the whole object fully visible and "
         "centered with generous empty margin around it, isolated on a plain seamless flat "
         "light grey background, soft even diffuse lighting, photorealistic, sharp focus, "
         "highly detailed realistic textures, aged and weathered, three-quarter view, "
         "no text, no logo, no hands, no other objects")
NEGATIVE = "multiple objects, text, watermark, logo, hands, cropped, frame, border, busy background"
# Objects with enclosed holes (the loops of a rosary, the frame of a crampon):
# rembg keeps the background inside them, so they are rendered on a chroma green
# that a colour key removes everywhere, holes included.
GREEN_BG = {"rosary", "crampons"}
STYLE_GREEN = STYLE.replace("isolated on a plain seamless flat light grey background",
                            "isolated on a solid pure chroma key green (#00FF00) background")

OBJECTS = {
    "rosary": "old wooden rosary with worn dark wooden beads and a small wooden cross, loosely coiled",
    "old_postcard": "yellowed vintage 1950s picture postcard of an alpine mountain village, "
                    "slightly bent corners, stained paper",
    "hip_flask": "vintage pewter hip flask with a screw cap, scratched and dented metal",
    "cowbell": "traditional alpine brass cowbell hanging from a worn brown leather collar strap",
    "rusty_padlock": "old heavy rusty iron padlock with its shackle closed, flaking rust",
    "crampons": "pair of vintage steel mountaineering crampons with old leather straps",
    "vintage_thermos": "vintage military green metal thermos flask with a cup cap, chipped paint",
    "wooden_crucifix": "small old carved wooden crucifix, dark varnished wood, cracked with age",
    "war_medal": "old bronze military valor medal with a faded striped ribbon, tarnished",
}


def graph(prompt: str, seed: int, prefix: str) -> dict:
    return {
        "478": {"class_type": "UnetLoaderGGUF", "inputs": {"unet_name": "qwen_image_2.1-Q8_0.gguf"}},
        "472": {"class_type": "CLIPLoader", "inputs": {
            "clip_name": "qwen3vl_8b_fp8_scaled.safetensors", "type": "qwen_image", "device": "default"}},
        "473": {"class_type": "VAELoader", "inputs": {"vae_name": "qwen_image_2.1_vae_bf16.safetensors"}},
        "471": {"class_type": "TextEncodeQwenImage21", "inputs": {
            "clip": ["472", 0], "prompt": prompt, "negative_prompt": NEGATIVE, "resolution": SIZE}},
        "474": {"class_type": "EmptyLatentImage", "inputs": {"width": SIZE, "height": SIZE, "batch_size": 1}},
        "476": {"class_type": "KSampler", "inputs": {
            "model": ["478", 0], "positive": ["471", 0], "negative": ["471", 1],
            "latent_image": ["474", 0], "seed": seed, "steps": STEPS, "cfg": 1.0,
            "sampler_name": "euler", "scheduler": "simple", "denoise": 1.0}},
        "475": {"class_type": "VAEDecode", "inputs": {"samples": ["476", 0], "vae": ["473", 0]}},
        "480": {"class_type": "SaveImage", "inputs": {"images": ["475", 0], "filename_prefix": prefix}},
    }


def post(path: str, payload: dict) -> dict:
    req = urllib.request.Request(SERVER + path, data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def get(path: str):
    with urllib.request.urlopen(SERVER + path, timeout=60) as r:
        return r.read()


def run(obj_id: str, what: str, seed: int) -> Path:
    prompt = (STYLE_GREEN if obj_id in GREEN_BG else STYLE).format(what=what)
    pid = post("/prompt", {"prompt": graph(prompt, seed, f"hie_{obj_id}")})["prompt_id"]
    t0 = time.time()
    while time.time() - t0 < TIMEOUT_S:
        hist = json.loads(get(f"/history/{pid}"))
        if pid in hist:
            outs = hist[pid].get("outputs", {})
            for node in outs.values():
                for img in node.get("images", []):
                    q = urllib.parse.urlencode({"filename": img["filename"],
                                                "subfolder": img.get("subfolder", ""),
                                                "type": img.get("type", "output")})
                    dest = OUT / f"{obj_id}.png"
                    dest.write_bytes(get(f"/view?{q}"))
                    return dest
            status = hist[pid].get("status", {})
            if status.get("status_str") == "error":
                raise RuntimeError(json.dumps(status)[:800])
        time.sleep(POLL_S)
    raise TimeoutError(obj_id)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    only = set(sys.argv[1:])
    for i, (obj_id, what) in enumerate(OBJECTS.items()):
        if only and obj_id not in only:
            continue
        t0 = time.time()
        dest = run(obj_id, what, seed=4242 + i)
        print(f"{obj_id}: {dest.name} in {time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
