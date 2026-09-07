"""
editor/mixins/newobj_modal.py

NewObjModalMixin — dialogo creazione nuovo oggetto catalogo + musica: logica + rendering.
"""

import logging
import threading

import pygame
from pathlib import Path

from editor.constants import (
    ACCENT, BORDER, BTN, BTN_HO,
    TXT, TXT_DIM, TXT_HI, OK_C, ERR_C, WARN_C,
)
from editor.core.io import (
    _load_json, _save_json, _load_catalog, _file_dialog,
)
from editor.mixins.batch_import import (
    draw_checkbox, process_image, rembg_available,
)
from editor.ui.draw import (
    _txt, _draw_text, _rect, _button, _in_rect, _text_wh, _button_w, _ui_scale,
)

# Geometry of the dialog at UI scale 1.0. Everything that holds text grows with
# the font: the rows used to advance by fixed pixel steps while their labels
# grew, so above scale 1.0 a label ran into the field under it. And the click
# handler re-derived every row offset with its own literals (54, 114, 148, ...)
# that the renderer only reproduced by accident.
_DLG_W = 500
_LABEL_COL_MIN = 120   # narrowest the label column may get
_LABEL_PAD = 24        # gap between the longest label and the field column
_FIELD_PAD = 12        # right margin of a field inside the dialog
_ROW_GAP = 10       # gap between two rows
_SECTION_GAP = 16   # gap around a separator
_CB_H = 24          # checkbox hitbox height
# Chiavi impostazioni persistite (.editor_settings.json)
_SETTING_REMOVE_BG = "newobj_remove_bg"
_SETTING_AUTOTRIM = "newobj_autotrim"


