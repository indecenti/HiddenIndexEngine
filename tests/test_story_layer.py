"""
tests/test_story_layer.py

The desktop side of the story and replay layer (docs/engine/STORY_AND_REPLAY.md):

  - the scene loader resolves alternative spots before the layer filter and the
    goal rotation, keeps clue objects as goals and collectibles out of the goals;
  - the save records clues and collectibles and still reads saves without them;
  - the journal is built in campaign order;
  - in a real EngineCore (headless, playtest mode, on a temporary game) story and
    clue cards open at the right moments, swallow the clicks and stop the clock,
    the outro plays before SCENE_COMPLETE, a collectible pays only once, and the
    journal opens from the J key and from the pause menu.

The temporary game lives in tmp_path: every engine module's get_resource_path is
redirected for that game id only, so nothing is written under games/.
"""

from __future__ import annotations

import configparser
import json
import os
import random
import sys
from types import SimpleNamespace

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pytest

pygame = pytest.importorskip("pygame")

import engine.utils as engine_utils  # noqa: E402
from engine import story  # noqa: E402
from engine.save_manager import SaveManager  # noqa: E402
# Imported up front, so they bind the real get_resource_path (see game_root).
import engine.campaign  # noqa: E402,F401
import engine.catalog_manager  # noqa: E402,F401
import engine.core  # noqa: E402,F401
import engine.level_manager  # noqa: E402,F401
import engine.scene_loader  # noqa: E402,F401

GAME_ID = "_story_layer_test_game"
LEVEL_ID = "lvl1"
SCENE_ID = "scene_a"
SCENE_B = "scene_b"
SCREEN = (1280, 720)
DT = 1 / 30.0
ICONS = {
    "lamp": "objects_cartoon/ca_acorn.png",
    "key": "objects_cartoon/ca_accordion_wood.png",
    "coin": "objects_cartoon/ca_advent_calendar.png",
    "book": "objects_cartoon/ca_abacus_wooden.png",
    "shell": "objects_cartoon/ca_acorn.png",
    "star": "objects_cartoon/ca_acorn.png",
}
STRINGS_EN = {
    "intro_1": "The train stopped in the middle of the valley.",
    "intro_2": "Nobody got off.",
    "outro_1": "The lights went out behind us.",
    "ch1": "Chapter One",
    "clue_a": "A radio still tuned to the night frequency.",
    "clue_b": "A key with a number scratched on it.",
    "collectible_name": "Golden acorn",
    "epilogue_title": "Epilogue",
    "epilogue_text": "Every acorn found its way home.",
    "obj_key": "Old key",
}


# -----------------------------------------------------------------------------
# Temporary game
# -----------------------------------------------------------------------------

def _obj(cid: str, x: float, y: float, **extra) -> dict:
    base = {"catalog_id": cid, "x": x, "y": y, "detection_type": "circle", "radius": 40}
    base.update(extra)
    return base


def _scene(scene_id: str, objects: list, **extra) -> dict:
    data = {"id": scene_id, "name_key": f"{scene_id}_name", "background": "background.png",
            "objects": objects}
    data.update(extra)
    return data


def _default_scene_a() -> dict:
    return _scene(SCENE_ID, [
        _obj("lamp", 200, 200),
        _obj("key", 600, 300, clue_key="clue_a"),
        _obj("star", 1000, 500, collectible=True),
    ], story={"chapter_key": "ch1", "intro": ["intro_1", "intro_2"], "outro": ["outro_1"]})


def _default_scene_b() -> dict:
    return _scene(SCENE_B, [_obj("coin", 300, 300), _obj("book", 700, 400, clue_key="clue_b"),
                            _obj("shell", 900, 200, collectible=True)])


