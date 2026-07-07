"""
editor/mixins/img_editor_logic.py

Logica avanzata di elaborazione immagini per ImgEditorMixin.
Utilizza NumPy e SciPy per operazioni ad alte prestazioni.
"""

import numpy as np
import pygame
import logging
from scipy import ndimage


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
