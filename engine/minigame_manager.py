"""
engine/minigame_manager.py

Gestore per il caricamento dinamico e l'esecuzione dei minigiochi.
Agisce come uno strato intermedio tra il Core dell'Engine e le classi dei Minigiochi.
"""

import json
import importlib
import pygame
from pathlib import Path
from engine.utils import get_logger, get_resource_path

log = get_logger(__name__)

class MinigameManager:
    def __init__(self, screen: pygame.Surface, scaling_manager, audio_manager, lang_manager) -> None:
        self.screen = screen
        self.scaling_manager = scaling_manager
        self.audio = audio_manager
        self.lang = lang_manager
        self.current_minigame = None
        self._current_mg_id = "" # Cache dell'ID attivo per ricaricamento lingua
        self._on_complete_callback = None
        self._is_running = False
        
        # UI Pausa globale per tutti i minigiochi
        self._pause_btn_rect = pygame.Rect(0, 0, 0, 0)
        self._pause_btn_hovered = False
        self._calculate_pause_rect()

    def _calculate_pause_rect(self) -> None:
        """Calcola la posizione del tasto pausa in alto a sinistra."""
        s = self.scaling_manager.scale
        margin = int(8 * s)
        size = int(28 * s)
        self._pause_btn_rect = pygame.Rect(margin, margin, size, size)

    def is_running(self) -> bool:
        return self._is_running and self.current_minigame is not None

    def sync_with_engine(self, new_screen: pygame.Surface) -> None:
        """Sincronizza il manager e il minigioco attivo con i nuovi parametri dell'engine."""
        self.screen = new_screen
        if self.current_minigame:
            # Aggiorna il riferimento fisico alla superficie (evita Surface quit)
            self.current_minigame.screen = new_screen
            # Notifica il minigioco che può ricalcolare il layout (opzionale)
            self.current_minigame.on_resize()
            
        # Ricalcola la posizione del tasto pausa per la nuova risoluzione/scala
        self._calculate_pause_rect()

    def start_minigame(self, minigame_id: str, on_complete=None,
                       params: dict = None) -> bool:
        """Carica e avvia un minigioco per ID.

        Args:
            minigame_id: ID del minigioco da avviare.
            on_complete: Callback invocato al termine con il dict risultato.
            params: Parametri custom dal minigame_trigger (es. max_levels).
        """
        log.info(f"Avvio minigioco: {minigame_id}")
        self._on_complete_callback = on_complete
        self._current_mg_id = minigame_id
        self._current_params = params or {}
        
        # 1. Trova il manifest utilizzando get_resource_path per compatibilità EXE
        mg_path = get_resource_path("engine", "minigames", minigame_id)
        manifest_path = mg_path / "manifest.json"
        
        if not manifest_path.exists():
            log.error(f"Manifest non trovato per minigioco {minigame_id} in {manifest_path}")
            return False
            
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest = json.load(f)
            
            class_name = manifest.get("main_class")
            log.debug(f"Manifest caricato. Main Class: {class_name}")
            
            # 2. Caricamento dinamico del modulo
            module_name = f"engine.minigames.{minigame_id}.{minigame_id}_game"
            log.info(f"Importazione modulo: {module_name}...")
            
            try:
                module = importlib.import_module(module_name)
            except ImportError as ie:
                log.error(f"Impossibile importare {module_name}: {ie}")
                return False

            if not hasattr(module, class_name):
                log.error(f"Classe {class_name} non trovata nel modulo {module_name}")
                return False

            mg_class = getattr(module, class_name)
            
            # 3. Registrazione Sorgente Traduzioni (Centralizzata nel LanguageManager)
            # Questo garantisce persistenza al cambio lingua e fallback automatici
            self.lang.add_extra_source(str(mg_path / "strings"))
            
            # 4. Inizializzazione
            self.current_minigame = mg_class(
                screen=self.screen,
                scaling_manager=self.scaling_manager,
                audio_manager=self.audio,
                lang_manager=self.lang
            )
            
            # Setup callback di chiusura interno
            self.current_minigame.on_complete = self._handle_minigame_finish
            
            # 4. Avvio
            self.current_minigame.start()
            self._is_running = True
            return True
            
        except Exception as e:
            log.exception(f"Errore fatale durante l'avvio del minigioco {minigame_id}: {e}")
            return False

    def _handle_minigame_finish(self, result: dict) -> None:
        """Callback invocato dal minigioco quando termina."""
        log.info(f"Minigioco terminato con risultato: {result}")
        
        # Pulizia sorgente traduzioni
        if self._current_mg_id:
            mg_path = get_resource_path("engine", "minigames", self._current_mg_id)
            self.lang.remove_extra_source(str(mg_path / "strings"))

        self._is_running = False
        self.current_minigame = None
        self._current_mg_id = "" # Reset cache
        
        if self._on_complete_callback:
            self._on_complete_callback(result)

    def handle_event(self, event: pygame.event.Event) -> bool:
        """
        Gestisce gli eventi per il minigioco corrente.
        Ritorna True se l'evento richiede l'attivazione della pausa globale.
        """
        if not self.current_minigame or not self._is_running:
            return False

        # 1. Intercettazione Pausa (Click su Icona o Tasto ESC)
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self._pause_btn_rect.collidepoint(event.pos):
                return True
        
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            log.debug("ESC rilevato nel minigioco: attivazione pausa.")
            return True

        # 2. Gestione Hover per l'icona
        if event.type == pygame.MOUSEMOTION:
            self._pause_btn_hovered = self._pause_btn_rect.collidepoint(event.pos)

        # 3. Delega al minigioco
        self.current_minigame.handle_event(event)
        return False

    def update(self, dt: float) -> None:
        if self.current_minigame and self._is_running:
            self.current_minigame.update(dt)

    def draw(self) -> None:
        if self.current_minigame and self._is_running:
            self.current_minigame.draw()
            # Sovrapponiamo il tasto pausa globale sopra il minigioco
            self._draw_pause_button()

    def _draw_pause_button(self) -> None:
        """Renderizza il pulsante pausa (stile HUD) sopra il minigioco."""
        s = self.scaling_manager.scale
        rect = self._pause_btn_rect
        
        # Colori coordinati con HudManager
        alpha = 180 if self._pause_btn_hovered else 100
        bg_color = (15, 15, 25, alpha)
        border_color = (255, 215, 0) if self._pause_btn_hovered else (80, 80, 110, 120)
        
        # Surface per il pulsante
        btn_surf = pygame.Surface(rect.size, pygame.SRCALPHA)
        pygame.draw.rect(btn_surf, bg_color, (0, 0, rect.w, rect.h), border_radius=5)
        pygame.draw.rect(btn_surf, border_color, (0, 0, rect.w, rect.h), 1, border_radius=5)
        
        # Icona Pausa ultra-mini (due barre)
        icon_color = (230, 235, 245, 160)
        bar_w, bar_h = int(2 * s), int(12 * s)
        bar_gap = int(4 * s)
        cx, cy = rect.w // 2, rect.h // 2
        pygame.draw.rect(btn_surf, icon_color, (cx - bar_w - bar_gap//2, cy - bar_h//2, bar_w, bar_h), border_radius=1)
        pygame.draw.rect(btn_surf, icon_color, (cx + bar_gap//2, cy - bar_h//2, bar_w, bar_h), border_radius=1)
        
        self.screen.blit(btn_surf, rect.topleft)
