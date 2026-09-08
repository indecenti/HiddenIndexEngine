"""
editor/mixins/render_topbar.py

RenderTopbarMixin — top bar con menù a discesa, titolo e status bar.
"""

import pygame

from editor.constants import (
    TOP_BAR_H, STATUS_H, MENU_W, STATUS_BTN_MIN_W,
    ACCENT, BORDER, BTN, BTN_HO, BTN_AC, STATUS,
    TXT, TXT_DIM, TXT_HI, OK_C, PANEL, BG
)
from editor.ui.draw import (_txt, _draw_text, _rect, _button, _in_rect, _text_wh,
                            _button_w)

# Geometria menu principale: le hitbox seguono la larghezza del testo localizzato
MENU_START_X = 10
MENU_PAD_X = 16
TITLE_GAP = 20


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
        menu_edit = self.lang_manager.get("menu_edit", "Edit")
        menu_lang = self.lang_manager.get("menu_language", "Language")

        # Etichette visualizzate (gli ID interni restano costanti in inglese)
        menu_display_names = {
            "File": menu_file,
            "Edit": menu_edit,
            "Lang": menu_lang
        }

        # Hitbox ricalcolate ogni frame sulla larghezza del testo renderizzato:
        # le etichette sono localizzate e la lingua puo' cambiare a runtime.
        menu_x = MENU_START_X
        bounds: dict = {}
        for internal_id, display_name in menu_display_names.items():
            tw, _ = _text_wh(display_name, "sm")
            bw = tw + MENU_PAD_X * 2
            bounds[internal_id] = pygame.Rect(menu_x, 0, bw, TOP_BAR_H)
            menu_x += bw
        self._menu_bounds = bounds

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

        # Titolo (a destra dell'ultimo menu, qualunque sia la larghezza localizzata)
        title_x = menu_x + TITLE_GAP
        title_str = "HIDDEN ENGINE"  # nome prodotto: non tradotto
        if self.game_path:
            title_str += f"  |  {self.game_path.name.upper()}"
        if self.scene_path:
            title_str += f"  >  {self.scene_path.name}"
        if getattr(self, "scene_dirty", False):
            title_str += "  " + self._TR("tb_title_modified", "[MODIFIED]*")
        
        _draw_text(self.screen, title_str, "sm", (120, 120, 140), title_x, 7, w - title_x - 100)

    def _get_menu_items(self, menu_name):
        """Restituisce la lista di (label, cmd) per il menu specificato."""
        if menu_name == "File":
            return [
                (self._TR("menu_new_game", "New project..."), "file_new_game"),
                (self._TR("menu_open_game", "Open project..."), "file_open_game"),
                None,
                (self._TR("menu_save_scene", "Save scene"), "file_save_scene"),
                (self._TR("menu_save_as", "Save as..."), "file_save_as"),
                None,
                (self._TR("menu_auditor", "Project auditor..."), "file_auditor"),
                (self._TR("menu_scene_stats", "Scene statistics..."), "file_scene_stats"),
                (self._TR("menu_batch_import", "Batch object import..."), "file_batch_import"),
                None,
                (self._TR("menu_exit_to_gs", "Back to selector"), "file_exit_to_gs"),
                (self._TR("menu_quit", "Quit"), "file_quit"),
            ]
        elif menu_name == "Edit":
            return [
                (self._TR("menu_undo", "Undo") + " (Ctrl+Z)", "edit_undo"),
                (self._TR("menu_redo", "Redo") + " (Ctrl+Y)", "edit_redo"),
                None,
                (self._TR("menu_cut", "Cut") + " (Ctrl+X)", "edit_cut"),
                (self._TR("menu_copy", "Copy") + " (Ctrl+C)", "edit_copy"),
                (self._TR("menu_paste", "Paste") + " (Ctrl+V)", "edit_paste"),
                None,
                (self._TR("menu_preset_save", "Save group..."), "edit_preset_save"),
                (self._TR("menu_preset_insert", "Insert group..."), "edit_preset_insert"),
                None,
                (self._TR("menu_lang_modal", "Translation editor..."), "edit_lang_modal"),
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
        y = h - STATUS_H
        # Background barra con linea di separazione chiara
        _rect(self.screen, STATUS, (0, y, w, STATUS_H))
        pygame.draw.line(self.screen, (60, 60, 75), (0, y), (w, y))

        mx2, my2 = pygame.mouse.get_pos()

        # Hitbox pubblicate per InputHandlers: le larghezze seguono il testo
        # localizzato, quindi il click non puo' piu' essere calcolato a parte
        # con costanti che il rendering non usa (i bottoni tradotti erano piu'
        # larghi della loro hitbox e meta' click andavano persi).
        self._status_hitboxes: dict = {}
        # The three text runs of the bar, as drawn. They share one line, so the
        # only way to know they do not write over each other is to publish
        # where each one actually ended (test_editor_status_bar.py reads this).
        self._status_spans: dict = {}

        # Geometria pulsanti basata sulla nuova altezza
        padding = 6
        btn_h = STATUS_H - (padding * 2)
        btn_y = y + padding

        # Pulsante < SELETTORE (Professional _button) - Nascosto se siamo già lì
        msg_x = 20
        if getattr(self, "state", "") != "game_select":
            back_label = self._TR("tb_back_selector")
            back_w = _button_w(back_label, "sm", icon="close", min_w=STATUS_BTN_MIN_W)
            btn_r = pygame.Rect(10, btn_y, back_w, btn_h)
            hov_back = _in_rect((mx2, my2), btn_r)
            if hov_back: self.active_tooltip = self._TR("tip_btn_back")
            _button(self.screen, btn_r, back_label, hov_back, icon="close")
            self._status_hitboxes["back"] = btn_r
            msg_x = btn_r.right + 20

            # Pulsante SALVA
            if hasattr(self, "scene_path") and self.scene_path:
                save_label = self._TR("tb_save")
                save_w = _button_w(save_label, "sm", icon="save",
                                   min_w=STATUS_BTN_MIN_W)
                save_r = pygame.Rect(btn_r.right + 10, btn_y, save_w, btn_h)
                hov_save = _in_rect((mx2, my2), save_r)
                if hov_save: self.active_tooltip = self._TR("tip_btn_save")

                # Colore dinamico: OK_C se modificato, BTN se salvato
                scol = OK_C if self.scene_dirty else BTN
                _button(self.screen, save_r, save_label, hov_save,
                        active=self.scene_dirty, icon="save", custom_bg=scol)
                self._status_hitboxes["save"] = save_r

                # Pulsante PLAYTEST (avvia la scena corrente in un processo separato)
                play_label = self._TR("tb_play_scene")
                play_w = _button_w(play_label, "sm", icon="play",
                                   min_w=STATUS_BTN_MIN_W)
                play_r = pygame.Rect(save_r.right + 10, btn_y, play_w, btn_h)
                hov_play = _in_rect((mx2, my2), play_r)
                if hov_play: self.active_tooltip = self._TR("tip_btn_play_scene")
                _button(self.screen, play_r, play_label, hov_play, icon="play")
                self._status_hitboxes["play"] = play_r
                msg_x = play_r.right + 25

        # Messaggio status (Chirurgicamente spostato a destra)
        # Centratura verticale nella barra
        ty = y + (STATUS_H - 18) // 2
        msg_w = _draw_text(self.screen, self.status_msg, "sm", self.status_col,
                           msg_x, ty, w // 2 - msg_x)
        self._status_spans["msg"] = (msg_x, msg_x + msg_w)

        # Info destra (Game / Scene / Undo)
        parts = []
        if getattr(self, "game_name", None):
            parts.append(f"{self._TR('tb_game')} {self.game_name}")
        if getattr(self, "scene_path", None):
            parts.append(f"{self._TR('tb_scene')} {self.scene_path.name}")
            if self.scene_dirty: parts.append(self._TR("tb_not_saved"))
        parts.append(f"{self._TR('tb_undo')} {len(self.undo_stack)}")
        
        info = "  |  ".join(parts)
        si_w, si_h = _txt(info, "sm", TXT_DIM).get_size()
        # A long game name plus a long scene name is wider than the room left
        # of it: the block keeps its right edge and loses its head instead of
        # running into the status message.
        info_max = max(120, w - 15 - (msg_x + msg_w + 20))
        si_w = min(si_w, info_max)
        info_x = w - si_w - 15
        si_w = _draw_text(self.screen, info, "sm", TXT_DIM, info_x,
                          y + (STATUS_H - si_h) // 2, info_max)
        self._status_spans["info"] = (info_x, info_x + si_w)

        # Shortcut hint (centrato, solo se c'è spazio sufficiente).
        # La riga intera resta la fonte delle scorciatoie per il pannello F1;
        # qui si mostra solo il puntatore, cosi' la barra non e' un muro di testo.
        hints = self._TR("tb_shortcuts_hint", "F1 = shortcuts")
        hw, hh = _txt(hints, "sm", (75, 75, 95)).get_size()
        hx = (w - hw) // 2
        # The bound on the left is where the status message actually ended, not
        # where it began: a long message used to be written over by this hint.
        if hx > msg_x + msg_w + 20 and hx + hw < info_x - 20:
            _draw_text(self.screen, hints, "sm", (75, 75, 95), hx, y + (STATUS_H - hh)//2)
            self._status_spans["hint"] = (hx, hx + hw)
