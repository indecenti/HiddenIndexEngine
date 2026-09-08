"""
editor/mixins/lang_modal.py

LangModalMixin — editor traduzioni multi-lingua: logica + rendering.
"""

import pygame
from editor.constants import (
    ACCENT, BORDER, BTN_HO,
    TXT, TXT_DIM, TXT_HI, WARN_C, OK_C, ERR_C,
)
from editor.core.io import _load_json, _save_json
from editor.mixins.lang_translate import SCOPE_CELL, SCOPE_VISIBLE
from editor.ui.draw import (
    _txt, _draw_text, _rect, _button, _in_rect, _text_wh, _input_box, _clamp,
    _button_w, _scrollbar,
)

# Geometry of the dialog at UI scale 1.0. Everything that holds text is
# derived from the font in _lang_geometry(), which is the only place the layout
# is computed: the renderer, the click handler and the wheel all read it.
LANG_DIALOG_W_RATIO = 0.92
LANG_DIALOG_H_RATIO = 0.88
LANG_FX_W_RATIO = 0.80
LANG_FX_H_RATIO = 0.80
LANG_PAD = 10
LANG_KEY_COL_MIN = 200      # narrowest the key column may get
LANG_KEY_COL_MAX = 420      # and the widest, so the languages keep room
LANG_CELL_GAP = 4
# A cell with no translation is drawn on this, with a matching border, so an
# empty one cannot be mistaken for a short one at a glance.
LANG_MISSING_BG = (74, 42, 42)
LANG_MISSING_BORDER = (140, 70, 70)


