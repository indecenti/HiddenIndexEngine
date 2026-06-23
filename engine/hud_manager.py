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
HUD_H_REF = 140           # Altezza maggiorata per leggibilità (mobile)
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

    # Durata dell'animazione di ritrovamento del tile nella lista a icone (mobile).
    FOUND_ANIM_DUR = 0.7

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
        self._mobile_hint_rect_local: pygame.Rect = pygame.Rect(0, 0, 0, 0)
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

        # Lista a icone (mobile): default per essere robusti se draw precede setup.
        self._found_anim: dict[str, float] = {}
        self._prev_found: set[str] = set()
        self._icon_thumb_cache: dict[tuple, pygame.Surface] = {}
        self._tile_cache: dict[tuple, pygame.Surface] = {}
        self._text_cache: dict[tuple, pygame.Surface] = {}
        self._hud_sig = None  # firma contenuto barra mobile (dirty-flag)
        self._obj_color_idx: dict[str, int] = {}
        self._caption_fonts: dict[int, pygame.font.Font] = {}

    def _load_resources(self) -> None:
        """Carica font e inizializza superfici base."""
        font_path = self._cfg.get("font", "")
        abs_font = get_resource_path(font_path) if font_path else None

        sizes = {"label": 22, "timer": 38, "score": 28, "tooltip": 15, "stats": 18}
        # Android: font più grandi per leggibilità su mobile (desktop invariato).
        if getattr(self, "_android", False):
            sizes = {k: int(round(v * 1.5)) for k, v in sizes.items()}
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

        # Font dedicati alla HUD mobile (pulsante hint): sans leggibile e grande,
        # indipendente dal tema serif del desktop. (La lista oggetti a icone usa
        # _caption_font, non piu' un font "chip" testuale.)
        if getattr(self, "_android", False):
            self._fonts["hint"] = pygame.font.SysFont("segoeui", int(round(20 * 1.5)), bold=True)
            self._fonts["hint_badge"] = pygame.font.SysFont("segoeui", int(round(26 * 1.5)), bold=True)

        self._rebuild_surface()

    def _rebuild_surface(self) -> None:
        """Rigenera le superfici scalate."""
        self._scale = self._sm.scale
        if getattr(self, "_android", False):
            # Su mobile la barra è un cassetto che si apre a richiesta: la
            # rendiamo più alta per ospitare le "chip" grandi degli oggetti a
            # font fisso leggibile (niente più testo rimpicciolito).
            self._hud_h = max(int(HUD_H_REF * self._scale), int(self._screen_h * 0.36))
        else:
            self._hud_h = int(HUD_H_REF * self._scale)
        # Android: barra OPACA (full-width, squadrata) → blit veloce. I blit
        # SRCALPHA full-width sono lentissimi su pygame ARM. Su desktop resta
        # SRCALPHA (glass/fade trasparente).
        if getattr(self, "_android", False):
            # .convert() al formato display: i tile opachi (anch'essi convert()) si
            # blittano cosi' senza conversione di formato per-pixel -> molto piu' veloce.
            try:
                self._hud_surf = pygame.Surface((self._screen_w, self._hud_h)).convert()
            except Exception:
                self._hud_surf = pygame.Surface((self._screen_w, self._hud_h))
        else:
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

        # Lista oggetti a ICONE (mobile): animazione di ritrovamento + cache thumbnail.
        self._found_anim = {}   # instance_id -> elapsed (s)
        self._prev_found = set(o.instance_id for o in self._objects if o.found)
        self._icon_thumb_cache = {}
        # Cache dei TILE composti (sfondo+icona+didascalia): si ricostruisce solo al
        # cambio stato/dimensione, non ogni frame -> taglia i ms di draw HUD su Android.
        self._tile_cache = {}
        self._hud_sig = None
        # Cache delle scritte info-row (tempo/punti/trovati): il tempo cambia ~1/sec.
        self._text_cache = {}
        # Colore stabile per oggetto (no .index() O(n) per tile a ogni frame).
        self._obj_color_idx = {o.instance_id: i for i, o in enumerate(self._objects)}

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

        # Animazione di ritrovamento (lista a icone, SOLO mobile): rileva i nuovi
        # found e fa restare il tile col segno di spunta per FOUND_ANIM_DUR prima di
        # sparire. Su desktop la lista e' testuale: niente tracking (overhead inutile).
        if self._android:
            found_now = set(o.instance_id for o in self._objects if o.found)
            new_found = found_now - self._prev_found
            for iid in new_found:
                self._found_anim[iid] = 0.0
            self._prev_found = found_now
            # Mostra brevemente il cassetto al ritrovamento, così la spunta sull'icona
            # e' visibile anche se il drawer era chiuso durante il gioco.
            if new_found:
                self.open_drawer(max(1.6, self.FOUND_ANIM_DUR + 0.6))
            for iid in list(self._found_anim.keys()):
                self._found_anim[iid] += dt
                if self._found_anim[iid] >= self.FOUND_ANIM_DUR:
                    del self._found_anim[iid]

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
        opened = False
        if self._position == "bottom":
            if start_pos[1] >= self._screen_h - edge and dy < -thr:
                self.open_drawer(); opened = True
            elif dy > thr:
                self.close_drawer(); opened = True
        else:
            if start_pos[1] <= edge and dy > thr:
                self.open_drawer(); opened = True
            elif dy < -thr:
                self.close_drawer(); opened = True
        return opened

    def on_screen_resize(self, screen_w: int, screen_h: int) -> None:
        self._screen_w = screen_w
        self._screen_h = screen_h
        self._rebuild_surface()
        # Le cache dipendono dalla dimensione dei tile: invalidale al resize.
        self._icon_thumb_cache = {}
        self._tile_cache = {}
        self._hud_sig = None

    def draw(self, surface: pygame.Surface, elapsed_s: float) -> None:
        """Disegna la HUD completa."""
        # Android: se il cassetto è chiuso (fuori schermo) NON disegniamo la barra
        # (build + blit SRCALPHA full-width = costoso su pygame ARM). Solo maniglia
        # e pulsante pausa, sempre accessibili.
        if self._android and self._drawer <= 0.01:
            self._draw_handle(surface, self._get_hud_rect())
            self._draw_pause_button(surface)
            if self._tooltip_visible:
                self._draw_tooltip(surface)
            return

        if self._android:
            # DIRTY-FLAG: la barra (_hud_surf) si ricompone SOLO quando il contenuto
            # cambia (secondo del timer, punti, trovati, stato hint, animazione found).
            # Altrimenti si riusa la surface gia' composta: durante lo slide del
            # cassetto e nei frame "fermi" si fa solo il blit -> grosso risparmio.
            anim_active = bool(self._found_anim)
            avail = self._reward_tracker.get_available_hints() if self._reward_tracker else 0
            sig = (int(self._time_elapsed), int(self._score_display), self._found_count,
                   self._hint_can_use, avail, round(self._hint_cooldown_pct, 2),
                   tuple(o.instance_id for o in self._mobile_display_objects()))
            if anim_active or sig != getattr(self, "_hud_sig", None):
                self._hud_surf.fill((0, 0, 0, 0))
                self._draw_glass_panel()
                self._draw_mobile_hud(elapsed_s)
                self._hud_sig = sig
        else:
            self._hud_surf.fill((0, 0, 0, 0))
            self._draw_glass_panel()
            # 2. Galleria obiettivi / 3. Timer / 4. Dashboard
            self._draw_objective_gallery()
            self._draw_central_timer(elapsed_s)
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
        """Pulsante pausa in alto a sinistra. Su desktop discreto; su touch deve
        essere un target comodo (>=48dp equivalenti) e visibile, perché va
        raggiunto col pollice."""
        s = self._scale
        margin = int(10 * s)
        if self._android:
            # Bersaglio touch comodo: ~48dp+ a prescindere dalla densità.
            btn_w = btn_h = max(int(40 * s), int(self._screen_h * 0.085))
        else:
            btn_w = btn_h = int(28 * s)

        draw_rect = pygame.Rect(
            self._sm.safe_left + margin, self._sm.safe_top + margin, btn_w, btn_h
        )
        # Area di tocco più generosa del disegno su mobile (non mancare il bersaglio);
        # su desktop coincide col disegno.
        self._pause_button_rect = draw_rect.inflate(btn_w // 2, btn_h // 2) if self._android else draw_rect

        # Opacità: mobile più visibile (discoverability), desktop discreto.
        if self._android:
            alpha = 230 if self._pause_button_hovered else 175
            border_alpha = 170
        else:
            alpha = 180 if self._pause_button_hovered else 100
            border_alpha = 120
        bg_color = (*COLOR_BG[:3], alpha)
        border_color = COLOR_ACCENT if self._pause_button_hovered else (*COLOR_BORDER[:3], border_alpha)

        btn_surf = pygame.Surface((btn_w, btn_h), pygame.SRCALPHA)
        radius = max(5, btn_w // 5)
        pygame.draw.rect(btn_surf, bg_color, (0, 0, btn_w, btn_h), border_radius=radius)
        pygame.draw.rect(btn_surf, border_color, (0, 0, btn_w, btn_h), max(1, int(2 * s)), border_radius=radius)

        # Icona Pausa proporzionale al pulsante
        bar_w = max(2, int(btn_w * 0.10))
        bar_h = int(btn_h * 0.42)
        bar_gap = max(2, int(btn_w * 0.12))
        cx, cy = btn_w // 2, btn_h // 2
        left_bar_x = cx - (bar_w + bar_gap // 2)
        right_bar_x = cx + bar_gap // 2
        bar_y = cy - bar_h // 2
        icon_color = (*COLOR_TEXT, 230 if self._android else 160)
        pygame.draw.rect(btn_surf, icon_color, (left_bar_x, bar_y, bar_w, bar_h), border_radius=2)
        pygame.draw.rect(btn_surf, icon_color, (right_bar_x, bar_y, bar_w, bar_h), border_radius=2)

        surface.blit(btn_surf, draw_rect.topleft)

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

    # ------------------------------------------------------------------
    # HUD Mobile (Android): chip oggetti + pulsante hint nella barra
    # ------------------------------------------------------------------

    def _draw_mobile_hud(self, elapsed_s: float) -> None:
        """Layout HUD ottimizzato per touch: una barra con riga info in alto
        (tempo / punti / trovati), una griglia di 'chip' grandi e leggibili per
        gli oggetti da trovare, e il pulsante HINT integrato a destra."""
        s = self._scale
        surf = self._hud_surf
        W = self._screen_w
        H = self._hud_h

        pad = int(14 * s)
        left = max(pad, self._sm.safe_left + pad)
        right = min(W - pad, self._sm.safe_right - pad)

        # ── Colonna destra: pulsante HINT (grande, integrato nella barra) ──────
        hint_w = max(int(150 * s), int(W * 0.16))
        hint_x = right - hint_w
        hint_y = pad
        hint_h = H - pad * 2
        self._draw_mobile_hint(hint_x, hint_y, hint_w, hint_h, s)

        # Separatore verticale tra chip e hint
        sep_x = hint_x - pad
        pygame.draw.line(surf, (*COLOR_BORDER[:3], 120), (sep_x, pad), (sep_x, H - pad), max(1, int(s)))

        content_left = left
        content_right = sep_x - pad

        # ── Riga info in alto: TEMPO | PUNTI | TROVATI ─────────────────────────
        info_h = int(H * 0.30)
        info_cy = pad + info_h // 2
        f_timer = self._fonts["timer"]
        f_score = self._fonts["score"]
        f_stats = self._fonts["stats"]

        mins, secs = divmod(int(max(0, self._time_elapsed)), 60)
        timer_str = f"{mins:02d}:{secs:02d}"
        t_surf = self._cached_text(f_timer, "timer", timer_str, COLOR_TEXT)
        surf.blit(t_surf, (content_left, info_cy - t_surf.get_height() // 2))

        score_str = f"{int(self._score_display):05d}"
        sc_surf = self._cached_text(f_score, "score", score_str, COLOR_ACCENT)
        surf.blit(sc_surf, ((content_left + content_right) // 2 - sc_surf.get_width() // 2,
                            info_cy - sc_surf.get_height() // 2))

        total = len(self._objects)
        is_all = self._found_count == total and total > 0
        found_str = (self._lang("hud_found_all").upper() if is_all
                     else f"{self._found_count}/{total}")
        fcol = COLOR_SUCCESS if is_all else COLOR_TEXT
        fnd_surf = self._cached_text(f_stats, "found", found_str, fcol)
        surf.blit(fnd_surf, (content_right - fnd_surf.get_width(),
                             info_cy - fnd_surf.get_height() // 2))

        # ── Griglia oggetti a ICONE (standard HOG) con found animato ───────────
        self._draw_mobile_icons(content_left, pad + info_h, content_right, H - pad, s)

    # ------------------------------------------------------------------
    # Lista oggetti a ICONE (mobile) — thumbnail + caption + found animato
    # ------------------------------------------------------------------

    def _mobile_display_objects(self) -> list:
        """Oggetti mostrati nella lista a icone: ordine di scena stabile, con un cap
        totale ~_max_visible (i tile in animazione di ritrovamento hanno priorita' e
        consumano slot, così una combo di find non rimpicciolisce le icone)."""
        n_anim = sum(1 for o in self._objects if o.instance_id in self._found_anim)
        slots = max(0, self._max_visible - n_anim)
        display, shown = [], 0
        for o in self._objects:
            if o.instance_id in self._found_anim:
                display.append(o)
            elif not o.found and shown < slots:
                display.append(o)
                shown += 1
        return display

    def _draw_mobile_icons(self, x0: int, y0: int, x1: int, y1: int, s: float) -> None:
        surf = self._hud_surf
        area_w = max(10, x1 - x0)
        area_h = max(10, y1 - y0)
        display = self._mobile_display_objects()
        if not display:
            return

        n = len(display)
        gap = int(10 * s)
        # Scegli righe/colonne massimizzando la dimensione del tile quadrato.
        best = (1, n, 0.0)
        for rows in (1, 2, 3):
            cols = math.ceil(n / rows)
            tw = (area_w - gap * (cols - 1)) / cols
            th = (area_h - gap * (rows - 1)) / rows
            tile = min(tw, th)
            if tile > best[2]:
                best = (rows, cols, tile)
        _, cols, tile = best
        tile = int(max(1, min(tile, area_h, area_w)))

        total_rows = math.ceil(n / cols)
        grid_h = total_rows * tile + (total_rows - 1) * gap
        start_y = y0 + max(0, (area_h - grid_h) // 2)
        for r in range(total_rows):
            row_items = display[r * cols:(r + 1) * cols]
            if not row_items:
                break
            row_w = len(row_items) * tile + (len(row_items) - 1) * gap
            cx = x0 + max(0, (area_w - row_w) // 2)
            cy = start_y + r * (tile + gap)
            for o in row_items:
                self._draw_icon_tile(surf, o, cx, cy, tile, s)
                cx += tile + gap

    def _draw_icon_tile(self, surf, obj, x: int, y: int, tile: int, s: float) -> None:
        # Tile composto CACHATO (per (id, stato-found, dimensione)): si ricostruisce
        # solo al primo uso o al cambio stato, non ogni frame -> draw HUD economico.
        anim = self._found_anim.get(obj.instance_id)
        found = anim is not None
        key = (obj.instance_id, found, tile)
        base = self._tile_cache.get(key)
        if base is None:
            base = self._build_tile_surface(obj, tile, found, s)
            self._tile_cache[key] = base

        scale, alpha = 1.0, 255
        if found:
            t = anim / self.FOUND_ANIM_DUR
            scale = 1.0 + 0.18 * math.sin(min(1.0, t * 1.6) * math.pi)  # pop
            if t > 0.65:
                alpha = max(0, int(255 * (1.0 - (t - 0.65) / 0.35)))    # fade out

        img = base
        if scale != 1.0:
            dsz = max(1, int(tile * scale))
            img = pygame.transform.smoothscale(base, (dsz, dsz))  # copia (non tocca la cache)
            x -= (dsz - tile) // 2
            y -= (dsz - tile) // 2
        if alpha < 255:
            if img is base:
                img = base.copy()
            img.set_alpha(alpha)
        surf.blit(img, (x, y))

    def _build_tile_surface(self, obj, tile: int, found: bool, s: float) -> pygame.Surface:
        """Compone (una volta, poi cachato) il tile: sfondo arrotondato + thumbnail
        icona + didascalia col NOME INTERO su max 2 righe (font ridotto per entrare,
        niente troncamento)."""
        color = COLOR_PALETTE[self._obj_color_idx.get(obj.instance_id, 0) % len(COLOR_PALETTE)]
        # Android: tile OPACO riempito col colore della barra HUD (12,14,22): gli angoli
        # arrotondati esterni coincidono col fondo barra (anch'esso opaco) -> il blit del
        # tile diventa OPACO. 7 tile SRCALPHA ~271px blittati ogni recompose costavano
        # ~108ms su GPU mobile (stesso killer per-pixel-alpha del cabinet slot).
        if self._android:
            ts = pygame.Surface((tile, tile))
            ts.fill((12, 14, 22))
        else:
            ts = pygame.Surface((tile, tile), pygame.SRCALPHA)
        radius = int(tile * 0.18)
        pygame.draw.rect(ts, (28, 60, 40) if found else (24, 30, 42), (0, 0, tile, tile), border_radius=radius)
        pygame.draw.rect(ts, COLOR_SUCCESS if found else (*color, 230),
                         (0, 0, tile, tile), max(2, int(2 * s)), border_radius=radius)

        cap_h = int(tile * 0.30)   # piu' spazio per la didascalia (fino a 2 righe)
        icon_area = tile - cap_h
        pad = int(6 * s)
        thumb = self._get_icon_thumb(obj, max(1, icon_area - pad))
        if thumb is not None:
            tw, th = thumb.get_size()
            ts.blit(thumb, ((tile - tw) // 2, pad // 2 + (icon_area - th) // 2))
        else:
            nm = (self._lang(obj.label_key) or str(obj.label_key)).strip()
            ini = nm[:1].upper() if nm else "?"
            bigf = self._caption_font(max(10, int(icon_area * 0.55)))
            gl = bigf.render(ini, True, color)
            ts.blit(gl, ((tile - gl.get_width()) // 2, (icon_area - gl.get_height()) // 2))

        name = self._lang(obj.label_key) or str(obj.label_key)
        cap = self._render_caption(name, tile - int(4 * s), cap_h, max(9, int(tile * 0.16)))
        if cap is not None:
            ts.blit(cap, ((tile - cap.get_width()) // 2, tile - cap_h + (cap_h - cap.get_height()) // 2))

        if found:
            self._draw_check_badge(ts, tile, s)
        # Su Android la tile e' opaca (vedi sopra): convert() -> blit rapido. Il fade
        # del found-anim usa set_alpha (alpha di superficie) che funziona anche opaco.
        return ts.convert() if self._android else ts

    def _render_caption(self, name: str, max_w: int, max_h: int, max_size: int):
        """Renderizza il nome su 1-2 righe centrate, riducendo il font finche' entra in
        (max_w x max_h). I nomi lunghi vanno A CAPO invece di essere troncati."""
        col = (220, 225, 235)
        for size in range(int(max_size), 8, -1):
            f = self._caption_font(size)
            lines = self._wrap_lines(name, f, max_w, 2)
            if lines is None:
                continue
            lh = f.get_height()
            total_h = lh * len(lines)
            if total_h > max_h:
                continue
            cap = pygame.Surface((max(1, max_w), total_h), pygame.SRCALPHA)
            cy = 0
            for ln in lines:
                ls = f.render(ln, True, col)
                cap.blit(ls, ((max_w - ls.get_width()) // 2, cy))
                cy += lh
            return cap
        # Fallback estremo: font minimo, 1 riga troncata
        f = self._caption_font(9)
        return f.render(self._truncate_text(name, f, max_w), True, col)

    @staticmethod
    def _wrap_lines(text: str, font: pygame.font.Font, max_w: int, max_lines: int):
        """Word-wrap greedy in <= max_lines righe, ciascuna <= max_w px.
        None se non ci sta (il chiamante riprova con un font piu' piccolo)."""
        if font.size(text)[0] <= max_w:
            return [text]
        lines, cur = [], ""
        for w in text.split():
            trial = (cur + " " + w).strip()
            if font.size(trial)[0] <= max_w:
                cur = trial
            else:
                if cur:
                    lines.append(cur)
                cur = w
                if font.size(cur)[0] > max_w:
                    return None  # parola singola troppo larga per questo font
                if len(lines) >= max_lines:
                    return None
        if cur:
            lines.append(cur)
        return lines if len(lines) <= max_lines else None

    def _get_icon_thumb(self, obj, size: int):
        """Thumbnail scalata e cachata dell'icona dell'oggetto (fit, aspect preservato).
        None se l'oggetto non ha icon_surface (fallback all'iniziale del nome)."""
        size = max(1, int(size))
        src = getattr(obj, "icon_surface", None)
        if src is None:
            return None
        key = (obj.instance_id, size)
        cached = self._icon_thumb_cache.get(key)
        if cached is not None:
            return cached
        sw, sh = src.get_size()
        if sw <= 0 or sh <= 0:
            return None
        f = min(size / sw, size / sh)
        tw, th = max(1, int(sw * f)), max(1, int(sh * f))
        try:
            thumb = pygame.transform.smoothscale(src, (tw, th))
        except Exception:
            thumb = pygame.transform.scale(src, (tw, th))
        self._icon_thumb_cache[key] = thumb
        return thumb

    def _caption_font(self, size: int) -> pygame.font.Font:
        size = max(8, int(size))
        cache = getattr(self, "_caption_fonts", None)
        if cache is None:
            cache = self._caption_fonts = {}
        if size not in cache:
            cache[size] = pygame.font.SysFont("segoeui", size, bold=True)
        return cache[size]

    def _cached_text(self, font, fkey: str, text: str, color) -> pygame.Surface:
        """font.render memoizzato per (font, testo, colore): la riga info HUD cambia
        valore al massimo ~1/sec (tempo) o di rado (trovati), quindi quasi sempre hit."""
        ck = (fkey, text, color)
        s = self._text_cache.get(ck)
        if s is None:
            s = font.render(text, True, color)
            self._text_cache[ck] = s
            if len(self._text_cache) > 80:
                self._text_cache.pop(next(iter(self._text_cache)))
        return s

    @staticmethod
    def _truncate_text(text: str, font: pygame.font.Font, max_w: int) -> str:
        if font.size(text)[0] <= max_w:
            return text
        ell = "…"
        while text and font.size(text + ell)[0] > max_w:
            text = text[:-1]
        return (text + ell) if text else ""

    def _draw_check_badge(self, surf: pygame.Surface, size: int, s: float) -> None:
        r = max(5, int(size * 0.16))
        cx, cy = size - r - int(2 * s), r + int(2 * s)
        pygame.draw.circle(surf, COLOR_SUCCESS, (cx, cy), r)
        pygame.draw.circle(surf, (10, 30, 18), (cx, cy), r, max(1, int(s)))
        pts = [(cx - r * 0.45, cy), (cx - r * 0.10, cy + r * 0.42), (cx + r * 0.50, cy - r * 0.42)]
        pygame.draw.lines(surf, (12, 30, 18), False,
                          [(int(px), int(py)) for px, py in pts], max(2, int(2 * s)))

    def _draw_mobile_hint(self, x: int, y: int, w: int, h: int, s: float) -> None:
        """Pulsante HINT grande integrato nella barra (touch friendly). Il pulsante
        e' CACHATO in una surface: prima faceva 3 font.render + 2 rounded-rect ad OGNI
        recompose della barra (ricorrente ogni frame durante il found-anim) -> caro su
        GPU mobile. Ora si ricostruisce solo a cambio stato (disponibilita'/cooldown)."""
        can_use = self._hint_can_use
        available = self._reward_tracker.get_available_hints() if self._reward_tracker else 0
        cd = 0.0 if can_use else round(self._hint_cooldown_pct, 2)
        key = (w, h, can_use, available, cd, round(s, 2))
        cached = getattr(self, "_hint_btn_cache", None)
        if cached is None or cached[0] != key:
            if can_use:
                bg, border, qcol, lblcol = (30, 90, 55), COLOR_SUCCESS, COLOR_SUCCESS, (210, 255, 225)
            else:
                bg, border, qcol, lblcol = (60, 60, 72), (110, 110, 130), (150, 150, 165), (170, 170, 185)
            btn = pygame.Surface((w, h), pygame.SRCALPHA)
            radius = int(18 * s)
            pygame.draw.rect(btn, bg, (0, 0, w, h), border_radius=radius)
            pygame.draw.rect(btn, border, (0, 0, w, h), max(2, int(2 * s)), border_radius=radius)
            q_surf = self._fonts["hint_badge"].render("?", True, qcol)
            btn.blit(q_surf, ((w - q_surf.get_width()) // 2, int(h * 0.16)))
            lbl = self._fonts["hint"].render(self._lang("hud_hint", "HINT").upper(), True, lblcol)
            btn.blit(lbl, ((w - lbl.get_width()) // 2, int(h * 0.46)))
            cnt = self._fonts["hint"].render(f"x{available}", True, lblcol)
            btn.blit(cnt, ((w - cnt.get_width()) // 2, int(h * 0.70)))
            if cd > 0 and not can_use:
                cov_h = int(h * cd)
                cov = pygame.Surface((w, cov_h), pygame.SRCALPHA)
                cov.fill((10, 10, 16, 150))
                btn.blit(cov, (0, h - cov_h))
            btn = btn.convert_alpha()
            self._hint_btn_cache = (key, btn)
            cached = self._hint_btn_cache
        self._hud_surf.blit(cached[1], (x, y))
        # Memorizza il rettangolo LOCALE (verrà convertito in schermo dal getter)
        self._mobile_hint_rect_local = pygame.Rect(x, y, w, h)

    def get_mobile_hint_rect(self) -> pygame.Rect:
        """Rettangolo del pulsante hint mobile in coordinate SCHERMO.
        Vuoto se non Android o se il cassetto è chiuso (hint non disponibile)."""
        if not self._android or not self.is_drawer_open():
            return pygame.Rect(0, 0, 0, 0)
        local = getattr(self, "_mobile_hint_rect_local", None)
        if not local:
            return pygame.Rect(0, 0, 0, 0)
        hud_rect = self._get_hud_rect()
        return local.move(hud_rect.x, hud_rect.y)

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

        # Su touch non c'è hover persistente: nessun tooltip e nessun calcolo
        # di layout per l'hover (la HUD mobile è gestita da _draw_mobile_hud).
        if self._android:
            return

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

