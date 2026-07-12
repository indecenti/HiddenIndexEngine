"""
tests/test_scatter_render_loop.py

Ondata 2: best-of-M render-in-the-loop (render_ctx), cancel/progress hook,
repair loop (run_scatter_with_repair). BG sintetici + icone temporanee.
"""

from __future__ import annotations

import os
import threading

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import numpy as np
import pytest

pygame = pytest.importorskip("pygame")
cv2 = pytest.importorskip("cv2")

from editor.tools.scatter_engine import (
    BGAnalysis, ObjAnalysis, ScatterCancelled, place_objects,
)
from editor.tools.scatter_validate import run_scatter_with_repair


@pytest.fixture(scope="module", autouse=True)
def _pygame_init():
    pygame.init()
    pygame.display.set_mode((64, 64))
    yield
    pygame.quit()


CH, CW, CP = 10, 14, 48   # griglia -> BG 672x480


def _bg_grid(hue: float = 0.33) -> BGAnalysis:
    return BGAnalysis(
        bg_w=CW * CP, bg_h=CH * CP, cell_w=CW, cell_h=CH, cell_px=CP,
        edge_density=np.full((CH, CW), 0.5, dtype=np.float32),
        saliency=np.zeros((CH, CW), dtype=np.float32),
        hue=np.full((CH, CW), hue, dtype=np.float32),
        sat=np.full((CH, CW), 0.6, dtype=np.float32),
        val=np.full((CH, CW), 0.55, dtype=np.float32),
        grad_orient=np.zeros((CH, CW), dtype=np.float32),
    )


def _obj(hue: float, cid: str) -> ObjAnalysis:
    return ObjAnalysis(
        catalog_id=cid, palette=[(hue, 0.6, 0.55)] * 3,
        edge_orient=0.0, aspect=1.0, size_class="mid",
        palette_ext=[{"h": hue, "s": 0.6, "v": 0.55, "w": 1.0, "var": 0.01}],
    )


def _icon(tmp_path, name: str, rgb: tuple[int, int, int]):
    surf = pygame.Surface((64, 64), pygame.SRCALPHA)
    surf.fill((*rgb, 255))
    pygame.image.save(surf, str(tmp_path / name))


GREEN = (60, 140, 60)
MAGENTA = (255, 40, 200)


def test_cancel_event_interrompe():
    bg = _bg_grid()
    analyses = {"o": _obj(0.33, "o")}
    entries = {"o": {"tags": [], "default_detection": "circle",
                     "default_radius": 24, "icon": "o.png"}}
    ev = threading.Event()
    ev.set()
    with pytest.raises(ScatterCancelled):
        place_objects(bg, analyses, entries, count=5, difficulty="medium",
                      style="real", allowed_layers=["objects_mid"], seed=3,
                      cancel_event=ev)


def test_progress_cb_monotono():
    bg = _bg_grid()
    analyses = {"o": _obj(0.33, "o")}
    entries = {"o": {"tags": [], "default_detection": "circle",
                     "default_radius": 24}}
    seen: list[tuple[int, int]] = []
    placed = place_objects(bg, analyses, entries, count=6, difficulty="medium",
                           style="real", allowed_layers=["objects_mid"], seed=3,
                           progress_cb=lambda d, t: seen.append((d, t)))
    assert placed
    assert seen, "progress_cb mai chiamata"
    dones = [d for d, _ in seen]
    assert dones == sorted(dones)              # monotono non decrescente
    assert dones[-1] == len(placed)
    assert all(t == 6 for _, t in seen)


