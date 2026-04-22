"""
engine/click_detector.py

Rilevamento click sugli oggetti nascosti.

Logica z-index:
  1. Raccoglie tutti gli oggetti non trovati la cui hit area contiene il punto
  2. Scarta oggetti su layer "overlay" (non interattivi)
  3. Ordina per layer_z decrescente (z più alto = in primo piano)
  4. Restituisce il primo (più in primo piano), o None se nessuno

Pipeline coordinate:
  screen -> scene (via ScalingManager.screen_to_scene)
"""

from __future__ import annotations

import math
from typing import Optional

import pygame

from engine.scene_loader import SceneObject
from engine.scaling_manager import ScalingManager
from engine.utils import get_logger

log = get_logger(__name__)


class ClickDetector:
    def __init__(self, scaling_manager: ScalingManager) -> None:
        self._sm = scaling_manager

    def detect(self,
               screen_x: int,
               screen_y: int,
               objects: list[SceneObject],
               background_scale: float = 1.0) -> Optional[SceneObject]:
        """
        Dato un click in coordinate schermo, restituisce l'oggetto colpito
        con la priorità z-index più alta, oppure None.

        Args:
            screen_x, screen_y: coordinate pixel del click
            objects:            lista di SceneObject attivi (non trovati)
            background_scale:   scala dello sfondo della scena corrente
        """
        # Converti coordinate schermo → coordinate background (spazio del file immagine)
        # Le coordinate JSON sono in pixel del background originale (es. 1920x1080)
        scene_x, scene_y = self._sm.screen_to_bg(screen_x, screen_y)

        candidates: list[SceneObject] = []

        for obj in objects:
            if obj.found:
                continue
            
            # Un oggetto è cliccabile se è un obiettivo DA TROVARE 
            # OPPURE se ha un minigioco associato.
            is_clickable = obj.is_goal or getattr(obj, "minigame_trigger", None) is not None
            
            if not is_clickable:
                continue
                
            if obj.layer == "overlay":
                continue
            if self._hit_test(obj, scene_x, scene_y):
                candidates.append(obj)

        if not candidates:
            return None

        # Ordine per z decrescente; a parità di z vince l'ordine nella lista (primo = precedenza)
        candidates.sort(key=lambda o: o.layer_z, reverse=True)
        hit = candidates[0]
        log.debug("Click (%.1f, %.1f) -> '%s' (z=%d)", scene_x, scene_y,
                  hit.instance_id, hit.layer_z)
        return hit

    # ------------------------------------------------------------------
    # Hit test per tipo
    # ------------------------------------------------------------------

    def _hit_test(self, obj: SceneObject, sx: float, sy: float) -> bool:
        match obj.detection_type:
            case "circle":
                return self._hit_circle(obj, sx, sy)
            case "rect":
                return self._hit_rect(obj, sx, sy)
            case "mask":
                return self._hit_mask(obj, sx, sy)
            case _:
                log.warning("detection_type sconosciuto: '%s'", obj.detection_type)
                return False

    def _hit_circle(self, obj: SceneObject, sx: float, sy: float) -> bool:
        # Se ha distorsione, usiamo il poligono come il rettangolo
        has_warp = any(c[0] != 0 or c[1] != 0 for c in obj.corners)
        if has_warp:
            w = obj.width if obj.width > 0 else obj.radius * 2
            h = obj.height if obj.height > 0 else obj.radius * 2
            x, y = obj.x - w/2, obj.y - h/2

            # Stessa logica del rettangolo: corners in scena space
            pts = [
                (x + obj.corners[0][0],   y + obj.corners[0][1]),
                (x + w + obj.corners[1][0], y + obj.corners[1][1]),
                (x + w + obj.corners[2][0], y + h + obj.corners[2][1]),
                (x + obj.corners[3][0],   y + h + obj.corners[3][1])
            ]

            # Applica FLIP ai punti se necessario
            if obj.flip_x or obj.flip_y:
                pts_flipped = []
                for px, py in pts:
                    if obj.flip_x:
                        px = 2 * obj.x - px  # Rifletti attorno al centro X
                    if obj.flip_y:
                        py = 2 * obj.y - py  # Rifletti attorno al centro Y
                    pts_flipped.append((px, py))
                pts = pts_flipped

            if obj.rotation != 0:
                pts = [self._rotate_point(p[0], p[1], obj.x, obj.y, obj.rotation) for p in pts]
            return self._is_point_in_poly(sx, sy, pts)

        # Recupera semi-assi x e y
        rx = obj.width / 2 if obj.width > 0 else obj.radius
        ry = obj.height / 2 if obj.height > 0 else obj.radius
        if rx <= 0: rx = 1.0
        if ry <= 0: ry = 1.0
            
        dx = sx - obj.x
        dy = sy - obj.y

        # Se ruotato, ruotiamo il punto di clic all'indietro
        if obj.rotation != 0:
            rad = math.radians(-obj.rotation)
            c, s = math.cos(rad), math.sin(rad)
            rdx = dx * c - dy * s
            rdy = dx * s + dy * c
            dx, dy = rdx, rdy

        # Test Ellisse: (dx/rx)^2 + (dy/ry)^2 <= 1
        return (dx/rx)**2 + (dy/ry)**2 <= 1.0001 # Small epsilon

    def _hit_rect(self, obj: SceneObject, sx: float, sy: float) -> bool:
        cx, cy = obj.x + obj.width / 2, obj.y + obj.height / 2

        # Se ha distorsione prospettica, usiamo il test del quadrilatero
        has_warp = any(c[0] != 0 or c[1] != 0 for c in obj.corners)

        if has_warp:
            # Calcoliamo i 4 punti del quadrilatero deformato in spazio scena
            # IMPORTANT: Applica lo STESSO scaling che usa il rendering in core.py
            w, h = obj.width, obj.height
            x, y = obj.x, obj.y

            # Punti base + offset corners (direttamente in scena space)
            pts = [
                (x + obj.corners[0][0],   y + obj.corners[0][1]),     # NW
                (x + w + obj.corners[1][0], y + obj.corners[1][1]),   # NE
                (x + w + obj.corners[2][0], y + h + obj.corners[2][1]), # SE
                (x + obj.corners[3][0],   y + h + obj.corners[3][1])    # SW
            ]

            # Applica FLIP ai punti se necessario (IMPORTANTE!)
            # Il flip deve essere applicato PRIMA della rotazione
            if obj.flip_x or obj.flip_y:
                pts_flipped = []
                for px, py in pts:
                    # Flip orizzontale: rifletti attorno alla linea verticale al centro
                    if obj.flip_x:
                        px = 2 * cx - px
                    # Flip verticale: rifletti attorno alla linea orizzontale al centro
                    if obj.flip_y:
                        py = 2 * cy - py
                    pts_flipped.append((px, py))
                pts = pts_flipped

            # Se ruotato, ruotiamo i 4 punti attorno al centro
            # (Lo stesso centro usato dall'editor e dal rendering: cx, cy)
            if obj.rotation != 0:
                pts = [self._rotate_point(p[0], p[1], cx, cy, obj.rotation) for p in pts]

            return self._is_point_in_poly(sx, sy, pts)

        # Logica standard per rettangolo/rettangolo ruotato
        if obj.rotation != 0:
            rx, ry = self._rotate_point(sx, sy, cx, cy, -obj.rotation)
        else:
            rx, ry = sx, sy

        half_w = obj.width / 2
        half_h = obj.height / 2
        return (cx - half_w <= rx <= cx + half_w and
                cy - half_h <= ry <= cy + half_h)

    @staticmethod
    def _is_point_in_poly(px: float, py: float, poly: list[tuple[float, float]]) -> bool:
        """Algoritmo Ray Casting per determinare se un punto è nel poligono."""
        n = len(poly)
        inside = False
        for i in range(n):
            j = (i + 1) % n
            xi, yi = poly[i]
            xj, yj = poly[j]
            intersect = ((yi > py) != (yj > py)) and \
                        (px < (xj - xi) * (py - yi) / (yj - yi) + xi)
            if intersect:
                inside = not inside
        return inside

    def _hit_mask(self, obj: SceneObject, sx: float, sy: float) -> bool:
        """
        Hit test pixel-perfect sulla mask.
        Supporta rotazione e flip.
        """
        if obj.mask_surface is None:
            est_r = max(obj.width, obj.height) / 2 if obj.width else 30.0
            dx = sx - obj.x
            dy = sy - obj.y
            return (dx * dx + dy * dy) <= (est_r * est_r)

        # 1. Rotazione inversa rispetto al centro
        if obj.rotation != 0:
            rx, ry = self._rotate_point(sx, sy, obj.x, obj.y, -obj.rotation)
        else:
            rx, ry = sx, sy

        # 2. Coordinate relative all'angolo top-left (assumendo x,y come centro)
        # Nota: core.py renderizza le icone centrate su x,y. 
        # Assumiamo che la mask segua la stessa logica.
        mask_w_full = obj.mask_surface.get_width() * obj.mask_scale_x
        mask_h_full = obj.mask_surface.get_height() * obj.mask_scale_y
        
        local_x = rx - (obj.x - mask_w_full / 2)
        local_y = ry - (obj.y - mask_h_full / 2)

        if not (0 <= local_x < mask_w_full and 0 <= local_y < mask_h_full):
            return False

        # 3. Scala inversa
        px = int(local_x / obj.mask_scale_x)
        py = int(local_y / obj.mask_scale_y)
        
        # 4. Applica flip inverso alle coordinate pixel
        if obj.flip_x:
            px = obj.mask_surface.get_width() - 1 - px
        if obj.flip_y:
            py = obj.mask_surface.get_height() - 1 - py

        px = max(0, min(px, obj.mask_surface.get_width() - 1))
        py = max(0, min(py, obj.mask_surface.get_height() - 1))

        try:
            pixel = obj.mask_surface.get_at((px, py))
            return pixel.a > 128
        except IndexError:
            return False

    @staticmethod
    def _rotate_point(px: float, py: float, cx: float, cy: float, angle_deg: float) -> tuple[float, float]:
        """Ruota un punto (px, py) attorno a (cx, cy) di angle_deg gradi (CCW Pygame)."""
        rad = math.radians(angle_deg)
        cos_a = math.cos(rad)
        sin_a = math.sin(rad)
        
        # Trasla al centro
        tx, ty = px - cx, py - cy
        
        # Ruota
        nx = tx * cos_a - ty * sin_a
        ny = tx * sin_a + ty * cos_a
        
        # Trasla indietro
        return nx + cx, ny + cy
