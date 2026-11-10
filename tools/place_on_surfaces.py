"""Place hidden objects on hand-marked surfaces, lit like the spot they sit in.

An alternative to the camouflage auto-scatter for scenes where it does not perform: the
level designer marks, per background, the lines objects can rest on (shelf planks, table
tops, window sills, steps, the floor) and how tall a typical object is on each line; the
tool does the rest.

- Contact: an object's bottom edge sits on its surface line (sunk a little), never floating.
- Light: `color_filter` (a per-pixel multiplier in both runtimes) is computed from the
  background around the spot, so objects darken in shadow, warm up under a lamp and turn
  blue in moonlight. Alpha stays high: they are real things in the room, not ghosts.
- Camouflage: every spot takes, among the objects still free, one of those whose colour
  is closest to the background around it.
- Replay: every object gets `alt_spots` more spots on the surfaces, all clear of each
  other, so any combination at runtime is free of overlaps
  (docs/engine/STORY_AND_REPLAY.md).
- Low light also takes colour away: `grayscale_factor` grows as the spot gets darker.
- Minigames: `"minigames": [{"catalog_id": ..., "minigame_id": ...}]` places themed
  trigger objects the same way; they are fixed goals (`always_show`).
- The bottom band covered by the HUD and the frame margins stay empty.

Surfaces live next to each scene in `surfaces.json` ({"surfaces": [...], optional "h_mul",
"light"}), drawn in the editor or by hand; the plan gives the objects (it may also carry
"surfaces" for a scene, the file wins). Plan (JSON, next to the game):

    {"defaults": {"count": 40, "goals": 15, "alt_spots": 2, "collectible": "rose_carved_pebble"},
     "scenes": [{"level": "...", "scene": "...", "seed": 7, "clue": "faded_letter",
                 "pool": ["salami", ...],
                 "surfaces": [{"p": [x0, y0, x1, y1], "h": 90, "kind": "shelf"}, ...]}]}

`p` is the resting line in background px (left to right), `h` the height in px of a
medium object standing there (it grows with nearness), `kind` one of shelf, table, floor,
sill, ledge (floor lets objects lie tilted). Optional per surface: "max": how many objects.
Optional per surface: "poses": ["lie", "flat"] limits what may rest there (a floor seen
steeply from above). Optional per scene: "h_mul" scales every surface height (aim at 35-55 px on a 1280x720
screen for a medium object).

Usage:
    python tools/place_on_surfaces.py <plan.json> [scene ...]             write scene.json
    python tools/place_on_surfaces.py <plan.json> --preview [scene ...]    PNG previews only
"""
from __future__ import annotations

import os

# The support model runs on the CPU (~10 s per background, cached): the GPU is usually
# busy with image or music generation and a CUDA session would wait on it. PLACE_GPU=1
# lets it use the GPU.
if os.environ.get("PLACE_GPU") != "1":
    os.environ["CUDA_VISIBLE_DEVICES"] = ""

import json
import logging
import math
import random
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

import numpy as np
from PIL import Image, ImageDraw

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from engine.catalog_manager import load_catalog  # noqa: E402
from engine.utils import safe_write_json  # noqa: E402

log = logging.getLogger("place_on_surfaces")

DEFAULTS = {"count": 40, "goals": 15, "alt_spots": 2, "hint_delay": 45,
            "collectible": None, "keep_minigames": False, "minigames": []}
# Real size: engine/data/real_sizes_cm.json (longest dimension in cm). A surface's "h" is
# the size in background px of a REF_CM object standing there. Objects missing from the
# table are not placed: the table is also the curation of what fits a realistic scene.
REF_CM = 20.0
REAL_SIZES = REPO / "engine" / "data" / "real_sizes_cm.json"
# Poses. Long thin things (tools, cutlery, weapons, umbrellas, keys) lie along the
# surface; flat paper lies flat, foreshortened with the 4-corner warp; the rest stands.
LIE_TAGS = {"attrezzo", "arma", "ombrello", "chiave", "posate"}
LIE_WORDS = ("bulb", "flask", "spoon", "ladle", "knife", "fork", "spatula", "pencil", "pen", "key", "saw",
             "rolling_pin", "screwdriver", "chisel", "hammer", "shears", "sickle", "file")
LIE_ASPECT = 0.6            # icon w/h below this, with a LIE tag or word, is laid down
LIE_JITTER = 8.0            # degrees around horizontal
FLAT_TAGS = {"carta", "foto", "mappa", "biglietto"}
FLAT_WORDS = ("pebble", "stone_fragment", "mold", "coin", "plate", "doily", "cards", "postcard", "letter", "photo",
              "ticket", "map", "newspaper", "envelope")
