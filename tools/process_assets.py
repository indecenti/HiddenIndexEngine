import os
import sys
import argparse
import numpy as np
from PIL import Image

def process_assets(image_path, output_dir, object_names, style="real"):
    if not os.path.exists(image_path):
        print(f"Errore: File non trovato {image_path}")
        return

    img = Image.open(image_path).convert("RGBA")
    data = np.array(img)
    
    # Estraiamo i canali
    r = data[:,:,0].astype(float)
    g = data[:,:,1].astype(float)
    b = data[:,:,2].astype(float)
    a = data[:,:,3].astype(float)

    if style == "lineart":
        print("Modalità Line Art: Applicazione Chrominance Offset su sfondo #788088...")
        # Identifica lo sfondo sfruttando il fatto che il Blu (136) è maggiore del Rosso (120)
        # In un oggetto B/N puro o grigio antialiasing, R, G e B sono quasi identici.
        is_bg = (b > r + 5) & (abs(g - 128) < 50)
        
        # Le linee sono scure (media canali bassa)
        is_dark_line = (r + g + b) / 3 < 128
        
        # Applica trasparenza allo sfondo rilevato
        data[:,:,3][is_bg] = 0
        
        # Forza il nero puro sulle linee (dove non è sfondo)
        mask_line = ~is_bg & is_dark_line
        data[mask_line, 0] = 0
        data[mask_line, 1] = 0
        data[mask_line, 2] = 0
        data[mask_line, 3] = 255

        # Forza il bianco puro sui riempimenti (dove non è sfondo e non è linea)
        mask_fill = ~is_bg & ~is_dark_line
        data[mask_fill, 0] = 255
        data[mask_fill, 1] = 255
        data[mask_fill, 2] = 255
        data[mask_fill, 3] = 255
    elif style == "cartoon":
        print("Modalità Cartoon: Applicazione Chroma Destroyer su sfondo verde...")
        # Alpha removal ultra-aggressiva con erosione
        green_score = g - (r * 0.55 + b * 0.45)
        
        # 1. Rimozione Alpha Massiccia
        new_alpha = np.clip(255 - (green_score * 5.0), 0, 255)
        
        # 2. Erosione Bordi (Shift-based dilation)
        strong_green = green_score > 5
        dilated = strong_green.copy()
        dilated[1:, :] |= strong_green[:-1, :]
        dilated[:-1, :] |= strong_green[1:, :]
        dilated[:, 1:] |= strong_green[:, :-1]
        dilated[:, :-1] |= strong_green[:, 1:]
        new_alpha[dilated] = np.clip(new_alpha[dilated] - 50, 0, 255)
        
        # 3. Spill Suppression Totale
        spill_mask = green_score > 2
        data[spill_mask, 1] = np.minimum(data[spill_mask, 1], (np.minimum(r[spill_mask], b[spill_mask]) + 4)).astype(np.uint8)
        data[:,:,3] = new_alpha.astype(np.uint8)
    else:
        # Logica originale (Chroma Key o Bianco) migliorata
        corners = [data[0,0], data[0,-1], data[-1,0], data[-1,-1]]
        avg_corner = np.mean(corners, axis=0)
        is_green = avg_corner[1] > (avg_corner[0] + avg_corner[2]) / 1.5
        
        if is_green:
            print("Sfondo verde rilevato. Applicazione Chroma Destroyer...")
            green_score = g - (r * 0.5 + b * 0.5)
            # Rimozione Alpha e Erosione semplificata
            new_alpha = np.clip(255 - (green_score * 4.5), 0, 255)
            
            # Erosione
            strong_green = green_score > 10
            dilated = strong_green.copy()
            dilated[1:, :] |= strong_green[:-1, :]
            dilated[:-1, :] |= strong_green[1:, :]
            new_alpha[dilated] = np.clip(new_alpha[dilated] - 40, 0, 255)
            
            # Neutralizzazione alone verde
            spill_mask = green_score > 5
            data[spill_mask, 1] = np.minimum(data[spill_mask, 1], (np.minimum(r[spill_mask], b[spill_mask]) + 8)).astype(np.uint8)
            data[:,:,3] = new_alpha.astype(np.uint8)
        else:
            print("Sfondo chiaro rilevato. Applicazione rimozione bianco...")
            white_threshold = 240
            is_white = (r > white_threshold) & (g > white_threshold) & (b > white_threshold)
            data[:,:,3][is_white] = 0
    
    final_full_img = Image.fromarray(data)
    
    w, h = final_full_img.size
    
    # Rileva griglia dinamica (3x3, 4x4, ecc) in base al numero di nomi
    import math
    n_items = len(object_names)
    grid_size = int(math.sqrt(n_items))
    if grid_size * grid_size < n_items:
        grid_size += 1
        
    cell_w, cell_h = w // grid_size, h // grid_size
    
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        
    print(f"Processando {image_path} (Griglia {grid_size}x{grid_size})...")
    for i in range(grid_size):
        for j in range(grid_size):
            idx = i * grid_size + j
            if idx >= n_items:
                break
                
            left = j * cell_w
            top = i * cell_h
            right = left + cell_w
            bottom = top + cell_h
            
            cell = final_full_img.crop((left, top, right, bottom))
            
            bbox = cell.getbbox()
            if bbox:
                final_obj = cell.crop(bbox)
                save_name = object_names[idx].strip()
                if not save_name.endswith(".png"):
                    save_name += ".png"
                save_path = os.path.join(output_dir, save_name)
                final_obj.save(save_path, "PNG")
                print(f"  -> Salvato: {save_name}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Processa master sheets di oggetti (3x3).")
    parser.add_argument("image", help="Path della master sheet")
    parser.add_argument("output", help="Directory di destinazione")
    parser.add_argument("names", help="Nomi degli oggetti separati da virgola")
    parser.add_argument("--style", choices=["real", "lineart", "cartoon"], default="real", help="Stile degli oggetti")
    
    args = parser.parse_args()
    
    names = args.names.split(",")
    process_assets(args.image, args.output, names, style=args.style)

