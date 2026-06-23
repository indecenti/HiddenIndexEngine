import pygame
import math

from editor.constants import (
    PANEL, BORDER, ACCENT, TXT_HI, TXT_DIM, BTN, BTN_AC, BG, OK_C
)
from editor.ui.draw import _txt, _rect, _button, _in_rect, _text_wh

def extract_palette(surf: pygame.Surface, n=10) -> list:
    if not surf:
        return []
    small = pygame.transform.scale(surf, (50, 50))
    counts = {}
    for x in range(50):
        for y in range(50):
            r, g, b, _ = small.get_at((x, y))
            r_q, g_q, b_q = r // 16 * 16, g // 16 * 16, b // 16 * 16
            color = (r_q, g_q, b_q)
            counts[color] = counts.get(color, 0) + 1
    
    # Rimuoviamo il nero/grigio scuro ed estremo bianco se dominano troppo,
    # per avere colori più "utili", ma non è strettamente necessario.
    sorted_colors = sorted(counts.items(), key=lambda idx: idx[1], reverse=True)
    res = []
    
    # Prendi i primi N colori distanti almeno un po'
    for color, count in sorted_colors:
        if len(res) >= n:
            break
        # Verifica distanza minima dai precedenti per varietà
        too_close = False
        for rgb in res:
            dist = math.hypot(color[0]-rgb[0], math.hypot(color[1]-rgb[1], color[2]-rgb[2]))
            if dist < 30:
                too_close = True
                break
        if not too_close:
            res.append(color)
            
    # Se non ce ne sono abbastanza, riempi con quelli che abbiamo ignorato
    if len(res) < n:
        for color, count in sorted_colors:
            if color not in res:
                res.append(color)
            if len(res) >= n:
                break
    return res

def build_sv_surface(hue, w, h):
    surf = pygame.Surface((w, h))
    for x in range(w):
        for y in range(h):
            s = x / w * 100
            v = 100 - (y / h * 100)
            c = pygame.Color(0)
            c.hsva = (hue, s, max(0, min(100, v)), 100)
            surf.set_at((x, y), c)
    return surf

def build_hue_surface(w, h):
    surf = pygame.Surface((w, h))
    for x in range(w):
        hue = (x / w) * 360
        c = pygame.Color(0)
        c.hsva = (hue, 100, 100, 100)
        pygame.draw.line(surf, c, (x, 0), (x, h))
    return surf