# Contact shadow (drawn by both runtimes under the object, see "shadow" in
# docs/engine/STORY_AND_REPLAY.md): width of the touching part of the shape, opacity
# lower where the spot is dark (there is less light to cast it).
SHADOW_BAND = 0.15          # bottom share of the shape whose width makes the shadow
SHADOW_WIDEN = 1.25
SHADOW_ALPHA = (95, 175)    # at light level LIGHT["min"] .. 1.0
TUCK_MAX = 1.2              # on areas: contact within this many object sizes of an edge
STAND_AREA_SHARE = 0.3      # far share of an area where upright objects may stand
LINE_END_MARGIN = 8         # px kept free at both ends of a line surface
SHADOW_ASPECT = 0.22        # ellipse height / width (same constant as the runtimes)
FLAT_SKIP_TAGS = {"libro", "contenitore"}
FLAT_DROP = 0.45            # share of the height the top edge drops (seen from above)
FLAT_NARROW = 0.10          # share of the width each top corner moves in (perspective)
# Camouflage audit, on a 1280x720 screen: every object must be findable but not obvious.
SCREEN_W = 1280
MIN_SCREEN_PX = 26          # longest side below this: too small to be fair
CLUE_MIN_SCREEN_PX = 44     # the story clue must be fair to find
SPECULAR_MAX = 1.3          # bright highlights (metal, glass) vs the bright part around
MAX_SCREEN_PX = 110         # above this: it fills the view, not hidden
# Value contrast with the surroundings (object luminance / local luminance after light):
CONTRAST_MAX = 1.35         # brighter than this: spotted at once (the bright spoon)
CONTRAST_MIN = 0.45         # darker than this: a black blob, unfair
LUM_MIN = 38.0              # lit object luminance (0..255) below this: invisible, unfair
CHROMA_MAX = 38.0           # saturation distance (Lab chroma) above local: a colour flare
SIZE_JITTER = (0.88, 1.08)
SINK = 0.05                 # share of the height sunk below the surface line
# Standing objects do not lean (a leaning bottle reads as falling); things lying on the
# floor may turn a little. The lowest point after rotation is what touches the line.
TILT = {"shelf": 1.5, "table": 2.0, "sill": 1.5, "ledge": 1.5, "floor": 10.0}
# Surface snap: the marked line moves to the strongest horizontal edge of the painting
# within this share of the surface height (a shelf front, a table edge, a sill).
SNAP_SHARE = 0.12
SNAP_MAX_PX = 14
MASK_SAMPLES = 3000         # opaque icon points kept for contact and extent
# Support map: pixels whose surface normal points up (Metric3D, the editor's scatter
# model), i.e. floors, table tops, the tops of crates. An "area" surface places objects
# only where the support map holds under the whole base.
UP_MIN = 0.5                # -normal_y above this: a horizontal, upward-facing surface
SUPPORT_ERODE = 12          # px the support map is shrunk (blurred model edges)
BASE_SAMPLES = 9            # points checked under an object's base
BASE_SUPPORTED = 0.8        # share of them that must stand on support
BASE_DEPTH = 10             # px under the base that must be support too
ELONGATED = 2.2             # principal-axis ratio from which a LIE object is laid down
GEOMETRY_CACHE = REPO / ".editor_cache" / "geometry"
OPAQUE = 40                 # alpha above which an icon pixel is the object
GAP = 6                     # px kept between two objects
SPREAD = 0.25               # extra side gap, share of the object width (no rows)
ROOM_PER_OBJECT = 1.5       # default surface capacity: one object per this many heights
HUD_BAND = 110 / 720        # bottom share of the screen covered by the HUD bar
EDGE = 0.02                 # frame margin share kept empty
TRIES = 60                  # spot samples per object
COLOR_TOP_K = 3             # pick among the k objects closest in colour to the spot
# Light balance (per scene override: "light": {"min", "gamma", "mix", "desat"}).
# Objects must read as part of the room AND stay findable: below LIGHT_MIN the eye
# loses them on a 720p screen, a strong hue cast or desaturation turns them into mud.
LIGHT = {"min": 0.62, "max": 1.0, "gamma": 0.4, "mix": 0.35, "desat": 0.3}
LIGHT_REF_PCT = 90          # background luminance percentile taken as full light

# Colours fade in low light: grayscale_factor = DESAT_MAX * (1 - light level), above a floor.
DESAT_MIN = 0.08
PREVIEW_W = 1920
SURFACES_FILE = "surfaces.json"   # per scene: {"surfaces": [...], "h_mul", "light"}


@dataclass
class Surface:
    x0: float
    y0: float
    x1: float
    y1: float
    h: float
    kind: str
    max: int
    h_near: float = 0.0     # areas: size at the bottom (near) edge; h is the far edge
    poses: tuple = ()       # allowed poses ("stand", "lie", "flat"); empty = all

    @property
    def is_area(self) -> bool:
        return self.kind == "area"

    def at(self, t: float, rng: Optional[random.Random] = None,
           back_only: bool = False) -> tuple[float, float]:
        if self.is_area and rng is not None:
            share = STAND_AREA_SHARE if back_only else 1.0
            return (self.x0 + (self.x1 - self.x0) * t,
                    self.y0 + (self.y1 - self.y0) * share * rng.random())
        return self.x0 + (self.x1 - self.x0) * t, self.y0 + (self.y1 - self.y0) * t

    def size_at(self, y: float) -> float:
        """Reference size at a contact height: areas grow from far to near."""
        if not self.is_area or self.y1 == self.y0:
            return self.h
        k = min(1.0, max(0.0, (y - self.y0) / (self.y1 - self.y0)))
        return self.h + (self.h_near - self.h) * k

    @property
    def length(self) -> float:
        if self.is_area:        # weight areas by their surface, like a long line
            return math.sqrt(abs(self.x1 - self.x0) * abs(self.y1 - self.y0)) * 2.0
        return math.hypot(self.x1 - self.x0, self.y1 - self.y0)


