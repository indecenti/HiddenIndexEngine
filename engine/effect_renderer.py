"""
engine/effect_renderer.py

Ambient scene effects: golden glint, chimney smoke, fly swarm, bubble tips.

The three animated effects are pure functions of (time, parameters): no random
state, so the editor preview, the game and the web runtime (which replicates
them in editor/web_template/runtime/core.js, see docs/web/WEB_EXPORT_SYNC.md
section E) show the same thing.

Parameters (scene.json, unchanged contract):

  glint   radius   halo radius (background px)
          intensity  brightness, 0..3
          pulse_period  seconds per breath
          pulse_min  brightness at the bottom of the breath, 0..1 (>= 1: steady)
          phase    offset in breaths, 0..1 (desynchronises neighbours)
  smoke   radius   column width unit
          intensity  opacity
          pulse_period  rising speed (puff lifetimes per second)
          pulse_min  puff size factor
          phase    offset in lifetimes
  flies   radius   swarm area
          intensity  density (40 flies at 1.0)
          pulse_period  flight speed
          pulse_min  fly size factor

What the rewrite fixed: the glint was quantized to 12 brightness levels (the
pulse moved in visible steps) and its white core switched on and off at a
threshold, which read as a blinking light, not a glow; its profile clipped to a
flat disc. Smoke puffs were born at full opacity (they popped in at the base)
and built from hard overlapping circles. Flies vibrated at 12-14 Hz with an
amplitude of a tenth of the swarm and were drawn as squares.
"""

from __future__ import annotations

import math

import pygame

from engine.utils import get_logger, is_android_runtime

try:
    import numpy as np
except ImportError:  # pragma: no cover - numpy ships with every build
    np = None

log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Tuning (shared with the web runtime)
# ---------------------------------------------------------------------------

GLINT_HALO_ALPHA = 0.92       # peak opacity of the halo at full brightness
GLINT_HALO_FALLOFF = 2.4      # gaussian exponent: exp(-k * (d/R)^2)
GLINT_WHITE_CORE = 0.55       # how far the centre goes towards white
GLINT_CORE_SIZE = 10.0        # exponent of the white core: exp(-k * (d/R)^2)
GLINT_SPARKLE_FROM = 0.55     # brightness where the star sparkle starts to show
GLINT_SPARKLE_LEN = 1.15      # sparkle arm length, in halo radii
GLINT_SPARKLE_SPIN = 0.08     # sparkle rotation, turns per breath
GLINT_SPARKLE_MAX = 80        # longest sparkle arm, px
GLINT_SPARKLE_FULL_RADIUS = 90  # halos wider than this get a fainter sparkle
GLINT_MIN_RADIUS = 6

SMOKE_PUFFS = 16
SMOKE_RISE = 5.0              # column height, in radii
SMOKE_WIND = 1.8              # sideways drift at the top, in radii
SMOKE_SWAY = 0.55             # sinuous sway, in radii
SMOKE_FADE_IN = 0.2           # fraction of a lifetime spent appearing
SMOKE_SCATTER = 0.9           # random sideways offset of a puff, in radii
SMOKE_FADE_OUT = 1.4          # exponent of the fade towards the top
SMOKE_ALPHA = 1.25            # peak opacity at intensity 1
SMOKE_GROW_FROM = 0.7         # puff radius at birth, in radii (x size factor)
SMOKE_GROW_TO = 2.4           # puff radius at the top, in radii (x size factor)
SMOKE_SIZE_BASE = 0.6         # size factor = base + pulse_min * gain
SMOKE_SIZE_GAIN = 0.8
SMOKE_SPRITE = 64             # base sprite diameter (px) before scaling
SMOKE_SPRITE_FALLOFF = 1.6    # puff density profile: exp(-k * (d/R)^2)
SMOKE_LIT_CORE = 0.3          # puff centre lightened towards white (volume)
SMOKE_LIT_SIZE = 3.0
SMOKE_SIZE_STEP = 4           # scaled sprites are cached every N px

