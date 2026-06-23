"""
engine/transition_manager.py

Gestisce le transizioni visive e le dissolvenze (fade-to-black, slide, flash).
Riceve delta-time e renderizza effetti full-screen su una Surface ausiliaria.
"""

import pygame
import math
from typing import Callable, Optional

from engine.utils import get_logger, is_android_runtime

# Su GPU mobile/software gli overlay SRCALPHA fullscreen per-frame e la CIRCLE_BURST
# (cerchi enormi + particelle) sono molto cari: degradiamo/ottimizziamo su Android.
_ANDROID = is_android_runtime()


class TransitionType:
    FADE_TO_BLACK = "fade"
    SLIDE_LEFT = "slide_left"
    SLIDE_RIGHT = "slide_right"
    RIPPLE = "ripple"
    FLASH = "flash"

    CIRCLE_BURST = "circle_burst"

class TransitionState:
    IDLE = 0
    OUT = 1 # Fase in cui lo schermo si oscura
    IN = 2  # Fase in cui lo schermo torna visibile

class TransitionManager:
    """Gestisce l'esportazione video tra schermate e l'offuscamento dell'engine."""
    
    def __init__(self, reduced_animations: bool = False) -> None:
        self.logger = get_logger(__name__)
        self.reduced_animations: bool = reduced_animations
        
        self.state: int = TransitionState.IDLE
        self.trans_type: str = TransitionType.FADE_TO_BLACK
        self.progress: float = 0.0
        self.duration_out: float = 0.0
        self.duration_in: float = 0.0
        
        # Coordinate opzionali per effetti di burst
        self.cx: int = 0
        self.cy: int = 0
        
        # Callback in esecuzione a schermo completamente nero (midpoint) e a fine evento
        self.on_midpoint_callback: Optional[Callable[[], None]] = None
        self.on_complete_callback: Optional[Callable[[], None]] = None
        
        self._overlay_surface: Optional[pygame.Surface] = None
        self._solid_cache: dict = {}

    def _get_solid(self, w: int, h: int, rgb: tuple) -> pygame.Surface:
        """Surface OPACA cachata di un colore. Per i fade usiamo opaco + set_alpha
        (alpha di superficie) invece di una Surface SRCALPHA riempita e blittata
        per-pixel ogni frame: molto piu' veloce su GPU mobile."""
        key = (w, h, rgb)
        s = self._solid_cache.get(key)
        if s is None:
            s = pygame.Surface((w, h)).convert()
            s.fill(rgb)
            self._solid_cache[key] = s
        return s

    def _get_overlay(self, w: int, h: int) -> pygame.Surface:
        """Inizializza una surface proxy hardware con trasparenza per i fade."""
        if self._overlay_surface is None or self._overlay_surface.get_size() != (w, h):
            self._overlay_surface = pygame.Surface((w, h), pygame.SRCALPHA)
            self._overlay_surface = self._overlay_surface.convert_alpha()
        return self._overlay_surface

    def start_transition(
        self, 
        t_type: str, 
        base_dur_out: float = 0.4, 
        base_dur_in: float = 0.4,
        on_midpoint: Optional[Callable[[], None]] = None,
        on_complete: Optional[Callable[[], None]] = None,
        cx: int = -1,
        cy: int = -1
    ) -> None:
        """Avvia animazione gestendo anche riduzioni di framerate."""
        if self.state != TransitionState.IDLE:
             self.logger.warning("Richiesta transizione ignorata: evento engine in corso.")
             return

        # Su Android la CIRCLE_BURST (4 cerchi grandi quanto ~1.5x lo schermo + 40
        # particelle su una Surface SRCALPHA fullscreen, OGNI frame, con la scena ancora
        # disegnata dietro) fa crollare gli FPS all'apertura dei minigiochi. La
        # degradiamo a un fade semplice, mantenendo lo stesso timing/callback.
        if _ANDROID and t_type == TransitionType.CIRCLE_BURST:
            t_type = TransitionType.FADE_TO_BLACK

        self.trans_type = t_type
        # Se richiesto nelle config globali si dimezzano i framerate d'azione
        multiplier = 0.5 if self.reduced_animations else 1.0
        self.duration_out = max(base_dur_out * multiplier, 0.01)
        self.duration_in = max(base_dur_in * multiplier, 0.01)
        
        # Se non passati, usa il centro schermo (verrà calcolato in draw o se necessario qui)
        self.cx = cx
        self.cy = cy

        # Inizializza particelle per effetti cinematografici burst
        self.particles = []
        if t_type == TransitionType.CIRCLE_BURST:
            import random
            for _ in range(40):
                angle = random.uniform(0, 6.28)
                speed = random.uniform(200, 800)
                self.particles.append({
                    "pos": [0, 0], # Verranno settate in draw rispetto a cx, cy
                    "vel": [math.cos(angle) * speed, math.sin(angle) * speed],
                    "color": random.choice([(255, 255, 255), (0, 255, 255), (255, 0, 150)]),
                    "size": random.randint(2, 6)
                })

        # Fallback a Fade To Black per Ripple se le animazioni ridotte sono attive
        if self.reduced_animations and self.trans_type == TransitionType.RIPPLE:
            self.trans_type = TransitionType.FADE_TO_BLACK

        self.on_midpoint_callback = on_midpoint
        self.on_complete_callback = on_complete
        
        self.progress = 0.0
        self.state = TransitionState.OUT
        self.logger.debug(f"Avviata Transizione: {self.trans_type} (OUT:{self.duration_out}s, IN:{self.duration_in}s)")

    def update(self, dt: float) -> None:
        """Da richiamare ogni loop dell'engine per avanzare i timer."""
        if self.state == TransitionState.IDLE:
            return
            
        if self.state == TransitionState.OUT:
            self.progress += (dt / self.duration_out)
            if self.progress >= 1.0:
                self.progress = 1.0
                if self.on_midpoint_callback:
                    self.on_midpoint_callback()
                    
                self.state = TransitionState.IN
                self.progress = 0.0 # reset per IN
                
        elif self.state == TransitionState.IN:
            self.progress += (dt / self.duration_in)
            if self.progress >= 1.0:
                self.progress = 1.0
                if self.on_complete_callback:
                    self.on_complete_callback()
                self.state = TransitionState.IDLE

    def draw(self, screen: pygame.Surface) -> None:
        """Dipingi l'overlay appropriato on-screen."""
        if self.state == TransitionState.IDLE:
            return
            
        w, h = screen.get_size()
        cx = self.cx if self.cx >= 0 else w // 2
        cy = self.cy if self.cy >= 0 else h // 2
        
        if self.trans_type in (TransitionType.FADE_TO_BLACK, TransitionType.RIPPLE):
            alpha = self.progress if self.state == TransitionState.OUT else (1.0 - self.progress)
            s = self._get_solid(w, h, (0, 0, 0))
            s.set_alpha(int(alpha * 255))
            screen.blit(s, (0, 0))

        elif self.trans_type == TransitionType.FLASH:
            alpha = self.progress if self.state == TransitionState.OUT else (1.0 - self.progress)
            s = self._get_solid(w, h, (255, 255, 255))
            s.set_alpha(int(alpha * 255))
            screen.blit(s, (0, 0))

        elif self.trans_type == TransitionType.CIRCLE_BURST:
            overlay = self._get_overlay(w, h)
            overlay.fill((0,0,0,0))
            
            if self.state == TransitionState.OUT:
                # 1. Anelli multipli con ritardo (Effetto Hyperspace)
                # Colori: Bianco, Ciano, Magenta, Oro
                colors = [(255, 255, 255, 255), (0, 255, 255, 180), (255, 0, 150, 120), (255, 200, 0, 80)]
                max_r = max(w, h) * 1.5
                
                # Disegna anelli concentrici (dal più esterno al più interno)
                for i in range(len(colors)-1, -1, -1):
                    # Ogni anello parte con un piccolo ritardo basato sull'indice
                    p_ring = max(0.0, self.progress * 1.2 - (i * 0.15))
                    p_ring = min(1.0, p_ring)
                    if p_ring <= 0: continue
                    
                    r = int(p_ring * max_r)
                    col = colors[i]
                    pygame.draw.circle(overlay, col, (cx, cy), r)
                
                # 2. Particelle "Scintille" che seguono l'esplosione
                for part in self.particles:
                    # Movimento radiale accelerato
                    dist_factor = self.progress * self.progress * 2.0
                    px = cx + part["vel"][0] * dist_factor * 2.5
                    py = cy + part["vel"][1] * dist_factor * 2.5
                    
                    # Sfumatura colore particella verso il bianco al centro
                    alpha = int(max(0, 1.0 - self.progress) * 255)
                    p_col = (*part["color"], alpha)
                    
                    # Disegna la "testa" della scintilla e una scia verso il centro
                    start_pt = (int(px), int(py))
                    end_pt = (int(cx + (px-cx)*0.8), int(cy + (py-cy)*0.8))
                    pygame.draw.line(overlay, p_col, start_pt, end_pt, part["size"])
                    pygame.draw.circle(overlay, p_col, start_pt, part["size"])

            else:
                # Transizione IN: Sfumatura dal bianco puro (Glitch/Flash)
                alpha = int((1.0 - self.progress) * 255)
                overlay.fill((255, 255, 255, alpha))
            
            screen.blit(overlay, (0, 0))
            
        elif self.trans_type in (TransitionType.SLIDE_LEFT, TransitionType.SLIDE_RIGHT):
            # Crea un rettangolo nero che slitta fisicamente
            if self.state == TransitionState.OUT:
                offset_x = int(w * (1.0 - self.progress)) if self.trans_type == TransitionType.SLIDE_LEFT else int(-w * (1.0 - self.progress))
                pygame.draw.rect(screen, (0, 0, 0), (offset_x, 0, w, h))
            elif self.state == TransitionState.IN:
                offset_x = int(-w * self.progress) if self.trans_type == TransitionType.SLIDE_LEFT else int(w * self.progress)
                pygame.draw.rect(screen, (0, 0, 0), (offset_x, 0, w, h))
