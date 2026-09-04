"""
tests/test_scatter_modal_worker.py

U1/U2 (ondata 2): il modal scatter gira in worker thread con progress e
cancel, e il seed e' riproducibile. Host fake con i soli attributi che
ScatterModalMixin usa: niente editor completo, niente display reale.
"""

from __future__ import annotations

import os
import time

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pytest

pygame = pytest.importorskip("pygame")
cv2 = pytest.importorskip("cv2")

from editor.mixins.scatter_modal import ScatterModalMixin


@pytest.fixture(scope="module", autouse=True)
def _pygame_init():
    pygame.init()
    pygame.display.set_mode((64, 64))
    from editor.ui.draw import _init_fonts
    _init_fonts()
    yield
    pygame.quit()


GREEN = (60, 140, 60)


class FakeEditor(ScatterModalMixin):
    """Host minimo per il mixin: catalogo sintetico + BG verde."""

    def __init__(self, tmp_path, n_objects: int = 3):
        self.base_path = tmp_path
        self.game_path = tmp_path
        self.scene_path = tmp_path / "scena"
        self.scene_path.mkdir(exist_ok=True)
        self.scene_data = {"objects": []}
        self.screen = pygame.Surface((1280, 800))
        self.bg_surf = pygame.Surface((672, 480))
        self.bg_surf.fill(GREEN)
        self.catalog = []
        for i in range(n_objects):
            name = f"obj_{i}.png"
            surf = pygame.Surface((64, 64), pygame.SRCALPHA)
            surf.fill((*GREEN, 255))
            pygame.image.save(surf, str(tmp_path / name))
            self.catalog.append({
                "id": f"obj_{i}", "style": "real", "icon": name,
                "tags": [], "default_detection": "circle",
                "default_radius": 24,
            })
        self._scatter_modal_init()
        self._scatter_tier_choice = "classic"   # niente modelli/download
        self._scatter_yunet_tried = True        # niente rete nel test
        self._scatter_model_tier_active = 0

    # Stub dell'infrastruttura editor usata dal mixin
    def _load_editor_settings(self):
        return {}

    def _save_editor_setting(self, key, value):
        pass

    def _status(self, msg, color=None, secs=0):
        pass

    def _TR(self, key, default=None):
        """Stub i18n: restituisce il default inglese passato dal codice."""
        return default if default is not None else key

    def _push_undo(self, *a, **k):
        pass

    def _mark_dirty(self):
        pass

    def _s2r(self, x, y):
        return x, y

    def _scatter_load_model(self):
        self._scatter_model = None
        self._scatter_model_tier_active = 0


def _wait_result(ed: FakeEditor, timeout_s: float = 30.0):
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        ed._scatter_consume_result()
        if not ed._scatter_busy:
            return
        time.sleep(0.05)
    raise AssertionError("worker scatter non ha finito entro il timeout")


def test_worker_end_to_end_con_seed(tmp_path):
    ed = FakeEditor(tmp_path)
    ed._scatter_modal_open = True
    ed._scatter_count = 5
    ed._scatter_seed_text = "1234"
    ed._scatter_run()
    assert ed._scatter_busy
    _wait_result(ed)
    assert ed._scatter_ghosts, ed._scatter_status_msg
    assert ed._scatter_last_seed == 1234
    assert "1234" in ed._scatter_status_msg
    first = [(g.catalog_id, g.x, g.y) for g in ed._scatter_ghosts]

    # Stesso seed nel campo -> stesso risultato (riproducibilita' U2)
    ed._scatter_seed_text = "1234"
    ed._scatter_run()
    _wait_result(ed)
    second = [(g.catalog_id, g.x, g.y) for g in ed._scatter_ghosts]
    assert first == second


def test_reroll_cambia_seed(tmp_path):
    ed = FakeEditor(tmp_path)
    ed._scatter_modal_open = True
    ed._scatter_count = 4
    ed._scatter_seed_text = "77"
    ed._scatter_seed_locked = True
    ed._scatter_run()
    _wait_result(ed)
    assert ed._scatter_last_seed == 77
    ed._scatter_run(reroll=True)          # RIPESCA: ignora lucchetto e campo
    _wait_result(ed)
    assert ed._scatter_last_seed != 77
    assert ed._scatter_seed_text == str(ed._scatter_last_seed)


def test_cancel_scarta_il_risultato(tmp_path):
    ed = FakeEditor(tmp_path)
    ed._scatter_modal_open = True
    ed._scatter_count = 30
    ed._scatter_run()
    ed._scatter_cancel_run()              # annulla subito
    assert not ed._scatter_busy
    time.sleep(1.0)                       # lascia morire il worker
    ed._scatter_consume_result()
    # Il risultato della run vecchia (token invalidato) non deve applicarsi
    assert ed._scatter_ghosts == []


