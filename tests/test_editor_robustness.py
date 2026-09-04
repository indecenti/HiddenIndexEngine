"""
tests/test_editor_robustness.py

Ondata 4 (P1): crash recovery dell'autosave (prima scritto e MAI riletto),
backup rotativi di scene.json, LRU della cache immagini dell'editor.
Host fake sul solo IoOpsMixin: niente editor completo.
"""

from __future__ import annotations

import json
import os
import time
from collections import OrderedDict
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pytest

pygame = pytest.importorskip("pygame")

from editor.constants import (AUTOSAVE_RETRY_SECS, AUTOSAVE_SECS, IMG_CACHE_MAX,
                              MAIN_LOOP_MAX_CRASHES, SCENE_BACKUPS_KEEP)
from editor.mixins.io_ops import IoOpsMixin


@pytest.fixture(scope="module", autouse=True)
def _pygame_init():
    pygame.init()
    pygame.display.set_mode((64, 64))
    yield
    pygame.quit()


class FakeIO(IoOpsMixin):
    """Host minimo per le funzioni di robustezza di IoOpsMixin."""

    def __init__(self, tmp_path: Path):
        self.base_path = tmp_path
        self.game_path = tmp_path / "games" / "g1"
        self.scene_path = self.game_path / "levels" / "L1" / "S1"
        self.scene_path.mkdir(parents=True, exist_ok=True)
        self.scene_data = {"objects": []}
        self.scene_dirty = False
        self.selected_idx = None
        self._img_cache = OrderedDict()
        self.statuses: list[str] = []
        self.undo_labels: list[str] = []

    def _status(self, msg, color=None, secs=0):
        self.statuses.append(str(msg))

    def _TR(self, key, default=None):
        """Stub i18n: restituisce il default inglese passato dal codice."""
        return default if default is not None else key

    def _push_undo(self, label="", coalesce_key=None):
        self.undo_labels.append(label)

    def _sanitize_effects(self):
        pass


def _write_scene(ed: FakeIO, objects: list, mtime: float) -> Path:
    p = ed.scene_path / "scene.json"
    p.write_text(json.dumps({"objects": objects}), encoding="utf-8")
    os.utime(p, (mtime, mtime))
    return p


def _write_autosave(ed: FakeIO, objects: list, mtime: float) -> Path:
    p = ed.scene_path / "scene.json.autosave"
    p.write_text(json.dumps({"objects": objects}), encoding="utf-8")
    os.utime(p, (mtime, mtime))
    return p


def test_recovery_proposto_se_autosave_piu_recente(tmp_path):
    ed = FakeIO(tmp_path)
    now = time.time()
    _write_scene(ed, [], now - 600)
    _write_autosave(ed, [{"catalog_id": "x", "x": 1, "y": 2}], now - 10)
    ed.scene_data = {"objects": []}

    ed._check_autosave_recovery()
    assert ed._recovery_modal
    n_auto, n_cur, _ts = ed._recovery_info
    assert (n_auto, n_cur) == (1, 0)

    ed._recovery_accept()
    assert not ed._recovery_modal
    assert ed.scene_dirty
    assert len(ed.scene_data["objects"]) == 1
    # the undo label goes through i18n (the stub _TR returns the English default)
    assert "Autosave restore" in ed.undo_labels


def test_recovery_non_proposto_se_autosave_vecchio_o_uguale(tmp_path):
    ed = FakeIO(tmp_path)
    now = time.time()
    _write_scene(ed, [], now - 10)
    _write_autosave(ed, [{"catalog_id": "x"}], now - 600)   # PIU' VECCHIO
    ed._check_autosave_recovery()
    assert not ed._recovery_modal

    # Autosave recente ma IDENTICO al contenuto in memoria: niente proposta
    ed2 = FakeIO(tmp_path)
    _write_scene(ed2, [], now - 600)
    _write_autosave(ed2, [], now - 5)
    ed2.scene_data = {"objects": []}
    ed2._check_autosave_recovery()
    assert not ed2._recovery_modal


def test_recovery_dismiss_vale_per_la_sessione(tmp_path):
    ed = FakeIO(tmp_path)
    now = time.time()
    _write_scene(ed, [], now - 600)
    _write_autosave(ed, [{"catalog_id": "x"}], now - 5)
    ed._check_autosave_recovery()
    assert ed._recovery_modal
    ed._recovery_dismiss()
    assert not ed._recovery_modal
    ed._check_autosave_recovery()          # niente riproposta
    assert not ed._recovery_modal


