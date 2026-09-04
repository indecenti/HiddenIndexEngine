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

from editor.constants import IMG_CACHE_MAX, SCENE_BACKUPS_KEEP
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
    assert "Ripristino autosave" in ed.undo_labels


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
