import pygame
import random
import math
from pathlib import Path
from typing import List, Dict, Any, Tuple

from engine.minigames.minigame_base import BaseMinigame
from engine.utils import get_resource_path, get_logger, is_android_runtime

# Su Android alcuni effetti "ricchi" dello slot (glow radiale full-screen, motion-blur
# dei simboli) sono troppo cari per-frame: vengono degradati per tenere alti gli FPS.
_ANDROID = is_android_runtime()

# Configurazione Logica Bilanciata (RTP ~96%)
INITIAL_CREDITS = 2000
MIN_BET = 10
MAX_BET = 500
PAYTABLE = {
    "shiny_star": 500,    # Jackpot / Free Spins
    "golden_bell": 100,
    "red_cherries": 50,
    "lucky_seven": 20,
    "blue_diamond": 10,
    "green_clover": 5,
    "grape_bunch": 2
}

class SlotClassicGame(BaseMinigame):
    """
    Minigioco Slot Machine: Lucky Reels.
    Stile Arcade/Fumetto con effetti particellari, rimbalzo elastico e logica RTP.
    """
    def __init__(self, screen: pygame.Surface, scaling_manager: Any, 
                 audio_manager: Any = None, lang_manager: Any = None,
                 on_complete: Any = None, params: Any = None) -> None:
        super().__init__(screen, scaling_manager, audio_manager, lang_manager, on_complete, params)
        self.logger = get_logger("SlotClassic")
        
        # Stato Gioco
        self.credits = INITIAL_CREDITS
        self.display_credits = float(INITIAL_CREDITS)
        self.current_bet = MIN_BET
        self.last_win = 0
        self.display_win = 0.0
        self.progressive_jackpot = 50000.0
        
        # Rulli
        self.num_reels = 3
        self.reels_pos = [0.0] * self.num_reels
        self.reels_speed = [0.0] * self.num_reels
        self.reels_overshoot = [0.0] * self.num_reels # Effetto molla allo stop
        self.spinning = [False] * self.num_reels
        self.reel_strips = self._generate_strips()
        
        # Animazioni e FX
        self.particles = []
        self.screen_shake = 0.0
        self.neon_cycle = 0.0
        self.win_animation_timer = 0.0
        self.win_text_scale = 1.0
        self.winning_line_alpha = 0
        self.free_spins_left = 0
        
        # UI, Assets & Cache
        self.symbols_images = {}
        self._symbols_cache = {} # Cache per icone pre-scalate
        self.btn_scales = {"spin": 1.0, "plus": 1.0, "minus": 1.0, "pay": 1.0, "exit": 1.0}
        self.show_paytable = False
        self._load_assets()
        
        # Localization
        strings_path = get_resource_path("engine", "minigames", "slot_classic", "strings")
        self.load_local_strings(strings_path)

    def start(self) -> None:
        """Metodo chiamato dall'engine all'avvio del minigioco."""
        self.logger.info("Slot Machine: Sessione avviata (Stile Fumetto).")

    def _generate_strips(self) -> List[List[str]]:
        symbols = list(PAYTABLE.keys())
        # Frequenza assoluta per ogni simbolo (Quantità per rullo)
        # [Jackpot, Campana, Ciliegie, Sette, Diamante, Quadrifoglio, Uva]
        frequencies = [1, 2, 4, 6, 8, 12, 20] 
        
        strip = []
        for s, f in zip(symbols, frequencies):
            strip.extend([s] * f)
            
        reels = []
        for _ in range(self.num_reels):
            current_strip = strip[:]
            random.shuffle(current_strip)
            reels.append(current_strip)
            
        return reels

    def _load_assets(self):
        assets_map = {
            "shiny_star": "obj_slot_shiny_star.png",
            "golden_bell": "obj_slot_golden_bell.png",
            "red_cherries": "obj_slot_red_cherries.png",
            "lucky_seven": "obj_slot_lucky_7.png",
            "blue_diamond": "obj_slot_big_diamond.png",
            "green_clover": "obj_slot_four_leaf_clover.png",
            "grape_bunch": "obj_slot_purple_grapes.png"
        }
        for key, filename in assets_map.items():
            # 1) Sprite BUNDLATO del minigioco (self-contained: sopravvive al pruning
            #    della libreria condivisa engine/assets/ nel packaging Android).
            path = get_resource_path("engine", "minigames", "slot_classic", "assets", "sprite", filename)
            if not path.exists():
                # 2) Fallback: catalogo Cartoon condiviso
                path = get_resource_path("engine", "assets", "objects_cartoon", filename)
            if not path.exists():
                # 3) Fallback: catalogo Real/Standard condiviso
                path = get_resource_path("engine", "assets", "objects", filename)

            if path.exists():
                self.symbols_images[key] = pygame.image.load(str(path)).convert_alpha()
            else:
                self.logger.warning(f"Asset non trovato: {filename}")

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE: self.finish_game()
            elif event.key == pygame.K_SPACE and not self.show_paytable: self._start_spin()
            
        elif event.type == pygame.MOUSEBUTTONDOWN:
            m_pos = event.pos
            if self.show_paytable:
                self.show_paytable = False
                self._play_sfx("click")
                return
                
            # Gestione click bottoni
            if self.btn_spin_rect.collidepoint(m_pos): 
                self.btn_scales["spin"] = 0.85
                self._start_spin()
            elif self.btn_bet_plus_rect.collidepoint(m_pos):
                self.btn_scales["plus"] = 0.8
                self._change_bet(10)
            elif self.btn_bet_minus_rect.collidepoint(m_pos):
                self.btn_scales["minus"] = 0.8
                self._change_bet(-10)
            elif self.btn_pay_rect.collidepoint(m_pos):
                self.btn_scales["pay"] = 0.8
                self.show_paytable = True
                self._play_sfx("click")
            elif self.btn_exit_rect.collidepoint(m_pos):
                self.btn_scales["exit"] = 0.8
                self._play_sfx("click")
                self.finish_game()

    def _change_bet(self, amount: int):
        self.current_bet = max(MIN_BET, min(MAX_BET, self.current_bet + amount))
        self._play_sfx("click")

    def _play_sfx(self, sound_id: str):
        if not self.audio_manager: return
        mapping = {
            "spin_start": ("engine", "assets", "sounds", "click_Low.wav"),
            "reel_stop": ("engine", "assets", "sounds", "click_Low.wav"),
            "win_small": ("engine", "assets", "sounds", "bling1.mp3"),
            "win_big": ("engine", "assets", "sounds", "level_up.mp3"),
            "jackpot": ("engine", "assets", "sounds", "victory.mp3"),
            "click": ("engine", "assets", "sounds", "click_Low.wav"),
            "bet_change": ("engine", "assets", "sounds", "click_Low.wav")
        }
        if sound_id in mapping:
            path_parts = mapping[sound_id]
            self.audio_manager.play_sfx(Path(*path_parts))

    def _start_spin(self):
        if self.credits < self.current_bet and self.free_spins_left <= 0: return 
        
        # Se i rulli stanno girando, il tasto GIOCA funge da STOP
        if any(self.spinning):
            self._force_stop()
            return
            
        if self.free_spins_left > 0: self.free_spins_left -= 1
        else: self.credits -= self.current_bet
        
        self.display_win = 0.0
        self.last_win = 0
        self.win_animation_timer = 0
        self.progressive_jackpot += self.current_bet * 0.02
        
        # Algoritmo Real Slot: Il risultato viene deciso QUI dall'RNG
        self.target_indices = []
        for i in range(self.num_reels):
            self.target_indices.append(random.randint(0, len(self.reel_strips[i]) - 1))
            self.spinning[i] = True
            # Velocità ridotta drasticamente per vedere i simboli girare (simboli per frame)
            self.reels_speed[i] = 0.6 + (i * 0.2)
            
        self.spin_timer = 2.5 # Aumentato il tempo di spin
        self.tick_timer = 0.0 # Timer per il suono ritmico
        self._play_sfx("spin_start")

    def _force_stop(self):
        """Ferma istantaneamente tutti i rulli ancora in movimento."""
        for i in range(self.num_reels):
            if self.spinning[i]:
                self._stop_reel(i)
        self.spin_timer = 0 # Azzera il timer residuo

    def update(self, dt: float) -> None:
        # Clamp del dt per la fisica: a FPS bassi (es. 8 FPS -> dt~0.125) i fattori
        # di decadimento "1 - dt*k" diventavano NEGATIVI, facendo oscillare i rulli
        # all'infinito (overshoot che cambia segno ogni frame) -> sembravano non
        # fermarsi mai. Limitando dt il decadimento resta stabile (sempre in [0,1]).
        dt = min(dt, 0.05)
        # Interpolazione fluida crediti e vincite (Professional LERP)
        lerp_speed = 8.0
        self.display_credits += (self.credits - self.display_credits) * dt * lerp_speed
        self.display_win += (self.last_win - self.display_win) * dt * lerp_speed
        
        self.neon_cycle += dt * 3.0
        
        if any(self.spinning):
            self.spin_timer -= dt
            
            # Suono meccanico adattivo (rallenta man mano che i rulli rallentano)
            self.tick_timer -= dt
            if self.tick_timer <= 0:
                self._play_sfx("click")
                active_speeds = [self.reels_speed[i] for i in range(self.num_reels) if self.spinning[i]]
                if active_speeds:
                    max_speed = max(active_speeds)
                    # Il click rallenta quando la velocità diminuisce
                    self.tick_timer = max(0.05, 0.1 / max_speed) if max_speed > 0.1 else 0.2
                else:
                    self.tick_timer = 0.15
                
            for i in range(self.num_reels):
                if self.spinning[i]:
                    # Scarto aumentato per dare il tempo ad ogni rullo di fermarsi (0.6s di differenza)
                    stop_time = -(i * 0.6) 
                    time_until_stop = self.spin_timer - stop_time
                    
                    # Decelerazione: negli ultimi 0.8 secondi inizia a rallentare progressivamente
                    if time_until_stop < 0.8:
                        self.reels_speed[i] *= (1.0 - (dt * 2.5))
                        self.reels_speed[i] = max(0.15, self.reels_speed[i]) # Evita che si fermi completamente
                        
                    self.reels_pos[i] = (self.reels_pos[i] + self.reels_speed[i] * dt * 60) % len(self.reel_strips[i])
                    
                    if time_until_stop <= 0: 
                        self._stop_reel(i)
        
        # Gestione Overshoot (Molla rulli allo stop)
        for i in range(self.num_reels):
            if not self.spinning[i]:
                self.reels_overshoot[i] *= (1.0 - dt * 15.0)
        
        if self.screen_shake > 0: self.screen_shake -= dt * 30
        for p in self.particles[:]:
            p['x'] += p['vx'] * 60 * dt
            p['y'] += p['vy'] * 60 * dt
            p['vy'] += p['gravity'] * 60 * dt
            p['angle'] += p['rot_speed'] * 60 * dt
            if p['y'] > self.scaling_manager.screen_h + 100: self.particles.remove(p)

        if self.win_animation_timer > 0:
            self.win_animation_timer -= dt
            self.win_text_scale = 1.0 + 0.15 * math.sin(pygame.time.get_ticks() * 0.01)
            self.winning_line_alpha = int(150 + 105 * math.sin(pygame.time.get_ticks() * 0.015))
            # Animazione pulsazione box vincita
            self.win_box_glow = abs(math.sin(pygame.time.get_ticks() * 0.01)) * 5 * self.scaling_manager.scale
        else:
            self.winning_line_alpha = 0
            self.win_text_scale = 1.0
            self.win_box_glow = 0
        for k in self.btn_scales: self.btn_scales[k] += (1.0 - self.btn_scales[k]) * dt * 12

    def _stop_reel(self, i: int):
        if not self.spinning[i]: return
        self.spinning[i] = False
        self.reels_speed[i] = 0
        # Snapping sul risultato pre-calcolato (Stile Slot Reale)
        self.reels_pos[i] = float(self.target_indices[i])
        self.reels_overshoot[i] = 0.25
        self.screen_shake = max(self.screen_shake, 6.0)
        self._play_sfx("reel_stop")
        if i == self.num_reels - 1: self._check_win()

    def _check_win(self):
        center_symbols = []
        for i in range(self.num_reels):
            # Calcoliamo il simbolo centrale basandoci sull'indice target
            idx = (self.target_indices[i] + 1) % len(self.reel_strips[i])
            center_symbols.append(self.reel_strips[i][idx])
        
        if center_symbols[0] == center_symbols[1] == center_symbols[2]:
            sym = center_symbols[0]
            mult = PAYTABLE.get(sym, 0)
            if self.free_spins_left > 0: mult *= 2
            self.last_win = self.current_bet * mult
            self.credits += self.last_win
            self.win_animation_timer = 3.5
            if sym == "shiny_star":
                self.free_spins_left += 10
                self.last_win += int(self.progressive_jackpot)
                self.credits += int(self.progressive_jackpot)
                self.progressive_jackpot = 50000.0
                self._spawn_coins(150)
                self.screen_shake = 25.0
                self._play_sfx("jackpot")
            else:
                self._spawn_coins(40 if mult < 50 else 100)
                self._play_sfx("win_big" if mult >= 50 else "win_small")
        elif center_symbols[0] == center_symbols[1] == "red_cherries":
            self.last_win, self.win_animation_timer = self.current_bet, 2.0
            self.credits += self.last_win
            self._spawn_coins(10)
            self._play_sfx("win_small")
            
        self.logger.info(f"Spin Result: {center_symbols} | Win: {self.last_win}")

    def _spawn_coins(self, count: int):
        sw, sh = self.scaling_manager.screen_w, self.scaling_manager.screen_h
        for _ in range(count):
            self.particles.append({
                'x': sw // 2, 'y': sh // 2,
                'vx': random.uniform(-6, 6), 'vy': random.uniform(-12, -4),
                'rot_speed': random.randint(-8, 8), 'angle': random.random() * 360,
                'gravity': 0.35, 'color': (255, 215, 0) if random.random() > 0.3 else (255, 255, 255)
            })

    def _get_slot_bg(self, sw, sh):
        """Sfondo statico cachato (fill scuro + raggiera). Su Android i raggi non
        ruotano (sarebbe un costo per-frame): pre-renderizzati una volta sola."""
        key = (sw, sh)
        cached = getattr(self, "_slot_bg_cache", None)
        if cached is not None and cached[0] == key:
            return cached[1]
        bg = pygame.Surface((sw, sh)).convert()
        bg.fill((2, 2, 8))
        center = (sw // 2, sh // 2)
        num_rays = 12
        ray_angle = 360 / num_rays
        for i in range(num_rays):
            angle = math.radians(i * ray_angle)
            p1 = center
            p2 = (center[0] + math.cos(angle - 0.2) * sw, center[1] + math.sin(angle - 0.2) * sw)
            p3 = (center[0] + math.cos(angle + 0.2) * sw, center[1] + math.sin(angle + 0.2) * sw)
            pygame.draw.polygon(bg, (25, 10, 50), [p1, p2, p3])
        self._slot_bg_cache = (key, bg)
        return bg

    def _draw_ambient_glow(self, sw, sh, scale):
        # Sfondo a raggiera (Sunburst) stile copertina fumetto
        center = (sw // 2, sh // 2)
        num_rays = 12
        ray_angle = 360 / num_rays
        time_offset = pygame.time.get_ticks() * 0.02
        
        for i in range(num_rays):
            angle = math.radians(i * ray_angle + time_offset)
            p1 = center
            p2 = (center[0] + math.cos(angle - 0.2) * sw, center[1] + math.sin(angle - 0.2) * sw)
            p3 = (center[0] + math.cos(angle + 0.2) * sw, center[1] + math.sin(angle + 0.2) * sw)
            # Colori più caldi e profondi (stile Vegas)
            pygame.draw.polygon(self.screen, (25, 10, 50), [p1, p2, p3])

        # Rimossi i punti Halftone (Ben-Day) dallo sfondo per un look più pulito

        # Glow radiale ambient: su Android e' troppo caro (Surface SRCALPHA ~900x900
        # + ~15 cerchi + blit BLEND_ADD OGNI frame) -> saltato. I raggi sopra bastano.
        if not _ANDROID:
            col = self._get_neon_color()
            g_size = int(600 * scale)
            g_surf = pygame.Surface((g_size*2, g_size*2), pygame.SRCALPHA)
            for r in range(g_size, 0, -int(30*scale)):
                alpha = int(60 * (1.0 - r/g_size))
                pygame.draw.circle(g_surf, (*col, alpha), (g_size, g_size), r)
            self.screen.blit(g_surf, (sw//2 - g_size, sh//2 - g_size), special_flags=pygame.BLEND_ADD)

    def _get_neon_color(self) -> Tuple[int, int, int]:
        if self.free_spins_left > 0:
            return (255, int(150 + 50 * math.cos(self.neon_cycle*2)), 0)
        return (int(100 + 50 * math.sin(self.neon_cycle)), 50, 255)

    def _font(self, name: str, size, bold: bool = False) -> pygame.font.Font:
        """Font cacheato (evita SysFont ogni frame: lento su Android)."""
        if not hasattr(self, "_font_cache"):
            self._font_cache = {}
        key = (name, int(size), bold)
        f = self._font_cache.get(key)
        if f is None:
            f = pygame.font.SysFont(name, max(8, int(size)), bold=bold)
            self._font_cache[key] = f
        return f

    def draw(self) -> None:
        sw, sh = self.scaling_manager.screen_w, self.scaling_manager.screen_h
        scale = self.scaling_manager.scale
        ox = random.randint(-int(self.screen_shake), int(self.screen_shake)) if self.screen_shake > 0 else 0
        oy = random.randint(-int(self.screen_shake), int(self.screen_shake)) if self.screen_shake > 0 else 0

        # Sfondo: su Android pre-renderizzato e cachato (fill + 12 raggi). I raggi
        # full-screen ridisegnati ogni frame erano un grosso costo su rendering ARM.
        if _ANDROID:
            self.screen.blit(self._get_slot_bg(sw, sh), (0, 0))
        else:
            self.screen.fill((2, 2, 8))
            self._draw_ambient_glow(sw, sh, scale)
        self._draw_particles(scale, ox, oy)

        cab_w = min(sw * 0.85, 800 * scale)
        cab_h = min(sh * 0.65, 480 * scale)
        cab_rect = pygame.Rect(sw//2 - cab_w//2 + ox, sh//2 - cab_h//2 + oy, cab_w, cab_h)

        self._draw_cabinet(cab_rect, scale)
        self._draw_jackpot_panel(cab_rect, scale, ox, oy)

        reels_w, reels_h = cab_w * 0.82, cab_h * 0.52 # Ridotto ulteriormente per dare aria
        reels_area = pygame.Rect(cab_rect.centerx - reels_w//2, cab_rect.centery - reels_h//2 - 55*scale, reels_w, reels_h)

        pygame.draw.rect(self.screen, (0, 0, 0), reels_area.inflate(16*scale, 16*scale), border_radius=int(14*scale))
        pygame.draw.rect(self.screen, (15, 15, 45), reels_area, border_radius=int(8*scale)) # Blu Casino Profondo

        # Rimossa texture a punti dai rulli per maggiore leggibilità
        self._draw_reels(reels_area, scale)
        self._draw_overlay_and_ui(sw, sh, scale, reels_area, ox, oy, cab_rect)

    def _get_coin_sprite(self, color, sz):
        """Sprite moneta pre-disegnato e cachato per (colore, dimensione). Senza cache
        ogni particella ricreava una Surface SRCALPHA + 2 draw.circle ogni frame: con
        fino a 150 monete (jackpot) e' un costo enorme su Android."""
        if not hasattr(self, "_coin_sprite_cache"):
            self._coin_sprite_cache = {}
        key = (color, sz)
        spr = self._coin_sprite_cache.get(key)
        if spr is None:
            spr = pygame.Surface((sz, sz), pygame.SRCALPHA)
            pygame.draw.circle(spr, color, (sz // 2, sz // 2), sz // 2)
            pygame.draw.circle(spr, (0, 0, 0), (sz // 2, sz // 2), sz // 2, 1)
            spr = spr.convert_alpha()
            self._coin_sprite_cache[key] = spr
        return spr

    def _draw_particles(self, scale, ox, oy):
        sz = int(12 * scale)
        for p in self.particles:
            spr = self._get_coin_sprite(p['color'], sz)
            if _ANDROID:
                # Su Android: niente rotate per-particella-per-frame (la moneta e'
                # un cerchio piccolo, la rotazione e' impercettibile mentre vola).
                self.screen.blit(spr, (p['x'] + ox - sz // 2, p['y'] + oy - sz // 2))
            else:
                rot = pygame.transform.rotate(spr, p['angle'])
                self.screen.blit(rot, (p['x'] + ox - rot.get_width() // 2, p['y'] + oy - rot.get_height() // 2))

    def _draw_cabinet(self, rect, scale):
        # Chrome statico (4 rounded-rect nidificati): la forma non cambia mai.
        if not _ANDROID:
            # Desktop: disegno diretto dei 4 rounded-rect TRASPARENTI come l'originale,
            # cosi' gli angoli arrotondati lasciano trasparire raggi/glow dello sfondo.
            pygame.draw.rect(self.screen, (0, 0, 0), rect.inflate(20*scale, 20*scale), border_radius=int(32*scale))
            pygame.draw.rect(self.screen, (255, 215, 0), rect.inflate(12*scale, 12*scale), border_radius=int(30*scale))
            pygame.draw.rect(self.screen, (180, 140, 20), rect.inflate(6*scale, 6*scale), border_radius=int(28*scale))
            pygame.draw.rect(self.screen, (15, 15, 25), rect, border_radius=int(26*scale))
            return
        # Android: chrome pre-renderizzato su Surface OPACA e cachato. Il blit
        # per-pixel-alpha (SRCALPHA) di una surface grande e' ~10x piu' caro su GPU
        # mobile (era ~90ms/frame); gli angoli esterni sono riempiti col colore di
        # sfondo (2,2,8) cosi' coincidono col fondo e il blit resta opaco/veloce.
        margin = int(20 * scale) + 4  # bordo piu' esterno (inflate 20*scale)
        key = (rect.width, rect.height, round(scale, 3))
        cached = getattr(self, "_cabinet_cache", None)
        if cached is None or cached[0] != key:
            surf_w = rect.width + margin * 2
            surf_h = rect.height + margin * 2
            # Surface OPACA: il blit per-pixel-alpha (SRCALPHA) di una surface grande
            # e' ~10x piu' caro su GPU software (swiftshader/ARM) del blit opaco. Gli
            # angoli arrotondati esterni vengono riempiti col colore di sfondo (2,2,8)
            # cosi' coincidono col fondo dello slot e il blit resta opaco/veloce.
            surf = pygame.Surface((surf_w, surf_h))
            surf.fill((2, 2, 8))
            local = pygame.Rect(margin, margin, rect.width, rect.height)
            pygame.draw.rect(surf, (0, 0, 0), local.inflate(20*scale, 20*scale), border_radius=int(32*scale))
            pygame.draw.rect(surf, (255, 215, 0), local.inflate(12*scale, 12*scale), border_radius=int(30*scale))
            pygame.draw.rect(surf, (180, 140, 20), local.inflate(6*scale, 6*scale), border_radius=int(28*scale))
            pygame.draw.rect(surf, (15, 15, 25), local, border_radius=int(26*scale))
            surf = surf.convert()
            self._cabinet_cache = (key, surf, margin)
            cached = self._cabinet_cache
        _, surf, margin = cached
        self.screen.blit(surf, (rect.left - margin, rect.top - margin))

    def _draw_jackpot_panel(self, cab_rect, scale, ox, oy):
        neon = self._get_neon_color()
        j_w, j_h = cab_rect.width * 0.7, 60 * scale
        j_rect = pygame.Rect(cab_rect.centerx - j_w//2, cab_rect.top - 20*scale + oy, j_w, j_h)
        pygame.draw.rect(self.screen, (0, 0, 0), j_rect.inflate(4*scale, 4*scale), border_radius=int(17*scale))
        pygame.draw.rect(self.screen, (5, 5, 10), j_rect, border_radius=int(15*scale))
        pygame.draw.rect(self.screen, neon, j_rect, int(2*scale), border_radius=int(15*scale))
        self._draw_text_centered(f"JACKPOT: {int(self.progressive_jackpot)}", self._font("Impact", 38*scale), j_rect.center, neon)

    def _get_symbol_tile(self, sym, rw, sh):
        """Tile OPACA (fondo rullo + simbolo centrato) per Android. Il blit
        per-pixel-alpha dei 15 simboli/frame era il costo dominante (~18ms su GPU
        software). Pre-componendo il simbolo su una tile opaca del colore del rullo
        (15,15,45) il blit diventa opaco (veloce) e le tile, contigue e dello stesso
        colore, riempiono la colonna senza giunte visibili."""
        if not hasattr(self, "_tile_cache"):
            self._tile_cache = {}
        key = (sym, rw, sh)
        tile = self._tile_cache.get(key)
        if tile is None:
            tile = pygame.Surface((rw, sh))
            tile.fill((15, 15, 45))
            img = self.symbols_images.get(sym)
            if img:
                iw, ih = img.get_size()
                fit = min(rw * 0.85 / iw, sh * 0.85 / ih)
                tw, th = max(1, int(iw * fit)), max(1, int(ih * fit))
                scaled = pygame.transform.smoothscale(img, (tw, th))
                tile.blit(scaled, ((rw - tw) // 2, (sh - th) // 2))
            tile = tile.convert()
            self._tile_cache[key] = tile
        return tile

    def _draw_reels(self, area, scale):
        rw, sh = area.width // self.num_reels, area.height // 3
        # Sfondo pulito senza linee per risaltare lo stretch dei simboli

        for i in range(self.num_reels):
            rx = area.left + (i * rw)
            # Applicazione visuale dell'overshoot
            visual_pos = self.reels_pos[i] + self.reels_overshoot[i]
            off_y = (visual_pos - int(visual_pos)) * sh
            st_idx = int(visual_pos)

            self.screen.set_clip(pygame.Rect(rx, area.top, rw, area.height))
            if _ANDROID:
                # Android: tile opache (fondo rullo + simbolo) -> blit opachi veloci.
                for j in range(-1, 4):
                    sym = self.reel_strips[i][(st_idx + j) % len(self.reel_strips[i])]
                    tile = self._get_symbol_tile(sym, rw, sh)
                    self.screen.blit(tile, (rx, int(area.top + (j * sh) - off_y)))
            else:
                for j in range(-1, 4):
                    sym = self.reel_strips[i][(st_idx + j) % len(self.reel_strips[i])]
                    img = self.symbols_images.get(sym)
                    if img:
                        cache_key = (sym, int(rw * 0.85), int(sh * 0.85))
                        if cache_key not in self._symbols_cache:
                            iw, ih = img.get_size()
                            fit = min(cache_key[1]/iw, cache_key[2]/ih)
                            self._symbols_cache[cache_key] = pygame.transform.smoothscale(img, (int(iw*fit), int(ih*fit)))

                        s_img = self._symbols_cache[cache_key]
                        tw, th = s_img.get_size()
                        px, py = rx + (rw-tw)//2, area.top + (j*sh) - off_y + (sh-th)//2

                        if self.reels_speed[i] > 10:
                            # Effetto Stretch Dinamico (Cartoon Motion Blur) — desktop only.
                            stretch = 1.0 + (self.reels_speed[i] / 40.0)
                            s_img = pygame.transform.smoothscale(s_img, (tw, int(th * stretch)))
                            self.screen.blit(s_img, (px, py - (s_img.get_height() - th) // 2))
                        else:
                            self.screen.blit(s_img, (px, py))

            self.screen.set_clip(None)
            if i < self.num_reels-1:
                # Divisori rulli netti
                pygame.draw.line(self.screen, (0, 0, 0), (rx + rw, area.top), (rx + rw, area.bottom), 4)

    def _draw_overlay_and_ui(self, sw, sh, scale, area, ox, oy, cab_rect):
        py = area.centery
        if self.winning_line_alpha > 0:
            # Striscia gialla cachata una volta; il pulsare e' gestito con set_alpha
            # (niente Surface SRCALPHA + draw.rect ricreati ogni frame).
            gw, gh = int(area.width), int(24 * scale)
            cached = getattr(self, "_winline_glow_cache", None)
            if cached is None or cached[0] != (gw, gh):
                glow = pygame.Surface((gw, gh)).convert()
                glow.fill((255, 255, 0))
                self._winline_glow_cache = ((gw, gh), glow)
                cached = self._winline_glow_cache
            glow = cached[1]
            glow.set_alpha(self.winning_line_alpha // 2)
            self.screen.blit(glow, (area.left, py - 12*scale))
        pygame.draw.line(self.screen, (0, 0, 0), (area.left, py), (area.right, py), int(4*scale))
        pygame.draw.line(self.screen, (255, 255, 255), (area.left, py), (area.right, py), int(2*scale))
        
        if self.win_animation_timer > 0:
            self._draw_comic_win(sw, area.top - 50*scale, scale)
            
        if self.credits < MIN_BET and not any(self.spinning) and self.free_spins_left <= 0:
            self.screen.blit(self._get_dim_overlay(sw, sh, (0, 0, 0, 230)), (0, 0))
            self._draw_text_comic(self._("game_over"), self._font("Impact", 110*scale), (sw//2, sh//2), (255, 0, 0))
            
        self._draw_ui(sw, sh, scale, cab_rect)
        if self.show_paytable: self._draw_paytable_overlay(sw, sh, scale)

    def _draw_comic_win(self, sw, y, scale):
        text = f"{self._('fever_prefix') if self.free_spins_left > 0 else ''}{self._('win_msg').format(amount=self.last_win)}"
        font = self._font("Impact", 75*scale*self.win_text_scale)
        center = (sw//2, y)
        points = []
        num_points = 18
        inner_r, outer_r = 115*scale*self.win_text_scale, 180*scale*self.win_text_scale
        for i in range(num_points * 2):
            r = outer_r if i % 2 == 0 else inner_r
            angle = math.radians(i * (360 / (num_points * 2)))
            points.append((center[0] + math.cos(angle) * r, center[1] + math.sin(angle) * r))
        
        pygame.draw.polygon(self.screen, (0, 0, 0), points, int(10*scale)) # Outline inchiostro
        pygame.draw.polygon(self.screen, (255, 215, 0), points)
        pygame.draw.polygon(self.screen, (0, 0, 0), points, int(3*scale))
        self._draw_text_comic(text, font, center, (255, 255, 255))

    def _get_comic_text_surface(self, text, font, color):
        """Compone UNA volta il testo fumetto (outline nero + riempimento) su una
        singola Surface trasparente e la cacha. Senza cache questo metodo renderizza
        il font ~50-120 volte per frame (loop di offset NxN) per OGNI bottone/etichetta:
        e' il piu' grosso costo per-frame su Android. Con cache un'etichetta statica
        (es. "GIOCA", "+", "ESCI") diventa un singolo blit dopo il primo frame."""
        if not hasattr(self, "_comic_text_cache"):
            self._comic_text_cache = {}
        thickness = int(max(2, 4 * (font.get_height() / 100)))
        # Chiave: testo, altezza font (cattura scale + win_text_scale), colore, spessore.
        key = (text, font.get_height(), color, thickness)
        cached = self._comic_text_cache.get(key)
        if cached is not None:
            return cached

        # Guard anti-crescita: il testo vincita pulsa attraverso molte altezze font.
        if len(self._comic_text_cache) > 256:
            self._comic_text_cache.clear()
        base = font.render(text, True, color)
        outline = font.render(text, True, (0, 0, 0))
        bw, bh = base.get_size()
        # Surface composita con margine per l'outline su tutti i lati.
        comp = pygame.Surface((bw + thickness * 2, bh + thickness * 2), pygame.SRCALPHA)
        cx, cy = thickness, thickness
        for dx in range(-thickness, thickness + 1):
            for dy in range(-thickness, thickness + 1):
                if dx * dx + dy * dy <= thickness * thickness:
                    comp.blit(outline, (cx + dx, cy + dy))
        comp.blit(base, (cx, cy))
        comp = comp.convert_alpha()
        self._comic_text_cache[key] = comp
        return comp

    def _draw_text_comic(self, text, font, center, color):
        surf = self._get_comic_text_surface(text, font, color)
        self.screen.blit(surf, surf.get_rect(center=center))

    def _draw_ui(self, sw, sh, scale, cab_rect):
        f_m = self._font("Impact", 30*scale)
        f_s = self._font("Impact", 16*scale)
        f_info = self._font("Arial", 14*scale)
        
        # HUD Comic Stickers: Box Dinamici su riga unica (LABEL: VALORE)
        labels = ["CREDITI", "PUNTATA", "VINCITA"]
        values = [f"{int(self.display_credits)}", f"{self.current_bet}", f"{int(self.display_win)}"]
        border_colors = [(50, 200, 100), (200, 50, 50), (255, 215, 0)]
        text_colors = [(100, 255, 150), (255, 150, 150), (255, 255, 200)]
        
        # Font unico più leggibile per riga singola
        f_hud = self._font("Impact", 24*scale)
        
        # Calcolo ingombri per centratura
        items_data = []
        total_width = 0
        spacing = 15 * scale
        
        for i in range(3):
            txt = f"{labels[i]}: {values[i]}"
            surf = f_hud.render(txt, True, text_colors[i])
            w = surf.get_width() + 40 * scale # Padding X
            items_data.append((surf, w))
            total_width += w
        total_width += spacing * 2
        
        start_x = cab_rect.centerx - total_width // 2
        y_pos = cab_rect.bottom - 75*scale - 20*scale
        
        curr_x = start_x
        for i in range(3):
            surf, w = items_data[i]
            h = 55 * scale
            rect = pygame.Rect(curr_x, y_pos, w, h)
            
            # Animazione pulsazione box vincita
            if i == 2 and self.win_animation_timer > 0:
                rect = rect.inflate(self.win_box_glow, self.win_box_glow)
            
            # Sfondo e Bordo
            pygame.draw.rect(self.screen, (15, 15, 25), rect, border_radius=int(10*scale))
            pygame.draw.rect(self.screen, border_colors[i], rect, int(4*scale), border_radius=int(10*scale))
            
            # Testo centrato nel box
            self.screen.blit(surf, (rect.centerx - surf.get_width()//2, rect.centery - surf.get_height()//2))
            curr_x += w + spacing

        # Bottoni Flat Fumetto
        btn_y = cab_rect.bottom + 65 * scale
        if btn_y + 35*scale > sh: btn_y = sh - 45*scale
        
        self.btn_exit_rect = self._draw_btn("ESCI", (cab_rect.left + 80*scale, btn_y), (140, 140, 150), f_s, scale, "exit")
        self.btn_pay_rect = self._draw_btn("PREMI", (cab_rect.right - 80*scale, btn_y), (140, 140, 150), f_s, scale, "pay")
        
        self.btn_bet_minus_rect = self._draw_btn("-", (sw//2 - 165*scale, btn_y), (230, 80, 80), f_s, scale, "minus")
        self.btn_bet_plus_rect = self._draw_btn("+", (sw//2 - 95*scale, btn_y), (80, 230, 80), f_s, scale, "plus")
        
        # Testo dinamico GIOCA/STOP
        spin_label = "STOP" if any(self.spinning) else "GIOCA"
        spin_color = (50, 100, 230) if any(self.spinning) else (230, 60, 60)
        self.btn_spin_rect = self._draw_btn(spin_label, (sw//2 + 125*scale, btn_y), spin_color, f_m, scale, "spin", True)

    def _draw_btn(self, label, center, color, font, scale, b_id, is_large=False):
        sc = self.btn_scales.get(b_id, 1.0)
        bw, bh = (165*scale*sc, 65*scale*sc) if is_large else (60*scale*sc, 60*scale*sc)
        rect = pygame.Rect(0, 0, bw, bh); rect.center = center
        
        # Drop shadow ridotto (più pulito)
        pygame.draw.rect(self.screen, (0, 0, 0), rect.move(2*scale, 2*scale), border_radius=int(12*scale))
        
        # Corpo bottone flat
        pygame.draw.rect(self.screen, color, rect, border_radius=int(12*scale))
        
        # Bordo nero inchiostro
        pygame.draw.rect(self.screen, (0, 0, 0), rect, int(4*scale), border_radius=int(12*scale))
        
        # Testo stile fumetto
        self._draw_text_comic(label, font, rect.center, (255, 255, 255))
        return rect

    def _draw_hud_item(self, label, value, center, f_s, f_m, text_color=(0, 0, 0), label_color=(100, 100, 100)):
        # Nota: Questo metodo è ora integrato in _draw_ui per gestire il dimensionamento dinamico
        pass

    def _draw_text_centered(self, text, font, center, color=(255, 255, 255)):
        # Cache per (testo, altezza, colore): cache-hit quando la stringa non cambia
        # (es. JACKPOT tra uno spin e l'altro, titolo paytable). Sicura su entrambe.
        if not hasattr(self, "_plain_text_cache"):
            self._plain_text_cache = {}
        key = (text, font.get_height(), color)
        surf = self._plain_text_cache.get(key)
        if surf is None:
            # Guard anti-crescita: il valore JACKPOT cambia tra spin, quindi le chiavi
            # si accumulano lentamente. Svuota se il dizionario diventa troppo grande.
            if len(self._plain_text_cache) > 256:
                self._plain_text_cache.clear()
            surf = font.render(text, True, color).convert_alpha()
            self._plain_text_cache[key] = surf
        self.screen.blit(surf, surf.get_rect(center=center))

    def _get_dim_overlay(self, sw, sh, rgba):
        """Overlay fullscreen semi-trasparente cachato per (dimensione, colore+alpha).
        Ricrearne uno SRCALPHA fullscreen + fill OGNI frame costa ~10x su Android."""
        if not hasattr(self, "_dim_overlay_cache"):
            self._dim_overlay_cache = {}
        key = (sw, sh, rgba)
        ov = self._dim_overlay_cache.get(key)
        if ov is None:
            ov = pygame.Surface((sw, sh), pygame.SRCALPHA)
            ov.fill(rgba)
            ov = ov.convert_alpha()
            self._dim_overlay_cache[key] = ov
        return ov

    def _draw_paytable_overlay(self, sw, sh, scale):
        self.screen.blit(self._get_dim_overlay(sw, sh, (5, 5, 10, 245)), (0, 0))
        f_title = self._font("Impact", 65*scale)
        self._draw_text_comic("TABELLA PAGAMENTI", f_title, (sw//2, 80*scale), (255, 215, 0))
        
        items = list(PAYTABLE.items())
        cols, card_w, card_h = 3, 245 * scale, 125 * scale
        margin_x, margin_y = 35 * scale, 30 * scale
        start_x = sw//2 - ((card_w + margin_x) * cols) // 2 + margin_x//2
        start_y = 180 * scale
        
        f_val, f_lbl = self._font("Impact", 32*scale), self._font("Arial", 14*scale, bold=True)
        for idx, (sym, mult) in enumerate(items):
            r, c = idx // cols, idx % cols
            rect = pygame.Rect(start_x + c * (card_w + margin_x), start_y + r * (card_h + margin_y), card_w, card_h)
            pygame.draw.rect(self.screen, (0, 0, 0), rect.inflate(4*scale, 4*scale), border_radius=int(17*scale))
            pygame.draw.rect(self.screen, (25, 25, 35), rect, border_radius=int(15*scale))
            
            img = self.symbols_images.get(sym)
            if img:
                fit_sz = int(85 * scale)
                cache_key = (sym, fit_sz, fit_sz)
                if cache_key not in self._symbols_cache:
                    fit = min(fit_sz/img.get_width(), fit_sz/img.get_height())
                    self._symbols_cache[cache_key] = pygame.transform.smoothscale(img, (int(img.get_width()*fit), int(img.get_height()*fit)))
                s_img = self._symbols_cache[cache_key]
                self.screen.blit(s_img, (rect.left + 20*scale, rect.centery - s_img.get_height()//2))
            
            val_text = "JACKPOT" if sym == "shiny_star" else f"x{mult}"
            v_surf = f_val.render(val_text, True, (255, 255, 255))
            self.screen.blit(v_surf, (rect.right - v_surf.get_width() - 25*scale, rect.centery - v_surf.get_height()//2))
            if sym == "shiny_star":
                ex = f_lbl.render("+10 FREE SPINS", True, (255, 215, 0))
                self.screen.blit(ex, (rect.right - ex.get_width() - 25*scale, rect.centery + 22*scale))

        self._draw_text_centered("Clicca ovunque per tornare al gioco", self._font("Arial", 22*scale), (sw//2, sh - 60*scale), (140, 140, 150))

    def finish_game(self):
        total_win = int(self.credits - INITIAL_CREDITS)
        results = {
            "success": total_win > 0,
            "score": total_win if total_win > 0 else 0,
            "final_credits": self.credits,
            "won_jackpot": self.progressive_jackpot == 50000.0 and self.last_win > 10000,
            "total_win": total_win
        }
        self.finish(results)

