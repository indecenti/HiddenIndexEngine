"""
engine/hint_system.py

Sistema hint professionale con:
  - Auto-hint visuale (glow crescente dopo delay configurato) — UN oggetto alla volta
  - Hint manuale con cooldown e penalità punti
  - Intensità variabile per layer (oggetti nascosti = hint più visibile)
  - Tracciamento statistiche (hints_used)
  - Disabilitazione progressiva dopo N hint
"""

from typing import TYPE_CHECKING
from engine.utils import get_logger
import logging

if TYPE_CHECKING:
    from engine.scene_loader import SceneObject


class HintSystem:
    """
    Gestisce suggerimenti automatici e manuali durante la scena.

    Configurazione (game_config.json):
      layer_hint_intensity: { "objects_low": 1.8, "objects_mid": 1.0, "objects_high": 0.6 }

    Per oggetto (objects_catalog.json):
      default_hint_delay: 30 (secondi, sovrascrivibile in scene.json)

    Penalità:
      - Primo hint: -50 punti
      - Secondo: -75
      - Terzo+: -100 + disabilitazione
    """

    def __init__(self, scaling_manager, effects_engine) -> None:
        self.logger = get_logger(__name__)
        self.scaling_manager = scaling_manager
        self.effects_engine = effects_engine

        # Configurazione
        self.layer_hint_intensity = {
            "objects_low": 1.8,    # Nascosti → hint più visibile
            "objects_mid": 1.0,
            "objects_high": 0.6,
            "overlay": 0.4,
        }

        # Auto-hint: UN solo glow attivo alla volta, sull'oggetto che aspetta da più tempo
        self.auto_hint_enabled = True
        self.per_object_inactivity: dict = {}   # {obj_id: elapsed_seconds}
        self.per_object_hint_active: dict = {}  # {obj_id: glow_intensity [0-1]}
        self.per_object_glow_timeout: dict = {} # {obj_id: secondi di glow già mostrati}

        # Hint manuale: timer glow separato dal sistema auto
        self.per_object_manual_hint_timer: dict = {}  # {obj_id: remaining_glow_seconds}

        # Hint manuale: cooldown + penalità
        self.manual_hint_cooldown_max: float = 20.0
        self.manual_hint_cooldown: float = 0.0
        self.hints_used_total: int = 0
        self.hints_per_obj: dict = {}  # {obj_id: count}

        # Penalità punteggio (valori in punti)
        self.hint_penalties = [0, -50, -75, -100]  # indice = hints_used - 1
        self.max_hints_before_disable = 3  # Dopo 3 hint, il pulsante si disabilita

    def configure_layer_intensity(self, layer_config: dict) -> None:
        """Imposta l'intensità dei hint per layer."""
        if layer_config:
            self.layer_hint_intensity.update(layer_config)

    def reset_for_scene(self, scene_objects: list["SceneObject"]) -> None:
        """Resettar i timer e stato per una nuova scena."""
        self.per_object_inactivity = {obj.instance_id: 0.0 for obj in scene_objects if obj.is_goal}
        self.per_object_hint_active = {obj.instance_id: 0.0 for obj in scene_objects if obj.is_goal}
        self.per_object_glow_timeout = {obj.instance_id: 0.0 for obj in scene_objects if obj.is_goal}
        self.per_object_manual_hint_timer = {}
        self.hints_per_obj = {obj.instance_id: 0 for obj in scene_objects if obj.is_goal}
        self.hints_used_total = 0
        self.manual_hint_cooldown = 0.0

    def reset_object_timer(self, obj_id: str) -> None:
        """Azzera il timer di inattività quando oggetto è trovato."""
        if obj_id in self.per_object_inactivity:
            self.per_object_inactivity[obj_id] = 0.0
            self.per_object_hint_active[obj_id] = 0.0
            self.per_object_glow_timeout[obj_id] = 0.0
        self.per_object_manual_hint_timer.pop(obj_id, None)

    def update(self, dt: float, scene_objects: list["SceneObject"],
               layer_config: dict = None) -> None:
        """Aggiorna auto-hint e cooldown."""
        if layer_config:
            self.configure_layer_intensity(layer_config)

        # Aggiorna cooldown hint manuale
        if self.manual_hint_cooldown > 0:
            self.manual_hint_cooldown -= dt

        # Decrement manual hint glow timers
        for oid in list(self.per_object_manual_hint_timer.keys()):
            self.per_object_manual_hint_timer[oid] -= dt
            if self.per_object_manual_hint_timer[oid] <= 0:
                del self.per_object_manual_hint_timer[oid]

        # Aggiorna timer inattività per tutti gli oggetti non trovati
        for obj in scene_objects:
            if not obj.is_goal or obj.found:
                continue
            oid = obj.instance_id
            if oid not in self.per_object_inactivity:
                self.per_object_inactivity[oid] = 0.0
                self.per_object_hint_active[oid] = 0.0
                self.per_object_glow_timeout[oid] = 0.0
            self.per_object_inactivity[oid] += dt

        if not self.auto_hint_enabled:
            # Auto-hint disabilitato: aggiorna solo glow da hint manuali
            for obj in scene_objects:
                if not obj.is_goal or obj.found:
                    continue
                oid = obj.instance_id
                self.per_object_hint_active[oid] = self._manual_glow_intensity(obj)
            return

        unfound_goals = [obj for obj in scene_objects if obj.is_goal and not obj.found]

        # Trova IL PRIMO oggetto pronto per l'auto-hint.
        # Solo UN oggetto alla volta può avere il glow auto attivo,
        # per evitare di evidenziare tutta la scena contemporaneamente.
        auto_target_id = None
        for obj in unfound_goals:
            hint_delay = getattr(obj, 'hint_delay', 30)
            if self.per_object_inactivity.get(obj.instance_id, 0.0) >= hint_delay:
                auto_target_id = obj.instance_id
                break

        # Aggiorna glow per ciascun oggetto
        for obj in unfound_goals:
            oid = obj.instance_id

            # Il glow da hint manuale ha sempre la precedenza sull'auto-hint
            manual_intensity = self._manual_glow_intensity(obj)
            if manual_intensity > 0:
                self.per_object_hint_active[oid] = manual_intensity
                continue

            if oid == auto_target_id:
                # Calcola intensità glow crescente (0.3→1.0 nei 10s dopo il delay)
                hint_delay = getattr(obj, 'hint_delay', 30)
                time_after_delay = self.per_object_inactivity[oid] - hint_delay
                glow_intensity = min(1.0, 0.3 + (time_after_delay / 10.0) * 0.7)
                layer = getattr(obj, 'layer', 'objects_mid')
                glow_intensity *= self.layer_hint_intensity.get(layer, 1.0)
                glow_intensity = min(1.0, glow_intensity)
                self.per_object_hint_active[oid] = glow_intensity

                # Avanza il timeout del glow (finestra di 15 secondi)
                self.per_object_glow_timeout[oid] += dt
                if self.per_object_glow_timeout[oid] >= 15.0:
                    # Finestra completata: spegni e resetta i timer così il ciclo
                    # potrà ricominciare dopo un nuovo hint_delay completo
                    self.per_object_hint_active[oid] = 0.0
                    self.per_object_inactivity[oid] = 0.0
                    self.per_object_glow_timeout[oid] = 0.0
            else:
                # Non è il turno di questo oggetto: nessun glow auto
                self.per_object_hint_active[oid] = 0.0

    def _manual_glow_intensity(self, obj: "SceneObject") -> float:
        """Restituisce l'intensità glow del hint manuale per questo oggetto [0-1]."""
        remaining = self.per_object_manual_hint_timer.get(obj.instance_id, 0.0)
        if remaining <= 0:
            return 0.0
        layer = getattr(obj, 'layer', 'objects_mid')
        intensity = 1.5 * self.layer_hint_intensity.get(layer, 1.0)
        return min(1.0, intensity)

    def get_hint_intensity(self, obj_id: str) -> float:
        """Restituisce intensità glow per oggetto [0-1]."""
        return self.per_object_hint_active.get(obj_id, 0.0)

    def get_manual_glow(self, obj: "SceneObject") -> float:
        """Glow del SOLO hint manuale (pressione bottone): evidenzia UN oggetto
        alla volta per ~1.2s. Esclude l'auto-hint, così non sembra che il gioco
        suggerisca tutti gli oggetti a catena."""
        return self._manual_glow_intensity(obj)

    def use_manual_hint(self, remaining_objects: list["SceneObject"], suppress_fx: bool = False) -> tuple[bool, int]:
        """
        Hint manuale: evidenzia il primo oggetto non trovato.

        Returns: (successo, penalità_punti)
        """
        # Controlli
        if self.manual_hint_cooldown > 0:
            self.logger.debug(f"Hint in cooldown: {self.manual_hint_cooldown:.1f}s")
            return False, 0

        if self.hints_used_total >= self.max_hints_before_disable:
            self.logger.debug("Numero massimo di hint raggiunto")
            return False, 0

        # Trova primo oggetto non ancora trovato
        goals = [o for o in remaining_objects if o.is_goal and not o.found]
        if not goals:
            return False, 0

        obj = goals[0]

        # Traccia hint usato
        self.hints_used_total += 1
        self.hints_per_obj[obj.instance_id] = self.hints_per_obj.get(obj.instance_id, 0) + 1

        # Calcola penalità punti
        hints_count = self.hints_per_obj[obj.instance_id]
        penalty_idx = min(hints_count - 1, len(self.hint_penalties) - 1)
        penalty = self.hint_penalties[penalty_idx]

        # Cooldown e reset timer inattività (così l'auto-hint non ri-scatta subito)
        self.manual_hint_cooldown = self.manual_hint_cooldown_max
        self.per_object_inactivity[obj.instance_id] = 0.0
        self.per_object_glow_timeout[obj.instance_id] = 0.0

        if not suppress_fx:
            # Glow manuale: 2.5 secondi (ben visibile) tramite timer separato
            self.per_object_manual_hint_timer[obj.instance_id] = 2.5

            # Effetto particelle CENTRATO sull'oggetto
            if obj.detection_type == "rect":
                cx = obj.x + obj.width / 2
                cy = obj.y + obj.height / 2
            else:
                cx = obj.x
                cy = obj.y
            self.effects_engine.spawn_hint_effect(cx, cy)

        self.logger.info(f"Hint manuale: {obj.instance_id} | Penalità: {penalty} pt | Hints: {self.hints_used_total}")

        return True, penalty

    def can_use_hint(self) -> bool:
        """Controlla se il pulsante hint è abilitato."""
        return (self.manual_hint_cooldown <= 0 and
                self.hints_used_total < self.max_hints_before_disable)

    def get_cooldown_percent(self) -> float:
        """Restituisce percentuale cooldown [0-1] per HUD."""
        if self.manual_hint_cooldown_max == 0:
            return 0.0
        return max(0.0, self.manual_hint_cooldown / self.manual_hint_cooldown_max)

    def get_stats(self) -> dict:
        """Restituisce statistiche per salvataggio/achievement."""
        return {
            "hints_used": self.hints_used_total,
            "per_object": self.hints_per_obj.copy(),
            "no_hints_achievement": self.hints_used_total == 0,
        }
