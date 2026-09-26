"""
tools/menu_audit.py

Visual audit harness for the game menus.

Boots the real EngineCore (not a mock MenuSystem) for one game, then walks every
menu page - main, confirm dialog, levels, every level's scenes, settings, pause,
results - for every theme and every requested resolution, and writes one PNG per
page plus a contact sheet per (theme, resolution).

The game's own background, levels, previews and strings are used, so what comes
out is what a player sees. Only the theme is swapped between passes.

Nothing is persisted: config.ini is read, then overridden in memory
(resolution, windowed), and no code path that writes config or saves is called.

Usage
-----
    python tools/menu_audit.py                                  # all themes, default sizes
    python tools/menu_audit.py --game Malonno_Survivors --lang de
    python tools/menu_audit.py --themes mystery kids --sizes 1280x720 2400x1080
    python tools/menu_audit.py --out scratch/menu_audit --real-display
    python tools/menu_audit.py --check      # also run tools/menu_layout_check rules

With --check every page is also verified against the layout rules (no cuts, no
overlaps, icons inside their buttons, readable text); the violations go to
<out>/layout_report.txt and the exit code is 1 when there is any.
"""
from __future__ import annotations

import argparse
import configparser
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DEFAULT_THEMES = ["default", "horror", "kids", "cyber_neon", "mystery", "android_std"]
# Reference 16:9, Android 20:9 landscape, desktop 4:3, 1440p.
DEFAULT_SIZES = ["1280x720", "2400x1080", "1024x768", "2560x1440"]
SETTLE_FRAMES = 40
FRAME_DT = 1 / 30
MOUSE_OUTSIDE = (-100, -100)
SHEET_TILE_W = 640
SHEET_COLS = 3
SHEET_LABEL_COLOR = (255, 230, 0)
SHEET_BG = (12, 12, 16)
RESULTS_TIMER_HOLD = 999.0
SAMPLE_WIN = {"score": 12450, "stars": 3, "time_elapsed": 183.0, "is_failed": False,
              "objects_found": 12, "total_objects": 12}
SAMPLE_FAIL = {"score": 0, "stars": 0, "time_elapsed": 300.0, "is_failed": True,
               "objects_found": 5, "total_objects": 12}


def _parse_size(text: str) -> tuple[int, int]:
    w, h = text.lower().split("x")
    return int(w), int(h)


def _read_config(size: tuple[int, int]) -> configparser.ConfigParser:
    from engine.utils import get_base_path, get_user_config_path
    config = configparser.ConfigParser()
    paths = [p for p in (get_base_path() / "config.ini", get_user_config_path()) if p.exists()]
    config.read(paths, encoding="utf-8")
    if not config.has_section("engine"):
        config.add_section("engine")
    # In-memory override only: the file on disk is never written.
    config.set("engine", "resolution_w", str(size[0]))
    config.set("engine", "resolution_h", str(size[1]))
    config.set("engine", "fullscreen", "0")
    return config


