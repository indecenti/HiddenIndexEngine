"""Create (or complete) a game folder from a scenes module and generated backgrounds.

python build_game.py Ultimo_Treno scenes_ultimo_treno "L'Ultimo Treno per Valdoria"

- games/<id>/game_config.json (levels in story order, mystery theme, menu background)
- games/<id>/levels/<level>/level_config.json (scenes with `order`)
- games/<id>/levels/<level>/<scene>/scene.json (no objects yet) + background.png copied
  from scratch/gen_assets/backgrounds/<scene>.png when it exists
- games/<id>/strings/<lang>.json: game title, level and scene names (5 languages)
- games/<id>/objects_catalog.json (empty), ui_theme copied from the engine theme,
  main.py / run.bat copied from an existing game.
Existing files are never overwritten, except background.png when --backgrounds is given.
"""
import importlib
import json
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT))
from engine.utils import safe_write_json  # noqa: E402

LANGS = ("en", "it", "de", "es", "fr")
BG = ROOT / "scratch" / "gen_assets" / "backgrounds"
THEME = "mystery"
TIME_LIMIT = 120
TEMPLATE_GAME = ROOT / "games" / "nuovo_gioco"


def write_new(path: Path, data) -> None:
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        assert safe_write_json(path, data)


def main() -> None:
    game_id, module, title = sys.argv[1], sys.argv[2], sys.argv[3]
    copy_bg = "--backgrounds" in sys.argv
    mod = importlib.import_module(module)
    game = ROOT / "games" / game_id
    game.mkdir(parents=True, exist_ok=True)

    first_scene = mod.SCENES[0][1]
    write_new(game / "game_config.json", {
        "id": game_id, "game_id": game_id, "title_key": "game_title", "version": "1.0",
        "ui_theme": THEME, "category": "desktop",
        "levels": [lv for lv, _names in mod.LEVELS],
        "menu": {"background": f"levels/{mod.LEVELS[0][0]}/{first_scene}/background.png",
                 "music": []},
    })
    write_new(game / "objects_catalog.json", {"objects": []})
    for name in ("main.py", "run.bat"):
        if not (game / name).exists() and (TEMPLATE_GAME / name).exists():
            shutil.copy2(TEMPLATE_GAME / name, game / name)
    theme_src = ROOT / "engine" / "assets" / "themes" / THEME
    if not (game / "ui_theme").exists() and theme_src.exists():
        shutil.copytree(theme_src, game / "ui_theme")

    strings = {lang: {"game_title": title} for lang in LANGS}
    for level_id, names in mod.LEVELS:
        scenes = [s for s in mod.SCENES if s[0] == level_id]
        write_new(game / "levels" / level_id / "level_config.json", {
            "id": level_id, "name_key": f"{level_id}_name", "difficulty": "normal",
            "timer_behavior": "complete",
            "scenes": [{"id": s[1], "order": i + 1, "time_limit": TIME_LIMIT,
                        "transition_out": "fade"} for i, s in enumerate(scenes)],
        })
        for i, lang in enumerate(LANGS):
            strings[lang][f"{level_id}_name"] = names[i]
        for _lv, scene_id, _what, snames in scenes:
            sdir = game / "levels" / level_id / scene_id
            write_new(sdir / "scene.json", {
                "id": scene_id, "background": "background.png", "background_scale": 1.0,
                "objects": [], "effects": [], "music": [], "name_key": f"{scene_id}_name",
                "objects_to_show": 12, "auto_random_finds": False, "flashlight": False,
            })
            src = BG / f"{scene_id}.png"
            if src.exists() and (copy_bg or not (sdir / "background.png").exists()):
                shutil.copy2(src, sdir / "background.png")
            for i, lang in enumerate(LANGS):
                strings[lang][f"{scene_id}_name"] = snames[i]
    for lang in LANGS:
        path = game / "strings" / f"{lang}.json"
        current = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        for k, v in strings[lang].items():
            current.setdefault(k, v)
        path.parent.mkdir(parents=True, exist_ok=True)
        assert safe_write_json(path, current)
    have = sum((game / "levels" / s[0] / s[1] / "background.png").exists() for s in mod.SCENES)
    print(f"{game_id}: {len(mod.LEVELS)} levels, {len(mod.SCENES)} scenes, {have} backgrounds")


if __name__ == "__main__":
    main()
