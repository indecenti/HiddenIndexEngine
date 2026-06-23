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

from engine.utils import is_android_runtime

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

        self._android = is_android_runtime()

        # FIX BUG: Inizializza prima il dizionario, poi carica i font
        self._fonts = {}
        self._font_cache: dict = {}
        self._load_fonts()

        # Filtri VHS (solo desktop: su mobile sono blit SRCALPHA full-screen
        # lentissimi su pygame ARM, vengono sostituiti da uno sfondo opaco).
        if not self._android:
            self._vignette_surf = self._create_vignette(screen_w, screen_h)
            self._scanlines_surf = self._create_scanlines(screen_w, screen_h)
        else:
            self._vignette_surf = None
            self._scanlines_surf = None
        self._mobile_bg = self._build_mobile_bg(screen_w, screen_h) if self._android else None
        self._vhs_noise_bar_y = 0.0

    # Riferimento di layout: tutto è progettato su questo pannello e poi scalato
    # uniformemente (cs) per stare nella safe-area del dispositivo.
    _REF_W = 520
    _REF_H = 660

    def _layout(self) -> tuple[int, int, int, int, float]:
        """Calcola (panel_x, panel_y, panel_w, panel_h, cs) adattando il pannello
        alla safe-area: su mobile rimpicciolisce così nulla esce dallo schermo."""
        sm = self.scaling_manager
        margin = max(12, int(18 * getattr(sm, "scale", 1.0)))
        safe_l = max(0, getattr(sm, "safe_left", 0))
        safe_r = min(self.screen_w, getattr(sm, "safe_right", self.screen_w))
        safe_t = max(0, getattr(sm, "safe_top", 0))
        safe_b = min(self.screen_h, getattr(sm, "safe_bottom", self.screen_h))
        avail_w = max(120, (safe_r - safe_l) - margin * 2)
        avail_h = max(120, (safe_b - safe_t) - margin * 2)

        # Scala uniforme: non superare il riferimento (desktop ~ invariato),
        # ma rimpicciolire quanto serve per entrare nello schermo (mobile).
        cs = min(1.0, avail_w / self._REF_W, avail_h / self._REF_H)
        panel_w = int(self._REF_W * cs)
        panel_h = int(self._REF_H * cs)
        panel_x = safe_l + (safe_r - safe_l - panel_w) // 2
        panel_y = safe_t + (safe_b - safe_t - panel_h) // 2
        return panel_x, panel_y, panel_w, panel_h, cs

    def _font(self, name: str, ref_size: int, cs: float) -> pygame.font.Font:
        """Font scalato e in cache per (nome, dimensione)."""
        size = max(9, int(round(ref_size * cs)))
        key = (name, size)
        f = self._font_cache.get(key)
        if f is None:
            if name == "georgia":
                f = pygame.font.SysFont("georgia", size, bold=True)
            elif name == "georgia_it":
                f = pygame.font.SysFont("georgia", size, italic=True)
            else:
                f = pygame.font.SysFont("arial", size, bold=(name == "arial_b"))
            self._font_cache[key] = f
        return f

    def _build_mobile_bg(self, w: int, h: int) -> pygame.Surface:
        """Sfondo opaco (scuro + scanline tenui pre-disegnate) per il mobile:
        un solo blit opaco per frame invece di 3 blit SRCALPHA full-screen."""
        bg = pygame.Surface((w, h))
        bg.fill((6, 6, 11))
        for y in range(0, h, 3):
            pygame.draw.line(bg, (0, 0, 0), (0, y), (w, y))
        return bg

    def _load_fonts(self) -> None:
        # Mantengo i font base (usati da eventuale codice legacy desktop); il
        # rendering scalato passa per _font().
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

    def get_continue_button_rect(self, panel_x: int, panel_y: int, panel_w: int, panel_h: int, cs: float = 1.0) -> pygame.Rect:
        # Pulsante grande e touch-friendly: largo ~62% del pannello.
        btn_w = int(panel_w * 0.62)
        btn_h = max(int(54 * cs), 40)
        btn_x = (panel_w - btn_w) // 2
        btn_y = panel_h - btn_h - int(28 * cs)
        return pygame.Rect(panel_x + btn_x, panel_y + btn_y, btn_w, btn_h)

    def check_click(self, mouse_pos: tuple[int, int]) -> bool:
        """Controlla se il click è sul pulsante 'CONTINUA', sincronizzato con l'animazione."""
        if not self.is_visible: return False

        panel_x, panel_y, panel_w, panel_h, cs = self._layout()

        progress = min(1.0, self.animation_timer / self.animation_duration)
        # Evita click accidentali prima che il pulsante sia ben visibile
        if progress < 0.6: return False

        offset_y = int(round(30 * cs * (1.0 - math.pow(1.0 - progress, 3))))
        draw_y = (panel_y - int(30 * cs)) + offset_y

        btn_rect = self.get_continue_button_rect(panel_x, draw_y, panel_w, panel_h, cs)
        return btn_rect.collidepoint(mouse_pos)

    def on_resize(self, w: int, h: int) -> None:
        """Rigenera i filtri grafici quando la risoluzione cambia."""
        self.screen_w = w
        self.screen_h = h
        if self._android:
            self._mobile_bg = self._build_mobile_bg(w, h)
        else:
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

        panel_x, panel_y, panel_w, panel_h, cs = self._layout()

        # Sfondo: mobile = un solo blit OPACO (veloce su ARM); desktop = overlay
        # SRCALPHA con fade-in.
        if self._android:
            if self._mobile_bg is None or self._mobile_bg.get_size() != (self.screen_w, self.screen_h):
                self._mobile_bg = self._build_mobile_bg(self.screen_w, self.screen_h)
            surface.blit(self._mobile_bg, (0, 0))
        else:
            overlay = pygame.Surface((self.screen_w, self.screen_h), pygame.SRCALPHA)
            overlay.fill((5, 5, 10, int(200 * min(1.0, progress))))
            surface.blit(overlay, (0, 0))

        # Animazione drop-down che termina perfettamente al centro
        offset_y = int(round(30 * cs * (1.0 - math.pow(1.0 - progress, 3))))
        draw_y = (panel_y - int(30 * cs)) + offset_y

        radius = max(6, int(BORDER_RADIUS * cs))
        # CACHE del pannello: la composizione (Surface SRCALPHA + ~6 font.render +
        # disegni) avveniva OGNI frame -> costosa su GPU mobile. Il contenuto cambia
        # solo durante l'animazione (conteggio punteggio, pop stelle, fade "perfect",
        # fade pulsante). Lo ricomponiamo solo quando la firma del contenuto cambia;
        # a riposo (animazione finita) e' un singolo blit. set_alpha + posizione
        # drop-down restano applicati per frame (cheap).
        p_alpha = int(255 * max(0, min(1, (self.animation_timer - 1.2) * 2)))
        sig = (panel_w, panel_h, round(cs, 3), self.is_failed, self.display_score, self.stars,
               tuple(round(t, 2) for t in self.star_pop_timers), p_alpha, alpha,
               self.objects_found, self.total_objects, int(self.time_elapsed))
        if getattr(self, "_panel_sig", None) != sig or getattr(self, "_panel_cache", None) is None:
            panel = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)
            pygame.draw.rect(panel, (*COLOR_BG, 252), (0, 0, panel_w, panel_h), border_radius=radius)
            pygame.draw.rect(panel, COLOR_BORDER, (0, 0, panel_w, panel_h), max(1, int(2 * cs)), border_radius=radius)

            margin = int(40 * cs)
            curr_y = int(40 * cs)

            # LOCALIZZAZIONE TITOLO
            t_key = "MISSION_FAILED" if self.is_failed else "MISSION_COMPLETE"
            title_str = self.lang(t_key).upper()
            t_col = COLOR_DANGER if self.is_failed else COLOR_SUCCESS
            title_surf = self._font("georgia", 34, cs).render(title_str, True, t_col)
            if title_surf.get_width() > panel_w - margin:
                sc = (panel_w - margin) / title_surf.get_width()
                title_surf = pygame.transform.smoothscale(title_surf, (int(title_surf.get_width() * sc), int(title_surf.get_height() * sc)))
            panel.blit(title_surf, ((panel_w - title_surf.get_width()) // 2, curr_y))

            curr_y += int(65 * cs)
            label_surf = self._font("georgia_it", 20, cs).render(self.lang("TOTAL_SCORE").upper(), True, COLOR_ACCENT)
            label_surf.set_alpha(150)
            panel.blit(label_surf, ((panel_w - label_surf.get_width()) // 2, curr_y))

            curr_y += int(35 * cs)
            score_surf = self._font("georgia", 54, cs).render(f"{self.display_score}", True, COLOR_ACCENT)
            if score_surf.get_width() > panel_w - int(80 * cs):
                sc = (panel_w - int(80 * cs)) / score_surf.get_width()
                score_surf = pygame.transform.smoothscale(score_surf, (int(score_surf.get_width() * sc), int(score_surf.get_height() * sc)))
            panel.blit(score_surf, ((panel_w - score_surf.get_width()) // 2, curr_y))

            curr_y += int(95 * cs)
            star_spacing = int(100 * cs)
            star_size = int(35 * cs)
            for i in range(3):
                sx = (panel_w // 2) + (i - 1) * star_spacing
                p_timer = self.star_pop_timers[i]
                if i < self.stars and p_timer > 0:
                    pop = min(1.0, p_timer / self.star_pop_duration)
                    sc = math.sin(pop * math.pi * 0.8) * 1.25 if pop < 1.0 else 1.0
                    self._draw_star(panel, sx, curr_y, int(star_size * sc), COLOR_ACCENT)
                else:
                    self._draw_star(panel, sx, curr_y, star_size, (40, 40, 50), 80)

            if self.objects_found == self.total_objects and not self.is_failed and self.total_objects > 0:
                curr_y += int(65 * cs)
                if p_alpha > 0:
                    p_text = self._font("georgia_it", 20, cs).render(f"— {self.lang('PERFECT_SCORE').upper()} —", True, COLOR_SUCCESS)
                    p_text.set_alpha(p_alpha)
                    panel.blit(p_text, ((panel_w - p_text.get_width()) // 2, curr_y))

            sep_y = panel_h - int(170 * cs)
            pygame.draw.line(panel, (60, 60, 75), (int(100 * cs), sep_y), (panel_w - int(100 * cs), sep_y), 1)

            self._draw_stat(panel, self.lang("TIME_ELAPSED"), f"{int(self.time_elapsed // 60)}:{int(self.time_elapsed % 60):02d}", sep_y + int(35 * cs), int(100 * cs), panel_w - int(200 * cs), cs)
            self._draw_stat(panel, self.lang("OBJECTS_FOUND"), f"{self.objects_found} / {self.total_objects}", sep_y + int(75 * cs), int(100 * cs), panel_w - int(200 * cs), cs)

            # Pulsante localizzato (grande, touch-friendly)
            btn_rect = self.get_continue_button_rect(0, 0, panel_w, panel_h, cs)
            pygame.draw.rect(panel, (*COLOR_ACCENT, alpha), btn_rect, border_radius=max(6, int(12 * cs)))
            txt = self._font("arial_b", 20, cs).render(self.lang("CONTINUE"), True, (20, 20, 30))
            panel.blit(txt, (btn_rect.centerx - txt.get_width() // 2, btn_rect.centery - txt.get_height() // 2))

            self._panel_cache = panel
            self._panel_sig = sig

        panel = self._panel_cache
        panel.set_alpha(alpha)
        surface.blit(panel, (panel_x, draw_y))

        # Filtri VHS: solo desktop (su mobile sono blit SRCALPHA full-screen lenti)
        if not self._android:
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

    def _draw_stat(self, surf, label, val, y, x, width, cs=1.0):
        lbl = self._font("arial", 15, cs).render(label.upper(), True, COLOR_TEXT_DIM)
        v = self._font("arial_b", 19, cs).render(val, True, COLOR_TEXT)
        surf.blit(lbl, (x, y))
        surf.blit(v, (x + width - v.get_width(), y - int(3 * cs)))

    def _draw_star(self, surface, x, y, size, color, alpha=255):
        pts = []
        for i in range(10):
            ang = math.pi/2 + i * math.pi/5
            r = size if i%2 == 0 else size*0.45
            pts.append((x + r * math.cos(ang), y - r * math.sin(ang)))
        pygame.draw.polygon(surface, (*color, alpha), pts)
        pygame.draw.polygon(surface, (0, 0, 0, alpha//2), pts, 2)
