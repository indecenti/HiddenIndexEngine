"""
engine/core.py

Contiene il loop principale (Pygame) e la macchina a stati dell'Engine.
"""

import sys
import random
import pygame
import re
import math
import logging
import os
from pathlib import Path

from engine.utils import get_logger, warp_surface, apply_grayscale
from engine.scaling_manager import ScalingManager
from engine.save_manager import SaveManager
from engine.transition_manager import TransitionManager, TransitionType
from engine.level_manager import SCENE_COMPLETE, LEVEL_COMPLETE, SCENE_FAILED

try:
    import ctypes
    ctypes.windll.user32.SetProcessDPIAware()
except Exception:
    pass

class EngineState:
    """Stati principali della state machine di sistema."""
    BOOT = "BOOT"
    MENU = "MENU"
    LEVEL_SELECT = "LEVEL_SELECT"
    SCENE = "SCENE"
    RESULTS = "RESULTS"
    PAUSE = "PAUSE"
    MINIGAME = "MINIGAME"

class EngineCore:
    """
    Gestisce il setup del contesto, lo step delta-time, e
    il disbrigo (dispatch) all'attuale stato di gioco.
    """
    def __init__(self, game_id: str, config, cli_args) -> None:
        self.logger = get_logger(__name__)
        self.game_id = game_id
        self.config = config
        self.state = EngineState.BOOT
        self.running = False
        
        # Dati Configurazione Display
        self.res_w = config.getint("engine", "resolution_w", fallback=1280)
        self.res_h = config.getint("engine", "resolution_h", fallback=720)
        self.is_fullscreen = cli_args.fullscreen or config.getboolean("engine", "fullscreen", fallback=False)
        self.music_volume = config.getfloat("engine", "music_volume", fallback=1.0)
        self.sfx_volume = config.getfloat("engine", "sfx_volume", fallback=1.0)
        
        self.logger.info(f"Inizializzazione gioco '{game_id}': {self.res_w}x{self.res_h} (FS:{self.is_fullscreen})")
        
        # Forza centratura finestra su Windows/Linux/Mac
        os.environ['SDL_VIDEO_CENTERED'] = '1'
        
        pygame.init()
        pygame.display.set_caption("Hidden Engine")
        
        flags = pygame.DOUBLEBUF
        if self.is_fullscreen:
            flags |= pygame.FULLSCREEN
            
        # VSync attivo per fluidità professionale (Pygame 2+)
        self.screen = pygame.display.set_mode((self.res_w, self.res_h), flags, vsync=1)
        self.clock = pygame.time.Clock()
        
        # Inizializzo Sistemi
        self.scaling_manager = ScalingManager()
        self.scaling_manager.update_screen_size(self.res_w, self.res_h)
        
        self.save_manager = SaveManager(self.game_id)
        
        reduced = config.getboolean("engine", "reduced_animations", fallback=False)
        self.transition_manager = TransitionManager(reduced_animations=reduced)
        
        import json
        from engine.utils import get_resource_path
        from engine.audio_manager import AudioManager
        from engine.language_manager import LanguageManager
        from engine.menu_system import MenuSystem
        from engine.effects_engine import EffectsEngine
        from engine.hint_system import HintSystem
        from engine.scene_loader import SceneLoader
        from engine.click_detector import ClickDetector
        from engine.hud_manager import HudManager
        from engine.level_manager import LevelManager
        from engine.catalog_manager import load_catalog
        from engine.results_screen import ResultsScreen

        # Lettura game_config.json interno al gioco
        self.game_config = {}
        gc_path = get_resource_path("games", self.game_id, "game_config.json")
        if gc_path.exists():
            with open(gc_path, "r", encoding="utf-8") as f:
                self.game_config = json.load(f)

        self.audio = AudioManager()
        self.audio.set_music_volume(self.music_volume)
        self.audio.set_sfx_volume(self.sfx_volume)
        self.lang = LanguageManager()
        
        # Priorità lingua: CLI > game_config > default(it)
        lang_to_load = getattr(cli_args, "lang", None) or self.game_config.get("default_language", "it")
        self.lang.load_for_game(self.game_id, lang_to_load)
        self.effects = EffectsEngine(self.scaling_manager)
        self.hint = HintSystem(self.scaling_manager, self.effects)

        # Inizializzazione manager core e loader
        catalog = load_catalog(self.game_id)
        from engine.effect_renderer import EffectRenderer
        self.fx_renderer = EffectRenderer()

        self.scene_loader = SceneLoader(self.game_id, catalog)
        self.level_manager = LevelManager(self.game_id, self.scene_loader, hint_system=self.hint)
        self.level_manager.set_game_config(self.game_config)

        self.menu_system = MenuSystem(self.scaling_manager, self.lang, self.game_id, self.save_manager)
        self.menu_system.current_res = f"{self.res_w}x{self.res_h}"
        self.menu_system.is_fullscreen = self.is_fullscreen
        self.menu_system.music_volume = self.music_volume
        self.menu_system.sfx_volume = self.sfx_volume
        
        # Se non ci sono livelli sbloccati, sblocchiamo il primo disponibile (nuovo gioco)
        self._ensure_first_level_unlocked()

        self.menu_system.build_buttons(has_save=self._has_progress())

        # Cache layer_hint_intensity per evitare .get() ogni frame
        self._cached_layer_intensity = self.game_config.get("layer_hint_intensity", {})
        self.click_detector = ClickDetector(self.scaling_manager)
        
        hud_cfg = self.game_config.get("hud", {})
        self.hud = HudManager(self.scaling_manager, self.lang, hud_cfg, self.res_w, self.res_h)
        self.hud.on_screen_resize(self.res_w, self.res_h)

        # ResultsScreen - schermata di risultati premium tra i livelli
        self.results_screen = ResultsScreen(self.res_w, self.res_h, self.lang, self.scaling_manager)

        from engine.minigame_manager import MinigameManager
        self.minigame_manager = MinigameManager(self.screen, self.scaling_manager, self.audio, self.lang)

        self._current_scene_objects = []
        self._current_scene_effects = []
        self._score = 0
        self._time_elapsed = 0.0

        self._last_result = None
        self._results_timer = 0.0

        # Stato salvataggi gestito per eventi (cambio scena/livello)

        # Anti-Spam state
        self._click_history: list[float] = [] # Timestamps degli ultimi click
        self._spam_lock_timer: float = 0.0    # Se > 0, click ignorati

        # Hint indicator animation
        self._hint_indicator_timer: float = 0.0
        self._hint_indicator_duration: float = 0.5
        self._hint_indicator_target_obj: Optional[str] = None
        
        # --- INTRO SCENICA (Zoom) ---
        self._scene_intro_timer: float = 0.0
        self._scene_intro_dur: float = 3.0

        # --- FLASHLIGHT EFFECT ---
        self._current_scene_data = None
        self._flashlight_mask = None
        self._flashlight_hole_cache = None  # Cache per il gradiente radiale
        self._flashlight_cached_rad = 0
        self._hint_flash_timer = 0.0 # Timer per illuminazione temporanea (Hint Flash)
        
        # --- MENU VIDEO ---
        self._menu_video_cap = None
        self._menu_video_surface = None
        self._menu_video_path = None
        
        if getattr(cli_args, "minigame", None):
            self.logger.info(f"MODALITÀ TEST: Avvio istantaneo minigioco {cli_args.minigame}")
            success = self.minigame_manager.start_minigame(
                cli_args.minigame, 
                on_complete=lambda res: setattr(self, "running", False)
            )
            if success:
                self.state = EngineState.MINIGAME
            else:
                self.logger.error("Fallito avvio minigioco in modalità test.")
                self.state = EngineState.BOOT
                # Se fallisce, usciamo per tornare all'editor
                self.running = False
        else:
            # Test pipeline di transizione: Fade da SplashScreen (BOOT) a Menu
            self.transition_manager.start_transition(
                TransitionType.FADE_TO_BLACK,
                base_dur_out=1.0, # Splash rimane visibile un secondo
                on_midpoint=self._switch_to_menu
            )

    def _handle_resize(self, w: int, h: int) -> None:
        """Centralizza l'aggiornamento dei sistemi dopo un cambio di risoluzione."""
        self.res_w, self.res_h = w, h
        self.scaling_manager.update_screen_size(w, h)
        
        # Aggiorna mapping specifico del background della scena (se attivo)
        if hasattr(self, '_current_bg_surface') and self._current_bg_surface:
            bw, bh = self._current_bg_surface.get_size()
            bg_scale = getattr(self, '_current_bg_scale', 1.0)
            self.scaling_manager.set_background(bw, bh, bg_scale)
            self.logger.debug(f"Background scena ri-scalato: {bw}x{bh} @ {bg_scale}")
        
        # Aggiorna HUD
        if hasattr(self, 'hud'):
            self.hud.on_screen_resize(w, h)
        
        # Aggiorna Menu UI
        if hasattr(self, 'menu_system'):
            self.menu_system.current_res = f"{w}x{h}"
            self.menu_system.is_fullscreen = self.is_fullscreen
            self.menu_system.build_buttons(has_save=self._has_progress())
            
        if hasattr(self, 'results_screen'):
             self.results_screen.on_resize(w, h)

        # Sincronizza minigiochi (evita 'Surface quit' su resize)
        if hasattr(self, 'minigame_manager'):
            self.minigame_manager.sync_with_engine(self.screen)
            
        self.logger.info(f"Sistemi engine sincronizzati alla risoluzione: {w}x{h}")

    def run(self) -> None:
        """Loop principale del gioco."""
        self.running = True
        self.logger.info("Main loop avviato.")
        
        while self.running:
            dt = self.clock.tick(60) / 1000.0  # limit framerate to 60 FPS
            self._handle_events()
            self._update(dt)
            self._draw()
            
        self._quit()
        
    def _handle_events(self) -> None:
        """Smista gli input di Pygame."""
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
                
            elif event.type == pygame.VIDEORESIZE:
                # In modalità SCALED non serve ricalcolare tutto, 
                # ma aggiorniamo i buffer interni se necessario.
                self.logger.debug(f"Video Resize rilevato: {event.w}x{event.h}")

            if self.state == EngineState.MINIGAME:
                # Se il minigioco intercetta un click sul tasto Pausa, attiva la pausa globale
                if self.minigame_manager.handle_event(event):
                    self._toggle_pause()
                continue
                    
            elif event.type == pygame.MOUSEBUTTONDOWN:
                if event.button == 1: # Left click
                    self.hud.on_mouse_activity()
                    if self.state in [EngineState.MENU, EngineState.PAUSE]:
                        action = self.menu_system.process_click(event.pos[0], event.pos[1])
                        if action and action != "none":
                            self.audio.play_sfx("engine/assets/sounds/click_Low.wav")
                        elif action == "none":
                            self.audio.play_sfx("engine/assets/sounds/UI_Forbidden.wav") # Feedback per bloccato
                        
                        if action:
                            if action == "goto_levels":
                                self.menu_system.change_state("levels")
                            elif action == "goto_settings":
                                self.menu_system.change_state("settings")
                            elif action == "goto_main":
                                if self.state == EngineState.PAUSE:
                                    self.menu_system.change_state("pause", has_save=self._has_progress())
                                else:
                                    self.menu_system.change_state("main", has_save=self._has_progress())
                            elif action == "confirm_new":
                                self.menu_system.change_state("confirm_new")
                            elif action == "do_new_game":
                                self.save_manager.reset_progress()
                                self._ensure_first_level_unlocked()
                                self.logger.info("Nuova partita avviata. Progressi resettati e primo livello sbloccato.")
                                self._switch_to_menu()
                            elif action == "resume_game":
                                if self.state == EngineState.PAUSE:
                                    self._toggle_pause()
                                else:
                                    # Caricamento dal Menu Principale
                                    self.transition_manager.start_transition(
                                        TransitionType.FADE_TO_BLACK, 
                                        on_midpoint=self._resume_from_save
                                    )
                            elif action == "quit_to_main":
                                # Stop musica e ritorno al menu
                                self.audio.stop_music(fade_ms=500)
                                self._switch_to_menu()
                            elif action == "toggle_lang":
                                av_langs = self.lang.available_languages
                                if av_langs:
                                    try:
                                        idx = av_langs.index(self.lang.current_language)
                                        new_idx = (idx + 1) % len(av_langs)
                                    except ValueError:
                                        new_idx = 0
                                    new_l = av_langs[new_idx]
                                    self.lang.change_language(new_l)
                                    self.logger.info(f"Lingua cambiata in: {new_l}")
                                    self.menu_system.build_buttons()
                            elif action == "toggle_res":
                                if self.res_w == 1280:
                                    new_w, new_h = 1920, 1080
                                elif self.res_w == 1920:
                                    new_w, new_h = 2560, 1440
                                else:
                                    new_w, new_h = 1280, 720
                                self._apply_display_settings(new_w, new_h, self.is_fullscreen)
                            elif action.startswith("goto_scenes:"):
                                level_id = action.split(":", 1)[1]
                                self.menu_system.change_state("scenes", has_save=self._has_progress(), extra_data=level_id)
                            elif action.startswith("play_scene:"):
                                pts = action.split(":")
                                lid, sid = pts[1], pts[2]
                                self.logger.info(f"Play scena '{sid}' del livello '{lid}' richiesto dal menu.")
                                self.transition_manager.start_transition(
                                    TransitionType.FADE_TO_BLACK, 
                                    on_midpoint=lambda l=lid, s=sid: self._start_level(l, s)
                                )
                            elif action.startswith("play_level:"):
                                level_id = action.split(":", 1)[1]
                                self.logger.info(f"Play livello '{level_id}' richiesto dal menu.")
                                self.transition_manager.start_transition(
                                    TransitionType.FADE_TO_BLACK, 
                                    on_midpoint=lambda lid=level_id: self._start_level(lid)
                                )
                            elif action == "quit":
                                self.running = False
                            elif action == "toggle_fs":
                                new_fs = not self.is_fullscreen
                                self._apply_display_settings(self.res_w, self.res_h, new_fs)
                        
                        # Aggiornamento parametri menu dinamici (res/lang/ecc)
                        if action and action.startswith("goto"):
                            self.menu_system.build_buttons(has_save=self._has_progress())

                    elif self.state == EngineState.SCENE:
                        # --- GESTIONE BUBBLE TIPS ---
                        is_visible = self.level_manager.is_any_bubble_visible()
                        is_pending_intro = self._scene_intro_timer > 0 and self.level_manager.has_start_scene_bubbles()

                        if is_visible or is_pending_intro:
                            # Se è visibile, gestiamo il click sul pulsante "OK"
                            if is_visible:
                                clicked_any = False
                                sm = self.scaling_manager
                                for fx in self._current_scene_effects:
                                    if fx.type == "bubble_tip" and getattr(fx, "_visible", False):
                                        if hasattr(self, "_last_bubble_btns"):
                                            for b_fx, b_rect in self._last_bubble_btns:
                                                if b_fx == fx and b_rect.collidepoint(event.pos):
                                                    fx._visible = False
                                                    self.audio.play_sfx("engine/assets/sounds/click_Low.wav")
                                                    clicked_any = True
                                                    break
                                        if clicked_any: break
                            
                            # Se una bubble è visibile o sta per apparire, ignoriamo ogni altro input di gioco
                            continue

                        # Controlla click su pulsante hint in alto a destra (bypass spam-lock)
                        if hasattr(self, '_hint_button_rect') and self._hint_button_rect.collidepoint(event.pos):
                            # [FIX] Controllo disponibilità hint prima dell'uso
                            if self.level_manager.get_available_hints() > 0:
                                # Nuova Logica: Hint Flash per scene con torcia
                                is_flashlight = self._current_scene_data and getattr(self._current_scene_data, 'flashlight', False)
                                
                                success, penalty = self.hint.use_manual_hint(
                                    self._current_scene_objects, 
                                    suppress_fx=False
                                )
                                
                                if success:
                                    self.audio.play_sfx("engine/assets/sounds/click_Low.wav")
                                    self.level_manager.apply_score_penalty(penalty)
                                    self.level_manager.consume_hint_from_rewards()  # Decrementa conteggio HUD
                                    
                                    if is_flashlight:
                                        self._hint_flash_timer = 5.0
                                        self.logger.info("Hint Flash attivato per 5 secondi (torcia presente)")
                                    else:
                                        # Popup vicino al mouse per il costo dell'hint standard
                                        bx, by = self.scaling_manager.screen_to_bg(*event.pos)
                                        self.effects.spawn_score_popup(bx, by, penalty)
                                        self.logger.info(f"Hint usato (bottone): penalità {penalty} pt")
                            else:
                                self.audio.play_sfx("engine/assets/sounds/UI_Forbidden.wav")
                                self.logger.warning("Tentativo di usare hint ma quantità disponibile è 0!")
                            continue

                        # Controlla click su pulsante PAUSE in alto a sinistra
                        if self.hud.is_pause_button_clicked(event.pos):
                            self.audio.play_sfx("engine/assets/sounds/click_Low.wav")
                            self._toggle_pause()
                            continue

                        # 1. Controllo Anti-Spam
                        now = pygame.time.get_ticks() / 1000.0
                        if self._spam_lock_timer > 0:
                            self.logger.debug("Click ignorato: Sistema in LOCKDOWN")
                            continue
                            
                        # Aggiorna cronologia (ultimi 2 secondi)
                        self._click_history = [t for t in self._click_history if now - t < 1.0]
                        self._click_history.append(now)
                        
                        if len(self._click_history) > 5: # Più di 5 click al secondo
                            self.logger.warning("SPAM DETECTED! Avvio lockdown per 3 secondi.")
                            self._spam_lock_timer = 3.0
                            continue

                        # 2. Rilevamento Hit (compensando lo zoom intro se presente)
                        z_fact = 1.0
                        if self._scene_intro_timer > 0:
                            t = self._scene_intro_timer / self._scene_intro_dur
                            z_fact = 1.0 + (t ** 3 * 0.25)

                        hit = self.click_detector.detect(
                            event.pos[0], event.pos[1], 
                            self._current_scene_objects,
                            scenic_factor=z_fact
                        )
                        if hit:
                            trigger = getattr(hit, "minigame_trigger", None)
                            self.logger.debug(f"[CLICK] Hit: {hit.instance_id} (trigger: {trigger is not None})")
                            
                            # --- INTERCETTAZIONE MINIGIOCO ---
                            if trigger:
                                mg_id = trigger.get("minigame_id")
                                if mg_id:
                                    # --- EFFETTO BURST PROFESSIONALE ---
                                    # Prendi posizione schermo del click per l'origine del burst
                                    cx, cy = event.pos[0], event.pos[1]
                                    
                                    def _on_burst_midpoint(mid_mg_id=mg_id, mid_hit=hit):
                                        success = self.minigame_manager.start_minigame(
                                            mid_mg_id, 
                                            on_complete=lambda res, h=mid_hit: self._on_minigame_complete(res, h)
                                        )
                                        if success:
                                            self.state = EngineState.MINIGAME
                                            self.logger.info(f">>> AVVIO MINIGIOCO: {mid_mg_id} via {mid_hit.instance_id}")
                                        else:
                                            self.logger.error(f"MANAGER: Fallito avvio minigioco {mid_mg_id}")
                                            self.state = EngineState.SCENE  # Fallback a scena se fallisce

                                    self.transition_manager.start_transition(
                                        TransitionType.CIRCLE_BURST,
                                        base_dur_out=0.8, # Esplosione cinematografica lenta e potente
                                        base_dur_in=0.6,   # Sfumatura di ingresso al minigioco
                                        cx=cx, cy=cy,
                                        on_midpoint=_on_burst_midpoint
                                    )
                                    # Aggiungiamo uno screen shake per dare "peso" all'esplosione
                                    self.effects.shake_screen(duration=0.8, intensity=8.0)
                                    continue

                            if hit.is_goal:
                                if self.hud.is_target_active(hit.instance_id):
                                    self.level_manager.register_found(hit.instance_id)
                                    
                                    # Calcola il CENTRO dell'oggetto per l'effetto
                                    if hit.detection_type == "rect":
                                        cx = hit.x + hit.width / 2
                                        cy = hit.y + hit.height / 2
                                    else:
                                        cx = hit.x
                                        cy = hit.y
                                        
                                    is_last_object = self.level_manager._found_count() == self.level_manager._total_count()
                                    if is_last_object:
                                        # Mega animazione epica per la fine del livello
                                        self.audio.play_sfx("engine/assets/sounds/victory.mp3")
                                        self.effects.spawn_final_found_effect(cx, cy)
                                        self.effects.shake_screen(duration=1.2, intensity=10.0)
                                    else:
                                        # Animazione standard
                                        self.audio.play_sfx("engine/assets/sounds/bling1.mp3")
                                        self.effects.spawn_found_effect(cx, cy)
                                else:
                                    self.audio.play_sfx("engine/assets/sounds/error4.mp3")
                                    self.logger.debug("Mancato: oggetto non in HUD")
                                    penalty = self.level_manager.register_miss()
                                    bx, by = self.scaling_manager.screen_to_bg(*event.pos)
                                    self.effects.spawn_score_popup(bx, by, penalty)
                        else:
                            # Click nel vuoto assoluto
                            self.audio.play_sfx("engine/assets/sounds/error4.mp3")
                            penalty = self.level_manager.register_miss()
                            # Trasforma click schermo in coordinate scena per le particelle
                            bx, by = self.scaling_manager.screen_to_bg(*event.pos)
                            self.effects.spawn_score_popup(bx, by, penalty)
                            self.logger.debug("Mancato / Click a vuoto")
                                
                    elif self.state == EngineState.RESULTS:
                        # Delega al ResultsScreen il controllo del click (gestisce layout e animazione)
                        if self.results_screen.check_click(event.pos):
                            self.audio.play_sfx("engine/assets/sounds/click_Low.wav")
                            self.transition_manager.start_transition(TransitionType.FADE_TO_BLACK, on_midpoint=self._advance_scene)
            
            elif event.type == pygame.MOUSEBUTTONUP:
                if event.button == 1: # Left click
                    if self.state in [EngineState.MENU, EngineState.PAUSE]:
                        # Salva volume se siamo usciti dal trascinamento
                        old_m, old_s = self.music_volume, self.sfx_volume
                        new_m, new_s = self.menu_system.music_volume, self.menu_system.sfx_volume
                        
                        if old_m != new_m or old_s != new_s:
                            # Se è cambiato il volume SFX, diamo un feedback sonoro
                            if old_s != new_s:
                                self.audio.play_sfx("engine/assets/sounds/click_Low.wav")
                                
                            self.music_volume = new_m
                            self.sfx_volume = new_s
                            self._apply_audio_settings(new_m, new_s)
                        
                        self.menu_system.release_click()
                        
            elif event.type == pygame.MOUSEMOTION:
                self.hud.on_mouse_activity()
                    
            elif event.type == SCENE_COMPLETE:
                self.logger.info("Ho ricevuto SCENE_COMPLETE. Transizione ai risultati...")
                self._last_result = getattr(event, "result", None)
                if self._last_result:
                    level_id = self.level_manager.current_level_id
                    self.save_manager.set_scene_score(
                        level_id, 
                        self._last_result.scene_id, 
                        self._last_result.score, 
                        self._last_result.stars
                    )
                    # --- SALVATAGGIO CHECKPOINT ---
                    # Salva sempre il checkpoint della prossima scena, anche se è l'ultima
                    # Il reset avviene quando l'utente torna al menu principale
                    next_scene_idx = self.level_manager._level_state.current_scene_index + 1
                    self.save_manager.set_progress("current_level", level_id)
                    self.save_manager.set_progress("current_scene_index", next_scene_idx)
                    
                    # Sblocca la prossima scena per la selezione manuale dal menu
                    self.save_manager.unlock_scene(level_id, next_scene_idx)
                self.audio.stop_music(fade_ms=1000)
                self.transition_manager.start_transition(TransitionType.FADE_TO_BLACK, on_midpoint=self._switch_to_results)
                
            elif event.type == LEVEL_COMPLETE:
                self.logger.info("Ho ricevuto LEVEL_COMPLETE. Salvo progressi e sblocco prossimo.")
                lvl_id = getattr(event, "level_id", self.level_manager.current_level_id)
                self.save_manager.unlock_level(lvl_id)
                
                # Sblocca il livello successivo nella gerarchia
                available_lvls = self.level_manager.get_available_levels()
                try:
                    curr_idx = available_lvls.index(lvl_id)
                    if curr_idx + 1 < len(available_lvls):
                        next_lvl_id = available_lvls[curr_idx + 1]
                        self.save_manager.unlock_level(next_lvl_id)
                        self.logger.info(f"Sbloccato livello successivo: {next_lvl_id}")
                except ValueError:
                    pass
                    
                self.transition_manager.start_transition(TransitionType.FADE_TO_BLACK, on_midpoint=self._switch_to_menu)
                
            elif event.type == SCENE_FAILED:
                self.logger.info("Ho ricevuto SCENE_FAILED. Transizione ai risultati...")
                self._last_result = getattr(event, "result", None)
                self.transition_manager.start_transition(TransitionType.FADE_TO_BLACK, on_midpoint=self._switch_to_results)
                    
            elif event.type == pygame.KEYDOWN:
                # Se è visibile una bubble, blocchiamo OGNI input da tastiera
                if self.level_manager.is_any_bubble_visible():
                    continue

                if event.key == pygame.K_ESCAPE:
                    self.logger.debug("Tasto ESC premuto")
                    # Se siamo nel menu o nel boot, ESC chiude l'app. 
                    # Altrimenti (Scene o Minigame), attiva/disattiva la pausa.
                    if self.state in [EngineState.BOOT, EngineState.MENU]:
                        self.running = False
                    else:
                        self._toggle_pause()

                elif event.key == pygame.K_h and self.state == EngineState.SCENE:
                    # Tasto H: Richiedi hint manuale
                    # [FIX] Controllo disponibilità hint prima dell'uso
                    if self.level_manager.get_available_hints() > 0:
                        is_flashlight = self._current_scene_data and getattr(self._current_scene_data, 'flashlight', False)
                        
                        success, penalty = self.hint.use_manual_hint(
                            self._current_scene_objects, 
                            suppress_fx=False
                        )
                        
                        if success:
                            self.level_manager.apply_score_penalty(penalty)
                            self.level_manager.consume_hint_from_rewards()  # Decrementa conteggio HUD
                            
                            if is_flashlight:
                                self._hint_flash_timer = 5.0
                                self.logger.info("Hint Flash attivato (Tasto H) per 5 secondi")
                            else:
                                # Popup vicino al mouse per il costo dell'hint (da tastiera)
                                bx, by = self.scaling_manager.screen_to_bg(*pygame.mouse.get_pos())
                                self.effects.spawn_score_popup(bx, by, penalty)
                                self.logger.info(f"Hint usato: penalità {penalty} pt")
                        else:
                            if self.hint.hints_used_total >= self.hint.max_hints_before_disable:
                                self.logger.debug("Numero massimo di hint raggiunto")
                            else:
                                self.logger.debug("Hint non disponibile (cooldown o nessun oggetto da cercare)")
                    else:
                        self.audio.play_sfx("engine/assets/sounds/UI_Forbidden.wav")
                        self.logger.warning("Tasto H: Nessun hint disponibile!")

                elif event.key == pygame.K_t and self.state == EngineState.SCENE:
                    # Tasto T: Mostra quale oggetto cercare (indicatore animato)
                    remaining = [o for o in self._current_scene_objects if o.is_goal and not o.found]
                    if remaining:
                        self.show_hint_indicator(remaining[0].instance_id)
                        self.logger.debug(f"Indicatore target: {remaining[0].label_key}")

    def _apply_display_settings(self, w: int, h: int, fullscreen: bool) -> None:
        """Applica risoluzione e screen mode alla finestra pygame e aggiorna configurazione."""
        self.is_fullscreen = fullscreen
        
        flags = pygame.DOUBLEBUF
        if self.is_fullscreen:
            flags |= pygame.FULLSCREEN
            
        self.logger.info(f"Applicazione Display Mode: {w}x{h} (Fullscreen: {fullscreen})")
        
        # Hack robusto per Windows: Ricrea il display context per forzare 
        # il resize fisico della finestra ed evitare bordi neri.
        pygame.display.quit()
        pygame.display.init()
        os.environ['SDL_VIDEO_CENTERED'] = '1'
        pygame.display.set_caption("Hidden Engine")
        
        # Sincronizzazione atomica: set_mode con i nuovi parametri e VSync
        self.screen = pygame.display.set_mode((w, h), flags, vsync=1)
        
        # Sincronizza tutti i manager con la nuova risoluzione
        self._handle_resize(w, h)
        
        # Scrivi persistenza su config.ini
        import configparser
        from engine.utils import get_base_path
        self.config.set("engine", "resolution_w", str(w))
        self.config.set("engine", "resolution_h", str(h))
        self.config.set("engine", "fullscreen", "1" if fullscreen else "0")
        try:
            with open(get_base_path() / "config.ini", "w") as f:
                self.config.write(f)
            self.logger.debug("Configurazione display salvata in config.ini")
        except Exception as e:
            self.logger.error(f"Errore durante il salvataggio della configurazione: {e}")

        # Se c'era resize_pending, lo abbiamo evaso con _handle_resize
        self.scaling_manager.consume_resize()

    def _apply_audio_settings(self, music_vol: float, sfx_vol: float) -> None:
        """Applica e persiste i settaggi audio."""
        self.audio.set_music_volume(music_vol)
        self.audio.set_sfx_volume(sfx_vol)
        
        # Scrivi persistenza su config.ini
        import configparser
        from engine.utils import get_base_path
        self.config.set("engine", "music_volume", f"{music_vol:.2f}")
        self.config.set("engine", "sfx_volume", f"{sfx_vol:.2f}")
        try:
            with open(get_base_path() / "config.ini", "w") as f:
                self.config.write(f)
            self.logger.debug(f"Volumi (M:{music_vol}, S:{sfx_vol}) salvati in config.ini")
        except Exception as e:
            self.logger.error(f"Errore durante il salvataggio del volume: {e}")

    def _update(self, dt: float) -> None:
        """Aggiorna la logica corrente (delegate to state)."""
        self.transition_manager.update(dt)
        
        if self.state == EngineState.MINIGAME:
            self.minigame_manager.update(dt)
            # Se il minigioco ha finito, il callback on_complete ci riporterà in SCENE
            return

        # State Dispatch logica
        if self.state == EngineState.BOOT:
            pass # Attende solo la fine del boot overlay
        elif self.state in [EngineState.MENU, EngineState.PAUSE]:
            # Hover sui bottoni controllato raw (anche in pausa)
            mx, my = pygame.mouse.get_pos()
            self.menu_system.update(dt, mx, my)
            
            # Se stiamo trascinando uno slider, aggiorna il volume in real-time
            if any(s.dragging for s in self.menu_system.sliders):
                self.audio.set_music_volume(self.menu_system.music_volume)
                self.audio.set_sfx_volume(self.menu_system.sfx_volume)
        elif self.state == EngineState.SCENE:
            self.effects.update(dt)
            self.fx_renderer.update(dt) # Sincronizzazione tempo per jittering e vibrazioni
            
            # Update FX e gestisci audio typewriter sincronizzato
            from engine.effect_renderer import update_effect_state
            for fx in self._current_scene_effects:
                if fx.type == "bubble_tip" and getattr(fx, "_visible", False):
                    # Recupera la lunghezza reale del testo per il blocco
                    text_str = self.lang.get(fx.text_key, fx.text_key)
                    max_chars = len(text_str)
                    
                    old_c = int(getattr(fx, "_chars_visible", 0))
                    update_effect_state(fx, dt)
                    
                    # Clamping: Impedisce di superare la lunghezza del testo e ferma il suono
                    curr_val = getattr(fx, "_chars_visible", 0.0)
                    if curr_val > max_chars:
                        setattr(fx, "_chars_visible", float(max_chars))
                        new_c = max_chars
                    else:
                        new_c = int(curr_val)
                    
                    # Suona solo se sono comparsi nuovi caratteri e non abbiamo finito
                    if new_c > old_c and old_c < max_chars:
                        # Suono ogni 2 caratteri per un ritmo costante e non eccessivo
                        if new_c % 2 == 0:
                            self.audio.play_sfx("engine/assets/sounds/click_Low.wav", vol=0.10)
                else:
                    update_effect_state(fx, dt)
                    
            self.level_manager.update(dt)

            # Cache mouse position per il frame (evita multiple get_pos() calls)
            mouse_pos = pygame.mouse.get_pos()
            self.hud.update(dt, mouse_pos, self.level_manager.time_elapsed, self.level_manager.scene_score, self.hint)

            # Aggiorna sistema hint (auto-hint + glow)
            # layer_hint_intensity è cachato in self._cached_layer_intensity
            self.hint.update(dt, self._current_scene_objects, self._cached_layer_intensity)

            # Aggiorna hint indicator animation
            if self._hint_indicator_target_obj:
                self._hint_indicator_timer += dt
                if self._hint_indicator_timer >= self._hint_indicator_duration:
                    self._hint_indicator_target_obj = None
                    self._hint_indicator_timer = 0.0

            # --- Gestione Intro Zoom ---
            if self._scene_intro_timer > 0:
                self._scene_intro_timer -= dt
                if self._scene_intro_timer <= 0:
                    self._scene_intro_timer = 0
                    # Attiva i fumetti di inizio scena quando lo zoom finisce
                    for fx in self._current_scene_effects:
                        if fx.type == "bubble_tip" and getattr(fx, "trigger", "") == "start_scene":
                            fx._visible = True
                            self.logger.info(f"Intro finita: attivato fumetto {fx.effect_id}")

            if self._spam_lock_timer > 0:
                self._spam_lock_timer -= dt
            
            # --- Aggiornamento Hint Flash ---
            if self._hint_flash_timer > 0:
                self._hint_flash_timer -= dt
                if self._hint_flash_timer <= 0:
                    self._hint_flash_timer = 0.0
                    self.logger.debug("Hint Flash terminato. Torcia ripristinata.")
            
        elif self.state == EngineState.RESULTS:
            # Aggiorna animazioni della schermata di risultati
            self.results_screen.update(dt)
            
    def _has_progress(self) -> bool:
        """Controlla se esistono progressi reali o un checkpoint nel salvataggio."""
        data = self.save_manager.data
        has_checkpoint = data.get("current_level") is not None
        # Progress reale se ha sbloccato più del primo livello 
        # (considerando che il primo lo sblocchiamo noi di default)
        has_real_unlocks = len(data.get("unlocked_levels", [])) > 1
        has_scores = any(len(v) > 0 for v in data.get("scores", {}).values())
        return has_checkpoint or has_real_unlocks or has_scores

    def _ensure_first_level_unlocked(self) -> None:
        """Garantisce che il primo livello sia sempre sbloccato se non ci sono progressi, oppure se il primo livello è cambiato/eliminato."""
        available = self.level_manager.get_available_levels()
        if available:
            first_level = available[0]
            unlocked = self.save_manager.get_progress("unlocked_levels", [])
            if first_level not in unlocked:
                self.save_manager.unlock_level(first_level)
                self.logger.info(f"Sbloccato livello iniziale di default: {first_level}")

    def _resume_from_save(self) -> None:
        """Riprende il gioco dall'ultimo checkpoint salvato."""
        lvl_id = self.save_manager.get_progress("current_level")
        idx = self.save_manager.get_progress("current_scene_index", 0)
        
        if not lvl_id:
            available = self.level_manager.get_available_levels()
            if available:
                lvl_id = available[0]
                idx = 0
            else:
                return
                
        self.logger.info(f"Resume richiesto: {lvl_id} alla scena index {idx}")
        self.scaling_manager.invalidate_cache()
        
        try:
            scene_data = self.level_manager.start_level(lvl_id, start_scene_index=idx)
        except Exception as e:
            self.logger.error(f"Errore resume {lvl_id}: {e}")
            available = self.level_manager.get_available_levels()
            if available:
                lvl_id = available[0]
                idx = 0
                scene_data = self.level_manager.start_level(lvl_id, start_scene_index=idx)
            else:
                return

        self._current_scene_data = scene_data
        self._current_scene_objects = scene_data.objects
        self._current_scene_effects = scene_data.effects
        self._current_bg_surface = scene_data.background_surface
        self._current_bg_scale = scene_data.background_scale

        if self._current_bg_surface:
            bw, bh = self._current_bg_surface.get_size()
            self.scaling_manager.set_background(bw, bh, self._current_bg_scale)
            
        self.hud.setup(self._current_scene_objects, self.level_manager.time_elapsed)
        self._play_scene_music(scene_data)
        self.state = EngineState.SCENE

    def _switch_to_menu(self) -> None:
        """Sincronizza core e menu_system verso lo stato principale."""
        # Reset checkpoint quando torni al menu principale
        self.save_manager.set_progress("current_level", None)
        self.save_manager.set_progress("current_scene_index", 0)
        self.state = EngineState.MENU
        self.menu_system.change_state("main", has_save=self._has_progress())
        self.logger.info("Entrato nello stato MENU (main).")

        # --- GESTIONE MUSICA MENU (PLAYLIST) ---
        menu_cfg = self.game_config.get("menu", {})
        music_list = menu_cfg.get("music", [])
        if isinstance(music_list, str): music_list = [music_list] # Fallback singolo brano
        
        if music_list:
            track = random.choice(music_list)
            # Costruzione normalizzata del percorso tramite Path (evita concatenazioni manuali)
            rel_path = Path("games") / self.game_id / track
            self.logger.info(f"Richiesta musica menu: {rel_path}")
            self.audio.play_music(rel_path, fade_ms=1000)
        else:
            self.audio.stop_music(fade_ms=500)
        
    def _switch_to_results(self) -> None:
        """Mostra tabellone score a fine scena."""
        self.state = EngineState.RESULTS
        self._results_timer = 4.0 # Autoavanza dopo 4 sec

        # Popola la schermata di risultati con i dati attuali
        if self._last_result:
            is_failed = getattr(self._last_result, 'failed', False)
            if not is_failed:
                self.audio.play_sfx("engine/assets/sounds/level_up.mp3")
            score = self._last_result.score
            stars = self._last_result.stars
            time_elapsed = self.level_manager.time_elapsed

            # Conta oggetti trovati
            objects_found = sum(1 for obj in self._current_scene_objects if obj.found and obj.is_goal)
            total_objects = sum(1 for obj in self._current_scene_objects if obj.is_goal)

            # Ottieni nome scena
            scene_name = getattr(self._last_result, 'scene_id', 'Scene')

            self.results_screen.show(
                score=score,
                stars=stars,
                time_elapsed=time_elapsed,
                is_failed=is_failed,
                scene_name=scene_name,
                objects_found=objects_found,
                total_objects=total_objects
            )
        else:
            # Fallback se non c'è result
            self.results_screen.show(score=0, stars=0, time_elapsed=0.0)
        
    def _advance_scene(self) -> None:
        self.scaling_manager.invalidate_cache()
        next_scene = self.level_manager.advance_to_next_scene()
        if next_scene:
            self._current_scene_data = next_scene
            self._current_scene_objects = next_scene.objects
            self._current_scene_effects = next_scene.effects
            self._current_bg_surface = next_scene.background_surface
            self._current_bg_scale = next_scene.background_scale
            # Aggiorna il mapping bg→screen (correzione: era mancante per le scene successive)
            if self._current_bg_surface:
                bw, bh = self._current_bg_surface.get_size()
                self.scaling_manager.set_background(bw, bh, self._current_bg_scale)
                self.logger.info(
                    f"Background avanzamento: {bw}x{bh}, scale={self._current_bg_scale}"
                )
            self.hud.setup(self._current_scene_objects, self.level_manager.time_elapsed)
            self._play_scene_music(next_scene)
            self.state = EngineState.SCENE
            self._scene_intro_timer = self._scene_intro_dur  # Avvia intro zoom
            self.logger.info("Avanzato alla scena successiva.")
        else:
            self._switch_to_menu()

    def _start_level(self, level_id: str, scene_id: str = None) -> None:
        """Carica un livello specifico e avvia la prima scena (o una specifica)."""
        self.logger.info(f"[GAME] Loading level: {level_id} (scene: {scene_id})...")
        self.scaling_manager.invalidate_cache()
        
        # Se è specificata una scena, dobbiamo trovarne l'indice
        start_idx = 0
        if scene_id:
            try:
                # Carichiamo il config per vedere l'ordine
                from engine.utils import get_resource_path
                import json
                cfg_p = get_resource_path("games", self.game_id, "levels", level_id, "level_config.json")
                if cfg_p.exists():
                    with open(cfg_p, "r", encoding="utf-8") as f:
                        cfg = json.load(f)
                        scenes = cfg.get("scenes", [])
                    for i, s in enumerate(scenes):
                        if s.get("id") == scene_id:
                            start_idx = i
                            break
            except: pass

        scene_data = self.level_manager.start_level(level_id, start_scene_index=start_idx)
        self._current_scene_data = scene_data
        self._current_scene_objects = scene_data.objects
        self._current_scene_effects = scene_data.effects
        self._current_bg_surface = scene_data.background_surface
        self._current_bg_scale = scene_data.background_scale

        # Registra le dimensioni del background nello scaling manager
        if self._current_bg_surface:
            bw, bh = self._current_bg_surface.get_size()
            self.scaling_manager.set_background(bw, bh, self._current_bg_scale)
            self.logger.debug(f"[GAME] Background: {bw}x{bh}, scene_scale={self._current_bg_scale}")

        # Attivazione HUD
        self.hud.setup(self._current_scene_objects, self.level_manager.time_elapsed)
        self._play_scene_music(scene_data)
        self.state = EngineState.SCENE
        self._scene_intro_timer = self._scene_intro_dur  # Avvia intro zoom
        self.logger.info(f"Livello '{level_id}' avviato con successo.")

    def _start_test_scene(self) -> None:
        """Carica il primo livello disponibile dinamicamente (fallback)."""
        available_lvls = self.level_manager.get_available_levels() 
        if not available_lvls:
            self.logger.error("Nessun livello trovato per questo gioco!")
            self._switch_to_menu()
            return
        self._start_level(available_lvls[0])

    def _play_scene_music(self, scene_data) -> None:
        """Avvia la musica della scena se presente, altrimenti ferma quella attuale."""
        if hasattr(scene_data, 'music') and scene_data.music:
            # Per ora prendiamo la prima traccia. 
            track_name = scene_data.music[0]
            # Percorso relativo agli asset del gioco costruito in modo OS-native
            music_path = Path("games") / self.game_id / "audio" / "music" / track_name
            self.audio.play_music(music_path, fade_ms=1000)
        else:
            self.logger.debug("Nessuna musica definita per questa scena.")
            self.audio.stop_music(fade_ms=1000)

    def _draw_hint_indicator(self) -> None:
        """Disegna indicatore target animato (cerchio azzurro pulsante) sull'oggetto suggerito."""
        if self.state != EngineState.SCENE or not self.level_manager:
            return

        sm = self.scaling_manager
        
        # Calcoliamo il fattore scenico attuale (se siamo in intro zoom)
        scenic_factor = 1.0
        if self._scene_intro_timer > 0:
            t = self._scene_intro_timer / self._scene_intro_dur
            scenic_factor = 1.0 + (t ** 3 * 0.25)

        for obj in self._current_scene_objects:
            if obj.found or not obj.is_goal:
                continue

            hint_intensity = self.hint.get_hint_intensity(obj.instance_id)
            if hint_intensity <= 0:
                continue

            # Calcola posizione centro oggetto
            if obj.detection_type == "rect":
                cx_bg = obj.x + obj.width / 2
                cy_bg = obj.y + obj.height / 2
                w_bg = obj.width
                h_bg = obj.height
            else:
                cx_bg = obj.x
                cy_bg = obj.y
                w_bg = obj.width if obj.width > 0 else obj.radius * 2
                h_bg = obj.height if obj.height > 0 else obj.radius * 2

            # IMPORTANTE: Usiamo bg_to_screen_scenic per allineare con lo zoom intro
            sx, sy = sm.bg_to_screen_scenic(cx_bg, cy_bg, scenic_factor)

            # Dimensione glow (leggermente più grande dell'oggetto, scalata)
            glow_size = int(max(w_bg, h_bg) * sm._bg_display_scale * 1.2 * scenic_factor)

            # Disegna cerchio glow azzurro pulsante CENTRATO
            glow_alpha = int(hint_intensity * 200)
            glow_surf = pygame.Surface((glow_size * 2, glow_size * 2), pygame.SRCALPHA)
            pygame.draw.circle(glow_surf, (100, 200, 255, glow_alpha), (glow_size, glow_size), glow_size, 3)

            # Posiziona la surface in modo che il cerchio sia centrato a (sx, sy)
            pos = (int(sx - glow_size), int(sy - glow_size))
            sh_x, sh_y = self.effects.shake_offset
            self.screen.blit(glow_surf, (pos[0] + sh_x, pos[1] + sh_y))

    def _draw_hint_count(self) -> None:
        """Disegna conteggio hint con design glassmorphism premium."""
        if self.state != EngineState.SCENE or not self.level_manager:
            return

        available_hints = self.level_manager.get_available_hints()
        sm = self.scaling_manager

        # Costanti glassmorphism (coerente con HudManager)
        COLOR_BG = (15, 15, 25, 180)
        COLOR_BORDER = (80, 80, 110, 200)
        COLOR_ACCENT = (255, 215, 0)  # Gold
        COLOR_TEXT = (230, 235, 245)  # Off-white
        # Panel dimensioni (ancora più piccoli)
        panel_w = sm.scale_value(90)
        panel_h = sm.scale_value(55)
        panel_x = self.res_w - panel_w - sm.scale_value(20)
        panel_y = sm.scale_value(10)

        # Salva rettangolo per click detection (serve se il panel diventa clikkabile)
        self._hint_panel_rect = pygame.Rect(panel_x, panel_y, panel_w, panel_h)

        # Crea superficie trasparente per il panel
        panel_surf = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)

        # Disegna background con border radius
        pygame.draw.rect(panel_surf, COLOR_BG, (0, 0, panel_w, panel_h), border_radius=sm.scale_value(8))
        pygame.draw.rect(panel_surf, COLOR_BORDER, (0, 0, panel_w, panel_h), max(1, sm.scale_value(1)), border_radius=sm.scale_value(8))

        # Disegna il numero hint con Gold accent
        font_number = pygame.font.SysFont("segoeui", sm.scale_value(30), bold=True)
        hint_surf = font_number.render(str(available_hints), True, COLOR_ACCENT)
        hint_rect = hint_surf.get_rect(center=(panel_w // 2, sm.scale_value(22)))
        panel_surf.blit(hint_surf, hint_rect)

        # Disegna label "HINTS" in Off-white
        font_label = pygame.font.SysFont("segoeui", sm.scale_value(9), bold=False)
        label_surf = font_label.render("HINTS AVAILABLE", True, COLOR_TEXT)
        label_rect = label_surf.get_rect(center=(panel_w // 2, sm.scale_value(44)))
        panel_surf.blit(label_surf, label_rect)

        # Blit panel sulla schermata
        self.screen.blit(panel_surf, (panel_x, panel_y))

    def _draw_hint_button(self) -> None:
        """Disegna bottone hint con design glassmorphism premium e progress bar integrato."""
        if self.state != EngineState.SCENE:
            return

        sm = self.scaling_manager

        # Costanti glassmorphism (coerente con HudManager)
        COLOR_BG = (15, 15, 25, 180)
        COLOR_BORDER = (80, 80, 110, 200)
        COLOR_ACCENT = (255, 215, 0)  # Gold
        COLOR_TEXT = (230, 235, 245)  # Off-white
        COLOR_SUCCESS = (60, 240, 120)  # Emerald
        COLOR_DANGER = (220, 40, 40)  # Crimson
        BORDER_RADIUS = sm.scale_value(10)

        # Panel dimensioni e posizione (ancora più compatto)
        panel_w = sm.scale_value(90)
        panel_h = sm.scale_value(80)
        panel_x = self.res_w - panel_w - sm.scale_value(20)
        panel_y = sm.scale_value(73)   # 10 (top) + 55 (h_count) + 8 (gap)

        # Salva rettangolo per click detection
        btn_y_off = sm.scale_value(8)
        btn_h = sm.scale_value(30)
        self._hint_button_rect = pygame.Rect(panel_x + sm.scale_value(5), panel_y + btn_y_off, panel_w - sm.scale_value(10), btn_h)

        # Crea superficie trasparente
        panel_surf = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)

        # Disegna background con border radius
        pygame.draw.rect(panel_surf, COLOR_BG, (0, 0, panel_w, panel_h), border_radius=sm.scale_value(8))
        pygame.draw.rect(panel_surf, COLOR_BORDER, (0, 0, panel_w, panel_h), max(1, sm.scale_value(1)), border_radius=sm.scale_value(8))

        is_max_used = self.hint.hints_used_total >= self.hint.max_hints_before_disable
        cooldown_time = self.hint.manual_hint_cooldown
        available_hints = self.level_manager.get_available_hints()

        # Determina colore del bottone basato sullo stato (Maggiore trasparenza: alpha 140)
        if is_max_used:
            btn_bg_color = (100, 100, 110, 140)
            btn_text_color = (160, 160, 170)
            btn_text = "DISABLED"
            progress_color = (120, 120, 140)
        elif available_hints <= 0:
            btn_bg_color = (80, 80, 90, 140)
            btn_text_color = (140, 140, 150)
            btn_text = "EMPTY"
            progress_color = (100, 100, 110)
        elif cooldown_time > 0:
            btn_bg_color = (220, 40, 40, 140)
            btn_text_color = (255, 200, 200)
            btn_text = "WAIT"
            progress_color = (220, 100, 100)
        else:
            btn_bg_color = (60, 240, 120, 140)  # Maggiore trasparenza richiesta
            btn_text_color = (20, 80, 60)
            btn_text = "HINT"
            progress_color = (100, 255, 180)

        # Disegna pulsante (rettangolo arrotondato)
        btn_rect = pygame.Rect(sm.scale_value(5), btn_y_off, panel_w - sm.scale_value(10), btn_h)
        pygame.draw.rect(panel_surf, btn_bg_color, btn_rect, border_radius=sm.scale_value(6))
        pygame.draw.rect(panel_surf, COLOR_BORDER, btn_rect, max(1, sm.scale_value(1)), border_radius=sm.scale_value(6))

        # Testo sul bottone
        font_btn = pygame.font.SysFont("segoeui", sm.scale_value(11), bold=True)
        btn_label = font_btn.render(btn_text, True, btn_text_color)
        btn_label_rect = btn_label.get_rect(center=(panel_w // 2, btn_y_off + btn_h // 2))
        panel_surf.blit(btn_label, btn_label_rect)

        # Progress bar per hint earning
        progress_y = btn_y_off + btn_h + sm.scale_value(6)
        progress_w = panel_w - sm.scale_value(10)
        progress_h = max(2, sm.scale_value(3))
        progress_x = sm.scale_value(5)

        # Background della progress bar
        pygame.draw.rect(panel_surf, (40, 40, 50, 130), (progress_x, progress_y, progress_w, progress_h), border_radius=sm.scale_value(1))

        # Fill della progress bar
        reward_tracker = self.level_manager.get_reward_tracker()
        if reward_tracker and not is_max_used:
            progress = reward_tracker.get_earn_progress()
            if progress > 0:
                fill_w = int(progress_w * progress)
                pygame.draw.rect(panel_surf, (*progress_color[:3], 140), (progress_x, progress_y, fill_w, progress_h), border_radius=sm.scale_value(1))

        # Testo informativo sotto progress bar
        info_y = progress_y + progress_h + sm.scale_value(10)
        font_info = pygame.font.SysFont("segoeui", sm.scale_value(10), bold=True)

        if is_max_used:
            info_text = "Max used"
            info_color = (200, 120, 120)
        elif available_hints <= 0:
            info_text = "No hints"
            info_color = (180, 180, 190)
        elif cooldown_time > 0:
            info_text = f"{cooldown_time:.1f}s"
            info_color = (255, 180, 120)
        else:
            info_text = "Ready"
            info_color = (150, 240, 150)

        info_surf = font_info.render(info_text, True, info_color)
        info_rect = info_surf.get_rect(center=(panel_w // 2, info_y))
        panel_surf.blit(info_surf, info_rect)

        # Blit panel sulla schermata
        self.screen.blit(panel_surf, (panel_x, panel_y))

    def _draw_hint_indicator(self) -> None:
        """Disegna indicatore target animato (solo durante animazione, dopo il conteggio)."""
        if not self._hint_indicator_target_obj or self.state != EngineState.SCENE:
            return

        sm = self.scaling_manager

        # Calcola alpha basato su fade-out (ultimo 0.2 secondi)
        fade_start = self._hint_indicator_duration - 0.2
        if self._hint_indicator_timer >= fade_start:
            # Fade out negli ultimi 0.2 secondi
            fade_progress = (self._hint_indicator_timer - fade_start) / 0.2
            alpha = int(255 * (1.0 - fade_progress))
        else:
            alpha = 255

        # Trova l'oggetto target
        target_obj = None
        for obj in self._current_scene_objects:
            if obj.instance_id == self._hint_indicator_target_obj:
                target_obj = obj
                break

        if not target_obj:
            return

        # Crea testo con nome oggetto
        font = pygame.font.SysFont("segoeui", sm.scale_value(20), italic=True)
        label_text = self.lang(target_obj.label_key).upper()
        hint_text = f"{self.lang('hud_hint_seek')}: {label_text}"

        # Render con alpha
        hint_surf = font.render(hint_text, True, (100, 200, 255))
        hint_surf.set_alpha(alpha)

        # Posiziona in alto a destra, SOTTO il conteggio hint
        x = self.res_w - hint_surf.get_width() - sm.scale_value(20)
        self.screen.blit(hint_surf, (x, sm.scale_value(240)))

    def show_hint_indicator(self, obj_instance_id: str) -> None:
        """Mostra l'indicatore hint per l'oggetto specificato per mezzo secondo."""
        if self.state == EngineState.SCENE:
            self._hint_indicator_target_obj = obj_instance_id
            self._hint_indicator_timer = 0.0

    def _draw(self) -> None:
        """Renderizza la logica corrente (delegate to state)."""
        if self.state == EngineState.MINIGAME:
            self.minigame_manager.draw()
        elif self.state == EngineState.BOOT:
            self.screen.fill((10, 10, 15)) # Colore splash
        elif self.state == EngineState.MENU:
            self.screen.fill((20, 20, 25)) # Sfondo base scuro
            
            menu_cfg = self.game_config.get("menu", {})
            bg_path = menu_cfg.get("background")
            
            if bg_path:
                from engine.utils import get_resource_path
                import os
                abs_bg = str(get_resource_path("games", self.game_id, bg_path))
                
                # --- Gestione VIDEO MP4/MOV/MKV ---
                if abs_bg.lower().endswith((".mp4", ".mov", ".mkv")):
                    import cv2
                    # Inizializzazione Lazy del Capture
                    if self._menu_video_path != abs_bg:
                        if self._menu_video_cap: self._menu_video_cap.release()
                        self._menu_video_cap = cv2.VideoCapture(abs_bg)
                        self._menu_video_path = abs_bg
                    
                    if self._menu_video_cap and self._menu_video_cap.isOpened():
                        ret, frame = self._menu_video_cap.read()
                        if not ret: # Loop video
                            self._menu_video_cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                            ret, frame = self._menu_video_cap.read()
                        
                        if ret:
                            # OpenCV usa BGR, Pygame usa RGB
                            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                            # Trasponiamo per pygame
                            frame = frame.transpose(1, 0, 2)
                            self._menu_video_surface = pygame.surfarray.make_surface(frame)
                            
                            # Scaling (NO CACHE per il video, altrimenti si blocca sul primo frame!)
                            target_w, target_h = 1280.0, 720.0
                            scaled_v = self.scaling_manager.scale_surface_to_ref(
                                self._menu_video_surface, target_w, target_h, cache_key=None
                            )
                            self.screen.blit(scaled_v, (self.scaling_manager.offset_x, self.scaling_manager.offset_y))
                
                # --- Gestione IMMAGINE STATICA ---
                else:
                    if not hasattr(self, '_menu_bg_surface') or self._menu_video_path:
                        self._menu_video_path = None # Reset se passiamo da video a immagine
                        if os.path.exists(abs_bg):
                            self._menu_bg_surface = pygame.image.load(abs_bg).convert()
                        else:
                            self._menu_bg_surface = None
                    
                    if hasattr(self, '_menu_bg_surface') and self._menu_bg_surface:
                        target_w, target_h = 1280.0, 720.0
                        scaled_menu_bg = self.scaling_manager.scale_surface_to_ref(
                            self._menu_bg_surface, target_w, target_h, cache_key="menu_bg"
                        )
                        self.screen.blit(scaled_menu_bg, (self.scaling_manager.offset_x, self.scaling_manager.offset_y))

            self.menu_system.draw(self.screen)
            
        elif self.state == EngineState.SCENE:
            sm = self.scaling_manager
            
            # ── Intro Scaling (Chirurgico) ────────────────────────────────────
            is_intro_zooming = False
            zoom_factor = 1.0

            if self._scene_intro_timer > 0:
                is_intro_zooming = True
                # Easing t^3 per un effetto cinematico (decelerazione morbida)
                t = self._scene_intro_timer / self._scene_intro_dur
                zoom_factor = 1.0 + (t ** 3 * 0.25) # Zoom del 25% con curva cubica
            
            scenic_factor = 1.0  # Forza sempre 1.0 per evitare il distacco (drift) tra oggetti e sfondo

            original_screen = self.screen
            if is_intro_zooming:
                render_target = pygame.Surface(original_screen.get_size())
                render_target.fill((0, 0, 0))
                self.screen = render_target
            else:
                self.screen.fill((0, 0, 0))  # Sfondo nero (letterbox)

            # ── Background ─────────────────────────────────────────────────────
            # Priorità 1: Video Background (Scene)
            bg_v_path = getattr(self._current_scene_data, "background_path", "")
            is_scene_vid = bg_v_path.lower().endswith((".mp4", ".mov", ".mkv"))
            
            if is_scene_vid and os.path.exists(bg_v_path):
                import cv2
                # Inizializzazione Lazy del Capture per la scena
                # Riutilizziamo _menu_video_cap se possibile o ne creiamo uno separato per consistenza
                if getattr(self, "_scene_video_path", None) != bg_v_path:
                    if hasattr(self, "_scene_video_cap") and self._scene_video_cap: self._scene_video_cap.release()
                    self._scene_video_cap = cv2.VideoCapture(bg_v_path)
                    self._scene_video_path = bg_v_path
                
                if self._scene_video_cap and self._scene_video_cap.isOpened():
                    ret, frame = self._scene_video_cap.read()
                    if not ret: # Loop video
                        self._scene_video_cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                        ret, frame = self._scene_video_cap.read()
                    
                    if ret:
                        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                        frame = frame.transpose(1, 0, 2)
                        v_surf = pygame.surfarray.make_surface(frame)
                        target_w, target_h = 1280.0, 720.0
                        scaled_v = sm.scale_surface_to_ref(v_surf, target_w, target_h, cache_key=None)
                        bx, by, _, _ = sm.get_scenic_params(scenic_factor)
                        sh_x, sh_y = self.effects.shake_offset
                        self.screen.blit(scaled_v, (int(bx) + sh_x, int(by) + sh_y))
            
            # Priorità 2: Immagine Statica (Scene)
            elif hasattr(self, '_current_bg_surface') and self._current_bg_surface:
                bx, by, bw, bh = sm.get_scenic_params(scenic_factor)
                bx, by, bw, bh = int(bx), int(by), int(bw), int(bh)

                std_bw, std_bh = int(sm._bg_screen_w), int(sm._bg_screen_h)

                if not hasattr(self, '_base_bg_scaled') or self._base_bg_params != (std_bw, std_bh, self._current_bg_surface):
                    self._base_bg_scaled = pygame.transform.smoothscale(self._current_bg_surface, (std_bw, std_bh))
                    self._base_bg_params = (std_bw, std_bh, self._current_bg_surface)
                
                scaled_bg = self._base_bg_scaled if scenic_factor == 1.0 else pygame.transform.scale(self._base_bg_scaled, (bw, bh))
                sh_x, sh_y = self.effects.shake_offset
                self.screen.blit(scaled_bg, (bx + sh_x, by + sh_y))

            # ── Oggetti ────────────────────────────────────────────────────────
            if not hasattr(self, '_debug_logged_objects'):
                self.logger.info(f"[GAME] Rendering {len([o for o in self._current_scene_objects if not o.found])} active objects")
                self._debug_logged_objects = True

            for obj in self._current_scene_objects:
                if obj.found or not obj.icon_surface:
                    continue

                # Centro in bg-space
                # NOTA: per i cerchi, se l'editor ha impostato width/height espliciti
                # (es. dopo un resize degli handle), usiamo quelli; altrimenti radius*2.
                if obj.detection_type == "rect":
                    cx_bg = obj.x + obj.width / 2
                    cy_bg = obj.y + obj.height / 2
                    hit_w_bg = obj.width
                    hit_h_bg = obj.height
                else:
                    cx_bg = obj.x
                    cy_bg = obj.y
                    raw_w = obj.width if obj.width > 0 else obj.radius * 2
                    raw_h = obj.height if obj.height > 0 else obj.radius * 2
                    hit_w_bg = raw_w
                    hit_h_bg = raw_h

                # Centro → screen (Versione Scenica)
                sx, sy = sm.bg_to_screen_scenic(cx_bg, cy_bg, scenic_factor)

                # Dimensione icona a schermo: hit-area in bg-space → pixel
                icon_w = max(1, int(hit_w_bg * sm._bg_display_scale * scenic_factor))
                icon_h = max(1, int(hit_h_bg * sm._bg_display_scale * scenic_factor))

                # Clamp dimensioni per evitare artefatti da over-scaling
                # Non superare 3000px per evitare memory overhead e artefatti visivi
                MAX_ICON_DIM = 3000
                draw_w = min(icon_w, MAX_ICON_DIM)
                draw_h = min(icon_h, MAX_ICON_DIM)

                # Se la dimensione richiesta era troppo grande, avvisiamo in log
                if icon_w > MAX_ICON_DIM or icon_h > MAX_ICON_DIM:
                    log.warning(
                        "Icon too large for '%s': requested %dx%d, clamped to %dx%d",
                        obj.catalog_id, icon_w, icon_h, draw_w, draw_h
                    )

                # --- Ottimizzazione: Cache dell'Oggetto ---
                obj_params = (
                    draw_w, draw_h, obj.rotation, obj.flip_x, obj.flip_y, 
                    obj.alpha, tuple(obj.color_filter), str(obj.corners),
                    getattr(obj, "grayscale", False), getattr(obj, "grayscale_factor", 1.0)
                )
                if obj._cached_surface is None or obj._cached_params != obj_params:
                    # Ricalcola la surface scalata e trasformata
                    render_surf = pygame.transform.smoothscale(obj.icon_surface, (draw_w, draw_h))
                    
                    has_warp = any(c[0] != 0 or c[1] != 0 for c in obj.corners)
                    warp_dx, warp_dy = 0, 0
                    if has_warp:
                        sx_scale = draw_w / hit_w_bg if hit_w_bg > 0 else sm._bg_display_scale
                        sy_scale = draw_h / hit_h_bg if hit_h_bg > 0 else sm._bg_display_scale
                        # Nota: warp_surface deve essere importata o disponibile (è in utils)
                        from engine.utils import warp_surface
                        q_scaled = [
                            (obj.corners[0][0] * sx_scale, obj.corners[0][1] * sy_scale),
                            (draw_w + obj.corners[1][0] * sx_scale, obj.corners[1][1] * sy_scale),
                            (draw_w + obj.corners[2][0] * sx_scale, draw_h + obj.corners[2][1] * sy_scale),
                            (obj.corners[3][0] * sx_scale, draw_h + obj.corners[3][1] * sy_scale),
                        ]
                        warp_dx = min(p[0] for p in q_scaled)
                        warp_dy = min(p[1] for p in q_scaled)
                        render_surf = warp_surface(render_surf, q_scaled)
                    
                    if obj.flip_x or obj.flip_y:
                        render_surf = pygame.transform.flip(render_surf, obj.flip_x, obj.flip_y)
                    if obj.rotation != 0:
                        render_surf = pygame.transform.rotozoom(render_surf, obj.rotation, 1.0)
                    
                    # --- FILTRO BIANCO E NERO (Grayscale) ---
                    if getattr(obj, "grayscale", False):
                        gs_f = getattr(obj, "grayscale_factor", 1.0)
                        self.logger.info(f"[RENDER] Grayscale active for {obj.instance_id} (factor={gs_f})")
                        render_surf = apply_grayscale(render_surf, gs_f)

                    
                    # 4. Filtro Colore (per-pixel multipliers)
                    if tuple(obj.color_filter) != (255, 255, 255):
                        tint = pygame.Surface(render_surf.get_size(), pygame.SRCALPHA)
                        tint.fill((*obj.color_filter, 255))
                        render_surf.blit(tint, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)

                    # 5. Opacitá (Surface-level alpha) - Per ultima per evitare double-multiplication
                    if obj.alpha < 255:
                        render_surf.set_alpha(obj.alpha)
                    
                    obj._cached_surface = render_surf
                    obj._cached_params = obj_params
                    obj._warp_offset = (warp_dx, warp_dy)

                final_surf = obj._cached_surface
                iw, ih = final_surf.get_size()
                warp_dx, warp_dy = getattr(obj, "_warp_offset", (0, 0))
                
                has_warp = any(c[0] != 0 or c[1] != 0 for c in obj.corners)
                if has_warp and obj.rotation == 0:
                    pos = (int(sx - draw_w / 2 + warp_dx), int(sy - draw_h / 2 + warp_dy))
                else:
                    # Posizionamento con arrotondamento preciso e Screen Shake integrato
                    sh_x, sh_y = self.effects.shake_offset
                    pos = (int(round(sx - iw / 2 + sh_x)), int(round(sy - ih / 2 + sh_y)))
                
                self.screen.blit(final_surf, pos)

            # Glow overlay rimosso — feedback visuale dato dalle particelle soltanto
            # self._draw_hint_glow_overlays()

            self.effects.draw(self.screen)
            # 1. Rendering Effetti Ambientali (Sotto la maschera torcia)
            env_fx = [f for f in self._current_scene_effects if getattr(f, "type", "") != "bubble_tip"]
            self.fx_renderer.draw(self.screen, env_fx, sm, self.lang, scenic_factor)
            
            if is_intro_zooming:
                self.screen = original_screen
                # Trasforma l'intero render_target come un'unica immagine unita e centralo!
                tw = int(render_target.get_width() * zoom_factor)
                th = int(render_target.get_height() * zoom_factor)
                scaled_rt = pygame.transform.smoothscale(render_target, (tw, th))
                
                cx = self.screen.get_width() // 2
                cy = self.screen.get_height() // 2
                rx = cx - tw // 2
                ry = cy - th // 2
                self.screen.fill((0, 0, 0))
                self.screen.blit(scaled_rt, (rx, ry))

            # --- EFFETTO TORCIA (FLASHLIGHT) ---
            # Viene applicato dopo lo zoom ma PRIMA degli effetti/HUD affinché le particelle
            # (come gli hint) siano visibili anche sopra l'oscurità.
            if self._current_scene_data and getattr(self._current_scene_data, 'flashlight', False):
                # Se l'Hint Flash è attivo, saltiamo il disegno dell'oscurità
                if self._hint_flash_timer > 0:
                    self._draw_hint_flash_timer()
                else:
                    self._draw_flashlight_effect()

            # --- EFFETTI E PARTICELLE (Sempre visibili sopra la torcia) ---
            self.effects.draw(self.screen)
            env_fx = [f for f in self._current_scene_effects if getattr(f, "type", "") != "bubble_tip"]
            self.fx_renderer.draw(self.screen, env_fx, sm, self.lang, scenic_factor=zoom_factor if is_intro_zooming else 1.0)

            # --- UI E FUMETTI (Sempre in primo piano) ---
            ui_fx = [f for f in self._current_scene_effects if getattr(f, "type", "") == "bubble_tip"]
            self._last_bubble_btns = self.fx_renderer.draw(self.screen, ui_fx, sm, self.lang, scenic_factor)
            
            self.hud.draw(self.screen, pygame.time.get_ticks() / 1000.0)

            # Disegna conteggio hint in alto a destra (sempre visibile)
            self._draw_hint_count()

            # Disegna bottone hint in alto a destra
            self._draw_hint_button()

            # Disegna indicatore target animato (su richiesta)
            self._draw_hint_indicator()
            
            # Overlay Lockdown per Anti-Spam
            if self._spam_lock_timer > 0:
                lock_surf = pygame.Surface(self.screen.get_size(), pygame.SRCALPHA)
                alpha = int(abs(math.sin(pygame.time.get_ticks() * 0.01)) * 40 + 20)
                lock_surf.fill((200, 0, 0, alpha))
                self.screen.blit(lock_surf, (0, 0))
            
        elif self.state == EngineState.PAUSE:
            # Pausa: oscuramento TOTALE per evitare "cheating" (vedere la scena a tempo fermo)
            self.screen.fill((10, 10, 15)) # Sfondo molto scuro (quasi nero)
            
            # Overlay vignetting per profondità e premium feel
            overlay = pygame.Surface((self.res_w, self.res_h), pygame.SRCALPHA)
            pygame.draw.rect(overlay, (0, 0, 0, 120), (0, 0, self.res_w, self.res_h))
            self.screen.blit(overlay, (0, 0))
            
            # Il menu system disegna i bottoni (Riprendi, Impostazioni, Esci) sopra l'oscuramento
            self.menu_system.draw(self.screen)
            
        elif self.state == EngineState.RESULTS:
            # Sfondo scuro per la schermata di risultati
            self.screen.fill((10, 10, 15))

            # Disegna la schermata di risultati premium
            self.results_screen.draw(self.screen)
                
        # Overlay grafico transizioni renderizzato SOPRA il resto
        self.transition_manager.draw(self.screen)
        
        pygame.display.flip()

    def _draw_flashlight_effect(self) -> None:
        """Disegna una maschera d'oscuramento con un buco luminoso sfumato attorno al mouse."""
        if not self._current_scene_data:
            return

        # 1. Creazione/Recupero maschera base (nera, semi-transparente)
        if self._flashlight_mask is None or self._flashlight_mask.get_size() != self.screen.get_size():
            self._flashlight_mask = pygame.Surface(self.screen.get_size(), pygame.SRCALPHA)
            
        # Reset maschera a nero TOTALE (0,0,0, 255)
        # Questo garantisce che tutto ciò che è coperto sia invisibile (non renderizzato visivamente)
        self._flashlight_mask.fill((0, 0, 0, 255)) 
        
        # 2. Coordinate mouse
        mx, my = pygame.mouse.get_pos()
        # Ampliamo leggermente il raggio nominale (+15%) per una visione più confortevole
        radius = int(self._current_scene_data.flashlight_radius * 1.15)
        
        # 3. Creazione/Recupero del "buco" sfumato (Cache per prestazioni)
        if self._flashlight_hole_cache is None or self._flashlight_cached_rad != radius:
            import numpy as np
            size = radius * 2
            hole = pygame.Surface((size, size), pygame.SRCALPHA)
            
            # Coordinate centrate -1 a +1
            ax = np.linspace(-1, 1, size)
            ay = np.linspace(-1, 1, size)
            gx, gy = np.meshgrid(ax, ay)
            dist = np.sqrt(gx**2 + gy**2)
            
            # Funzione di falloff premium (0 al centro -> 255 al raggio)
            alpha_arr = np.clip(np.power(dist, 1.4) * 255, 0, 255).astype(np.uint8)
            
            # Fuori dal cerchio = oscurità totale (rispetto alla maschera)
            alpha_arr[dist > 1.0] = 255
            
            # Trasferiamo l'array all'alpha della surface
            pygame.surfarray.pixels_alpha(hole)[:] = alpha_arr.T
            # RGB a zero per coordinarsi col nero della maschera
            pygame.surfarray.pixels3d(hole)[:] = 0

            self._flashlight_hole_cache = hole
            self._flashlight_cached_rad = radius
            self.logger.debug(f"Rigenerato cache torcia (total darkness): r={radius}")

        # 4. Applica il buco alla maschera usando BLEND_RGBA_MIN
        # La maschera base ha alpha 255. 
        # Al centro della torcia: MIN(255, 0) = 0 (trasparente -> si vede la scena)
        # Fuori: MIN(255, 255) = 255 (nero coprente -> nulla viene renderizzato visivamente)
        self._flashlight_mask.blit(self._flashlight_hole_cache, 
                                 (mx - radius, my - radius), 
                                 special_flags=pygame.BLEND_RGBA_MIN)

        # 5. Rendering finale sopra la scena (copre fumo, glint, etc. se fuori dalla luce)
        self.screen.blit(self._flashlight_mask, (0, 0))

    def _draw_hint_flash_timer(self) -> None:
        """Disegna il countdown numerico al centro dello schermo durante il Flash."""
        timer_val = int(math.ceil(self._hint_flash_timer))
        if timer_val <= 0: return
        
        # Uso font Segoe UI Black o Impact per un look premium
        font_size = int(self.scaling_manager.scale_value(120))
        try:
            font = pygame.font.SysFont("segoe ui black", font_size)
        except:
            font = pygame.font.SysFont("impact", font_size)
            
        text = str(timer_val)
        cx, cy = self.screen.get_width() // 2, self.screen.get_height() // 2
        
        # Rendering con Outline per visibilità perfetta su ogni sfondo
        offsets = [(-3, -3), (3, -3), (-3, 3), (3, 3), (0, -3), (0, 3), (-3, 0), (3, 0)]
        for ox, oy in offsets:
            out_s = font.render(text, True, (20, 20, 30))
            self.screen.blit(out_s, (cx + ox - out_s.get_width()//2, cy + oy - out_s.get_height()//2))
            
        # Testo principale (Bianco con pulsazione alpha)
        alpha = int(180 + math.sin(pygame.time.get_ticks() * 0.01) * 75)
        main_s = font.render(text, True, (255, 255, 255))
        main_s.set_alpha(alpha)
        self.screen.blit(main_s, (cx - main_s.get_width()//2, cy - main_s.get_height()//2))

    def _on_minigame_complete(self, result: dict, obj) -> None:
        """Ritorna alla scena e gestisce i risultati del minigioco."""
        self.state = EngineState.SCENE
        success = result.get("success", False)
        added_score = result.get("score", 0)
        self.logger.info(f"Ritorno alla scena. Successo: {success}, Score: {added_score}")

        # Aggiungiamo SEMPRE il punteggio se presente
        if added_score > 0:
            self.level_manager.add_score(added_score)

        # L'oggetto che ha triggerato il minigioco deve sparire dalla scena al termine,
        # indipendentemente dall'esito, per segnalare che l'interazione è conclusa.
        # Se l'oggetto è un obiettivo, va registrato come trovato per il progresso del livello.
        self.level_manager.register_found(obj.instance_id)
        obj.found = True 

        if success:
            self.audio.play_sfx("engine/assets/sounds/victory.mp3")
            
            # Effetto visivo di ritrovamento
            cx = obj.x + (obj.width / 2 if obj.detection_type == "rect" else 0)
            cy = obj.y + (obj.height / 2 if obj.detection_type == "rect" else 0)
            self.effects.spawn_found_effect(cx, cy)
            self.effects.shake_screen(duration=0.5, intensity=5.0)
        else:
            # Se ha fallito, sparisce comunque (consumato) ma con un feedback più neutro
            self.audio.play_sfx("engine/assets/sounds/bling1.mp3")

    def _toggle_pause(self) -> None:
        """Gestisce il passaggio tra gioco (SCENE o MINIGAME) e MENU PAUSA."""
        if self.state in [EngineState.SCENE, EngineState.MINIGAME]:
            # Salviamo lo stato corrente per poter tornare correttamente dopo la pausa
            self._state_before_pause = self.state
            self.menu_system.change_state("pause", has_save=self._has_progress())
            self.state = EngineState.PAUSE
            self.logger.info(f"Gioco in pausa (da stato: {self._state_before_pause}).")
        elif self.state == EngineState.PAUSE:
            # Ripristiniamo lo stato precedente o SCENE come fallback
            self.state = getattr(self, "_state_before_pause", EngineState.SCENE)
            self.logger.info(f"Gioco ripreso (ritorno a: {self.state}).")

    def _quit(self) -> None:
        """Shutdown pulito."""
        self.logger.info("Chiusura del motore Pygame.")
        if hasattr(self, '_menu_video_cap') and self._menu_video_cap:
            self._menu_video_cap.release()
        pygame.quit()
        sys.exit(0)
