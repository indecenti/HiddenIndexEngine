"""
engine/menu_skins/

Registry of the menu skins. Every skin is a pluggable module selected by id
(= ui_theme). Adding a theme = adding a skin here, without touching the MENU
CORE. Unregistered themes fall back to DefaultSkin (no regression).
"""

from engine.utils import get_logger
from .base import (MenuSkin, SurfaceCache, cached_title, skin_call,
                   as_bool, as_float, as_int, as_rgb)
from .default_skin import DefaultSkin
from .horror_skin import HorrorSkin
from .kids_skin import KidsSkin
from .cyber_neon_skin import CyberNeonSkin
from .mystery_skin import MysterySkin

logger = get_logger(__name__)

# theme id -> skin class. Missing themes use DefaultSkin.
_REGISTRY: dict[str, type] = {
    "default": DefaultSkin,
    "horror": HorrorSkin,
    "kids": KidsSkin,
    "cyber_neon": CyberNeonSkin,
    "mystery": MysterySkin,
    # android_std: no dedicated skin -> DefaultSkin (light/performance variant).
}


def register_skin(theme_id: str, skin_cls: type) -> None:
    """Register (or override) the skin for a theme id."""
    _REGISTRY[theme_id] = skin_cls


def get_skin(theme) -> MenuSkin:
    """Instantiate the skin for the given theme (fallback DefaultSkin).

    A skin whose __init__ raises must not take the menu down: DefaultSkin is
    tried next and, if even that fails (broken theme object), the neutral
    MenuSkin keeps the core look alive.
    """
    theme_id = getattr(theme, "theme_id", "default")
    cls = _REGISTRY.get(theme_id, DefaultSkin)
    try:
        return cls(theme)
    except Exception as e:
        logger.warning("menu_skins: skin '%s' cannot be initialised (%s); using DefaultSkin.",
                       theme_id, e)
    try:
        return DefaultSkin(theme)
    except Exception as e:
        logger.error("menu_skins: DefaultSkin cannot be initialised (%s); using the base skin.", e)
        return MenuSkin(theme)


__all__ = ["MenuSkin", "DefaultSkin", "HorrorSkin", "KidsSkin",
           "CyberNeonSkin", "MysterySkin", "get_skin", "register_skin",
           "SurfaceCache", "cached_title", "skin_call",
           "as_bool", "as_float", "as_int", "as_rgb"]
