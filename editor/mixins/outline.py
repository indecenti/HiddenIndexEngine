"""
editor/mixins/outline.py

OutlineMixin - scene outline: the list of the objects placed in the current
scene (name, layer, goal, minigame, hidden/locked) with search and filters.

Why it exists: the canvas is the only place where a placed object could be
found, so an object hidden behind another one, outside the viewport or in a
scene with a hundred objects was effectively unreachable. The outline lists
them, selects them (single, ctrl to toggle, shift for a range) and brings them
into view; the bulk edit of the properties is the one already provided by the
properties panel for a multi-selection.

Interaction:
  * click        - select the object and reveal it (pan, zoom untouched)
  * ctrl+click   - add/remove the object from the selection
  * shift+click  - select the range from the last clicked row
  * double click - frame the object (same as the Z shortcut)
  * eye/lock     - editor-only visibility and lock, on the whole selection when
                   the clicked row belongs to it
"""

import time

import pygame

from editor.constants import (
    TOP_BAR_H, STATUS_H, BORDER, BTN, BTN_HO, BTN_AC,
    TXT, TXT_DIM, TXT_HI, ACCENT, OK_C, WARN_C, ERR_C, FX_C,
    TAB_PROPS, OUTLINE_ROW_H, DOUBLE_CLICK_S, layer_color,
)
from editor.ui.draw import (
    _rect, _txt, _draw_text, _in_rect, _clamp, _input_box, _scrollbar,
    _draw_shape_icon, _text_wh,
)

# Header geometry (search box + filter row + counter), in pixels.
_MARGIN = 8
_SEARCH_H = 30
_FILTER_H = 22
_ICON_BTN = 22