def _write(path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def build_game(root, scenes: dict[str, dict]) -> None:
    """games/<GAME_ID> under root with one level and the given scenes."""
    game = root / "games" / GAME_ID
    _write(game / "game_config.json", {
        "game_id": GAME_ID, "version": "1.0", "title_key": "title",
        "menu": {"background": "menu.png"},
        "levels": [LEVEL_ID], "default_language": "en",
        "story": {"collectible_name_key": "collectible_name",
                  "epilogue_key": "epilogue_text", "epilogue_title_key": "epilogue_title"},
    })
    _write(game / "objects_catalog.json", {"objects": [
        {"id": cid, "label_key": f"obj_{cid}", "icon": icon, "tags": []}
        for cid, icon in ICONS.items()]})
    _write(game / "levels" / LEVEL_ID / "level_config.json", {
        "id": LEVEL_ID,
        "scenes": [{"id": sid, "order": i, "time_limit": 120}
                   for i, sid in enumerate(scenes, start=1)]})
    _write(game / "strings" / "en.json", STRINGS_EN)
    for sid, data in scenes.items():
        scene_dir = game / "levels" / LEVEL_ID / sid
        _write(scene_dir / "scene.json", data)
        bg = pygame.Surface(SCREEN)
        bg.fill((40, 60, 50))
        pygame.image.save(bg, str(scene_dir / "background.png"))


@pytest.fixture(scope="module")
def display():
    pygame.init()
    pygame.font.init()
    surface = pygame.display.set_mode(SCREEN)
    yield surface
    pygame.quit()


@pytest.fixture(autouse=True)
def _restore_active_language():
    """An EngineCore registers its LanguageManager globally: put the old one back."""
    from engine.language_manager import get_active_manager, set_active_manager
    previous = get_active_manager()
    yield
    set_active_manager(previous)


@pytest.fixture
def game_root(tmp_path, monkeypatch, display):
    """Redirects games/<GAME_ID>/... of every engine module into tmp_path."""
    real = engine_utils.get_resource_path
    assert not getattr(real, "story_test_redirect", False)

    def redirected(*parts):
        if len(parts) >= 2 and parts[0] == "games" and parts[1] == GAME_ID:
            return tmp_path.joinpath(*parts)
        return real(*parts)

    redirected.story_test_redirect = True
    monkeypatch.setattr(engine_utils, "get_resource_path", redirected)
    # Modules first imported while a previous test's redirect was in place hold
    # that redirect: they are re-pointed too.
    for name, module in list(sys.modules.items()):
        current = getattr(module, "get_resource_path", None) if name.startswith("engine") else None
        if current is real or getattr(current, "story_test_redirect", False):
            monkeypatch.setattr(module, "get_resource_path", redirected)
    return tmp_path


def make_loader(root, scenes: dict[str, dict]):
    from engine.catalog_manager import load_catalog
    from engine.scene_loader import SceneLoader
    build_game(root, scenes)
    return SceneLoader(GAME_ID, load_catalog(GAME_ID))


def by_cid(scene_data, cid: str):
    return next(o for o in scene_data.objects if o.catalog_id == cid)


# -----------------------------------------------------------------------------
# Scene loader
# -----------------------------------------------------------------------------

def test_alt_spots_are_resolved_by_the_loader(game_root):
    loader = make_loader(game_root, {SCENE_ID: _scene(SCENE_ID, [
        _obj("lamp", 100, 120, rotation=0.0,
             alt_spots=[{"x": 900, "y": 50, "rotation": 12.0, "flip_x": True}]),
    ])})
    random.seed(7)
    placements = set()
    for _ in range(40):
        lamp = by_cid(loader.load_scene(LEVEL_ID, SCENE_ID), "lamp")
        placements.add((lamp.x, lamp.y, lamp.rotation, lamp.flip_x))
    assert placements == {(100.0, 120.0, 0.0, False), (900.0, 50.0, 12.0, True)}


def test_alt_spot_layer_counts_for_random_layer_selection(game_root, monkeypatch):
    """The spot is resolved first, so its layer decides the random layer filter."""
    loader = make_loader(game_root, {SCENE_ID: _scene(SCENE_ID, [
        _obj("lamp", 100, 120, layer="objects_low",
             alt_spots=[{"x": 900, "y": 50, "layer": "objects_high"}]),
        _obj("coin", 300, 300, layer="objects_low"),
    ], random_layer_selection=True)})
    monkeypatch.setattr(random, "choice", lambda seq: "objects_high")
    monkeypatch.setattr(random, "randrange", lambda n: 1)   # always the first alt spot
    data = loader.load_scene(LEVEL_ID, SCENE_ID)
    assert [o.catalog_id for o in data.objects] == ["lamp"]
    assert by_cid(data, "lamp").layer == "objects_high"
    assert by_cid(data, "lamp").x == 900.0


def test_story_fields_are_carried_on_objects_and_scene(game_root):
    loader = make_loader(game_root, {SCENE_ID: _default_scene_a()})
    data = loader.load_scene(LEVEL_ID, SCENE_ID)
    assert by_cid(data, "key").clue_key == "clue_a"
    assert by_cid(data, "star").collectible is True
    assert by_cid(data, "lamp").clue_key == "" and by_cid(data, "lamp").collectible is False
    assert data.story.chapter_key == "ch1"
    assert data.story.intro == ("intro_1", "intro_2")
    assert data.story.outro == ("outro_1",)


def test_scene_without_story_gets_an_empty_block(game_root):
    loader = make_loader(game_root, {SCENE_ID: _scene(SCENE_ID, [_obj("lamp", 1, 1)])})
    assert loader.load_scene(LEVEL_ID, SCENE_ID).story.is_empty


def test_clue_is_a_goal_even_when_marked_otherwise(game_root):
    loader = make_loader(game_root, {SCENE_ID: _scene(SCENE_ID, [
        _obj("key", 1, 1, clue_key="clue_a", is_goal=False)])})
    assert by_cid(loader.load_scene(LEVEL_ID, SCENE_ID), "key").is_goal is True


def test_collectible_is_never_a_goal(game_root):
    loader = make_loader(game_root, {SCENE_ID: _scene(SCENE_ID, [
        _obj("star", 1, 1, collectible=True, is_goal=True, always_show=True)])})
    assert by_cid(loader.load_scene(LEVEL_ID, SCENE_ID), "star").is_goal is False


def test_clue_is_always_a_goal_under_goal_rotation(game_root):
    loader = make_loader(game_root, {SCENE_ID: _scene(SCENE_ID, [
        _obj("lamp", 1, 1, always_show=True),
        _obj("key", 2, 2, clue_key="clue_a"),
        _obj("coin", 3, 3), _obj("book", 4, 4), _obj("shell", 5, 5),
        _obj("star", 6, 6, collectible=True, always_show=True),
    ], auto_random_finds=True, num_random_finds=3)})
    random.seed(3)
    rotated = set()
    for _ in range(30):
        data = loader.load_scene(LEVEL_ID, SCENE_ID)
        goals = {o.catalog_id for o in data.objects if o.is_goal}
        assert len(goals) == 3
        assert {"key", "lamp"} <= goals
        assert "star" not in goals
        rotated |= goals - {"key", "lamp"}
    assert rotated == {"coin", "book", "shell"}


def test_clue_survives_a_goal_count_smaller_than_the_fixed_set(game_root):
    loader = make_loader(game_root, {SCENE_ID: _scene(SCENE_ID, [
        _obj("lamp", 1, 1, always_show=True), _obj("coin", 3, 3, always_show=True),
        _obj("key", 2, 2, clue_key="clue_a"),
    ], auto_random_finds=True, num_random_finds=1)})
    goals = {o.catalog_id for o in loader.load_scene(LEVEL_ID, SCENE_ID).objects if o.is_goal}
    assert goals == {"key"}


def test_clue_and_collectible_survive_random_layer_selection(game_root, monkeypatch):
    loader = make_loader(game_root, {SCENE_ID: _scene(SCENE_ID, [
        _obj("lamp", 1, 1, layer="objects_low"),
        _obj("key", 2, 2, layer="objects_low", clue_key="clue_a"),
        _obj("star", 3, 3, layer="objects_low", collectible=True),
        _obj("coin", 4, 4, layer="objects_high"),
    ], random_layer_selection=True)})
    monkeypatch.setattr(random, "choice", lambda seq: "objects_high")
    ids = {o.catalog_id for o in loader.load_scene(LEVEL_ID, SCENE_ID).objects}
    assert ids == {"key", "star", "coin"}


def test_collectible_is_clickable_but_not_a_goal(display):
    from engine.click_detector import ClickDetector
    from engine.scaling_manager import ScalingManager
    from engine.scene_loader import SceneObject
    sm = ScalingManager()
    sm.update_screen_size(*SCREEN)
    sm.set_background(*SCREEN, 1.0)
    star = SceneObject(instance_id="star", catalog_id="star", label_key="obj_star",
                       icon_path="", x=640, y=360, detection_type="circle", radius=40,
                       is_goal=False, collectible=True)
    sx, sy = sm.bg_to_screen_scenic(640, 360, 1.0)
    assert ClickDetector(sm).detect(sx, sy, [star]) is star
    star.found = True
    assert ClickDetector(sm).detect(sx, sy, [star]) is None


# -----------------------------------------------------------------------------
# Save
# -----------------------------------------------------------------------------

@pytest.fixture
def saves_dir(tmp_path, monkeypatch):
    import engine.save_manager as sm
    target = tmp_path / "saves"
    target.mkdir()
    monkeypatch.setattr(sm, "get_writable_path", lambda name: target / name, raising=True)
    return target


def test_new_save_has_empty_story_fields(saves_dir):
    save = SaveManager("g")
    assert save.data["clues"] == {} and save.data["collectibles"] == []
    assert save.get_clues() == {} and save.get_collectibles() == []


def test_story_fields_round_trip(saves_dir):
    save = SaveManager("g")
    save.record_clue("scene_a", "clue_a")
    assert save.record_collectible("scene_a") is True
    assert save.record_collectible("scene_a") is False
    again = SaveManager("g")
    assert again.get_clues() == {"scene_a": "clue_a"}
    assert again.get_collectibles() == ["scene_a"]
    on_disk = json.loads((saves_dir / "save_g.json").read_text(encoding="utf-8"))
    assert on_disk["clues"] == {"scene_a": "clue_a"}
    assert on_disk["collectibles"] == ["scene_a"]


def test_old_save_without_story_fields_loads(saves_dir):
    (saves_dir / "save_g.json").write_text(json.dumps({
        "version": "1.0", "current_level": None, "scores": {"lvl1": {"scene_a": 300}},
        "stars": {}, "unlocked_levels": ["lvl1"], "unlocked_scenes": {"lvl1": 0}}),
        encoding="utf-8")
    save = SaveManager("g")
    assert save.get_clues() == {} and save.get_collectibles() == []
    assert save.data["scores"] == {"lvl1": {"scene_a": 300}}
    assert save.record_collectible("scene_a") is True


def test_malformed_story_fields_read_as_empty(saves_dir):
    (saves_dir / "save_g.json").write_text(json.dumps({"clues": [1, 2], "collectibles": "x"}),
                                           encoding="utf-8")
    save = SaveManager("g")
    assert save.get_clues() == {} and save.get_collectibles() == []
    save.record_clue("s", "c")
    assert save.get_clues() == {"s": "c"}


def test_reset_progress_clears_the_story_fields(saves_dir):
    save = SaveManager("g")
    save.record_clue("s", "c")
    save.record_collectible("s")
    save.reset_progress()
    assert save.get_clues() == {} and save.get_collectibles() == []


# -----------------------------------------------------------------------------
# Journal
# -----------------------------------------------------------------------------

def test_journal_follows_the_campaign_and_the_save():
    scenes = [(LEVEL_ID, SCENE_ID, _default_scene_a()), (LEVEL_ID, SCENE_B, _default_scene_b()),
              (LEVEL_ID, "plain", _scene("plain", [_obj("lamp", 1, 1)]))]
    journal = story.build_journal(scenes, {SCENE_ID: "clue_a"}, [SCENE_ID])
    assert [e.scene_id for e in journal.entries] == [SCENE_ID, SCENE_B]
    assert [e.unlocked for e in journal.entries] == [True, False]
    assert journal.entries[0].clue_object_id == "key"
    assert (journal.collectibles_found, journal.collectibles_total) == (1, 2)
    assert not journal.epilogue_unlocked
    full = story.build_journal(scenes, {}, [SCENE_ID, SCENE_B])
    assert full.epilogue_unlocked


# -----------------------------------------------------------------------------
# EngineCore (headless, playtest mode)
# -----------------------------------------------------------------------------

def make_core(root, scenes: dict[str, dict], scene_id: str = SCENE_ID):
    build_game(root, scenes)
    from engine.core import EngineCore
    config = configparser.ConfigParser()
    config["engine"] = {"resolution_w": str(SCREEN[0]), "resolution_h": str(SCREEN[1]),
                        "fullscreen": "0", "music_volume": "0", "sfx_volume": "0"}
    args = SimpleNamespace(fullscreen=False, scene=f"{LEVEL_ID}/{scene_id}", lang="en",
                           minigame=None)
    core = EngineCore(game_id=GAME_ID, config=config, cli_args=args)
    pygame.event.clear()
    return core


def run(core, seconds: float) -> None:
    for _ in range(int(round(seconds / DT))):
        core._update(DT)


def click_object(core, obj) -> None:
    """A real left click on the object, through the event loop."""
    sx, sy = core.scaling_manager.bg_to_screen_scenic(obj.x, obj.y, 1.0)
    core._click_history.clear()
    pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=(int(sx), int(sy))))
    pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=(int(sx), int(sy))))
    core._handle_events()


