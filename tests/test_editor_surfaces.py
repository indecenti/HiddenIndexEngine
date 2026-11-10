"""
tests/test_editor_surfaces.py

The placement surfaces in the editor (surfaces mode) and "Place on surfaces".

  1. surfaces.json: load, normalize, save, keys the editor does not edit kept;
  2. the geometry the canvas hit-tests;
  3. the commands are declared, reachable and translated, the legacy scatter is
     labelled as such and comes after the new one;
  4. the worker (with a fake placer: no model, no game) and the conversion of
     its result into the scene's objects, exactly as the command line tool
     writes them;
  5. the real editor, headless: drawing, editing, undo, the props panel, the
     dialog and Apply.
"""

from __future__ import annotations

import ast
import json
import os
import threading
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pytest

pygame = pytest.importorskip("pygame")

from editor.commands import COMMANDS, COMMANDS_BY_ID  # noqa: E402
from editor.constants import LANGS, MODE_SELECT, MODE_SURFACES, STATE_MAIN  # noqa: E402
from editor.core import surfaces as sf  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
STRINGS_DIR = ROOT / "engine" / "assets" / "strings"


# ─────────────────────────────────────────────────────────────────────────────
# 1. surfaces.json
# ─────────────────────────────────────────────────────────────────────────────

def test_a_scene_without_the_file_has_no_surfaces(tmp_path):
    assert sf.load_surfaces_doc(tmp_path) == {"surfaces": []}


def test_load_normalizes_and_keeps_the_other_keys(tmp_path):
    doc = {
        "surfaces": [
            {"p": [500.4, 300, 100, 320], "h": 85, "kind": "shelf"},
            {"p": [900, 800, 400, 600], "h": [80, 120], "kind": "area"},
            {"p": [0, 0, 10, 10], "h": 50, "kind": "nonsense"},
        ],
        "h_mul": 1.2, "light": {"min": 0.7}, "pool": ["a", "b"],
    }
    (tmp_path / sf.SURFACES_FILE).write_text(json.dumps(doc), encoding="utf-8")
    loaded = sf.load_surfaces_doc(tmp_path)
    line, area, other = loaded["surfaces"]
    assert line["p"] == [100, 320, 500, 300], "a line is stored left to right"
    assert line["h"] == 85
    assert area["p"] == [400, 600, 900, 800], "an area's corners are ordered"
    assert area["h"] == [80, 120]
    assert other["kind"] == sf.DEFAULT_KIND
    assert loaded["h_mul"] == 1.2 and loaded["light"] == {"min": 0.7}
    assert loaded["pool"] == ["a", "b"]


def test_save_round_trips(tmp_path):
    doc = {"surfaces": [sf.new_line(10, 50, 300, 52, 80),
                        sf.new_area(100, 400, 600, 700, 90, 130)],
           "h_mul": 0.9, "count": 30}
    assert sf.save_surfaces_doc(tmp_path, doc)
    again = sf.load_surfaces_doc(tmp_path)
    assert again == doc
    assert not list(tmp_path.glob("*.tmp")), "the write is atomic"


def test_an_empty_scene_gets_no_file(tmp_path):
    assert sf.save_surfaces_doc(tmp_path, {"surfaces": []})
    assert not (tmp_path / sf.SURFACES_FILE).exists()


def test_emptying_an_existing_file_writes_it(tmp_path):
    sf.save_surfaces_doc(tmp_path, {"surfaces": [sf.new_line(0, 10, 100, 10, 40)]})
    sf.save_surfaces_doc(tmp_path, {"surfaces": []})
    assert sf.load_surfaces_doc(tmp_path)["surfaces"] == []


def test_broken_entries_are_dropped(tmp_path):
    doc = {"surfaces": [{"p": [1, 2, 3]}, {"h": 4}, "x",
                        {"p": [0, 0, "a", 1], "h": 3},
                        {"p": [0, 5, 50, 5], "h": 30}]}
    (tmp_path / sf.SURFACES_FILE).write_text(json.dumps(doc), encoding="utf-8")
    assert len(sf.load_surfaces_doc(tmp_path)["surfaces"]) == 1


def test_an_unreadable_file_is_not_fatal(tmp_path):
    (tmp_path / sf.SURFACES_FILE).write_text("{not json", encoding="utf-8")
    assert sf.load_surfaces_doc(tmp_path) == {"surfaces": []}


