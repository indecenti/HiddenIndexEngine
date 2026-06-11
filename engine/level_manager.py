"""
engine/level_manager.py

Gestione dello stato di gioco: livello corrente, scena corrente,
punteggio, timer, eventi di completamento e preloading predittivo.

Responsabilità:
  - Tenere il conteggio oggetti trovati / totali
  - Decrementare il timer e determinare se la scena è completata
  - Calcolare il punteggio (base + bonus tempo + moltiplicatore stelle)
  - Emettere eventi: SCENE_COMPLETE, LEVEL_COMPLETE, SCENE_FAILED
  - Avviare il preload della scena successiva al momento giusto:
      · quando ≥ 70% degli oggetti sono stati trovati
      · oppure quando il timer è ≤ 40% del limite (trigger temporale)

Logica timer_behavior:
  "complete"  — alla scadenza la scena avanza comunque (modalità casual)
  "fail"      — alla scadenza la scena viene fallita e riavviata (modalità hard)

Punteggio:
  punti_base  = POINTS_PER_OBJECT * oggetti_trovati
  bonus_tempo = int(time_left / time_total * BONUS_TIME_MAX)   [solo se all found]
  stelle      = 3 se trovati >= richiesti e bonus >= 66%
                2 se trovati >= richiesti
                1 altrimenti
  score_scene = (punti_base + bonus_tempo) * moltiplicatore_stelle
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Optional, TYPE_CHECKING, Tuple

import pygame

from engine.json_validator import load_and_validate
from engine.scene_loader import SceneLoader, SceneData
from engine.utils import get_resource_path, get_logger

if TYPE_CHECKING:
    pass

log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Costanti punteggio
# ---------------------------------------------------------------------------

POINTS_PER_OBJECT = 100
BONUS_TIME_MAX    = 500   # massimo bonus tempo per scena
STAR_MULTIPLIER   = {1: 1, 2: 1, 3: 2}   # moltiplicatore per stelle

# Soglie preload predittivo
PRELOAD_FOUND_RATIO  = 0.70   # avvia preload quando >= 70% trovati
PRELOAD_TIME_RATIO   = 0.40   # avvia preload quando <= 40% timer rimanente

# Penalità
MISS_PENALTY_TIME    = 5.0    # secondi aggiunti per ogni click a vuoto
MISS_PENALTY_SCORE   = -25    # punteggio base sottratto per ogni click a vuoto
# Curva progressiva sui miss consecutivi e finestra (secondi) entro cui un miss
# conta come "consecutivo". FONTE UNICA DI VERITA' condivisa col runtime web
# (game.js::_missPenalty) via web_rules.engine_rules() -> manifest.rules.
MISS_PENALTY_CURVE   = [25, 50, 100, 150, 300, 500]
MISS_COMBO_WINDOW    = 1.5

# ---------------------------------------------------------------------------
# Evento custom Pygame
# ---------------------------------------------------------------------------

SCENE_COMPLETE = pygame.USEREVENT + 1
LEVEL_COMPLETE = pygame.USEREVENT + 2
SCENE_FAILED   = pygame.USEREVENT + 3


@dataclass
class SceneResult:
    """Risultato di una scena completata."""
    scene_id: str
    found: int
    total: int
    time_left: float
    time_total: float
    score: int
    stars: int
    failed: bool = False
    hints_used: int = 0  # Numero di hint usati durante la scena


@dataclass
class LevelState:
    """Stato corrente del livello."""
    level_id: str
    scene_ids: list[str]
    current_scene_index: int = 0
    total_score: int = 0
    scene_results: list[SceneResult] = field(default_factory=list)

    @property
    def current_scene_id(self) -> str:
        return self.scene_ids[self.current_scene_index]

    @property
    def is_last_scene(self) -> bool:
        return self.current_scene_index >= len(self.scene_ids) - 1


class RewardTracker:
    """Traccia combo, bonus, e earning di hint durante una scena."""

    def __init__(self, config: dict, initial_hints: int = 2) -> None:
        self.config = config.get("hint_earn_config", {})
        self.initial_hints = initial_hints
        self.available_hints = initial_hints

        # Timing
        self.scene_start_time = time.time()
        self.last_find_time = None

        # Combo tracking
        self.combo_count = 0
        self.combo_threshold = self.config.get("combo_thresholds", [])[0].get("time", 2.0) if self.config.get("combo_thresholds") else 2.0

        # First-second bonus
        self.first_find_done = False
        self.first_second_bonus_earned = False

        # Accumulator
        self.earned_hints_this_scene = 0
        self.progress_to_next_hint = 0.0  # [0-1]

    def on_object_found(self, dt_since_scene_start: float) -> Tuple[int, int, int]:
        """
        Chiamato quando un oggetto è trovato.
        Ritorna: (combo_level, hints_earned_total, bonus_points)
        """
        now = time.time()
        self.last_find_time = now

        # First-second bonus
        bonus_points = 0
        hints_earned = 0

        if not self.first_find_done:
            self.first_find_done = True
            if dt_since_scene_start <= 1.0:
                first_bonus = self.config.get("first_second_bonus", 50)
                bonus_points += first_bonus
                self.first_second_bonus_earned = True

        # Combo checking - cerca il threshold che questo oggetto raggiunge
        combo_level = self._check_combo_threshold(dt_since_scene_start)

        # Accumula progress per il prossimo hint con curva di difficoltà progressiva
        # Più hint guadagni nella scena, più oggetti servono per il prossimo.
        # 1° extra: 5 oggetti (+0.20) | 2° extra: 7 oggetti (+0.143) | 3° extra: 9 oggetti (+0.112)
        earned = self.earned_hints_this_scene
        if earned == 0:
            increment = 0.20
        elif earned == 1:
            increment = 0.143
        elif earned == 2:
            increment = 0.112
        else:
            increment = 0.05

        # Bonus Skill: le combo velocizzano il guadagno (+0.02 per livello combo)
        increment += (combo_level * 0.02)
        
        self.progress_to_next_hint = min(1.0, self.progress_to_next_hint + increment)

        # Se progress raggiunge 1.0, guadagna hint
        if self.progress_to_next_hint >= 1.0:
            self.available_hints += 1
            hints_earned = 1
            self.earned_hints_this_scene += 1
            self.progress_to_next_hint = 0.0

        return (combo_level, hints_earned, bonus_points)

    def _check_combo_threshold(self, dt_since_scene_start: float) -> int:
        """Controlla quale threshold di combo è stato raggiunto."""
        thresholds = self.config.get("combo_thresholds", [])

        combo_level = 0
        for threshold in thresholds:
            if dt_since_scene_start <= threshold.get("time", 100):
                combo_level += 1

        return combo_level

    def add_hint(self) -> None:
        """Aggiungi un hint guadagnato."""
        self.available_hints += 1
        self.earned_hints_this_scene += 1

    def consume_hint(self) -> bool:
        """Consuma un hint se disponibile."""
        if self.available_hints > 0:
            self.available_hints -= 1
            return True
        return False

    def get_earn_progress(self) -> float:
        """Ritorna [0-1] progress al prossimo hint guadagnato."""
        return self.progress_to_next_hint

    def get_available_hints(self) -> int:
        """Ritorna il numero di hint disponibili."""
        return self.available_hints

    def get_stats(self) -> dict:
        """Ritorna statistiche di questa scena."""
        return {
            "available_hints": self.available_hints,
            "earned_this_scene": self.earned_hints_this_scene,
            "first_second_bonus_earned": self.first_second_bonus_earned,
        }


class LevelManager:
    def __init__(self, game_id: str, scene_loader: SceneLoader, hint_system=None) -> None:
        self._game_id = game_id
        self._loader = scene_loader
        self._hint_system = hint_system

        self._level_state: Optional[LevelState] = None
        self._scene_data: Optional[SceneData] = None

        # Timer
        self._time_elapsed: float = 0.0
        self._time_total: float = 0.0
        self._timer_running: bool = False

        # Score corrente scena
        self._scene_score: int = 0

        # Reward tracking
        self._reward_tracker: Optional[RewardTracker] = None
        self._game_config: dict = {}

        # Flags preload
        self._preload_triggered_found: bool = False
        self._preload_triggered_time: bool = False

        # Flag completamento già inviato (evita doppio evento)
        self._scene_complete_sent: bool = False

        # Statistiche scena
        self._miss_clicks: int = 0
        
        # Stato Bubble Tips
        self._end_bubbles_triggered = False

    def is_any_bubble_visible(self) -> bool:
        """Ritorna True se c'è almeno un fumetto attivo che blocca il gioco."""
        if not self._scene_data: return False
        for fx in self._scene_data.effects:
            if fx.type == "bubble_tip" and getattr(fx, "_visible", False):
                return True
        return False

    def has_start_scene_bubbles(self) -> bool:
        """Ritorna True se la scena corrente ha dei fumetti previsti all'inizio."""
        if not self._scene_data: return False
        for fx in self._scene_data.effects:
            if fx.type == "bubble_tip" and getattr(fx, "trigger", "") == "start_scene":
                return True
        return False

    def set_game_config(self, config: dict) -> None:
        """Imposta la configurazione del gioco."""
        self._game_config = config

    def get_available_levels(self) -> list[str]:
        """Ritorna una lista di ID dei livelli disponibili per il gioco attuale."""
        root = get_resource_path("games", self._game_id, "levels")
        if not root.exists():
            return []
        # Consideriamo validi solo i folder che contengono un level_config.json
        dirs = [d.name for d in root.iterdir() if d.is_dir() and (d / "level_config.json").exists()]
        
        levels_order = self._game_config.get("levels", [])
        order_map = {lvl_id: i for i, lvl_id in enumerate(levels_order)}
        
        registered = [d for d in dirs if d in order_map]
        orphans = [d for d in dirs if d not in order_map]
        
        registered.sort(key=lambda x: order_map[x])
        orphans.sort()
        
        return registered + orphans

    # ------------------------------------------------------------------
    # Avvio livello
    # ------------------------------------------------------------------

    def start_level(self, level_id: str, start_scene_index: int = 0) -> SceneData:
        """
        Carica la configurazione del livello e avvia la scena specificata.
        Restituisce la SceneData della scena di partenza.
        """
        level_cfg = self._load_level_config(level_id)
        scene_ids = [s["id"] for s in level_cfg.get("scenes", [])]
        if not scene_ids:
            raise ValueError(f"Livello '{level_id}' senza scene definite")

        if start_scene_index >= len(scene_ids):
            start_scene_index = 0

        self._level_state = LevelState(
            level_id=level_id,
            scene_ids=scene_ids,
            current_scene_index=start_scene_index
        )
        scene_id = scene_ids[start_scene_index]
        log.info("Livello '%s' avviato dalla scena index %d (%s)", 
                 level_id, start_scene_index, scene_id)
        return self._load_and_start_scene(level_id, scene_id, level_cfg)

    def _load_level_config(self, level_id: str) -> dict:
        path = get_resource_path("games", self._game_id,
                                  "levels", level_id, "level_config.json")
        return load_and_validate(path, "level_config")

    def _get_scene_cfg(self, level_cfg: dict, scene_id: str) -> dict:
        for s in level_cfg.get("scenes", []):
            if s["id"] == scene_id:
                return s
        return {}

    def _load_and_start_scene(self, level_id: str, scene_id: str,
                               level_cfg: dict) -> SceneData:
        scene_cfg = self._get_scene_cfg(level_cfg, scene_id)
        self._scene_data = self._loader.load_scene(level_id, scene_id)

        # Inizializza visibilità Bubble Tips
        for fx in self._scene_data.effects:
            if fx.type == "bubble_tip":
                # La visibilità iniziale viene gestita dal Core dopo l'intro zoom
                fx._visible = False

        time_limit = float(scene_cfg.get("time_limit", 120))
        self._time_total = time_limit
        self._time_elapsed  = 0.0
        self._timer_running  = True
        self._scene_score    = 0
        self._preload_triggered_found = False
        self._preload_triggered_time  = False
        self._scene_complete_sent     = False
        self._miss_clicks             = 0
        self._last_miss_real_time    = 0.0    # Tempo reale dell'ultimo miss (per spam detection)
        self._consecutive_misses     = 0      # Contatore per penalità progressiva
        self._end_bubbles_triggered   = False
        self._end_scene_delay         = 2.25  # Pausa scenografica epica prima dei popup di fine livello

        # Reset del sistema hint per la nuova scena
        if self._hint_system:
            self._hint_system.reset_for_scene(self._scene_data.objects)

        # Creazione reward tracker (2 hint iniziali per scena)
        initial_hints = self._game_config.get("hint_earn_config", {}).get("hints_per_scene", 2)
        self._reward_tracker = RewardTracker(self._game_config, initial_hints)

        total_goals = self._total_count()
        log.info("Scena '%s' avviata — cronometro attivo — OBIETTIVI: %d",
                 scene_id, total_goals)
        return self._scene_data

    # ------------------------------------------------------------------
    # Update frame
    # ------------------------------------------------------------------

    def update(self, dt: float) -> None:
        """
        Aggiorna il timer e controlla condizioni di completamento/fallimento.
        Deve essere chiamato ogni frame dal game loop.
        Emette eventi pygame in coda.
        """
        if self._scene_data is None or self._level_state is None:
            return
        if not self._timer_running or self._scene_complete_sent:
            return

        # Controlla completamento oggetti
        found = self._found_count()
        total = self._total_count()

        # Incrementa timer (countup) finché non sono trovati tutti
        if found < total:
            self._time_elapsed += dt

        # Preload predittivo — oggetti
        if (not self._preload_triggered_found and total > 0
                and found / total >= PRELOAD_FOUND_RATIO):
            self._trigger_preload()
            self._preload_triggered_found = True

        # Tutti trovati → Trigger Bubbles Finali o SCENE_COMPLETE
        if found == total and total > 0 and not self._scene_complete_sent:
            
            # Attendi il ritardo di scena prima di mostrare gli UI / Bubbles tip
            if getattr(self, "_end_scene_delay", 0.0) > 0:
                self._end_scene_delay -= dt
                return
            # Se ci sono bubble di fine scena non ancora attivate, attivale
            has_end_bubbles = any(fx.type == "bubble_tip" and fx.trigger == "end_scene" for fx in self._scene_data.effects)
            
            if has_end_bubbles and not self._end_bubbles_triggered:
                for fx in self._scene_data.effects:
                    if fx.type == "bubble_tip" and fx.trigger == "end_scene":
                        fx._visible = True
                        log.info("Attivata bubble tip di fine scena.")
                self._end_bubbles_triggered = True
            
            # Se tutte le bubble (comprese quelle appena attivate) sono chiuse, procedi
            if not self.is_any_bubble_visible():
                self._emit_scene_complete(failed=False)
            return

    def _trigger_preload(self) -> None:
        """Avvia il preloading della scena successiva se disponibile."""
        if self._level_state is None or self._level_state.is_last_scene:
            return
        next_idx = self._level_state.current_scene_index + 1
        next_id  = self._level_state.scene_ids[next_idx]
        level_id = self._level_state.level_id
        if not self._loader.is_preload_ready(next_id):
            log.debug("Avvio preload predittivo scena '%s'", next_id)
            self._loader.start_preload(level_id, next_id)

    # ------------------------------------------------------------------
    # Azioni esterne
    # ------------------------------------------------------------------

    def register_found(self, instance_id: str) -> tuple:
        """
        Notifica al LevelManager che un oggetto è stato trovato.
        Ritorna: (combo_level, hints_earned, bonus_points) per gli effetti visivi
        """
        if self._scene_data is None:
            return (0, 0, 0)

        combo_level = 0
        hints_earned = 0
        bonus_points = 0

        for obj in self._scene_data.objects:
            if obj.instance_id == instance_id and not obj.found and obj.is_goal:
                obj.found = True
                self._scene_score += POINTS_PER_OBJECT

                # Aggiorna reward tracker
                if self._reward_tracker:
                    dt_since_start = self._time_elapsed
                    combo_level, hints_earned, bonus_points = self._reward_tracker.on_object_found(dt_since_start)
                    self._scene_score += bonus_points

                log.debug("Trovato '%s' — score scena: %d (+ %d bonus)", instance_id, self._scene_score, bonus_points)

                # Resetta il timer di hint per questo oggetto
                if self._hint_system:
                    self._hint_system.reset_object_timer(instance_id)

                return (combo_level, hints_earned, bonus_points)

        return (0, 0, 0)

    def register_miss(self) -> int:
        """Registra un click a vuoto e applica penalità di tempo e punteggio progressiva lineare."""
        if self._scene_data is None or self._scene_complete_sent:
            return 0
        
        # Usiamo il tempo reale per rilevare la frequenza fisica dei click dell'utente
        now_real = time.time()
        if now_real - self._last_miss_real_time < MISS_COMBO_WINDOW:
            self._consecutive_misses += 1
        else:
            self._consecutive_misses = 1

        self._last_miss_real_time = now_real
        self._miss_clicks += 1

        # 1. Penalità temporale fissa (5.0s)
        self._time_elapsed += MISS_PENALTY_TIME

        # 2. Penalità punteggio progressiva: -25, -50, -100, -150, -300, -500
        penalty = -self.miss_penalty(self._consecutive_misses)
        
        self.apply_score_penalty(penalty)
        
        log.info("MISS CLICK! Cons: %d | Time +%.1fs | Score %d. Totale miss: %d",
                 self._consecutive_misses, MISS_PENALTY_TIME, penalty, self._miss_clicks)
        
        return penalty

    def apply_score_penalty(self, penalty: int) -> None:
        """Applica una penalità punteggio. Permette punteggi negativi."""
        if self._scene_data is None or self._scene_complete_sent:
            return
        # Rimosso il max(0, ...) per permettere il punteggio negativo come richiesto
        self._scene_score += penalty
        log.info("Penalità punteggio applicata: %d. Score scena: %d", penalty, self._scene_score)

    def add_score(self, points: int) -> None:
        """Aggiunge punti allo score della scena (usato dai minigiochi)."""
        if self._scene_data is None:
            return
        self._scene_score += points
        log.info("Punteggio aggiunto via minigioco: %d. Totale scena: %d", points, self._scene_score)

    # Reward Tracker accessors
    def get_reward_tracker(self) -> Optional[RewardTracker]:
        """Ritorna il reward tracker corrente."""
        return self._reward_tracker

    def consume_hint_from_rewards(self) -> bool:
        """Consuma un hint dal pool guadagnato. Ritorna True se disponibile."""
        if self._reward_tracker:
            return self._reward_tracker.consume_hint()
        return False

    def get_available_hints(self) -> int:
        """Ritorna i hint disponibili nel reward tracker."""
        if self._reward_tracker:
            return self._reward_tracker.get_available_hints()
        return 0

    def advance_to_next_scene(self) -> Optional[SceneData]:
        """
        Passa alla scena successiva del livello.
        Restituisce la nuova SceneData, oppure None se il livello è finito.
        """
        if self._level_state is None:
            return None
        if self._level_state.is_last_scene:
            self._emit_level_complete()
            return None

        self._level_state.current_scene_index += 1
        level_id  = self._level_state.level_id
        scene_id  = self._level_state.current_scene_id
        level_cfg = self._load_level_config(level_id)
        return self._load_and_start_scene(level_id, scene_id, level_cfg)

    def retry_current_scene(self) -> SceneData:
        """Ricarica la scena corrente (usato dopo SCENE_FAILED)."""
        if self._level_state is None:
            raise RuntimeError("Nessun livello attivo")
        level_id  = self._level_state.level_id
        scene_id  = self._level_state.current_scene_id
        level_cfg = self._load_level_config(level_id)
        return self._load_and_start_scene(level_id, scene_id, level_cfg)

    # ------------------------------------------------------------------
    # Emissione eventi
    # ------------------------------------------------------------------

    def _emit_scene_complete(self, failed: bool) -> None:
        self._timer_running = False
        self._scene_complete_sent = True
        result = self._build_result(failed=failed)
        if self._level_state:
            self._level_state.total_score += result.score
            self._level_state.scene_results.append(result)
        log.info("SCENE_COMPLETE '%s' — score=%d stelle=%d failed=%s",
                 result.scene_id, result.score, result.stars, failed)
        pygame.event.post(pygame.event.Event(SCENE_COMPLETE, result=result))

    def _emit_scene_failed(self) -> None:
        self._timer_running = False
        self._scene_complete_sent = True
        result = self._build_result(failed=True)
        log.info("SCENE_FAILED '%s'", result.scene_id)
        pygame.event.post(pygame.event.Event(SCENE_FAILED, result=result))

    def _emit_level_complete(self) -> None:
        log.info("LEVEL_COMPLETE '%s' — score totale=%d",
                 self._level_state.level_id if self._level_state else "?",
                 self._level_state.total_score if self._level_state else 0)
        pygame.event.post(pygame.event.Event(
            LEVEL_COMPLETE,
            level_id=self._level_state.level_id if self._level_state else "",
            total_score=self._level_state.total_score if self._level_state else 0,
            scene_results=list(self._level_state.scene_results) if self._level_state else [],
        ))

    # ------------------------------------------------------------------
    # Calcolo risultato / punteggio
    # ------------------------------------------------------------------

    def _build_result(self, failed: bool) -> SceneResult:
        found = self._found_count()
        total = self._total_count()
        bonus, stars, score = self.compute_scene_score(
            found, total, self._scene_score,
            self._time_elapsed, self._time_total, failed,
        )

        hints_used = 0
        if self._hint_system:
            hints_used = self._hint_system.hints_used_total

        return SceneResult(
            scene_id=self._scene_data.id if self._scene_data else "",
            found=found,
            total=total,
            time_left=max(0.0, self._time_total - self._time_elapsed),
            time_total=self._time_total,
            score=score,
            stars=stars,
            failed=failed,
            hints_used=hints_used,
        )

    @staticmethod
    def _calc_stars(found: int, total: int, bonus: int, failed: bool) -> int:
        if failed or found < total:
            return 1
        bonus_ratio = bonus / BONUS_TIME_MAX if BONUS_TIME_MAX > 0 else 0
        return 3 if bonus_ratio >= 0.66 else 2

    @staticmethod
    def compute_scene_score(
        found: int, total: int, scene_score: int,
        time_elapsed: float, time_total: float, failed: bool,
    ) -> tuple[int, int, int]:
        """Calcolo PURO di (bonus, stars, score) di una scena.

        Fonte unica di verita' dello scoring lato engine: usato sia da
        _build_result sia dai test di parita' Python<->JS (tests/test_web_sync.py).
        Il runtime web (game.js::_doFinish) DEVE replicare questa stessa formula.
        """
        bonus = 0
        if not failed and found == total and time_total > 0:
            # Bonus tempo se trovi tutto prima del 'time_total' suggerito.
            time_ratio = max(0, time_total - time_elapsed) / time_total
            bonus = int(time_ratio * BONUS_TIME_MAX)   # troncamento (verso zero)
        stars = LevelManager._calc_stars(found, total, bonus, failed)
        score = (scene_score + bonus) * STAR_MULTIPLIER.get(stars, 1)
        return bonus, stars, score

    @staticmethod
    def miss_penalty(consecutive_misses: int) -> int:
        """Penalita' punteggio (valore positivo) per un click a vuoto, data la
        lunghezza della sequenza di miss consecutivi.

        Curva progressiva = MISS_PENALTY_CURVE. Fonte unica di verita' replicata
        dal runtime web (game.js::_missPenalty), verificata in test_web_sync.py.
        """
        idx = min(max(consecutive_misses, 1) - 1, len(MISS_PENALTY_CURVE) - 1)
        return MISS_PENALTY_CURVE[idx]

    # ------------------------------------------------------------------
    # Accessors
    # ------------------------------------------------------------------

    @property
    def time_elapsed(self) -> float:
        return self._time_elapsed

    @property
    def time_total(self) -> float:
        return self._time_total

    @property
    def scene_score(self) -> int:
        return self._scene_score

    @property
    def total_score(self) -> int:
        if self._level_state:
            return self._level_state.total_score
        return 0

    @property
    def current_scene(self) -> Optional[SceneData]:
        return self._scene_data

    @property
    def current_level_id(self) -> str:
        return self._level_state.level_id if self._level_state else ""

    @property
    def current_scene_id(self) -> str:
        return self._level_state.current_scene_id if self._level_state else ""

    def _found_count(self) -> int:
        if self._scene_data is None:
            return 0
        return sum(1 for o in self._scene_data.objects if o.found and o.is_goal)

    def _total_count(self) -> int:
        if self._scene_data is None:
            return 0
        return sum(1 for o in self._scene_data.objects if o.is_goal)
