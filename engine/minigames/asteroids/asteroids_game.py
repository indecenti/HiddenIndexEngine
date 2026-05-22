import pygame
import random
import math
import logging
from pathlib import Path
from typing import List, Optional, Tuple

from engine.minigames.minigame_base import BaseMinigame
from engine.minigames.asteroids import asteroids_config as cfg
from engine.minigames.touch_controls import TouchControls
from engine.utils import get_resource_path, is_android_runtime

log = logging.getLogger(__name__)

# Template Asteroidi Originali (Normalizzati a raggio 1.0)
ASTEROID_TEMPLATES = [
    [pygame.Vector2(0.5, -1.0), pygame.Vector2(1.0, -0.5), pygame.Vector2(1.0, 0.2), 
     pygame.Vector2(0.3, 1.0), pygame.Vector2(-0.3, 1.0), pygame.Vector2(-1.0, 0.5), 
     pygame.Vector2(-1.0, -0.2), pygame.Vector2(-0.5, -1.0)],
    
    [pygame.Vector2(1.0, -0.3), pygame.Vector2(1.0, 0.3), pygame.Vector2(0.5, 1.0), 
     pygame.Vector2(-0.2, 1.0), pygame.Vector2(-1.0, 0.3), pygame.Vector2(-1.0, -0.3), 
     pygame.Vector2(-0.5, -1.0), pygame.Vector2(0.2, -1.0)],
     
    [pygame.Vector2(1.0, -0.5), pygame.Vector2(0.5, 0.2), pygame.Vector2(1.0, 0.5), 
     pygame.Vector2(0.3, 1.0), pygame.Vector2(-0.2, 0.5), pygame.Vector2(-1.0, 1.0), 
     pygame.Vector2(-1.0, -0.5), pygame.Vector2(-0.5, -1.0), pygame.Vector2(0.2, -0.5)],
     
    [pygame.Vector2(1.0, -0.5), pygame.Vector2(1.0, 0.5), pygame.Vector2(0.2, 0.3), 
     pygame.Vector2(0.5, 1.0), pygame.Vector2(-0.5, 1.0), pygame.Vector2(-0.2, 0.5), 
     pygame.Vector2(-1.0, 0.5), pygame.Vector2(-1.0, -0.5), pygame.Vector2(-0.5, -1.0), 
     pygame.Vector2(0.5, -0.3)]
]

class Entity:
    """Classe base per tutti gli oggetti in gioco."""
    def __init__(self, pos: pygame.Vector2, vel: pygame.Vector2, radius: float):
        self.pos = pygame.Vector2(pos)
        self.vel = pygame.Vector2(vel)
        self.radius = radius
        self.angle = 0.0
        self.is_dead = False

    def update(self, dt: float):
        self.pos += self.vel * dt
        # Wrap around
        self.pos.x %= cfg.REF_W
        self.pos.y %= cfg.REF_H

    def collides_with(self, other: 'Entity') -> bool:
        dist = self.pos.distance_to(other.pos)
        return dist < (self.radius + other.radius)

class Asteroid(Entity):
    def __init__(self, pos: pygame.Vector2, size: int):
        # size: 3=Large, 2=Medium, 1=Small
        self.size = size
        if size == 3:
            radius = cfg.ASTER_LARGE_RADIUS
            speed_range = cfg.ASTER_LARGE_SPEED
        elif size == 2:
            radius = cfg.ASTER_MEDIUM_RADIUS
            speed_range = cfg.ASTER_MEDIUM_SPEED
        else:
            radius = cfg.ASTER_SMALL_RADIUS
            speed_range = cfg.ASTER_SMALL_SPEED

        angle = random.uniform(0, math.pi * 2)
        speed = random.uniform(*speed_range)
        vel = pygame.Vector2(math.cos(angle), math.sin(angle)) * speed
        
        super().__init__(pos, vel, radius)
        
        if size == 3: self.points = cfg.ASTER_LARGE_POINTS
        elif size == 2: self.points = cfg.ASTER_MEDIUM_POINTS
        else: self.points = cfg.ASTER_SMALL_POINTS

        # Scegli un template originale e applica lo scale
        template = random.choice(ASTEROID_TEMPLATES)
        self.poly = [p * self.radius for p in template]
        
        # Aggiungi una leggera variazione per non averli identici
        for p in self.poly:
            p.x += random.uniform(-self.radius*0.1, self.radius*0.1)
            p.y += random.uniform(-self.radius*0.1, self.radius*0.1)

