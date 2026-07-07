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
_ICON_CACHE: dict = {}

def _get_icon(icon_id):
    """Carica e mette in cache le icone PNG premium."""
    if icon_id in _ICON_CACHE:
        return _ICON_CACHE[icon_id]
    
    mapping = {
        "x": "close", "cross": "close", "close": "close", "cancel": "close",
        "play": "play", "run": "play",
        "edit": "edit", "pencil": "edit",
        "build": "build", "exe": "build", "package": "build",
        "add": "add", "+": "add", "plus": "add",
        "select_rect": "select_rect", "select": "select_rect",
        "circle": "circle", "square": "square",
        "effect": "effect", "fx": "effect", "magic": "effect",
        "lock_open": "lock_open", "unlock": "lock_open",
        "lock_closed": "lock_closed", "lock": "lock_closed",
        "eye_hidden": "eye_hidden", "hide": "eye_hidden",
        "eye_visible": "eye_visible", "show": "eye_visible",
        "save": "save", "disk": "save",
        "delete": "delete", "trash": "delete", "remove": "delete",
        "settings": "settings", "gear": "settings",
        "search": "search", "find": "search", "magnify": "search",
        "tag": "tag", "label": "tag",
        # Nuove icone (griglia 4x4 generata)
        "globe": "globe", "web": "globe", "html": "globe", "internet": "globe",
        "android": "android", "apk": "android", "mobile": "android", "phone": "android",
        "folder": "folder", "directory": "folder",
        "refresh": "refresh", "reload": "refresh", "sync": "refresh",
        "download": "download", "export": "download",
        "upload": "upload", "import": "upload",
        "layers": "layers", "stack": "layers",
        "copy": "copy", "duplicate": "copy",
        "music": "music", "note": "music",
        "speaker": "speaker", "audio": "speaker", "sound": "speaker",
        "warning": "warning", "alert": "warning",
        "info": "info", "help": "info",
        "undo": "undo",
        "redo": "redo",
        "grid_view": "grid_view", "grid": "grid_view",
    }
    
    fname = mapping.get(icon_id)
    if not fname: return None
    
    from engine.utils import get_base_path
    path = get_base_path() / "engine" / "assets" / "icons" / f"{fname}.png"
    if path.exists():
        try:
            surf = pygame.image.load(str(path)).convert_alpha()
            _ICON_CACHE[icon_id] = surf
            return surf
        except Exception: pass
    return None


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


def _wrap_lines(text: str, font_key: str, max_w: int) -> list:
    """Spezza il testo in righe che stanno in max_w pixel (a parole; spezza
    le parole singole troppo lunghe carattere per carattere)."""
    font = _FONTS.get(font_key, _FONTS["md"])
    lines: list = []
    for raw_line in str(text).split("\n"):
        words = raw_line.split(" ")
        current = ""
        for word in words:
            candidate = word if not current else current + " " + word
            if font.size(candidate)[0] <= max_w:
                current = candidate
                continue
            if current:
                lines.append(current)
                current = ""
            # Parola singola piu' larga di max_w: spezzala a caratteri
            while font.size(word)[0] > max_w and len(word) > 1:
                cut = len(word)
                while cut > 1 and font.size(word[:cut])[0] > max_w:
                    cut -= 1
                lines.append(word[:cut])
                word = word[cut:]
            current = word
        lines.append(current)
    return lines


