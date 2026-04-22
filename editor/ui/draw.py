"""
editor/ui/draw.py

Primitive di disegno e gestione font per l'editor.
Tutte le funzioni sono module-level (non metodi) e possono essere importate
con `from editor.ui.draw import *` nei mixin e nel modulo principale.
"""

import pygame

# ─────────────────────────────────────────────────────────────────────────────
# FONT
# ─────────────────────────────────────────────────────────────────────────────

_FONTS: dict = {}


def _init_fonts():
    candidates_ui   = ["Segoe UI", "Arial", "DejaVu Sans", None]
    candidates_mono = ["Consolas", "Courier New", "Courier", None]

    def best_font(candidates, size):
        for name in candidates:
            try:
                return pygame.font.SysFont(name, size)
            except Exception:
                continue
        return pygame.font.Font(None, size)

    _FONTS["xs"]   = best_font(candidates_ui,   11)
    _FONTS["sm"]   = best_font(candidates_ui,   13)
    _FONTS["md"]   = best_font(candidates_ui,   16)
    _FONTS["lg"]   = best_font(candidates_ui,   20)
    _FONTS["xl"]   = best_font(candidates_ui,   30)
    _FONTS["mono"] = best_font(candidates_mono, 13)


# ─────────────────────────────────────────────────────────────────────────────
# TESTO
# ─────────────────────────────────────────────────────────────────────────────

def _txt(text: str, font_key: str, color: tuple) -> pygame.Surface:
    return _FONTS.get(font_key, _FONTS["md"]).render(str(text), True, color)


def _draw_text(surf, text, font_key, color, x, y, max_w=None):
    s    = str(text)
    font = _FONTS.get(font_key, _FONTS["md"])
    rendered = font.render(s, True, color)
    if max_w and rendered.get_width() > max_w:
        while len(s) > 1 and font.size(s + "...")[0] > max_w:
            s = s[:-1]
        rendered = font.render(s + "...", True, color)
    surf.blit(rendered, (x, y))
    return rendered.get_width()


def _text_wh(text: str, font_key: str) -> tuple:
    return _FONTS.get(font_key, _FONTS["md"]).size(str(text))


# ─────────────────────────────────────────────────────────────────────────────
# PRIMITIVE UI
# ─────────────────────────────────────────────────────────────────────────────

def _rect(surf, color, r, border=0, radius=0):
    try:
        # Assicura che le coordinate siano interi (previene TypeError in alcune versioni di pygame)
        ir = (int(r[0]), int(r[1]), int(r[2]), int(r[3]))
        if radius > 0:
            pygame.draw.rect(surf, color, ir, int(border), border_radius=int(radius))
        else:
            pygame.draw.rect(surf, color, ir, int(border))
    except Exception as e:
        import logging
        logging.error(f"Error drawing rect {r} with color {color}, radius {radius}: {e}")


def _draw_shape_icon(surf, r, icon_id, color):
    """Disegna icone procedurali per evitare problemi di font/unicode."""
    import pygame
    cx, cy = r[0] + r[2]//2, r[1] + r[3]//2
    sz = min(r[2], r[3]) // 2 - 5
    
    if icon_id == "up":
        pts = [(cx, cy - sz), (cx - sz, cy + sz - 2), (cx + sz, cy + sz - 2)]
        pygame.draw.polygon(surf, color, pts)
    elif icon_id == "down":
        pts = [(cx, cy + sz), (cx - sz, cy - sz + 2), (cx + sz, cy - sz + 2)]
        pygame.draw.polygon(surf, color, pts)
    elif icon_id == "play":
        pts = [(cx + sz - 1, cy), (cx - sz + 1, cy - sz), (cx - sz + 1, cy + sz)]
        pygame.draw.polygon(surf, color, pts)
    elif icon_id == "edit" or icon_id == "pencil":
        # Simbolo matita stilizzato
        rect = (cx - 2, cy - sz + 2, 4, sz * 2 - 4)
        pygame.draw.rect(surf, color, rect)
        pygame.draw.circle(surf, color, (cx, cy - sz + 2), 3)
    elif icon_id == "cross" or icon_id == "x":
        s2 = sz - 2
        pygame.draw.line(surf, color, (cx - s2, cy - s2), (cx + s2, cy + s2), 2)
        pygame.draw.line(surf, color, (cx + s2, cy - s2), (cx - s2, cy + s2), 2)
    elif icon_id == "plus" or icon_id == "+":
        s2 = sz - 1
        pygame.draw.line(surf, color, (cx, cy - s2), (cx, cy + s2), 2)
        pygame.draw.line(surf, color, (cx - s2, cy), (cx + s2, cy), 2)
    elif icon_id == "camera":
        # Corpo macchina
        body = (cx - sz, cy - sz + 4, sz * 2, sz * 2 - 8)
        _rect(surf, color, body, 2, radius=2)
        # Obiettivo
        pygame.draw.circle(surf, color, (cx, cy + 2), sz // 2, 2)
        # Flash / Mirino
        top = (cx - sz + 4, cy - sz, sz, 4)
        _rect(surf, color, top, 2, radius=1)


def _button(surf, r, label, hovered=False, active=False, danger=False, font="sm", custom_bg=None):
    from editor.constants import BTN, BTN_HO, BTN_AC, BORDER, TXT_HI
    if custom_bg:
        # Applica una leggera variazione di luminosità al passaggio del mouse
        if hovered:
            bg = tuple(min(255, c + 30) for c in custom_bg)
        else:
            bg = custom_bg
    elif danger:
        bg = (130, 40, 40) if hovered else (90, 30, 30)
    elif active:
        bg = BTN_AC
    else:
        bg = BTN_HO if hovered else BTN
    
    _rect(surf, bg, r, radius=4)
    _rect(surf, BORDER, r, 1, radius=4)
    
    # Riconoscimento Icone
    icon_map = {
        "^": "up", "v": "down", "▴": "up", "▾": "down", 
        "▲": "up", "▼": "down", "▶": "play", "✎": "edit", 
        "×": "cross", "+": "plus", "⬆": "up"
    }
    if label in icon_map:
        _draw_shape_icon(surf, r, icon_map[label], TXT_HI)
    else:
        tw, th = _text_wh(label, font)
        _draw_text(surf, label, font, TXT_HI, r[0] + (r[2]-tw)//2, r[1] + (r[3]-th)//2)


def _pip(surf, mx, my) -> tuple:
    """Current mouse position."""
    return pygame.mouse.get_pos()


def _in_rect(p, r) -> bool:
    return r[0] <= p[0] <= r[0]+r[2] and r[1] <= p[1] <= r[1]+r[3]


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))