def finish_intro(core) -> None:
    run(core, core._scene_intro_dur + DT)


def close_cards(core) -> None:
    for _ in range(20):
        if not core._story_cards.is_open:
            return
        core._story_cards.advance()
    raise AssertionError("cards did not close")


@pytest.fixture
def core(game_root):
    engine_core = make_core(game_root, {SCENE_ID: _default_scene_a(), SCENE_B: _default_scene_b()})
    yield engine_core
    engine_core._story_reset()


def test_intro_cards_open_after_the_zoom_with_the_chapter(core):
    assert not core._story_cards.is_open
    finish_intro(core)
    cards = core._story_cards
    assert cards.is_open and cards.kind == "story" and cards.page_count == 2
    assert cards._pages[0].heading == "Chapter One"
    assert cards._pages[1].heading == ""
    assert cards._pages[0].body == STRINGS_EN["intro_1"]
    core._draw()   # renders without errors


def test_story_card_pauses_the_timer_and_swallows_clicks(core):
    finish_intro(core)
    elapsed = core.level_manager.time_elapsed
    run(core, 2.0)
    assert core.level_manager.time_elapsed == elapsed
    lamp = by_cid(core._current_scene_data, "lamp")
    click_object(core, lamp)
    assert not lamp.found
    assert core._story_cards.is_open
    close_cards(core)
    run(core, 1.0)
    assert core.level_manager.time_elapsed > elapsed


