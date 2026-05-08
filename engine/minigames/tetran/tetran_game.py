import pygame
import random
import time
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from engine.minigames.minigame_base import BaseMinigame
from engine.utils import get_resource_path, get_logger

# Logger per conformità GEMINI.md
logger = get_logger(__name__)

# Costanti di Gioco
GRID_WIDTH = 10
GRID_HEIGHT = 20
BLOCK_SIZE_BASE = 32
TICK_RATE = 0.5
COMBO_TIMEOUT = 2.5

# Mappatura Pezzi (Forme e Colori Asset-Centrici)
TETROMINOS = {
    'I': {'shape': [[0,0,0,0], [1,1,1,1], [0,0,0,0], [0,0,0,0]], 'color': 'purple'},
    'J': {'shape': [[1,0,0], [1,1,1], [0,0,0]], 'color': 'blue'},
    'L': {'shape': [[0,0,1], [1,1,1], [0,0,0]], 'color': 'green'},
    'O': {'shape': [[1,1], [1,1]], 'color': 'red'},
    'S': {'shape': [[0,1,1], [1,1,0], [0,0,0]], 'color': 'yellow'},
    'T': {'shape': [[0,1,0], [1,1,1], [0,0,0]], 'color': 'pink'},
    'Z': {'shape': [[1,1,0], [0,1,1], [0,0,0]], 'color': 'cyan'}
}