def test_backup_rotativo_tiene_ultimi_n(tmp_path):
    ed = FakeIO(tmp_path)
    scene_p = _write_scene(ed, [], time.time())
    for i in range(SCENE_BACKUPS_KEEP + 3):
        scene_p.write_text(json.dumps({"objects": [], "rev": i}),
                           encoding="utf-8")
        ed._backup_scene_file(scene_p)
    bdir = ed.base_path / ".editor_backups" / "g1" / "L1" / "S1"
    backups = list(bdir.glob("scene_*.json"))
    assert len(backups) == SCENE_BACKUPS_KEEP
    # Devono sopravvivere ESATTAMENTE le ultime N revisioni (i nomi possono
    # essere riusati dopo il prune: conta il contenuto, non l'ordine dei nomi)
    revs = {json.loads(p.read_text(encoding="utf-8")).get("rev")
            for p in backups}
    n_total = SCENE_BACKUPS_KEEP + 3
    assert revs == set(range(n_total - SCENE_BACKUPS_KEEP, n_total))


def test_img_cache_lru_evict_graduale(tmp_path):
    ed = FakeIO(tmp_path)
    icon = tmp_path / "icon.png"
    surf = pygame.Surface((16, 16), pygame.SRCALPHA)
    surf.fill((255, 0, 0, 255))
    pygame.image.save(surf, str(icon))

    for i in range(IMG_CACHE_MAX + 40):
        got = ed._load_img(icon, (8 + (i % 500), 8))
        assert got is not None
    assert len(ed._img_cache) <= IMG_CACHE_MAX

    # LRU: una chiave toccata di recente sopravvive alle prossime insert
    hot_key = (str(icon), (8 + 0, 8))
    ed._load_img(icon, (8, 8))             # tocco la piu' vecchia possibile
    for i in range(30):
        ed._load_img(icon, (600 + i, 8))
    assert hot_key in ed._img_cache


# ─────────────────────────────────────────────────────────────────────────────
# Autosave hardening + main loop crash guard
# ─────────────────────────────────────────────────────────────────────────────

def test_autosave_force_saves_a_clean_scene(tmp_path):
    """The crash guard must be able to flush a scene that is not dirty."""
    ed = FakeIO(tmp_path)
    ed.scene_data = {"objects": [{"catalog_id": "x", "x": 1, "y": 2, "_tmp": 1}]}
    ed.scene_dirty = False

    assert ed._autosave() is False                    # nothing to do when clean
    assert not (ed.scene_path / "scene.json.autosave").exists()

    assert ed._autosave(force=True) is True
    saved = json.loads((ed.scene_path / "scene.json.autosave").read_text(encoding="utf-8"))
    assert saved["objects"][0]["catalog_id"] == "x"
    assert "_tmp" not in saved["objects"][0]          # runtime keys are stripped


def test_autosave_failure_does_not_propagate_and_backs_off(tmp_path, monkeypatch):
    """A failing write must not kill the main loop, nor retry every frame."""
    import editor.mixins.io_ops as io_ops

    ed = FakeIO(tmp_path)
    ed.scene_data = {"objects": []}
    ed.scene_dirty = True
    ed.last_autosave = 0.0

    def _boom(path, data):
        raise OSError("disk full")

    monkeypatch.setattr(io_ops, "_save_json", _boom)
    assert ed._autosave() is False                    # swallowed, not raised
    # the next attempt is one back-off away, not on the very next frame
    due_in = ed.last_autosave + AUTOSAVE_SECS - time.time()
    assert 0 < due_in <= AUTOSAVE_RETRY_SECS + 1

    # a writer that refuses without raising is handled the same way
    ed.last_autosave = 0.0
    monkeypatch.setattr(io_ops, "_save_json", lambda path, data: False)
    assert ed._autosave() is False
    due_in = ed.last_autosave + AUTOSAVE_SECS - time.time()
    assert 0 < due_in <= AUTOSAVE_RETRY_SECS + 1


def test_recovery_restores_the_scene_in_place(tmp_path):
    """Rebinding scene_data would leave the other mixins on the stale dict."""
    ed = FakeIO(tmp_path)
    now = time.time()
    _write_scene(ed, [], now - 600)
    _write_autosave(ed, [{"catalog_id": "x", "x": 1, "y": 2}], now - 10)
    ed.scene_data = {"objects": []}
    held_by_another_mixin = ed.scene_data

    ed._check_autosave_recovery()
    ed._recovery_accept()
    assert ed.scene_data is held_by_another_mixin
    assert len(held_by_another_mixin["objects"]) == 1


class FakeLoopEditor:
    """Host for EditorBase.run(): counts frames and fails on demand."""

    def __init__(self, fail_frames: set, total: int = 8):
        from editor.editor_base import LevelEditor
        self.run = LevelEditor.run.__get__(self)
        self._crash_guard = LevelEditor._crash_guard.__get__(self)
        self.running = True
        self.clock = type("C", (), {"tick": lambda self, fps: 0})()
        self.frame = 0
        self.fail_frames = fail_frames
        self.total = total
        self.rendered = 0
        self.autosaves = 0
        self.last_autosave = 0.0
        self.statuses: list[str] = []
        self.cleaned = False

    def _handle_events(self):
        self.frame += 1
        if self.frame > self.total:
            self.running = False
        if self.frame in self.fail_frames:
            raise RuntimeError(f"frame {self.frame} exploded")

    def _update(self):
        pass

    def _render(self):
        self.rendered += 1

    def _autosave(self, force=False):
        self.autosaves += 1
        self.last_autosave = time.time()   # as the real one does on success
        return True

    def _status(self, msg, color=None, duration=0):
        self.statuses.append(str(msg))

    def _TR(self, key, default=None):
        return default if default is not None else key

    def _cleanup_processes(self):
        self.cleaned = True