# ─────────────────────────────────────────────────────────────────────────────
# 2. Geometry
# ─────────────────────────────────────────────────────────────────────────────

def test_hit_test_finds_handles_before_bodies():
    surfaces = [sf.new_line(100, 100, 300, 100, 50)]
    assert sf.hit_test(surfaces, 101, 99, 5) == (0, "p0")
    assert sf.hit_test(surfaces, 299, 101, 5) == (0, "p1")
    assert sf.hit_test(surfaces, 200, 103, 5) == (0, "body")
    assert sf.hit_test(surfaces, 200, 120, 5) is None


def test_hit_test_tries_the_selected_surface_first():
    a = sf.new_line(100, 100, 300, 100, 50)
    b = sf.new_line(100, 102, 300, 102, 50)
    assert sf.hit_test([a, b], 200, 101, 5)[0] == 1, "the last drawn is on top"
    assert sf.hit_test([a, b], 200, 101, 5, first=0)[0] == 0


def test_an_area_is_picked_inside_and_by_its_corners():
    area = sf.new_area(100, 100, 400, 300, 60)
    assert sf.hit_test([area], 250, 200, 5) == (0, "body")
    assert sf.hit_test([area], 400, 300, 5) == (0, "c2")


def test_kind_changes_keep_the_extent():
    line = sf.new_line(100, 500, 400, 500, 80)
    area = sf.with_kind(line, sf.AREA_KIND)
    assert area["kind"] == "area"
    assert area["p"] == [100, 420, 400, 500], "the line is the near edge"
    assert area["h"][0] == 80
    back = sf.with_kind(area, "table")
    assert back["p"] == [100, 420, 400, 420] and back["h"] == 80
    assert sf.with_kind(line, "sill")["p"] == line["p"]


def test_a_click_is_not_a_surface():
    assert not sf.long_enough(sf.new_line(10, 10, 12, 11, 40))
    assert sf.long_enough(sf.new_line(10, 10, 80, 11, 40))
    assert not sf.long_enough(sf.new_area(10, 10, 200, 14, 40))


def test_handles_move_one_end_only():
    line = sf.new_line(0, 0, 100, 0, 40)
    moved = sf.normalized(sf.with_handle(line, "p1", 150, 20))
    assert moved["p"] == [0, 0, 150, 20]
    crossed = sf.normalized(sf.with_handle(line, "p0", 200, 0))
    assert crossed["p"] == [100, 0, 200, 0], "crossing the other end flips the line"


def test_default_size_follows_the_background_width():
    assert sf.default_h(sf.REF_SCREEN_W) == sf.DEFAULT_H_SCREEN_PX
    assert sf.default_h(sf.REF_SCREEN_W * 2) == sf.DEFAULT_H_SCREEN_PX * 2


# ─────────────────────────────────────────────────────────────────────────────
# 3. Commands
# ─────────────────────────────────────────────────────────────────────────────

def test_the_surface_commands_are_declared():
    from editor.editor_base import LevelEditor
    for cid, method in (("tool_surfaces", "_surfaces_toggle_mode"),
                        ("place_surfaces", "_place_open_dialog")):
        command = COMMANDS_BY_ID[cid]
        assert command.run == ("call", method)
        assert command.needs == "scene"
        assert hasattr(LevelEditor, method)
    assert COMMANDS_BY_ID["tool_surfaces"].keys == "5"


def test_the_new_placement_comes_before_the_legacy_scatter():
    ids = [c.id for c in COMMANDS]
    assert ids.index("place_surfaces") < ids.index("autoscatter")


@pytest.mark.parametrize("lang", LANGS)
def test_the_legacy_scatter_says_it_is_legacy(lang):
    strings = json.loads((STRINGS_DIR / f"{lang}.json").read_text(encoding="utf-8"))
    for key in ("cmd_place_surfaces", "cmd_tool_surfaces", "tip_place_surfaces",
                "tip_mode_surfaces", "menu_view_surfaces", "menu_place_surfaces",
                "menu_legacy_scatter", "tb_surfaces_btn", "tb_place_surfaces_btn"):
        assert strings.get(key), f"{lang}: {key}"
    english = json.loads((STRINGS_DIR / "en.json").read_text(encoding="utf-8"))
    assert "Legacy" in english["cmd_autoscatter"]
    assert strings["cmd_autoscatter"] != strings["cmd_place_surfaces"]


