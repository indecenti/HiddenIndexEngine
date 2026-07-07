"""
editor/mixins/icon_modal.py

IconModalMixin — Gestione selezione e conversione icone di gioco.
"""

import shutil
import logging
from pathlib import Path
import pygame
from PIL import Image

from editor.constants import (
    ACCENT, BORDER, BTN, BTN_HO, TXT, TXT_HI, TXT_DIM, BG, OK_C
)
from editor.ui.draw import (
    _rect, _draw_text, _button, _in_rect, _draw_shape_icon, _scrollbar
)

logger = logging.getLogger("icon_modal")

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
            self._status(f"Errore .ico: {e}", (200, 50, 50))

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

        self._status("Icona gioco aggiornata e convertita!", OK_C, 3)
        self._icon_modal = False

    def _r_icon_modal(self, w, h):
        if not self._icon_modal:
            return

        # Overlay scuro
        dim = pygame.Surface((w, h), pygame.SRCALPHA)
        dim.fill((0, 0, 0, 200))
        self.screen.blit(dim, (0, 0))

        # Box modale
        mw, mh = 900, 700
        mx, my = (w - mw) // 2, (h - mh) // 2
        box = pygame.Rect(mx, my, mw, mh)
        
        _rect(self.screen, (30, 32, 45), box, radius=12)
        _rect(self.screen, ACCENT, box, 2, radius=12)

        # Header
        _draw_text(self.screen, "SELEZIONE ICONA GIOCO", "lg", TXT_HI, mx + 30, my + 25)
        _draw_text(self.screen, "Le icone verranno convertite automaticamente in .ico e formati mobile", "xs", TXT_DIM, mx + 30, my + 60)

        # Bottone X
        mpos = pygame.mouse.get_pos()
        xr = pygame.Rect(mx + mw - 45, my + 20, 30, 30)
        if _button(self.screen, xr, "X", _in_rect(mpos, xr), danger=True):
            self._icon_modal = False
            return

        # Grid Area
        grid_r = pygame.Rect(mx + 30, my + 100, mw - 60, mh - 180)
        _rect(self.screen, (20, 22, 30), grid_r, radius=8)
        
        cols = 6
        item_w = (grid_r.width - 40) // cols
        item_h = item_w + 20
        gap = 8
        
        # Scrollbar
        total_items = len(self._icon_list)
        rows = (total_items + cols - 1) // cols
        vis_rows = grid_r.height // item_h
        
        if rows > vis_rows:
            _scrollbar(self.screen, grid_r.right - 10, grid_r.top + 5, 6, grid_r.height - 10, 
                       self._icon_scroll, rows, vis_rows)

        # Rendering icone
        self.screen.set_clip(grid_r)
        for i, icon_p in enumerate(self._icon_list):
            r = i // cols
            c = i % cols
            
            if r < self._icon_scroll or r >= self._icon_scroll + vis_rows + 1:
                continue
                
            ix = grid_r.x + 20 + c * (item_w + gap)
            iy = grid_r.y + 20 + (r - self._icon_scroll) * (item_h + gap)
            
            item_rect = pygame.Rect(ix, iy, item_w, item_h)
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
        btn_close_r = pygame.Rect(mx + mw - 180, my + mh - 55, 150, 34)
        _button(self.screen, btn_close_r, "ANNULLA", _in_rect(mpos, btn_close_r))

    def _icon_click(self, mx, my, w, h):
        """Gestisce il click nella modale icone. Ritorna True se intercettato."""
        if not self._icon_modal:
            return False

        mw, mh = 900, 700
        dx, dy = (w - mw) // 2, (h - mh) // 2
        
        # Bottone X
        xr = pygame.Rect(dx + mw - 45, dy + 20, 30, 30)
        if _in_rect((mx, my), xr):
            self._icon_modal = False; return True

        # Bottone Annulla
        btn_close_r = pygame.Rect(dx + mw - 180, dy + mh - 55, 150, 34)
        if _in_rect((mx, my), btn_close_r):
            self._icon_modal = False; return True

        # Grid Area
        grid_r = pygame.Rect(dx + 30, dy + 100, mw - 60, mh - 180)
        if _in_rect((mx, my), grid_r):
            cols = 6
            item_w = (grid_r.width - 40) // cols
            item_h = item_w + 20
            gap = 8
            
            total_items = len(self._icon_list)
            rows = (total_items + cols - 1) // cols
            vis_rows = grid_r.height // item_h

            for i, icon_p in enumerate(self._icon_list):
                r = i // cols
                c = i % cols
                if r < self._icon_scroll or r >= self._icon_scroll + vis_rows + 1: continue
                
                ix = grid_r.x + 20 + c * (item_w + gap)
                iy = grid_r.y + 20 + (r - self._icon_scroll) * (item_h + gap)
                item_rect = pygame.Rect(ix, iy, item_w, item_h)
                
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
                                self._status(f"Icona '{icon_p.name}' eliminata.", (255, 100, 100), 2)
                            except Exception as e:
                                self._status(f"Errore: {e}", (255, 0, 0), 3)
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
        if _in_rect((mx, my), (dx, dy, mw, mh)):
            self._icon_del_confirm = None
            return True

        return False

    def _icon_wheel(self, ev):
        if not self._icon_modal:
            return
        
        cols = 6
        total_items = len(self._icon_list)
        rows = (total_items + cols - 1) // cols
        vis_rows = (700 - 180) // ((900 - 100) // 6 + 20) # Stima approssimativa vis_rows
        
        max_scroll = max(0, rows - 3) # 3 è un valore conservativo per la grid visibile
        self._icon_scroll = max(0, min(max_scroll, self._icon_scroll - ev.y))

    def _icon_handle_drop(self, filepath: str):
        """Gestisce il drag & drop di un nuovo file PNG nella modale."""
        if not self._icon_modal:
            return
            
        src = Path(filepath)
        if src.suffix.lower() != ".png":
            self._status("Solo file PNG supportati per le icone!", (200, 50, 50), 3)
            return
            
        dst_dir = self.base_path / "engine" / "assets" / "game_icons"
        dst_dir.mkdir(parents=True, exist_ok=True)
        
        dst = dst_dir / src.name
        try:
            shutil.copy2(src, dst)
            logger.info(f"Nuova icona aggiunta tramite drop: {dst}")
            self._status(f"Icona '{src.name}' aggiunta al catalogo!", OK_C, 2)
            # Refresh lista
            self._icon_list = sorted(list(dst_dir.glob("*.png")))
        except Exception as e:
            logger.error(f"Errore copia icona droppata: {e}")
            self._status(f"Errore caricamento: {e}", (200, 50, 50), 3)
