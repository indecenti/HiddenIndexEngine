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
        # Cache delle cifre gia' scalate, keyed da (digit, size): evita lo
        # scale per-frame nel hot loop dei punteggi (caro su ARM/Android).
        self._scaled_digit_cache: Dict[tuple, pygame.Surface] = {}
        # Cache delle Surface di testo renderizzate (font.render e' tra le op
        # piu' care su Android): keyed da (text, int_size, color).
        self._text_cache: Dict[tuple, pygame.Surface] = {}
        # Cache dei font SysFont per (nome, dimensione, bold): SysFont e' costoso
        # se costruito ogni frame.
        self._font_cache: Dict[tuple, pygame.font.Font] = {}
        # Surface opaca scura riusata per l'overlay finale (niente SRCALPHA
        # fullscreen ricreata ogni frame).
        self._end_overlay_surf = None

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
            # convert_alpha una volta: blit ripetuti enormemente piu' veloci.
            self.digit_surfaces[val] = surf.convert_alpha()
        # La cache delle cifre scalate va invalidata se ricreiamo le sorgenti.
        self._scaled_digit_cache.clear()

    def _create_scanlines(self):
        # Su Android niente scanline (blit full-screen SRCALPHA per frame troppo lento).
        if self._android:
            self.scanline_surf = None
            return
        sw, sh = self.screen.get_size()
        surf = pygame.Surface((sw, sh), pygame.SRCALPHA)
        for y in range(0, sh, 3):
            pygame.draw.line(surf, (0, 0, 0, 35), (0, y), (sw, y))
        # convert_alpha: questa surface viene blittata ogni frame.
        self.scanline_surf = surf.convert_alpha()

    def _get_font(self, name: str, size: int, bold: bool = False) -> pygame.font.Font:
        """Ritorna un SysFont cachato per (nome, dimensione, bold)."""
        key = (name, size, bold)
        font = self._font_cache.get(key)
        if font is None:
            font = pygame.font.SysFont(name, size, bold=bold)
            self._font_cache[key] = font
        return font

    def _get_text_surface(self, font_key: tuple, text: str, color: tuple) -> pygame.Surface:
        """Ritorna una Surface di testo renderizzata e cachata.

        La chiave include font (nome/size/bold), testo e colore: quando nulla
        cambia e' un cache-hit e si evita la costosa font.render per-frame.
        """
        cache_key = (font_key, text, color)
        surf = self._text_cache.get(cache_key)
        if surf is None:
            font = self._get_font(*font_key)
            surf = font.render(text, True, color).convert_alpha()
            self._text_cache[cache_key] = surf
        return surf

    def on_resize(self) -> None:
        # Alla variazione di risoluzione invalido le cache dipendenti dalla
        # scala/dimensione schermo e ricostruisco le scanline.
        self._scaled_digit_cache.clear()
        self._text_cache.clear()
        self._end_overlay_surf = None
        self._create_scanlines()

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
        # Overlay scuro: una Surface opaca riusata con set_alpha invece di
        # ricreare una SRCALPHA fullscreen + fill ogni frame (~10x su Android).
        overlay = self._end_overlay_surf
        if overlay is None or overlay.get_size() != (sw, sh):
            overlay = pygame.Surface((sw, sh)).convert()
            overlay.fill((0, 0, 0))
            overlay.set_alpha(200)
            self._end_overlay_surf = overlay
        self.screen.blit(overlay, (0, 0))

        success = self.player_score >= cfg.WIN_LIMIT
        msg_key = "pong_win" if success else "pong_lose"
        text = self._(msg_key).upper()

        color = (100, 255, 100) if success else (255, 100, 100)
        font_key = ("Segoe UI", self.scaling_manager.scale_value(80), True)

        # Effetto pulsante: seleziona tra due Surface cachate (colore vs bianco)
        # invece di ri-renderizzare il font ogni frame.
        pulsate = abs(math.sin(pygame.time.get_ticks() * 0.005))
        draw_color = (255, 255, 255) if pulsate > 0.8 else color
        surf = self._get_text_surface(font_key, text, draw_color)
        rect = surf.get_rect(center=(sw//2, sh//2))
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
                # Scalo l'intera cifra con Nearest Neighbor per pixel perfetti.
                # Cache keyed da (digit, size): lo scale avviene una sola volta
                # per dimensione (la chiave cambia solo su resize), non ogni frame.
                cache_key = (digit, size)
                scaled_digit = self._scaled_digit_cache.get(cache_key)
                if scaled_digit is None:
                    orig_surf = self.digit_surfaces[digit]
                    scaled = pygame.transform.scale(orig_surf, size)
                    if self._android:
                        # Su Android la cifra viene composta su una tile OPACA
                        # riempita col colore di sfondo (lo schermo e' gia'
                        # COLOR_BG sotto i punteggi): blit opaco per-frame ~10x
                        # piu' veloce dell'SRCALPHA. Pixel identici perche' il
                        # fondo e' noto e costante. Sul desktop resta SRCALPHA.
                        tile = pygame.Surface(size)
                        tile.fill(cfg.COLOR_BG)
                        tile.blit(scaled, (0, 0))
                        scaled_digit = tile.convert()
                    else:
                        scaled_digit = scaled.convert_alpha()
                    self._scaled_digit_cache[cache_key] = scaled_digit
                self.screen.blit(scaled_digit, (int(round(curr_x)), int(round(y))))
                curr_x += size[0] + (size[0]//3) # Spazio proporzionale

    def _draw_text_overlay(self, text: str, y_off: int) -> None:
        # Font e Surface cachati: niente SysFont + font.render per-frame.
        font_key = ("Arial", self.scaling_manager.scale_value(25), False)
        surf = self._get_text_surface(font_key, text, (150, 150, 150))
        self.screen.blit(surf, (self.screen.get_width()//2 - surf.get_width()//2,
                                self.screen.get_height()//2 + self.scaling_manager.scale_value(y_off)))
