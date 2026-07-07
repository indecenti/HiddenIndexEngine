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

from engine.utils import get_logger, warp_surface, apply_grayscale, is_android_runtime, get_resource_path
from engine import haptics
from engine.scaling_manager import ScalingManager
from engine.save_manager import SaveManager
from engine.transition_manager import TransitionManager, TransitionType
from engine.level_manager import SCENE_COMPLETE, LEVEL_COMPLETE, SCENE_FAILED

try:
    import ctypes
    ctypes.windll.user32.SetProcessDPIAware()
except Exception:
    pass

# Optional dependency: cv2 (OpenCV) per i background MP4 (menu + scene).
# Su desktop (Windows/macOS/Linux) è quasi sempre disponibile.
# Su Android non è praticabile cross-compilare opencv-python con p4a,
# quindi qui facciamo import safe: se manca, i blocchi video si auto-skippano
# (guard `HAS_CV2`) e il menu/scena rendono lo sfondo base (nero/letterbox)
# senza crash. Su Windows EXE il comportamento è invariato.
try:
    import cv2  # type: ignore
    HAS_CV2 = True
except ImportError:
    cv2 = None  # type: ignore
    HAS_CV2 = False

class EngineState:
    """Stati principali della state machine di sistema."""
    BOOT = "BOOT"
    MENU = "MENU"
    LEVEL_SELECT = "LEVEL_SELECT"
    SCENE = "SCENE"
    RESULTS = "RESULTS"
    PAUSE = "PAUSE"
    MINIGAME = "MINIGAME"


