"""
engine/story_overlay.py

Desktop drawing and input of the story layer (docs/engine/STORY_AND_REPLAY.md):

  - CardOverlay: story cards (full screen narration over the dimmed scene) and clue
    cards (a panel with the object icon), typed in at STORY_CHARS_PER_S.
  - JournalOverlay: the scrollable journal of clues and collectibles.
  - CollectibleToast: the short popup of a collectible find.

The overlays only hold their own state and draw themselves; the core decides when
they open, pauses the scene while one is open and routes the input to them.
All sizes are reference pixels (1280x720), scaled through the ScalingManager.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, Optional

import pygame

from engine.story import STORY_CHARS_PER_S
from engine.utils import get_logger

log = get_logger(__name__)

# -- palette (the in-scene HUD palette: dark glass, gold accent, bubble green) --
DIM_COLOR = (6, 8, 14)
DIM_ALPHA_STORY = 215          # full screen narration: the scene stays a hint behind
DIM_ALPHA_PANEL = 165          # clue card / journal: the scene stays readable
PANEL_BG = (16, 19, 30, 238)
PANEL_BORDER = (92, 110, 150, 210)
PANEL_INNER_LINE = (255, 255, 255, 18)
TEXT_MAIN = (234, 237, 245)
TEXT_SOFT = (196, 202, 218)
TEXT_DIM = (128, 136, 156)
GOLD = (255, 215, 0)
GOLD_SOFT = (238, 204, 120)
BTN_COLOR = (60, 185, 105)     # same as the bubble tip button
BTN_HOVER = (70, 210, 120)
BTN_TEXT = (255, 255, 255)
SCROLL_TRACK = (255, 255, 255, 24)
SCROLL_THUMB = (238, 204, 120, 170)
ICON_PLATE = (255, 255, 255, 14)
ICON_PLATE_BORDER = (238, 204, 120, 90)
LOCK_COLOR = (120, 128, 148)
FOOTER_RULE = (52, 58, 76)     # opaque: drawn straight on the screen surface
ROW_RULE = (255, 255, 255, 22)

# -- text sizes (reference px) --
SIZE_CHAPTER = 40
SIZE_STORY_BODY = 27
SIZE_CLUE_LABEL = 16
SIZE_CLUE_TITLE = 32
SIZE_CLUE_BODY = 22
SIZE_BUTTON = 19
SIZE_JOURNAL_TITLE = 36
SIZE_JOURNAL_SCENE = 15
SIZE_JOURNAL_OBJECT = 21
SIZE_JOURNAL_BODY = 18
SIZE_JOURNAL_FOOTER = 17
SIZE_TOAST = 22
SIZE_TOAST_POINTS = 20
# Text is read on a phone at arm's length: everything grows on touch devices.
TOUCH_TEXT_BOOST = 1.3
LINE_SPACING = 1.32

# -- layout (reference px) --
STORY_COLUMN_W = 780
STORY_RULE_W = 72
STORY_RULE_H = 2
STORY_GAP = 22
SCREEN_MARGIN = 48
BTN_H = 46
BTN_MIN_W = 190
BTN_PAD_X = 34
BTN_RADIUS = 14
PAGE_DOT_R = 4
PAGE_DOT_GAP = 14
CLUE_PANEL_W = 860
CLUE_ICON_BOX = 200
CLUE_PAD = 32
PANEL_RADIUS = 18
JOURNAL_W = 900
JOURNAL_H_RATIO = 0.86
JOURNAL_PAD = 34
JOURNAL_ROW_GAP = 18
JOURNAL_HEADER_H = 74
JOURNAL_FOOTER_H = 74
JOURNAL_SCROLL_STEP = 64
JOURNAL_SCROLLBAR_W = 5
LOCK_ICON = 16
DRAG_THRESHOLD = 6
TOAST_H = 58
TOAST_TOP = 92
TOAST_STAR_R = 15
# -- timing (seconds) --
TOAST_DURATION = 2.8
TOAST_FADE = 0.35
PULSE_SPEED = 3.0             # radians per second of the Continue button pulse
FONT_CACHE_LIMIT = 48
# -- small layout details (reference px) and button alphas --
ICON_PLATE_RADIUS = 12
ICON_INSET = 14
LOCK_TEXT_GAP = 10
TITLE_BASELINE_NUDGE = 6
SCROLL_THUMB_MIN = 24
TOAST_GAP = 14
TOAST_PAD = 22
TOAST_DROP = 10
BTN_ALPHA_TYPING = 110         # the Continue button while the text is still typing
BTN_ALPHA_BASE = 215
BTN_ALPHA_PULSE = 40
BTN_BORDER_ALPHA = 60

KIND_STORY = "story"
KIND_CLUE = "clue"


def wrap_text(text: str, font: pygame.font.Font, max_w: int) -> list[str]:
    """Word wrap that keeps explicit line breaks; a word longer than the line is cut."""
    lines: list[str] = []
    for para in str(text).replace("\r\n", "\n").split("\n"):
        words = para.split(" ")
        current = ""
        for word in words:
            candidate = f"{current} {word}" if current else word
            if font.size(candidate)[0] <= max_w:
                current = candidate
                continue
            if current:
                lines.append(current)
            current = word
            while current and font.size(current)[0] > max_w and len(current) > 1:
                cut = len(current) - 1
                while cut > 1 and font.size(current[:cut])[0] > max_w:
                    cut -= 1
                lines.append(current[:cut])
                current = current[cut:]
        lines.append(current)
    return lines


def safe_format(template: str, **values: object) -> str:
    """str.format that never raises on a translation with a broken placeholder."""
    try:
        return template.format(**values)
    except (KeyError, IndexError, ValueError):
        return template


class _Fonts:
    """Theme fonts by role (title/body), scaled; SysFont fallback without a theme."""

    def __init__(self, sm, theme=None, is_touch: bool = False) -> None:
        self._sm = sm
        self._theme = theme
        self._boost = TOUCH_TEXT_BOOST if is_touch else 1.0
        self._cache: dict[tuple, pygame.font.Font] = {}

    def ref(self, v: float) -> int:
        """A reference length in screen px (text-related sizes grow on touch)."""
        return max(1, self._sm.scale_value(v * self._boost))

    def get(self, role: str, ref_size: int, bold: bool = False) -> pygame.font.Font:
        size = int(round(ref_size * self._boost))
        if self._theme is not None:
            try:
                return self._theme.get_font_role(role, size, self._sm)
            except Exception as exc:  # a broken theme font must not stop the game
                log.warning("Story overlay: theme font '%s' unavailable (%s)", role, exc)
                self._theme = None
        key = (role, size, bold)
        font = self._cache.get(key)
        if font is None:
            if len(self._cache) >= FONT_CACHE_LIMIT:
                self._cache.pop(next(iter(self._cache)))
            font = pygame.font.SysFont("segoeui", max(10, self._sm.scale_value(size)), bold=bold)
            self._cache[key] = font
        return font


def _rounded_panel(size: tuple[int, int], radius: int, fill=PANEL_BG,
                   border=PANEL_BORDER) -> pygame.Surface:
    w, h = size
    surf = pygame.Surface((max(1, w), max(1, h)), pygame.SRCALPHA)
    pygame.draw.rect(surf, fill, (0, 0, w, h), border_radius=radius)
    pygame.draw.rect(surf, PANEL_INNER_LINE, (2, 2, w - 4, h - 4), 1,
                     border_radius=max(0, radius - 2))
    pygame.draw.rect(surf, border, (0, 0, w, h), 2, border_radius=radius)
    return surf


class _Dimmer:
    """Full screen darkening with surface alpha (cheap to blit, cached per size)."""

    def __init__(self) -> None:
        self._surf: Optional[pygame.Surface] = None
        self._key: Optional[tuple] = None

    def draw(self, screen: pygame.Surface, alpha: int) -> None:
        key = (screen.get_size(), alpha)
        if self._key != key:
            self._surf = pygame.Surface(screen.get_size())
            self._surf.fill(DIM_COLOR)
            self._surf.set_alpha(alpha)
            self._key = key
        screen.blit(self._surf, (0, 0))


def _draw_button(screen: pygame.Surface, rect: pygame.Rect, label_surf: pygame.Surface,
                 alpha: int = 255, radius: int = BTN_RADIUS) -> None:
    hover = rect.collidepoint(pygame.mouse.get_pos())
    color = BTN_HOVER if hover else BTN_COLOR
    btn = pygame.Surface(rect.size, pygame.SRCALPHA)
    pygame.draw.rect(btn, (*color, alpha), (0, 0, rect.w, rect.h), border_radius=radius)
    pygame.draw.rect(btn, (255, 255, 255, min(alpha, BTN_BORDER_ALPHA)), (0, 0, rect.w, rect.h), 1,
                     border_radius=radius)
    lbl = label_surf.copy()
    lbl.set_alpha(alpha)
    btn.blit(lbl, lbl.get_rect(center=(rect.w // 2, rect.h // 2)))
    screen.blit(btn, rect.topleft)


def _draw_lock(screen: pygame.Surface, x: int, y: int, size: int, color) -> None:
    """A small padlock drawn with shapes (no font glyph needed)."""
    body_h = int(size * 0.62)
    body = pygame.Rect(x, y + size - body_h, size, body_h)
    shackle_w = int(size * 0.64)
    shackle = pygame.Rect(x + (size - shackle_w) // 2, y, shackle_w, int(size * 0.8))
    pygame.draw.arc(screen, color, shackle, 0, math.pi, max(2, size // 7))
    pygame.draw.line(screen, color, (shackle.left + 1, shackle.centery),
                     (shackle.left + 1, body.top), max(2, size // 7))
    pygame.draw.line(screen, color, (shackle.right - 2, shackle.centery),
                     (shackle.right - 2, body.top), max(2, size // 7))
    pygame.draw.rect(screen, color, body, border_radius=max(1, size // 6))


def _star_points(cx: float, cy: float, r: float) -> list[tuple[float, float]]:
    pts = []
    for i in range(10):
        ang = -math.pi / 2 + i * math.pi / 5
        rad = r if i % 2 == 0 else r * 0.45
        pts.append((cx + math.cos(ang) * rad, cy + math.sin(ang) * rad))
    return pts


# ---------------------------------------------------------------------------
# Story and clue cards
# ---------------------------------------------------------------------------

@dataclass
class CardPage:
    """One page of a card. Story: heading = chapter (may be empty). Clue: heading =
    the "Clue found" label, title = the object name, icon = the object image."""

    body: str
    heading: str = ""
    title: str = ""
    icon: Optional[pygame.Surface] = None


class CardOverlay:
    """Story and clue cards: pages typed in one after the other, then on_close."""

    def __init__(self, sm, theme=None, is_touch: bool = False,
                 continue_label: str = "Continue") -> None:
        self._sm = sm
        self._fonts = _Fonts(sm, theme, is_touch)
        self.continue_label = continue_label
        self._dimmer = _Dimmer()
        self._pages: list[CardPage] = []
        self._index = 0
        self._chars = 0.0
        self._kind = KIND_STORY
        self._on_close: Optional[Callable[[], None]] = None
        self._time = 0.0
        self._btn_rect: Optional[pygame.Rect] = None
        self._icon_cache: Optional[tuple] = None
        self._panel_cache: Optional[tuple] = None

    # -- state -------------------------------------------------------------

    @property
    def is_open(self) -> bool:
        return bool(self._pages)

    @property
    def kind(self) -> str:
        return self._kind

    @property
    def page_index(self) -> int:
        return self._index

    @property
    def page_count(self) -> int:
        return len(self._pages)

    @property
    def is_typing(self) -> bool:
        return self.is_open and self._chars < len(self._page.body)

    @property
    def _page(self) -> CardPage:
        return self._pages[self._index]

    def open(self, pages: list[CardPage], kind: str = KIND_STORY,
             on_close: Optional[Callable[[], None]] = None) -> bool:
        """Shows the pages; False (and on_close is not kept) when there are none."""
        pages = [p for p in pages if p.body or p.title]
        if not pages:
            return False
        self._pages = pages
        self._index = 0
        self._chars = 0.0
        self._kind = kind
        self._on_close = on_close
        self._time = 0.0
        self._icon_cache = None
        log.info("Story overlay: %s card opened (%d page(s))", kind, len(pages))
        return True

    def update(self, dt: float) -> int:
        """Advances the typing; returns how many characters appeared this frame."""
        if not self.is_open:
            return 0
        self._time += dt
        total = len(self._page.body)
        before = int(self._chars)
        self._chars = min(float(total), self._chars + STORY_CHARS_PER_S * dt)
        return int(self._chars) - before

    def advance(self) -> None:
        """A click or Enter: completes the typing, else goes to the next page."""
        if not self.is_open:
            return
        if self.is_typing:
            self._chars = float(len(self._page.body))
            return
        if self._index + 1 < len(self._pages):
            self._index += 1
            self._chars = 0.0
            self._icon_cache = None
            return
        self.close()

    def reset(self) -> None:
        """Drops any open card without running its callback (new scene, quit)."""
        self._pages = []
        self._on_close = None
        self._btn_rect = None

    def close(self) -> None:
        callback = self._on_close
        self._pages = []
        self._on_close = None
        self._btn_rect = None
        log.info("Story overlay: %s card closed", self._kind)
        if callback is not None:
            callback()

    def handle_click(self, pos: tuple[int, int]) -> None:
        """Any click on a card counts: the Continue button is the visible affordance."""
        self.advance()

    # -- drawing -------------------------------------------------------------

    def draw(self, screen: pygame.Surface) -> None:
        if not self.is_open:
            return
        if self._kind == KIND_CLUE:
            self._draw_clue(screen)
        else:
            self._draw_story(screen)

    def _button(self, screen: pygame.Surface, x: int, bottom: int,
                align_right: bool = False) -> None:
        """The Continue button: bottom-centred on x, or with its right edge on x."""
        font = self._fonts.get("body", SIZE_BUTTON, bold=True)
        label = font.render(self.continue_label.upper(), True, BTN_TEXT)
        w = max(self._fonts.ref(BTN_MIN_W), label.get_width() + self._fonts.ref(BTN_PAD_X) * 2)
        h = self._fonts.ref(BTN_H)
        rect = pygame.Rect(0, 0, w, h)
        if align_right:
            rect.bottomright = (x, bottom)
        else:
            rect.midbottom = (x, bottom)
        self._btn_rect = rect
        if self.is_typing:
            alpha = BTN_ALPHA_TYPING
        else:
            pulse = 0.5 + 0.5 * math.sin(self._time * PULSE_SPEED)
            alpha = int(BTN_ALPHA_BASE + BTN_ALPHA_PULSE * pulse)
        _draw_button(screen, rect, label, alpha, self._fonts.ref(BTN_RADIUS))

    def _draw_page_dots(self, screen: pygame.Surface, center_x: int, y: int) -> None:
        n = len(self._pages)
        if n < 2:
            return
        r = self._fonts.ref(PAGE_DOT_R)
        gap = self._fonts.ref(PAGE_DOT_GAP)
        x0 = center_x - (n - 1) * gap // 2
        for i in range(n):
            color = GOLD_SOFT if i == self._index else TEXT_DIM
            pygame.draw.circle(screen, color, (x0 + i * gap, y), r if i == self._index else r - 1)

    def _typed_lines(self, screen: pygame.Surface, lines: list[str], font: pygame.font.Font,
                     x: int, y: int, width: int, color, center: bool) -> None:
        budget = int(self._chars)
        line_h = int(font.get_linesize() * LINE_SPACING)
        for i, line in enumerate(lines):
            if budget <= 0:
                break
            shown = line[:budget]
            budget -= len(line) + 1
            if not shown:
                continue
            surf = font.render(shown, True, color)
            if center:
                full_w = font.size(line)[0]
                lx = x + (width - full_w) // 2
            else:
                lx = x
            screen.blit(surf, (lx, y + i * line_h))

    def _draw_story(self, screen: pygame.Surface) -> None:
        sm = self._sm
        sw, sh = screen.get_size()
        self._dimmer.draw(screen, DIM_ALPHA_STORY)
        page = self._page
        margin = self._fonts.ref(SCREEN_MARGIN)
        col_w = min(self._fonts.ref(STORY_COLUMN_W),
                    sm.safe_right - sm.safe_left - 2 * margin)
        col_x = (sw - col_w) // 2
        body_font = self._fonts.get("body", SIZE_STORY_BODY)
        lines = wrap_text(page.body, body_font, col_w)
        line_h = int(body_font.get_linesize() * LINE_SPACING)
        body_h = line_h * len(lines)

        head_surf = None
        head_h = 0
        if page.heading:
            head_font = self._fonts.get("title", SIZE_CHAPTER, bold=True)
            head_surf = head_font.render(page.heading, True, GOLD_SOFT)
            if head_surf.get_width() > col_w:
                scale = col_w / head_surf.get_width()
                head_surf = pygame.transform.smoothscale(
                    head_surf, (col_w, max(1, int(head_surf.get_height() * scale))))
            gap = self._fonts.ref(STORY_GAP)
            head_h = head_surf.get_height() + gap + self._fonts.ref(STORY_RULE_H) + gap

        btn_zone = self._fonts.ref(BTN_H) + self._fonts.ref(STORY_GAP) * 3
        top = sm.safe_top + margin
        avail = (sm.safe_bottom - margin - btn_zone) - top
        y = top + max(0, (avail - head_h - body_h) // 2)
        if head_surf is not None:
            screen.blit(head_surf, ((sw - head_surf.get_width()) // 2, y))
            y += head_surf.get_height() + self._fonts.ref(STORY_GAP)
            rule_w = self._fonts.ref(STORY_RULE_W)
            pygame.draw.rect(screen, GOLD_SOFT, ((sw - rule_w) // 2, y, rule_w,
                                                 self._fonts.ref(STORY_RULE_H)))
            y += self._fonts.ref(STORY_RULE_H) + self._fonts.ref(STORY_GAP)
        self._typed_lines(screen, lines, body_font, col_x, y, col_w, TEXT_MAIN, center=True)

        bottom = sm.safe_bottom - margin
        self._button(screen, sw // 2, bottom)
        self._draw_page_dots(screen, sw // 2,
                             bottom - self._fonts.ref(BTN_H) - self._fonts.ref(STORY_GAP))

    def _scaled_icon(self, icon: pygame.Surface, box: int) -> pygame.Surface:
        key = (id(icon), box)
        if self._icon_cache is not None and self._icon_cache[0] == key:
            return self._icon_cache[1]
        iw, ih = icon.get_size()
        k = min(box / max(1, iw), box / max(1, ih))
        scaled = pygame.transform.smoothscale(icon, (max(1, int(iw * k)), max(1, int(ih * k))))
        self._icon_cache = (key, scaled)
        return scaled

    def _draw_clue(self, screen: pygame.Surface) -> None:
        sm = self._sm
        sw, sh = screen.get_size()
        self._dimmer.draw(screen, DIM_ALPHA_PANEL)
        page = self._page
        f = self._fonts
        pad = f.ref(CLUE_PAD)
        panel_w = min(f.ref(CLUE_PANEL_W), sm.safe_right - sm.safe_left - 2 * f.ref(SCREEN_MARGIN))
        icon_box = f.ref(CLUE_ICON_BOX) if page.icon is not None else 0
        if icon_box and panel_w - icon_box - 3 * pad < f.ref(CLUE_ICON_BOX):
            icon_box = max(0, (panel_w - 3 * pad) // 3)
        text_x_off = pad + (icon_box + pad if icon_box else 0)
        text_w = panel_w - text_x_off - pad

        label_font = f.get("body", SIZE_CLUE_LABEL, bold=True)
        title_font = f.get("title", SIZE_CLUE_TITLE, bold=True)
        body_font = f.get("body", SIZE_CLUE_BODY)
        label = label_font.render(page.heading.upper(), True, GOLD) if page.heading else None
        title_lines = wrap_text(page.title, title_font, text_w) if page.title else []
        body_lines = wrap_text(page.body, body_font, text_w)
        body_lh = int(body_font.get_linesize() * LINE_SPACING)
        gap = f.ref(STORY_GAP) // 2
        text_h = ((label.get_height() + gap) if label else 0) \
            + title_font.get_linesize() * len(title_lines) + gap * 2 \
            + body_lh * len(body_lines)
        content_h = max(icon_box, text_h)
        btn_h = f.ref(BTN_H)
        panel_h = pad + content_h + pad + btn_h + pad
        panel_h = min(panel_h, sm.safe_bottom - sm.safe_top - f.ref(SCREEN_MARGIN))
        px = (sw - panel_w) // 2
        py = (sh - panel_h) // 2

        key = (panel_w, panel_h)
        if self._panel_cache is None or self._panel_cache[0] != key:
            self._panel_cache = (key, _rounded_panel(key, f.ref(PANEL_RADIUS)))
        screen.blit(self._panel_cache[1], (px, py))

        if icon_box and page.icon is not None:
            plate = pygame.Rect(px + pad, py + pad + (content_h - icon_box) // 2,
                                icon_box, icon_box)
            plate_s = pygame.Surface(plate.size, pygame.SRCALPHA)
            radius = f.ref(ICON_PLATE_RADIUS)
            pygame.draw.rect(plate_s, ICON_PLATE, (0, 0, *plate.size), border_radius=radius)
            pygame.draw.rect(plate_s, ICON_PLATE_BORDER, (0, 0, *plate.size), 1,
                             border_radius=radius)
            screen.blit(plate_s, plate.topleft)
            inner = max(1, icon_box - 2 * f.ref(ICON_INSET))
            icon = self._scaled_icon(page.icon, inner)
            screen.blit(icon, icon.get_rect(center=plate.center))

        tx = px + text_x_off
        ty = py + pad + max(0, (content_h - text_h) // 2)
        if label:
            screen.blit(label, (tx, ty))
            ty += label.get_height() + gap
        for line in title_lines:
            screen.blit(title_font.render(line, True, TEXT_MAIN), (tx, ty))
            ty += title_font.get_linesize()
        pygame.draw.rect(screen, GOLD_SOFT, (tx, ty + gap // 2, f.ref(STORY_RULE_W),
                                             f.ref(STORY_RULE_H)))
        ty += gap * 2
        self._typed_lines(screen, body_lines, body_font, tx, ty, text_w, TEXT_SOFT, center=False)

        self._button(screen, px + panel_w - pad, py + panel_h - pad, align_right=True)


# ---------------------------------------------------------------------------
# Journal
# ---------------------------------------------------------------------------

@dataclass
class JournalRow:
    scene_name: str
    object_name: str = ""
    clue_text: str = ""
    unlocked: bool = False


@dataclass
class JournalView:
    """Everything the journal shows, already localized."""

    title: str
    rows: list[JournalRow]
    locked_text: str
    empty_text: str
    footer: str = ""
    epilogue_title: str = ""
    epilogue_text: str = ""
    close_label: str = "Close"


class JournalOverlay:
    """Scrollable journal panel. Closes on a click outside, Esc or its button."""

    def __init__(self, sm, theme=None, is_touch: bool = False) -> None:
        self._sm = sm
        self._fonts = _Fonts(sm, theme, is_touch)
        self._dimmer = _Dimmer()
        self._view: Optional[JournalView] = None
        self._scroll = 0
        self._content: Optional[pygame.Surface] = None
        self._content_key: Optional[tuple] = None
        self._panel_cache: Optional[tuple] = None
        self._panel_rect = pygame.Rect(0, 0, 0, 0)
        self._viewport = pygame.Rect(0, 0, 0, 0)
        self._close_rect: Optional[pygame.Rect] = None
        self._drag_y: Optional[int] = None
        self._drag_scroll = 0
        self._dragged = False

    @property
    def is_open(self) -> bool:
        return self._view is not None

    def open(self, view: JournalView) -> None:
        self._view = view
        self._scroll = 0
        self._content = None
        self._content_key = None
        self._drag_y = None
        log.info("Journal opened (%d entries)", len(view.rows))

    def close(self) -> None:
        if self._view is not None:
            log.info("Journal closed")
        self._view = None
        self._content = None
        self._drag_y = None

    # -- input ---------------------------------------------------------------

    def _max_scroll(self) -> int:
        if self._content is None:
            return 0
        return max(0, self._content.get_height() - self._viewport.h)

    def scroll_by(self, delta_px: int) -> None:
        self._scroll = max(0, min(self._max_scroll(), self._scroll + int(delta_px)))

    def handle_wheel(self, wheel_y: int) -> None:
        self.scroll_by(-wheel_y * self._fonts.ref(JOURNAL_SCROLL_STEP))

    def handle_key(self, key: int) -> bool:
        """Esc closes, arrows/page keys scroll. True when the key was used."""
        if key in (pygame.K_ESCAPE, pygame.K_AC_BACK, pygame.K_j):
            self.close()
            return True
        step = self._fonts.ref(JOURNAL_SCROLL_STEP)
        page = max(step, self._viewport.h - step)
        moves = {pygame.K_UP: -step, pygame.K_DOWN: step,
                 pygame.K_PAGEUP: -page, pygame.K_PAGEDOWN: page,
                 pygame.K_HOME: -10 ** 6, pygame.K_END: 10 ** 6}
        if key in moves:
            self.scroll_by(moves[key])
            return True
        return False

    def handle_down(self, pos: tuple[int, int]) -> None:
        if not self.is_open:
            return
        if self._close_rect is not None and self._close_rect.collidepoint(pos):
            self.close()
            return
        if not self._panel_rect.collidepoint(pos):
            self.close()
            return
        self._drag_y = pos[1]
        self._drag_scroll = self._scroll
        self._dragged = False

    def handle_motion(self, pos: tuple[int, int], pressed: bool) -> None:
        if self._drag_y is None or not pressed:
            return
        dy = pos[1] - self._drag_y
        if abs(dy) > self._fonts.ref(DRAG_THRESHOLD):
            self._dragged = True
        if self._dragged:
            self._scroll = max(0, min(self._max_scroll(), self._drag_scroll - dy))

    def handle_up(self, pos: tuple[int, int]) -> None:
        self._drag_y = None

    # -- drawing -------------------------------------------------------------

    def _build_content(self, width: int) -> pygame.Surface:
        view = self._view
        f = self._fonts
        scene_font = f.get("body", SIZE_JOURNAL_SCENE, bold=True)
        obj_font = f.get("title", SIZE_JOURNAL_OBJECT, bold=True)
        body_font = f.get("body", SIZE_JOURNAL_BODY)
        body_lh = int(body_font.get_linesize() * LINE_SPACING)
        row_gap = f.ref(JOURNAL_ROW_GAP)
        lock = f.ref(LOCK_ICON)
        blocks: list[tuple[str, object]] = []   # (kind, payload) drawn in order

        if not any(r.unlocked for r in view.rows):
            blocks.append(("empty", wrap_text(view.empty_text, body_font, width)))
        for row in view.rows:
            if row.unlocked:
                blocks.append(("row", (row.scene_name.upper(), row.object_name,
                                       wrap_text(row.clue_text, body_font, width))))
            else:
                blocks.append(("locked", (row.scene_name.upper(), view.locked_text)))
        if view.epilogue_text:
            blocks.append(("epilogue", (view.epilogue_title,
                                        wrap_text(view.epilogue_text, body_font, width))))

        # Measure, then draw onto one tall surface (rebuilt only on open/resize).
        def block_h(kind: str, payload) -> int:
            if kind == "empty":
                return body_lh * len(payload)
            if kind == "row":
                return (scene_font.get_linesize() + obj_font.get_linesize()
                        + body_lh * len(payload[2]))
            if kind == "locked":
                return scene_font.get_linesize() + max(lock, body_font.get_linesize())
            return obj_font.get_linesize() + row_gap // 2 + body_lh * len(payload[1])

        total = sum(block_h(k, p) for k, p in blocks) + row_gap * 2 * max(0, len(blocks) - 1)
        surf = pygame.Surface((width, max(1, total)), pygame.SRCALPHA)
        y = 0
        for i, (kind, payload) in enumerate(blocks):
            if i > 0:
                y += row_gap
                pygame.draw.line(surf, ROW_RULE, (0, y), (width, y))
                y += row_gap
            if kind == "empty":
                for line in payload:
                    surf.blit(body_font.render(line, True, TEXT_DIM), (0, y))
                    y += body_lh
            elif kind == "row":
                scene, obj, lines = payload
                surf.blit(scene_font.render(scene, True, GOLD_SOFT), (0, y))
                y += scene_font.get_linesize()
                if obj:
                    surf.blit(obj_font.render(obj, True, TEXT_MAIN), (0, y))
                y += obj_font.get_linesize()
                for line in lines:
                    surf.blit(body_font.render(line, True, TEXT_SOFT), (0, y))
                    y += body_lh
            elif kind == "locked":
                scene, text = payload
                surf.blit(scene_font.render(scene, True, TEXT_DIM), (0, y))
                y += scene_font.get_linesize()
                line_h = max(lock, body_font.get_linesize())
                _draw_lock(surf, 0, y + (line_h - lock) // 2, lock, LOCK_COLOR)
                txt = body_font.render(text, True, TEXT_DIM)
                surf.blit(txt, (lock + f.ref(LOCK_TEXT_GAP), y + (line_h - txt.get_height()) // 2))
                y += line_h
            else:
                title, lines = payload
                if title:
                    surf.blit(obj_font.render(title, True, GOLD), (0, y))
                y += obj_font.get_linesize() + row_gap // 2
                for line in lines:
                    surf.blit(body_font.render(line, True, TEXT_MAIN), (0, y))
                    y += body_lh
        return surf

    def draw(self, screen: pygame.Surface) -> None:
        if not self.is_open:
            return
        view = self._view
        sm = self._sm
        f = self._fonts
        sw, sh = screen.get_size()
        self._dimmer.draw(screen, DIM_ALPHA_PANEL)
        margin = f.ref(SCREEN_MARGIN) // 2
        panel_w = min(f.ref(JOURNAL_W), sm.safe_right - sm.safe_left - 2 * margin)
        panel_h = min(int(sh * JOURNAL_H_RATIO), sm.safe_bottom - sm.safe_top - 2 * margin)
        px, py = (sw - panel_w) // 2, (sh - panel_h) // 2
        self._panel_rect = pygame.Rect(px, py, panel_w, panel_h)
        key = (panel_w, panel_h)
        if self._panel_cache is None or self._panel_cache[0] != key:
            self._panel_cache = (key, _rounded_panel(key, f.ref(PANEL_RADIUS)))
        screen.blit(self._panel_cache[1], (px, py))

        pad = f.ref(JOURNAL_PAD)
        header_h = f.ref(JOURNAL_HEADER_H)
        footer_h = f.ref(JOURNAL_FOOTER_H)
        title_font = f.get("title", SIZE_JOURNAL_TITLE, bold=True)
        title = title_font.render(view.title, True, TEXT_MAIN)
        screen.blit(title, (px + pad, py + (header_h - title.get_height()) // 2
                            + f.ref(TITLE_BASELINE_NUDGE)))
        pygame.draw.line(screen, GOLD_SOFT, (px + pad, py + header_h),
                         (px + pad + f.ref(STORY_RULE_W), py + header_h), f.ref(STORY_RULE_H))

        bar_w = f.ref(JOURNAL_SCROLLBAR_W)
        content_w = panel_w - 2 * pad - bar_w * 3
        self._viewport = pygame.Rect(px + pad, py + header_h + pad // 2, content_w,
                                     panel_h - header_h - footer_h - pad // 2)
        ckey = (content_w, id(view))
        if self._content is None or self._content_key != ckey:
            self._content = self._build_content(content_w)
            self._content_key = ckey
            self._scroll = min(self._scroll, self._max_scroll())
        prev_clip = screen.get_clip()
        screen.set_clip(self._viewport)
        screen.blit(self._content, (self._viewport.x, self._viewport.y - self._scroll))
        screen.set_clip(prev_clip)

        max_scroll = self._max_scroll()
        if max_scroll > 0:
            track = pygame.Rect(px + panel_w - pad // 2 - bar_w, self._viewport.y,
                                bar_w, self._viewport.h)
            track_s = pygame.Surface(track.size, pygame.SRCALPHA)
            track_s.fill(SCROLL_TRACK)
            screen.blit(track_s, track.topleft)
            ratio = self._viewport.h / self._content.get_height()
            thumb_h = max(f.ref(SCROLL_THUMB_MIN), int(track.h * ratio))
            thumb_y = track.y + int((track.h - thumb_h) * (self._scroll / max_scroll))
            thumb = pygame.Surface((bar_w, thumb_h), pygame.SRCALPHA)
            pygame.draw.rect(thumb, SCROLL_THUMB, (0, 0, bar_w, thumb_h),
                             border_radius=bar_w // 2)
            screen.blit(thumb, (track.x, thumb_y))

        footer_y = py + panel_h - footer_h
        pygame.draw.line(screen, FOOTER_RULE, (px + pad, footer_y),
                         (px + panel_w - pad, footer_y))
        if view.footer:
            ffont = f.get("body", SIZE_JOURNAL_FOOTER, bold=True)
            ftxt = ffont.render(view.footer, True, GOLD_SOFT)
            screen.blit(ftxt, (px + pad, footer_y + (footer_h - ftxt.get_height()) // 2))
        bfont = f.get("body", SIZE_BUTTON, bold=True)
        blabel = bfont.render(view.close_label.upper(), True, BTN_TEXT)
        bw = max(f.ref(BTN_MIN_W) * 3 // 4, blabel.get_width() + f.ref(BTN_PAD_X) * 2)
        bh = f.ref(BTN_H)
        self._close_rect = pygame.Rect(0, 0, bw, bh)
        self._close_rect.midright = (px + panel_w - pad, footer_y + footer_h // 2)
        _draw_button(screen, self._close_rect, blabel, 255, f.ref(BTN_RADIUS))


# ---------------------------------------------------------------------------
# Collectible toast
# ---------------------------------------------------------------------------

class CollectibleToast:
    """A short pill at the top of the screen: star, "<name> found!", "+points"."""

    def __init__(self, sm, theme=None, is_touch: bool = False) -> None:
        self._sm = sm
        self._fonts = _Fonts(sm, theme, is_touch)
        self._text = ""
        self._points = ""
        self._t = 0.0

    @property
    def is_visible(self) -> bool:
        return self._t > 0.0

    def show(self, text: str, points_text: str = "") -> None:
        self._text = text
        self._points = points_text
        self._t = TOAST_DURATION

    def update(self, dt: float) -> None:
        if self._t > 0.0:
            self._t = max(0.0, self._t - dt)

    def draw(self, screen: pygame.Surface) -> None:
        if not self.is_visible:
            return
        f = self._fonts
        elapsed = TOAST_DURATION - self._t
        alpha = 1.0
        if elapsed < TOAST_FADE:
            alpha = elapsed / TOAST_FADE
        elif self._t < TOAST_FADE:
            alpha = self._t / TOAST_FADE
        text = f.get("body", SIZE_TOAST, bold=True).render(self._text, True, TEXT_MAIN)
        pts = (f.get("body", SIZE_TOAST_POINTS, bold=True).render(self._points, True, GOLD)
               if self._points else None)
        star_r = f.ref(TOAST_STAR_R)
        gap = f.ref(TOAST_GAP)
        pad = f.ref(TOAST_PAD)
        h = f.ref(TOAST_H)
        w = pad + star_r * 2 + gap + text.get_width() + (gap + pts.get_width() if pts else 0) + pad
        surf = pygame.Surface((w, h), pygame.SRCALPHA)
        pygame.draw.rect(surf, PANEL_BG, (0, 0, w, h), border_radius=h // 2)
        pygame.draw.rect(surf, (*GOLD_SOFT, 150), (0, 0, w, h), 2, border_radius=h // 2)
        cx = pad + star_r
        pygame.draw.polygon(surf, GOLD, _star_points(cx, h / 2, star_r))
        x = pad + star_r * 2 + gap
        surf.blit(text, (x, (h - text.get_height()) // 2))
        if pts:
            surf.blit(pts, (x + text.get_width() + gap, (h - pts.get_height()) // 2))
        surf.set_alpha(int(255 * alpha))
        sw = screen.get_width()
        drop = int(f.ref(TOAST_DROP) * (1.0 - min(1.0, elapsed / TOAST_FADE)))
        screen.blit(surf, ((sw - w) // 2, self._sm.safe_top + f.ref(TOAST_TOP) - drop))
