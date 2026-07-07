"""
editor/mixins/img_editor_logic.py

Logica avanzata di elaborazione immagini per ImgEditorMixin.
Utilizza NumPy e SciPy per operazioni ad alte prestazioni.
"""

import numpy as np
import pygame
import logging
from scipy import ndimage

# Filtri colore: parametri utente in -100..+100 (0 = nessun effetto)
FILTER_VAL_MIN = -100
FILTER_VAL_MAX = 100
BRIGHTNESS_UNIT = 2.55           # Mappa -100..+100 su -255..+255
CONTRAST_UNIT = 2.55             # Mappa -100..+100 su -255..+255
CONTRAST_PIVOT = 128.0           # Punto fisso della curva di contrasto
CONTRAST_MAGIC = 259.0           # Costante della formula classica a 8 bit
LUMA_WEIGHTS = (0.299, 0.587, 0.114)  # Pesi ITU-R BT.601 per la luminanza

# Contorno: soglia alpha oltre cui un pixel appartiene alla silhouette
OUTLINE_ALPHA_THRESHOLD = 10

# Ridimensionamento numerico: limiti hard su entrambi i lati
RESIZE_MIN_PX = 8
RESIZE_MAX_PX = 4096


def apply_color_adjust(
    rgb: np.ndarray, brightness: float, contrast: float, saturation: float
) -> np.ndarray:
    """
    Regola luminosita', contrasto e saturazione di un array RGB.

    Il canale alpha non viene passato e quindi non viene mai toccato.
    Ordine di applicazione: luminosita' -> contrasto -> saturazione.

    Args:
        rgb: Array shape (..., 3), qualsiasi dtype numerico (tipicamente uint8).
        brightness: -100..+100; +100 porta tutto a bianco, -100 a nero.
        contrast: -100..+100; -100 appiattisce tutto sul grigio 128.
        saturation: -100..+100; -100 desatura completamente (scala di grigi).

    Returns:
        Nuovo array uint8 della stessa shape, clampato a 0..255.
    """
    arr = rgb.astype(np.float32)
    if brightness:
        arr += float(brightness) * BRIGHTNESS_UNIT
    if contrast:
        c = float(contrast) * CONTRAST_UNIT
        factor = (CONTRAST_MAGIC * (c + 255.0)) / (255.0 * (CONTRAST_MAGIC - c))
        arr = (arr - CONTRAST_PIVOT) * factor + CONTRAST_PIVOT
    if saturation:
        sat_factor = 1.0 + float(saturation) / 100.0
        luma = (arr[..., 0] * LUMA_WEIGHTS[0]
                + arr[..., 1] * LUMA_WEIGHTS[1]
                + arr[..., 2] * LUMA_WEIGHTS[2])[..., np.newaxis]
        arr = luma + (arr - luma) * sat_factor
    return np.clip(arr, 0.0, 255.0).astype(np.uint8)


def apply_color_adjust_surface(
    surf: pygame.Surface, brightness: float, contrast: float, saturation: float
) -> None:
    """
    Applica apply_color_adjust ai soli canali RGB della superficie, in-place.
    Il canale alpha resta intatto per costruzione.
    """
    rgb = pygame.surfarray.pixels3d(surf)
    rgb[:] = apply_color_adjust(rgb, brightness, contrast, saturation)
    del rgb  # Sblocca la superficie


def _dilate_once(mask: np.ndarray) -> np.ndarray:
    """Una passata di dilatazione 8-connessa senza wrap-around (fallback numpy)."""
    out = mask.copy()
    out[1:, :] |= mask[:-1, :]
    out[:-1, :] |= mask[1:, :]
    out[:, 1:] |= mask[:, :-1]
    out[:, :-1] |= mask[:, 1:]
    out[1:, 1:] |= mask[:-1, :-1]
    out[1:, :-1] |= mask[:-1, 1:]
    out[:-1, 1:] |= mask[1:, :-1]
    out[:-1, :-1] |= mask[1:, 1:]
    return out


