import pygame
import random
import math
from pathlib import Path
from typing import Dict, Any

from engine.minigames.minigame_base import BaseMinigame
from engine.minigames.minipong import pong_config as cfg
from engine.utils import get_resource_path

class MiniPongGame(BaseMinigame):
    # Griglia 3x5 per ogni cifra. Ogni stringa rappresenta 5 righe di 3 pixel.
    # 'X' = pixel bianco, '.' = vuoto
    DIGIT_MAPS = {
        0: ["XXX", "X.X", "X.X", "X.X", "XXX"],
        1: ["..X", "..X", "..X", "..X", "..X"],
        2: ["XXX", "..X", "XXX", "X..", "XXX"],
        3: ["XXX", "..X", "XXX", "..X", "XXX"],
        4: ["X.X", "X.X", "XXX", "..X", "..X"],
        5: ["XXX", "X..", "XXX", "..X", "XXX"],
        6: ["XXX", "X..", "XXX", "X.X", "XXX"],
        7: ["XXX", "..X", "..X", "..X", "..X"],
        8: ["XXX", "X.X", "XXX", "X.X", "XXX"],
        9: ["XXX", "X.X", "XXX", "..X", "..X"]
    }

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.load_local_strings(get_resource_path("engine", "minigames", "minipong", "strings"))

        self.phase = "START"
        self.player_score = 0
        self.ai_score = 0
        
        self.p1_y = (cfg.REF_H - cfg.PADDLE_H) / 2
        self.p2_y = (cfg.REF_H - cfg.PADDLE_H) / 2
        
        self.ball_pos = pygame.Vector2(cfg.REF_W / 2, cfg.REF_H / 2)
        self.ball_vel = pygame.Vector2(0, 0)
        self.ball_speed = cfg.INITIAL_BALL_SPEED
        
        self.state_timer = 0.0
        self.scanline_surf = None
        
        # Cache per le surface dei numeri (per evitare di ricrearle ogni frame)
        self.digit_surfaces: Dict[int, pygame.Surface] = {}

    def start(self) -> None:
        self.player_score = 0
        self.ai_score = 0
        self.phase = "START"
        self._reset_ball(to_player=True)
        self._create_scanlines()
        self._prepare_digit_surfaces()

    def _prepare_digit_surfaces(self):
        """Crea le mini-surfaces 3x5 per ogni cifra."""
        for val, rows in self.DIGIT_MAPS.items():
            surf = pygame.Surface((3, 5), pygame.SRCALPHA)
            for y, row in enumerate(rows):
                for x, char in enumerate(row):
                    if char == 'X':
                        surf.set_at((x, y), cfg.COLOR_MAIN)
            self.digit_surfaces[val] = surf

    def _create_scanlines(self):
        sw, sh = self.screen.get_size()
        self.scanline_surf = pygame.Surface((sw, sh), pygame.SRCALPHA)
        for y in range(0, sh, 3):
            pygame.draw.line(self.scanline_surf, (0, 0, 0, 35), (0, y), (sw, y))

    def _reset_ball(self, to_player: bool = True) -> None:
        self.ball_pos = pygame.Vector2(cfg.REF_W / 2, cfg.REF_H / 2)
        self.ball_speed = cfg.INITIAL_BALL_SPEED
        angle = random.uniform(-0.4, 0.4)
        direction = -1 if to_player else 1
        self.ball_vel = pygame.Vector2(direction * math.cos(angle), math.sin(angle)).normalize()

    def handle_event(self, event: pygame.event.Event) -> None:
        if self.phase == "START":
            if event.type in (pygame.MOUSEBUTTONDOWN, pygame.KEYDOWN):
                self.phase = "PLAY"
        
        if event.type == pygame.MOUSEMOTION:
            _, ry = self.scaling_manager.screen_to_ref(*event.pos)
            self.p1_y = ry - cfg.PADDLE_H / 2
            self._clamp_paddles()

    def _clamp_paddles(self) -> None:
        self.p1_y = max(cfg.PADDLE_TOP_LIMIT, min(self.p1_y, cfg.REF_H - cfg.PADDLE_H))
        self.p2_y = max(cfg.PADDLE_TOP_LIMIT, min(self.p2_y, cfg.REF_H - cfg.PADDLE_H))

    def update(self, dt: float) -> None:
        if self.phase == "SCORED":
            self.state_timer -= dt
            if self.state_timer <= 0:
                if self.player_score >= cfg.WIN_LIMIT or self.ai_score >= cfg.WIN_LIMIT:
                    self.phase = "END"
                    self.state_timer = 4.0 # Timer per mostrare la schermata finale
                else: 
                    self.phase = "PLAY"
            return
            
        if self.phase == "PLAY":
            self._update_physics(dt)
            self._update_ai(dt)
            
        if self.phase == "END":
            self.state_timer -= dt
            if self.state_timer <= 0:
                success = self.player_score >= cfg.WIN_LIMIT
                self.finish({"success": success, "score": 1000 if success else 0})

    def _update_physics(self, dt: float) -> None:
        self.ball_pos += self.ball_vel * self.ball_speed * dt
        
        if self.ball_pos.y <= 0:
            self.ball_pos.y = 0
            self.ball_vel.y *= -1
            self._play_sfx(cfg.SND_WALL)
        elif self.ball_pos.y >= cfg.REF_H - cfg.BALL_SIZE:
            self.ball_pos.y = cfg.REF_H - cfg.BALL_SIZE
            self.ball_vel.y *= -1
            self._play_sfx(cfg.SND_WALL)
            
        ball_rect = pygame.Rect(self.ball_pos.x, self.ball_pos.y, cfg.BALL_SIZE, cfg.BALL_SIZE)
        p1_rect = pygame.Rect(cfg.MARGIN_SIDE, self.p1_y, cfg.PADDLE_W, cfg.PADDLE_H)
        p2_rect = pygame.Rect(cfg.REF_W - cfg.MARGIN_SIDE - cfg.PADDLE_W, self.p2_y, 
                              cfg.PADDLE_W, cfg.PADDLE_H)
        
        if self.ball_vel.x < 0 and ball_rect.colliderect(p1_rect):
            self._handle_paddle_hit(p1_rect, is_p1=True)
        elif self.ball_vel.x > 0 and ball_rect.colliderect(p2_rect):
            self._handle_paddle_hit(p2_rect, is_p1=False)
            
        if self.ball_pos.x < 0:
            self.ai_score += 1
            self._trigger_score(to_player=True)
        elif self.ball_pos.x > cfg.REF_W:
            self.player_score += 1
            self._trigger_score(to_player=False)

    def _handle_paddle_hit(self, paddle_rect: pygame.Rect, is_p1: bool) -> None:
        hit_pos = (self.ball_pos.y + cfg.BALL_SIZE/2) - (paddle_rect.y + cfg.PADDLE_H/2)
        relative_hit = hit_pos / (cfg.PADDLE_H / 2)
        relative_hit = max(-1.0, min(1.0, relative_hit))
        
        segment = int((relative_hit + 1.0) * 4)
        segment = min(7, segment)
        angles = [math.radians(60), math.radians(45), math.radians(30), math.radians(15),
                  math.radians(15), math.radians(30), math.radians(45), math.radians(60)]
        
        angle = angles[segment]
        dir_y = -1 if relative_hit < 0 else 1
        new_dir_x = 1 if is_p1 else -1
        self.ball_vel = pygame.Vector2(new_dir_x * math.cos(angle), dir_y * math.sin(angle)).normalize()
        self.ball_speed = min(cfg.MAX_BALL_SPEED, self.ball_speed + cfg.SPEED_INCREMENT)
        
        if is_p1: self.ball_pos.x = paddle_rect.right
        else: self.ball_pos.x = paddle_rect.left - cfg.BALL_SIZE
        self._play_sfx(cfg.SND_HIT)

    def _update_ai(self, dt: float) -> None:
        target_center = self.ball_pos.y + cfg.BALL_SIZE/2
        current_center = self.p2_y + cfg.PADDLE_H/2
        dist = target_center - current_center
        if abs(dist) > 15:
            self.p2_y += cfg.AI_SPEED_BASE * dt * (1 if dist > 0 else -1)
        self._clamp_paddles()

    def _trigger_score(self, to_player: bool) -> None:
        self.phase = "SCORED"
        self.state_timer = 1.2
        self._play_sfx(cfg.SND_SCORE)
        self._reset_ball(to_player=to_player)

    def _play_sfx(self, path: str) -> None:
        if self.audio_manager: self.audio_manager.play_sfx(path, vol=cfg.SFX_VOLUME)

    def draw(self) -> None:
        self.screen.fill(cfg.COLOR_BG)
        self._draw_center_line()
        
        p1 = self.scaling_manager.scale_rect(cfg.MARGIN_SIDE, self.p1_y, cfg.PADDLE_W, cfg.PADDLE_H)
        p2 = self.scaling_manager.scale_rect(cfg.REF_W - cfg.MARGIN_SIDE - cfg.PADDLE_W, self.p2_y, 
                                             cfg.PADDLE_W, cfg.PADDLE_H)
        ball = self.scaling_manager.scale_rect(self.ball_pos.x, self.ball_pos.y, 
                                               cfg.BALL_SIZE, cfg.BALL_SIZE)
        
        pygame.draw.rect(self.screen, cfg.COLOR_MAIN, p1)
        pygame.draw.rect(self.screen, cfg.COLOR_MAIN, p2)
        pygame.draw.rect(self.screen, cfg.COLOR_MAIN, ball)
        
        # Punteggi Pixel-Perfect
        self._draw_pixel_perfect_scores()
        
        if self.phase == "START":
            self._draw_text_overlay(self._("pong_help"), 200)

        if self.phase == "END":
            self._draw_end_overlay()
            
        if self.scanline_surf:
            self.screen.blit(self.scanline_surf, (0, 0))

    def _draw_end_overlay(self) -> None:
        sw, sh = self.screen.get_size()
        overlay = pygame.Surface((sw, sh), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 200))
        self.screen.blit(overlay, (0, 0))
        
        success = self.player_score >= cfg.WIN_LIMIT
        msg_key = "pong_win" if success else "pong_lose"
        text = self._(msg_key)
        
        color = (100, 255, 100) if success else (255, 100, 100)
        font = pygame.font.SysFont("Segoe UI", self.scaling_manager.scale_value(80), bold=True)
        surf = font.render(text.upper(), True, color)
        rect = surf.get_rect(center=(sw//2, sh//2))
        
        # Effetto pulsante
        pulsate = abs(math.sin(pygame.time.get_ticks() * 0.005))
        if pulsate > 0.8:
            surf = font.render(text.upper(), True, (255, 255, 255))
            
        self.screen.blit(surf, rect)

    def _draw_center_line(self) -> None:
        x = cfg.REF_W / 2 - cfg.DASH_W / 2
        for y in range(10, cfg.REF_H, cfg.DASH_H + cfg.DASH_GAP):
            r = self.scaling_manager.scale_rect(x, y, cfg.DASH_W, cfg.DASH_H)
            pygame.draw.rect(self.screen, cfg.COLOR_MAIN, r)

    def _draw_pixel_perfect_scores(self) -> None:
        """Disegna i punteggi scalando intere superfici 3x5 per evitare jittering."""
        # Unità di scala: quanto è grande un 'pixel' del numero retro
        pixel_size = self.scaling_manager.scale_value(25)
        # Dimensione finale della cifra (3x5 pixel originali)
        target_size = (3 * pixel_size, 5 * pixel_size)
        spacing = self.scaling_manager.scale_value(150)
        
        # Player 1
        self._draw_full_score(self.screen.get_width()//2 - spacing, 80, 
                             self.player_score, target_size, align_right=True)
        # AI
        self._draw_full_score(self.screen.get_width()//2 + spacing, 80, 
                             self.ai_score, target_size, align_right=False)

    def _draw_full_score(self, x: int, y: int, score: int, size: tuple, align_right: bool):
        s_score = str(score)
        total_w = len(s_score) * size[0] + (len(s_score)-1) * (size[0]//3)
        
        start_x = x - total_w if align_right else x
        
        curr_x = start_x
        for char in s_score:
            digit = int(char)
            if digit in self.digit_surfaces:
                orig_surf = self.digit_surfaces[digit]
                # Scalo l'intera cifra con Nearest Neighbor per pixel perfetti
                scaled_digit = pygame.transform.scale(orig_surf, size)
                self.screen.blit(scaled_digit, (int(round(curr_x)), int(round(y))))
                curr_x += size[0] + (size[0]//3) # Spazio proporzionale

    def _draw_text_overlay(self, text: str, y_off: int) -> None:
        font = pygame.font.SysFont("Arial", self.scaling_manager.scale_value(25))
        surf = font.render(text, True, (150, 150, 150))
        self.screen.blit(surf, (self.screen.get_width()//2 - surf.get_width()//2, 
                                self.screen.get_height()//2 + self.scaling_manager.scale_value(y_off)))