class _EphemeralSaveManager(SaveManager):
    """SaveManager effimero per la modalità playtest (--scene).

    Legge l'eventuale salvataggio esistente ma NON scrive mai su disco:
    tutte le mutazioni (score, unlock, checkpoint) restano in memoria e
    muoiono con il processo. Così una sessione di prova lanciata dall'editor
    non sporca i progressi reali del giocatore. Vive qui in core.py per non
    toccare engine/save_manager.py (logica replicata dal runtime web)."""

    def save(self) -> None:
        # No-op deliberato: nessuna persistenza in modalità playtest.
        self.logger.debug("Playtest: scrittura salvataggio ignorata (modalità effimera).")

    def _quarantine_corrupt_save(self) -> None:
        # No-op: in playtest non tocchiamo nemmeno i file corrotti su disco.
        pass

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
        # Feedback aptico: abilitato di default. La preferenza e' letta/persistita via
        # SaveManager (store scrivibile anche su Android), non via config.ini che su
        # Android e' in una dir read-only. Inizializzato dopo la creazione del save.
        self.vibration_enabled = True

        self.logger.info(f"Inizializzazione gioco '{game_id}': {self.res_w}x{self.res_h} (FS:{self.is_fullscreen})")
        
        # Forza centratura finestra su Windows/Linux/Mac
        os.environ['SDL_VIDEO_CENTERED'] = '1'
        
        # Hint SDL renderer ottimizzati per Android (devono essere settati PRIMA di
        # pygame.init / set_mode). Su Windows queste variabili sono ignorate.
        if is_android_runtime():
            # '1' = bilinear (default per un HOG: gli oggetti e il testo upscalati
            # dalla risoluzione interna restano morbidi invece di "scalettare").
            # '0' = nearest (più nitido sui pixel ma stairstepping su icone/glow,
            # difetto fatale per un genere "del guardare"). Su GLES2 il bilinear è
            # quasi gratis. '2' = anisotropic (lento su Android).
            os.environ.setdefault('SDL_HINT_RENDER_SCALE_QUALITY', '1')
            # Forza l'uso del renderer hardware-accelerated (OpenGL ES)
            os.environ.setdefault('SDL_HINT_RENDER_DRIVER', 'opengles2')
            # Batching dei draw calls per ridurre overhead per chiamata
            os.environ.setdefault('SDL_HINT_RENDER_BATCHING', '1')
            # Filtro texture lineare coerente con lo scale quality (no stairstepping)
            os.environ.setdefault('SDL_HINT_RENDER_TEXTURE_FILTERING', 'linear')
            # Evita inizializzazione moduli pygame non usati
            os.environ.setdefault('PYGAME_HIDE_SUPPORT_PROMPT', '1')

        pygame.init()
        pygame.display.set_caption("Hidden Engine")

        flags = pygame.DOUBLEBUF

        # Su Android: pygame.SCALED + risoluzione interna ADATTIVA all'aspect
        # del device. Calcola width interno proporzionale a height=540 in base
        # al ratio del dispositivo, evitando letterbox laterali (i Pixel 9+/10
        # sono ultra-wide 2.24:1, non 16:9). Pixel count interno ~0.6 MP (vs
        # 2.6 MP del device) → 4.3x meno lavoro per frame. SDL fa upscale GPU.
        self._android_internal_h = 540
        if is_android_runtime():
            self._device_w, self._device_h = 0, 0
            try:
                info = pygame.display.Info()
                if info.current_w > 0 and info.current_h > 0:
                    self._device_w, self._device_h = info.current_w, info.current_h
            except Exception:
                pass
            self.res_w, self.res_h = self._compute_android_internal_size(
                self._device_w, self._device_h
            )
            flags |= pygame.SCALED | pygame.FULLSCREEN
            self.logger.info(
                f"Android: pygame.SCALED rendering interno {self.res_w}x{self.res_h} "
                f"→ GPU upscale al device {self._device_w}x{self._device_h}"
            )
        elif self.is_fullscreen:
            flags |= pygame.FULLSCREEN

        self._display_flags = flags

        # vsync=0 su Android: la pipeline SDL hardware-accelerata gestisce
        # il presentation senza bloccare il rendering. Vsync=1 capava a refresh
        # display (60Hz) penalizzando frame con drop a 30Hz half-rate.
        # Su Windows EXE manteniamo vsync=1 per anti-tearing professionale.
        _vsync = 0 if is_android_runtime() else 1
        self.screen = pygame.display.set_mode((self.res_w, self.res_h), flags, vsync=_vsync)

        # Android: blocca eventi pygame mai usati dal motore per ridurre overhead
        # di event polling. MOUSEMOTION/FINGERMOTION restano abilitati perché
        # potrebbero servire per drag/hover in alcune scene/minigiochi.
        if is_android_runtime():
            pygame.event.set_blocked([
                # MULTIGESTURE bloccato di proposito: il pinch-zoom e' implementato via
                # eventi FINGER* (vedi _handle_finger_*), non tramite MULTIGESTURE. NON
                # riabilitarlo: creerebbe un secondo flusso di zoom in conflitto.
                pygame.MULTIGESTURE,
                pygame.JOYAXISMOTION,
                pygame.JOYHATMOTION,
                pygame.JOYBALLMOTION,
                pygame.JOYBUTTONDOWN,
                pygame.JOYBUTTONUP,
                pygame.JOYDEVICEADDED,
                pygame.JOYDEVICEREMOVED,
                pygame.TEXTINPUT,       # niente input testuale
                pygame.TEXTEDITING,
                pygame.AUDIODEVICEADDED,
                pygame.AUDIODEVICEREMOVED,
                pygame.DROPFILE,
                pygame.DROPBEGIN,
                pygame.DROPCOMPLETE,
                pygame.DROPTEXT,
            ])
            # Previene lo screensaver Android durante gameplay (auto wake-lock UI)
            try:
                pygame.display.set_allow_screensaver(False)
            except Exception:
                pass
            # Nasconde il cursore di sistema: su touch non deve MAI comparire
            # alcun puntatore (cerchio bianco semitrasparente di SDL).
            try:
                pygame.mouse.set_visible(False)
            except Exception:
                pass
        self.clock = pygame.time.Clock()
        
        # Inizializzo Sistemi
        self.scaling_manager = ScalingManager()
        self.scaling_manager.update_screen_size(self.res_w, self.res_h)

        # Safe area (solo Android): cutout + padding minimo.
        self._reconfigure_safe_area()

        # Modalità playtest (--scene "<livello>/<scena>"): avvio diretto di una
        # scena senza menu, con salvataggi in sola lettura (store effimero).
        self._playtest_scene: str | None = getattr(cli_args, "scene", None)
        self._playtest_mode: bool = bool(self._playtest_scene)

        if self._playtest_mode:
            self.save_manager = _EphemeralSaveManager(self.game_id)
        else:
            self.save_manager = SaveManager(self.game_id)
        # Preferenza vibrazione dallo store persistente (scrivibile su Android).
        self.vibration_enabled = bool(self.save_manager.get_progress("vibration_enabled", True))
        haptics.set_enabled(self.vibration_enabled)
        
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

        # Lettura game_config.json interno al gioco (validato contro lo schema).
        # La validazione e' DIAGNOSTICA: un config che non passa lo schema non deve
        # mai far perdere la configurazione reale del gioco, quindi in caso di
        # errore ricadiamo sul caricamento grezzo invece di azzerare la config.
        self.game_config = {}
        gc_path = get_resource_path("games", self.game_id, "game_config.json")
        if gc_path.exists():
            try:
                from engine.json_validator import load_and_validate
                self.game_config = load_and_validate(str(gc_path), "game_config")
            except Exception as e:
                self.logger.error(f"game_config.json non valido ({e}). Uso il caricamento grezzo.")
                try:
                    with open(gc_path, "r", encoding="utf-8") as f:
                        self.game_config = json.load(f)
                except Exception as e2:
                    self.logger.error(f"Impossibile leggere game_config.json ({e2}). Uso default vuoto.")
                    self.game_config = {}

        self.audio = AudioManager()
        self.audio.set_music_volume(self.music_volume)
        self.audio.set_sfx_volume(self.sfx_volume)
        self.lang = LanguageManager()
        
        # Priorità lingua: CLI > game_config > default(it)
        lang_to_load = getattr(cli_args, "lang", None) or self.game_config.get("default_language", "it")
        self.lang.load_for_game(self.game_id, lang_to_load)

        # Audit completezza lingue al boot (solo dev/DEBUG — niente overhead in EXE).
        # Stampa nel log un report compatto delle traduzioni mancanti per ciascuna
        # lingua disponibile. Aiuta a catturare drift di chiavi tra lingue PRIMA
        # che il giocatore lo veda come "obj_xyz" letterale a video.
        from engine.utils import DEBUG as _DEBUG
        if _DEBUG:
            try:
                self.lang.audit_completeness(self.game_id, log_warnings=True)
            except Exception as e:
                self.logger.warning(f"[i18n] audit_completeness fallito: {e}")
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
        self.menu_system.vibration_enabled = self.vibration_enabled
        
        # Se non ci sono livelli sbloccati, sblocchiamo il primo disponibile (nuovo gioco)
        self._ensure_first_level_unlocked()

        self.menu_system.build_buttons(has_save=self._has_progress())

        # Cache layer_hint_intensity per evitare .get() ogni frame
        self._cached_layer_intensity = self.game_config.get("layer_hint_intensity", {})
        self.click_detector = ClickDetector(self.scaling_manager)

        # Cache font HUD: SysFont enumera tutti i font di sistema ad ogni chiamata
        # (costosissimo su Android). Riusiamo le istanze tra i frame.
        self._hud_font_cache: dict[tuple, pygame.font.Font] = {}

        # ── Performance overlay (Android only) ────────────────────────────
        # Su Windows EXE _is_android = False → tutto disabilitato, niente
        # rendering extra, niente overhead. Su Android renderizziamo FPS
        # in top-left e logghiamo medie events/update/draw ogni ~60 frame.
        self._is_android = is_android_runtime()
        self._perf_sec: dict[str, float] = {}  # accumulo tempi per-sezione (profiling)
        if self._is_android:
            try:
                self._perf_font = pygame.font.Font(None, 28)
            except Exception:
                self._perf_font = None
            self._perf_frame_count = 0
            self._perf_acc_events_ms = 0.0
            self._perf_acc_update_ms = 0.0
            self._perf_acc_draw_ms = 0.0
            self._perf_acc_flip_ms = 0.0
            self._perf_acc_fill_ms = 0.0

        # ── Android lifecycle: pause/resume su entrata in background ──────
        # Quando l'utente toglie il focus all'app (Home button, recents,
        # incoming call, ecc.), pygame riceve eventi APP_*BACKGROUND. Mettiamo
        # il game loop in pausa per non consumare CPU/batteria mentre l'app
        # è invisibile. Su Windows questi eventi non arrivano mai → resta
        # sempre False, nessun cambio di comportamento.
        self._app_paused = False
        
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

        # Inizio gesto touch (per swipe del cassetto HUD su Android)
        self._touch_start = None

        # ── Gesti touch multi-dito: pinch-to-zoom + pan (ispezione scena) ────────
        # Tracciamo le dita via eventi FINGER* (multitouch reale). Le regole d'oro:
        #   - un gesto a 2 dita NON deve mai generare un tap/penalità (snap-find) né
        #     aprire/chiudere il cassetto HUD;
        #   - lo zoom è centrato sul punto medio delle dita (pinch naturale);
        #   - a una dita, quando si è ingranditi, il trascinamento fa pan (non tap).
        self._touch_points: dict[int, tuple[float, float]] = {}  # finger_id -> px interni
        self._gesture_active = False   # 2+ dita a contatto adesso
        self._gesture_seen = False     # gesto multitouch in corso (True finché restano dita)
        self._pinch_ref_dist = 0.0
        self._pinch_ref_zoom = 1.0
        self._pinch_last_centroid = (0.0, 0.0)
        self._one_finger_panning = False  # drag a una dita mentre si è ingranditi

        # ── Onboarding first-run (solo Android): coachmark una tantum che insegna
        # pinch-to-zoom, lista oggetti e maniglia HUD. Persistito via SaveManager
        # (store scrivibile su Android, a differenza di config.ini).
        self._coach_active = self._is_android and not self.save_manager.get_progress("coach_seen", False)
        self._coach_timer = 0.0

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
        elif self._playtest_mode:
            # MODALITÀ PLAYTEST: bypass completo di splash/menu, la scena parte
            # subito in gameplay. main.py ha già validato livello e scena.
            level_id, _, scene_id = self._playtest_scene.replace("\\", "/").partition("/")
            self.logger.info(
                f"MODALITÀ PLAYTEST: avvio diretto scena '{level_id}/{scene_id}' "
                f"(salvataggi disabilitati)"
            )
            self._start_level(level_id, scene_id)
            if self.state != EngineState.SCENE:
                # _start_level ha fallito (scena corrotta/asset mancanti): in
                # playtest niente fallback al menu, propaga come errore fatale
                # così main.py esce con codice != 0.
                raise RuntimeError(
                    f"Playtest: impossibile avviare la scena '{self._playtest_scene}' "
                    f"(vedi errori precedenti nel log)."
                )
        else:
            # Test pipeline di transizione: Fade da SplashScreen (BOOT) a Menu
            self.transition_manager.start_transition(
                TransitionType.FADE_TO_BLACK,
                base_dur_out=1.0, # Splash rimane visibile un secondo
                on_midpoint=self._switch_to_menu
            )

    def _compute_android_internal_size(self, phys_w: int, phys_h: int) -> tuple[int, int]:
        """Risoluzione interna adattiva all'aspect del device (altezza fissa 540,
        larghezza proporzionale, allineata a multipli di 4). Fallback 16:9."""
        h = self._android_internal_h
        aspect = (phys_w / phys_h) if (phys_w and phys_h) else (16.0 / 9.0)
        # Clamp difensivo per evitare surface assurde in split-screen estremo
        aspect = max(1.0, min(aspect, 3.0))
        w = int(round(h * aspect))
        w = (w + 3) & ~3  # multiplo di 4
        return w, h

    def _reconfigure_safe_area(self) -> None:
        """(Ri)configura la safe area dello ScalingManager dagli inset del cutout
        Android (px fisici → px interni). Solo Android; su desktop è no-op."""
        if not is_android_runtime():
            return
        try:
            from engine.utils import get_android_safe_insets
            cl, ct, cr, cb = get_android_safe_insets()
            dw = getattr(self, "_device_w", 0) or self.res_w
            dh = getattr(self, "_device_h", 0) or self.res_h
            sx = self.res_w / dw if dw else 1.0
            sy = self.res_h / dh if dh else 1.0
            self.scaling_manager.configure_safe_area(
                True, int(cl * sx), int(ct * sy), int(cr * sx), int(cb * sy)
            )
            self.logger.info(
                f"Safe area: cutout fisico (l={cl},t={ct},r={cr},b={cb}) "
                f"-> interno (l={int(cl*sx)},t={int(ct*sy)},r={int(cr*sx)},b={int(cb*sy)})"
            )
        except Exception as exc:
            self.logger.warning(f"Safe area non configurata: {exc}")

    def _handle_android_resize(self, phys_w: int, phys_h: int) -> None:
        """Adatta dinamicamente la risoluzione interna al nuovo display (Android).
        Ricalcola l'aspect, ricrea la surface SCALED solo se la dimensione interna
        cambia, poi riallinea safe area e tutti i sistemi."""
        # Dimensione fisica autoritativa: in SCALED l'evento può riportare la
        # dimensione logica, mentre Info() riflette il display reale.
        try:
            info = pygame.display.Info()
            if info.current_w > 0 and info.current_h > 0:
                phys_w, phys_h = info.current_w, info.current_h
        except Exception:
            pass

        new_w, new_h = self._compute_android_internal_size(phys_w, phys_h)
        self._device_w, self._device_h = phys_w, phys_h
        if (new_w, new_h) == (self.res_w, self.res_h):
            # Aspect invariato: aggiorna comunque la safe area (cutout può cambiare
            # in multi-window) senza ricreare la surface.
            self._reconfigure_safe_area()
            return
        self.logger.info(
            f"Android resize dinamico: interno {self.res_w}x{self.res_h} -> {new_w}x{new_h} "
            f"(device {phys_w}x{phys_h})"
        )
        self.screen = pygame.display.set_mode(
            (new_w, new_h), self._display_flags, vsync=0
        )
        self._handle_resize(new_w, new_h)
        self._reconfigure_safe_area()
        # Invalida cache dipendenti dalla risoluzione
        self._base_bg_params = None
        self._flashlight_mask = None

    def _handle_resize(self, w: int, h: int) -> None:
        """Centralizza l'aggiornamento dei sistemi dopo un cambio di risoluzione."""
        self.res_w, self.res_h = w, h
        self.scaling_manager.update_screen_size(w, h)
        
        # Aggiorna mapping specifico del background della scena (se attivo)
        if hasattr(self, '_current_bg_surface') and self._current_bg_surface:
            bw, bh = self._current_bg_surface.get_size()
            bg_scale = getattr(self, '_current_bg_scale', 1.0)
            self.scaling_manager.set_background(bw, bh, bg_scale)
            # Il pan è un offset in pixel-schermo legato alla geometria precedente:
            # dopo un resize (split-screen/foldable/cutout su Android, o cambio
            # risoluzione su desktop) lo azzeriamo per non far "saltare" la vista.
            self.scaling_manager.reset_pan_zoom()
            if hasattr(self, '_touch_points'):
                self._reset_touch_state()
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

        if self._is_android:
            # Versione Android con profiling — overhead trascurabile (3 perf_counter
            # + 3 sottrazioni per frame). Su Windows si usa il path nudo sotto.
            # Cap a 60 FPS con vsync: SDL fa frame-skip automatico (60Hz quando
            # il frame si chiude in <16.67ms, half-rate 30Hz quando no).
            # tick_busy_loop = busy-wait più preciso di tick (OS sleep jittery
            # su Android).
            import time as _time
            ANDROID_FPS_CAP = 60
            while self.running:
                dt = self.clock.tick_busy_loop(ANDROID_FPS_CAP) / 1000.0
                t0 = _time.perf_counter()
                self._handle_events()
                t1 = _time.perf_counter()
                # Lifecycle: se in background, dormi e salta update/draw
                # (continua a processare eventi per rispondere a foreground).
                if self._app_paused:
                    _time.sleep(0.1)
                    continue
                self._update(dt)
                t2 = _time.perf_counter()
                self._draw()
                t3 = _time.perf_counter()

                self._perf_acc_events_ms += (t1 - t0) * 1000.0
                self._perf_acc_update_ms += (t2 - t1) * 1000.0
                self._perf_acc_draw_ms += (t3 - t2) * 1000.0
                self._perf_frame_count += 1
                if self._perf_frame_count >= 60:
                    fps = self.clock.get_fps()
                    n = float(self._perf_frame_count)
                    draw_ms = self._perf_acc_draw_ms / n
                    flip_ms = self._perf_acc_flip_ms / n
                    self.logger.info(
                        "[PERF] FPS=%.1f events=%.1fms update=%.1fms draw=%.1fms (interno=%.1fms flip=%.1fms) state=%s",
                        fps,
                        self._perf_acc_events_ms / n,
                        self._perf_acc_update_ms / n,
                        draw_ms,
                        max(0.0, draw_ms - flip_ms),
                        flip_ms,
                        self.state,
                    )
                    if self._perf_sec:
                        secs = " ".join(f"{k}={v/n*1000.0:.1f}ms" for k, v in sorted(self._perf_sec.items()))
                        self.logger.info("[PERF2] %s", secs)
                        self._perf_sec.clear()
                    self._perf_frame_count = 0
                    self._perf_acc_events_ms = 0.0
                    self._perf_acc_update_ms = 0.0
                    self._perf_acc_draw_ms = 0.0
                    self._perf_acc_flip_ms = 0.0
        else:
            while self.running:
                dt = self.clock.tick(60) / 1000.0  # limit framerate to 60 FPS
                self._handle_events()
                self._update(dt)
                self._draw()

        self._quit()

    def _handle_back_navigation(self) -> None:
        """Navigazione 'Indietro' contestuale, condivisa da ESC (desktop) e dal
        tasto/gesto Indietro di Android (K_AC_BACK). Comportamento da vera app:
        nei sotto-menu torna al menu precedente, in gioco apre la pausa, nel
        menu principale esce."""
        if self._playtest_mode:
            # Playtest: ESC/Indietro chiude subito la sessione di prova.
            self.logger.info("Playtest: uscita richiesta (ESC/Indietro).")
            self.running = False
            return
        if self.state == EngineState.MENU:
            ms = getattr(self.menu_system, "state", "main")
            if ms == "scenes":
                self.menu_system.change_state("levels")
            elif ms in ("settings", "levels", "confirm_new"):
                self.menu_system.change_state("main", has_save=self._has_progress())
            else:  # main
                self.running = False
        elif self.state == EngineState.PAUSE:
            ms = getattr(self.menu_system, "state", "pause")
            if ms == "settings":
                self.menu_system.change_state("pause", has_save=self._has_progress())
            else:
                self._toggle_pause()  # riprendi
        elif self.state in (EngineState.SCENE, EngineState.MINIGAME):
            self._toggle_pause()
        elif self.state == EngineState.BOOT:
            self.running = False

    def _process_scene_click(self, pos) -> None:
        """Gestisce un click/tap nella scena (anti-spam, hit detection, oggetto
        trovato/mancato). `pos` è in coordinate schermo. Su Android viene chiamato
        al rilascio solo per i tap (non per gli swipe del cassetto HUD)."""
        now = pygame.time.get_ticks() / 1000.0
        if self._spam_lock_timer > 0:
            self.logger.debug("Click ignorato: Sistema in LOCKDOWN")
            return
        self._click_history = [t for t in self._click_history if now - t < 1.0]
        self._click_history.append(now)
        if len(self._click_history) > 5:
            self.logger.warning("SPAM DETECTED! Avvio lockdown per 3 secondi.")
            self._spam_lock_timer = 3.0
            return

        z_fact = 1.0
        if self._scene_intro_timer > 0:
            t = self._scene_intro_timer / self._scene_intro_dur
            z_fact = 1.0 + (t ** 3 * 0.25)

        # Tolleranza tap fat-finger solo su touch (~7mm); il mouse desktop resta preciso.
        slop = self.res_h * 0.045 if self._is_android else 0.0
        hit = self.click_detector.detect(
            pos[0], pos[1], self._current_scene_objects,
            scenic_factor=z_fact, slop_screen=slop,
        )
        if hit:
            trigger = getattr(hit, "minigame_trigger", None)
            self.logger.debug(f"[CLICK] Hit: {hit.instance_id} (trigger: {trigger is not None})")
            if trigger:
                mg_id = trigger.get("minigame_id")
                if mg_id:
                    cx, cy = pos[0], pos[1]

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
                            self.state = EngineState.SCENE

                    self.transition_manager.start_transition(
                        TransitionType.CIRCLE_BURST,
                        base_dur_out=0.8, base_dur_in=0.6, cx=cx, cy=cy,
                        on_midpoint=_on_burst_midpoint
                    )
                    self.effects.shake_screen(duration=0.8, intensity=8.0)
                    return

            if hit.is_goal:
                # Registra il ritrovamento per QUALSIASI obiettivo valido non ancora
                # trovato, anche se fuori dalla finestra visibile della HUD
                # (_max_visible): prima un goal corretto oltre il 7° elemento veniva
                # erroneamente trattato come errore e penalizzato.
                self.level_manager.register_found(hit.instance_id)
                if hit.detection_type == "rect":
                    cx = hit.x + hit.width / 2
                    cy = hit.y + hit.height / 2
                else:
                    cx = hit.x
                    cy = hit.y
                is_last_object = self.level_manager._found_count() == self.level_manager._total_count()
                if is_last_object:
                    self.audio.play_sfx("engine/assets/sounds/victory.mp3")
                    self.effects.spawn_final_found_effect(cx, cy)
                    self.effects.shake_screen(duration=1.2, intensity=10.0)
                    haptics.success_strong()
                else:
                    self.audio.play_sfx("engine/assets/sounds/bling1.mp3")
                    self.effects.spawn_found_effect(cx, cy)
                    haptics.found()
        else:
            self.audio.play_sfx("engine/assets/sounds/error4.mp3")
            haptics.miss()
            penalty = self.level_manager.register_miss()
            bx, by = self.scaling_manager.screen_to_bg(*pos)
            self.effects.spawn_score_popup(bx, by, penalty)
            self.logger.debug("Mancato / Click a vuoto")

    # ── Gesti touch multi-dito: pinch-to-zoom + pan (ispezione scena) ────────
    def _finger_xy(self, event) -> tuple[float, float]:
        """Coordinate del tocco in pixel interni. Gli eventi FINGER* portano
        coordinate normalizzate 0..1: le scaliamo alla risoluzione interna, coerente
        con le coordinate mouse usate dal resto del motore."""
        return (event.x * self.res_w, event.y * self.res_h)

    @staticmethod
    def _finger_id(event):
        return getattr(event, "finger_id", getattr(event, "finger", 0))

    def _pinch_metrics(self) -> tuple[float, tuple[float, float]]:
        """Distanza e punto medio (centroid) delle prime due dita a contatto."""
        ids = sorted(self._touch_points.keys())[:2]
        (x1, y1), (x2, y2) = self._touch_points[ids[0]], self._touch_points[ids[1]]
        return math.hypot(x2 - x1, y2 - y1), ((x1 + x2) / 2.0, (y1 + y2) / 2.0)

    def _begin_pinch(self) -> None:
        dist, centroid = self._pinch_metrics()
        self._pinch_ref_dist = max(1.0, dist)
        self._pinch_ref_zoom = self.scaling_manager.zoom
        self._pinch_last_centroid = centroid

    def _handle_finger_down(self, event) -> None:
        if self.state != EngineState.SCENE:
            return
        self._touch_points[self._finger_id(event)] = self._finger_xy(event)
        if len(self._touch_points) >= 2:
            # Secondo dito: entra in modalità gesto. Annulla ogni tap/pan in sospeso
            # così il pinch non genera mai un find/penalità né tocca il cassetto HUD.
            self._gesture_active = True
            self._gesture_seen = True
            self._touch_start = None
            self._one_finger_panning = False
            self._begin_pinch()

    def _handle_finger_motion(self, event) -> None:
        if self.state != EngineState.SCENE:
            return
        fid = self._finger_id(event)
        if fid in self._touch_points:
            self._touch_points[fid] = self._finger_xy(event)
        # Durante l'intro zoom scenica la camera resta ferma (lo scenic è ancorato
        # al centro schermo: applicarvi sopra pan/zoom separerebbe sfondo e oggetti).
        if self._gesture_active and len(self._touch_points) >= 2 and self._scene_intro_timer <= 0:
            dist, centroid = self._pinch_metrics()
            # Pan: la scena segue lo spostamento del punto medio delle dita.
            dx = centroid[0] - self._pinch_last_centroid[0]
            dy = centroid[1] - self._pinch_last_centroid[1]
            if dx or dy:
                self.scaling_manager.pan_by(dx, dy)
            self._pinch_last_centroid = centroid
            # Zoom centrato sul punto medio (pinch naturale).
            if self._pinch_ref_dist > 0:
                new_zoom = self._pinch_ref_zoom * (dist / self._pinch_ref_dist)
                self.scaling_manager.zoom_at(new_zoom, centroid[0], centroid[1])

    def _handle_finger_up(self, event) -> None:
        self._touch_points.pop(self._finger_id(event), None)
        if len(self._touch_points) < 2:
            self._gesture_active = False
        if not self._touch_points:
            # Fine sequenza di tocco: azzera lo stato gesto multitouch.
            # NON azzeriamo qui _one_finger_panning: per il dito primario SDL accoda
            # FINGERUP PRIMA del MOUSEBUTTONUP emulato, quindi il flag deve restare
            # armato finché il MOUSEBUTTONUP non lo legge e lo consuma (ramo UP).
            # Viene comunque azzerato all'inizio del prossimo tocco e da _reset_touch_state.
            self._gesture_seen = False

    def _reset_touch_state(self) -> None:
        """Azzera tutto lo stato di tocco/gesto. Da chiamare a inizio scena per non
        ereditare dita/flag dalla scena precedente (evita tap/find persi o spuri)."""
        self._touch_points.clear()
        self._gesture_active = False
        self._gesture_seen = False
        self._one_finger_panning = False
        self._touch_start = None

    def _dismiss_coach(self) -> None:
        """Chiude il coachmark di onboarding e segna che e' stato visto (persistente)."""
        if not self._coach_active:
            return
        self._coach_active = False
        try:
            self.save_manager.set_progress("coach_seen", True)
        except Exception:
            pass

    def _activate_manual_hint(self, popup_pos) -> None:
        """Attiva un hint manuale (da pulsante UI). popup_pos serve solo per il
        popup del costo nelle scene senza torcia."""
        if self.level_manager.get_available_hints() > 0:
            is_flashlight = self._current_scene_data and getattr(self._current_scene_data, 'flashlight', False)
            success, penalty = self.hint.use_manual_hint(self._current_scene_objects, suppress_fx=False)
            if success:
                self.audio.play_sfx("engine/assets/sounds/click_Low.wav")
                self.level_manager.apply_score_penalty(penalty)
                self.level_manager.consume_hint_from_rewards()
                if is_flashlight:
                    self._hint_flash_timer = 5.0
                    self.logger.info("Hint Flash attivato per 5 secondi (torcia presente)")
                else:
                    bx, by = self.scaling_manager.screen_to_bg(*popup_pos)
                    self.effects.spawn_score_popup(bx, by, penalty)
                    self.logger.info(f"Hint usato (bottone): penalità {penalty} pt")
        else:
            self.audio.play_sfx("engine/assets/sounds/error4.mp3")
            self.logger.warning("Tentativo di usare hint ma quantità disponibile è 0!")

    def _handle_scene_tap(self, pos) -> None:
        """Tap PULITO (no gesto, no pan, no swipe) in scena su Android: instrada su
        hint / maniglia HUD / pausa, altrimenti click sull'oggetto. Chiamato dal
        rilascio così un pinch che inizia su un pulsante non lo attiva per sbaglio."""
        hint_rect = self.hud.get_mobile_hint_rect()
        if hint_rect and hint_rect.collidepoint(pos):
            self._activate_manual_hint(pos)
            return
        if self.hud.is_handle_clicked(pos):
            self.hud.toggle_drawer()
            self.audio.play_sfx("engine/assets/sounds/click_Low.wav")
            return
        if self.hud.is_pause_button_clicked(pos):
            self.audio.play_sfx("engine/assets/sounds/click_Low.wav")
            self._toggle_pause()
            return
        # Tap sulla barra HUD aperta: ignora (non penalizza).
        if self.hud.is_drawer_open() and self.hud.get_hud_rect().collidepoint(pos):
            return
        self._process_scene_click(pos)

    def _handle_events(self) -> None:
        """Smista gli input di Pygame."""
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False

            # ── Android lifecycle (no-op su Windows: questi event non arrivano)
            elif event.type == pygame.APP_WILLENTERBACKGROUND or \
                 event.type == pygame.APP_DIDENTERBACKGROUND:
                self._app_paused = True
                self.logger.info("[Lifecycle] App in background — pausing render loop")
                try:
                    pygame.mixer.pause()
                    pygame.mixer.music.pause()
                except Exception:
                    pass
                continue
            elif event.type == pygame.APP_WILLENTERFOREGROUND or \
                 event.type == pygame.APP_DIDENTERFOREGROUND:
                self._app_paused = False
                self.logger.info("[Lifecycle] App in foreground — resuming")
                try:
                    pygame.mixer.unpause()
                    pygame.mixer.music.unpause()
                except Exception:
                    pass
                continue

            elif event.type == pygame.VIDEORESIZE:
                self.logger.debug(f"Video Resize rilevato: {event.w}x{event.h}")
                # Android: adatta dinamicamente la risoluzione interna al nuovo
                # display (rotazione bloccata, ma split-screen/foldable/cutout
                # possono cambiare dimensione e aspect a runtime).
                if self._is_android:
                    self._handle_android_resize(event.w, event.h)

            elif event.type == pygame.MOUSEWHEEL:
                if self.state in [EngineState.MENU, EngineState.PAUSE]:
                    self.menu_system.handle_scroll(event.y)

            # Gesti multitouch in scena (pinch-to-zoom + pan). Gli eventi mouse
            # emulati da SDL continuano a gestire il tap a una dita; questi tracciano
            # le dita reali e pilotano la camera senza generare tap/penalità.
            elif event.type == pygame.FINGERDOWN:
                self._handle_finger_down(event)
            elif event.type == pygame.FINGERMOTION:
                self._handle_finger_motion(event)
            elif event.type == pygame.FINGERUP:
                self._handle_finger_up(event)

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
                            self.audio.play_sfx("engine/assets/sounds/error4.mp3") # Feedback per bloccato
                        
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
                            elif action == "toggle_vibration":
                                self.vibration_enabled = not self.vibration_enabled
                                haptics.set_enabled(self.vibration_enabled)
                                self.menu_system.vibration_enabled = self.vibration_enabled
                                self._persist_vibration_setting()
                                if self.vibration_enabled:
                                    haptics.tick()  # conferma tattile dell'attivazione
                                self.menu_system.build_buttons(has_save=self._has_progress())

                        # Aggiornamento parametri menu dinamici (res/lang/ecc)
                        if action and action.startswith("goto"):
                            self.menu_system.build_buttons(has_save=self._has_progress())

                    elif self.state == EngineState.SCENE:
                        if self._is_android:
                            # Android: tap e gesti risolti al RILASCIO / via FINGER.
                            # Sul DOWN nessuna azione one-shot (hint/maniglia/pausa/
                            # oggetto): così un pinch che inizia su un pulsante non lo
                            # attiva e uno swipe/pan non genera mai find o penalità.
                            if self._gesture_seen or self._gesture_active:
                                continue  # gesto multitouch in corso: ignora il mouse emulato
                            # I bubble modali hanno la priorità (anche sul coachmark).
                            is_visible = self.level_manager.is_any_bubble_visible()
                            is_pending_intro = self._scene_intro_timer > 0 and self.level_manager.has_start_scene_bubbles()
                            if is_visible or is_pending_intro:
                                if is_visible:
                                    for fx in self._current_scene_effects:
                                        if fx.type == "bubble_tip" and getattr(fx, "_visible", False):
                                            if hasattr(self, "_last_bubble_btns"):
                                                for b_fx, b_rect in self._last_bubble_btns:
                                                    if b_fx == fx and b_rect.collidepoint(event.pos):
                                                        fx._visible = False
                                                        self.audio.play_sfx("engine/assets/sounds/click_Low.wav")
                                                        break
                                continue
                            # Onboarding: la prima interazione CHIUDE il coachmark e
                            # viene CONSUMATA (continue): NON deve valere come tap di
                            # gioco. Il gameplay parte dal tocco successivo.
                            if self._coach_active:
                                self._dismiss_coach()
                                continue
                            # Memorizza l'inizio del tocco: tap vs swipe risolti al rilascio.
                            # Reset del flag pan a inizio tocco (backstop nel caso raro in
                            # cui un MOUSEBUTTONUP precedente fosse andato perso).
                            self._one_finger_panning = False
                            self._touch_start = event.pos
                            continue

                        # ── Desktop (mouse): azione immediata sul DOWN ──
                        # --- GESTIONE BUBBLE TIPS ---
                        is_visible = self.level_manager.is_any_bubble_visible()
                        is_pending_intro = self._scene_intro_timer > 0 and self.level_manager.has_start_scene_bubbles()
                        if is_visible or is_pending_intro:
                            if is_visible:
                                clicked_any = False
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
                            continue

                        # Pulsante hint (desktop: box in alto a destra)
                        _hint_rect = getattr(self, '_hint_button_rect', None)
                        if _hint_rect and _hint_rect.collidepoint(event.pos):
                            self._activate_manual_hint(event.pos)
                            continue

                        # Pulsante pausa
                        if self.hud.is_pause_button_clicked(event.pos):
                            self.audio.play_sfx("engine/assets/sounds/click_Low.wav")
                            self._toggle_pause()
                            continue

                        # Click sull'oggetto (immediato su desktop)
                        self._process_scene_click(event.pos)

                    elif self.state == EngineState.RESULTS:
                        # Delega al ResultsScreen il controllo del click (gestisce layout e animazione)
                        if self.results_screen.check_click(event.pos):
                            self.audio.play_sfx("engine/assets/sounds/click_Low.wav")
                            self.transition_manager.start_transition(TransitionType.FADE_TO_BLACK, on_midpoint=self._advance_scene)
            
            elif event.type == pygame.MOUSEBUTTONUP:
                # Android, scena: al rilascio distinguiamo SWIPE (cassetto HUD), PAN e
                # gesto da TAP. Solo un tap pulito instrada su hint/maniglia/pausa o
                # click oggetto; gesti e pan non generano MAI find/penalità/toggle.
                if event.button == 1 and self._is_android and self.state == EngineState.SCENE:
                    if self._gesture_seen or self._one_finger_panning or self._touch_start is None:
                        # Coda di un gesto (pinch/pan) o tocco già consumato: niente tap.
                        self._one_finger_panning = False
                        self._touch_start = None
                    else:
                        sp = self._touch_start
                        self._touch_start = None
                        dx = event.pos[0] - sp[0]
                        dy = event.pos[1] - sp[1]
                        moved = (dx * dx + dy * dy) ** 0.5
                        swiped = self.hud.handle_swipe(sp, event.pos)
                        if not swiped and moved < self.res_h * 0.045:
                            self._handle_scene_tap(sp)
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
                # Drag a una dita mentre si è ingranditi -> pan della scena (no tap,
                # no penalità). Solo touch/Android e solo con zoom attivo, così a
                # zoom 1.0 lo swipe del cassetto HUD resta invariato.
                if (self._is_android and self.state == EngineState.SCENE
                        and not self._gesture_active and not self._gesture_seen
                        and self.scaling_manager.is_zoomed()
                        and event.buttons and event.buttons[0]
                        and self._touch_start is not None):
                    # Slop: avvia il pan solo oltre soglia, identica al tap. Un tap
                    # fermo con micro-jitter resta un tap (find), non diventa pan.
                    tdx = event.pos[0] - self._touch_start[0]
                    tdy = event.pos[1] - self._touch_start[1]
                    if self._one_finger_panning or (tdx * tdx + tdy * tdy) ** 0.5 > self.res_h * 0.045:
                        self._one_finger_panning = True
                        rel = getattr(event, "rel", (0, 0))
                        if rel[0] or rel[1]:
                            self.scaling_manager.pan_by(rel[0], rel[1])

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

                if event.key in (pygame.K_ESCAPE, pygame.K_AC_BACK):
                    # ESC (desktop) e tasto/gesto Indietro Android (K_AC_BACK):
                    # navigazione contestuale unificata.
                    self.logger.debug("Indietro/ESC premuto")
                    self._handle_back_navigation()

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
                        self.audio.play_sfx("engine/assets/sounds/error4.mp3")
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

        # Persistenza display sul path scrivibile (Android-safe, vedi _persist_config).
        self.config.set("engine", "resolution_w", str(w))
        self.config.set("engine", "resolution_h", str(h))
        self.config.set("engine", "fullscreen", "1" if fullscreen else "0")
        self._persist_config("display")

        # Se c'era resize_pending, lo abbiamo evaso con _handle_resize
        self.scaling_manager.consume_resize()

    def _persist_config(self, what: str = "config") -> None:
        """Scrive self.config sul path config UTENTE scrivibile.

        Su Android e' ANDROID_PRIVATE/saves/config.ini: get_base_path()/config.ini
        (dir di unpack dell'app) e' READ-ONLY, scrivervi fallirebbe e la preferenza
        andrebbe persa al riavvio. Su desktop e' il config.ini nella root (immutato).
        I default bundlati restano in get_base_path()/config.ini e vengono caricati
        da main.py PRIMA di questo file utente (che li sovrascrive)."""
        from engine.utils import get_user_config_path
        try:
            with open(get_user_config_path(), "w", encoding="utf-8") as f:
                self.config.write(f)
            self.logger.debug(f"Configurazione '{what}' salvata in {get_user_config_path()}")
        except Exception as e:
            self.logger.error(f"Errore salvataggio configurazione '{what}': {e}")

    def _apply_audio_settings(self, music_vol: float, sfx_vol: float) -> None:
        """Applica e persiste i settaggi audio."""
        self.audio.set_music_volume(music_vol)
        self.audio.set_sfx_volume(sfx_vol)

        self.config.set("engine", "music_volume", f"{music_vol:.2f}")
        self.config.set("engine", "sfx_volume", f"{sfx_vol:.2f}")
        self._persist_config("audio")

    def _persist_vibration_setting(self) -> None:
        """Persiste l'impostazione vibrazione via SaveManager (store scrivibile anche
        su Android, a differenza di config.ini)."""
        try:
            self.save_manager.set_progress("vibration_enabled", bool(self.vibration_enabled))
            self.logger.debug(f"Vibrazione salvata: {self.vibration_enabled}")
        except Exception as e:
            self.logger.error(f"Errore salvataggio impostazione vibrazione: {e}")

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

            # Onboarding coachmark: auto-dismiss dopo qualche secondo (oltre al
            # dismiss sulla prima interazione).
            if self._coach_active:
                self._coach_timer += dt
                if self._coach_timer > 7.0:
                    self._dismiss_coach()
            
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

        # Nuova scena: azzera lo zoom/pan di ispezione ereditato dalla precedente.
        self.scaling_manager.reset_pan_zoom()
        self._reset_touch_state()
        self.hud.setup(self._current_scene_objects, self.level_manager.time_elapsed)
        self._play_scene_music(scene_data)
        self.state = EngineState.SCENE

    def _switch_to_menu(self) -> None:
        """Sincronizza core e menu_system verso lo stato principale."""
        if self._playtest_mode:
            # Playtest: nessun ritorno al menu, qualunque percorso vi arrivi
            # (fine livello, quit dalla pausa, errore) termina la sessione.
            self.logger.info("Playtest: sessione terminata, uscita senza menu.")
            self.running = False
            return
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
        if self._playtest_mode:
            # Playtest: la scena di prova è conclusa (schermata risultati
            # confermata), niente scena successiva: chiudi il processo.
            self.logger.info("Playtest: scena conclusa, chiusura della sessione.")
            self.running = False
            return
        self.scaling_manager.invalidate_cache()
        try:
            next_scene = self.level_manager.advance_to_next_scene()
        except Exception as e:
            self.logger.error(f"Impossibile caricare la scena successiva: {e}. Ritorno al menu.")
            self._switch_to_menu()
            return
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
            self.scaling_manager.reset_pan_zoom()
            self._reset_touch_state()
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

        try:
            scene_data = self.level_manager.start_level(level_id, start_scene_index=start_idx)
        except Exception as e:
            self.logger.error(f"[GAME] Impossibile avviare il livello '{level_id}': {e}. Ritorno al menu.")
            self._switch_to_menu()
            return

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

        # Nuova scena: azzera lo zoom/pan di ispezione.
        self.scaling_manager.reset_pan_zoom()
        self._reset_touch_state()
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

    def _get_hint_glow(self, qr: int, b: float) -> "pygame.Surface":
        """Alone hint (disco oro + 2 anelli) CACHATO per (raggio quantizzato, intensita').
        Evita l'alloc di una Surface SRCALPHA + 3 draw.circle a OGNI frame durante
        l'evidenziazione dell'indizio in scena. set_alpha non e' usabile (la surface ha
        alpha per-pixel), quindi l'intensita' e' bakata nella key (poche varianti)."""
        cache = getattr(self, "_hint_glow_cache", None)
        if cache is None:
            cache = self._hint_glow_cache = {}
        key = (qr, b)
        g = cache.get(key)
        if g is None:
            if len(cache) > 48:
                cache.clear()
            g = pygame.Surface((qr * 2, qr * 2), pygame.SRCALPHA)
            pygame.draw.circle(g, (255, 220, 60, int(70 * b)), (qr, qr), qr)
            rw = max(4, qr // 6)
            pygame.draw.circle(g, (255, 230, 80, int(235 * b)), (qr, qr), qr, width=rw)
            pygame.draw.circle(g, (255, 250, 200, int(180 * b)), (qr, qr), max(1, qr - rw), width=max(2, rw // 2))
            g = g.convert_alpha()
            cache[key] = g
        return g

    def _hud_font(self, family: str, size: int, bold: bool = False, italic: bool = False) -> pygame.font.Font:
        """Restituisce un SysFont cacheato per evitare di ricrearlo ogni frame."""
        key = (family, size, bold, italic)
        font = self._hud_font_cache.get(key)
        if font is None:
            font = pygame.font.SysFont(family, size, bold=bold, italic=italic)
            self._hud_font_cache[key] = font
        return font

    def _draw_coachmark(self) -> None:
        """Overlay di onboarding (una tantum, Android): insegna pinch-zoom, lista a
        icone e maniglia HUD. Non blocca l'input: si chiude alla prima interazione
        o dopo qualche secondo."""
        sm = self.scaling_manager
        W, H = self.res_w, self.res_h
        gold = (255, 215, 0)
        white = (235, 238, 245)

        veil = pygame.Surface((W, H), pygame.SRCALPHA)
        veil.fill((0, 0, 0, 150))
        self.screen.blit(veil, (0, 0))

        title = self.lang.get("coach_title", "COME GIOCARE")
        lines = [
            self.lang.get("coach_zoom", "Pizzica con due dita per ingrandire la scena"),
            self.lang.get("coach_find", "Tocca gli oggetti della lista per trovarli"),
            self.lang.get("coach_drawer", "Trascina la maniglia in basso per la lista"),
        ]
        dismiss = self.lang.get("coach_dismiss", "Tocca per iniziare")

        title_f = self._hud_font("segoeui", sm.scale_value(40), bold=True)
        line_f = self._hud_font("segoeui", sm.scale_value(26))
        dismiss_f = self._hud_font("segoeui", sm.scale_value(22), bold=True)

        t_surf = title_f.render(title, True, gold)
        line_surfs = [line_f.render(s, True, white) for s in lines]
        d_surf = dismiss_f.render(dismiss, True, (180, 200, 255))

        pad = sm.scale_value(28)
        gap = sm.scale_value(16)
        line_h = line_f.get_height()
        content_w = max([t_surf.get_width()] + [s.get_width() for s in line_surfs] + [d_surf.get_width()])
        content_h = (t_surf.get_height() + gap
                     + len(line_surfs) * (line_h + gap // 2)
                     + gap + d_surf.get_height())
        panel_w = content_w + pad * 2
        panel_h = content_h + pad * 2
        px = (W - panel_w) // 2
        py = (H - panel_h) // 2

        panel = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)
        radius = sm.scale_value(18)
        pygame.draw.rect(panel, (18, 22, 34, 235), (0, 0, panel_w, panel_h), border_radius=radius)
        pygame.draw.rect(panel, (90, 110, 150, 220), (0, 0, panel_w, panel_h),
                         max(2, sm.scale_value(2)), border_radius=radius)
        self.screen.blit(panel, (px, py))

        cy = py + pad
        self.screen.blit(t_surf, (px + (panel_w - t_surf.get_width()) // 2, cy))
        cy += t_surf.get_height() + gap
        for s in line_surfs:
            self.screen.blit(s, (px + (panel_w - s.get_width()) // 2, cy))
            cy += line_h + gap // 2

        a = int(160 + abs(math.sin(pygame.time.get_ticks() * 0.004)) * 95)
        d2 = d_surf.copy()
        d2.set_alpha(a)
        self.screen.blit(d2, (px + (panel_w - d_surf.get_width()) // 2,
                              py + panel_h - pad - d_surf.get_height()))

    def _draw_hint_count(self) -> None:
        """Disegna conteggio hint con design glassmorphism premium."""
        if self.state != EngineState.SCENE or not self.level_manager:
            return
        # Su Android il conteggio hint è mostrato dentro la barra HUD.
        if self._is_android:
            return

        available_hints = self.level_manager.get_available_hints()
        sm = self.scaling_manager

        # Costanti glassmorphism (coerente con HudManager)
        COLOR_BG = (15, 15, 25, 180)
        COLOR_BORDER = (80, 80, 110, 200)
        COLOR_ACCENT = (255, 215, 0)  # Gold
        COLOR_TEXT = (230, 235, 245)  # Off-white
        # Box hint più grande e leggibile su mobile.
        hs = 1.5 if self._is_android else 1.0
        def _sv(v):
            return sm.scale_value(v * hs)
        panel_w = _sv(90)
        panel_h = _sv(55)
        panel_x = sm.safe_right - panel_w
        panel_y = sm.safe_top

        # Salva rettangolo per click detection (serve se il panel diventa clikkabile)
        self._hint_panel_rect = pygame.Rect(panel_x, panel_y, panel_w, panel_h)

        # Crea superficie trasparente per il panel
        panel_surf = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)

        # Disegna background con border radius
        pygame.draw.rect(panel_surf, COLOR_BG, (0, 0, panel_w, panel_h), border_radius=_sv(8))
        pygame.draw.rect(panel_surf, COLOR_BORDER, (0, 0, panel_w, panel_h), max(1, sm.scale_value(1)), border_radius=_sv(8))

        # Disegna il numero hint con Gold accent
        font_number = self._hud_font("segoeui", _sv(30), bold=True)
        hint_surf = font_number.render(str(available_hints), True, COLOR_ACCENT)
        hint_rect = hint_surf.get_rect(center=(panel_w // 2, _sv(22)))
        panel_surf.blit(hint_surf, hint_rect)

        # Disegna label "HINTS" in Off-white
        font_label = self._hud_font("segoeui", _sv(9), bold=False)
        label_surf = font_label.render("HINTS AVAILABLE", True, COLOR_TEXT)
        label_rect = label_surf.get_rect(center=(panel_w // 2, _sv(44)))
        panel_surf.blit(label_surf, label_rect)

        # Blit panel sulla schermata
        self.screen.blit(panel_surf, (panel_x, panel_y))

    def _draw_hint_button(self) -> None:
        """Disegna bottone hint con design glassmorphism premium e progress bar integrato."""
        if self.state != EngineState.SCENE:
            return
        # Su Android il pulsante hint è integrato nella barra HUD (HudManager).
        if self._is_android:
            return

        sm = self.scaling_manager

        # Costanti glassmorphism (coerente con HudManager)
        COLOR_BG = (15, 15, 25, 180)
        COLOR_BORDER = (80, 80, 110, 200)
        COLOR_ACCENT = (255, 215, 0)  # Gold
        COLOR_TEXT = (230, 235, 245)  # Off-white
        COLOR_SUCCESS = (60, 240, 120)  # Emerald
        COLOR_DANGER = (220, 40, 40)  # Crimson
        hs = 1.5 if self._is_android else 1.0
        def _sv(v):
            return sm.scale_value(v * hs)
        BORDER_RADIUS = _sv(10)

        # Panel dimensioni e posizione (box più grande su mobile)
        panel_w = _sv(90)
        panel_h = _sv(80)
        panel_x = sm.safe_right - panel_w
        panel_y = sm.safe_top + _sv(63)   # 55 (h_count) + 8 (gap)

        # Salva rettangolo per click detection
        btn_y_off = _sv(8)
        btn_h = _sv(30)
        self._hint_button_rect = pygame.Rect(panel_x + _sv(5), panel_y + btn_y_off, panel_w - _sv(10), btn_h)

        # Crea superficie trasparente
        panel_surf = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)

        # Disegna background con border radius
        pygame.draw.rect(panel_surf, COLOR_BG, (0, 0, panel_w, panel_h), border_radius=_sv(8))
        pygame.draw.rect(panel_surf, COLOR_BORDER, (0, 0, panel_w, panel_h), max(1, sm.scale_value(1)), border_radius=_sv(8))

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
        btn_rect = pygame.Rect(_sv(5), btn_y_off, panel_w - _sv(10), btn_h)
        pygame.draw.rect(panel_surf, btn_bg_color, btn_rect, border_radius=_sv(6))
        pygame.draw.rect(panel_surf, COLOR_BORDER, btn_rect, max(1, sm.scale_value(1)), border_radius=_sv(6))

        # Testo sul bottone
        font_btn = self._hud_font("segoeui", _sv(11), bold=True)
        btn_label = font_btn.render(btn_text, True, btn_text_color)
        btn_label_rect = btn_label.get_rect(center=(panel_w // 2, btn_y_off + btn_h // 2))
        panel_surf.blit(btn_label, btn_label_rect)

        # Progress bar per hint earning
        progress_y = btn_y_off + btn_h + _sv(6)
        progress_w = panel_w - _sv(10)
        progress_h = max(2, _sv(3))
        progress_x = _sv(5)

        # Background della progress bar
        pygame.draw.rect(panel_surf, (40, 40, 50, 130), (progress_x, progress_y, progress_w, progress_h), border_radius=_sv(1))

        # Fill della progress bar
        reward_tracker = self.level_manager.get_reward_tracker()
        if reward_tracker and not is_max_used:
            progress = reward_tracker.get_earn_progress()
            if progress > 0:
                fill_w = int(progress_w * progress)
                pygame.draw.rect(panel_surf, (*progress_color[:3], 140), (progress_x, progress_y, fill_w, progress_h), border_radius=_sv(1))

        # Testo informativo sotto progress bar
        info_y = progress_y + progress_h + _sv(10)
        font_info = self._hud_font("segoeui", _sv(10), bold=True)

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
        font = self._hud_font("segoeui", sm.scale_value(20), italic=True)
        label_text = self.lang(target_obj.label_key).upper()
        hint_text = f"{self.lang('hud_hint_seek')}: {label_text}"

        # Render con alpha
        hint_surf = font.render(hint_text, True, (100, 200, 255))
        hint_surf.set_alpha(alpha)

        # Posiziona in alto a destra, SOTTO il conteggio hint
        x = sm.safe_right - hint_surf.get_width()
        self.screen.blit(hint_surf, (x, sm.safe_top + sm.scale_value(230)))

    def show_hint_indicator(self, obj_instance_id: str) -> None:
        """Mostra l'indicatore hint per l'oggetto specificato per mezzo secondo."""
        if self.state == EngineState.SCENE:
            self._hint_indicator_target_obj = obj_instance_id
            self._hint_indicator_timer = 0.0

    def _psec(self, name: str, t0: float) -> None:
        """Accumula il tempo di una sezione di rendering (profiling Android)."""
        if self._is_android:
            import time as _t
            self._perf_sec[name] = self._perf_sec.get(name, 0.0) + (_t.perf_counter() - t0)

    def _draw(self) -> None:
        """Renderizza la logica corrente (delegate to state)."""
        if self.state == EngineState.MINIGAME:
            self.minigame_manager.draw()
        elif self.state == EngineState.BOOT:
            self.screen.fill((10, 10, 15)) # Colore splash
        elif self.state == EngineState.MENU:
            import time as _tb
            _tbg = _tb.perf_counter()
            self.screen.fill((20, 20, 25)) # Sfondo base scuro

            menu_cfg = self.game_config.get("menu", {})
            bg_path = menu_cfg.get("background")

            if bg_path:
                abs_bg = str(get_resource_path("games", self.game_id, bg_path))

                # --- Fallback statico per il video ---
                # Se lo sfondo è un video ma non possiamo riprodurlo (Android: niente
                # cv2, e gli .mp4 non sono nemmeno nell'APK), cerchiamo un'immagine
                # statica così il menu non resta nero. Ordine: background_static in
                # config -> menu_poster.jpg accanto -> stesso nome con .jpg/.png.
                if abs_bg.lower().endswith((".mp4", ".mov", ".mkv")) and not HAS_CV2:
                    candidates = []
                    static_cfg = menu_cfg.get("background_static")
                    if static_cfg:
                        candidates.append(str(get_resource_path("games", self.game_id, static_cfg)))
                    base_dir = os.path.dirname(abs_bg)
                    base_noext = os.path.splitext(abs_bg)[0]
                    candidates.append(os.path.join(base_dir, "menu_poster.jpg"))
                    candidates.extend([base_noext + ".jpg", base_noext + ".png"])
                    for cand in candidates:
                        if os.path.exists(cand):
                            abs_bg = cand
                            break

                # --- Gestione VIDEO MP4/MOV/MKV ---
                # HAS_CV2 guard: su Android cv2 non è disponibile e il video
                # viene silenziosamente skippato (rimane solo lo sfondo scuro
                # già renderizzato da self.screen.fill all'inizio del branch).
                if abs_bg.lower().endswith((".mp4", ".mov", ".mkv")) and HAS_CV2:
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
                # Skippiamo anche i file MP4/MOV/MKV se siamo arrivati qui:
                # senza cv2 (Android) `pygame.image.load("background.mp4")`
                # crasherebbe. In quel caso resta solo lo sfondo scuro base.
                elif not abs_bg.lower().endswith((".mp4", ".mov", ".mkv")):
                    if not hasattr(self, '_menu_bg_surface') or self._menu_video_path:
                        self._menu_video_path = None # Reset se passiamo da video a immagine
                        self._menu_bg_cover_key = None  # invalida cover cache
                        if os.path.exists(abs_bg):
                            self._menu_bg_surface = pygame.image.load(abs_bg).convert()
                        else:
                            self._menu_bg_surface = None
                    
                    # Scrim di leggibilità INCORPORATO nello sfondo (scurito UNA
                    # volta in cache): evita il blit SRCALPHA a schermo intero per
                    # frame, che su pygame ARM è lentissimo (~130ms!).
                    menu_state = getattr(self.menu_system, "state", "main")
                    scrim_alpha = 96 if menu_state == "main" else 172
                    if hasattr(self, '_menu_bg_surface') and self._menu_bg_surface:
                        # Cover-fill + scrim bakeato. Cache per (res, alpha).
                        if getattr(self, "_menu_bg_cover_key", None) != (self.res_w, self.res_h, scrim_alpha):
                            iw, ih = self._menu_bg_surface.get_size()
                            cover = max(self.res_w / iw, self.res_h / ih)
                            cw, ch = max(1, int(iw * cover)), max(1, int(ih * cover))
                            base = pygame.transform.smoothscale(self._menu_bg_surface, (cw, ch))
                            # Scurisci una sola volta (alpha a livello di superficie, opaco dopo)
                            dark = pygame.Surface((cw, ch))
                            dark.fill((8, 10, 18))
                            dark.set_alpha(scrim_alpha)
                            base.blit(dark, (0, 0))
                            self._menu_bg_cover = base
                            self._menu_bg_cover_pos = ((self.res_w - cw) // 2, (self.res_h - ch) // 2)
                            self._menu_bg_cover_key = (self.res_w, self.res_h, scrim_alpha)
                        self.screen.blit(self._menu_bg_cover, self._menu_bg_cover_pos)
                    else:
                        # Nessuno sfondo: riempi scuro (nessun blit alpha).
                        self.screen.fill((10, 12, 18))

            self._psec("menu_bg", _tbg)
            import time as _t
            _ts = _t.perf_counter()
            self.menu_system.draw(self.screen)
            self._psec("menu_sys", _ts)
            
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
                # Render-target PERSISTENTE (riusato): evita di allocare una Surface
                # full-screen ad ogni frame per i 3s di intro di ogni scena.
                rt = getattr(self, "_intro_render_target", None)
                if rt is None or rt.get_size() != original_screen.get_size():
                    rt = pygame.Surface(original_screen.get_size())
                    self._intro_render_target = rt
                rt.fill((0, 0, 0))
                render_target = rt
                self.screen = render_target
            else:
                self.screen.fill((0, 0, 0))  # Sfondo nero (letterbox)

            # ── Background ─────────────────────────────────────────────────────
            import time as _tsc_m
            _tsc = _tsc_m.perf_counter()
            # Priorità 1: Video Background (Scene)
            bg_v_path = getattr(self._current_scene_data, "background_path", "")
            is_scene_vid = bg_v_path.lower().endswith((".mp4", ".mov", ".mkv"))
            
            if is_scene_vid and os.path.exists(bg_v_path) and HAS_CV2:
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
                # Rettangolo EFFETTIVO (camera zoom/pan + intro scenic) per il blit.
                bx, by, bw, bh = sm.get_scenic_params(scenic_factor)
                bx, by, bw, bh = int(bx), int(by), int(bw), int(bh)

                # Cache BASE (senza camera): smoothscale una sola volta per scena.
                base_w, base_h = sm.base_bg_screen_size()
                if not hasattr(self, '_base_bg_scaled') or self._base_bg_params != (base_w, base_h, self._current_bg_surface):
                    self._base_bg_scaled = pygame.transform.smoothscale(self._current_bg_surface, (base_w, base_h))
                    self._base_bg_params = (base_w, base_h, self._current_bg_surface)
                    self._zoom_bg_scaled = None
                    self._zoom_bg_key = None

                if (bw, bh) == (base_w, base_h):
                    scaled_bg = self._base_bg_scaled
                else:
                    # Versione zoomata/scenica: si ricostruisce solo quando cambia la
                    # dimensione (zoom o intro), NON durante il pan a zoom costante.
                    # Scaliamo dal BG ORIGINALE a piena risoluzione (non dalla versione
                    # gia' ridotta a fit): ingrandendo per ispezionare si preserva il
                    # dettaglio, che e' lo scopo della feature in un HOG.
                    if getattr(self, '_zoom_bg_key', None) != (bw, bh):
                        self._zoom_bg_scaled = pygame.transform.smoothscale(
                            self._current_bg_surface, (max(1, bw), max(1, bh))
                        )
                        self._zoom_bg_key = (bw, bh)
                    scaled_bg = self._zoom_bg_scaled

                sh_x, sh_y = self.effects.shake_offset
                self.screen.blit(scaled_bg, (bx + sh_x, by + sh_y))

            # ── Oggetti ────────────────────────────────────────────────────────
            self._psec("scn_bg", _tsc); _tsc = _tsc_m.perf_counter()
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

                # Dimensione icona a schermo: hit-area in bg-space → pixel, applicando obj.scale
                obj_scale = getattr(obj, "scale", 1.0)
                icon_w = max(1, int(hit_w_bg * sm._bg_display_scale * scenic_factor * obj_scale))
                icon_h = max(1, int(hit_h_bg * sm._bg_display_scale * scenic_factor * obj_scale))

                # Clamp dimensioni per evitare smoothscale enormi. Su Android lo
                # schermo interno e' ~540p (max zoom 3x ~1600px): cap piu' basso.
                MAX_ICON_DIM = 1600 if self._is_android else 3000
                draw_w = min(icon_w, MAX_ICON_DIM)
                draw_h = min(icon_h, MAX_ICON_DIM)
                # Quantizza la dimensione su Android: durante il pinch-zoom
                # _bg_display_scale varia in continuo; senza snap la cache di TUTTI
                # gli oggetti si invaliderebbe ogni frame (smoothscale+warp x9/frame).
                if self._is_android:
                    _q = 8
                    draw_w = max(1, (draw_w // _q) * _q)
                    draw_h = max(1, (draw_h // _q) * _q)

                # --- Ottimizzazione: Cache dell'Oggetto ---
                obj_params = (
                    draw_w, draw_h, obj.rotation, obj.flip_x, obj.flip_y, 
                    obj.alpha, tuple(obj.color_filter), str(obj.corners),
                    getattr(obj, "grayscale", False), getattr(obj, "grayscale_factor", 1.0),
                    obj_scale
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
                        render_surf = apply_grayscale(render_surf, gs_f)

                    # 4. Filtro Colore (per-pixel multipliers)
                    if tuple(obj.color_filter) != (255, 255, 255):
                        tint = pygame.Surface(render_surf.get_size(), pygame.SRCALPHA)
                        tint.fill((*obj.color_filter, 255))
                        render_surf.blit(tint, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)

                    # Converti al formato display una volta sola: i blit per-frame
                    # successivi (cache hit) sono cosi' molto piu' veloci su ARM.
                    try:
                        render_surf = render_surf.convert_alpha()
                    except Exception:
                        pass

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

            # --- Evidenziazione HINT MANUALE: alone pulsante attorno all'oggetto
            # suggerito. Passaggio dedicato (non nel loop icone) perché molti
            # oggetti fanno parte dello sfondo e non hanno icona: vanno evidenziati
            # comunque, in base alla loro AREA DI HIT. Solo hint manuale (un
            # oggetto alla volta), niente auto-hint a catena.
            if self.hint:
                for _ho in self._current_scene_objects:
                    if _ho.found:
                        continue
                    _gi = self.hint.get_manual_glow(_ho)
                    if _gi <= 0.01:
                        continue
                    if _ho.detection_type == "rect":
                        _cxb = _ho.x + _ho.width / 2
                        _cyb = _ho.y + _ho.height / 2
                        _rb = max(_ho.width, _ho.height) / 2
                    else:
                        _cxb = _ho.x
                        _cyb = _ho.y
                        _rb = _ho.radius if _ho.radius > 0 else max(_ho.width, _ho.height) / 2
                    _scx, _scy = sm.bg_to_screen_scenic(_cxb, _cyb, scenic_factor)
                    _shk = self.effects.shake_offset
                    _base = int(_rb * sm._bg_display_scale * scenic_factor) + sm.scale_value(18)
                    if _base > 3:
                        _pulse = 0.5 + 0.5 * math.sin(pygame.time.get_ticks() * 0.010)
                        _rad = int(_base * (1.0 + 0.25 * _pulse))
                        _aa = min(1.0, _gi)
                        if self._is_android:
                            # Alone CACHATO per (raggio quantizzato, intensita'): prima si
                            # allocava una Surface SRCALPHA + 3 draw.circle (disco grande +
                            # 2 anelli) OGNI frame durante l'evidenziazione -> caro su GPU
                            # mobile. Ora i cerchi si disegnano una volta sola; il "pulse"
                            # resta dato dal raggio (quantizzato) e dall'intensita'.
                            _qr = max(4, (_rad // 6) * 6)
                            _gs = self._get_hint_glow(_qr, round(_aa, 2))
                            self.screen.blit(_gs, (int(_scx + _shk[0]) - _qr, int(_scy + _shk[1]) - _qr))
                        else:
                            _gs = pygame.Surface((_rad * 2, _rad * 2), pygame.SRCALPHA)
                            # Disco translucido + anello spesso luminoso (oro)
                            pygame.draw.circle(_gs, (255, 220, 60, int(70 * _aa * (0.6 + 0.4 * _pulse))), (_rad, _rad), _rad)
                            _rw = max(4, _rad // 6)
                            pygame.draw.circle(_gs, (255, 230, 80, int(235 * _aa)), (_rad, _rad), _rad, width=_rw)
                            pygame.draw.circle(_gs, (255, 250, 200, int(180 * _aa)), (_rad, _rad), max(1, _rad - _rw), width=max(2, _rw // 2))
                            self.screen.blit(_gs, (int(_scx + _shk[0]) - _rad, int(_scy + _shk[1]) - _rad))
            self._psec("scn_obj", _tsc); _tsc = _tsc_m.perf_counter()

            env_fx = [f for f in self._current_scene_effects if getattr(f, "type", "") != "bubble_tip"]

            # Quando c'è la torcia (e non l'hint-flash) gli effetti vanno disegnati
            # DOPO la maschera d'oscuramento, altrimenti li disegniamo subito qui
            # (così vengono catturati nello zoom intro). Evitiamo il doppio rendering.
            flashlight_active = bool(
                self._current_scene_data
                and getattr(self._current_scene_data, 'flashlight', False)
                and self._hint_flash_timer <= 0
            )
            if not flashlight_active:
                self.effects.draw(self.screen)
                self.fx_renderer.draw(self.screen, env_fx, sm, self.lang, scenic_factor)

            if is_intro_zooming:
                self.screen = original_screen
                # Trasforma l'intero render_target come un'unica immagine unita e centralo!
                tw = int(render_target.get_width() * zoom_factor)
                th = int(render_target.get_height() * zoom_factor)
                # Su Android scale (nearest, veloce): il movimento di zoom maschera
                # l'aliasing; smoothscale full-screen per frame e' troppo caro su ARM.
                scaled_rt = (pygame.transform.scale(render_target, (tw, th))
                             if self._is_android
                             else pygame.transform.smoothscale(render_target, (tw, th)))
                
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

            # --- EFFETTI E PARTICELLE (sopra la torcia, solo per scene flashlight) ---
            if flashlight_active:
                self.effects.draw(self.screen)
                self.fx_renderer.draw(self.screen, env_fx, sm, self.lang, scenic_factor=zoom_factor if is_intro_zooming else 1.0)

            self._psec("scn_fx", _tsc); _tsc = _tsc_m.perf_counter()
            # --- UI E FUMETTI (Sempre in primo piano) ---
            ui_fx = [f for f in self._current_scene_effects if getattr(f, "type", "") == "bubble_tip"]
            self._last_bubble_btns = self.fx_renderer.draw(self.screen, ui_fx, sm, self.lang, scenic_factor)

            self.hud.draw(self.screen, pygame.time.get_ticks() / 1000.0)
            self._psec("scn_hud", _tsc)

            # Disegna conteggio hint in alto a destra (sempre visibile)
            self._draw_hint_count()

            # Disegna bottone hint in alto a destra
            self._draw_hint_button()

            # Disegna indicatore target animato (su richiesta)
            self._draw_hint_indicator()

            # Onboarding coachmark (solo Android, una tantum). Non sovrapporlo a un
            # bubble intro modale: in quel caso resta attivo ma non disegnato.
            if self._coach_active and not self.level_manager.is_any_bubble_visible():
                self._draw_coachmark()

            # Overlay Lockdown per Anti-Spam
            if self._spam_lock_timer > 0:
                lock_surf = pygame.Surface(self.screen.get_size(), pygame.SRCALPHA)
                alpha = int(abs(math.sin(pygame.time.get_ticks() * 0.01)) * 40 + 20)
                lock_surf.fill((200, 0, 0, alpha))
                self.screen.blit(lock_surf, (0, 0))
            
        elif self.state == EngineState.PAUSE:
            # Pausa: oscuramento TOTALE per evitare "cheating" (vedere la scena a tempo fermo).
            # Un SINGOLO fill opaco col colore gia' combinato (prima: fill (10,10,15) + overlay
            # SRCALPHA (0,0,0,120) ricreato e blittato A TUTTO SCHERMO OGNI frame -> ~220ms e 4 FPS
            # su GPU mobile). Il fill copre comunque tutta la scena, quindi l'overlay era inutile.
            self.screen.fill((5, 5, 8))

            # Il menu system disegna i bottoni (Riprendi, Impostazioni, Esci) sopra l'oscuramento
            self.menu_system.draw(self.screen)
            
        elif self.state == EngineState.RESULTS:
            # Sfondo scuro per la schermata di risultati
            self.screen.fill((10, 10, 15))

            # Disegna la schermata di risultati premium
            self.results_screen.draw(self.screen)
                
        # Overlay grafico transizioni renderizzato SOPRA il resto
        self.transition_manager.draw(self.screen)

        # Overlay diagnostico FPS — solo Android (Windows EXE niente render extra).
        if self._is_android and self._perf_font is not None:
            try:
                fps = self.clock.get_fps()
                txt = self._perf_font.render(f"{fps:.0f} FPS", True, (255, 255, 0))
                bg = pygame.Surface((txt.get_width() + 12, txt.get_height() + 6), pygame.SRCALPHA)
                bg.fill((0, 0, 0, 170))
                ox, oy = self.scaling_manager.safe_left, self.scaling_manager.safe_top
                self.screen.blit(bg, (ox, oy))
                self.screen.blit(txt, (ox + 6, oy + 3))
            except Exception:
                pass

        # Misuro flip separato dal rendering interno (solo Android profiling).
        # Se flip domina → bottleneck nella pipeline SDL/GPU upload.
        # Se rendering interno domina → bottleneck nei pygame ops (fill/blit/draw).
        if self._is_android:
            import time as _time
            _t_flip = _time.perf_counter()
            pygame.display.flip()
            self._perf_acc_flip_ms += (_time.perf_counter() - _t_flip) * 1000.0
        else:
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
            font = self._hud_font("segoe ui black", font_size)
        except Exception:
            font = self._hud_font("impact", font_size)
            
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
