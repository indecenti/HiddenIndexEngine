---
name: run-game
description: Starts the HiddenIndexEngine game or editor and visually verifies a scene, the menu or a minigame. Use it when the user asks to launch/try the game, see a rendered scene, test a minigame or the editor, or capture a screenshot to confirm a change.
---

# run-game

Visual verification and startup of HiddenIndexEngine.

## Deciding HOW to verify

- **A HOG scene only** (object layout, background, positions): NO need to start the
  game. Use the MCP tool `render_scene` (server `hie`), much faster and headless.
  For a single asset use `render_asset`.
- **Menus, transitions, minigames, editor, real input**: start the app.

## Starting the app

```powershell
# Game (uses default_game from config.ini)
python main.py
python main.py --game Malonno_Survivors --lang it

# Direct minigame
python main.py --minigame sudoku

# Level editor
python run_editor.py
python run_editor.py --game Malonno_Survivors
```

Available games: see `list_games` (MCP) or the folders in `games/` with a
`game_config.json`. Minigames: folders in `engine/minigames/`.

## Verification and screenshots

The app is a desktop pygame window. To capture a screenshot for verification use
the desktop tools (computer-use) if available, otherwise ask the user. For scenes
always prefer the MCP headless render: it is deterministic and needs no interaction.

## Notes

- No `pygame.SCALED` (conflicts with `ScalingManager`). See `CLAUDE.md`.
- Logs go to `saves/engine.log`.
- If startup fails at boot, check `saves/engine.log` and `saves/crash_native.log`.
