# Story and replay layer

Four optional scene features that turn a sequence of hidden object scenes into a told
story that plays differently on every run. All of them are data in `scene.json` (and one
block in `game_config.json`); a scene without them plays exactly as before.
Both runtimes implement them: desktop (`engine/story.py`, `engine/scene_loader.py`,
`engine/core.py`, `engine/save_manager.py`) and web (`editor/web_template/runtime/game.js`,
`core.js`). Parity contract: `docs/web/WEB_EXPORT_SYNC.md`, section M.

## 1. Story cards (`story`)

```json
"story": {
  "chapter_key": "ch1_title",
  "intro": ["Brescia_Edolo_intro_1", "Brescia_Edolo_intro_2"],
  "outro": ["Cimitero_Montagna_outro_1"]
}
```

- A story card is a full screen narration page over the dimmed scene: optional chapter
  heading (only on the first intro page), the localized text typed in at
  `STORY_CHARS_PER_S`, a "Continue" button. A click while the text is still typing
  completes the text; the next click goes on.
- Order at scene start: intro cards, then the `start_scene` bubble tips.
  Order at the end (all goals found): `end_scene` bubble tips, then outro cards, then
  the results screen.
- While a card is open the game is paused: the timer does not run and clicks do not
  reach the scene.

## 2. Clue objects (`clue_key` on an object)

```json
{ "catalog_id": "walkie_talkies", "clue_key": "clue_Brescia_Edolo", ... }
```

- A clue object is always a goal: goal rotation (`auto_random_finds`) treats it as
  `always_show` and takes it first, so it stays a goal even when `num_random_finds` is
  smaller than the fixed set. `random_layer_selection` never drops a clue object or a
  collectible (the scene's clue must be findable on every run).
- When found, a clue card opens: the object's localized name as the title, the text of
  `clue_key` as the body, the object icon on the left. Same pause rules as a story card.
  If it was the last goal, the scene completes after the card is closed.
- The clue is recorded in the save (`clues[scene_id] = clue_key`) and shows in the
  journal.

## 3. Collectibles (`collectible: true` on an object)

- A collectible is never a goal and never in the object list. It is clickable; when found
  it gives `COLLECTIBLE_POINTS`, a popup with the collectible's name and is recorded in
  the save (`collectibles` = set of scene ids). One collectible per scene counts.
- Once found in a scene it is still placed on replays (so the scene looks the same) but a
  second find gives no points.
- `game_config.json` names it and the epilogue it unlocks:

```json
"story": {
  "collectible_name_key": "collectible_name",
  "epilogue_key": "epilogue_text",
  "epilogue_title_key": "epilogue_title"
}
```

## 4. Alternative spots (`alt_spots` on an object)

```json
"alt_spots": [ {"x": 812, "y": 1440, "rotation": 12.0},
               {"x": 2210, "y": 905, "flip_x": true, "layer": "objects_low"} ]
```

- On every scene start each object takes its base placement or one of its alternative
  spots, uniformly at random. A spot may override `x`, `y`, `rotation`, `scale`,
  `flip_x`, `flip_y`, `alpha`, `color_filter`, `layer`; anything else comes from the base.
- Resolution happens before `random_layer_selection` and goal rotation, so the
  same object can be a goal in a different place on the next run.
- Spots come from `tools/place_on_surfaces.py` (objects resting on hand-marked surfaces,
  lit by the spot) or from the camouflage auto-scatter (`tools/populate_scene.py`).

## Contact shadow (`shadow` on an object or an alt spot)

```json
"shadow": {"dy": 46.0, "w": 120.0, "a": 150}
```

An object resting on the ground needs a contact shadow or it looks like it floats.
`dy` is the distance, in the object's reference px (the space of `width`/`height`, times
`scale`), from the centre of the object rectangle down to the resting point; `w` is the
width of the shadow (times `scale`), its height is `w * SHADOW_ASPECT`; `a` is the opacity
at the centre. The shadow is a soft unrotated ellipse (alpha `a * (1 - d) ** SHADOW_FALLOFF`
at normalized distance `d`, further multiplied by the object's own `alpha`), drawn just
before the object in the same bg->screen space, and not drawn once the object is found or
when it is hidden (no icon). An alt spot may carry its own `shadow` (it is one of the
`ALT_SPOT_FIELDS`). Desktop: `engine/object_shadow.py`; web: `core.js::drawObjectShadow`.

## 5. Journal

Opened from the pause menu (desktop: also the `J` key in a scene). The pause entry
(`open_journal`, label `pause_journal`) is shown only when some scene of the game has a
clue or a collectible; it is added before "quit to menu" even when a theme declares its
own pause view. Lists, in campaign
order, every completed scene that has a clue: scene name, clue object name, clue text.
Scenes not reached yet show as locked lines. Footer: collectibles found / total; when all
are found the epilogue (title + text) is shown at the end.

## Save fields

`clues` (object, scene_id -> clue_key) and `collectibles` (list of scene ids), next to the
existing campaign fields. Missing in old saves = empty.

## Constants (single source: `editor/web_rules.py::engine_rules()`)

| Name | Value | Meaning |
|---|---|---|
| `STORY_CHARS_PER_S` | 40 | typing speed of story and clue cards |
| `COLLECTIBLE_POINTS` | 250 | points for the first find of a collectible in a scene |
| `SHADOW_ASPECT` | 0.22 | height / width of the contact shadow (`engine/object_shadow.py`) |
| `SHADOW_FALLOFF` | 1.6 | exponent of the contact shadow's radial fade |