class TetranGame(BaseMinigame):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        
        # Caricamento localizzazione
        strings_path = get_resource_path("engine", "minigames", "tetran", "strings")
        self.load_local_strings(Path(strings_path))
        
        # Stato del Gioco
        self.grid = [[None for _ in range(GRID_WIDTH)] for _ in range(GRID_HEIGHT)]
        self.score = 0
        self.time_left = 60.0
        self.multiplier = 1.0
        self.combo_count = 0
        self.last_clear_time = 0.0
        
        # Pezzi e Randomizer (7-Bag)
        self.bag = []
        self.current_piece = None
        self.next_piece_type = self._get_next_from_bag()
        self.held_piece_type = None
        self.can_hold = True
        
        # Timing e Animazioni
        self.fall_timer = 0.0
        self.game_over = False
        self.floating_texts = []
        self.last_tick_sec = 10
        self.das_timer = 0.0
        self.das_direction = 0 # -1 Left, 1 Right
        self.DAS_DELAY = 0.18
        self.DAS_REPEAT = 0.05
        self.game_over_timer = 0.0 # Per evitare skip accidentali
        
        # Asset Caching
        self.assets = {}
        self._load_assets()

    def _load_assets(self) -> None:
        base_path = Path(get_resource_path("engine", "minigames", "tetran", "assets"))
        blocks_path = base_path / "blocks"
        self.assets['blocks'] = {}
        for color in ['blue', 'cyan', 'green', 'pink', 'purple', 'red', 'yellow']:
            p = blocks_path / f"{color}_block" / f"{color}_block.png"
            self.assets['blocks'][color] = pygame.image.load(str(p)).convert_alpha()
            
        ui_path = base_path / "UI"
        self.assets['ui'] = {
            'border': pygame.image.load(str(ui_path / "border" / "border.png")).convert_alpha(),
            'hold': pygame.image.load(str(ui_path / "hold" / "hold.png")).convert_alpha(),
            'next': pygame.image.load(str(ui_path / "next" / "next.png")).convert_alpha(),
        }

    def _get_next_from_bag(self) -> str:
        if not self.bag:
            self.bag = list(TETROMINOS.keys())
            random.shuffle(self.bag)
        return self.bag.pop()

    def spawn_piece(self) -> None:
        piece_type = self.next_piece_type
        self.next_piece_type = self._get_next_from_bag()
        data = TETROMINOS[piece_type]
        self.current_piece = {
            'type': piece_type,
            'shape': [row[:] for row in data['shape']],
            'color': data['color'],
            'x': GRID_WIDTH // 2 - len(data['shape'][0]) // 2,
            'y': 0,
            'special': random.choices(['none', 'T1', 'T2', 'T3'], weights=[75, 10, 10, 5])[0]
        }
        if self.check_collision(self.current_piece['x'], self.current_piece['y']):
            self.trigger_top_out()

    def trigger_top_out(self) -> None:
        logger.info("Top Out raggiunto! Fine partita.")
        self._play_sfx("game_over")
        self.end_game()

    def handle_event(self, event: pygame.event.Event) -> None:
        if self.game_over:
            # Permetti l'uscita solo dopo 1 secondo di cooldown per evitare skip accidentali
            if self.game_over_timer > 1.0:
                if event.type == pygame.KEYDOWN or event.type == pygame.MOUSEBUTTONDOWN:
                    self.finish({"success": self.score > 5000, "score": self.score})
            return
            
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_LEFT:
                self.das_direction = -1
                self.das_timer = 0.0
                self._move_horizontal(-1)
            elif event.key == pygame.K_RIGHT:
                self.das_direction = 1
                self.das_timer = 0.0
                self._move_horizontal(1)
            elif event.key == pygame.K_DOWN:
                pass
            elif event.key == pygame.K_UP:
                self.rotate_piece()
            elif event.key == pygame.K_SPACE:
                self.hard_drop()
            elif event.key == pygame.K_c:
                self.hold_piece()
        elif event.type == pygame.KEYUP:
            if event.key == pygame.K_LEFT and self.das_direction == -1:
                self.das_direction = 0
            elif event.key == pygame.K_RIGHT and self.das_direction == 1:
                self.das_direction = 0

    def rotate_piece(self) -> None:
        if self.current_piece['type'] == 'O': return
        old_shape = self.current_piece['shape']
        new_shape = [list(row) for row in zip(*old_shape[::-1])]
        self.current_piece['shape'] = new_shape
        for dx in [0, -1, 1, -2, 2]:
            if not self.check_collision(self.current_piece['x'] + dx, self.current_piece['y']):
                self.current_piece['x'] += dx
                self._play_sfx("rotation")
                return
        self.current_piece['shape'] = old_shape

    def hard_drop(self) -> None:
        while not self.check_collision(self.current_piece['x'], self.current_piece['y'] + 1):
            self.current_piece['y'] += 1
            self.score += 2
        self.lock_piece()
        self._play_sfx("drop")

    def hold_piece(self) -> None:
        if not self.can_hold:
            self._play_sfx("no_hold")
            return
        current_type = self.current_piece['type']
        if self.held_piece_type is None:
            self.held_piece_type = current_type
            self.spawn_piece()
        else:
            self.held_piece_type, next_type = current_type, self.held_piece_type
            data = TETROMINOS[next_type]
            self.current_piece = {
                'type': next_type,
                'shape': [row[:] for row in data['shape']],
                'color': data['color'],
                'x': GRID_WIDTH // 2 - len(data['shape'][0]) // 2,
                'y': 0,
                'special': 'none'
            }
        self.can_hold = False
        self._play_sfx("hold")

    def check_collision(self, nx: int, ny: int, shape: Optional[List[List[int]]] = None) -> bool:
        shape = shape or self.current_piece['shape']
        for y, row in enumerate(shape):
            for x, cell in enumerate(row):
                if cell:
                    tx, ty = nx + x, ny + y
                    if tx < 0 or tx >= GRID_WIDTH or ty >= GRID_HEIGHT: return True
                    if ty >= 0 and self.grid[ty][tx]: return True
        return False

    def lock_piece(self) -> None:
        for y, row in enumerate(self.current_piece['shape']):
            for x, cell in enumerate(row):
                if cell:
                    ty, tx = self.current_piece['y'] + y, self.current_piece['x'] + x
                    if ty >= 0:
                        self.grid[ty][tx] = {'color': self.current_piece['color'], 'special': self.current_piece['special']}
        self.clear_lines()
        self.spawn_piece()
        self.can_hold = True

    def clear_lines(self) -> None:
        lines_to_clear = [y for y in range(GRID_HEIGHT) if all(self.grid[y][x] for x in range(GRID_WIDTH))]
        if not lines_to_clear:
            if time.time() - self.last_clear_time > COMBO_TIMEOUT: self.combo_count = 0
            return
            
        extra = set()
        for y in lines_to_clear:
            for x in range(GRID_WIDTH):
                b = self.grid[y][x]
                if b['special'] == 'T1': 
                    self.time_left += 2.0
                    self._add_floating_text("+2 SEC", x, y, (0, 255, 100))
                elif b['special'] == 'T2': 
                    self.multiplier += 0.2
                    self._add_floating_text("MULT UP!", x, y, (255, 215, 0))
                elif b['special'] == 'T3':
                    if y > 0: extra.add(y - 1)
                    if y < GRID_HEIGHT - 1: extra.add(y + 1)
                    self._add_floating_text("BOMB!", x, y, (255, 80, 0))
        
        final = sorted(list(set(lines_to_clear) | extra), reverse=True)
        cleared_count = len(final)
        
        # Calcolo punteggio base
        base_points = {1:100, 2:300, 3:500, 4:800}.get(min(4, cleared_count), cleared_count * 200)
        total_gain = int(base_points * self.multiplier)
        
        self.score += total_gain
        self.combo_count += 1
        self.multiplier += (cleared_count * 0.05)
        self.last_clear_time = time.time()
        
        # Feedback punteggio riga
        if lines_to_clear:
            self._add_floating_text(f"+{total_gain}", GRID_WIDTH // 2, lines_to_clear[0], (255, 255, 255))

        for y in final:
            del self.grid[y]
            self.grid.insert(0, [None for _ in range(GRID_WIDTH)])
        self._play_sfx("tetris_clear" if cleared_count >= 4 else "line_clear")

    def update(self, dt: float) -> None:
        if self.game_over:
            self.game_over_timer += dt
            return
        self.time_left -= dt
        if self.time_left <= 0:
            self.end_game()
            return
            
        # Gestione Suoni Countdown (Ansia)
        if self.time_left < 10.5:
            current_sec = int(math.ceil(self.time_left))
            if current_sec < self.last_tick_sec:
                self._play_sfx("click")
                self.last_tick_sec = current_sec
        # Difficoltà Aggressiva + Soft Drop
        current_tick = TICK_RATE * (0.2 + 0.8 * (max(0, self.time_left) / 60.0))
        
        # Soft Drop se il tasto GIÙ è premuto
        keys = pygame.key.get_pressed()
        is_soft_dropping = not self.game_over and keys[pygame.K_DOWN]
        if is_soft_dropping:
            current_tick = min(current_tick, 0.05) # Velocità fissa molto alta per soft drop
        
        self.fall_timer += dt
        if self.fall_timer >= current_tick:
            if not self.check_collision(self.current_piece['x'], self.current_piece['y'] + 1):
                self.current_piece['y'] += 1
                if is_soft_dropping: self.score += 1
            else:
                self.lock_piece()
            self.fall_timer = 0
        if time.time() - self.last_clear_time > COMBO_TIMEOUT:
            self.multiplier = max(1.0, self.multiplier - dt * 0.05)
            
        # Gestione DAS (Orizzontale Continuo)
        if self.das_direction != 0 and not self.game_over:
            self.das_timer += dt
            if self.das_timer >= self.DAS_DELAY:
                if self.das_timer >= self.DAS_DELAY + self.DAS_REPEAT:
                    self._move_horizontal(self.das_direction)
                    self.das_timer = self.DAS_DELAY # Reset allo step di ripetizione

        # Update Floating Texts
        for ft in self.floating_texts[:]:
            ft['y'] -= dt * 60 # Sale verso l'alto
            ft['life'] -= dt
            if ft['life'] <= 0:
                self.floating_texts.remove(ft)

    def draw(self) -> None:
        self.screen.fill((15, 15, 18))
        sw, sh = self.screen.get_size()
        scale = self.scaling_manager.scale
        bs = int(round(BLOCK_SIZE_BASE * scale))
        gw, gh = GRID_WIDTH * bs, GRID_HEIGHT * bs
        ox, oy = int(round((sw - gw) / 2)), int(round((sh - gh) / 2))

        if 'ui' in self.assets:
            border = pygame.transform.scale(self.assets['ui']['border'], (gw + 20, gh + 20))
            self.screen.blit(border, (ox - 10, oy - 10))

        # Ghost Piece
        if self.current_piece:
            gy = self.current_piece['y']
            while not self.check_collision(self.current_piece['x'], gy + 1): gy += 1
            self._draw_shape(self.current_piece['shape'], self.current_piece['color'], 
                             self.current_piece['x'], gy, ox, oy, bs, alpha=60)

        # Griglia
        for y in range(GRID_HEIGHT):
            for x in range(GRID_WIDTH):
                if self.grid[y][x]:
                    self._draw_block(x, y, self.grid[y][x]['color'], ox, oy, bs, self.grid[y][x]['special'])

        # Pezzo Attivo
        if self.current_piece:
            self._draw_shape(self.current_piece['shape'], self.current_piece['color'], 
                             self.current_piece['x'], self.current_piece['y'], ox, oy, bs, 
                             special=self.current_piece['special'])

        # Floating Texts
        font_ft = pygame.font.SysFont("Arial", int(round(20 * scale)), bold=True)
        for ft in self.floating_texts:
            alpha = int(255 * (ft['life'] / 1.5))
            text_surf = font_ft.render(ft['text'], True, ft['color'])
            text_surf.set_alpha(alpha)
            # Coord x,y sono in unità di griglia, le convertiamo in pixel
            tx = ox + ft['x'] * bs
            ty = oy + ft['y'] * bs
            self.screen.blit(text_surf, (tx, ty))

        self._draw_ui_overlay(ox, oy, gw, bs, scale)

        # Game Over Overlay
        if self.game_over:
            self._draw_game_over_overlay(sw, sh, scale)

    def _draw_game_over_overlay(self, sw, sh, scale):
        # Overlay scuro
        overlay = pygame.Surface((sw, sh), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 200))
        self.screen.blit(overlay, (0, 0))
        
        # Font
        font_big = pygame.font.SysFont("Arial", int(round(60 * scale)), bold=True)
        font_mid = pygame.font.SysFont("Arial", int(round(32 * scale)), bold=True)
        font_small = pygame.font.SysFont("Arial", int(round(20 * scale)), bold=True)
        
        # Testi
        title = font_big.render("GAME OVER", True, (255, 50, 50))
        score_txt = font_mid.render(f"Punteggio Finale: {self.score}", True, (255, 255, 255))
        exit_txt = font_small.render("Premi un tasto per uscire", True, (180, 180, 180))
        
        # Centratura
        self.screen.blit(title, ((sw - title.get_width()) // 2, sh // 2 - 80))
        self.screen.blit(score_txt, ((sw - score_txt.get_width()) // 2, sh // 2))
        self.screen.blit(exit_txt, ((sw - exit_txt.get_width()) // 2, sh // 2 + 80))

    def _draw_block(self, x, y, color, ox, oy, bs, special='none', alpha=255):
        if y < 0: return
        img = self.assets['blocks'][color].copy()
        if alpha < 255: img.set_alpha(alpha)
        img_scaled = pygame.transform.scale(img, (bs, bs))
        self.screen.blit(img_scaled, (ox + x * bs, oy + y * bs))
        
        # Effetto Sparkle per blocchi speciali
        if special != 'none':
            t = time.time()
            base_seed = int((x * 37 + y * 23) % 100)
            for i in range(4):
                px = (base_seed + i * 17) % (bs - 8) + 4
                py = (base_seed + i * 31) % (bs - 8) + 4
                sparkle_val = math.sin(t * (4 + i) + base_seed)
                if sparkle_val > 0.4:
                    s_alpha = int(255 * (sparkle_val - 0.4) / 0.6)
                    sparkle_surf = pygame.Surface((2, 2), pygame.SRCALPHA)
                    sparkle_surf.fill((255, 255, 255, s_alpha))
                    self.screen.blit(sparkle_surf, (ox + x * bs + px, oy + y * bs + py))

    def _draw_shape(self, shape, color, px, py, ox, oy, bs, alpha=255, special='none'):
        for y, row in enumerate(shape):
            for x, cell in enumerate(row):
                if cell: self._draw_block(px + x, py + y, color, ox, oy, bs, special, alpha)

    def _draw_ui_overlay(self, ox, oy, gw, bs, scale):
        # Font e Dimensioni dinamiche
        font_main = pygame.font.SysFont("Arial", int(round(28 * scale)), bold=True)
        font_small = pygame.font.SysFont("Arial", int(round(18 * scale)), bold=True)
        panel_alpha = 190
        
        # Buffer orizzontale (distanza dashboard dalla griglia)
        h_margin = int(round(50 * scale))
        dash_w = int(round(200 * scale))
        
        def draw_panel(rect, color=(20, 20, 30)):
            s = pygame.Surface((rect[2], rect[3]), pygame.SRCALPHA)
            pygame.draw.rect(s, (*color, panel_alpha), (0, 0, rect[2], rect[3]), border_radius=int(12 * scale))
            pygame.draw.rect(s, (120, 120, 160, 255), (0, 0, rect[2], rect[3]), 2, border_radius=int(12 * scale))
            self.screen.blit(s, (rect[0], rect[1]))

        # --- Dashboard Sinistra (Tempo e Hold) ---
        dash_left_x = ox - dash_w - h_margin
        
        # Pannello Tempo
        t_panel_h = int(round(80 * scale))
        draw_panel((dash_left_x, oy, dash_w, t_panel_h))
        t_time = self._("time_left").format(time=int(self.time_left))
        
        # Effetto "Ansia" sotto i 10 secondi
        time_color = (255, 255, 255)
        current_font = font_main
        if self.time_left < 10:
            time_color = (255, 50, 50)
            # Pulsazione: ingrandimento dinamico
            pulse = 1.0 + 0.15 * math.sin(time.time() * 10)
            p_size = int(round(28 * scale * pulse))
            current_font = pygame.font.SysFont("Arial", p_size, bold=True)
            if int(time.time() * 5) % 2 == 0: # Flicker
                time_color = (255, 200, 200)

        time_surf = current_font.render(t_time, True, time_color)
        self.screen.blit(time_surf, (dash_left_x + (dash_w - time_surf.get_width()) // 2, oy + (t_panel_h - time_surf.get_height()) // 2))
        
        # Pannello Hold
        hold_y = oy + t_panel_h + int(round(20 * scale))
        hold_panel_h = int(round(200 * scale))
        draw_panel((dash_left_x, hold_y, dash_w, hold_panel_h))
        if 'ui' in self.assets:
            box_size = int(round(140 * scale))
            self.screen.blit(pygame.transform.scale(self.assets['ui']['hold'], (box_size, box_size)), 
                            (dash_left_x + (dash_w - box_size) // 2, hold_y + 40))
            if self.held_piece_type:
                # Spostato molto più in basso (+95) per liberare la scritta "HOLD"
                self._draw_preview(self.held_piece_type, dash_left_x + (dash_w - box_size) // 2 + 30, hold_y + 95, bs * 0.6)

        # --- Dashboard Destra (Score, Multiplier e Next) ---
        dash_right_x = ox + gw + h_margin
        
        # Pannello Score
        s_panel_h = int(round(120 * scale))
        draw_panel((dash_right_x, oy, dash_w, s_panel_h))
        self.screen.blit(font_small.render("SCORE", True, (200, 200, 240)), (dash_right_x + 20, oy + 12))
        score_val = font_main.render(str(self.score), True, (255, 255, 255))
        self.screen.blit(score_val, (dash_right_x + 20, oy + 42))
        
        mult_color = (255, int(max(0, 255 - self.multiplier * 20)), 0)
        mult_text = font_main.render(f"x{round(self.multiplier, 1)}", True, mult_color)
        self.screen.blit(mult_text, (dash_right_x + 20, oy + 78))

        # Pannello Next
        next_y = oy + s_panel_h + int(round(20 * scale))
        next_panel_h = int(round(200 * scale))
        draw_panel((dash_right_x, next_y, dash_w, next_panel_h))
        if 'ui' in self.assets:
            box_size = int(round(140 * scale))
            self.screen.blit(pygame.transform.scale(self.assets['ui']['next'], (box_size, box_size)), 
                            (dash_right_x + (dash_w - box_size) // 2, next_y + 40))
            # Spostato molto più in basso (+95) per liberare la scritta "NEXT"
            self._draw_preview(self.next_piece_type, dash_right_x + (dash_w - box_size) // 2 + 30, next_y + 95, bs * 0.6)
        
        # Combo Indicator
        if self.combo_count > 1:
            combo_y = next_y + next_panel_h + int(round(20 * scale))
            draw_panel((dash_right_x, combo_y, dash_w, int(round(70 * scale))), color=(35, 55, 45))
            combo_text = font_main.render(f"COMBO x{self.combo_count}", True, (0, 255, 180))
            self.screen.blit(combo_text, (dash_right_x + (dash_w - combo_text.get_width()) // 2, combo_y + (int(round(70*scale)) - combo_text.get_height()) // 2))

    def _draw_preview(self, p_type, px, py, bs):
        data = TETROMINOS[p_type]
        for y, row in enumerate(data['shape']):
            for x, cell in enumerate(row):
                if cell:
                    img = pygame.transform.scale(self.assets['blocks'][data['color']], (int(bs), int(bs)))
                    self.screen.blit(img, (px + x * bs, py + y * bs))

    def _play_sfx(self, key):
        if self.audio_manager: self.audio_manager.play_sfx(f"engine/minigames/tetran/assets/sound/{key}.mp3")

    def _move_horizontal(self, dx):
        if not self.current_piece: return
        if not self.check_collision(self.current_piece['x'] + dx, self.current_piece['y']):
            self.current_piece['x'] += dx
            self._play_sfx("click")

    def _add_floating_text(self, text, x, y, color):
        self.floating_texts.append({
            'text': text,
            'x': x,
            'y': y,
            'color': color,
            'life': 1.5 # Secondi di durata
        })

    def start(self) -> None: self.spawn_piece()

    def finish(self, result: dict) -> None:
        self.is_running = False
        if self.on_complete: self.on_complete(result)

    def end_game(self) -> None:
        self.game_over = True
        logger.info(f"Minigioco Tetran concluso: {self.score}")
