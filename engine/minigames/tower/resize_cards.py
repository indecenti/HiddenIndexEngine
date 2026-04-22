import os
from PIL import Image
from pathlib import Path

def resize_to_minimum():
    # Lo script opera nella cartella in cui viene eseguito
    folder = Path(".")
    images_paths = list(folder.glob("card_*.png"))
    
    if not images_paths:
        print("Nessuna immagine trovata nella cartella.")
        return

    # 1. Trova le dimensioni minime tra tutte le immagini
    min_w = float('inf')
    min_h = float('inf')
    
    for p in images_paths:
        with Image.open(p) as img:
            w, h = img.size
            if w < min_w: min_w = w
            if h < min_h: min_h = h
            
    target_size = (int(min_w), int(min_h))
    print(f"Dimensioni target individuate (minime): {target_size[0]}x{target_size[1]}")

    # 2. Ridimensiona tutte le immagini alle dimensioni target
    for p in images_paths:
        with Image.open(p) as img:
            if img.size != target_size:
                resized = img.resize(target_size, Image.Resampling.LANCZOS)
                resized.save(p)
                print(f"  Ridimensionata: {p.name}")
            else:
                print(f"  Invariata (già minima): {p.name}")

if __name__ == "__main__":
    try:
        resize_to_minimum()
        print("\nOperazione completata con successo!")
    except Exception as e:
        print(f"Errore durante l'esecuzione: {e}")
