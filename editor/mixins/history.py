"""
editor/mixins/history.py

HistoryMixin — stack undo/redo (max UNDO_MAX passi).
"""

import copy
from editor.constants import UNDO_MAX, TXT_DIM


class HistoryMixin:
    """Undo/Redo basato su deep-copy della lista oggetti."""

    def _push_undo(self):
        # Snapshot profondo dell'intero stato della scena
        snap = copy.deepcopy(self.scene_data)
        
        # Evitiamo di pushare stati identici (es. clic senza modifiche)
        if self.undo_stack and self.undo_stack[-1] == snap:
            return
            
        self.undo_stack.append(snap)
        if len(self.undo_stack) > UNDO_MAX:
            self.undo_stack.pop(0)
        self.redo_stack.clear()
        self.scene_dirty = True

    def _undo(self):
        if not self.undo_stack:
            self._status("Undo: Nulla da annullare", TXT_DIM, 1)
            return
            
        # Salva lo stato corrente nel redo prima di ripristinare
        self.redo_stack.append(copy.deepcopy(self.scene_data))
        
        # Ripristina l'intero stato della scena
        restored_data = self.undo_stack.pop()
        self.scene_data.clear()
        self.scene_data.update(restored_data)
        
        # Reset totale selezioni
        self.selected_idx = None
        self.selected_indices = []
        if hasattr(self, "sel_effect_idx"):
            self.sel_effect_idx = None
            
        self._status("Undo eseguito", TXT_DIM, 1.5)

    def _redo(self):
        if not self.redo_stack:
            self._status("Redo: Nulla da ripristinare", TXT_DIM, 1)
            return
            
        self.undo_stack.append(copy.deepcopy(self.scene_data))
        
        # Ripristina l'intero stato della scena
        restored_data = self.redo_stack.pop()
        self.scene_data.clear()
        self.scene_data.update(restored_data)
        
        # Reset totale selezioni
        self.selected_idx = None
        self.selected_indices = []
        if hasattr(self, "sel_effect_idx"):
            self.sel_effect_idx = None
            
        self._status("Redo eseguito", TXT_DIM, 1.5)

