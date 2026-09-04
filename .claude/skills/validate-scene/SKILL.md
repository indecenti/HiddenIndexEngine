---
name: validate-scene
description: Validates or creates a HiddenIndexEngine scene.json (coordinates, existing catalog_ids, present icons, goal objects, referential integrity). Use it when the user asks to check/validate a scene, understand why an object does not appear in the game, or create/edit a scene by hand.
---

# validate-scene

Scene validation and creation for HiddenIndexEngine.

## Validating (preferred way)

Use the MCP tool `validate_scene` (server `hie`) with `game`, `level`, `scene`.
It returns: schema errors, missing `catalog_id`s, missing icons, objects outside
the background bounds, goal count. After a change, use `render_scene` to confirm
the result visually.

Alternatively, pure schema validation:
`engine/json_validator.py::validate(data, "scene")` against
`engine/schemas/scene_schema.json`.

## Structure of a scene.json

Path: `games/<game>/levels/<level>/<scene>/scene.json`. Key constraints (schema):

- Required at scene level: `id`, `background`, `objects`.
- `background`: path relative TO the scene folder (usually `background.png` next to it).
- Object coordinates: **native pixel space of the background**.
- Every object requires: `catalog_id`, `x`, `y`, `detection_type` (`circle`/`rect`/`mask`).
  - `rect`: `(x,y)` is the **top-left**; `width` and `height` are required.
  - `circle`: `(x,y)` is the **center**; `radius` is required.
- `is_goal` (default true) marks an object as a target to find.

## Frequent errors

- **Non-existent `catalog_id`**: the engine DROPS the object (it would be an invisible
  goal = scene impossible to complete). It is the most serious error: `validate_scene`
  reports it as an error.
- **Missing icon**: the image is neither in `games/<game>/<icon>` nor in
  `engine/assets/<icon>`.
- **Object out of bounds**: coordinates beyond the background size.

## Catalog integrity

For catalog-side problems (duplicate ids, schema): `python tools/audit_catalog.py`.
To find missing PNGs across the whole catalog: MCP tool `check_missing_assets`.
