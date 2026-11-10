"""
editor/core/surfaces.py

Placement surfaces of a scene and the bridge to `tools/place_on_surfaces.py`.

The surface placement tool puts hidden objects on surfaces the level designer
marks by hand: resting lines (shelf boards, table edges, sills, ledges, the
floor seen from the front) and "area" rectangles (floors and table tops seen
from above, validated by a support map computed from the Metric3D normals).
They live next to the scene in `surfaces.json`:

    {"surfaces": [{"p": [x0, y0, x1, y1], "h": 85, "kind": "shelf"},
                  {"p": [x0, y0, x1, y1], "h": [far, near], "kind": "area"}],
     "h_mul": 1.0, ...}

This module holds everything the editor needs that does not draw: reading and
writing that file (keys the editor does not edit are kept as they are), the
geometry the canvas hit-tests, the configuration a run is built from (the
game's `placement_plan.json` entry, or a pool taken from the catalog), the
worker that runs `Placer.plan_scene` off the UI thread, and the conversion of
its result into the scene's objects, the same one the command line tool
performs.

The tool is imported as a library, lazily: it pulls numpy, PIL and OpenCV and
it hides the GPU from the process at import time. The editor restores the
environment right after the import, and builds its own CPU-only model for the
support map, so the legacy scatter keeps whatever accelerator it had.
"""

from __future__ import annotations

import copy
import importlib
import inspect
import json
import logging
import math
import os
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from engine.utils import safe_write_json

log = logging.getLogger(__name__)

SURFACES_FILE = "surfaces.json"
PLAN_FILE = "placement_plan.json"
REAL_SIZES_REL = ("engine", "data", "real_sizes_cm.json")
PLACER_MODULE = "tools.place_on_surfaces"
CUDA_ENV = "CUDA_VISIBLE_DEVICES"
CPU_PROVIDER = "CPUExecutionProvider"
SUPPORT_MODEL_TIER = 2               # Metric3D (depth + normals)

LINE_KINDS = ("shelf", "table", "sill", "ledge", "floor")
AREA_KIND = "area"
KINDS = LINE_KINDS + (AREA_KIND,)
DEFAULT_KIND = "shelf"

# A new surface's "h" (px of a 20 cm object, see REF_CM in the tool) before the
# designer measures it: a medium object about this tall on a 1280 px screen.
REF_SCREEN_W = 1280
DEFAULT_H_SCREEN_PX = 40
AREA_NEAR_GROWTH = 1.3               # default near / far size of a new area
H_MIN = 4.0                          # smallest "h" accepted, bg px
H_MAX = 2000.0
H_MUL_MIN = 0.1
H_MUL_MAX = 5.0
MAX_OBJECTS_CAP = 200

# Smallest surface a drag creates, in background px: a click is not a surface.
MIN_LINE_PX = 12.0
MIN_AREA_PX = 16.0

# Fallbacks of the tool's layout rules, used when it cannot be imported.
FALLBACK_HUD_BAND = 110 / 720
FALLBACK_EDGE = 0.02
FALLBACK_DEFAULTS = {"count": 40, "goals": 15, "alt_spots": 2, "hint_delay": 45,
                     "collectible": None, "keep_minigames": False, "minigames": []}

# Downsampled support map kept for the canvas overlay: at most this wide.
SUPPORT_PREVIEW_MAX_W = 1024

KEEP_REPLACE = "replace"             # the tool's behaviour: the run rewrites the scene
KEEP_ALL = "keep"                    # the current objects stay and are avoided

POOL_PLAN = "plan"
POOL_CATALOG = "catalog"


# ─────────────────────────────────────────────────────────────────────────────
# surfaces.json
# ─────────────────────────────────────────────────────────────────────────────

def surfaces_path(scene_dir: Path) -> Path:
    return Path(scene_dir) / SURFACES_FILE


def load_surfaces_doc(scene_dir: Path) -> dict:
    """The scene's surfaces.json, normalized; {"surfaces": []} when absent.

    Keys the editor does not edit (h_mul, light, pool...) are kept as they are,
    so writing the document back never loses what the tool reads from it.
    """
    path = surfaces_path(scene_dir)
    doc: dict = {}
    if path.exists():
        try:
            doc = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError) as exc:
            log.warning("Unreadable %s: %s", path, exc)
            doc = {}
    if not isinstance(doc, dict):
        doc = {}
    raw = doc.get("surfaces", [])
    doc["surfaces"] = [normalized(s) for s in raw if _valid_raw(s)]
    return doc


