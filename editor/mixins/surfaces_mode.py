"""
editor/mixins/surfaces_mode.py

SurfacesModeMixin - the placement surfaces of a scene, drawn on the canvas.

`tools/place_on_surfaces.py` puts hidden objects on surfaces marked by hand:
resting lines (a shelf board, a table edge, a sill, seen from the front) and
"area" rectangles (floors and table tops seen from above, where an object goes
only if the support map holds under it). They were written by hand into
`surfaces.json` after reading coordinates off a labelled grid. This mode draws
them on the canvas instead:

  * drag            -> a resting line (stored left to right);
  * Shift+drag      -> an area (or the Area sub-mode of the bar);
  * click           -> select; drag a handle to move an end or a corner, drag
                       the body to move the whole surface; arrows nudge it;
  * Del             -> delete; Esc -> deselect, then leave the mode.

Every surface shows its size gizmo: a vertical tick as tall as a 20 cm object
standing there (the "h" of the file, times the scene's h_mul), the same tick
the tool's preview draws. The band the game HUD covers and the frame margin,
where nothing is placed, are shaded. For areas the support map can be shown
(computed once per background on the CPU, cached on disk by the tool).

Edits are written to `<scene>/surfaces.json` at once (safe_write_json) and are
undoable with the scene's undo stack: HistoryMixin carries the document in its
snapshots through `_surfaces_capture` / `_surfaces_restore`.
"""

from __future__ import annotations

import copy
import logging
import threading
from pathlib import Path
from typing import Any, Optional

import pygame

from editor.constants import (
    ACCENT, BORDER, ERR_C, HANDLE_R, MODE_SELECT, MODE_SURFACES, OK_C,
    SEL_C, STATUS, TAB_PROPS, TOP_BAR_H, TXT, TXT_DIM, TXT_HI, WARN_C, BTN_AC,
    BTN_HO, HUD_BG, TOOLBAR_BTN_PAD_X, TOOLBAR_GAP, TOOLBAR_MARGIN,
    TOOLBAR_ROW_GAP,
    SURF_AREA_C, SURF_GIZMO_C, SURF_GIZMO_W, SURF_HIT_PX, SURF_HMUL_STEP,
    SURF_HUD_C, SURF_H_STEP, SURF_H_STEP_FAST, SURF_LABEL_PAD, SURF_LINE_C,
    SURF_LINE_W, SURF_MARGIN_C, SURF_NUDGE_FAST, SURF_SEL_LINE_W,
    SURF_SUPPORT_C, SURF_HUD_LABEL_C, SURF_HANDLE_RIM_C, PLACE_APPLY_BG,
)
from editor.core import surfaces as sf
from editor.ui.draw import (
    _button, _button_w, _draw_text, _draw_text_wrapped, _in_rect, _input_box,
    _rect, _text_wh, _txt, _ui_scale,
)

log = logging.getLogger(__name__)


def _ps(value: float) -> int:
    """A panel offset at the current UI scale (same rule as render_panels)."""
    return int(round(value * _ui_scale()))


