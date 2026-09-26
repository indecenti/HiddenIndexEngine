"""
engine/results_screen.py

End-of-scene results panel: title, scene name, stars, score, time and objects
found, and the Continue button.

Layout is a vertical stack of blocks measured on a 520 px wide reference panel;
the panel is as tall as its content (it used to be a fixed 660 px box with an
empty band in the middle) and scales with the menu ScalingManager, capped by
the safe area. Fonts and colours come from the menu theme when one is given
(`set_theme`), so the panel belongs to the same game as the menus; without one
it keeps a neutral dark look. Strings resolve with the same keys as the web
runtime (mission_complete, total_score, ...).
"""

from __future__ import annotations

import math

import pygame

from engine.utils import is_android_runtime

# Neutral palette, used when no menu theme is set.
COLOR_BG = (14, 14, 20)
COLOR_BORDER = (60, 60, 80)
COLOR_ACCENT = (218, 165, 32)
COLOR_TEXT_DIM = (150, 150, 168)
COLOR_TEXT = (220, 220, 228)
COLOR_SUCCESS = (70, 190, 120)
COLOR_DANGER = (206, 72, 64)
COLOR_SEPARATOR = (60, 60, 75)
COLOR_STAR_OFF = (48, 48, 60)
COLOR_BUTTON_TEXT = (20, 20, 30)
PANEL_ALPHA = 246
BACKDROP_ALPHA = 200

BORDER_RADIUS = 14

# Type sizes on the reference panel.
TITLE_SIZE = 34
SUBTITLE_SIZE = 20
LABEL_SIZE = 20
SCORE_SIZE = 52
BUTTON_SIZE = 22
STAT_LABEL_SIZE = 18
STAT_VALUE_SIZE = 22

# Vertical rhythm of the panel, top to bottom (reference px).
PAD_TOP = 34
TITLE_TO_SUBTITLE = 6
HEADER_TO_STARS = 22
STAR_RADIUS = 30
STAR_SPACING = 88
STARS_TO_SCORE = 18
LABEL_TO_SCORE = 2
SCORE_TO_PERFECT = 6
BLOCK_GAP = 22
STAT_SEPARATOR_GAP = 16
STAT_ROW_STEP = 40
STAT_BUTTON_GAP = 18
BUTTON_H = 56
PAD_BOTTOM = 28
STAT_INSET = 64
BUTTON_WIDTH_RATIO = 0.62

# Animation.
DROP_PX = 30
APPEAR_DURATION = 0.9
CLICKABLE_AT = 0.6          # fraction of the appear animation
SCORE_COUNT_DURATION = 0.6
STAR_DELAY = 0.5
STAR_STAGGER = 0.12
STAR_POP_DURATION = 0.3
PERFECT_DELAY = 1.2


class _Scale:
    """Adapter giving MenuTheme.get_font_role the panel scale, not the menu one."""

    def __init__(self, cs: float) -> None:
        self.cs = cs

    def scale_value(self, v: float) -> int:
        return int(round(v * self.cs))


