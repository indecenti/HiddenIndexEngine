"""
engine/effects_engine.py

Sistema particellare e di animazione per il feedback visuale sugli oggetti.
"""
import pygame
import random
import math

class Particle:
    def __init__(self, x: float, y: float, color: tuple[int,int,int], dx: float, dy: float, life: float) -> None:
        self.x = x
        self.y = y
        self.color = color
        self.dx = dx
        self.dy = dy
        self.life = life
        self.max_life = life

class ScorePopup:
    def __init__(self, x: float, y: float, text: str, color: tuple[int,int,int], life: float = 1.5) -> None:
        self.x = x
        self.y = y
        self.text = text
        self.color = color
        self.life = life
        self.max_life = life
        self.vel_y = -80.0  # Velocità di ascesa iniziale
        self.vel_x = random.uniform(-20.0, 20.0) # Leggera deriva orizzontale
        self.scale = 1.0

class EffectsEngine:
    """Disegna effetti e popup rispettando le coordinate virtuali di scaling."""
    def __init__(self, scaling_manager) -> None:
        self.scaling_manager = scaling_manager
        self.particles: list[Particle] = []
        self.popups: list[ScorePopup] = []
        
        # Cache per i font per evitare ricaricamenti continui
        self._font_cache = {}

        # Screen Shake state
        self.shake_duration = 0.0
        self.shake_intensity = 0.0
        self.shake_offset = [0.0, 0.0]
        self._shake_original_duration = 0.3
        
    def _get_font(self, size: int) -> pygame.font.Font:
        if size not in self._font_cache:
            # Font di sistema che ricorda un fumetto (Segoe UI Black o Impact)
            try:
                self._font_cache[size] = pygame.font.SysFont("impact", size)
            except:
                self._font_cache[size] = pygame.font.SysFont("arial", size, bold=True)
        return self._font_cache[size]

    def spawn_score_popup(self, ref_x: float, ref_y: float, penalty: int) -> None:
        """Crea un popup testuale con colore dinamico basato sulla penalità."""
        val = abs(penalty)
        text = str(penalty)
        
        # Mappatura colori richiesta:
        if val <= 25:
            color = (255, 255, 80)   # Giallo Brillante
        elif val <= 50:
            color = (255, 210, 0)    # Giallo-Arancio
        elif val <= 100:
            color = (255, 160, 0)    # Arancio
        elif val <= 150:
            color = (255, 100, 40)   # Arancio-Rosso
        elif val <= 300:
            color = (255, 50, 50)    # Rosso
        else:
            color = (255, 0, 0)      # Rosso Acceso
            
        self.popups.append(ScorePopup(ref_x, ref_y, text, color))
        
        # Effetto particellare extra se la penalità è pesante (>= 500)
        if val >= 500:
            self.spawn_heavy_miss_effect(ref_x, ref_y)

    def spawn_heavy_miss_effect(self, ref_x: float, ref_y: float) -> None:
        """Esplosione di particelle rosso scuro per penalità gravi."""
        for _ in range(40):
            angle = random.uniform(0, math.pi * 2)
            speed = random.uniform(30, 150)
            dx = math.cos(angle) * speed
            dy = math.sin(angle) * speed
            color = (random.randint(100, 150), 0, 0) # Rosso scuro "sangue"
            self.particles.append(Particle(ref_x, ref_y, color, dx, dy, life=1.5))

    def spawn_found_effect(self, ref_x: float, ref_y: float) -> None:
        """Esplosione aurea al raggiungimento e al click di un oggetto corretto."""
        for _ in range(25):
            angle = random.uniform(0, math.pi * 2)
            speed = random.uniform(80, 200)
            dx = math.cos(angle) * speed
            dy = math.sin(angle) * speed
            color = (255, random.randint(200, 255), 50)
            self.particles.append(Particle(ref_x, ref_y, color, dx, dy, life=1.2))

    def spawn_final_found_effect(self, ref_x: float, ref_y: float) -> None:
        """Esplosione epica ed enorme quando l'ultimo oggetto del livello viene trovato."""
        for _ in range(80):
            angle = random.uniform(0, math.pi * 2)
            speed = random.uniform(150, 600)
            dx = math.cos(angle) * speed
            dy = math.sin(angle) * speed
            color = (255, random.randint(230, 255), random.randint(150, 255))
            self.particles.append(Particle(ref_x, ref_y, color, dx, dy, life=2.2))
            
        for _ in range(50):
            angle = random.uniform(0, math.pi * 2)
            speed = random.uniform(250, 450)
            dx = math.cos(angle) * speed
            dy = math.sin(angle) * speed
            color = (150, 255, 255)
            self.particles.append(Particle(ref_x, ref_y, color, dx, dy, life=1.5))

    def spawn_miss_effect(self, ref_x: float, ref_y: float) -> None:
        """Esplosione rossa al click errato."""
        for _ in range(15):
            angle = random.uniform(0, math.pi * 2)
            speed = random.uniform(50, 120)
            dx = math.cos(angle) * speed
            dy = math.sin(angle) * speed
            color = (random.randint(200, 255), 30, 30)
            self.particles.append(Particle(ref_x, ref_y, color, dx, dy, life=0.8))

    def spawn_hint_effect(self, ref_x: float, ref_y: float) -> None:
        """Effetto ciano/blu per hint."""
        for _ in range(30):
            angle = random.uniform(0, math.pi * 2)
            speed = random.uniform(80, 180)
            dx = math.cos(angle) * speed
            dy = math.sin(angle) * speed
            color = (100, random.randint(180, 255), 255)
            self.particles.append(Particle(ref_x, ref_y, color, dx, dy, life=1.2))

    def shake_screen(self, duration: float = 0.3, intensity: float = 8.0) -> None:
        """Attiva una vibrazione della camera."""
        self.shake_duration = duration
        self.shake_intensity = intensity
        self._shake_original_duration = duration

    def update(self, dt: float) -> None:
        """Avanzamento ciclico fisico delle particelle e dei popup."""
        # Update Particelle
        alive_p = []
        for p in self.particles:
            p.x += p.dx * dt
            p.y += p.dy * dt
            p.life -= dt
            if p.life > 0:
                alive_p.append(p)
        self.particles = alive_p

        # Update Popups (Floating text)
        alive_pop = []
        for pop in self.popups:
            pop.life -= dt
            # Accelerazione negativa sulla Y per smorzare l'ascesa (effetto "pop")
            pop.vel_y *= 0.95 
            pop.x += pop.vel_x * dt
            pop.y += pop.vel_y * dt
            # Effetto pulsazione iniziale
            pop.scale = 1.0 + math.sin((1.0 - pop.life/pop.max_life) * 10) * 0.1
            
            if pop.life > 0:
                alive_pop.append(pop)
        self.popups = alive_pop
        
        # Update Shake
        if self.shake_duration > 0:
            self.shake_duration -= dt
            progress = self.shake_duration / self._shake_original_duration if self._shake_original_duration > 0 else 0
            current_int = self.shake_intensity * progress
            self.shake_offset = [
                random.uniform(-current_int, current_int),
                random.uniform(-current_int, current_int)
            ]
        else:
            self.shake_offset = [0.0, 0.0]

    def draw(self, screen: pygame.Surface) -> None:
        """Disegna particelle e popups."""
        # 1. Disegna Particelle
        for p in self.particles:
            progress = p.life / p.max_life
            radius = max(2, int(self.scaling_manager.scale_bg_value(10) * progress))
            sx, sy = self.scaling_manager.bg_to_screen(p.x, p.y)
            pygame.draw.circle(screen, p.color, (int(sx), int(sy)), radius)

        # 2. Disegna Popups (Stile Fumetto)
        for pop in self.popups:
            progress = pop.life / pop.max_life
            alpha = int(255 * min(1.0, progress * 2)) # Fade out negli ultimi 50% di vita
            
            # Calcola dimensione font scalata
            font_size = int(self.scaling_manager.scale_value(32) * pop.scale)
            if font_size < 10: continue
            
            font = self._get_font(font_size)
            sx, sy = self.scaling_manager.bg_to_screen(pop.x, pop.y)
            
            # Rendering con bordo nero (stile fumetto)
            # Disegniamo il testo nero in 8 direzioni per creare un contorno solido
            offsets = [(-2, -2), (2, -2), (-2, 2), (2, 2), (0, -2), (0, 2), (-2, 0), (2, 0)]
            for ox, oy in offsets:
                outline_surf = font.render(pop.text, True, (10, 10, 20))
                outline_surf.set_alpha(alpha)
                screen.blit(outline_surf, (sx + ox - outline_surf.get_width()//2, sy + oy - outline_surf.get_height()//2))
            
            # Rendering testo principale (Rosso)
            main_surf = font.render(pop.text, True, pop.color)
            main_surf.set_alpha(alpha)
            screen.blit(main_surf, (sx - main_surf.get_width()//2, sy - main_surf.get_height()//2))
