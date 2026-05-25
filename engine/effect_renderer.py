"""
engine/effect_renderer.py

EffectRenderer — renderizza effetti visivi animati ad ALTA FEDELTÀ.
Specializzato in fumo organico asimmetrico (Cloud Clustering) e bagliori ultra-soft.
"""

from __future__ import annotations

import math
import os
import pygame

from engine.utils import get_logger

log = get_logger(__name__)

# ---------------------------------------------------------------------------
# LOGICA DI AGGIORNAMENTO CENTRALIZZATA
# ---------------------------------------------------------------------------

def update_effect_state(fx: dict | object, dt: float):
    """Avanzamento temporale per effetti di gioco ed editor."""
    def get_v(key, default):
        if isinstance(fx, dict): return fx.get(key, default)
        return getattr(fx, key, default)

    def set_v(key, val):
        if isinstance(fx, dict): fx[key] = val
        else: setattr(fx, key, val)

    t_accum = get_v("_t_accum", 0.0)
    t_type = get_v("type", "glint")
    period = max(0.01, get_v("pulse_period", 2.0))

    if t_type == "glint":
        t_accum += dt / period
    elif t_type == "bubble_tip":
        if get_v("_visible", False):
            chars = get_v("_chars_visible", 0.0)
            chars += dt * 25.0
            set_v("_chars_visible", chars)
        else:
            set_v("_chars_visible", 0.0)
    else:
        t_accum += dt * period
    
    set_v("_t_accum", t_accum)

# ---------------------------------------------------------------------------
# LOGICA DI DISEGNO AVANZATA
# ---------------------------------------------------------------------------