def _run_loop(ed, monkeypatch):
    """Run the real main loop with pygame stubbed out (no display, no quit)."""
    import editor.editor_base as eb

    fake_pygame = type("P", (), {
        "display": type("D", (), {"flip": staticmethod(lambda: None)})(),
        "quit": staticmethod(lambda: None),
    })()
    monkeypatch.setattr(eb, "pygame", fake_pygame)
    ed.run()


def test_main_loop_survives_an_isolated_crash(tmp_path, monkeypatch):
    """A bad frame saves the work and the editor keeps running."""
    ed = FakeLoopEditor(fail_frames={2, 5}, total=8)
    _run_loop(ed, monkeypatch)

    assert ed.frame == 9                       # the loop reached its natural end
    assert ed.rendered == 7                    # only the two bad frames skipped
    assert len(ed.statuses) == 2               # the user was told about both
    # the whole loop runs well inside one second: the work is written once and
    # the second crash is throttled instead of rewriting the scene
    assert ed.autosaves == 1
    assert ed.cleaned


def test_main_loop_gives_up_after_repeated_crashes(tmp_path, monkeypatch):
    """An unrecoverable state must not spin forever - but saves first."""
    ed = FakeLoopEditor(fail_frames=set(range(1, 50)), total=100)
    with pytest.raises(RuntimeError):
        _run_loop(ed, monkeypatch)

    assert ed.frame == MAIN_LOOP_MAX_CRASHES
    assert ed.autosaves >= 1                   # the work was written before giving up
    assert ed.cleaned                          # cleanup still runs on the way out


# ─────────────────────────────────────────────────────────────────────────────
# Theme harvest: staged swap (a failure must not leave the game themeless)
# ─────────────────────────────────────────────────────────────────────────────

class FakeGameSelect:
    """Host for the harvest routine only (no editor, no window)."""

    def __init__(self, tmp_path: Path):
        from editor.mixins.game_select import GameSelectMixin
        self._gs_harvest_theme = GameSelectMixin._gs_harvest_theme.__get__(self)
        self.base_path = tmp_path
        self.statuses: list[str] = []
        (tmp_path / "games" / "g1").mkdir(parents=True, exist_ok=True)

    def _status(self, msg, color=None, duration=0):
        self.statuses.append(str(msg))

    def _TR(self, key, default=None):
        return default if default is not None else key

    @property
    def theme_dir(self) -> Path:
        return self.base_path / "games" / "g1" / "ui_theme"

    def seed_previous_theme(self) -> None:
        self.theme_dir.mkdir(parents=True, exist_ok=True)
        (self.theme_dir / "theme.json").write_text('{"id": "previous"}', encoding="utf-8")


def _theme_id(path: Path) -> str:
    return json.loads((path / "theme.json").read_text(encoding="utf-8"))["id"]


def test_theme_harvest_replaces_the_game_theme(tmp_path):
    ed = FakeGameSelect(tmp_path)
    ed.seed_previous_theme()
    assert ed._gs_harvest_theme("g1", "horror") is True
    assert _theme_id(ed.theme_dir) == "horror"
    # no staging leftovers next to the harvested theme
    assert not (ed.theme_dir.parent / "ui_theme.__new__").exists()
    assert not (ed.theme_dir.parent / "ui_theme.__old__").exists()


def test_missing_theme_keeps_the_previous_one(tmp_path):
    """Regression: the old code deleted ui_theme/ before looking for the source."""
    ed = FakeGameSelect(tmp_path)
    ed.seed_previous_theme()
    assert ed._gs_harvest_theme("g1", "does_not_exist") is False
    assert _theme_id(ed.theme_dir) == "previous"
    assert ed.statuses, "the user must be told the theme was not applied"


def test_failed_copy_rolls_back_to_the_previous_theme(tmp_path, monkeypatch):
    import shutil

    ed = FakeGameSelect(tmp_path)
    ed.seed_previous_theme()
    monkeypatch.setattr(shutil, "copytree",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("disk full")))
    assert ed._gs_harvest_theme("g1", "horror") is False
    assert _theme_id(ed.theme_dir) == "previous"
    assert not (ed.theme_dir.parent / "ui_theme.__new__").exists()


def test_emergency_save_is_throttled(tmp_path, monkeypatch):
    """A fresh autosave must not be rewritten by the crash guard."""
    ed = FakeLoopEditor(fail_frames={2, 3}, total=4)
    ed.last_autosave = time.time()             # saved a moment ago
    _run_loop(ed, monkeypatch)
    assert ed.autosaves == 0
    assert len(ed.statuses) == 2               # the user is warned anyway
