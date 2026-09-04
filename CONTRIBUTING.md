# Contributing to HiddenIndexEngine

Thanks for your interest. This document collects the minimum rules for opening an
issue or a pull request.

## Language

Everything committed to the repository is in **English**: documentation, code comments,
docstrings, log messages and commit messages. Part of the codebase still carries comments
in Italian from before the project went public; when you touch such a file, translate the
comments you edit. Issues and pull requests are best in English; Italian is fine too.
Player-facing strings always go through the i18n system, never hardcoded.

## Setup

You need **Python 3.12** on Windows 10/11 (the tested platform).

```bash
git clone https://github.com/indecenti/HiddenIndexEngine.git
cd HiddenIndexEngine
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt -r requirements-dev.txt
```

Check that everything runs:

```bash
pytest
python main.py
python run_editor.py
```

## Code rules

They are binding; the CI and the review enforce them.

- **Type hints required** on every public signature. PEP 8, lines of ~100 characters.
- **Never `print()`** — use `logging` through `engine.utils.get_logger(__name__)`.
- **Never magic numbers** — module constants or configuration values.
- **Never emoji** in code, documentation, UI or output.
- **Resource paths**: always `engine.utils.get_resource_path(...)`. For writes,
  `engine.utils.get_writable_path(...)`. Never absolute paths or `os.getcwd()`.
- **JSON writes**: always `engine.utils.safe_write_json` (atomic).
  Deletions: `engine.utils.safe_delete` (`.editor_trash/` bin + audit log).
- **Rendering**: never `pygame.SCALED` on `set_mode` (it conflicts with
  `ScalingManager`); use `DOUBLEBUF` / `FULLSCREEN`. LRU render caches with gradual
  eviction via `popitem(last=False)`. Positioning with `int(round(float))`.
- **No new dependencies** without discussing them first in an issue. Versions in
  `requirements*.txt` are pinned on purpose.

## Binding rule: engine <-> web sync

The web export (`editor/web_exporter.py` + `editor/web_template/runtime/`) **replicates**
in JavaScript the logic of `engine/scaling_manager.py`, `click_detector.py`,
`level_manager.py`, `hint_system.py`, `scene_loader.py`, `effect_renderer.py`,
`save_manager.py` and `engine/minigames/*`.

If you touch any of these files you **must**, in the same PR:

1. read and update `docs/web/WEB_EXPORT_SYNC.md`;
2. propagate the change to the JavaScript runtime;
3. make `pytest tests/test_web_sync.py` pass.

Shared constants have a single source of truth in `editor/web_rules.py::engine_rules()`.
A PR that desynchronizes Python and JavaScript is not accepted.

## Data model

- A scene is `games/<id>/levels/<level>/<scene>/scene.json`, validated against
  `engine/schemas/scene_schema.json`.
- Object coordinates live in the **native pixel space of the background**.
- Anchor convention: for `rect` the `(x, y)` pair is the **top-left**;
  for `circle` and `mask` it is the **center**.
- The `catalog_id` resolves against the merged global + local catalog, with the local
  entry winning on equal `id`.

Before opening a PR that touches scenes: `python tools/audit_catalog.py`.

## Pull requests

1. Fork and work on a dedicated branch (`feat/...`, `fix/...`, `docs/...`).
2. One topic per PR. Large mixed PRs are sent back.
3. `pytest` must pass locally before opening the PR.
4. Commit messages in Conventional Commits format:
   `feat(editor): ...`, `fix(engine): ...`, `docs: ...`, `test: ...`, `refactor: ...`.
5. Describe **what** changes and **why**. For a fix, say how to reproduce the bug.
6. If on-screen behavior changes, attach a screenshot or a GIF.

## Reporting bugs

Open an issue with the Bug report template. Always include:

- Python version and operating system;
- the exact command you ran;
- the full traceback (not a screenshot of it);
- for scene issues: the `scene.json` or the output of `tools/audit_catalog.py`.

## Assets

The graphic and audio assets in the repository are CC BY-NC 4.0 (see
[LICENSE-ASSETS.md](LICENSE-ASSETS.md)), and assets you contribute are covered by the same
grant as the code (below). **Do not open PRs that add third-party assets** whose license
you cannot prove: they will be rejected.

## License of contributions

You keep the copyright on what you write. By opening a pull request you grant the author
of the project (Indecenti) a perpetual, worldwide, irrevocable right to use your
contribution and to license it to others, both under the project license
(**[PolyForm Noncommercial 1.0.0](LICENSE)**) and under the commercial licenses described
in [LICENSING.md](LICENSING.md), including under different terms in future releases.

That grant is what makes the model work: the project is free for noncommercial use and
commercial use is paid, and it can only be sold as a whole if every line in it can be
licensed commercially. You also confirm that the contribution is your own work, or that you
have the right to submit it under these terms.