class OutlineMixin:
    """Scene outline panel: list, filters and selection of the placed objects."""

    # ── Data ────────────────────────────────────────────────────────────────

    def _outline_rows(self) -> list[tuple[int, dict]]:
        """(index, object) pairs matching the current search and filters.

        The index is the position in scene_data["objects"]: it is what the
        selection, the canvas and the properties panel all speak.
        """
        objs = (self.scene_data or {}).get("objects", [])
        query = (getattr(self, "outline_search", "") or "").strip().lower()
        only_goal = bool(getattr(self, "outline_filter_goal", False))
        only_layer = bool(getattr(self, "outline_filter_layer", False))
        active_layer = getattr(self, "active_layer", None)

        rows: list[tuple[int, dict]] = []
        for i, obj in enumerate(objs):
            if only_goal and not obj.get("is_goal", False):
                continue
            if only_layer and active_layer and obj.get("layer", "objects_mid") != active_layer:
                continue
            if query:
                haystack = " ".join((
                    str(obj.get("catalog_id", "")),
                    self._get_friendly_name(obj),
                    str(obj.get("layer", "")),
                    str(obj.get("minigame_trigger", "") or ""),
                )).lower()
                if query not in haystack:
                    continue
            rows.append((i, obj))
        return rows

    def _outline_visible_rows(self, h: int) -> int:
        """How many rows fit under the header at the current window height."""
        top = self._outline_list_top()
        return max(1, (h - STATUS_H - top) // OUTLINE_ROW_H)

    def _outline_list_top(self) -> int:
        """Y of the first row (below the tab bar and the header)."""
        return TOP_BAR_H + 32 + _SEARCH_H + _FILTER_H + 26

    def _outline_max_scroll(self, h: int) -> int:
        return max(0, len(self._outline_rows()) - self._outline_visible_rows(h))

    def _outline_scroll_by(self, dy: int) -> None:
        h = self.screen.get_size()[1]
        self.outline_scroll = _clamp(self.outline_scroll - dy, 0,
                                     self._outline_max_scroll(h))

    def _outline_follow_selection(self) -> None:
        """Scroll the list so the selected object is visible.

        Called from the render pass: the selection also changes from the canvas,
        from undo and from the object operations, and the outline has to follow
        it without every one of those call sites knowing about the panel.
        """
        idx = self.selected_idx
        if idx is None or idx == getattr(self, "_outline_last_sel", None):
            self._outline_last_sel = idx
            return
        self._outline_last_sel = idx
        rows = self._outline_rows()
        pos = next((n for n, (i, _o) in enumerate(rows) if i == idx), None)
        if pos is None:
            return
        h = self.screen.get_size()[1]
        visible = self._outline_visible_rows(h)
        if pos < self.outline_scroll:
            self.outline_scroll = pos
        elif pos >= self.outline_scroll + visible:
            self.outline_scroll = pos - visible + 1
        self.outline_scroll = _clamp(self.outline_scroll, 0, self._outline_max_scroll(h))

    # ── Render ──────────────────────────────────────────────────────────────

    def _r_outline(self, h: int) -> None:
        w = self.panel_l_w
        inner_w = w - _MARGIN * 2
        mx, my = pygame.mouse.get_pos()
        self._outline_hitboxes = []      # (rect, row_index, zone) rebuilt per frame
        self._outline_filter_hitboxes = {}

        # 1. Search box
        y = TOP_BAR_H + 36
        search_r = pygame.Rect(_MARGIN, y, inner_w, _SEARCH_H - 4)
        _input_box(self.screen, search_r, getattr(self, "outline_search", ""),
                   focused=getattr(self, "outline_searching", False),
                   hint=self._TR("outline_search_hint", "Search objects..."),
                   icon="search", font="sm")
        self._outline_search_rect = search_r
        y += _SEARCH_H

        # 2. Filters: goal only / active layer only
        f_w = (inner_w - 6) // 2
        goal_r = pygame.Rect(_MARGIN, y, f_w, _FILTER_H - 4)
        layer_r = pygame.Rect(_MARGIN + f_w + 6, y, f_w, _FILTER_H - 4)
        self._outline_chip(goal_r, self._TR("outline_filter_goal", "GOAL"),
                           bool(getattr(self, "outline_filter_goal", False)),
                           _in_rect((mx, my), goal_r), OK_C)
        self._outline_chip(layer_r, self._TR("outline_filter_layer", "LAYER"),
                           bool(getattr(self, "outline_filter_layer", False)),
                           _in_rect((mx, my), layer_r), ACCENT)
        self._outline_filter_hitboxes["goal"] = goal_r
        self._outline_filter_hitboxes["layer"] = layer_r
        y += _FILTER_H

        # 3. Counter
        rows = self._outline_rows()
        total = len((self.scene_data or {}).get("objects", []))
        _draw_text(self.screen,
                   self._TR("outline_count", "{shown} of {total} objects").format(
                       shown=len(rows), total=total),
                   "xs", TXT_DIM, _MARGIN, y + 4, inner_w)
        y += 22
        pygame.draw.line(self.screen, BORDER, (0, y), (w, y))

        # 4. Rows
        list_top = self._outline_list_top()
        visible = self._outline_visible_rows(h)
        self.outline_scroll = _clamp(getattr(self, "outline_scroll", 0), 0,
                                     max(0, len(rows) - visible))
        if not rows:
            msg = ("outline_no_results" if (getattr(self, "outline_search", "")
                                            or getattr(self, "outline_filter_goal", False)
                                            or getattr(self, "outline_filter_layer", False))
                   else "outline_empty")
            _draw_text(self.screen,
                       self._TR(msg, "No object matches" if msg == "outline_no_results"
                                else "No object in this scene"),
                       "sm", TXT_DIM, _MARGIN, list_top + 8, inner_w)
            return

        clip = pygame.Rect(0, list_top, w, h - STATUS_H - list_top)
        self.screen.set_clip(clip)
        sel_all = set(getattr(self, "selected_indices", []) or [])
        if self.selected_idx is not None:
            sel_all.add(self.selected_idx)

        ry = list_top
        for n in range(self.outline_scroll, min(len(rows), self.outline_scroll + visible)):
            idx, obj = rows[n]
            self._r_outline_row(pygame.Rect(0, ry, w, OUTLINE_ROW_H), n, idx, obj,
                                idx in sel_all, (mx, my))
            ry += OUTLINE_ROW_H
        self.screen.set_clip(None)

        if len(rows) > visible:
            _scrollbar(self.screen, w - 8, list_top, 3, h - STATUS_H - list_top - 4,
                       self.outline_scroll, len(rows), visible)

    def _outline_chip(self, r: pygame.Rect, label: str, active: bool,
                      hovered: bool, on_color) -> None:
        """Compact filter toggle (the tag chips are too tall for this header)."""
        bg = BTN_AC if active else (BTN_HO if hovered else BTN)
        _rect(self.screen, bg, r, radius=4)
        _rect(self.screen, on_color if active else BORDER, r, 1, radius=4)
        s = _txt(label, "xs", TXT_HI if active else TXT_DIM)
        self.screen.blit(s, (r.centerx - s.get_width() // 2,
                             r.centery - s.get_height() // 2))

    def _r_outline_row(self, row: pygame.Rect, n: int, idx: int, obj: dict,
                       selected: bool, mouse: tuple) -> None:
        hovered = _in_rect(mouse, row)
        hidden = bool(obj.get("editor_hidden", False))
        locked = bool(obj.get("editor_locked", False))

        if selected:
            _rect(self.screen, BTN_AC, row)
            _rect(self.screen, ACCENT, row, 1)
        elif hovered:
            _rect(self.screen, BTN_HO, row)

        # Layer colour bar: the layer of an object is a constant read, a chip
        # would cost horizontal space the name needs more.
        lid = obj.get("layer", "objects_mid")
        pygame.draw.rect(self.screen, layer_color(lid), (0, row.y + 2, 3, row.h - 4))

        # Icon from the catalog (LRU cached by _load_img)
        x = 10
        cat_e = next((c for c in getattr(self, "catalog", []) if c["id"] == obj.get("catalog_id")), None)
        if cat_e and self.game_path:
            ic = self._load_img(self.game_path / cat_e.get("icon", ""), (18, 18))
            if ic:
                self.screen.blit(ic, (x, row.y + (row.h - 18) // 2))
        x += 24

        # Badges (goal / minigame) are right aligned, before the two buttons
        eye_r = pygame.Rect(row.right - _ICON_BTN - 4, row.y + (row.h - _ICON_BTN) // 2,
                            _ICON_BTN, _ICON_BTN)
        lock_r = pygame.Rect(eye_r.left - _ICON_BTN - 2, eye_r.y, _ICON_BTN, _ICON_BTN)
        bx = lock_r.left - 4
        for label, on, col in ((self._TR("outline_badge_minigame", "M"),
                                bool(obj.get("minigame_trigger")), FX_C),
                               (self._TR("outline_badge_goal", "G"),
                                bool(obj.get("is_goal", False)), OK_C)):
            if not on:
                continue
            tw, th = _text_wh(label, "xs")
            br = pygame.Rect(bx - tw - 8, row.y + (row.h - 16) // 2, tw + 8, 16)
            _rect(self.screen, (24, 26, 32), br, radius=4)
            _rect(self.screen, col, br, 1, radius=4)
            self.screen.blit(_txt(label, "xs", col), (br.x + 4, br.centery - th // 2))
            bx = br.left - 4

        name_col = TXT_DIM if hidden else (TXT_HI if selected else TXT)
        _draw_text(self.screen, self._get_friendly_name(obj), "sm", name_col,
                   x, row.y + (row.h - 14) // 2, max(20, bx - x - 4))

        eye_hov = _in_rect(mouse, eye_r)
        lock_hov = _in_rect(mouse, lock_r)
        _draw_shape_icon(self.screen, eye_r, "eye_hidden" if hidden else "eye_visible",
                         ACCENT if eye_hov else (WARN_C if hidden else TXT_DIM))
        _draw_shape_icon(self.screen, lock_r, "lock_closed" if locked else "lock_open",
                         ACCENT if lock_hov else (ERR_C if locked else TXT_DIM))
        if eye_hov:
            self.active_tooltip = self._TR("outline_tip_hide", "Hide in the editor")
        elif lock_hov:
            self.active_tooltip = self._TR("outline_tip_lock", "Lock in the editor")

        self._outline_hitboxes.append((eye_r, n, "eye"))
        self._outline_hitboxes.append((lock_r, n, "lock"))
        self._outline_hitboxes.append((row.copy(), n, "row"))

    # ── Input ───────────────────────────────────────────────────────────────

    def _outline_click(self, mx: int, my: int) -> None:
        """Click inside the outline panel (my is the raw screen y)."""
        if _in_rect((mx, my), getattr(self, "_outline_search_rect", pygame.Rect(0, 0, 0, 0))):
            self.outline_searching = True
            self.catalog_searching = False
            self.catalog_tag_searching = False
            return
        self.outline_searching = False

        for key, r in getattr(self, "_outline_filter_hitboxes", {}).items():
            if _in_rect((mx, my), r):
                attr = f"outline_filter_{key}"
                setattr(self, attr, not getattr(self, attr, False))
                self.outline_scroll = 0
                return

        # Hitboxes are ordered per row (eye, lock, row): the buttons win.
        for rect, n, zone in getattr(self, "_outline_hitboxes", []):
            if not _in_rect((mx, my), rect):
                continue
            rows = self._outline_rows()
            if n >= len(rows):
                return
            idx = rows[n][0]
            if zone == "eye":
                self._outline_toggle_flag(idx, "editor_hidden")
            elif zone == "lock":
                self._outline_toggle_flag(idx, "editor_locked")
            else:
                self._outline_select(n, idx, rows)
            return

    def _outline_select(self, n: int, idx: int, rows: list) -> None:
        mods = pygame.key.get_mods()
        ctrl = bool(mods & pygame.KMOD_CTRL)
        shift = bool(mods & pygame.KMOD_SHIFT)
        now = time.time()
        is_double = (not ctrl and not shift
                     and idx == getattr(self, "_outline_last_click_idx", None)
                     and now - getattr(self, "_outline_last_click_t", 0.0) <= DOUBLE_CLICK_S)
        self._outline_last_click_idx = idx
        self._outline_last_click_t = now

        if ctrl:
            sel = list(getattr(self, "selected_indices", []) or [])
            if idx in sel:
                sel.remove(idx)
            else:
                sel.append(idx)
            self.selected_indices = sel
            self.selected_idx = sel[-1] if sel else None
        elif shift and getattr(self, "_outline_anchor", None) is not None:
            anchor = self._outline_anchor
            positions = [i for i, _o in rows]
            if anchor in positions:
                a, b = sorted((positions.index(anchor), n))
                self.selected_indices = [rows[k][0] for k in range(a, b + 1)]
                self.selected_idx = idx
            else:
                self.selected_indices = [idx]
                self.selected_idx = idx
        else:
            self.selected_indices = [idx]
            self.selected_idx = idx
            self._outline_anchor = idx

        self.sel_effect_idx = None
        # The properties of what was just picked belong on screen: the outline
        # is the hierarchy, the right panel is the inspector.
        self.r_tab = TAB_PROPS
        self._outline_last_sel = self.selected_idx
        if is_double:
            self._zoom_to_selection()
        else:
            self._reveal_selection()
        self._mark_dirty()

    def _outline_toggle_flag(self, idx: int, key: str) -> None:
        """Toggle editor_hidden / editor_locked on the row (or on the selection
        when the row is part of it, so the button matches what is highlighted)."""
        objs = (self.scene_data or {}).get("objects", [])
        if not 0 <= idx < len(objs):
            return
        sel = set(getattr(self, "selected_indices", []) or [])
        if self.selected_idx is not None:
            sel.add(self.selected_idx)
        targets = sorted(sel) if idx in sel and len(sel) > 1 else [idx]
        self._push_undo(self._TR("undo_outline_flag", "Editor flags"))
        new_val = not all(objs[i].get(key, False) for i in targets if i < len(objs))
        for i in targets:
            if i < len(objs):
                objs[i][key] = new_val
        self.scene_dirty = True
        self._mark_dirty()
        msg_key = "ih_hide_editor" if key == "editor_hidden" else "ih_lock_editor"
        default = "Hide editor: {0}" if key == "editor_hidden" else "Lock editor: {0}"
        self._status(self._TR(msg_key, default).format("ON" if new_val else "OFF"),
                     WARN_C if key == "editor_hidden" else ERR_C, 2)

    def _outline_key(self, ev) -> bool:
        """Typing in the search box. Returns True when the event was consumed."""
        if not getattr(self, "outline_searching", False):
            return False
        if ev.key in (pygame.K_ESCAPE, pygame.K_RETURN):
            self.outline_searching = False
        elif ev.key in (pygame.K_BACKSPACE, pygame.K_DELETE):
            self.outline_search = getattr(self, "outline_search", "")[:-1]
            self.outline_scroll = 0
        elif ev.unicode and ev.unicode.isprintable():
            self.outline_search = getattr(self, "outline_search", "") + ev.unicode.lower()
            self.outline_scroll = 0
        return True
