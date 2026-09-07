"""
editor/mixins/icon_modal.py

IconModalMixin — Gestione selezione e conversione icone di gioco.
"""

import shutil
import logging
from pathlib import Path
import pygame
from PIL import Image

from editor.constants import ACCENT, TXT_HI, TXT_DIM, OK_C
from editor.ui.draw import (
    _rect, _draw_text, _button, _in_rect, _draw_shape_icon, _scrollbar,
    _button_w, _text_wh,
)

logger = logging.getLogger("icon_modal")

# Geometry of the icon picker. It used to be written three times - render,
# click and wheel - and the wheel copy did not even try: it clamped the scroll
# with a hand-picked "3 rows are probably visible", so a longer icon list
# scrolled past its end or stopped short of it.
_ICON_DLG_W, _ICON_DLG_H = 900, 700
_ICON_COLS = 6
_ICON_GAP = 8
_ICON_CAPTION_H = 20   # room under the thumbnail for name and size


class IconModalMixin:
    """Mixin per la selezione professionale dell'icona del gioco."""

    def _icon_modal_init(self):
        self._icon_modal = False
        self._icon_list = []
        self._icon_scroll = 0
        self._icon_cache = {} # path -> surface (preview scaled)
        self._icon_dims = {}  # path -> (w, h)
        self._icon_context = "game_edit" # o "game_new"
        self._icon_del_confirm = None # Path dell'icona in attesa di conferma eliminazione

    def _icon_modal_open(self, context="game_edit"):
        self._icon_modal = True
        self._icon_context = context
        self._icon_scroll = 0

        icon_dir = self.base_path / "engine" / "assets" / "game_icons"
        if not icon_dir.exists():
            icon_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"Creata directory icone: {icon_dir}")

        self._icon_list = sorted(list(icon_dir.glob("*.png")))
        logger.info(f"Trovate {len(self._icon_list)} icone in {icon_dir}")

    def _icon_process_selection(self, src_png: Path):
        """Copia e converte l'icona nel gioco selezionato."""
        if self.gs_sel_game is None:
            return

        game_id = self.gs_games[self.gs_sel_game]
        game_dir = self.base_path / "games" / game_id

        # 1. Copia PNG originale come master in assets/
        assets_dir = game_dir / "assets"
        assets_dir.mkdir(parents=True, exist_ok=True)
        dst_png = assets_dir / "icon.png"
        shutil.copy2(src_png, dst_png)

        # 2. Generazione .ICO professionale per Windows (multi-size)
        try:
            dst_ico = game_dir / "icon.ico"
            with Image.open(src_png) as img:
                # Supporta i formati standard Windows
                sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
                img.save(dst_ico, format='ICO', sizes=sizes)
            logger.info(f"Icona .ico generata con successo per {game_id}")
        except Exception as e:
            logger.error(f"Errore conversione .ico: {e}")
            self._status(self._TR("ico_error", ".ico error: {0}").format(e), (200, 50, 50))

        # 3. Generazione asset Android (se necessario)
        # Creiamo una struttura standard per buildozer/p4a se il gioco è categoria android
        cfg_p = game_dir / "game_config.json"
        if cfg_p.exists():
            from editor.core.io import _load_json, _save_json
            cfg = _load_json(cfg_p)
            if cfg.get("category") == "android":
                android_dir = game_dir / "android_assets"
                android_dir.mkdir(parents=True, exist_ok=True)
                # Copiamo il png master anche qui per buildozer
                shutil.copy2(src_png, android_dir / "icon.png")

            # Aggiorna il config con il path dell'icona (opzionale, ma utile)
            cfg["icon"] = "assets/icon.png"
            _save_json(cfg_p, cfg)

        self._status(self._TR("ico_updated", "Game icon updated and converted"), OK_C, 3)
        self._icon_modal = False

    def _icon_grid_metrics(self, w: int, h: int) -> dict:
        """Every rect the icon picker needs, derived once from the window size.

        Keys: box, close, cancel, cancel_label, grid, item_w, item_h, cols,
        gap, rows, visible_rows, max_scroll.
        """
        mw = min(_ICON_DLG_W, w - 40)
        mh = min(_ICON_DLG_H, h - 40)
        mx, my = (w - mw) // 2, (h - mh) // 2
        grid = pygame.Rect(mx + 30, my + 100, mw - 60, mh - 180)
        # The gaps between the columns are part of the width to divide up:
        # without them the last column overflowed the grid and was clipped.
        item_w = ((grid.width - 40 - _ICON_GAP * (_ICON_COLS - 1))
                  // _ICON_COLS)
        item_h = item_w + _ICON_CAPTION_H
        rows = (len(self._icon_list) + _ICON_COLS - 1) // _ICON_COLS
        visible = max(1, (grid.height - 20) // (item_h + _ICON_GAP))
        cancel_label = self._TR("btn_cancel_caps", "CANCEL")
        cancel_w = _button_w(cancel_label, "sm", min_w=150)
        return {
            "box": pygame.Rect(mx, my, mw, mh),
            "close": pygame.Rect(mx + mw - 45, my + 20, 30, 30),
            "cancel": pygame.Rect(mx + mw - cancel_w - 30, my + mh - 55,
                                  cancel_w, 34),
            "cancel_label": cancel_label,
            "grid": grid,
            "item_w": item_w,
            "item_h": item_h,
            "cols": _ICON_COLS,
            "gap": _ICON_GAP,
            "rows": rows,
            "visible_rows": visible,
            "max_scroll": max(0, rows - visible),
        }

    def _icon_item_rect(self, geo: dict, index: int):
        """Rect of the icon at `index`, at the current scroll."""
        row, col = divmod(index, geo["cols"])
        x = geo["grid"].x + 20 + col * (geo["item_w"] + geo["gap"])
        y = (geo["grid"].y + 20
             + (row - self._icon_scroll) * (geo["item_h"] + geo["gap"]))
        return pygame.Rect(x, y, geo["item_w"], geo["item_h"])

    def _r_icon_modal(self, w, h):
        if not self._icon_modal:
            return

        # Overlay scuro
        dim = pygame.Surface((w, h), pygame.SRCALPHA)
        dim.fill((0, 0, 0, 200))
        self.screen.blit(dim, (0, 0))

        # Box modale
        geo = self._icon_grid_metrics(w, h)
        box = geo["box"]
        self._icon_scroll = max(0, min(self._icon_scroll, geo["max_scroll"]))
        mx, my = box.x, box.y

        _rect(self.screen, (30, 32, 45), box, radius=12)
        _rect(self.screen, ACCENT, box, 2, radius=12)

        # Header
        _draw_text(self.screen, self._TR("ico_title", "GAME ICON SELECTION"), "lg", TXT_HI, mx + 30, my + 25)
        _draw_text(self.screen, self._TR("ico_hint", "Icons are converted automatically to .ico and mobile formats"), "xs", TXT_DIM, mx + 30, my + 60)

        # Bottone X
        mpos = pygame.mouse.get_pos()
        xr = geo["close"]
        if _button(self.screen, xr, "X", _in_rect(mpos, xr), danger=True):
            self._icon_modal = False
            return

        # Grid Area
        grid_r = geo["grid"]
        item_w = geo["item_w"]
        cols, vis_rows = geo["cols"], geo["visible_rows"]
        _rect(self.screen, (20, 22, 30), grid_r, radius=8)

        if not self._icon_list:
            # Empty state: the picker accepts a dropped PNG, so say so instead
            # of showing an empty black rectangle.
            msg = self._TR("ico_empty", "No icon yet - drop a PNG file here")
            tw, th = _text_wh(msg, "sm")
            _draw_text(self.screen, msg, "sm", (95, 100, 125),
                       grid_r.centerx - tw // 2, grid_r.centery - th // 2)

        if geo["rows"] > vis_rows:
            _scrollbar(self.screen, grid_r.right - 10, grid_r.top + 5, 6,
                       grid_r.height - 10, self._icon_scroll, geo["rows"], vis_rows)

        # Rendering icone
        self.screen.set_clip(grid_r)
        for i, icon_p in enumerate(self._icon_list):
            r = i // cols
            if r < self._icon_scroll or r >= self._icon_scroll + vis_rows + 1:
                continue

            item_rect = self._icon_item_rect(geo, i)
            ix, iy = item_rect.x, item_rect.y
            hov = _in_rect(mpos, item_rect)

            # Box icona
            bg_col = (45, 48, 65) if hov else (35, 38, 50)
            _rect(self.screen, bg_col, item_rect, radius=8)
            if hov:
                _rect(self.screen, ACCENT, item_rect, 1, radius=8)

            # Anteprima immagine
            img_rect = pygame.Rect(ix + 10, iy + 10, item_w - 20, item_w - 20)
            _rect(self.screen, (10, 10, 15), img_rect, radius=4)

            # Cache surface
            cache_key = str(icon_p)
            if cache_key not in self._icon_cache:
                try:
                    full_surf = pygame.image.load(str(icon_p)).convert_alpha()
                    self._icon_dims[cache_key] = full_surf.get_size()
                    # Resize per la grid
                    surf = pygame.transform.smoothscale(full_surf, (img_rect.width, img_rect.height))
                    self._icon_cache[cache_key] = surf
                except Exception:
                    self._icon_cache[cache_key] = None
                    self._icon_dims[cache_key] = (0, 0)

            if self._icon_cache[cache_key]:
                self.screen.blit(self._icon_cache[cache_key], img_rect.topleft)
            else:
                _draw_shape_icon(self.screen, img_rect, "image", (60, 60, 70))

            # Nome file e Dimensioni
            _draw_text(self.screen, icon_p.stem[:12], "xs", TXT_HI if hov else TXT_DIM, ix + 10, iy + item_w - 5, item_w - 20)

            w_px, h_px = self._icon_dims.get(cache_key, (0, 0))
            if w_px > 0:
                _draw_text(self.screen, f"{w_px}x{h_px}", "xs", (100, 150, 100) if hov else (70, 90, 70), ix + 10, iy + item_w + 5)

            # Pulsante Elimina (in alto a destra dell'item)
            del_r = pygame.Rect(ix + item_w - 24, iy + 4, 20, 20)
            del_hov = _in_rect(mpos, del_r)
            is_confirming = (self._icon_del_confirm == icon_p)

            del_col = (255, 50, 50) if is_confirming else (150, 60, 60)
            _rect(self.screen, del_col if del_hov else (40, 40, 50), del_r, radius=4)
            _draw_text(self.screen, "!" if is_confirming else "x", "xs", (255, 255, 255), del_r.x + 6, del_r.y + 2)

        self.screen.set_clip(None)

        # Footer
        btn_close_r = geo["cancel"]
        _button(self.screen, btn_close_r, geo["cancel_label"],
                _in_rect(mpos, btn_close_r))

    def _icon_click(self, mx, my, w, h):
        """Gestisce il click nella modale icone. Ritorna True se intercettato."""
        if not self._icon_modal:
            return False

        geo = self._icon_grid_metrics(w, h)

        if _in_rect((mx, my), geo["close"]) or _in_rect((mx, my), geo["cancel"]):
            self._icon_modal = False
            return True

        grid_r = geo["grid"]
        if _in_rect((mx, my), grid_r):
            item_w, vis_rows = geo["item_w"], geo["visible_rows"]
            for i, icon_p in enumerate(self._icon_list):
                r = i // geo["cols"]
                if r < self._icon_scroll or r >= self._icon_scroll + vis_rows + 1:
                    continue

                item_rect = self._icon_item_rect(geo, i)
                ix, iy = item_rect.x, item_rect.y

                if _in_rect((mx, my), item_rect):
                    # Pulsante Elimina
                    del_r = pygame.Rect(ix + item_w - 24, iy + 4, 20, 20)
                    if _in_rect((mx, my), del_r):
                        if self._icon_del_confirm == icon_p:
                            # ELIMINA
                            try:
                                icon_p.unlink()
                                if str(icon_p) in self._icon_cache: del self._icon_cache[str(icon_p)]
                                self._icon_list = sorted(list(icon_p.parent.glob("*.png")))
                                self._icon_del_confirm = None
                                self._status(self._TR("ico_deleted", "Icon '{0}' deleted").format(icon_p.name), (255, 100, 100), 2)
                            except Exception as e:
                                self._status(self._TR("io_error", "Error: {0}").format(e), (255, 0, 0), 3)
                        else:
                            self._icon_del_confirm = icon_p
                        return True
                    else:
                        # SELEZIONA
                        self._icon_del_confirm = None
                        self._icon_process_selection(icon_p)
                        return True

            # Click nella grid ma non su item: reset conferma
            self._icon_del_confirm = None
            return True

        # Click nella modale ma fuori dalla grid: intercetta e non fa nulla
        if _in_rect((mx, my), geo["box"]):
            self._icon_del_confirm = None
            return True

        return False

    def _icon_wheel(self, ev):
        if not self._icon_modal:
            return
        geo = self._icon_grid_metrics(*self.screen.get_size())
        self._icon_scroll = max(0, min(geo["max_scroll"], self._icon_scroll - ev.y))

    def _icon_handle_drop(self, filepath: str):
        """Gestisce il drag & drop di un nuovo file PNG nella modale."""
        if not self._icon_modal:
            return

        src = Path(filepath)
        if src.suffix.lower() != ".png":
            self._status(self._TR("ico_png_only", "Only PNG files are supported for icons"), (200, 50, 50), 3)
            return

        dst_dir = self.base_path / "engine" / "assets" / "game_icons"
        dst_dir.mkdir(parents=True, exist_ok=True)

        dst = dst_dir / src.name
        try:
            shutil.copy2(src, dst)
            logger.info(f"Nuova icona aggiunta tramite drop: {dst}")
            self._status(self._TR("ico_added", "Icon '{0}' added to the catalog").format(src.name), OK_C, 2)
            # Refresh lista
            self._icon_list = sorted(list(dst_dir.glob("*.png")))
        except Exception as e:
            logger.error(f"Errore copia icona droppata: {e}")
            self._status(self._TR("err_loading", "Load error: {0}").format(e), (200, 50, 50), 3)
