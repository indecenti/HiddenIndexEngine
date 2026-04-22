"""
engine/results_screen.py

Versione FINAL BUG-FREE con localizzazione completa.
- Fix errore inizializzazione _fonts
- Integrazione totale self.lang()
- Layout 520px con auto-scaling
"""

import math
import random
import pygame

# Palette Premium Horror/Mystery
COLOR_BG = (10, 10, 15)
COLOR_BORDER = (60, 60, 80)
COLOR_ACCENT = (218, 165, 32)
COLOR_TEXT_DIM = (120, 120, 140)
COLOR_TEXT = (210, 210, 220)
COLOR_SUCCESS = (40, 180, 100)
COLOR_DANGER = (180, 40, 40)

BORDER_RADIUS = 12


class ResultsScreen:
    """Schermata di risultati sicura, localizzata e con effetti VHS."""

    def __init__(self, screen_w: int, screen_h: int, lang_fn, scaling_manager) -> None:
        self.screen_w = screen_w
        self.screen_h = screen_h
        self.lang = lang_fn # Funzione lang(key)
        self.scaling_manager = scaling_manager

        self.is_visible = False
        self.animation_timer = 0.0
        self.animation_duration = 0.9

        self.score = 0
        self.display_score = 0
        self.stars = 0
        self.time_elapsed = 0.0
        self.is_failed = False
        self.objects_found = 0
        self.total_objects = 0

        self.star_pop_timers = [0.0, 0.0, 0.0]
        self.star_pop_duration = 0.3

        # FIX BUG: Inizializza prima il dizionario, poi carica i font
        self._fonts = {}
        self._load_fonts()
        
        # Filtri VHS
        self._vignette_surf = self._create_vignette(screen_w, screen_h)
        self._scanlines_surf = self._create_scanlines(screen_w, screen_h)
        self._vhs_noise_bar_y = 0.0

    def _get_panel_size(self) -> tuple[int, int]:
        """Ritorna (larghezza, altezza) dinamica in base alla risoluzione corrente."""
        # Richiesta specifica: in 720p (altezza <= 720) il box deve essere più stretto
        if self.screen_h <= 720:
            return 420, 580
        return 520, 660

    def _load_fonts(self) -> None:
        title_font = "georgia"
        stat_font = "arial"
        self._fonts["title"] = pygame.font.SysFont(title_font, 34, bold=True)
        self._fonts["score"] = pygame.font.SysFont(title_font, 54, bold=True)
        self._fonts["label"] = pygame.font.SysFont(title_font, 20, italic=True)
        self._fonts["stat_val"] = pygame.font.SysFont(stat_font, 19, bold=True)
        self._fonts["stat_lbl"] = pygame.font.SysFont(stat_font, 15)
        self._fonts["btn"] = pygame.font.SysFont(stat_font, 18, bold=True)

    def _create_vignette(self, w: int, h: int) -> pygame.Surface:
        vig = pygame.Surface((w, h), pygame.SRCALPHA)
        for y in range(0, h, 12): 
            for x in range(0, w, 12):
                dx = (x - w / 2) / (w / 2)
                dy = (y - h / 2) / (h / 2)
                d = dx*dx + dy*dy
                alpha = int(min(255, d * 160))
                pygame.draw.rect(vig, (0, 0, 8, alpha), (x, y, 12, 12))
        return vig

    def _create_scanlines(self, w: int, h: int) -> pygame.Surface:
        surf = pygame.Surface((w, h), pygame.SRCALPHA)
        for y in range(0, h, 3):
            pygame.draw.line(surf, (0, 0, 0, 30), (0, y), (w, y))
        return surf

    def show(self, score: int, stars: int, time_elapsed: float,
             is_failed: bool = False, scene_name: str = "",
             objects_found: int = 0, total_objects: int = 0) -> None:
        self.is_visible = True
        self.animation_timer = 0.0
        self.score = score
        self.stars = min(3, max(0, stars))
        self.time_elapsed = time_elapsed
        self.is_failed = is_failed
        self.objects_found = objects_found
        self.total_objects = total_objects
        self.star_pop_timers = [0.0, 0.0, 0.0]

    def hide(self) -> None:
        self.is_visible = False

    def get_continue_button_rect(self, panel_x: int, panel_y: int, panel_w: int, panel_h: int) -> pygame.Rect:
        btn_h = 54
        btn_w = 200
        btn_y = panel_h - 70
        btn_x = (panel_w - btn_w) // 2
        return pygame.Rect(panel_x + btn_x, panel_y + btn_y, btn_w, btn_h)

    def check_click(self, mouse_pos: tuple[int, int]) -> bool:
        """Controlla se il click è sul pulsante 'CONTINUA', sincronizzato con l'animazione."""
        if not self.is_visible: return False
        
        # Dimensioni dinamiche basate sulla risoluzione
        panel_w, panel_h = self._get_panel_size()
        panel_x = (self.screen_w - panel_w) // 2
        panel_y = (self.screen_h - panel_h) // 2
        
        progress = min(1.0, self.animation_timer / self.animation_duration)
        # Evita click accidentali prima che il pulsante sia ben visibile
        if progress < 0.6: return False 
        
        offset_y = int(round(30 * (1.0 - math.pow(1.0 - progress, 3))))
        draw_y = (panel_y - 30) + offset_y
        
        btn_rect = self.get_continue_button_rect(panel_x, draw_y, panel_w, panel_h)
        return btn_rect.collidepoint(mouse_pos)

    def on_resize(self, w: int, h: int) -> None:
        """Rigenera i filtri grafici quando la risoluzione cambia."""
        self.screen_w = w
        self.screen_h = h
        self._vignette_surf = self._create_vignette(w, h)
        self._scanlines_surf = self._create_scanlines(w, h)

    def update(self, dt: float) -> None:
        if not self.is_visible: return
        self.animation_timer += dt
        score_prog = min(1.0, self.animation_timer / 0.6)
        self.display_score = int(self.score * score_prog)
        self._vhs_noise_bar_y += 180 * dt
        if self._vhs_noise_bar_y > self.screen_h: self._vhs_noise_bar_y = -50
        for i in range(3):
            delay = 0.5 + i * 0.12
            if self.animation_timer >= delay:
                self.star_pop_timers[i] = min(self.star_pop_duration, self.animation_timer - delay)

    def draw(self, surface: pygame.Surface) -> None:
        if not self.is_visible: return

        progress = min(1.0, self.animation_timer / self.animation_duration)
        alpha = int(255 * min(1.0, progress * 1.5))

        overlay = pygame.Surface((self.screen_w, self.screen_h), pygame.SRCALPHA)
        overlay.fill((5, 5, 10, int(200 * min(1.0, progress))))
        surface.blit(overlay, (0, 0))

        # Dimensioni dinamiche basate sulla risoluzione
        panel_w, panel_h = self._get_panel_size()
        panel_x = (self.screen_w - panel_w) // 2
        panel_y = (self.screen_h - panel_h) // 2
        
        # Animazione drop-down che termina perfettamente al centro
        offset_y = int(round(30 * (1.0 - math.pow(1.0 - progress, 3))))
        draw_y = (panel_y - 30) + offset_y

        panel = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)
        pygame.draw.rect(panel, (*COLOR_BG, 252), (0, 0, panel_w, panel_h), border_radius=BORDER_RADIUS)
        pygame.draw.rect(panel, COLOR_BORDER, (0, 0, panel_w, panel_h), 2, border_radius=BORDER_RADIUS)
        
        curr_y = 40
        
        # LOCALIZZAZIONE TITOLO
        t_key = "MISSION_FAILED" if self.is_failed else "MISSION_COMPLETE"
        title_str = self.lang(t_key).upper()
        t_col = COLOR_DANGER if self.is_failed else COLOR_SUCCESS
        title_surf = self._fonts["title"].render(title_str, True, t_col)
        
        if title_surf.get_width() > panel_w - 40:
            scale = (panel_w - 40) / title_surf.get_width()
            title_surf = pygame.transform.smoothscale(title_surf, (int(title_surf.get_width()*scale), int(title_surf.get_height()*scale)))
        
        panel.blit(title_surf, ((panel_w - title_surf.get_width()) // 2, curr_y))
        
        curr_y += 65
        label_score = self.lang("TOTAL_SCORE").upper()
        label_surf = self._fonts["label"].render(label_score, True, COLOR_ACCENT)
        label_surf.set_alpha(150)
        panel.blit(label_surf, ((panel_w - label_surf.get_width()) // 2, curr_y))
        
        curr_y += 35
        score_surf = self._fonts["score"].render(f"{self.display_score}", True, COLOR_ACCENT)
        if score_surf.get_width() > panel_w - 80:
             scale = (panel_w - 80) / score_surf.get_width()
             score_surf = pygame.transform.smoothscale(score_surf, (int(score_surf.get_width()*scale), int(score_surf.get_height()*scale)))
        
        panel.blit(score_surf, ((panel_w - score_surf.get_width()) // 2, curr_y))
        
        curr_y += 95
        for i in range(3):
            sx = (panel_w // 2) + (i - 1) * 100
            p_timer = self.star_pop_timers[i]
            if i < self.stars and p_timer > 0:
                pop = min(1.0, p_timer / self.star_pop_duration)
                scale = math.sin(pop * math.pi * 0.8) * 1.25 if pop < 1.0 else 1.0
                self._draw_star(panel, sx, curr_y, int(35 * scale), COLOR_ACCENT)
            else:
                self._draw_star(panel, sx, curr_y, 35, (40, 40, 50), 80)

        if self.objects_found == self.total_objects and not self.is_failed and self.total_objects > 0:
            curr_y += 65
            p_alpha = int(255 * max(0, min(1, (self.animation_timer - 1.2) * 2)))
            if p_alpha > 0:
                p_text = self._fonts["label"].render(f"— {self.lang('PERFECT_SCORE').upper()} —", True, COLOR_SUCCESS)
                p_text.set_alpha(p_alpha)
                panel.blit(p_text, ((panel_w - p_text.get_width()) // 2, curr_y))

        curr_y = panel_h - 170
        pygame.draw.line(panel, (60, 60, 75), (100, curr_y), (panel_w - 100, curr_y), 1)
        
        t_lbl = self.lang("TIME_ELAPSED")
        o_lbl = self.lang("OBJECTS_FOUND")
        
        self._draw_stat(panel, t_lbl, f"{int(self.time_elapsed // 60)}:{int(self.time_elapsed % 60):02d}", curr_y + 35, 100, panel_w - 200)
        self._draw_stat(panel, o_lbl, f"{self.objects_found} / {self.total_objects}", curr_y + 75, 100, panel_w - 200)

        # Pulsante localizzato
        btn_rect = self.get_continue_button_rect(0, 0, panel_w, panel_h)
        pygame.draw.rect(panel, (*COLOR_ACCENT, alpha), btn_rect, border_radius=10)
        txt = self._fonts["btn"].render(self.lang("CONTINUE"), True, (20, 20, 30))
        panel.blit(txt, (btn_rect.centerx - txt.get_width() // 2, btn_rect.centery - txt.get_height() // 2))

        panel.set_alpha(alpha)
        surface.blit(panel, (panel_x, draw_y))

        # Filtri VHS
        surface.blit(self._scanlines_surf, (0, 0))
        surface.blit(self._vignette_surf, (0, 0))
        n_surf = pygame.Surface((self.screen_w, 30), pygame.SRCALPHA)
        for _ in range(20):
            nx = random.randint(0, self.screen_w)
            pygame.draw.rect(n_surf, (200, 200, 255, 30), (nx, 0, 4, 30))
        surface.blit(n_surf, (0, self._vhs_noise_bar_y))
        
        if random.random() < 0.2:
             for _ in range(50):
                 surface.set_at((random.randint(0, self.screen_w), random.randint(0, self.screen_h)), (255, 255, 255, 20))

    def _draw_stat(self, surf, label, val, y, x, width):
        lbl = self._fonts["stat_lbl"].render(label.upper(), True, COLOR_TEXT_DIM)
        v = self._fonts["stat_val"].render(val, True, COLOR_TEXT)
        surf.blit(lbl, (x, y))
        surf.blit(v, (x + width - v.get_width(), y - 3))

    def _draw_star(self, surface, x, y, size, color, alpha=255):
        pts = []
        for i in range(10):
            ang = math.pi/2 + i * math.pi/5
            r = size if i%2 == 0 else size*0.45
            pts.append((x + r * math.cos(ang), y - r * math.sin(ang)))
        pygame.draw.polygon(surface, (*color, alpha), pts)
        pygame.draw.polygon(surface, (0, 0, 0, alpha//2), pts, 2)