def test_a_click_while_typing_completes_the_text_first(core):
    finish_intro(core)
    cards = core._story_cards
    assert cards.is_typing
    cards.handle_click((10, 10))
    assert not cards.is_typing and cards.page_index == 0
    cards.handle_click((10, 10))
    assert cards.page_index == 1


def test_typing_speed_follows_the_shared_constant(core):
    finish_intro(core)
    cards = core._story_cards
    cards.update(1.0)
    assert int(cards._chars) == min(len(cards._pages[0].body), int(story.STORY_CHARS_PER_S))


def test_start_bubbles_wait_for_the_intro_cards(game_root):
    scene = _default_scene_a()
    scene["effects"] = [{"type": "bubble_tip", "x": 640, "y": 360, "trigger": "start_scene",
                         "text_key": "intro_1", "effect_id": "b1"}]
    core = make_core(game_root, {SCENE_ID: scene})
    finish_intro(core)
    bubble = core._current_scene_effects[0]
    assert core._story_cards.is_open and not bubble._visible
    close_cards(core)
    assert bubble._visible


def test_clue_card_records_the_clue_and_holds_the_completion(core):
    finish_intro(core)
    close_cards(core)
    lamp = by_cid(core._current_scene_data, "lamp")
    key = by_cid(core._current_scene_data, "key")
    click_object(core, lamp)
    assert lamp.found
    click_object(core, key)              # the last goal, and the clue
    assert key.found
    cards = core._story_cards
    assert cards.is_open and cards.kind == "clue"
    assert cards._pages[0].title == "Old key"
    assert cards._pages[0].body == STRINGS_EN["clue_a"]
    assert cards._pages[0].icon is key.icon_surface
    assert core.save_manager.get_clues() == {SCENE_ID: "clue_a"}
    core._draw()
    run(core, 5.0)
    assert not pygame.event.peek(pygame.USEREVENT + 1)   # no SCENE_COMPLETE yet
    close_cards(core)
    run(core, 3.0)                       # end-of-scene delay, then the outro
    assert core._story_cards.is_open and core._story_cards.kind == "story"
    assert core._story_cards._pages[0].body == STRINGS_EN["outro_1"]
    assert not pygame.event.peek(pygame.USEREVENT + 1)
    close_cards(core)
    run(core, DT * 2)
    from engine.level_manager import SCENE_COMPLETE
    assert pygame.event.peek(SCENE_COMPLETE)


