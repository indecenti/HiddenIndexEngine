"""
engine/scaling_manager.py

Gestione dello scaling dinamico tra la risoluzione di riferimento (1280x720)
e la risoluzione reale dello schermo corrente.

Responsabilità:
- Calcolo del fattore di scala uniforme (letterbox)
- Conversione coordinate schermo <-> coordinate di riferimento
- Trasformazione coordinate con pan/zoom attivo
- Cache LRU delle Surface scalate
- Notifica resize tra schermate
"""

import pygame
from functools import lru_cache
from engine.utils import get_logger
import collections

log = get_logger(__name__)

# Risoluzione di riferimento — "verità" del progetto
REF_W: int = 1280
REF_H: int = 720


class ScalingManager:
    """
    Unica istanza condivisa da tutti i moduli.
    Inizializzata da core.py prima di qualsiasi altra cosa.
    """

    def __init__(self) -> None:
        self._screen_w: int = REF_W
        self._screen_h: int = REF_H
        self._scale: float = 1.0
        self._offset_x: int = 0
        self._offset_y: int = 0

        # Pan/Zoom della scena attiva
        self._pan_x: float = 0.0
        self._pan_y: float = 0.0
        self._zoom: float = 1.0

        # Background mapping (aggiornato per ogni scena)
        self._bg_orig_w: int = REF_W
        self._bg_orig_h: int = REF_H
        self._bg_json_scale: float = 1.0
        self._bg_display_scale: float = 1.0
        self._bg_screen_x: float = 0.0
        self._bg_screen_y: float = 0.0
        self._bg_screen_w: float = float(REF_W)
        self._bg_screen_h: float = float(REF_H)

        # Cache Surface scalate (path -> Surface)
        self._surface_cache: collections.OrderedDict[str, pygame.Surface] = collections.OrderedDict()
        self._cache_max_bytes: int = 64 * 1024 * 1024  # 64 MB
        self._cache_bytes: int = 0

        self._resize_pending: bool = False

    # ------------------------------------------------------------------
    # Setup e resize
    # ------------------------------------------------------------------

    def update_screen_size(self, screen_w: int, screen_h: int) -> None:
        """Ricalcola fattori di scala per la nuova risoluzione dello schermo."""
        self._screen_w = screen_w
        self._screen_h = screen_h

        scale_x = screen_w / REF_W
        scale_y = screen_h / REF_H
        self._scale = min(scale_x, scale_y)

        # Offset per centrare il contenuto (letterbox)
        self._offset_x = int((screen_w - REF_W * self._scale) / 2)
        self._offset_y = int((screen_h - REF_H * self._scale) / 2)

        self.invalidate_cache()
        log.debug(
            "Screen %dx%d | scale=%.4f | offset=(%d,%d)",
            screen_w, screen_h, self._scale, self._offset_x, self._offset_y,
        )

    def notify_resize(self) -> None:
        """Segnala che c'è un resize pendente da applicare alla prossima schermata."""
        self._resize_pending = True

    def consume_resize(self) -> bool:
        """Restituisce True se c'è un resize da applicare, e lo consuma."""
        if self._resize_pending:
            self._resize_pending = False
            return True
        return False

    # ------------------------------------------------------------------
    # Proprietà
    # ------------------------------------------------------------------

    @property
    def scale(self) -> float:
        return self._scale

    @property
    def offset_x(self) -> int:
        return self._offset_x

    @property
    def offset_y(self) -> int:
        return self._offset_y

    @property
    def screen_w(self) -> int:
        return self._screen_w

    @property
    def screen_h(self) -> int:
        return self._screen_h

    @property
    def zoom(self) -> float:
        return self._zoom

    @property
    def pan(self) -> tuple[float, float]:
        return (self._pan_x, self._pan_y)

    # ------------------------------------------------------------------
    # Conversione coordinate
    # ------------------------------------------------------------------

    def ref_to_screen(self, rx: float, ry: float) -> tuple[int, int]:
        """Converte coordinate di riferimento in coordinate schermo."""
        sx = int(round(rx * self._scale + self._offset_x))
        sy = int(round(ry * self._scale + self._offset_y))
        return sx, sy

    def screen_to_ref(self, sx: int, sy: int) -> tuple[float, float]:
        """Converte coordinate schermo in coordinate di riferimento."""
        rx = (sx - self._offset_x) / self._scale
        ry = (sy - self._offset_y) / self._scale
        return rx, ry

    def screen_to_scene(self, sx: int, sy: int) -> tuple[float, float]:
        """
        Converte coordinate schermo in coordinate scena (di riferimento),
        tenendo conto di pan e zoom attivi.

        Pipeline: screen -> viewport (ref) -> scene
        """
        rx, ry = self.screen_to_ref(sx, sy)
        # Inverti zoom e pan
        scene_x = (rx - self._pan_x) / self._zoom
        scene_y = (ry - self._pan_y) / self._zoom
        return scene_x, scene_y

    def scale_value(self, v: float) -> int:
        """Scala un singolo valore numerico (es. raggio, dimensione font)."""
        return int(round(v * self._scale))

    def scale_rect(self, x: float, y: float, w: float, h: float) -> pygame.Rect:
        """Scala un rettangolo in coordinate di riferimento a coordinate schermo."""
        sx, sy = self.ref_to_screen(x, y)
        sw = int(round(w * self._scale))
        sh = int(round(h * self._scale))
        return pygame.Rect(sx, sy, sw, sh)

    # ------------------------------------------------------------------
    # Background space mapping
    # ------------------------------------------------------------------

    def set_background(self, bg_w: int, bg_h: int, bg_scale: float = 1.0) -> None:
        """
        Calcola il mapping background→screen per la scena corrente.

        Le coordinate degli oggetti nel JSON sono in spazio background
        (pixel del file immagine originale).  Questo metodo calcola
        come il background viene mostrato sullo schermo e permette di
        convertire coordinate in entrambe le direzioni.

        Il background viene letterboxato: scalato uniformemente per
        adattarsi allo schermo senza distorcere, con barre nere se
        necessario.
        """
        self._bg_orig_w = bg_w
        self._bg_orig_h = bg_h
        self._bg_json_scale = bg_scale  # fattore extra da scene.json

        # Dimensioni "logiche" del background (applica background_scale)
        logical_w = bg_w * bg_scale
        logical_h = bg_h * bg_scale

        # Scala per adattarsi allo schermo (letterbox: prende il minimo)
        fit_scale = min(self._screen_w / logical_w, self._screen_h / logical_h)
        self._bg_display_scale = fit_scale * bg_scale

        # Dimensioni a schermo e posizione centrata
        display_w = logical_w * fit_scale
        display_h = logical_h * fit_scale
        self._bg_screen_x = (self._screen_w - display_w) / 2
        self._bg_screen_y = (self._screen_h - display_h) / 2
        self._bg_screen_w = display_w
        self._bg_screen_h = display_h

        log.debug(
            "Background %dx%d (scale=%.2f) → display %.0fx%.0f @ (%.0f, %.0f)",
            bg_w, bg_h, bg_scale, display_w, display_h,
            self._bg_screen_x, self._bg_screen_y,
        )

    def bg_to_screen(self, bx: float, by: float) -> tuple[float, float]:
        """Coordinate background (px del file) → coordinate schermo."""
        sx = bx * self._bg_display_scale + self._bg_screen_x
        sy = by * self._bg_display_scale + self._bg_screen_y
        return sx, sy

    def screen_to_bg(self, sx: float, sy: float) -> tuple[float, float]:
        """Coordinate schermo → coordinate background (px del file)."""
        bx = (sx - self._bg_screen_x) / self._bg_display_scale
        by = (sy - self._bg_screen_y) / self._bg_display_scale
        return bx, by

    def scale_bg_value(self, v: float) -> float:
        """Scala un valore scalare (raggio, dimensione) da bg-space a pixel schermo."""
        return v * self._bg_display_scale

    def get_scenic_params(self, factor: float) -> tuple[float, float, float, float]:
        """Ritorna (x, y, w, h) per il background applicando uno zoom scenico centrato."""
        w = self._bg_screen_w * factor
        h = self._bg_screen_h * factor
        x = self._bg_screen_x - (w - self._bg_screen_w) / 2
        y = self._bg_screen_y - (h - self._bg_screen_h) / 2
        return x, y, w, h

    def bg_to_screen_scenic(self, bx: float, by: float, factor: float) -> tuple[float, float]:
        """Versione dello zoom scenico (solo visuale) di bg_to_screen."""
        # 1. Coordinate schermo nominali
        sx = bx * self._bg_display_scale + self._bg_screen_x
        sy = by * self._bg_display_scale + self._bg_screen_y
        
        # 2. Applica zoom centrato sullo schermo
        cx, cy = self._screen_w / 2, self._screen_h / 2
        jsx = cx + (sx - cx) * factor
        jsy = cy + (sy - cy) * factor
        return jsx, jsy

    # ------------------------------------------------------------------
    # Pan / Zoom scena
    # ------------------------------------------------------------------

    def set_pan(self, px: float, py: float) -> None:
        self._pan_x = px
        self._pan_y = py

    def set_zoom(self, zoom: float) -> None:
        self._zoom = max(0.5, min(zoom, 4.0))

    def reset_pan_zoom(self) -> None:
        self._pan_x = 0.0
        self._pan_y = 0.0
        self._zoom = 1.0

    # ------------------------------------------------------------------
    # Cache Surface scalate
    # ------------------------------------------------------------------

    def scale_surface(self, surface: pygame.Surface, cache_key: str | None = None) -> pygame.Surface:
        """
        Scala una Surface alla dimensione corrente.
        Se cache_key è fornita, usa la cache LRU.
        """
        if cache_key and cache_key in self._surface_cache:
            self._surface_cache.move_to_end(cache_key)
            return self._surface_cache[cache_key]

        new_w = int(surface.get_width() * self._scale)
        new_h = int(surface.get_height() * self._scale)
        scaled = pygame.transform.smoothscale(surface, (new_w, new_h))

        if cache_key:
            self._put_cache(cache_key, scaled)

        return scaled

    def scale_surface_to_ref(self, surface: pygame.Surface, ref_w: float, ref_h: float,
                              cache_key: str | None = None) -> pygame.Surface:
        """
        Scala una Surface a dimensioni di riferimento specifiche,
        poi applica il fattore di scala corrente.
        """
        if cache_key and cache_key in self._surface_cache:
            self._surface_cache.move_to_end(cache_key)
            return self._surface_cache[cache_key]

        target_w = int(ref_w * self._scale)
        target_h = int(ref_h * self._scale)
        scaled = pygame.transform.smoothscale(surface, (target_w, target_h))

        if cache_key:
            self._put_cache(cache_key, scaled)

        return scaled

    def _put_cache(self, key: str, surface: pygame.Surface) -> None:
        size = surface.get_width() * surface.get_height() * 4  # stima RGBA
        
        if key in self._surface_cache:
            old_surf = self._surface_cache[key]
            old_size = old_surf.get_width() * old_surf.get_height() * 4
            self._cache_bytes -= old_size
            del self._surface_cache[key]

        # Evicting finchè non c'è spazio sufficiente
        while self._surface_cache and self._cache_bytes + size > self._cache_max_bytes:
            _, stale_surf = self._surface_cache.popitem(last=False)
            stale_size = stale_surf.get_width() * stale_surf.get_height() * 4
            self._cache_bytes -= stale_size

        self._surface_cache[key] = surface
        self._cache_bytes += size

    def invalidate_cache(self) -> None:
        """Svuota completamente la cache delle Surface scalate."""
        self._surface_cache.clear()
        self._cache_bytes = 0
        log.debug("Surface cache invalidata")
