import pygame
import random
import time
from typing import Dict, Any, List, Tuple, Optional
from engine.minigames.minigame_base import BaseMinigame
from engine.utils import get_resource_path, is_android_runtime

# Flag runtime Android: su SDL2/ARM le op care (font.render ripetuti, SRCALPHA
# a tutto schermo, chrome ridisegnato con decine di pygame.draw ogni frame)
# affondano gli FPS. Si usa per gateare gli FX e scegliere il path veloce.
_ANDROID = is_android_runtime()

# Colori Stile Fumetto
DARK_BGS = [
    (25, 35, 55),    # Dark Navy
    (45, 25, 55),    # Deep Purple
    (25, 50, 35),    # Forest Green
    (60, 25, 25),    # Deep Crimson
    (40, 40, 45)     # Dark Slate
]
COLOR_GRID_BG = (255, 255, 255)   # Bianco puro
COLOR_LINE_THICK = (20, 20, 20)   # Quasi nero
COLOR_LINE_THIN = (60, 60, 60)    # Grigio scuro per linee interne
COLOR_TEXT_GIVEN = (20, 20, 20)   # Numeri iniziali
COLOR_TEXT_USER = (30, 100, 200)  # Numeri utente (Blu accesso)
COLOR_TEXT_ERROR = (220, 40, 40)  # Numeri sbagliati
COLOR_CELL_SEL = (255, 255, 100)  # Giallo acceso (selezione)
COLOR_BTN_BG = (240, 120, 50)     # Arancione scuro
COLOR_BTN_HOVER = (255, 160, 80)  # Arancione chiaro
COLOR_BTN_TEXT = (255, 255, 255)