def test_the_menu_commands_are_dispatched():
    source = (ROOT / "editor" / "mixins" / "input_handlers.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    handled = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_exec_menu_cmd":
            for cmp_node in ast.walk(node):
                if isinstance(cmp_node, ast.Compare):
                    for operand in cmp_node.comparators:
                        if isinstance(operand, ast.Constant):
                            handled.add(operand.value)
    assert {"view_surfaces", "edit_place_surfaces", "edit_legacy_scatter"} <= handled


def test_the_palette_offers_the_new_commands():
    from editor.commands import runnable_commands
    ids = {c.id for c in runnable_commands()}
    assert {"tool_surfaces", "place_surfaces", "autoscatter"} <= ids


# ─────────────────────────────────────────────────────────────────────────────
# 4. Worker and result -> scene objects
# ─────────────────────────────────────────────────────────────────────────────

PLANNED = [
    {"catalog_id": "faded_letter", "x": 10, "y": 20, "detection_type": "rect",
     "width": 40, "height": 30, "rotation": 0.0, "flip_x": False, "alpha": 255,
     "layer": "objects_mid", "is_goal": True, "hint_delay": 45,
     "color_filter": [200, 190, 180], "clue_key": "clue_S",
     "alt_spots": [{"x": 300, "y": 40, "rotation": 0.0, "scale": 1.1,
                    "flip_x": True, "color_filter": [180, 180, 180]}]},
    {"catalog_id": "pebble", "x": 100, "y": 120, "detection_type": "rect",
     "width": 20, "height": 20, "rotation": 1.0, "flip_x": True, "alpha": 255,
     "layer": "objects_mid", "is_goal": False, "hint_delay": 45,
     "color_filter": [210, 200, 190], "collectible": True},
]


def test_the_result_replaces_the_objects_like_the_tool():
    scene = {"background": "bg.png", "objects": [{"catalog_id": "old"}],
             "objects_to_show": ["old"], "auto_random_finds": False}
    kept = [{"catalog_id": "mg", "minigame_trigger": {"minigame_id": "sudoku"}}]
    out = sf.merged_scene(scene, kept, PLANNED, goals=7)
    assert [o["catalog_id"] for o in out["objects"]] == ["mg", "faded_letter", "pebble"]
    assert out["auto_random_finds"] is True and out["num_random_finds"] == 7
    assert "objects_to_show" not in out
    assert out["background"] == "bg.png"
    assert scene["objects"] == [{"catalog_id": "old"}], "the input is not modified"
    out["objects"][1]["x"] = -1
    assert PLANNED[0]["x"] == 10, "the result does not alias the plan"


def test_kept_objects_follow_the_mode():
    objects = [{"catalog_id": "a"},
               {"catalog_id": "b", "minigame_trigger": {"minigame_id": "x"}}]
    assert sf.kept_objects(objects, sf.KEEP_REPLACE, keep_minigames=False) == []
    assert [o["catalog_id"] for o in
            sf.kept_objects(objects, sf.KEEP_REPLACE, keep_minigames=True)] == ["b"]
    assert len(sf.kept_objects(objects, sf.KEEP_ALL, keep_minigames=False)) == 2


def test_a_variant_shows_the_alternative_spot():
    assert sf.with_variant(PLANNED[0], 0) is PLANNED[0]
    alt = sf.with_variant(PLANNED[0], 1)
    assert (alt["x"], alt["y"], alt["scale"]) == (300, 40, 1.1)
    assert alt["catalog_id"] == "faded_letter"
    assert sf.with_variant(PLANNED[1], 1) is PLANNED[1], "no alternative: the base"


def test_the_catalog_pool_needs_a_real_size():
    catalog = [{"id": "a", "style": "real", "tags": ["cucina"]},
               {"id": "b", "style": "real", "tags": []},
               {"id": "c", "style": "cartoon", "tags": ["cucina"]}]
    sizes = {"a": 10, "c": 10}
    assert sf.catalog_pool(catalog, "real", None, sizes) == ["a"]
    assert sf.catalog_pool(catalog, "cartoon", "cucina", sizes) == ["c"]
    assert sf.usable_pool(["a", "b", "c"], sizes) == ["a", "c"]


def test_the_plan_entry_is_found(tmp_path):
    plan = {"defaults": {"count": 30, "collectible": "pebble"},
            "scenes": [{"level": "L1", "scene": "S1", "seed": 4, "pool": ["a"]},
                       {"level": "L2", "scene": "S1", "seed": 5, "pool": ["b"]}]}
    (tmp_path / sf.PLAN_FILE).write_text(json.dumps(plan), encoding="utf-8")
    defaults, entry = sf.plan_for_scene(tmp_path, "L2", "S1")
    assert defaults["count"] == 30 and entry["seed"] == 5
    assert sf.plan_for_scene(tmp_path, "L3", "S9")[1] is None
    cfg = sf.base_config({"count": 40, "goals": 15}, defaults, entry,
                         {"surfaces": [], "h_mul": 1.1, "count": 25}, "L2", "S1")
    assert cfg["count"] == 25, "surfaces.json wins, like in the tool"
    assert cfg["goals"] == 15 and cfg["collectible"] == "pebble"
    assert cfg["scene"] == "S1" and cfg["h_mul"] == 1.1


class FakeBackground:
    def __init__(self):
        self.support_calls = 0

    def background(self):
        return "bg"

    def ensure_support(self):
        self.support_calls += 1
        return None


class FakePlacer:
    """plan_scene with the progress hook of tools/place_on_surfaces.py."""

    def __init__(self, on_step=None, fail=False):
        self.on_step = on_step
        self.fail = fail
        self.seen_cfg = None

    def plan_scene(self, cfg, bg, existing, progress=None):
        self.seen_cfg = cfg
        if self.fail:
            raise RuntimeError("boom")
        for i in range(len(PLANNED)):
            if self.on_step:
                self.on_step(i)
            if progress:
                progress("place", i + 1, len(PLANNED))
        return json.loads(json.dumps(PLANNED))

    def render(self, bg, objects, variant):
        from PIL import Image
        return Image.new("RGB", (8, 8))

    def audit_sheet(self, bg, objects, clean):
        from PIL import Image
        return Image.new("RGB", (60, 30), (20, 20, 20))


class OldPlacer(FakePlacer):
    """A tool without the progress hook: the job must still run."""

    def plan_scene(self, cfg, bg, existing):
        return super().plan_scene(cfg, bg, existing)


def _job(placer, surfaces, kept=None):
    cfg = {"surfaces": surfaces, "count": 2, "goals": 1, "seed": 9, "pool": ["a"]}
    bg = FakeBackground()
    job = sf.PlaceJob(game_id="g", scene_bg=bg, cfg=cfg, kept=kept or [],
                      placer_cache={"g": placer})
    return job, bg


def test_the_job_returns_the_plan_and_the_audit():
    placer = FakePlacer()
    job, bg = _job(placer, [sf.new_line(0, 10, 100, 10, 40)])
    job.run()
    assert job.finished.is_set() and not job.error and not job.cancelled
    assert job.outcome.planned == PLANNED
    assert job.outcome.seed == 9 and job.outcome.goals == 1 and job.outcome.count == 2
    assert job.outcome.audit.size == (60, 30)
    assert bg.support_calls == 0, "lines only: no support map"


def test_the_job_computes_the_support_map_for_areas():
    job, bg = _job(FakePlacer(), [sf.new_area(0, 0, 100, 100, 40)])
    job.run()
    assert bg.support_calls == 1


def test_the_job_can_be_cancelled_from_the_progress_hook():
    holder = {}
    placer = FakePlacer(on_step=lambda i: holder["job"].cancel() if i == 1 else None)
    job, _bg = _job(placer, [sf.new_line(0, 10, 100, 10, 40)])
    holder["job"] = job
    job.run()
    assert job.cancelled and job.outcome is None and not job.error


def test_the_job_works_with_a_tool_without_hooks():
    job, _bg = _job(OldPlacer(), [sf.new_line(0, 10, 100, 10, 40)])
    job.run()
    assert job.outcome is not None and len(job.outcome.planned) == 2


def test_the_job_reports_an_error():
    job, _bg = _job(FakePlacer(fail=True), [sf.new_line(0, 10, 100, 10, 40)])
    job.run()
    assert job.error == "boom" and job.outcome is None


def test_the_job_runs_in_a_thread():
    job, _bg = _job(FakePlacer(), [sf.new_line(0, 10, 100, 10, 40)])
    job.start()
    assert job.finished.wait(10)
    assert job.outcome is not None


def test_the_tool_hooks_are_present():
    """The editor relies on two optional hooks of tools/place_on_surfaces.py."""
    import inspect
    mod = sf.import_placer()
    assert "progress" in inspect.signature(mod.Placer.plan_scene).parameters
    assert "model_factory" in inspect.signature(mod.Background.load_support).parameters


def test_importing_the_tool_leaves_the_environment_alone(monkeypatch):
    monkeypatch.setattr(sf, "_placer_module", None)
    monkeypatch.setenv(sf.CUDA_ENV, "0")
    import sys
    monkeypatch.delitem(sys.modules, sf.PLACER_MODULE, raising=False)
    sf.import_placer()
    assert os.environ[sf.CUDA_ENV] == "0"


# ─────────────────────────────────────────────────────────────────────────────
# 5. The real editor, headless
# ─────────────────────────────────────────────────────────────────────────────

BG_SIZE = (1280, 720)


@pytest.fixture(scope="module")
def editor():
    from editor.editor_base import LevelEditor
    from editor.ui.draw import _init_fonts
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(LevelEditor, "_scatter_preload_async", lambda self: None)
        mp.setattr(LevelEditor, "_save_recent", lambda self, p: None)
        mp.setattr(LevelEditor, "_save_editor_setting", lambda self, k, v: None)
        pygame.init()
        ed = LevelEditor(ROOT)
        ed.screen = pygame.display.set_mode((1600, 900))
        ed.screen_size = ed.screen.get_size()
        _init_fonts(1.0)
        yield ed
        ed.running = False
    pygame.quit()


@pytest.fixture
def scene(editor, tmp_path):
    """A scene folder in tmp_path, open in the editor, no game catalog."""
    scene_dir = tmp_path / "Level" / "Scene"
    scene_dir.mkdir(parents=True)
    surf = pygame.Surface(BG_SIZE)
    surf.fill((90, 80, 70))
    pygame.image.save(surf, str(scene_dir / "bg.png"))
    editor.state = STATE_MAIN
    editor.game_path = tmp_path / "game"
    editor.catalog = []
    editor.scene_path = scene_dir
    editor.scene_data = {"background": "bg.png",
                         "objects": [{"catalog_id": "old", "x": 5, "y": 5,
                                      "detection_type": "rect", "width": 10,
                                      "height": 10}]}
    editor.bg_surf = surf
    editor.undo_stack.clear()
    editor.redo_stack.clear()
    editor.scene_dirty = False
    editor.modal_stack.clear()
    editor._place_reset()
    editor._surfaces_reset()
    editor.mode = MODE_SELECT
    # 1:1 view on whole pixels: a point dragged on screen is that exact
    # background pixel, so the tests can compare coordinates exactly.
    cr = editor._canvas_rect()
    editor.zoom, editor.origin_x, editor.origin_y = 1.0, float(cr.x), float(cr.y)
    editor._mark_dirty()
    yield editor
    editor._place_reset()
    editor.mode = MODE_SELECT
    editor.scene_path = None


def _drag(ed, a, b, shift=False, monkeypatch=None):
    sa, sb = ed._r2s(*a), ed._r2s(*b)
    if monkeypatch is not None:
        monkeypatch.setattr(pygame.key, "get_mods",
                            lambda: pygame.KMOD_SHIFT if shift else 0)
    ed._surfaces_ldown(int(sa[0]), int(sa[1]))
    ed._surfaces_motion(int(sb[0]), int(sb[1]))
    ed._surfaces_lup(int(sb[0]), int(sb[1]))


def _on_disk(ed):
    return json.loads((ed.scene_path / sf.SURFACES_FILE).read_text(encoding="utf-8"))


def test_the_mode_toggles(scene):
    scene._surfaces_toggle_mode()
    assert scene.mode == MODE_SURFACES
    scene._surfaces_toggle_mode()
    assert scene.mode == MODE_SELECT


def test_a_drag_draws_a_line_saved_at_once(scene, monkeypatch):
    scene._surfaces_toggle_mode()
    _drag(scene, (600, 300), (200, 310), monkeypatch=monkeypatch)
    surfaces = scene._surfaces()
    assert len(surfaces) == 1
    line = surfaces[0]
    assert line["kind"] == sf.DEFAULT_KIND
    assert line["p"][0] < line["p"][2], "stored left to right"
    assert _on_disk(scene)["surfaces"] == surfaces
    assert scene._surf_sel == 0
    assert scene.scene_dirty is False, "surfaces.json is saved, the scene is untouched"


def test_shift_drag_draws_an_area(scene, monkeypatch):
    scene._surfaces_toggle_mode()
    _drag(scene, (100, 400), (500, 600), shift=True, monkeypatch=monkeypatch)
    assert scene._surfaces()[0]["kind"] == sf.AREA_KIND
    assert isinstance(scene._surfaces()[0]["h"], list)


def test_a_click_draws_nothing(scene, monkeypatch):
    scene._surfaces_toggle_mode()
    _drag(scene, (100, 400), (101, 401), monkeypatch=monkeypatch)
    assert scene._surfaces() == []
    assert not (scene.scene_path / sf.SURFACES_FILE).exists()


def test_undo_and_redo_restore_the_file(scene, monkeypatch):
    scene._surfaces_toggle_mode()
    _drag(scene, (100, 300), (500, 300), monkeypatch=monkeypatch)
    _drag(scene, (100, 500), (500, 500), monkeypatch=monkeypatch)
    assert len(_on_disk(scene)["surfaces"]) == 2
    scene._undo()
    assert len(scene._surfaces()) == 1 and len(_on_disk(scene)["surfaces"]) == 1
    scene._redo()
    assert len(scene._surfaces()) == 2 and len(_on_disk(scene)["surfaces"]) == 2
    assert "__editor_extra__" not in scene.scene_data


def test_dragging_an_end_moves_it(scene, monkeypatch):
    scene._surfaces_toggle_mode()
    _drag(scene, (100, 300), (500, 300), monkeypatch=monkeypatch)
    _drag(scene, (500, 300), (600, 280), monkeypatch=monkeypatch)
    assert scene._surfaces()[0]["p"] == [100, 300, 600, 280]
    scene._undo()
    assert scene._surfaces()[0]["p"] == [100, 300, 500, 300]


def test_delete_and_escape(scene, monkeypatch):
    scene._surfaces_toggle_mode()
    _drag(scene, (100, 300), (500, 300), monkeypatch=monkeypatch)
    delete = pygame.event.Event(pygame.KEYDOWN, key=pygame.K_DELETE, unicode="", mod=0)
    assert scene._surfaces_key(delete)
    assert scene._surfaces() == [] and _on_disk(scene)["surfaces"] == []
    assert scene.scene_data["objects"], "Delete in this mode never deletes objects"
    escape = pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE, unicode="", mod=0)
    scene._surfaces_key(escape)
    assert scene.mode == MODE_SELECT


