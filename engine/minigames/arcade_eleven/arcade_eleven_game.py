"""
engine/minigames/arcade_eleven/arcade_eleven_game.py

Un gioco di carte dinamico basato sulla logica della somma a 11.
Design Premium: Neon effects, Smooth animations, Glassmorphism.
"""

import random
import math
import pygame
from pathlib import Path
from typing import List, Optional, Tuple
from engine.minigames.minigame_base import BaseMinigame
from engine.utils import get_logger, get_resource_path

log = get_logger(__name__)

# Costanti Comic Style (Sincronizzate con Tower)
ARCADE_RED = (255, 30, 80)
COMIC_YELLOW = (255, 240, 0)
COMIC_ORANGE = (255, 140, 0)
GOLD = (255, 215, 0)

class AEParticle:
    """Particella neon per feedback visivo gratificante."""
    def __init__(self, pos: pygame.Vector2, color: Tuple[int, int, int]):
        self.pos = pygame.Vector2(pos)
        angle = random.uniform(0, math.pi * 2)
        speed = random.uniform(150, 400)
        self.vel = pygame.Vector2(math.cos(angle) * speed, math.sin(angle) * speed)
        self.alpha = 255
        self.color = color
        self.size = random.uniform(2, 4)
        self.gravity = 400

    def update(self, dt: float) -> bool:
        self.vel.y += self.gravity * dt
        self.pos += self.vel * dt
        self.alpha -= 600 * dt
        return self.alpha > 0

    def draw(self, screen: pygame.Surface, s: float):
        if self.alpha <= 0: return
        # Arrotondamento per prevenire jittering
        draw_x = int(round(self.pos.x))
        draw_y = int(round(self.pos.y))
        size = int(round(self.size * s))
        if size < 1: size = 1
        
        surf = pygame.Surface((size * 2, size * 2), pygame.SRCALPHA)
        pygame.draw.circle(surf, (*self.color, int(self.alpha)), (size, size), size)
        screen.blit(surf, (draw_x - size, draw_y - size))

