# Fixing Rendering Anomalies (Display Scaling on Windows)

## The problem ("black borders on the right and at the bottom")
When changing resolution (e.g. from 1280x720 to 1920x1080) in windowed mode on Windows, `pygame.display.set_mode` updated the internal rendering logic of the _Surface_ but systematically failed to make the OS pick up the new physical window bounds.
As a result, the new, larger resolution was compressed or clipped inside the old static window, producing an ugly partial letterbox (the "black borders") because the canvas cut the raster off-axis.

Three technical causes contribute to this:
1. The forced `os.environ['SDL_VIDEO_CENTERED'] = '1'`.
2. The absence of `pygame.SCALED` or `pygame.RESIZABLE` among the `set_mode` `flags` (both deliberately avoided for architectural reasons of the `HiddenIndexEngine` framework).
3. Wrong DPI (dots per inch) context detection by the hardware backend on Windows.

## Architectural solution
To solve the problem without hurting performance or resorting to destructive refactoring, the video context is torn down and re-initialized right before setting the new display.
Since Pygame 2, resources loaded into native memory (fonts, `.convert_alpha()` pre-computations) persist even after detaching from the GPU, so this practice is fast, smooth and robust against application crashes.

```python
# Procedure in engine/core.py -> _apply_display_settings(self, w, h, fullscreen)

# 1. Hard shutdown, detach the viewport from the OS
pygame.display.quit()

# 2. Re-initialize the SDL display driver
pygame.display.init()

# 3. Re-register the centering hook (it must be set again after init)
os.environ['SDL_VIDEO_CENTERED'] = '1'
pygame.display.set_caption("Hidden Engine")

# 4. Final atomic set_mode
self.screen = pygame.display.set_mode((w, h), flags, vsync=1)
```

## Technical benefits
* Windows is forced into a guaranteed topological redraw of the window (`WM_SIZE` and `WM_NCCALCSIZE` are reliably invoked on win32).
* Fully compatible with and agnostic to future updates of `ScalingManager` or full-screen conversions.
* Prevents the ghosting memory leaks that SDL usually shows on staggered display changes.
