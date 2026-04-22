"""
engine/catalog_manager.py

Sistema di gestione del catalogo oggetti con indici in-memory ad alta performance.

Architettura two-tier (invariata):
  1. Catalogo globale : engine/data/global_objects_catalog.json  (~200 oggetti condivisi)
  2. Catalogo gioco  : games/{game_id}/objects_catalog.json     (opzionale, sovrascrive globale)

Ottimizzazioni rispetto alla versione dict-plain:
  - Lookup by ID   : O(1)  (era O(n))
  - Lookup by tag  : O(1)  (era O(n))
  - Interfaccia pubblica : 100% compatibile con il codice esistente
  - Packaging      : zero modifiche al build_system.py (solo JSON)
"""

import json
import logging
from pathlib import Path
from typing import Optional

from engine.utils import get_resource_path

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# CatalogDB — wrapper ad alta performance con indici O(1)
# ---------------------------------------------------------------------------

class CatalogDB:
    """
    Wrapper per il catalogo oggetti con indici in-memory.

    Costruisce due indici dalla lista raw al momento del caricamento:
      _id_index  : dict[str, dict]        — lookup O(1) per ID
      _tag_index : dict[str, list[dict]]  — lookup O(1) per tag

    Compatibilità backward: implementa .get("objects", []) per il codice
    esistente che tratta il catalogo come un plain dict {"objects": [...]}.
    """

    def __init__(self, raw_catalog: dict) -> None:
        objects_list: list[dict] = raw_catalog.get("objects", [])

        # Indice primario: id → oggetto
        self._id_index: dict[str, dict] = {
            obj["id"]: obj for obj in objects_list if "id" in obj
        }

        # Indice secondario: tag → lista oggetti
        self._tag_index: dict[str, list[dict]] = {}
        for obj in objects_list:
            for tag in obj.get("tags", []):
                self._tag_index.setdefault(tag, []).append(obj)

        logger.debug(
            "CatalogDB: %d oggetti indicizzati, %d tag unici",
            len(self._id_index),
            len(self._tag_index),
        )

    # ── Interfaccia backward-compatible con dict {"objects": [...]} ──────────

    def get(self, key: str, default=None):
        """
        Compatibilità con catalog.get("objects", []).
        Usato da SceneLoader e editor/core/io.py.
        """
        if key == "objects":
            return list(self._id_index.values())
        return default

    def __contains__(self, obj_id: str) -> bool:
        return obj_id in self._id_index

    def __len__(self) -> int:
        return len(self._id_index)

    # ── API ad alta performance (uso diretto) ────────────────────────────────

    def get_by_id(self, obj_id: str) -> Optional[dict]:
        """Lookup O(1) by ID. Ritorna None se non trovato."""
        return self._id_index.get(obj_id)

    def search_by_tag(self, tag: str) -> list[dict]:
        """Lookup O(1) by tag. Ritorna lista vuota se nessun match."""
        return self._tag_index.get(tag, [])

    def all_tags(self) -> set[str]:
        """Ritorna l'insieme di tutti i tag presenti nel catalogo."""
        return set(self._tag_index.keys())

    def all_ids(self) -> list[str]:
        """Ritorna tutti gli ID degli oggetti catalogati."""
        return list(self._id_index.keys())


# ---------------------------------------------------------------------------
# API pubblica (firme identiche alla versione precedente)
# ---------------------------------------------------------------------------

def load_catalog(game_id: str) -> CatalogDB:
    """
    Carica e unisce il catalogo globale + quello specifico del gioco.
    In modalità build standalone, il catalogo globale può mancare.

    Args:
        game_id: Identificatore del gioco (es. 'villa_segreta')

    Returns:
        CatalogDB: indice in-memory consultabile in O(1)

    Raises:
        FileNotFoundError: se non viene trovato né il catalogo globale né quello del gioco.
    """
    global_catalog = {"objects": []}

    # Tentiamo il caricamento del globale (può mancare in build standalone/per scelta utente)
    try:
        global_catalog = _load_global_catalog()
    except (FileNotFoundError, json.JSONDecodeError) as e:
        # Se siamo in EXE/Build, è tollerato se esiste il catalogo del gioco.
        logger.warning("Catalogo globale ignorato o mancante: %s", e)

    game_catalog = _load_game_catalog(game_id)

    # Se mancano entrambi, allora è un errore fatale
    if not global_catalog["objects"] and not game_catalog:
        raise FileNotFoundError(
            f"Nessun catalogo valido trovato per '{game_id}' (globale assente e locale mancante)."
        )

    if game_catalog:
        merged = _merge_catalogs(global_catalog, game_catalog)
        return CatalogDB(merged)

    return CatalogDB(global_catalog)