def test_collectible_pays_once_and_never_joins_the_goals(core):
    finish_intro(core)
    close_cards(core)
    star = by_cid(core._current_scene_data, "star")
    assert star not in core.hud._objects
    score = core.level_manager.scene_score
    elapsed_goals = core.level_manager._total_count()
    click_object(core, star)
    assert star.found
    assert core.level_manager.scene_score == score + story.COLLECTIBLE_POINTS
    assert core.save_manager.get_collectibles() == [SCENE_ID]
    assert core._toast.is_visible and "Golden acorn" in core._toast._text
    assert core.level_manager._total_count() == elapsed_goals
    core._draw()
    # A replay of the scene: the collectible is placed again, a find pays nothing.
    core._start_level(LEVEL_ID, SCENE_ID)
    finish_intro(core)
    close_cards(core)
    star = by_cid(core._current_scene_data, "star")
    assert not star.found
    score = core.level_manager.scene_score
    core._toast._t = 0.0
    click_object(core, star)
    assert star.found
    assert core.level_manager.scene_score == score
    assert not core._toast.is_visible


def test_journal_opens_with_j_and_pauses_the_scene(core):
    finish_intro(core)
    close_cards(core)
    core.save_manager.record_clue(SCENE_ID, "clue_a")
    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_j, mod=0, unicode="j"))
    core._handle_events()
    assert core._journal.is_open
    view = core._journal._view
    assert [r.unlocked for r in view.rows] == [True, False]
    assert view.rows[0].object_name == "Old key"
    assert view.rows[0].clue_text == STRINGS_EN["clue_a"]
    assert view.footer == "Golden acorn: 0/2"
    assert view.epilogue_text == ""
    elapsed = core.level_manager.time_elapsed
    run(core, 1.0)
    assert core.level_manager.time_elapsed == elapsed
    lamp = by_cid(core._current_scene_data, "lamp")
    core._draw()
    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE, mod=0, unicode=""))
    core._handle_events()
    assert not core._journal.is_open
    assert core.state == "SCENE"
    assert not lamp.found


