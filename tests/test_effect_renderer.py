"""
tests/test_effect_renderer.py

Behaviour of the ambient effects (engine/effect_renderer.py):

  - the glint breathes continuously: no step between two close instants, the
    floor is pulse_min, and its heart is never darker than its halo (a grey
    opaque disc used to sit in the middle of the old glow);
  - a smoke puff is born transparent and dies transparent (they used to pop in
    at full opacity at the base), rises and grows;
  - flies stay inside their swarm and only buzz a little.
"""

from __future__ import annotations

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pytest

pygame = pytest.importorskip("pygame")

from engine import effect_renderer as fx


@pytest.fixture(scope="module", autouse=True)
def _pygame_init():
    pygame.init()
    pygame.display.set_mode((8, 8))
    yield
    pygame.quit()


def test_the_breath_is_continuous():
    steps = [fx.glint_brightness(i / 600, 0.0, 0.1) for i in range(601)]
    assert max(abs(a - b) for a, b in zip(steps, steps[1:])) < 0.01


def test_the_breath_spans_from_the_floor_to_full():
    values = [fx.glint_brightness(i / 200, 0.0, 0.25) for i in range(201)]
    assert min(values) == pytest.approx(0.25, abs=1e-6)
    assert max(values) == pytest.approx(1.0, abs=1e-3)


def test_a_floor_of_one_is_a_steady_light():
    assert {round(fx.glint_brightness(i / 10, 0.3, 1.0), 6) for i in range(10)} == {1.0}


def test_phase_shifts_the_breath():
    assert fx.glint_brightness(0.25, 0.25, 0.0) == pytest.approx(fx.glint_brightness(0.5, 0.0, 0.0))


def test_the_heart_of_the_glow_is_its_brightest_point():
    screen = pygame.Surface((200, 200))
    screen.fill((40, 40, 50))
    fx.draw_glint_effect(screen, 100, 100, 60, (255, 215, 60), 1.0, 0.5, 0.0, 0.0, {})
    centre = sum(screen.get_at((100, 100))[:3])
    ring = sum(screen.get_at((100 + 20, 100 + 20))[:3])
    edge = sum(screen.get_at((100 + 58, 100))[:3])
    assert centre > ring > edge


def test_a_puff_is_born_and_dies_transparent():
    size = 0.84
    for i in range(fx.SMOKE_PUFFS):
        seed = fx._hash01(i + 1)
        speed = 0.85 + 0.3 * fx._hash01(i + 17)
        # Instant where this puff's age is 0.
        t0 = (1.0 - (i / fx.SMOKE_PUFFS + seed * 0.05)) / speed
        _dx, _dy, _r, born = fx.smoke_puff(i, t0 + 1e-6, 30.0, size)
        _dx, _dy, _r, dying = fx.smoke_puff(i, t0 + (0.999 / speed), 30.0, size)
        assert born < 0.02 and dying < 0.02


def test_a_puff_rises_and_grows():
    speed = 0.85 + 0.3 * fx._hash01(17)
    base = (1.0 - fx._hash01(1) * 0.05) / speed
    low = fx.smoke_puff(0, base + 0.2 / speed, 30.0, 0.84)
    high = fx.smoke_puff(0, base + 0.7 / speed, 30.0, 0.84)
    assert high[1] < low[1]       # further up (negative y)
    assert high[2] > low[2]       # bigger


def test_flies_stay_in_their_swarm():
    sr = 120.0
    for i in range(40):
        for k in range(50):
            x, y, depth = fx.fly_position(i, k * 0.37, k * 0.11, 0.0, 0.0, sr)
            assert abs(x) <= sr * 0.9 and abs(y) <= sr * 0.6
            assert 0.6 <= depth <= 1.0


def test_every_effect_draws_without_error():
    screen = pygame.Surface((320, 320))
    cache: dict = {}
    for t in (0.0, 0.37, 1.9):
        fx.draw_glint_effect(screen, 160, 160, 300, (255, 215, 60), 3.0, t, 0.5, 0.1, cache)
        fx.draw_glint_effect(screen, 160, 160, 2, (255, 215, 60), 0.5, t, 0.0, 0.1, None)
        fx.draw_smoke_effect(screen, 160, 300, 50, (100, 100, 105), 1.34, t, 0.0, 2.2, cache)
        fx.draw_flies_effect(screen, 160, 160, 120, (20, 20, 20), 0.25, t, t, 1.2)
        fx.draw_radial_glow(screen, 160, 160, 40, (255, 200, 80), 0.8, cache)