class NewObjModalMixin:
    """Dialogo '+Nuovo Oggetto' e gestione musica scena."""

    # ─────────────────────────────────────────────────────────────────────────
    # APERTURA / INPUT
    # ─────────────────────────────────────────────────────────────────────────

    def _newobj_open(self):
        settings = self._load_editor_settings()
        self._newobj = {
            "id": "", "icon_path": "", "detection": "circle",
            "radius": 30, "width": 60, "height": 60, "hint": 30,
            # Preferenze di elaborazione icona, persistite tra sessioni
            "remove_bg": bool(settings.get(_SETTING_REMOVE_BG, False)),
            "autotrim":  bool(settings.get(_SETTING_AUTOTRIM, False)),
        }
        self._newobj_field = "id"
        self._newobj_buf   = ""
        # Elaborazione (rembg/trim) in thread: stato busy + handoff risultato
        self._newobj_busy = False
        self._newobj_proc_result = None  # (token, bytes RGBA, (w, h)) dal worker
        self._newobj_proc_error  = None  # (token, messaggio) dal worker
        self._newobj_proc_token  = getattr(self, "_newobj_proc_token", 0) + 1
        self._newobj_pending     = None  # (dest, icon_rel) in attesa del worker
        self._newobj_modal = True

    def _newobj_key(self, ev):
        if getattr(self, "_newobj_busy", False):
            # Durante l'elaborazione solo ESC: annulla (scarta il risultato) e chiude
            if ev.key == pygame.K_ESCAPE:
                self._newobj_cancel_processing()
                self._newobj_modal = False
            return
        field = self._newobj_field
        if ev.key == pygame.K_ESCAPE:
            self._newobj_modal = False; return
        if ev.key == pygame.K_RETURN:
            self._newobj_commit_field(); return
        if ev.key == pygame.K_TAB:
            self._newobj_commit_field()
            fields = ["id", "radius", "width", "height", "hint"]
            idx = fields.index(field) if field in fields else 0
            self._newobj_field = fields[(idx + 1) % len(fields)]
            self._newobj_buf   = str(self._newobj.get(self._newobj_field, ""))
            return
        if ev.key == pygame.K_BACKSPACE:
            self._newobj_buf = self._newobj_buf[:-1]
        elif ev.unicode and ev.unicode.isprintable():
            self._newobj_buf += ev.unicode

    def _newobj_commit_field(self):
        f = self._newobj_field
        if f == "id":
            self._newobj["id"] = self._newobj_buf.strip().replace(" ", "_")
        elif f in ("radius", "width", "height", "hint"):
            try:
                v = int(self._newobj_buf)
                # Clamp a minimi sensati: raggio/dimensioni >= 1, hint >= 0.
                # Zero/negativi produrrebbero un oggetto senza area valida nel catalogo.
                self._newobj[f] = max(0, v) if f == "hint" else max(1, v)
            except ValueError:
                pass
        self._newobj_buf = ""

    def _newobj_click(self, mx, my_raw, w, h):
        """Click inside the dialog, resolved on the rects the renderer drew.

        The offsets used to be written a second time here, as literals that
        matched the ones the renderer accumulated only as long as nobody
        touched either. `w` and `h` are kept for the signature the router
        calls with.
        """
        hits = getattr(self, "_newobj_hitboxes", None)
        if not hits:
            return                       # not drawn yet: nothing to hit
        pos = (mx, my_raw)

        def hit(name) -> bool:
            r = hits.get(name)
            return bool(r) and _in_rect(pos, r)

        if getattr(self, "_newobj_busy", False):
            # Durante l'elaborazione: solo X/Annulla (scartano il risultato)
            if hit("close") or hit("cancel"):
                self._newobj_cancel_processing()
                self._newobj_modal = False
            return

        if hit("close") or hit("cancel"):
            self._newobj_modal = False
            return

        if hit("id"):
            self._newobj_commit_field()
            self._newobj_field = "id"
            self._newobj_buf = self._newobj["id"]
            return

        if hit("icon"):
            self._newobj_commit_field()
            picked = _file_dialog(self._TR("nob_pick_icon_title", "Choose a PNG icon"),
                                  filetypes=[("PNG", "*.png")],
                                  initialdir=self.game_path)
            if picked:
                self._newobj["icon_path"] = str(picked)
            return

        if hit("type_circle"):
            self._newobj["detection"] = "circle"
            return
        if hit("type_rect"):
            self._newobj["detection"] = "rect"
            return

        for field in ("radius", "width", "height", "hint"):
            if hit(field):
                self._newobj_commit_field()
                self._newobj_field = field
                self._newobj_buf = str(self._newobj.get(field, ""))
                return

        # Toggle elaborazione icona (persistiti in .editor_settings.json)
        if hit("remove_bg"):
            self._newobj["remove_bg"] = not self._newobj.get("remove_bg", False)
            self._save_editor_setting(_SETTING_REMOVE_BG, self._newobj["remove_bg"])
            return
        if hit("autotrim"):
            self._newobj["autotrim"] = not self._newobj.get("autotrim", False)
            self._save_editor_setting(_SETTING_AUTOTRIM, self._newobj["autotrim"])
            return

        if hit("add"):
            self._newobj_commit_field()
            self._confirm_newobj()
            return

    def _confirm_newobj(self):
        import shutil
        obj = self._newobj
        oid = obj["id"].strip()
        if getattr(self, "_newobj_busy", False):
            return
        if not oid:
            self._status(self._TR("nob_need_id", "Enter an object ID"), WARN_C, 3); return
        if any(c["id"] == oid for c in self.catalog):
            self._status(self._TR("nob_id_exists", "ID '{0}' already in the catalog").format(oid), ERR_C, 3); return

        src = Path(obj["icon_path"]) if obj["icon_path"] else None
        if not (src and src.exists()):
            self._status(self._TR("nob_select_png", "Select a PNG icon"), WARN_C, 3); return

        (self.game_path / "objects").mkdir(exist_ok=True)
        if obj.get("remove_bg") or obj.get("autotrim"):
            # Icona rielaborata in thread: salvata sempre come PNG (alpha)
            dest_name = f"{oid}_icon.png"
            self._newobj_start_processing(
                src, self.game_path / "objects" / dest_name,
                f"objects/{dest_name}")
            return

        dest_name = f"{oid}_icon{src.suffix}"
        shutil.copy2(str(src), str(self.game_path / "objects" / dest_name))
        self._newobj_register(f"objects/{dest_name}")

    def _newobj_register(self, icon_rel: str):
        """Registra l'entry nel catalogo locale, ricarica e chiude il modale."""
        obj = self._newobj
        oid = obj["id"].strip()
        det = obj["detection"]
        entry = {
            "id": oid, "label_key": f"obj_{oid}", "icon": icon_rel,
            "default_detection": det, "default_hint_delay": obj["hint"], "tags": [],
        }
        if det == "circle":
            entry["default_radius"] = obj["radius"]
        else:
            entry["default_width"]  = obj["width"]
            entry["default_height"] = obj["height"]

        cat_path = self.game_path / "objects_catalog.json"
        cat_data = _load_json(cat_path)
        cat_data.setdefault("objects", []).append(entry)
        _save_json(cat_path, cat_data)
        self.catalog = _load_catalog(self.game_name)
        self._bump_catalog_rev()
        self._newobj_modal = False
        self._status(self._TR("nob_added", "Object '{0}' added to the catalog").format(oid), OK_C, 4)
        if self._lang_data:
            for lang in self.LANGS:
                self._lang_data.setdefault(lang, {}).setdefault(f"obj_{oid}", "")
            self._bump_catalog_rev()   # the catalog search reads these labels

    # ─────────────────────────────────────────────────────────────────────────
    # ELABORAZIONE ICONA (rembg / auto-ritaglio in thread)
    # ─────────────────────────────────────────────────────────────────────────

    def _newobj_start_processing(self, src: Path, dest: Path, icon_rel: str):
        """
        Avvia rimozione sfondo AI e/o auto-ritaglio in un thread separato
        (pattern img_editor: il worker tocca solo dati locali, il risultato
        e' applicato nel loop principale da _newobj_poll).
        """
        obj = self._newobj
        if obj.get("remove_bg") and not rembg_available():
            self._status(self._TR("nob_rembg_missing", "rembg is not installed: turn off 'Remove background (AI)'"),
                         WARN_C, 4)
            return
        token = self._newobj_proc_token
        self._newobj_busy = True
        self._newobj_pending = (dest, icon_rel)
        self._newobj_proc_result = None
        self._newobj_proc_error = None
        self._status(self._TR("nob_processing_icon", "Processing the icon..."), ACCENT, 2)
        remove_bg = bool(obj.get("remove_bg"))
        autotrim = bool(obj.get("autotrim"))

        def worker() -> None:
            try:
                surf = process_image(src, remove_bg, autotrim)
                raw = pygame.image.tobytes(surf, "RGBA")
                self._newobj_proc_result = (token, raw, surf.get_size())
            except Exception as exc:
                logging.error(f"[NEWOBJ] Elaborazione icona fallita: {exc}")
                self._newobj_proc_error = (token, str(exc))

        threading.Thread(target=worker, daemon=True, name="newobj_process").start()

    def _newobj_cancel_processing(self):
        """Invalida l'elaborazione in corso: il risultato del worker e' scartato."""
        self._newobj_proc_token += 1
        self._newobj_busy = False
        self._newobj_pending = None

    def _newobj_poll(self):
        """
        Applica nel loop principale (render) il risultato del worker.
        I risultati con token diverso appartengono a sessioni chiuse: scartati.
        """
        err = getattr(self, "_newobj_proc_error", None)
        if err is not None:
            self._newobj_proc_error = None
            if err[0] == self._newobj_proc_token:
                self._newobj_busy = False
                self._newobj_pending = None
                self._status(self._TR("err_processing", "Processing error: {0}").format(err[1]), ERR_C, 4)
            return
        res = getattr(self, "_newobj_proc_result", None)
        if res is None:
            return
        self._newobj_proc_result = None
        token, raw, size = res
        if token != self._newobj_proc_token or not self._newobj_pending:
            return  # Elaborazione annullata o di una sessione precedente
        self._newobj_busy = False
        dest, icon_rel = self._newobj_pending
        self._newobj_pending = None
        surf = pygame.image.frombytes(raw, size, "RGBA")
        dest.parent.mkdir(exist_ok=True)
        pygame.image.save(surf, str(dest))
        self._newobj_register(icon_rel)

    # ─────────────────────────────────────────────────────────────────────────
    # MUSICA
    # ─────────────────────────────────────────────────────────────────────────

    def _add_music_dialog(self):
        """Apre la modale interna per la selezione della musica."""
        if not self.game_path: 
            return
        self._music_modal_open()

    # ─────────────────────────────────────────────────────────────────────────
    # RENDERING
    # ─────────────────────────────────────────────────────────────────────────

    # Labels of the "label: [field]" rows, in the order they are drawn.
    _NEWOBJ_LABELS = (
        ("nob_id", "Object ID:"),
        ("nob_type", "Type:"),
        ("nob_radius", "Radius (px):"),
        ("nob_width", "Width (px):"),
        ("nob_height", "Height (px):"),
        ("nob_hint", "Hint delay (s):"),
    )

    def _newobj_row_h(self) -> int:
        """Height of one labelled row, following the font of its label."""
        return max(26, _text_wh("Ag", "sm")[1] + 8)

    def _newobj_label_col(self) -> int:
        """X of the field column: as far right as the longest label needs.

        A fixed column truncated the longest translated label ("Hinweis-
        Verzoegerung (s):" became "Hinweis-Verzo...") as soon as the UI scale
        or the language grew it.
        """
        widest = max(_text_wh(self._TR(key, default), "sm")[0]
                     for key, default in self._NEWOBJ_LABELS)
        return max(_LABEL_COL_MIN, widest + _LABEL_PAD)

    def _r_newobj_modal(self, w, h):
        # Applica l'eventuale risultato del worker di elaborazione (main loop)
        self._newobj_poll()
        if not self._newobj_modal:
            return  # il poll puo' aver registrato l'oggetto e chiuso il modale

        mx2, my2 = pygame.mouse.get_pos()
        busy = getattr(self, "_newobj_busy", False)
        row_h = self._newobj_row_h()
        label_h = _text_wh("Ag", "sm")[1]
        title_h = _text_wh("Ag", "lg")[1]
        show_c = (self._newobj["detection"] == "circle")

        label_col = self._newobj_label_col()
        dw = max(int(round(_DLG_W * _ui_scale())),
                 label_col + _LABEL_COL_MIN + _FIELD_PAD + 20)
        # The dialog is exactly as tall as the rows it has to stack.
        dh = (10 + title_h + _SECTION_GAP + _ROW_GAP
              + row_h + _ROW_GAP
              + label_h + 2 + row_h + 2 + 2 + _ROW_GAP
              + row_h + _ROW_GAP
              + (row_h + _ROW_GAP) * 4
              + _CB_H + _SECTION_GAP
              + 8 + row_h + 8 + 10)
        dx, dy = (w - dw) // 2, max(10, (h - dh) // 2)

        dim = pygame.Surface((w, h), pygame.SRCALPHA)
        dim.fill((0, 0, 0, 160))
        self.screen.blit(dim, (0, 0))

        box = pygame.Rect(dx, dy, dw, dh)
        _rect(self.screen, (42, 42, 52), box, radius=8)
        _rect(self.screen, ACCENT, box, 2, radius=8)

        # Hitboxes published for _newobj_click: one geometry, not two.
        hits: dict = {}
        self._newobj_hitboxes = hits

        self.screen.blit(_txt(self._TR("nob_title", "+ New catalog object"),
                              "lg", TXT_HI), (dx + 12, dy + 10))
        close_r = pygame.Rect(dx + dw - 36, dy + 8, 26, 22)
        _button(self.screen, close_r, "X", _in_rect((mx2, my2), close_r))
        hits["close"] = close_r
        if busy:
            note = _txt(self._TR("nob_processing", "Processing..."), "sm", ACCENT)
            self.screen.blit(note, (close_r.left - note.get_width() - 8, dy + 14))

        y = dy + 10 + title_h + _SECTION_GAP
        pygame.draw.line(self.screen, BORDER, (dx, y), (dx + dw, y))
        y += _ROW_GAP

        hits["id"] = self._r_newobj_field(
            dx, y, dw, self._TR("nob_id", "Object ID:"), "id", self._newobj["id"])
        y += row_h + _ROW_GAP

        self.screen.blit(_txt(self._TR("nob_png_icon", "PNG icon:"), "sm", TXT_DIM),
                         (dx + 10, y))
        y += label_h + 2
        pick_r = pygame.Rect(dx + 10, y, dw - 20, row_h + 2)
        icon_txt = (Path(self._newobj["icon_path"]).name
                    if self._newobj["icon_path"]
                    else self._TR("nob_pick_icon", "- click to choose -"))
        icon_c = TXT if self._newobj["icon_path"] else TXT_DIM
        _rect(self.screen, BTN_HO if _in_rect((mx2, my2), pick_r) else BTN,
              pick_r, radius=4)
        _rect(self.screen, BORDER, pick_r, 1, radius=4)
        thumb = row_h
        _draw_text(self.screen, icon_txt, "sm", icon_c, pick_r.x + 8,
                   pick_r.y + (pick_r.h - label_h) // 2, pick_r.w - thumb - 24)
        if self._newobj["icon_path"]:
            ic = self._load_img(Path(self._newobj["icon_path"]), (thumb, thumb))
            if ic:
                self.screen.blit(ic, (pick_r.right - thumb - 6, pick_r.y + 1))
        hits["icon"] = pick_r
        y += pick_r.h + 2 + _ROW_GAP

        self.screen.blit(_txt(self._TR("nob_type", "Type:"), "sm", TXT_DIM),
                         (dx + 10, y + (row_h - label_h) // 2))
        circle_label = self._TR("nob_circle", "Circle")
        rect_label = self._TR("nob_rect", "Rect.")
        cr_r = pygame.Rect(dx + label_col, y,
                           _button_w(circle_label, "sm", min_w=90), row_h)
        rc_r = pygame.Rect(cr_r.right + 8, y,
                           _button_w(rect_label, "sm", min_w=90), row_h)
        _button(self.screen, cr_r, circle_label, _in_rect((mx2, my2), cr_r),
                active=show_c)
        _button(self.screen, rc_r, rect_label, _in_rect((mx2, my2), rc_r),
                active=not show_c)
        hits["type_circle"], hits["type_rect"] = cr_r, rc_r
        y += row_h + _ROW_GAP

        for field, key, default, enabled in (
                ("radius", "nob_radius", "Radius (px):", show_c),
                ("width", "nob_width", "Width (px):", not show_c),
                ("height", "nob_height", "Height (px):", not show_c),
                ("hint", "nob_hint", "Hint delay (s):", True)):
            hits[field] = self._r_newobj_field(
                dx, y, dw, self._TR(key, default), field,
                str(self._newobj[field]), enabled=enabled)
            y += row_h + _ROW_GAP

        # Opzioni di elaborazione icona (persistite tra sessioni)
        cb_w = (dw - 30) // 2
        rm_r = pygame.Rect(dx + 10, y, cb_w, _CB_H)
        at_r = pygame.Rect(dx + 20 + cb_w, y, cb_w, _CB_H)
        draw_checkbox(self.screen, rm_r,
                      self._TR("nob_remove_bg", "Remove background (AI)"),
                      self._newobj.get("remove_bg", False), enabled=not busy)
        draw_checkbox(self.screen, at_r,
                      self._TR("nob_autotrim", "Auto-crop"),
                      self._newobj.get("autotrim", False), enabled=not busy)
        hits["remove_bg"], hits["autotrim"] = rm_r, at_r
        y += _CB_H + _SECTION_GAP

        pygame.draw.line(self.screen, BORDER, (dx, y), (dx + dw, y))
        y += 8
        half = (dw - 30) // 2
        add_r = pygame.Rect(dx + 10, y, half, row_h + 8)
        ann_r = pygame.Rect(add_r.right + 10, y, half, row_h + 8)
        can_add = bool(self._newobj["id"].strip() and self._newobj["icon_path"]
                       and not busy)
        add_label = (self._TR("nob_processing", "Processing...") if busy
                     else self._TR("nob_add_to_catalog", "+ Add to catalog"))
        _button(self.screen, add_r, add_label, _in_rect((mx2, my2), add_r),
                active=can_add)
        _button(self.screen, ann_r, self._TR("btn_cancel", "Cancel"),
                _in_rect((mx2, my2), ann_r), danger=True)
        hits["add"], hits["cancel"] = add_r, ann_r

    def _r_newobj_field(self, dx, y, dw, label, field_id, value, enabled=True):
        """Draw one "label: [field]" row. Returns the rect of the field."""
        row_h = self._newobj_row_h()
        label_h = _text_wh("Ag", "sm")[1]
        label_col = self._newobj_label_col()
        lc = TXT if enabled else TXT_DIM
        _draw_text(self.screen, label, "sm", lc, dx + 10,
                   y + (row_h - label_h) // 2, label_col - 20)
        is_active = (self._newobj_field == field_id and enabled)
        bg = (50, 50, 65) if is_active else (BTN if enabled else (35, 35, 42))
        r = pygame.Rect(dx + label_col, y, dw - label_col - _FIELD_PAD, row_h)
        _rect(self.screen, bg, r, radius=3)
        _rect(self.screen, ACCENT if is_active else BORDER, r, 1, radius=3)
        display = (self._newobj_buf + "|") if is_active else value
        _draw_text(self.screen, display, "mono",
                   TXT_HI if enabled else TXT_DIM, r.x + 6,
                   r.y + (row_h - _text_wh("Ag", "mono")[1]) // 2, r.w - 12)
        return r