class Card:
    """Rappresentazione Premium di una carta da gioco."""
    WIDTH = 120
    HEIGHT = 170

    def __init__(self, rank: str, suit: str, value: int, front_surf: pygame.Surface, back_surf: pygame.Surface):
        self.rank = rank
        self.suit = suit
        self.value = value # 1-10 per numeri, 11=J, 12=Q, 13=K
        self.front_surf = pygame.transform.smoothscale(front_surf, (self.WIDTH, self.HEIGHT))
        self.back_surf = pygame.transform.smoothscale(back_surf, (self.WIDTH, self.HEIGHT))
        
        self.pos = pygame.Vector2(0, 0)
        self.target_pos = pygame.Vector2(0, 0)
        self.scale = 0.1 
        self.target_scale = 1.0
        self.alpha = 0
        self.target_alpha = 255
        
        self.rot_y = 180.0  # Inizia coperta
        self.target_rot_y = 180.0
        
        self.is_selected = False
        self.is_hovered = False
        self.is_removing = False
        self.is_entering = True
        
        # Animazione
        self.vibrato = 0.0
        self.hover_scale_bonus = 0.0
        self.hover_lift = 0.0
        self.anim_speed = 8.0
        self.entry_delay = 0.0
        
        self.flip_t = 1.0 # 0.0 to 1.0 per l'arco di salto
        self.is_flipping = False
        self.error_pulse = 0.0

    def update(self, dt: float):
        if self.entry_delay > 0:
            self.entry_delay -= dt
            return

        # Movimento fluido (Lerp)
        lerp_factor = self.anim_speed * dt
        if self.pos.distance_to(self.target_pos) > 0.5:
            self.pos += (self.target_pos - self.pos) * lerp_factor
        else:
            self.pos = pygame.Vector2(self.target_pos)
            self.is_entering = False

        # Scala, Alpha e Lift dinamico
        target_bonus = 0.1 if self.is_hovered else 0.0
        target_lift = -20.0 if self.is_hovered else 0.0
        
        self.hover_scale_bonus += (target_bonus - self.hover_scale_bonus) * lerp_factor
        self.hover_lift += (target_lift - self.hover_lift) * lerp_factor
        
        self.scale += (self.target_scale + self.hover_scale_bonus - self.scale) * lerp_factor
        self.alpha += (self.target_alpha - self.alpha) * lerp_factor
        
        # Animazione rotazione 3D simulata
        self.rot_y += (self.target_rot_y - self.rot_y) * lerp_factor

        if self.is_selected:
            self.vibrato += dt * 15
        else:
            self.vibrato = 0

        # Gestione arco di salto e pulsazione errore
        if self.is_flipping:
            self.flip_t = min(1.0, self.flip_t + dt * 3.5)
            if self.flip_t >= 1.0: self.is_flipping = False
            
        if self.error_pulse > 0:
            self.error_pulse -= dt * 2.5

    def draw(self, screen: pygame.Surface, s: float, shake_off=(0, 0)):
        if self.entry_delay > 0: return
        
        scaled_w = int(self.WIDTH * self.scale * s)
        scaled_h = int(self.HEIGHT * self.scale * s)
        
        if scaled_w < 1 or scaled_h < 1: return

        off_x = math.sin(self.vibrato) * 3 * s if self.is_selected else 0
        # Applicazione lift con arrotondamento
        render_pos = (int(round(self.pos.x + off_x + shake_off[0])), 
                      int(round(self.pos.y + shake_off[1] + self.hover_lift * s)))
        
        # Simulazione Flip 3D (angolo e scala orizzontale)
        rad = math.radians(self.rot_y)
        flip_scale = abs(math.cos(rad))
        
        # Calcolo salto dinamico
        jump_y = -60 * math.sin(self.flip_t * math.pi) * s if self.is_flipping else 0
        
        # Selezione faccia in base all'angolo
        actual_surf = self.front_surf if abs(math.cos(rad)) == math.cos(rad) else self.back_surf
        
        # Effetto Errore (Pulse & Glow)
        final_scale = self.scale + self.error_pulse * 0.2
        current_w = max(1, int(self.WIDTH * final_scale * s * flip_scale))
        current_h = int(self.HEIGHT * final_scale * s)
        
        final_surf = pygame.transform.smoothscale(actual_surf, (current_w, current_h))
        if self.error_pulse > 0:
            glow = pygame.Surface(final_surf.get_size(), pygame.SRCALPHA)
            glow.fill((255, 30, 80, int(150 * self.error_pulse)))
            final_surf.blit(glow, (0,0), special_flags=pygame.BLEND_RGBA_ADD)

        if self.alpha < 250:
            final_surf.set_alpha(int(self.alpha))
            
        rect = final_surf.get_rect(center=(render_pos[0], render_pos[1] + int(jump_y)))
        
        # --- ORDINE DI DISEGNO CORRETTO ---
        
        # 1. Ombra dinamica (più profonda se sollevata)
        shadow_rect = rect.copy()
        shadow_off = (6 + abs(self.hover_lift)*0.2) * s
        shadow_rect.x += shadow_off
        shadow_rect.y += shadow_off
        # Se la carta è "di taglio" (flip_scale vicino a 0), l'ombra deve sparire
        if flip_scale > 0.1:
            pygame.draw.rect(screen, (0, 0, 0, 70), shadow_rect, border_radius=10)

        # 2. Glow reattivo (ora dietro la carta)
        if (self.is_selected or self.is_hovered) and flip_scale > 0.5:
            glow_color = (0, 255, 255) if self.is_selected else (220, 255, 255)
            glow_range = int((10 if self.is_hovered and not self.is_selected else 15) * flip_scale)
            
            if glow_range > 0:
                glow_surf = pygame.Surface((current_w + glow_range*2, scaled_h + glow_range*2), pygame.SRCALPHA)
                for i in range(glow_range):
                    a = (180 if self.is_selected else 100) - i * (180 // glow_range)
                    pygame.draw.rect(glow_surf, (*glow_color, max(0, a)), 
                                     (i, i, glow_surf.get_width() - i*2, glow_surf.get_height() - i*2), 
                                     3, border_radius=15)
                screen.blit(glow_surf, (rect.x - glow_range, rect.y - glow_range))

        # 3. Carta finale
        screen.blit(final_surf, rect)

class ArcadeElevenGame(BaseMinigame):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.deck: List[Card] = []
        self.grid: List[Optional[Card]] = [None] * 12 
        self.selected_indices: List[int] = []
        self.score = 0
        self.particles: List[AEParticle] = []
        
        self.phase = "START" 
        self.timer = 0.0
        self.intro_alpha = 255
        
        # Effetti
        self.shake_energy = 0.0
        self.neon_cycle = 0.0
        
        # Suoni con Path OS (compatibility PyInstaller)
        self._sfx_click = get_resource_path("engine", "minigames", "tower", "sounds", "click.wav")
        self._sfx_win = get_resource_path("engine", "minigames", "tower", "sounds", "victory.mp3")
        self._sfx_error = get_resource_path("engine", "minigames", "tower", "sounds", "ai_action.wav")
        self._sfx_lose = get_resource_path("engine", "minigames", "tower", "sounds", "error4.mp3")
        self._sfx_score = get_resource_path("engine", "minigames", "tower", "sounds", "score.mp3")
        self._sfx_match = get_resource_path("engine", "minigames", "tower", "sounds", "bling5.mp3")
        
        
        self.bg_surf: Optional[pygame.Surface] = None
        self.timer_anim = 0.0
        self.game_time = 0.0
        self.time_bonus, self.total_score = 0, 0
        self.f_comic = None

    def start(self) -> None:
        self.load_local_strings(get_resource_path("engine", "minigames", "arcade_eleven", "strings"))
        self._load_cards()
        self._setup_grid_positions()
        self._fill_grid(initial=True)
        self.timer = 5.0 
        
        # Caricamento Background Tematico (Aspect Fill/Cover per evitare stretching)
        try:
            bg_path = get_resource_path("engine", "minigames", "arcade_eleven", "background.png")
            if bg_path.exists():
                raw_bg = pygame.image.load(str(bg_path)).convert()
                sw, sh = self.screen.get_size()
                ow, oh = raw_bg.get_size()
                
                # Calcolo scaling factor per riempire lo schermo (Cover logic)
                scale = max(sw / ow, sh / oh)
                new_size = (int(ow * scale), int(oh * scale))
                scaled_bg = pygame.transform.smoothscale(raw_bg, new_size)
                
                # Ritaglio centrale
                self.bg_surf = pygame.Surface((sw, sh))
                off_x = (new_size[0] - sw) // 2
                off_y = (new_size[1] - sh) // 2
                self.bg_surf.blit(scaled_bg, (0, 0), (off_x, off_y, sw, sh))
                
                # Applichiamo un leggero scurimento per far risaltare le carte neon
                darken = pygame.Surface((sw, sh), pygame.SRCALPHA)
                darken.fill((0, 0, 0, 70))
                self.bg_surf.blit(darken, (0, 0))
        except Exception as e:
            log.error(f"Errore caricamento background: {e}")

        # Inizializzazione Font Comic
        s = self.scaling_manager.scale
        self.f_comic = pygame.font.SysFont("Impact", int(75 * s))

    def _load_cards(self):
        asset_path = get_resource_path("engine", "minigames", "tower")
        ranks = ["ace", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "jack", "queen", "king"]
        rank_values = {"ace": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, 
                       "seven": 7, "eight": 8, "nine": 9, "ten": 10, "jack": 11, "queen": 12, "king": 13}
        suits = ["clubs", "diamonds", "hearts", "spades"]
        
        back_surf = pygame.image.load(str(asset_path / "card_back_red.png")).convert_alpha()
        
        full_deck = []
        for r in ranks:
            for s in suits:
                file_name = f"card_{r}_{s}.png"
                try:
                    front = pygame.image.load(str(asset_path / file_name)).convert_alpha()
                    card = Card(r, s, rank_values[r], front, back_surf)
                    full_deck.append(card)
                except: continue
        
        random.shuffle(full_deck)
        self.deck = full_deck

    def _setup_grid_positions(self):
        sw, sh = self.screen.get_size()
        s = self.scaling_manager.scale
        cw, ch = Card.WIDTH * s, Card.HEIGHT * s
        gap = 25 * s
        
        # Griglia posizionata centralmente ma leggermente più in alto (ora che il titolo è nell'angolo)
        start_x = sw // 2 - (4 * (cw + gap)) // 2 + (cw // 2)
        start_y = sh // 2 - (3 * (ch + gap)) // 2 + (ch // 2) + 20 * s
        
        self.grid_pos = []
        for i in range(12):
            col, row = i % 4, i // 4
            self.grid_pos.append(pygame.Vector2(start_x + col * (cw + gap), 
                                               start_y + row * (ch + gap)))

    def _fill_grid(self, initial=False):
        for i in range(12):
            if self.grid[i] is None and self.deck:
                card = self.deck.pop(0)
                # Entrata da sotto con delay e rotazione iniziale
                card.pos = pygame.Vector2(self.grid_pos[i].x, self.screen.get_height() + 200)
                card.target_pos = pygame.Vector2(self.grid_pos[i])
                card.rot_y = 180.0
                card.target_rot_y = 0.0
                card.flip_t = 0.0
                card.is_flipping = True
                
                if initial:
                    card.entry_delay = i * 0.08
                else:
                    card.entry_delay = 0.1
                self.grid[i] = card

    def _check_game_over(self) -> bool:
        present = [c for c in self.grid if c is not None]
        if not present and not self.deck: return False 
        
        # Somma 11
        nums = [c for c in present if c.value <= 10]
        for i in range(len(nums)):
            for j in range(i + 1, len(nums)):
                if nums[i].value + nums[j].value == 11: return False
                
        # Tris Reale (un J, una Q, un K sulla griglia)
        vals = {c.value for c in present if c.value > 10}
        if {11, 12, 13}.issubset(vals): return False
            
        return True

    def handle_event(self, event: pygame.event.Event) -> None:
        if self.phase == "START":
            if event.type in [pygame.MOUSEBUTTONDOWN, pygame.KEYDOWN]:
                self.phase = "PLAY"
            return
            
        if self.phase == "SUMMARY":
            if event.type == pygame.MOUSEBUTTONDOWN:
                self.finish({"success": True, "score": self.total_score})
            return

        if self.phase != "PLAY": return

        if event.type == pygame.MOUSEBUTTONDOWN:
            mx, my = event.pos
            s = self.scaling_manager.scale
            clicked_any = False
            for i, card in enumerate(self.grid):
                if card and not card.is_entering:
                    rect = pygame.Rect(0, 0, Card.WIDTH * s, Card.HEIGHT * s)
                    rect.center = (int(card.pos.x), int(card.pos.y))
                    if rect.collidepoint(mx, my):
                        self._toggle_selection(i)
                        clicked_any = True
                        break
            
            if not clicked_any:
                self._reset_selection()

    def _toggle_selection(self, idx: int):
        card = self.grid[idx]
        if not card or card.is_entering: return

        if idx in self.selected_indices:
            self.selected_indices.remove(idx)
            card.is_selected = False
            card.target_scale = 1.0
        else:
            # BLOCCO SELEZIONE: Max 3 carte totali
            if len(self.selected_indices) >= 3:
                self._reset_selection(error=True)
                return
            
            self.selected_indices.append(idx)
            card.is_selected = True
            card.target_scale = 1.2
            if self.audio_manager: self.audio_manager.play_sfx(self._sfx_click)
        
        self._validate_move()

    def _validate_move(self):
        sel = [self.grid[i] for i in self.selected_indices if self.grid[i]]
        
        # Logica rigorosa per Numeri (max 2) e Figure (max 3)
        if len(sel) == 2:
            num_cards = [c for c in sel if c.value <= 10]
            figure_cards = [c for c in sel if c.value > 10]
            
            # Se abbiamo 2 numeri, controlliamo la somma subito
            if len(num_cards) == 2:
                if sum(c.value for c in num_cards) == 11:
                    self._resolve_match(points=50)
                else:
                    self._reset_selection(error=True)
                    self.shake_energy = 5.0
            # Se abbiamo 1 numero e 1 figura, è un errore (non possono stare insieme)
            elif len(num_cards) > 0 and len(figure_cards) > 0:
                self._reset_selection(error=True)
                self.shake_energy = 5.0
        
        elif len(sel) == 3:
            # Regola Tris Reale: J + Q + K (valori 11, 12, 13)
            vals = {c.value for c in sel}
            if vals == {11, 12, 13}:
                self._resolve_match(points=150)
            else:
                # Qualsiasi altro tris (3 Jack, 2 Figure e 1 numero, etc) è errore
                self._reset_selection(error=True)
                self.shake_energy = 8.0

    def _resolve_match(self, points: int):
        # Burst di particelle: Oro per Tris Reale, Ciano per Somma 11
        burst_color = (255, 215, 0) if points > 50 else (0, 255, 255)
        
        for idx in self.selected_indices:
            c = self.grid[idx]
            if c:
                # Generazione esplosione
                for _ in range(20):
                    self.particles.append(AEParticle(c.pos, burst_color))
                
                c.target_alpha = 0
                c.target_scale = 0.5
                c.target_pos.y -= 300 
                c.is_flipping = True
                c.flip_t = 0.0
                c.target_rot_y = 720.0 # Spin finale
                self.grid[idx] = None
        
        if self.audio_manager:
            self.audio_manager.play_sfx(self._sfx_match if points > 50 else self._sfx_score)
        
        self.score += points
        self.selected_indices = []
        self._fill_grid()
        
        if not any(self.grid) and not self.deck:
            self.phase = "VICTORY"
            self.timer = 4.0
            self.time_bonus = max(0, int((120 - self.game_time) * 15))
            self.total_score = self.score + self.time_bonus + 1000
            if self.audio_manager: self.audio_manager.play_sfx(self._sfx_win)
        elif self._check_game_over():
            self.phase = "GAME_OVER"
            self.total_score = 0 # No punti se perdi
            self.timer = 5.0
            self.shake_energy = 25.0 
            if self.audio_manager: self.audio_manager.play_sfx(self._sfx_lose)

    def _reset_selection(self, error=False):
        if error and self.audio_manager: 
            self.audio_manager.play_sfx(self._sfx_error)
            
        for idx in self.selected_indices:
            if idx < len(self.grid) and self.grid[idx]:
                card_err = self.grid[idx]
                card_err.is_selected = False
                card_err.target_scale = 1.0
                if error:
                    card_err.error_pulse = 1.0
        self.selected_indices = []

    def update(self, dt: float) -> None:
        mx, my = pygame.mouse.get_pos()
        s = self.scaling_manager.scale
        
        # Update carte e hover detection
        for c in self.grid:
            if c: 
                # Hover check
                rect = pygame.Rect(0, 0, Card.WIDTH * s, Card.HEIGHT * s)
                rect.center = (int(round(c.pos.x)), int(round(c.pos.y)))
                c.is_hovered = rect.collidepoint(mx, my) and not c.is_entering
                c.update(dt)
            
        # Update particelle
        self.particles = [p for p in self.particles if p.update(dt)]
            
        if self.phase == "START":
            self.intro_alpha = 255
        elif self.phase == "PLAY":
            self.intro_alpha = max(0, self.intro_alpha - dt * 400)
            self.game_time += dt
        elif self.phase == "VICTORY":
            self.timer -= dt
            if self.timer <= 0: self.phase = "SUMMARY"
        else:
            self.timer -= dt
            if self.timer <= 0:
                self.finish({"success": self.phase == "VICTORY", "score": self.total_score})

        if self.shake_energy > 0:
            self.shake_energy -= dt * 20
        else:
            self.shake_energy = 0

        self.neon_cycle += dt * 2
        self.timer_anim += dt

    def draw(self) -> None:
        sw, sh = self.screen.get_size()
        s = self.scaling_manager.scale
        
        shake_x = random.uniform(-self.shake_energy, self.shake_energy) * s
        shake_y = random.uniform(-self.shake_energy, self.shake_energy) * s
        shake_off = (shake_x, shake_y)

        # Background
        if self.bg_surf:
            self.screen.blit(self.bg_surf, (0, 0))
        else:
            for i in range(sh):
                c = (15 + i//40, 15 + i//70, 35 + i//30)
                pygame.draw.line(self.screen, c, (0, i), (sw, i))
            
        # Particelle
        for p in self.particles:
            p.draw(self.screen, s)

        # Carte
        for c in self.grid:
            if c: c.draw(self.screen, s, shake_off)

        # HUD - Titolo Neon in alto a sinistra
        self.f_tit = pygame.font.SysFont("Verdana", int(28 * s), bold=True)
        self.f_ui = pygame.font.SysFont("Impact", int(22 * s))
        
        # Disegno Titolo con Stile Crystal (Unificato - Titolo Statico)
        title_text = self._("mg_title", "ARCADE ELEVEN").upper()
        self._draw_logo_text(title_text, 50*s, 15*s, s, self.f_tit, (0, 255, 255))
        
        
        # Punti - In alto a destra
        score_label = self._("arcade_eleven_score", "SCORE")
        score_text = f"{score_label}: {self.score}"
        score_surf = self.f_ui.render(score_text, True, GOLD) # Usiamo GOLD per uniformità
        self.screen.blit(score_surf, (sw - score_surf.get_width() - 40 * s + shake_x, 25 * s + shake_y))

        # Timer - In basso a destra
        if self.phase == "PLAY":
            t_label = self._("arcade_eleven_time_label", "TIME")
            time_text = f"{t_label}: {int(self.game_time)}s"
            t_color = (200, 200, 255) if self.game_time < 60 else (255, 100, 100)
            time_surf = self.f_ui.render(time_text, True, t_color)
            self.screen.blit(time_surf, (sw - time_surf.get_width() - 40 * s + shake_x, sh - time_surf.get_height() - 25 * s + shake_y))
        
        # Overlays
        if self.intro_alpha > 0:
            overlay = pygame.Surface((sw, sh), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, int(self.intro_alpha * 0.7)))
            
            p_w, p_h = 800 * s, 350 * s
            panel_rect = pygame.Rect(sw//2 - p_w//2, sh//2 - p_h//2, p_w, p_h)
            
            # Pannello Glassmorphism Premium
            pygame.draw.rect(overlay, (20, 40, 60, 180), panel_rect, border_radius=20)
            pygame.draw.rect(overlay, (0, 255, 255, 120), panel_rect, 2, border_radius=20)
            
            instr_font = pygame.font.SysFont("Segoe UI", int(26 * s))
            
            # --- SISTEMA DI WRAPPING TESTO ---
            text = self._("arcade_eleven_instructions")
            words = text.split(' ')
            lines = []
            current_line = []
            
            max_w = p_w - 80 * s
            for word in words:
                test_line = ' '.join(current_line + [word])
                w, _ = instr_font.size(test_line)
                if w < max_w:
                    current_line.append(word)
                else:
                    lines.append(' '.join(current_line))
                    current_line = [word]
            lines.append(' '.join(current_line))
            
            # Renderizzazione righe centrate
            y_off = sh // 2 - (len(lines) * 35 * s) // 2 - 20 * s
            for line in lines:
                line_surf = instr_font.render(line, True, (255, 255, 255))
                overlay.blit(line_surf, (sw//2 - line_surf.get_width()//2, y_off))
                y_off += 40 * s
            
            # Messaggio pulsante
            msg_font = pygame.font.SysFont("Segoe UI", int(22 * s), italic=True, bold=True)
            pulsate = abs(math.sin(pygame.time.get_ticks() * 0.005))
            msg_color = (200 + 55 * pulsate, 200 + 55 * pulsate, 200 + 55 * pulsate)
            msg = msg_font.render(self._("arcade_eleven_click_to_start"), True, msg_color)
            overlay.blit(msg, (sw//2 - msg.get_width()//2, sh//2 + 100 * s))
            
            self.screen.blit(overlay, (0, 0))

        if self.phase == "VICTORY":
            self._draw_comic_overlay(self._("arcade_eleven_win"), COMIC_YELLOW)
        elif self.phase == "GAME_OVER":
            if self.timer < 3.5:
                self._draw_comic_overlay("GAME OVER", ARCADE_RED)
        
        if self.phase == "SUMMARY": self._draw_results_summary(sw, sh, s)

    def _draw_results_summary(self, sw, sh, s):
        ov = pygame.Surface((sw, sh), pygame.SRCALPHA); ov.fill((0, 0, 0, 220)); self.screen.blit(ov, (0, 0))
        self._draw_comic_overlay("RESULTS", COMIC_YELLOW) # Titolo in alto
        
        y = sh//2 - 50*s
        items = [("BASE SCORE:", self.score), ("SPEED BONUS:", self.time_bonus), ("WIN BONUS:", 1000), ("TOTAL:", self.total_score)]
        for i, (label, val) in enumerate(items):
            c = GOLD if "TOTAL" in label else (255, 255, 255)
            fs = int(24*s) if "TOTAL" not in label else int(32*s)
            font = pygame.font.SysFont("Impact", fs)
            self.screen.blit(font.render(f"{label} {val}", True, (0,0,0)), (sw//2 - 198*s, y + 2*s))
            self.screen.blit(font.render(f"{label} {val}", True, c), (sw//2 - 200*s, y))
            y += 50*s
        
        msg = pygame.font.SysFont("Verdana", int(18*s), italic=True).render("CLICK TO CONTINUE", True, (200, 200, 200))
        self.screen.blit(msg, (sw//2 - msg.get_width()//2, sh - 60*s))

    def _draw_logo_text(self, text, x, y, s, font, color):
        # Outline sottile e pulito per massima leggibilità
        for dx, dy in [(-1,-1), (1,-1), (-1,1), (1,1)]:
            ts = font.render(text, True, (0, 0, 0))
            self.screen.blit(ts, (int(x + dx*s), int(y + dy*s)))
        self.screen.blit(font.render(text, True, color), (int(x), int(y)))

    def _draw_comic_overlay(self, text: str, base_color: tuple):
        sw, sh = self.screen.get_size()
        s = self.scaling_manager.scale
        t = self.timer_anim
        
        # Animazione Burst / Shake (Identica a Tower)
        sc = 1.8 + math.sin(t * 10) * 0.05
        rot = math.sin(t * 5) * 2
        
        # Overlay sfondo
        overlay = pygame.Surface((sw, sh), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 180))
        self.screen.blit(overlay, (0, 0))

        # Colore Strobe
        color = base_color
        if base_color == ARCADE_RED:
            color = ARCADE_RED if (t * 20) % 2 < 1 else (255, 255, 255)
        else:
            color = COMIC_YELLOW if (t * 20) % 2 < 1 else COMIC_ORANGE

        # 1. Bordo Nero Inchiostrato (Ink Outline 8-way)
        for dx, dy in [(-3,-3), (3,-3), (-3,3), (3,3), (0,-4), (0,4), (-4,0), (4,0)]:
            ts_border = self.f_comic.render(text, True, (0, 0, 0))
            rt_border = pygame.transform.rotozoom(ts_border, rot, sc)
            self.screen.blit(rt_border, (sw//2 - rt_border.get_width()//2 + dx*s, 
                                         sh//2 - rt_border.get_height()//2 + dy*s))

        # 2. Testo Principale
        ts = self.f_comic.render(text, True, color)
        rt = pygame.transform.rotozoom(ts, rot, sc)
        self.screen.blit(rt, (sw//2 - rt.get_width()//2, sh//2 - rt.get_height()//2))