def get_object_by_id(catalog: CatalogDB, obj_id: str) -> Optional[dict]:
    """
    Recupera un oggetto dal catalogo per ID.

    Firma identica alla versione precedente; ora O(1) invece di O(n).

    Args:
        catalog: CatalogDB oppure dict legacy {"objects": [...]}
        obj_id:  ID dell'oggetto da cercare

    Returns:
        dict con i dati dell'oggetto, oppure None se non trovato
    """
    # Supporto duck-typing: funziona sia con CatalogDB che con dict legacy
    if isinstance(catalog, CatalogDB):
        return catalog.get_by_id(obj_id)

    # Fallback per dict plain (compatibilità con codice di test)
    for obj in catalog.get("objects", []):
        if obj.get("id") == obj_id:
            return obj
    return None


def search_by_tags(catalog: CatalogDB, tag: str) -> list[dict]:
    """
    Restituisce tutti gli oggetti che hanno un determinato tag.

    Firma identica alla versione precedente; ora O(1) invece di O(n).

    Args:
        catalog: CatalogDB oppure dict legacy {"objects": [...]}
        tag:     Tag da cercare

    Returns:
        Lista di dict degli oggetti corrispondenti (può essere vuota)
    """
    if isinstance(catalog, CatalogDB):
        return catalog.search_by_tag(tag)

    # Fallback per dict plain (compatibilità con codice di test)
    return [
        obj for obj in catalog.get("objects", [])
        if tag in obj.get("tags", [])
    ]


# ---------------------------------------------------------------------------
# Funzioni interne di caricamento
# ---------------------------------------------------------------------------

def _load_global_catalog() -> dict:
    """Carica il catalogo globale da engine/data/."""
    path = get_resource_path("engine", "data", "global_objects_catalog.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            catalog = json.load(f)
        if not isinstance(catalog, dict) or "objects" not in catalog:
            raise ValueError("Il catalogo globale deve avere la chiave 'objects'")
        logger.debug("Catalogo globale caricato: %d oggetti", len(catalog["objects"]))
        return catalog
    except FileNotFoundError:
        raise FileNotFoundError(f"Catalogo globale non trovato: {path}")
    except json.JSONDecodeError as e:
        raise json.JSONDecodeError(
            f"JSON non valido nel catalogo globale: {e.msg}", e.doc, e.pos
        )


def _load_game_catalog(game_id: str) -> Optional[dict]:
    """
    Carica il catalogo specifico del gioco se esiste.
    Ritorna None se assente o malformato (fail silenzioso).
    """
    path = get_resource_path("games", game_id, "objects_catalog.json")
    if not Path(path).exists():
        return None

    try:
        with open(path, "r", encoding="utf-8") as f:
            catalog = json.load(f)
        if not isinstance(catalog, dict) or "objects" not in catalog:
            logger.warning("Catalogo gioco '%s' malformato — ignorato", game_id)
            return None
        logger.debug(
            "Catalogo gioco '%s' caricato: %d oggetti", game_id, len(catalog["objects"])
        )
        return catalog
    except (json.JSONDecodeError, IOError) as e:
        logger.warning("Errore caricamento catalogo gioco '%s': %s — ignorato", game_id, e)
        return None


def _merge_catalogs(global_catalog: dict, game_catalog: dict) -> dict:
    """
    Unisce il catalogo del gioco in quello globale.

    Strategia: gli oggetti del gioco sovrascrivono quelli globali con stesso ID.

    Args:
        global_catalog: {"objects": [...]} dal catalogo globale
        game_catalog:   {"objects": [...]} dal catalogo specifico del gioco

    Returns:
        {"objects": [...]} unificato
    """
    global_objects: dict[str, dict] = {
        obj["id"]: obj for obj in global_catalog.get("objects", [])
    }
    game_objects: dict[str, dict] = {
        obj["id"]: obj for obj in game_catalog.get("objects", [])
    }

    merged: dict[str, dict] = {**global_objects, **game_objects}
    logger.debug(
        "Catalogo unito: %d globali + %d gioco = %d totali",
        len(global_objects),
        len(game_objects),
        len(merged),
    )
    return {"objects": list(merged.values())}