def save_surfaces_doc(scene_dir: Path, doc: dict) -> bool:
    """Write the document atomically. A scene that never had surfaces gets no
    file for an empty list."""
    path = surfaces_path(scene_dir)
    if not doc.get("surfaces") and not path.exists():
        return True
    out = dict(doc)
    out["surfaces"] = [normalized(s) for s in doc.get("surfaces", [])]
    return safe_write_json(path, out)


def _valid_raw(s: Any) -> bool:
    if not isinstance(s, dict):
        return False
    p = s.get("p")
    if not isinstance(p, (list, tuple)) or len(p) != 4:
        return False
    try:
        [float(v) for v in p]
    except (TypeError, ValueError):
        return False
    return "h" in s


# ─────────────────────────────────────────────────────────────────────────────
# One surface
# ─────────────────────────────────────────────────────────────────────────────

def is_area(s: dict) -> bool:
    return s.get("kind") == AREA_KIND


def heights(s: dict) -> tuple[float, float]:
    """(far, near) size of a surface; a line has the same value twice."""
    h = s.get("h", 0)
    if isinstance(h, (list, tuple)):
        far = float(h[0]) if h else 0.0
        near = float(h[1]) if len(h) > 1 else far
        return far, near
    return float(h), float(h)


def _num(v: float) -> float | int:
    """Whole numbers stay ints in the JSON (the hand-written files use them)."""
    r = round(float(v), 1)
    return int(r) if r == int(r) else r


def normalized(s: dict) -> dict:
    """A clean copy: lines run left to right, an area's corners are ordered, `h`
    is a number for a line and [far, near] for an area, the kind is known."""
    out = {k: copy.deepcopy(v) for k, v in s.items()}
    kind = s.get("kind", DEFAULT_KIND)
    out["kind"] = kind if kind in KINDS else DEFAULT_KIND
    x0, y0, x1, y1 = (float(v) for v in s["p"])
    far, near = heights(s)
    if out["kind"] == AREA_KIND:
        x0, x1 = min(x0, x1), max(x0, x1)
        y0, y1 = min(y0, y1), max(y0, y1)
        out["h"] = [_num(far), _num(near)]
    else:
        if x1 < x0:
            x0, y0, x1, y1 = x1, y1, x0, y0
        out["h"] = _num(far)
    # Whole background pixels: the hand-written files use them, and a drawn
    # point is not more precise than one pixel anyway.
    out["p"] = [int(round(v)) for v in (x0, y0, x1, y1)]
    return out


def default_h(bg_width: float) -> float:
    """Size of a 20 cm object on a new surface, before it is measured."""
    return float(round(DEFAULT_H_SCREEN_PX * float(bg_width) / REF_SCREEN_W))


def new_line(x0: float, y0: float, x1: float, y1: float, h: float,
             kind: str = DEFAULT_KIND) -> dict:
    return normalized({"p": [x0, y0, x1, y1], "h": h,
                       "kind": kind if kind in LINE_KINDS else DEFAULT_KIND})


def new_area(x0: float, y0: float, x1: float, y1: float, far: float,
             near: Optional[float] = None) -> dict:
    near = far * AREA_NEAR_GROWTH if near is None else near
    return normalized({"p": [x0, y0, x1, y1], "h": [far, near], "kind": AREA_KIND})


def with_kind(s: dict, kind: str) -> dict:
    """The surface turned into another kind; line <-> area keeps the extent.

    A line becomes the area that has it as its near edge (the floor in front of
    the resting line, one size tall), an area becomes the line of its far edge.
    """
    if kind not in KINDS or kind == s.get("kind"):
        return normalized(s)
    out = dict(s)
    far, near = heights(s)
    x0, y0, x1, y1 = (float(v) for v in s["p"])
    if kind == AREA_KIND and not is_area(s):
        out["p"] = [x0, min(y0, y1) - far, x1, max(y0, y1)]
        out["h"] = [far, far * AREA_NEAR_GROWTH]
        out.pop("snap", None)
    elif kind != AREA_KIND and is_area(s):
        out["p"] = [x0, y0, x1, y0]
        out["h"] = far
    out["kind"] = kind
    return normalized(out)


def moved(s: dict, dx: float, dy: float) -> dict:
    out = dict(s)
    x0, y0, x1, y1 = (float(v) for v in s["p"])
    out["p"] = [x0 + dx, y0 + dy, x1 + dx, y1 + dy]
    return normalized(out)


