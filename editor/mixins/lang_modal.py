"""
editor/mixins/lang_modal.py

LangModalMixin — editor traduzioni multi-lingua: logica + rendering.
"""

import pygame
from editor.constants import (
    ACCENT, BORDER, BTN, BTN_HO, BTN_AC,
    TXT, TXT_DIM, TXT_HI, WARN_C, OK_C,
)
from editor.core.io import _load_json, _save_json
from editor.ui.draw import (
    _txt, _draw_text, _rect, _button, _in_rect, _text_wh, _input_box
)


class LangModalMixin:
    """Language editor integrato (modal full-screen)."""

    def __init__(self):
        self._lang_context = "global"
        self._engine_strings = {}  # Cache delle stringhe originali dell'engine (sola lettura)

    # ─────────────────────────────────────────────────────────────────────────
    # APERTURA / SALVATAGGIO
    # ─────────────────────────────────────────────────────────────────────────

    def _load_strings(self):
        self._lang_data = {}
        self._engine_strings = {}
        master_strings_p = self.base_path / "engine" / "assets" / "strings"
        
        for lang in self.LANGS:
            # 1. Carica le basi dal motore (globale) e le tiene separate
            master_p = master_strings_p / f"{lang}.json"
            engine_data = _load_json(master_p) if master_p.exists() else {}
            self._engine_strings[lang] = engine_data.copy()
            
            # 2. Carica/Unisci con quelle del gioco (locale)
            data = engine_data.copy()
            if self.game_path:
                game_p = self.game_path / "strings" / f"{lang}.json"
                if game_p.exists():
                    data.update(_load_json(game_p))
            
            self._lang_data[lang] = data

    def _lang_open(self, context="global", filter_key=None):
        # Rimossa la restrizione game_path per permettere la consultazione
        # delle stringhe Engine anche dal selettore progetti.
        
        self._load_strings()
        self._lang_context = context

        if context == "fx" and filter_key:
            self._lang_keys = [filter_key]
            # Selezione automatica prima cella
            self._lang_sel = (0, 0)
            self._lang_buf = self._lang_cell_value(filter_key, self.LANGS[0])
        else:
            keys_set = set()
            for cat in self.catalog:
                keys_set.add(cat.get("label_key", f"obj_{cat['id']}"))
            for lang_d in self._lang_data.values():
                keys_set.update(lang_d.keys())
            self._lang_keys   = sorted(keys_set)
            self._lang_sel    = None
            self._lang_buf    = ""
            
        self._lang_scroll = 0
        self._lang_dirty  = False
        self._lang_confirm_close = False  # guardia chiusura con modifiche non salvate
        self._lang_modal  = True
        self._lang_cursor = len(self._lang_buf)
        self._lang_all_sel = False
        self._lang_search = ""
        self._lang_search_active = False
        self._lang_filtered_keys = self._lang_keys[:]


    def _lang_save(self):
        if not self.game_path: return
        strings_dir = self.game_path / "strings"
        strings_dir.mkdir(exist_ok=True)
        
        for lang in self.LANGS:
            # Filtriamo: salviamo nel gioco solo ciò che NON è nell'engine 
            # o che è stato sovrascritto con un valore differente.
            combined = self._lang_data.get(lang, {})
            engine   = self._engine_strings.get(lang, {})
            
            game_only_data = {}
            for k, v in combined.items():
                # Se la chiave non è nell'engine, è del gioco (es. TIP_*, obj_*)
                if k not in engine:
                    game_only_data[k] = v
                else:
                    # Se è nell'engine, la salviamo nel gioco SOLO se il valore è diverso
                    # (sovrascrittura locale delle stringhe di sistema)
                    if v != engine[k]:
                        game_only_data[k] = v
            
            # Ordinamento alfabetico per pulizia file JSON
            sorted_data = dict(sorted(game_only_data.items()))
            _save_json(strings_dir / f"{lang}.json", sorted_data)

        self._lang_dirty = False
        self._lang_modal = False

        self._status(self._TR("lm_saved", "Translations saved"), OK_C, 3)

    def _ensure_translation_key(self, key: str, default_value: str = "") -> list:
        """
        Garantisce che 'key' esista come segnaposto vuoto in tutti i file lingua del gioco.
        Scrive solo nei file del gioco (games/<id>/strings/), non in quelli engine.
        Ritorna la lista di lingue in cui la chiave era assente e ora è stata aggiunta.
        """
        if not getattr(self, 'game_path', None):
            return []
        strings_dir = self.game_path / "strings"
        strings_dir.mkdir(exist_ok=True)
        langs = getattr(self, 'LANGS', ['it', 'en', 'de', 'fr', 'es'])
        added_to = []
        for lang in langs:
            lang_file = strings_dir / f"{lang}.json"
            data = _load_json(lang_file) if lang_file.exists() else {}
            if key not in data:
                data[key] = default_value
                _save_json(lang_file, data)
                added_to.append(lang)
        return added_to

    def _cleanup_translation_key(self, key: str) -> bool:
        """
        Rimuove 'key' da tutti i file lingua del gioco.
        Usato quando un effetto bubble_tip viene eliminato.
        Ritorna True se la chiave è stata trovata e rimossa in almeno una lingua.
        """
        if not getattr(self, 'game_path', None):
            return False
        strings_dir = self.game_path / "strings"
        if not strings_dir.exists():
            return False
        langs = getattr(self, 'LANGS', ['it', 'en', 'de', 'fr', 'es'])
        removed = False
        for lang in langs:
            lang_file = strings_dir / f"{lang}.json"
            if not lang_file.exists():
                continue
            data = _load_json(lang_file)
            if key in data:
                del data[key]
                _save_json(lang_file, data)
                removed = True
        return removed

    # ─────────────────────────────────────────────────────────────────────────
    # HELPERS
    # ─────────────────────────────────────────────────────────────────────────

    def _lang_cell_value(self, key: str, lang: str) -> str:
        return self._lang_data.get(lang, {}).get(key, "")

    def _lang_update_filter(self):
        """Aggiorna la lista delle chiavi filtrate in base alla ricerca."""
        if not self._lang_search:
            self._lang_filtered_keys = self._lang_keys[:]
            return

        q = self._lang_search.lower()
        filtered = []
        for k in self._lang_keys:
            # Ricerca nella chiave
            if q in k.lower():
                filtered.append(k)
                continue
            
            # Ricerca nei valori di tutte le lingue
            found = False
            for lang in self.LANGS:
                if q in self._lang_cell_value(k, lang).lower():
                    found = True
                    break
            if found:
                filtered.append(k)
        
        self._lang_filtered_keys = filtered
        # Se la selezione corrente sparisce, la resettiamo
        if self._lang_sel:
            ki, li = self._lang_sel
            # Nota: ki qui è l'indice della vecchia lista filtrata o di quella globale?
            # È meglio resettare se cambiamo ricerca per evitare puntatori a caso.
            self._lang_sel = None
            self._lang_buf = ""
        
        self._lang_scroll = 0

    def _lang_try_close(self) -> bool:
        """Chiude il modale traduzioni. Con modifiche non salvate richiede una seconda
        conferma (prima volta ritorna False senza chiudere), evitando perdita silenziosa."""
        if getattr(self, "_lang_dirty", False) and not getattr(self, "_lang_confirm_close", False):
            self._lang_confirm_close = True
            self._status(self._TR("lm_unsaved", "Unsaved translations: press again to discard, or SAVE"), (230, 170, 60), 4)
            return False
        self._lang_confirm_close = False
        self._lang_modal = False
        return True

    def _lang_commit(self):
        if not self._lang_sel or not self._lang_filtered_keys:
            return
        ki, li = self._lang_sel
        if ki >= len(self._lang_filtered_keys): return
        key  = self._lang_filtered_keys[ki]
        lang = self.LANGS[li]
        self._lang_data.setdefault(lang, {})[key] = self._lang_buf
        self._lang_dirty = True

    # ─────────────────────────────────────────────────────────────────────────
    # INPUT
    # ─────────────────────────────────────────────────────────────────────────

    def _lang_key(self, ev):
        ctrl = (pygame.key.get_mods() & pygame.KMOD_CTRL)
        
        # Gestione input barra di ricerca
        if getattr(self, "_lang_search_active", False):
            if ev.key == pygame.K_ESCAPE or ev.key == pygame.K_RETURN:
                self._lang_search_active = False
            elif ev.key == pygame.K_BACKSPACE:
                self._lang_search = self._lang_search[:-1]
                self._lang_update_filter()
            elif ev.unicode and ev.unicode.isprintable() and not ctrl:
                self._lang_search += ev.unicode
                self._lang_update_filter()
            return

        if not self._lang_sel:
            if ev.key == pygame.K_ESCAPE:
                self._lang_try_close()

            return

        ki, li = self._lang_sel
        key_name = self._lang_filtered_keys[ki] if ki < len(self._lang_filtered_keys) else ""
        lang_code = self.LANGS[li]

        if ev.key == pygame.K_ESCAPE:
            if self._lang_context == "global":
                self._lang_sel = None
                self._lang_buf = ""
                self._lang_all_sel = False
            else:
                self._lang_try_close()

        
        elif ev.key == pygame.K_RETURN:
            self._lang_commit()
            self._lang_all_sel = False
            if self._lang_context == "fx":
                # Salta alla lingua successiva
                if li < len(self.LANGS) - 1:
                    self._lang_sel = (ki, li + 1)
                    self._lang_buf = self._lang_cell_value(key_name, self.LANGS[li+1])
                    self._lang_cursor = len(self._lang_buf)
                else:
                    self._lang_modal = False

            else:
                # Navigazione nella lista filtrata
                next_ki = min(ki + 1, len(self._lang_filtered_keys) - 1)
                self._lang_sel = (next_ki, li)
                self._lang_buf = self._lang_cell_value(self._lang_filtered_keys[next_ki], self.LANGS[li])
                self._lang_cursor = len(self._lang_buf)

        elif ev.key == pygame.K_TAB:
            self._lang_commit()
            self._lang_all_sel = False
            li = (li + 1) % len(self.LANGS)
            self._lang_sel = (ki, li)
            self._lang_buf = self._lang_cell_value(key_name, self.LANGS[li])
            self._lang_cursor = len(self._lang_buf)

        elif ev.key == pygame.K_LEFT:
            self._lang_cursor = max(0, self._lang_cursor - 1)
            self._lang_all_sel = False
        elif ev.key == pygame.K_RIGHT:
            self._lang_cursor = min(len(self._lang_buf), self._lang_cursor + 1)
            self._lang_all_sel = False
        elif ev.key == pygame.K_HOME:
            self._lang_cursor = 0
            self._lang_all_sel = False
        elif ev.key == pygame.K_END:
            self._lang_cursor = len(self._lang_buf)
            self._lang_all_sel = False

        elif ev.key == pygame.K_BACKSPACE:
            if self._lang_all_sel:
                self._lang_buf = ""
                self._lang_cursor = 0
                self._lang_all_sel = False
            elif self._lang_cursor > 0:
                self._lang_buf = self._lang_buf[:self._lang_cursor-1] + self._lang_buf[self._lang_cursor:]
                self._lang_cursor -= 1
        elif ev.key == pygame.K_DELETE:
            if self._lang_all_sel:
                self._lang_buf = ""
                self._lang_cursor = 0
                self._lang_all_sel = False
            elif self._lang_cursor < len(self._lang_buf):
                self._lang_buf = self._lang_buf[:self._lang_cursor] + self._lang_buf[self._lang_cursor+1:]

        elif ctrl and ev.key == pygame.K_a:
            self._lang_all_sel = True
            self._lang_cursor = len(self._lang_buf)

        elif ctrl and ev.key == pygame.K_c:
            from editor.ui.widgets import clipboard_set
            clipboard_set(self._lang_buf)

        elif ctrl and ev.key == pygame.K_v:
            # Incolla da appunti (helper unico in ui/widgets)
            from editor.ui.widgets import clipboard_get
            clipped = clipboard_get()
            if clipped:
                if self._lang_all_sel:
                    self._lang_buf = clipped
                    self._lang_all_sel = False
                    self._lang_cursor = len(clipped)
                else:
                    self._lang_buf = (self._lang_buf[:self._lang_cursor] + clipped
                                      + self._lang_buf[self._lang_cursor:])
                    self._lang_cursor += len(clipped)

        elif ev.unicode and ev.unicode.isprintable() and not ctrl:
            if self._lang_all_sel:
                self._lang_buf = ev.unicode
                self._lang_cursor = 1
                self._lang_all_sel = False
            else:
                self._lang_buf = self._lang_buf[:self._lang_cursor] + ev.unicode + self._lang_buf[self._lang_cursor:]
                self._lang_cursor += 1

    def _lang_click(self, mx, my_raw, w, h):
        is_fx = (getattr(self, "_lang_context", "global") == "fx")
        dw = int(w * (0.8 if is_fx else 0.92))
        dh = int(h * (0.8 if is_fx else 0.88))
        dx = (w - dw) // 2
        dy = (h - dh) // 2

        save_r  = (dx + dw - 160, dy + dh - 40, 150, 30)
        close_r = (dx + dw - 310, dy + dh - 40, 140, 30)

        if _in_rect((mx, my_raw), save_r):
            if self._lang_sel: self._lang_commit()
            self._lang_save(); return
        if _in_rect((mx, my_raw), close_r):
            if self._lang_sel: self._lang_commit()
            self._lang_try_close()
            return

        if not is_fx:
            # Barra di ricerca
            search_r = (dx + 10, dy + 45, dw - 20, 32)
            if _in_rect((mx, my_raw), search_r):
                if self._lang_sel: self._lang_commit()
                self._lang_search_active = True
                self._lang_sel = None
                return
            else:
                self._lang_search_active = False

            add_r = (dx + 10, dy + dh - 40, 160, 30)
            if _in_rect((mx, my_raw), add_r):
                new_key = f"new_key_{len(self._lang_keys)}"
                self._lang_keys.append(new_key)
                for lang in self.LANGS:
                    self._lang_data.setdefault(lang, {})[new_key] = ""
                self._lang_update_filter()
                return

        HEADER_H = 44 if is_fx else 118
        ROW_H    = 50 if is_fx else 28
        KEY_W    = 0 if is_fx else 200
        lang_w   = (dw - KEY_W - 20) // (1 if is_fx else len(self.LANGS))
        content_y = dy + HEADER_H
        content_x = dx + 10

        if is_fx:
            # Lista verticale lingue per FX
            for li, lang in enumerate(self.LANGS):
                cell_r = (content_x, content_y + li * ROW_H, dw - 20, ROW_H - 2)
                if _in_rect((mx, my_raw), cell_r):
                    if self._lang_sel: self._lang_commit()
                    self._lang_sel = (0, li)
                    self._lang_buf = self._lang_cell_value(self._lang_keys[0], lang)
                    self._lang_cursor = len(self._lang_buf)
                    return
        else:
            # Tabella globale
            for ki, key in enumerate(self._lang_filtered_keys):
                ry = content_y + ki * ROW_H - self._lang_scroll * ROW_H
                if ry < dy + HEADER_H or ry > dy + dh - 50: continue
                for li, lang in enumerate(self.LANGS):
                    cx_ = content_x + KEY_W + li * lang_w
                    cell_r = (cx_, ry, lang_w - 4, ROW_H - 2)
                    if _in_rect((mx, my_raw), cell_r):
                        if self._lang_sel: self._lang_commit()
                        self._lang_sel = (ki, li)
                        self._lang_buf = self._lang_cell_value(key, lang)
                        self._lang_cursor = len(self._lang_buf)
                        return

    # ─────────────────────────────────────────────────────────────────────────
    # RENDERING
    # ─────────────────────────────────────────────────────────────────────────

    def _r_lang_modal(self, w, h):
        is_fx = (getattr(self, "_lang_context", "global") == "fx")
        dim = pygame.Surface((w, h), pygame.SRCALPHA)
        dim.fill((0, 0, 0, 180))
        self.screen.blit(dim, (0, 0))

        dw = int(w * (0.8 if is_fx else 0.92))
        dh = int(h * (0.8 if is_fx else 0.88))
        dx = (w - dw) // 2
        dy = (h - dh) // 2

        box = pygame.Rect(dx, dy, dw, dh)
        _rect(self.screen, (42, 42, 52), box, radius=8)
        _rect(self.screen, ACCENT, box, 2, radius=8)

        txt_hdr = "TRADUZIONI FUMETTO" if is_fx else "EDITOR TRADUZIONI"
        title = _txt(txt_hdr, "lg", TXT_HI)
        self.screen.blit(title, (dx + 12, dy + 10))
        
        if is_fx and self._lang_keys:
            key_info = _txt(self._TR("lm_key_label", "Key: {0}").format(self._lang_keys[0]), "sm", TXT_DIM)
            self.screen.blit(key_info, (dx + dw - key_info.get_width() - 12, dy + 16))

        if self._lang_dirty:
            pygame.draw.circle(self.screen, WARN_C, (dx + 16 + title.get_width() + 6, dy + 22), 5)

        HEADER_H = 44
        ROW_H    = 50 if is_fx else 28
        KEY_W    = 0 if is_fx else 200
        lang_w   = (dw - KEY_W - 20) // (1 if is_fx else len(self.LANGS))
        cx       = dx + 10
        cy       = dy + HEADER_H
        mx2, my2 = pygame.mouse.get_pos()

        if is_fx:
            # Rendering verticale per FX (più pulito per una sola chiave)
            HEADER_H = 44
            ROW_H    = 50
            KEY_W    = 0
            lang_w   = (dw - 20)
            cx       = dx + 10
            cy       = dy + HEADER_H
            
            for li, lang in enumerate(self.LANGS):
                ry = cy + li * ROW_H
                is_c = (self._lang_sel == (0, li))
                hov_c = _in_rect((mx2, my2), (cx, ry, dw - 20, ROW_H - 2))
                
                # Lingua Label
                _draw_text(self.screen, lang.upper(), "sm", ACCENT if is_c else TXT_DIM, cx, ry + 16, 40)
                
                # Input Field
                field_r = pygame.Rect(cx + 50, ry + 4, dw - 70, ROW_H - 10)
                val = self._lang_buf if is_c else self._lang_cell_value(self._lang_keys[0], lang)
                all_s = getattr(self, "_lang_all_sel", False) if is_c else False
                _input_box(self.screen, field_r, val, focused=is_c, font="sm", all_selected=all_s)
        else:
            # Traduzione Globale (Tabella)
            HEADER_H = 118
            ROW_H    = 28
            KEY_W    = 200
            lang_w   = (dw - KEY_W - 20) // len(self.LANGS)
            cx       = dx + 10
            cy       = dy + HEADER_H

            # 1. BARRA DI RICERCA
            search_r = pygame.Rect(cx, dy + 48, dw - 20, 32)
            _input_box(self.screen, search_r, self._lang_search, focused=self._lang_search_active, 
                      hint=self._TR("lm_search", "Search keys and translations..."), icon="search", font="sm")

            # 2. HEADERS TABELLA
            _rect(self.screen, (52, 52, 66), (cx, cy - 22, KEY_W, 20))
            _draw_text(self.screen, self._TR("lm_key", "Key"), "sm", TXT_DIM, cx + 4, cy - 20, KEY_W - 8)
            for li, lang in enumerate(self.LANGS):
                lx = cx + KEY_W + li * lang_w
                _rect(self.screen, (52, 52, 66), (lx, cy - 22, lang_w - 4, 20))
                ls = _txt(lang.upper(), "sm", ACCENT)
                self.screen.blit(ls, (lx + (lang_w - ls.get_width()) // 2 - 2, cy - 20))

            pygame.draw.line(self.screen, BORDER, (dx, cy), (dx + dw, cy))

            # 3. CONTENUTO FILTRATO
            clip = pygame.Rect(dx, cy, dw, dh - HEADER_H - 48)
            self.screen.set_clip(clip)
            for ki, key in enumerate(self._lang_filtered_keys):
                ry = cy + ki * ROW_H - self._lang_scroll * ROW_H
                if ry + ROW_H < cy or ry > dy + dh - 48: continue
                row_bg = (54, 54, 66) if ki % 2 == 0 else (46, 46, 58)
                _rect(self.screen, row_bg, (cx, ry, KEY_W, ROW_H - 2))
                is_row = self._lang_sel and self._lang_sel[0] == ki
                _draw_text(self.screen, key, "sm", TXT if is_row else TXT_DIM, cx + 4, ry + 6, KEY_W - 8)
                for li, lang in enumerate(self.LANGS):
                    lx = cx + KEY_W + li * lang_w
                    is_c = (self._lang_sel == (ki, li))
                    hov_c = _in_rect((mx2, my2), (lx, ry, lang_w - 4, ROW_H - 2))
                    cell_bg = BTN_AC if is_c else (BTN_HO if hov_c else row_bg)
                    _rect(self.screen, cell_bg, (lx, ry, lang_w - 4, ROW_H - 2))
                    _rect(self.screen, ACCENT if is_c else BORDER, (lx, ry, lang_w - 4, ROW_H - 2), 1)
                    
                    val = self._lang_buf if is_c else self._lang_cell_value(key, lang)
                    all_s = getattr(self, "_lang_all_sel", False) if is_c else False
                    _input_box(self.screen, pygame.Rect(lx, ry, lang_w - 4, ROW_H - 2), val, 
                              focused=is_c, font="sm", all_selected=all_s)
            self.screen.set_clip(None)

        # Footer
        fy = dy + dh - 44
        pygame.draw.line(self.screen, BORDER, (dx, fy), (dx + dw, fy))
        close_r = pygame.Rect(dx + dw - 310, fy + 8, 140, 28)
        save_r  = pygame.Rect(dx + dw - 160, fy + 8, 150, 28)
        _button(self.screen, close_r, self._TR("lm_cancel", "Cancel (Esc)"),    _in_rect((mx2, my2), close_r))
        _button(self.screen, save_r,  self._TR("lm_save_project", "SAVE PROJECT"),  _in_rect((mx2, my2), save_r), active=self._lang_dirty)
        
        if not is_fx:
            add_r = pygame.Rect(dx + 10, fy + 8, 160, 28)
            _button(self.screen, add_r, self._TR("lm_new_key", "+ New key"), _in_rect((mx2, my2), add_r))