@dataclass
class Spot:
    x: float          # top-left, background px
    y: float
    w: float
    h: float
    rotation: float
    flip_x: bool
    color_filter: tuple[int, int, int]
    surface: int
    level: float = 1.0
    corners: Optional[list] = None
    pose: str = "stand"
    ext: tuple = (0.0, 0.0, 0.0, 0.0)   # opaque shape extent around the centre
    shadow: Optional[dict] = None        # {"dy", "w", "a"} in the spot's own px

    @property
    def box(self) -> tuple[float, float, float, float]:
        """Box of the visible shape, widened on the sides so objects never form rows."""
        cx, cy = self.x + self.w / 2, self.y + self.h / 2
        x0, x1, y0, y1 = self.ext
        side = GAP + SPREAD * (x1 - x0)
        top = cy + y0
        if self.corners:            # flat warp: the top edge dropped
            top = self.y + self.corners[0][1]
        return (cx + x0 - side, top - GAP, cx + x1 + side, cy + y1 + GAP)


def _overlap(a, b) -> bool:
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


class Background:
    def __init__(self, path: Path) -> None:
        self.img = Image.open(path).convert("RGB")
        self.arr = np.asarray(self.img).astype(np.float32)
        self.H, self.W = self.arr.shape[:2]
        lum = self.arr @ np.array([0.299, 0.587, 0.114], dtype=np.float32)
        self.lum_ref = max(1.0, float(np.percentile(lum, LIGHT_REF_PCT)))

    def patch_mean(self, x0: float, y0: float, x1: float, y1: float) -> np.ndarray:
        xa, xb = int(max(0, x0)), int(min(self.W, x1))
        ya, yb = int(max(0, y0)), int(min(self.H, y1))
        if xb <= xa or yb <= ya:
            return np.array([128.0, 128.0, 128.0])
        return self.arr[ya:yb, xa:xb].reshape(-1, 3).mean(axis=0)

    def load_support(self, path: Path,
                     model_factory: Optional[Callable[[], object]] = None) -> None:
        """Upward-facing surface mask from the Metric3D normals (cached per image).

        `model_factory` (optional) builds the model on a cache miss instead of
        get_best_model (the editor passes a CPU-only session)."""
        import hashlib
        GEOMETRY_CACHE.mkdir(parents=True, exist_ok=True)
        key = hashlib.sha1(path.read_bytes()).hexdigest()[:16]
        cache = GEOMETRY_CACHE / f"{key}.npz"
        if cache.exists():
            up = np.load(cache)["up"].astype(np.float32)
        else:
            if model_factory is not None:
                model = model_factory()
            else:
                from editor.tools.scatter_models import get_best_model
                model = get_best_model(REPO, force_tier=2, quick_benchmark=False)
            out = model.analyze(np.asarray(self.img))
            up = (-out["normals"][..., 1]).astype(np.float16)
            np.savez_compressed(cache, up=up)
            up = up.astype(np.float32)
        mask = up > UP_MIN
        if SUPPORT_ERODE > 0:
            import cv2
            k = np.ones((SUPPORT_ERODE * 2 + 1, SUPPORT_ERODE * 2 + 1), np.uint8)
            mask = cv2.erode(mask.astype(np.uint8), k) > 0
        self.support = mask
        import cv2
        # distance of every support pixel from the nearest non-support one (a wall, the
        # foot of a cabinet, a crate): objects hide tucked against things, not in the open
        self.support_dist = cv2.distanceTransform(mask.astype(np.uint8), cv2.DIST_L2, 5)

    def supported(self, x0: float, x1: float, y: float) -> bool:
        """True when the base from x0 to x1 at height y stands on the support map."""
        if getattr(self, "support", None) is None:
            return True
        xs = np.linspace(x0, x1, BASE_SAMPLES).astype(int).clip(0, self.W - 1)
        # the base and a band under it: on a surface, not on its blurred upper rim
        for dy in (0, BASE_DEPTH):
            yy = int(min(self.H - 1, max(0, y + dy)))
            if float(self.support[yy, xs].mean()) < BASE_SUPPORTED:
                return False
        return True

    def snap(self, x0: float, y0: float, x1: float, y1: float, reach: float) -> float:
        """Vertical shift that puts the line on the strongest horizontal edge nearby."""
        lum = self.arr @ np.array([0.299, 0.587, 0.114], dtype=np.float32)
        n = max(8, int(abs(x1 - x0) / 4))
        xs = np.linspace(x0, x1, n)
        ys = np.linspace(y0, y1, n)
        best, best_d = 0.0, 0
        for d in range(-int(reach), int(reach) + 1):
            yy = (ys + d).astype(int)
            xx = xs.astype(int).clip(0, self.W - 1)
            ok = (yy > 1) & (yy < self.H - 2)
            if not ok.any():
                continue
            g = np.abs(lum[yy[ok] + 1, xx[ok]] - lum[yy[ok] - 1, xx[ok]]).mean()
            # prefer the marked position when edges are equally strong
            g *= 1.0 - 0.15 * abs(d) / max(1.0, reach)
            if g > best:
                best, best_d = g, d
        return float(best_d)

    def light(self, x: float, y: float, w: float, h: float, cfg: Optional[dict] = None
              ) -> tuple[tuple[int, int, int], float]:
        """Multiplier from the background around the object (a box twice its size),
        and the light level 0..1 it stands for."""
        m = self.patch_mean(x - w / 2, y - h / 2, x + w * 1.5, y + h * 1.5)
        lum = float(m @ np.array([0.299, 0.587, 0.114]))
        lc = {**LIGHT, **(cfg or {})}
        level = min(lc["max"], max(lc["min"], (lum / self.lum_ref) ** lc["gamma"]))
        hue = m / max(1.0, float(m.max()))
        mult = (1 - lc["mix"]) + lc["mix"] * hue
        return tuple(int(round(255 * level * c)) for c in mult), level


