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
        # I campi _bg_* sono il mapping EFFETTIVO (base + camera zoom/pan): tutti i
        # consumatori (bg_to_screen, screen_to_bg, scale_bg_value, get_scenic_params,
        # rendering oggetti/effetti, hit-test) usano questi e rispettano quindi lo
        # zoom/pan interattivo senza modifiche. I campi _base_bg_* tengono il mapping
        # SENZA camera, usato per ricalcolare l'effettivo e per la cache del BG.
        self._bg_orig_w: int = REF_W
        self._bg_orig_h: int = REF_H
        self._bg_json_scale: float = 1.0
        self._bg_display_scale: float = 1.0
        self._bg_screen_x: float = 0.0
        self._bg_screen_y: float = 0.0
        self._bg_screen_w: float = float(REF_W)
        self._bg_screen_h: float = float(REF_H)

        self._base_bg_display_scale: float = 1.0
        self._base_bg_screen_x: float = 0.0
        self._base_bg_screen_y: float = 0.0
        self._base_bg_screen_w: float = float(REF_W)
        self._base_bg_screen_h: float = float(REF_H)

        # Limiti camera (zoom interattivo per ispezione HOG). Min 1.0: non si
        # rimpicciolisce oltre il fit; max 3.0 adeguato a target mid-range.
        self._zoom_min: float = 1.0
        self._zoom_max: float = 3.0

        # Cache Surface scalate (path -> Surface)
        self._surface_cache: collections.OrderedDict[str, pygame.Surface] = collections.OrderedDict()
        self._cache_max_bytes: int = 64 * 1024 * 1024  # 64 MB
        self._cache_bytes: int = 0

        self._resize_pending: bool = False

        # ── Safe area (insets per notch/angoli arrotondati/barre di sistema) ──
        # Disattivata di default: su desktop i safe_* coincidono con i bordi
        # grezzi, quindi nessun cambiamento. Su Android viene abilitata da core
        # e combina un padding minimo (% schermo) con il display cutout reale.
        self._safe_enabled: bool = False
        self._cut_l: int = 0
        self._cut_t: int = 0
        self._cut_r: int = 0
        self._cut_b: int = 0
        self._safe_pad_ref: int = 22   # padding minimo in unità di riferimento
        self._safe_pct: float = 0.035  # frazione della dimensione schermo

    # ------------------------------------------------------------------
    # Safe area
    # ------------------------------------------------------------------

    def configure_safe_area(self, enabled: bool, cut_l: int = 0, cut_t: int = 0,
                            cut_r: int = 0, cut_b: int = 0) -> None:
        """Abilita la safe area e imposta gli inset del cutout (in px schermo)."""
        self._safe_enabled = enabled
        self._cut_l, self._cut_t, self._cut_r, self._cut_b = cut_l, cut_t, cut_r, cut_b

    def _base_margin_x(self) -> int:
        return max(self.scale_value(self._safe_pad_ref), int(self._screen_w * self._safe_pct))

    def _base_margin_y(self) -> int:
        return max(self.scale_value(self._safe_pad_ref), int(self._screen_h * self._safe_pct))

    @property
    def safe_left(self) -> int:
        """Coordinata X del bordo sinistro sicuro."""
        if not self._safe_enabled:
            return 0
        return max(self._base_margin_x(), self._cut_l)

    @property
    def safe_right(self) -> int:
        """Coordinata X del bordo destro sicuro."""
        if not self._safe_enabled:
            return self._screen_w
        return self._screen_w - max(self._base_margin_x(), self._cut_r)

    @property
    def safe_top(self) -> int:
        """Coordinata Y del bordo superiore sicuro."""
        if not self._safe_enabled:
            return 0
        return max(self._base_margin_y(), self._cut_t)

    @property
    def safe_bottom(self) -> int:
        """Coordinata Y del bordo inferiore sicuro."""
        if not self._safe_enabled:
            return self._screen_h
        return self._screen_h - max(self._base_margin_y(), self._cut_b)

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
        self._base_bg_display_scale = fit_scale * bg_scale

        # Dimensioni a schermo e posizione centrata (mapping BASE, senza camera)
        display_w = logical_w * fit_scale
        display_h = logical_h * fit_scale
        self._base_bg_screen_x = (self._screen_w - display_w) / 2
        self._base_bg_screen_y = (self._screen_h - display_h) / 2
        self._base_bg_screen_w = display_w
        self._base_bg_screen_h = display_h

        # Applica la camera corrente per ottenere il mapping effettivo.
        self._recompute_camera()

        log.debug(
            "Background %dx%d (scale=%.2f) → display %.0fx%.0f @ (%.0f, %.0f)",
            bg_w, bg_h, bg_scale, display_w, display_h,
            self._base_bg_screen_x, self._base_bg_screen_y,
        )

    def base_bg_screen_size(self) -> tuple[int, int]:
        """Dimensione del background a schermo SENZA camera (per la cache del BG)."""
        return int(round(self._base_bg_screen_w)), int(round(self._base_bg_screen_h))

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

    def screen_to_bg_scenic(self, sx: float, sy: float, factor: float) -> tuple[float, float]:
        """
        Coordinate schermo → coordinate background tenendo conto dello zoom scenico centrato.
        Usato per Hitbox durante l'intro zoom.
        """
        if factor == 1.0:
            return self.screen_to_bg(sx, sy)
            
        # 1. Inverti lo zoom centrato sullo schermo per tornare alle coordinate nominali
        cx, cy = self._screen_w / 2, self._screen_h / 2
        nsx = cx + (sx - cx) / factor
        nsy = cy + (sy - cy) / factor
        
        # 2. Usa la normale conversione screen_to_bg
        return self.screen_to_bg(nsx, nsy)

    def scale_bg_value(self, v: float) -> float:
        """Scala un valore scalare (raggio, dimensione) da bg-space a pixel schermo."""
        return v * self._bg_display_scale

    def screen_dist_to_bg(self, d_screen: float, scenic_factor: float = 1.0) -> float:
        """Converte una distanza in pixel schermo nell'equivalente in spazio
        background. Inverso di scale_bg_value, con eventuale zoom scenico.
        Usato per la tolleranza tap (fat-finger) del rilevamento oggetti."""
        denom = self._bg_display_scale * (scenic_factor if scenic_factor else 1.0)
        return d_screen / denom if denom else d_screen

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

    def _recompute_camera(self) -> None:
        """Ricalcola il mapping background→schermo EFFETTIVO applicando la camera
        (zoom attorno al centro schermo + pan) al mapping base. Clampa il pan in
        modo che il background copra sempre lo schermo quando è ingrandito, e resti
        centrato quando lo zoom è 1.0 (niente bande nere extra né scena alla deriva)."""
        z = self._zoom
        cx, cy = self._screen_w / 2.0, self._screen_h / 2.0

        bw = self._base_bg_screen_w * z
        bh = self._base_bg_screen_h * z
        # Posizione del top-left del bg con solo lo zoom (pan = 0)
        x0 = cx + (self._base_bg_screen_x - cx) * z
        y0 = cy + (self._base_bg_screen_y - cy) * z

        # Range ammesso per il top-left: se il bg è più grande dello schermo può
        # scorrere fino a mostrarne i bordi; altrimenti resta centrato.
        if bw >= self._screen_w:
            lo_x, hi_x = self._screen_w - bw, 0.0
        else:
            lo_x = hi_x = (self._screen_w - bw) / 2.0
        if bh >= self._screen_h:
            lo_y, hi_y = self._screen_h - bh, 0.0
        else:
            lo_y = hi_y = (self._screen_h - bh) / 2.0

        eff_x = min(hi_x, max(lo_x, x0 + self._pan_x))
        eff_y = min(hi_y, max(lo_y, y0 + self._pan_y))
        # Ri-normalizza il pan al valore clampato (così i delta successivi sono coerenti)
        self._pan_x = eff_x - x0
        self._pan_y = eff_y - y0

        self._bg_display_scale = self._base_bg_display_scale * z
        self._bg_screen_x = eff_x
        self._bg_screen_y = eff_y
        self._bg_screen_w = bw
        self._bg_screen_h = bh

    def set_pan(self, px: float, py: float) -> None:
        self._pan_x = px
        self._pan_y = py
        self._recompute_camera()

    def pan_by(self, dx: float, dy: float) -> None:
        """Trascina la scena di (dx, dy) pixel schermo (clamp ai bordi automatico)."""
        self._pan_x += dx
        self._pan_y += dy
        self._recompute_camera()

    def set_zoom(self, zoom: float) -> None:
        self._zoom = max(self._zoom_min, min(zoom, self._zoom_max))
        self._recompute_camera()

    def zoom_at(self, zoom: float, focus_x: float, focus_y: float) -> None:
        """Imposta lo zoom mantenendo fermo sotto le dita il punto schermo
        (focus_x, focus_y): è il comportamento naturale del pinch-to-zoom."""
        bgx, bgy = self.screen_to_bg(focus_x, focus_y)
        self._zoom = max(self._zoom_min, min(zoom, self._zoom_max))
        self._recompute_camera()
        # Sposta il pan per riportare il punto-mondo sotto al focus.
        nx, ny = self.bg_to_screen(bgx, bgy)
        self._pan_x += (focus_x - nx)
        self._pan_y += (focus_y - ny)
        self._recompute_camera()

    def is_zoomed(self) -> bool:
        return self._zoom > 1.001

    def reset_pan_zoom(self) -> None:
        self._pan_x = 0.0
        self._pan_y = 0.0
        self._zoom = 1.0
        self._recompute_camera()

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
