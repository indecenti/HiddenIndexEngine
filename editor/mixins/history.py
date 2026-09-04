"""
editor/mixins/history.py

HistoryMixin — stack undo/redo (max UNDO_MAX passi) con etichette azione,
coalescing opzionale delle raffiche e selezione preservata quando ancora valida.
"""

import copy
import time
from typing import Optional

from editor.constants import UNDO_MAX, UNDO_COALESCE_GAP_S, TXT_DIM


class HistoryMixin:
    """Undo/Redo basato su snapshot profondi di scene_data.

    Ogni voce dello stack e' una tupla (snapshot, label). La label descrive
    l'azione che lo snapshot PRECEDE (es. "Sposta oggetti") e viene mostrata
    nella status bar su annulla/ripristina.
    """

    def _push_undo(self, label: str = "",
                   coalesce_key: Optional[str] = None):
        """Salva uno snapshot. Con coalesce_key, raffiche ravvicinate della
        stessa azione (es. rotella sul raggio) producono un solo snapshot."""
        now = time.time()
        if (coalesce_key
                and coalesce_key == getattr(self, "_undo_last_key", None)
                and now - getattr(self, "_undo_last_ts", 0.0) <= UNDO_COALESCE_GAP_S):
            self._undo_last_ts = now
            return
        self._undo_last_key = coalesce_key
        self._undo_last_ts = now

        # Snapshot profondo dell'intero stato della scena
        snap = copy.deepcopy(self.scene_data)

        # Evitiamo di pushare stati identici (es. clic senza modifiche)
        if self.undo_stack and self.undo_stack[-1][0] == snap:
            return

        self.undo_stack.append((snap, label))
        if len(self.undo_stack) > UNDO_MAX:
            self.undo_stack.pop(0)
        self.redo_stack.clear()
        self.scene_dirty = True
        if hasattr(self, "_mark_dirty"):
            self._mark_dirty()

    def _restore_snapshot(self, snap: dict):
        """Applica uno snapshot preservando la selezione se ancora valida."""
        self.scene_data.clear()
        self.scene_data.update(snap)

        # Selezione: mantienila per gli indici ancora validi invece di azzerarla
        n_obj = len(self.scene_data.get("objects", []))
        self.selected_indices = [i for i in self.selected_indices if i < n_obj]
        if self.selected_idx is not None and self.selected_idx >= n_obj:
            self.selected_idx = self.selected_indices[0] if self.selected_indices else None
        n_fx = len(self.scene_data.get("effects", []))
        if getattr(self, "sel_effect_idx", None) is not None and self.sel_effect_idx >= n_fx:
            self.sel_effect_idx = None

        if hasattr(self, "_mark_dirty"):
            self._mark_dirty()

    def _undo(self):
        if not self.undo_stack:
            self._status(self._TR("hist_nothing_undo", "Undo: nothing to undo"), TXT_DIM, 1)
            return

        snap, label = self.undo_stack.pop()
        # Salva lo stato corrente nel redo prima di ripristinare
        self.redo_stack.append((copy.deepcopy(self.scene_data), label))
        self._restore_snapshot(snap)
        self._undo_last_key = None

        msg = (self._TR("hist_undone", "Undone: {label}").format(label=label)
               if label else self._TR("hist_undone_generic", "Undo done"))
        self._status(msg, TXT_DIM, 1.5)

    def _redo(self):
        if not self.redo_stack:
            self._status(self._TR("hist_nothing_redo", "Redo: nothing to redo"), TXT_DIM, 1)
            return

        snap, label = self.redo_stack.pop()
        self.undo_stack.append((copy.deepcopy(self.scene_data), label))
        self._restore_snapshot(snap)
        self._undo_last_key = None

        msg = (self._TR("hist_redone", "Redone: {label}").format(label=label)
               if label else self._TR("hist_redone_generic", "Redo done"))
        self._status(msg, TXT_DIM, 1.5)
