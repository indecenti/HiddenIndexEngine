"""
engine/menu_skins/base.py

SKIN interface for the pygame menus.

The MENU CORE (engine/menu_system.py) owns data, navigation, save/lock, i18n,
audio, scroll and hit testing: it is identical for every theme. The SKIN only
defines the look and feel and is selected at runtime from ui_theme (fallback
'default').

Skins work through additive HOOKS invoked by the core at precise points of the
rendering pass; the base class draws nothing extra, so a theme without the newer
theme.json sections keeps exactly the historical behaviour.

Robustness: a theme is user authored data (the editor harvests theme.json into
the game). Two guards live here so a malformed theme degrades the look instead
of taking the menu down:

  * the ``as_*`` coercers turn a bad JSON value back into the documented default;
  * :func:`skin_call` runs a hook fail-soft, falling back to the neutral base
    implementation and disabling the broken hook for the session.
"""

from collections import OrderedDict
from typing import Any, Callable

from engine.utils import get_logger

logger = get_logger(__name__)

# Default cap of SurfaceCache: a few chip/particle sizes per skin, no more.
SURFACE_CACHE_MAX = 32


# ── Coercion of theme values (theme.json is authored data, not trusted) ──────

def as_float(value: Any, default: float) -> float:
    """Coerce a theme value to float; malformed data falls back to `default`."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def as_int(value: Any, default: int) -> int:
    """Coerce a theme value to int; malformed data falls back to `default`."""
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def as_bool(value: Any, default: bool) -> bool:
    """Coerce a theme value to bool (None keeps `default`)."""
    if value is None:
        return default
    return bool(value)


def as_rgb(value: Any, default: tuple[int, int, int]) -> tuple[int, int, int]:
    """Coerce a theme colour ([r, g, b]) to a clamped RGB tuple."""
    try:
        r, g, b = (int(c) for c in tuple(value)[:3])
    except (TypeError, ValueError):
        return tuple(default)
    return (max(0, min(255, r)), max(0, min(255, g)), max(0, min(255, b)))


# ── Caches shared by the skins ──────────────────────────────────────────────

class SurfaceCache:
    """Bounded LRU for surfaces that are static but expensive to rebuild.

    Skins pre-render decorations (chip shadows, particle glows) whose pixels
    only depend on a size/colour key: rebuilding them per frame costs an
    SRCALPHA allocation plus several draw calls per element. This keeps them
    with the engine eviction convention - gradual `popitem(last=False)` instead
    of clearing everything, which would rebuild every surface on the same frame
    and show up as a hitch.
    """

    def __init__(self, cap: int = SURFACE_CACHE_MAX) -> None:
        self._cap = max(1, int(cap))
        self._items: OrderedDict = OrderedDict()

    def get_or_build(self, key, build: Callable[[], Any]):
        """Return the surface for `key`, building (and caching) it on a miss."""
        surf = self._items.get(key)
        if surf is None:
            surf = build()
            self._items[key] = surf
            while len(self._items) > self._cap:
                self._items.popitem(last=False)   # evict the least recently used
        else:
            self._items.move_to_end(key)
        return surf

    def clear(self) -> None:
        self._items.clear()

    def __len__(self) -> int:
        return len(self._items)


def cached_title(skin: "MenuSkin", key, build: Callable[[], Any]):
    """Cache the title surfaces of a skin, rebuilt only when `key` changes.

    Composing a title costs one font.render per glyph (render_spaced) times the
    number of layers, so rebuilding it every frame is a measurable share of the
    menu frame time. `key` MUST include the SCALED font size: without it the
    title would stay at the previous resolution after a resize/fullscreen
    switch.
    """
    if getattr(skin, "_title_key", None) != key or getattr(skin, "_title_val", None) is None:
        skin._title_val = build()
        skin._title_key = key
    return skin._title_val


# ── Fail-soft hook dispatch ──────────────────────────────────────────────────

def skin_call(skin: "MenuSkin", hook: str, *args) -> Any:
    """Invoke a skin hook without letting it kill the menu.

    A hook that raises (broken theme value, missing asset, skin bug) would
    otherwise propagate through the whole draw pass and crash the game on the
    main menu. Here the first failure is logged with its traceback, the hook is
    disabled for the rest of the session and the neutral :class:`MenuSkin`
    implementation takes over: the menu keeps working with the core look
    instead of crashing (or spamming one traceback per frame).
    """
    disabled = getattr(skin, "_disabled_hooks", None)
    if disabled is None:
        disabled = set()
        skin._disabled_hooks = disabled

    if hook not in disabled:
        try:
            return getattr(skin, hook)(*args)
        except Exception:
            disabled.add(hook)
            logger.error("menu_skins: hook '%s' of skin '%s' failed; "
                         "falling back to the base skin for this session.",
                         hook, getattr(skin, "id", "?"), exc_info=True)

    # Neutral fallback: the base implementation never decorates, so the menu
    # degrades to the core look. If even that fails it is a core bug: log it
    # once and give up on the hook entirely.
    base_key = hook + ":base"
    if base_key in disabled:
        return None
    try:
        return getattr(MenuSkin, hook)(skin, *args)
    except Exception:
        disabled.add(base_key)
        logger.error("menu_skins: base fallback for hook '%s' failed.",
                     hook, exc_info=True)
        return None


class MenuSkin:
    """Base skin: no extra decoration (neutral behaviour)."""

    id = "base"

    def __init__(self, theme) -> None:
        self.theme = theme
        self._t = 0.0  # time accumulator for the skin animations
        self._disabled_hooks: set[str] = set()  # hooks disabled by skin_call
        self._title_key = None   # cached_title: key of the composed title
        self._title_val = None   # cached_title: composed surface(s)

    # ── Motion knobs (read from theme.motion, with the historical defaults) ──
    @property
    def carousel_zoom(self) -> float:
        return as_float(self.theme.motion("carousel_zoom", 0.25), 0.25)

    @property
    def float_amp(self) -> float:
        return as_float(self.theme.motion("float_amp", 4.0), 4.0)

    @property
    def magnetic(self) -> bool:
        return as_bool(self.theme.motion("magnetic", True), True)

    # ── Reduced motion / performance ─────────────────────────────────────────
    def reduced(self, ms) -> bool:
        """Reduced mode (Android/low-end): heavy effects degrade."""
        return bool(getattr(ms, "_android", False))

    def fx_on(self, ms, feature: str) -> bool:
        """True if `feature` must run: off only when reduced-motion lists it."""
        if self.reduced(ms) and self.theme.motion_disabled(feature):
            return False
        return True

    def update(self, ms, dt: float) -> None:
        self._t += as_float(dt, 0.0)

    # ── Rendering hooks (default: no decoration) ─────────────────────────────
    def draw_background_pre(self, ms, screen, sw, sh) -> None:
        """Atmosphere behind title/buttons (over the background drawn by the core)."""
        pass

    def draw_title(self, ms, screen) -> None:
        """State title; by default it uses the core renderer."""
        ms._draw_state_title(screen)

    def button_jitter(self, ms, b):
        """Positional offset (dx, dy) in reference coordinates for the button."""
        return (0.0, 0.0)

    def behind_button(self, ms, screen, b, draw_rect, is_locked) -> None:
        """Decoration drawn BEHIND the button (plate, halo, frame)."""
        pass

    def draw_overlay(self, ms, screen, sw, sh) -> None:
        """FRONT decoration over the contents (grain, confetti, vignette)."""
        pass

    def arrange(self, ms) -> None:
        """Recompose the button positions after build_buttons.
        Default: the core layout is untouched. Skins may move the buttons
        (vertical offsets only, so horizontal scroll/zoom keep working)."""
        pass