class SudokuBoard:
    """Generatore e gestore di plancia Sudoku a dimensione dinamica."""
    def __init__(self, difficulty: int):
        # Progression: Liv 1 = 4x4, Liv 2 = 6x6, Liv 3+ = 9x9
        if difficulty == 1:
            self.n = 4
            self.bw, self.bh = 2, 2
        elif difficulty == 2:
            self.n = 6
            self.bw, self.bh = 3, 2
        else:
            self.n = 9
            self.bw, self.bh = 3, 3
            
        self.grid = [[0 for _ in range(self.n)] for _ in range(self.n)]
        self.solution = [[0 for _ in range(self.n)] for _ in range(self.n)]
        self.fixed = [[False for _ in range(self.n)] for _ in range(self.n)]
        self.generate()
        self.apply_difficulty(difficulty)

    def generate(self):
        # Formula universale per base valida: (h*r + r//w + c) % n + 1
        for r in range(self.n):
            for c in range(self.n):
                val = (r * self.bh + r // self.bw + c) % self.n + 1
                self.solution[r][c] = val
                self.grid[r][c] = val
        
        # Shuffle numeri
        nums = list(range(1, self.n + 1))
        random.shuffle(nums)
        mapping = {i+1: nums[i] for i in range(self.n)}
        
        for r in range(self.n):
            for c in range(self.n):
                self.solution[r][c] = mapping[self.solution[r][c]]
                self.grid[r][c] = self.solution[r][c]

        # Shuffle blocchi di righe e colonne (semplificato per arcade)
        # N.B. In arcade la varietà basta data dallo shuffle numeri e rimozione
        pass

    def apply_difficulty(self, diff: int):
        # Percentuale di rimozione basata sulla dimensione
        if diff == 1:
            remove_cnt = int(self.n * self.n * 0.4) # Molto semplice
        elif diff == 2:
            remove_cnt = int(self.n * self.n * 0.5)
        else:
            remove_cnt = int(self.n * self.n * 0.6)
            
        cells = [(r, c) for r in range(self.n) for c in range(self.n)]
        random.shuffle(cells)
        for i in range(remove_cnt):
            r, c = cells[i]
            self.grid[r][c] = 0
            
        for r in range(self.n):
            for c in range(self.n):
                if self.grid[r][c] != 0:
                    self.fixed[r][c] = True

class SudokuGame(BaseMinigame):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        
        # Localizzazione
        strings_path = get_resource_path("engine", "minigames", "sudoku", "strings")
        self.load_local_strings(strings_path)
        
        # Stato Gioco configurabile dall'editor
        self.level = 1
        self.score = 0
        
        # Gestione parametri da editor (se non presente, fallback a 3)
        try:
            self.max_levels = int(self.params.get("levels", 3))
        except (ValueError, TypeError):
            self.max_levels = 3
            
        self.current_bg_color = random.choice(DARK_BGS)
        
        self.board = SudokuBoard(self.level)
        self.selected_cell: Optional[Tuple[int, int]] = None
        
        # UI & Layout (Dynamic)
        self.font_large = None
        self.font_med = None
        self.font_small = None

        # Cache di rendering (sicura su entrambe le piattaforme):
        # - _text_cache: Surface gia' renderizzate keyed da (id(font), text, color)
        # - _grid_chrome: chrome statico (linee + bordo) pre-renderizzato
        self._text_cache: Dict[Tuple[int, str, Tuple], pygame.Surface] = {}
        self._grid_chrome: Optional[pygame.Surface] = None
        self._grid_chrome_size: int = -1
        self._vignette_cache: Optional[pygame.Surface] = None
        self._vignette_alpha: int = -1

        self.grid_size = 0.0
        self.cell_size = 0.0
        self.grid_x = 0.0
        self.grid_y = 0.0
        
        self.numpad_rects: List[Tuple[pygame.Rect, int]] = []
        self.btn_clear = pygame.Rect(0, 0, 0, 0)
        self.btn_submit = pygame.Rect(0, 0, 0, 0)
        
        self.state = "PLAYING" # PLAYING, LEVEL_CLEAR, GAME_OVER, TIME_UP
        self.timer_msg = 0.0
        self.error_cells = []
        
        # Countdown System
        self.game_timer = 0.0
        self.max_time = 0.0
        self._reset_timer()
        
        # Tutorial System
        self.tutorial_step = 0 if self.level == 1 else -1
        self.tutorial_timer = 0.0
        self.tut_anim_scale = 0.0 # Per animazione pop-in
        self.tut_pulse = 0.0      # Per pulsazione celle
        
        # Feedback System
        self.info_msg = ""
        self.info_timer = 0.0
        self.shake_timer = 0.0
        self.panic_pulse = 0.0    # Per heartbeat e vignetta
        self.heartbeat_timer = 0.0 # Per gestione doppio tick audio
        
        self._calculate_layout()

    def _reset_timer(self):
        # Formula arcade: 210 - (livello * 30). Liv1=180s, Liv2=150s, Liv3=120s... (Min 60s)
        self.max_time = max(60.0, 210.0 - (self.level * 30.0))
        self.game_timer = self.max_time

    def _calculate_layout(self):
        sw, sh = self.screen.get_size()
        
        # Dynamic sizes based on screen height
        self.grid_size = sh * 0.75
        self.cell_size = self.grid_size / self.board.n
        
        # Grid Center (shifted left to fit numpad)
        self.grid_x = (sw / 2.0) - (self.grid_size / 2.0) - (sh * 0.15)
        self.grid_y = (sh / 2.0) - (self.grid_size / 2.0)
        
        # Dynamic Fonts
        f_large = int(round(self.cell_size * 0.7))
        f_med = int(round(sh * 0.04))
        f_small = int(round(sh * 0.03))
        self.font_large = pygame.font.SysFont("impact", f_large)
        self.font_med = pygame.font.SysFont("impact", f_med)
        self.font_small = pygame.font.SysFont("impact", f_small)

        # Cambiando font/dimensioni, le Surface testuali e il chrome cachati
        # non sono piu' validi: invalida tutto cosi' verra' ri-renderizzato.
        self._text_cache.clear()
        self._grid_chrome = None
        self._grid_chrome_size = -1
        
        # Numpad (a destra della griglia)
        numpad_x = self.grid_x + self.grid_size + (sh * 0.05)
        numpad_y = self.grid_y + (sh * 0.05)
        btn_s = int(round(sh * 0.09))
        gap = int(round(sh * 0.02))
        
        # Font specifico per bottoni tastierino
        f_btn = int(round(btn_s * 0.6))
        self.font_btn = pygame.font.SysFont("impact", f_btn)
        
        # Colonne dinamiche: 2 per 4x4, 3 per gli altri
        cols_n = 2 if self.board.n == 4 else 3
        
        self.numpad_rects.clear()
        for i in range(1, self.board.n + 1):
            row = (i - 1) // cols_n
            col = (i - 1) % cols_n
            bx = int(round(numpad_x + col * (btn_s + gap)))
            by = int(round(numpad_y + row * (btn_s + gap)))
            self.numpad_rects.append((pygame.Rect(bx, by, btn_s, btn_s), i))
            
        # Bottoni Extra
        btn_w = int(round(btn_s * cols_n + gap * (cols_n - 1)))
        btn_h = int(round(sh * 0.07))
        
        n_rows = (self.board.n - 1) // cols_n + 1
        clear_y = int(round(numpad_y + n_rows * (btn_s + gap)))
        self.btn_clear = pygame.Rect(int(round(numpad_x)), clear_y, btn_w, btn_h)
        
        submit_y = int(round(clear_y + btn_h + gap))
        self.btn_submit = pygame.Rect(int(round(numpad_x)), submit_y, btn_w, btn_h)

    def on_resize(self):
        self._calculate_layout()

    def start(self) -> None:
        pass

    def _check_solution(self):
        errors = []
        is_full = True
        
        for r in range(self.board.n):
            for c in range(self.board.n):
                val = self.board.grid[r][c]
                if val == 0:
                    is_full = False
                elif val != self.board.solution[r][c]:
                    errors.append((r, c))
                    
        if errors:
            self.error_cells = errors
            self.score = max(0, self.score - 50)
            self.info_msg = "ERRORI TROVATI!"
            self.info_timer = 1.5
            self.shake_timer = 0.4
            if self.audio_manager:
                self.audio_manager.play_sfx("engine/assets/sounds/error4.mp3")
        elif not is_full:
            self.info_msg = "INCOMPLETO!"
            self.info_timer = 1.0
            if self.audio_manager:
                self.audio_manager.play_sfx("engine/assets/sounds/click_Low.wav", 0.5)
        else:
            # Corretto!
            self.score += 1000 * self.level
            if self.level >= self.max_levels:
                self.state = "GAME_OVER"
                self.timer_msg = 3.0
                if self.audio_manager:
                    self.audio_manager.play_sfx("engine/assets/sounds/victory.mp3")
            else:
                self.level += 1
                self.board = SudokuBoard(self.level)
                self._calculate_layout() # Ricalcola per nuova dimensione
                self.current_bg_color = random.choice(DARK_BGS)
                self.selected_cell = None
                self.error_cells = []
                self.info_msg = "LIVELLO COMPLETATO!"
                self.info_timer = 2.0
                self._reset_timer() # Reset tempo per nuovo livello
                if self.audio_manager:
                    self.audio_manager.play_sfx("engine/assets/sounds/level_up.mp3")

    def handle_event(self, event: pygame.event.Event) -> None:
        if self.state != "PLAYING" or self.shake_timer > 0:
            return
            
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            mx, my = pygame.mouse.get_pos()
            
            # Calcolo esatto hitbox griglia (allineato al render)
            gx = int(round(self.grid_x))
            gy = int(round(self.grid_y))
            gs = int(round(self.grid_size))
            
            # Click griglia
            if gx <= mx <= gx + gs and gy <= my <= gy + gs:
                c = int((mx - gx) // (gs / self.board.n))
                r = int((my - gy) // (gs / self.board.n))
                # Clamp per sicurezza
                c = max(0, min(self.board.n - 1, c))
                r = max(0, min(self.board.n - 1, r))
                if not self.board.fixed[r][c]:
                    self.selected_cell = (r, c)
                    if self.tutorial_step == 0:
                        self.tutorial_step = 1 # Regole viste -> seleziona cella
                        self.tut_anim_scale = 0
                    elif self.tutorial_step == 1:
                        self.tutorial_step = 2 # Cella selezionata -> inserisci numero
                        self.tutorial_timer = 0
                        self.tut_anim_scale = 0 # Trigger pop-in
                        if self.audio_manager:
                            self.audio_manager.play_sfx("engine/assets/sounds/bling1.mp3", 0.5)
                    if self.audio_manager:
                        self.audio_manager.play_sfx("engine/assets/sounds/click_Low.wav", 0.7)
            
            # Click tastierino numerico
            if self.selected_cell:
                r, c = self.selected_cell
                for rect, val in self.numpad_rects:
                    if rect.collidepoint(mx, my):
                        self.board.grid[r][c] = val
                        
                        # VERIFICA ISTANTANEA
                        if val != self.board.solution[r][c]:
                            # Errore: feedback aggressivo
                            if (r, c) not in self.error_cells:
                                self.error_cells.append((r, c))
                            self.shake_timer = 0.3
                            self.score = max(0, self.score - 20)
                            if self.audio_manager:
                                self.audio_manager.play_sfx("engine/minigames/tower/sounds/error4.mp3", 0.6)
                        else:
                            # Corretto: pulizia errore e feedback positivo
                            if (r, c) in self.error_cells:
                                self.error_cells.remove((r, c))
                            
                            if self.tutorial_step == 2:
                                self.tutorial_step = 3
                                self.tutorial_timer = 5.0 # Mostra timer tutorial
                                self.tut_anim_scale = 0
                                if self.audio_manager:
                                    self.audio_manager.play_sfx("engine/assets/sounds/bling1.mp3", 0.5)
                                
                            if self.audio_manager:
                                self.audio_manager.play_sfx("engine/assets/sounds/bling5.mp3", 0.6)
                            
                            # Auto-check vittoria se la griglia è completa
                            is_full = all(all(row) for row in self.board.grid)
                            if is_full and not self.error_cells:
                                self._check_solution()
                        
                if self.btn_clear.collidepoint(mx, my):
                    self.board.grid[r][c] = 0
                    if (r, c) in self.error_cells:
                        self.error_cells.remove((r, c))
                    if self.audio_manager:
                        self.audio_manager.play_sfx("engine/assets/sounds/click_Low.wav", 0.5)
                    
            if self.btn_submit.collidepoint(mx, my):
                self._check_solution()

    def update(self, dt: float) -> None:
        if self.info_timer > 0:
            self.info_timer = max(0.0, self.info_timer - dt)
        if self.shake_timer > 0:
            self.shake_timer = max(0.0, self.shake_timer - dt)
            
        if self.tutorial_timer > 0:
            self.tutorial_timer -= dt
            if self.tutorial_timer <= 0:
                old_step = self.tutorial_step
                # Step 0 e 1 non avanzano più col timer, ma solo col click
                if self.tutorial_step in [3, 4]:
                    self.tutorial_step += 1
                    if self.tutorial_step <= 5:
                        self.tutorial_timer = 5.0
                    else:
                        self.tutorial_step = -1 # Fine
                
                if old_step != self.tutorial_step and self.tutorial_step != -1:
                    self.tut_anim_scale = 0 # Trigger pop-in
                    if self.audio_manager:
                        self.audio_manager.play_sfx("engine/assets/sounds/bling1.mp3", 0.4)
            
        # Animazioni
        self.tut_anim_scale = min(1.0, self.tut_anim_scale + dt * 5.0)
        import math
        self.tut_pulse = abs(math.sin(time.time() * 6))
            
        if self.state == "PLAYING":
            old_sec = int(self.game_timer)
            self.game_timer -= dt
            new_sec = int(self.game_timer)
            
            # Gestione Panico (< 10s)
            if self.game_timer < 10 and self.game_timer > 0:
                import math
                # Battito cardiaco: sinusoide complessa per lub-dub
                # Accelerazione: frequenza aumenta man mano che il tempo cala
                freq = 5.0 + (10.0 - self.game_timer) * 1.5
                self.panic_pulse = abs(math.sin(time.time() * freq)) * (1.1 - self.game_timer / 10.0)
                
                # Doppio Tick Audio (Heartbeat)
                self.heartbeat_timer += dt * freq
                if self.heartbeat_timer >= math.pi:
                    self.heartbeat_timer -= math.pi
                    if self.audio_manager:
                        # Lub
                        self.audio_manager.play_sfx("engine/assets/sounds/click_Low.wav", 0.5)
                        # Dub leggermente dopo (simulato con delay piccolissimo o volume diverso)
                        # Qui giochiamo sul fatto che il prossimo tick arriverà presto
            else:
                self.panic_pulse = 0.0
            
            if self.game_timer <= 0:
                self.game_timer = 0
                self.state = "TIME_UP"
                self.timer_msg = 3.0
                if self.audio_manager:
                    self.audio_manager.play_sfx("engine/assets/sounds/error4.mp3")
            
        if self.state in ["GAME_OVER", "TIME_UP"]:
            self.timer_msg -= dt
            if self.timer_msg <= 0:
                success = (self.state == "GAME_OVER")
                self.finish({"success": success, "score": self.score})

    def _text(self, text: str, font: pygame.font.Font, color: Tuple) -> pygame.Surface:
        """Surface testuale cachata: evita font.render ripetuto ogni frame
        (op tra le piu' care su ARM). Keyed da (id(font), text, color); quando
        la stringa/colore non cambiano e' un cache-hit. Sicuro su entrambe le
        piattaforme: il risultato visivo e' identico."""
        key = (id(font), text, color)
        surf = self._text_cache.get(key)
        if surf is None:
            surf = font.render(text, True, color)
            surf = surf.convert_alpha()
            self._text_cache[key] = surf
        return surf

    def _draw_text_centered(self, text: str, font: pygame.font.Font, color: Tuple, rect: pygame.Rect):
        surf = self._text(text, font, color)
        r = surf.get_rect(center=rect.center)
        self.screen.blit(surf, r)

    def _get_grid_chrome(self, gs: int) -> pygame.Surface:
        """Chrome statico della griglia (linee blocco/interne + bordo esterno)
        pre-renderizzato su una Surface trasparente e cachato. Ridisegnare
        decine di pygame.draw.line ogni frame e' un costo notevole su ARM:
        qui si ri-renderizza solo quando la dimensione (gs, dovuta allo zoom
        del panico) cambia. Sicuro su entrambe le piattaforme."""
        if self._grid_chrome is not None and self._grid_chrome_size == gs:
            return self._grid_chrome

        chrome = pygame.Surface((gs + 1, gs + 1), pygame.SRCALPHA)
        n = self.board.n
        for i in range(n + 1):
            # Orizzontali (blocchi h)
            thick = 4 if i % self.board.bh == 0 else 1
            color = COLOR_LINE_THICK if i % self.board.bh == 0 else COLOR_LINE_THIN
            ly = int(round(i * (gs / n)))
            pygame.draw.line(chrome, color, (0, ly), (gs, ly), thick)

            # Verticali (blocchi w)
            thick = 4 if i % self.board.bw == 0 else 1
            color = COLOR_LINE_THICK if i % self.board.bw == 0 else COLOR_LINE_THIN
            lx = int(round(i * (gs / n)))
            pygame.draw.line(chrome, color, (lx, 0), (lx, gs), thick)

        # Bordo esterno spesso (stile fumetto)
        pygame.draw.rect(chrome, COLOR_LINE_THICK, pygame.Rect(0, 0, gs, gs), 6)

        chrome = chrome.convert_alpha()
        self._grid_chrome = chrome
        self._grid_chrome_size = gs
        return chrome

    def _get_overlay(self, color: Tuple[int, int, int]) -> pygame.Surface:
        """Overlay opaco fullscreen cachato per (colore, dimensione schermo),
        da usare con set_alpha. Path veloce per Android: evita di ricreare e
        riempire una Surface SRCALPHA a tutto schermo ogni frame (~10x su ARM).
        Usato SOLO dietro il flag _ANDROID; il desktop resta sul path SRCALPHA."""
        if not hasattr(self, "_overlay_cache"):
            self._overlay_cache = {}
        size = self.screen.get_size()
        key = (color, size)
        surf = self._overlay_cache.get(key)
        if surf is None:
            surf = pygame.Surface(size)
            surf.fill(color)
            surf = surf.convert()
            self._overlay_cache[key] = surf
        return surf

    def _get_vignette_strips(self, sw: int, sh: int, border: int):
        """4 strisce opache (rosse) cachate per la vignetta di panico, una per
        bordo. Si ri-creano solo se cambia la firma (sw, sh, border). L'alpha
        del battito viene applicato a runtime via set_alpha sul chiamante.
        Usato SOLO dietro _ANDROID; il desktop resta sul path SRCALPHA."""
        sig = (sw, sh, border)
        if self._vignette_cache is not None and self._vignette_alpha == hash(sig):
            return self._vignette_cache

        col = (200, 0, 0)
        layout = [
            ((sw, border), (0, 0)),            # Sopra
            ((sw, border), (0, sh - border)),  # Sotto
            ((border, sh), (0, 0)),            # Sinistra
            ((border, sh), (sw - border, 0)),  # Destra
        ]
        strips = []
        for (w, h), pos in layout:
            if w <= 0 or h <= 0:
                continue
            s = pygame.Surface((w, h))
            s.fill(col)
            s = s.convert()
            strips.append((s, pos))

        self._vignette_cache = strips
        self._vignette_alpha = hash(sig)
        return strips

    def _draw_comic_tooltip(self, text: str, pos: Tuple[int, int], arrow_pos: str = "down"):
        """Disegna un tooltip in stile fumetto puntando a una posizione con animazione pop-in."""
        scale = getattr(self, "tut_anim_scale", 1.0)
        # Elastic easing
        if scale < 1.0:
            scale = -scale * (scale - 2) # Semplice quad ease out
            
        padding = 15
        lines = text.split("\n")
        # Surface per riga cachate: la stringa del tutorial e' fissa per step,
        # quindi e' un cache-hit ogni frame durante l'animazione pop-in.
        surfs = [self._text(line, self.font_small, (20, 20, 20)) for line in lines]
        
        tw = int((max(s.get_width() for s in surfs) + padding * 2) * scale)
        th = int((sum(s.get_height() for s in surfs) + padding * 2) * scale)
        
        if tw < 10 or th < 10: return # Troppo piccolo per disegnare
        
        # Posizionamento rispetto a pos
        if arrow_pos == "down":
            rx, ry = pos[0] - tw // 2, pos[1] - th - 20
        elif arrow_pos == "up":
            rx, ry = pos[0] - tw // 2, pos[1] + 20
        elif arrow_pos == "left":
            rx, ry = pos[0] + 20, pos[1] - th // 2
        else: # right
            rx, ry = pos[0] - tw - 20, pos[1] - th // 2
            
        # SAFETY CLAMP: Forza il fumetto a restare a schermo
        sw, sh = self.screen.get_size()
        rx = max(10, min(sw - tw - 10, rx))
        ry = max(10, min(sh - th - 10, ry))
            
        bubble_rect = pygame.Rect(rx, ry, tw, th)
        
        # Coordinate Coda (Triangolo) - Scalate
        off = int(12 * scale)
        h_off = int(24 * scale)
        if arrow_pos == "down":
            points = [(pos[0], pos[1]-5), (pos[0]-off, pos[1]-h_off), (pos[0]+off, pos[1]-h_off)]
        elif arrow_pos == "up":
            points = [(pos[0], pos[1]+5), (pos[0]-off, pos[1]+h_off), (pos[0]+off, pos[1]+h_off)]
        elif arrow_pos == "left":
            points = [(pos[0]+5, pos[1]), (pos[0]+h_off, pos[1]-off), (pos[0]+h_off, pos[1]+off)]
        else: # right
            points = [(pos[0]-5, pos[1]), (pos[0]-h_off, pos[1]-off), (pos[0]-h_off, pos[1]+off)]
            
        # 1. DISEGNA RIEMPIMENTO (Bolla + Coda)
        pygame.draw.rect(self.screen, (255, 255, 255), bubble_rect, border_radius=12)
        if scale > 0.5: # Disegna coda solo se abbastanza grande
            pygame.draw.polygon(self.screen, (255, 255, 255), points)
        
        # 2. DISEGNA BORDO BOLLA
        pygame.draw.rect(self.screen, (20, 20, 20), bubble_rect, 4, border_radius=12)
        
        # 3. DISEGNA BORDO CODA
        if scale > 0.5:
            pygame.draw.polygon(self.screen, (255, 255, 255), points) # Re-fill
            pygame.draw.line(self.screen, (20, 20, 20), points[0], points[1], 4)
            pygame.draw.line(self.screen, (20, 20, 20), points[0], points[2], 4)
        
        # Disegna Testo (solo se scala quasi completa)
        if scale > 0.8:
            curr_y = ry + padding
            for s in surfs:
                self.screen.blit(s, (rx + (tw - s.get_width()) // 2, curr_y))
                curr_y += s.get_height()

    def draw(self) -> None:
        self.screen.fill(self.current_bg_color)
        
        mx, my = pygame.mouse.get_pos()
        
        # Disegna UI (Score & Livello)
        txt_level = f"{self._('sudoku_level')} {self.level}/{self.max_levels}"
        txt_score = f"{self._('sudoku_score')} {self.score}"
        
        # Testo UI bianco per contrastare con gli sfondi scuri (cachato)
        surf_l = self._text(txt_level, self.font_med, (255, 255, 255))
        surf_s = self._text(txt_score, self.font_med, (255, 255, 255))
        
        sh = self.screen.get_height()
        ui_y = int(round(sh * 0.05))
        ui_x = int(round(self.screen.get_width() * 0.05))
        
        self.screen.blit(surf_l, (ui_x, ui_y))
        self.screen.blit(surf_s, (ui_x, ui_y + surf_l.get_height() + 10))
        
        # Disegna Timer (Angolo Top-Right)
        if self.state == "PLAYING":
            mins = int(self.game_timer // 60)
            secs = int(self.game_timer % 60)
            txt_timer = f"{mins:02d}:{secs:02d}"
            
            # Effetto Ansia: lampeggia rosso se < 10 secondi
            t_col = (255, 255, 255)
            tx = self.screen.get_width() - ui_x
            ty = ui_y
            panic = self.game_timer < 10

            if panic:
                import math
                pulse = abs(math.sin(time.time() * 10))
                if _ANDROID:
                    # Android: colore quantizzato (step 16) per non saturare
                    # la cache testuale con un colore diverso a ogni frame.
                    ch = (int(255 * (1 - pulse)) // 16) * 16
                    t_col = (255, ch, ch)
                else:
                    # Desktop: colore continuo originale (pixel-fedele).
                    t_col = (255, int(255 * (1 - pulse)), int(255 * (1 - pulse)))
                # Shake del timer
                tx += int(math.sin(time.time() * 50) * 4)
                ty += int(math.cos(time.time() * 45) * 2)

            if panic and not _ANDROID:
                # Desktop in panico: render diretto ogni frame (solo gli ultimi
                # 10s) per non far crescere la cache con un colore continuo
                # diverso a ogni frame. Il path normale resta cachato.
                surf_t = self.font_med.render(txt_timer, True, t_col)
            else:
                # Path normale (e Android in panico col colore quantizzato):
                # resta cachato e invariato.
                surf_t = self._text(txt_timer, self.font_med, t_col)
            tx -= surf_t.get_width()
            self.screen.blit(surf_t, (tx, ty))
        
        # Sub-pixel rounding base
        gx = int(round(self.grid_x))
        gy = int(round(self.grid_y))
        gs = int(round(self.grid_size))
        
        # Shake & Heartbeat effect
        if self.panic_pulse > 0:
            import math
            # La griglia pulsa (zoom)
            zoom = 1.0 + self.panic_pulse * 0.03
            gs = int(round(self.grid_size * zoom))
            # Ricentra dopo lo zoom
            gx = int(round(self.grid_x - (gs - self.grid_size) / 2))
            gy = int(round(self.grid_y - (gs - self.grid_size) / 2))
            
            # Shake coordinato al battito
            shake_amp = int(12 * self.panic_pulse)
            gx += int(math.sin(time.time() * 60) * shake_amp)
            gy += int(math.cos(time.time() * 55) * (shake_amp // 2))
        elif self.shake_timer > 0:
            import math
            shake_amp = 8
            gx += int(math.sin(self.shake_timer * 40) * shake_amp)
        
        # Disegna Griglia Sudoku (Sfondo)
        rect_grid = pygame.Rect(gx, gy, gs, gs)
        pygame.draw.rect(self.screen, COLOR_GRID_BG, rect_grid)
        
        # Cella selezionata e celle
        for r in range(self.board.n):
            for c in range(self.board.n):
                # Usa gy e gx con offset dello shake
                cx = int(round(gx + c * (gs / self.board.n)))
                cy = int(round(gy + r * (gs / self.board.n)))
                cw = int(round(gx + (c + 1) * (gs / self.board.n))) - cx
                ch = int(round(gy + (r + 1) * (gs / self.board.n))) - cy
                
                cell_rect = pygame.Rect(cx, cy, cw, ch)
                
                # Sfondo cella
                if self.selected_cell == (r, c):
                    color = list(COLOR_CELL_SEL)
                    if self.tutorial_step != -1: # Pulse durante tutorial
                        color[0] = min(255, int(color[0] + self.tut_pulse * 40))
                        color[1] = min(255, int(color[1] + self.tut_pulse * 40))
                    pygame.draw.rect(self.screen, color, cell_rect)
                elif (r, c) in self.error_cells:
                    pygame.draw.rect(self.screen, (255, 200, 200), cell_rect)
                    
                # Numero
                val = self.board.grid[r][c]
                if val != 0:
                    color = COLOR_TEXT_GIVEN if self.board.fixed[r][c] else COLOR_TEXT_USER
                    if (r, c) in self.error_cells:
                        color = COLOR_TEXT_ERROR
                        
                    self._draw_text_centered(str(val), self.font_large, color, cell_rect)

        # Linee Griglia + Bordo esterno (chrome statico cachato, blittato
        # con l'offset dello shake/zoom). Evita ~2*(n+1) draw.line + 1 draw.rect
        # ogni frame, costo notevole su ARM.
        self.screen.blit(self._get_grid_chrome(gs), (gx, gy))
        
        # Feedback info message
        if self.info_timer > 0 and self.info_msg:
            alpha = min(255, int(self.info_timer * 255))
            msg_col = COLOR_TEXT_ERROR if "ERROR" in self.info_msg else COLOR_BTN_BG
            msg_surf = self._text(self.info_msg, self.font_large, msg_col)
            msg_surf.set_alpha(alpha)
            msg_rect = msg_surf.get_rect(center=(gx + gs // 2, gy + gs // 2))
            
            # Comic backplate per il testo
            bp = msg_rect.inflate(30, 20)
            pygame.draw.rect(self.screen, (255, 255, 255), bp, border_radius=15)
            pygame.draw.rect(self.screen, COLOR_LINE_THICK, bp, 4, border_radius=15)
            self.screen.blit(msg_surf, msg_rect)
        
        # Disegna Numpad
        for rect, val in self.numpad_rects:
            bg_col = COLOR_BTN_HOVER if rect.collidepoint(mx, my) else COLOR_BTN_BG
            pygame.draw.rect(self.screen, bg_col, rect)
            pygame.draw.rect(self.screen, COLOR_LINE_THICK, rect, 3)
            self._draw_text_centered(str(val), self.font_btn, COLOR_BTN_TEXT, rect)
            
        # Bottoni Clear e Submit
        for btn, key in [(self.btn_clear, "sudoku_clear"), (self.btn_submit, "sudoku_submit")]:
            bg_col = COLOR_BTN_HOVER if btn.collidepoint(mx, my) else COLOR_BTN_BG
            pygame.draw.rect(self.screen, bg_col, btn)
            pygame.draw.rect(self.screen, COLOR_LINE_THICK, btn, 3)
            self._draw_text_centered(self._(key), self.font_med, COLOR_BTN_TEXT, btn)

        # Overlay Vittoria (Animato)
        if self.state == "GAME_OVER":
            progress = max(0.0, min(1.0, (3.0 - self.timer_msg) / 0.5))
            ov_alpha = int(200 * progress)
            if _ANDROID:
                # Su ARM una SRCALPHA fullscreen ricreata+riempita ogni frame
                # costa ~10x: si usa una surface opaca cachata con set_alpha.
                over_surf = self._get_overlay((0, 0, 0))
                over_surf.set_alpha(ov_alpha)
                self.screen.blit(over_surf, (0, 0))
            else:
                over_surf = pygame.Surface(self.screen.get_size(), pygame.SRCALPHA)
                over_surf.fill((0, 0, 0, ov_alpha))
                self.screen.blit(over_surf, (0, 0))

            if progress >= 1.0:
                import math
                bounce = abs(math.sin(self.timer_msg * 5)) * 20
                color = (255, 255, 0) if int(self.timer_msg * 10) % 2 == 0 else (255, 100, 0)
                msg_surf = self._text(self._("sudoku_game_over"), self.font_large, color)
                center_x = self.screen.get_width() // 2
                center_y = int(self.screen.get_height() // 2 - bounce)
                msg_rect = msg_surf.get_rect(center=(center_x, center_y))
                
                bp = msg_rect.inflate(60, 40)
                pygame.draw.rect(self.screen, (255, 255, 255), bp, border_radius=20)
                pygame.draw.rect(self.screen, COLOR_LINE_THICK, bp, 6, border_radius=20)
                self.screen.blit(msg_surf, msg_rect)

        # Overlay Tempo Scaduto
        if self.state == "TIME_UP":
            if _ANDROID:
                # Path veloce ARM: surface opaca cachata + set_alpha invece di
                # ricreare una SRCALPHA fullscreen ogni frame.
                over_surf = self._get_overlay((100, 0, 0))
                over_surf.set_alpha(180)
                self.screen.blit(over_surf, (0, 0))
            else:
                over_surf = pygame.Surface(self.screen.get_size(), pygame.SRCALPHA)
                over_surf.fill((100, 0, 0, 180)) # Rosso scuro trasparente
                self.screen.blit(over_surf, (0, 0))

            msg = self._("sudoku_time_up")
            msg_surf = self._text(msg, self.font_large, (255, 255, 0))
            msg_rect = msg_surf.get_rect(center=(self.screen.get_width()//2, self.screen.get_height()//2))
            
            # Comic backplate
            bp = msg_rect.inflate(60, 40)
            pygame.draw.rect(self.screen, (255, 255, 255), bp, border_radius=20)
            pygame.draw.rect(self.screen, COLOR_LINE_THICK, bp, 6, border_radius=20)
            self.screen.blit(msg_surf, msg_rect)

        # Rendering TUTORIAL (ultimo layer)
        if self.tutorial_step >= 0:
            if self.tutorial_step == 0:
                msg = self._("tut_step_0", "Ciao! Lo scopo è riempire la griglia.\nOgni numero deve essere unico per\nriga, colonna e quadrato 3x3.")
                self._draw_comic_tooltip(msg, (int(self.grid_x + self.grid_size//2), int(self.grid_y + self.grid_size//2)), "down")
            elif self.tutorial_step == 1:
                msg = self._("tut_step_1", "Per iniziare,\nclicca una cella vuota.")
                self._draw_comic_tooltip(msg, (int(self.grid_x + self.grid_size//2), int(self.grid_y + self.grid_size//2)), "down")
            elif self.tutorial_step == 2:
                # Suggerimento intelligente: punta esattamente al bottone corretto
                val_sug = 1
                target_pos = (int(self.screen.get_width()*0.8), int(self.screen.get_height()*0.5))
                
                if self.selected_cell:
                    r, c = self.selected_cell
                    val_sug = self.board.solution[r][c]
                    # Trova il rettangolo del bottone specifico
                    for rect, val in self.numpad_rects:
                        if val == val_sug:
                            target_pos = rect.center
                            break
                
                msg_base = self._("tut_step_2_evolved", "Ottimo!\nOra clicca il numero {val} a destra.\nRicorda: unico per riga/colonna/quadrato!")
                msg = msg_base.replace("{val}", str(val_sug))
                self._draw_comic_tooltip(msg, target_pos, "right")
            elif self.tutorial_step == 3:
                msg = self._("tut_step_3", "Attento al tempo!\nSe scade, la partita finisce.")
                tx = self.screen.get_width() - 50
                self._draw_comic_tooltip(msg, (tx, 50), "up")
            elif self.tutorial_step == 4:
                msg = self._("tut_step_4", "Fallo il più velocemente possibile.\nBuona fortuna!")
                self._draw_comic_tooltip(msg, (int(self.grid_x + self.grid_size//2), int(self.grid_y + self.grid_size//2)), "down")

        # Overlay Panico (Vignetta Rossa). Disegnata come 4 strisce ai bordi
        # invece di una SRCALPHA a tutto schermo (che su pygame ARM è lentissima):
        # si fa l'alpha-blit solo sull'area effettivamente colorata.
        if self.state == "PLAYING" and self.game_timer < 10 and self.game_timer > 0:
            sw, sh = self.screen.get_size()
            alpha = int(120 * self.panic_pulse)
            border = int(sh * 0.15)

            if _ANDROID:
                # Path veloce ARM: 4 strisce opache cachate (per dimensione) +
                # set_alpha per frame, invece di creare+riempire 4 SRCALPHA ogni
                # frame. L'alpha varia col battito senza nuove allocazioni.
                strips = self._get_vignette_strips(sw, sh, border)
                for surf, pos in strips:
                    surf.set_alpha(alpha)
                    self.screen.blit(surf, pos)
            else:
                col = (200, 0, 0, alpha)

                def _strip(w, h, x, y):
                    if w <= 0 or h <= 0:
                        return
                    strip = pygame.Surface((w, h), pygame.SRCALPHA)
                    strip.fill(col)
                    self.screen.blit(strip, (x, y))

                _strip(sw, border, 0, 0)            # Sopra
                _strip(sw, border, 0, sh - border)  # Sotto
                _strip(border, sh, 0, 0)            # Sinistra
                _strip(border, sh, sw - border, 0)  # Destra
