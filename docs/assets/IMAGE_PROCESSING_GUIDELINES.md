# Image Processing Guidelines (Background Removal)

## The problem: OpenCV FloodFill and global ranges
The old approach used `cv2.inRange()` (which removed every white pixel, including eyes, teeth or reflections inside the objects) or a perimeter `FloodFill` (which protected the interiors but left the background intact inside closed "holes", such as the inside of a hula hoop or a nunchaku). Both classic threshold-based approaches proved inadequate for a **"perfectly clean job"**.

## The official solution: artificial intelligence (Rembg)
Since our environment has `rembg` (a module based on the U2-Net neural network), it has become the **only accepted standard** for removing the background from generated icons.

**Why Rembg?**
- It is a semantic matting algorithm: it **recognizes the subject** against the background.
- **Cleans inner backgrounds:** it perfectly removes the white from the "holes" and the closed empty spaces of the objects.
- **Protects inner colors:** it will NEVER erase reflections, teeth, or the white sclera of the eyes, because it knows they belong to the subject.
- The edge anti-aliasing produced by the alpha masks is of higher quality than any manual thresholding.

### Safe Python code example (Rembg)
For every generated grid or single asset, always use the following logic:

```python
import rembg
from PIL import Image

def process_asset_with_ai(image_path, out_path):
    # Load the original image (even with white borders, complex backgrounds or inner holes)
    img = Image.open(image_path)

    # Remove the background with AI
    out = rembg.remove(img)

    # Save the clean PNG
    out.save(out_path)
```

### Golden rules for future scripts:
1. **NO MORE OPENCV FOR TRANSPARENCY:** stop trying to guess the floodfill tolerance. Drop `cv2.floodFill` and `cv2.inRange` for cutouts.
2. **CROP FIRST, REMBG AFTER:** if the AI generated a grid (e.g. 4x4), first cut the single cells with `img.crop()`, then pass each cell to `rembg.remove()`. Passing the whole grid to Rembg would confuse the neural network about what the "main subject" is.
3. **SPEED:** the first run of `rembg` may take a few extra seconds to load the model weights. Subsequent runs are instant.
