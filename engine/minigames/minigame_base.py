"""
engine/minigames/minigame_base.py

Definisce l'interfaccia standard per tutti i minigiochi dell'HiddenEngine.
Ogni nuovo minigioco deve ereditare da BaseMinigame.
"""

from abc import ABC, abstractmethod
from typing import Any, Callable, Optional
from pathlib import Path
import pygame

class BaseMinigame(ABC):
    def __init__(self, screen: pygame.Surface, scaling_manager: Any, 
                 audio_manager: Any = None,
                 lang_manager: Any = None,
                 on_complete: Optional[Callable[[dict], None]] = None, 
                 params: Optional[dict] = None) -> None:
        """
        Inizializza il minigioco.
        
        Args:
            screen: La surface di rendering principale.
            scaling_manager: Il manager per la gestione delle coordinate scalate.
            on_complete: Callback da invocare alla fine del minigioco. 
                         Riceve un dizionario con i risultati (es. {'success': True, 'score': 500}).
            params: Parametri opzionali passati dall'editor o dalla scena.
        """
        self.screen = screen
        self.scaling_manager = scaling_manager
        self.audio_manager = audio_manager
        self.lang = lang_manager
        self._ = lang_manager # Alias per traduzioni rapide: self._("key")
        self.on_complete = on_complete
        self.params = params or {}
        self.is_running = True

    def load_local_strings(self, strings_path: Path) -> None:
        """Carica e registra una sorgente di stringhe locali nel LanguageManager."""
        if not self.lang or not strings_path.exists():
            return
            
        self.lang.add_extra_source(str(strings_path))

    @abstractmethod
    def start(self) -> None:
        """Invocato all'avvio del minigioco per setup iniziali."""
        pass

    def on_resize(self) -> None:
        """Invocato quando la risoluzione del gioco cambia durante l'esecuzione del minigioco."""
        pass

    @abstractmethod
    def handle_event(self, event: pygame.event.Event) -> None:
        """Gestisce gli eventi di input (Pygame)."""
        pass

    @abstractmethod
    def update(self, dt: float) -> None:
        """Aggiorna la logica del minigioco."""
        pass

    @abstractmethod
    def draw(self) -> None:
        """Esegue il rendering del minigioco sulla surface self.screen."""
        pass

    def finish(self, result: dict) -> None:
        """
        Termina il minigioco e invoca il callback di completamento.
        """
        self.is_running = False
        if self.on_complete:
            self.on_complete(result)