def dilate_mask(mask: np.ndarray, thickness: int, use_scipy: bool = True) -> np.ndarray:
    """
    Dilata una maschera booleana di thickness pixel (kernel 3x3 pieno).

    Usa scipy.ndimage.binary_dilation se disponibile; altrimenti fallback
    numpy con shift nelle 8 direzioni ripetuto thickness volte (equivalente).

    Args:
        mask: Maschera booleana 2D.
        thickness: Numero di iterazioni di dilatazione (>= 1 per avere effetto).
        use_scipy: Se False forza il fallback numpy (utile nei test).
    """
    base = mask.astype(bool)
    if thickness <= 0:
        return base.copy()
    if use_scipy:
        try:
            from scipy.ndimage import binary_dilation
            kernel = np.ones((3, 3), dtype=bool)
            return binary_dilation(base, structure=kernel, iterations=int(thickness))
        except ImportError:
            logging.info("[IMG_LOGIC] scipy non disponibile: fallback numpy per dilatazione")
    out = base.copy()
    for _ in range(int(thickness)):
        out = _dilate_once(out)
    return out


def outline_ring(
    alpha: np.ndarray,
    thickness: int,
    alpha_threshold: int = OUTLINE_ALPHA_THRESHOLD,
    use_scipy: bool = True,
) -> np.ndarray:
    """
    Maschera booleana dell'anello di contorno attorno alla silhouette alpha:
    dilatazione di thickness px meno la silhouette originale. Per costruzione
    non include mai pixel interni alla silhouette.

    Args:
        alpha: Canale alpha 2D (uint8 o numerico).
        thickness: Spessore dell'anello in pixel.
        alpha_threshold: Alpha oltre cui il pixel appartiene alla silhouette.
        use_scipy: Se False forza il fallback numpy della dilatazione.
    """
    solid = alpha > alpha_threshold
    if not solid.any():
        return np.zeros_like(solid)
    return dilate_mask(solid, thickness, use_scipy=use_scipy) & ~solid


def aspect_resize_dims(
    cur_w: int,
    cur_h: int,
    target_w: int | None = None,
    target_h: int | None = None,
) -> tuple[int, int]:
    """
    Dimensioni finali per un resize che mantiene l'aspect ratio.

    Esattamente uno tra target_w e target_h deve essere valorizzato; l'altro
    lato viene derivato dal rapporto corrente. Entrambi i lati risultanti sono
    clampati a RESIZE_MIN_PX..RESIZE_MAX_PX (il clamp puo' alterare il
    rapporto nei casi estremi: i limiti hard hanno precedenza).

    Returns:
        Tupla (nuova_larghezza, nuova_altezza) in pixel.
    """
    if (target_w is None) == (target_h is None):
        raise ValueError("Specificare esattamente uno tra target_w e target_h")
    if cur_w <= 0 or cur_h <= 0:
        raise ValueError("Dimensioni correnti non valide")
    if target_w is not None:
        new_w = max(RESIZE_MIN_PX, min(RESIZE_MAX_PX, int(target_w)))
        new_h = int(round(new_w * cur_h / cur_w))
    else:
        new_h = max(RESIZE_MIN_PX, min(RESIZE_MAX_PX, int(target_h)))
        new_w = int(round(new_h * cur_w / cur_h))
    new_w = max(RESIZE_MIN_PX, min(RESIZE_MAX_PX, new_w))
    new_h = max(RESIZE_MIN_PX, min(RESIZE_MAX_PX, new_h))
    return new_w, new_h


def brush_power_map(shape: str, radius: int, hardness: float) -> np.ndarray:
    """
    Mappa (size x size) della potenza del pennello: 1.0 entro il bordo duro,
    decrescente linearmente fino al raggio. Condivisa da gomma e ripristino
    cosi' i due strumenti hanno esattamente lo stesso profilo.

    Args:
        shape: "round" o "square".
        radius: Raggio del pennello in pixel (>= 1).
        hardness: Frazione 0..1 del raggio a piena potenza.
    """
    size = radius * 2 + 1
    center = float(radius)
    y_arr, x_arr = np.ogrid[0:size, 0:size]
    if shape == "round":
        dist_arr = np.sqrt((x_arr - center) ** 2 + (y_arr - center) ** 2)
    else:
        dist_arr = np.maximum(np.abs(x_arr - center), np.abs(y_arr - center))
    hard_r = radius * hardness
    power = np.zeros((size, size), dtype=float)
    power[dist_arr <= hard_r] = 1.0
    gradient = (dist_arr > hard_r) & (dist_arr <= radius)
    if radius > hard_r:
        power[gradient] = 1.0 - (dist_arr[gradient] - hard_r) / (radius - hard_r)
    return power


