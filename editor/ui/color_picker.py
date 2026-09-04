"""
editor/ui/color_picker.py

Color picker HSV con palette estratta dal background.

ColorPickerModal e' un modale NON bloccante per lo stack modale unificato
dell'editor (editor.modal_stack): render/handle_event per frame, callback
on_done(color | None) alla chiusura. Sostituisce il vecchio ask_color con
event-loop bloccante separato.
"""

import math
from typing import Callable, Optional

import pygame

from engine.language_manager import tr
from editor.constants import PANEL, BORDER, TXT_HI, TXT_DIM
from editor.ui.draw import _txt, _rect, _button, _in_rect

# Geometria del modale
PICKER_W, PICKER_H = 480, 520
PAD = 20
HUE_BAR_H = 20
SV_H = 256
SWATCH = 30
SWATCH_GAP = 4
BTN_W, BTN_H = 100, 30
PALETTE_N = 10
PALETTE_MIN_DIST = 30
OVERLAY_ALPHA = 150


def extract_palette(surf: pygame.Surface, n: int = PALETTE_N) -> list:
    if not surf:
        return []
    small = pygame.transform.scale(surf, (50, 50))
    counts: dict = {}
    for x in range(50):
        for y in range(50):
            r, g, b, _ = small.get_at((x, y))
            color = (r // 16 * 16, g // 16 * 16, b // 16 * 16)
            counts[color] = counts.get(color, 0) + 1

    sorted_colors = sorted(counts.items(), key=lambda idx: idx[1], reverse=True)
    res: list = []

    # Prendi i primi N colori distanti almeno un po'
    for color, _count in sorted_colors:
        if len(res) >= n:
            break
        too_close = False
        for rgb in res:
            dist = math.hypot(color[0] - rgb[0],
                              math.hypot(color[1] - rgb[1], color[2] - rgb[2]))
            if dist < PALETTE_MIN_DIST:
                too_close = True
                break
        if not too_close:
            res.append(color)

    if len(res) < n:
        for color, _count in sorted_colors:
            if color not in res:
                res.append(color)
            if len(res) >= n:
                break
    return res


def build_sv_surface(hue: float, w: int, h: int) -> pygame.Surface:
    surf = pygame.Surface((w, h))
    for x in range(w):
        for y in range(h):
            s = x / w * 100
            v = 100 - (y / h * 100)
            c = pygame.Color(0)
            c.hsva = (hue, s, max(0, min(100, v)), 100)
            surf.set_at((x, y), c)
    return surf


def build_hue_surface(w: int, h: int) -> pygame.Surface:
    surf = pygame.Surface((w, h))
    for x in range(w):
        hue = (x / w) * 360
        c = pygame.Color(0)
        c.hsva = (hue, 100, 100, 100)
        pygame.draw.line(surf, c, (x, 0), (x, h))
    return surf


class ColorPickerModal:
    """Selettore colore HSV non bloccante per lo stack modale dell'editor."""

    def __init__(self, bg_surf: Optional[pygame.Surface],
                 initial_color=(255, 255, 255),
                 title: str = "",
                 on_done: Optional[Callable[[Optional[tuple]], None]] = None) -> None:
        self.title = title
        self.on_done = on_done
        c = pygame.Color(*initial_color)
        self.hue, self.sat, self.val, _ = c.hsva
        self.palette = extract_palette(bg_surf, PALETTE_N)
        self.dragging_hue = False
        self.dragging_sv = False
        self._hue_surf: Optional[pygame.Surface] = None
        self._sv_surf: Optional[pygame.Surface] = None
        self._sv_hue_drawn: Optional[float] = None
        # Rects calcolati dal layout corrente (finestra ridimensionabile)
        self._rects: dict = {}

    # ── Layout ───────────────────────────────────────────────────────────────

    def _layout(self, w_win: int, h_win: int) -> dict:
        x = (w_win - PICKER_W) // 2
        y = (h_win - PICKER_H) // 2
        inner_w = PICKER_W - PAD * 2
        rects = {
            "panel": pygame.Rect(x, y, PICKER_W, PICKER_H),
            "hue": pygame.Rect(x + PAD, y + 60, inner_w, HUE_BAR_H),
            "sv": pygame.Rect(x + PAD, y + 90, inner_w, SV_H),
            "palette_origin": (x + PAD, y + 370),
            "ok": pygame.Rect(x + PICKER_W - PAD * 2 - BTN_W * 2 - 10,
                              y + PICKER_H - 50, BTN_W, BTN_H),
            "cancel": pygame.Rect(x + PICKER_W - PAD - BTN_W,
                                  y + PICKER_H - 50, BTN_W, BTN_H),
            "current": pygame.Rect(x + PAD, y + PICKER_H - 50, 40, BTN_H),
        }
        self._rects = rects
        return rects

    def _current_color(self) -> tuple:
        c = pygame.Color(0)
        c.hsva = (self.hue, self.sat, max(0, min(100, self.val)), 100)
        return (c.r, c.g, c.b)

    def _close(self, editor, result: Optional[tuple]) -> None:
        editor._modal_pop(self)
        if self.on_done:
            self.on_done(result)

    # ── Input ────────────────────────────────────────────────────────────────

    def handle_event(self, editor, ev) -> bool:
        w_win, h_win = editor.screen.get_size()
        r = self._layout(w_win, h_win)

        if ev.type == pygame.KEYDOWN:
            if ev.key == pygame.K_ESCAPE:
                self._close(editor, None)
            elif ev.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                self._close(editor, self._current_color())
            return True

        if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
            pos = ev.pos
            if _in_rect(pos, r["hue"]):
                self.dragging_hue = True
                self._apply_hue(pos[0], r)
            elif _in_rect(pos, r["sv"]):
                self.dragging_sv = True
                self._apply_sv(pos, r)
            elif _in_rect(pos, r["ok"]):
                self._close(editor, self._current_color())
            elif _in_rect(pos, r["cancel"]):
                self._close(editor, None)
            else:
                ox, oy = r["palette_origin"]
                for pcol in self.palette:
                    swatch = pygame.Rect(ox, oy, SWATCH, SWATCH)
                    if _in_rect(pos, swatch):
                        pc = pygame.Color(*pcol)
                        self.hue, self.sat, self.val, _ = pc.hsva
                        break
                    ox += SWATCH + SWATCH_GAP
            return True

        if ev.type == pygame.MOUSEBUTTONUP and ev.button == 1:
            self.dragging_hue = False
            self.dragging_sv = False
            return True

        if ev.type == pygame.MOUSEMOTION:
            if self.dragging_hue:
                self._apply_hue(ev.pos[0], r)
            elif self.dragging_sv:
                self._apply_sv(ev.pos, r)
            return True

        return True  # app-modal: consuma comunque l'input utente

    def _apply_hue(self, mx: int, r: dict) -> None:
        rel_x = max(0.0, min(1.0, (mx - r["hue"].x) / r["hue"].width))
        self.hue = rel_x * 360
        if self.hue >= 360:
            self.hue = 0

    def _apply_sv(self, pos, r: dict) -> None:
        rel_x = max(0.0, min(1.0, (pos[0] - r["sv"].x) / r["sv"].width))
        rel_y = max(0.0, min(1.0, (pos[1] - r["sv"].y) / r["sv"].height))
        self.sat = rel_x * 100
        self.val = 100 - (rel_y * 100)

    # ── Render ───────────────────────────────────────────────────────────────

    def render(self, editor) -> None:
        screen = editor.screen
        w_win, h_win = screen.get_size()
        r = self._layout(w_win, h_win)
        mx, my = pygame.mouse.get_pos()

        # Overlay scuro sull'editor (ridisegnato sotto ogni frame)
        overlay = pygame.Surface((w_win, h_win), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, OVERLAY_ALPHA))
        screen.blit(overlay, (0, 0))

        panel = r["panel"]
        _rect(screen, PANEL, panel, radius=8)
        _rect(screen, BORDER, panel, 1, radius=8)

        header = _txt(self.title or tr("cp_title", "Select color"),
                      "md", TXT_HI)
        screen.blit(header, (panel.x + PAD, panel.y + PAD))

        # Barre (cache: hue statica, sv rigenerata al cambio di hue)
        if (self._hue_surf is None
                or self._hue_surf.get_size() != r["hue"].size):
            self._hue_surf = build_hue_surface(r["hue"].width, r["hue"].height)
        if (self._sv_surf is None or self._sv_hue_drawn != self.hue
                or self._sv_surf.get_size() != r["sv"].size):
            self._sv_surf = build_sv_surface(self.hue, r["sv"].width, r["sv"].height)
            self._sv_hue_drawn = self.hue

        screen.blit(self._hue_surf, r["hue"])
        pygame.draw.rect(screen, BORDER, r["hue"], 1)
        hx = r["hue"].x + int((self.hue / 360) * r["hue"].width)
        pygame.draw.line(screen, (255, 255, 255),
                         (hx, r["hue"].y - 2), (hx, r["hue"].bottom + 2), 2)
        pygame.draw.line(screen, (0, 0, 0),
                         (hx, r["hue"].y - 2), (hx, r["hue"].bottom + 2), 1)

        screen.blit(self._sv_surf, r["sv"])
        pygame.draw.rect(screen, BORDER, r["sv"], 1)
        sx = r["sv"].x + int((self.sat / 100) * r["sv"].width)
        sy = r["sv"].y + int(((100 - self.val) / 100) * r["sv"].height)
        pygame.draw.circle(screen, (255, 255, 255), (sx, sy), 5, 1)
        pygame.draw.circle(screen, (0, 0, 0), (sx, sy), 6, 1)

        lbl_pal = _txt(tr("cp_from_background", "Sampled from the background:"), "sm", TXT_DIM)
        screen.blit(lbl_pal, (panel.x + PAD, panel.y + 350))

        ox, oy = r["palette_origin"]
        for pcol in self.palette:
            pr = pygame.Rect(ox, oy, SWATCH, SWATCH)
            _rect(screen, pcol, pr)
            _rect(screen, BORDER, pr, 1)
            ox += SWATCH + SWATCH_GAP

        cur = self._current_color()
        _rect(screen, cur, r["current"])
        _rect(screen, BORDER, r["current"], 1)
        val_txt = _txt(f"RGB: {cur[0]}, {cur[1]}, {cur[2]}", "sm", TXT_HI)
        screen.blit(val_txt, (panel.x + 70, panel.y + PICKER_H - 45))

        _button(screen, r["ok"], tr("btn_apply", "Apply"), _in_rect((mx, my), r["ok"]), active=True)
        _button(screen, r["cancel"], tr("btn_cancel", "Cancel"), _in_rect((mx, my), r["cancel"]))