def draw_radial_glow(dest: pygame.Surface, cx: int, cy: int, 
                     radius: int, color: list | tuple, eff_intensity: float,
                     cache: dict | None = None):
    """Bagliore radiale ultra-soft con campionamento a 64 livelli."""
    r_raw, g_raw, b_raw = color[0], color[1], color[2]
    
    glow_surf = None
    if cache is not None:
        glow_surf = cache.get(("ultra_radial", radius, r_raw, g_raw, b_raw))
    
    if glow_surf is None:
        diam = radius * 2
        glow_surf = pygame.Surface((diam, diam), pygame.SRCALPHA)
        steps = 64
        boost = 2.4
        for s in range(steps, 0, -1):
            ratio = s / steps
            circle_r = max(1, int(radius * ratio))
            factor = (1.0 - ratio) ** 2.4
            alpha = min(255, int(210 * factor * boost))
            if alpha > 1:
                pygame.draw.circle(glow_surf, (r_raw, g_raw, b_raw, alpha), (radius, radius), circle_r)
        
        if cache is not None:
            cache[("ultra_radial", radius, r_raw, g_raw, b_raw)] = glow_surf
            
    original_alpha = glow_surf.get_alpha()
    temp_alpha = int(255 * eff_intensity)
    if temp_alpha > 0:
        glow_surf.set_alpha(temp_alpha)
        dest.blit(glow_surf, (cx - radius, cy - radius))
    glow_surf.set_alpha(original_alpha)

    if eff_intensity > 0.3:
        core_r = max(1, radius // 8)
        cv = min(255, int(230 * eff_intensity * 0.9))
        pygame.draw.circle(dest, (cv, cv, cv), (cx, cy), core_r)

def draw_glint_effect(screen: pygame.Surface, sx: float, sy: float, sr: float,
                      color: list | tuple, intensity: float, t_accum: float, phase: float,
                      pulse_min: float, cache: dict | None = None):
    """Glint additivo ottimizzato per ARM: invece di fill+blit-alpha+blit-ADD
    (3 op da ~diam²/frame), pre-cuociamo il bagliore OPACO su nero per livello
    di intensità (cache) e facciamo UNA sola ADD-blit dimensionata al raggio.
    BLEND_RGB_ADD ignora l'alpha per-superficie, quindi l'intensità va cotta."""
    t = t_accum + phase
    pulse = pulse_min + ((math.sin(2.0 * math.pi * t) + 1.0) * 0.5) * (1.0 - pulse_min)
    eff_intensity = intensity * pulse
    if eff_intensity <= 0.02:
        return

    sr_i = max(6, int(sr))
    diam = sr_i * 2
    lvl = max(1, min(12, int(eff_intensity * 12 + 0.5)))  # quantizza a 12 livelli
    r0, g0, b0 = int(color[0]), int(color[1]), int(color[2])
    key = ("glint_baked", sr_i, r0, g0, b0, lvl)
    glow = cache.get(key) if cache is not None else None
    if glow is None:
        glow = pygame.Surface((diam, diam))   # OPACA (nero = additivo neutro)
        glow.fill((0, 0, 0))
        scale = (lvl / 12.0) * 2.4            # boost coerente con la versione originale
        steps = 40
        for s in range(steps, 0, -1):
            ratio = s / steps
            cr = max(1, int(sr_i * ratio))
            factor = (1.0 - ratio) ** 2.4
            v = factor * scale
            col = (min(255, int(r0 * v)), min(255, int(g0 * v)), min(255, int(b0 * v)))
            if col[0] or col[1] or col[2]:
                pygame.draw.circle(glow, col, (sr_i, sr_i), cr)
        if cache is not None:
            cache[key] = glow
    screen.blit(glow, (int(sx) - sr_i, int(sy) - sr_i), special_flags=pygame.BLEND_RGB_ADD)
    if eff_intensity > 0.3:
        core_r = max(1, sr_i // 8)
        cv = min(255, int(230 * eff_intensity * 0.9))
        pygame.draw.circle(screen, (cv, cv, cv), (int(sx), int(sy)), core_r)

def draw_smoke_effect(screen: pygame.Surface, sx: float, sy: float, sr: float, 
                      color: list | tuple, intensity: float, t_accum: float, phase: float = 0.0,
                      pulse_min: float = 1.0, cache: dict | None = None):
    """
    Fumo organico rifinito con controllo granulare della dimensione dei soffi (pulse_min).
    """
    t = t_accum + phase
    r_c, g_c, b_c = color
    num_puffs = 12
    # Espandiamo il canvas in base allo sr (radius)
    work_w, work_h = int(sr * 7.5), int(sr * 12.5)
    
    smoke_surf = cache.get(("work_smoke", work_w, work_h)) if cache is not None else None
    if smoke_surf is None:
        smoke_surf = pygame.Surface((work_w, work_h), pygame.SRCALPHA)
        if cache is not None: cache[("work_smoke", work_w, work_h)] = smoke_surf
        
    smoke_surf.fill((0, 0, 0, 0))
    base_x, base_y = work_w // 2, work_h * 0.9
    
    for i in range(num_puffs):
        seed = i * 2.618 
        v_speed = 0.7 + 0.3 * math.sin(seed * 0.5)
        p_t = (t * v_speed + i / num_puffs) % 1.0
        
        sway = math.sin(p_t * 4.5 + seed) * 0.7 + math.cos(p_t * 8.5 + seed * 1.5) * 0.3
        drift_x = sway * (sr * 0.8 * (1.1 + p_t * 1.5))
        drift_y = -p_t * sr * 9.0
        
        # AGGIORNAMENTO: puff_r ora è influenzato da pulse_min per controllare la 'cicciositá' del fumo
        puff_r = sr * (0.55 + p_t * 0.7) * pulse_min
        
        alpha_base = int(180 * intensity * max(0, (1.0 - p_t)**1.6))
        
        if alpha_base > 1:
            # RIDUZIONE: Da 6 a 5 micro-blob per ridurre sovrapposizione luminosa
            num_blobs = 5
            for b in range(num_blobs):
                b_ang = b * (math.pi * 2 / num_blobs) + p_t * 0.4
                b_dist = puff_r * 0.2 * (0.7 + 0.3 * math.sin(seed + b))
                bx = int(base_x + drift_x + math.cos(b_ang) * b_dist)
                by = int(base_y + drift_y + math.sin(b_ang) * b_dist)
                
                # Rendering a 3 strati morbidi
                for layer in range(3):
                    l_ratio = (3 - layer) / 3
                    sub_r = int(puff_r * (0.6 + 0.12 * b) * l_ratio)
                    # Alpha ridotto per un blending più etereo
                    sub_a = int(alpha_base * (0.1 + 0.07 * layer))
                    if sub_r > 0 and sub_a > 0:
                        pygame.draw.circle(smoke_surf, (r_c, g_c, b_c, sub_a), (bx, by), sub_r)
                             
    # Blit finale della colonna di fumo
    screen.blit(smoke_surf, (int(sx) - work_w // 2, int(sy) - base_y))

def draw_flies_effect(screen: pygame.Surface, sx: float, sy: float, sr: float,
                      color: list | tuple, intensity: float, t_accum: float, t_global: float, 
                      pulse_min: float = 1.0):
    """Particelle sciame."""
    num_flies = int(intensity * 40)
    if num_flies < 1: return
    base_sz = max(1, round(pulse_min * 3.0 * (sr / max(1.0, sr))))
    for i in range(num_flies):
        phi = i * 1.234 
        pos_x = sx + math.cos(t_accum * (1.0 + math.sin(phi * 0.5)) + phi) * sr * (0.4 + 0.4 * math.sin(t_accum * 0.8 + phi)) + math.sin(t_global * 12.0 + phi) * (sr * 0.1)
        pos_y = sy + math.sin(t_accum * (0.8 + math.cos(phi * 0.3)) + phi * 1.1) * sr * (0.4 + 0.4 * math.cos(t_accum * 0.7 + phi * 1.2)) + math.cos(t_global * 14.0 + phi * 1.5) * (sr * 0.1)
        sz = round(base_sz if i % 4 != 0 else base_sz * 0.8)
        if sz <= 1: screen.set_at((int(pos_x), int(pos_y)), color)
        else: pygame.draw.rect(screen, color, (int(pos_x - sz//2), int(pos_y - sz//2), sz, sz))

# Sistemi testuali cachati
_TEXT_WRAP_CACHE, _FONT_CACHE = {}, {}

def draw_bubble_tip_effect(screen: pygame.Surface, sx: float, sy: float, 
                             text: str, trigger: str, is_editor: bool = False,
                             width: float = 300, height: float = 180, zoom: float = 1.0,
                             color: list | tuple = (252, 252, 255), alpha: int = 255,
                             font_size: int = 22, font_color: list | tuple = (40, 40, 40),
                             chars_limit: int = 9999, cache: dict | None = None):
    """Fumetti interattivi premium."""
    sz = max(10, int(font_size * zoom))
    if ("Segoe UI", sz) not in _FONT_CACHE: 
        _FONT_CACHE[("Segoe UI", sz)] = pygame.font.SysFont("Segoe UI", sz)
    font_main = _FONT_CACHE[("Segoe UI", sz)]
    
    padding, corner_radius, bubble_w, bubble_h = 24 * zoom, int(22 * zoom), int(width), int(height)
    bx, by, margin = sx - bubble_w // 2, sy - bubble_h - 40 * zoom, int(20 * zoom)
    cv_w, cv_h = bubble_w + margin * 2, bubble_h + int(45 * zoom) + margin * 2
    
    bubble_surf = cache.get(("bubble_canvas", cv_w, cv_h)) if cache is not None else None
    if bubble_surf is None:
        bubble_surf = pygame.Surface((cv_w, cv_h), pygame.SRCALPHA)
        if cache is not None: cache[("bubble_canvas", cv_w, cv_h)] = bubble_surf
    
    bubble_surf.fill((0, 0, 0, 0))
    rbx, rby, rsx, rsy = margin, margin, cv_w // 2, margin + bubble_h + int(40 * zoom)
    for i in range(12, 0, -2): 
        pygame.draw.rect(bubble_surf, (0, 0, 0, int(22 * (1.0 - i/12))), (rbx-i, rby-i+4, bubble_w+i*2, bubble_h+i*2), border_radius=corner_radius+i)
    
    pygame.draw.polygon(bubble_surf, (*color, alpha), [(rsx, rsy - margin), (rsx-12*zoom, rsy-margin-30*zoom), (rsx+12*zoom, rsy-margin-30*zoom)])
    pygame.draw.rect(bubble_surf, (*color, alpha), (rbx, rby, bubble_w, bubble_h), border_radius=corner_radius)
    pygame.draw.rect(bubble_surf, (*[max(0, c - 40) for c in color], 255), (rbx, rby, bubble_w, bubble_h), 2, border_radius=corner_radius)

    screen.blit(bubble_surf, (bx - margin, by - margin))

    w_key = (text, sz, bubble_w - padding*2)
    if w_key not in _TEXT_WRAP_CACHE:
        words = str(text).split(' '); lines, curr = [], []
        for w in words:
            if font_main.size(' '.join(curr + [w]))[0] < w_key[2]: curr.append(w)
            else:
                if curr: lines.append(' '.join(curr)); curr = [w]
        if curr: lines.append(' '.join(curr))
        _TEXT_WRAP_CACHE[w_key] = lines
    
    lh, ty, curr_c = font_main.get_linesize(), by + int(padding), 0
    for i, line in enumerate(_TEXT_WRAP_CACHE.get(w_key, [])):
        if curr_c >= chars_limit: break
        l_draw = line[:chars_limit - curr_c]
        curr_c += len(line) + 1
        ts = font_main.render(l_draw, True, tuple(font_color))
        screen.blit(ts, (bx + (bubble_w - ts.get_width()) // 2, ty + i * lh))

    if not is_editor:
        f_key = ("Segoe UI_Bold", int(18 * zoom))
        if f_key not in _FONT_CACHE: _FONT_CACHE[f_key] = pygame.font.SysFont("Segoe UI", f_key[1], bold=True)
        btn_w, btn_h, btn_x = int(100 * zoom), int(34 * zoom), bx + (bubble_w - int(100 * zoom)) // 2
        btn_y, btn_r = by + bubble_h - int(34 * zoom) - 15 * zoom, pygame.Rect(btn_x, 0, int(100 * zoom), int(34 * zoom)) # Temp Rect
        btn_r.y = btn_y
        b_col = (70, 210, 120) if btn_r.collidepoint(pygame.mouse.get_pos()) else (60, 185, 105)
        pygame.draw.rect(screen, b_col, btn_r, border_radius=12)
        btn_l = _FONT_CACHE[f_key].render("CHIUDI", True, (255, 255, 255))
        screen.blit(btn_l, (btn_x + (btn_w - btn_l.get_width()) // 2, btn_y + (btn_h - btn_l.get_height()) // 2))
        return btn_r
    return None

class EffectRenderer:
    """Motore effetti con Cloud Clustering e Intelligent Pooling."""
    def __init__(self) -> None:
        self._time, self._render_pool = 0.0, {}

    def update(self, dt: float, effects: list = None) -> None:
        self._time += dt
        if effects:
            for fx in effects: update_effect_state(fx, dt)

    def draw(self, screen: pygame.Surface, effects: list, scaling_manager, lang_manager=None, scenic_factor: float = 1.0) -> list:
        if not effects: return []
        sorted_fx, sm, bubble_btns = sorted(effects, key=lambda f: getattr(f, "layer_z", 40)), scaling_manager, []
        for fx in sorted_fx:
            sx, sy, sr = *sm.bg_to_screen_scenic(fx.x, fx.y, scenic_factor), fx.radius * sm._bg_display_scale * scenic_factor
            if fx.type == "glint":
                draw_glint_effect(screen, sx, sy, sr, fx.color, fx.intensity, fx._t_accum, fx.phase, fx.pulse_min, self._render_pool)
            elif fx.type == "smoke":
                draw_smoke_effect(screen, sx, sy, sr, fx.color, fx.intensity, fx._t_accum, fx.phase, fx.pulse_min, self._render_pool)
            elif fx.type == "flies":
                draw_flies_effect(screen, sx, sy, sr, fx.color, fx.intensity, fx._t_accum, self._time, getattr(fx, "pulse_min", 1.0))
            elif fx.type == "bubble_tip":
                if lang_manager and not getattr(fx, "_visible", False): continue
                text = lang_manager.get(fx.text_key, fx.text_key) if lang_manager else getattr(fx, "text_key", "NEW_TIP")
                btn_r = draw_bubble_tip_effect(screen, sx, sy, text, fx.trigger, is_editor=(lang_manager is None), width=getattr(fx, "width", 300) * sm._bg_display_scale, height=getattr(fx, "height", 180) * sm._bg_display_scale, zoom=sm._bg_display_scale, color=getattr(fx, "color", (252, 252, 255)), alpha=getattr(fx, "alpha", 255), font_size=getattr(fx, "font_size", 22), font_color=getattr(fx, "font_color", (40, 40, 40)), chars_limit=int(getattr(fx, "_chars_visible", 9999)), cache=self._render_pool)
                if btn_r: bubble_btns.append((fx, btn_r))
        if len(self._render_pool) > 500: self._render_pool.clear()
        return bubble_btns
