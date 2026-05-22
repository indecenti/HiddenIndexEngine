"""Render offscreen del menu per ogni tema -> contact sheet (verifica visiva)."""
import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import sys
from pathlib import Path
import pygame

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from engine.scaling_manager import ScalingManager
from engine.menu_system import MenuSystem
from engine.menu_theme import ThemeManager

W, H = 1280, 720
THEMES = ["default", "kids", "horror", "mystery", "cyber_neon", "android_std"]


class FakeLang:
    current_language = "en"
    def get(self, k, d=None):
        labels = {
            "btn_play": "PLAY", "btn_settings": "SETTINGS", "btn_quit": "QUIT",
            "label_music_volume": "Music", "label_sfx_volume": "SFX",
            "label_language": "Language", "label_resolution": "Resolution",
            "label_fullscreen": "Fullscreen", "menu_title_settings": "SETTINGS",
        }
        return labels.get(k, d if d is not None else k.replace("btn_", "").upper())
    def __call__(self, k, d=None):
        return d


def fake_bg(theme):
    surf = pygame.Surface((W, H))
    c = theme.color3("background_overlay")
    # gradiente semplice per simulare lo sfondo di gioco
    for y in range(0, H, 4):
        t = y / H
        col = (int(70 * (1 - t) + 20 * t), int(80 * (1 - t) + 25 * t), int(95 * (1 - t) + 35 * t))
        pygame.draw.rect(surf, col, (0, y, W, 4))
    ov = pygame.Surface((W, H), pygame.SRCALPHA)
    raw = theme._colors.get("background_overlay", [0, 0, 0, 200])
    a = raw[3] if len(raw) > 3 else 220
    ov.fill((raw[0], raw[1], raw[2], a))
    surf.blit(ov, (0, 0))
    return surf


def render(theme_id, state="main"):
    sm = ScalingManager()
    sm.update_screen_size(W, H)
    ms = MenuSystem(sm, FakeLang(), game_id="__preview__", save_manager=None)
    ms.theme = ThemeManager.get_theme(theme_id)
    ms.change_state(state)
    ms.update(0.5, -100, -100)  # avanza il tick animazioni, mouse fuori
    screen = pygame.Surface((W, H))
    screen.blit(fake_bg(ms.theme), (0, 0))
    ms.draw(screen)
    return screen


def main():
    pygame.init()
    pygame.display.set_mode((W, H))
    out = Path("theme_previews")
    out.mkdir(exist_ok=True)
    shots = []
    for tid in THEMES:
        s = render(tid, "main")
        p = out / f"{tid}_main.png"
        pygame.image.save(s, str(p))
        shots.append((tid, p))
        print("rendered", p)
    # settings shot per default (verifica slider + pillole)
    s = render("default", "settings")
    pygame.image.save(s, str(out / "default_settings.png"))
    shots.append(("default_settings", out / "default_settings.png"))

    # contact sheet
    from PIL import Image, ImageDraw, ImageFont
    cols = 2
    tw, th = W // 2, H // 2
    rows = (len(shots) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * tw, rows * th), (15, 15, 18))
    dr = ImageDraw.Draw(sheet)
    for i, (tid, p) in enumerate(shots):
        im = Image.open(p).resize((tw, th))
        x = (i % cols) * tw
        y = (i // cols) * th
        sheet.paste(im, (x, y))
        dr.rectangle([x, y, x + tw - 1, y + th - 1], outline=(80, 80, 90))
        dr.text((x + 8, y + 6), tid, fill=(255, 255, 0))
    sheet.save("theme_contact_sheet.png")
    print("contact sheet -> theme_contact_sheet.png")


if __name__ == "__main__":
    main()
