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
    _txt, _draw_text, _rect, _button, _in_rect,
)

# Geometria dialogo: altezza estesa per la riga delle opzioni di elaborazione
_DLG_W, _DLG_H = 500, 410
# Offset verticali delle righe aggiunte (condivisi tra hit-test e rendering)
_Y_PROC = 326   # checkbox "Rimuovi sfondo (AI)" / "Auto-ritaglio"
_Y_BTNS = 364   # riga bottoni conferma/annulla
_CB_H = 24      # altezza hitbox checkbox
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
        dw, dh = _DLG_W, _DLG_H
        dx, dy = (w-dw)//2, (h-dh)//2

        half     = (dw-20)//2-5
        y_btns   = dy + _Y_BTNS
        close_r  = (dx+dw-36, dy+8, 26, 22)
        cancel_r = (dx+10+half+10, y_btns, half, 34)

        if getattr(self, "_newobj_busy", False):
            # Durante l'elaborazione: solo X/Annulla (scartano il risultato)
            if _in_rect((mx, my_raw), close_r) or _in_rect((mx, my_raw), cancel_r):
                self._newobj_cancel_processing()
                self._newobj_modal = False
            return

        if _in_rect((mx, my_raw), close_r):
            self._newobj_modal = False; return

        y_id     = dy + 54
        y_icon   = dy + 114
        y_det    = dy + 148
        y_radius = dy + 182
        y_width  = dy + 218
        y_height = dy + 254
        y_hint   = dy + 290
        y_proc   = dy + _Y_PROC

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

        # Toggle elaborazione icona (persistiti in .editor_settings.json)
        cb_w = (dw - 30) // 2
        if _in_rect((mx, my_raw), (dx+10, y_proc, cb_w, _CB_H)):
            self._newobj["remove_bg"] = not self._newobj.get("remove_bg", False)
            self._save_editor_setting(_SETTING_REMOVE_BG, self._newobj["remove_bg"])
            return
        if _in_rect((mx, my_raw), (dx+20+cb_w, y_proc, cb_w, _CB_H)):
            self._newobj["autotrim"] = not self._newobj.get("autotrim", False)
            self._save_editor_setting(_SETTING_AUTOTRIM, self._newobj["autotrim"])
            return

        if _in_rect((mx, my_raw), (dx+10, y_btns, half, 34)):
            self._newobj_commit_field()
            self._confirm_newobj(); return
        if _in_rect((mx, my_raw), cancel_r):
            self._newobj_modal = False; return

    def _confirm_newobj(self):
        import shutil
        obj = self._newobj
        oid = obj["id"].strip()
        if getattr(self, "_newobj_busy", False):
            return
        if not oid:
            self._status("Inserisci un ID oggetto", WARN_C, 3); return
        if any(c["id"] == oid for c in self.catalog):
            self._status(f"ID '{oid}' già presente nel catalogo", ERR_C, 3); return

        src = Path(obj["icon_path"]) if obj["icon_path"] else None
        if not (src and src.exists()):
            self._status("Seleziona un'icona PNG", WARN_C, 3); return

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
        self._newobj_modal = False
        self._status(f"Oggetto '{oid}' aggiunto al catalogo!", OK_C, 4)
        if self._lang_data:
            for lang in self.LANGS:
                self._lang_data.setdefault(lang, {}).setdefault(f"obj_{oid}", "")

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
            self._status("rembg non installato: disattiva 'Rimuovi sfondo (AI)'",
                         WARN_C, 4)
            return
        token = self._newobj_proc_token
        self._newobj_busy = True
        self._newobj_pending = (dest, icon_rel)
        self._newobj_proc_result = None
        self._newobj_proc_error = None
        self._status("Elaborazione icona in corso...", ACCENT, 2)
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
                self._status(f"Errore elaborazione: {err[1]}", ERR_C, 4)
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

    def _r_newobj_modal(self, w, h):
        # Applica l'eventuale risultato del worker di elaborazione (main loop)
        self._newobj_poll()
        if not self._newobj_modal:
            return  # il poll puo' aver registrato l'oggetto e chiuso il modale

        dim = pygame.Surface((w, h), pygame.SRCALPHA)
        dim.fill((0, 0, 0, 160))
        self.screen.blit(dim, (0, 0))

        dw, dh = _DLG_W, _DLG_H
        dx, dy = (w-dw)//2, (h-dh)//2
        busy = getattr(self, "_newobj_busy", False)

        box = pygame.Rect(dx, dy, dw, dh)
        _rect(self.screen, (42, 42, 52), box, radius=8)
        _rect(self.screen, ACCENT, box, 2, radius=8)

        title = _txt("+ Nuovo Oggetto Catalogo", "lg", TXT_HI)
        self.screen.blit(title, (dx + 12, dy + 10))
        if busy:
            s = _txt("Elaborazione in corso...", "sm", ACCENT)
            self.screen.blit(s, (dx + dw - s.get_width() - 44, dy + 14))

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

        # Opzioni di elaborazione icona (persistite tra sessioni)
        cb_w = (dw - 30) // 2
        draw_checkbox(self.screen, pygame.Rect(dx + 10, y, cb_w, _CB_H),
                      "Rimuovi sfondo (AI)", self._newobj.get("remove_bg", False),
                      enabled=not busy)
        draw_checkbox(self.screen, pygame.Rect(dx + 20 + cb_w, y, cb_w, _CB_H),
                      "Auto-ritaglio", self._newobj.get("autotrim", False),
                      enabled=not busy)
        y += 30

        pygame.draw.line(self.screen, BORDER, (dx, y), (dx + dw, y))
        y += 8
        half   = (dw - 20) // 2 - 5
        add_r  = pygame.Rect(dx + 10,             y, half, 34)
        ann_r  = pygame.Rect(dx + 10 + half + 10, y, half, 34)
        can_add = bool(self._newobj["id"].strip() and self._newobj["icon_path"]
                       and not busy)
        add_label = "Elaborazione..." if busy else "+ Aggiungi al catalogo"
        _button(self.screen, add_r, add_label,
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
