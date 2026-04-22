"""
engine/audio_manager.py

Gestore audio isolato.
Inizializza il mixer di Pygame e gestisce riproduzioni, volumi
e caricamenti pesanti su un thread separato.
"""

import pygame
import threading
from pathlib import Path
from queue import Queue

from engine.utils import get_logger, get_resource_path

class AudioCommand:
    PLAY_MUSIC = "PLAY_MUSIC"
    STOP_MUSIC = "STOP_MUSIC"
    PLAY_SFX = "PLAY_SFX"
    SET_MUSIC_VOL = "SET_MUSIC_VOL"
    SET_SFX_VOL = "SET_SFX_VOL"

class AudioManager:
    """Implementa code asincrone in modo che I/O Audio non causi stutter al framerate grafico."""
    def __init__(self) -> None:
        self.logger = get_logger(__name__)
        self.music_volume: float = 1.0
        self.sfx_volume: float = 1.0
        
        # Setup mixer Pygame con buffer esteso anti-crackling (16bit, stereo)
        if not pygame.mixer.get_init():
            pygame.mixer.pre_init(44100, -16, 2, 2048)
            pygame.mixer.init()
            
        pygame.mixer.set_num_channels(16)
        
        self._command_queue: Queue[tuple[str, dict]] = Queue()
        self._running: bool = True
        
        # Daemon Thread per evitare che tenga il programma vivo ad oltranza in caso di crash
        self._worker: threading.Thread = threading.Thread(target=self._audio_worker, daemon=True)
        self._worker.start()

    def play_music(self, path: str | Path, fade_ms: int = 500) -> None:
        self._command_queue.put((AudioCommand.PLAY_MUSIC, {"path": str(path), "fade": fade_ms}))

    def stop_music(self, fade_ms: int = 500) -> None:
        self._command_queue.put((AudioCommand.STOP_MUSIC, {"fade": fade_ms}))

    def play_sfx(self, path: str | Path, vol: float = 1.0) -> None:
        """Riproduce un SFX con un moltiplicatore di volume opzionale (0.0 - 1.0)."""
        self._command_queue.put((AudioCommand.PLAY_SFX, {"path": str(path), "vol": vol}))

    def set_music_volume(self, vol: float) -> None:
        self.music_volume = max(0.0, min(vol, 1.0))
        self._command_queue.put((AudioCommand.SET_MUSIC_VOL, {"vol": self.music_volume}))
        
    def set_sfx_volume(self, vol: float) -> None:
        self.sfx_volume = max(0.0, min(vol, 1.0))
        self._command_queue.put((AudioCommand.SET_SFX_VOL, {"vol": self.sfx_volume}))

    def _audio_worker(self) -> None:
        """Loop asincrono del consumatore audio."""
        while self._running:
            try:
                cmd, args = self._command_queue.get(timeout=0.5)
            except Exception:
                continue # Timeout coda per rinfrescare il loop booleano _running
                
            if cmd == AudioCommand.PLAY_MUSIC:
                try:
                    abs_path = get_resource_path(args["path"])
                    self.logger.info(f"Caricamento BGM: {abs_path} (Esiste: {abs_path.exists()})")
                    if not abs_path.exists():
                        raise FileNotFoundError(f"File non trovato: {abs_path}")
                        
                    pygame.mixer.music.load(str(abs_path))
                    pygame.mixer.music.set_volume(self.music_volume)
                    pygame.mixer.music.play(-1, fade_ms=args["fade"])
                except Exception as e:
                    self.logger.error(f"Impossibile caricare BGM '{args['path']}': {e}")
                    
            elif cmd == AudioCommand.STOP_MUSIC:
                pygame.mixer.music.fadeout(args["fade"])
                
            elif cmd == AudioCommand.PLAY_SFX:
                try:
                    abs_path = str(get_resource_path(args["path"]))
                    sound = pygame.mixer.Sound(abs_path)
                    # Applica volume globale * moltiplicatore locale
                    vol_mult = args.get("vol", 1.0)
                    sound.set_volume(self.sfx_volume * vol_mult)
                    sound.play()
                except Exception as e:
                    self.logger.error(f"Impossibile caricare SFX '{args['path']}': {e}")
                    
            elif cmd == AudioCommand.SET_MUSIC_VOL:
                pygame.mixer.music.set_volume(args["vol"])
                
    def quit(self) -> None:
        """Distruzione corretta dal MainThread."""
        self._running = False
        if self._worker.is_alive():
            self._worker.join(timeout=1.0)
        pygame.mixer.quit()