def handles(s: dict) -> list[tuple[str, float, float]]:
    """Draggable points in background px: a line's two ends, an area's corners."""
    x0, y0, x1, y1 = (float(v) for v in s["p"])
    if is_area(s):
        return [("c0", x0, y0), ("c1", x1, y0), ("c2", x1, y1), ("c3", x0, y1)]
    return [("p0", x0, y0), ("p1", x1, y1)]


def with_handle(s: dict, part: str, x: float, y: float) -> dict:
    """The surface with one handle moved to (x, y). Not normalized, so a drag
    can cross the other end; normalize when the drag ends."""
    out = dict(s)
    x0, y0, x1, y1 = (float(v) for v in s["p"])
    if part == "p0":
        x0, y0 = x, y
    elif part == "p1":
        x1, y1 = x, y
    elif part == "c0":
        x0, y0 = x, y
    elif part == "c1":
        x1, y0 = x, y
    elif part == "c2":
        x1, y1 = x, y
    elif part == "c3":
        x0, y1 = x, y
    out["p"] = [x0, y0, x1, y1]
    return out


def _dist_to_segment(px: float, py: float, x0: float, y0: float,
                     x1: float, y1: float) -> float:
    dx, dy = x1 - x0, y1 - y0
    seg = dx * dx + dy * dy
    if seg <= 0:
        return math.hypot(px - x0, py - y0)
    t = max(0.0, min(1.0, ((px - x0) * dx + (py - y0) * dy) / seg))
    return math.hypot(px - (x0 + t * dx), py - (y0 + t * dy))


def hit_test(surfaces: list[dict], x: float, y: float, tol: float,
             first: Optional[int] = None) -> Optional[tuple[int, str]]:
    """(index, part) of the surface under (x, y), background px.

    `tol` is the pick distance in background px. Handles win over bodies, the
    surface `first` (the selected one) is tried before the others, then the
    last drawn first. An area is picked on its border or anywhere inside.
    """
    order = list(range(len(surfaces) - 1, -1, -1))
    if first is not None and 0 <= first < len(surfaces):
        order.remove(first)
        order.insert(0, first)
    for i in order:
        for part, hx, hy in handles(surfaces[i]):
            if math.hypot(x - hx, y - hy) <= tol:
                return i, part
    for i in order:
        s = surfaces[i]
        x0, y0, x1, y1 = (float(v) for v in s["p"])
        if is_area(s):
            if (min(x0, x1) - tol <= x <= max(x0, x1) + tol
                    and min(y0, y1) - tol <= y <= max(y0, y1) + tol):
                return i, "body"
        elif _dist_to_segment(x, y, x0, y0, x1, y1) <= tol:
            return i, "body"
    return None


def long_enough(s: dict) -> bool:
    """False for what a click without a real drag produces."""
    x0, y0, x1, y1 = (float(v) for v in s["p"])
    if is_area(s):
        return abs(x1 - x0) >= MIN_AREA_PX and abs(y1 - y0) >= MIN_AREA_PX
    return math.hypot(x1 - x0, y1 - y0) >= MIN_LINE_PX


# ─────────────────────────────────────────────────────────────────────────────
# The tool, as a library
# ─────────────────────────────────────────────────────────────────────────────

_placer_module: Any = None
_import_lock = threading.Lock()


def import_placer() -> Any:
    """tools/place_on_surfaces.py, imported once, the environment left as it was.

    Importing it sets CUDA_VISIBLE_DEVICES to hide the GPU from the whole
    process; the editor restores it so the legacy scatter is not affected.
    """
    global _placer_module
    with _import_lock:
        if _placer_module is None:
            previous = os.environ.get(CUDA_ENV)
            try:
                _placer_module = importlib.import_module(PLACER_MODULE)
            finally:
                if previous is None:
                    os.environ.pop(CUDA_ENV, None)
                else:
                    os.environ[CUDA_ENV] = previous
        return _placer_module


def placement_rules() -> dict:
    """Layout rules of the tool the canvas shows: the HUD band and the margin."""
    try:
        mod = import_placer()
        return {"hud_band": float(mod.HUD_BAND), "edge": float(mod.EDGE),
                "defaults": dict(mod.DEFAULTS)}
    except Exception as exc:                       # tool missing in a build
        log.debug("Placement tool not importable: %s", exc)
        return {"hud_band": FALLBACK_HUD_BAND, "edge": FALLBACK_EDGE,
                "defaults": dict(FALLBACK_DEFAULTS)}


def _accepts(func: Callable, name: str) -> bool:
    """True when `func` takes a keyword `name` (a hook of the tool)."""
    try:
        return name in inspect.signature(func).parameters
    except (TypeError, ValueError):
        return False