class ResultsScreen:
    """End-of-scene results, themed, localised, touch friendly."""

    _REF_W = 520

    def __init__(self, screen_w: int, screen_h: int, lang_fn, scaling_manager,
                 theme=None) -> None:
        self.screen_w = screen_w
        self.screen_h = screen_h
        self.lang = lang_fn
        self.scaling_manager = scaling_manager
        self.theme = theme

        self.is_visible = False
        self.animation_timer = 0.0
        self.animation_duration = APPEAR_DURATION

        self.score = 0
        self.display_score = 0
        self.stars = 0
        self.time_elapsed = 0.0
        self.is_failed = False
        self.scene_name = ""
        self.objects_found = 0
        self.total_objects = 0

        self.star_pop_timers = [0.0, 0.0, 0.0]
        self.star_pop_duration = STAR_POP_DURATION

        self._android = is_android_runtime()
        self._font_cache: dict = {}
        self._vignette_surf = None if self._android else self._create_vignette(screen_w, screen_h)
        self._panel_cache = None
        self._panel_sig = None

    # -- theme ---------------------------------------------------------------

    def set_theme(self, theme) -> None:
        """Use the menu theme's fonts and colours."""
        self.theme = theme
        self._font_cache.clear()
        self._panel_sig = None

    def _colors(self) -> dict:
        t = self.theme
        if t is None:
            return {"bg": COLOR_BG, "border": COLOR_BORDER, "accent": COLOR_ACCENT,
                    "text": COLOR_TEXT, "dim": COLOR_TEXT_DIM, "win": COLOR_SUCCESS,
                    "fail": COLOR_DANGER, "sep": COLOR_SEPARATOR, "star_off": COLOR_STAR_OFF,
                    "star": COLOR_ACCENT,
                    "btn_text": COLOR_BUTTON_TEXT}
        r, g, b, _a = t.row_bg()
        bg = (int(r * 0.7), int(g * 0.7), int(b * 0.7))
        if t.luminance((r, g, b)) > 140:     # light theme (kids): keep the panel light
            bg = (r, g, b)
        accent = t.accent_on(bg)
        text = t.color3("text_normal")
        if t.contrast(text, bg) < 4.5:
            text = (238, 238, 244) if t.luminance(bg) < 128 else (28, 30, 38)
        dim = t.color3("text_locked")
        if t.contrast(dim, bg) < 3.0:
            dim = tuple(t.lerp_color(text, bg, 0.35)[:3])
        btn_text = (20, 20, 30) if t.luminance(accent) > 128 else (250, 250, 252)
        # Stars are gold unless the theme accent itself reads as a star colour
        # on this panel (accent_on falls back to the TEXT colour, which made
        # the kids stars navy).
        raw_accent = t.accent()
        star = raw_accent if t.contrast(raw_accent, bg) >= 2.0 else COLOR_ACCENT
        return {"bg": bg, "border": accent, "accent": accent, "text": text, "dim": dim,
                "star": star,
                "win": accent, "fail": COLOR_DANGER,
                "sep": tuple(t.lerp_color(bg, text, 0.2)[:3]),
                "star_off": tuple(t.lerp_color(bg, text, 0.18)[:3]), "btn_text": btn_text}

    # -- geometry ------------------------------------------------------------

    def _font(self, name: str, ref_size: int, cs: float) -> pygame.font.Font:
        """Scaled, cached font. `name` is a theme role (title/body/display) or a
        legacy face name (georgia/arial_b), mapped onto the roles."""
        role = {"georgia": "title", "georgia_it": "body", "arial": "body",
                "arial_b": "body"}.get(name, name)
        size = max(9, int(round(ref_size * cs)))
        key = (role, size, id(self.theme))
        f = self._font_cache.get(key)
        if f is None:
            if self.theme is not None:
                f = self.theme.get_font_role(role, ref_size, _Scale(cs))
            else:
                bold = role in ("title", "display") or name == "arial_b"
                f = pygame.font.SysFont("arial", size, bold=bold)
            self._font_cache[key] = f
        return f

    def _has_perfect_line(self) -> bool:
        return (not self.is_failed and self.total_objects > 0
                and self.objects_found == self.total_objects)

    def _panel_ref_height(self) -> float:
        """Height of the stack of blocks at scale 1."""
        h = PAD_TOP + self._font("title", TITLE_SIZE, 1.0).get_height()
        if self.scene_name:
            h += TITLE_TO_SUBTITLE + self._font("body", SUBTITLE_SIZE, 1.0).get_height()
        h += HEADER_TO_STARS + STAR_RADIUS * 2 + STARS_TO_SCORE
        h += self._font("body", LABEL_SIZE, 1.0).get_height() + LABEL_TO_SCORE
        h += self._font("display", SCORE_SIZE, 1.0).get_height()
        if self._has_perfect_line():
            h += SCORE_TO_PERFECT + self._font("body", LABEL_SIZE, 1.0).get_height()
        h += BLOCK_GAP + STAT_SEPARATOR_GAP + 2 * STAT_ROW_STEP + STAT_BUTTON_GAP
        h += BUTTON_H + PAD_BOTTOM
        return h

    def _layout(self) -> tuple[int, int, int, int, float]:
        """(panel_x, panel_y, panel_w, panel_h, cs): the panel follows the menu
        scale and shrinks only when it would not fit the safe area."""
        sm = self.scaling_manager
        margin = max(12, int(18 * getattr(sm, "scale", 1.0)))
        safe_l = max(0, getattr(sm, "safe_left", 0))
        safe_r = min(self.screen_w, getattr(sm, "safe_right", self.screen_w))
        safe_t = max(0, getattr(sm, "safe_top", 0))
        safe_b = min(self.screen_h, getattr(sm, "safe_bottom", self.screen_h))
        avail_w = max(120, (safe_r - safe_l) - margin * 2)
        avail_h = max(120, (safe_b - safe_t) - margin * 2)
        ref_h = self._panel_ref_height()
        cs = min(getattr(sm, "scale", 1.0), avail_w / self._REF_W, avail_h / ref_h)
        panel_w = int(self._REF_W * cs)
        panel_h = int(ref_h * cs)
        panel_x = safe_l + (safe_r - safe_l - panel_w) // 2
        panel_y = safe_t + (safe_b - safe_t - panel_h) // 2
        return panel_x, panel_y, panel_w, panel_h, cs

    def get_continue_button_rect(self, panel_x: int, panel_y: int, panel_w: int,
                                 panel_h: int, cs: float = 1.0) -> pygame.Rect:
        btn_w = int(panel_w * BUTTON_WIDTH_RATIO)
        btn_h = max(int(BUTTON_H * cs), 40)
        btn_x = (panel_w - btn_w) // 2
        btn_y = panel_h - btn_h - int(PAD_BOTTOM * cs)
        return pygame.Rect(panel_x + btn_x, panel_y + btn_y, btn_w, btn_h)

    def stats_layout(self, panel_w: int, panel_h: int,
                     cs: float) -> tuple[int, int, int, int, int]:
        """(row1_y, row2_y, separator_y, x, width) of the stats block, panel-local.

        The rows stack upwards from the Continue button, so they can never end
        under it.
        """
        btn_rect = self.get_continue_button_rect(0, 0, panel_w, panel_h, cs)
        row_step = int(STAT_ROW_STEP * cs)
        row2_y = btn_rect.top - int(STAT_BUTTON_GAP * cs) - row_step
        row1_y = row2_y - row_step
        sep_y = row1_y - int(STAT_SEPARATOR_GAP * cs)
        stat_x = int(STAT_INSET * cs)
        return row1_y, row2_y, sep_y, stat_x, panel_w - 2 * stat_x

    def _drawn_panel_y(self, panel_y: int, cs: float) -> int:
        progress = min(1.0, self.animation_timer / self.animation_duration)
        offset = int(round(DROP_PX * cs * (1.0 - math.pow(1.0 - progress, 3))))
        return (panel_y - int(DROP_PX * cs)) + offset

    # -- state ---------------------------------------------------------------

    def show(self, score: int, stars: int, time_elapsed: float,
             is_failed: bool = False, scene_name: str = "",
             objects_found: int = 0, total_objects: int = 0) -> None:
        self.is_visible = True
        self.animation_timer = 0.0
        self.score = score
        self.display_score = 0
        self.stars = min(3, max(0, stars))
        self.time_elapsed = time_elapsed
        self.is_failed = is_failed
        self.scene_name = scene_name or ""
        self.objects_found = objects_found
        self.total_objects = total_objects
        self.star_pop_timers = [0.0, 0.0, 0.0]
        self._panel_sig = None

    def hide(self) -> None:
        self.is_visible = False

    def check_click(self, mouse_pos: tuple[int, int]) -> bool:
        """True on a click on Continue, once the panel has settled enough."""
        if not self.is_visible:
            return False
        panel_x, panel_y, panel_w, panel_h, cs = self._layout()
        progress = min(1.0, self.animation_timer / self.animation_duration)
        if progress < CLICKABLE_AT:
            return False
        draw_y = self._drawn_panel_y(panel_y, cs)
        button = self.get_continue_button_rect(panel_x, draw_y, panel_w, panel_h, cs)
        return button.collidepoint(mouse_pos)

    def on_resize(self, w: int, h: int) -> None:
        self.screen_w = w
        self.screen_h = h
        self._panel_sig = None
        if not self._android:
            self._vignette_surf = self._create_vignette(w, h)

    def update(self, dt: float) -> None:
        if not self.is_visible:
            return
        self.animation_timer += dt
        score_prog = min(1.0, self.animation_timer / SCORE_COUNT_DURATION)
        self.display_score = int(self.score * score_prog)
        for i in range(3):
            delay = STAR_DELAY + i * STAR_STAGGER
            if self.animation_timer >= delay:
                self.star_pop_timers[i] = min(self.star_pop_duration,
                                              self.animation_timer - delay)

    # -- drawing -------------------------------------------------------------

    @staticmethod
    def _create_vignette(w: int, h: int) -> pygame.Surface:
        vig = pygame.Surface((w, h), pygame.SRCALPHA)
        step = 12
        for y in range(0, h, step):
            for x in range(0, w, step):
                dx = (x - w / 2) / (w / 2)
                dy = (y - h / 2) / (h / 2)
                alpha = int(min(255, (dx * dx + dy * dy) * 150))
                pygame.draw.rect(vig, (0, 0, 8, alpha), (x, y, step, step))
        return vig

    def _compose_panel(self, panel_w: int, panel_h: int, cs: float, alpha: int,
                       perfect_alpha: int) -> pygame.Surface:
        col = self._colors()
        radius = max(6, int(BORDER_RADIUS * cs))
        panel = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)
        pygame.draw.rect(panel, (*col["bg"], PANEL_ALPHA), (0, 0, panel_w, panel_h),
                         border_radius=radius)
        pygame.draw.rect(panel, (*col["border"], 150), (0, 0, panel_w, panel_h),
                         max(1, int(2 * cs)), border_radius=radius)
        inner_w = panel_w - int(STAT_INSET * cs)

        def blit_center(surf: pygame.Surface, y: int) -> int:
            if surf.get_width() > inner_w:
                k = inner_w / surf.get_width()
                surf = pygame.transform.smoothscale(
                    surf, (int(surf.get_width() * k), int(surf.get_height() * k)))
            panel.blit(surf, ((panel_w - surf.get_width()) // 2, y))
            return y + surf.get_height()

        y = int(PAD_TOP * cs)
        if self.is_failed:
            title = self.lang("mission_failed", "Out of Time")
            title_col = col["fail"]
        else:
            title = self.lang("mission_complete", "Level Complete!")
            title_col = col["win"]
        y = blit_center(self._font("title", TITLE_SIZE, cs).render(
            title.upper(), True, title_col), y)
        if self.scene_name:
            y += int(TITLE_TO_SUBTITLE * cs)
            y = blit_center(self._font("body", SUBTITLE_SIZE, cs).render(
                self.scene_name, True, col["dim"]), y)

        y += int((HEADER_TO_STARS + STAR_RADIUS) * cs)
        star_r = int(STAR_RADIUS * cs)
        spacing = int(STAR_SPACING * cs)
        for i in range(3):
            sx = panel_w // 2 + (i - 1) * spacing
            t = self.star_pop_timers[i]
            if i < self.stars and t > 0:
                pop = min(1.0, t / self.star_pop_duration)
                k = math.sin(pop * math.pi * 0.8) * 1.25 if pop < 1.0 else 1.0
                self._draw_star(panel, sx, y, max(1, int(star_r * k)), col["star"])
            else:
                self._draw_star(panel, sx, y, star_r, col["star_off"])
        y += star_r + int(STARS_TO_SCORE * cs)

        y = blit_center(self._font("body", LABEL_SIZE, cs).render(
            self.lang("total_score", "Score").upper(), True, col["dim"]), y)
        y += int(LABEL_TO_SCORE * cs)
        y = blit_center(self._font("display", SCORE_SIZE, cs).render(
            f"{self.display_score}", True, col["accent"]), y)
        if self._has_perfect_line():
            y += int(SCORE_TO_PERFECT * cs)
            line = self._font("body", LABEL_SIZE, cs).render(
                self.lang("perfect_score", "Perfect! All found"), True, col["win"])
            line.set_alpha(perfect_alpha)
            blit_center(line, y)

        row1_y, row2_y, sep_y, stat_x, stat_w = self.stats_layout(panel_w, panel_h, cs)
        pygame.draw.line(panel, col["sep"], (stat_x, sep_y), (stat_x + stat_w, sep_y), 1)
        elapsed = f"{int(self.time_elapsed // 60)}:{int(self.time_elapsed % 60):02d}"
        self._draw_stat(panel, self.lang("time_elapsed", "Time"), elapsed,
                        row1_y, stat_x, stat_w, cs, col)
        self._draw_stat(panel, self.lang("objects_found", "Objects"),
                        f"{self.objects_found} / {self.total_objects}",
                        row2_y, stat_x, stat_w, cs, col)

        btn = self.get_continue_button_rect(0, 0, panel_w, panel_h, cs)
        pygame.draw.rect(panel, (*col["accent"], alpha), btn,
                         border_radius=max(6, int(12 * cs)))
        txt = self._font("body", BUTTON_SIZE, cs).render(
            self.lang("btn_continue", "Continue").upper(), True, col["btn_text"])
        panel.blit(txt, txt.get_rect(center=btn.center))
        return panel

    def draw(self, surface: pygame.Surface) -> None:
        if not self.is_visible:
            return
        progress = min(1.0, self.animation_timer / self.animation_duration)
        alpha = int(255 * min(1.0, progress * 1.5))
        panel_x, panel_y, panel_w, panel_h, cs = self._layout()

        if not self._android:
            backdrop = pygame.Surface((self.screen_w, self.screen_h), pygame.SRCALPHA)
            backdrop.fill((5, 5, 10, int(BACKDROP_ALPHA * progress)))
            surface.blit(backdrop, (0, 0))
            if self._vignette_surf is not None:
                surface.blit(self._vignette_surf, (0, 0))

        # The composition only changes during the opening animation (score
        # count, star pops, the perfect line fading in): recomposed when its
        # signature changes, otherwise a single blit per frame.
        perfect_alpha = int(255 * max(0.0, min(1.0, (self.animation_timer - PERFECT_DELAY) * 2)))
        sig = (panel_w, panel_h, round(cs, 3), self.is_failed, self.display_score, self.stars,
               tuple(round(t, 2) for t in self.star_pop_timers), perfect_alpha, alpha,
               self.objects_found, self.total_objects, int(self.time_elapsed),
               self.scene_name, id(self.theme))
        if self._panel_sig != sig or self._panel_cache is None:
            self._panel_cache = self._compose_panel(panel_w, panel_h, cs, alpha, perfect_alpha)
            self._panel_sig = sig
        self._panel_cache.set_alpha(alpha)
        surface.blit(self._panel_cache, (panel_x, self._drawn_panel_y(panel_y, cs)))

    def _draw_stat(self, surf, label, val, y, x, width, cs=1.0, col=None) -> None:
        col = col or self._colors()
        lbl = self._font("body", STAT_LABEL_SIZE, cs).render(label.upper(), True, col["dim"])
        v = self._font("body", STAT_VALUE_SIZE, cs).render(val, True, col["text"])
        # Label and value share one band.
        surf.blit(lbl, (x, y + (v.get_height() - lbl.get_height()) // 2))
        surf.blit(v, (x + width - v.get_width(), y))

    @staticmethod
    def _draw_star(surface, x, y, size, color, alpha=255) -> None:
        pts = []
        for i in range(10):
            ang = math.pi / 2 + i * math.pi / 5
            r = size if i % 2 == 0 else size * 0.45
            pts.append((x + r * math.cos(ang), y - r * math.sin(ang)))
        pygame.draw.polygon(surface, (*color, alpha), pts)
