"""
engine/menu_skins/

Registry degli skin dei menu. Ogni skin e' un modulo pluggabile selezionato per
id (= ui_theme). Aggiungere un tema = aggiungere uno skin qui, senza toccare il
MENU CORE. Temi non registrati ricadono su DefaultSkin (nessuna regressione).
"""

from engine.utils import get_logger
from .base import MenuSkin
from .default_skin import DefaultSkin
from .horror_skin import HorrorSkin
from .kids_skin import KidsSkin
from .cyber_neon_skin import CyberNeonSkin
from .mystery_skin import MysterySkin

logger = get_logger(__name__)

# id tema -> classe skin. I temi assenti usano DefaultSkin.
_REGISTRY: dict[str, type] = {
    "default": DefaultSkin,
    "horror": HorrorSkin,
    "kids": KidsSkin,
    "cyber_neon": CyberNeonSkin,
    "mystery": MysterySkin,
    # android_std: nessuno skin dedicato -> DefaultSkin (variante leggera/performance).
}


def register_skin(theme_id: str, skin_cls: type) -> None:
    """Registra (o sovrascrive) lo skin per un id tema."""
    _REGISTRY[theme_id] = skin_cls


def get_skin(theme) -> MenuSkin:
    """Istanzia lo skin per il tema dato (fallback DefaultSkin)."""
    theme_id = getattr(theme, "theme_id", "default")
    cls = _REGISTRY.get(theme_id, DefaultSkin)
    try:
        return cls(theme)
    except Exception as e:
        logger.warning("menu_skins: skin '%s' non inizializzabile (%s); uso DefaultSkin.", theme_id, e)
        return DefaultSkin(theme)


__all__ = ["MenuSkin", "DefaultSkin", "HorrorSkin", "KidsSkin",
           "CyberNeonSkin", "MysterySkin", "get_skin", "register_skin"]