def restore_stamp(
    dst: pygame.Surface,
    src: pygame.Surface,
    top_left: tuple[int, int],
    strength: np.ndarray,
) -> None:
    """
    Ricopia su dst i pixel RGBA di src pesati da strength (0..1, quadrata),
    con clipping ai bordi. dst e src devono avere le stesse dimensioni.

    Args:
        dst: Superficie di lavoro (modificata in-place).
        src: Superficie originale da cui ricopiare.
        top_left: Angolo alto-sinistra dello stamp in coordinate immagine.
        strength: Mappa di forza del pennello (brush_power_map * opacita').
    """
    w, h = dst.get_size()
    size = strength.shape[0]
    bx, by = top_left
    x0, y0 = max(0, bx), max(0, by)
    x1, y1 = min(w, bx + size), min(h, by + size)
    if x0 >= x1 or y0 >= y1:
        return
    s = strength[x0 - bx:x1 - bx, y0 - by:y1 - by]
    if not np.any(s):
        return
    s3 = s[:, :, np.newaxis]
    dst_rgb = pygame.surfarray.pixels3d(dst)
    src_rgb = pygame.surfarray.pixels3d(src)
    cur = dst_rgb[x0:x1, y0:y1].astype(float)
    org = src_rgb[x0:x1, y0:y1].astype(float)
    dst_rgb[x0:x1, y0:y1] = np.clip(cur * (1.0 - s3) + org * s3, 0, 255).astype(np.uint8)
    del dst_rgb, src_rgb
    dst_a = pygame.surfarray.pixels_alpha(dst)
    src_a = pygame.surfarray.pixels_alpha(src)
    a_cur = dst_a[x0:x1, y0:y1].astype(float)
    a_org = src_a[x0:x1, y0:y1].astype(float)
    dst_a[x0:x1, y0:y1] = np.clip(a_cur * (1.0 - s) + a_org * s, 0, 255).astype(np.uint8)
    del dst_a, src_a


def evolved_trim(surf: pygame.Surface, noise_threshold: int = 2) -> pygame.Surface:
    """
    Esegue un trim intelligente ignorando solo il rumore minuscolo.
    
    Args:
        surf: La superficie da trimmare.
        noise_threshold: Dimensione massima (in pixel) dei cluster da ignorare.
    """
    w, h = surf.get_size()
    alpha = pygame.surfarray.array_alpha(surf)
    
    # Maschera binaria dei pixel non trasparenti (alpha > 5 per essere più sensibili)
    binary = (alpha > 5).astype(int)
    
    # Etichettatura dei componenti connessi
    labeled, num_features = ndimage.label(binary)
    
    if num_features == 0:
        return surf
        
    # Calcolo dimensioni componenti
    component_sizes = ndimage.sum(binary, labeled, range(num_features + 1))
    
    # TROVIAMO IL COMPONENTE PIÙ GRANDE (L'oggetto principale)
    # Lo 0 è lo sfondo, lo saltiamo
    if num_features > 0:
        main_label = np.argmax(component_sizes[1:]) + 1
    else:
        return surf

    # Maschera per componenti "validi":
    # 1. Devono essere più grandi della soglia di rumore
    # 2. O devono essere il componente principale (protezione)
    mask_valid = (component_sizes > noise_threshold)
    mask_valid[main_label] = True # Protezione assoluta dell'oggetto principale
    
    # Il componente 0 è lo sfondo, lo ignoriamo sempre
    mask_valid[0] = False
    
    # Creiamo una maschera pulita
    clean_mask = mask_valid[labeled]
    
    if not np.any(clean_mask):
        return surf
        
    # Calcolo bounding box della maschera pulita.
    # pygame.surfarray usa shape (W, H), quindi argwhere ritorna coppie (x, y).
    coords = np.argwhere(clean_mask)
    x0, y0 = coords.min(axis=0)
    x1, y1 = coords.max(axis=0) + 1  # +1 perché slice è esclusivo

    # Ritaglio
    new_w = int(x1 - x0)
    new_h = int(y1 - y0)

    # Puliamo anche l'immagine originale dai segni ignorati (li trattiamo come trasparenti)
    arr_alpha = pygame.surfarray.pixels_alpha(surf)
    arr_alpha[~clean_mask] = 0
    del arr_alpha  # Sblocca superficie

    final_surf = pygame.Surface((new_w, new_h), pygame.SRCALPHA)
    final_surf.blit(surf, (0, 0), (int(x0), int(y0), new_w, new_h))
    
    logging.info(f"[IMG_LOGIC] Trim evoluto: {w}x{h} -> {new_w}x{new_h} (Rimosse {num_features - np.sum(mask_valid)} impurità)")
    return final_surf
