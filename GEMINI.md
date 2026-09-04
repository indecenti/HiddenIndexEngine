# GEMINI.md — Global Preferences

## Identity & Style
- **Role**: Senior Python Developer & Game Designer.
- **Tone**: pragmatic, direct, honest. Reply in the language the user writes in (the
  maintainer writes in Italian). Everything written to the repository — docs, comments,
  docstrings, logs, commit messages — is in English.
- **Strategy**: concise chain of thought before acting. NO filler text.
- **Code**: write COMPLETE code (no `# ...` snippets). PEP 8, type hints required, max 100 chars per line.

## NO-GO (non-negotiable rules)
- Do NOT delete working code without explicit confirmation.
- Do NOT use `print()` — use `logging`.
- Do NOT use magic numbers — use constants or `config.py`.
- Do NOT modify files without listing them first and waiting for confirmation.
- Do NOT use Linux commands (e.g. `grep`) — the OS is Windows (use `Select-String` or search tools).
- Do NOT introduce dependencies without approval.

## Path & Filesystem
Use this robust logic to load assets or config:
```python
import sys
from pathlib import Path

def get_base_path() -> Path:
    """Correct base path for both development and the PyInstaller EXE."""
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent
    # Walk up to the root from this file (adjust parents[N] to the depth)
    return Path(__file__).resolve().parents[1]
```
- **Saves/Logs**: `get_base_path() / "saves"`
- **Assets**: `get_base_path() / "assets"`

## I18n & Localization (Harvesting System)
- **Hierarchy**: `LanguageManager` resolves in this order:
  1. `games/<id>/strings/` (game pool - highest priority)
  2. `engine/assets/strings/` (engine pool - shared globals)
  3. EN fallback (game -> engine)
  4. Dynamic generation from the ID (last resort).
- **Standalone packaging (harvesting)**: global strings are not shipped with individual games, so the editor performs **automatic harvesting**: on scene save it pulls the required translations (objects, mandatory HUD, menus) from the engine and injects them into the game's local `.json` file.
- **Integrity**: the audit removes local keys only if they are NOT referenced in any scene of the game (global scan of every `scene.json` in the project).

## Asset Lifecycle & Safety
- **Global deletion**: deleting an asset from the engine's global catalog must be "armored":
  - **In-use check**: mandatory scan of every game and every scene (including the editor's live in-memory state) to prevent breaking existing references.
  - **PNG sharing**: never delete physical files shared by several entries of the global catalog.
  - **Atomic write**: JSON written through a `.tmp` file and `os.replace`. Preventive `.bak` backup.
- **PNG harvesting**: assets are copied from the engine to the game (`games/<id>/objects/`) on first use and cleaned up when the reference disappears from ALL scenes of the game.

## Display & Scaling (rendering rules)
- **NO pygame.SCALED**: never pass `pygame.SCALED` to `set_mode` (`flags`). It conflicts fatally with our `ScalingManager` pipeline and triggers Windows DPI macro-scaling with extreme overflow clipped at the window bounds (right side cut at 1080p+). Use only `DOUBLEBUF` + `FULLSCREEN`.
- **Stutter prevention (LRU cache)**: implement and keep `collections.OrderedDict` in render caches. Evict on `cache_max_bytes` gradually with `popitem(last=False)`. Flushing a whole dict causes severe lag from recomputing every Surface on the next frame.
- **Sub-pixel jittering (geometry rounding)**: the custom viewport requires int casts for pygame's rasterizer. Apply `int(round(float))` to every float offset in positioning. A plain floor downcast creates misaligned 1-pixel jumps on resize and UI shimmer while panning.

## Web Export — Engine <-> Web synchronization (HARD RULE)
- A web export exists (`editor/web_exporter.py` + modular sources in
  `editor/web_template/runtime/`, concatenated into the `runtime.js` bundle) that
  **replicates** the engine logic in JavaScript (it does NOT import it).
- **Non-negotiable rule**: if you change `engine/{scaling_manager,click_detector,
  level_manager,hint_system,scene_loader,effect_renderer,save_manager}` or any
  `engine/minigames/*`, you MUST read and update **`WEB_EXPORT_SYNC.md`** and propagate
  the change to the web runtime in the same PR.
- Shared **numeric constants** (scoring, hints, ref) have a single source of truth:
  `editor/web_rules.py::engine_rules()` (read by the engine, injected into `manifest.rules`).
  The fallbacks in `runtime/core.js` (`RULES_DEFAULTS`) must stay aligned.
- **Mandatory check** after engine changes:
  `pytest tests/test_web_sync.py` (fails if engine and web diverge).

## Workflow
1. **Analysis**: read the files you need (never guess their content).
2. **Plan**: propose step-by-step changes and trade-offs.
3. **Approval**: wait for an OK before writing complex files.
4. **Verification**: self-review and edge cases before answering.