class Icon:
    def __init__(self, path: Path) -> None:
        self.img = Image.open(path).convert("RGBA")
        a = np.asarray(self.img).astype(np.float32)
        alpha = a[..., 3:4] / 255.0
        self.mean = (a[..., :3] * alpha).reshape(-1, 3).sum(0) / max(1.0, float(alpha.sum()))
        self.lum = float(self.mean @ np.array([0.299, 0.587, 0.114]))
        lum_px = a[..., :3] @ np.array([0.299, 0.587, 0.114], dtype=np.float32)
        opaque = a[..., 3] > OPAQUE
        self.p90 = float(np.percentile(lum_px[opaque], 90)) if opaque.any() else self.lum
        self.aspect = self.img.width / self.img.height
        ys, xs = np.nonzero(a[..., 3] > OPAQUE)
        if len(xs) > MASK_SAMPLES:
            pick = np.random.default_rng(0).choice(len(xs), MASK_SAMPLES, replace=False)
            xs, ys = xs[pick], ys[pick]
        # opaque points, centred and normalised to the icon size (u, v in -0.5..0.5)
        self.u = (xs + 0.5) / self.img.width - 0.5
        self.v = (ys + 0.5) / self.img.height - 0.5
        # principal axis in pixels (y down): the CCW rotation that lays it horizontal
        px, py = self.u * self.img.width, self.v * self.img.height
        cov = np.cov(np.vstack([px, py])) if len(px) > 2 else np.eye(2)
        vals, vecs = np.linalg.eigh(cov)
        vx, vy = vecs[:, int(np.argmax(vals))]
        ang = math.degrees(math.atan2(vy, vx))
        self.lay_angle = (ang + 90.0) % 180.0 - 90.0     # in -90..90
        self.elongation = math.sqrt(max(vals) / max(1e-6, min(vals)))

    def base_width(self, w: float, h: float, rot: float) -> float:
        """Width of the bottom band of the turned shape (what touches the surface)."""
        t = math.radians(rot)
        X, Y = self.u * w, self.v * h
        xr = X * math.cos(t) + Y * math.sin(t)
        yr = -X * math.sin(t) + Y * math.cos(t)
        lo, hi = float(yr.min()), float(yr.max())
        band = yr >= hi - SHADOW_BAND * (hi - lo)
        return float(xr[band].max() - xr[band].min()) if band.any() else w

    def extent(self, w: float, h: float, rot: float) -> tuple[float, float, float, float]:
        """(min x, max x, min y, max y) of the opaque shape drawn w x h and turned `rot`
        degrees counter-clockwise (as both runtimes do), relative to its centre."""
        t = math.radians(rot)
        X, Y = self.u * w, self.v * h
        xr = X * math.cos(t) + Y * math.sin(t)
        yr = -X * math.sin(t) + Y * math.cos(t)
        return float(xr.min()), float(xr.max()), float(yr.min()), float(yr.max())


