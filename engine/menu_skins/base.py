"""
engine/menu_skins/base.py

Interfaccia SKIN per i menu pygame.

Il MENU CORE (engine/menu_system.py) gestisce dati, navigazione, save/lock,
i18n, audio, scroll e hit-test: e' identico per tutti i temi. Lo SKIN definisce
SOLO il look & feel ed e' selezionato a runtime da ui_theme (fallback 'default').

Gli skin lavorano per HOOK additivi richiamati dal core in punti precisi del
rendering; la classe base non disegna nulla di extra, cosi' un tema privo delle
nuove sezioni di theme.json mantiene esattamente il comportamento storico.
"""


class MenuSkin:
    """Skin base: nessuna decorazione extra (comportamento neutro)."""

    id = "base"

    def __init__(self, theme) -> None:
        self.theme = theme
        self._t = 0.0  # accumulatore tempo per le animazioni dello skin

    # ── Knob di motion (letti da theme.motion, con default storici) ──────────
    @property
    def carousel_zoom(self) -> float:
        return float(self.theme.motion("carousel_zoom", 0.25))

    @property
    def float_amp(self) -> float:
        return float(self.theme.motion("float_amp", 4.0))

    @property
    def magnetic(self) -> bool:
        return bool(self.theme.motion("magnetic", True))

    # ── Reduced-motion / performance ─────────────────────────────────────────
    def reduced(self, ms) -> bool:
        """Modalita' ridotta (Android/low-end): gli effetti pesanti degradano."""
        return bool(getattr(ms, "_android", False))

    def fx_on(self, ms, feature: str) -> bool:
        """True se 'feature' deve girare: spento solo se reduced-motion lo elenca."""
        if self.reduced(ms) and self.theme.motion_disabled(feature):
            return False
        return True

    def update(self, ms, dt: float) -> None:
        self._t += dt

    # ── Hook di rendering (default: nessuna decorazione) ─────────────────────
    def draw_background_pre(self, ms, screen, sw, sh) -> None:
        """Atmosfera dietro titolo/bottoni (sopra lo sfondo gia' disegnato dal core)."""
        pass

    def draw_title(self, ms, screen) -> None:
        """Titolo di stato; di default usa il renderer del core."""
        ms._draw_state_title(screen)

    def button_jitter(self, ms, b):
        """Offset posizionale (dx, dy) in coord di riferimento per il bottone."""
        return (0.0, 0.0)

    def behind_button(self, ms, screen, b, draw_rect, is_locked) -> None:
        """Decoro disegnato DIETRO al bottone (placca, alone, cornice)."""
        pass

    def draw_overlay(self, ms, screen, sw, sh) -> None:
        """Decoro FRONTALE sopra i contenuti (grana, coriandoli, vignetta)."""
        pass

    def arrange(self, ms) -> None:
        """Ricompone le posizioni dei bottoni dopo build_buttons.
        Default: layout del core invariato. Gli skin possono spostare i bottoni
        (solo offset verticali, per non interferire con scroll/zoom orizzontale)."""
        pass