def _draw_text_wrapped(surf, text, font_key, color, x, y, max_w, line_gap=2,
                       max_lines=None) -> int:
    """Disegna testo con word-wrap dentro max_w. Ritorna l'altezza totale usata.
    Se max_lines e' impostato, l'ultima riga visibile viene troncata con ellissi."""
    font = _FONTS.get(font_key, _FONTS["md"])
    lines = _wrap_lines(text, font_key, max_w)
    if max_lines is not None and len(lines) > max_lines:
        lines = lines[:max_lines]
        last = lines[-1]
        while last and font.size(last + "...")[0] > max_w:
            last = last[:-1]
        lines[-1] = last + "..."
    line_h = font.get_linesize()
    cur_y = y
    for line in lines:
        if line:
            surf.blit(font.render(line, True, color), (x, cur_y))
        cur_y += line_h + line_gap
    return cur_y - y


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
    """Disegna icone premium PNG se disponibili, altrimenti fallback procedurale."""
    cx, cy = r[0] + r[2]//2, r[1] + r[3]//2
    sz = min(r[2], r[3]) // 2 - 5
    
    icon_surf = _get_icon(icon_id)
    if icon_surf:
        # Padding interno per l'icona
        target_sz = int(min(r[2], r[3]) * 0.8)
        scaled = pygame.transform.smoothscale(icon_surf, (target_sz, target_sz))
        surf.blit(scaled, (cx - target_sz//2, cy - target_sz//2))
        return

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


def _button(surf, r, label, hovered=False, active=False, danger=False, font="sm", custom_bg=None, icon=None, center_text=False):
    from editor.constants import BTN, BTN_HO, BTN_AC, BORDER, TXT_HI
    if custom_bg:
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
    
    # Shadow / Outline soft
    _rect(surf, bg, r, radius=5)
    _rect(surf, BORDER, r, 1, radius=5)
    
    if icon:
        icon_sz = 18
        tw, th = _text_wh(label, font)
        spacing = 8
        total_w = icon_sz + spacing + tw
        
        # Centratura verticale comune
        iy = r[1] + (r[3] - icon_sz) // 2
        ty = r[1] + (r[3] - th) // 2
        
        if center_text:
            start_x = r[0] + (r[2] - total_w) // 2
            _draw_shape_icon(surf, (start_x, iy, icon_sz, icon_sz), icon, TXT_HI)
            _draw_text(surf, label, font, TXT_HI, start_x + icon_sz + spacing, ty)
        else:
            _draw_shape_icon(surf, (r[0] + 12, iy, icon_sz, icon_sz), icon, TXT_HI)
            _draw_text(surf, label, font, TXT_HI, r[0] + 12 + icon_sz + spacing, ty)
        return

    # Riconoscimento Icone (label stringa -> id icona)
    icon_map = {
        "^": "up", "v": "down", "▴": "up", "▾": "down",
        "▲": "up", "▼": "down", "▶": "play", "✎": "edit",
        "×": "cross", "X": "x", "+": "plus", "⬆": "up",
        "EXE": "build", "BUILD": "build",
        "APK": "android",
        "WEB": "globe",
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


def _input_box(surf, r, text, focused=False, hint="", icon=None, font="md", all_selected=False, cursor_pos=None):
    """Disegna una casella di input premium con glow, placeholder e cursore smooth."""
    from editor.constants import BTN, BORDER, TXT_HI, TXT_DIM, ACCENT
    import math
    import time
    
    # 1. Background base
    bg = (35, 38, 50) if focused else BTN
    _rect(surf, bg, r, radius=6)
    
    t = time.time()
    if focused:
        # 2. Glow Ring (Effetto pulsante premium)
        glow_alpha = int(100 + math.sin(t * 12) * 100)
        glow_surf = pygame.Surface((r[2], r[3]), pygame.SRCALPHA)
        pygame.draw.rect(glow_surf, (*ACCENT[:3], glow_alpha), glow_surf.get_rect(), 3, border_radius=6)
        surf.blit(glow_surf, (r[0], r[1]))
    
    # 3. Bordo
    _rect(surf, ACCENT if focused else BORDER, r, 2 if focused else 1, radius=6)
    
    # 4. Icona opzionale
    text_x = r[0] + 10
    if icon:
        icon_sz = 18
        iy = r[1] + (r[3] - icon_sz) // 2
        _draw_shape_icon(surf, (r[0] + 8, iy, icon_sz, icon_sz), icon, TXT_DIM)
        text_x += 28

    # 5. Testo o Placeholder
    if not text and not focused:
        _, th = _text_wh(hint if hint else " ", font)
        _draw_text(surf, hint, font, TXT_DIM, text_x, r[1] + (r[3] - th) // 2)
    else:
        # 6. Selezione totale (Highlights)
        txt_s = str(text)
        tw, th = _text_wh(txt_s, font)
        ty = r[1] + (r[3] - th) // 2
        
        if all_selected and txt_s:
            sel_w = min(tw, r[2] - (text_x - r[0]) - 10)
            _rect(surf, (70, 90, 160), (text_x, ty, sel_w, th), radius=2)

        # 7. Rendering testo
        _draw_text(surf, txt_s, font, TXT_HI, text_x, ty, max_w=r[2] - (text_x - r[0]) - 10)
        
        # 8. Cursore Smooth (Alpha Interpolated) — posizionato a cursor_pos se fornito
        if focused and not all_selected:
            cursor_alpha = int(127 + math.sin(t * 15) * 127)
            c_h = th - 4
            c_surf = pygame.Surface((2, c_h), pygame.SRCALPHA)
            c_surf.fill((*TXT_HI[:3], cursor_alpha))
            if cursor_pos is not None:
                cx, _ = _text_wh(txt_s[:max(0, min(cursor_pos, len(txt_s)))], font)
            else:
                cx = tw
            surf.blit(c_surf, (text_x + cx + 1, ty + 2))

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

def _draw_tag_chip(surf, r, label, active=False, hovered=False, removable=False):
    """Disegna un chip di tag premium con supporto per stato attivo e rimozione."""
    from editor.constants import ACCENT, TXT_HI, TXT_DIM, BORDER
    bg = ACCENT if active else ((55, 60, 80) if hovered else (40, 42, 54))
    tcol = (15, 15, 25) if active else (TXT_HI if hovered else (200, 205, 220))
    
    _rect(surf, bg, r, radius=6)
    if active:
        _rect(surf, (255, 255, 255, 100), r, 1, radius=6)
    else:
        _rect(surf, BORDER, r, 1, radius=6)
    
    # Label
    tw, th = _text_wh(label, "sm")
    text_x = r[0] + (r[2] - tw) // 2
    if removable:
        text_x = r[0] + 8
    
    _draw_text(surf, label, "sm", tcol, text_x, r[1] + (r[3] - th) // 2, max_w=r[2]-10)
    
    if removable:
        # Icona X per rimozione
        xr = pygame.Rect(r[0] + r[2] - 22, r[1] + (r[3]-16)//2, 16, 16)
        _draw_shape_icon(surf, xr, "x", (255, 100, 100) if hovered else tcol)
