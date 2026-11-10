"""Populate scenes from a plan: camouflage auto-scatter of a themed object pool, the story
clue and the collectible, each with alternative hiding spots (docs/engine/STORY_AND_REPLAY.md).

The plan is a JSON file next to the game (e.g. games/Malonno_Survivors/populate_plan.json):

    {"defaults": {"count": 28, "goals": 12, "alt_spots": 2, "difficulty": "hard"},
     "scenes": [{"level": "Welcome_To_Malonno", "scene": "Formis", "seed": 11,
                 "pool": ["salami", "cheese_wheel", ...], "clue": "faded_letter",
                 "collectible": "rose_carved_pebble", "keep_minigames": true}]}

For each scene: the clue and the collectible are placed first (each restricted to its own
id), then `count` objects chosen by the scatter from `pool`; every placed object then gets
`alt_spots` more placements, each from a new scatter pass restricted to the placed ids and
kept clear of every spot already taken. The scene's `objects` list is rewritten (objects
with a minigame_trigger are kept when `keep_minigames` is true), `auto_random_finds` is
switched on with `num_random_finds = goals`. The rest of scene.json is left alone.

Usage:
    python tools/populate_scene.py games/Malonno_Survivors/populate_plan.json [scene ...]
"""
from __future__ import annotations

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import json  # noqa: E402
import logging  # noqa: E402
import sys  # noqa: E402
from pathlib import Path  # noqa: E402
from typing import Optional  # noqa: E402

import pygame  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from editor.tools import scatter_engine as se  # noqa: E402
from editor.tools.scatter_engine import PlacedObject, build_forbidden_mask  # noqa: E402
from editor.tools.scatter_models import get_best_model  # noqa: E402
from editor.tools.scatter_validate import run_scatter_with_repair  # noqa: E402
from engine.catalog_manager import load_catalog  # noqa: E402
from engine.utils import safe_write_json  # noqa: E402

log = logging.getLogger("populate_scene")

STYLE = "real"
LAYERS = ["objects_low", "objects_mid", "objects_high"]
DEFAULTS = {"count": 28, "goals": 12, "alt_spots": 2, "difficulty": "hard",
            "hint_delay": 45}
# Seed offsets of the passes, so every pass of a scene draws a different stream.
SEED_CLUE, SEED_COLLECTIBLE, SEED_ALT = 1000, 2000, 3000
DISPLAY_SIZE = (64, 64)  # pygame needs a display for convert(); never shown
# Scatter model tier: 3 = ULTRA (Metric3D depth + normals, SegFormer semantics, CLIP
# patches), the editor's best. Objects land on supporting surfaces that suit them.
# Override with the SCATTER_TIER environment variable.
DEFAULT_TIER = 3


def _bbox(p: PlacedObject) -> tuple[float, float, float, float]:
    """Bounding box in background px, same convention as the editor."""
    if p.detection_type == "circle":
        r = p.radius * p.scale
        return (p.x - r, p.y - r, p.x + r, p.y + r)
    w, h = p.width * p.scale, p.height * p.scale
    return (p.x, p.y, p.x + w, p.y + h)


def _entry(p: PlacedObject, hint_delay: int) -> dict:
    """Scene object from a placement (mirror of the editor's scatter apply)."""
    out = {
        "catalog_id": p.catalog_id,
        "x": round(p.x), "y": round(p.y),
        "detection_type": p.detection_type,
        "scale": round(p.scale, 2),
        "rotation": round(p.rotation, 1),
        "flip_x": bool(p.flip_x), "flip_y": bool(p.flip_y),
        "alpha": int(p.alpha),
        "layer": p.layer,
        "is_goal": True,
        "hint_delay": hint_delay,
        "width": round(p.width), "height": round(p.height),
    }
    if p.detection_type == "circle":
        out["radius"] = round(p.radius)
    if tuple(p.color_filter) != (255, 255, 255):
        out["color_filter"] = list(p.color_filter)
    return out


def _spot(p: PlacedObject) -> dict:
    spot = {"x": round(p.x), "y": round(p.y), "rotation": round(p.rotation, 1),
            "scale": round(p.scale, 2), "flip_x": bool(p.flip_x), "alpha": int(p.alpha)}
    if tuple(p.color_filter) != (255, 255, 255):
        spot["color_filter"] = list(p.color_filter)
    return spot