class Bullet(Entity):
    def __init__(self, pos: pygame.Vector2, angle: float, owner: str = "ship"):
        vel = pygame.Vector2(math.cos(math.radians(angle)), 
                             math.sin(math.radians(angle))) * cfg.BULLET_SPEED
        super().__init__(pos, vel, 2)
        self.life = cfg.BULLET_LIFETIME
        self.owner = owner

    def update(self, dt: float):
        super().update(dt)
        self.life -= dt
        if self.life <= 0:
            self.is_dead = True

class Ufo(Entity):
    def __init__(self, size: int):
        # 2 = Big, 1 = Small
        self.size = size
        y = random.uniform(50, cfg.REF_H - 50)
        side = random.choice([-1, 1])
        x = 0 if side == 1 else cfg.REF_W
        speed = 150 if size == 2 else 250
        vel = pygame.Vector2(side * speed, 0)
        
        radius = 20 if size == 2 else 10
        super().__init__(pygame.Vector2(x, y), vel, radius)
        
        self.points = cfg.UFO_BIG_POINTS if size == 2 else cfg.UFO_SMALL_POINTS
        self.fire_timer = random.uniform(1.0, 2.0)
        self.dir_timer = random.uniform(1.0, 3.0)
        
        self.poly = [
            pygame.Vector2(-15, 0), pygame.Vector2(-5, -5), 
            pygame.Vector2(5, -5), pygame.Vector2(15, 0),
            pygame.Vector2(5, 5), pygame.Vector2(-5, 5),
            pygame.Vector2(-15, 0), pygame.Vector2(-5, 10),
            pygame.Vector2(5, 10), pygame.Vector2(15, 0)
        ] if size == 2 else [
            pygame.Vector2(-8, 0), pygame.Vector2(-3, -3), 
            pygame.Vector2(3, -3), pygame.Vector2(8, 0),
            pygame.Vector2(3, 3), pygame.Vector2(-3, 3),
            pygame.Vector2(-8, 0), pygame.Vector2(-3, 5),
            pygame.Vector2(3, 5), pygame.Vector2(8, 0)
        ]

    def update(self, dt: float):
        self.pos += self.vel * dt
        # UFOs don't wrap in Y, but can leave in X
        if self.pos.x < -50 or self.pos.x > cfg.REF_W + 50:
            self.is_dead = True
        
        # Change direction occasionally
        self.dir_timer -= dt
        if self.dir_timer <= 0:
            self.dir_timer = random.uniform(1, 4)
            self.vel.y = random.choice([-1, 0, 1]) * 100

    def get_shot_angle(self, ship_pos: Optional[pygame.Vector2], score: int) -> float:
        if self.size == 2 or not ship_pos:
            return random.uniform(0, 360)
        else:
            # Small UFO mira al giocatore. La precisione aumenta col punteggio.
            target_vec = ship_pos - self.pos
            angle = math.degrees(math.atan2(target_vec.y, target_vec.x))
            
            # Errore decrescente: da 40 gradi a quasi 0 a 40000 punti
            error_range = max(2, 40 - (score / 1000))
            error = random.uniform(-error_range, error_range)
            return angle + error

class Fragment(Entity):
    def __init__(self, pos: pygame.Vector2, vel: pygame.Vector2):
        super().__init__(pos, vel, 0)
        self.points = [pygame.Vector2(-5, 0), pygame.Vector2(5, 0)]
        self.angle = random.uniform(0, 360)
        self.rot_speed = random.uniform(-200, 200)
        self.life = 1.0

    def update(self, dt: float):
        super().update(dt)
        self.angle += self.rot_speed * dt
        self.life -= dt
        if self.life <= 0:
            self.is_dead = True

class Particle(Entity):
    def __init__(self, pos: pygame.Vector2, vel: pygame.Vector2):
        super().__init__(pos, vel, 1)
        self.life = random.uniform(0.3, 0.6)

    def update(self, dt: float):
        super().update(dt)
        self.life -= dt
        if self.life <= 0:
            self.is_dead = True

