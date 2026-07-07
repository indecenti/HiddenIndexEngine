"""
editor/mixins/presets.py

PresetsMixin — gruppi di oggetti riutilizzabili tra scene.

Un preset salva una selezione multipla come lista di oggetti con posizioni
relative al bounding box del gruppo. L'inserimento piazza il gruppo al centro
della vista corrente e lo seleziona. Persistenza globale (tutti i giochi) in
.editor_object_presets.json nella root del repo.

UI basata su stack modale unificato (editor.modal_stack) + widget layer
(editor/ui/widgets.py): nessun flag booleano aggiuntivo.
"""

import copy
import logging
import time
from pathlib import Path
from typing import Callable, Optional

import pygame

from editor.constants import (
    PANEL, BORDER, TXT, TXT_HI, TXT_DIM, ACCENT, OK_C, ERR_C, WARN_C,
)
from editor.ui.draw import _rect, _txt, _draw_text, _in_rect
from editor.ui.widgets import Button, InputBox, ScrollList, WidgetGroup

logger = logging.getLogger(__name__)

PRESETS_FILENAME = ".editor_object_presets.json"
PRESET_NAME_MAX = 40
# Campi runtime da NON serializzare nel preset
_PRESET_STRIP_KEYS = ("found",)

# Geometria modali
_SAVE_W, _SAVE_H = 420, 170
_LIST_W, _LIST_H = 460, 420
_LIST_ITEM_H = 34
_MODAL_PAD = 20
_OVERLAY_ALPHA = 150
_BTN_W, _BTN_H = 110, 30


class PresetsMixin:
    """Salvataggio/inserimento gruppi di oggetti."""

    # ── Persistenza ──────────────────────────────────────────────────────────

    def _presets_path(self) -> Path:
        return Path(self.base_path) / PRESETS_FILENAME

    def _presets_load(self) -> list:
        path = self._presets_path()
        if not path.exists():
            return []
        try:
            import json
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data.get("presets", []) if isinstance(data, dict) else []
        except Exception:
            logger.exception("Lettura preset fallita: %s", path)
            return []

    def _presets_write(self, presets: list) -> bool:
        from engine.utils import safe_write_json
        try:
            safe_write_json(self._presets_path(), {"presets": presets})
            return True
        except Exception:
            logger.exception("Scrittura preset fallita")
            return False

    # ── Operazioni ───────────────────────────────────────────────────────────

    def _preset_from_selection(self, name: str) -> Optional[dict]:
        """Crea il dict preset dalla selezione corrente (posizioni relative)."""
        objs_sel = self._get_objs_selection()
        if not objs_sel:
            return None
        boxes = [self._get_obj_bbox(o) for o in objs_sel]
        x_min = min(b[0] for b in boxes)
        y_min = min(b[1] for b in boxes)
        items = []
        for obj in objs_sel:
            item = copy.deepcopy(obj)
            for key in _PRESET_STRIP_KEYS:
                item.pop(key, None)
            item["x"] = round(obj.get("x", 0) - x_min)
            item["y"] = round(obj.get("y", 0) - y_min)
            items.append(item)
        return {"name": name, "created": int(time.time()), "objects": items}

    def _preset_save_selection(self, name: str) -> None:
        name = name.strip()[:PRESET_NAME_MAX]
        if not name:
            self._status("Nome preset vuoto", WARN_C, 2)
            return
        preset = self._preset_from_selection(name)
        if not preset:
            self._status("Nessuna selezione da salvare", WARN_C, 2)
            return
        presets = self._presets_load()
        # Stesso nome = sovrascrittura
        presets = [p for p in presets if p.get("name") != name]
        presets.append(preset)
        if self._presets_write(presets):
            self._status(
                f"Preset '{name}' salvato ({len(preset['objects'])} oggetti)", OK_C, 3)
        else:
            self._status("Errore salvataggio preset", ERR_C, 3)

    def _preset_insert(self, preset: dict) -> None:
        """Inserisce il gruppo al centro della vista corrente e lo seleziona."""
        items = preset.get("objects", [])
        if not items or not self.scene_data:
            return
        cr = self._canvas_rect()
        cx, cy = self._s2r(cr.centerx, cr.centery)
        # Bbox del preset per centrare il gruppo
        w_max = max((it.get("x", 0) + it.get("width", it.get("radius", 30) * 2))
                    for it in items)
        h_max = max((it.get("y", 0) + it.get("height", it.get("radius", 30) * 2))
                    for it in items)
        off_x = self._snap(cx - w_max / 2)
        off_y = self._snap(cy - h_max / 2)

        self._push_undo(f"Inserisci preset '{preset.get('name', '')}'")
        objs = self.scene_data.setdefault("objects", [])
        first_new = len(objs)
        for it in items:
            new_obj = copy.deepcopy(it)
            new_obj["x"] = round(it.get("x", 0) + off_x)
            new_obj["y"] = round(it.get("y", 0) + off_y)
            objs.append(new_obj)
        self.selected_indices = list(range(first_new, len(objs)))
        self.selected_idx = first_new
        self.scene_dirty = True
        self._mark_dirty()
        self._status(
            f"Preset '{preset.get('name', '')}': {len(items)} oggetti inseriti", OK_C, 3)

    def _preset_delete(self, name: str) -> None:
        presets = [p for p in self._presets_load() if p.get("name") != name]
        self._presets_write(presets)
        self._status(f"Preset '{name}' eliminato", WARN_C, 2)

    # ── Aperture modali ──────────────────────────────────────────────────────

    def _preset_open_save(self) -> None:
        if not self._get_objs_selection():
            self._status("Seleziona prima gli oggetti da salvare", WARN_C, 2)
            return
        self._modal_push(_PresetSaveModal(self))

    def _preset_open_insert(self) -> None:
        if not self.scene_data:
            self._status("Apri prima una scena", WARN_C, 2)
            return
        if not self._presets_load():
            self._status("Nessun preset salvato", TXT_DIM, 2)
            return
        self._modal_push(_PresetListModal(self))


