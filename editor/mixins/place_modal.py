"""
editor/mixins/place_modal.py

PlaceModalMixin - "Place on surfaces": the believable placement, from the editor.

Runs `tools/place_on_surfaces.py` (Placer.plan_scene) on the open scene, with
the surfaces drawn in the surfaces mode, and shows the result on the canvas
before anything is written:

  1. the dialog: where the objects come from (the game's placement_plan.json
     entry for this scene, or the catalog filtered by the style and theme tag
     of the legacy scatter, both limited to engine/data/real_sizes_cm.json),
     how many, how many are goals, the alternative spots, the clue and the
     collectible, the seed, and whether the current objects are replaced (what
     the command line tool does) or kept and placed around;
  2. the run, in a worker thread with progress and cancel (the UI never
     freezes; the support map of the areas is computed on the CPU, once);
  3. the result: ghosts on the canvas (the objects the run would replace are
     hidden), each alternative spot viewable, the audit sheet of the tool in a
     scrollable dialog, then Apply (one undo step, the scene objects rewritten
     exactly as the tool writes them), Re-roll (a new seed) or Discard.

The dialog is app modal; the result bar lets the canvas pan and zoom so the
ghosts can be inspected at full size.
"""

from __future__ import annotations

import logging
import random
from typing import Any, Optional

import pygame

from editor.constants import (
    ACCENT, BORDER, ERR_C, MODE_SURFACES, OK_C, PANEL, TXT, TXT_DIM, TXT_HI,
    WARN_C, HUD_BG, TOOLBAR_GAP, TOOLBAR_MARGIN, TOOLBAR_ROW_GAP,
    PLACE_ALT_MAX, PLACE_COUNT_MAX, PLACE_DIALOG_W, PLACE_GHOST_ALPHA, PLACE_PAD,
    PLACE_ROLE_C, PLACE_ROW_GAP, PLACE_SCRIM, PLACE_SEED_MAX,
    PLACE_APPLY_BG, PLACE_FIELD_BG, PLACE_PROGRESS_BG, PLACE_PROGRESS_FILL,
    PLACE_ROW_PAD_Y, PLACE_LINE_GAP, PLACE_NUM_PAD, PLACE_NUM_MIN_W,
    PLACE_TAG_MIN_W, PLACE_RUN_MIN_W, PLACE_TEXT_INSET, PLACE_BAR_MIN, PLACE_STEP_FAST,
    AUDIT_MARGIN, AUDIT_SCROLL_STEP,
)
from editor.core import surfaces as sf
from editor.mixins.surfaces_mode import step_button
from editor.ui.draw import (
    _button, _button_w, _draw_text, _in_rect, _input_box, _rect, _scrollbar,
    _text_wh, _ui_scale, dialog_rect,
)

log = logging.getLogger(__name__)

STAGE_OPTIONS = "options"
STAGE_RUNNING = "running"
STAGE_RESULT = "result"

NUMERIC_FIELDS = ("count", "goals", "alt", "seed")
TEXT_FIELDS = ("clue", "collectible")
FIELD_ORDER = ("count", "goals", "alt", "seed", "clue", "collectible")
ID_CHARS = "abcdefghijklmnopqrstuvwxyz0123456789_-"


def _sc(value: float) -> int:
    """A dialog offset at the current UI scale."""
    return int(round(value * _ui_scale()))


