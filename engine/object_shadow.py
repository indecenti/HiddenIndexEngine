"""
engine/object_shadow.py

Contact shadow of a scene object: a soft ellipse under the object, so an object resting
on the ground does not look like it floats. Data contract (scene.json object, also inside
an alt spot):

    "shadow": {"dy": <float>, "w": <float>, "a": <int 0..255>}

  - dy: distance in reference px of the object (the space of width/height, multiplied by
    the object's scale) from the centre of the object rectangle down to the resting point;
  - w:  width of the ellipse in reference px (multiplied by scale); the height is
    w * SHADOW_ASPECT;
  - a:  opacity at the centre (further multiplied by the object's own alpha).

The ellipse is not rotated, is drawn just before (under) the object in the same bg->screen
space, and is not drawn for found or hidden objects. Alpha at normalized elliptical
distance d (0 at the centre, 1 at the rim) is a * (1 - d) ** SHADOW_FALLOFF.

Web parity: editor/web_template/runtime/core.js (drawObjectShadow); the constants reach
the web runtime through editor/web_rules.py::engine_rules() (docs/web/WEB_EXPORT_SYNC.md,
section M).
"""

from __future__ import annotations

from collections import OrderedDict
from typing import Any, Optional

import numpy as np
import pygame

# Height / width of the shadow ellipse.
SHADOW_ASPECT = 0.22
# Exponent of the radial fade: higher = darker core, softer rim.
SHADOW_FALLOFF = 1.6
SHADOW_ALPHA_MAX = 255
# Desktop render cache: sizes are snapped to this step (px) so zoom and resize reuse
# entries, and at most this many ellipses are kept (LRU, gradual eviction).
SHADOW_SIZE_STEP = 2
SHADOW_CACHE_LIMIT = 96

_cache: "OrderedDict[tuple[int, int, int], pygame.Surface]" = OrderedDict()


def parse_shadow(raw: Any) -> Optional[dict]:
    """Validated shadow dict {dy: float, w: float, a: int}, or None when absent/invalid."""
    if not isinstance(raw, dict):
        return None
    try:
        dy = float(raw.get("dy", 0.0))
        w = float(raw["w"])
        a = int(raw.get("a", 0))
    except (KeyError, TypeError, ValueError):
        return None
    a = max(0, min(SHADOW_ALPHA_MAX, a))
    if w <= 0 or a <= 0:
        return None
    return {"dy": dy, "w": w, "a": a}


def shadow_alpha(d: float, a: int) -> float:
    """Alpha at normalized elliptical distance d (0 = centre, >= 1 = outside)."""
    if d >= 1.0:
        return 0.0
    return a * (1.0 - max(0.0, d)) ** SHADOW_FALLOFF


def shadow_surface(width_px: int, alpha: int) -> Optional[pygame.Surface]:
    """The shadow ellipse (black, per-pixel alpha) for a screen width, cached."""
    w = max(SHADOW_SIZE_STEP, int(round(width_px / SHADOW_SIZE_STEP)) * SHADOW_SIZE_STEP)
    h = max(SHADOW_SIZE_STEP, int(round(w * SHADOW_ASPECT)))
    alpha = max(0, min(SHADOW_ALPHA_MAX, int(alpha)))
    if alpha <= 0:
        return None
    key = (w, h, alpha)
    surf = _cache.get(key)
    if surf is not None:
        _cache.move_to_end(key)
        return surf
    xs = (np.arange(w, dtype=np.float32) + 0.5 - w / 2.0) / (w / 2.0)
    ys = (np.arange(h, dtype=np.float32) + 0.5 - h / 2.0) / (h / 2.0)
    d = np.sqrt(xs[:, None] ** 2 + ys[None, :] ** 2)
    a_arr = alpha * np.clip(1.0 - d, 0.0, 1.0) ** SHADOW_FALLOFF
    surf = pygame.Surface((w, h), pygame.SRCALPHA)
    surf.fill((0, 0, 0, 0))
    pygame.surfarray.pixels_alpha(surf)[:] = np.round(a_arr).astype(np.uint8)
    _cache[key] = surf
    while len(_cache) > SHADOW_CACHE_LIMIT:
        _cache.popitem(last=False)
    return surf


def draw_shadow(screen: pygame.Surface, shadow: Optional[dict], center_screen: tuple,
                px_per_ref: float, scale: float, obj_alpha: int = 255) -> Optional[pygame.Rect]:
    """Blits the shadow of an object whose rectangle centre is at center_screen.

    px_per_ref: screen px per reference px of the object (bg display scale x scenic).
    Returns the screen rect drawn, or None when nothing was drawn.
    """
    if not shadow:
        return None
    width_px = shadow["w"] * scale * px_per_ref
    alpha = int(round(shadow["a"] * max(0, min(SHADOW_ALPHA_MAX, obj_alpha))
                      / SHADOW_ALPHA_MAX))
    if width_px < 1.0:
        return None
    surf = shadow_surface(int(round(width_px)), alpha)
    if surf is None:
        return None
    cx = center_screen[0]
    cy = center_screen[1] + shadow["dy"] * scale * px_per_ref
    rect = surf.get_rect(center=(int(round(cx)), int(round(cy))))
    screen.blit(surf, rect.topleft)
    return rect
