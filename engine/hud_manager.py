"""
engine/hud_manager.py

Heads-Up Display premium del gioco.
Implementa un design "Glassmorphism" con icone oggetti circolari, 
timer stilizzato e dashboard punti ottimizzata.
"""

from __future__ import annotations

import math
import os
import logging
from typing import Optional, TYPE_CHECKING

import pygame

from engine.scene_loader import SceneObject
from engine.utils import get_resource_path, is_android_runtime

if TYPE_CHECKING:
    from engine.scaling_manager import ScalingManager
    from engine.language_manager import LanguageManager

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Costanti layout (coordinate di riferimento 1280×720)
# ---------------------------------------------------------------------------
HUD_H_REF = 110           # Altezza aumentata per icone più grandi
ICON_MARGIN_REF = 12      # Spazio tra nomi
BORDER_RADIUS = 15        # Arrotondamento pannelli
ANIM_SPEED = 8.0          # Velocità generale animazioni (lerp)
DASHBOARD_W_REF = 185     # Larghezza riservata al pannello score/found (a destra)

# Colori Premium
COLOR_BG = (15, 15, 25, 180)        # Deep Navy trasparente
COLOR_BORDER = (80, 80, 110, 200)   # Blue-Grey glow
COLOR_ACCENT = (255, 215, 0)        # Gold
COLOR_TEXT = (230, 235, 245)        # Off-white
COLOR_DANGER = (220, 40, 40)        # Crimson
COLOR_SUCCESS = (60, 240, 120)      # Emerald

# Palette diversificata per obiettivi (Vibrant & Warm Pastels)
COLOR_PALETTE = [
    (180, 255, 180),  # Pastel Green
    (255, 235, 150),  # Warm Yellow
    (150, 240, 255),  # Soft Cyan
    (255, 180, 180),  # Salmon
    (220, 180, 255),  # Orchid
    (160, 255, 230),  # Light Turquoise
]

# Dialog States
class DialogState:
    HIDDEN = 0
    SLIDING_IN = 1
    ACTIVE = 2
    SLIDING_OUT = 3


