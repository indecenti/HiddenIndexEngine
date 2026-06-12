import rembg
from PIL import Image
import io

img_path = r"g:\HIE git\engine\assets\objects_cartoon\ca_tuba_brass.png"
# This image already had background removed by OpenCV, maybe I should load from the original grid instead
img = Image.open(r"C:\Users\indecenti\.gemini\antigravity\brain\54e1b99a-4397-4fea-b7bb-124218366c1c\weird_cartoon_objects_grid_5_1781215765715.png")

# Crop the first cell
w, h = img.size
cell_img = img.crop((0, 0, w//4, h//4))

# Remove background perfectly
out = rembg.remove(cell_img)
out.save("scratch/test_tuba_rembg.png")
print("Rembg test done!")
