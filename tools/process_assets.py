import os
import sys
import numpy as np
from PIL import Image

def process_assets(image_path, output_dir, object_names):
    if not os.path.exists(image_path):
        print(f"Errore: File non trovato {image_path}")
        return

    img = Image.open(image_path).convert("RGBA")
    data = np.array(img)
    
    r, g, b = data[:,:,0].astype(float), data[:,:,1].astype(float), data[:,:,2].astype(float)
    
    # Rileva se lo sfondo è prevalentemente verde o bianco
    # Calcoliamo una media dei pixel agli angoli
    corners = [data[0,0], data[0,-1], data[-1,0], data[-1,-1]]
    avg_corner = np.mean(corners, axis=0)
    
    is_green = avg_corner[1] > (avg_corner[0] + avg_corner[2]) / 1.5
    
    if is_green:
        # Logica Chroma Key verde originale con spill suppression
        green_score = g - (r + b) / 2
        new_alpha = np.clip(255 - (green_score * 1.5), 0, 255).astype(np.uint8)
        
        spill_condition = (g > r) & (g > b)
        data[:,:,1][spill_condition] = np.maximum(r[spill_condition], b[spill_condition])
        data[:,:,3] = new_alpha
    else:
        # Logica per sfondo bianco (o chiaro)
        # Se i pixel sono molto vicini al bianco, rendili trasparenti
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
                save_path = os.path.join(output_dir, f"{object_names[idx]}.png")
                final_obj.save(save_path, "PNG")
                print(f"  -> Salvato: {object_names[idx]}.png")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Uso: python process_assets.py <path_master_sheet> <output_dir> [nomi_separati_da_virgola]")
    else:
        # Se i nomi non sono passati, usa una lista di default (backup)
        if len(sys.argv) > 3:
            names = sys.argv[3].split(",")
        else:
            # Lista di fallback se l'utente dimentica i nomi
            names = [f"asset_{i}" for i in range(9)]
            
        process_assets(sys.argv[1], sys.argv[2], names)
