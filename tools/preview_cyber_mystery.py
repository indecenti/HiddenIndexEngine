"""Verifica visiva approfondita di cyber_neon e mystery: main/settings con hover
attivo (glow + tooltip) e levels con sblocco simulato."""
import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
import sys
from pathlib import Path
import pygame

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from engine.scaling_manager import ScalingManager
from engine.menu_system import MenuSystem
from engine.menu_theme import ThemeManager, load_theme_for_game

W, H = 1280, 720


class FakeLang:
    current_language = "en"
    _m = {
        "btn_play": "PLAY", "btn_settings": "SETTINGS", "btn_quit": "QUIT",
        "btn_continue": "CONTINUE", "btn_new_game": "NEW GAME",
        "btn_resume": "RESUME", "btn_quit_to_main": "MAIN MENU",
        "menu_title_settings": "SETTINGS", "menu_title_levels": "SELECT LEVEL",
        "label_music_volume": "Music", "label_sfx_volume": "SFX",
        "label_language": "Language", "label_resolution": "Resolution",
        "label_fullscreen": "Fullscreen",
        "tip_play": "Start playing and choose a level",
        "tip_settings": "Audio, language and display settings",
        "tip_quit": "Quit the game", "tip_back": "Go back",
        "tip_language": "Change the game language",
        "tip_continue": "Resume your saved game",
        "tip_new_game": "Erase your progress and start over",
        "tip_resume": "Resume the current game",
        "tip_quit_to_main": "Return to the main menu",
        "tip_resolution": "Change the screen resolution",
        "tip_fullscreen": "Toggle fullscreen mode",
    }
    def get(self, k, d=None): return self._m.get(k, d if d is not None else k)
    def __call__(self, k, d=None): return self._m.get(k, d)


class FakeSave:
    def get_progress(self, k, d=None):
        if k == "unlocked_levels":
            return ["One"]
        return d
    def is_scene_unlocked(self, lvl, i): return True


def bg(theme):
    s = pygame.Surface((W, H))
    for y in range(0, H, 4):
        t = y / H
        s.fill((int(60*(1-t)+18*t), int(70*(1-t)+22*t), int(85*(1-t)+30*t)), (0, y, W, 4))
    raw = theme._colors.get("background_overlay", [0, 0, 0, 210])
    ov = pygame.Surface((W, H), pygame.SRCALPHA)
    ov.fill((raw[0], raw[1], raw[2], raw[3] if len(raw) > 3 else 220))
    s.blit(ov, (0, 0))
    return s


def render(theme_id, game_id, state, hover_idx=None):
    sm = ScalingManager(); sm.update_screen_size(W, H)
    ms = MenuSystem(sm, FakeLang(), game_id, save_manager=FakeSave())
    ms.theme = ThemeManager.get_theme(theme_id, game_id=game_id)
    ms.change_state(state, has_save=True, extra_data=("One" if state == "scenes" else None))
    screen = pygame.Surface((W, H)); screen.blit(bg(ms.theme), (0, 0))
    mx, my = -200, -200
    if hover_idx is not None and hover_idx < len(ms.buttons):
        mx, my = ms.buttons[hover_idx].ref_rect.center
    for _ in range(30):  # ramp hover + avanza animazioni
        ms.update(0.05, mx, my)
    ms.mouse_pos = (mx, my)
    ms.draw(screen)
    return screen


def main():
    pygame.init(); pygame.display.set_mode((W, H))
    out = Path("verify"); out.mkdir(exist_ok=True)
    jobs = [
        ("cyber_neon", "LineVenture", "main", 0),
        ("cyber_neon", "LineVenture", "settings", 1),
        ("mystery", "Malonno_Survivors", "main", 1),
        ("mystery", "Malonno_Survivors", "settings", 1),
        ("mystery", "Malonno_Survivors", "levels", 0),
        ("cyber_neon", "LineVenture", "pause", 1),
    ]
    shots = []
    for tid, gid, st, hi in jobs:
        s = render(tid, gid, st, hi)
        p = out / f"{tid}_{st}.png"; pygame.image.save(s, str(p)); shots.append((f"{tid} {st}", p))
        print("rendered", p)
    from PIL import Image, ImageDraw
    cols = 2; tw, th = W // 2, H // 2
    rows = (len(shots) + cols - 1) // cols
    sheet = Image.new("RGB", (cols*tw, rows*th), (12, 12, 15))
    dr = ImageDraw.Draw(sheet)
    for i, (lab, p) in enumerate(shots):
        im = Image.open(p).resize((tw, th)); x = (i % cols)*tw; y = (i//cols)*th
        sheet.paste(im, (x, y)); dr.rectangle([x, y, x+tw-1, y+th-1], outline=(70, 70, 80))
        dr.text((x+8, y+6), lab, fill=(255, 255, 0))
    sheet.save("verify_cyber_mystery.png"); print("sheet -> verify_cyber_mystery.png")


if __name__ == "__main__":
    main()