class PlaceModalMixin:
    """The "Place on surfaces" dialog, its worker and its result preview."""

    # ── state ─────────────────────────────────────────────────────────────
    def _place_init_state(self) -> None:
        self._place_modal_open: bool = False
        self._place_stage: str = STAGE_OPTIONS
        self._place_opts: dict = {}
        self._place_opts_scene: Any = None
        self._place_base_cfg: dict = {}
        self._place_entry: Optional[dict] = None
        self._place_real_sizes: dict = {}
        self._place_focus: Optional[str] = None
        self._place_buf: str = ""
        self._place_job: Optional[sf.PlaceJob] = None
        self._place_busy: bool = False
        self._place_outcome: Optional[sf.PlaceOutcome] = None
        self._place_kept_idx: set = set()
        self._place_keep_mode: str = sf.KEEP_REPLACE
        self._place_variant: int = 0
        self._place_audit_surf: Optional[pygame.Surface] = None
        self._place_placers: dict = {}
        self._place_hitboxes: dict = {}
        self._place_msg: str = ""
        self._place_msg_color: tuple = TXT_DIM

    def _place_reset(self) -> None:
        """Scene change: nothing of the previous scene survives."""
        self._place_cancel_job()
        self._place_modal_open = False
        self._place_stage = STAGE_OPTIONS
        self._place_outcome = None
        self._place_audit_surf = None
        self._place_kept_idx = set()
        self._place_opts_scene = None
        self._place_focus = None

    # ── open / close ──────────────────────────────────────────────────────
    def _place_open_dialog(self) -> None:
        """Command "Place on surfaces...": open the dialog for this scene."""
        if not getattr(self, "scene_path", None):
            self._status(self._TR("surf_need_scene", "Open a scene first"), WARN_C, 2)
            return
        if getattr(self, "bg_surf", None) is None:
            self._status(self._TR("surf_need_background", "Load a background first"),
                         WARN_C, 2)
            return
        if not self._surfaces():
            if self.mode != MODE_SURFACES:
                self._surfaces_toggle_mode()
            self._status(self._TR(
                "place_need_surfaces",
                "No surfaces yet: draw them first (drag = line, Shift+drag = area)"),
                WARN_C, 5)
            return
        self._place_prepare()
        self._place_modal_open = True
        if self._place_stage != STAGE_RUNNING:
            self._place_stage = STAGE_OPTIONS
        self._place_focus = None
        self._place_set_msg(self._TR("place_ready", "Ready: Enter places the objects"),
                            TXT_DIM)
        self._mark_dirty()

    def _place_prepare(self) -> None:
        """The configuration the tool would use for this scene, and the dialog
        values, kept while the same scene stays open."""
        scene_dir = self.scene_path
        level, scene = scene_dir.parent.name, scene_dir.name
        rules = sf.placement_rules()
        plan_defaults, entry = sf.plan_for_scene(self.game_path, level, scene)
        cfg = sf.base_config(rules["defaults"], plan_defaults, entry, self._surf_doc,
                             level, scene)
        self._place_base_cfg = cfg
        self._place_entry = entry
        self._place_real_sizes = sf.load_real_sizes(self.base_path)
        if self._place_opts_scene == scene_dir and self._place_opts:
            return
        self._place_opts_scene = scene_dir
        has_plan_pool = bool(entry and entry.get("pool"))
        self._place_opts = {
            "pool": sf.POOL_PLAN if has_plan_pool else sf.POOL_CATALOG,
            "count": int(cfg.get("count", 0)),
            "goals": int(cfg.get("goals", 0)),
            "alt": int(cfg.get("alt_spots", 0)),
            "seed": int(cfg.get("seed") or random.randint(1, PLACE_SEED_MAX)),
            "clue": str(cfg.get("clue") or ""),
            "collectible": str(cfg.get("collectible") or ""),
            "keep": sf.KEEP_REPLACE,
        }

    def _place_close(self) -> None:
        """Discard: nothing is written, the preview disappears."""
        self._place_cancel_job()
        self._place_modal_open = False
        self._place_stage = STAGE_OPTIONS
        self._place_outcome = None
        self._place_audit_surf = None
        self._place_kept_idx = set()
        self._place_focus = None
        self._mark_dirty()

    def _place_cancel_job(self) -> None:
        job = self._place_job
        if job is not None:
            job.cancel()
        self._place_job = None
        self._place_busy = False

    def _place_set_msg(self, msg: str, color: tuple) -> None:
        self._place_msg = msg
        self._place_msg_color = color

    # ── pool ──────────────────────────────────────────────────────────────
    def _place_plan_pool(self) -> list:
        entry = self._place_entry or {}
        return sf.usable_pool(list(entry.get("pool", [])), self._place_real_sizes)

    def _place_catalog_pool(self) -> list:
        return sf.catalog_pool(self.catalog, self._scatter_style, self._scatter_tag,
                               self._place_real_sizes)

    def _place_pool(self) -> list:
        if self._place_opts.get("pool") == sf.POOL_PLAN and self._place_entry:
            return self._place_plan_pool()
        return self._place_catalog_pool()

    def _place_cycle_style(self) -> None:
        styles = ("real", "cartoon", "line art")
        cur = self._scatter_style if self._scatter_style in styles else styles[0]
        self._scatter_style = styles[(styles.index(cur) + 1) % len(styles)]
        self._scatter_tag = None

    def _place_cycle_tag(self, step: int) -> None:
        tags = [None] + [t for t, _n in self._scatter_available_tags()]
        cur = self._scatter_tag if self._scatter_tag in tags else None
        self._scatter_tag = tags[(tags.index(cur) + step) % len(tags)]

    # ── run ───────────────────────────────────────────────────────────────
    def _place_check(self) -> str:
        """Why the run cannot start, or ""."""
        if not self._surfaces():
            return self._TR("place_need_surfaces",
                            "No surfaces yet: draw them first (drag = line, Shift+drag = area)")
        if not self._place_pool():
            return self._TR("place_no_pool",
                            "No usable object: the pool is empty or none has a real size")
        known = {c.get("id") for c in self.catalog}
        for key in TEXT_FIELDS:
            value = self._place_opts.get(key, "")
            if value and value not in known:
                return self._TR("place_unknown_id", "Unknown catalog id: {id}").format(
                    id=value)
        if self._surfaces_scene_bg() is None:
            return self._TR("surf_need_background", "Load a background first")
        return ""

    def _place_run(self, reroll: bool = False) -> None:
        if self._place_busy:
            return
        self._place_commit_focus()
        if reroll:
            old = self._place_opts.get("seed")
            seed = random.randint(1, PLACE_SEED_MAX)
            while seed == old:
                seed = random.randint(1, PLACE_SEED_MAX)
            self._place_opts["seed"] = seed
        problem = self._place_check()
        if problem:
            self._place_set_msg(problem, ERR_C)
            self._place_stage = STAGE_OPTIONS
            self._place_modal_open = True
            return
        opts = self._place_opts
        cfg = dict(self._place_base_cfg)
        cfg.update({k: v for k, v in self._surf_doc.items() if k != "surfaces"})
        cfg["surfaces"] = [dict(s) for s in self._surfaces()]
        cfg["pool"] = self._place_pool()
        cfg["count"] = int(opts["count"])
        cfg["goals"] = int(opts["goals"])
        cfg["alt_spots"] = int(opts["alt"])
        cfg["seed"] = int(opts["seed"])
        cfg["clue"] = opts["clue"] or None
        cfg["collectible"] = opts["collectible"] or None
        objects = self.scene_data.get("objects", [])
        keep_mg = bool(cfg.get("keep_minigames"))
        self._place_keep_mode = opts["keep"]
        if opts["keep"] == sf.KEEP_ALL:
            self._place_kept_idx = set(range(len(objects)))
        else:
            self._place_kept_idx = {i for i, o in enumerate(objects)
                                    if keep_mg and o.get("minigame_trigger")}
        kept = sf.kept_objects(objects, opts["keep"], keep_mg)
        job = sf.PlaceJob(game_id=self.game_path.name,
                          scene_bg=self._surfaces_scene_bg(), cfg=cfg, kept=kept,
                          placer_cache=self._place_placers,
                          cache_key=(self.game_path.name,
                                     getattr(self, "_catalog_rev", 0)))
        self._place_job = job
        self._place_busy = True
        self._place_outcome = None
        self._place_audit_surf = None
        self._place_variant = 0
        self._place_stage = STAGE_RUNNING
        self._place_modal_open = True
        self._place_set_msg(self._TR("place_running", "Placing (seed {seed})...").format(
            seed=cfg["seed"]), ACCENT)
        self._mark_dirty()
        job.start()

    def _place_poll(self) -> None:
        """Collect the worker's result on the main thread (called every frame)."""
        job = self._place_job
        if job is None or not job.finished.is_set():
            return
        self._place_job = None
        self._place_busy = False
        if job.cancelled:
            self._place_stage = STAGE_OPTIONS
            self._place_set_msg(self._TR("place_cancelled", "Placement cancelled"), WARN_C)
            return
        if job.error:
            self._place_stage = STAGE_OPTIONS
            self._place_set_msg(self._TR("place_error", "Error: {e}").format(e=job.error),
                                ERR_C)
            return
        self._place_outcome = job.outcome
        self._place_stage = STAGE_RESULT
        self._mark_dirty()
        planned = len(job.outcome.planned)
        color = OK_C if planned >= job.outcome.count else WARN_C
        self._place_set_msg(self._place_summary(), color)

    def _place_summary(self) -> str:
        out = self._place_outcome
        if out is None:
            return ""
        alts = sum(len(o.get("alt_spots", [])) for o in out.planned)
        return self._TR(
            "place_summary",
            "{n} objects ({req} asked), {a} alternative spots, seed {seed}").format(
                n=len(out.planned), req=out.count, a=alts, seed=out.seed)

    def _place_apply(self) -> None:
        """Write the result into the scene, as the tool does, in one undo step."""
        out = self._place_outcome
        if out is None:
            return
        self._push_undo(self._TR("place_undo", "Place on surfaces"))
        new = sf.merged_scene(self.scene_data, out.kept, out.planned, out.goals)
        self.scene_data.clear()
        self.scene_data.update(new)
        self.selected_idx = None
        self.selected_indices = []
        self.scene_dirty = True
        n = len(out.planned)
        self._place_close()
        self._status(self._TR(
            "place_applied", "{n} objects placed: save the scene to keep them").format(n=n),
            OK_C, 5)

    def _place_cycle_variant(self) -> None:
        out = self._place_outcome
        if out is None:
            return
        n_alt = max((len(o.get("alt_spots", [])) for o in out.planned), default=0)
        self._place_variant = (self._place_variant + 1) % (n_alt + 1)

    def _place_open_audit(self) -> None:
        out = self._place_outcome
        if out is None or out.audit is None:
            self._place_set_msg(self._TR("place_no_audit", "No audit sheet for this run"),
                                WARN_C)
            return
        if self._place_audit_surf is None:
            img = out.audit.convert("RGB")
            self._place_audit_surf = pygame.image.frombuffer(
                img.tobytes(), img.size, "RGB").copy()
        self._modal_push(AuditView(self._place_audit_surf))

    # ── canvas preview ────────────────────────────────────────────────────
    def _place_preview_active(self) -> bool:
        return (self._place_modal_open and self._place_stage == STAGE_RESULT
                and self._place_outcome is not None)

    def _place_hides_object(self, idx: int) -> bool:
        """True for a scene object the previewed run would remove."""
        return self._place_preview_active() and idx not in self._place_kept_idx

    def _r_place_ghosts(self) -> None:
        if not self._place_preview_active():
            return
        for obj in self._place_outcome.planned:
            try:
                ghost = dict(sf.with_variant(obj, self._place_variant))
                ghost["alpha"] = PLACE_GHOST_ALPHA
                self._draw_obj_icon(ghost, self.screen, 0, 0)
                role = ("clue" if obj.get("clue_key") else
                        "collectible" if obj.get("collectible") else
                        "minigame" if obj.get("minigame_trigger") else "pool")
                scale = float(ghost.get("scale", 1.0))
                w, h = ghost.get("width", 0) * scale, ghost.get("height", 0) * scale
                a = self._r2s(ghost["x"], ghost["y"])
                b = self._r2s(ghost["x"] + w, ghost["y"] + h)
                pygame.draw.rect(self.screen, PLACE_ROLE_C[role],
                                 pygame.Rect(int(a[0]), int(a[1]),
                                             max(1, int(b[0] - a[0])),
                                             max(1, int(b[1] - a[1]))), 1)
            except Exception:
                log.warning("Ghost of %s not drawn", obj.get("catalog_id"), exc_info=True)

    # ── result bar ────────────────────────────────────────────────────────
    def _place_bar_layout(self) -> dict:
        """The result bar under the canvas toolbar: summary and buttons."""
        n_alt = max((len(o.get("alt_spots", [])) for o in self._place_outcome.planned),
                    default=0) if self._place_outcome else 0
        if self._place_variant == 0:
            view = self._TR("place_view_base", "View: base spots")
        else:
            view = self._TR("place_view_alt", "View: alternative {n}/{t}").format(
                n=self._place_variant, t=n_alt)
        buttons = [
            ("variant", view),
            ("audit", self._TR("place_btn_audit", "Audit")),
            ("reroll", self._TR("place_btn_reroll", "Re-roll")),
            ("options", self._TR("place_btn_options", "Options")),
            ("discard", self._TR("place_btn_discard", "Discard")),
            ("apply", self._TR("place_btn_apply", "Apply")),
        ]
        cr = self._canvas_rect()
        top = max((it["r"].bottom for it in self._get_toolbar_layout()),
                  default=cr.top) + TOOLBAR_ROW_GAP
        line_h = _text_wh("Ag", "sm")[1]
        btn_h = self._toolbar_btn_h()
        pad = _sc(PLACE_ROW_GAP)
        left, right = cr.left + TOOLBAR_MARGIN, cr.right - TOOLBAR_MARGIN
        x, y = left + pad, top + pad + line_h + pad
        rects = {}
        for key, label in buttons:
            width = _button_w(label, "sm")
            if x > left + pad and x + width > right - pad:
                x, y = left + pad, y + btn_h + TOOLBAR_ROW_GAP
            rects[key] = (pygame.Rect(x, y, width, btn_h), label)
            x += width + TOOLBAR_GAP
        bottom = max(r.bottom for r, _l in rects.values()) + pad
        width = max(r.right for r, _l in rects.values()) + pad - left
        width = max(width, _text_wh(self._place_msg, "sm")[0] + pad * 2)
        box = pygame.Rect(left, top, min(right - left, width), bottom - top)
        return {"box": box, "buttons": rects, "msg_pos": (left + pad, top + pad)}

    def _r_place_bar(self) -> None:
        layout = self._place_bar_layout()
        self._place_hitboxes = {k: r for k, (r, _l) in layout["buttons"].items()}
        self._place_hitboxes["bar"] = layout["box"]
        box = layout["box"]
        pill = pygame.Surface(box.size, pygame.SRCALPHA)
        pygame.draw.rect(pill, HUD_BG, pill.get_rect(), border_radius=6)
        self.screen.blit(pill, box.topleft)
        _rect(self.screen, ACCENT, box, 1, radius=6)
        _draw_text(self.screen, self._place_msg, "sm", self._place_msg_color,
                   *layout["msg_pos"], box.w - _sc(PLACE_ROW_GAP) * 2)
        mx, my = pygame.mouse.get_pos()
        for key, (r, label) in layout["buttons"].items():
            hov = _in_rect((mx, my), r)
            if key == "apply":
                _button(self.screen, r, label, hov, custom_bg=PLACE_APPLY_BG)
            elif key == "discard":
                _button(self.screen, r, label, hov, danger=True)
            else:
                _button(self.screen, r, label, hov,
                        active=(key == "variant" and self._place_variant > 0))

    def _place_bar_click(self, pos: tuple) -> bool:
        for key in ("variant", "audit", "reroll", "options", "discard", "apply"):
            r = self._place_hitboxes.get(key)
            if r is None or not _in_rect(pos, r):
                continue
            if key == "variant":
                self._place_cycle_variant()
            elif key == "audit":
                self._place_open_audit()
            elif key == "reroll":
                self._place_run(reroll=True)
            elif key == "options":
                self._place_back_to_options()
            elif key == "discard":
                self._place_close()
            elif key == "apply":
                self._place_apply()
            return True
        bar = self._place_hitboxes.get("bar")
        return bool(bar and _in_rect(pos, bar))

    def _place_back_to_options(self) -> None:
        self._place_outcome = None
        self._place_audit_surf = None
        self._place_stage = STAGE_OPTIONS
        self._place_set_msg(self._TR("place_ready", "Ready: Enter places the objects"),
                            TXT_DIM)
        self._mark_dirty()

    # ── dialog geometry ───────────────────────────────────────────────────
    def _place_field_text(self, key: str) -> str:
        if self._place_focus == key:
            return self._place_buf
        return str(self._place_opts.get(key, ""))

    def _place_rows(self) -> list:
        """(row id, label) of the dialog, top to bottom."""
        rows = [("pool", self._TR("place_lbl_pool", "Objects from"))]
        if self._place_opts.get("pool") == sf.POOL_CATALOG or not self._place_entry:
            rows.append(("filter", self._TR("place_lbl_filter", "Catalog filter")))
        rows += [
            ("count", self._TR("place_lbl_count", "Objects to place")),
            ("goals", self._TR("place_lbl_goals", "Goals per game")),
            ("alt", self._TR("place_lbl_alt", "Alternative spots")),
            ("seed", self._TR("place_lbl_seed", "Seed")),
            ("clue", self._TR("place_lbl_clue", "Clue object")),
            ("collectible", self._TR("place_lbl_collectible", "Collectible")),
            ("keep", self._TR("place_lbl_keep", "Current objects")),
        ]
        return rows

    def _place_dialog_layout(self, w: int, h: int) -> dict:
        """Every rect of the dialog: the renderer draws them, the click reads
        them back (docs/editor/EDITOR_UI.md, rule 2)."""
        rows = self._place_rows()
        line_h = _text_wh("Ag", "sm")[1]
        small_h = _text_wh("Ag", "xs")[1]
        row_h = line_h + _sc(PLACE_ROW_PAD_Y)
        gap = _sc(PLACE_ROW_GAP)
        pad = _sc(PLACE_PAD)
        label_w = max(_text_wh(label, "sm")[0] for _r, label in rows) + pad
        title_h = _text_wh("Ag", "md")[1] + small_h + gap * 2
        info_h = (small_h + _sc(PLACE_LINE_GAP)) * 2 + gap
        footer_h = row_h + gap
        status_h = small_h + gap * 2
        want_h = (pad * 2 + title_h + len(rows) * (row_h + gap) + info_h
                  + footer_h + status_h)
        box = dialog_rect(w, h, _sc(PLACE_DIALOG_W), want_h)
        L: dict = {"box": box, "rows": [], "row_h": row_h}
        L["close"] = pygame.Rect(box.right - pad - row_h, box.y + pad, row_h, row_h)
        x_ctrl = box.x + pad + label_w
        right = box.right - pad
        y = box.y + pad + title_h
        btn = _button_w("+", "sm")
        num_w = max(_text_wh(str(PLACE_SEED_MAX), "sm")[0] + _sc(PLACE_NUM_PAD),
                    _sc(PLACE_NUM_MIN_W))
        for row_id, label in rows:
            L["rows"].append((row_id, label, (box.x + pad, y + (row_h - line_h) // 2)))
            if row_id == "pool":
                plan_lbl = self._TR("place_pool_plan", "Plan ({n})").format(
                    n=len(self._place_plan_pool()) if self._place_entry else 0)
                cat_lbl = self._TR("place_pool_catalog", "Catalog ({n})").format(
                    n=len(self._place_catalog_pool()))
                a = pygame.Rect(x_ctrl, y, _button_w(plan_lbl, "sm"), row_h)
                b = pygame.Rect(a.right + gap, y, _button_w(cat_lbl, "sm"), row_h)
                L["pool_plan"], L["pool_catalog"] = (a, plan_lbl), (b, cat_lbl)
            elif row_id == "filter":
                style_lbl = (self._scatter_style or "real").upper()
                tag_lbl = (self._scatter_tag or self._TR("place_tag_all", "all tags"))
                s = pygame.Rect(x_ctrl, y, _button_w(style_lbl, "sm"), row_h)
                prev = pygame.Rect(s.right + gap, y, btn, row_h)
                tag_w = max(_sc(PLACE_TAG_MIN_W), right - (prev.right + gap) - btn - gap)
                tag = pygame.Rect(prev.right + gap, y, tag_w, row_h)
                nxt = pygame.Rect(tag.right + gap, y, btn, row_h)
                L["style"], L["tag_prev"] = (s, style_lbl), prev
                L["tag"], L["tag_next"] = (tag, tag_lbl), nxt
            elif row_id in ("count", "goals", "alt"):
                minus = pygame.Rect(x_ctrl, y, btn, row_h)
                box_r = pygame.Rect(minus.right + gap, y, num_w, row_h)
                plus = pygame.Rect(box_r.right + gap, y, btn, row_h)
                L[f"{row_id}_minus"], L[f"{row_id}_box"] = minus, box_r
                L[f"{row_id}_plus"] = plus
            elif row_id == "seed":
                box_r = pygame.Rect(x_ctrl, y, num_w + btn + gap, row_h)
                new_lbl = self._TR("place_new_seed", "New seed")
                L["seed_box"] = box_r
                L["seed_new"] = (pygame.Rect(box_r.right + gap, y,
                                             _button_w(new_lbl, "sm"), row_h), new_lbl)
            elif row_id in TEXT_FIELDS:
                L[f"{row_id}_box"] = pygame.Rect(x_ctrl, y, right - x_ctrl, row_h)
            elif row_id == "keep":
                rep = self._TR("place_keep_replace", "Replace")
                keep = self._TR("place_keep_all", "Keep and avoid")
                a = pygame.Rect(x_ctrl, y, _button_w(rep, "sm"), row_h)
                b = pygame.Rect(a.right + gap, y, _button_w(keep, "sm"), row_h)
                L["keep_replace"], L["keep_all"] = (a, rep), (b, keep)
            y += row_h + gap
        L["info_y"] = y
        y += info_h
        if self._place_stage == STAGE_RUNNING:
            cancel_lbl = self._TR("place_btn_cancel", "Cancel")
            cw = _button_w(cancel_lbl, "sm")
            L["cancel"] = (pygame.Rect(right - cw, y, cw, row_h), cancel_lbl)
            L["progress"] = pygame.Rect(box.x + pad, y, right - cw - gap - box.x - pad,
                                        row_h)
        else:
            run_lbl = self._TR("place_btn_run", "Place")
            close_lbl = self._TR("place_btn_close", "Close")
            rw = _button_w(run_lbl, "sm", min_w=_sc(PLACE_RUN_MIN_W))
            cw = _button_w(close_lbl, "sm")
            L["run"] = (pygame.Rect(right - rw, y, rw, row_h), run_lbl)
            L["close_btn"] = (pygame.Rect(right - rw - gap - cw, y, cw, row_h), close_lbl)
        L["status_y"] = y + row_h + gap
        return L

    # ── dialog render ─────────────────────────────────────────────────────
    def _r_place_modal(self, w: int, h: int) -> None:
        self._place_poll()
        if self._place_stage == STAGE_RESULT and self._place_outcome is not None:
            self._r_place_bar()
            return
        scrim = pygame.Surface((w, h), pygame.SRCALPHA)
        scrim.fill(PLACE_SCRIM)
        self.screen.blit(scrim, (0, 0))
        L = self._place_dialog_layout(w, h)
        self._place_hitboxes = L
        box = L["box"]
        pad = _sc(PLACE_PAD)
        mx, my = pygame.mouse.get_pos()
        _rect(self.screen, PANEL, box, radius=10)
        _rect(self.screen, ACCENT, box, 2, radius=10)
        _draw_text(self.screen, self._TR("place_title", "PLACE ON SURFACES"), "md", TXT_HI,
                   box.x + pad, box.y + pad, box.w - pad * 3 - L["close"].w)
        _draw_text(self.screen, self._TR(
            "place_subtitle",
            "Objects rest on the surfaces, at real size, lit like their spot"),
            "xs", TXT_DIM, box.x + pad, box.y + pad + _text_wh("Ag", "md")[1] + _sc(PLACE_LINE_GAP),
            box.w - pad * 2)
        _button(self.screen, L["close"], "X", _in_rect((mx, my), L["close"]))

        opts = self._place_opts
        for row_id, label, pos in L["rows"]:
            _draw_text(self.screen, label, "sm", TXT_DIM, *pos)
        if "pool_plan" in L:
            for key, value in (("pool_plan", sf.POOL_PLAN), ("pool_catalog", sf.POOL_CATALOG)):
                r, lbl = L[key]
                usable = value == sf.POOL_CATALOG or self._place_entry is not None
                _button(self.screen, r, lbl, _in_rect((mx, my), r) and usable,
                        active=(opts.get("pool") == value))
        if "style" in L:
            r, lbl = L["style"]
            _button(self.screen, r, lbl, _in_rect((mx, my), r))
            step_button(self.screen, L["tag_prev"], "<", _in_rect((mx, my), L["tag_prev"]))
            r, lbl = L["tag"]
            _rect(self.screen, PLACE_FIELD_BG, r, radius=4)
            _rect(self.screen, BORDER, r, 1, radius=4)
            _draw_text(self.screen, lbl, "sm", TXT, r.x + _sc(PLACE_TEXT_INSET),
                       r.y + (r.h - _text_wh("Ag", "sm")[1]) // 2,
                       r.w - _sc(PLACE_TEXT_INSET) * 2)
            step_button(self.screen, L["tag_next"], ">", _in_rect((mx, my), L["tag_next"]))
        for key in ("count", "goals", "alt"):
            if f"{key}_box" not in L:
                continue
            step_button(self.screen, L[f"{key}_minus"], "-",
                        _in_rect((mx, my), L[f"{key}_minus"]))
            _input_box(self.screen, L[f"{key}_box"], self._place_field_text(key),
                       self._place_focus == key, font="sm")
            step_button(self.screen, L[f"{key}_plus"], "+",
                        _in_rect((mx, my), L[f"{key}_plus"]))
        _input_box(self.screen, L["seed_box"], self._place_field_text("seed"),
                   self._place_focus == "seed", font="sm")
        r, lbl = L["seed_new"]
        _button(self.screen, r, lbl, _in_rect((mx, my), r))
        known = {c.get("id") for c in self.catalog}
        for key in TEXT_FIELDS:
            text = self._place_field_text(key)
            _input_box(self.screen, L[f"{key}_box"], text, self._place_focus == key,
                       hint=self._TR("place_none", "(none)"), font="sm")
            if text and text not in known and self._place_focus != key:
                _rect(self.screen, ERR_C, L[f"{key}_box"], 1, radius=6)
        for key, value in (("keep_replace", sf.KEEP_REPLACE), ("keep_all", sf.KEEP_ALL)):
            r, lbl = L[key]
            _button(self.screen, r, lbl, _in_rect((mx, my), r),
                    active=(opts.get("keep") == value))

        surfaces = self._surfaces()
        n_area = sum(1 for s in surfaces if sf.is_area(s))
        info = [self._TR("place_info_surfaces", "{n} lines and {a} areas").format(
            n=len(surfaces) - n_area, a=n_area)]
        if n_area:
            info[0] += " " + self._TR("place_info_support",
                                       "(areas use the support map: CPU, cached)")
        n_obj = len(self.scene_data.get("objects", []))
        if opts.get("keep") == sf.KEEP_ALL:
            info.append(self._TR("place_info_keep",
                                 "The {n} current objects stay and are avoided").format(
                                     n=n_obj))
        else:
            info.append(self._TR("place_info_replace",
                                 "Apply replaces the {n} current objects").format(n=n_obj))
        y = L["info_y"]
        for line in info:
            _draw_text(self.screen, line, "xs", TXT_DIM, box.x + pad, y, box.w - pad * 2)
            y += _text_wh("Ag", "xs")[1] + _sc(PLACE_LINE_GAP)

        if "progress" in L:
            self._r_place_progress(L["progress"])
            r, lbl = L["cancel"]
            _button(self.screen, r, lbl, _in_rect((mx, my), r), danger=True)
        else:
            r, lbl = L["close_btn"]
            _button(self.screen, r, lbl, _in_rect((mx, my), r))
            r, lbl = L["run"]
            _button(self.screen, r, lbl, _in_rect((mx, my), r), custom_bg=PLACE_APPLY_BG)
        _draw_text(self.screen, self._place_msg, "xs", self._place_msg_color,
                   box.x + pad, L["status_y"], box.w - pad * 2)

    def _r_place_progress(self, r: pygame.Rect) -> None:
        job = self._place_job
        phase, done, total = job.progress if job else (sf.PHASE_LOAD, 0, 1)
        names = {
            sf.PHASE_LOAD: self._TR("place_phase_load", "Loading the scene"),
            sf.PHASE_SUPPORT: self._TR("place_phase_support",
                                       "Support map (CPU, first time only)"),
            sf.PHASE_PLACE: self._TR("place_phase_place", "Placing"),
            sf.PHASE_ALT: self._TR("place_phase_alt", "Alternative spots"),
            sf.PHASE_AUDIT: self._TR("place_phase_audit", "Audit sheet"),
        }
        _rect(self.screen, PLACE_PROGRESS_BG, r, radius=5)
        frac = max(0.0, min(1.0, done / max(1, total)))
        if frac > 0:
            _rect(self.screen, PLACE_PROGRESS_FILL,
                  pygame.Rect(r.x, r.y, max(_sc(PLACE_BAR_MIN), int(r.w * frac)), r.h),
                  radius=5)
        _rect(self.screen, ACCENT, r, 1, radius=5)
        label = names.get(phase, phase)
        if total > 1:
            label = f"{label} {done}/{total}"
        tw, th = _text_wh(label, "sm")
        inset = _sc(PLACE_BAR_MIN)
        _draw_text(self.screen, label, "sm", TXT_HI, r.x + max(inset, (r.w - tw) // 2),
                   r.y + (r.h - th) // 2, r.w - inset * 2)

    # ── input ─────────────────────────────────────────────────────────────
    def _place_event(self, ev) -> bool:
        """ModalRouter adapter. The dialog takes every input; the result bar
        lets panning, zooming and the HUD reach the canvas."""
        if self._place_stage == STAGE_RESULT and self._place_outcome is not None:
            return self._place_result_event(ev)
        if ev.type == pygame.KEYDOWN:
            self._place_dialog_key(ev)
        elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
            self._place_dialog_click(ev.pos)
        return True

    def _place_result_event(self, ev) -> bool:
        if ev.type == pygame.KEYDOWN:
            if ev.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                self._place_apply()
            elif ev.key == pygame.K_ESCAPE:
                self._place_back_to_options()
            elif ev.key == pygame.K_v:
                self._place_cycle_variant()
            elif ev.key == pygame.K_r:
                self._place_run(reroll=True)
            return True
        if ev.type == pygame.MOUSEBUTTONDOWN:
            if ev.button == 1:
                if not self._place_bar_click(ev.pos):
                    self._hud_click(*ev.pos)
                return True
            return False                     # pan with the middle / right button
        if ev.type == pygame.MOUSEBUTTONUP and ev.button == 3:
            if not getattr(self, "_pan_moved", False):
                self._panning = False
                return True                  # no context menu under the preview
            return False
        if ev.type in (pygame.TEXTINPUT, pygame.KEYUP):
            return True
        return False

    def _place_dialog_click(self, pos: tuple) -> None:
        L = self._place_hitboxes or self._place_dialog_layout(*self.screen.get_size())
        if self._place_focus is not None:
            self._place_commit_focus()
        if _in_rect(pos, L["close"]):
            self._place_close()
            return
        if not _in_rect(pos, L["box"]):
            return
        if "cancel" in L and _in_rect(pos, L["cancel"][0]):
            self._place_cancel_job()
            self._place_stage = STAGE_OPTIONS
            self._place_set_msg(self._TR("place_cancelled", "Placement cancelled"), WARN_C)
            return
        if self._place_stage == STAGE_RUNNING:
            return
        opts = self._place_opts
        fast = bool(pygame.key.get_mods() & pygame.KMOD_SHIFT)
        if "run" in L and _in_rect(pos, L["run"][0]):
            self._place_run()
        elif "close_btn" in L and _in_rect(pos, L["close_btn"][0]):
            self._place_close()
        elif "pool_plan" in L and _in_rect(pos, L["pool_plan"][0]):
            if self._place_entry is not None:
                opts["pool"] = sf.POOL_PLAN
        elif "pool_catalog" in L and _in_rect(pos, L["pool_catalog"][0]):
            opts["pool"] = sf.POOL_CATALOG
        elif "style" in L and _in_rect(pos, L["style"][0]):
            self._place_cycle_style()
        elif "tag_prev" in L and _in_rect(pos, L["tag_prev"]):
            self._place_cycle_tag(-1)
        elif "tag_next" in L and _in_rect(pos, L["tag_next"]):
            self._place_cycle_tag(1)
        elif _in_rect(pos, L["seed_new"][0]):
            opts["seed"] = random.randint(1, PLACE_SEED_MAX)
        elif _in_rect(pos, L["keep_replace"][0]):
            opts["keep"] = sf.KEEP_REPLACE
        elif _in_rect(pos, L["keep_all"][0]):
            opts["keep"] = sf.KEEP_ALL
        else:
            for key in ("count", "goals", "alt"):
                step = PLACE_STEP_FAST if fast else 1
                if _in_rect(pos, L[f"{key}_minus"]):
                    self._place_set_number(key, opts[key] - step)
                    return
                if _in_rect(pos, L[f"{key}_plus"]):
                    self._place_set_number(key, opts[key] + step)
                    return
            for key in FIELD_ORDER:
                if _in_rect(pos, L[f"{key}_box"]):
                    self._place_focus = key
                    self._place_buf = str(opts.get(key, ""))
                    return

    def _place_set_number(self, key: str, value: int) -> None:
        limits = {"count": (1, PLACE_COUNT_MAX), "goals": (1, PLACE_COUNT_MAX),
                  "alt": (0, PLACE_ALT_MAX), "seed": (1, PLACE_SEED_MAX)}
        lo, hi = limits[key]
        self._place_opts[key] = int(max(lo, min(hi, value)))
        if key == "count" and self._place_opts["goals"] > self._place_opts["count"]:
            self._place_opts["goals"] = self._place_opts["count"]

    def _place_commit_focus(self) -> None:
        key = self._place_focus
        if key is None:
            return
        self._place_focus = None
        buf = self._place_buf.strip()
        if key in NUMERIC_FIELDS:
            if buf.isdigit():
                self._place_set_number(key, int(buf))
        else:
            self._place_opts[key] = buf

    def _place_dialog_key(self, ev) -> None:
        key = self._place_focus
        if key is not None:
            if ev.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                self._place_commit_focus()
            elif ev.key == pygame.K_ESCAPE:
                self._place_focus = None
            elif ev.key == pygame.K_TAB:
                self._place_commit_focus()
                nxt = FIELD_ORDER[(FIELD_ORDER.index(key) + 1) % len(FIELD_ORDER)]
                self._place_focus = nxt
                self._place_buf = str(self._place_opts.get(nxt, ""))
            elif ev.key == pygame.K_BACKSPACE:
                self._place_buf = self._place_buf[:-1]
            elif ev.unicode:
                ch = ev.unicode.lower() if key in TEXT_FIELDS else ev.unicode
                allowed = ID_CHARS if key in TEXT_FIELDS else "0123456789"
                if ch in allowed:
                    self._place_buf += ch
            return
        if ev.key == pygame.K_ESCAPE:
            if self._place_stage == STAGE_RUNNING:
                self._place_cancel_job()
                self._place_stage = STAGE_OPTIONS
                self._place_set_msg(self._TR("place_cancelled", "Placement cancelled"),
                                    WARN_C)
            else:
                self._place_close()
        elif ev.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            if self._place_stage == STAGE_OPTIONS:
                self._place_run()


class AuditView:
    """The tool's audit sheet, fitted to the window width and scrollable.

    Lives on the unified modal stack: Esc, Enter or a click outside close it,
    the wheel, the arrows and PageUp/PageDown scroll it.
    """

    def __init__(self, sheet: pygame.Surface) -> None:
        self.sheet = sheet
        self.scroll = 0
        self._scaled: Optional[pygame.Surface] = None
        self._box = pygame.Rect(0, 0, 0, 0)
        self._view = pygame.Rect(0, 0, 0, 0)
        self._close = pygame.Rect(0, 0, 0, 0)

    def _layout(self, editor: Any) -> None:
        w, h = editor.screen.get_size()
        margin = _sc(AUDIT_MARGIN)
        self._box = dialog_rect(w, h, w - margin * 2, h - margin * 2)
        pad = _sc(PLACE_PAD)
        head = _text_wh("Ag", "md")[1] + pad
        self._close = pygame.Rect(self._box.right - pad - head, self._box.y + pad // 2,
                                  head, head)
        self._view = pygame.Rect(self._box.x + pad, self._box.y + pad + head,
                                 self._box.w - pad * 2, self._box.h - pad * 2 - head)
        width = min(self._view.w, self.sheet.get_width())
        if self._scaled is None or self._scaled.get_width() != width:
            k = width / max(1, self.sheet.get_width())
            size = (max(1, width), max(1, int(self.sheet.get_height() * k)))
            self._scaled = pygame.transform.smoothscale(self.sheet, size)
        self.scroll = max(0, min(self.scroll, self.max_scroll()))

    def max_scroll(self) -> int:
        if self._scaled is None:
            return 0
        return max(0, self._scaled.get_height() - self._view.h)

    def render(self, editor: Any) -> None:
        self._layout(editor)
        w, h = editor.screen.get_size()
        scrim = pygame.Surface((w, h), pygame.SRCALPHA)
        scrim.fill(PLACE_SCRIM)
        editor.screen.blit(scrim, (0, 0))
        _rect(editor.screen, PANEL, self._box, radius=10)
        _rect(editor.screen, ACCENT, self._box, 2, radius=10)
        pad = _sc(PLACE_PAD)
        title = editor._TR("place_audit_title", "AUDIT SHEET")
        hint = editor._TR("place_audit_hint",
                          "Every object at twice its size on a 1280 px screen: "
                          "look for floating, too big, too dark or obvious ones")
        _draw_text(editor.screen, title, "md", TXT_HI, self._box.x + pad,
                   self._box.y + pad // 2)
        tw = _text_wh(title, "md")[0]
        _draw_text(editor.screen, hint, "xs", TXT_DIM, self._box.x + pad * 2 + tw,
                   self._box.y + pad // 2 + _sc(PLACE_LINE_GAP),
                   self._close.x - (self._box.x + pad * 3 + tw))
        mx, my = pygame.mouse.get_pos()
        _button(editor.screen, self._close, "X", _in_rect((mx, my), self._close))
        editor.screen.set_clip(self._view)
        editor.screen.blit(self._scaled, (self._view.x, self._view.y - self.scroll))
        editor.screen.set_clip(None)
        total = self._scaled.get_height()
        if total > self._view.h:
            _scrollbar(editor.screen, self._view.right - _sc(PLACE_BAR_MIN), self._view.y,
                       _sc(PLACE_LINE_GAP),
                       self._view.h, self.scroll, total, self._view.h)

    def _close_me(self, editor: Any) -> None:
        editor._modal_pop(self)
        editor._mark_dirty()

    def handle_event(self, editor: Any, ev) -> None:
        if ev.type == pygame.KEYDOWN:
            page = max(1, self._view.h - _sc(AUDIT_SCROLL_STEP))
            if ev.key in (pygame.K_ESCAPE, pygame.K_RETURN, pygame.K_KP_ENTER):
                self._close_me(editor)
            elif ev.key == pygame.K_DOWN:
                self.scroll += _sc(AUDIT_SCROLL_STEP)
            elif ev.key == pygame.K_UP:
                self.scroll -= _sc(AUDIT_SCROLL_STEP)
            elif ev.key == pygame.K_PAGEDOWN:
                self.scroll += page
            elif ev.key == pygame.K_PAGEUP:
                self.scroll -= page
            elif ev.key == pygame.K_HOME:
                self.scroll = 0
            elif ev.key == pygame.K_END:
                self.scroll = self.max_scroll()
        elif ev.type == pygame.MOUSEWHEEL:
            self.scroll -= ev.y * _sc(AUDIT_SCROLL_STEP)
        elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
            if _in_rect(ev.pos, self._close) or not _in_rect(ev.pos, self._box):
                self._close_me(editor)
                return
        self.scroll = max(0, min(self.scroll, self.max_scroll()))
