# Stability plan

Measured on 2026-09-04 (commit `0cb0e3b`). Numbers come from the repository, not from
impressions: they are reproducible with the commands in each section. Update them when the
work is done.

Priority order: **A → B → C → D → E**.

---

## A. The game runtime has no test net

Eight engine modules are not referenced by a single test:

`audio_manager`, `effect_renderer`, `effects_engine`, `hud_manager`, `results_screen`,
`taxonomy`, `transition_manager`, `utils`.

The nine minigames now boot, run and draw under test. What is left uncovered is the
drawing side of the runtime: the HUD, the results screen, the effects and the
transitions.

```bash
python - <<'PY'
from pathlib import Path
tests = " ".join(p.read_text(encoding="utf-8", errors="ignore") for p in Path("tests").glob("*.py"))
print([p.stem for p in Path("engine").glob("*.py") if p.stem not in tests and p.stem != "__init__"])
PY
```

**To do**

- ~~`save_manager`~~ done (`fb108bd`, 18 tests): round trip across a restart, missing file,
  corrupt file quarantined, a save from an older version, scores and stars keeping their
  own record, unlocking forward only, every change flushed. Found and fixed a crash on
  SCENE_COMPLETE when a save had a level in `scores` and not in `stars`.
- ~~`level_manager`~~ scoring done (`97d54e2`, 34 tests): time bonus, star cut,
  negative scores, miss penalty curve, reward tracker. Turned up that the timer never
  fails a scene, that `timer_behavior` is shipped and read by nobody, and that
  SCENE_FAILED is never emitted; all three are now stated in the module docstring.
  Still to cover there: `update()`, scene advancing and level progression.
- ~~`hint_system`~~ done (`5f11b71`, 27 tests): automatic glow, one object at a time, the
  fifteen second window, the manual hint with its cooldown, its per-object cost and its
  limit. The class docstring promised a cost the code does not charge; corrected.
- ~~`minigame_manager` + the nine minigames~~ done (`9ca7d17`, 67 tests): manifest, dynamic
  import, boot, five frames of update and draw, input, result reported back. All nine pass
  as they are.
- `results_screen`, `hud_manager`: build and draw once, headless.

---

## B. Lint is not enforced anywhere

`ruff check --select F` (real errors only, no style) reports **228** findings (measured
2026-09-07, up from 196 on 2026-09-04), 194 of them auto-fixable:

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