FLIES_PER_INTENSITY = 40
FLIES_SPEED = 6.0             # orbit radians per unit of t_accum
FLIES_BUZZ_HZ = 9.0
FLIES_BUZZ_AMP = 0.025        # buzz amplitude, in swarm radii
FLIES_BASE_SIZE = 4.2         # body length in px at scale 1
FLIES_WING_ALPHA = 90

CACHE_LIMIT = 500
# Android: per-pixel-alpha blits dominate the frame on a mobile GPU, so the smoke
# draws every other puff, each a little denser (same look at a glance).
SMOKE_ANDROID_STRIDE = 2
SMOKE_ANDROID_ALPHA_GAIN = 1.35
_ANDROID = is_android_runtime()


def _hash01(n: float) -> float:
    """Deterministic pseudo-random value in [0, 1) (same formula in JS)."""
    x = math.sin(n * 12.9898 + 78.233) * 43758.5453
    return x - math.floor(x)


def _smoothstep(e0: float, e1: float, x: float) -> float:
    if e1 == e0:
        return 1.0 if x >= e1 else 0.0
    t = max(0.0, min(1.0, (x - e0) / (e1 - e0)))
    return t * t * (3.0 - 2.0 * t)


_DEFAULT_CACHE: dict = {}


def _cache(cache: dict | None) -> dict:
    """The caller's pool, or a module one (the editor passes none)."""
    pool = cache if cache is not None else _DEFAULT_CACHE
    if len(pool) > CACHE_LIMIT:
        pool.clear()
    return pool


# ---------------------------------------------------------------------------
# Time
# ---------------------------------------------------------------------------

def update_effect_state(fx: dict | object, dt: float) -> None:
    """Advance an effect's clock (game and editor share this)."""
    def get_v(key, default):
        if isinstance(fx, dict):
            return fx.get(key, default)
        return getattr(fx, key, default)

    def set_v(key, val):
        if isinstance(fx, dict):
            fx[key] = val
        else:
            setattr(fx, key, val)

    t_accum = get_v("_t_accum", 0.0)
    t_type = get_v("type", "glint")
    period = max(0.01, get_v("pulse_period", 2.0))

    if t_type == "glint":
        t_accum += dt / period          # breaths
    elif t_type == "bubble_tip":
        if get_v("_visible", False):
            set_v("_chars_visible", get_v("_chars_visible", 0.0) + dt * 25.0)
        else:
            set_v("_chars_visible", 0.0)
    else:
        t_accum += dt * period          # lifetimes / orbit units
    set_v("_t_accum", t_accum)


# ---------------------------------------------------------------------------
# Glint
# ---------------------------------------------------------------------------

def glint_brightness(t_accum: float, phase: float, pulse_min: float) -> float:
    """Brightness of the breath, 0..1: a smooth cosine, eased at both ends."""
    floor = max(0.0, min(1.0, pulse_min))
    raw = 0.5 - 0.5 * math.cos(2.0 * math.pi * (t_accum + phase))
    return floor + (1.0 - floor) * _smoothstep(0.0, 1.0, raw)