def test_the_panel_edits_the_size_and_the_kind(scene, monkeypatch):
    scene._surfaces_toggle_mode()
    _drag(scene, (100, 300), (500, 300), monkeypatch=monkeypatch)
    scene._surface_prop_commit(0, "h", "123")
    scene._surfaces_set_kind(0, "sill")
    scene._surfaces_set_value(-1, "h_mul", 1.25)
    scene._surfaces_set_value(0, "max", 3)
    saved = _on_disk(scene)
    assert saved["surfaces"][0]["h"] == 123 and saved["surfaces"][0]["kind"] == "sill"
    assert saved["surfaces"][0]["max"] == 3 and saved["h_mul"] == 1.25
    scene._surfaces_set_value(0, "max", None)
    assert "max" not in _on_disk(scene)["surfaces"][0]
    assert scene.scene_dirty is False


def test_the_mode_renders_with_its_panel(scene, monkeypatch):
    scene._surfaces_toggle_mode()
    _drag(scene, (100, 300), (500, 300), monkeypatch=monkeypatch)
    _drag(scene, (100, 400), (500, 600), shift=True, monkeypatch=monkeypatch)
    scene._render()
    hits = scene._surface_props_hitboxes
    assert {"h_far_box", "h_near_box", "delete", "place", "kind_area"} <= set(hits)
    assert scene._surfaces_bar_layout(), "the sub-toolbar is laid out"


