"""
editor/mixins/newobj_modal.py

NewObjModalMixin — dialogo creazione nuovo oggetto catalogo + musica: logica + rendering.
"""

import pygame
from pathlib import Path

from editor.constants import (
    ACCENT, BORDER, BTN, BTN_HO,
    TXT, TXT_DIM, TXT_HI, OK_C, ERR_C, WARN_C,
)
from editor.core.io import (
    _load_json, _save_json, _load_catalog, _file_dialog,
)
from editor.ui.draw import (
    _txt, _draw_text, _rect, _button, _in_rect,
)


class NewObjModalMixin:
    """Dialogo '+Nuovo Oggetto' e gestione musica scena."""

    # ─────────────────────────────────────────────────────────────────────────
    # APERTURA / INPUT
    # ─────────────────────────────────────────────────────────────────────────

    def _newobj_open(self):
        self._newobj = {
            "id": "", "icon_path": "", "detection": "circle",
            "radius": 30, "width": 60, "height": 60, "hint": 30,
        }
        self._newobj_field = "id"
        self._newobj_buf   = ""
        self._newobj_modal = True

    def _newobj_key(self, ev):
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
                self._newobj[f] = int(self._newobj_buf)
            except ValueError:
                pass
        self._newobj_buf = ""

    def _newobj_click(self, mx, my_raw, w, h):
        dw, dh = 500, 400
        dx, dy = (w-dw)//2, (h-dh)//2

        if _in_rect((mx, my_raw), (dx+dw-36, dy+8, 26, 22)):
            self._newobj_modal = False; return

        y_id     = dy + 54
        y_icon   = dy + 114
        y_det    = dy + 148
        y_radius = dy + 182
        y_width  = dy + 218
        y_height = dy + 254
        y_hint   = dy + 290
        y_btns   = dy + 334

        if _in_rect((mx, my_raw), (dx+160, y_id, dw-172, 26)):
            self._newobj_commit_field()
            self._newobj_field = "id"
            self._newobj_buf   = self._newobj["id"]; return

        if _in_rect((mx, my_raw), (dx+10, y_icon, dw-50, 28)):
            self._newobj_commit_field()
            p = _file_dialog("Scegli icona PNG",
                             filetypes=[("PNG", "*.png")],
                             initialdir=self.game_path)
            if p:
                self._newobj["icon_path"] = str(p)
            return

        if _in_rect((mx, my_raw), (dx+160, y_det, 90, 26)):
            self._newobj["detection"] = "circle"; return
        if _in_rect((mx, my_raw), (dx+258, y_det, 90, 26)):
            self._newobj["detection"] = "rect";   return

        num_fields = [("radius", y_radius), ("width", y_width),
                      ("height", y_height), ("hint",  y_hint)]
        for fname, fy in num_fields:
            if _in_rect((mx, my_raw), (dx+160, fy, dw-172, 26)):
                self._newobj_commit_field()
                self._newobj_field = fname
                self._newobj_buf   = str(self._newobj.get(fname, ""))
                return

        half = (dw-20)//2-5
        if _in_rect((mx, my_raw), (dx+10, y_btns, half, 34)):
            self._newobj_commit_field()
            self._confirm_newobj(); return
        if _in_rect((mx, my_raw), (dx+10+half+10, y_btns, half, 34)):
            self._newobj_modal = False; return

    def _confirm_newobj(self):
        import shutil
        obj = self._newobj
        oid = obj["id"].strip()
        if not oid:
            self._status("Inserisci un ID oggetto", WARN_C, 3); return
        if any(c["id"] == oid for c in self.catalog):
            self._status(f"ID '{oid}' già presente nel catalogo", ERR_C, 3); return

        icon_rel = ""
        src = Path(obj["icon_path"]) if obj["icon_path"] else None
        if src and src.exists():
            dest_name = f"{oid}_icon{src.suffix}"
            dest = self.game_path / "objects" / dest_name
            (self.game_path / "objects").mkdir(exist_ok=True)
            shutil.copy2(str(src), str(dest))
            icon_rel = f"objects/{dest_name}"
        else:
            self._status("Seleziona un'icona PNG", WARN_C, 3); return

        det   = obj["detection"]
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
        self._newobj_modal = False
        self._status(f"Oggetto '{oid}' aggiunto al catalogo!", OK_C, 4)
        if self._lang_data:
            for lang in self.LANGS:
                self._lang_data.setdefault(lang, {}).setdefault(f"obj_{oid}", "")

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

    def _r_newobj_modal(self, w, h):
        dim = pygame.Surface((w, h), pygame.SRCALPHA)
        dim.fill((0, 0, 0, 160))
        self.screen.blit(dim, (0, 0))

        dw, dh = 500, 400
        dx, dy = (w-dw)//2, (h-dh)//2

        box = pygame.Rect(dx, dy, dw, dh)
        _rect(self.screen, (42, 42, 52), box, radius=8)
        _rect(self.screen, ACCENT, box, 2, radius=8)

        title = _txt("+ Nuovo Oggetto Catalogo", "lg", TXT_HI)
        self.screen.blit(title, (dx + 12, dy + 10))

        mx2, my2 = pygame.mouse.get_pos()
        xr = pygame.Rect(dx + dw - 36, dy + 8, 26, 22)
        _button(self.screen, xr, "X", _in_rect((mx2, my2), xr))

        y = dy + 44
        pygame.draw.line(self.screen, BORDER, (dx, y), (dx + dw, y))
        y += 10

        self._r_newobj_field(dx, y, dw, "ID oggetto:", "id", self._newobj["id"])
        y += 42

        s = _txt("Icona PNG:", "sm", TXT_DIM)
        self.screen.blit(s, (dx + 10, y))
        y += 18
        pick_r   = pygame.Rect(dx + 10, y, dw - 50, 28)
        icon_txt = (Path(self._newobj["icon_path"]).name
                    if self._newobj["icon_path"] else "— clicca per scegliere —")
        icon_c   = TXT if self._newobj["icon_path"] else TXT_DIM
        _rect(self.screen, BTN_HO if _in_rect((mx2, my2), pick_r) else BTN, pick_r, radius=4)
        _rect(self.screen, BORDER, pick_r, 1, radius=4)
        _draw_text(self.screen, icon_txt, "sm", icon_c, dx + 18, y + 6, dw - 70)
        if self._newobj["icon_path"]:
            ic = self._load_img(Path(self._newobj["icon_path"]), (28, 28))
            if ic:
                self.screen.blit(ic, (dx + dw - 42, y + 0))
        y += 34

        s   = _txt("Tipo:", "sm", TXT_DIM)
        self.screen.blit(s, (dx + 10, y))
        det  = self._newobj["detection"]
        cr_r = pygame.Rect(dx + 160, y, 90, 26)
        rc_r = pygame.Rect(dx + 258, y, 90, 26)
        _button(self.screen, cr_r, "Cerchio",  _in_rect((mx2, my2), cr_r), active=(det == "circle"))
        _button(self.screen, rc_r, "Rettang.", _in_rect((mx2, my2), rc_r), active=(det == "rect"))
        y += 34

        show_c = (det == "circle")
        self._r_newobj_field(dx, y, dw, "Raggio (px):",    "radius",
                             str(self._newobj["radius"]),  enabled=show_c);     y += 36
        self._r_newobj_field(dx, y, dw, "Larghezza (px):", "width",
                             str(self._newobj["width"]),   enabled=not show_c); y += 36
        self._r_newobj_field(dx, y, dw, "Altezza (px):",   "height",
                             str(self._newobj["height"]),  enabled=not show_c); y += 36
        self._r_newobj_field(dx, y, dw, "Hint delay (s):", "hint",
                             str(self._newobj["hint"]));                         y += 36

        pygame.draw.line(self.screen, BORDER, (dx, y), (dx + dw, y))
        y += 8
        half   = (dw - 20) // 2 - 5
        add_r  = pygame.Rect(dx + 10,             y, half, 34)
        ann_r  = pygame.Rect(dx + 10 + half + 10, y, half, 34)
        can_add = bool(self._newobj["id"].strip() and self._newobj["icon_path"])
        _button(self.screen, add_r, "+ Aggiungi al catalogo",
                _in_rect((mx2, my2), add_r), active=can_add)
        _button(self.screen, ann_r, "Annulla",
                _in_rect((mx2, my2), ann_r), danger=True)

    def _r_newobj_field(self, dx, y, dw, label, field_id, value, enabled=True):
        lc = TXT if enabled else TXT_DIM
        s  = _txt(label, "sm", lc)
        self.screen.blit(s, (dx + 10, y))
        is_active = (self._newobj_field == field_id and enabled)
        bg = (50, 50, 65) if is_active else (BTN if enabled else (35, 35, 42))
        r  = pygame.Rect(dx + 160, y, dw - 172, 26)
        _rect(self.screen, bg, r, radius=3)
        _rect(self.screen, ACCENT if is_active else BORDER, r, 1, radius=3)
        display = (self._newobj_buf + "|") if is_active else value
        _draw_text(self.screen, display, "mono",
                   TXT_HI if enabled else TXT_DIM, dx + 164, y + 4, dw - 182)
