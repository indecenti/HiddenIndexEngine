"""
engine/campaign.py

The campaign: the order in which a game's levels and scenes are played, what
is unlocked, what has been completed, and where the player goes next.

Meant as the one source of truth for the core loop, the menu cards and the
results screen. Today engine.level_manager uses it for the scene order and the
timer mode; wiring the core and the menu to it is the next step of
docs/engine/MENU_UX_PLAN.md (Campaign). Web parity: docs/web/WEB_EXPORT_SYNC.md,
section L.

Rules
-----
- Level order: the `levels` list of game_config.json, then any other level
  folder that has a level_config.json, alphabetically. The menu shows the
  levels in this order and the unlock chain follows it.
- Scene order: the `order` field of each scene in level_config.json, ties and
  missing values broken by the position in the list.
- The first level is always unlocked. A level is unlocked by completing the
  last scene of the level before it.
- Inside an unlocked level the first scene is unlocked; a scene is unlocked by
  completing the scene before it.
- Completing a scene means finding every goal. A scene lost on time (only
  possible with `timer_behavior: "fail"`) records nothing and unlocks nothing.
- Best score and best stars are kept per scene; a replay never lowers them.
- Resume target ("Continue"): the first unlocked scene, in campaign order,
  that is not completed yet. When everything is completed there is none.
- After a completed scene the next step is the next scene of the level, or
  the first scene of the next level, or the end of the campaign.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from engine.utils import get_logger, get_resource_path

log = get_logger(__name__)

TIMER_COMPLETE = "complete"   # the clock only scores: a scene cannot be lost
TIMER_FAIL = "fail"           # time out loses the scene
DEFAULT_TIMER_BEHAVIOR = TIMER_COMPLETE
MAX_STARS = 3


@dataclass(frozen=True)
class SceneRef:
    """One scene of the campaign."""

    level_id: str
    scene_id: str
    index: int          # position inside its level, in campaign order


def ordered_scene_ids(level_cfg: dict) -> list[str]:
    """Scene ids of a level config in campaign order (`order`, then position)."""
    scenes = [s for s in level_cfg.get("scenes", []) if isinstance(s, dict) and s.get("id")]
    keyed = []
    for pos, scene in enumerate(scenes):
        order = scene.get("order")
        rank = order if isinstance(order, (int, float)) and not isinstance(order, bool) else pos
        keyed.append((rank, pos, scene["id"]))
    return [sid for _rank, _pos, sid in sorted(keyed)]


def ordered_level_ids(game_levels: list, level_dirs: list[str]) -> list[str]:
    """Registered levels in game_config order, then the orphans alphabetically."""
    order = [lv for lv in game_levels if isinstance(lv, str)]
    registered = [lv for lv in order if lv in level_dirs]
    orphans = sorted(d for d in level_dirs if d not in order)
    seen: set[str] = set()
    out = []
    for lv in registered + orphans:
        if lv not in seen:
            seen.add(lv)
            out.append(lv)
    return out


def timer_behavior(level_cfg: dict) -> str:
    """The level's timer mode, falling back to the relaxed one."""
    value = str(level_cfg.get("timer_behavior", DEFAULT_TIMER_BEHAVIOR)).lower()
    return value if value in (TIMER_COMPLETE, TIMER_FAIL) else DEFAULT_TIMER_BEHAVIOR