def _radial_sprite(radius: int, color: tuple, alpha_peak: float, falloff: float,
                   white_core: float = 0.0, core_size: float = 10.0) -> pygame.Surface:
    """Soft round sprite: gaussian alpha reaching 0 at the rim, optionally
    whiter towards the centre. numpy for a band-free gradient."""
    diam = radius * 2
    surf = pygame.Surface((diam, diam), pygame.SRCALPHA)
    r0, g0, b0 = (int(c) for c in color[:3])
    if np is not None:
        yy, xx = np.mgrid[0:diam, 0:diam].astype(np.float32)
        d = np.sqrt((xx + 0.5 - radius) ** 2 + (yy + 0.5 - radius) ** 2) / max(1, radius)
        rim = np.clip(1.0 - d, 0.0, 1.0)
        alpha = np.exp(-falloff * d * d) * rim * (255.0 * alpha_peak)
        w = np.exp(-core_size * d * d) * white_core
        rgb = np.empty((diam, diam, 3), dtype=np.float32)
        rgb[..., 0] = r0 + (255 - r0) * w
        rgb[..., 1] = g0 + (255 - g0) * w
        rgb[..., 2] = b0 + (255 - b0) * w
        pygame.surfarray.blit_array(surf, np.clip(rgb, 0, 255).astype(np.uint8).swapaxes(0, 1))
        a_view = pygame.surfarray.pixels_alpha(surf)
        a_view[...] = np.clip(alpha, 0, 255).astype(np.uint8).T
        del a_view
        return surf
    steps = max(24, radius)                      # fallback: many thin rings
    for s in range(steps, 0, -1):
        d = s / steps
        a = int(255 * alpha_peak * math.exp(-falloff * d * d) * (1.0 - d))
        w = math.exp(-core_size * d * d) * white_core
        col = (int(r0 + (255 - r0) * w), int(g0 + (255 - g0) * w), int(b0 + (255 - b0) * w), a)
        pygame.draw.circle(surf, col, (radius, radius), max(1, int(radius * d)))
    return surf


