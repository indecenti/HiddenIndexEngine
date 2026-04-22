"""
engine/minigames/tower/tower_game.py
Versione con feedback errore "Pulse & Red Glow" e audio ai_action.wav per slot non validi.
"""

import random
import math
import pygame
import json
from pathlib import Path
from typing import List, Optional, Tuple, Dict
from engine.minigames.minigame_base import BaseMinigame
from engine.utils import get_logger, get_resource_path

log = get_logger(__name__)

CELL_WIDTH, CELL_HEIGHT = 95, 138
SPACING = 10
SIDEBAR_WIDTH_RATIO = 0.28
CYAN = (0, 240, 255)
ARCADE_RED = (255, 30, 80)
GOLD = (255, 215, 0)
COMIC_YELLOW = (255, 240, 0)
COMIC_ORANGE = (255, 140, 0)

K_SLOTS = [(0, 0), (0, 3), (3, 0), (3, 3)]
J_SLOTS = [(0, 1), (0, 2), (3, 1), (3, 2)]
Q_SLOTS = [(1, 0), (2, 0), (1, 3), (2, 3)]

EV_FINISH = pygame.USEREVENT + 21

class Particle:
    def __init__(self, x, y, color):
        self.pos = pygame.Vector2(x, y)
        self.vel = pygame.Vector2(random.uniform(-400, 400), random.uniform(-600, 100))
        self.color = color
        self.life = 1.0
        self.gravity = 800

    def update(self, dt):
        self.vel.y += self.gravity * dt; self.pos += self.vel * dt; self.life -= dt * 0.5

class Card:
    def __init__(self, value: int, suit: str, surf: pygame.Surface, back: pygame.Surface):
        self.value, self.suit, self.surf, self.back = value, suit, surf, back
        self.is_face_up = False
        self.pos, self.target_pos = pygame.Vector2(0, 0), pygame.Vector2(0, 0)
        self.anim_t, self.flip_t = 1.0, 1.0     
        self.is_flipping, self.is_vanishing = False, False
        self.vanish_t, self.fall_vel = 0.0, 0.0
        self._cached_surf = {True: None, False: None}
        self._last_scale = 0

    @property
    def is_royal(self) -> bool: return self.value > 10

    def start_flip(self, current_pos: pygame.Vector2, target_pos: pygame.Vector2):
        self.pos = pygame.Vector2(current_pos); self.target_pos = target_pos
        self.anim_t = 0.0; self.flip_t = 0.0; self.is_flipping = True

    def start_vanish(self): self.is_vanishing = True; self.vanish_t = 0.0

    def update(self, dt: float, phase: str = "PLAYING"):
        if phase == "LOSE":
            self.fall_vel += 1200 * dt; self.pos.y += self.fall_vel * dt; return
        if self.is_vanishing:
            self.vanish_t = min(1.0, self.vanish_t + dt * 2.0); return
        if self.anim_t < 1.0:
            self.anim_t = min(1.0, self.anim_t + dt * 4.0)
            self.pos = self.pos.lerp(self.target_pos, 1 - (1 - self.anim_t)**2)
        if self.is_flipping:
            self.flip_t += dt * 3.5
            if self.flip_t >= 1.0: self.flip_t = 1.0; self.is_flipping = False
            if self.flip_t >= 0.5: self.is_face_up = True

    def draw(self, screen: pygame.Surface, scale: float, is_sel: bool = False, err_pulse: float = 0):
        if scale != self._last_scale:
            w, h = int(CELL_WIDTH * scale), int(CELL_HEIGHT * scale)
            self._cached_surf[True], self._cached_surf[False] = pygame.transform.smoothscale(self.surf, (w, h)), pygame.transform.smoothscale(self.back, (w, h))
            self._last_scale = scale
        if self.is_vanishing:
            al = int(255 * (1 - self.vanish_t)); sm = 1.1 + self.vanish_t * 0.6
            s = self._cached_surf[True].copy()
            ov = pygame.Surface(s.get_size(), pygame.SRCALPHA); ov.fill((*CYAN, int(100 * (1-self.vanish_t))))
            s.blit(ov, (0, 0)); s.set_alpha(al); s = pygame.transform.rotate(s, self.vanish_t * 180)
            s = pygame.transform.scale(s, (int(s.get_width() * sm), int(s.get_height() * sm)))
            screen.blit(s, s.get_rect(center=(int(self.pos.x), int(self.pos.y)))); return

        ay = -70 * math.sin(self.flip_t * math.pi) * scale if self.is_flipping else 0
        wm = abs(math.cos(math.pi * self.flip_t))
        si = self.is_face_up if not self.is_flipping else (self.flip_t > 0.5)
        s = self._cached_surf[si].copy()
        
        dyn_scale = 1.0 + err_pulse * 0.2 # Impulso scala per errore
        if dyn_scale > 1.0:
            s = pygame.transform.rotozoom(s, 0, dyn_scale)
            if err_pulse > 0:
                glow = pygame.Surface(s.get_size(), pygame.SRCALPHA)
                glow.fill((*ARCADE_RED, int(150 * err_pulse)))
                s.blit(glow, (0, 0), special_flags=pygame.BLEND_RGBA_ADD)

        if is_sel:
            ov = pygame.Surface(s.get_size(), pygame.SRCALPHA); ov.fill((*CYAN, 80)); s.blit(ov, (0, 0))
            pygame.draw.rect(screen, CYAN, s.get_rect(center=(int(self.pos.x), int(self.pos.y + ay))), 3)

        if wm < 0.01: return
        ws = int(s.get_width() * wm)
        if ws > 0:
            fs = pygame.transform.scale(s, (ws, s.get_height()))
            rect = fs.get_rect(center=(int(self.pos.x), int(self.pos.y + ay)))
            screen.blit(fs, rect)