class MenuAudit:
    """Drives one EngineCore instance through every menu page."""

    def __init__(self, game_id: str, lang: str | None, size: tuple[int, int],
                 out_dir: Path, logger, check: bool = False) -> None:
        from engine.core import EngineCore
        self.logger = logger
        self.size = size
        self.out_dir = out_dir
        args = argparse.Namespace(game=game_id, fullscreen=False, minigame=None,
                                  lang=lang, scene=None)
        self.eng = EngineCore(game_id=game_id, config=_read_config(size), cli_args=args)
        self.ms = self.eng.menu_system
        self.check = check
        self.violations: list[str] = []

    def _frames(self, n: int = SETTLE_FRAMES) -> None:
        import pygame
        for _ in range(n):
            self.eng._update(FRAME_DT)
            self.ms.update(FRAME_DT, *MOUSE_OUTSIDE)
            self.eng._draw()
            pygame.event.pump()
            pygame.display.flip()

    def _shot(self, folder: Path, name: str, shots: list) -> None:
        import pygame
        self._frames()
        if self.check and self.eng.state != "RESULTS":
            from tools.menu_layout_check import check_frame
            self.ms.layout_probe = []
            self._frames(1)
            boxes, self.ms.layout_probe = self.ms.layout_probe, None
            sm = self.eng.scaling_manager
            for v in check_frame(boxes, self.eng.screen.get_size(), sm.scale):
                self.violations.append(f"{self.size[0]}x{self.size[1]} {folder.name} {name} {v}")
        path = folder / f"{name}.png"
        pygame.image.save(self.eng.screen, str(path))
        shots.append((name, path))

    def _apply_theme(self, theme_id: str) -> None:
        from engine.menu_skins import get_skin
        from engine.menu_theme import ThemeManager
        self.ms.theme = ThemeManager.get_theme(theme_id, game_id=self.eng.game_id)
        self.ms.skin = get_skin(self.ms.theme)
        self.eng.results_screen.set_theme(self.ms.theme)
        self.ms._settings_groups = []

    def run_theme(self, theme_id: str | None) -> list:
        from engine.core import EngineState
        label = theme_id or "game"
        folder = self.out_dir / f"{self.size[0]}x{self.size[1]}" / label
        folder.mkdir(parents=True, exist_ok=True)
        if theme_id:
            self._apply_theme(theme_id)
        shots: list = []
        eng, ms = self.eng, self.ms

        eng.state = EngineState.MENU
        ms.change_state("main", has_save=True)
        self._shot(folder, "01_main", shots)
        ms.change_state("confirm_new")
        self._shot(folder, "02_confirm_new", shots)
        ms.change_state("levels", has_save=True)
        self._shot(folder, "03_levels", shots)
        levels = [lv.get("id") if isinstance(lv, dict) else lv
                  for lv in eng.game_config.get("levels", [])]
        for i, level_id in enumerate(levels):
            ms.change_state("scenes", has_save=True, extra_data=level_id)
            self._shot(folder, f"04_scenes_{i:02d}", shots)
            if ms.max_scroll_x > 0:
                ms.target_scroll_x = ms.max_scroll_x
                self._shot(folder, f"04_scenes_{i:02d}_end", shots)
        ms.change_state("settings")
        self._shot(folder, "05_settings", shots)
        if ms.max_scroll_y > 0:
            ms.target_scroll_y = ms.max_scroll_y
            self._shot(folder, "05_settings_end", shots)
        eng.state = EngineState.PAUSE
        ms.change_state("pause", has_save=True)
        self._shot(folder, "06_pause", shots)
        eng.state = EngineState.RESULTS
        for name, data in (("07_results_win", SAMPLE_WIN), ("08_results_fail", SAMPLE_FAIL)):
            eng._results_timer = RESULTS_TIMER_HOLD
            eng.results_screen.show(scene_name="Albergo Lobby", **data)
            self._shot(folder, name, shots)
        eng.state = EngineState.MENU
        _contact_sheet(shots, folder.parent / f"_sheet_{label}.png")
        self.logger.info("audit %s %dx%d: %d pages", label, *self.size, len(shots))
        return shots


def _contact_sheet(shots: list, dest: Path) -> None:
    from PIL import Image, ImageDraw
    if not shots:
        return
    w, h = Image.open(shots[0][1]).size
    tw = SHEET_TILE_W
    th = int(round(tw * h / w))
    rows = (len(shots) + SHEET_COLS - 1) // SHEET_COLS
    sheet = Image.new("RGB", (SHEET_COLS * tw, rows * th), SHEET_BG)
    draw = ImageDraw.Draw(sheet)
    for i, (name, path) in enumerate(shots):
        x, y = (i % SHEET_COLS) * tw, (i // SHEET_COLS) * th
        sheet.paste(Image.open(path).convert("RGB").resize((tw, th)), (x, y))
        draw.text((x + 6, y + 4), name, fill=SHEET_LABEL_COLOR)
    sheet.save(dest)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[1])
    parser.add_argument("--game", default=None, help="game id (default: config.ini)")
    parser.add_argument("--lang", default=None, help="it, en, es, fr, de")
    parser.add_argument("--themes", nargs="*", default=DEFAULT_THEMES,
                        help="theme ids; pass 'game' to keep the game's own theme")
    parser.add_argument("--sizes", nargs="*", default=DEFAULT_SIZES)
    parser.add_argument("--out", default=str(ROOT / "scratch" / "menu_audit"))
    parser.add_argument("--check", action="store_true",
                        help="verify every page against tools/menu_layout_check")
    parser.add_argument("--real-display", action="store_true",
                        help="open a real window instead of the dummy SDL driver")
    opts = parser.parse_args()

    if not opts.real_display:
        os.environ["SDL_VIDEODRIVER"] = "dummy"
    os.environ["SDL_AUDIODRIVER"] = "dummy"
    os.chdir(ROOT)

    import pygame
    from engine.utils import get_logger, setup_logging
    setup_logging()
    logger = get_logger("menu_audit")

    game_id = opts.game or _read_config((1, 1)).get("engine", "default_game", fallback="")
    out_dir = Path(opts.out)
    violations: list[str] = []
    for size_text in opts.sizes:
        size = _parse_size(size_text)
        audit = MenuAudit(game_id, opts.lang, size, out_dir, logger, check=opts.check)
        for theme_id in opts.themes:
            audit.run_theme(None if theme_id == "game" else theme_id)
        violations.extend(audit.violations)
        pygame.display.quit()
    logger.info("menu audit written to %s", out_dir)
    if opts.check:
        report = out_dir / "layout_report.txt"
        report.write_text("".join(v + "\n" for v in violations), encoding="utf-8")
        logger.info("layout check: %d violations -> %s", len(violations), report)
        if violations:
            sys.exit(1)


if __name__ == "__main__":
    main()