def _draw_tooltip(surf, text, pos):
    """Disegna un piccolo box informativo vicino alla posizione indicata."""
    from editor.constants import TXT_HI
    font = _FONTS["sm"]
    tw, th = font.size(str(text))
    # Box padding
    padding = 6
    bx, by = pos[0] + 15, pos[1] + 15
    bw, bh = tw + padding*2, th + padding*2
    
    # Clamp allo schermo
    sw, sh = surf.get_size()
    if bx + bw > sw: bx = pos[0] - bw - 5
    if by + bh > sh: by = pos[1] - bh - 5
    
    # Ombra
    pygame.draw.rect(surf, (10, 10, 15, 150), (bx+2, by+2, bw, bh), border_radius=3)
    # Background
    pygame.draw.rect(surf, (45, 45, 55), (bx, by, bw, bh), border_radius=3)
    # Bordo
    pygame.draw.rect(surf, (100, 100, 110), (bx, by, bw, bh), 1, border_radius=3)
    
    surf.blit(font.render(str(text), True, TXT_HI), (bx + padding, by + padding))


def _slider(surf, r, value, min_v, max_v, color=(100, 100, 255), power=1.0):
    """Disegna uno slider moderno con supporto per curve di potenza (es. 2.0 per quadratica)."""
    from editor.constants import BORDER, BTN
    # Background bar
    bar_h = 4
    bar_r = (r[0], r[1] + (r[3] - bar_h) // 2, r[2], bar_h)
    pygame.draw.rect(surf, BTN, bar_r, border_radius=2)
    pygame.draw.rect(surf, BORDER, bar_r, 1, border_radius=2)
    
    # Active part
    v_range = max_v - min_v if max_v > min_v else 0.001
    # Calcolo ratio lineare
    linear_ratio = (value - min_v) / v_range
    linear_ratio = max(0, min(1, linear_ratio))
    
    # Applica curva inversa per il rendering se power != 1.0
    # Se input usa ratio^power, rendering usa ratio^(1/power)
    draw_ratio = linear_ratio ** (1.0 / power) if power != 1.0 else linear_ratio
    
    active_w = int(r[2] * draw_ratio)
    if active_w > 0:
        active_r = (r[0], r[1] + (r[3] - bar_h) // 2, active_w, bar_h)
        pygame.draw.rect(surf, color, active_r, border_radius=2)
    
    # Handle
    hx = r[0] + active_w
    hy = r[1] + r[3] // 2
    pygame.draw.circle(surf, (220, 220, 220), (hx, hy), 6)
    pygame.draw.circle(surf, (40, 40, 50), (hx, hy), 7, 1)


def _input_box(surf, r, text, focused=False, hint=""):
    """Disegna una casella di input testo/numerica pulsante se focalizzata."""
    from editor.constants import BTN, BTN_AC, BORDER, TXT_HI, TXT_DIM
    bg = (40, 42, 54) if focused else BTN
    border_c = BTN_AC if focused else BORDER
    
    _rect(surf, bg, r, radius=3)
    _rect(surf, border_c, r, 1 if not focused else 2, radius=3)
    
    if not text and not focused:
        _, th = _text_wh(hint if hint else " ", "sm")
        # +1 pixel per compensazione ottica degli ascendenti
        _draw_text(surf, hint, "sm", TXT_DIM, r[0]+6, r[1]+(r[3]-th)//2 + 1)
    else:
        cursor = "|" if (focused and (pygame.time.get_ticks() // 500 % 2 == 0)) else ""
        txt_s = str(text) + cursor
        _, th = _text_wh(txt_s if txt_s else " ", "mono")
        _draw_text(surf, txt_s, "mono", TXT_HI, r[0]+6, r[1]+(r[3]-th)//2 + 1)

def _scrollbar(screen, x, y, w, h, scroll, total_items, visible_items):
    """Disegna una scrollbar verticale moderna e discreta."""
    if total_items <= visible_items or total_items <= 0:
        return
    thumb_h = max(20, int((visible_items / total_items) * h))
    max_scroll = total_items - visible_items
    scroll_ratio = scroll / max_scroll if max_scroll > 0 else 0
    thumb_y = y + int(scroll_ratio * (h - thumb_h))
    pygame.draw.rect(screen, (35, 38, 48), (x, y, w, h), border_radius=w//2)
    pygame.draw.rect(screen, (80, 85, 110), (x, thumb_y, w, thumb_h), border_radius=w//2)
