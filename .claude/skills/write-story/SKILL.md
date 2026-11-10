---
name: write-story
description: Write and wire the story of a HiddenIndexEngine game - premise, chapters, per-scene story cards, one clue object per scene, the hidden collectible and its secret epilogue, the journal - in five languages, then put it in the scenes. Use when the user asks to give a game a story or "curare la storia", to add chapters or scenes to a story, to rewrite intros/outros, clues or the epilogue, or to translate story texts.
---

# write-story

Engine features: `docs/engine/STORY_AND_REPLAY.md` (story cards, clue objects,
collectibles, alternative spots, journal; desktop and web). Reference game:
`games/Malonno_Survivors/STORY.md` and its `strings/*.json`.

## 1. Design before writing (STORY.md in the game folder, English)

- **Why the player is there**, in one line, personal and concrete (a grandmother who
  stopped answering the phone), not "you are an investigator".
- **One guide voice** the player trusts (a radio voice, a letter writer), who speaks in the
  outros: it carries the plot without cut-scenes.
- **A mystery with a mechanism**: something broken that the scenes put back together piece
  by piece (fragments of a stone, gears of a lock). Each scene yields one piece or one fact.
- **Ground it in the real place** (local history, a real symbol, real roads and stations),
  checked, never invented facts presented as real.
- **A twist that recolours what came before**, prepared by small details (a radio that is
  on in a dead building), and an ending that resolves the personal reason.
- **Collectible + secret epilogue**: one small hidden object per scene (not a goal), all of
  them unlock a last journal page. It rewards replays.
- Chapters of 4-5 scenes (levels); a table scene -> place -> clue object -> what we learn.
- Clue objects come from the catalog and stay generic (catalog rule: no plot names on
  assets); the story lives in the clue text, not in the object.

## 2. Write (Italian source when the user is Italian)

Key convention (tools/apply_story.py relies on it):
`game_title`, `<level_id>_name`, `ch<n>_title`, `<scene>_name`, `<scene>_intro_<n>`,
`<scene>_outro_<n>`, `clue_<scene>`, `collectible_name`, `epilogue_title`, `epilogue_text`.

- Intro: 1-2 cards, 2-3 sentences each: where we are, what is wrong, one sensory detail.
- Outro: the guide voice, 1 card (2 for turning points), ends by pointing to the next place.
- Clue text: what the object says about the plot, 1-2 sentences, concrete.
- The player is "you", never gendered (Italian: avoid agreeing adjectives/participles).
- Short sentences, no AI tics (see the user's `umanizza`/`voce-nicola` skills for Italian).
- Typographic apostrophe `’` and the quotation marks of each language («» it/es/fr with
  NBSP in French, „“ de, "" en): an ASCII `'` after a vowel fails
  `tests/test_string_encoding.py` (it looks like a lost accent).

## 3. Translate

en, de, es, fr from the source, as a native novelist would, same keys and same paragraph
breaks; a subagent with the source file and these rules works well. Verify key sets and
`\n` counts match.

## 4. Wire

1. Merge the texts into `games/<id>/strings/<lang>.json` (safe_write_json).
2. Levels = chapters: `level_config.json` per chapter, `game_config.json` `levels` order,
   `"story": {"collectible_name_key", "epilogue_key", "epilogue_title_key"}`.
3. `python tools/apply_story.py <game_id> --drop-bubbles [--music=<level>:<file>]` writes
   each scene's `story` block (chapter heading on the first scene of a level), `name_key`,
   music. Do not run it while another process writes the same scene files.
4. Clue and collectible objects are placed by the place-objects skill (`clue` per scene and
   `collectible` in the placement plan); the clue object gets `clue_key = clue_<scene>`.
5. Check: `pytest tests/test_string_encoding.py tests/test_string_glyphs.py
   tests/test_story_layer.py tests/test_web_sync.py`, then play the first scene of each
   chapter (cards, clue card, journal from the pause menu) on desktop and in the web export.