def test_best_of_m_preferisce_la_meta_giusta(tmp_path):
    """BG REALE mezzo verde / mezzo magenta, griglia neutra (lo score matrix
    non sa i colori): SOLO il best-of-M render puo' capire dove l'oggetto
    verde si fonde. Con render_ctx i piazzamenti finiscono nel lato verde."""
    bg = _bg_grid(hue=0.33)
    surf = pygame.Surface((bg.bg_w, bg.bg_h))
    surf.fill(GREEN)
    half_x = bg.bg_w // 2
    surf.fill(MAGENTA, pygame.Rect(half_x, 0, bg.bg_w - half_x, bg.bg_h))
    _icon(tmp_path, "green.png", GREEN)
    analyses = {"g": _obj(0.33, "g")}
    entries = {"g": {"tags": [], "default_detection": "circle",
                     "default_radius": 24, "icon": "green.png"}}
    render_ctx = {"bg_surface": surf, "game_path": tmp_path,
                  "repo_root": tmp_path}
    placed = place_objects(bg, analyses, entries, count=8, difficulty="hard",
                           style="real", allowed_layers=["objects_mid"],
                           seed=11, render_ctx=render_ctx)
    assert len(placed) >= 5
    on_green = sum(1 for p in placed if p.x < half_x)
    assert on_green >= int(0.75 * len(placed)), \
        f"solo {on_green}/{len(placed)} nel lato dove l'oggetto si fonde"


def test_render_ctx_deterministico(tmp_path):
    bg = _bg_grid()
    surf = pygame.Surface((bg.bg_w, bg.bg_h))
    surf.fill(GREEN)
    _icon(tmp_path, "green.png", GREEN)
    analyses = {"g": _obj(0.33, "g")}
    entries = {"g": {"tags": [], "default_detection": "circle",
                     "default_radius": 24, "icon": "green.png"}}

    def _run():
        ctx = {"bg_surface": surf, "game_path": tmp_path,
               "repo_root": tmp_path}
        return place_objects(bg, analyses, entries, count=6,
                             difficulty="medium", style="real",
                             allowed_layers=["objects_mid"], seed=42,
                             render_ctx=ctx)

    a, b = _run(), _run()
    assert len(a) == len(b) > 0
    for pa, pb in zip(a, b):
        assert (pa.x, pa.y, pa.rotation, pa.alpha) == (pb.x, pb.y,
                                                       pb.rotation, pb.alpha)


def test_repair_completa_il_count(tmp_path):
    """Oggetto identico al BG: nessun fail, delivered == requested, 0 giri."""
    bg = _bg_grid(hue=0.33)
    surf = pygame.Surface((bg.bg_w, bg.bg_h))
    surf.fill(GREEN)
    _icon(tmp_path, "green.png", GREEN)
    analyses = {"g": _obj(0.33, "g")}
    entries = {"g": {"tags": [], "default_detection": "circle",
                     "default_radius": 24, "icon": "green.png"}}
    kept, results, report = run_scatter_with_repair(
        bg, analyses, entries, bg_surface=surf, game_path=tmp_path,
        repo_root=tmp_path, count=6, difficulty="medium", style="real",
        allowed_layers=["objects_mid"], seed=5)
    assert report["requested"] == 6
    assert report["delivered"] == len(kept) == 6
    assert report["repair_rounds"] == 0
    assert report["dropped_fail"] == 0
    assert len(results) == len(kept)
    assert all(r["verdict"] != "fail" for r in results)


def test_repair_report_onesto_quando_tutto_fallisce(tmp_path):
    """La griglia MENTE (dice magenta) ma il BG reale e' verde: ogni oggetto
    magenta piazzato viene bocciato dalla validazione; il repair ritenta e
    alla fine il report dice la verita' (delivered < requested)."""
    bg = _bg_grid(hue=0.83)          # griglia compatibile col magenta
    surf = pygame.Surface((bg.bg_w, bg.bg_h))
    surf.fill(GREEN)                 # realta': verde pieno
    _icon(tmp_path, "mag.png", MAGENTA)
    analyses = {"m": _obj(0.83, "m")}
    entries = {"m": {"tags": [], "default_detection": "circle",
                     "default_radius": 24, "icon": "mag.png"}}
    kept, results, report = run_scatter_with_repair(
        bg, analyses, entries, bg_surface=surf, game_path=tmp_path,
        repo_root=tmp_path, count=5, difficulty="medium", style="real",
        allowed_layers=["objects_mid"], seed=5, max_repair_rounds=2)
    assert report["delivered"] == len(kept) < 5
    assert report["dropped_fail"] > 0
    assert report["repair_rounds"] >= 1
    assert all(r["verdict"] != "fail" for r in results)
