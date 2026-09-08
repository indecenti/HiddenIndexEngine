"""
editor/mixins/lang_translate.py

LangTranslateMixin - machine translation inside the translation editor.

A project carries thousands of keys in five languages, so the distance between
"the strings exist in English" and "the game is playable in German" is
thousands of small edits. This fills the empty cells with a model that runs on
the machine: nothing leaves it, and after the language packages are downloaded
once it works offline.

Nothing happens without being asked twice. A request builds a *plan* - which
cells, from which language, into which - and shows it: how many cells, which
languages, and whether a package has to be downloaded first. Only then does
anything run, in a worker thread, with a progress bar and a cancel button. The
plan only ever fills empty cells, and a result that lost a placeholder is
refused rather than written (see editor/tools/translator.py).
"""

from __future__ import annotations

import logging
import threading
from typing import List, Optional

import pygame

from editor.constants import (
    ACCENT, BORDER, ERR_C, OK_C, PANEL, TXT, TXT_DIM, TXT_HI, WARN_C,
    TR_PANEL_W, TR_PAD, TR_SCRIM,
)
from editor.tools.translator import (
    STATUS_NO_BACKEND, STATUS_NO_MODEL, ArgosBackend, TranslationJob,
    TranslationService,
)
from editor.tools.translator_backends import discover_backends
from editor.ui.draw import (
    _button, _button_w, _draw_text, _draw_text_wrapped, _in_rect, _rect,
    _text_wh, _wrap_lines,
)

logger = logging.getLogger(__name__)

# What a request covers.
SCOPE_CELL = "cell"        # only the selected cell
SCOPE_VISIBLE = "visible"  # the keys the list is showing