class _PresetSaveModal:
    """Modale con campo nome + Salva/Annulla (stack modale unificato)."""

    def __init__(self, editor) -> None:
        n_sel = len(editor._get_objs_selection())
        self.title = f"Salva gruppo ({n_sel} oggetti)"
        self.input = InputBox((0, 0, 10, 30), "", hint="Nome preset",
                              max_len=PRESET_NAME_MAX,
                              on_submit=lambda text: self._confirm(editor, text))
        self.input.focused = True
        self.btn_ok = Button((0, 0, _BTN_W, _BTN_H), "Salva",
                             lambda: self._confirm(editor, self.input.text),
                             custom_bg=OK_C)
        self.btn_cancel = Button((0, 0, _BTN_W, _BTN_H), "Annulla",
                                 lambda: editor._modal_pop(self))
        self.group = WidgetGroup([self.input, self.btn_ok, self.btn_cancel])

    def _confirm(self, editor, text: str) -> None:
        editor._modal_pop(self)
        editor._preset_save_selection(text)

    def _layout(self, w_win: int, h_win: int) -> pygame.Rect:
        panel = pygame.Rect((w_win - _SAVE_W) // 2, (h_win - _SAVE_H) // 2,
                            _SAVE_W, _SAVE_H)
        self.input.rect.update(panel.x + _MODAL_PAD, panel.y + 60,
                               _SAVE_W - _MODAL_PAD * 2, 32)
        self.btn_ok.rect.update(panel.right - _MODAL_PAD - _BTN_W * 2 - 10,
                                panel.bottom - _MODAL_PAD - _BTN_H, _BTN_W, _BTN_H)
        self.btn_cancel.rect.update(panel.right - _MODAL_PAD - _BTN_W,
                                    panel.bottom - _MODAL_PAD - _BTN_H,
                                    _BTN_W, _BTN_H)
        return panel

    def handle_event(self, editor, ev) -> bool:
        self._layout(*editor.screen.get_size())
        if ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE:
            if not self.input.focused:
                editor._modal_pop(self)
                return True
        self.group.handle_event(ev)
        return True

    def render(self, editor) -> None:
        screen = editor.screen
        w_win, h_win = screen.get_size()
        panel = self._layout(w_win, h_win)
        overlay = pygame.Surface((w_win, h_win), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, _OVERLAY_ALPHA))
        screen.blit(overlay, (0, 0))
        _rect(screen, PANEL, panel, radius=8)
        _rect(screen, BORDER, panel, 1, radius=8)
        _draw_text(screen, self.title, "md", TXT_HI,
                   panel.x + _MODAL_PAD, panel.y + _MODAL_PAD)
        self.group.draw(screen)


