# Minigame Development Guide (HiddenIndexEngine)

This guide describes the standard for creating, integrating and localizing new minigames in the engine. By following these steps, every minigame automatically inherits pause handling, scaling and the visual consistency of the main system.

## 1. File system layout
Every minigame lives in a dedicated subfolder inside `engine/minigames/`.

```text
engine/minigames/<minigame_id>/
├── strings/            # JSON files for the 5 languages (it, en, fr, es, de)
├── manifest.json       # Configuration for dynamic loading
└── <minigame_id>_game.py  # Main game class
```

## 2. The manifest (`manifest.json`)
The manifest lets the `MinigameManager` locate the right class without importing it manually in the engine code.
```json
{
  "id": "game_name",
  "name": "Displayed Title",
  "main_class": "MyNewGame",
  "version": "1.0.0"
}
```

## 3. Localization (mandatory)
Every minigame **MUST** support the 5 official languages to avoid warnings or empty text.
- Path: `engine/minigames/<id>/strings/*.json`
- Loading: must happen in the `__init__` constructor.

> [!IMPORTANT]
> To display correctly in the editor's **Minigame Selector**, every language `.json` file must contain these two keys:
> - `mg_title`: the localized minigame name (e.g. "PONG CHALLENGE").
> - `mg_description`: a short description (max 2 lines) of the game mechanics.
>
> The editor uses these keys to populate the selection interface and let the user understand what they are attaching to the object.

```python
from engine.utils import get_resource_path

def __init__(self, **kwargs):
    super().__init__(**kwargs)
    # Load the local translations (it, en, fr, es, de)
    strings_path = get_resource_path("engine", "minigames", "my_id", "strings")
    self.load_local_strings(strings_path)
```

## 4. Game logic (inheritance)
The class must inherit from `BaseMinigame` and implement the standard Pygame methods.

```python
from engine.minigames.minigame_base import BaseMinigame

class MyNewGame(BaseMinigame):
    def start(self) -> None:
        """Called once when the game is activated."""
        pass

    def handle_event(self, event: pygame.event.Event) -> None:
        """Input handling. NOTE: ESC automatically triggers the global pause through the MinigameManager."""
        pass

    def update(self, dt: float) -> None:
        """Per-frame logic (movement, collisions)."""
        pass

    def draw(self) -> None:
        """Render the current state."""
        self.screen.fill((20, 20, 20))
```

## 5. Results and score
To close the minigame and return to the main scene, call `self.finish(results)`.
- `success`: if `True`, it counts as a completed objective.
- `score`: bonus points added to the main run's score.

```python
results = {
    "success": True,
    "score": 1000      # bonus for winning
}
self.finish(results)
```

## 6. Synchronization with the engine
The minigame must be ready to react to global state changes:
- **Pause**: the top-left button is handled by the engine. Do not draw it.
- **Resize**: implement `on_resize(self)` if you want to recompute the layout when the user changes resolution while paused.
- **Scaling**: use `self.scaling_manager.scale` to keep proportions (fonts, speeds, sizes).

## 7. Registration
No manual registration required. Once the folder with the manifest exists, the minigame can be triggered from any scene object through the editor simply by entering its `id`.
