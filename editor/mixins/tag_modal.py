"""
editor/mixins/tag_modal.py

TagModalMixin — dialogo per la modifica dei tag di un oggetto del catalogo.
"""

import pygame
import logging

from editor.constants import (
    ACCENT, BORDER, BTN, TXT_DIM, TXT_HI, OK_C, ERR_C,
)
from editor.core.io import (
    _load_json, _save_json, _load_catalog,
)
from editor.ui.draw import (
    _draw_text, _rect, _button, _in_rect, _scrollbar, _draw_tag_chip,
    _clamp, _text_wh, _ui_scale,
)


class TagModalMixin:
    """Dialogo per aggiungere/rimuovere tag esistenti da un oggetto del catalogo."""

    def _tag_modal_wheel(self, dy: int) -> None:
        """Scroll the chips of the available tags (bounds set by the render)."""
        max_scroll = getattr(self, "_tag_modal_max_scroll", 0)
        self._tag_modal_scroll = _clamp(self._tag_modal_scroll - dy, 0, max_scroll)

    def _tag_modal_open(self, catalog_id: str):
        self._tag_modal_target_id = catalog_id
        # Trova l'entry nel catalogo (può essere globale o locale)
        cat_entry = next((c for c in self.catalog if c["id"] == catalog_id), None)
        if not cat_entry:
            self._status(self._TR("tg_asset_not_found", "Error: asset {0} not found").format(catalog_id), ERR_C, 3)
            return

        self._tag_modal_current_tags = set(cat_entry.get("tags", []))
        
        # Sincronizzazione con il TagManager globale
        self._tag_modal_search = ""
        self._tag_modal_scroll = 0
        self._tag_modal_active = True
        self._tag_modal_searching = True # Focus immediato sulla ricerca
        self._tag_modal_dirty = False
        # limit alto: il default (20) impedisce di vedere/assegnare i tag oltre il 20esimo.
        self._tag_modal_suggestions = self.tag_manager.get_suggestions("", limit=10000)

    def _tag_modal_key(self, ev):
        if ev.key == pygame.K_ESCAPE:
            self._tag_modal_active = False
            return
        if ev.key == pygame.K_RETURN:
            if self._tag_modal_searching and self._tag_modal_search:
                # CREAZIONE DINAMICA: invio crea/recupera il tag e lo assegna.
                new_tag = self.tag_manager.ensure_tag(self._tag_modal_search)
                if new_tag and new_tag not in self._tag_modal_current_tags:
                    self._tag_modal_current_tags.add(new_tag)
                    self._tag_modal_dirty = True
                self._tag_modal_search = ""
                self._tag_modal_scroll = 0
                self._tag_modal_suggestions = self.tag_manager.get_suggestions("", limit=10000)
            elif self._tag_modal_searching:
                self._tag_modal_searching = False
            else:
                self._tag_modal_commit()
            return

        if self._tag_modal_searching:
            if ev.key == pygame.K_BACKSPACE:
                self._tag_modal_search = self._tag_modal_search[:-1]
                self._tag_modal_scroll = 0
                self._tag_modal_suggestions = self.tag_manager.get_suggestions(self._tag_modal_search, limit=10000)
            elif ev.unicode and ev.unicode.isprintable() and ev.unicode not in ",;":
                self._tag_modal_search += ev.unicode.lower()
                self._tag_modal_scroll = 0
                self._tag_modal_suggestions = self.tag_manager.get_suggestions(self._tag_modal_search, limit=10000)
        else:
            if ev.key == pygame.K_SLASH:
                self._tag_modal_searching = True
                self._tag_modal_search = ""

    def _tag_modal_click(self, mx, my_raw, w, h):
        """Click inside the dialog, resolved on the rects the renderer drew.

        The geometry used to be written twice, and the two copies already
        disagreed: the close button was hit-tested 4 px above where it was
        drawn. `w` and `h` are kept for the signature the router calls with.
        """
        hits = getattr(self, "_tag_modal_hitboxes", None)
        if not hits:
            return
        pos = (mx, my_raw)

        if not _in_rect(pos, hits["box"]) or _in_rect(pos, hits["close"]):
            self._tag_modal_active = False
            return

        self._tag_modal_searching = _in_rect(pos, hits["search"])
        if self._tag_modal_searching:
            return

        for tag_id, r in getattr(self, "_tag_modal_chip_rects", []):
            if _in_rect(pos, r):
                if tag_id in self._tag_modal_current_tags:
                    self._tag_modal_current_tags.remove(tag_id)
                else:
                    self._tag_modal_current_tags.add(tag_id)
                self._tag_modal_dirty = True
                return

        if _in_rect(pos, hits["save"]):
            self._tag_modal_commit()
        elif _in_rect(pos, hits["cancel"]):
            self._tag_modal_active = False

    def _tag_modal_commit(self):
        cid = self._tag_modal_target_id
        new_tags = sorted(list(self._tag_modal_current_tags))
        
        # 1. Trova dove risiede l'asset (Global o Game)
        # Proviamo prima il catalogo del gioco
        game_cat_p = self.game_path / "objects_catalog.json"
        modified = False
        
        if game_cat_p.exists():
            data = _load_json(game_cat_p)
            for obj in data.get("objects", []):
                if obj["id"] == cid:
                    obj["tags"] = new_tags
                    _save_json(game_cat_p, data)
                    modified = True
                    logging.info(f"[TAG] Aggiornati tag per {cid} nel catalogo GIOCO")
                    break
        
        # Se non è nel catalogo del gioco (o non è stato trovato lì), proviamo il globale
        # NOTA: Se l'asset è globale ma non ancora nel gioco, lo salviamo nel globale?
        # Sì, i tag sono metadati della risorsa.
        if not modified:
            global_cat_p = self.base_path / "engine" / "data" / "global_objects_catalog.json"
            if global_cat_p.exists():
                data = _load_json(global_cat_p)
                for obj in data.get("objects", []):
                    if obj["id"] == cid:
                        obj["tags"] = new_tags
                        _save_json(global_cat_p, data)
                        modified = True
                        logging.info(f"[TAG] Aggiornati tag per {cid} nel catalogo GLOBALE")
                        break
        
        if modified:
            # Refresh catalogo in memoria
            self.catalog = _load_catalog(self.game_name)
            self._bump_catalog_rev()
            self._status(self._TR("tg_updated", "Tags updated for {0}").format(cid), OK_C, 3)
        else:
            self._status(self._TR("tg_save_error", "Error: cannot save the tags for {0}").format(cid), ERR_C, 3)
            
        self._tag_modal_active = False

    def _r_tag_modal(self, w, h):
        if not getattr(self, "_tag_modal_active", False):
            return

        # Overlay oscurante
        dim = pygame.Surface((w, h), pygame.SRCALPHA)
        dim.fill((0, 0, 0, 180))
        self.screen.blit(dim, (0, 0))

        # The dialog and its rows follow the UI scale: at 600x500 fixed, a
        # larger font left the chips and the search box cramped.
        scale = _ui_scale()
        dw, dh = int(round(600 * scale)), int(round(500 * scale))
        dw, dh = min(dw, w - 40), min(dh, h - 40)
        dx, dy = (w - dw) // 2, (h - dh) // 2
        mx, my = pygame.mouse.get_pos()
        line_h = _text_wh("Ag", "md")[1]
        search_h = line_h + 12

        # Box principale
        box = pygame.Rect(dx, dy, dw, dh)
        hits: dict = {"box": box}
        self._tag_modal_hitboxes = hits
        _rect(self.screen, (35, 35, 45), box, radius=12)
        _rect(self.screen, ACCENT, box, 2, radius=12)

        # Header
        title_str = self._TR("tg_title", "Edit tags: {0}").format(
            self._tag_modal_target_id)
        _draw_text(self.screen, title_str, "lg", TXT_HI, dx + 20, dy + 15)
        
        xr = pygame.Rect(dx + dw - 36, dy + 12, 26, 22)
        _button(self.screen, xr, "X", _in_rect((mx, my), xr), danger=True)
        hits["close"] = xr

        # Search Bar
        search_r = pygame.Rect(dx + 20, dy + 60, dw - 40, search_h)
        hits["search"] = search_r
        is_searching = self._tag_modal_searching
        _rect(self.screen, (45, 48, 60) if is_searching else BTN, search_r, radius=6)
        _rect(self.screen, ACCENT if is_searching else BORDER, search_r, 1 if not is_searching else 2, radius=6)
        
        search_txt = (self._tag_modal_search or
                      self._TR("tg_search_hint", "Search the existing tags..."))
        search_col = TXT_HI if (self._tag_modal_search or is_searching) else TXT_DIM
        _draw_text(self.screen, search_txt, "md", search_col, search_r.x + 12,
                   search_r.centery - line_h // 2, search_r.w - 24)
        
        # Griglia di tag (Chips)
        clip_r = pygame.Rect(dx + 20, search_r.bottom + 13, dw - 40,
                             dh - (search_r.bottom - dy) - 78)
        _rect(self.screen, (25, 26, 35), clip_r, radius=8)
        _rect(self.screen, BORDER, clip_r, 1, radius=8)
        
        self.screen.set_clip(clip_r)
        
        # Mostriamo i tag suggeriti (quelli che matchano la ricerca)
        CHIP_W = (clip_r.w - 30) // 3
        CHIP_H = max(32, line_h + 12)
        GAP = 8
        
        self._tag_modal_chip_rects = []
        for i, tag in enumerate(self._tag_modal_suggestions):
            col = i % 3
            row = i // 3
            tx = clip_r.x + 10 + col * (CHIP_W + GAP)
            ty = clip_r.y + 10 + row * (CHIP_H + GAP) - self._tag_modal_scroll * (CHIP_H + GAP)
            
            if ty + CHIP_H < clip_r.y or ty > clip_r.bottom:
                continue
                
            r = pygame.Rect(tx, ty, CHIP_W, CHIP_H)
            is_active = tag in self._tag_modal_current_tags
            hov = _in_rect((mx, my), r) and clip_r.collidepoint(mx, my)
            
            # Rendering chip tramite la nuova funzione centralizzata
            # Same lookup as the catalog panel: the taxonomy only carries the
            # Italian label, the translations live in the strings files.
            label = self._TR(f"tag_{tag}", tag.replace("_", " ").capitalize())
            _draw_tag_chip(self.screen, r, label, active=is_active, hovered=hov)
            
            self._tag_modal_chip_rects.append((tag, r))

        self.screen.set_clip(None)
        
        # Scrollbar
        total_rows = (len(self._tag_modal_suggestions) + 2) // 3
        visible_rows = clip_r.h // (CHIP_H + GAP)
        if total_rows > visible_rows:
            max_scroll = total_rows - visible_rows
            self._tag_modal_max_scroll = max_scroll
            _scrollbar(self.screen, clip_r.right - 6, clip_r.y + 10, 4, clip_r.h - 20, 
                       self._tag_modal_scroll, total_rows, visible_rows)
        else:
            self._tag_modal_max_scroll = 0

        # Footer
        btn_h = max(34, line_h + 14)
        btn_y = dy + dh - btn_h - 16
        half = (dw - 50) // 2

        ok_r = pygame.Rect(dx + 20, btn_y, half, btn_h)
        can_r = pygame.Rect(ok_r.right + 10, btn_y, half, btn_h)
        hits["save"], hits["cancel"] = ok_r, can_r
        
        _button(self.screen, ok_r, self._TR("tg_save", "Save changes"), _in_rect((mx, my), ok_r), active=self._tag_modal_dirty)
        _button(self.screen, can_r, self._TR("btn_cancel", "Cancel"), _in_rect((mx, my), can_r), danger=True)
