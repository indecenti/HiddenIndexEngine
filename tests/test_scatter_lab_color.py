"""
tests/test_scatter_lab_color.py

Colore in Lab (camouflage v4, ondata 1): la similarita' per cella usa il
Delta-E percettivo con L pesata, con ASIMMETRIA del tint moltiplicativo
(l'engine puo' solo scurire: un oggetto piu' chiaro del fondo e' recuperabile,
uno piu' scuro no); il mix del tint e' ottimizzato per piazzamento; l'alpha
e' adattivo per difficolta'. Il percorso HSV storico resta il fallback quando
lab_grid non c'e' (BG sintetici dei test legacy).
"""

from __future__ import annotations

import numpy as np
import pytest

cv2 = pytest.importorskip("cv2")

from editor.tools.scatter_engine import (
    ALPHA_RANGE, BGAnalysis, LAB_TINT_RECOVER, ObjAnalysis, TINT_MIX_MAX,
    _color_similarity_map, _color_similarity_map_lab, _lab_harmonize_tint,
    _obj_lab_clusters, place_objects,
)


def _bg_grid(ch: int = 6, cw: int = 8, lab: tuple[float, float, float] = (50.0, 0.0, 0.0)
             ) -> BGAnalysis:
    """BG sintetico con lab_grid uniforme (L, a, b dati)."""
    cp = 48
    grid = np.zeros((ch, cw, 3), dtype=np.float32)
    grid[..., 0] = lab[0]
    grid[..., 1] = lab[1]
    grid[..., 2] = lab[2]
    return BGAnalysis(
        bg_w=cw * cp, bg_h=ch * cp, cell_w=cw, cell_h=ch, cell_px=cp,
        edge_density=np.full((ch, cw), 0.5, dtype=np.float32),
        saliency=np.zeros((ch, cw), dtype=np.float32),
        hue=np.full((ch, cw), 0.3, dtype=np.float32),
        sat=np.full((ch, cw), 0.5, dtype=np.float32),
        val=np.full((ch, cw), 0.5, dtype=np.float32),
        grad_orient=np.zeros((ch, cw), dtype=np.float32),
        lab_grid=grid,
    )


def _obj_hsv(h: float, s: float, v: float, cid: str = "obj") -> ObjAnalysis:
    return ObjAnalysis(
        catalog_id=cid, palette=[(h, s, v)] * 3,
        edge_orient=0.0, aspect=1.0, size_class="mid",
        palette_ext=[{"h": h, "s": s, "v": v, "w": 1.0, "var": 0.01}],
    )


def _lab_of_hsv(h: float, s: float, v: float) -> tuple[float, float, float]:
    px = np.uint8([[[int(h * 180) % 180, int(s * 255), int(v * 255)]]])
    rgb = cv2.cvtColor(px, cv2.COLOR_HSV2RGB)
    lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB)[0, 0].astype(np.float32)
    return float(lab[0]) * 100.0 / 255.0, float(lab[1]) - 128.0, float(lab[2]) - 128.0


def test_lab_path_attivo_e_ordinato():
    """Con lab_grid: match perfetto -> cs alto; colore lontano -> cs basso."""
    obj = _obj_hsv(0.33, 0.7, 0.6)          # verde
    ol, oa, ob = _lab_of_hsv(0.33, 0.7, 0.6)
    bg_match = _bg_grid(lab=(ol, oa, ob))    # cella = colore oggetto
    bg_far = _bg_grid(lab=(ol, -oa, -ob))    # stessa L, cromia opposta
    cs_match = _color_similarity_map(bg_match, obj)
    cs_far = _color_similarity_map(bg_far, obj)
    assert float(cs_match.min()) > 0.85
    assert float(cs_far.max()) < float(cs_match.min())


def test_lab_fallback_none_senza_grid():
    """Senza lab_grid il percorso Lab e' spento (fallback HSV legacy)."""
    obj = _obj_hsv(0.0, 0.6, 0.6)
    bg = _bg_grid()
    bg.lab_grid = None
    assert _color_similarity_map_lab(bg, obj) is None
    # e la mappa complessiva resta calcolabile via HSV
    cs = _color_similarity_map(bg, obj)
    assert cs.shape == (bg.cell_h, bg.cell_w)


def test_asimmetria_tint_luminanza():
    """Oggetto PIU' CHIARO del fondo (tint puo' scurire) deve scorare meglio
    di uno PIU' SCURO dello stesso Delta-L (il tint non schiarisce)."""
    assert 0.0 < LAB_TINT_RECOVER < 1.0
    # Due grigi reali, il fondo esattamente a meta' della loro L: Delta-L
    # simmetrico per costruzione, senza hook privati.
    lighter = _obj_hsv(0.0, 0.0, 0.67, cid="light")
    darker = _obj_hsv(0.0, 0.0, 0.286, cid="dark")
    l_hi, _, _ = _lab_of_hsv(0.0, 0.0, 0.67)
    l_lo, _, _ = _lab_of_hsv(0.0, 0.0, 0.286)
    bg = _bg_grid(lab=((l_hi + l_lo) / 2.0, 0.0, 0.0))
    cs_light = _color_similarity_map_lab(bg, lighter)
    cs_dark = _color_similarity_map_lab(bg, darker)
    assert cs_light is not None and cs_dark is not None
    assert float(cs_light.mean()) > float(cs_dark.mean()) + 0.03