class _PresetListModal:
    """Lista preset: click inserisce, X elimina (stack modale unificato)."""

    def __init__(self, editor) -> None:
        self.presets = editor._presets_load()
        self._del_rects: dict = {}
        self.list = ScrollList((0, 0, 10, 10), lambda: self.presets,
                               self._draw_item, item_h=_LIST_ITEM_H,
                               on_select=lambda p, i: self._insert(editor, p))
        self.btn_close = Button((0, 0, _BTN_W, _BTN_H), "Chiudi",
                                lambda: editor._modal_pop(self))
        self.group = WidgetGroup([self.list, self.btn_close])
        self._editor = editor

    def _insert(self, editor, preset: dict) -> None:
        editor._modal_pop(self)
        editor._preset_insert(preset)

    def _draw_item(self, surf, rect, preset, index, hovered) -> None:
        bg = (55, 60, 80) if hovered else (44, 46, 58)
        _rect(surf, bg, rect, radius=4)
        name = preset.get("name", "?")
        count = len(preset.get("objects", []))
        _draw_text(surf, f"{name}", "sm", TXT_HI, rect.x + 10, rect.y + 8,
                   rect.w - 120)
        _draw_text(surf, f"{count} ogg.", "xs", TXT_DIM,
                   rect.right - 100, rect.y + 10)
        # X di eliminazione
        del_r = pygame.Rect(rect.right - 34, rect.y + 5, 24, 24)
        mx, my = pygame.mouse.get_pos()
        del_hov = _in_rect((mx, my), del_r)
        _rect(surf, (90, 30, 30) if del_hov else (60, 40, 40), del_r, radius=4)
        xs = _txt("x", "sm", TXT_HI)
        surf.blit(xs, (del_r.centerx - xs.get_width() // 2,
                       del_r.centery - xs.get_height() // 2))
        self._del_rects[index] = del_r

    def _layout(self, w_win: int, h_win: int) -> pygame.Rect:
        panel = pygame.Rect((w_win - _LIST_W) // 2, (h_win - _LIST_H) // 2,
                            _LIST_W, _LIST_H)
        self.list.rect.update(panel.x + _MODAL_PAD, panel.y + 56,
                              _LIST_W - _MODAL_PAD * 2,
                              _LIST_H - 56 - _MODAL_PAD * 2 - _BTN_H)
        self.btn_close.rect.update(panel.right - _MODAL_PAD - _BTN_W,
                                   panel.bottom - _MODAL_PAD - _BTN_H,
                                   _BTN_W, _BTN_H)
        return panel

    def handle_event(self, editor, ev) -> bool:
        self._layout(*editor.screen.get_size())
        if ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE:
            editor._modal_pop(self)
            return True
        # Eliminazione: intercetta il click sulla X prima della selezione riga
        if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
            for index, del_r in self._del_rects.items():
                if _in_rect(ev.pos, del_r) and index < len(self.presets):
                    name = self.presets[index].get("name", "")
                    editor._preset_delete(name)
                    self.presets = editor._presets_load()
                    self._del_rects.clear()
                    return True
        self.group.handle_event(ev)
        return True

    def render(self, editor) -> None:
        screen = editor.screen
        w_win, h_win = screen.get_size()
        panel = self._layout(w_win, h_win)
        overlay = pygame.Surface((w_win, h_win), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, _OVERLAY_ALPHA))
        screen.blit(overlay, (0, 0))
        _rect(screen, PANEL, panel, radius=8)
        _rect(screen, BORDER, panel, 1, radius=8)
        _draw_text(screen, "Inserisci gruppo", "md", TXT_HI,
                   panel.x + _MODAL_PAD, panel.y + _MODAL_PAD)
        _draw_text(screen, "Click = inserisci al centro vista, x = elimina",
                   "xs", TXT_DIM, panel.x + _MODAL_PAD, panel.y + 40)
        self._del_rects.clear()
        self.group.draw(screen)