class Campaign:
    """Campaign order and progress of one game, over its SaveManager."""

    def __init__(self, game_id: str, save_manager=None, game_config: dict | None = None,
                 level_configs: dict[str, dict] | None = None) -> None:
        self.game_id = game_id
        self.save = save_manager
        self._game_config = game_config if game_config is not None else self._read_game_config()
        self._level_cfgs: dict[str, dict] = dict(level_configs or {})
        if level_configs is None:
            self._load_level_configs()
        self._levels = ordered_level_ids(self._game_config.get("levels", []),
                                         list(self._level_cfgs))
        self._scenes = {lv: ordered_scene_ids(self._level_cfgs[lv]) for lv in self._levels}
        # A level without scenes cannot be played nor completed: it is left out
        # of the chain instead of blocking every level after it.
        self._levels = [lv for lv in self._levels if self._scenes[lv]]

    # -- loading -------------------------------------------------------------

    def _read_game_config(self) -> dict:
        path = get_resource_path("games", self.game_id, "game_config.json")
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError) as exc:
            log.warning("Campaign: game_config.json unreadable for '%s': %s", self.game_id, exc)
            return {}

    def _load_level_configs(self) -> None:
        root = get_resource_path("games", self.game_id, "levels")
        if not root.exists():
            return
        for folder in sorted(root.iterdir()):
            cfg_path = folder / "level_config.json"
            if not (folder.is_dir() and cfg_path.exists()):
                continue
            try:
                with open(cfg_path, "r", encoding="utf-8") as fh:
                    cfg = json.load(fh)
            except (OSError, ValueError) as exc:
                log.warning("Campaign: %s unreadable: %s", cfg_path, exc)
                continue
            if isinstance(cfg, dict):
                self._level_cfgs[folder.name] = cfg

    # -- structure -----------------------------------------------------------

    def levels(self) -> list[str]:
        return list(self._levels)

    def scenes(self, level_id: str) -> list[str]:
        return list(self._scenes.get(level_id, []))

    def level_config(self, level_id: str) -> dict:
        return self._level_cfgs.get(level_id, {})

    def scene_index(self, level_id: str, scene_id: str) -> int:
        scenes = self._scenes.get(level_id, [])
        return scenes.index(scene_id) if scene_id in scenes else -1

    def scene_ref(self, level_id: str, index: int) -> SceneRef | None:
        scenes = self._scenes.get(level_id, [])
        if 0 <= index < len(scenes):
            return SceneRef(level_id, scenes[index], index)
        return None

    def timer_behavior(self, level_id: str) -> str:
        return timer_behavior(self.level_config(level_id))

    # -- progress ------------------------------------------------------------

    def _data(self, key: str, default: Any) -> Any:
        if self.save is None:
            return default
        value = self.save.get_progress(key, default)
        return value if value is not None else default

    def is_level_unlocked(self, level_id: str) -> bool:
        if level_id not in self._levels:
            return False
        if self.save is None or level_id == self._levels[0]:
            return True
        return level_id in self._data("unlocked_levels", [])

    def is_scene_unlocked(self, level_id: str, index: int) -> bool:
        if not self.is_level_unlocked(level_id):
            return False
        if not 0 <= index < len(self._scenes.get(level_id, [])):
            return False
        if self.save is None or index == 0:
            return True
        return index <= int(self._data("unlocked_scenes", {}).get(level_id, 0))

    def best_stars(self, level_id: str, scene_id: str) -> int:
        return int(self._data("stars", {}).get(level_id, {}).get(scene_id, 0))

    def best_score(self, level_id: str, scene_id: str) -> int:
        return int(self._data("scores", {}).get(level_id, {}).get(scene_id, 0))

    def is_scene_completed(self, level_id: str, scene_id: str) -> bool:
        return (scene_id in self._data("scores", {}).get(level_id, {})
                or self.best_stars(level_id, scene_id) > 0)

    def level_progress(self, level_id: str) -> tuple[int, int, int, int]:
        """(scenes completed, scenes, stars earned, stars available)."""
        scenes = self._scenes.get(level_id, [])
        done = sum(1 for s in scenes if self.is_scene_completed(level_id, s))
        stars = sum(self.best_stars(level_id, s) for s in scenes)
        return done, len(scenes), stars, MAX_STARS * len(scenes)

    def is_level_completed(self, level_id: str) -> bool:
        done, total, _s, _m = self.level_progress(level_id)
        return total > 0 and done == total

    def has_progress(self) -> bool:
        """True once the player has completed anything."""
        return any(self._data("scores", {}).get(lv) for lv in self._levels)

    def next_level(self, level_id: str) -> str | None:
        if level_id not in self._levels:
            return None
        i = self._levels.index(level_id)
        return self._levels[i + 1] if i + 1 < len(self._levels) else None

    def next_scene(self, level_id: str, index: int) -> SceneRef | None:
        """The scene after (level, index) in campaign order, across levels."""
        ref = self.scene_ref(level_id, index + 1)
        if ref is not None:
            return ref
        nxt = self.next_level(level_id)
        return self.scene_ref(nxt, 0) if nxt else None

    def resume_target(self) -> SceneRef | None:
        """First unlocked, not completed scene in campaign order."""
        for level_id in self._levels:
            if not self.is_level_unlocked(level_id):
                break
            for i, scene_id in enumerate(self._scenes[level_id]):
                if not self.is_scene_unlocked(level_id, i):
                    break
                if not self.is_scene_completed(level_id, scene_id):
                    return SceneRef(level_id, scene_id, i)
        return None

    def unlock_requirement(self, level_id: str, index: int) -> SceneRef | None:
        """The scene whose completion unlocks (level, index), when it is locked."""
        if self.is_scene_unlocked(level_id, index):
            return None
        if index > 0 and self.is_level_unlocked(level_id):
            return self.scene_ref(level_id, index - 1)
        prev = self._levels[self._levels.index(level_id) - 1] \
            if level_id in self._levels and self._levels.index(level_id) > 0 else None
        if prev:
            return self.scene_ref(prev, len(self._scenes[prev]) - 1)
        return None

    # -- recording -----------------------------------------------------------

    def ensure_started(self) -> None:
        """Make sure the first level is recorded as unlocked."""
        if self.save is not None and self._levels:
            if self._levels[0] not in self._data("unlocked_levels", []):
                self.save.unlock_level(self._levels[0])

    def record_result(self, level_id: str, scene_id: str, score: int, stars: int,
                      failed: bool) -> SceneRef | None:
        """Store a finished scene and apply the unlocks. Returns the next step.

        A lost scene stores nothing and unlocks nothing; the next step is then
        None - the player retries or leaves, the campaign does not move.
        """
        index = self.scene_index(level_id, scene_id)
        if failed or index < 0:
            return None
        if self.save is not None:
            self.save.set_scene_score(level_id, scene_id, int(score), int(stars))
            scenes = self._scenes[level_id]
            if index + 1 < len(scenes):
                self.save.unlock_scene(level_id, index + 1)
            else:
                nxt = self.next_level(level_id)
                if nxt:
                    self.save.unlock_level(nxt)
        return self.next_scene(level_id, index)