def test_journal_shows_the_epilogue_when_every_collectible_is_found(core):
    core.save_manager.record_collectible(SCENE_ID)
    core.save_manager.record_collectible(SCENE_B)
    core._open_journal()
    view = core._journal._view
    assert view.footer == "Golden acorn: 2/2"
    assert (view.epilogue_title, view.epilogue_text) == ("Epilogue", STRINGS_EN["epilogue_text"])
    core._journal.scroll_by(10 ** 6)
    core._draw()


def test_pause_menu_offers_the_journal(core):
    finish_intro(core)
    close_cards(core)
    core._toggle_pause()
    actions = [b.action for b in core.menu_system.buttons]
    assert "open_journal" in actions
    btn = next(b for b in core.menu_system.buttons if b.action == "open_journal")
    rect = core.menu_system._get_hitbox(btn)
    pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=rect.center))
    core._handle_events()
    assert core._journal.is_open and core.state == "PAUSE"
    core._draw()
    # A click outside the panel closes it without reaching the pause menu.
    pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=(2, 2)))
    core._handle_events()
    assert not core._journal.is_open and core.state == "PAUSE"


def test_pause_menu_has_no_journal_without_story_content(game_root):
    core = make_core(game_root, {SCENE_ID: _scene(SCENE_ID, [_obj("lamp", 200, 200)])})
    finish_intro(core)
    assert not core._story_cards.is_open      # no story block: no cards at all
    core._toggle_pause()
    assert "open_journal" not in [b.action for b in core.menu_system.buttons]


# -----------------------------------------------------------------------------
# Contact shadow (engine/object_shadow.py)
# -----------------------------------------------------------------------------

SHADOW = {"dy": 150.0, "w": 120.0, "a": 200}