def cpu_support_model(base_path: Path) -> Any:
    """Metric3D on the CPU only: the GPU is usually busy with generation."""
    from editor.tools.scatter_models import Metric3DLarge, model_path_for
    path = model_path_for(SUPPORT_MODEL_TIER, Path(base_path))
    if not path.exists():
        raise FileNotFoundError(str(path))
    return Metric3DLarge(path, providers=[CPU_PROVIDER])


class SceneBackground:
    """The tool's Background of one scene, built once, and its support map.

    Shared by the canvas overlay and the placement runs, from worker threads:
    every access goes through one lock. The support map is cached on disk by
    the tool (.editor_cache/geometry), so only the first run on a background
    pays for the model.
    """

    def __init__(self, base_path: Path, image_path: Path) -> None:
        self.base_path = Path(base_path)
        self.path = Path(image_path)
        self._lock = threading.RLock()
        self._bg: Any = None

    def background(self) -> Any:
        with self._lock:
            if self._bg is None:
                self._bg = import_placer().Background(self.path)
            return self._bg

    def has_support(self) -> bool:
        with self._lock:
            return self._bg is not None and getattr(self._bg, "support", None) is not None

    def ensure_support(self) -> Any:
        """The boolean support map (H x W), computed on the CPU if not cached."""
        with self._lock:
            bg = self.background()
            if getattr(bg, "support", None) is None:
                factory = lambda: cpu_support_model(self.base_path)  # noqa: E731
                if _accepts(bg.load_support, "model_factory"):
                    bg.load_support(self.path, model_factory=factory)
                else:                              # a tool without the hook
                    bg.load_support(self.path)
            return bg.support


def support_preview(mask: Any, max_w: int = SUPPORT_PREVIEW_MAX_W) -> tuple[Any, int]:
    """(downsampled mask, step) of a support map, for the canvas overlay."""
    width = int(mask.shape[1])
    step = max(1, int(math.ceil(width / float(max_w))))
    return mask[::step, ::step].copy(), step


# ─────────────────────────────────────────────────────────────────────────────
# Configuration of a run
# ─────────────────────────────────────────────────────────────────────────────

def load_real_sizes(base_path: Path) -> dict:
    """Catalog id -> longest real size in cm (the curation of what is placed)."""
    path = Path(base_path).joinpath(*REAL_SIZES_REL)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        log.warning("real_sizes_cm.json unreadable: %s", exc)
        return {}
    return {k: v for k, v in data.items() if not k.startswith("_")}


def plan_for_scene(game_path: Path, level: str, scene: str) -> tuple[dict, Optional[dict]]:
    """(plan defaults, the scene's entry or None) from placement_plan.json."""
    path = Path(game_path) / PLAN_FILE
    if not path.exists():
        return {}, None
    try:
        plan = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        log.warning("placement_plan.json unreadable: %s", exc)
        return {}, None
    defaults = dict(plan.get("defaults", {}))
    for entry in plan.get("scenes", []):
        if entry.get("scene") == scene and entry.get("level", level) == level:
            return defaults, dict(entry)
    return defaults, None


def base_config(tool_defaults: dict, plan_defaults: dict, entry: Optional[dict],
                surfaces_doc: dict, level: str, scene: str) -> dict:
    """The configuration the command line tool would build for this scene:
    tool defaults < plan defaults < scene entry < surfaces.json."""
    cfg = {**tool_defaults, **plan_defaults, **(entry or {})}
    cfg.setdefault("level", level)
    cfg.setdefault("scene", scene)
    cfg.setdefault("pool", [])
    cfg.update(copy.deepcopy(surfaces_doc))
    return cfg


def catalog_pool(catalog: list, style: str, tag: Optional[str],
                 real_sizes: dict) -> list[str]:
    """Catalog ids of a style (and tag), limited to the ones with a real size."""
    out = []
    for entry in catalog:
        if entry.get("style", "real") != style:
            continue
        if tag and tag not in entry.get("tags", []):
            continue
        if entry.get("id") in real_sizes:
            out.append(entry["id"])
    return sorted(out)


def usable_pool(pool: list, real_sizes: dict) -> list[str]:
    """The ids of a pool the tool will consider (it skips unsized ones)."""
    return [c for c in pool if c in real_sizes]


def kept_objects(objects: list, keep: str, keep_minigames: bool) -> list[dict]:
    """The current objects a run keeps (and places around)."""
    if keep == KEEP_ALL:
        return copy.deepcopy(list(objects))
    return [copy.deepcopy(o) for o in objects
            if keep_minigames and o.get("minigame_trigger")]


