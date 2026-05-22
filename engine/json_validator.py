"""
engine/json_validator.py

Validazione dei file JSON di gioco contro gli schemi ufficiali.
Produce messaggi di errore leggibili — mai crash criptici.

Dipende opzionalmente da 'jsonschema'. Se non installato,
la validazione viene saltata con un avviso (non blocca il gioco).
"""

import json
import os
from engine.utils import get_resource_path, get_logger

log = get_logger(__name__)

try:
    import jsonschema
    _VALIDATION_AVAILABLE = True
except ImportError:
    _VALIDATION_AVAILABLE = False
    log.warning(
        "jsonschema non installato — validazione JSON disabilitata. "
        "Installa con: pip install jsonschema"
    )

# Mappa nome_schema -> schema caricato (lazy)
_schema_cache: dict[str, dict] = {}

_SCHEMA_FILES = {
    "scene":        "engine/schemas/scene_schema.json",
    "level_config": "engine/schemas/level_config_schema.json",
    "game_config":  "engine/schemas/game_config_schema.json",
    "catalog":      "engine/schemas/catalog_schema.json",
    "taxonomy":     "engine/schemas/taxonomy_schema.json",
}


def _load_schema(name: str) -> dict | None:
    if name in _schema_cache:
        return _schema_cache[name]
    path = get_resource_path(*_SCHEMA_FILES[name].split("/"))
    if not os.path.exists(path):
        log.warning("Schema non trovato: %s", path)
        return None
    with open(path, encoding="utf-8") as f:
        schema = json.load(f)
    _schema_cache[name] = schema
    return schema


def validate(data: dict, schema_name: str, source_path: str = "") -> list[str]:
    """
    Valida `data` contro lo schema `schema_name`.

    Restituisce una lista di stringhe di errore (vuota = valido).
    Non solleva eccezioni — gestisce tutto internamente.

    Args:
        data:        dizionario già parsato dal JSON
        schema_name: "scene", "level_config" o "game_config"
        source_path: path del file originale (solo per i messaggi di errore)
    """
    if not _VALIDATION_AVAILABLE:
        return []

    schema = _load_schema(schema_name)
    if schema is None:
        return []

    validator = jsonschema.Draft7Validator(schema)
    errors = sorted(validator.iter_errors(data), key=lambda e: list(e.path))

    messages: list[str] = []
    for err in errors:
        field_path = " -> ".join(str(p) for p in err.absolute_path) or "(radice)"
        messages.append(f"  [{field_path}] {err.message}")

    if messages:
        header = f"[ERRORE JSON] {source_path or schema_name}"
        log.error("%s\n%s", header, "\n".join(messages))

    return messages


def load_and_validate(file_path: str, schema_name: str) -> dict:
    """
    Carica un file JSON, lo valida e lo restituisce come dizionario.

    Solleva ValueError con messaggio leggibile se:
    - il file non esiste
    - il JSON non è parsabile
    - la validazione fallisce
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File non trovato: {file_path}")

    with open(file_path, encoding="utf-8") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"JSON malformato in {file_path}:\n  {exc}"
            ) from exc

    errors = validate(data, schema_name, source_path=file_path)
    if errors:
        raise ValueError(
            f"Validazione fallita per {file_path}:\n" + "\n".join(errors)
        )

    return data