def ask_color(screen: pygame.Surface, bg_surf: pygame.Surface = None, 
              initial_color=(255, 255, 255), title="Seleziona Colore") -> tuple:
    """
    Mostra un modal per la selezione del colore. Ritorna il colore RGB scelto o None.
    Blocca l'esecuzione tramite un mini-loop di eventi.
    """
    w_win, h_win = screen.get_size()
    w, h = 480, 520
    x, y = (w_win - w) // 2, (h_win - h) // 2

    # UI elements
    hue_bar_rect = pygame.Rect(x + 20, y + 60, w - 40, 20)
    sv_rect = pygame.Rect(x + 20, y + 90, w - 40, 256)
    
    current_hue = 0.0
    current_s = 0.0
    current_v = 100.0
    
    # Try reversing initial color to HSV
    c = pygame.Color(*initial_color)
    current_hue, current_s, current_v, _ = c.hsva
    
    hue_surf = build_hue_surface(hue_bar_rect.width, hue_bar_rect.height)
    sv_surf = build_sv_surface(current_hue, sv_rect.width, sv_rect.height)
    last_hue_drawn = current_hue
    
    # Palette estratta
    palette = extract_palette(bg_surf, 10)
    
    running = True
    result = None
    clock = pygame.time.Clock()

    dragging_hue = False
    dragging_sv = False

    # Snapshot dello schermo allo stato attuale per evitare sovrapposizioni o alpha stacking
    bg_snapshot = screen.copy()
    bg_dark = pygame.Surface(screen.get_size(), pygame.SRCALPHA)
    bg_dark.fill((0, 0, 0, 150))
    bg_snapshot.blit(bg_dark, (0, 0))

    while running:
        clock.tick(60)
        mx, my = pygame.mouse.get_pos()
        
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                # Ri-posta l'evento: questo loop bloccante consuma tutta la coda,
                # quindi senza re-post l'intento di chiusura andrebbe perso e l'app
                # non si chiuderebbe. Il main loop dell'editor lo gestira'.
                pygame.event.post(pygame.event.Event(pygame.QUIT))
                running = False
            elif ev.type == pygame.MOUSEBUTTONDOWN:
                if ev.button == 1:
                    if _in_rect((mx, my), hue_bar_rect):
                        dragging_hue = True
                    elif _in_rect((mx, my), sv_rect):
                        dragging_sv = True
                    else:
                        # Controllo click palette
                        ox = x + 20
                        oy = y + 370
                        for pcol in palette:
                            r = pygame.Rect(ox, oy, 30, 30)
                            if _in_rect((mx, my), r):
                                pc = pygame.Color(*pcol)
                                current_hue, current_s, current_v, _ = pc.hsva
                            ox += 34
                            
                        # Bottoni conferme
                        btn_w = 100
                        ok_r = pygame.Rect(x + w - 40 - btn_w * 2 - 10, y + h - 50, btn_w, 30)
                        can_r = pygame.Rect(x + w - 20 - btn_w, y + h - 50, btn_w, 30)
                        
                        if _in_rect((mx, my), ok_r):
                            sc = pygame.Color(0)
                            sc.hsva = (current_hue, current_s, current_v, 100)
                            result = (sc.r, sc.g, sc.b)
                            running = False
                        elif _in_rect((mx, my), can_r):
                            running = False
                            
            elif ev.type == pygame.MOUSEBUTTONUP:
                if ev.button == 1:
                    dragging_hue = False
                    dragging_sv = False
            elif ev.type == pygame.KEYDOWN:
                if ev.key == pygame.K_ESCAPE:
                    running = False
                elif ev.key == pygame.K_RETURN:
                    sc = pygame.Color(0)
                    sc.hsva = (current_hue, current_s, current_v, 100)
                    result = (sc.r, sc.g, sc.b)
                    running = False

        if dragging_hue:
            rel_x = max(0, min(1.0, (mx - hue_bar_rect.x) / hue_bar_rect.width))
            current_hue = rel_x * 360
            if current_hue >= 360:
                current_hue = 0
        
        if dragging_sv:
            rel_x = max(0, min(1.0, (mx - sv_rect.x) / sv_rect.width))
            rel_y = max(0, min(1.0, (my - sv_rect.y) / sv_rect.height))
            current_s = rel_x * 100
            current_v = 100 - (rel_y * 100)

        if str(current_hue) != str(last_hue_drawn):
            sv_surf = build_sv_surface(current_hue, sv_rect.width, sv_rect.height)
            last_hue_drawn = current_hue

        cur_color = pygame.Color(0)
        cur_color.hsva = (current_hue, current_s, max(0, min(100, current_v)), 100)

        screen.blit(bg_snapshot, (0, 0))
        
        # Modal Background
        modal_r = pygame.Rect(x, y, w, h)
        _rect(screen, PANEL, modal_r, radius=8)
        _rect(screen, BORDER, modal_r, 1, radius=8)
        
        header = _txt(title, "md", TXT_HI)
        screen.blit(header, (x + 20, y + 20))
        
        screen.blit(hue_surf, hue_bar_rect)
        pygame.draw.rect(screen, BORDER, hue_bar_rect, 1)
        hx = hue_bar_rect.x + int((current_hue / 360) * hue_bar_rect.width)
        pygame.draw.line(screen, (255, 255, 255), (hx, hue_bar_rect.y - 2), (hx, hue_bar_rect.bottom + 2), 2)
        pygame.draw.line(screen, (0, 0, 0), (hx, hue_bar_rect.y - 2), (hx, hue_bar_rect.bottom + 2), 1)
        
        screen.blit(sv_surf, sv_rect)
        pygame.draw.rect(screen, BORDER, sv_rect, 1)
        sx = sv_rect.x + int((current_s / 100) * sv_rect.width)
        sy = sv_rect.y + int(((100 - current_v) / 100) * sv_rect.height)
        pygame.draw.circle(screen, (255, 255, 255), (sx, sy), 5, 1)
        pygame.draw.circle(screen, (0, 0, 0), (sx, sy), 6, 1)
        
        lbl_pal = _txt("Estratti dal Background:", "sm", TXT_DIM)
        screen.blit(lbl_pal, (x + 20, y + 350))
        
        ox = x + 20
        oy = y + 370
        for pcol in palette:
            pr = pygame.Rect(ox, oy, 30, 30)
            _rect(screen, pcol, pr)
            _rect(screen, BORDER, pr, 1)
            ox += 34
            
        cur_r = pygame.Rect(x + 20, y + h - 50, 40, 30)
        _rect(screen, (cur_color.r, cur_color.g, cur_color.b), cur_r)
        _rect(screen, BORDER, cur_r, 1)
        
        val_txt = _txt(f"RGB: {cur_color.r}, {cur_color.g}, {cur_color.b}", "sm", TXT_HI)
        screen.blit(val_txt, (x + 70, y + h - 45))
        
        btn_w = 100
        ok_r = pygame.Rect(x + w - 40 - btn_w * 2 - 10, y + h - 50, btn_w, 30)
        can_r = pygame.Rect(x + w - 20 - btn_w, y + h - 50, btn_w, 30)
        _button(screen, ok_r, "Applica", _in_rect((mx, my), ok_r), active=True)
        _button(screen, can_r, "Annulla", _in_rect((mx, my), can_r))
        
        pygame.display.flip()

    return result