class Ship(Entity):
    def __init__(self):
        pos = pygame.Vector2(cfg.REF_W / 2, cfg.REF_H / 2)
        super().__init__(pos, pygame.Vector2(0, 0), cfg.SHIP_RADIUS)
        self.angle = -90.0  # Punta verso l'alto
        self.thrusting = False
        self.invulnerable_timer = cfg.SHIP_INVULNERABLE_TIME
        self.poly = [
            pygame.Vector2(20, 0),
            pygame.Vector2(-15, 12),
            pygame.Vector2(-10, 0),
            pygame.Vector2(-15, -12)
        ]
        self.flame_poly = [
            pygame.Vector2(-10, 0),
            pygame.Vector2(-18, 5),
            pygame.Vector2(-25, 0),
            pygame.Vector2(-18, -5)
        ]

    def rotate(self, direction: float, dt: float):
        self.angle += direction * cfg.SHIP_ROT_SPEED * dt

    def thrust(self, dt: float):
        accel = pygame.Vector2(math.cos(math.radians(self.angle)), 
                               math.sin(math.radians(self.angle))) * cfg.SHIP_THRUST
        self.vel += accel * dt
        if self.vel.length() > cfg.SHIP_MAX_SPEED:
            self.vel.scale_to_length(cfg.SHIP_MAX_SPEED)

    def update(self, dt: float):
        super().update(dt)
        self.vel *= cfg.SHIP_DRAG
        if self.invulnerable_timer > 0:
            self.invulnerable_timer -= dt

