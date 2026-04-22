"""
engine/menu_system.py

Implementa un sistema di pulsanti basici nativi che scalano automaticamente col game_manager.
Risolve il menu principale d'atterraggio post splash-screen.
"""
import json
import pygame
from engine.utils import get_logger, get_resource_path

class MenuButton:
    """Classe logica per contenitore bottone scalabile con supporto icone/anteprime."""
    def __init__(self, text: str, action: str, rx: float, ry: float, rw: float, rh: float, image: pygame.Surface = None):
        self.text = text
        self.action = action
        self.ref_rect = pygame.Rect(rx, ry, rw, rh) # Rettangolo originale a 1280x720
        self.hovered = False
        self.image = image

class MenuSlider:
    """Controllo per range di valori (es: volume)."""
    def __init__(self, label: str, action: str, rx: float, ry: float, rw: float, rh: float, value: float):
        self.label = label
        self.action = action 
        self.ref_rect = pygame.Rect(rx, ry, rw, rh)
        self.value = value
        self.hovered = False
        self.dragging = False

class MenuSystem:
    def __init__(self, scaling_manager, lang_manager, game_id: str, save_manager=None) -> None:
        self.logger = get_logger(__name__)
        self.scaling_manager = scaling_manager
        self.lang = lang_manager
        self.game_id = game_id
        self.save_manager = save_manager
        
        self.state = "main"
        self.current_res = "1280x720"
        self.is_fullscreen = False
        self.music_volume = 1.0 # Cache locale per lo slider
        self.sfx_volume = 1.0   # Cache locale per SFX
        
        self.buttons: list[MenuButton] = []
        self.sliders: list[MenuSlider] = []
        self.selected_level: str | None = None
        self.build_buttons()

    def build_buttons(self, has_save: bool = False) -> None:
        """Ricalcola i bottoni mostrati in base allo sub-stato del Menu."""
        self.buttons.clear()
        self.sliders.clear()
        
        if self.state == "main":
            # Se esiste un salvataggio, mostriamo "Continua"
            if has_save:
                self.buttons = [
                    MenuButton(self.lang.get("btn_continue", "Continua"), "goto_levels", 500, 260, 280, 50),
                    MenuButton(self.lang.get("btn_new_game", "Pulisci File"), "confirm_new", 500, 330, 280, 50),
                    MenuButton(self.lang.get("btn_settings"), "goto_settings", 500, 400, 280, 50),
                    MenuButton(self.lang.get("btn_quit"), "quit", 500, 470, 280, 50)
                ]
            else:
                self.buttons = [
                    MenuButton(self.lang.get("btn_play"), "goto_levels", 500, 300, 280, 50),
                    MenuButton(self.lang.get("btn_settings"), "goto_settings", 500, 380, 280, 50),
                    MenuButton(self.lang.get("btn_quit"), "quit", 500, 460, 280, 50)
                ]
        elif self.state == "confirm_new":
            self.buttons = [
                MenuButton(self.lang.get("msg_confirm_new_game", "ATTENZIONE: Perderai i progressi!"), "none", 440, 250, 400, 40),
                MenuButton(self.lang.get("btn_confirm_new_game", "Sì, Inizia Nuovo Gioco"), "do_new_game", 440, 310, 400, 50),
                MenuButton(self.lang.get("btn_back"), "goto_main", 500, 400, 280, 40)
            ]
        elif self.state == "levels":
            # Caricamento dinamico dei livelli dal filesystem
            levels_path = get_resource_path("games", self.game_id, "levels")
            y_start = 240
            
            # Leggi progressi
            unlocked_lvls = []
            if self.save_manager:
                unlocked_lvls = self.save_manager.get_progress("unlocked_levels", [])

            if levels_path.exists():
                lvl_dirs = sorted([d for d in levels_path.iterdir() if d.is_dir()])
                for i, ld in enumerate(lvl_dirs):
                    level_id = ld.name
                    level_name = level_id
                    
                    cfg_p = ld / "level_config.json"
                    if cfg_p.exists():
                        try:
                            with open(cfg_p, "r", encoding="utf-8") as f:
                                cfg = json.load(f)
                            nk = cfg.get("name_key")
                            if nk:
                                level_name = self.lang.get(nk, level_id)
                        except: pass
                    
                    is_unlocked = level_id in unlocked_lvls
                    display_text = level_name if is_unlocked else f"[LOCK] {level_name}"
                    btn_action = f"goto_scenes:{level_id}" if is_unlocked else "none"

                    self.buttons.append(
                        MenuButton(display_text, btn_action, 440, y_start + (i * 70), 400, 60)
                    )
            
            self.buttons.append(
                MenuButton(self.lang.get("btn_back"), "goto_main", 500, 600, 280, 40)
            )

        elif self.state == "scenes":
            # Mostra le scene del livello selezionato con anteprime grafiche
            if self.selected_level:
                lvl_path = get_resource_path("games", self.game_id, "levels", self.selected_level)
                cfg_p = lvl_path / "level_config.json"
                if cfg_p.exists():
                    try:
                        with open(cfg_p, "r", encoding="utf-8") as f:
                            cfg = json.load(f)
                        scenes = cfg.get("scenes", [])
                        
                        y_start = 140
                        for i, s in enumerate(scenes):
                            scene_id = s.get("id")
                            
                            # Verifica sblocco
                            is_unlocked = True
                            if self.save_manager:
                                is_unlocked = self.save_manager.is_scene_unlocked(self.selected_level, i)

                            # Caricamento anteprima dello sfondo della scena
                            preview = None
                            try:
                                scene_dir = lvl_path / scene_id
                                # Leggiamo scene.json per identificare il background esatto
                                s_cfg_p = scene_dir / "scene.json"
                                if s_cfg_p.exists():
                                    with open(s_cfg_p, "r", encoding="utf-8") as sf:
                                        s_cfg = json.load(sf)
                                    bg_file = s_cfg.get("background", "background.png")
                                    bg_full_path = scene_dir / bg_file
                                    
                                    if bg_full_path.exists():
                                        raw_surf = pygame.image.load(str(bg_full_path))
                                        # Creiamo una miniatura ottimizzata
                                        preview = pygame.transform.smoothscale(raw_surf, (320, 180))
                                        
                                        # Effetto Bianco e Nero per le scene bloccate (richiede Pygame 2.1.2+)
                                        if not is_unlocked:
                                            try:
                                                preview = pygame.transform.grayscale(preview)
                                            except:
                                                # Fallback molto semplice se transform.grayscale fallisce
                                                pass
                            except Exception as ex:
                                self.logger.warning(f"Impossibile caricare anteprima per {scene_id}: {ex}")

                            name = self.lang.get(f"{scene_id}_name", scene_id)
                            btn_action = f"play_scene:{self.selected_level}:{scene_id}" if is_unlocked else "none"
                            
                            # Calcolo posizione griglia (3 colonne)
                            row = i // 3
                            col = i % 3
                            grid_x = 120 + (col * 360)
                            grid_y = y_start + (row * 220)

                            self.buttons.append(
                                MenuButton(name, btn_action, grid_x, grid_y, 320, 180, image=preview)
                            )
                    except Exception as e:
                        self.logger.error(f"Errore caricamento scene per {self.selected_level}: {e}")
            
            self.buttons.append(
                MenuButton(self.lang.get("btn_back"), "goto_levels", 500, 600, 280, 40)
            )
        elif self.state == "settings":
            lang_lbl = self.lang.get("label_language", "Lingua:")
            res_lbl = self.lang.get("label_resolution", "Risoluzione:")
            fs_lbl = self.lang.get("label_fullscreen", "Schermo:")
            
            # Recupera traduzione dello stato (Fullscreen/Windowed)
            mode_key = "mode_fullscreen" if self.is_fullscreen else "mode_window"
            mode_text = self.lang.get(mode_key, "Full" if self.is_fullscreen else "Win")

            self.buttons = [
                MenuButton(f"{lang_lbl} {self.lang.current_language.upper()}", "toggle_lang", 440, 160, 400, 50),
                MenuButton(f"{res_lbl} {self.current_res}", "toggle_res", 440, 230, 400, 50),
                MenuButton(f"{fs_lbl} {mode_text}", "toggle_fs", 440, 300, 400, 50),
                MenuButton(self.lang.get("btn_back"), "goto_main", 500, 580, 280, 40)
            ]
            # Aggiungiamo gli slider per i volumi
            self.sliders = [
                MenuSlider(self.lang.get("label_music_volume", "Volume Musica"), "set_music_volume", 440, 380, 400, 50, self.music_volume),
                MenuSlider(self.lang.get("label_sfx_volume", "Volume Effetti"), "set_sfx_volume", 440, 470, 400, 50, self.sfx_volume)
            ]
        elif self.state == "pause":
            self.buttons = [
                MenuButton(self.lang.get("btn_resume", "Riprendi"), "resume_game", 500, 250, 280, 50),
                MenuButton(self.lang.get("btn_settings", "Impostazioni"), "goto_settings", 500, 330, 280, 50),
                MenuButton(self.lang.get("btn_quit_to_main", "Menu"), "quit_to_main", 500, 410, 280, 50)
            ]

    def change_state(self, new_state: str, has_save: bool = False, extra_data: str = None) -> None:
        self.state = new_state
        if new_state == "scenes" and extra_data:
            self.selected_level = extra_data
        elif new_state == "levels":
            self.selected_level = None
        self.build_buttons(has_save=has_save)

    def update(self, dt: float, mouse_x: int, mouse_y: int) -> None:
        """Esegue hit test reverso sul puntatore del mouse raw."""
        # Trasforma mouse reale in coordinate scena interna
        rx, ry = self.scaling_manager.screen_to_ref(mouse_x, mouse_y)
        for b in self.buttons:
            b.hovered = b.ref_rect.collidepoint(rx, ry)
            
        for s in self.sliders:
            s.hovered = s.ref_rect.collidepoint(rx, ry)
            if s.dragging:
                # Calcola nuovo valore in base alla coordinata X relativa
                rel_x = max(0, min(rx - s.ref_rect.x, s.ref_rect.w))
                s.value = rel_x / s.ref_rect.w
                if s.action == "set_music_volume":
                    self.music_volume = s.value
                elif s.action == "set_sfx_volume":
                    self.sfx_volume = s.value

    def draw(self, screen: pygame.Surface) -> None:
        """Dipingimento fisico e test del testo per i bottoni."""
        for b in self.buttons:
            # Crea e scala rect per il renderer
            rect = self.scaling_manager.scale_rect(b.ref_rect.x, b.ref_rect.y, b.ref_rect.w, b.ref_rect.h)
            
            # Se il bottone ha un'immagine, la disegniamo (anteprima scena)
            if b.image:
                # Scaliamo l'immagine per riempire il rettangolo del bottone
                img_scaled = pygame.transform.smoothscale(b.image, (rect.w, rect.h))
                screen.blit(img_scaled, rect)
                
                # Overlay semi-trasparente per migliorare leggibilità testo
                overlay_alpha = 180 if b.hovered else 100
                overlay = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
                overlay.fill((20, 20, 20, overlay_alpha))
                screen.blit(overlay, rect)
                
                # Bordo di selezione
                border_col = (255, 215, 0) if b.hovered else (150, 150, 150)
                pygame.draw.rect(screen, border_col, rect, width=2, border_radius=4)
                
                # Se l'azione è "none", disegniamo un lucchetto (testo per ora)
                if b.action == "none":
                    lock_font = pygame.font.SysFont(None, max(20, self.scaling_manager.scale_value(40)))
                    lock_surf = lock_font.render("[LOCKED]", True, (255, 50, 50))
                    # Posiziona il testo più in basso rispetto al bordo superiore
                    offset_y = self.scaling_manager.scale_value(60)
                    lock_rect = lock_surf.get_rect(center=(rect.centerx, rect.top + offset_y))
                    screen.blit(lock_surf, lock_rect)
            else:
                # Bottone standard (testuale)
                bg_col = (200, 160, 60) if b.hovered else (80, 60, 60)
                pygame.draw.rect(screen, bg_col, rect, border_radius=6)
            
            # Render testo a grandezza dinamica
            font_size = max(14, self.scaling_manager.scale_value(24 if b.image else 28))
            font = pygame.font.SysFont(None, font_size)
            text_surf = font.render(b.text, True, (255, 255, 255))
            
            # Se c'è immagine, mettiamo il testo in basso
            if b.image:
                text_rect = text_surf.get_rect(midbottom=(rect.centerx, rect.bottom - 10))
            else:
                text_rect = text_surf.get_rect(center=rect.center)
            
            screen.blit(text_surf, text_rect)
            
        # Draw Sliders
        for s in self.sliders:
            rect = self.scaling_manager.scale_rect(s.ref_rect.x, s.ref_rect.y, s.ref_rect.w, s.ref_rect.h)
            
            # Label
            font_label = pygame.font.SysFont(None, max(14, self.scaling_manager.scale_value(22)))
            label_surf = font_label.render(f"{s.label}: {int(s.value * 100)}%", True, (200, 200, 200))
            screen.blit(label_surf, (rect.x, rect.y - self.scaling_manager.scale_value(20)))
            
            # Background bar
            pygame.draw.rect(screen, (40, 40, 40), rect, border_radius=4)
            pygame.draw.rect(screen, (80, 80, 80), rect, width=2, border_radius=4)
            
            # Progress bar
            if s.value > 0:
                prog_w = int(rect.w * s.value)
                prog_rect = pygame.Rect(rect.x, rect.y, prog_w, rect.h)
                # Gradiente o colore solido premium
                pygame.draw.rect(screen, (200, 160, 60), prog_rect, border_radius=4)
            
            # Handle (Cursore)
            handle_x = rect.x + int(rect.w * s.value)
            handle_rect = pygame.Rect(handle_x - 5, rect.y - 5, 10, rect.h + 10)
            pygame.draw.rect(screen, (255, 255, 255), handle_rect, border_radius=2)

    def process_click(self, mouse_x: int, mouse_y: int) -> str | None:
        """Invocato da core.py quando vi è una MOUSEBUTTONDOWN."""
        rx, ry = self.scaling_manager.screen_to_ref(mouse_x, mouse_y)
        for b in self.buttons:
            if b.ref_rect.collidepoint(rx, ry):
                return b.action
                
        for s in self.sliders:
            if s.ref_rect.collidepoint(rx, ry):
                s.dragging = True
                # Restituisce l'azione subito per feedback audio o altro
                return f"{s.action}:{s.value}"
        return None

    def release_click(self) -> None:
        """Ferma il trascinamento di tutti gli slider."""
        for s in self.sliders:
            s.dragging = False

    def get_slider_value(self, action: str) -> float | None:
        """Recupera il valore di uno slider specifico."""
        for s in self.sliders:
            if s.action == action:
                return s.value
        return None
