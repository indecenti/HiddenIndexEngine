"""
tests/test_menu_skins.py

Contract of the menu skins (engine/menu_skins/):

  1. every registered skin draws a full frame on its REAL theme.json without
     raising (smoke test on a dummy SDL surface);
  2. a broken hook does not take the menu down: skin_call logs it, disables it
     for the session and falls back to the neutral base implementation;
  3. theme.json is authored data: malformed values fall back to the documented
     defaults instead of raising inside the draw pass;
  4. the shared caches are bounded and evict gradually (engine convention),
     and the title caches invalidate when the SCALED font size changes.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pytest

pygame = pytest.importorskip("pygame")

from engine.menu_skins import (MenuSkin, SurfaceCache, as_bool, as_float, as_int,
                               as_rgb, get_skin, register_skin, skin_call)
from engine.menu_skins.base import cached_title
from engine.menu_theme import MenuTheme

ROOT = Path(__file__).resolve().parents[1]
THEMES_DIR = ROOT / "engine" / "assets" / "themes"
SKIN_THEMES = ("default", "horror", "kids", "cyber_neon", "mystery")
REF_W, REF_H = 1280, 720


@pytest.fixture(scope="module", autouse=True)
def _pygame_init():
    pygame.init()
    pygame.display.set_mode((REF_W // 2, REF_H // 2))
    yield
    pygame.quit()


class FakeScaling:
    """Minimal ScalingManager: reference space == screen space."""

    def scale_value(self, v):
        return int(v)

    def scale_rect(self, x, y, w, h):
        return pygame.Rect(int(x), int(y), int(w), int(h))


class FakeButton:
    def __init__(self, x=200, y=300, w=120, h=120, image=None):
        self.ref_rect = pygame.Rect(x, y, w, h)
        self.image = image
        self.hovered = True
        self.hover_time = 0.5
        self.text = "PLAY"
        self.action = "start_game"


class FakeMenu:
    """Menu core stub exposing only what the skin hooks touch."""

    def __init__(self, theme, state="main"):
        self.theme = theme
        self.state = state
        self._android = False
        self.scaling_manager = FakeScaling()
        self.buttons = [FakeButton(), FakeButton(x=400), FakeButton(x=40, y=40)]
        self.title_calls = 0

    def _state_title_text(self) -> str:
        return "Main Menu"

    def _draw_state_title(self, screen) -> None:
        self.title_calls += 1


def _theme(theme_id: str) -> MenuTheme:
    data = json.loads((THEMES_DIR / theme_id / "theme.json").read_text(encoding="utf-8"))
    return MenuTheme(data)


def _draw_frame(skin, ms, screen, frames: int = 3) -> None:
    """Run the full hook sequence the core executes for a frame."""
    sw, sh = screen.get_size()
    for _ in range(frames):
        skin_call(skin, "update", ms, 1 / 60.0)
        skin_call(skin, "arrange", ms)
        skin_call(skin, "draw_background_pre", ms, screen, sw, sh)
        skin_call(skin, "draw_title", ms, screen)
        for b in ms.buttons:
            skin_call(skin, "button_jitter", ms, b)
            skin_call(skin, "behind_button", ms, screen, b, b.ref_rect.copy(), False)
        skin_call(skin, "draw_overlay", ms, screen, sw, sh)


# ── 1. Smoke: every skin draws on its real theme ────────────────────────────

@pytest.mark.parametrize("theme_id", SKIN_THEMES)
def test_every_skin_draws_a_full_frame(theme_id):
    theme = _theme(theme_id)
    skin = get_skin(theme)
    assert skin.id == theme_id
    screen = pygame.Surface((REF_W, REF_H))
    ms = FakeMenu(theme)
    _draw_frame(skin, ms, screen)
    assert not skin._disabled_hooks, f"hook disabled on a healthy theme: {skin._disabled_hooks}"


@pytest.mark.parametrize("theme_id", SKIN_THEMES)
def test_every_skin_draws_in_reduced_motion(theme_id):
    """Android/low-end path: the heavy effects degrade, nothing raises."""
    theme = _theme(theme_id)
    skin = get_skin(theme)
    screen = pygame.Surface((REF_W, REF_H))
    ms = FakeMenu(theme, state="settings")
    ms._android = True
    _draw_frame(skin, ms, screen)
    assert not skin._disabled_hooks


@pytest.mark.parametrize("theme_id", SKIN_THEMES)
def test_every_skin_survives_a_resize(theme_id):
    """The title caches must follow the scaled size, not stay at the old one."""
    theme = _theme(theme_id)
    skin = get_skin(theme)
    ms = FakeMenu(theme)
    _draw_frame(skin, ms, pygame.Surface((REF_W, REF_H)))
    small = skin._title_val

    class Scaled(FakeScaling):
        def scale_value(self, v):
            return int(v * 2)

    ms.scaling_manager = Scaled()
    _draw_frame(skin, ms, pygame.Surface((REF_W * 2, REF_H * 2)))
    if small is not None:            # the default skin delegates the title to the core
        assert skin._title_val is not small, "title cache not invalidated on resize"
    assert not skin._disabled_hooks


# ── 2. Fail-soft hooks ──────────────────────────────────────────────────────

class BrokenSkin(MenuSkin):
    id = "broken"

    def __init__(self, theme) -> None:
        super().__init__(theme)
        self.calls = 0

    def draw_overlay(self, ms, screen, sw, sh) -> None:
        self.calls += 1
        raise RuntimeError("skin bug")

    def button_jitter(self, ms, b):
        return "not-a-pair"

    def draw_title(self, ms, screen) -> None:
        raise ValueError("broken title")


def test_broken_hook_is_contained_and_disabled(caplog):
    skin = BrokenSkin(_theme("default"))
    screen = pygame.Surface((320, 240))
    ms = FakeMenu(skin.theme)
    for _ in range(5):
        skin_call(skin, "draw_overlay", ms, screen, 320, 240)
    assert "draw_overlay" in skin._disabled_hooks
    assert skin.calls == 1, "the broken hook must be called once, not once per frame"


def test_broken_draw_title_falls_back_to_core_title():
    skin = BrokenSkin(_theme("default"))
    ms = FakeMenu(skin.theme)
    screen = pygame.Surface((320, 240))
    skin_call(skin, "draw_title", ms, screen)
    skin_call(skin, "draw_title", ms, screen)
    # base MenuSkin.draw_title delegates to the core renderer, on both passes
    assert ms.title_calls == 2


def test_malformed_jitter_does_not_break_the_draw():
    from engine.menu_system import _jitter_pair
    skin = BrokenSkin(_theme("default"))
    ms = FakeMenu(skin.theme)
    assert _jitter_pair(skin_call(skin, "button_jitter", ms, FakeButton())) == (0.0, 0.0)
    assert _jitter_pair(None) == (0.0, 0.0)
    assert _jitter_pair((2, 3)) == (2.0, 3.0)


def test_uninstantiable_skin_falls_back_to_default():
    class Exploding(MenuSkin):
        def __init__(self, theme):
            raise RuntimeError("boom")

    register_skin("__exploding__", Exploding)
    theme = _theme("default")
    theme.theme_id = "__exploding__"
    skin = get_skin(theme)
    assert skin.id == "default"


# ── 3. Malformed theme values ───────────────────────────────────────────────

def test_theme_value_coercion():
    assert as_float("1.5", 0.0) == 1.5
    assert as_float(None, 0.25) == 0.25
    assert as_float("abc", 0.25) == 0.25
    assert as_int(3.7, 0) == 3
    assert as_int([], 7) == 7
    assert as_bool(None, True) is True
    assert as_bool(0, True) is False
    assert as_rgb([10, 20, 30], (0, 0, 0)) == (10, 20, 30)
    assert as_rgb([10, 20], (1, 2, 3)) == (1, 2, 3)
    assert as_rgb("red", (1, 2, 3)) == (1, 2, 3)
    assert as_rgb([999, -5, 30], (0, 0, 0)) == (255, 0, 30)


@pytest.mark.parametrize("theme_id", SKIN_THEMES)
def test_corrupt_theme_does_not_crash_the_skin(theme_id):
    """A theme.json with garbage in the skin sections must still render."""
    data = json.loads((THEMES_DIR / theme_id / "theme.json").read_text(encoding="utf-8"))
    data["motion"] = {"carousel_zoom": "big", "float_amp": None, "magnetic": "yes",
                      "jitter": "lots"}
    data["particles"] = {"type": data.get("particles", {}).get("type", "none"),
                         "density": "many", "color": "blue"}
    data["background"] = dict(data.get("background", {}))
    for key in ("aurora_color", "fog_color", "sky_top", "sky_bottom", "sun_color",
                "grid_color", "glow_color"):
        if key in data["background"]:
            data["background"][key] = "nope"
    data["decor"] = dict(data.get("decor", {}))
    for key in ("card_border", "toy_shadow", "card_radius", "grain", "scanline",
                "vignette"):
        if key in data["decor"]:
            data["decor"][key] = "nope"
    theme = MenuTheme(data)
    skin = get_skin(theme)
    ms = FakeMenu(theme)
    _draw_frame(skin, ms, pygame.Surface((REF_W, REF_H)))
    assert not skin._disabled_hooks, f"broken theme disabled {skin._disabled_hooks}"
    assert skin.carousel_zoom == 0.25 and skin.float_amp == 4.0


def test_particle_density_is_capped():
    """A theme asking for 100k particles must not allocate 100k of them."""
    from engine.menu_skins.kids_skin import CONFETTI_MAX
    from engine.menu_skins.mystery_skin import DUST_MAX

    data = json.loads((THEMES_DIR / "kids" / "theme.json").read_text(encoding="utf-8"))
    data.setdefault("particles", {})["density"] = 100000
    kids = get_skin(MenuTheme(data))
    ms = FakeMenu(kids.theme)
    skin_call(kids, "update", ms, 1 / 60.0)
    assert len(kids._confetti) <= CONFETTI_MAX

    data = json.loads((THEMES_DIR / "mystery" / "theme.json").read_text(encoding="utf-8"))
    data.setdefault("particles", {})["density"] = 100000
    myst = get_skin(MenuTheme(data))
    ms = FakeMenu(myst.theme)
    skin_call(myst, "update", ms, 1 / 60.0)
    assert len(myst._dust) <= DUST_MAX

    # lowering the density must shed the extras, not keep them alive forever
    myst.theme._particles["density"] = 4
    skin_call(myst, "update", ms, 1 / 60.0)
    assert len(myst._dust) == 4


# ── 4. Shared caches ────────────────────────────────────────────────────────

def test_surface_cache_evicts_gradually():
    cache = SurfaceCache(cap=3)
    built = []

    def _mk(tag):
        built.append(tag)
        return pygame.Surface((2, 2))

    for tag in ("a", "b", "c"):
        cache.get_or_build(tag, lambda t=tag: _mk(t))
    cache.get_or_build("a", lambda: _mk("a"))       # hit: 'a' becomes the newest
    cache.get_or_build("d", lambda: _mk("d"))       # evicts the LRU ('b')
    assert len(cache) == 3
    assert built == ["a", "b", "c", "d"]
    cache.get_or_build("a", lambda: _mk("a2"))      # still cached
    assert built == ["a", "b", "c", "d"]
    cache.get_or_build("b", lambda: _mk("b2"))      # was evicted -> rebuilt
    assert built[-1] == "b2"


def test_cached_title_rebuilds_only_on_key_change():
    skin = MenuSkin(_theme("default"))
    calls = []
    first = cached_title(skin, ("T", 48), lambda: calls.append(1) or "surf-1")
    again = cached_title(skin, ("T", 48), lambda: calls.append(1) or "surf-2")
    assert first == again == "surf-1" and len(calls) == 1
    scaled = cached_title(skin, ("T", 96), lambda: calls.append(1) or "surf-3")
    assert scaled == "surf-3" and len(calls) == 2


def test_chip_shadow_cache_stays_bounded():
    """DefaultSkin: the chip shadows are bounded (they used to be cleared whole)."""
    from engine.menu_skins.base import SURFACE_CACHE_MAX

    data = json.loads((THEMES_DIR / "default" / "theme.json").read_text(encoding="utf-8"))
    data.setdefault("decor", {})["icon_chip"] = True
    skin = get_skin(MenuTheme(data))
    ms = FakeMenu(skin.theme)
    screen = pygame.Surface((REF_W, REF_H))
    for size in range(60, 60 + SURFACE_CACHE_MAX * 2):
        b = FakeButton(w=size, h=size)
        skin_call(skin, "behind_button", ms, screen, b, b.ref_rect.copy(), False)
    assert len(skin._chip_shadow_cache) == SURFACE_CACHE_MAX
    assert not skin._disabled_hooks