def test_parse_shadow_validates_the_block():
    from engine.object_shadow import SHADOW_ALPHA_MAX, parse_shadow
    assert parse_shadow({"dy": 3, "w": 40, "a": 90}) == {"dy": 3.0, "w": 40.0, "a": 90}
    assert parse_shadow({"w": 40, "a": 999})["a"] == SHADOW_ALPHA_MAX
    assert parse_shadow({"w": 0, "a": 90}) is None
    assert parse_shadow({"dy": 3, "a": 90}) is None
    assert parse_shadow({"w": 40, "a": 0}) is None
    assert parse_shadow("dark") is None
    assert parse_shadow(None) is None


def test_shadow_is_carried_by_the_loader_and_by_alt_spots(game_root, monkeypatch):
    other = {"dy": 10.0, "w": 50.0, "a": 90}
    loader = make_loader(game_root, {SCENE_ID: _scene(SCENE_ID, [
        _obj("lamp", 100, 120, shadow=SHADOW, alt_spots=[{"x": 900, "y": 50, "shadow": other}]),
        _obj("coin", 300, 300),
    ])})
    monkeypatch.setattr(random, "randrange", lambda n: 0)    # base placement
    data = loader.load_scene(LEVEL_ID, SCENE_ID)
    assert by_cid(data, "lamp").shadow == SHADOW
    assert by_cid(data, "coin").shadow is None
    monkeypatch.setattr(random, "randrange", lambda n: 1)    # the alt spot
    lamp = by_cid(loader.load_scene(LEVEL_ID, SCENE_ID), "lamp")
    assert (lamp.x, lamp.shadow) == (900.0, other)


def test_web_export_passes_a_validated_shadow():
    from editor.web_exporter import _build_alt_spots, _build_object
    built = _build_object(_obj("lamp", 1, 2, shadow={"dy": 4, "w": 30, "a": 300}), "lamp", {})
    assert built["shadow"] == {"dy": 4.0, "w": 30.0, "a": 255}
    assert _build_object(_obj("lamp", 1, 2), "lamp", {})["shadow"] is None
    spots = _build_alt_spots([{"x": 1, "y": 2, "shadow": {"w": 20, "a": 50}},
                              {"x": 3, "y": 4, "shadow": {"w": -1, "a": 50}}])
    assert spots[0]["shadow"] == {"dy": 0.0, "w": 20.0, "a": 50}
    assert "shadow" not in spots[1]


def test_shadow_ellipse_is_dark_in_the_middle_and_clear_outside(display):
    from engine.object_shadow import SHADOW_ASPECT, draw_shadow
    canvas = pygame.Surface((400, 200))
    canvas.fill((200, 200, 200))
    rect = draw_shadow(canvas, {"dy": 20.0, "w": 100.0, "a": 255}, (200, 80), 2.0, 1.0)
    assert rect.center == (200, 120)
    assert rect.w == 200 and abs(rect.h - 200 * SHADOW_ASPECT) <= 2
    assert canvas.get_at((200, 120))[0] < 60                   # dark core
    assert canvas.get_at((200 + 90, 120))[0] > canvas.get_at((200, 120))[0]
    assert canvas.get_at((200, 120 + rect.h))[:3] == (200, 200, 200)   # outside
    assert canvas.get_at((200, 80))[:3] == (200, 200, 200)     # object centre untouched


def test_scene_draws_the_shadow_under_the_object_and_drops_it_when_found(game_root):
    scene = _scene(SCENE_ID, [_obj("lamp", 300, 200, shadow=SHADOW), _obj("coin", 900, 200)])
    core = make_core(game_root, {SCENE_ID: scene})
    finish_intro(core)
    lamp = by_cid(core._current_scene_data, "lamp")
    coin = by_cid(core._current_scene_data, "coin")
    sm = core.scaling_manager

    def pixel_below(obj):
        x, y = sm.bg_to_screen_scenic(obj.x, obj.y + SHADOW["dy"], 1.0)
        return core.screen.get_at((int(x), int(y)))

    core._draw()
    shaded, plain = pixel_below(lamp), pixel_below(coin)
    assert sum(shaded[:3]) < sum(plain[:3]) - 60
    lamp.found = True
    core._draw()
    assert pixel_below(lamp)[:3] == plain[:3]