class LangModalMixin:
    """Language editor integrato (modal full-screen)."""

    def __init__(self):
        self._lang_context = "global"
        self._engine_strings = {}  # Cache delle stringhe originali dell'engine (sola lettura)

    # ─────────────────────────────────────────────────────────────────────────
    # GEOMETRIA (unica sorgente per rendering, click e rotella)
    # ─────────────────────────────────────────────────────────────────────────

    def _lang_geometry(self, w: int, h: int) -> dict:
        """Every rect of the translation editor, derived once.

        Keys: box, is_fx, row_h, header_h, key_col, lang_w, search, filter,
        table_top, content, visible_rows, max_scroll, footer_y, btn_h.
        """
        is_fx = (getattr(self, "_lang_context", "global") == "fx")
        line_h = _text_wh("Ag", "sm")[1]
        title_h = _text_wh("Ag", "lg")[1]

        dw = int(w * (LANG_FX_W_RATIO if is_fx else LANG_DIALOG_W_RATIO))
        dh = int(h * (LANG_FX_H_RATIO if is_fx else LANG_DIALOG_H_RATIO))
        box = pygame.Rect((w - dw) // 2, (h - dh) // 2, dw, dh)

        btn_h = max(28, line_h + 10)
        footer_y = box.bottom - btn_h - 16
        row_h = max(28, line_h + 10)
        search_h = max(32, line_h + 12)

        if is_fx:
            header_h = title_h + 18
            content = pygame.Rect(box.x + LANG_PAD, box.y + header_h,
                                  dw - LANG_PAD * 2, footer_y - box.y - header_h)
            return {
                "box": box, "is_fx": True, "row_h": max(50, line_h + 30),
                "header_h": header_h, "key_col": 0, "lang_w": content.w,
                "search": pygame.Rect(0, 0, 0, 0),
                "filter": pygame.Rect(0, 0, 0, 0),
                "translate": pygame.Rect(0, 0, 0, 0),
                "table_top": content.y, "content": content,
                "visible_rows": len(self.LANGS), "max_scroll": 0,
                "footer_y": footer_y, "btn_h": btn_h,
            }

        # The key column is as wide as the keys need, within bounds: fixed at
        # 200 px, a longer key or a larger UI scale cut it with an ellipsis.
        keys = getattr(self, "_lang_filtered_keys", None) or self._lang_keys
        widest = max((_text_wh(k, "sm")[0] for k in keys[:400]), default=0)
        key_col = max(LANG_KEY_COL_MIN, min(LANG_KEY_COL_MAX, widest + 16))

        filter_label = self._TR("lm_only_missing", "Only incomplete")
        filter_w = _button_w(filter_label, "sm", min_w=140)
        tr_label = self._TR("tr_button", "Translate...")
        tr_w = _button_w(tr_label, "sm", min_w=130)
        search = pygame.Rect(box.x + LANG_PAD, box.y + title_h + 16,
                             dw - LANG_PAD * 2 - filter_w - tr_w - 16, search_h)
        filter_r = pygame.Rect(search.right + 8, search.y, filter_w, search_h)
        translate_r = pygame.Rect(filter_r.right + 8, search.y, tr_w, search_h)

        col_head_h = line_h + 6
        table_top = search.bottom + 10 + col_head_h
        content = pygame.Rect(box.x + LANG_PAD, table_top,
                              dw - LANG_PAD * 2, max(row_h, footer_y - table_top - 8))
        visible = max(1, content.h // row_h)
        return {
            "box": box, "is_fx": False, "row_h": row_h,
            "header_h": table_top - box.y, "key_col": key_col,
            "lang_w": (content.w - key_col) // len(self.LANGS),
            "search": search, "filter": filter_r, "filter_label": filter_label,
            "translate": translate_r, "translate_label": tr_label,
            "col_head_h": col_head_h,
            "table_top": table_top, "content": content,
            "visible_rows": visible,
            "max_scroll": max(0, len(keys) - visible),
            "footer_y": footer_y, "btn_h": btn_h,
        }

    def _lang_cell_rect(self, geo: dict, row: int, lang_index: int):
        """Rect of one language cell, at the current scroll."""
        y = geo["table_top"] + (row - self._lang_scroll) * geo["row_h"]
        x = geo["content"].x + geo["key_col"] + lang_index * geo["lang_w"]
        return pygame.Rect(x, y, geo["lang_w"] - LANG_CELL_GAP,
                           geo["row_h"] - 2)

    def _lang_completion(self) -> dict:
        """Share of the keys translated, per language, as a percentage."""
        keys = self._lang_keys
        if not keys:
            return {lang: 100 for lang in self.LANGS}
        done = {}
        for lang in self.LANGS:
            filled = sum(1 for k in keys
                         if str(self._lang_cell_value(k, lang)).strip())
            done[lang] = int(round(filled * 100 / len(keys)))
        return done

    def _lang_is_incomplete(self, key: str) -> bool:
        """True when any language has nothing for this key."""
        return any(not str(self._lang_cell_value(key, lang)).strip()
                   for lang in self.LANGS)

    def _lang_modal_wheel(self, dy: int) -> None:
        """Scroll the key list. The effect context has no list to scroll."""
        if getattr(self, "_lang_context", "global") == "fx":
            return
        geo = self._lang_geometry(*self.screen.get_size())
        self._lang_scroll = _clamp(self._lang_scroll - dy, 0, geo["max_scroll"])

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

        # The catalog search matches against these labels.
        self._bump_catalog_rev()

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
        self._lang_only_missing = False
        self._lang_naming = None
        self._lang_name_buf = ""
        self._lang_new_keys = set()
        self._lang_tr_init()
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
        """Aggiorna la lista delle chiavi filtrate: ricerca + solo incomplete."""
        only_missing = getattr(self, "_lang_only_missing", False)
        if not self._lang_search:
            self._lang_filtered_keys = [
                k for k in self._lang_keys
                if not only_missing or self._lang_is_incomplete(k)]
            self._lang_sel = None
            self._lang_buf = ""
            self._lang_scroll = 0
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

        if only_missing:
            filtered = [k for k in filtered if self._lang_is_incomplete(k)]
        self._lang_filtered_keys = filtered
        # La selezione e' un indice nella lista filtrata: dopo un filtro nuovo
        # punterebbe a una chiave diversa, quindi si azzera.
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
        self._bump_catalog_rev()

    # ─────────────────────────────────────────────────────────────────────────
    # INPUT
    # ─────────────────────────────────────────────────────────────────────────

    def _lang_key(self, ev):
        if self._lang_tr_key(ev):
            return
        ctrl = (pygame.key.get_mods() & pygame.KMOD_CTRL)

        # Editor del nome di una chiave appena creata: cattura tutto finche' e' aperto
        if getattr(self, "_lang_naming", None) is not None:
            if ev.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                self._lang_finish_naming(commit=True)
            elif ev.key == pygame.K_ESCAPE:
                self._lang_finish_naming(commit=False)
            elif ev.key == pygame.K_BACKSPACE:
                self._lang_name_buf = self._lang_name_buf[:-1]
            elif ev.unicode and ev.unicode.isprintable() and not ctrl:
                self._lang_name_buf += ev.unicode
            return

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
        """Click inside the dialog, resolved on the rects the renderer drew.

        The geometry used to be restated here, and the two copies disagreed:
        the search box was drawn at dy+48 and hit-tested at dy+45, so its top
        three pixels did nothing, and the row area was clipped three pixels
        away from where clicks stopped being accepted.
        """
        if self._lang_tr_click(mx, my_raw):
            return
        geo = self._lang_geometry(w, h)
        pos = (mx, my_raw)
        footer = getattr(self, "_lang_footer_hitboxes", {})
        empty = pygame.Rect(0, 0, 0, 0)

        if _in_rect(pos, footer.get("save", empty)):
            if self._lang_sel:
                self._lang_commit()
            self._lang_save()
            return
        if _in_rect(pos, footer.get("cancel", empty)):
            if self._lang_sel:
                self._lang_commit()
            self._lang_try_close()
            return

        if not geo["is_fx"]:
            if _in_rect(pos, geo["search"]):
                self._lang_finish_naming(commit=True)
                if self._lang_sel:
                    self._lang_commit()
                self._lang_search_active = True
                self._lang_sel = None
                return
            self._lang_search_active = False

            if _in_rect(pos, geo["filter"]):
                self._lang_toggle_only_missing()
                return

            if _in_rect(pos, geo["translate"]):
                self._lang_tr_request(SCOPE_CELL if self._lang_sel else SCOPE_VISIBLE)
                return

            if _in_rect(pos, footer.get("add", empty)):
                self._lang_add_key()
                return

        if geo["is_fx"]:
            for li, lang in enumerate(self.LANGS):
                cell = pygame.Rect(geo["content"].x,
                                   geo["table_top"] + li * geo["row_h"],
                                   geo["content"].w, geo["row_h"] - 2)
                if _in_rect(pos, cell):
                    if self._lang_sel:
                        self._lang_commit()
                    self._lang_sel = (0, li)
                    self._lang_buf = self._lang_cell_value(self._lang_keys[0], lang)
                    self._lang_cursor = len(self._lang_buf)
                    return
            return

        first = self._lang_scroll
        for ki in range(first, min(len(self._lang_filtered_keys),
                                   first + geo["visible_rows"] + 1)):
            key = self._lang_filtered_keys[ki]
            for li, lang in enumerate(self.LANGS):
                cell = self._lang_cell_rect(geo, ki, li)
                if not geo["content"].contains(cell) and not geo["content"].colliderect(cell):
                    continue
                if _in_rect(pos, cell) and geo["content"].collidepoint(pos):
                    self._lang_finish_naming(commit=True)
                    if self._lang_sel:
                        self._lang_commit()
                    self._lang_sel = (ki, li)
                    self._lang_buf = self._lang_cell_value(key, lang)
                    self._lang_cursor = len(self._lang_buf)
                    return
            # The key column of a key added in this session can be renamed.
            key_cell = pygame.Rect(geo["content"].x,
                                   geo["table_top"] + (ki - first) * geo["row_h"],
                                   geo["key_col"], geo["row_h"] - 2)
            if _in_rect(pos, key_cell) and key in getattr(self, "_lang_new_keys", set()):
                self._lang_start_naming(ki)
                return

    # ─────────────────────────────────────────────────────────────────────────
    # FILTRO E NUOVE CHIAVI
    # ─────────────────────────────────────────────────────────────────────────

    def _lang_toggle_only_missing(self) -> None:
        """List only the keys some language has nothing for."""
        self._lang_only_missing = not getattr(self, "_lang_only_missing", False)
        self._lang_update_filter()

    def _lang_add_key(self) -> None:
        """Add a key and start naming it right away.

        It used to be created as "new_key_12" with no way to rename it, and
        the name is what the game refers to: a key nobody can name is a key
        nobody can use.
        """
        base = self._TR("lm_new_key_name", "new_key")
        name, n = base, 1
        while name in self._lang_keys:
            n += 1
            name = f"{base}_{n}"
        self._lang_keys.append(name)
        self._lang_keys.sort()
        for lang in self.LANGS:
            self._lang_data.setdefault(lang, {})[name] = ""
        self._lang_new_keys = set(getattr(self, "_lang_new_keys", set())) | {name}
        self._lang_dirty = True
        self._bump_catalog_rev()
        self._lang_update_filter()
        if name in self._lang_filtered_keys:
            index = self._lang_filtered_keys.index(name)
            self._lang_scroll = _clamp(
                index - 2, 0,
                max(0, len(self._lang_filtered_keys) - 1))
            self._lang_start_naming(index)

    def _lang_start_naming(self, row: int) -> None:
        """Edit the name of the key on `row`."""
        if row >= len(self._lang_filtered_keys):
            return
        self._lang_sel = None
        self._lang_search_active = False
        self._lang_naming = row
        self._lang_name_buf = self._lang_filtered_keys[row]

    def _lang_finish_naming(self, commit: bool) -> None:
        """Close the name editor, renaming the key when asked and allowed."""
        row = getattr(self, "_lang_naming", None)
        if row is None:
            return
        self._lang_naming = None
        old = self._lang_filtered_keys[row] if row < len(self._lang_filtered_keys) else ""
        new = (self._lang_name_buf or "").strip()
        self._lang_name_buf = ""
        if not commit or not old or not new or new == old:
            return
        if new in self._lang_keys:
            self._status(self._TR("lm_key_exists",
                                  "A key named '{0}' already exists").format(new),
                         WARN_C, 3)
            return
        for lang in self.LANGS:
            values = self._lang_data.setdefault(lang, {})
            values[new] = values.pop(old, "")
        self._lang_keys = sorted(k for k in self._lang_keys if k != old)
        self._lang_keys.append(new)
        self._lang_keys.sort()
        news = set(getattr(self, "_lang_new_keys", set()))
        news.discard(old)
        news.add(new)
        self._lang_new_keys = news
        self._lang_dirty = True
        self._bump_catalog_rev()
        self._lang_update_filter()

    # ─────────────────────────────────────────────────────────────────────────
    # RENDERING
    # ─────────────────────────────────────────────────────────────────────────

    def _r_lang_modal(self, w, h):
        geo = self._lang_geometry(w, h)
        box, is_fx = geo["box"], geo["is_fx"]
        row_h = geo["row_h"]
        mx2, my2 = pygame.mouse.get_pos()
        self._lang_scroll = _clamp(self._lang_scroll, 0, geo["max_scroll"])

        dim = pygame.Surface((w, h), pygame.SRCALPHA)
        dim.fill((0, 0, 0, 180))
        self.screen.blit(dim, (0, 0))
        _rect(self.screen, (42, 42, 52), box, radius=8)
        _rect(self.screen, ACCENT, box, 2, radius=8)

        txt_hdr = (self._TR("lm_title_fx", "BUBBLE TRANSLATIONS") if is_fx
                   else self._TR("lm_title", "TRANSLATION EDITOR"))
        title = _txt(txt_hdr, "lg", TXT_HI)
        self.screen.blit(title, (box.x + 12, box.y + 10))
        if self._lang_dirty:
            pygame.draw.circle(self.screen, WARN_C,
                               (box.x + 18 + title.get_width(),
                                box.y + 12 + title.get_height() // 2), 5)

        if is_fx:
            if self._lang_keys:
                info = _txt(self._TR("lm_key_label", "Key: {0}").format(
                    self._lang_keys[0]), "sm", TXT_DIM)
                self.screen.blit(info, (box.right - info.get_width() - 12,
                                        box.y + 16))
            for li, lang in enumerate(self.LANGS):
                ry = geo["table_top"] + li * row_h
                is_c = (self._lang_sel == (0, li))
                _draw_text(self.screen, lang.upper(), "sm",
                           ACCENT if is_c else TXT_DIM, geo["content"].x, ry + 16, 40)
                field = pygame.Rect(geo["content"].x + 50, ry + 4,
                                    geo["content"].w - 60, row_h - 10)
                value = (self._lang_buf if is_c
                         else self._lang_cell_value(self._lang_keys[0], lang))
                _input_box(self.screen, field, value, focused=is_c, font="sm",
                           all_selected=getattr(self, "_lang_all_sel", False) if is_c
                           else False)
        else:
            self._r_lang_table(geo, mx2, my2)

        self._r_lang_footer(geo, mx2, my2)
        self._lang_tr_poll()
        self._r_lang_translate(w, h)

    def _r_lang_table(self, geo: dict, mx: int, my: int) -> None:
        """Search bar, column headers with their completion, and the rows."""
        box = geo["box"]
        row_h, key_col, lang_w = geo["row_h"], geo["key_col"], geo["lang_w"]
        content = geo["content"]

        _input_box(self.screen, geo["search"], self._lang_search,
                   focused=self._lang_search_active,
                   hint=self._TR("lm_search", "Search keys and translations..."),
                   icon="search", font="sm")
        only_missing = getattr(self, "_lang_only_missing", False)
        _button(self.screen, geo["filter"], geo["filter_label"],
                _in_rect((mx, my), geo["filter"]), active=only_missing)
        _button(self.screen, geo["translate"], geo["translate_label"],
                _in_rect((mx, my), geo["translate"]))

        # Column headers. Each language says how much of the project it covers:
        # this dialog exists to find what is missing, and nothing said so.
        completion = self._lang_completion()
        head_y = geo["table_top"] - geo["col_head_h"]
        _rect(self.screen, (52, 52, 66), (content.x, head_y, key_col, geo["col_head_h"]))
        _draw_text(self.screen, self._TR("lm_key", "Key"), "sm", TXT_DIM,
                   content.x + 4, head_y + 3, key_col - 8)
        for li, lang in enumerate(self.LANGS):
            lx = content.x + key_col + li * lang_w
            done = completion[lang]
            _rect(self.screen, (52, 52, 66),
                  (lx, head_y, lang_w - LANG_CELL_GAP, geo["col_head_h"]))
            label = f"{lang.upper()}  {done}%"
            colour = OK_C if done == 100 else (WARN_C if done >= 60 else ERR_C)
            lw = _text_wh(label, "sm")[0]
            _draw_text(self.screen, label, "sm", colour,
                       lx + max(4, (lang_w - lw) // 2), head_y + 3,
                       lang_w - LANG_CELL_GAP - 8)
        pygame.draw.line(self.screen, BORDER, (box.x, geo["table_top"]),
                         (box.right, geo["table_top"]))

        keys = self._lang_filtered_keys
        if not keys:
            _draw_text(self.screen,
                       self._TR("lm_no_match", "No key matches"), "sm", TXT_DIM,
                       content.x + 6, content.y + 8, content.w - 12)
            return

        prev_clip = self.screen.get_clip()
        self.screen.set_clip(content)
        first = self._lang_scroll
        for ki in range(first, min(len(keys), first + geo["visible_rows"] + 1)):
            key = keys[ki]
            ry = geo["table_top"] + (ki - first) * row_h
            row_bg = (54, 54, 66) if ki % 2 == 0 else (46, 46, 58)
            is_row = bool(self._lang_sel) and self._lang_sel[0] == ki

            _rect(self.screen, row_bg, (content.x, ry, key_col, row_h - 2))
            naming = (getattr(self, "_lang_naming", None) == ki)
            if naming:
                _input_box(self.screen,
                           pygame.Rect(content.x, ry, key_col - 2, row_h - 2),
                           self._lang_name_buf, focused=True, font="sm")
            else:
                _draw_text(self.screen, key, "sm", TXT if is_row else TXT_DIM,
                           content.x + 4, ry + (row_h - 14) // 2, key_col - 8)

            for li, lang in enumerate(self.LANGS):
                cell = self._lang_cell_rect(geo, ki, li)
                is_c = (self._lang_sel == (ki, li))
                value = (self._lang_buf if is_c
                         else self._lang_cell_value(key, lang))
                empty = not str(value).strip()
                if is_c:
                    # Only the cell being edited needs a field: it carries the
                    # cursor and the selection.
                    _input_box(self.screen, cell, value, focused=True, font="sm",
                               all_selected=getattr(self, "_lang_all_sel", False))
                    _rect(self.screen, ACCENT, cell, 1)
                    continue
                hovered = _in_rect((mx, my), cell)
                background = (BTN_HO if hovered
                              else (LANG_MISSING_BG if empty else row_bg))
                _rect(self.screen, background, cell)
                _rect(self.screen, LANG_MISSING_BORDER if empty else BORDER,
                      cell, 1)
                if not empty:
                    _draw_text(self.screen, value, "sm",
                               TXT_HI if hovered else TXT,
                               cell.x + 6, cell.y + (cell.h - 14) // 2,
                               cell.w - 12)
        self.screen.set_clip(prev_clip)

        if geo["max_scroll"] > 0:
            _scrollbar(self.screen, content.right - 5, content.y, 4, content.h,
                       self._lang_scroll, len(keys), geo["visible_rows"])

    def _r_lang_footer(self, geo: dict, mx: int, my: int) -> None:
        """Footer buttons. Widths follow the translated labels."""
        box, btn_h = geo["box"], geo["btn_h"]
        fy = geo["footer_y"]
        pygame.draw.line(self.screen, BORDER, (box.x, fy), (box.right, fy))

        cancel_label = self._TR("lm_cancel", "Cancel (Esc)")
        save_label = self._TR("lm_save_project", "SAVE PROJECT")
        save_w = _button_w(save_label, "sm", min_w=150)
        cancel_w = _button_w(cancel_label, "sm", min_w=140)
        save_r = pygame.Rect(box.right - save_w - 10, fy + 8, save_w, btn_h)
        close_r = pygame.Rect(save_r.left - cancel_w - 10, fy + 8, cancel_w, btn_h)
        _button(self.screen, close_r, cancel_label, _in_rect((mx, my), close_r))
        _button(self.screen, save_r, save_label, _in_rect((mx, my), save_r),
                active=self._lang_dirty)

        hits = {"cancel": close_r, "save": save_r}
        if not geo["is_fx"]:
            add_label = self._TR("lm_new_key", "+ New key")
            add_r = pygame.Rect(box.x + 10, fy + 8,
                                _button_w(add_label, "sm", min_w=160), btn_h)
            _button(self.screen, add_r, add_label, _in_rect((mx, my), add_r))
            hits["add"] = add_r

            shown = len(self._lang_filtered_keys)
            count = self._TR("lm_count", "{shown} of {total} keys").format(
                shown=shown, total=len(self._lang_keys))
            cw = _text_wh(count, "xs")[0]
            _draw_text(self.screen, count, "xs", TXT_DIM,
                       close_r.left - cw - 20, fy + 8 + (btn_h - 12) // 2)
        self._lang_footer_hitboxes = hits