class AsteroidsGame(BaseMinigame):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.game_path = get_resource_path("engine", "minigames", "asteroids")
        self.load_local_strings(self.game_path / "strings")

        self.ship: Optional[Ship] = None
        self.asteroids: List[Asteroid] = []
        self.bullets: List[Bullet] = []
        self.ufos: List[Ufo] = []
        self.fragments: List[Fragment] = []
        self.particles: List[Particle] = []
        
        self.score = 0
        self.last_extra_life_score = 0
        self.lives = cfg.INITIAL_LIVES
        self.level = 0
        self.phase = "START" # START, PLAY, DYING, GAMEOVER
        
        self.state_timer = 0.0
        self.beat_timer = 1.0
        self.beat_state = 0
        self.ufo_timer = cfg.UFO_MIN_INTERVAL
        self.thrust_sfx_timer = 0.0
        
        self.scanline_surf = None
        self.flicker_timer = 0.0
        
        # Tracking Mouse
        self.last_mouse_pos = pygame.mouse.get_pos()
        self.using_mouse = False
        self.mouse_fire_timer = 0.0
        
        self.font_main = None
        self.font_score = None

    def start(self) -> None:
        self.score = 0
        self.lives = cfg.INITIAL_LIVES
        self.level = 0
        self.phase = "START"
        self.bullets = []
        self.particles = []
        self.fragments = []
        self.ufos = []
        self.last_extra_life_score = 0
        self._spawn_level()
        self._prepare_fonts()
        self._setup_fx_surfaces()
        # Su Android NON mostrare il cursore (nessun puntatore a schermo).
        if not is_android_runtime():
            pygame.mouse.set_visible(True)
        # Controlli touch: bottone SPINTA (toggle). Mira e fuoco restano sul
        # tocco nell'area di gioco (tocca per puntare e sparare).
        self.touch = TouchControls(self.scaling_manager)
        self.touch_thrust = False
        self._setup_touch()

    def _setup_touch(self) -> None:
        if not hasattr(self, "touch"):
            return
        self.touch.clear()
        if not self.touch.enabled:
            return
        sw, sh = self.screen.get_size()
        b = max(56, int(min(sw, sh) * 0.16))
        m = int(b * 0.3)
        self.touch.add("thrust", pygame.Rect(m, sh - m - b, b, b),
                       glyph="up", color=(120, 255, 170))

    def on_resize(self) -> None:
        self._setup_touch()

    def _prepare_fonts(self):
        # Carica un font monospazio o arcade se disponibile, altrimenti sistema
        self.font_main = pygame.font.SysFont("Courier New", self.scaling_manager.scale_value(40), bold=True)
        self.font_score = pygame.font.SysFont("Courier New", self.scaling_manager.scale_value(25))

    def _spawn_level(self):
        self.level += 1
        num_asteroids = 4 + self.level
        self.asteroids = []
        for _ in range(num_asteroids):
            # Spawn lontano dal centro
            while True:
                pos = pygame.Vector2(random.uniform(0, cfg.REF_W), random.uniform(0, cfg.REF_H))
                if pos.distance_to(pygame.Vector2(cfg.REF_W/2, cfg.REF_H/2)) > 200:
                    break
            self.asteroids.append(Asteroid(pos, 3))

    def _spawn_ship(self):
        self.ship = Ship()

    def handle_event(self, event: pygame.event.Event) -> None:
        if self.phase == "START":
            if event.type in (pygame.KEYDOWN, pygame.MOUSEBUTTONDOWN):
                self.phase = "PLAY"
                self._spawn_ship()
                return

        if self.phase == "GAMEOVER":
            if event.type in (pygame.KEYDOWN, pygame.MOUSEBUTTONDOWN):
                self.finish({"success": self.score > 0, "score": self.score})
            return

        if self.phase == "PLAY" and self.ship:
            # Bottone touch SPINTA (toggle on/off)
            if self.touch.handle_event(event) == "thrust":
                self.touch_thrust = not self.touch_thrust
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_SPACE:
                    self._fire_bullet()
                elif event.key == pygame.K_h:
                    self._hyperspace()

    def _fire_bullet(self, pos: Optional[pygame.Vector2] = None, 
                     angle: float = 0, owner: str = "ship"):
        if owner == "ship":
            if not self.ship or len([b for b in self.bullets if b.owner == "ship"]) >= cfg.BULLET_MAX:
                return
            tip = self.ship.pos + pygame.Vector2(math.cos(math.radians(self.ship.angle)), 
                                                 math.sin(math.radians(self.ship.angle))) * 20
            self.bullets.append(Bullet(tip, self.ship.angle, owner))
            self._play_sfx(cfg.SND_FIRE)
        else:
            # UFO bullet
            self.bullets.append(Bullet(pos, angle, owner))

    def _hyperspace(self):
        if not self.ship: return
        self.ship.pos = pygame.Vector2(random.uniform(0, cfg.REF_W), random.uniform(0, cfg.REF_H))
        self.ship.vel = pygame.Vector2(0, 0)
        # 10% di probabilità di esplodere all'uscita (come l'originale)
        if random.random() < 0.1:
            self._handle_ship_death()

    def update(self, dt: float) -> None:
        # Cap delta time per evitare esplosioni di coordinate in caso di lag
        dt = min(dt, 0.05)
        # Aggiorniamo sempre proiettili, particelle e frammenti per evitare "fantasmi"
        for b in self.bullets[:]:
            b.update(dt)
            if b.is_dead: self.bullets.remove(b)

        for f in self.fragments[:]:
            f.update(dt)
            if f.is_dead: self.fragments.remove(f)

        for p in self.particles[:]:
            p.update(dt)
            if p.is_dead: self.particles.remove(p)

        if self.phase == "PLAY":
            self._update_play(dt)
        elif self.phase in ("DYING", "START", "GAMEOVER"):
            self.state_timer -= dt
            # Gli asteroidi e UFO continuano a muoversi nello sfondo
            for a in self.asteroids: a.update(dt)
            for u in self.ufos[:]: 
                u.update(dt)
                if u.is_dead: self.ufos.remove(u)
            
            if self.phase == "DYING" and self.state_timer <= 0:
                if self.lives > 0:
                    self.phase = "PLAY"
                    self._spawn_ship()
                else:
                    self.phase = "GAMEOVER"
                    self.state_timer = 5.0 # 5 secondi di Game Over prima di uscire

            elif self.phase == "GAMEOVER" and self.state_timer <= 0:
                # Torna al gioco principale automaticamente
                self.finish({"success": self.score > 0, "score": self.score})

    def _update_play(self, dt: float):
        keys = pygame.key.get_pressed()
        mouse_pos = pygame.mouse.get_pos()
        mouse_buttons = pygame.mouse.get_pressed()
        
        if not self.ship: return

        # Tocco su un bottone touch (es. SPINTA) non deve puntare/sparare.
        on_btn = self.touch.point_on_button(mouse_pos) if hasattr(self, "touch") else False

        # 1. Gestione Orientamento (Mouse vs Keyboard)
        # Attiviamo il mouse se si muove o se viene premuto un tasto del mouse
        if not on_btn and (mouse_pos != self.last_mouse_pos or any(mouse_buttons)):
            self.using_mouse = True
            self.last_mouse_pos = mouse_pos

        if self.using_mouse and not on_btn:
            rx, ry = self.scaling_manager.screen_to_ref(*mouse_pos)
            dx = rx - self.ship.pos.x
            dy = ry - self.ship.pos.y
            if abs(dx) > 2 or abs(dy) > 2:
                self.ship.angle = math.degrees(math.atan2(dy, dx))

        if keys[pygame.K_LEFT]:
            self.ship.rotate(-1, dt)
            self.using_mouse = False
        if keys[pygame.K_RIGHT]:
            self.ship.rotate(1, dt)
            self.using_mouse = False

        # 2. Gestione Propulsione (Su, Click Destro, o bottone touch SPINTA)
        self.ship.thrusting = keys[pygame.K_UP] or mouse_buttons[2] or getattr(self, "touch_thrust", False)
        if self.ship.thrusting:
            self.ship.thrust(dt)
            self._update_thrust_sfx(dt)

        # 3. Gestione Fuoco (Event-based per Space, Polling per Mouse con limite)
        if mouse_buttons[0] and not on_btn:
            if self.mouse_fire_timer <= 0:
                self._fire_bullet(owner="ship")
                self.mouse_fire_timer = 0.2 # Cooldown tra colpi col mouse
        
        if self.mouse_fire_timer > 0:
            self.mouse_fire_timer -= dt
        
        # Aggiornamento Entità (proiettili e particelle sono aggiornati nel main loop)
        self.ship.update(dt)
        
        for a in self.asteroids:
            a.update(dt)

        for u in self.ufos[:]:
            u.update(dt)
            if u.is_dead: self.ufos.remove(u)
            else:
                u.fire_timer -= dt
                if u.fire_timer <= 0:
                    u.fire_timer = random.uniform(1.5, 2.5)
                    angle = u.get_shot_angle(self.ship.pos if self.ship else None, self.score)
                    self._fire_bullet(u.pos, angle, "ufo")

        # UFO spawning
        self.ufo_timer -= dt
        if self.ufo_timer <= 0 and not self.ufos:
            self.ufo_timer = cfg.UFO_MIN_INTERVAL + random.uniform(0, 10)
            size = 2 if self.score < 10000 else random.choice([1, 2])
            self.ufos.append(Ufo(size))

        # Collisioni Bullet -> Asteroid
        for b in self.bullets[:]:
            # Bullet -> Asteroid
            for a in self.asteroids[:]:
                if b.collides_with(a):
                    if b in self.bullets: self.bullets.remove(b)
                    self._split_asteroid(a, b.owner == "ship")
                    break
            
            # Bullet -> Ship
            if b.owner == "ufo" and self.ship and self.ship.invulnerable_timer <= 0:
                if b.collides_with(self.ship):
                    if b in self.bullets: self.bullets.remove(b)
                    self._handle_ship_death()

            # Bullet -> UFO
            if b.owner == "ship":
                for u in self.ufos[:]:
                    if b.collides_with(u):
                        if b in self.bullets: self.bullets.remove(b)
                        self._handle_ufo_death(u)
                        break
        
        if self.ship and self.ship.invulnerable_timer <= 0:
            for a in self.asteroids:
                if self.ship.collides_with(a):
                    self._handle_ship_death()
                    break
            
            if self.ship: # Ricontrollo dopo morte per collisione asteroide
                for u in self.ufos:
                    if self.ship.collides_with(u):
                        self._handle_ship_death()
                        self._handle_ufo_death(u)
                        break

        # Controllo fine livello
        if not self.asteroids:
            self._spawn_level()

        # Heartbeat logic
        self._update_heartbeat(dt)

    def _update_heartbeat(self, dt: float):
        # Più pochi asteroidi ci sono, più è veloce
        num = len(self.asteroids)
        delay = 0.2 + (num * 0.05)
        self.beat_timer -= dt
        if self.beat_timer <= 0:
            self.beat_timer = delay
            self.beat_state = 1 - self.beat_state
            # Heartbeat più leggero per non essere invasivo
            self._play_sfx(cfg.SND_BEAT1 if self.beat_state == 0 else cfg.SND_BEAT2, vol=0.3)

    def _split_asteroid(self, a: Asteroid, scored: bool = True):
        if scored:
            self._add_score(a.points)

        # Spawn particles
        for _ in range(5):
            v = a.vel + pygame.Vector2(random.uniform(-50, 50), random.uniform(-50, 50))
            self.particles.append(Particle(a.pos, v))

        if a.size > 1:
            # Crea due piccoli
            for _ in range(2):
                self.asteroids.append(Asteroid(a.pos, a.size - 1))
        
        self.asteroids.remove(a)
        # SFX in base alla taglia
        if a.size == 3: self._play_sfx(cfg.SND_BANG_LARGE)
        elif a.size == 2: self._play_sfx(cfg.SND_BANG_MEDIUM)
        else: self._play_sfx(cfg.SND_BANG_SMALL)

    def _handle_ufo_death(self, u: Ufo):
        self._add_score(u.points)
        if u in self.ufos: self.ufos.remove(u)
        self._play_sfx(cfg.SND_BANG_MEDIUM)

    def _add_score(self, points: int):
        self.score += points
        if self.score // cfg.EXTRA_LIFE_SCORE > self.last_extra_life_score:
            self.lives += 1
            self.last_extra_life_score = self.score // cfg.EXTRA_LIFE_SCORE
            self._play_sfx(cfg.SND_EXTRA_SHIP)

    def _handle_ship_death(self):
        if not self.ship: return
        
        # Ferma eventuale suono thrust
        self.thrust_sfx_timer = 0.0

        # Effetto esplosione: frammenti e particelle
        for _ in range(6):
            v = pygame.Vector2(random.uniform(-150, 150), random.uniform(-150, 150))
            self.fragments.append(Fragment(self.ship.pos, self.ship.vel + v))
        
        for _ in range(12):
            v = pygame.Vector2(random.uniform(-200, 200), random.uniform(-200, 200))
            self.particles.append(Particle(self.ship.pos, self.ship.vel + v))

        self.lives -= 1
        self.ship = None
        self.phase = "DYING"
        self.state_timer = 2.0
        self._play_sfx(cfg.SND_BANG_LARGE)

    def _play_sfx(self, name: str, vol: float = 0.5):
        if self.audio_manager:
            path = f"engine/minigames/asteroids/assets/sounds/{name}"
            try:
                self.audio_manager.play_sfx(path, vol=vol)
            except: pass

    def _setup_fx_surfaces(self):
        """Inizializza o rigenera le superfici per gli effetti CRT."""
        sw, sh = self.screen.get_size()
        
        # 1. Scanlines (SRCALPHA necessarie per le righe nere trasparenti)
        self.scanline_surf = pygame.Surface((sw, sh), pygame.SRCALPHA)
        for y in range(0, sh, 3):
            pygame.draw.line(self.scanline_surf, (0, 0, 0, 40), (0, y), (sw, y))
            
        log.debug(f"Asteroids FX surfaces initialized: {sw}x{sh}")

    def _update_thrust_sfx(self, dt: float):
        self.thrust_sfx_timer -= dt
        if self.thrust_sfx_timer <= 0:
            self.thrust_sfx_timer = 0.1 # Suono breve e ripetuto
            self._play_sfx(cfg.SND_THRUST, vol=0.2)

    def draw(self) -> None:
        self.screen.fill(cfg.COLOR_BG)
        
        # Disegna Proiettili
        for b in self.bullets:
            sp = self.scaling_manager.ref_to_screen(b.pos.x, b.pos.y)
            pygame.draw.circle(self.screen, cfg.COLOR_WHITE, sp, self.scaling_manager.scale_value(2))

        # Disegna Asteroidi
        for a in self.asteroids:
            self._draw_poly(a.pos, a.poly, 0, cfg.COLOR_WHITE)

        # Disegna UFO
        for u in self.ufos:
            self._draw_poly(u.pos, u.poly, 0, cfg.COLOR_WHITE)

        # Disegna Frammenti Morte
        for f in self.fragments:
            alpha = int(f.life * 255)
            self._draw_poly(f.pos, f.points, f.angle, (alpha, alpha, alpha))

        # Disegna Particelle
        for p in self.particles:
            alpha = int((p.life / 0.6) * 255)
            sp = self.scaling_manager.ref_to_screen(p.pos.x, p.pos.y)
            pygame.draw.circle(self.screen, (alpha, alpha, alpha), sp, self.scaling_manager.scale_value(1))

        # Disegna Nave
        if self.ship:
            color = cfg.COLOR_WHITE
            if self.ship.invulnerable_timer > 0 and int(self.ship.invulnerable_timer * 10) % 2 == 0:
                color = (100, 100, 100) # Lampeggio
            
            self._draw_poly(self.ship.pos, self.ship.poly, self.ship.angle, color)
            if self.ship.thrusting:
                self._draw_poly(self.ship.pos, self.ship.flame_poly, self.ship.angle, cfg.COLOR_THRUST)

        # UI
        self._draw_ui()

        # Controlli touch (solo Android, solo in gioco)
        if hasattr(self, "touch") and self.phase == "PLAY":
            self.touch.draw(self.screen)

        # Applicazione Scanlines
        if self.scanline_surf:
            self.screen.blit(self.scanline_surf, (0, 0))

    def _draw_poly(self, pos: pygame.Vector2, poly: List[pygame.Vector2], angle_deg: float, color: tuple):
        shifted_points = []
        angle_rad = math.radians(angle_deg)
        for p in poly:
            # Ruota
            rx = p.x * math.cos(angle_rad) - p.y * math.sin(angle_rad)
            ry = p.x * math.sin(angle_rad) + p.y * math.cos(angle_rad)
            # Trasla e Scala
            sp = self.scaling_manager.ref_to_screen(pos.x + rx, pos.y + ry)
            shifted_points.append(sp)
        
        if len(shifted_points) >= 2:
            # Effetto BLOOM/GLOW (Vector Style)
            # Disegna una versione più spessa e trasparente sotto
            glow_color = (color[0]//4, color[1]//4, color[2]//4)
            if len(shifted_points) == 2:
                # Per i segmenti (frammenti), disegniamo un glow leggero
                pygame.draw.line(self.screen, glow_color, shifted_points[0], shifted_points[1], 3)
                pygame.draw.aaline(self.screen, color, shifted_points[0], shifted_points[1])
            else:
                # Per i poligoni chiusi
                pygame.draw.lines(self.screen, glow_color, True, shifted_points, 3)
                pygame.draw.aalines(self.screen, color, True, shifted_points)

    def _draw_ui(self):
        # Score (allineato a destra in coordinate di riferimento)
        score_text = self._("asteroids_score").format(score=self.score)
        score_surf = self.font_score.render(score_text, True, cfg.COLOR_WHITE)
        
        # Calcoliamo la posizione partendo dal margine destro di riferimento (1280)
        # e la convertiamo in pixel schermo per il blit
        ref_x = cfg.REF_W - 20
        sx, sy = self.scaling_manager.ref_to_screen(ref_x, 20)
        self.screen.blit(score_surf, (sx - score_surf.get_width(), sy))
        
        # Lives (Pico-navi allineate a destra sotto lo score in coordinate REF)
        for i in range(self.lives):
            # Usiamo le coordinate di riferimento (1280x720)
            lx = cfg.REF_W - 30 - (i * 30)
            ly = 60
            # _draw_poly penserà a convertirle in coordinate schermo
            self._draw_poly(pygame.Vector2(lx, ly), [pygame.Vector2(10, 0), pygame.Vector2(-7, 6), 
                                                     pygame.Vector2(-7, -6)], -90, cfg.COLOR_WHITE)

        if self.phase == "START":
            self._draw_centered_text(self._("asteroids_title"), -50, self.font_main)
            self._draw_centered_text(self._("asteroids_start"), 20, self.font_score)
            self._draw_centered_text(self._("asteroids_instructions"), 80, self.font_score)

        elif self.phase == "GAMEOVER":
            self._draw_centered_text(self._("asteroids_gameover"), -30, self.font_main)
            self._draw_centered_text("PRESS ANY KEY TO EXIT", 30, self.font_score)

    def _draw_centered_text(self, text: str, y_offset: int, font: pygame.font.Font):
        surf = font.render(text, True, cfg.COLOR_WHITE)
        x = self.screen.get_width() // 2 - surf.get_width() // 2
        y = self.screen.get_height() // 2 - surf.get_height() // 2 + int(round(self.scaling_manager.scale_value(y_offset)))
        self.screen.blit(surf, (x, y))

    def on_resize(self) -> None:
        self._prepare_fonts()
        self._setup_fx_surfaces()
