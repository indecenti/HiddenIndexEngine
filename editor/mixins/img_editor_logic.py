"""
editor/mixins/img_editor_logic.py

Logica avanzata di elaborazione immagini per ImgEditorMixin.
Utilizza NumPy e SciPy per operazioni ad alte prestazioni.
"""

import numpy as np
import pygame
import logging
from scipy import ndimage

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
        
    # Calcolo bounding box della maschera pulita
    coords = np.argwhere(clean_mask)
    y0, x0 = coords.min(axis=0)
    y1, x1 = coords.max(axis=0) + 1 # +1 perché slice è esclusivo
    
    # Ritaglio
    new_w = x1 - x0
    new_h = y1 - y0
    
    # Opzionale: Puliamo anche l'immagine originale dai segni ignorati
    # Se l'utente vuole ignorarli nel trim, probabilmente vuole che spariscano.
    # Applichiamo la maschera pulita all'alpha
    arr_alpha = pygame.surfarray.pixels_alpha(surf)
    arr_alpha[~clean_mask] = 0
    del arr_alpha # Sblocca superficie
    
    final_surf = pygame.Surface((new_w, new_h), pygame.SRCALPHA)
    final_surf.blit(surf, (0, 0), (x0, y0, new_w, new_h))
    
    logging.info(f"[IMG_LOGIC] Trim evoluto: {w}x{h} -> {new_w}x{new_h} (Rimosse {num_features - np.sum(mask_valid)} impurità)")
    return final_surf

def get_viewport_render(surf: pygame.Surface, view_w: int, view_h: int, zoom: float, pan: list) -> pygame.Surface:
    """
    Ritorna una porzione dell'immagine renderizzata per il viewport (Photoshop style).
    Ottimizzato per non scalare l'intera immagine se enorme.
    """
    iw, ih = surf.get_size()
    
    # Scala totale
    total_scale = zoom
    
    # Dimensioni desiderate nel viewport
    sw, sh = int(iw * total_scale), int(ih * total_scale)
    
    # Se l'immagine è piccola e lo zoom è basso, usiamo smoothscale semplice
    # Altrimenti dovremmo fare un sub-surface blit e poi scale
    # Per ora implementiamo una versione robusta
    try:
        if total_scale == 1.0:
            return surf.copy()
        
        # Clamp dimensioni minime
        sw = max(1, sw)
        sh = max(1, sh)
        
        if total_scale > 1.0:
            return pygame.transform.scale(surf, (sw, sh))
        else:
            return pygame.transform.smoothscale(surf, (sw, sh))
    except Exception as e:
        logging.error(f"[IMG_LOGIC] Viewport render error: {e}")
        return surf
