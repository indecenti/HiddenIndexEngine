"""
editor/tools/face_zones.py

Rilevamento volti sul background per lo scatter: i volti sono zone VIETATE
(un oggetto nascosto su una faccia e' sempre in bella vista e "sbagliato"
per un hidden-object professionale).

Due percorsi, in ordine di preferenza:
  1. YuNet (cv2.FaceDetectorYN, modello ONNX ~0.3MB scaricato on-demand via
     editor/tools/download_models.py) — preciso, veloce su CPU.
  2. Haar cascade (frontalface + profileface, inclusi in opencv-python) —
     fallback senza download, meno preciso.

Output: lista di box (x0, y0, x1, y1) in pixel BG, e maschera bool sulla
griglia celle dello scatter (face_cell_mask). Entrambi deterministici.
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np

log = logging.getLogger(__name__)

try:
    import cv2  # type: ignore
    _HAS_CV2 = True
except Exception:
    _HAS_CV2 = False

# Lato lungo massimo dell'immagine passata al detector: i BG possono essere
# 5000px+, la detection non guadagna nulla oltre questa risoluzione.
FACE_DETECT_MAX_SIDE = 1280
# Parametri YuNet
FACE_SCORE_THRESHOLD = 0.6
FACE_NMS_THRESHOLD = 0.3
FACE_TOP_K = 500
# Parametri Haar fallback
HAAR_SCALE_FACTOR = 1.1
HAAR_MIN_NEIGHBORS = 5
# Dimensione minima volto = lato lungo (downscalato) / questo divisore.
HAAR_MIN_SIZE_DIVISOR = 64
# Dilatazione dei box volto per lato (0.25 = +25% per lato): copre collo/
# capelli e assorbe l'imprecisione del detector.
FACE_BOX_DILATE_FRAC = 0.25
# Estensione "corpo" sotto il volto (personaggi in piedi): larghezza e altezza
# del box corpo in multipli del box volto. Evita oggetti su busto/braccia,
# non solo sulla faccia.
FACE_BODY_WIDTH_FACTOR = 1.4
FACE_BODY_HEIGHT_FACTOR = 3.0


def detect_face_boxes(rgb: np.ndarray, base_path: Path) -> list[tuple[float, float, float, float]]:
    """Rileva i volti nel BG. Ritorna box (x0, y0, x1, y1) in pixel BG.

    Prova YuNet se il modello e' presente su disco, altrimenti Haar cascade.
    Senza cv2 ritorna lista vuota. Mai solleva: qualunque errore degrada a [].
    """
    if not _HAS_CV2:
        return []
    h, w = rgb.shape[:2]
    long_side = max(h, w)
    scale = min(1.0, FACE_DETECT_MAX_SIDE / max(1, long_side))
    if scale < 1.0:
        det_w = max(1, int(round(w * scale)))
        det_h = max(1, int(round(h * scale)))
        small = cv2.resize(rgb, (det_w, det_h), interpolation=cv2.INTER_AREA)
    else:
        det_w, det_h = w, h
        small = rgb

    boxes = _detect_yunet(small, base_path)
    if boxes is None:
        boxes = _detect_haar(small)

    inv = 1.0 / scale
    out = []
    for (x0, y0, x1, y1) in boxes:
        out.append((float(x0) * inv, float(y0) * inv,
                    float(x1) * inv, float(y1) * inv))
    if out:
        log.info(f"[FACE_ZONES] rilevati {len(out)} volti sul BG {w}x{h}")
    return out


def _detect_yunet(rgb_small: np.ndarray, base_path: Path
                  ) -> list[tuple[float, float, float, float]] | None:
    """Detection via YuNet. None = YuNet non disponibile (usa fallback Haar)."""
    if not hasattr(cv2, "FaceDetectorYN"):
        return None
    try:
        from editor.tools.scatter_models import yunet_path
        model_p = yunet_path(base_path)
        if not model_p.exists():
            return None
        h, w = rgb_small.shape[:2]
        det = cv2.FaceDetectorYN.create(
            str(model_p), "", (w, h),
            FACE_SCORE_THRESHOLD, FACE_NMS_THRESHOLD, FACE_TOP_K)
        # YuNet lavora in BGR
        bgr = cv2.cvtColor(rgb_small, cv2.COLOR_RGB2BGR)
        _, faces = det.detect(bgr)
        out: list[tuple[float, float, float, float]] = []
        if faces is not None:
            for f in faces:
                x, y, fw, fh = float(f[0]), float(f[1]), float(f[2]), float(f[3])
                if fw > 1 and fh > 1:
                    out.append((x, y, x + fw, y + fh))
        log.debug(f"[FACE_ZONES] YuNet: {len(out)} volti")
        return out
    except Exception as e:
        log.warning(f"[FACE_ZONES] YuNet fallito ({e}), fallback Haar")
        return None


def _detect_haar(rgb_small: np.ndarray) -> list[tuple[float, float, float, float]]:
    """Fallback Haar cascade (frontal + profile), inclusi in opencv-python."""
    try:
        gray = cv2.cvtColor(rgb_small, cv2.COLOR_RGB2GRAY)
        h, w = gray.shape[:2]
        min_side = max(16, max(h, w) // HAAR_MIN_SIZE_DIVISOR)
        out: list[tuple[float, float, float, float]] = []
        for casc_name in ("haarcascade_frontalface_default.xml",
                          "haarcascade_profileface.xml"):
            casc = cv2.CascadeClassifier(cv2.data.haarcascades + casc_name)
            if casc.empty():
                continue
            faces = casc.detectMultiScale(
                gray, scaleFactor=HAAR_SCALE_FACTOR,
                minNeighbors=HAAR_MIN_NEIGHBORS,
                minSize=(min_side, min_side))
            for (x, y, fw, fh) in faces:
                out.append((float(x), float(y), float(x + fw), float(y + fh)))
        log.debug(f"[FACE_ZONES] Haar: {len(out)} volti")
        return out
    except Exception as e:
        log.warning(f"[FACE_ZONES] Haar fallito ({e})")
        return []


def face_cell_mask(boxes: list[tuple[float, float, float, float]],
                   cell_w: int, cell_h: int, cell_px: int,
                   dilate_frac: float = FACE_BOX_DILATE_FRAC,
                   body_extend: bool = False) -> np.ndarray:
    """Rasterizza i box volto (pixel BG) sulla griglia celle dello scatter.

    Ogni box viene dilatato di dilate_frac per lato prima della
    rasterizzazione. Con body_extend=True aggiunge sotto ogni volto un box
    "corpo" (FACE_BODY_WIDTH_FACTOR x FACE_BODY_HEIGHT_FACTOR del volto):
    per personaggi in piedi evita oggetti anche su busto e braccia.
    Ritorna (cell_h, cell_w) bool, True = cella vietata.
    Funzione pura (testabile senza cv2/modelli).
    """
    mask = np.zeros((cell_h, cell_w), dtype=bool)

    def _mark(px0: float, py0: float, px1: float, py1: float) -> None:
        cx0 = max(0, int(px0 // cell_px))
        cy0 = max(0, int(py0 // cell_px))
        cx1 = min(cell_w, int(px1 // cell_px) + 1)
        cy1 = min(cell_h, int(py1 // cell_px) + 1)
        if cx1 > cx0 and cy1 > cy0:
            mask[cy0:cy1, cx0:cx1] = True

    for (x0, y0, x1, y1) in boxes:
        bw = x1 - x0
        bh = y1 - y0
        if bw <= 0 or bh <= 0:
            continue
        dx = bw * dilate_frac
        dy = bh * dilate_frac
        _mark(x0 - dx, y0 - dy, x1 + dx, y1 + dy)
        if body_extend:
            fcx = (x0 + x1) / 2.0
            half_bw = bw * FACE_BODY_WIDTH_FACTOR / 2.0
            _mark(fcx - half_bw, y1, fcx + half_bw,
                  y1 + bh * FACE_BODY_HEIGHT_FACTOR)
    return mask
