"""
engine/story.py

Story and replay layer: story cards, clue objects, collectibles, alternative spots and
the journal. Pure data logic shared by the scene loader, the core and the save; the
drawing lives in the core. Contract: docs/engine/STORY_AND_REPLAY.md. Web parity:
docs/web/WEB_EXPORT_SYNC.md, section M (the constants below reach the web runtime through
editor/web_rules.py::engine_rules()).
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any, Optional

# Typing speed of story and clue cards, characters per second.
STORY_CHARS_PER_S = 40.0
# Points for the first find of a collectible in a scene.
COLLECTIBLE_POINTS = 250
# Fields an alternative spot may override on its base object.
ALT_SPOT_FIELDS = ("x", "y", "rotation", "scale", "flip_x", "flip_y", "alpha",
                   "color_filter", "layer", "shadow")


@dataclass(frozen=True)
class StoryBlock:
    """The `story` block of a scene.json (all keys are i18n string keys)."""

    chapter_key: str = ""
    intro: tuple[str, ...] = ()
    outro: tuple[str, ...] = ()

    @property
    def is_empty(self) -> bool:
        return not self.intro and not self.outro


def parse_story(raw: Any) -> StoryBlock:
    """Reads a scene's `story` value; anything malformed becomes an empty block."""
    if not isinstance(raw, dict):
        return StoryBlock()

    def _keys(v: Any) -> tuple[str, ...]:
        if isinstance(v, str):
            v = [v]
        if not isinstance(v, list):
            return ()
        return tuple(k for k in v if isinstance(k, str) and k)

    chapter = raw.get("chapter_key")
    return StoryBlock(chapter_key=chapter if isinstance(chapter, str) else "",
                      intro=_keys(raw.get("intro")), outro=_keys(raw.get("outro")))


def resolve_alt_spot(raw_obj: dict, rng: Optional[random.Random] = None) -> dict:
    """Returns a copy of a raw scene object placed on its base spot or on one of its
    `alt_spots`, chosen uniformly. The returned dict has no `alt_spots` key."""
    obj = {k: v for k, v in raw_obj.items() if k != "alt_spots"}
    spots = raw_obj.get("alt_spots")
    if not isinstance(spots, list):
        return obj
    spots = [s for s in spots if isinstance(s, dict) and "x" in s and "y" in s]
    if not spots:
        return obj
    pick = (rng or random).randrange(len(spots) + 1)
    if pick == 0:
        return obj
    for key in ALT_SPOT_FIELDS:
        if key in spots[pick - 1]:
            obj[key] = spots[pick - 1][key]
    return obj


def is_clue(raw_obj: dict) -> bool:
    key = raw_obj.get("clue_key")
    return isinstance(key, str) and bool(key)


def is_collectible(raw_obj: dict) -> bool:
    return raw_obj.get("collectible") is True


def game_story_config(game_config: dict) -> dict:
    """The `story` block of game_config.json with string defaults."""
    raw = game_config.get("story") if isinstance(game_config, dict) else None
    raw = raw if isinstance(raw, dict) else {}
    return {
        "collectible_name_key": str(raw.get("collectible_name_key", "collectible_name")),
        "epilogue_key": str(raw.get("epilogue_key", "")),
        "epilogue_title_key": str(raw.get("epilogue_title_key", "")),
    }


@dataclass
class JournalEntry:
    """One line of the journal."""

    level_id: str
    scene_id: str
    scene_name_key: str
    clue_key: str = ""            # empty when the scene has no clue
    clue_object_id: str = ""      # catalog id of the clue object
    unlocked: bool = False        # the clue was found


@dataclass
class Journal:
    entries: list[JournalEntry] = field(default_factory=list)
    collectibles_found: int = 0
    collectibles_total: int = 0

    @property
    def epilogue_unlocked(self) -> bool:
        return self.collectibles_total > 0 and self.collectibles_found >= self.collectibles_total


def build_journal(scenes: list[tuple[str, str, dict]], clues_found: dict,
                  collectibles_found: list) -> Journal:
    """Journal in campaign order.

    scenes: (level_id, scene_id, scene_json) in campaign order.
    clues_found: save field `clues` (scene_id -> clue_key).
    collectibles_found: save field `collectibles` (scene ids).
    """
    journal = Journal()
    found_set = set(collectibles_found or [])
    for level_id, scene_id, data in scenes:
        objects = data.get("objects", []) if isinstance(data, dict) else []
        clue = next((o for o in objects if isinstance(o, dict) and is_clue(o)), None)
        if any(isinstance(o, dict) and is_collectible(o) for o in objects):
            journal.collectibles_total += 1
            if scene_id in found_set:
                journal.collectibles_found += 1
        if clue is None:
            continue
        journal.entries.append(JournalEntry(
            level_id=level_id, scene_id=scene_id,
            scene_name_key=str(data.get("name_key", scene_id)),
            clue_key=clue["clue_key"], clue_object_id=str(clue.get("catalog_id", "")),
            unlocked=scene_id in (clues_found or {})))
    return journal
