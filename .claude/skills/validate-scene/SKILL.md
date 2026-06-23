---
name: validate-scene
description: Valida o crea una scene.json di HiddenIndexEngine (coordinate, catalog_id esistenti, icone presenti, oggetti goal, integrita' referenziale). Usala quando l'utente chiede di controllare/validare una scena, capire perche' un oggetto non appare in gioco, o creare/modificare una scena a mano.
---

# validate-scene

Validazione e creazione di scene per HiddenIndexEngine.

## Validare (modo preferito)

Usa il tool MCP `validate_scene` (server `hie`) con `game`, `level`, `scene`.
Ritorna: errori di schema, `catalog_id` assenti, icone mancanti, oggetti fuori
dai bounds del background, conteggio goal. Dopo una modifica, usa `render_scene`
per confermare visivamente il risultato.

In alternativa, validazione schema pura:
`engine/json_validator.py::validate(data, "scene")` contro
`engine/schemas/scene_schema.json`.

## Struttura di una scene.json

Path: `games/<game>/levels/<level>/<scene>/scene.json`. Vincoli chiave (schema):

- Richiesti a livello scena: `id`, `background`, `objects`.
- `background`: path relativo ALLA cartella della scena (di solito `background.png` accanto).
- Coordinate oggetti: spazio **pixel nativo del background**.
- Ogni oggetto richiede: `catalog_id`, `x`, `y`, `detection_type` (`circle`/`rect`/`mask`).
  - `rect`: `(x,y)` e' il **top-left**; servono `width` e `height`.
  - `circle`: `(x,y)` e' il **centro**; serve `radius`.
- `is_goal` (default true) marca un oggetto come obiettivo da trovare.

## Errori frequenti

- **`catalog_id` inesistente**: l'engine SCARTA l'oggetto (sarebbe un goal
  invisibile = scena non completabile). E' l'errore piu' grave: `validate_scene`
  lo segnala come error.
- **Icona mancante**: l'immagine non e' ne' in `games/<game>/<icon>` ne' in
  `engine/assets/<icon>`.
- **Oggetto fuori bounds**: coordinate oltre la dimensione del background.

## Integrita' del catalogo

Per problemi lato catalogo (id duplicati, schema): `python tools/audit_catalog.py`.
Per trovare PNG mancanti su tutto il catalogo: tool MCP `check_missing_assets`.
