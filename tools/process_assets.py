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
    else:
        # Logica originale (Chroma Key o Bianco)
        # Rileva se lo sfondo è prevalentemente verde o bianco
        corners = [data[0,0], data[0,-1], data[-1,0], data[-1,-1]]
        avg_corner = np.mean(corners, axis=0)
        
        is_green = avg_corner[1] > (avg_corner[0] + avg_corner[2]) / 1.5
        
        if is_green:
            print("Sfondo verde rilevato. Applicazione Chroma Key...")
            green_score = g - (r + b) / 2
            new_alpha = np.clip(255 - (green_score * 1.5), 0, 255).astype(np.uint8)
            
            spill_condition = (g > r) & (g > b)
            data[:,:,1][spill_condition] = np.maximum(r[spill_condition], b[spill_condition])
            data[:,:,3] = new_alpha
        else:
            print("Sfondo chiaro rilevato. Applicazione rimozione bianco...")
            white_threshold = 240
            is_white = (r > white_threshold) & (g > white_threshold) & (b > white_threshold)
            data[:,:,3][is_white] = 0
    
    final_full_img = Image.fromarray(data)
    
    w, h = final_full_img.size
    cell_w, cell_h = w // 3, h // 3
    
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        
    print(f"Processando {image_path}...")
    for i in range(3):
        for j in range(3):
            idx = i * 3 + j
            if idx >= len(object_names):
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
    parser.add_argument("--style", choices=["real", "lineart"], default="real", help="Stile degli oggetti")
    
    args = parser.parse_args()
    
    names = args.names.split(",")
    process_assets(args.image, args.output, names, style=args.style)

