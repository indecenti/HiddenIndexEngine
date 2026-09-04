# Stability plan

Measured on 2026-09-04 (commit `0cb0e3b`). Numbers come from the repository, not from
impressions: they are reproducible with the commands in each section. Update them when the
work is done.

Priority order: **A → B → C → D → E**.

---

## A. The game runtime has no test net

Eleven engine modules are not referenced by a single test:

`audio_manager`, `effect_renderer`, `effects_engine`, `hint_system`, `hud_manager`,
`minigame_manager`, `results_screen`, `save_manager`, `taxonomy`, `transition_manager`,
`utils`.

Eight of the nine minigames are equally untouched (only `sudoku` appears in the suite),
while the editor's auto-scatter alone has 12 test files. The safety net is stretched over
the tool, not over what the player runs — and `save_manager` holds the player's progress.

```bash
python - <<'PY'
from pathlib import Path
tests = " ".join(p.read_text(encoding="utf-8", errors="ignore") for p in Path("tests").glob("*.py"))
print([p.stem for p in Path("engine").glob("*.py") if p.stem not in tests and p.stem != "__init__"])
PY
```

**To do**

- `save_manager`: save/load round trip, corrupt file, missing file, version migration,
  concurrent write. A save bug costs the player their progress and is invisible until it
  happens.
- `level_manager`: score, miss penalty curve, stars, unlock and progression.
- `hint_system`: cooldown, penalties, exhaustion.
- `minigame_manager` + the nine minigames: a headless boot and a few frames each, which is
  enough to catch an import or asset error that today only shows up in a shipped build.
- `results_screen`, `hud_manager`: build and draw once, headless.

---

## B. Lint is not enforced anywhere

`ruff check --select F` (real errors only, no style) reports **196** findings, 163 of them
auto-fixable:

| Code | Count | What it means |
|---|---|---|
| F401 | 134 | unused imports |
| F841 | 35 | unused variables |
| F541 | 18 | f-strings with no placeholder |
| F811 | 6 | name redefined (a local re-import shadows the module-level one) |
| F601 | 2 | **repeated dict key**: the first value is silently lost |
| F821 | 1 | **undefined name** |

The two that matter:

- `engine/core.py:355` — `Optional` is used in an annotation but never imported. Verified:
  it does **not** crash, because Python does not evaluate annotations on attribute targets
  inside a function body. It still breaks `typing.get_type_hints` and would become a real
  error the moment the line moves to class or module scope.
- `tools/tag_fix_pass2.py:38` and `:153` — `precision_caliper` and `desiderius_cross`
  appear twice in the same dict literal, so one of the two tag assignments is dropped.

**To do**: fix those two, run the auto-fixes, add `ruff` to `requirements-dev.txt` and a
blocking `ruff check --select F` step to the CI. New dependency: needs the maintainer's
approval (CLAUDE.md).

---

## C. 79 exceptions swallowed in silence

```bash
grep -rn -A1 "except Exception" editor/ --include=*.py | grep -c "pass$"   # 60
grep -rn -A1 "except Exception" engine/ --include=*.py | grep -c "pass$"   # 19
grep -rn "except:" editor/ engine/ --include=*.py                          # 7 bare
```

The remaining bare `except:` are in `engine/core.py:1577`, `engine/effects_engine.py:53`,
`engine/utils.py:647` and four minigames (`arcade_eleven`, `asteroids`, `centipede`,
`tower`). Each one swallows real bugs together with the expected failure.

**To do**: triage, starting with the paths that touch data (`io_ops`, `save_manager`,
catalog writes). Typed exceptions plus a log line; keep the silent catch only where the
failure genuinely does not matter, and say so in a comment.

---

## D. Publishing checklist (plan item P8)

A pre-build wizard chaining the auditor, missing assets, translation completeness, scene
difficulty statistics and an estimated package size, ending with a "ready to build"
verdict and the list of blockers. Now that the games carry commercial value, shipping a
broken build costs more than it used to.

---

## E. Android phases 2 and 4

Sharpness at 720p and system integration (back button, lifecycle). They are the first
things a mobile player notices. Details in
[android/ANDROID_MOBILE_UX_AUDIT.md](android/ANDROID_MOBILE_UX_AUDIT.md).

---

## Also worth doing

- **CI is permissive**: the catalog audit runs with `continue-on-error`, there is no lint
  step and no coverage report. Make the audit blocking once it is clean.
- **Coverage has no tooling**: `coverage`/`pytest-cov` are not installed, so the numbers
  above are a static module-to-test mapping, not a measurement. Adding `pytest-cov` to the
  dev requirements would turn section A into something measurable.