def step_button(surf: pygame.Surface, r: pygame.Rect, sign: str, hovered: bool) -> None:
    """A small "-" / "+" button drawn as text: _button turns "+" into the large
    "add" icon and leaves "-" as text, and the pair did not match."""
    _button(surf, r, "", hovered)
    tw, th = _text_wh(sign, "sm")
    surf.blit(_txt(sign, "sm", TXT_HI), (r.x + (r.w - tw) // 2, r.y + (r.h - th) // 2))


class SurfacesModeMixin:
    """Surfaces mode: draw, edit and save the placement surfaces of a scene."""

    # ── state ─────────────────────────────────────────────────────────────
    def _surfaces_init_state(self) -> None:
        self._surf_doc: dict = {"surfaces": []}
        self._surf_sel: Optional[int] = None
        self._surf_drag: Optional[dict] = None
        self._surf_area_mode: bool = False
        self._surf_show_support: bool = False
        self._surf_last_h: dict = {}               # "line" / "area" -> last size used
        self._surf_last_kind: str = sf.DEFAULT_KIND
        self._surf_rules: Optional[dict] = None
        self._surf_scene_bg: Optional[sf.SceneBackground] = None
        self._surf_support_busy: bool = False
        self._surf_support_token: int = 0
        self._surf_support_result: Optional[tuple] = None
        self._surf_support_small: Any = None       # downsampled bool mask
        self._surf_support_step: int = 1
        self._surf_support_surf: Optional[pygame.Surface] = None
        self._surf_support_cache: Optional[tuple] = None   # (key, scaled, pos)
        self._surf_support_error: str = ""
        self._surface_props_hitboxes: dict = {}

    def _surfaces_reset(self) -> None:
        """A new scene: its own surfaces, nothing selected, no support map."""
        self._surf_support_token += 1
        self._surf_support_busy = False
        self._surf_support_result = None
        self._surf_support_small = None
        self._surf_support_surf = None
        self._surf_support_cache = None
        self._surf_support_error = ""
        self._surf_scene_bg = None
        self._surf_sel = None
        self._surf_drag = None
        scene_dir = getattr(self, "scene_path", None)
        self._surf_doc = sf.load_surfaces_doc(scene_dir) if scene_dir else {"surfaces": []}

    def _surfaces(self) -> list:
        return self._surf_doc.setdefault("surfaces", [])

    def _surfaces_rules(self) -> dict:
        if self._surf_rules is None:
            self._surf_rules = sf.placement_rules()
        return self._surf_rules

    def _surfaces_h_mul(self) -> float:
        try:
            return float(self._surf_doc.get("h_mul", 1.0))
        except (TypeError, ValueError):
            return 1.0

    # ── mode ──────────────────────────────────────────────────────────────
    def _surfaces_toggle_mode(self) -> None:
        """Enter or leave the surfaces mode (key 5, toolbar, View menu)."""
        if self.mode == MODE_SURFACES:
            self._surfaces_leave()
            return
        if not getattr(self, "scene_path", None):
            self._status(self._TR("surf_need_scene", "Open a scene first"), WARN_C, 2)
            return
        self.mode = MODE_SURFACES
        self._cancel_rect()
        self.selected_idx = None
        self.selected_indices = []
        self.sel_effect_idx = None
        self._editing_prop = None
        self.r_tab = TAB_PROPS
        self.prop_scroll = 0
        self._mark_dirty()
        self._status(self._TR(
            "surf_mode_on",
            "Surfaces: drag = line, Shift+drag = area, Del = delete, Esc = done"),
            ACCENT, 4)

    def _surfaces_leave(self) -> None:
        self.mode = MODE_SELECT
        self._surf_drag = None
        if getattr(self, "_editing_prop", None) and self._editing_prop[0] == "surface":
            self._editing_prop = None
        self._mark_dirty()

    # ── undo + disk ───────────────────────────────────────────────────────
    def _surfaces_capture(self) -> dict:
        return copy.deepcopy(self._surf_doc)

    def _surfaces_restore(self, doc: Optional[dict]) -> None:
        """Undo/redo brought back another version of the surfaces."""
        if doc is None or doc == self._surf_doc:
            return
        self._surf_doc = copy.deepcopy(doc)
        n = len(self._surfaces())
        if self._surf_sel is not None and self._surf_sel >= n:
            self._surf_sel = None
        self._surf_drag = None
        self._surfaces_save()

    def _surfaces_push_undo(self, label: str, coalesce_key: Optional[str] = None) -> None:
        """An undo step for a surfaces edit. The scene itself did not change, so
        its dirty flag stays as it was: surfaces.json is written on the spot."""
        dirty = self.scene_dirty
        self._push_undo(label, coalesce_key=coalesce_key)
        self.scene_dirty = dirty

    def _surfaces_save(self) -> None:
        scene_dir = getattr(self, "scene_path", None)
        if not scene_dir:
            return
        if not sf.save_surfaces_doc(scene_dir, self._surf_doc):
            self._status(self._TR("surf_save_failed", "Could not write surfaces.json"),
                         ERR_C, 4)

    def _surfaces_default_h(self, area: bool) -> float:
        last = self._surf_last_h.get("area" if area else "line")
        if last:
            return float(last)
        width = self.bg_surf.get_width() if getattr(self, "bg_surf", None) else sf.REF_SCREEN_W
        return sf.default_h(width)

    # ── canvas input ──────────────────────────────────────────────────────
    def _surfaces_bg_point(self, mx: int, my: int) -> tuple[float, float]:
        """Screen point -> background px, clamped to the background."""
        rx, ry = self._s2r(mx, my)
        if getattr(self, "bg_surf", None) is not None:
            bw, bh = self.bg_surf.get_size()
            rx = max(0.0, min(float(bw), rx))
            ry = max(0.0, min(float(bh), ry))
        return float(rx), float(ry)

    def _surfaces_ldown(self, mx: int, my: int) -> None:
        if not getattr(self, "scene_path", None) or getattr(self, "bg_surf", None) is None:
            self._status(self._TR("surf_need_background", "Load a background first"),
                         WARN_C, 2)
            return
        rx, ry = self._surfaces_bg_point(mx, my)
        tol = (SURF_HIT_PX + HANDLE_R) / max(self.zoom, 1e-6)
        hit = sf.hit_test(self._surfaces(), rx, ry, tol, first=self._surf_sel)
        if hit is not None:
            idx, part = hit
            self._surf_sel = idx
            self._surf_drag = {"op": "move" if part == "body" else "handle",
                               "idx": idx, "part": part, "start": (rx, ry),
                               "orig": copy.deepcopy(self._surfaces()[idx]),
                               "pushed": False}
            return
        self._surf_sel = None
        area = self._surf_area_mode or bool(pygame.key.get_mods() & pygame.KMOD_SHIFT)
        self._surf_drag = {"op": "new_area" if area else "new_line",
                           "start": (rx, ry), "cur": (rx, ry)}

    def _surfaces_motion(self, mx: int, my: int) -> None:
        drag = self._surf_drag
        if drag is None:
            return
        rx, ry = self._surfaces_bg_point(mx, my)
        if drag["op"] in ("new_line", "new_area"):
            drag["cur"] = (rx, ry)
            return
        idx = drag["idx"]
        if idx >= len(self._surfaces()):
            self._surf_drag = None
            return
        if not drag["pushed"]:
            self._surfaces_push_undo(self._TR("surf_undo_edit", "Edit surface"))
            drag["pushed"] = True
        sx, sy = drag["start"]
        if drag["op"] == "move":
            self._surfaces()[idx] = sf.moved(drag["orig"], rx - sx, ry - sy)
        else:
            self._surfaces()[idx] = sf.with_handle(drag["orig"], drag["part"], rx, ry)

    def _surfaces_lup(self, mx: int, my: int) -> None:
        drag = self._surf_drag
        self._surf_drag = None
        if drag is None:
            return
        if drag["op"] in ("new_line", "new_area"):
            (x0, y0), (x1, y1) = drag["start"], self._surfaces_bg_point(mx, my)
            if drag["op"] == "new_area":
                new = sf.new_area(x0, y0, x1, y1, self._surfaces_default_h(True),
                                  self._surf_last_h.get("near"))
            else:
                kind = self._surf_last_kind if self._surf_last_kind in sf.LINE_KINDS \
                    else sf.DEFAULT_KIND
                new = sf.new_line(x0, y0, x1, y1, self._surfaces_default_h(False), kind)
            if not sf.long_enough(new):
                return
            self._surfaces_push_undo(self._TR("surf_undo_add", "Add surface"))
            self._surfaces().append(new)
            self._surf_sel = len(self._surfaces()) - 1
            self._surfaces_save()
            self._status(self._TR("surf_added", "Surface added: measure its size in the panel"),
                         OK_C, 3)
            return
        idx = drag["idx"]
        if drag["pushed"] and idx < len(self._surfaces()):
            self._surfaces()[idx] = sf.normalized(self._surfaces()[idx])
            self._surfaces_save()

    def _surfaces_cancel_drag(self) -> None:
        drag = self._surf_drag
        self._surf_drag = None
        if drag and drag.get("pushed") and drag["idx"] < len(self._surfaces()):
            self._surfaces()[drag["idx"]] = drag["orig"]
            self._surfaces_save()

    def _surfaces_delete(self) -> None:
        idx = self._surf_sel
        if idx is None or idx >= len(self._surfaces()):
            return
        self._surfaces_push_undo(self._TR("surf_undo_delete", "Delete surface"))
        self._surfaces().pop(idx)
        self._surf_sel = None
        self._surfaces_save()
        self._status(self._TR("surf_deleted", "Surface deleted"), WARN_C, 2)

    def _surfaces_nudge(self, dx: float, dy: float) -> None:
        idx = self._surf_sel
        if idx is None or idx >= len(self._surfaces()):
            return
        self._surfaces_push_undo(self._TR("surf_undo_edit", "Edit surface"),
                                 coalesce_key="surface_nudge")
        self._surfaces()[idx] = sf.moved(self._surfaces()[idx], dx, dy)
        self._surfaces_save()

    def _surfaces_key(self, ev) -> bool:
        """Keys of the mode. True when the key was used here."""
        if ev.key == pygame.K_ESCAPE:
            if self._surf_drag is not None:
                self._surfaces_cancel_drag()
            elif self._surf_sel is not None:
                self._surf_sel = None
            else:
                self._surfaces_leave()
            return True
        if ev.key in (pygame.K_DELETE, pygame.K_BACKSPACE):
            self._surfaces_delete()
            return True
        if self._surf_sel is not None and ev.key in (
                pygame.K_LEFT, pygame.K_RIGHT, pygame.K_UP, pygame.K_DOWN):
            step = SURF_NUDGE_FAST if (pygame.key.get_mods() & pygame.KMOD_SHIFT) else 1
            dx = int(ev.key == pygame.K_RIGHT) - int(ev.key == pygame.K_LEFT)
            dy = int(ev.key == pygame.K_DOWN) - int(ev.key == pygame.K_UP)
            self._surfaces_nudge(dx * step, dy * step)
            return True
        return False

    # ── values ────────────────────────────────────────────────────────────
    def _surfaces_set_value(self, idx: int, key: str, value: Optional[float]) -> None:
        """Set one number of a surface (h, h_far, h_near, max) or of the scene
        (h_mul, idx -1). None clears an optional value (max -> automatic)."""
        if key == "h_mul":
            if value is None:
                return
            new_mul = round(max(sf.H_MUL_MIN, min(sf.H_MUL_MAX, float(value))), 2)
            if new_mul == self._surfaces_h_mul():
                return
            self._surfaces_push_undo(self._TR("surf_undo_edit", "Edit surface"),
                                     coalesce_key="surface_h_mul")
            self._surf_doc["h_mul"] = new_mul
            self._surfaces_save()
            return
        if idx is None or not 0 <= idx < len(self._surfaces()):
            return
        s = dict(self._surfaces()[idx])
        if key == "max":
            if value is None or value < 1:
                s.pop("max", None)
            else:
                s["max"] = int(min(sf.MAX_OBJECTS_CAP, round(value)))
        else:
            if value is None:
                return
            v = max(sf.H_MIN, min(sf.H_MAX, float(value)))
            far, near = sf.heights(s)
            if key == "h_near":
                near = v
            else:
                far = v
            s["h"] = [far, near] if sf.is_area(s) else far
            if sf.is_area(s):
                self._surf_last_h["area"] = far
                self._surf_last_h["near"] = near
            else:
                self._surf_last_h["line"] = far
        s = sf.normalized(s)
        if s == self._surfaces()[idx]:
            return
        self._surfaces_push_undo(self._TR("surf_undo_edit", "Edit surface"),
                                 coalesce_key=f"surface_{idx}_{key}")
        self._surfaces()[idx] = s
        self._surfaces_save()

    def _surface_prop_commit(self, idx: int, key: str, buf: str) -> None:
        """Enter in a number box of the surface panel (see _prop_commit)."""
        try:
            value = float(buf.replace(",", "."))
        except ValueError:
            self._status(self._TR("ih_need_number", "Error: enter a number"), ERR_C, 2)
            return
        self._surfaces_set_value(idx, key, value)

    def _surfaces_set_kind(self, idx: int, kind: str) -> None:
        if not 0 <= idx < len(self._surfaces()):
            return
        new = sf.with_kind(self._surfaces()[idx], kind)
        if new == self._surfaces()[idx]:
            return
        self._surfaces_push_undo(self._TR("surf_undo_edit", "Edit surface"))
        self._surfaces()[idx] = new
        if kind in sf.LINE_KINDS:
            self._surf_last_kind = kind
        self._surfaces_save()

    def _surfaces_toggle_snap(self, idx: int) -> None:
        if not 0 <= idx < len(self._surfaces()):
            return
        s = dict(self._surfaces()[idx])
        if s.get("snap", True):
            s["snap"] = False
        else:
            s.pop("snap", None)
        self._surfaces_push_undo(self._TR("surf_undo_edit", "Edit surface"))
        self._surfaces()[idx] = sf.normalized(s)
        self._surfaces_save()

    def _surfaces_kind_label(self, kind: str) -> str:
        labels = {
            "shelf": self._TR("surf_kind_shelf", "Shelf"),
            "table": self._TR("surf_kind_table", "Table"),
            "sill": self._TR("surf_kind_sill", "Sill"),
            "ledge": self._TR("surf_kind_ledge", "Ledge"),
            "floor": self._TR("surf_kind_floor", "Floor"),
            "area": self._TR("surf_kind_area", "Area"),
        }
        return labels.get(kind, kind)

    # ── support map ───────────────────────────────────────────────────────
    def _surfaces_scene_bg(self) -> Optional[sf.SceneBackground]:
        """The tool's Background of the open scene, shared with the placement."""
        scene_dir = getattr(self, "scene_path", None)
        name = (getattr(self, "scene_data", None) or {}).get("background", "")
        if not scene_dir or not name:
            return None
        path = Path(scene_dir) / name
        if not path.exists():
            return None
        if self._surf_scene_bg is None or self._surf_scene_bg.path != path:
            self._surf_scene_bg = sf.SceneBackground(self.base_path, path)
        return self._surf_scene_bg

    def _surfaces_toggle_support(self) -> None:
        self._surf_show_support = not self._surf_show_support
        if self._surf_show_support:
            self._surfaces_request_support()
        self._mark_dirty()

    def _surfaces_request_support(self) -> None:
        """Compute the support map in the background, once per scene."""
        if self._surf_support_small is not None or self._surf_support_busy:
            return
        scene_bg = self._surfaces_scene_bg()
        if scene_bg is None:
            self._status(self._TR("surf_need_background", "Load a background first"),
                         WARN_C, 2)
            return
        self._surf_support_busy = True
        self._surf_support_error = ""
        self._surf_support_token += 1
        token = self._surf_support_token
        self._status(self._TR("surf_support_busy",
                              "Computing the support map (CPU, cached)..."), ACCENT, 0)

        def work() -> None:
            try:
                small, step = sf.support_preview(scene_bg.ensure_support())
                result = (small, step, "")
            except Exception as exc:
                log.warning("Support map failed: %s", exc)
                result = (None, 1, str(exc) or exc.__class__.__name__)
            if token == self._surf_support_token:
                self._surf_support_result = result

        threading.Thread(target=work, daemon=True, name="SurfacesSupport").start()

    def _surfaces_consume_support(self) -> None:
        result = self._surf_support_result
        if result is None:
            return
        self._surf_support_result = None
        self._surf_support_busy = False
        small, step, error = result
        if error:
            self._surf_support_error = error
            self._surf_show_support = False
            self._status(self._TR("surf_support_failed",
                                  "Support map unavailable: {e}").format(e=error), ERR_C, 6)
            return
        import numpy as np
        h, w = small.shape[:2]
        rgba = np.zeros((h, w, 4), dtype=np.uint8)
        rgba[small] = SURF_SUPPORT_C
        self._surf_support_small = small
        self._surf_support_step = step
        self._surf_support_surf = pygame.image.frombuffer(
            rgba.tobytes(), (w, h), "RGBA").copy()
        self._surf_support_cache = None
        self._status(self._TR("surf_support_ready", "Support map ready"), OK_C, 2)

    # ── sub-toolbar ───────────────────────────────────────────────────────
    def _surfaces_bar_layout(self) -> list:
        """The bar under the canvas toolbar, shared by draw and click."""
        items = [
            ("line", self._TR("surf_bar_line", "Line"), not self._surf_area_mode),
            ("area", self._TR("surf_bar_area", "Area"), self._surf_area_mode),
            ("support", self._TR("surf_bar_support", "Support map"),
             self._surf_show_support),
            ("place", self._TR("surf_bar_place", "Place on surfaces..."), False),
            ("done", self._TR("surf_bar_done", "Done"), False),
        ]
        cr = self._canvas_rect()
        toolbar = self._get_toolbar_layout()
        top = max((it["r"].bottom for it in toolbar), default=cr.top) + TOOLBAR_ROW_GAP
        btn_h = self._toolbar_btn_h()
        left, right = cr.left + TOOLBAR_MARGIN, cr.right - TOOLBAR_MARGIN
        x, y = left, top
        out = []
        for key, label, active in items:
            width = _button_w(label, "sm", min_w=TOOLBAR_BTN_PAD_X * 2)
            if x > left and x + width > right:
                x, y = left, y + btn_h + TOOLBAR_ROW_GAP
            out.append({"id": key, "lbl": label, "active": active,
                        "r": pygame.Rect(x, y, width, btn_h)})
            x += width + TOOLBAR_GAP
        return out

    def _surfaces_bar_click(self, mx: int, my: int) -> bool:
        if self.mode != MODE_SURFACES:
            return False
        for item in self._surfaces_bar_layout():
            if not _in_rect((mx, my), item["r"]):
                continue
            key = item["id"]
            if key == "line":
                self._surf_area_mode = False
            elif key == "area":
                self._surf_area_mode = True
            elif key == "support":
                self._surfaces_toggle_support()
            elif key == "place":
                self._place_open_dialog()
            elif key == "done":
                self._surfaces_leave()
            return True
        return False

    def _r_surfaces_bar(self) -> None:
        mx, my = pygame.mouse.get_pos()
        items = self._surfaces_bar_layout()
        for item in items:
            r, active = item["r"], item["active"]
            hov = _in_rect((mx, my), r)
            primary = item["id"] == "place"
            bg = BTN_AC if active else (BTN_HO if hov else STATUS)
            _rect(self.screen, bg, r, radius=4)
            _rect(self.screen, OK_C if primary else (ACCENT if active else BORDER),
                  r, 1, radius=4)
            tw, th = _text_wh(item["lbl"], "sm")
            self.screen.blit(_txt(item["lbl"], "sm", TXT_HI if (active or hov) else TXT),
                             (r.x + (r.w - tw) // 2, r.y + (r.h - th) // 2))
        if not items:
            return
        hint = self._TR("surf_hint",
                        "Drag = line (left to right) | Shift+drag = area | "
                        "click = select | Del = delete | arrows = nudge | Esc = done")
        if self._surf_support_busy:
            hint = self._TR("surf_support_busy",
                            "Computing the support map (CPU, cached)...")
        tw, th = _text_wh(hint, "xs")
        bottom = max(it["r"].bottom for it in items)
        x = items[0]["r"].x
        width = min(tw + TOOLBAR_BTN_PAD_X, self._canvas_rect().right - TOOLBAR_MARGIN - x)
        box = pygame.Rect(x, bottom + TOOLBAR_ROW_GAP, width, th + TOOLBAR_ROW_GAP * 2)
        pill = pygame.Surface(box.size, pygame.SRCALPHA)
        pygame.draw.rect(pill, HUD_BG, pill.get_rect(), border_radius=4)
        self.screen.blit(pill, box.topleft)
        _draw_text(self.screen, hint, "xs", TXT_DIM, box.x + TOOLBAR_BTN_PAD_X // 2,
                   box.y + TOOLBAR_ROW_GAP, box.w - TOOLBAR_BTN_PAD_X)

    # ── canvas drawing ────────────────────────────────────────────────────
    def _r_surfaces_overlay(self, cr: pygame.Rect, active: bool = True) -> None:
        """Forbidden bands, support map, surfaces and their gizmos.

        `active` is False when the surfaces are only shown under a placement
        preview: then they are drawn thin and without handles or labels.
        """
        if getattr(self, "bg_surf", None) is None:
            return
        self._surfaces_consume_support()
        if active:
            self._r_surfaces_forbidden(cr)
            if self._surf_show_support:
                self._r_surfaces_support(cr)
        for i, s in enumerate(self._surfaces()):
            self._r_surface_one(s, selected=(active and i == self._surf_sel),
                                labels=active)
        drag = self._surf_drag
        if active and drag and drag["op"] in ("new_line", "new_area"):
            (x0, y0), (x1, y1) = drag["start"], drag["cur"]
            if drag["op"] == "new_area":
                preview = sf.new_area(x0, y0, x1, y1, self._surfaces_default_h(True),
                                      self._surf_last_h.get("near"))
            else:
                preview = sf.new_line(x0, y0, x1, y1, self._surfaces_default_h(False))
            self._r_surface_one(preview, selected=True, labels=False)

    def _r_surfaces_forbidden(self, cr: pygame.Rect) -> None:
        rules = self._surfaces_rules()
        bw, bh = self.bg_surf.get_size()
        hud_y = bh * (1.0 - rules["hud_band"])
        edge_x, edge_y = bw * rules["edge"], bh * rules["edge"]
        bands = [
            ((0, hud_y, bw, bh), SURF_HUD_C),
            ((0, 0, bw, edge_y), SURF_MARGIN_C),
            ((0, edge_y, edge_x, hud_y), SURF_MARGIN_C),
            ((bw - edge_x, edge_y, bw, hud_y), SURF_MARGIN_C),
        ]
        for (x0, y0, x1, y1), color in bands:
            sx0, sy0 = self._r2s(x0, y0)
            sx1, sy1 = self._r2s(x1, y1)
            r = pygame.Rect(int(sx0), int(sy0), int(sx1 - sx0) + 1,
                            int(sy1 - sy0) + 1).clip(cr)
            if r.w <= 0 or r.h <= 0:
                continue
            band = pygame.Surface(r.size, pygame.SRCALPHA)
            band.fill(color)
            self.screen.blit(band, r.topleft)
        sx, sy = self._r2s(0, hud_y)
        label = self._TR("surf_hud_band", "HUD: nothing is placed here")
        lx = max(cr.left + SURF_LABEL_PAD, int(sx) + SURF_LABEL_PAD)
        ly = int(sy) + SURF_LABEL_PAD
        if cr.top <= ly < cr.bottom:
            _draw_text(self.screen, label, "xs", SURF_HUD_LABEL_C, lx, ly)

    def _r_surfaces_support(self, cr: pygame.Rect) -> None:
        surf = self._surf_support_surf
        if surf is None:
            return
        step = self._surf_support_step
        bw, bh = self.bg_surf.get_size()
        # Visible part of the background, in the small map's cells.
        rx0, ry0 = self._s2r(cr.left, cr.top)
        rx1, ry1 = self._s2r(cr.right, cr.bottom)
        cx0 = max(0, int(max(0.0, rx0) // step))
        cy0 = max(0, int(max(0.0, ry0) // step))
        cx1 = min(surf.get_width(), int(min(float(bw), rx1) // step) + 1)
        cy1 = min(surf.get_height(), int(min(float(bh), ry1) // step) + 1)
        if cx1 <= cx0 or cy1 <= cy0:
            return
        key = (cx0, cy0, cx1, cy1, round(self.zoom, 4), round(self.origin_x, 1),
               round(self.origin_y, 1))
        cache = self._surf_support_cache
        if cache is None or cache[0] != key:
            sx0, sy0 = self._r2s(cx0 * step, cy0 * step)
            sx1, sy1 = self._r2s(cx1 * step, cy1 * step)
            size = (max(1, int(sx1 - sx0)), max(1, int(sy1 - sy0)))
            sub = surf.subsurface(pygame.Rect(cx0, cy0, cx1 - cx0, cy1 - cy0))
            cache = (key, pygame.transform.scale(sub, size), (int(sx0), int(sy0)))
            self._surf_support_cache = cache
        self.screen.blit(cache[1], cache[2])

    def _r_surface_one(self, s: dict, selected: bool, labels: bool) -> None:
        area = sf.is_area(s)
        color = SEL_C if selected else (SURF_AREA_C if area else SURF_LINE_C)
        width = SURF_SEL_LINE_W if selected else SURF_LINE_W
        x0, y0, x1, y1 = (float(v) for v in s["p"])
        far, near = sf.heights(s)
        h_mul = self._surfaces_h_mul()
        a, b = self._r2s(x0, y0), self._r2s(x1, y1)
        if area:
            rect = pygame.Rect(int(min(a[0], b[0])), int(min(a[1], b[1])),
                               int(abs(b[0] - a[0])) + 1, int(abs(b[1] - a[1])) + 1)
            pygame.draw.rect(self.screen, color, rect, width)
            ticks = [(min(x0, x1), min(y0, y1), far), (min(x0, x1), max(y0, y1), near)]
        else:
            pygame.draw.line(self.screen, color, (int(a[0]), int(a[1])),
                             (int(b[0]), int(b[1])), width)
            ticks = [(x0, y0, far)]
        # Size gizmo: a 20 cm object standing at that line, as the tool sees it.
        for tx, ty, th in ticks:
            top = self._r2s(tx, ty - th * h_mul)
            bottom = self._r2s(tx, ty)
            pygame.draw.line(self.screen, SURF_GIZMO_C, (int(top[0]), int(top[1])),
                             (int(bottom[0]), int(bottom[1])), SURF_GIZMO_W)
            pygame.draw.line(self.screen, SURF_GIZMO_C,
                             (int(top[0]) - HANDLE_R, int(top[1])),
                             (int(top[0]) + HANDLE_R, int(top[1])), SURF_GIZMO_W)
        if labels:
            size = (f"{far:g}/{near:g}" if area else f"{far:g}")
            text = f"{self._surfaces_kind_label(s.get('kind', ''))} {size}"
            if s.get("snap") is False:
                text += " " + self._TR("surf_label_nosnap", "(no snap)")
            tw, th = _text_wh(text, "xs")
            top = self._r2s(ticks[0][0], ticks[0][1] - ticks[0][2] * h_mul)
            box = pygame.Rect(int(top[0]) + HANDLE_R + SURF_LABEL_PAD,
                              int(top[1]) - th // 2 - SURF_LABEL_PAD,
                              tw + SURF_LABEL_PAD * 2, th + SURF_LABEL_PAD * 2)
            pill = pygame.Surface(box.size, pygame.SRCALPHA)
            pygame.draw.rect(pill, HUD_BG, pill.get_rect(), border_radius=3)
            self.screen.blit(pill, box.topleft)
            self.screen.blit(_txt(text, "xs", color),
                             (box.x + SURF_LABEL_PAD, box.y + SURF_LABEL_PAD))
        if selected:
            for _part, hx, hy in sf.handles(s):
                sx, sy = self._r2s(hx, hy)
                pygame.draw.circle(self.screen, TXT_HI, (int(sx), int(sy)), HANDLE_R + 1)
                pygame.draw.circle(self.screen, SURF_HANDLE_RIM_C, (int(sx), int(sy)),
                                   HANDLE_R + 1, 1)

    # ── properties panel ──────────────────────────────────────────────────
    def _surf_hbox(self, name: str, rx0: int, rect: pygame.Rect) -> None:
        """Register a hitbox in the panel's virtual space (like _set_hbox_*)."""
        self._surface_props_hitboxes[name] = pygame.Rect(
            rect.x - rx0, rect.y + self.prop_scroll - TOP_BAR_H, rect.w, rect.h)

    def _r_surf_num_row(self, rx0: int, y: int, label: str, key: str,
                        idx: int, text: str) -> int:
        """Label, then [-] [value] [+]. Returns the y under the row."""
        mx, my = pygame.mouse.get_pos()
        y += _draw_text_wrapped(self.screen, label, "sm", TXT_DIM, rx0 + _ps(8), y,
                                self.panel_r_w - _ps(16))
        y += _ps(2)
        box_w, field_h = self._prop_field_metrics()
        btn_w = _button_w("+", "sm")
        x = rx0 + _ps(8)
        minus = pygame.Rect(x, y, btn_w, field_h)
        box = pygame.Rect(minus.right + _ps(4), y, box_w, field_h)
        plus = pygame.Rect(box.right + _ps(4), y, btn_w, field_h)
        editing = getattr(self, "_editing_prop", None) == ("surface", idx, key)
        step_button(self.screen, minus, "-", _in_rect((mx, my), minus))
        _input_box(self.screen, box, self._prop_buf if editing else text, editing,
                   font="sm")
        step_button(self.screen, plus, "+", _in_rect((mx, my), plus))
        self._surf_hbox(f"{key}_minus", rx0, minus)
        self._surf_hbox(f"{key}_box", rx0, box)
        self._surf_hbox(f"{key}_plus", rx0, plus)
        return y + field_h + _ps(10)

    def _r_surface_props(self, rx0: int, y: int) -> int:
        """The right panel in surfaces mode. Returns the y under the content."""
        self._surface_props_hitboxes = {}
        mx, my = pygame.mouse.get_pos()
        full_w = self.panel_r_w - _ps(16)
        line_h = _text_wh("Ag", "sm")[1]
        surfaces = self._surfaces()
        n_area = sum(1 for s in surfaces if sf.is_area(s))
        _draw_text(self.screen, self._TR("surf_panel_hdr", "PLACEMENT SURFACES"),
                   "sm", ACCENT, rx0 + _ps(8), y, full_w)
        y += line_h + _ps(4)
        _draw_text(self.screen, self._TR(
            "surf_panel_count", "{n} lines, {a} areas").format(
                n=len(surfaces) - n_area, a=n_area),
            "xs", TXT_DIM, rx0 + _ps(8), y, full_w)
        y += _text_wh("Ag", "xs")[1] + _ps(6)
        pygame.draw.line(self.screen, BORDER, (rx0, y), (rx0 + self.panel_r_w, y))
        y += _ps(8)

        idx = self._surf_sel
        if idx is not None and idx < len(surfaces):
            s = surfaces[idx]
            _draw_text(self.screen, self._TR("surf_panel_sel", "Surface {n}").format(
                n=idx + 1), "sm", TXT_HI, rx0 + _ps(8), y, full_w)
            y += line_h + _ps(6)
            # Kind: one button per kind, wrapped to the panel width.
            x = rx0 + _ps(8)
            btn_h = line_h + _ps(8)
            for kind in sf.KINDS:
                label = self._surfaces_kind_label(kind)
                w = _button_w(label, "sm")
                if x > rx0 + _ps(8) and x + w > rx0 + self.panel_r_w - _ps(8):
                    x = rx0 + _ps(8)
                    y += btn_h + _ps(4)
                r = pygame.Rect(x, y, w, btn_h)
                _button(self.screen, r, label, _in_rect((mx, my), r),
                        active=(s.get("kind") == kind))
                self._surf_hbox(f"kind_{kind}", rx0, r)
                x += w + _ps(4)
            y += btn_h + _ps(10)
            far, near = sf.heights(s)
            if sf.is_area(s):
                y = self._r_surf_num_row(rx0, y, self._TR(
                    "surf_far", "Far size (px of a 20 cm object, top edge)"),
                    "h_far", idx, f"{far:g}")
                y = self._r_surf_num_row(rx0, y, self._TR(
                    "surf_near", "Near size (bottom edge)"), "h_near", idx, f"{near:g}")
            else:
                y = self._r_surf_num_row(rx0, y, self._TR(
                    "surf_h", "Size (px of a 20 cm object standing here)"),
                    "h", idx, f"{far:g}")
                snap_r = pygame.Rect(rx0 + _ps(4), y, self.panel_r_w - _ps(8),
                                     max(_ps(28), line_h + _ps(10)))
                self._render_toggle(snap_r.x, snap_r.y, snap_r.w, snap_r.h,
                                    self._TR("surf_snap", "Snap to the painted edge"),
                                    s.get("snap", True) is not False,
                                    hover=_in_rect((mx, my), snap_r))
                self._surf_hbox("snap", rx0, snap_r)
                y += snap_r.h + _ps(8)
            max_text = (str(s["max"]) if "max" in s
                        else self._TR("surf_max_auto", "auto"))
            y = self._r_surf_num_row(rx0, y, self._TR("surf_max", "Max objects"),
                                     "max", idx, max_text)
            x0, y0, x1, y1 = s["p"]
            _draw_text(self.screen, f"({x0:g}, {y0:g}) - ({x1:g}, {y1:g})", "xs",
                       TXT_DIM, rx0 + _ps(8), y, full_w)
            y += _text_wh("Ag", "xs")[1] + _ps(8)
            del_r = pygame.Rect(rx0 + _ps(4), y, self.panel_r_w - _ps(8), btn_h + _ps(4))
            _button(self.screen, del_r, self._TR("surf_delete", "Delete surface"),
                    _in_rect((mx, my), del_r), danger=True)
            self._surf_hbox("delete", rx0, del_r)
            y += del_r.h + _ps(10)
        else:
            hint = self._TR(
                "surf_panel_hint",
                "Drag on the scene to draw a resting line (a shelf board, a table "
                "edge, a sill), left to right, where painted objects touch it. "
                "Shift+drag draws an area (floor or table top seen from above). "
                "Click a surface to edit it.")
            y += _draw_text_wrapped(self.screen, hint, "xs", TXT_DIM, rx0 + _ps(8), y,
                                    full_w)
            y += _ps(10)

        pygame.draw.line(self.screen, BORDER, (rx0, y), (rx0 + self.panel_r_w, y))
        y += _ps(8)
        y = self._r_surf_num_row(rx0, y, self._TR(
            "surf_h_mul", "Scene size multiplier (h_mul)"), "h_mul", -1,
            f"{self._surfaces_h_mul():g}")
        btn_h = line_h + _ps(12)
        place_r = pygame.Rect(rx0 + _ps(4), y, self.panel_r_w - _ps(8), btn_h)
        _button(self.screen, place_r, self._TR("surf_bar_place", "Place on surfaces..."),
                _in_rect((mx, my), place_r), custom_bg=PLACE_APPLY_BG)
        self._surf_hbox("place", rx0, place_r)
        y += btn_h + _ps(6)
        done_r = pygame.Rect(rx0 + _ps(4), y, self.panel_r_w - _ps(8), btn_h)
        _button(self.screen, done_r, self._TR("surf_leave", "Leave surfaces mode"),
                _in_rect((mx, my), done_r))
        self._surf_hbox("done", rx0, done_r)
        return y + btn_h + _ps(8)

    def _surface_props_click(self, rx: int, my: int) -> bool:
        """Click on the surfaces panel; rx, my in the panel's virtual space."""
        hits = self._surface_props_hitboxes
        name = next((n for n, r in hits.items() if _in_rect((rx, my), r)), None)
        if name is None:
            return False
        idx = self._surf_sel if self._surf_sel is not None else -1
        fast = bool(pygame.key.get_mods() & pygame.KMOD_SHIFT)
        if name.startswith("kind_"):
            self._surfaces_set_kind(idx, name[len("kind_"):])
        elif name == "snap":
            self._surfaces_toggle_snap(idx)
        elif name == "delete":
            self._surfaces_delete()
        elif name == "place":
            self._place_open_dialog()
        elif name == "done":
            self._surfaces_leave()
        elif name.endswith("_box"):
            key = name[:-len("_box")]
            self._editing_prop = ("surface", -1 if key == "h_mul" else idx, key)
            self._prop_buf = ""
        elif name.endswith(("_minus", "_plus")):
            key, _, which = name.rpartition("_")
            sign = 1 if which == "plus" else -1
            self._surfaces_step(idx, key, sign, fast)
        return True

    def _surfaces_step(self, idx: int, key: str, sign: int, fast: bool) -> None:
        if key == "h_mul":
            self._surfaces_set_value(-1, key, self._surfaces_h_mul() + sign * SURF_HMUL_STEP)
            return
        if not 0 <= idx < len(self._surfaces()):
            return
        s = self._surfaces()[idx]
        if key == "max":
            current = s.get("max")
            if current is None:
                self._surfaces_set_value(idx, key, 1 if sign > 0 else None)
            else:
                self._surfaces_set_value(idx, key, current + sign)
            return
        far, near = sf.heights(s)
        current = near if key == "h_near" else far
        step = SURF_H_STEP_FAST if fast else SURF_H_STEP
        self._surfaces_set_value(idx, key, current + sign * step)
