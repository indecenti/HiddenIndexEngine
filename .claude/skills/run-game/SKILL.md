---
name: run-game
description: Avvia il gioco o l'editor di HiddenIndexEngine e verifica visivamente una scena, il menu o un minigioco. Usala quando l'utente chiede di lanciare/provare il gioco, vedere una scena renderizzata, testare un minigioco o l'editor, o catturare uno screenshot per confermare una modifica.
---

# run-game

Verifica visiva e avvio di HiddenIndexEngine.

## Decidere COME verificare

- **Solo una scena HOG** (layout oggetti, sfondo, posizioni): NON serve avviare il
  gioco. Usa il tool MCP `render_scene` (server `hie`), molto piu' veloce e headless.
  Per un singolo asset usa `render_asset`.
- **Menu, transizioni, minigiochi, editor, input reale**: avvia l'app.

## Avvio dell'app

```powershell
# Gioco (usa default_game da config.ini)
python main.py
python main.py --game Malonno_Survivors --lang it

# Minigioco diretto
python main.py --minigame sudoku

# Editor di livelli
python run_editor.py
python run_editor.py --game Malonno_Survivors
```

Giochi disponibili: vedi `list_games` (MCP) o le cartelle in `games/` con
`game_config.json`. Minigiochi: cartelle in `engine/minigames/`.

## Verifica e screenshot

L'app e' una finestra pygame desktop. Per catturare uno screenshot a fini di
verifica usa gli strumenti desktop (computer-use) se disponibili, altrimenti
chiedi all'utente. Per le scene preferisci sempre il render headless dell'MCP:
e' deterministico e non richiede interazione.

## Note

- Niente `pygame.SCALED` (conflitto con `ScalingManager`). Vedi `CLAUDE.md`.
- I log girano in `saves/engine.log`.
- Se l'avvio fallisce al boot, controlla `saves/engine.log` e `saves/crash_native.log`.