class HintConfirmDialog:
    """Modal dialog per confermare l'uso di un hint."""

    def __init__(self, screen_w: int, screen_h: int, lang_fn) -> None:
        self.screen_w = screen_w
        self.screen_h = screen_h
        self.lang = lang_fn
        self.state = DialogState.HIDDEN
        self.timer = 0.0
        self.timeout = 10.0  # Auto-dismiss dopo 10 secondi

        # Dialog dimensions
        self.dialog_w = 400
        self.dialog_h = 200
        self.dialog_x = (screen_w - self.dialog_w) // 2
        self.dialog_base_y = screen_h - 120

        # Animation
        self.slide_duration = 0.3
        self.slide_progress = 0.0

        # Button rectangles
        self.btn_confirm_rect = pygame.Rect(0, 0, 0, 0)
        self.btn_cancel_rect = pygame.Rect(0, 0, 0, 0)

        # Hover state
        self.hovered_button = None  # "confirm" or "cancel"

        # Data for display
        self.current_penalty = 0
        self.hints_remaining = 0
        self.can_use_hint = False

    def show(self, hints_remaining: int, can_use: bool, penalty: int = 50) -> None:
        """Mostra il dialog e inizia l'animazione di slide-in."""
        if self.state != DialogState.HIDDEN:
            return
        self.state = DialogState.SLIDING_IN
        self.timer = 0.0
        self.slide_progress = 0.0
        self.hints_remaining = hints_remaining
        self.can_use_hint = can_use
        self.current_penalty = penalty
        self.hovered_button = None

    def hide(self) -> None:
        """Nascondi il dialog con slide-out animation."""
        if self.state != DialogState.HIDDEN:
            self.state = DialogState.SLIDING_OUT
            self.timer = 0.0
            self.slide_progress = 1.0

    def update(self, dt: float, mouse_pos: tuple[int, int]) -> Optional[str]:
        """Aggiorna stato e animazioni. Ritorna action se button premuto."""
        if self.state == DialogState.HIDDEN:
            return None

        self.timer += dt

        # Animazione slide-in
        if self.state == DialogState.SLIDING_IN:
            self.slide_progress = min(1.0, self.timer / self.slide_duration)
            if self.slide_progress >= 1.0:
                self.state = DialogState.ACTIVE
                self.timer = 0.0

        # Animazione slide-out
        elif self.state == DialogState.SLIDING_OUT:
            self.slide_progress = max(0.0, 1.0 - self.timer / 0.2)
            if self.slide_progress <= 0.0:
                self.state = DialogState.HIDDEN
                return None

        # Timeout auto-dismiss
        elif self.state == DialogState.ACTIVE:
            if self.timer >= self.timeout:
                self.hide()

        # Hover detection
        self._update_hover_state(mouse_pos)

        return None

    def _update_hover_state(self, mouse_pos: tuple[int, int]) -> None:
        """Aggiorna stato di hover sui bottoni."""
        self.hovered_button = None
        if self.state != DialogState.ACTIVE:
            return

        if self.btn_confirm_rect.collidepoint(mouse_pos):
            self.hovered_button = "confirm"
        elif self.btn_cancel_rect.collidepoint(mouse_pos):
            self.hovered_button = "cancel"

    def get_button_action(self, mouse_pos: tuple[int, int]) -> Optional[str]:
        """Ritorna l'azione se un bottone è cliccato."""
        if self.state != DialogState.ACTIVE:
            return None

        if self.btn_confirm_rect.collidepoint(mouse_pos):
            return "confirm_hint"
        elif self.btn_cancel_rect.collidepoint(mouse_pos):
            return "cancel_hint"
        return None

    def handle_key(self, key: int) -> Optional[str]:
        """Gestisci input keyboard. Esc cancella."""
        if self.state != DialogState.ACTIVE:
            return None
        if key == pygame.K_ESCAPE:
            self.hide()
            return "cancel_hint"
        return None

    def draw(self, surface: pygame.Surface, font: pygame.font.Font, font_small: pygame.font.Font) -> None:
        """Disegna il dialog."""
        if self.state == DialogState.HIDDEN:
            return

        # Calcola Y con animazione
        current_y = self.dialog_base_y + (1.0 - self.slide_progress) * 150

        # Semi-transparent overlay
        overlay = pygame.Surface((self.screen_w, self.screen_h), pygame.SRCALPHA)
        overlay_alpha = int(self.slide_progress * 100)
        overlay.fill((0, 0, 0, overlay_alpha))
        surface.blit(overlay, (0, 0))

        # Dialog background
        dialog_rect = pygame.Rect(self.dialog_x, int(current_y), self.dialog_w, self.dialog_h)
        pygame.draw.rect(surface, COLOR_BG, dialog_rect, border_radius=BORDER_RADIUS)
        pygame.draw.rect(surface, COLOR_BORDER, dialog_rect, 2, border_radius=BORDER_RADIUS)

        # Title
        title = self.lang("confirm_hint_title")
        title_surf = font.render(title, True, COLOR_ACCENT)
        surface.blit(title_surf, (dialog_rect.x + 20, dialog_rect.y + 15))

        # Info text
        penalty_text = f"{self.lang('hud_penalty')}: {self.current_penalty} pt"
        info_surf = font_small.render(penalty_text, True, COLOR_TEXT)
        surface.blit(info_surf, (dialog_rect.x + 20, dialog_rect.y + 50))

        hints_text = f"{self.lang('hud_available')}: {self.hints_remaining}"
        hints_surf = font_small.render(hints_text, True, COLOR_SUCCESS if self.hints_remaining > 0 else COLOR_DANGER)
        surface.blit(hints_surf, (dialog_rect.x + 20, dialog_rect.y + 75))

        # Buttons
        btn_y = dialog_rect.y + self.dialog_h - 50
        btn_h = 35
        btn_w = 150
        margin = 30

        # Confirm button
        confirm_x = dialog_rect.x + margin
        self.btn_confirm_rect = pygame.Rect(confirm_x, btn_y, btn_w, btn_h)
        confirm_color = COLOR_SUCCESS if self.hovered_button == "confirm" else (80, 120, 180)
        pygame.draw.rect(surface, confirm_color, self.btn_confirm_rect, border_radius=8)
        confirm_txt = font_small.render(self.lang('hud_confirm'), True, (20, 20, 30))
        surface.blit(confirm_txt, (confirm_x + (btn_w - confirm_txt.get_width()) // 2, btn_y + 8))

        # Cancel button
        cancel_x = dialog_rect.x + dialog_rect.width - btn_w - margin
        self.btn_cancel_rect = pygame.Rect(cancel_x, btn_y, btn_w, btn_h)
        cancel_color = COLOR_DANGER if self.hovered_button == "cancel" else (120, 120, 140)
        pygame.draw.rect(surface, cancel_color, self.btn_cancel_rect, border_radius=8)
        cancel_txt = font_small.render(self.lang('hud_cancel'), True, (220, 220, 230))
        surface.blit(cancel_txt, (cancel_x + (btn_w - cancel_txt.get_width()) // 2, btn_y + 8))


class HudManager:
    """Gestisce il rendering e la logica della HUD moderna."""

    def __init__(self,
                 scaling_manager: "ScalingManager",
                 lang: "LanguageManager",
                 hud_config: dict,
                 screen_w: int,
                 screen_h: int) -> None:
        self._sm = scaling_manager
        self._lang = lang
        self._cfg = hud_config
        self._position = hud_config.get("position", "bottom")

        # Stato
        self._objects: list[SceneObject] = []
        self._time_elapsed: float = 0.0
        self._time_total: float = 1.0
        self._score_display: float = 0.0  # Float per animazione fluida
        self._score_target: int = 0
        self._found_count: int = 0

        # UI State
        self._alpha: int = 255
        self._fade_timer: float = 0.0
        self._fading_out: bool = False

        # ── Drawer Android ─────────────────────────────────────────────────
        # Su touch l'HUD è un cassetto: nascosto di default (così la scena è
        # completamente visibile), si apre con swipe dal bordo o toccando la
        # maniglia, e si richiude da solo dopo qualche secondo.
        self._android = is_android_runtime()
        self._drawer = 0.0          # 0 = nascosto, 1 = completamente aperto
        self._drawer_target = 0.0
        self._drawer_auto = 0.0     # timer di auto-chiusura
        self._handle_rect = pygame.Rect(0, 0, 0, 0)
        self._hovered_idx: int = -1  # Indice oggetto sotto mouse
        self._hint_button_hovered: bool = False  # Hover sul pulsante hint
        self._pause_button_hovered: bool = False # Hover sul pulsante pausa
        self._pause_button_rect: pygame.Rect = pygame.Rect(0, 0, 0, 0)

        # Gestione obiettivi dinamici (finestra visibile)
        self._max_visible = hud_config.get("max_visible_goals", 7)
        self._visible_objects: list[SceneObject] = []

        # Hint System State
        self._hint_system = None
        self._hint_cooldown_pct: float = 0.0
        self._hint_can_use: bool = True
        self._hint_button_rect: pygame.Rect = pygame.Rect(0, 0, 0, 0)
        self._reward_tracker = None

        # Tooltip
        self._tooltip_text: str = ""
        self._tooltip_pos: tuple[int, int] = (0, 0)
        self._tooltip_visible: bool = False

        # Risorse
        self._screen_w = screen_w
        self._screen_h = screen_h
        self._fonts: dict[str, pygame.font.Font] = {}

        self._load_resources()

        # Hint confirmation dialog
        self._hint_dialog = HintConfirmDialog(screen_w, screen_h, lang)

        # Cache font per galleria obiettivi (performance)
        self._shared_hud_font: Optional[pygame.font.Font] = None
        self._last_shared_size: int = 0

    def _load_resources(self) -> None:
        """Carica font e inizializza superfici base."""
        font_path = self._cfg.get("font", "")
        abs_font = get_resource_path(font_path) if font_path else None

        sizes = {"label": 22, "timer": 38, "score": 28, "tooltip": 15, "stats": 18}
        # Android: font un po' più grandi per leggibilità su mobile (desktop invariato).
        if getattr(self, "_android", False):
            sizes = {k: int(round(v * 1.22)) for k, v in sizes.items()}
        for name, size in sizes.items():
            if abs_font and os.path.exists(abs_font):
                try:
                    self._fonts[name] = pygame.font.Font(abs_font, size)
                    continue
                except Exception as exc:
                    log.warning("Errore caricamento font '%s': %s", abs_font, exc)
            
            # Fallback elegante e Retro (Serif)
            if name == "label":
                # Lista di font eleganti retrò comuni su Windows
                self._fonts[name] = pygame.font.SysFont(["georgia", "palatino", "timesnewroman", "serif"], size, italic=True)
            else:
                self._fonts[name] = pygame.font.SysFont("segoeui", size, bold=(name in ["timer", "score"]))

        self._rebuild_surface()

    def _rebuild_surface(self) -> None:
        """Rigenera le superfici scalate."""
        self._scale = self._sm.scale
        self._hud_h = int(HUD_H_REF * self._scale)
        self._hud_surf = pygame.Surface((self._screen_w, self._hud_h), pygame.SRCALPHA)

    # ------------------------------------------------------------------
    # API Pubblica
    # ------------------------------------------------------------------

    def setup(self, objects: list[SceneObject], time_elapsed: float, reward_tracker=None) -> None:
        """Inizializza HUD per la scena corrente."""
        self._objects = [o for o in objects if o.is_goal]
        self._time_elapsed = time_elapsed
        self._time_total = 1.0
        self._score_display = 0.0
        self._score_target = 0
        self._found_count = 0
        self._reward_tracker = reward_tracker

        self._update_visible_pool()
        # Su Android mostra il cassetto all'avvio scena (poi si chiude da solo),
        # così il giocatore vede gli obiettivi e nota la maniglia.
        if self._android:
            self.open_drawer(5.0)
        log.debug("HUD Reset: %d obiettivi totali, finestra di %d",
                  len(self._objects), self._max_visible)

    def _update_visible_pool(self) -> None:
        """Aggiorna la lista degli obiettivi mostrati (solo quelli non trovati)."""
        remaining = [o for o in self._objects if not o.found]
        selected = remaining[:self._max_visible]
        # Ordina per lunghezza nome per ottimizzare la distribuzione spazi in HUD
        # Usiamo .get() esplicito per sicurezza
        selected.sort(key=lambda o: len(str(self._lang.get(o.label_key, ""))))
        self._visible_objects = selected

    def is_target_active(self, instance_id: str) -> bool:
        """Restituisce True se l'oggetto è tra gli obiettivi attivi in vista nella HUD."""
        for obj in self._visible_objects:
            if obj.instance_id == instance_id:
                return True
        return False


    def update(self, dt: float, mouse_pos: tuple[int, int],
               time_elapsed: float, score: int, hint_system=None) -> None:
        """Aggiorna logica e animazioni."""
        self._time_elapsed = time_elapsed
        self._score_target = score
        self._found_count = sum(1 for o in self._objects if o.found)

        # Aggiorna stato hint system
        self._hint_system = hint_system
        if hint_system:
            self._hint_cooldown_pct = hint_system.get_cooldown_percent()
            # [FIX] Il bottone è usabile solo se c'è almeno un hint nel reward pool
            available = self._reward_tracker.get_available_hints() if self._reward_tracker else 0
            self._hint_can_use = hint_system.can_use_hint() and available > 0

        # Aggiorna il pool visibile (automatico: chi è trovato sparisce)
        self._update_visible_pool()

        # Animazione Punteggio fluida
        diff = self._score_target - self._score_display
        if abs(diff) > 0.1:
            self._score_display += diff * dt * 5.0
        else:
            self._score_display = float(self._score_target)

        hud_rect = self._get_hud_rect()
        is_hovering_hud = hud_rect.collidepoint(mouse_pos)

        if self._android:
            # Su Android nessun fade: l'HUD è sempre opaco, ma scorre dentro/fuori
            # come un cassetto. Animazione del drawer + auto-chiusura.
            self._alpha = 255
            spd = dt * 7.0
            if self._drawer < self._drawer_target:
                self._drawer = min(self._drawer_target, self._drawer + spd)
            elif self._drawer > self._drawer_target:
                self._drawer = max(self._drawer_target, self._drawer - spd)
            if self._drawer_target > 0.0:
                self._drawer_auto -= dt
                if self._drawer_auto <= 0.0:
                    self._drawer_target = 0.0
        else:
            # Gestione Fade per Inattività Globale o Hover (desktop invariato)
            self._fade_timer += dt
            if self._fade_timer > 1.2 or is_hovering_hud:
                self._fading_out = True
            fade_out_spd = (400 if is_hovering_hud else 120) * dt
            fade_in_spd = 500 * dt
            if self._fading_out:
                self._alpha = max(40, int(self._alpha - fade_out_spd))
            else:
                self._alpha = min(255, int(self._alpha + fade_in_spd))

        # Update Dialog
        self._hint_dialog.update(dt, mouse_pos)

        # Update Hover Stati
        self._update_hover_states(mouse_pos, hud_rect, dt)
        
        # Hover pulsante pausa (top-left)
        self._pause_button_hovered = self._pause_button_rect.collidepoint(mouse_pos)

    def on_mouse_activity(self) -> None:
        """Reset immediato del fade su attività mouse (click/movimento)."""
        self._fade_timer = 0.0
        self._fading_out = False

    # ── Drawer Android: API pubblica ───────────────────────────────────────
    def open_drawer(self, seconds: float = 4.0) -> None:
        """Apre il cassetto HUD e programma l'auto-chiusura."""
        self._drawer_target = 1.0
        self._drawer_auto = seconds

    def close_drawer(self) -> None:
        self._drawer_target = 0.0

    def toggle_drawer(self) -> None:
        if self._drawer_target > 0.0:
            self.close_drawer()
        else:
            self.open_drawer()

    def is_drawer_open(self) -> bool:
        return self._drawer > 0.05

    def get_handle_rect(self) -> pygame.Rect:
        return self._handle_rect

    def is_handle_clicked(self, pos) -> bool:
        return self._android and self._handle_rect.collidepoint(pos)

    def handle_swipe(self, start_pos, end_pos) -> bool:
        """Gestisce uno swipe verticale dal bordo dove vive l'HUD.
        Ritorna True se ha aperto/chiuso il cassetto."""
        if not self._android:
            return False
        dy = end_pos[1] - start_pos[1]
        thr = self._screen_h * 0.06
        edge = self._screen_h * 0.12
        if self._position == "bottom":
            # swipe verso l'alto partendo dal bordo basso → apri
            if start_pos[1] >= self._screen_h - edge and dy < -thr:
                self.open_drawer(); return True
            if dy > thr:  # swipe verso il basso → chiudi
                self.close_drawer(); return True
        else:
            if start_pos[1] <= edge and dy > thr:
                self.open_drawer(); return True
            if dy < -thr:
                self.close_drawer(); return True
        return False

    def on_screen_resize(self, screen_w: int, screen_h: int) -> None:
        self._screen_w = screen_w
        self._screen_h = screen_h
        self._rebuild_surface()

    def draw(self, surface: pygame.Surface, elapsed_s: float) -> None:
        """Disegna la HUD completa."""
        self._hud_surf.fill((0, 0, 0, 0))
        
        # 1. Pannello di Sfondo (Glassmorphism)
        self._draw_glass_panel()

        # 2. Modulo Sinistra: Galleria Obiettivi
        self._draw_objective_gallery()

        # 3. Modulo Centro: Timer Premium
        self._draw_central_timer(elapsed_s)

        # 4. Modulo Destra: Dashboard Punti/Stats
        self._draw_right_dashboard()

        # Applica alpha e disegna a schermo
        self._hud_surf.set_alpha(self._alpha)
        hud_rect = self._get_hud_rect()
        surface.blit(self._hud_surf, hud_rect.topleft)

        # Maniglia del cassetto (solo Android): sempre visibile, indica dove
        # fare swipe / si può toccare per aprire-chiudere l'HUD.
        if self._android:
            self._draw_handle(surface, hud_rect)

        # 5. Dialog (top-level overlay)
        self._hint_dialog.draw(surface, self._fonts["score"], self._fonts["stats"])

        # 6. Pulsante Pausa (top-left)
        self._draw_pause_button(surface)

        # 7. Tooltip (esterno per alpha pieno)
        if self._tooltip_visible:
            self._draw_tooltip(surface)

    # ------------------------------------------------------------------
    # Moduli di Disegno
    # ------------------------------------------------------------------

    def _draw_handle(self, surface: pygame.Surface, hud_rect: pygame.Rect) -> None:
        """Maniglia/linguetta del cassetto HUD (Android). Sempre visibile."""
        s = self._scale
        hw = int(74 * s)
        hh = int(16 * s)
        cx = self._screen_w // 2
        if self._position == "bottom":
            hy = min(hud_rect.top - hh, self._sm.safe_bottom - hh)
        else:
            hy = max(hud_rect.bottom, self._sm.safe_top)
        pill = pygame.Rect(cx - hw // 2, hy, hw, hh)
        # Area di tocco generosa
        self._handle_rect = pill.inflate(hw, hh * 2)

        pill_surf = pygame.Surface((hw, hh), pygame.SRCALPHA)
        pygame.draw.rect(pill_surf, (15, 18, 28, 200), (0, 0, hw, hh), border_radius=hh // 2)
        pygame.draw.rect(pill_surf, (*COLOR_BORDER[:3], 220), (0, 0, hw, hh), max(1, int(s)), border_radius=hh // 2)
        # Grip + chevron: su=apri (chiuso), giù=chiudi (aperto)
        gc = COLOR_ACCENT
        midx = hw // 2
        if self._drawer < 0.5:  # chiuso → freccia su
            pygame.draw.polygon(pill_surf, gc, [(midx - int(8 * s), hh - int(5 * s)),
                                                (midx + int(8 * s), hh - int(5 * s)),
                                                (midx, int(5 * s))])
        else:                    # aperto → freccia giù
            pygame.draw.polygon(pill_surf, gc, [(midx - int(8 * s), int(5 * s)),
                                                (midx + int(8 * s), int(5 * s)),
                                                (midx, hh - int(5 * s))])
        surface.blit(pill_surf, pill.topleft)

    def _draw_pause_button(self, surface: pygame.Surface) -> None:
        """Disegna il pulsante pausa in formato ultra-mini e quasi invisibile."""
        s = self._scale
        margin = int(8 * s)
        btn_w = int(28 * s)
        btn_h = int(28 * s)

        self._pause_button_rect = pygame.Rect(
            self._sm.safe_left + margin, self._sm.safe_top + margin, btn_w, btn_h
        )
        
        # Background molto trasparente
        alpha = 180 if self._pause_button_hovered else 100
        bg_color = (*COLOR_BG[:3], alpha)
        border_color = COLOR_ACCENT if self._pause_button_hovered else (*COLOR_BORDER[:3], 120)
        
        # Rendering su una surface temporanea
        btn_surf = pygame.Surface((btn_w, btn_h), pygame.SRCALPHA)
        pygame.draw.rect(btn_surf, bg_color, (0, 0, btn_w, btn_h), border_radius=5)
        pygame.draw.rect(btn_surf, border_color, (0, 0, btn_w, btn_h), 1, border_radius=5)
        
        # Icona Pausa ultra-mini
        bar_w = int(2 * s)
        bar_h = int(12 * s)
        bar_gap = int(4 * s)
        
        cx, cy = btn_w // 2, btn_h // 2
        left_bar_x = cx - (bar_w + bar_gap // 2)
        right_bar_x = cx + bar_gap // 2
        bar_y = cy - bar_h // 2
        
        # Icona sottile e trasparente
        icon_color = (*COLOR_TEXT, 160)
        pygame.draw.rect(btn_surf, icon_color, (left_bar_x, bar_y, bar_w, bar_h), border_radius=1)
        pygame.draw.rect(btn_surf, icon_color, (right_bar_x, bar_y, bar_w, bar_h), border_radius=1)
        
        surface.blit(btn_surf, self._pause_button_rect.topleft)

    def is_pause_button_clicked(self, pos: tuple[int, int]) -> bool:
        """Controlla se il click è sul pulsante pausa."""
        return self._pause_button_rect.collidepoint(pos)


    def _draw_glass_panel(self) -> None:
        """Disegna il contenitore principale con effetto vetro."""
        if self._android:
            # Android: barra a TUTTA LARGHEZZA, angoli squadrati (no arrotondamento),
            # più opaca per leggibilità sopra la scena.
            rect = pygame.Rect(0, 0, self._screen_w, self._hud_h)
            bg = (12, 14, 22, 235)
            pygame.draw.rect(self._hud_surf, bg, rect)
            # Bordo sul lato interno (verso la scena) come accento netto
            edge_y = rect.bottom - 3 if self._position == "top" else rect.y
            pygame.draw.rect(self._hud_surf, COLOR_ACCENT, (0, edge_y, self._screen_w, 3))
            pygame.draw.rect(self._hud_surf, (*COLOR_BORDER[:3], 160), rect, 2)
        else:
            left = max(10, self._sm.safe_left)
            right = min(self._screen_w - 10, self._sm.safe_right)
            rect = pygame.Rect(left, 5, right - left, self._hud_h - 10)
            pygame.draw.rect(self._hud_surf, COLOR_BG, rect, border_radius=BORDER_RADIUS)
            pygame.draw.rect(self._hud_surf, COLOR_BORDER, rect, 2, border_radius=BORDER_RADIUS)
            accent_rect = pygame.Rect(rect.x + 20, rect.y, rect.width - 40, 2)
            pygame.draw.rect(self._hud_surf, (*COLOR_BORDER[:3], 100), accent_rect)

    def _draw_objective_gallery(self) -> None:
        """Visualizza nomi distribuiti su 2 righe sfasate con Uniform Scaling globale per matchare destra/sinistra."""
        s = self._scale
        cx = self._screen_w // 2
        base_y = self._hud_h // 2
        
        timer_clearance = int(140 * s)
        dashboard_w = int(130 * s)
        side_margin = max(int(25 * s), self._sm.safe_left + int(8 * s))
        right_limit = min(self._screen_w, self._sm.safe_right) - dashboard_w
        inner_margin = int(10 * s)

        bounds = {
            "left":  (side_margin, cx - timer_clearance - inner_margin),
            "right": (cx + timer_clearance + inner_margin, right_limit),
        }

        # 1. Determinare il fattore di scala GLOBALE per parificare la grandezza font
        global_sf = 1.0
        base_font = self._fonts["label"]
        min_gap_ref = int(15 * s)

        for block_type, (bx1, bx2) in bounds.items():
            objs = self._visible_objects[:4] if block_type == "left" else self._visible_objects[4:7]
            if not objs: continue
            max_w = max(10, bx2 - bx1)
            
            n_top = math.ceil(len(objs) / 2.0)
            top_objs, bot_objs = objs[:n_top], objs[n_top:]

            req_top = sum(base_font.size(self._lang(o.label_key).lower())[0] for o in top_objs) + max(0, len(top_objs)-1)*min_gap_ref
            req_bot = sum(base_font.size(self._lang(o.label_key).lower())[0] for o in bot_objs) + max(0, len(bot_objs)-1)*min_gap_ref
            req_max_w = max(req_top, req_bot)

            if req_max_w > max_w:
                sf = max_w / float(req_max_w + 5)
                if sf < global_sf: global_sf = sf

        # Recupero del Font dalla cache per evitare lag massicci o esaurimento risorse
        final_size = max(10, int(20 * s * global_sf))
        if not self._shared_hud_font or final_size != self._last_shared_size:
            self._shared_hud_font = pygame.font.SysFont("georgia,palatino,serif", final_size, italic=True)
            self._last_shared_size = final_size
        
        shared_font = self._shared_hud_font

        for block_type, (bx1, bx2) in bounds.items():
            objs = self._visible_objects[:4] if block_type == "left" else self._visible_objects[4:7]
            if not objs: continue
            max_w = max(10, bx2 - bx1)
            
            n_top = math.ceil(len(objs) / 2.0)
            top_objs, bot_objs = objs[:n_top], objs[n_top:]

            def get_w(row_objs):
                return [shared_font.size(self._lang(o.label_key).lower())[0] for o in row_objs]
            top_w, bot_w = get_w(top_objs), get_w(bot_objs)

            def layout_row(r_idx, row_objs, widths, y_offset):
                if not row_objs: return
                
                if len(row_objs) == 1:
                    gap = 0
                else:
                    gap = max(int(6 * s), min(int(38 * s), (max_w - sum(widths)) // (len(row_objs) - 1)))
                
                total_w = sum(widths) + gap * (len(row_objs) - 1)
                start_x = bx1 + (max_w - total_w) // 2
                
                curr_x = start_x
                for i, obj in enumerate(row_objs):
                    txt = self._lang(obj.label_key).lower()
                    if not txt:
                        # Fallback alla chiave grezza se la traduzione è vuota, per evitare HUD vuota
                        txt = str(obj.label_key).lower()
                    
                    if not txt: 
                        curr_x += widths[i] + gap
                        continue

                    h = shared_font.size(txt)[1]
                    
                    absolute_idx = (i if r_idx == 0 else i + n_top) + (0 if block_type == "left" else 4)
                    jy = int(math.cos(absolute_idx * 3.7) * 4 * s)
                    render_y = base_y + y_offset + jy
                    
                    color = COLOR_PALETTE[absolute_idx % len(COLOR_PALETTE)]
                    sh = shared_font.render(txt, True, (0, 0, 0, 180))
                    self._hud_surf.blit(sh, (curr_x + 1, render_y - h // 2 + 1))
                    surf = shared_font.render(txt, True, color)
                    self._hud_surf.blit(surf, (curr_x, render_y - h // 2))
                    
                    curr_x += widths[i] + gap

            layout_row(0, top_objs, top_w, int(-22 * s))
            layout_row(1, bot_objs, bot_w, int(22 * s))








    def _draw_central_timer(self, elapsed_s: float) -> None:
        """Timer stile cronometro al centro (in avanti)."""
        s = self._scale
        center_x = self._screen_w // 2
        center_y = self._hud_h // 2
        
        # Calcolo Tempo Crescente
        mins, secs = divmod(int(max(0, self._time_elapsed)), 60)
        timer_str = f"{mins:02d}:{secs:02d}"
        
        color = COLOR_TEXT

        # Testo Timer
        timer_font = self._fonts["timer"]
        timer_surf = timer_font.render(timer_str, True, color)
        
        tw, th = timer_surf.get_size()
        self._hud_surf.blit(timer_surf, (center_x - tw // 2, center_y - th // 2))

        # Etichetta "TIME"
        label = self._lang("hud_time").upper()
        lbl_surf = self._fonts["label"].render(label, True, (*COLOR_TEXT[:3], 150))
        self._hud_surf.blit(lbl_surf, (center_x - lbl_surf.get_width() // 2, center_y - th // 2 - 18))

    def _draw_right_dashboard(self) -> None:
        """Dashboard punteggio e progresso ancorata al bordo destro con separatore."""
        s = self._scale
        dashboard_w = int(DASHBOARD_W_REF * s)
        right_edge = min(self._screen_w - int(18 * s), self._sm.safe_right)
        sep_x = right_edge - dashboard_w
        center_y = self._hud_h // 2

        # — Label "SCORE" (piccola, sopra) —
        score_lbl = self._fonts["stats"].render(
            self._lang("hud_score").upper(), True, COLOR_ACCENT
        )
        self._hud_surf.blit(score_lbl, (right_edge - score_lbl.get_width(), center_y - int(34 * s)))

        # — Valore punteggio (grande, centro) —
        score_surf = self._fonts["score"].render(f"{int(self._score_display):05d}", True, COLOR_ACCENT)
        self._hud_surf.blit(score_surf, (right_edge - score_surf.get_width(), center_y - int(13 * s)))

        # — Objects found (piccola, sotto) —
        total = len(self._objects)
        is_all_found = self._found_count == total and total > 0
        found_color = COLOR_SUCCESS if is_all_found else COLOR_TEXT
        
        if is_all_found:
            found_str = self._lang("hud_found_all").upper()
        else:
            found_str = f"{self._found_count}/{total} {self._lang('hud_found').upper()}"
            
        found_surf = self._fonts["stats"].render(found_str, True, found_color)
        self._hud_surf.blit(found_surf, (right_edge - found_surf.get_width(), center_y + int(18 * s)))

    def _draw_hint_button(self, right_edge: int, center_y: int, s: float) -> None:
        """Disegna il pulsante hint con stato cooldown."""
        if not self._hint_system:
            return

        # Dimensioni e posizionamento
        btn_size = int(36 * s)
        btn_margin = int(8 * s)
        btn_x = right_edge - btn_size - btn_margin
        btn_y = center_y + int(50 * s)

        # Colore in base allo stato
        if self._hint_can_use:
            btn_color = COLOR_SUCCESS
            border_color = COLOR_SUCCESS
        else:
            btn_color = (120, 120, 140)
            border_color = (80, 80, 100)

        # Disegna cerchio pulsante
        pygame.draw.circle(self._hud_surf, btn_color, (btn_x + btn_size // 2, btn_y + btn_size // 2), btn_size // 2 - 2)
        pygame.draw.circle(self._hud_surf, border_color, (btn_x + btn_size // 2, btn_y + btn_size // 2), btn_size // 2 - 2, 2)

        # Disegna "?" nel centro
        q_font = self._fonts["score"]
        q_surf = q_font.render("?", True, (20, 20, 30) if self._hint_can_use else (100, 100, 110))
        q_rect = q_surf.get_rect(center=(btn_x + btn_size // 2, btn_y + btn_size // 2))
        self._hud_surf.blit(q_surf, q_rect)

        # Salva rettangolo per click detection
        self._hint_button_rect = pygame.Rect(btn_x, btn_y, btn_size, btn_size)

        # Disegna cooldown arc se in cooldown
        if self._hint_cooldown_pct > 0 and not self._hint_can_use:
            # Barra di cooldown circonferenziale (semplice: barra verticale che cresce)
            cooldown_h = int(btn_size * (1.0 - self._hint_cooldown_pct))
            cooldown_rect = pygame.Rect(btn_x, btn_y + btn_size - cooldown_h, btn_size, cooldown_h)
            pygame.draw.rect(self._hud_surf, (*COLOR_DANGER[:3], 100), cooldown_rect)

        # Hover highlight
        if self._hint_button_hovered:
            pygame.draw.circle(self._hud_surf, (*COLOR_ACCENT, 100), (btn_x + btn_size // 2, btn_y + btn_size // 2), btn_size // 2 - 1, 3)

    def _draw_hint_reward_display(self, right_edge: int, center_y: int, s: float) -> None:
        """Disegna il conteggio hint e barra di progresso per guadagnare hints."""
        if not self._hint_system:
            return

        # Get current hints from system or fallback
        available_hints = self._hint_system.max_hints_before_disable + 1  # Default fallback
        earn_progress = 0.0

        # Se il reward tracker è disponibile, usa quei dati
        if hasattr(self, '_reward_tracker') and self._reward_tracker:
            available_hints = self._reward_tracker.get_available_hints()
            earn_progress = self._reward_tracker.get_earn_progress()

        # Hint count label
        hint_text = f"{available_hints} HINT"
        hint_lbl = self._fonts["stats"].render(hint_text, True, COLOR_SUCCESS)
        self._hud_surf.blit(hint_lbl, (right_edge - hint_lbl.get_width(), center_y + int(38 * s)))

        # Progress bar verso il prossimo hint
        bar_w = int(100 * s)
        bar_h = int(6 * s)
        bar_x = right_edge - bar_w
        bar_y = center_y + int(58 * s)

        # Background bar (scuro)
        pygame.draw.rect(self._hud_surf, (40, 40, 60), (bar_x, bar_y, bar_w, bar_h))

        # Progress fill (blue -> green gradient)
        if earn_progress > 0:
            fill_w = int(bar_w * earn_progress)
            color = self._lerp_color((100, 150, 255), (60, 240, 120), earn_progress)
            pygame.draw.rect(self._hud_surf, color, (bar_x, bar_y, fill_w, bar_h))

        # Border
        pygame.draw.rect(self._hud_surf, COLOR_BORDER, (bar_x, bar_y, bar_w, bar_h), 1)

    def get_hint_button_rect(self) -> pygame.Rect:
        """Restituisce il rettangolo del pulsante hint (usato per click detection)."""
        return getattr(self, '_hint_button_rect', pygame.Rect(0, 0, 0, 0))

    def is_hint_button_clicked(self, pos: tuple[int, int], hud_rect: pygame.Rect) -> bool:
        """Controlla se il click è sul pulsante hint."""
        local_pos = (pos[0] - hud_rect.x, pos[1] - hud_rect.y)
        return self.get_hint_button_rect().collidepoint(local_pos)

    # ------------------------------------------------------------------
    # Tooltip e Interazione
    # ------------------------------------------------------------------

    def _update_hover_states(self, mouse_pos: tuple[int, int], hud_rect: pygame.Rect, dt: float) -> None:
        self._hovered_idx = -1
        self._tooltip_visible = False
        self._hint_button_hovered = False

        if not hud_rect.collidepoint(mouse_pos): return

        # Controlla hover sul pulsante hint
        if self.is_hint_button_clicked(mouse_pos, hud_rect):
            self._hint_button_hovered = True
            if self._hint_system:
                if self._hint_can_use:
                    self._tooltip_text = self._lang("hud_hint_tooltip")
                else:
                    self._tooltip_text = self._lang("hud_hint_cooldown")
                self._tooltip_pos = mouse_pos
                self._tooltip_visible = True
            return

        s = self._scale
        cx = self._screen_w // 2
        base_y = self._hud_h // 2
        local_x = mouse_pos[0] - hud_rect.x
        local_y = mouse_pos[1] - hud_rect.y

        timer_clearance = int(140 * s)
        dashboard_w = int(130 * s)
        side_margin = int(25 * s)
        inner_margin = int(10 * s)
        bounds = {"left": (side_margin, cx - timer_clearance - inner_margin),
                  "right": (cx + timer_clearance + inner_margin, self._screen_w - dashboard_w)}

        global_sf = 1.0
        base_font = self._fonts["label"]
        min_gap_ref = int(15 * s)

        for block_type, (bx1, bx2) in bounds.items():
            objs = self._visible_objects[:4] if block_type == "left" else self._visible_objects[4:7]
            if not objs: continue
            max_w = max(10, bx2 - bx1)
            n_top = math.ceil(len(objs) / 2.0)
            top_objs, bot_objs = objs[:n_top], objs[n_top:]

            req_top = sum(base_font.size(self._lang(o.label_key).lower())[0] for o in top_objs) + max(0, len(top_objs)-1)*min_gap_ref
            req_bot = sum(base_font.size(self._lang(o.label_key).lower())[0] for o in bot_objs) + max(0, len(bot_objs)-1)*min_gap_ref
            req_max_w = max(req_top, req_bot)

            if req_max_w > max_w:
                sf = max_w / float(req_max_w + 5)
                if sf < global_sf: global_sf = sf

        final_size = max(10, int(20 * s * global_sf))
        shared_font = pygame.font.SysFont("georgia,palatino,serif", final_size, italic=True)

        for block_type, (bx1, bx2) in bounds.items():
            objs = self._visible_objects[:4] if block_type == "left" else self._visible_objects[4:7]
            if not objs: continue
            max_w = max(10, bx2 - bx1)
            n_top = math.ceil(len(objs) / 2.0)
            top_objs, bot_objs = objs[:n_top], objs[n_top:]

            def get_w(row_objs):
                return [shared_font.size(self._lang(o.label_key).lower())[0] for o in row_objs]
            top_w, bot_w = get_w(top_objs), get_w(bot_objs)

            def check_row_hover(r_idx, row_objs, widths, y_offset):
                if not row_objs: return
                
                if len(row_objs) == 1:
                    gap = 0
                else:
                    gap = max(int(6 * s), min(int(38 * s), (max_w - sum(widths)) // (len(row_objs) - 1)))
                
                total_w = sum(widths) + gap * (len(row_objs) - 1)
                start_x = bx1 + (max_w - total_w) // 2
                
                curr_x = start_x
                for i, obj in enumerate(row_objs):
                    absolute_idx = (i if r_idx == 0 else i + n_top) + (0 if block_type == "left" else 4)
                    jy = int(math.cos(absolute_idx * 3.7) * 4 * s)
                    render_y = base_y + y_offset + jy
                    
                    hitbox = pygame.Rect(curr_x - 4, render_y - int(12 * s), widths[i] + 8, int(24 * s))
                    if hitbox.collidepoint(local_x, local_y):
                        self._hovered_idx = absolute_idx
                        self._prepare_tooltip(self._hovered_idx, mouse_pos)
                    curr_x += widths[i] + gap

            check_row_hover(0, top_objs, top_w, int(-22 * s))
            check_row_hover(1, bot_objs, bot_w, int(22 * s))


    def _prepare_tooltip(self, idx: int, mouse_pos: tuple[int, int]) -> None:
        obj = self._visible_objects[idx]
        status = self._lang("hud_remaining_status")
        self._tooltip_text = f"{self._lang(obj.label_key)} | {status}"
        self._tooltip_pos = mouse_pos
        self._tooltip_visible = True

    def _draw_tooltip(self, surface: pygame.Surface) -> None:
        """Disegna un tooltip elegante sopra la HUD."""
        txt_surf = self._fonts["tooltip"].render(self._tooltip_text, True, COLOR_TEXT)
        pw, ph = 10, 6
        rect = txt_surf.get_rect(center=(self._tooltip_pos[0], self._tooltip_pos[1] - 30))
        bg_rect = rect.inflate(pw * 2, ph * 2)
        
        # Assicura che sia dentro lo schermo
        bg_rect.clamp_ip(surface.get_rect().inflate(-20, -20))
        
        pygame.draw.rect(surface, (20, 20, 35, 230), bg_rect, border_radius=5)
        pygame.draw.rect(surface, COLOR_BORDER, bg_rect, 1, border_radius=5)
        surface.blit(txt_surf, bg_rect.move(pw, ph).topleft)

    # ------------------------------------------------------------------
    # Hint Dialog Control
    # ------------------------------------------------------------------

    def show_hint_dialog(self, hints_remaining: int, can_use: bool, penalty: int = 50) -> None:
        """Mostra il dialog di conferma hint."""
        self._hint_dialog.show(hints_remaining, can_use, penalty)

    def get_hint_dialog_button_action(self, mouse_pos: tuple[int, int]) -> Optional[str]:
        """Ritorna l'azione se un bottone del dialog è cliccato."""
        return self._hint_dialog.get_button_action(mouse_pos)

    def handle_hint_dialog_key(self, key: int) -> Optional[str]:
        """Gestisci input keyboard per il dialog."""
        return self._hint_dialog.handle_key(key)

    def is_hint_dialog_visible(self) -> bool:
        """Controlla se il dialog è visibile."""
        return self._hint_dialog.state != DialogState.HIDDEN

    def hide_hint_dialog(self) -> None:
        """Nascondi il dialog."""
        self._hint_dialog.hide()

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    def _get_hud_rect(self) -> pygame.Rect:
        # Posiziona la barra dentro la safe area verticale (notch/angoli).
        if self._position == "bottom":
            y = self._sm.safe_bottom - self._hud_h
            if self._android:
                # Scorre fuori dal bordo basso quando il cassetto è chiuso.
                y += int((1.0 - self._drawer) * (self._hud_h + (self._screen_h - self._sm.safe_bottom)))
        else:
            y = self._sm.safe_top
            if self._android:
                y -= int((1.0 - self._drawer) * (self._hud_h + self._sm.safe_top))
        return pygame.Rect(0, y, self._screen_w, self._hud_h)

    @staticmethod
    def _lerp_color(c1: tuple, c2: tuple, t: float) -> tuple:
        t = max(0.0, min(1.0, t))
        return tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3))

    def get_hud_rect(self) -> pygame.Rect:
        """Metodo richiesto dal game loop per le collisioni click."""
        return self._get_hud_rect()

