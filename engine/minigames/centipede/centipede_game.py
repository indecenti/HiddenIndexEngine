import pygame
import random
import math
from pathlib import Path
from typing import List, Optional, Tuple, Dict

from engine.minigames.minigame_base import BaseMinigame
from engine.minigames.centipede import centipede_config as cfg
from engine.utils import get_resource_path

class Mushroom:
    def __init__(self, gx: int, gy: int):
        self.gx = gx
        self.gy = gy
        self.health = 4
        self.poisoned = False

    def draw(self, screen, sm, offset_x, offset_y):
        color = cfg.COLOR_MUSHROOM_POISON if self.poisoned else cfg.COLOR_MUSHROOM
        fact = 0.4 + (self.health / 4.0) * 0.6
        c = (int(color[0]*fact), int(color[1]*fact), int(color[2]*fact))
        
        rx = offset_x + self.gx * cfg.GRID_SIZE
        ry = offset_y + self.gy * cfg.GRID_SIZE
        
        # Glow sotto
        glow_rect = sm.scale_rect(rx + 1, ry + 1, cfg.GRID_SIZE - 2, cfg.GRID_SIZE - 2)
        pygame.draw.rect(screen, (c[0]//3, c[1]//3, c[2]//3), glow_rect, border_radius=sm.scale_value(6))
        
        # Cappello
        hat_rect = sm.scale_rect(rx + 2, ry + 2, cfg.GRID_SIZE - 4, cfg.GRID_SIZE // 2 + 2)
        pygame.draw.rect(screen, c, hat_rect, border_radius=sm.scale_value(8))
        # Gambo
        stem_rect = sm.scale_rect(rx + cfg.GRID_SIZE//2 - 2, ry + cfg.GRID_SIZE//2, 4, cfg.GRID_SIZE//2)
        pygame.draw.rect(screen, c, stem_rect)

class CentipedeSegment:
    def __init__(self, x: float, y: float, is_head: bool = False):
        self.pos = pygame.Vector2(x, y)
        self.is_head = is_head
        self.dir_x = 1 
        self.dir_y = 1 
        self.moving_down = False
        self.target_y = y
        self.speed = cfg.CENTIPEDE_SPEED_BASE
        self.poisoned = False

    def update(self, dt: float, mushrooms: Dict[Tuple[int, int], Mushroom], player_zone_top: int):
        if self.moving_down:
            self.pos.y += self.speed * dt
            if self.dir_y > 0:
                if self.pos.y >= self.target_y:
                    self.pos.y = self.target_y
                    self.moving_down = False
            else:
                if self.pos.y <= self.target_y:
                    self.pos.y = self.target_y
                    self.moving_down = False
            return

        prev_gx = int(self.pos.x // cfg.GRID_SIZE)
        self.pos.x += self.dir_x * self.speed * dt
        curr_gx = int(self.pos.x // cfg.GRID_SIZE)
        gy = int(self.pos.y // cfg.GRID_SIZE)

        hit = False
        if self.dir_x > 0 and self.pos.x + cfg.GRID_SIZE > cfg.GAME_W:
            hit = True; self.pos.x = cfg.GAME_W - cfg.GRID_SIZE
        elif self.dir_x < 0 and self.pos.x < 0:
            hit = True; self.pos.x = 0
        
        if not hit and curr_gx != prev_gx:
            if (curr_gx, gy) in mushrooms:
                hit = True
                m = mushrooms[(curr_gx, gy)]
                if m.poisoned: self.poisoned = True
                self.pos.x = prev_gx * cfg.GRID_SIZE

        if hit:
            self.dir_x *= -1
            self.moving_down = True
            if self.poisoned and gy < cfg.ROWS - 1:
                self.target_y = self.pos.y + cfg.GRID_SIZE
                self.dir_y = 1
            else:
                if self.dir_y > 0:
                    if gy >= cfg.ROWS - 1: self.dir_y = -1; self.target_y = self.pos.y - cfg.GRID_SIZE
                    else: self.target_y = self.pos.y + cfg.GRID_SIZE
                else:
                    if gy <= player_zone_top: self.dir_y = 1; self.target_y = self.pos.y + cfg.GRID_SIZE
                    else: self.target_y = self.pos.y - cfg.GRID_SIZE

    def draw(self, screen, sm, offset_x, offset_y):
        color = cfg.COLOR_CENTI_HEAD if self.is_head else cfg.COLOR_CENTI_BODY
        if self.poisoned: color = cfg.COLOR_MUSHROOM_POISON
        rx, ry = offset_x + self.pos.x, offset_y + self.pos.y
        
        # Glow
        glow_c = (color[0]//4, color[1]//4, color[2]//4)
        pygame.draw.rect(screen, glow_c, sm.scale_rect(rx-1, ry-1, cfg.GRID_SIZE+2, cfg.GRID_SIZE+2), border_radius=sm.scale_value(10))
        
        rect = sm.scale_rect(rx + 1, ry + 1, cfg.GRID_SIZE - 2, cfg.GRID_SIZE - 2)
        pygame.draw.rect(screen, color, rect, border_radius=sm.scale_value(self.is_head and 8 or 10))
        
        if self.is_head:
            eye_c = (0, 0, 0)
            ex = rx + (12 if self.dir_x > 0 else 4)
            pygame.draw.rect(screen, eye_c, sm.scale_rect(ex, ry + 4, 4, 4))
            pygame.draw.rect(screen, (255, 255, 255), sm.scale_rect(ex+1, ry + 5, 2, 2))

class Spider:
    def __init__(self, side: int):
        self.pos = pygame.Vector2(-40 if side == 1 else cfg.GAME_W + 20, random.randint(cfg.ROWS-10, cfg.ROWS-2)*cfg.GRID_SIZE)
        self.vel = pygame.Vector2(side * cfg.SPIDER_SPEED, cfg.SPIDER_SPEED)
        self.is_dead = False
        self.move_timer = 0.0

    def update(self, dt: float):
        self.pos += self.vel * dt
        self.move_timer += dt
        if self.move_timer > random.uniform(0.2, 0.4):
            self.move_timer = 0
            self.vel.y *= -1 if random.random() > 0.1 else 1
            # Occasional horizontal flip to keep things erratic
            if random.random() > 0.95: self.vel.x *= -1
        
        # Rimbalzo Orizzontale (MANTIENE IL RAGNO NELL'AREA DI GIOCO)
        if self.pos.x < 0:
            self.pos.x = 0
            self.vel.x = abs(self.vel.x)
        elif self.pos.x > cfg.GAME_W - 20:
            self.pos.x = cfg.GAME_W - 20
            self.vel.x = -abs(self.vel.x)

        # Rimbalzo Verticale (Area Player)
        if self.pos.y < (cfg.ROWS - 12) * cfg.GRID_SIZE:
            self.pos.y = (cfg.ROWS - 12) * cfg.GRID_SIZE
            self.vel.y = abs(self.vel.y)
        elif self.pos.y > cfg.GAME_H - 20:
            self.pos.y = cfg.GAME_H - 20
            self.vel.y = -abs(self.vel.y)

    def draw(self, screen, sm, offset_x, offset_y):
        rx, ry = offset_x + self.pos.x, offset_y + self.pos.y
        color = cfg.COLOR_SPIDER
        # Glow
        pygame.draw.circle(screen, (color[0]//5, color[1]//5, color[2]//5), sm.ref_to_screen(rx+10, ry+10), sm.scale_value(15))
        
        rect = sm.scale_rect(rx, ry, 20, 20)
        pygame.draw.rect(screen, color, rect, border_radius=sm.scale_value(4))
        # Zampe animate
        t = pygame.time.get_ticks() * 0.02
        for i in range(4):
            offset = math.sin(t + i) * 8
            pygame.draw.line(screen, color, sm.ref_to_screen(rx+2+i*5, ry+10), sm.ref_to_screen(rx+2+i*5, ry+10+offset), 2)

class Particle:
    def __init__(self, pos, color):
        self.pos = pygame.Vector2(pos)
        self.vel = pygame.Vector2(random.uniform(-1, 1), random.uniform(-1, 1)).normalize() * random.uniform(50, 150)
        self.color = color
        self.life = 1.0
        self.size = random.randint(2, 5)

    def update(self, dt):
        self.pos += self.vel * dt
        self.life -= dt * 1.5

    def draw(self, screen, sm, offset_x, offset_y):
        if self.life > 0:
            rx, ry = offset_x + self.pos.x, offset_y + self.pos.y
            alpha = int(self.life * 255)
            s = pygame.Surface((sm.scale_value(self.size), sm.scale_value(self.size)), pygame.SRCALPHA)
            s.fill((*self.color, alpha))
            screen.blit(s, (sm.scale_value(rx), sm.scale_value(ry)))

class CentipedeGame(BaseMinigame):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.game_path = get_resource_path("engine", "minigames", "centipede")
        self.load_local_strings(self.game_path / "strings")

        self.mushrooms: Dict[Tuple[int, int], Mushroom] = {}
        self.segments: List[CentipedeSegment] = []
        self.spiders: List[Spider] = []
        self.particles: List[Particle] = []
        self.bullets: List[pygame.Vector2] = []
        self.player_pos = pygame.Vector2(cfg.GAME_W // 2, cfg.GAME_H - 40)
        
        self.score = 0
        self.lives = cfg.INITIAL_LIVES
        self.level = 0
        self.phase = "START"
        self.death_timer = 0.0
        self.invul_timer = 0.0
        
        self.player_zone_top = cfg.ROWS - 10
        self.offset_x = (1280 - cfg.GAME_W) // 2
        self.offset_y = 0
        self.spider_timer = 2.0
        self.scanline_surf = None
        self.last_mouse_pos = pygame.mouse.get_pos()
        self.using_mouse = False

    def start(self) -> None:
        self.score, self.lives, self.level, self.phase = 0, cfg.INITIAL_LIVES, 0, "START"
        self._reset_level(); self._create_scanlines()

    def _reset_level(self):
        self.mushrooms.clear(); self.spiders = []; self.bullets = []
        for _ in range(45):
            gx, gy = random.randint(0, cfg.COLS-1), random.randint(2, cfg.ROWS-10)
            self.mushrooms[(gx, gy)] = Mushroom(gx, gy)
        self._spawn_centipede(12 + self.level)

    def _spawn_centipede(self, length: int):
        self.segments = [CentipedeSegment((cfg.COLS//2 - i) * cfg.GRID_SIZE, 0, i==0) for i in range(length)]

    def _create_scanlines(self):
        sw, sh = self.screen.get_size()
        self.scanline_surf = pygame.Surface((sw, sh), pygame.SRCALPHA)
        for y in range(0, sh, 3): pygame.draw.line(self.scanline_surf, (0, 0, 0, 50), (0, y), (sw, y))

    def handle_event(self, event: pygame.event.Event) -> None:
        if self.phase == "START":
            if event.type in (pygame.KEYDOWN, pygame.MOUSEBUTTONDOWN): self.phase = "PLAY"
        elif self.phase == "GAMEOVER":
            if event.type in (pygame.KEYDOWN, pygame.MOUSEBUTTONDOWN):
                self.finish({"success": self.score > 0, "score": self.score})
        elif self.phase == "PLAY":
            if (event.type == pygame.KEYDOWN and event.key == pygame.K_SPACE) or \
               (event.type == pygame.MOUSEBUTTONDOWN and event.button == 1): self._fire()

    def _fire(self):
        if len(self.bullets) < 1:
            self.bullets.append(pygame.Vector2(self.player_pos.x + 8, self.player_pos.y))
            self._play_sfx(cfg.SND_FIRE)

    def update(self, dt: float) -> None:
        for p in self.particles[:]:
            p.update(dt)
            if p.life <= 0: self.particles.remove(p)
            
        if self.phase == "PLAY":
            if self.invul_timer > 0: self.invul_timer -= dt
            self._update_play(dt)
        elif self.phase == "DYING":
            self.death_timer -= dt
            if self.death_timer <= 0:
                if self.lives <= 0: self.phase = "GAMEOVER"
                else: 
                    self.phase = "PLAY"
                    self.invul_timer = 2.5
                    self.player_pos = pygame.Vector2(cfg.GAME_W//2, cfg.GAME_H-40)
                    self.bullets, self.spiders = [], []
                    self._spawn_centipede(12 + self.level)

    def _update_play(self, dt: float):
        keys = pygame.key.get_pressed()
        mp = pygame.mouse.get_pos()
        if mp != self.last_mouse_pos: self.using_mouse, self.last_mouse_pos = True, mp
        
        new_pos = pygame.Vector2(self.player_pos)
        if self.using_mouse:
            rx, ry = self.scaling_manager.screen_to_ref(*mp)
            new_pos.x = rx - self.offset_x - 10
            new_pos.y = ry - self.offset_y - 10
        else:
            new_pos.x += (keys[pygame.K_RIGHT] - keys[pygame.K_LEFT]) * cfg.PLAYER_SPEED * dt
            new_pos.y += (keys[pygame.K_DOWN] - keys[pygame.K_UP]) * cfg.PLAYER_SPEED * dt

        # Clamp area di gioco
        new_pos.x = max(0, min(new_pos.x, cfg.GAME_W - 20))
        new_pos.y = max(self.player_zone_top * cfg.GRID_SIZE, min(new_pos.y, cfg.GAME_H - 20))

        # Collisione con Funghi (Blocco movimento) - Check su 16x16 per tolleranza
        player_rect = pygame.Rect(new_pos.x + 2, new_pos.y + 2, 16, 16)
        collision = False
        gx, gy = int((new_pos.x+10)//cfg.GRID_SIZE), int((new_pos.y+10)//cfg.GRID_SIZE)
        for dx in [-1, 0, 1]:
            for dy in [-1, 0, 1]:
                check_p = (gx + dx, gy + dy)
                if check_p in self.mushrooms:
                    mr = pygame.Rect(check_p[0]*cfg.GRID_SIZE, check_p[1]*cfg.GRID_SIZE, 20, 20)
                    if player_rect.colliderect(mr):
                        collision = True; break
            if collision: break
        
        if not collision: self.player_pos = new_pos
        if any(keys[k] for k in [pygame.K_LEFT, pygame.K_RIGHT, pygame.K_UP, pygame.K_DOWN]): self.using_mouse = False

        self.spider_timer -= dt
        if self.spider_timer <= 0:
            self.spiders.append(Spider(random.choice([1, -1])))
            self.spider_timer = random.uniform(*cfg.SPIDER_SPAWN_TIME)

        if self.invul_timer <= 0:
            pr = pygame.Rect(self.player_pos.x, self.player_pos.y, 16, 16)
            for s in self.segments:
                s.update(dt, self.mushrooms, self.player_zone_top)
                if pr.colliderect(pygame.Rect(s.pos.x+2, s.pos.y+2, 16, 16)): self._handle_death(); return
            for sp in self.spiders[:]:
                sp.update(dt)
                if sp.is_dead: self.spiders.remove(sp)
                elif pr.colliderect(pygame.Rect(sp.pos.x+2, sp.pos.y+2, 16, 16)): self._handle_death(); return
        else:
            # Anche se invulnerabile, il centopiedi e i ragni devono muoversi!
            for s in self.segments: s.update(dt, self.mushrooms, self.player_zone_top)
            for sp in self.spiders[:]:
                sp.update(dt)
                if sp.is_dead: self.spiders.remove(sp)

        # Bullets
        for b in self.bullets[:]:
            b.y -= cfg.BULLET_SPEED * dt
            if b.y < 0: self.bullets.remove(b); continue
            
            br = pygame.Rect(b.x, b.y, 4, 12)
            gx, gy = int((b.x+2) // cfg.GRID_SIZE), int((b.y+6) // cfg.GRID_SIZE)
            
            if (gx, gy) in self.mushrooms:
                m = self.mushrooms[(gx, gy)]
                m.health -= 1
                if m.health <= 0: del self.mushrooms[(gx, gy)]; self.score += cfg.PT_MUSHROOM
                self.bullets.remove(b); self._play_sfx(cfg.SND_MUSH_HIT, 0.2); continue
                
            # Hit Spider
            hit_spider = next((sp for sp in self.spiders if br.colliderect(pygame.Rect(sp.pos.x, sp.pos.y, 20, 20))), None)
            if hit_spider:
                self.spiders.remove(hit_spider); self.bullets.remove(b); self.score += cfg.PT_SPIDER_MID; self._play_sfx(cfg.SND_KILL_SPIDER); continue

            # Hit Centipede
            hit_seg = next((s for s in self.segments if br.colliderect(pygame.Rect(s.pos.x, s.pos.y, 20, 20))), None)
            if hit_seg:
                self.bullets.remove(b); self.score += cfg.PT_CENTI_HEAD if hit_seg.is_head else cfg.PT_CENTI_BODY
                mx, my = int((hit_seg.pos.x+10)//cfg.GRID_SIZE), int((hit_seg.pos.y+10)//cfg.GRID_SIZE)
                self.mushrooms[(mx, my)] = Mushroom(mx, my); idx = self.segments.index(hit_seg); self.segments.remove(hit_seg)
                if idx < len(self.segments): self.segments[idx].is_head = True
                self._play_sfx(cfg.SND_KILL_CENTI); continue
        if not self.segments: self.level += 1; self._spawn_centipede(12)

    def _handle_death(self):
        self.lives -= 1
        self._play_sfx(cfg.SND_DEATH)
        self.phase = "DYING"
        self.death_timer = 1.5
        # Esplosione particelle
        for _ in range(30):
            self.particles.append(Particle(self.player_pos + pygame.Vector2(10, 10), cfg.COLOR_PLAYER))
            self.particles.append(Particle(self.player_pos + pygame.Vector2(10, 10), (255, 255, 255)))

    def _play_sfx(self, name: str, vol: float = 0.4):
        if self.audio_manager:
            try: 
                sfx_path = f"engine/minigames/centipede/assets/sounds/{name}"
                self.audio_manager.play_sfx(sfx_path, vol=vol)
            except: pass

    def draw(self) -> None:
        self.screen.fill((0,0,0))
        sm = self.scaling_manager
        game_rect = sm.scale_rect(self.offset_x, self.offset_y, cfg.GAME_W, cfg.GAME_H)
        pygame.draw.rect(self.screen, cfg.COLOR_BG, game_rect)
        for m in self.mushrooms.values(): m.draw(self.screen, sm, self.offset_x, self.offset_y)
        for s in self.segments: s.draw(self.screen, sm, self.offset_x, self.offset_y)
        for sp in self.spiders: sp.draw(self.screen, sm, self.offset_x, self.offset_y)
        for b in self.bullets:
            sp = sm.ref_to_screen(self.offset_x+b.x, self.offset_y+b.y)
            pygame.draw.rect(self.screen, cfg.COLOR_BULLET, (sp[0], sp[1], sm.scale_value(4), sm.scale_value(12)))
        
        # Draw Particles
        for p in self.particles: p.draw(self.screen, sm, self.offset_x, self.offset_y)

        # Draw Player
        if self.phase == "PLAY":
            # Blink se invulnerabile
            if self.invul_timer > 0 and (int(self.invul_timer * 10) % 2 == 0):
                pass # Salta il frame per il lampeggio
            else:
                ps = sm.ref_to_screen(self.offset_x+self.player_pos.x, self.offset_y+self.player_pos.y)
                # Player Glow
                pygame.draw.circle(self.screen, (0, 80, 80), (ps[0]+sm.scale_value(10), ps[1]+sm.scale_value(10)), sm.scale_value(15))
                pygame.draw.rect(self.screen, cfg.COLOR_PLAYER, (ps[0], ps[1], sm.scale_value(20), sm.scale_value(20)), border_radius=4)
                pygame.draw.rect(self.screen, cfg.COLOR_PLAYER, (ps[0]+sm.scale_value(8), ps[1]-sm.scale_value(5), sm.scale_value(4), sm.scale_value(5)))
        
        self._draw_ui()
        if self.scanline_surf: self.screen.blit(self.scanline_surf, (0,0))

    def _draw_ui(self):
        sm = self.scaling_manager
        font = pygame.font.SysFont("Courier New", sm.scale_value(28), bold=True)
        score_surf = font.render(self._("centipede_score").format(score=self.score), True, (255, 255, 255))
        self.screen.blit(score_surf, (sm.scale_value(1260 - score_surf.get_width()), sm.scale_value(10)))
        for i in range(self.lives):
            lx = 1260 - 15 - (i * 30)
            pygame.draw.rect(self.screen, cfg.COLOR_PLAYER, (sm.scale_value(lx), sm.scale_value(50), sm.scale_value(15), sm.scale_value(15)))

        if self.phase in ("START", "GAMEOVER"):
            self._draw_overlay_panel(font)

    def _draw_overlay_panel(self, font):
        sm = self.scaling_manager
        sw, sh = self.screen.get_size()
        panel_w, panel_h = sm.scale_value(580), sm.scale_value(240)
        panel_x, panel_y = (sw - panel_w)//2, (sh - panel_h)//2
        
        # Glass Panel
        panel_surf = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)
        pygame.draw.rect(panel_surf, (10, 10, 25, 230), (0,0,panel_w,panel_h), border_radius=int(sm.scale_value(15)))
        pygame.draw.rect(panel_surf, (0, 255, 255, 120), (0,0,panel_w,panel_h), int(sm.scale_value(3)), border_radius=int(sm.scale_value(15)))
        self.screen.blit(panel_surf, (panel_x, panel_y))
        
        if self.phase == "START":
            self._blit_centered_text(self._("centipede_title"), panel_x, panel_y + sm.scale_value(40), panel_w, font, (0, 255, 255))
            sm_font = pygame.font.SysFont("Courier New", sm.scale_value(18))
            self._blit_centered_text(self._("centipede_instructions"), panel_x, panel_y + sm.scale_value(100), panel_w, sm_font, (200, 200, 200))
            self._blit_centered_text(self._("centipede_start"), panel_x, panel_y + sm.scale_value(160), panel_w, font, (255, 255, 255))
        elif self.phase == "GAMEOVER":
            self._blit_centered_text(self._("centipede_gameover"), panel_x, panel_y + sm.scale_value(60), panel_w, font, (255, 50, 50))
            sm_font = pygame.font.SysFont("Courier New", sm.scale_value(20))
            self._blit_centered_text(self._("centipede_exit"), panel_x, panel_y + sm.scale_value(130), panel_w, sm_font, (255, 255, 255))

    def _blit_centered_text(self, text, px, py, pw, font, color):
        s = font.render(text, True, color)
        self.screen.blit(s, (px + (pw - s.get_width())//2, py))
