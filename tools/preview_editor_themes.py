"""Render offscreen del dialog 'Impostazioni Progetto' per verificare le card tema."""
import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import sys
from pathlib import Path
import pygame

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from engine.utils import get_base_path
from editor.editor_base import LevelEditor

W, H = 1600, 1000


def main():
    ed = LevelEditor(get_base_path())
    ed.screen = pygame.display.set_mode((W, H))
    ed.screen.fill((18, 20, 28))

    # Stato minimo per il dialog 'game'
    ed._gs_edit_mode = "game"
    ed._gs_edit_active_field = None
    ed._gs_edit_lang_bufs = {l: ("Demo " + l.upper()) for l in ed.LANGS}
    ed._gs_edit_cursors = {l: 0 for l in ed.LANGS}
    ed._gs_edit_all_selected = False
    ed._gs_edit_category = "desktop"
    ed._gs_edit_cat_dropdown = False
    ed._gs_edit_theme_id = "mystery"
    ed._gs_edit_magnifier = True
    ed.gs_games = ["DemoGame"]
    ed.gs_sel_game = 0
    ed._img_cache = {}

    ed._r_gs_edit_dialog(W, H)
    out = Path("editor_theme_panel.png")
    pygame.image.save(ed.screen, str(out))
    print("saved", out.resolve())


if __name__ == "__main__":
    main()
