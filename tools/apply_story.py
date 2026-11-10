"""Write the story blocks of a game's scenes from its string keys (docs/engine/STORY_AND_REPLAY.md).

Convention (skill write-story): for a scene <id> the texts are the keys
  <id>_name                     scene name
  <id>_intro_1, _intro_2, ...   story cards before the scene
  <id>_outro_1, ...             story cards after it
  clue_<id>                     text of the scene's clue (object with clue_key)
and the chapter heading of level n (campaign order, 1-based) is ch<n>_title, shown on the
first intro card of the level's first scene.

For every scene this sets `story` (intro/outro keys that exist in the source language
file, chapter_key on a level's first scene) and `name_key`; with --music it sets the
scene music per level; with --drop-bubbles it removes the bubble tips (their texts are
usually the generic ones the story replaces).

Usage:
    python tools/apply_story.py <game_id> [--lang=it] [--drop-bubbles]
                                [--music=<level_id>:<file.mp3>] ...
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from engine.campaign import ordered_level_ids, ordered_scene_ids  # noqa: E402
from engine.utils import safe_write_json  # noqa: E402

log = logging.getLogger("apply_story")
DEFAULT_LANG = "it"


def _keys(strings: dict, scene_id: str, kind: str) -> list[str]:
    out, n = [], 1
    while f"{scene_id}_{kind}_{n}" in strings:
        out.append(f"{scene_id}_{kind}_{n}")
        n += 1
    return out


def apply(game_id: str, lang: str, drop_bubbles: bool, music: dict[str, str]) -> int:
    game = REPO / "games" / game_id
    strings = json.loads((game / "strings" / f"{lang}.json").read_text(encoding="utf-8"))
    config = json.loads((game / "game_config.json").read_text(encoding="utf-8"))
    level_dirs = sorted(p.name for p in (game / "levels").iterdir()
                        if (p / "level_config.json").exists())
    changed = 0
    for n, level_id in enumerate(ordered_level_ids(config.get("levels", []), level_dirs), 1):
        level_cfg = json.loads((game / "levels" / level_id / "level_config.json")
                               .read_text(encoding="utf-8"))
        for i, scene_id in enumerate(ordered_scene_ids(level_cfg)):
            path = game / "levels" / level_id / scene_id / "scene.json"
            if not path.exists():
                log.warning("missing %s", path)
                continue
            data = json.loads(path.read_text(encoding="utf-8"))
            story = {"intro": _keys(strings, scene_id, "intro"),
                     "outro": _keys(strings, scene_id, "outro")}
            chapter = f"ch{n}_title"
            if i == 0 and chapter in strings:
                story["chapter_key"] = chapter
            data["story"] = story
            if f"{scene_id}_name" in strings:
                data["name_key"] = f"{scene_id}_name"
            if level_id in music:
                data["music"] = [music[level_id]]
            if drop_bubbles:
                data["effects"] = [e for e in data.get("effects", [])
                                   if e.get("type") != "bubble_tip"]
            safe_write_json(str(path), data)
            changed += 1
            clue = [o for o in data.get("objects", []) if o.get("clue_key")]
            if f"clue_{scene_id}" in strings and not clue:
                log.warning("%s: clue text exists but no object has clue_key", scene_id)
            log.info("%s/%s: %d intro, %d outro%s", level_id, scene_id, len(story["intro"]),
                     len(story["outro"]), " + chapter" if "chapter_key" in story else "")
    return changed


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = sys.argv[1:]
    lang = next((a.split("=", 1)[1] for a in args if a.startswith("--lang=")), DEFAULT_LANG)
    music = dict(a.split("=", 1)[1].split(":", 1) for a in args if a.startswith("--music="))
    game_id = next(a for a in args if not a.startswith("--"))
    n = apply(game_id, lang, "--drop-bubbles" in args, music)
    log.info("%d scenes updated", n)


if __name__ == "__main__":
    main()