def test_render_modal_idle_e_busy_non_crasha(tmp_path):
    """Smoke render: riga seed (idle) e barra progresso + ANNULLA (busy)."""
    ed = FakeEditor(tmp_path)
    ed._scatter_modal_open = True
    ed._r_scatter_modal(1280, 800)        # idle: riga seed disegnata
    assert "seed_box" in ed._scatter_hitboxes
    assert "seed_lock" in ed._scatter_hitboxes
    assert "generate" in ed._scatter_hitboxes

    ed._scatter_busy = True
    ed._scatter_progress = ("Piazzamento", 3, 10)
    ed._r_scatter_modal(1280, 800)        # busy: barra + ANNULLA
    assert "cancel_run" in ed._scatter_hitboxes
    assert "generate" not in ed._scatter_hitboxes


def _run_and_wait(ed: FakeEditor, count: int = 5, seed: str = "1234"):
    ed._scatter_modal_open = True
    ed._scatter_count = count
    ed._scatter_seed_text = seed
    ed._scatter_run()
    _wait_result(ed)


def test_preview_seleziona_sposta_elimina_blocca(tmp_path):
    """U3: hit-test, spostamento con rimisura, delete, lock, keep su reroll."""
    ed = FakeEditor(tmp_path)
    _run_and_wait(ed)
    assert ed._scatter_ghosts
    assert len(ed._scatter_ghost_info) == len(ed._scatter_ghosts)

    ed._scatter_preview_enter()
    assert ed._scatter_preview_active

    # Hit-test sul centro del primo ghost (identita' schermo=riferimento)
    g0 = ed._scatter_ghosts[0]
    cx, cy, _w, _h = ed._scatter_ghost_center(g0)
    idx = ed._scatter_ghost_at(int(cx), int(cy))
    assert idx is not None and ed._scatter_ghosts[idx] is g0

    # Sposta e rimisura: info del ghost aggiornata, dentro il BG
    n_before = len(ed._scatter_ghosts)
    ed._scatter_sel_ghost = idx
    ed._scatter_drag = (idx, 0.0, 0.0)
    ed._scatter_ghost_move_to(idx, 50.0, 50.0)
    ed._scatter_preview_drag_end()
    assert ed._scatter_drag is None
    inf = ed._scatter_ghost_info[idx]
    assert inf is not None and inf["verdict"] in ("ok", "warn", "fail")

    # Lock + reroll: il bloccato sopravvive identico
    ed._scatter_toggle_lock(idx)
    locked_obj = ed._scatter_ghosts[idx]
    assert getattr(locked_obj, "locked", False)
    locked = [g for g in ed._scatter_ghosts if getattr(g, "locked", False)]
    ed._scatter_preview_exit()
    ed._scatter_run(reroll=True, keep=locked)
    _wait_result(ed)
    assert locked_obj in ed._scatter_ghosts
    assert len(ed._scatter_ghosts) == n_before

    # Delete: il conteggio scende e la selezione si azzera
    ed._scatter_preview_enter()
    ed._scatter_delete_ghost(0)
    assert len(ed._scatter_ghosts) == n_before - 1
    assert ed._scatter_sel_ghost is None


def test_preview_reroll_singolo(tmp_path):
    """R sul ghost selezionato: solo quello cambia, gli altri restano."""
    ed = FakeEditor(tmp_path)
    _run_and_wait(ed, count=4)
    ghosts0 = list(ed._scatter_ghosts)
    assert len(ghosts0) >= 2
    ed._scatter_preview_enter()
    ed._scatter_reroll_single(0)
    assert len(ed._scatter_ghosts) == len(ghosts0)
    assert ed._scatter_ghosts[1:] == ghosts0[1:]      # gli altri intatti
    inf0 = ed._scatter_ghost_info[0]
    assert inf0 is None or inf0["verdict"] in ("ok", "warn", "fail")


def test_key_handler_seed(tmp_path):
    ed = FakeEditor(tmp_path)
    ed._scatter_modal_open = True
    ed._scatter_seed_editing = True

    class Ev:
        def __init__(self, key, unicode=""):
            self.key = key
            self.unicode = unicode

    for ch in "42":
        assert ed._scatter_modal_key(Ev(pygame.K_0, ch))
    assert ed._scatter_seed_text == "42"
    ed._scatter_modal_key(Ev(pygame.K_BACKSPACE))
    assert ed._scatter_seed_text == "4"
    ed._scatter_modal_key(Ev(pygame.K_RETURN))
    assert not ed._scatter_seed_editing
    # ESC senza editing e senza run: chiude il modal
    ed._scatter_modal_key(Ev(pygame.K_ESCAPE))
    assert not ed._scatter_modal_open