def test_obj_lab_clusters_da_palette():
    """Conversione palette_ext -> cluster Lab pesati."""
    obj = _obj_hsv(0.0, 0.0, 1.0)  # bianco
    clusters = _obj_lab_clusters(obj)
    assert clusters
    l, a, b, w = clusters[0]
    assert l > 90.0 and abs(a) < 5.0 and abs(b) < 5.0
    assert w == pytest.approx(1.0)


def _bg_with_footprint(rgb_color: tuple[int, int, int]) -> BGAnalysis:
    """BG piccolo reale (64x64) con lab_full/hsv_full per il tint."""
    rgb = np.zeros((96, 96, 3), dtype=np.uint8)
    rgb[...] = rgb_color
    bg = _bg_grid(ch=2, cw=2)
    bg.hsv_full = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    bg.lab_full = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB)
    return bg


def test_tint_ottimizzato_per_oggetto():
    """Oggetto BIANCO su fondo verde scuro: il mix ottimo e' alto (scurisce
    verso il fondo). Oggetto GIA' verde: il mix ottimo resta basso e il
    filtro e' piu' chiaro (vicino al bianco = nessun tint)."""
    bg = _bg_with_footprint((40, 90, 40))
    white = [(250, 250, 250)]
    green = [(40, 90, 40)]
    f_white = _lab_harmonize_tint(bg, 8, 8, 88, 88, "hard", obj_rgbs=white)
    f_green = _lab_harmonize_tint(bg, 8, 8, 88, 88, "hard", obj_rgbs=green)
    assert f_white is not None and f_green is not None
    # filtro per il bianco deve scurire di piu' (somma canali piu' bassa)
    assert sum(f_white) < sum(f_green)
    # per l'oggetto gia' identico al fondo il tint deve essere ~neutro
    assert min(f_green) > 235


def test_tint_rispetta_mix_max_per_difficolta():
    """Il filtro non puo' scurire oltre il mix massimo della difficolta'."""
    bg = _bg_with_footprint((10, 10, 10))     # fondo quasi nero
    white = [(255, 255, 255)]
    for diff, mix_max in TINT_MIX_MAX.items():
        f = _lab_harmonize_tint(bg, 8, 8, 88, 88, diff, obj_rgbs=white)
        assert f is not None
        # mix massimo -> canale minimo raggiungibile = (1-mix)*255 + mix*L_clamp
        # con L clampata a TINT_MIN_L: il filtro resta sopra questa soglia.
        assert min(f) >= int((1.0 - mix_max) * 255) - 1


def _bg_placement(ch: int = 12, cw: int = 16) -> BGAnalysis:
    cp = 48
    return BGAnalysis(
        bg_w=cw * cp, bg_h=ch * cp, cell_w=cw, cell_h=ch, cell_px=cp,
        edge_density=np.full((ch, cw), 0.5, dtype=np.float32),
        saliency=np.zeros((ch, cw), dtype=np.float32),
        hue=np.full((ch, cw), 0.0, dtype=np.float32),
        sat=np.full((ch, cw), 0.6, dtype=np.float32),
        val=np.full((ch, cw), 0.6, dtype=np.float32),
        grad_orient=np.zeros((ch, cw), dtype=np.float32),
    )


def test_alpha_adattivo_per_difficolta():
    """hard: alpha nel range ALPHA_RANGE; easy: sempre 255. Deterministico."""
    bg = _bg_placement()
    obj = _obj_hsv(0.0, 0.6, 0.6, cid="obj_red")
    analyses = {"obj_red": obj}
    entries = {"obj_red": {"tags": [], "default_detection": "circle",
                           "default_radius": 24}}

    hard1 = place_objects(bg, analyses, entries, count=8, difficulty="hard",
                          style="real", allowed_layers=["objects_mid"], seed=5)
    hard2 = place_objects(bg, analyses, entries, count=8, difficulty="hard",
                          style="real", allowed_layers=["objects_mid"], seed=5)
    assert len(hard1) > 0
    lo, hi = ALPHA_RANGE["hard"]
    for p in hard1:
        assert lo <= p.alpha <= hi
    assert [p.alpha for p in hard1] == [p.alpha for p in hard2]  # deterministico

    easy = place_objects(bg, analyses, entries, count=8, difficulty="easy",
                         style="real", allowed_layers=["objects_mid"], seed=5)
    assert easy and all(p.alpha == 255 for p in easy)