def test_the_panel_click_reaches_the_surface(scene, monkeypatch):
    scene._surfaces_toggle_mode()
    _drag(scene, (100, 300), (500, 300), monkeypatch=monkeypatch)
    scene.panels_visible = True
    scene._render()
    before = scene._surfaces()[0]["h"]
    plus = scene._surface_props_hitboxes["h_plus"]
    assert scene._surface_props_click(plus.centerx, plus.centery)
    assert scene._surfaces()[0]["h"] == before + 1


def test_the_dialog_opens_lays_out_and_closes(scene, monkeypatch):
    scene._surfaces_toggle_mode()
    _drag(scene, (100, 300), (500, 300), monkeypatch=monkeypatch)
    scene._place_open_dialog()
    assert scene._place_modal_open
    scene._render()
    layout = scene._place_hitboxes
    box = layout["box"]
    for name, value in layout.items():
        rect = value[0] if isinstance(value, tuple) else value
        if isinstance(rect, pygame.Rect) and name != "box":
            assert box.contains(rect), f"{name} is outside the dialog"
    escape = pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE, unicode="", mod=0)
    assert scene._place_event(escape)
    assert not scene._place_modal_open


def test_without_surfaces_the_command_opens_the_mode(scene):
    scene._place_open_dialog()
    assert not scene._place_modal_open
    assert scene.mode == MODE_SURFACES