def _sparkle_sprite(length: int, color: tuple) -> pygame.Surface:
    """Four-armed star: thin arms fading from the centre, a small bright hub."""
    size = length * 2 + 1
    surf = pygame.Surface((size, size), pygame.SRCALPHA)
    c = length
    r0, g0, b0 = (int(v) for v in color[:3])
    tint = (min(255, (r0 + 255 * 2) // 3), min(255, (g0 + 255 * 2) // 3),
            min(255, (b0 + 255 * 2) // 3))
    for i in range(length, 0, -1):
        k = i / length
        a = int(230 * (1.0 - k) ** 1.6)
        width = max(1, int(round(2.2 * (1.0 - k) + 0.6)))
        if a <= 0:
            continue
        col = (*tint, a)
        pygame.draw.line(surf, col, (c - i, c), (c + i, c), width)
        pygame.draw.line(surf, col, (c, c - i), (c, c + i), width)
    hub = max(1, length // 10)
    pygame.draw.circle(surf, (255, 255, 255, 235), (c, c), hub)
    return surf


def draw_glint_effect(screen: pygame.Surface, sx: float, sy: float, sr: float,
                      color: list | tuple, intensity: float, t_accum: float, phase: float,
                      pulse_min: float, cache: dict | None = None) -> None:
    """A glow that breathes: soft halo, warm-white heart, a star at the crest.

    Halo and star are cached once per size/colour and faded with surface
    alpha, so the brightness is continuous (no quantized levels) and the frame
    costs two blits.
    """
    pool = _cache(cache)
    b = glint_brightness(t_accum, phase, pulse_min)
    level = max(0.0, min(1.0, intensity * b))
    if level <= 0.01 or sr <= 0:
        return
    r = max(GLINT_MIN_RADIUS, int(round(sr)))
    col = (int(color[0]), int(color[1]), int(color[2]))
    key = ("glint_halo", r, col)
    halo = pool.get(key)
    if halo is None:
        halo = _radial_sprite(r, col, GLINT_HALO_ALPHA, GLINT_HALO_FALLOFF,
                              GLINT_WHITE_CORE, GLINT_CORE_SIZE)
        pool[key] = halo
    halo.set_alpha(int(255 * level))
    screen.blit(halo, (int(sx) - r, int(sy) - r))

    # Star sparkle: only near the top of the breath, fading in with it, and
    # slowly turning so it never looks like a static sticker.
    # A wide ambient glow (a lit window, a lamp's pool) gets a fainter star,
    # and the star never grows past GLINT_SPARKLE_MAX px.
    spark = _smoothstep(GLINT_SPARKLE_FROM, 1.0, b) * min(1.0, intensity)         * min(1.0, GLINT_SPARKLE_FULL_RADIUS / r)
    if spark > 0.02:
        length = max(4, int(min(r * GLINT_SPARKLE_LEN, GLINT_SPARKLE_MAX)
                            * (0.75 + 0.25 * b)))
        skey = ("glint_star", length, col)
        star = pool.get(skey)
        if star is None:
            star = _sparkle_sprite(length, col)
            pool[skey] = star
        angle = 360.0 * GLINT_SPARKLE_SPIN * (t_accum + phase)
        turned = pygame.transform.rotate(star, angle % 90.0)
        turned.set_alpha(int(255 * spark))
        screen.blit(turned, turned.get_rect(center=(int(sx), int(sy))))


def draw_radial_glow(dest: pygame.Surface, cx: int, cy: int, radius: int,
                     color: list | tuple, eff_intensity: float,
                     cache: dict | None = None) -> None:
    """A still glow of the same look (kept for callers of the old helper)."""
    pool = _cache(cache)
    r = max(GLINT_MIN_RADIUS, int(radius))
    col = (int(color[0]), int(color[1]), int(color[2]))
    key = ("glint_halo", r, col)
    halo = pool.get(key)
    if halo is None:
        halo = _radial_sprite(r, col, GLINT_HALO_ALPHA, GLINT_HALO_FALLOFF,
                              GLINT_WHITE_CORE, GLINT_CORE_SIZE)
        pool[key] = halo
    halo.set_alpha(int(255 * max(0.0, min(1.0, eff_intensity))))
    dest.blit(halo, (cx - r, cy - r))


# ---------------------------------------------------------------------------
# Smoke
# ---------------------------------------------------------------------------

def smoke_puff(i: int, t: float, sr: float, size: float) -> tuple[float, float, float, float]:
    """(dx, dy, radius, opacity 0..1) of puff i at time t, relative to the vent."""
    seed = _hash01(i + 1)
    speed = 0.85 + 0.3 * _hash01(i + 17)
    p = (t * speed + i / SMOKE_PUFFS + seed * 0.05) % 1.0
    appear = _smoothstep(0.0, SMOKE_FADE_IN, p)
    fade = (1.0 - p) ** SMOKE_FADE_OUT
    opacity = appear * fade
    rise = -p * sr * SMOKE_RISE
    wind = SMOKE_WIND * sr * p * p
    sway = math.sin(2.0 * math.pi * (p * 1.3 + seed)) * SMOKE_SWAY * sr * (0.3 + p)
    radius = sr * size * (SMOKE_GROW_FROM + (SMOKE_GROW_TO - SMOKE_GROW_FROM) * p) \
        * (0.85 + 0.3 * _hash01(i + 31))
    scatter = (_hash01(i + 53) - 0.5) * SMOKE_SCATTER * sr * (0.4 + p)
    return wind + sway + scatter, rise, radius, opacity


def draw_smoke_effect(screen: pygame.Surface, sx: float, sy: float, sr: float,
                      color: list | tuple, intensity: float, t_accum: float,
                      phase: float = 0.0, pulse_min: float = 0.3,
                      cache: dict | None = None) -> None:
    """A column of soft puffs that appear, rise, drift with the wind, swell
    and fade. Each puff is a cached gaussian sprite (scaled in SMOKE_SIZE_STEP
    buckets) blitted with its own opacity: no work surface to clear, no hard
    circles."""
    if sr <= 0 or intensity <= 0:
        return
    pool = _cache(cache)
    col = (int(color[0]), int(color[1]), int(color[2]))
    base_key = ("smoke_base", col)
    base = pool.get(base_key)
    if base is None:
        base = _radial_sprite(SMOKE_SPRITE // 2, col, 1.0, SMOKE_SPRITE_FALLOFF,
                              SMOKE_LIT_CORE, SMOKE_LIT_SIZE)
        pool[base_key] = base
    size = max(0.25, SMOKE_SIZE_BASE + SMOKE_SIZE_GAIN * pulse_min)
    peak = SMOKE_ALPHA * min(2.0, intensity)
    stride = SMOKE_ANDROID_STRIDE if _ANDROID else 1
    if stride > 1:
        peak *= SMOKE_ANDROID_ALPHA_GAIN
    t = t_accum + phase
    # Oldest (highest) puffs first, so the newer ones at the base sit on top.
    order = sorted(range(SMOKE_PUFFS), key=lambda i: -((t * (0.85 + 0.3 * _hash01(i + 17))
                                                         + i / SMOKE_PUFFS) % 1.0))
    for i in order:
        if i % stride:
            continue
        dx, dy, pr, op = smoke_puff(i, t, sr, size)
        a = int(255 * min(1.0, peak * op))
        if a <= 2 or pr < 1:
            continue
        d = max(2, int(round(pr * 2 / SMOKE_SIZE_STEP)) * SMOKE_SIZE_STEP)
        key = ("smoke_puff", col, d)
        sprite = pool.get(key)
        if sprite is None:
            sprite = pygame.transform.smoothscale(base, (d, d))
            pool[key] = sprite
        sprite.set_alpha(a)
        screen.blit(sprite, (int(sx + dx) - d // 2, int(sy + dy) - d // 2))


# ---------------------------------------------------------------------------
# Flies
# ---------------------------------------------------------------------------

def fly_position(i: int, t_accum: float, t_global: float, sx: float, sy: float,
                 sr: float) -> tuple[float, float, float]:
    """(x, y, depth 0.6..1) of fly i: two superposed orbits per axis with their
    own frequencies (a wandering loop), plus a small high-frequency buzz."""
    h = [_hash01(i * 7 + k) for k in range(8)]
    t = t_accum * FLIES_SPEED
    fx1, fx2 = 0.6 + 0.8 * h[0], 1.3 + 1.2 * h[1]
    fy1, fy2 = 0.5 + 0.9 * h[2], 1.1 + 1.3 * h[3]
    x = sr * (0.55 * math.sin(t * fx1 + 6.283 * h[4]) + 0.3 * math.sin(t * fx2 + 6.283 * h[5]))
    y = sr * 0.6 * (0.55 * math.cos(t * fy1 + 6.283 * h[6]) + 0.3 * math.sin(t * fy2 + 6.283 * h[7]))
    buzz = FLIES_BUZZ_AMP * sr
    x += buzz * math.sin(2.0 * math.pi * FLIES_BUZZ_HZ * t_global + 11.0 * h[0])
    y += buzz * math.cos(2.0 * math.pi * FLIES_BUZZ_HZ * 1.13 * t_global + 7.0 * h[1])
    depth = 0.6 + 0.4 * h[5]
    return sx + x, sy + y, depth


def draw_flies_effect(screen: pygame.Surface, sx: float, sy: float, sr: float,
                      color: list | tuple, intensity: float, t_accum: float, t_global: float,
                      pulse_min: float = 1.0) -> None:
    """A swarm: each fly a small dark body with two flickering wings, nearer
    flies slightly bigger and more opaque."""
    count = int(round(max(0.0, intensity) * FLIES_PER_INTENSITY))
    if count < 1 or sr <= 0:
        return
    col = (int(color[0]), int(color[1]), int(color[2]))
    scale = max(0.8, min(2.0, sr / 120.0)) * max(0.3, pulse_min)
    wing_col = (min(255, col[0] + 150), min(255, col[1] + 150), min(255, col[2] + 160),
                FLIES_WING_ALPHA)
    for i in range(count):
        x, y, depth = fly_position(i, t_accum, t_global, sx, sy, sr)
        length = max(1.5, FLIES_BASE_SIZE * scale * depth)
        ix, iy = int(x), int(y)
        if length < 2.2:
            screen.set_at((ix, iy), col)
            continue
        w = int(round(length))
        h = max(1, int(round(length * 0.6)))
        # Wings: up/down on alternate beats of the buzz, per fly offset.
        beat = int(t_global * 40 + i * 3) % 2
        wing_h = max(1, h - beat)
        wings = pygame.Surface((w + 2, wing_h + 1), pygame.SRCALPHA)
        pygame.draw.ellipse(wings, wing_col, wings.get_rect())
        screen.blit(wings, (ix - (w + 2) // 2, iy - h - wing_h // 2 + beat))
        pygame.draw.ellipse(screen, col, (ix - w // 2, iy - h // 2, w, h))


# ---------------------------------------------------------------------------
# Bubble tips
# ---------------------------------------------------------------------------

_TEXT_WRAP_CACHE, _FONT_CACHE = {}, {}


def draw_bubble_tip_effect(screen: pygame.Surface, sx: float, sy: float,
                           text: str, trigger: str, is_editor: bool = False,
                           width: float = 300, height: float = 180, zoom: float = 1.0,
                           color: list | tuple = (252, 252, 255), alpha: int = 255,
                           font_size: int = 22, font_color: list | tuple = (40, 40, 40),
                           chars_limit: int = 9999, cache: dict | None = None,
                           close_label: str = "Close"):
    """Speech-bubble tip with a close button (game only)."""
    sz = max(10, int(font_size * zoom))
    if ("Segoe UI", sz) not in _FONT_CACHE:
        _FONT_CACHE[("Segoe UI", sz)] = pygame.font.SysFont("Segoe UI", sz)
    font_main = _FONT_CACHE[("Segoe UI", sz)]

    padding, corner_radius, bubble_w, bubble_h = 24 * zoom, int(22 * zoom), int(width), int(height)
    bx, by, margin = sx - bubble_w // 2, sy - bubble_h - 40 * zoom, int(20 * zoom)
    cv_w, cv_h = bubble_w + margin * 2, bubble_h + int(45 * zoom) + margin * 2

    bubble_surf = cache.get(("bubble_canvas", cv_w, cv_h)) if cache is not None else None
    if bubble_surf is None:
        bubble_surf = pygame.Surface((cv_w, cv_h), pygame.SRCALPHA)
        if cache is not None:
            cache[("bubble_canvas", cv_w, cv_h)] = bubble_surf

    bubble_surf.fill((0, 0, 0, 0))
    rbx, rby, rsx, rsy = margin, margin, cv_w // 2, margin + bubble_h + int(40 * zoom)
    for i in range(12, 0, -2):
        pygame.draw.rect(bubble_surf, (0, 0, 0, int(22 * (1.0 - i / 12))),
                         (rbx - i, rby - i + 4, bubble_w + i * 2, bubble_h + i * 2),
                         border_radius=corner_radius + i)

    pygame.draw.polygon(bubble_surf, (*color, alpha),
                        [(rsx, rsy - margin), (rsx - 12 * zoom, rsy - margin - 30 * zoom),
                         (rsx + 12 * zoom, rsy - margin - 30 * zoom)])
    pygame.draw.rect(bubble_surf, (*color, alpha), (rbx, rby, bubble_w, bubble_h),
                     border_radius=corner_radius)
    pygame.draw.rect(bubble_surf, (*[max(0, c - 40) for c in color], 255),
                     (rbx, rby, bubble_w, bubble_h), 2, border_radius=corner_radius)

    screen.blit(bubble_surf, (bx - margin, by - margin))

    w_key = (text, sz, bubble_w - padding * 2)
    if w_key not in _TEXT_WRAP_CACHE:
        words = str(text).split(' ')
        lines, curr = [], []
        for w in words:
            if font_main.size(' '.join(curr + [w]))[0] < w_key[2]:
                curr.append(w)
            else:
                if curr:
                    lines.append(' '.join(curr))
                    curr = [w]
        if curr:
            lines.append(' '.join(curr))
        _TEXT_WRAP_CACHE[w_key] = lines

    lh, ty, curr_c = font_main.get_linesize(), by + int(padding), 0
    for i, line in enumerate(_TEXT_WRAP_CACHE.get(w_key, [])):
        if curr_c >= chars_limit:
            break
        l_draw = line[:chars_limit - curr_c]
        curr_c += len(line) + 1
        ts = font_main.render(l_draw, True, tuple(font_color))
        screen.blit(ts, (bx + (bubble_w - ts.get_width()) // 2, ty + i * lh))

    if not is_editor:
        f_key = ("Segoe UI_Bold", int(18 * zoom))
        if f_key not in _FONT_CACHE:
            _FONT_CACHE[f_key] = pygame.font.SysFont("Segoe UI", f_key[1], bold=True)
        btn_l = _FONT_CACHE[f_key].render(str(close_label).upper(), True, (255, 255, 255))
        # The button takes the width of its label (German "SCHLIESSEN" did
        # not fit the old fixed 100 px).
        btn_w = max(int(100 * zoom), btn_l.get_width() + int(28 * zoom))
        btn_h = int(34 * zoom)
        btn_x = bx + (bubble_w - btn_w) // 2
        btn_y = by + bubble_h - btn_h - 15 * zoom
        btn_r = pygame.Rect(int(btn_x), int(btn_y), btn_w, btn_h)
        b_col = (70, 210, 120) if btn_r.collidepoint(pygame.mouse.get_pos()) else (60, 185, 105)
        pygame.draw.rect(screen, b_col, btn_r, border_radius=12)
        screen.blit(btn_l, btn_l.get_rect(center=btn_r.center))
        return btn_r
    return None


class EffectRenderer:
    """Draws a scene's effects, sorted by layer, with one shared sprite pool."""

    def __init__(self) -> None:
        self._time, self._render_pool = 0.0, {}

    def update(self, dt: float, effects: list = None) -> None:
        self._time += dt
        if effects:
            for fx in effects:
                update_effect_state(fx, dt)

    def draw(self, screen: pygame.Surface, effects: list, scaling_manager, lang_manager=None,
             scenic_factor: float = 1.0) -> list:
        if not effects:
            return []
        sm, bubble_btns = scaling_manager, []
        close_label = lang_manager.get("btn_close", "Close") if lang_manager else "Close"
        for fx in sorted(effects, key=lambda f: getattr(f, "layer_z", 40)):
            sx, sy = sm.bg_to_screen_scenic(fx.x, fx.y, scenic_factor)
            sr = fx.radius * sm._bg_display_scale * scenic_factor
            if fx.type == "glint":
                draw_glint_effect(screen, sx, sy, sr, fx.color, fx.intensity, fx._t_accum,
                                  fx.phase, fx.pulse_min, self._render_pool)
            elif fx.type == "smoke":
                draw_smoke_effect(screen, sx, sy, sr, fx.color, fx.intensity, fx._t_accum,
                                  fx.phase, fx.pulse_min, self._render_pool)
            elif fx.type == "flies":
                draw_flies_effect(screen, sx, sy, sr, fx.color, fx.intensity, fx._t_accum,
                                  self._time, getattr(fx, "pulse_min", 1.0))
            elif fx.type == "bubble_tip":
                if lang_manager and not getattr(fx, "_visible", False):
                    continue
                text = (lang_manager.get(fx.text_key, fx.text_key) if lang_manager
                        else getattr(fx, "text_key", "NEW_TIP"))
                btn_r = draw_bubble_tip_effect(
                    screen, sx, sy, text, fx.trigger, is_editor=(lang_manager is None),
                    width=getattr(fx, "width", 300) * sm._bg_display_scale,
                    height=getattr(fx, "height", 180) * sm._bg_display_scale,
                    zoom=sm._bg_display_scale, color=getattr(fx, "color", (252, 252, 255)),
                    alpha=getattr(fx, "alpha", 255), font_size=getattr(fx, "font_size", 22),
                    font_color=getattr(fx, "font_color", (40, 40, 40)),
                    chars_limit=int(getattr(fx, "_chars_visible", 9999)),
                    cache=self._render_pool, close_label=close_label)
                if btn_r:
                    bubble_btns.append((fx, btn_r))
        if len(self._render_pool) > CACHE_LIMIT:
            self._render_pool.clear()
        return bubble_btns
