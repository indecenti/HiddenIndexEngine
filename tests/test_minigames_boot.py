"""
tests/test_minigames_boot.py

Every minigame the engine ships must load, start, run and draw. None of them
had a test, so an import that no longer resolves, a manifest pointing at a
class that was renamed, a missing asset or a crash on the first frame only
showed up in a build already in someone's hands.

The manager loads them the way the game does, by manifest and dynamic import.
The scaling and language managers are the real ones; only the audio is stubbed,
since a test machine has no sound device.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pytest

pygame = pytest.importorskip("pygame")

from engine.language_manager import LanguageManager
from engine.minigame_manager import MinigameManager
from engine.scaling_manager import ScalingManager

MINIGAMES_DIR = Path("engine/minigames")
SCREEN_SIZE = (1280, 720)
FRAMES = 5
DT = 1 / 60.0


def _minigame_ids() -> list[str]:
    """Every directory that declares a manifest, which is what the game loads."""
    return sorted(p.name for p in MINIGAMES_DIR.iterdir()
                  if p.is_dir() and (p / "manifest.json").exists())


MINIGAME_IDS = _minigame_ids()


class SilentAudio:
    """The test machine has no sound device; record the calls instead."""

    def __init__(self):
        self.played: list = []

    def play_sfx(self, *args, **kwargs):
        self.played.append((args, kwargs))

    def play_music(self, *args, **kwargs):
        pass

    def stop_music(self, *args, **kwargs):
        pass


@pytest.fixture(scope="module")
def screen():
    pygame.init()
    surface = pygame.display.set_mode(SCREEN_SIZE)
    yield surface
    pygame.quit()


@pytest.fixture
def manager(screen):
    scaling = ScalingManager()
    scaling.update_screen_size(*SCREEN_SIZE)
    lang = LanguageManager()
    lang.load_for_game("engine", "en")
    return MinigameManager(screen, scaling, SilentAudio(), lang)


# -----------------------------------------------------------------------------
# WHAT SHIPS
# -----------------------------------------------------------------------------

def test_there_are_minigames_to_test():
    assert MINIGAME_IDS, "no minigame with a manifest was found"


@pytest.mark.parametrize("mg_id", MINIGAME_IDS)
def test_the_manifest_says_what_to_load(mg_id):
    """The manager reads main_class out of it and imports <id>_game."""
    manifest = json.loads((MINIGAMES_DIR / mg_id / "manifest.json").read_text(encoding="utf-8"))
    assert manifest.get("main_class"), f"{mg_id}: manifest without main_class"
    assert (MINIGAMES_DIR / mg_id / f"{mg_id}_game.py").exists(), (
        f"{mg_id}: the manager will import engine.minigames.{mg_id}.{mg_id}_game")


@pytest.mark.parametrize("mg_id", MINIGAME_IDS)
def test_the_class_the_manifest_names_exists(mg_id):
    import importlib

    manifest = json.loads((MINIGAMES_DIR / mg_id / "manifest.json").read_text(encoding="utf-8"))
    module = importlib.import_module(f"engine.minigames.{mg_id}.{mg_id}_game")
    assert hasattr(module, manifest["main_class"]), (
        f"{mg_id}: {manifest['main_class']} not found in the module")


# -----------------------------------------------------------------------------
# BOOT AND RUN
# -----------------------------------------------------------------------------

@pytest.mark.parametrize("mg_id", MINIGAME_IDS)
def test_a_minigame_starts(manager, mg_id):
    """start_minigame swallows every failure and answers False: that is the
    signal a shipped build would give, so it is what the test reads."""
    assert manager.start_minigame(mg_id) is True, f"{mg_id} did not start"
    assert manager.is_running()
    assert manager.current_minigame is not None


@pytest.mark.parametrize("mg_id", MINIGAME_IDS)
def test_a_minigame_survives_its_first_frames(manager, mg_id):
    assert manager.start_minigame(mg_id) is True
    game = manager.current_minigame
    for _ in range(FRAMES):
        game.update(DT)
        game.draw()


@pytest.mark.parametrize("mg_id", MINIGAME_IDS)
def test_a_minigame_puts_something_on_the_screen(manager, screen, mg_id):
    screen.fill((0, 0, 0))
    blank = pygame.image.tostring(screen, "RGB")
    assert manager.start_minigame(mg_id) is True
    game = manager.current_minigame
    for _ in range(FRAMES):
        game.update(DT)
        game.draw()
    assert pygame.image.tostring(screen, "RGB") != blank, f"{mg_id} drew nothing"


@pytest.mark.parametrize("mg_id", MINIGAME_IDS)
def test_a_minigame_takes_input_without_falling_over(manager, mg_id):
    """A click, a key and a drag: none of them may raise on the first frames."""
    assert manager.start_minigame(mg_id) is True
    game = manager.current_minigame
    cx, cy = SCREEN_SIZE[0] // 2, SCREEN_SIZE[1] // 2
    events = [
        pygame.event.Event(pygame.MOUSEMOTION, pos=(cx, cy), rel=(1, 1), buttons=(0, 0, 0)),
        pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=(cx, cy), button=1),
        pygame.event.Event(pygame.MOUSEBUTTONUP, pos=(cx, cy), button=1),
        pygame.event.Event(pygame.KEYDOWN, key=pygame.K_SPACE, unicode=" ", mod=0, scancode=44),
        pygame.event.Event(pygame.KEYUP, key=pygame.K_SPACE, mod=0, scancode=44),
    ]
    for event in events:
        game.handle_event(event)
        game.update(DT)
        game.draw()


@pytest.mark.parametrize("mg_id", MINIGAME_IDS)
def test_a_minigame_reports_its_result_when_it_ends(manager, mg_id):
    results: list = []
    assert manager.start_minigame(mg_id, on_complete=results.append) is True
    game = manager.current_minigame

    game.finish({"success": True, "score": 123})

    assert results, f"{mg_id}: finishing reported nothing back"
    assert results[0]["score"] == 123
    assert manager.is_running() is False, "the manager must let the minigame go"
    assert manager.current_minigame is None


# -----------------------------------------------------------------------------
# THE MANAGER ITSELF
# -----------------------------------------------------------------------------

def test_an_unknown_minigame_is_refused_not_raised(manager):
    """The game asks for whatever the scene names: a typo must not kill it."""
    assert manager.start_minigame("does_not_exist") is False
    assert manager.is_running() is False


def test_nothing_runs_before_a_minigame_is_started(manager):
    assert manager.is_running() is False
    assert manager.current_minigame is None


def test_a_resize_reaches_the_running_minigame(manager, screen):
    assert manager.start_minigame(MINIGAME_IDS[0]) is True
    bigger = pygame.Surface((1920, 1080))
    manager.sync_with_engine(bigger)
    assert manager.current_minigame.screen is bigger
    manager.current_minigame.update(DT)
    manager.current_minigame.draw()