class LangTranslateMixin:
    """Plan, confirm, run and apply a machine translation."""

    # ── Stato ───────────────────────────────────────────────────────────────

    def _lang_tr_init(self) -> None:
        """Reset the translation state. Called when the modal opens."""
        self._lang_tr_service = TranslationService(backend=ArgosBackend())
        self._lang_tr_plan: List[TranslationJob] = []
        self._lang_tr_scope = SCOPE_VISIBLE
        self._lang_tr_confirm = False
        self._lang_tr_busy = False
        self._lang_tr_done = 0
        self._lang_tr_failed = 0
        self._lang_tr_results: list = []
        self._lang_tr_message = ""
        self._lang_tr_hitboxes: dict = {}
        # Discovery probes localhost, so it waits for the first request rather
        # than slowing down the opening of the dialog.
        self._lang_tr_options: list = []
        self._lang_tr_choice = 0

    def _lang_tr_discover(self) -> list:
        """The engines available here, probed once per opening."""
        if not self._lang_tr_options:
            self._lang_tr_options = discover_backends()
            self._lang_tr_choice = next(
                (i for i, option in enumerate(self._lang_tr_options)
                 if option.ready), 0)
            self._lang_tr_apply_choice()
        return self._lang_tr_options

    def _lang_tr_apply_choice(self) -> None:
        """Point the service at the engine currently selected."""
        options = self._lang_tr_options
        if not options:
            return
        self._lang_tr_choice = max(0, min(self._lang_tr_choice, len(options) - 1))
        self._lang_tr_service.backend = options[self._lang_tr_choice].backend

    def _lang_tr_select(self, index: int) -> None:
        """Pick an engine and rebuild the plan for it."""
        self._lang_tr_choice = index
        self._lang_tr_apply_choice()

    def _lang_tr_cycle_model(self) -> None:
        """Next model of the selected engine, when it offers a choice."""
        option = self._lang_tr_selected()
        if option is None or len(option.models) < 2:
            return
        backend = option.backend
        current = getattr(backend, "model", "")
        index = (option.models.index(current) + 1) % len(option.models) \
            if current in option.models else 0
        backend.model = option.models[index]

    def _lang_tr_selected(self):
        options = self._lang_tr_options
        if not options:
            return None
        return options[max(0, min(self._lang_tr_choice, len(options) - 1))]

    def _lang_tr_targets(self) -> list:
        """Languages a translation would write into."""
        source = self._lang_tr_service.source_lang
        return [lang for lang in self.LANGS if lang != source]

    # ── Richiesta e conferma ────────────────────────────────────────────────

    def _lang_tr_request(self, scope: str) -> None:
        """Build the plan for `scope` and ask before doing anything."""
        if self._lang_tr_busy:
            return
        self._lang_tr_discover()
        service = self._lang_tr_service
        service.source_lang = self.LANGS[0]

        if scope == SCOPE_CELL:
            if not self._lang_sel:
                return
            row, column = self._lang_sel
            if row >= len(self._lang_filtered_keys):
                return
            keys = [self._lang_filtered_keys[row]]
            targets = [self.LANGS[column]]
        else:
            keys = list(self._lang_filtered_keys)
            targets = self._lang_tr_targets()

        self._lang_tr_scope = scope
        self._lang_tr_plan = service.plan(keys, targets, self._lang_cell_value)
        self._lang_tr_message = ""
        self._lang_tr_confirm = True

    def _lang_tr_dismiss(self) -> None:
        """Close the confirmation without translating anything."""
        self._lang_tr_confirm = False
        self._lang_tr_plan = []

    # ── Esecuzione ──────────────────────────────────────────────────────────

    def _lang_tr_start(self, download_first: bool = False) -> None:
        """Run the plan in a worker thread."""
        plan = list(self._lang_tr_plan)
        if not plan or self._lang_tr_busy:
            return
        service = self._lang_tr_service
        service.reset()
        self._lang_tr_confirm = False
        self._lang_tr_busy = True
        self._lang_tr_done = 0
        self._lang_tr_failed = 0
        self._lang_tr_results = []
        pairs = service.missing_pairs(sorted({job.target for job in plan}))

        def worker() -> None:
            try:
                if download_first:
                    for source, target in pairs:
                        if service.cancelled():
                            break
                        service.backend.download(source, target)
                service.run(plan,
                            on_done=lambda job, text: self._lang_tr_results.append(
                                (job, text)),
                            on_error=lambda job, exc: self._lang_tr_note_failure())
            except Exception as exc:                       # noqa: BLE001
                logger.error(f"[TRANSLATOR] batch fallito: {exc}")
            finally:
                self._lang_tr_busy = False

        threading.Thread(target=worker, daemon=True, name="lang_translate").start()

    def _lang_tr_note_failure(self) -> None:
        self._lang_tr_failed += 1

    def _lang_tr_cancel(self) -> None:
        self._lang_tr_service.cancel()

    def _lang_tr_poll(self) -> None:
        """Apply what the worker produced. Called from the render loop."""
        if not self._lang_tr_results:
            if not self._lang_tr_busy and self._lang_tr_plan and self._lang_tr_done:
                self._lang_tr_finish()
            return
        while self._lang_tr_results:
            job, text = self._lang_tr_results.pop(0)
            self._lang_data.setdefault(job.target, {})[job.key] = text
            self._lang_dirty = True
            self._lang_tr_done += 1
        self._bump_catalog_rev()
        if not self._lang_tr_busy:
            self._lang_tr_finish()

    def _lang_tr_finish(self) -> None:
        """Report the outcome once and forget the plan."""
        total = len(self._lang_tr_plan)
        self._lang_tr_plan = []
        if self._lang_tr_failed:
            self._status(self._TR("tr_done_partial",
                                  "Translated {n} of {total}, {failed} skipped").format(
                              n=self._lang_tr_done, total=total,
                              failed=self._lang_tr_failed), WARN_C, 5)
        else:
            self._status(self._TR("tr_done", "Translated {n} cells").format(
                n=self._lang_tr_done), OK_C, 4)

    # ── Rendering ───────────────────────────────────────────────────────────

    def _r_lang_translate(self, w: int, h: int) -> None:
        """The confirmation, or the progress of a running batch."""
        if not (self._lang_tr_confirm or self._lang_tr_busy):
            return
        service = self._lang_tr_service
        mx, my = pygame.mouse.get_pos()
        line_h = _text_wh("Ag", "sm")[1]
        btn_h = max(30, line_h + 12)

        scrim = pygame.Surface((w, h), pygame.SRCALPHA)
        scrim.fill(TR_SCRIM)
        self.screen.blit(scrim, (0, 0))

        title = self._TR("tr_title", "Machine translation")
        body = self._lang_tr_body()
        options = [] if self._lang_tr_busy else self._lang_tr_discover()
        row_h = line_h + 14
        box_w = min(TR_PANEL_W, w - 80)
        # The panel is as tall as the sentence it actually shows: sized for a
        # fixed four lines it left a band of nothing under a short one.
        body_lines = min(4, max(1, len(_wrap_lines(body, "sm",
                                                   box_w - TR_PAD * 2))))
        body_h = line_h * body_lines + 10
        engines_h = (line_h + 6 + len(options) * (row_h + 4)) if options else 0
        box_h = (TR_PAD * 3 + _text_wh(title, "lg")[1] + engines_h + body_h
                 + btn_h)
        box = pygame.Rect((w - box_w) // 2, max(20, (h - box_h) // 2), box_w, box_h)
        _rect(self.screen, PANEL, box, radius=10)
        _rect(self.screen, ACCENT, box, 2, radius=10)

        hits: dict = {}
        self._lang_tr_hitboxes = hits

        y = box.y + TR_PAD
        _draw_text(self.screen, title, "lg", TXT_HI, box.x + TR_PAD, y)
        y += _text_wh(title, "lg")[1] + TR_PAD // 2

        if options:
            _draw_text(self.screen, self._TR("tr_engine", "Engine"), "xs",
                       TXT_DIM, box.x + TR_PAD, y)
            y += line_h + 2
            rows = []
            for index, option in enumerate(options):
                row = pygame.Rect(box.x + TR_PAD, y, box.w - TR_PAD * 2, row_h)
                chosen = (index == self._lang_tr_choice)
                _rect(self.screen, (46, 60, 84) if chosen else (34, 36, 46),
                      row, radius=6)
                _rect(self.screen, ACCENT if chosen else BORDER, row,
                      2 if chosen else 1, radius=6)
                _draw_text(self.screen, option.label, "sm",
                           TXT_HI if chosen else TXT, row.x + 10,
                           row.y + (row_h - line_h) // 2, row.w // 2)
                detail = option.detail
                model = getattr(option.backend, "model", "")
                if model:
                    detail = f"{model}  ({detail})"
                colour = OK_C if option.ready else WARN_C
                detail_w = _text_wh(detail, "xs")[0]
                _draw_text(self.screen, detail, "xs", colour,
                           row.right - detail_w - 10,
                           row.y + (row_h - _text_wh(detail, "xs")[1]) // 2,
                           row.w // 2)
                rows.append(row)
                y += row_h + 4
            hits["engines"] = rows
            y += 4

        _draw_text_wrapped(self.screen, body, "sm", TXT, box.x + TR_PAD, y,
                           box.w - TR_PAD * 2, max_lines=body_lines)
        y = box.bottom - TR_PAD - btn_h
        if self._lang_tr_busy:
            bar = pygame.Rect(box.x + TR_PAD, y - 18, box.w - TR_PAD * 2, 6)
            total = max(1, len(self._lang_tr_plan))
            _rect(self.screen, (40, 42, 55), bar, radius=3)
            _rect(self.screen, ACCENT,
                  pygame.Rect(bar.x, bar.y,
                              int(bar.w * min(1.0, self._lang_tr_done / total)),
                              bar.h), radius=3)
            label = self._TR("btn_cancel", "Cancel")
            rect = pygame.Rect(box.right - TR_PAD - _button_w(label, "sm", min_w=120),
                               y, _button_w(label, "sm", min_w=120), btn_h)
            _button(self.screen, rect, label, _in_rect((mx, my), rect), danger=True)
            hits["cancel_run"] = rect
            return

        status = service.status(sorted({job.target for job in self._lang_tr_plan}))
        close_label = self._TR("btn_cancel", "Cancel")
        close_w = _button_w(close_label, "sm", min_w=120)
        close_r = pygame.Rect(box.right - TR_PAD - close_w, y, close_w, btn_h)
        _button(self.screen, close_r, close_label, _in_rect((mx, my), close_r))
        hits["dismiss"] = close_r

        if status == STATUS_NO_BACKEND or not self._lang_tr_plan:
            return
        if status == STATUS_NO_MODEL:
            go_label = self._TR("tr_download_and_run", "Download and translate")
        else:
            go_label = self._TR("tr_run", "Translate")
        go_w = _button_w(go_label, "sm", min_w=160)
        go_r = pygame.Rect(close_r.left - go_w - 10, y, go_w, btn_h)
        _button(self.screen, go_r, go_label, _in_rect((mx, my), go_r),
                custom_bg=OK_C)
        hits["run"] = go_r
        hits["needs_download"] = (status == STATUS_NO_MODEL)

    def _lang_tr_body(self) -> str:
        """The sentence the confirmation shows."""
        service = self._lang_tr_service
        if self._lang_tr_busy:
            return self._TR("tr_running", "Translating {n} of {total}...").format(
                n=self._lang_tr_done, total=len(self._lang_tr_plan))
        targets = sorted({job.target for job in self._lang_tr_plan})
        status = service.status(targets)
        if status == STATUS_NO_BACKEND:
            return self._TR(
                "tr_no_backend",
                "No translation engine installed. Install it with: {cmd}").format(
                    cmd=ArgosBackend.install_hint)
        if not self._lang_tr_plan:
            return self._TR("tr_nothing", "Nothing to translate: no empty cell "
                                          "with a source text.")
        lines = [self._TR("tr_summary",
                          "{n} empty cells, from {source} into {targets}.").format(
                     n=len(self._lang_tr_plan),
                     source=service.source_lang.upper(),
                     targets=", ".join(t.upper() for t in targets))]
        lines.append(self._TR("tr_only_empty",
                              "Only empty cells are filled; nothing is overwritten."))
        if status == STATUS_NO_MODEL:
            pairs = service.missing_pairs(targets)
            lines.append(self._TR(
                "tr_needs_download",
                "{n} language packages have to be downloaded first.").format(
                    n=len(pairs)))
        return "  ".join(lines)

    # ── Input ───────────────────────────────────────────────────────────────

    def _lang_tr_click(self, mx: int, my: int) -> bool:
        """Click on the confirmation or the progress panel. True when taken."""
        if not (self._lang_tr_confirm or self._lang_tr_busy):
            return False
        hits = getattr(self, "_lang_tr_hitboxes", {})
        for index, row in enumerate(hits.get("engines", [])):
            if _in_rect((mx, my), row):
                if index == self._lang_tr_choice:
                    self._lang_tr_cycle_model()
                else:
                    self._lang_tr_select(index)
                return True
        if _in_rect((mx, my), hits.get("cancel_run", pygame.Rect(0, 0, 0, 0))):
            self._lang_tr_cancel()
            return True
        if _in_rect((mx, my), hits.get("run", pygame.Rect(0, 0, 0, 0))):
            self._lang_tr_start(download_first=bool(hits.get("needs_download")))
            return True
        if _in_rect((mx, my), hits.get("dismiss", pygame.Rect(0, 0, 0, 0))):
            self._lang_tr_dismiss()
            return True
        return True          # the panel is modal: it eats the rest

    def _lang_tr_key(self, ev) -> bool:
        """Keys while the panel is up. True when the event was taken."""
        if not (self._lang_tr_confirm or self._lang_tr_busy):
            return False
        if ev.key == pygame.K_ESCAPE:
            if self._lang_tr_busy:
                self._lang_tr_cancel()
            else:
                self._lang_tr_dismiss()
        elif ev.key in (pygame.K_RETURN, pygame.K_KP_ENTER) and not self._lang_tr_busy:
            hits = getattr(self, "_lang_tr_hitboxes", {})
            if "run" in hits:
                self._lang_tr_start(download_first=bool(hits.get("needs_download")))
        return True