class TowerGame(BaseMinigame):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.deck, self.grid, self.vanishing = [], {(r, c): None for r in range(4) for c in range(4)}, []
        self.hand, self.selected, self.score, self.phase = None, [], 0, "PLAYING"
        self.matching_mode = False; self.castle_alpha, self.castle_img = 0, None
        self.particles: List[Particle] = []; self.timer_anim = 0; self.phase_banner_t = 0
        self.lose_delay_timer, self.error_pulse_t = 0, 0
        self.game_time, self.time_bonus, self.total_score = 0, 0, 0
        # Suoni con Path OS (compatibility PyInstaller)
        self.sfx_click = get_resource_path("engine", "minigames", "tower", "sounds", "click.wav")
        self.sfx_score = get_resource_path("engine", "minigames", "tower", "sounds", "score.mp3")
        self.sfx_victory = get_resource_path("engine", "minigames", "tower", "sounds", "victory.mp3")
        self.sfx_lose = get_resource_path("engine", "minigames", "tower", "sounds", "error4.mp3")
        self.sfx_match_start = get_resource_path("engine", "minigames", "tower", "sounds", "bling5.mp3")
        self.sfx_error = get_resource_path("engine", "minigames", "tower", "sounds", "ai_action.wav")

    def start(self):
        p = get_resource_path("engine", "minigames", "tower")
        self.load_local_strings(p / "strings")
        try: self.castle_img = pygame.image.load(str(p / "castle_victory.png")).convert_alpha()
        except: pass
        self._init_deck(p); random.shuffle(self.deck); self._update_fonts(); self._auto_draw()


    def _update_fonts(self):
        s = self.scaling_manager.scale
        self.f_tit = pygame.font.SysFont("Verdana", int(28 * s), bold=True) 
        self.f_ui = pygame.font.SysFont("Impact", int(22 * s))
        self.f_side = pygame.font.SysFont("Georgia", int(15 * s), italic=True)
        self.f_banner = pygame.font.SysFont("Impact", int(70 * s))

    def on_resize(self):
        self._update_fonts()
        for i in self.deck: i._last_scale = 0
        for c in self.grid.values(): 
            if c: c._last_scale = 0
        if self.hand: self.hand._last_scale = 0
        for (r, c), card in self.grid.items():
            if card: card.target_pos = self._get_pos(r, c); card.pos = pygame.Vector2(card.target_pos)
        if self.hand:
            s, sw, sh = self.scaling_manager.scale, *self.screen.get_size()
            dx, dy = sw - 140 * s, sh - 180 * s
            self.hand.target_pos = pygame.Vector2(dx + (CELL_WIDTH * s / 2), dy - 5 * s); self.hand.pos = pygame.Vector2(self.hand.target_pos)

    def _init_deck(self, path: Path):
        values = ["ace","two","three","four","five","six","seven","eight","nine","ten","jack","queen","king"]
        suits = ["hearts", "diamonds", "clubs", "spades"]; bk = pygame.image.load(str(path / "card_back_red.png")).convert_alpha()
        for i, vn in enumerate(values):
            for suit in suits:
                f = path / f"card_{vn}_{suit}.png"
                if f.exists(): self.deck.append(Card(i + 1, suit, pygame.image.load(str(f)).convert_alpha(), bk))

    def _get_pos(self, r: int, c: int) -> pygame.Vector2:
        sw, sh = self.screen.get_size(); s = self.scaling_manager.scale
        # Centratura griglia senza sidebar
        gx = (sw - (CELL_WIDTH + SPACING) * 4 * s) // 2 + (CELL_WIDTH * s // 2)
        gy = (sh - (CELL_HEIGHT + SPACING) * 4 * s) // 2 + (CELL_HEIGHT * s // 2) + 50 * s
        return pygame.Vector2(gx + c * (CELL_WIDTH + SPACING) * s, gy + r * (CELL_HEIGHT + SPACING) * s)

    def _auto_draw(self):
        if not self.deck or self.hand or self._is_grid_full() or self.phase != "PLAYING": return
        s, sw, sh = self.scaling_manager.scale, *self.screen.get_size(); dx, dy = sw - 140 * s, sh - 220 * s
        self.hand = self.deck.pop(); cp = pygame.Vector2(dx + (CELL_WIDTH*s/2), dy + (CELL_HEIGHT*s/2))
        self.hand.start_flip(cp, pygame.Vector2(dx + (CELL_WIDTH*s/2), dy - 5*s))
        if self.audio_manager: self.audio_manager.play_sfx(self.sfx_click)

    def _is_grid_full(self) -> bool:
        return all(self.grid[(r,c)] is not None for r in range(4) for c in range(4))

    def handle_event(self, event: pygame.event.Event):
        if event.type == EV_FINISH: 
            self.finish({"success": self.phase != "LOSE", "score": self.total_score}); return
        
        if self.phase == "SUMMARY":
            if event.type == pygame.MOUSEBUTTONDOWN:
                pygame.time.set_timer(EV_FINISH, 100)
            return

        if self.phase != "PLAYING" or self.lose_delay_timer > 0: return
        if event.type != pygame.MOUSEBUTTONDOWN: return
        
        mx, my = event.pos; s = self.scaling_manager.scale
        for (r, c) in self.grid.keys():
            p = self._get_pos(r, c); rect = pygame.Rect(0, 0, CELL_WIDTH * s, CELL_HEIGHT * s); rect.center = (int(p.x), int(p.y))
            if rect.collidepoint(mx, my):
                if self.hand:
                    if self._place_test(self.hand, r, c):
                        self.grid[(r, c)] = self.hand; self.hand.target_pos = p; self.hand.anim_t = 0; self.score += 50
                        self.hand = None
                        if self._is_grid_full(): 
                            self.matching_mode = True; self.phase_banner_t = 2.0
                            if self.audio_manager: self.audio_manager.play_sfx(self.sfx_match_start)
                        else: self._auto_draw()
                        self._check_win()
                    else:
                        # ERRORE: Slot non compatibile
                        self.error_pulse_t = 0.5
                        if self.audio_manager: self.audio_manager.play_sfx(self.sfx_error) # ai_action.wav
                    return
                # Matching Logic
                if self.matching_mode:
                    card = self.grid[(r, c)]
                    if card and not card.is_royal:
                        if card.value == 10:
                            card.start_vanish(); self.vanishing.append(card); self.grid[(r, c)] = None; self.score += 150
                            if self.audio_manager: self.audio_manager.play_sfx(self.sfx_score)
                            self.selected.clear(); self._check_matching_finished(); return
                        if (r, c) in self.selected: self.selected.remove((r, c))
                        else: 
                            self.selected.append((r, c)); self._try_scart_pairs()
                            if self.audio_manager: self.audio_manager.play_sfx(self.sfx_click)
                    return

    def _place_test(self, card: Card, r: int, c: int) -> bool:
        if self.grid[(r, c)]: return False
        if not card.is_royal: return True
        val = card.value
        if val == 13: return (r, c) in K_SLOTS
        if val == 12: return (r, c) in Q_SLOTS
        if val == 11: return (r, c) in J_SLOTS
        return False

    def _try_scart_pairs(self):
        if len(self.selected) == 2:
            p1, p2 = self.selected; v1, v2 = self.grid[p1], self.grid[p2]
            if v1.value + v2.value == 10:
                v1.start_vanish(); v2.start_vanish(); self.vanishing.extend([v1, v2]); self.grid[p1] = self.grid[p2] = None; self.score += 200
                if self.audio_manager: self.audio_manager.play_sfx(self.sfx_score)
            else:
                self.error_pulse_t = 0.5
                if self.audio_manager: self.audio_manager.play_sfx(self.sfx_error)
            self.selected.clear(); self._check_matching_finished()

    def _check_matching_finished(self):
        numerics = [(r, c) for (r, c), card in self.grid.items() if card and not card.is_royal]
        moves = any(self.grid[p].value == 10 for p in numerics) or any(self.grid[p1].value + self.grid[p2].value == 10 for i, p1 in enumerate(numerics) for p2 in numerics[i+1:])
        if not moves: self.matching_mode = False; self._auto_draw()

    def _check_win(self):
        royals_count = sum(1 for p in (K_SLOTS+Q_SLOTS+J_SLOTS) if self.grid[p] and self.grid[p].is_royal)
        if royals_count == 12 and not self.deck and not self.hand:
            if all(not self.grid[p] or self.grid[p].is_royal for p in self.grid):
                self.phase = "WIN"; self.timer_anim = 0
                self.time_bonus = max(0, int((180 - self.game_time) * 10))
                self.total_score = self.score + self.time_bonus + 1000
                if self.audio_manager: self.audio_manager.play_sfx(self.sfx_victory)
                for _ in range(60): self.particles.append(Particle(self.screen.get_width()//2, self.screen.get_height()//2, GOLD))

    def update(self, dt: float):
        self.timer_anim += dt
        if self.phase == "PLAYING" and self.lose_delay_timer <= 0:
            self.game_time += dt

        if self.phase_banner_t > 0: self.phase_banner_t -= dt
        if self.error_pulse_t > 0: self.error_pulse_t -= dt * 2.0
            
        if self.lose_delay_timer > 0:
            self.lose_delay_timer -= dt
            if self.lose_delay_timer <= 0:
                self.phase = "LOSE"; self.timer_anim = 0
                if self.audio_manager: self.audio_manager.play_sfx(self.sfx_lose)
                pygame.time.set_timer(EV_FINISH, 5000)

        for c in self.grid.values(): 
            if c: c.update(dt, self.phase)
        if self.hand: self.hand.update(dt, self.phase)
        for v in self.vanishing[:]: 
            v.update(dt); 
            if v.vanish_t >= 1.0: self.vanishing.remove(v)
        if self.phase == "PLAYING" and self.lose_delay_timer <= 0: self._evaluate_stallo()
        for p in self.particles[:]:
            p.update(dt); 
            if p.life <= 0: self.particles.remove(p)
        if self.phase == "WIN":
            self.castle_alpha = min(255, self.castle_alpha + dt * 100)
            if self.castle_alpha >= 255: self.phase = "SUMMARY"

    def _evaluate_stallo(self):
        if self.deck or self.hand or self.matching_mode:
            if self.hand:
                can_place = any(self._place_test(self.hand, r, c) for r in range(4) for c in range(4))
                if not can_place and not self._is_grid_full(): self.lose_delay_timer = 2.0
            return
        if not self.deck and not self.hand:
            if not self._is_grid_full() or not self.matching_mode: self.lose_delay_timer = 1.0

    def draw(self):
        self.screen.fill((5, 5, 12))
        sw, sh = self.screen.get_size(); s = self.scaling_manager.scale
        
        # --- HUD UNIFICATA (LOGO CRYSTAL) ---
        title_text = self._("mg_title").upper()
        self._draw_logo_text(title_text, 50*s, 15*s, s, self.f_tit, CYAN)
        
        # Istruzioni (Super Slim Column)
        y_instr = 75*s; max_w = 210*s
        for line in [self._("tower_instr_1"), self._("tower_instr_2")]:
            words = line.split(' '); cur_line = ""
            for w in words:
                test_line = cur_line + w + " "
                if self.f_side.size(test_line)[0] < max_w: cur_line = test_line
                else:
                    self.screen.blit(self.f_side.render(cur_line, True, (130, 130, 160)), (50*s, y_instr)); y_instr += 18*s; cur_line = w + " "
            self.screen.blit(self.f_side.render(cur_line, True, (130, 130, 160)), (50*s, y_instr)); y_instr += 25*s
            
        # Punti & Deck (Top Right)
        score_label = self._('tower_score_label', 'SCORE')
        score_str = f"{score_label}: {self.score}"
        st = self.f_ui.render(score_str, True, GOLD)
        self.screen.blit(st, (sw - st.get_width() - 40*s, 25*s))
        
        deck_label = self._('tower_deck_label', 'DECK')
        deck_str = f"{deck_label}: {len(self.deck)}"
        dt = self.f_ui.render(deck_str, True, (160, 160, 220))
        self.screen.blit(dt, (sw - dt.get_width() - 40*s, 60*s))
        
        for (r, c) in self.grid.keys():
            p = self._get_pos(r, c); rect = pygame.Rect(0, 0, CELL_WIDTH * s, CELL_HEIGHT * s); rect.center = (int(p.x), int(p.y))
            glow = abs(math.sin(self.timer_anim * 5)) if self.matching_mode else 0
            sc = (35 + 25*glow, 35 + 25*glow, 50 + 40*glow) if self.matching_mode else (20, 20, 28)
            pygame.draw.rect(self.screen, sc, rect, border_radius=int(10 * s))
            if self.matching_mode: pygame.draw.rect(self.screen, CYAN, rect, int(2*s), border_radius=int(10*s))
            card = self.grid[(r, c)]
            if card: card.draw(self.screen, s, is_sel=((r, c) in self.selected))
        for v in self.vanishing: v.draw(self.screen, s)
        if self.deck:
            dp = (sw - 140 * s, sh - 250 * s) # Spostato più in alto (sh - 250 invece di 180)
            for i in range(min(4, len(self.deck))):
                bk = pygame.transform.smoothscale(self.deck[0].back, (int(CELL_WIDTH * s), int(CELL_HEIGHT * s)))
                self.screen.blit(bk, (int(dp[0] - i * 2), int(dp[1] - i * 2)))

        if self.hand:
            # Passiamo l'impulso errore se la carta è in mano
            ep = max(0, self.error_pulse_t) if self.error_pulse_t > 0 else 0
            self.hand.draw(self.screen, s, err_pulse=ep)

        for p in self.particles: pygame.draw.circle(self.screen, p.color, (int(p.pos.x), int(p.pos.y)), int(3*s))
        
        # Timer in basso a destra
        if self.phase == "PLAYING":
            t_label = self._("tower_time_label", "TIME")
            t_str = f"{t_label}: {int(self.game_time)}s"
            ts = self.f_ui.render(t_str, True, (200, 200, 255) if self.game_time < 120 else (255, 100, 100))
            self.screen.blit(ts, (sw - ts.get_width() - 40*s, sh - ts.get_height() - 25*s))

        if self.phase_banner_t > 0: self._draw_comic_banner("MATCH PHASE!", sw//2, sh//2, s, self.phase_banner_t)

        if self.phase == "LOSE":
            ov = pygame.Surface((sw, sh), pygame.SRCALPHA); ov.fill((0, 0, 0, 160)); self.screen.blit(ov, (0, 0))
            self._draw_comic_banner("GAME OVER", sw//2, sh//2, s, life=1.0)
        if self.castle_alpha > 0 and self.castle_img:
            ci = pygame.transform.smoothscale(self.castle_img, (sw, sh)); ci.set_alpha(int(self.castle_alpha)); self.screen.blit(ci, (0, 0))
            if self.phase == "WIN": self._draw_comic_banner(self._("tower_win"), sw//2, sh//2, s, life=1.0)
        
        if self.phase == "SUMMARY": self._draw_summary(sw, sh, s)

    def _draw_summary(self, sw, sh, s):
        ov = pygame.Surface((sw, sh), pygame.SRCALPHA); ov.fill((0, 0, 0, 220)); self.screen.blit(ov, (0, 0))
        self._draw_comic_banner("RESULTS", sw//2, sh//2 - 150*s, s, life=2.0)
        
        y = sh//2 - 50*s
        items = [("BASE SCORE:", self.score), ("TIME BONUS:", self.time_bonus), ("WIN BONUS:", 1000), ("TOTAL:", self.total_score)]
        for i, (label, val) in enumerate(items):
            c = GOLD if "TOTAL" in label else (255, 255, 255)
            fs = int(24*s) if "TOTAL" not in label else int(32*s)
            font = pygame.font.SysFont("Impact", fs)
            # Shadow
            self.screen.blit(font.render(f"{label} {val}", True, (0,0,0)), (sw//2 - 198*s, y + 2*s))
            self.screen.blit(font.render(f"{label} {val}", True, c), (sw//2 - 200*s, y))
            y += 50*s
        
        msg = pygame.font.SysFont("Verdana", int(18*s), italic=True).render("CLICK TO CONTINUE", True, (200, 200, 200))
        self.screen.blit(msg, (sw//2 - msg.get_width()//2, sh - 60*s))

    def _draw_comic_banner(self, text, x, y, s, life=1.0):
        t = self.timer_anim; al = 255; sc = 1.0; rot = 0
        if life < 2.0:
             sc = 0.5 + (2.0 - life) * 3.0 if (2.0 - life) < 0.5 else 2.0 + math.sin(t*15)*0.1
             rot = math.sin(t * 10) * 5; al = int(255 * min(1.0, life * 2))
        else:
             sc = 1.8 + math.sin(t*10)*0.05; rot = math.sin(t*5)*2
        for dx, dy in [(-3,-3),(3,-3),(-3,3),(3,3),(0,-4),(0,4),(-4,0),(4,0)]:
            ts = self.f_banner.render(text, True, (0, 0, 0)); ts.set_alpha(al)
            rt = pygame.transform.rotozoom(ts, rot, sc); self.screen.blit(rt, (x - rt.get_width()//2 + dx*s, y - rt.get_height()//2 + dy*s))
        c = COMIC_YELLOW if (t * 20) % 2 < 1 else COMIC_ORANGE
        if "GAME OVER" in text: c = ARCADE_RED if (t * 20) % 2 < 1 else (255, 255, 255)
        ts_color = self.f_banner.render(text, True, c); ts_color.set_alpha(al)
        rt = pygame.transform.rotozoom(ts_color, rot, sc); self.screen.blit(rt, (x - rt.get_width()//2, y - rt.get_height()//2))

    def _draw_logo_text(self, text, x, y, s, font, color):
        # Outline 1px per massima nitidezza
        for dx, dy in [(-1,-1), (1,-1), (-1,1), (1,1)]:
            ts = font.render(text, True, (0, 0, 0))
            self.screen.blit(ts, (int(x + dx*s), int(y + dy*s)))
        self.screen.blit(font.render(text, True, color), (int(x), int(y)))
