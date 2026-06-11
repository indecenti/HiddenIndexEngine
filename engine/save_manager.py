"""
engine/save_manager.py

Gestisce il salvataggio strutturato e la persistenza dei progressi.
Il target JSON risiede nella cartella saves determinata dal modulo utils.
"""

import json
from typing import Any
from pathlib import Path

from engine.utils import get_writable_path, get_logger, safe_write_json

class SaveManager:
    """Implementa i requisiti di read/write progressi basati sul Game ID."""
    
    def __init__(self, game_id: str) -> None:
        self.game_id = game_id
        self.logger = get_logger(__name__)
        # Genera il file con get_writable_path (root/saves/save_ID.json)
        self.save_path: Path = get_writable_path(f"save_{self.game_id}.json")
        self.data: dict[str, Any] = self._get_default_save()
        self.load()

    def _get_default_save(self) -> dict[str, Any]:
        """Blueprint del salvataggio vuoto."""
        return {
            "version": "1.0",
            "current_level": None,       # livello su cui si trovava l'utente se esce
            "current_scene": None,       # scena mid-level (nome)
            "current_scene_index": 0,    # indice della scena attuale nel livello (per resume)
            "scores": {},                # dict di map level_id -> {scene_id: score}
            "stars": {},                 # dict di map level_id -> {scene_id: stars}
            "unlocked_levels": [],       # array di IDs livelli sbloccati
            "unlocked_scenes": {},       # dict: level_id -> max_unlocked_index
            "achievements": [],          # lista ids degli achievement già bloccati
            "temp_level_score": 0        # Punteggio intermedio durante sessione
        }

    def load(self) -> None:
        """Carica da file se disponibile ed unisce chiavi necessarie."""
        if not self.save_path.exists():
            self.logger.info(f"Nessun file {self.save_path.name} individuato. Stato vergine inizializzato.")
            self.save()
            return
            
        try:
            with open(self.save_path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                # Un merge shallow previene corruzioni/incompatibilità future sugli alberi di dict
                self.data.update(loaded)
            self.logger.info("Salvataggio letto e normalizzato con successo.")
        except Exception as e:
            self.logger.error(
                f"Impossibile leggere file salvataggio ({e}). "
                "Metto in quarantena il file e rigenero stato locale sicuro."
            )
            # Il file su disco potrebbe contenere progressi recuperabili: lo preserviamo
            # con un suffisso .corrupt-<ts> invece di sovrascriverlo con il default.
            self._quarantine_corrupt_save()
            self.data = self._get_default_save()
            self.save()

    def _quarantine_corrupt_save(self) -> None:
        """Rinomina un salvataggio illeggibile in un sidecar .corrupt-<timestamp>.

        Evita che un errore di lettura transitorio (o una scrittura parziale di
        una vecchia versione) distrugga in modo permanente i progressi: il file
        originale resta su disco e può essere ispezionato/recuperato a mano.
        """
        try:
            if not self.save_path.exists():
                return
            from datetime import datetime
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            quarantined = self.save_path.with_name(f"{self.save_path.name}.corrupt-{ts}")
            self.save_path.replace(quarantined)
            self.logger.warning(f"Salvataggio illeggibile messo in quarantena: {quarantined.name}")
        except Exception as e:
            self.logger.error(f"Impossibile mettere in quarantena il salvataggio corrotto: {e}")

    def save(self) -> None:
        """
        Flush su disco — atomic write per non corrompere mai i progressi.
        Un crash a metà write (chiusura forzata del gioco) non lascia più il
        save in stato semi-scritto: il file originale resta valido.
        """
        if not safe_write_json(self.save_path, self.data, indent=4):
            self.logger.error(f"Errore scrittura JSON progressi su disco: {self.save_path}")

    def get_progress(self, key_name: str, default: Any = None) -> Any:
        return self.data.get(key_name, default)

    def set_progress(self, key_name: str, value: Any) -> None:
        self.data[key_name] = value
        self.save()

    def unlock_level(self, level_id: str) -> None:
        """Sblocca ed aggiorna i livelli sul profilo attuale."""
        if level_id not in self.data["unlocked_levels"]:
            self.data["unlocked_levels"].append(level_id)
            # Inizializza unlocked_scenes per questo livello all'indice 0 (prima scena)
            if level_id not in self.data["unlocked_scenes"]:
                self.data["unlocked_scenes"][level_id] = 0
            self.save()

    def unlock_scene(self, level_id: str, scene_index: int) -> None:
        """Sblocca una specifica scena (indice) all'interno di un livello."""
        current_max = self.data["unlocked_scenes"].get(level_id, 0)
        if scene_index > current_max:
            self.data["unlocked_scenes"][level_id] = scene_index
            self.save()
            self.logger.info(f"Sbloccata scena {scene_index} per livello {level_id}")

    def is_scene_unlocked(self, level_id: str, scene_index: int) -> bool:
        """Verifica se una scena è sbloccata."""
        # Se il livello non è nei progressi ma è il primo in assoluto, sbloccalo al volo?
        # In realtà gestiamo tutto via unlock_level() iniziale.
        max_idx = self.data["unlocked_scenes"].get(level_id, 0)
        return scene_index <= max_idx

    def set_scene_score(self, level_id: str, scene_id: str, score: int, stars: int) -> None:
        """Salva lo score, tenendo sempre solo la performance record come da design casual."""
        if level_id not in self.data["scores"]:
            self.data["scores"][level_id] = {}
            self.data["stars"][level_id] = {}
            
        # Punteggio: check su record
        current_score = self.data["scores"][level_id].get(scene_id, 0)
        if score > current_score:
            self.data["scores"][level_id][scene_id] = score
            
        # Stelle: check su record
        current_stars = self.data["stars"][level_id].get(scene_id, 0)
        if stars > current_stars:
            self.data["stars"][level_id][scene_id] = stars
            
        self.save()

    def reset_progress(self) -> None:
        """Cancella tutti i progressi e riporta il gioco allo stato iniziale."""
        self.data = self._get_default_save()
        self.save()
        self.logger.info("Salvataggio resettato completamente.")