class ScenePopulator:
    def __init__(self, game_id: str) -> None:
        self.game_id = game_id
        self.game_path = REPO / "games" / game_id
        self.catalog = [c for c in load_catalog(game_id).get("objects", [])
                        if c.get("style", "real") == STYLE]
        self.entries = {c["id"]: c for c in self.catalog}
        tier = int(os.environ.get("SCATTER_TIER", DEFAULT_TIER))
        self.model = get_best_model(REPO, force_tier=tier, quick_benchmark=False)
        log.info("scatter model: tier %s (%s)", self.model.tier, self.model.name)
        clip = getattr(self.model, "clip", None) if self.model.tier == 3 else None
        self.analyses = se.precompute_catalog(self.catalog, STYLE, REPO, clip_model=clip)

    def _place(self, ids: list[str], count: int, *, bg, surf, forbidden, difficulty: str,
               seed: int, taken: list) -> list[PlacedObject]:
        ids = [i for i in ids if i in self.analyses and i in self.entries]
        if not ids or count <= 0:
            return []
        analyses = {i: self.analyses[i] for i in ids}
        entries = {i: self.entries[i] for i in ids}
        kept, _results, report = run_scatter_with_repair(
            bg, analyses, entries, bg_surface=surf, game_path=self.game_path,
            repo_root=REPO, count=count, difficulty=difficulty, style=STYLE,
            existing_bboxes=list(taken), seed=seed, allowed_layers=LAYERS,
            forbidden_mask=forbidden,
            render_ctx={"bg_surface": surf, "game_path": self.game_path, "repo_root": REPO})
        log.info("  placed %d/%d (ok %s, warn %s, replaced %s)", len(kept), count,
                 report.get("ok"), report.get("warn"), report.get("dropped_fail"))
        return kept

    def populate(self, cfg: dict) -> dict:
        level, scene = cfg["level"], cfg["scene"]
        scene_dir = self.game_path / "levels" / level / scene
        path = scene_dir / "scene.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        surf = pygame.image.load(str(scene_dir / data["background"])).convert()
        bg = se.analyze_background(surf, ia_model=self.model, base_path=REPO, use_cache=True)
        forbidden = build_forbidden_mask(bg, set())
        seed = int(cfg.get("seed", 1))
        diff = cfg["difficulty"]
        missing = [i for i in cfg["pool"] + [cfg.get("clue"), cfg.get("collectible")]
                   if i and i not in self.entries]
        if missing:
            log.warning("  ids not in the %s catalog, skipped: %s", STYLE, missing)

        taken: list = []
        kept_mg = [o for o in data.get("objects", [])
                   if cfg.get("keep_minigames") and o.get("minigame_trigger")]
        for o in kept_mg:
            w, h = o.get("width", 60) * o.get("scale", 1.0), o.get("height", 60) * o.get("scale", 1.0)
            taken.append((o["x"], o["y"], o["x"] + w, o["y"] + h))

        base: list[tuple[PlacedObject, dict]] = []   # (placement, role)
        for role, key, off in (("clue", "clue", SEED_CLUE),
                                ("collectible", "collectible", SEED_COLLECTIBLE)):
            if cfg.get(key):
                log.info("  %s: %s", role, cfg[key])
                got = self._place([cfg[key]], 1, bg=bg, surf=surf, forbidden=forbidden,
                                  difficulty=diff, seed=seed + off, taken=taken)
                for p in got:
                    base.append((p, {"role": role}))
                    taken.append(_bbox(p))
        log.info("  pool of %d ids, %d to place", len(cfg["pool"]), cfg["count"])
        for p in self._place(cfg["pool"], cfg["count"], bg=bg, surf=surf, forbidden=forbidden,
                             difficulty=diff, seed=seed, taken=taken):
            base.append((p, {"role": "pool"}))
            taken.append(_bbox(p))

        spots: list[list[dict]] = [[] for _ in base]
        for r in range(int(cfg["alt_spots"])):
            log.info("  alternative spots, pass %d", r + 1)
            groups = {"clue": [], "collectible": [], "pool": []}
            for i, (p, role) in enumerate(base):
                groups[role["role"]].append(i)
            for role, idx in groups.items():
                if not idx:
                    continue
                ids = sorted({base[i][0].catalog_id for i in idx})
                got = self._place(ids, len(idx), bg=bg, surf=surf, forbidden=forbidden,
                                  difficulty=diff, seed=seed + SEED_ALT + 97 * r
                                  + (0 if role == "pool" else 13 * len(role)), taken=taken)
                free = list(idx)
                for p in got:
                    match: Optional[int] = next(
                        (i for i in free if base[i][0].catalog_id == p.catalog_id), None)
                    if match is None:
                        continue
                    free.remove(match)
                    spots[match].append(_spot(p))
                    taken.append(_bbox(p))

        objects = list(kept_mg)
        for (p, role), alts in zip(base, spots):
            o = _entry(p, int(cfg["hint_delay"]))
            if role["role"] == "clue":
                o["clue_key"] = cfg.get("clue_key", f"clue_{scene}")
            elif role["role"] == "collectible":
                o["collectible"] = True
                o["is_goal"] = False
            if alts:
                o["alt_spots"] = alts
            objects.append(o)
        data["objects"] = objects
        data["auto_random_finds"] = True
        data["num_random_finds"] = int(cfg["goals"])
        data.pop("objects_to_show", None)
        safe_write_json(str(path), data)
        n_alt = sum(len(s) for s in spots)
        log.info("  %s/%s: %d objects, %d alternative spots written", level, scene,
                 len(objects), n_alt)
        return {"scene": scene, "objects": len(objects), "alt_spots": n_alt}


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    for noisy in ("editor", "engine"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    plan_path = Path(sys.argv[1])
    only = set(sys.argv[2:])
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    game_id = plan_path.resolve().parent.name
    pygame.init()
    pygame.display.set_mode(DISPLAY_SIZE)
    pop = ScenePopulator(game_id)
    report = []
    for sc in plan["scenes"]:
        if only and sc["scene"] not in only:
            continue
        cfg = {**DEFAULTS, **plan.get("defaults", {}), **sc}
        log.info("%s/%s", cfg["level"], cfg["scene"])
        report.append(pop.populate(cfg))
    log.info("done: %s", json.dumps(report))


if __name__ == "__main__":
    main()