def merged_scene(scene_data: dict, kept: list, planned: list, goals: int) -> dict:
    """The scene after a run, exactly as tools/place_on_surfaces.py writes it:
    the kept objects then the planned ones, random finds on, `goals` of them."""
    out = copy.deepcopy(scene_data)
    out["objects"] = copy.deepcopy(list(kept)) + copy.deepcopy(list(planned))
    out["auto_random_finds"] = True
    out["num_random_finds"] = int(goals)
    out.pop("objects_to_show", None)
    return out


def with_variant(obj: dict, variant: int) -> dict:
    """The object drawn on its `variant`-th alternative spot (0 = its base)."""
    alts = obj.get("alt_spots") or []
    if variant <= 0 or len(alts) < variant:
        return obj
    out = dict(obj)
    out.update(alts[variant - 1])
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Worker
# ─────────────────────────────────────────────────────────────────────────────

class PlacementCancelled(Exception):
    """Raised inside the run when the user cancels it."""


PHASE_LOAD = "load"
PHASE_SUPPORT = "support"
PHASE_PLACE = "place"
PHASE_ALT = "alt"
PHASE_AUDIT = "audit"


@dataclass
class PlaceOutcome:
    planned: list
    kept: list
    seed: int
    count: int
    goals: int
    audit: Any = None                      # PIL image of the audit sheet
    warnings: list = field(default_factory=list)


class PlaceJob:
    """One run of Placer.plan_scene, in a daemon thread.

    The UI reads `progress` (phase, done, total) every frame and collects
    `outcome`, `error` or `cancelled` once `finished` is set. Nothing here
    touches pygame. `run()` is the body and can be called directly.
    """

    def __init__(self, *, game_id: str, scene_bg: SceneBackground, cfg: dict,
                 kept: list, placer_cache: dict, cache_key: Any = None,
                 with_audit: bool = True) -> None:
        self.game_id = game_id
        self.scene_bg = scene_bg
        self.cfg = copy.deepcopy(cfg)
        self.kept = copy.deepcopy(kept)
        self.placer_cache = placer_cache
        self.cache_key = cache_key if cache_key is not None else game_id
        self.with_audit = with_audit
        self.progress: tuple[str, int, int] = (PHASE_LOAD, 0, 1)
        self.outcome: Optional[PlaceOutcome] = None
        self.error: str = ""
        self.cancelled = False
        self.finished = threading.Event()
        self._cancel = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self.run, daemon=True,
                                        name="PlaceOnSurfaces")
        self._thread.start()

    def cancel(self) -> None:
        self._cancel.set()

    def _check(self) -> None:
        if self._cancel.is_set():
            raise PlacementCancelled()

    def _on_progress(self, phase: str, done: int, total: int) -> None:
        self.progress = (phase, int(done), max(1, int(total)))
        self._check()

    def _placer(self) -> Any:
        placer = self.placer_cache.get(self.cache_key)
        if placer is None:
            placer = import_placer().Placer(self.game_id)
            self.placer_cache.clear()          # one game at a time
            self.placer_cache[self.cache_key] = placer
        return placer

    def run(self) -> None:
        try:
            self.progress = (PHASE_LOAD, 0, 1)
            bg = self.scene_bg.background()
            placer = self._placer()
            self._check()
            if any(s.get("kind") == AREA_KIND for s in self.cfg.get("surfaces", [])):
                self.progress = (PHASE_SUPPORT, 0, 1)
                self.scene_bg.ensure_support()
            self._check()
            if _accepts(placer.plan_scene, "progress"):
                planned = placer.plan_scene(self.cfg, bg, self.kept,
                                            progress=self._on_progress)
            else:                                   # a tool without the hook
                planned = placer.plan_scene(self.cfg, bg, self.kept)
            self._check()
            audit = None
            if self.with_audit:
                self.progress = (PHASE_AUDIT, 0, 1)
                every = self.kept + planned
                clean = placer.render(bg, every, 0)
                audit = placer.audit_sheet(bg, every, clean) if every else None
            self._check()
            self.outcome = PlaceOutcome(planned=planned, kept=self.kept,
                                        seed=int(self.cfg.get("seed", 1)),
                                        count=int(self.cfg.get("count", 0)),
                                        goals=int(self.cfg.get("goals", 0)),
                                        audit=audit)
        except PlacementCancelled:
            self.cancelled = True
        except Exception as exc:
            log.exception("Placement on surfaces failed")
            self.error = str(exc) or exc.__class__.__name__
        finally:
            self.finished.set()
