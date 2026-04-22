"""
editor/mixins/render_topbar.py

RenderTopbarMixin — top bar con menù a discesa, titolo e status bar.
"""

import pygame

from editor.constants import (
    TOP_BAR_H, STATUS_H, MENU_W,
    ACCENT, BORDER, BTN, BTN_HO, BTN_AC, STATUS,
    TXT, TXT_DIM, TXT_HI, OK_C, PANEL, BG
)
from editor.ui.draw import _txt, _draw_text, _rect, _button, _in_rect


class RenderTopbarMixin:
    """Top bar (menù, titolo) e status bar."""

    # ─────────────────────────────────────────────────────────────────────────
    # TOP BAR & MENUS
    # ─────────────────────────────────────────────────────────────────────────

    def _r_top_bar(self, w):
        bg_bar = (25, 25, 30)
        _rect(self.screen, bg_bar, (0, 0, w, TOP_BAR_H))
        pygame.draw.line(self.screen, (60, 60, 75), (0, TOP_BAR_H-1), (w, TOP_BAR_H-1))
        
        mx, my = pygame.mouse.get_pos()
        
        # Etichette localizzate per i menu principali
        menu_file = self.lang_manager.get("menu_file", "File")
        menu_edit = self.lang_manager.get("menu_edit", "Modifica")
        menu_lang = self.lang_manager.get("menu_language", "Lingua")

        # Inizializza bounds se vuoti (usando i nomi inglesi come ID interni costanti)
        if not self._menu_bounds:
            self._menu_bounds = {
                "File": pygame.Rect(10, 0, 60, TOP_BAR_H),
                "Edit": pygame.Rect(70, 0, 90, TOP_BAR_H),
                "Lang": pygame.Rect(160, 0, 80, TOP_BAR_H),
            }

        # Rendering voci principali
        menu_display_names = {
            "File": menu_file,
            "Edit": menu_edit,
            "Lang": menu_lang
        }

        for internal_id, rect in self._menu_bounds.items():
            is_active = (self._active_menu == internal_id)
            is_hov = _in_rect((mx, my), rect)
            
            if is_active or is_hov:
                _rect(self.screen, BTN_HO if is_hov else BTN_AC, rect)
            
            color = TXT_HI if (is_hov or is_active) else TXT_DIM
            display_name = menu_display_names[internal_id]
            tw, th = _txt(display_name, "sm", color).get_size()
            _draw_text(self.screen, display_name, "sm", color, 
                       rect.x + (rect.w - tw)//2, rect.y + (rect.h - th)//2)

        # Rendering Dropdown se attivo
        if self._active_menu:
            self._r_dropdown(self._active_menu)

        # Titolo (spostato a destra per non coprire i menu)
        title_x = 260
        title_str = "HIDDEN ENGINE"
        if self.game_path:
            title_str += f"  |  {self.game_path.name.upper()}"
        if self.scene_path:
            title_str += f"  >  {self.scene_path.name}"
        if getattr(self, "scene_dirty", False):
            title_str += "  [MODIFICATO]*"
        
        _draw_text(self.screen, title_str, "sm", (120, 120, 140), title_x, 7, w - title_x - 100)

    def _get_menu_items(self, menu_name):
        """Restituisce la lista di (label, cmd) per il menu specificato."""
        l = self.lang_manager
        if menu_name == "File":
            return [
                (l.get("menu_new_game", "Nuovo Progetto..."), "file_new_game"),
                (l.get("menu_open_game", "Apri Progetto..."), "file_open_game"),
                None,
                (l.get("menu_save_scene", "Salva Scena"), "file_save_scene"),
                (l.get("menu_save_as", "Salva con nome..."), "file_save_as"),
                None,
                (l.get("menu_exit_to_gs", "Torna al Selettore"), "file_exit_to_gs"),
                (l.get("menu_quit", "Esci"), "file_quit"),
            ]
        elif menu_name == "Edit":
            return [
                (l.get("menu_undo", "Annulla") + " (Ctrl+Z)", "edit_undo"),
                (l.get("menu_redo", "Ripristina") + " (Ctrl+Y)", "edit_redo"),
                None,
                (l.get("menu_cut", "Taglia") + " (Ctrl+X)", "edit_cut"),
                (l.get("menu_copy", "Copia") + " (Ctrl+C)", "edit_copy"),
                (l.get("menu_paste", "Incolla") + " (Ctrl+V)", "edit_paste"),
                None,
                (l.get("menu_lang_modal", "Editor Traduzioni..."), "edit_lang_modal"),
            ]
        elif menu_name == "Lang":
            items = []
            for lang in self.LANGS:
                label = lang.upper()
                if lang == self.current_lang:
                    label = f"• {label}"
                items.append((label, f"lang_switch_{lang}"))
            return items
        return []

    def _r_dropdown(self, menu_name):
        """Disegna il contenuto del menu selezionato."""
        mx, my = pygame.mouse.get_pos()
        root_r = self._menu_bounds[menu_name]
        items = self._get_menu_items(menu_name)
        
        if not items: return

        # Calcolo dimensioni
        ITEM_H = 26
        drop_h = len(items) * ITEM_H
        drop_r = pygame.Rect(root_r.x, TOP_BAR_H, MENU_W, drop_h)
        
        # Background shadow
        _rect(self.screen, (10, 10, 15), (drop_r.x+3, drop_r.y+3, drop_r.w, drop_r.h), radius=4)
        _rect(self.screen, PANEL, drop_r, radius=4)
        _rect(self.screen, BORDER, drop_r, 1, radius=4)

        curr_y = drop_r.y
        for item in items:
            if item is None:
                pygame.draw.line(self.screen, BORDER, (drop_r.x + 5, curr_y + ITEM_H//2), 
                                 (drop_r.x + drop_r.w - 5, curr_y + ITEM_H//2))
                curr_y += ITEM_H
                continue
            
            label, cmd = item
            item_r = pygame.Rect(drop_r.x + 2, curr_y + 2, drop_r.w - 4, ITEM_H - 4)
            is_hov = _in_rect((mx, my), item_r)
            
            if is_hov:
                _rect(self.screen, ACCENT, item_r, radius=3)
            
            color = TXT_HI if is_hov else TXT
            _draw_text(self.screen, label, "sm", color, item_r.x + 10, item_r.y + 4)
            curr_y += ITEM_H

    # ─────────────────────────────────────────────────────────────────────────
    # STATUS BAR
    # ─────────────────────────────────────────────────────────────────────────

    def _r_status(self, w, h):
        from editor.constants import UI_TIPS
        y = h - STATUS_H
        _rect(self.screen, STATUS, (0, y, w, STATUS_H))
        pygame.draw.line(self.screen, BORDER, (0, y), (w, y))

        mx2, my2 = pygame.mouse.get_pos()

        # Pulsante < SELETTORE
        btn_r    = pygame.Rect(4, y+4, 110, STATUS_H-8)
        hov_back = _in_rect((mx2, my2), btn_r)
        if hov_back: self.active_tooltip = UI_TIPS.get("btn_back")
        
        _rect(self.screen, BTN_HO if hov_back else BTN, btn_r, radius=3)
        _rect(self.screen, BORDER, btn_r, 1, radius=3)
        sb = _txt(self._TR("tb_back_selector"), "sm", TXT_HI)
        self.screen.blit(sb, (btn_r.centerx - sb.get_width()//2,
                               btn_r.centery - sb.get_height()//2))

        # Pulsante SALVA
        if hasattr(self, "scene_path") and self.scene_path:
            save_r   = pygame.Rect(118, y+4, 100, STATUS_H-8)
            hov_save = _in_rect((mx2, my2), save_r)
            if hov_save: self.active_tooltip = UI_TIPS.get("btn_save")
            
            scol = OK_C if self.scene_dirty else BTN
            _rect(self.screen, BTN_HO if hov_save else scol, save_r, radius=3)
            _rect(self.screen, (ACCENT if self.scene_dirty else BORDER), save_r, 1, radius=3)
            ss = _txt(self._TR("tb_save"), "sm", TXT_HI if self.scene_dirty else TXT_DIM)
            self.screen.blit(ss, (save_r.centerx - ss.get_width()//2,
                                   save_r.centery - ss.get_height()//2))

        # Messaggio status
        msg_x = 224 if getattr(self, "scene_path", None) else 114
        _draw_text(self.screen, self.status_msg, "sm", self.status_col,
                   msg_x, y+8, w//2 - msg_x)

        # Info destra
        parts = []
        if getattr(self, "game_name", None):  parts.append(f"{self._TR('tb_game')} {self.game_name}")
        if getattr(self, "scene_path", None):
            parts.append(f"{self._TR('tb_scene')} {self.scene_path.name}")
            if self.scene_dirty: parts.append(self._TR("tb_not_saved"))
        parts.append(f"{self._TR('tb_undo')} {len(self.undo_stack)}")
        info = "  |  ".join(parts)
        si = _txt(info, "sm", TXT_DIM)
        self.screen.blit(si, (w - si.get_width() - 8, y+8))

        # Shortcut hint (centro, solo se c'è spazio)
        hints = self._TR("tb_shortcuts")
        hs = _txt(hints, "sm", (70, 70, 88))
        hx = (w - hs.get_width()) // 2
        if hx > w // 3:
            self.screen.blit(hs, (hx, y+8))