class Placer:
    def __init__(self, game_id: str) -> None:
        self.game_id = game_id
        self.game_path = REPO / "games" / game_id
        self.catalog = {c["id"]: c for c in load_catalog(game_id).get("objects", [])}
        self._icons: dict[str, Icon] = {}
        self.light_cfg: dict = {}
        self.real_sizes = {k: v for k, v in
                           json.loads(REAL_SIZES.read_text(encoding="utf-8")).items()
                           if not k.startswith("_")}

    def icon(self, cid: str) -> Optional[Icon]:
        if cid in self._icons:
            return self._icons[cid]
        entry = self.catalog.get(cid)
        if not entry or not entry.get("icon"):
            return None
        for base in (self.game_path, REPO / "engine" / "assets"):
            p = base / entry["icon"]
            if p.exists():
                self._icons[cid] = Icon(p)
                return self._icons[cid]
        return None

    def size_factor(self, cid: str) -> float:
        """Real size of the object (longest side) relative to REF_CM."""
        return float(self.real_sizes.get(cid, REF_CM)) / REF_CM

    def pose(self, cid: str) -> str:
        """'lie', 'flat' or 'stand'."""
        tags = set(self.catalog.get(cid, {}).get("tags", []))
        icon = self.icon(cid)
        if icon is None:
            return "stand"
        thin = icon.aspect < LIE_ASPECT or icon.elongation >= ELONGATED
        if any(w in cid for w in LIE_WORDS) or (thin and tags & LIE_TAGS):
            return "lie"
        if (tags & FLAT_TAGS and not tags & FLAT_SKIP_TAGS) or any(w in cid for w in FLAT_WORDS):
            return "flat"
        return "stand"

    @staticmethod
    def _chroma(rgb) -> float:
        r, g, b = (float(c) for c in rgb)
        return math.hypot(r - g, (r + g) / 2 - b) * 0.5

    # -- spots ------------------------------------------------------------------
    def _sample(self, rng: random.Random, bg: Background, surfaces: list[Surface],
                cid: str, size_mul: float, taken: list, counts: list[int],
                min_px: float = MIN_SCREEN_PX) -> Optional[Spot]:
        icon = self.icon(cid)
        if icon is None:
            return None
        weights = [s.length * (0 if counts[i] >= s.max else 1) for i, s in enumerate(surfaces)]
        if not any(weights):
            return None
        hud_y = bg.H * (1 - HUD_BAND)
        for _ in range(TRIES):
            i = rng.choices(range(len(surfaces)), weights=weights)[0]
            s = surfaces[i]
            pose = self.pose(cid)
            if s.poses and pose not in s.poses:
                continue            # this surface takes only some poses (e.g. a near floor)
            # the icons are shot near eye level: on a floor or a table top seen from above
            # an upright object looks lifted, so it stands only on the far band of an area
            cx, ly = s.at(rng.random(), rng, back_only=(pose == "stand"))
            longest = s.size_at(ly) * size_mul * rng.uniform(*SIZE_JITTER)
            on_screen = longest * SCREEN_W / bg.W
            if on_screen < min_px:                   # fair size floor on a 720p screen
                longest = min_px * bg.W / SCREEN_W
            elif on_screen > MAX_SCREEN_PX:
                longest = MAX_SCREEN_PX * bg.W / SCREEN_W
            if icon.aspect >= 1:
                w, h = longest, longest / icon.aspect
            else:
                w, h = longest * icon.aspect, longest
            corners = None
            if pose == "lie":
                # the shape's long axis horizontal, a little off, either way round
                rot = round(icon.lay_angle + rng.uniform(-LIE_JITTER, LIE_JITTER), 1)
            elif pose == "flat":
                rot = 0.0
            else:
                tilt = TILT.get(s.kind, 1.5)
                rot = round(rng.uniform(-tilt, tilt), 1)
            # the lowest opaque point of the turned shape touches the line, sunk by SINK
            ext = icon.extent(w, h, rot)
            sink = SINK * (ext[3] - ext[2])
            cy = ly + sink - ext[3]
            x, y = cx - w / 2, cy - h / 2
            if pose == "flat":
                # seen from above: the top edge drops and narrows, the bottom edge stays
                corners = [[round(FLAT_NARROW * w), round(FLAT_DROP * h)],
                           [-round(FLAT_NARROW * w), round(FLAT_DROP * h)], [0, 0], [0, 0]]
            if (x < bg.W * EDGE or x + w > bg.W * (1 - EDGE) or y < bg.H * EDGE
                    or y + h > hud_y):
                continue
            if s.is_area and (cx + ext[0] < min(s.x0, s.x1) or cx + ext[1] > max(s.x0, s.x1)):
                continue            # past the side of the area (a long saw off a table)
            if s.is_area and not bg.supported(cx + ext[0], cx + ext[1], ly + 2):
                continue            # the base would not stand on the floor / table top
            if s.is_area and getattr(bg, "support_dist", None) is not None:
                d = float(bg.support_dist[int(min(bg.H - 1, ly + 2)), int(min(bg.W - 1, cx))])
                if d > TUCK_MAX * s.size_at(ly):   # the surface's scale, not the object's
                    continue        # alone in the middle of the floor: obvious
            if not s.is_area:
                # the whole visible width on the board: nothing sticks out past its ends
                lo, hi = min(s.x0, s.x1) + LINE_END_MARGIN, max(s.x0, s.x1) - LINE_END_MARGIN
                if cx + ext[0] < lo or cx + ext[1] > hi:
                    continue
            flip = rng.random() < 0.5 and pose != "lie"
            if flip:                    # a mirrored shape: recompute the extent
                ext = (-ext[1], -ext[0], ext[2], ext[3])
            spot = Spot(x, y, w, h, rot, flip, (255, 255, 255), i,
                        corners=corners, pose=pose, ext=ext)
            if any(_overlap(spot.box, b) for b in taken):
                continue
            spot.color_filter, spot.level = bg.light(x, y, w, h, self.light_cfg)
            if not self._camouflaged(bg, icon, spot):
                continue
            lo_level = LIGHT["min"]
            k = min(1.0, max(0.0, (spot.level - lo_level) / max(1e-6, 1.0 - lo_level)))
            spot.shadow = {"dy": ext[3] - sink,
                           "w": icon.base_width(w, h, rot) * SHADOW_WIDEN,
                           "a": int(SHADOW_ALPHA[0] + (SHADOW_ALPHA[1] - SHADOW_ALPHA[0]) * k)}
            if pose == "flat":
                spot.shadow["a"] = int(spot.shadow["a"] * 0.6)
            return spot
        return None

    def _camouflaged(self, bg: Background, icon: "Icon", spot: Spot) -> bool:
        """Value and colour audit of a lit spot; dims a bright object toward its
        surroundings, refuses what stays a flare or turns into a black blob."""
        x, y, w, h = spot.x, spot.y, spot.w, spot.h
        local = bg.patch_mean(x - w / 2, y - h / 2, x + w * 1.5, y + h * 1.5)
        local_lum = max(1.0, float(local @ np.array([0.299, 0.587, 0.114])))
        mult = np.array(spot.color_filter, dtype=np.float32) / 255.0
        lit = icon.mean * mult
        ratio = float(lit @ np.array([0.299, 0.587, 0.114])) / local_lum
        if ratio > CONTRAST_MAX:                     # dim it down to the limit
            k = CONTRAST_MAX / ratio
            spot.color_filter = tuple(int(round(c * k)) for c in spot.color_filter)
            spot.level *= k
            lit = lit * k
            ratio = CONTRAST_MAX
        if ratio < CONTRAST_MIN or float(lit @ np.array([0.299, 0.587, 0.114])) < LUM_MIN:
            return False
        # highlights: a shiny tin pops out by its bright spots even with a fair mean
        xa, xb = int(max(0, x - w / 2)), int(min(bg.W, x + w * 1.5))
        ya, yb = int(max(0, y - h / 2)), int(min(bg.H, y + h * 1.5))
        if xb > xa and yb > ya:
            patch = bg.arr[ya:yb, xa:xb].reshape(-1, 3) @ np.array([0.299, 0.587, 0.114])
            local_p90 = max(1.0, float(np.percentile(patch, 90)))
            gain = float(np.mean(np.array(spot.color_filter) / 255.0))
            if icon.p90 * gain > local_p90 * SPECULAR_MAX:
                k = local_p90 * SPECULAR_MAX / (icon.p90 * gain)
                if float(lit @ np.array([0.299, 0.587, 0.114])) * k < LUM_MIN:
                    return False
                spot.color_filter = tuple(int(round(c * k)) for c in spot.color_filter)
                spot.level *= k
        return self._chroma(lit) - self._chroma(local) <= CHROMA_MAX

    def _color_dist(self, bg: Background, cid: str, spot_probe: tuple) -> float:
        icon = self.icon(cid)
        local = bg.patch_mean(*spot_probe)
        return float(np.linalg.norm(icon.mean - local)) if icon else 1e9

    # -- scene ------------------------------------------------------------------
    def plan_scene(self, cfg: dict, bg: Background, existing: list[dict],
                   progress: Optional[Callable[[str, int, int], None]] = None
                   ) -> list[dict]:
        """`progress` (optional) is called as progress(phase, done, total) with phase
        "place" or "alt"; it may raise to cancel the run (the editor does)."""
        rng = random.Random(int(cfg.get("seed", 1)))
        self.light_cfg = dict(cfg.get("light", {}))
        h_mul = float(cfg.get("h_mul", 1.0))   # whole-scene size tuning
        surfaces = []
        for s in cfg["surfaces"]:
            hv = s["h"] if isinstance(s["h"], list) else [s["h"], s["h"]]
            sf = Surface(*s["p"], h=float(hv[0]) * h_mul, kind=s.get("kind", "shelf"), max=0,
                         h_near=float(hv[1]) * h_mul, poses=tuple(s.get("poses", ())))
            if s.get("snap", True) and not sf.is_area:
                dy = bg.snap(sf.x0, sf.y0, sf.x1, sf.y1,
                             min(SNAP_MAX_PX, SNAP_SHARE * float(s["h"])))
                sf.y0 += dy
                sf.y1 += dy
            ref = (sf.h + sf.h_near) / 2 if sf.is_area else sf.h
            cap = max(1, int(sf.length / (ROOM_PER_OBJECT * ref)))
            sf.max = int(s.get("max", cap))
            surfaces.append(sf)
        counts = [0] * len(surfaces)
        taken: list = []
        for o in existing:
            w = o.get("width", 60) * o.get("scale", 1.0)
            h = o.get("height", 60) * o.get("scale", 1.0)
            taken.append((o["x"] - GAP, o["y"] - GAP, o["x"] + w + GAP, o["y"] + h + GAP))

        placed: list[tuple[str, str, Spot, float]] = []   # (catalog_id, role, spot, size_mul)

        def put(cid: str, role: str, size_mul: float) -> bool:
            min_px = CLUE_MIN_SCREEN_PX if role == "clue" else MIN_SCREEN_PX
            spot = self._sample(rng, bg, surfaces, cid, size_mul, taken, counts, min_px)
            if spot is None:
                log.warning("  no room for %s (%s)", cid, role)
                return False
            taken.append(spot.box)
            counts[spot.surface] += 1
            placed.append((cid, role, spot, size_mul))
            return True

        if cfg.get("clue"):
            put(cfg["clue"], "clue", self.size_factor(cfg["clue"]))
        if cfg.get("collectible"):
            put(cfg["collectible"], "collectible", self.size_factor(cfg["collectible"]))
        minigame_of: dict[str, str] = {}
        for mg in cfg.get("minigames", []):
            if self.icon(mg["catalog_id"]) is not None and put(
                    mg["catalog_id"], "minigame", self.size_factor(mg["catalog_id"])):
                minigame_of[mg["catalog_id"]] = mg["minigame_id"]
        unsized = [c for c in cfg["pool"] if c not in self.real_sizes]
        if unsized:
            log.info("  not in real_sizes_cm.json, left out: %s", " ".join(unsized))
        free = [c for c in cfg["pool"] if c in self.real_sizes and self.icon(c) is not None
                and c not in
                (cfg.get("clue"), cfg.get("collectible")) and c not in minigame_of]
        missing = [c for c in cfg["pool"] if self.icon(c) is None]
        if missing:
            log.warning("  pool ids without an image, skipped: %s", missing)
        rng.shuffle(free)
        target = int(cfg["count"])
        n_pool = 0
        while n_pool < target and free:
            # probe a spot on a random surface, then give it the best-matching free object
            s = rng.choices(surfaces, weights=[x.length for x in surfaces])[0]
            px, py = s.at(rng.random())
            probe = (px - s.h, py - s.h * 1.2, px + s.h, py)
            ranked = sorted(free, key=lambda c: self._color_dist(bg, c, probe))
            cid = rng.choice(ranked[:COLOR_TOP_K])
            free.remove(cid)
            if put(cid, "pool", self.size_factor(cid)):
                n_pool += 1
            if progress is not None:
                progress("place", n_pool, target)

        out = []
        # One capacity counter per alternative pass: at runtime each object shows on one
        # spot only, so a surface never holds more than its base load plus one pass.
        alt_counts = [[0] * len(surfaces) for _ in range(int(cfg["alt_spots"]))]
        for n_done, (cid, role, spot, size_mul) in enumerate(placed):
            if progress is not None:
                progress("alt", n_done, len(placed))
            alts = []
            for r in range(int(cfg["alt_spots"])):
                alt = self._sample(rng, bg, surfaces, cid, size_mul, taken, alt_counts[r],
                                   CLUE_MIN_SCREEN_PX if role == "clue" else MIN_SCREEN_PX)
                if alt is None:
                    continue
                taken.append(alt.box)
                alt_counts[r][alt.surface] += 1
                # same REF size as the base: scale carries the size difference
                k = alt.h / spot.h
                entry = {"x": round(alt.x), "y": round(alt.y), "rotation": alt.rotation,
                         "scale": round(k, 3), "flip_x": alt.flip_x,
                         "color_filter": list(alt.color_filter)}
                if alt.shadow:      # in REF px: the runtimes multiply it by the scale
                    entry["shadow"] = {"dy": round(alt.shadow["dy"] / k, 1),
                                       "w": round(alt.shadow["w"] / k, 1),
                                       "a": alt.shadow["a"]}
                alts.append(entry)
            o = {"catalog_id": cid, "x": round(spot.x), "y": round(spot.y),
                 "detection_type": "rect", "width": round(spot.w), "height": round(spot.h),
                 "rotation": spot.rotation, "flip_x": spot.flip_x, "alpha": 255,
                 "layer": "objects_mid", "is_goal": True, "hint_delay": int(cfg["hint_delay"]),
                 "color_filter": list(spot.color_filter)}
            if spot.corners:
                o["corners"] = spot.corners
            if spot.shadow:
                o["shadow"] = {"dy": round(spot.shadow["dy"], 1),
                               "w": round(spot.shadow["w"], 1), "a": spot.shadow["a"]}
            desat = round({**LIGHT, **self.light_cfg}["desat"] * (1 - spot.level), 2)
            if desat >= DESAT_MIN:
                o["grayscale"] = True
                o["grayscale_factor"] = desat
            if role == "minigame":
                o["minigame_trigger"] = {"minigame_id": minigame_of[cid]}
                o["always_show"] = True
            if role == "clue":
                o["clue_key"] = cfg.get("clue_key", f"clue_{cfg['scene']}")
            elif role == "collectible":
                o["collectible"] = True
                o["is_goal"] = False
            if alts:
                o["alt_spots"] = alts
            out.append(o)
        log.info("  %d objects (%d pool), %d alternative spots", len(out), n_pool,
                 sum(len(o.get("alt_spots", [])) for o in out))
        return out

    # -- preview ------------------------------------------------------------------
    def audit_sheet(self, bg: Background, objects: list[dict], rendered: Image.Image,
                    cols: int = 6, cell: int = 300) -> Image.Image:
        """Every object cropped with its surroundings (3x its size), shown at twice the
        size it has on a 1280 px wide screen, labelled: the sheet to review by eye."""
        k_screen = SCREEN_W / bg.W
        n = len(objects)
        rows = (n + cols - 1) // cols
        sheet = Image.new("RGB", (cols * cell, rows * cell), (20, 20, 20))
        d = ImageDraw.Draw(sheet)
        for i, o in enumerate(objects):
            w, h = o["width"], o["height"]
            cx, cy = o["x"] + w / 2, o["y"] + h / 2
            r = max(w, h) * 1.6
            crop = rendered.crop((round(cx - r), round(cy - r), round(cx + r), round(cy + r)))
            side = max(1, round(2 * r * k_screen * 2))
            crop = crop.resize((side, side), Image.LANCZOS)
            crop.thumbnail((cell - 4, cell - 22))
            px, py = (i % cols) * cell, (i // cols) * cell
            sheet.paste(crop, (px + 2, py + 20))
            px_screen = round(max(w, h) * k_screen)
            d.text((px + 4, py + 3), f"{o['catalog_id'][:26]} {px_screen}px", fill=(255, 220, 0))
        return sheet

    @staticmethod
    def _draw_shadow(canvas: Image.Image, cx: float, cy: float, w: float, a: int) -> None:
        """Soft elliptic contact shadow (preview of what the runtimes draw)."""
        sw, sh = max(2, round(w)), max(2, round(w * SHADOW_ASPECT))
        yy, xx = np.mgrid[0:sh, 0:sw]
        r = np.sqrt(((xx + 0.5) / sw * 2 - 1) ** 2 + ((yy + 0.5) / sh * 2 - 1) ** 2)
        alpha = (np.clip(1 - r, 0, 1) ** 1.5 * a).astype(np.uint8)
        layer = np.zeros((sh, sw, 4), np.uint8)
        layer[..., 3] = alpha
        canvas.alpha_composite(Image.fromarray(layer, "RGBA"),
                               (round(cx - sw / 2), round(cy - sh / 2)))

    @staticmethod
    def _warp(im: Image.Image, corners: list, k: float) -> Image.Image:
        """4-corner warp like the runtimes: corner offsets (REF px, times scale) moved
        from the rect corners TL, TR, BR, BL."""
        import cv2
        w, h = im.size
        src = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
        dst = np.float32([[corners[0][0] * k, corners[0][1] * k],
                          [w + corners[1][0] * k, corners[1][1] * k],
                          [w + corners[2][0] * k, h + corners[2][1] * k],
                          [corners[3][0] * k, h + corners[3][1] * k]])
        m = cv2.getPerspectiveTransform(src, dst)
        out = cv2.warpPerspective(np.asarray(im), m, (w, h), flags=cv2.INTER_LINEAR,
                                  borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0, 0))
        return Image.fromarray(out, "RGBA")

    def render(self, bg: Background, objects: list[dict], variant: int,
               surfaces: Optional[list] = None) -> Image.Image:
        """variant 0 = base spots, n = n-th alternative spot where present."""
        canvas = bg.img.copy().convert("RGBA")
        for o in objects:
            spot = dict(o)
            alts = o.get("alt_spots", [])
            if variant and len(alts) >= variant:
                spot.update(alts[variant - 1])
            icon = self.icon(o["catalog_id"])
            if icon is None:
                continue
            k = float(spot.get("scale", 1.0))
            w, h = max(1, round(o["width"] * k)), max(1, round(o["height"] * k))
            im = icon.img.resize((w, h), Image.LANCZOS)
            if spot.get("flip_x"):
                im = im.transpose(Image.FLIP_LEFT_RIGHT)
            cf = spot.get("color_filter", [255, 255, 255])
            arr = np.asarray(im).astype(np.float32)
            if o.get("grayscale"):
                f = float(o.get("grayscale_factor", 1.0))
                g = arr[..., :3] @ np.array([0.299, 0.587, 0.114], dtype=np.float32)
                arr[..., :3] = arr[..., :3] * (1 - f) + g[..., None] * f
            arr[..., :3] *= np.array(cf, dtype=np.float32) / 255.0
            im = Image.fromarray(arr.clip(0, 255).astype(np.uint8), "RGBA")
            corners = o.get("corners")
            if corners and any(c[0] or c[1] for c in corners):
                im = self._warp(im, corners, k)
            rot = float(spot.get("rotation", 0.0))
            if rot:
                im = im.rotate(rot, resample=Image.BICUBIC, expand=True)
            cx, cy = spot["x"] + w / 2, spot["y"] + h / 2
            sh = spot.get("shadow") or o.get("shadow")
            if sh:
                self._draw_shadow(canvas, cx, cy + sh["dy"] * k, sh["w"] * k, sh["a"])
            canvas.alpha_composite(im, (round(cx - im.width / 2), round(cy - im.height / 2)))
        if surfaces:
            d = ImageDraw.Draw(canvas)
            for s in surfaces:
                hv = s["h"] if isinstance(s["h"], list) else [s["h"], s["h"]]
                if s.get("kind") == "area":
                    d.rectangle(s["p"], outline=(0, 255, 120, 255), width=5)
                else:
                    d.line(s["p"], fill=(255, 0, 255, 255), width=5)
                d.line([s["p"][0], s["p"][1] - hv[0], s["p"][0], s["p"][1]],
                       fill=(0, 255, 255, 255), width=4)
            sup = getattr(bg, "support", None)
            if sup is not None:
                tint = Image.new("RGBA", canvas.size, (0, 255, 120, 0))
                a = (sup.astype(np.uint8) * 60)
                tint.putalpha(Image.fromarray(a))
                canvas.alpha_composite(tint)
            hud = bg.H * (1 - HUD_BAND)
            d.line([0, hud, bg.W, hud], fill=(255, 255, 0, 255), width=4)
        return canvas.convert("RGB")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = sys.argv[1:]
    preview = "--preview" in args
    args = [a for a in args if a != "--preview"]
    plan_path = Path(args[0])
    only = set(args[1:])
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    game_id = plan_path.resolve().parent.name
    placer = Placer(game_id)
    out_dir = REPO / "scratch" / "placement"
    out_dir.mkdir(parents=True, exist_ok=True)
    for sc in plan["scenes"]:
        if only and sc["scene"] not in only:
            continue
        cfg = {**DEFAULTS, **plan.get("defaults", {}), **sc}
        scene_dir = REPO / "games" / game_id / "levels" / cfg["level"] / cfg["scene"]
        # surfaces.json next to scene.json (drawn in the editor) wins over the plan
        sfile = scene_dir / SURFACES_FILE
        if sfile.exists():
            cfg.update(json.loads(sfile.read_text(encoding="utf-8")))
        if not cfg.get("surfaces"):
            log.warning("%s: no surfaces, skipped", cfg["scene"])
            continue
        data = json.loads((scene_dir / "scene.json").read_text(encoding="utf-8"))
        bg = Background(scene_dir / data["background"])
        log.info("%s/%s (%dx%d)", cfg["level"], cfg["scene"], bg.W, bg.H)
        if any(sf.get("kind") == "area" for sf in cfg["surfaces"]):
            bg.load_support(scene_dir / data["background"])
        kept = [o for o in data.get("objects", [])
                if cfg.get("keep_minigames") and o.get("minigame_trigger")]
        objects = kept + placer.plan_scene(cfg, bg, kept)
        for v in range(int(cfg["alt_spots"]) + 1):
            im = placer.render(bg, objects, v, cfg["surfaces"] if v == 0 else None)
            if v == 0:
                clean = placer.render(bg, objects, 0)
                placer.audit_sheet(bg, objects, clean).save(
                    out_dir / f"{cfg['scene']}_audit.jpg", quality=88)
            im.thumbnail((PREVIEW_W, PREVIEW_W))
            im.save(out_dir / f"{cfg['scene']}_v{v}.jpg", quality=88)
        if preview:
            continue
        data["objects"] = objects
        data["auto_random_finds"] = True
        data["num_random_finds"] = int(cfg["goals"])
        data.pop("objects_to_show", None)
        safe_write_json(str(scene_dir / "scene.json"), data)
        log.info("  written %s", scene_dir / "scene.json")


if __name__ == "__main__":
    main()