def test_apply_writes_the_objects_and_undo_brings_them_back(scene, monkeypatch):
    scene._surfaces_toggle_mode()
    _drag(scene, (100, 300), (500, 300), monkeypatch=monkeypatch)
    scene._place_modal_open = True
    scene._place_stage = "result"
    scene._place_outcome = sf.PlaceOutcome(planned=json.loads(json.dumps(PLANNED)),
                                           kept=[], seed=3, count=2, goals=1)
    scene._place_kept_idx = set()
    assert scene._canvas_hides_object(0), "the replaced object is hidden"
    scene._render()                         # ghosts + result bar
    assert "apply" in scene._place_hitboxes
    scene._place_apply()
    objects = scene.scene_data["objects"]
    assert [o["catalog_id"] for o in objects] == ["faded_letter", "pebble"]
    assert scene.scene_data["auto_random_finds"] is True
    assert scene.scene_data["num_random_finds"] == 1
    assert scene.scene_dirty is True
    assert not scene._place_modal_open
    scene._undo()
    assert [o["catalog_id"] for o in scene.scene_data["objects"]] == ["old"]


def test_the_audit_view_scrolls_and_closes(scene):
    from editor.mixins.place_modal import AuditView
    sheet = pygame.Surface((1800, 3000))
    view = AuditView(sheet)
    scene._modal_push(view)
    view.render(scene)
    assert view.max_scroll() > 0
    view.handle_event(scene, pygame.event.Event(pygame.MOUSEWHEEL, x=0, y=-3))
    assert view.scroll > 0
    view.handle_event(scene, pygame.event.Event(pygame.KEYDOWN, key=pygame.K_END,
                                                unicode="", mod=0))
    assert view.scroll == view.max_scroll()
    view.handle_event(scene, pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE,
                                                unicode="", mod=0))
    assert view not in scene.modal_stack


