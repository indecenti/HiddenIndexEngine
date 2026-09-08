"""
tests/test_editor_save_as.py

"Save scene as...": the File menu offered it from the beginning and nothing was
wired to it - `_exec_menu_cmd` had no branch for `file_save_as`, so the entry
did nothing at all, silently. tests/test_editor_commands.py now refuses a menu
command with no branch; this pins what the operation does:

  1. the scene folder is copied next to the original, under a free name;
  2. the copy carries the scene as it is being edited, not the one on disk;
  3. the copy is registered in level_config.json right after the original,
     because a scene missing from that file is never played;
  4. the autosave of the original does not follow the copy;
  5. the editor ends up on the copy, leaving the original untouched.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pytest

pygame = pytest.importorskip("pygame")

from editor.mixins.game_select import GameSelectMixin
from editor.mixins.io_ops import IoOpsMixin


class FakeSaver(IoOpsMixin, GameSelectMixin):
    """Only the parts _save_scene_as needs: the writes are the real ones."""

    def __init__(self, scene_dir: Path):
        self.scene_path = scene_dir
        self.scene_data = {"id": scene_dir.name, "objects": [{"catalog_id": "x"}]}
        self.status: list = []
        self.loaded: list = []
        self.saved: list = []

    def _TR(self, key, *args):
        return args[0] if args else key

    def _status(self, message, colour=None, seconds=0):
        self.status.append(message)

    def _save(self):
        # The real _save needs the whole editor: write the scene the way it
        # would, which is what the test is about.
        self.saved.append(self.scene_path)
        (self.scene_path / "scene.json").write_text(
            json.dumps(self.scene_data), encoding="utf-8")

    def _load_scene(self, path):
        self.loaded.append(path)


def _level(tmp_path: Path, scene_name: str = "Room", *, with_config=True) -> Path:
    level = tmp_path / "levels" / "One"
    scene = level / scene_name
    scene.mkdir(parents=True)
    (scene / "scene.json").write_text(
        json.dumps({"id": scene_name, "objects": []}), encoding="utf-8")
    (scene / "background.png").write_bytes(b"not really a png")
    if with_config:
        (level / "level_config.json").write_text(json.dumps({
            "scenes": [{"id": scene_name, "order": 1, "time_limit": 120}]
        }), encoding="utf-8")
    return scene


def test_save_as_copies_the_folder_next_to_the_original(tmp_path):
    scene = _level(tmp_path)
    host = FakeSaver(scene)
    host._save_scene_as()

    copies = [p for p in scene.parent.iterdir() if p.is_dir() and p != scene]
    assert len(copies) == 1
    assert (copies[0] / "background.png").exists(), "the assets come along"
    assert scene.exists(), "the original stays"


def test_save_as_writes_the_scene_being_edited(tmp_path):
    scene = _level(tmp_path)
    host = FakeSaver(scene)
    host.scene_data["objects"] = [{"catalog_id": "unsaved_edit"}]
    host._save_scene_as()

    copy = next(p for p in scene.parent.iterdir() if p.is_dir() and p != scene)
    written = json.loads((copy / "scene.json").read_text(encoding="utf-8"))
    assert written["objects"] == [{"catalog_id": "unsaved_edit"}]
    assert written["id"] == copy.name, "the copy carries its own id"


def test_save_as_registers_the_copy_after_the_original(tmp_path):
    scene = _level(tmp_path)
    host = FakeSaver(scene)
    host._save_scene_as()

    cfg = json.loads((scene.parent / "level_config.json").read_text(encoding="utf-8"))
    ids = [s["id"] for s in cfg["scenes"]]
    assert ids[0] == "Room"
    assert len(ids) == 2 and ids[1].startswith("Room")
    assert [s["order"] for s in cfg["scenes"]] == [1, 2]


def test_save_as_registers_an_orphan_original_too(tmp_path):
    scene = _level(tmp_path)
    cfg_path = scene.parent / "level_config.json"
    cfg_path.write_text(json.dumps({"scenes": []}), encoding="utf-8")

    FakeSaver(scene)._save_scene_as()

    ids = [s["id"] for s in json.loads(cfg_path.read_text(encoding="utf-8"))["scenes"]]
    assert ids[0] == "Room", "the orphan original is registered first"
    assert len(ids) == 2


def test_save_as_without_a_level_config_still_copies(tmp_path):
    scene = _level(tmp_path, with_config=False)
    host = FakeSaver(scene)
    host._save_scene_as()
    assert any(p.is_dir() and p != scene for p in scene.parent.iterdir())


def test_save_as_does_not_inherit_the_autosave(tmp_path):
    scene = _level(tmp_path)
    (scene / "scene.json.autosave").write_text("{}", encoding="utf-8")
    host = FakeSaver(scene)
    host._save_scene_as()

    copy = next(p for p in scene.parent.iterdir() if p.is_dir() and p != scene)
    assert not (copy / "scene.json.autosave").exists()
    assert (scene / "scene.json.autosave").exists(), "the original keeps its own"


def test_save_as_leaves_the_editor_on_the_copy(tmp_path):
    scene = _level(tmp_path)
    host = FakeSaver(scene)
    host._save_scene_as()

    copy = next(p for p in scene.parent.iterdir() if p.is_dir() and p != scene)
    assert host.scene_path == copy
    assert host.loaded == [copy]


def test_save_as_twice_never_reuses_a_name(tmp_path):
    scene = _level(tmp_path)
    host = FakeSaver(scene)
    host._save_scene_as()
    host._save_scene_as()

    copies = sorted(p.name for p in scene.parent.iterdir()
                    if p.is_dir() and p != scene)
    assert len(copies) == len(set(copies)) == 2


def test_save_as_without_a_scene_says_so(tmp_path):
    host = FakeSaver(tmp_path)
    host.scene_path = None
    host._save_scene_as()
    assert host.status and not host.loaded
