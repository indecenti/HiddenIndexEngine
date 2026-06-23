import pygame
import random
import math
import logging
import json
from typing import List, Dict, Any, Tuple
from pathlib import Path

from engine.minigames.minigame_base import BaseMinigame
from engine.utils import get_resource_path

def _clamp(val, min_v, max_v):
    return max(min_v, min(max_v, val))

class SpotDifferencesGame(BaseMinigame):
    """
    Minigioco 'Trova le Differenze'.
    Posiziona oggetti identici in due pannelli, nascondendone 5 a destra.
    """
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.logger = logging.getLogger("SpotDifferences")
        # Carica le traduzioni locali
        strings_path = get_resource_path("engine", "minigames", "spot_differences", "strings")
        self.load_local_strings(strings_path)
        
        # Stato di gioco persistente tra livelli
        self.current_score = 0
        self.total_score = 0
        self.level = 1
        # Legge max_levels dai parametri dell'editor o default a 5
        self.max_levels = int(self.params.get("max_levels", 5))
        self.won_all = False
        
        # Parametri di difficoltà iniziali
        self.num_total_objects = 50
        self.num_differences = 6
        self.time_limit = 120
        self.time_left = self.time_limit
        
        # Feedback visivo avanzato
        self.wrong_click_timer = 0
        self.wrong_click_pos = (0, 0)
        self.pulse_timer = 0
        self.particles = []
        self.screen_shake = 0
        self.victory_timer = 0
        
        # Inizializzazione Suoni (Casino Style)
        self.sounds = {}
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init()
            s_path = get_resource_path("engine", "assets", "sounds")
            for s_name, f_name in [("hit", "bling1.mp3"), ("error", "error4.mp3"), ("win", "victory.mp3"), ("level", "level_up.mp3")]:
                f_path = s_path / f_name
                if f_path.exists():
                    self.sounds[s_name] = pygame.mixer.Sound(str(f_path))
                    self.sounds[s_name].set_volume(0.5)
            
            # Suono di palpitazione/tick per l'ansia
            p_tick = get_resource_path("engine", "minigames", "asteroids", "assets", "sounds", "beat1.wav")
            if p_tick.exists():
                self.sounds["tick"] = pygame.mixer.Sound(str(p_tick))
                self.sounds["tick"].set_volume(0.8)
        except Exception as e:
            self.logger.warning(f"Audio init failed: {e}")

        self.last_tick_time = 0

        # Caricamento Asset e Cataloghi (Stili)
        self.style_pools = {"cartoon": [], "real": [], "line art": []}
        self.tags_map = {}
        self._load_catalogs()
        
        # Scegli lo stile della sessione (Cura estetica: coerenza di stile)
        valid_styles = [s for s, p in self.style_pools.items() if len(p) >= 30]
        self.chosen_style = random.choice(valid_styles) if valid_styles else "cartoon"
        self.logger.info(f"Stile sessione scelto: {self.chosen_style} ({len(self.style_pools[self.chosen_style])} oggetti)")
        
        # Temi Casino / Arcade (Scuri e profondi)
        self.themes = [
            {
                "name": "Vegas Gold",
                "bg": (15, 5, 30),         # Viola profondo
                "panel_bg": (45, 15, 75),  # Viola scuro
                "hud_bg": (255, 215, 0)    # Oro vibrante
            },
            {
                "name": "Feltro Verde",
                "bg": (5, 25, 10),         # Verde abisso
                "panel_bg": (15, 65, 25),  # Verde biliardo scuro
                "hud_bg": (218, 165, 32)   # Bronzo/Oro scuro
            },
            {
                "name": "Neon Slot",
                "bg": (10, 10, 15),        # Quasi nero
                "panel_bg": (20, 20, 40),  # Blu notte
                "hud_bg": (0, 250, 154)    # Verde fluo
            }
        ]
        self.ui_theme = random.choice(self.themes)
        self.logger.info(f"Tema visuale scelto: {self.ui_theme['name']}")
        
        # Gestione Deck Asset (No Ripetizioni)
        self.deck_small = []
        self.deck_other = []

        self.game_over = False
        self.objects_to_draw = []
        self.differences_indices = []
        self.found_indices = {} # Indice -> Tempo di animazione
        
        # Feedback UX
        self.combo = 0
        self.combo_timer = 0
        self.last_hit_msg = ""
        self.last_hit_timer = 0
        self.wrong_clicks = 0
        
        # Viewport (Safe Area sync with ScalingManager)
        sw, sh = self.scaling_manager.screen_w, self.scaling_manager.screen_h
        ox, oy = self.scaling_manager.offset_x, self.scaling_manager.offset_y
        
        # Area utile per il gioco (senza letterbox)
        self.panel_width = (sw - ox * 2) // 2
        self.panel_height = (sh - oy * 2) - 120 # Spazio maggiorato per non sovrapporsi alla HUD
        self.object_base_size = 65 
        
        self._setup_level()
        
    def _load_catalogs(self) -> None:
        """Carica i cataloghi per raggruppare oggetti per stile e tag."""
        catalog_files = [
            "global_cartoon_catalog.json", 
            "global_real_catalog.json", 
            "global_lineart_catalog.json"
        ]
        
        for cat_name in catalog_files:
            try:
                cp = get_resource_path("engine", "data", cat_name)
                if cp.exists():
                    with open(cp, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        for obj in data.get("objects", []):
                            style = obj.get("style", "cartoon").lower()
                            # Normalizza nomi stili
                            if style == "line art": style = "line art"
                            elif style == "real": style = "real"
                            else: style = "cartoon"
                            
                            icon_path = obj.get("icon")
                            if icon_path:
                                full_path = get_resource_path("engine", "assets", icon_path)
                                if full_path.exists():
                                    self.style_pools[style].append(full_path)
                                    self.tags_map[full_path.stem] = [t.lower() for t in obj.get("tags", [])]
            except Exception as e:
                self.logger.warning(f"Errore caricamento catalogo {cat_name}: {e}")

    def start(self) -> None:
        """Avvio del gioco dal livello 1."""
        self.level = 1
        self.total_score = 0
        self.won_all = False
        self.game_over = False
        self._setup_level()

    def _setup_level(self) -> None:
        """Popola il livello con alta densità, sovrapposizioni naturali e differenze strategiche."""
        self.objects_to_draw = []
        self.differences_indices = []
        self.found_indices = {}
        self.game_over = False
        self.wrong_click_timer = 0
        self.particles = []
        self.victory_timer = 0
        self.screen_shake = 0
        
        # Difficoltà progressiva (Parti da 63 oggetti)
        level_scale = (self.level - 1) / max(1, self.max_levels - 1)
        self.num_total_objects = 63 + int(85 * level_scale) 
        self.num_differences = 6 + int(9 * level_scale)
        self.time_left = max(30, self.time_limit * (1.0 - level_scale * 0.45))
        
        pool = self.style_pools.get(self.chosen_style, [])
        if not pool:
            pool = [p for sub in self.style_pools.values() for p in sub]
            
        if not pool:
            self.logger.error("Nessun oggetto trovato nei cataloghi!")
            self.finish({"success": False, "score": 0})
            return

        # Deck System per evitare ripetizioni
        if not self.deck_small or not self.deck_other:
            all_small = [p for p in pool if "piccolo" in self.tags_map.get(p.stem, [])]
            all_other = [p for p in pool if p not in all_small]
            
            # Se la suddivisione è povera, mischia tutto
            if len(all_small) < 20:
                all_small = pool[:]
            if len(all_other) < 20:
                all_other = pool[:]
                
            random.shuffle(all_small)
            random.shuffle(all_other)
            self.deck_small = all_small
            self.deck_other = all_other

        # Assicurati di pescare TANTISSIMI oggetti piccoli per poterli usare come differenze ben distanziate
        num_small_target = min(len(self.deck_small), self.num_differences * 4 + 15)
        num_others_target = min(len(self.deck_other), self.num_total_objects)
        
        selected_assets = []
        
        # Pescaggio dal deck piccolo
        for _ in range(num_small_target):
            if not self.deck_small: break
            selected_assets.append(self.deck_small.pop())
            
        # Pescaggio dal deck grande
        for _ in range(num_others_target):
            if not self.deck_other: break
            selected_assets.append(self.deck_other.pop())

        # Se servono ancora oggetti, aggiungi duplicati casuali dal pool generale
        while len(selected_assets) < self.num_total_objects + 10:
            selected_assets.append(random.choice(pool))
            
        random.shuffle(selected_assets)
        
        placed_rects: List[pygame.Rect] = []
        base_size = self.object_base_size * self.scaling_manager.scale
        
        # Quadranti per bilanciamento densità (Dettaglio Algoritmo)
        quadrants = [
            (15, 15, self.panel_width//2, self.panel_height//2), # TL
            (self.panel_width//2, 15, self.panel_width-15, self.panel_height//2), # TR
            (15, self.panel_height//2, self.panel_width//2, self.panel_height-25), # BL
            (self.panel_width//2, self.panel_height//2, self.panel_width-15, self.panel_height-25) # BR
        ]
        quad_idx = 0
        
        # Algoritmo di posizionamento evoluto
        for pass_num in [1, 2]:
            for asset_path in selected_assets[:]:
                if len(self.objects_to_draw) >= self.num_total_objects: break
                
                is_small = "piccolo" in self.tags_map.get(asset_path.stem, [])
                if pass_num == 1 and is_small: continue 
                if pass_num == 2 and not is_small: continue 
                
                try:
                    img = pygame.image.load(str(asset_path)).convert_alpha()
                    # VARIETÀ: Flipping orizzontale casuale (Dettaglio estetico)
                    if random.random() > 0.5:
                        img = pygame.transform.flip(img, True, False)
                        
                    orig_w, orig_h = img.get_size()
                    
                    tag_mult = 1.0
                    a_id = asset_path.stem
                    tags = self.tags_map.get(a_id, [])
                    
                    # Cura delle proporzioni: gli oggetti piccoli sono disegnati piccoli ma sempre diversi
                    if "grande" in tags: tag_mult *= 1.15
                    if "piccolo" in tags: tag_mult *= random.uniform(0.45, 0.80) 
                    if "lungo" in tags or "largo" in tags: tag_mult *= 0.90
                    
                    # Applica il moltiplicatore base in base al pass (piccoli in pass 2)
                    size_mult = (random.uniform(0.9, 1.2) if pass_num == 1 else random.uniform(0.7, 1.1)) * tag_mult
                    scale_factor = (base_size / max(orig_w, orig_h)) * size_mult
                    new_w, new_h = int(round(orig_w * scale_factor)), int(round(orig_h * scale_factor))
                    
                    new_w = _clamp(new_w, 20, int(self.panel_width * 0.70))
                    new_h = _clamp(new_h, 20, int(self.panel_height * 0.70))
                    
                    img = pygame.transform.smoothscale(img, (new_w, new_h))
                    
                    # Bilanciamento per quadranti: prova a piazzare nel quadrante corrente
                    found_pos = False
                    attempts = 200
                    for _ in range(attempts):
                        q = quadrants[quad_idx % 4]
                        x = random.randint(q[0], max(q[0]+1, q[2] - new_w))
                        y = random.randint(q[1], max(q[1]+1, q[3] - new_h))
                        
                        new_rect = pygame.Rect(x, y, new_w, new_h)
                        
                        collision_margin = -15 if is_small else -5
                        if not any(new_rect.inflate(collision_margin, collision_margin).colliderect(r.inflate(collision_margin, collision_margin)) for r in placed_rects):
                            placed_rects.append(new_rect)
                            self.objects_to_draw.append({
                                "img": img,
                                "rect": new_rect,
                                "angle": random.randint(-25, 25),
                                "z_order": pass_num,
                                "is_small": is_small,
                                "asset_id": a_id
                            })
                            selected_assets.remove(asset_path)
                            quad_idx += 1 # Passa al prossimo quadrante
                            found_pos = True
                            break
                        # Se fallisce, prova random in tutto il pannello per non bloccarsi
                        elif _ > 100:
                            x = random.randint(15, self.panel_width - new_w - 15)
                            y = random.randint(15, self.panel_height - new_h - 25)
                            new_rect = pygame.Rect(x, y, new_w, new_h)
                            if not any(new_rect.inflate(collision_margin, collision_margin).colliderect(r.inflate(collision_margin, collision_margin)) for r in placed_rects):
                                placed_rects.append(new_rect)
                                self.objects_to_draw.append({
                                    "img": img, "rect": new_rect, "angle": random.randint(-25, 25),
                                    "z_order": pass_num, "is_small": is_small, "asset_id": a_id
                                })
                                selected_assets.remove(asset_path)
                                found_pos = True
                                break
                except Exception:
                    if asset_path in selected_assets: selected_assets.remove(asset_path)
                except Exception as e:
                    if asset_path in selected_assets: selected_assets.remove(asset_path)

        # SELEZIONE DIFFERENZE EVOLUTA e DISTANZIATA:
        # Nascondiamo oggetti piccoli dando priorità, MA assicurandoci che non siano vicini tra loro
        # per non creare "buchi" vuoti enormi nel pannello di destra.
        diff_count = min(self.num_differences, len(self.objects_to_draw))
        self.differences_indices = []
        
        small_indices = [i for i, o in enumerate(self.objects_to_draw) if o.get("is_small")]
        other_indices = [i for i, o in enumerate(self.objects_to_draw) if not o.get("is_small")]
        
        random.shuffle(small_indices)
        random.shuffle(other_indices)
        
        # Uniamo le liste dando sempre la precedenza ASSOLUTA ai piccoli
        candidates = small_indices + other_indices
        
        # Distanza minima garantita tra le differenze
        min_distance = 180 * self.scaling_manager.scale
        
        for idx in candidates:
            if len(self.differences_indices) >= diff_count:
                break
                
            obj_rect = self.objects_to_draw[idx]["rect"]
            cx, cy = obj_rect.center
            
            # Controlla la distanza da tutte le differenze già confermate
            too_close = False
            for sel_idx in self.differences_indices:
                sel_rect = self.objects_to_draw[sel_idx]["rect"]
                sx, sy = sel_rect.center
                dist = math.hypot(cx - sx, cy - sy)
                if dist < min_distance:
                    too_close = True
                    break
                    
            if not too_close:
                self.differences_indices.append(idx)
                
        # Fallback di sicurezza: se la regola spaziale è stata troppo severa, completiamo forzatamente
        if len(self.differences_indices) < diff_count:
            missing = diff_count - len(self.differences_indices)
            remaining_c = [i for i in candidates if i not in self.differences_indices]
            self.differences_indices.extend(remaining_c[:missing])

    def handle_event(self, event: pygame.event.Event) -> None:
        if self.game_over:
            if event.type == pygame.MOUSEBUTTONDOWN:
                if self.won_all or self.time_left <= 0:
                    self.finish({"success": self.won_all, "score": self.total_score})
                else:
                    # Passa al prossimo livello
                    self.level += 1
                    if "level" in self.sounds:
                        self.sounds["level"].play()
                        
                    if self.level > self.max_levels:
                        # Vittoria finale raggiunta
                        self.level = self.max_levels # Mantieni il numero corretto per la HUD
                        self.won_all = True
                        if "win" in self.sounds:
                            self.sounds["win"].play()
                    else:
                        self._setup_level()
                        self.game_over = False
            return

        if event.type == pygame.MOUSEBUTTONDOWN:
            mouse_pos = event.pos
            check_pos = list(mouse_pos)
            is_right_panel = mouse_pos[0] >= (self.panel_width + self.scaling_manager.offset_x)
            if is_right_panel: check_pos[0] -= (self.panel_width + self.scaling_manager.offset_x)
            else: check_pos[0] -= self.scaling_manager.offset_x
            check_pos[1] -= self.scaling_manager.offset_y
            
            hit = False
            for idx in self.differences_indices:
                if idx in self.found_indices: continue
                obj = self.objects_to_draw[idx]
                if obj["rect"].collidepoint(check_pos):
                    self.found_indices[idx] = 1.0 
                    if "hit" in self.sounds:
                        # Pitch vario per stile casino
                        snd = self.sounds["hit"]
                        snd.play()
                    
                    # Gestione Combo (Cura dell'esperienza)
                    points = 500
                    if self.combo_timer > 0:
                        self.combo += 1
                        multiplier = 1.0 + (self.combo * 0.5)
                        points = int(points * multiplier)
                        self.last_hit_msg = f"COMBO X{multiplier}!"
                    else:
                        self.combo = 0
                        self.last_hit_msg = "+500"
                    
                    self.combo_timer = 4.0 # 4 secondi per concatenare
                    self.last_hit_timer = 1.5
                    self.current_score += points
                    self.total_score += points
                    hit = True
                    
                    if len(self.found_indices) == len(self.differences_indices):
                        # Livello completato (Animazione Gratificante)
                        self.total_score += int(self.time_left * 50) 
                        self.game_over = True
                        self.victory_timer = 2.0
                        self.screen_shake = 20.0
                        self._spawn_confetti(mouse_pos)
                        if "win" in self.sounds:
                            self.sounds["win"].play()
                    break
            
            if not hit:
                self.wrong_clicks += 1
                self.combo = 0
                self.combo_timer = 0
                self.wrong_click_timer = 0.6 # Feedback visivo "X"
                self.wrong_click_pos = mouse_pos
                self.screen_shake = 8.0 # Shake sull'errore
                if "error" in self.sounds:
                    self.sounds["error"].play()
                self.current_score = max(0, self.current_score - 150)
                self.total_score = max(0, self.total_score - 150)

    def update(self, dt: float) -> None:
        """Aggiorna countdown e animazioni."""
        if not self.game_over:
            self.time_left -= dt
            
            # Effetto Ansia/Palpitazioni negli ultimi 10 secondi (Entra prima e accelera)
            if 0 < self.time_left <= 10.0:
                freq = 1.0 + ((10.0 - self.time_left) / 10.0) * 4.0 # Da 1 a 5 battiti al secondo
                self.last_tick_time += dt * freq
                if self.last_tick_time >= 1.0:
                    self.last_tick_time -= 1.0
                    if "tick" in self.sounds:
                        self.sounds["tick"].play()
                    self.screen_shake = 5.0 + (10.0 - self.time_left) # Da 5 a 15 intensità
                    
            if self.time_left <= 0:
                self.time_left = 0
                self.game_over = True # Tempo scaduto
                self.victory_timer = 0.0 # Usato come contatore per l'overlay Game Over
                if "error" in self.sounds:
                    self.sounds["error"].play()
                self.screen_shake = 10.0 # Botta finale esplosiva
                self._spawn_explosion(self.scaling_manager.screen_w // 2, self.scaling_manager.screen_h // 2)
                
        if self.combo_timer > 0: self.combo_timer -= dt
        if self.last_hit_timer > 0: self.last_hit_timer -= dt
        if self.wrong_click_timer > 0: self.wrong_click_timer -= dt
        if self.screen_shake > 0: self.screen_shake -= dt * 30
        
        # victory_timer usato sia in discesa (vittoria) che in salita (gameover)
        if self.game_over and self.time_left <= 0:
            self.victory_timer += dt
        elif self.victory_timer > 0: 
            self.victory_timer -= dt
            
        self.pulse_timer += dt * 5 # Per animazioni pulsing
        
        # Update particles
        for p in self.particles[:]:
            p["x"] += p["vx"] * dt
            p["y"] += p["vy"] * dt
            p["vy"] += 500 * dt # Gravità
            p["life"] -= dt
            if p["life"] <= 0: self.particles.remove(p)

        for idx in list(self.found_indices.keys()):
            if self.found_indices[idx] > 0:
                self.found_indices[idx] -= dt
                if self.found_indices[idx] < 0: self.found_indices[idx] = 0

    def _spawn_confetti(self, pos: Tuple[int, int]) -> None:
        """Crea coriandoli e stelle stile fumetto esplosivo."""
        colors = [(255, 50, 50), (50, 255, 50), (50, 50, 255), (255, 255, 50), (255, 100, 200)]
        for _ in range(100):
            angle = random.uniform(0, math.pi * 2)
            speed = random.uniform(300, 800)
            self.particles.append({
                "x": pos[0], "y": pos[1],
                "vx": math.cos(angle) * speed,
                "vy": math.sin(angle) * speed,
                "color": random.choice(colors),
                "life": random.uniform(1.0, 2.5),
                "size": random.randint(8, 18),
                "type": random.choice(["comic_sq", "star"])
            })

    def _spawn_explosion(self, cx: int, cy: int) -> None:
        """Crea una massiccia esplosione comic per il game over."""
        colors = [(255, 50, 50), (255, 100, 0), (255, 255, 0), (200, 200, 200)]
        for _ in range(150):
            angle = random.uniform(0, math.pi * 2)
            speed = random.uniform(500, 1800)
            self.particles.append({
                "x": cx, "y": cy,
                "vx": math.cos(angle) * speed,
                "vy": math.sin(angle) * speed,
                "color": random.choice(colors),
                "life": random.uniform(1.0, 3.0),
                "size": random.randint(20, 60),
                "type": random.choice(["comic_sq", "star", "boom_cloud"])
            })

    def on_resize(self) -> None:
        """Sincronizza le dimensioni dei pannelli al cambio risoluzione rispettando i margini."""
        sw, sh = self.scaling_manager.screen_w, self.scaling_manager.screen_h
        ox, oy = self.scaling_manager.offset_x, self.scaling_manager.offset_y
        self.panel_width = (sw - ox * 2) // 2
        self.panel_height = (sh - oy * 2) - 120 # Spazio maggiorato per non sovrapporsi alla HUD
        # Gli oggetti non vengono riposizionati per evitare di rompere la partita in corso,
        # ma i nuovi limiti verranno usati al prossimo update/draw.

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

    def _outline_surface(self, text: str, font: pygame.font.Font, color: tuple,
                         outline_color: tuple, thickness: int) -> pygame.Surface:
        """Compone testo + bordo spesso UNA volta su una surface trasparente e
        la cacha. Evita di ri-renderizzare il font e di blittarlo NxN volte ogni
        frame (il loop di outline costa fino a ~113 blit/frame con thickness 6).
        Il risultato e' una singola Surface composita gia' convertita."""
        if not hasattr(self, "_outline_cache"):
            self._outline_cache = {}
        # La chiave include l'identita' del font (id) oltre all'altezza per
        # evitare collisioni tra font diversi con la stessa get_height().
        key = (text, id(font), font.get_height(), color, outline_color, thickness)
        surf = self._outline_cache.get(key)
        if surf is None:
            base = font.render(text, True, color)
            out = font.render(text, True, outline_color)
            w, h = base.get_size()
            pad = thickness
            comp = pygame.Surface((w + pad * 2, h + pad * 2), pygame.SRCALPHA)
            for dx in range(-thickness, thickness + 1):
                for dy in range(-thickness, thickness + 1):
                    if dx * dx + dy * dy <= thickness * thickness:
                        comp.blit(out, (pad + dx, pad + dy))
            comp.blit(base, (pad, pad))
            surf = comp.convert_alpha()
            self._outline_cache[key] = surf
        return surf

    def draw(self) -> None:
        # Screen Shake (Cura UX)
        draw_offset_x = 0
        draw_offset_y = 0
        if self.screen_shake > 0:
            draw_offset_x = random.randint(-int(self.screen_shake), int(self.screen_shake))
            draw_offset_y = random.randint(-int(self.screen_shake), int(self.screen_shake))
            
        # Sfondo neutro
        self.screen.fill(self.ui_theme["bg"]) 
        
        ox, oy = self.scaling_manager.offset_x + draw_offset_x, self.scaling_manager.offset_y + draw_offset_y
        
        # Un singolo grande pannello unificato
        big_panel = pygame.Rect(ox+5, oy+5, (self.panel_width * 2) - 10, self.panel_height-10)

        # Sfondo pannello chiaro
        pygame.draw.rect(self.screen, self.ui_theme["panel_bg"], big_panel)
        
        # Bordo NERO sottile
        pygame.draw.rect(self.screen, (0, 0, 0), big_panel, 3)

        # Singola linea verticale nera divisoria
        pygame.draw.line(self.screen, (0, 0, 0), (ox + self.panel_width, oy+5), (ox + self.panel_width, oy+self.panel_height-5), 3)
        
        # Disegna oggetti - Lato Sinistro
        for i, obj in enumerate(self.objects_to_draw):
            self._draw_animated_obj(obj, i, is_right=False)

        # Disegna oggetti - Lato Destro
        # Lookup via set (O(1)) invece di scansione di lista per ogni oggetto
        # ogni frame; semantica identica, la lista resta intatta per la logica.
        diff_set = frozenset(self.differences_indices)
        for i, obj in enumerate(self.objects_to_draw):
            if i in diff_set:
                if i in self.found_indices:
                    self._draw_animated_obj(obj, i, is_right=True)
            else:
                self._draw_animated_obj(obj, i, is_right=True)

        # HUD e Feedback Combo (Dettaglio UX)
        # Disegna Particelle Comic
        for p in self.particles:
            color = p["color"]
            x, y, s = int(p["x"]), int(p["y"]), p["size"]
            if p["type"] == "comic_sq":
                # Quadrato spesso
                pygame.draw.rect(self.screen, (0, 0, 0), (x-2, y-2, s+4, s+4))
                pygame.draw.rect(self.screen, color, (x, y, s, s))
            elif p["type"] == "boom_cloud":
                # Nuvola rotonda
                pygame.draw.circle(self.screen, (0,0,0), (x, y), s + 4)
                pygame.draw.circle(self.screen, color, (x, y), s)
            else:
                # Piccolo triangolo/stella
                pts = [(x, y-s), (x+s//2, y+s//2), (x-s//2, y+s//2)]
                pygame.draw.polygon(self.screen, (0,0,0), pts, 4)
                pygame.draw.polygon(self.screen, color, pts)

        self._draw_hud()
        
        # Overlay Fine Partita
        if self.game_over:
            if len(self.found_indices) == len(self.differences_indices):
                self._draw_victory_overlay()
            elif self.time_left <= 0:
                self._draw_gameover_overlay()

    def _draw_gameover_overlay(self) -> None:
        """Disegna la schermata di Game Over in stile fumetto con il punteggio finale."""
        font_v = self._font("Impact", 110*self.scaling_manager.scale)
        font_sub = self._font("Impact", 40*self.scaling_manager.scale)
        
        # Sfondo semitrasparente per far risaltare il popup.
        # Cachato: ricreare una Surface SRCALPHA fullscreen + fill ogni frame
        # costa ~10x su Android. Si rigenera solo al cambio dimensione schermo.
        size = self.screen.get_size()
        dark = getattr(self, "_dark_overlay", None)
        if dark is None or dark.get_size() != size:
            if getattr(self, "_android", False):
                # Android: il velo ha alpha COSTANTE (160 ovunque), quindi non
                # serve l'alpha per-pixel. Una Surface OPACA con set_alpha
                # (alpha per-surface) blitta molto piu' veloce della SRCALPHA
                # fullscreen sui blitter software/mobile, ed e' visivamente
                # IDENTICA (nero uniforme al 160% sul render sottostante).
                dark = pygame.Surface(size).convert()
                dark.fill((0, 0, 0))
                dark.set_alpha(160)
            else:
                # Desktop: comportamento ORIGINALE pixel-fedele (SRCALPHA).
                dark = pygame.Surface(size, pygame.SRCALPHA)
                dark.fill((0, 0, 0, 160))
                dark = dark.convert_alpha()
            self._dark_overlay = dark
        self.screen.blit(dark, (0, 0))
        
        cx, cy = self.screen.get_width() // 2, self.screen.get_height() // 2 - 40
        
        # Animazione di comparsa del box (rimbalzo)
        t = min(1.0, self.victory_timer * 3)
        scale = math.sin(t * math.pi / 2)
        
        box_w = int(600 * self.scaling_manager.scale * scale)
        box_h = int(250 * self.scaling_manager.scale * scale)
        
        if scale > 0.1:
            box_rect = pygame.Rect(0, 0, box_w, box_h)
            box_rect.center = (cx, cy)
            
            # Box stile fumetto
            pygame.draw.rect(self.screen, (0, 0, 0), box_rect.move(10, 10))
            pygame.draw.rect(self.screen, self.ui_theme["panel_bg"], box_rect)
            pygame.draw.rect(self.screen, (0, 0, 0), box_rect, 8)
            
            # Testi
            self._draw_text_with_outline("GAME OVER!", font_v, (cx, cy - 30), (255, 50, 50), (0,0,0), 6)
            self._draw_text_with_outline(f"SCORE FINALE: {self.total_score}", font_sub, (cx, cy + 60), (255, 255, 255), (0,0,0), 4)
            
            # Lampeggio clicca per continuare
            if self.victory_timer > 1.0 and math.sin(self.pulse_timer) > 0:
                self._draw_text_with_outline("CLICCA PER USCIRE", font_sub, (cx, cy + 180), (255, 255, 255), (0,0,0), 4)

    def _draw_victory_overlay(self) -> None:
        """Disegna un banner animato stile fumetto per celebrare il successo."""
        font_v = self._font("Impact", 100*self.scaling_manager.scale)
        t = max(0, 2.0 - self.victory_timer)
        # Effetto bounce comic
        scale = min(1.0, math.sin(t * 3) * 1.2) if t < 0.5 else 1.0
        
        msg = "PERFECT!!!" if self.wrong_clicks == 0 else "WINNER!"
        color = (255, 255, 255) # Bianco acceso per staccare dal pannello
        
        self._draw_text_with_outline(msg, font_v, (self.screen.get_width()//2, self.screen.get_height()//2 - 50), color, (0,0,0), 6)
        
        if self.last_hit_timer > 0:
            alpha = int(min(1.0, self.last_hit_timer) * 255)
            font_combo = self._font("Arial", 38*self.scaling_manager.scale, bold=True)
            combo_surf = font_combo.render(self.last_hit_msg, True, (255, 255, 0))
            combo_surf.set_alpha(alpha)
            self.screen.blit(combo_surf, (self.screen.get_width()//2 - combo_surf.get_width()//2, 80))

    def _draw_animated_obj(self, obj: Dict[str, Any], idx: int, is_right: bool) -> None:
        """Renderizza oggetto con ombre e animazioni (Cura estetica)."""
        img = obj["img"]
        rect = obj["rect"]
        angle = obj.get("angle", 0)
        ox, oy = self.scaling_manager.offset_x, self.scaling_manager.offset_y
        
        # Applica offset globale per stare nell'area visibile
        draw_rect = rect.move(ox, oy)
        if is_right:
            draw_rect = draw_rect.move(self.panel_width, 0)
            
        # Animazione di "trovato"
        scale = 1.0
        if idx in self.found_indices and self.found_indices[idx] > 0:
            t = 1.0 - self.found_indices[idx]
            scale = 1.0 + 0.3 * (1.0 - abs(t - 0.5) * 2) 
            
        # Disegna Oggetto
        if scale != 1.0:
            # Animazione "trovato" in corso (pochi oggetti, breve): rotozoom live.
            scaled_img = pygame.transform.rotozoom(img, angle, scale)
            new_rect = scaled_img.get_rect(center=draw_rect.center)
            self.screen.blit(scaled_img, new_rect)
        elif angle != 0:
            # L'angolo e' costante per oggetto: la rotazione e' identica ogni
            # frame. Cachala una volta (rotozoom per-frame su 100+ oggetti x 2
            # pannelli era il killer FPS principale su Android).
            rot = obj.get("_rot_img")
            if rot is None:
                rot = pygame.transform.rotozoom(img, angle, 1.0).convert_alpha()
                obj["_rot_img"] = rot
            new_rect = rot.get_rect(center=draw_rect.center)
            self.screen.blit(rot, new_rect)
        else:
            self.screen.blit(img, draw_rect)
            
        # Feedback cerchio se trovato (Comic Style)
        if idx in self.found_indices:
            pulse = math.sin(self.pulse_timer) * 6
            center = draw_rect.center
            radius = int(max(draw_rect.width, draw_rect.height) // 2 * scale) + 10 + int(pulse)
            # Doppio bordo stile adesivo
            pygame.draw.circle(self.screen, (0, 0, 0), center, radius + 2, 4)
            pygame.draw.circle(self.screen, (255, 255, 255), center, radius, 3)
            pygame.draw.circle(self.screen, (50, 255, 50), center, radius - 2, 2)
            
            # Comic "POP" starburst al primo istante
            if self.found_indices[idx] > 0.8:
                self._draw_starburst(center, radius * 1.8)

    def _draw_starburst(self, center: Tuple[int, int], size: float):
        """Disegna una stella gialla stile fumetto (BOOM!) con bordi spessi."""
        pts = []
        for i in range(14):
            ang = i * (math.pi * 2 / 14)
            dist = size if i % 2 == 0 else size * 0.4
            pts.append((center[0] + math.cos(ang) * dist, center[1] + math.sin(ang) * dist))
        # Bordo esterno spesso
        pygame.draw.polygon(self.screen, (0, 0, 0), pts, 10)
        pygame.draw.polygon(self.screen, (255, 255, 0), pts)
        # Bordo interno arancione
        pygame.draw.polygon(self.screen, (255, 100, 0), pts, 3)

    def _draw_hud(self) -> None:
        """Disegna la HUD con margini di sicurezza estremi (Safe Area) e stile Comic."""
        ox, oy = self.scaling_manager.offset_x, self.scaling_manager.offset_y
        sh = self.scaling_manager.screen_h
        
        hud_h = 85
        hud_y = sh - oy - hud_h - 15 
        
        hud_rect = pygame.Rect(ox + 20, hud_y, self.panel_width * 2 - 40, hud_h)
        
        # Sfondo HUD luminoso stile fumetto
        pygame.draw.rect(self.screen, self.ui_theme["hud_bg"], hud_rect, border_radius=15)
        # Bordo NERO sottile
        pygame.draw.rect(self.screen, (0, 0, 0), hud_rect, 3, border_radius=15)
        
        # Feedback errore "X" 
        if self.wrong_click_timer > 0:
            cx, cy = self.wrong_click_pos
            color = (255, 50, 50)
            # Croce con bordo nero
            for off in [(-2,-2), (2,-2), (-2,2), (2,2)]:
                pygame.draw.line(self.screen, (0,0,0), (cx-32+off[0], cy-32+off[1]), (cx+32+off[0], cy+32+off[1]), 8)
                pygame.draw.line(self.screen, (0,0,0), (cx+32+off[0], cy-32+off[1]), (cx-32+off[0], cy+32+off[1]), 8)
            pygame.draw.line(self.screen, color, (cx-30, cy-30), (cx+30, cy+30), 4)
            pygame.draw.line(self.screen, color, (cx+30, cy-30), (cx-30, cy+30), 4)
        
        font_main = self._font("Impact", 28*self.scaling_manager.scale)
        font_time = self._font("Impact", 32*self.scaling_manager.scale)
        
        # Parametri di posizionamento simmetrici e ultra-sicuri
        # Usiamo un margine fisso di 220px dagli estremi della safe area
        margin_x = 220 * self.scaling_manager.scale
        text_y = hud_y + hud_h // 2
        
        # Area sicura orizzontale
        safe_left = ox + margin_x
        safe_right = (ox + self.panel_width * 2) - margin_x
        msg_center_x = ox + self.panel_width
        
        if not self.game_over:
            remaining = len(self.differences_indices) - len(self.found_indices)
            msg = f"LIV {self.level}/{self.max_levels} - RIMANENTI: {remaining}"
            color = (255, 255, 255) # Bianco per massima leggibilità
        elif self.time_left <= 0:
            msg = "K.O. - TEMPO SCADUTO!"
            color = (255, 50, 50)
        elif self.won_all:
            msg = "SUPER CAMPIONE!"
            color = (255, 255, 0)
        else:
            msg = "LIVELLO COMPLETATO!"
            color = (50, 255, 100)
            
        # 1. Messaggio Centrale
        self._draw_text_with_outline(msg, font_main, (msg_center_x, text_y), color, (0,0,0), 3)
        
        # 2. Tempo (Simmetrico a Destra) con Ingrandimento Dinamico
        time_color = (255, 255, 255) if self.time_left > 10 else (255, 50, 50)
        time_str = f"{int(self.time_left // 60):02}:{int(self.time_left % 60):02}"
        
        zoom = 1.0
        if 0 < self.time_left <= 10.0 and not self.game_over:
            # Pulsazione battito: accelera e si ingrandisce man mano che si arriva a 0
            pulse = abs(math.sin(self.time_left * math.pi * 3))
            zoom = 1.0 + (pulse * 0.8 * ((10.0 - self.time_left) / 10.0))
            
        self._draw_zoomed_text_with_outline(time_str, font_time, (safe_right, text_y), time_color, (0,0,0), 3, zoom)
        
        # 3. Punteggio (Simmetrico a Sinistra)
        self._draw_text_with_outline(f"SCORE: {self.total_score}", font_main, (safe_left, text_y), (255, 255, 255), (0,0,0), 3)

    def _draw_zoomed_text_with_outline(self, text: str, font: pygame.font.Font, pos: Tuple[int, int], color: tuple, outline_color: tuple, thickness: int, zoom: float):
        """Disegna testo scalato per l'effetto ansia (timer in ultimi 10s).

        Su Android: path ottimizzato che parte dalla composita cachata
        (cache-hit per stringa) e applica UN solo scale (nearest) invece di
        2x font.render + 2x scale + loop di outline ogni frame.
        ATTENZIONE: precomporre l'outline PRIMA dello scale fa scalare anche
        lo spessore del bordo con lo zoom, quindi il bordo cambia spessore.

        Su desktop: ripristina il comportamento ORIGINALE pixel-fedele, dove
        l'outline e' blittato a offset +/-thickness DOPO lo scale, cosi' lo
        spessore del bordo resta costante in pixel-schermo (non scala con lo
        zoom ~1.8x)."""
        if getattr(self, "_android", False):
            comp = self._outline_surface(text, font, color, outline_color, thickness)
            if zoom != 1.0:
                new_size = (int(comp.get_width() * zoom), int(comp.get_height() * zoom))
                comp = pygame.transform.scale(comp, new_size)
            rect = comp.get_rect(center=pos)
            self.screen.blit(comp, rect)
        else:
            # Comportamento ORIGINALE desktop: render separati, scale di
            # entrambi, poi loop di outline a offset costanti DOPO lo scale.
            surf = font.render(text, True, color)
            out_surf = font.render(text, True, outline_color)

            if zoom != 1.0:
                surf = pygame.transform.smoothscale(surf, (int(surf.get_width() * zoom), int(surf.get_height() * zoom)))
                out_surf = pygame.transform.smoothscale(out_surf, (int(out_surf.get_width() * zoom), int(out_surf.get_height() * zoom)))

            rect = surf.get_rect(center=pos)

            for dx in range(-thickness, thickness + 1):
                for dy in range(-thickness, thickness + 1):
                    if dx*dx + dy*dy <= thickness*thickness:
                        self.screen.blit(out_surf, rect.move(dx, dy))
            self.screen.blit(surf, rect)

    def _draw_text_with_outline(self, text: str, font: pygame.font.Font, pos: Tuple[int, int], color: tuple, outline_color: tuple, thickness: int):
        """Disegna testo con bordo spesso stile adesivo/fumetto.
        Usa una Surface composita cachata: identica visivamente ma blitta UNA
        sola surface invece di renderizzare il font NxN volte ogni frame."""
        comp = self._outline_surface(text, font, color, outline_color, thickness)
        rect = comp.get_rect(center=pos)
        self.screen.blit(comp, rect)