def test_the_run_goes_through_the_worker(scene, monkeypatch):
    """_place_run builds the job; the fake placer answers through the cache."""
    scene._surfaces_toggle_mode()
    _drag(scene, (100, 300), (500, 300), monkeypatch=monkeypatch)
    scene.catalog = [{"id": "a", "style": "real", "tags": []},
                     {"id": "faded_letter", "style": "real", "tags": []}]
    scene._place_open_dialog()
    scene._place_opts.update({"pool": sf.POOL_CATALOG, "clue": "", "collectible": ""})
    monkeypatch.setattr(scene, "_place_real_sizes", {"a": 10})
    monkeypatch.setattr(scene, "_scatter_style", "real")
    monkeypatch.setattr(scene, "_scatter_tag", None)
    placer = FakePlacer()
    scene._place_placers[(scene.game_path.name, getattr(scene, "_catalog_rev", 0))] = placer
    started = threading.Event()
    monkeypatch.setattr(sf.SceneBackground, "background", lambda self: "bg")
    original_start = sf.PlaceJob.start

    def start(job):
        started.set()
        original_start(job)

    monkeypatch.setattr(sf.PlaceJob, "start", start)
    scene._place_run()
    assert started.is_set() and scene._place_busy
    assert scene._place_job.finished.wait(10)
    scene._place_poll()
    assert scene._place_stage == "result"
    assert placer.seen_cfg["pool"] == ["a"]
    assert placer.seen_cfg["surfaces"] == scene._surfaces()
    assert placer.seen_cfg["scene"] == "Scene" and placer.seen_cfg["level"] == "Level"
