"""
editor/mixins/modal_router.py

ModalRouterMixin — one ordered path for every modal of the editor.

The editor grew two generations of modals: the new ones live on the unified
stack (`editor.modal_stack`, protocol `render(editor)` / `handle_event(editor,
ev)`), the older ones are a boolean flag on the editor plus a render function
and a handful of handlers. The flag based ones used to be dispatched by hand in
five different places (`_render`, `_on_key`, `_on_mdown`, `_on_mmove`,
`_on_wheel`), each with its own chain of `if`, and the three chains did not
agree: the quit confirmation was drawn over the auditor but the auditor still
ate the input, so closing the window with the auditor open left the editor
stuck behind a dialog that answered to nothing.

MODAL_LAYERS is now the single source of that order, top of the screen first.
Rendering walks it backwards (what is drawn last is on top), input walks it
forwards (what is on top is served first). Each layer has one adapter method
turning a single event into the calls that modal already had, and answering
whether the event was consumed: a modal that lets an event through (the
context menu clicked outside itself, the scatter modal painting on the canvas)
simply returns False and the next layer, or the editor, sees the event.

Adding a modal means adding one line to MODAL_LAYERS and one adapter, instead
of touching five dispatchers. Migrating one to the unified stack means deleting
its line and its adapter.
"""

from dataclasses import dataclass

import pygame

# Events a modal can consume. The others (window, quit, timers) always reach
# the editor: QUIT in particular must never be swallowed, or the window would
# stop closing while a modal is open.
MODAL_INPUT_EVENTS = (
    pygame.KEYDOWN, pygame.KEYUP, pygame.TEXTINPUT,
    pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP,
    pygame.MOUSEMOTION, pygame.MOUSEWHEEL,
)

# A file dropped on the window is offered to the flag based modals as well:
# the background, video, music and icon pickers accept one. The stack modals
# do not declare a drop handler, so it is not part of what they absorb.
MODAL_LAYER_EVENTS = MODAL_INPUT_EVENTS + (pygame.DROPFILE,)


@dataclass(frozen=True)
class ModalLayer:
    """One flag based modal: how to know it is open, draw it and feed it."""

    name: str       # stable id, used by the tests and the logs
    flag: str       # editor attribute, truthy while the modal is open
    render: str     # method(w, h) that draws it
    event: str      # method(ev) -> bool, True when it consumed the event


class ModalRouterMixin:
    """Routing of the flag based modals: order, rendering and input."""

    # Top of the screen first. This is the only place the stacking order of
    # the modals is written down.
    MODAL_LAYERS = (
        ModalLayer("confirm_leave", "_confirm_leave_modal",
                   "_r_confirm_leave_modal", "_ml_confirm_leave"),
        ModalLayer("recovery", "_recovery_modal",
                   "_r_recovery_modal", "_ml_recovery"),
        ModalLayer("stats", "_stats_modal",
                   "_r_stats_modal", "_ml_stats"),
        ModalLayer("scatter", "_scatter_modal_open",
                   "_r_scatter_modal", "_ml_scatter"),
        ModalLayer("auditor", "_auditor_active",
                   "_r_auditor_modal", "_ml_auditor"),
        ModalLayer("ctx_menu", "_ctx_menu",
                   "_r_ctx_menu", "_ml_ctx_menu"),
        ModalLayer("icon", "_icon_modal",
                   "_r_icon_modal", "_ml_icon"),
        ModalLayer("video", "_vid_modal",
                   "_r_video_modal", "_ml_video"),
        ModalLayer("background", "_bg_modal",
                   "_r_background_modal", "_ml_background"),
        ModalLayer("minigame", "_minigame_modal",
                   "_r_minigame_modal", "_ml_minigame"),
        ModalLayer("music", "_music_modal",
                   "_r_music_modal", "_ml_music"),
        ModalLayer("tag", "_tag_modal_active",
                   "_r_tag_modal", "_ml_tag"),
        ModalLayer("img_editor", "_img_editor_active",
                   "_r_img_editor_modal", "_ml_img_editor"),
        ModalLayer("newobj", "_newobj_modal",
                   "_r_newobj_modal", "_ml_newobj"),
        ModalLayer("lang", "_lang_modal",
                   "_r_lang_modal", "_ml_lang"),
    )

    # ─────────────────────────────────────────────────────────────────────────
    # QUERY
    # ─────────────────────────────────────────────────────────────────────────

    def _modal_open_layers(self) -> list:
        """The open flag based modals, the one on top first."""
        return [ly for ly in self.MODAL_LAYERS if getattr(self, ly.flag, False)]

    def _modal_top(self):
        """The modal on top, flag based or on the stack, or None."""
        if self.modal_stack:
            return self.modal_stack[-1]
        open_layers = self._modal_open_layers()
        return open_layers[0] if open_layers else None

    def _modal_any_open(self) -> bool:
        """True while anything modal covers the editor."""
        return bool(self.modal_stack) or bool(self._modal_open_layers())

    # ─────────────────────────────────────────────────────────────────────────
    # RENDER
    # ─────────────────────────────────────────────────────────────────────────

    def _modal_render(self, w: int, h: int) -> None:
        """Draw every open modal, bottom to top, the stack above them all."""
        for layer in reversed(self.MODAL_LAYERS):
            if getattr(self, layer.flag, False):
                getattr(self, layer.render)(w, h)
        for modal in self.modal_stack:
            modal.render(self)

    # ─────────────────────────────────────────────────────────────────────────
    # INPUT
    # ─────────────────────────────────────────────────────────────────────────

    def _modal_dispatch(self, ev) -> bool:
        """Offer the event to the modals, top first. True when one took it."""
        # A modal on the unified stack is app modal: it takes every input.
        if self.modal_stack and ev.type in MODAL_INPUT_EVENTS:
            self.modal_stack[-1].handle_event(self, ev)
            if ev.type == pygame.MOUSEBUTTONDOWN:
                self._play_click()
            return True

        if ev.type not in MODAL_LAYER_EVENTS:
            return False

        for layer in self.MODAL_LAYERS:
            if not getattr(self, layer.flag, False):
                continue
            if getattr(self, layer.event)(ev):
                if ev.type == pygame.MOUSEBUTTONDOWN:
                    self._play_click()
                return True
        return False

    # ─────────────────────────────────────────────────────────────────────────
    # ADAPTERS
    # ─────────────────────────────────────────────────────────────────────────
    # One per layer. They only translate an event into the calls the modal
    # already had, and say whether it was consumed: no logic of their own.

    def _ml_confirm_leave(self, ev) -> bool:
        """Leave without saving: blocks everything until it is answered."""
        if ev.type == pygame.KEYDOWN:
            if ev.key == pygame.K_ESCAPE:
                self._confirm_leave_modal = False
                self._pending_action = None
            return True
        if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
            self._confirm_leave_click(*ev.pos)
            return True
        return False

    def _ml_recovery(self, ev) -> bool:
        """Autosave recovery: Enter restores, Esc drops it for this session."""
        if ev.type == pygame.KEYDOWN:
            if ev.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                self._recovery_accept()
            elif ev.key == pygame.K_ESCAPE:
                self._recovery_dismiss()
            return True
        if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
            self._recovery_modal_click(*ev.pos)
            return True
        return False

    def _ml_stats(self, ev) -> bool:
        if ev.type == pygame.KEYDOWN:
            self._stats_modal_key(ev)
            return True
        if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
            w, h = self.screen.get_size()
            self._stats_modal_click(*ev.pos, w, h)
            return True
        if ev.type == pygame.MOUSEWHEEL:
            self._stats_modal_wheel(ev)
            return True
        return False

    def _ml_scatter(self, ev) -> bool:
        """Scatter: clicks and wheel outside the panel work on the canvas."""
        if ev.type == pygame.KEYDOWN:
            self._scatter_modal_key(ev)
            return True
        if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
            w, h = self.screen.get_size()
            return bool(self._scatter_modal_click(*ev.pos, w, h))
        if ev.type == pygame.MOUSEWHEEL:
            mx, my = pygame.mouse.get_pos()
            return bool(self._scatter_modal_wheel(mx, my, ev.y))
        return False

    def _ml_auditor(self, ev) -> bool:
        """The auditor answers what it knows and absorbs the rest."""
        self._auditor_handle_event(ev)
        return True

    def _ml_ctx_menu(self, ev) -> bool:
        """Context menu: a click outside closes it and goes through."""
        if ev.type != pygame.MOUSEBUTTONDOWN or ev.button != 1:
            return False
        items = self._get_ctx_items()
        m_w, m_h, mx_m, my_m = self._get_ctx_menu_info(items)
        if pygame.Rect(mx_m, my_m, m_w, m_h).collidepoint(ev.pos):
            if not self._ctx_menu_click(*ev.pos):
                self._ctx_menu = None
            return True
        self._ctx_menu = None
        return False

    def _ml_icon(self, ev) -> bool:
        if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
            w, h = self.screen.get_size()
            return bool(self._icon_click(*ev.pos, w, h))
        if ev.type == pygame.DROPFILE:
            self._icon_handle_drop(ev.file)
            return True
        return False

    def _ml_video(self, ev) -> bool:
        if ev.type == pygame.KEYDOWN:
            self._vid_modal_key(ev)
            return True
        if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
            w, h = self.screen.get_size()
            self._vid_modal_click(*ev.pos, w, h)
            return True
        if ev.type == pygame.MOUSEWHEEL:
            self._vid_modal_wheel(ev.y)
            return True
        if ev.type == pygame.DROPFILE:
            self._vid_handle_drop(ev.file)
            return True
        return False

    def _ml_background(self, ev) -> bool:
        if ev.type == pygame.KEYDOWN:
            self._bg_modal_key(ev)
            return True
        if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
            w, h = self.screen.get_size()
            self._bg_modal_click(*ev.pos, w, h)
            return True
        if ev.type == pygame.MOUSEWHEEL:
            self._bg_modal_wheel(ev.y)
            return True
        if ev.type == pygame.DROPFILE:
            self._bg_handle_drop(ev.file)
            return True
        return False

    def _ml_minigame(self, ev) -> bool:
        if ev.type == pygame.KEYDOWN:
            if ev.key == pygame.K_ESCAPE:
                self._minigame_modal = False
            return True
        if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
            self._minigame_click(*ev.pos)
            return True
        if ev.type == pygame.MOUSEWHEEL:
            self._minigame_wheel(ev.y)
            return True
        return False

    def _ml_music(self, ev) -> bool:
        """Music: the mouse up also finishes a drag started on the canvas."""
        if ev.type == pygame.KEYDOWN:
            self._music_modal_key(ev)
            return True
        if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
            w, h = self.screen.get_size()
            self._music_modal_click(*ev.pos, w, h)
            return True
        if ev.type == pygame.MOUSEBUTTONUP:
            self._music_modal_mup()
            return False
        if ev.type == pygame.MOUSEMOTION:
            w, h = self.screen.get_size()
            self._music_modal_mmove(*ev.pos, w, h)
            return True
        if ev.type == pygame.MOUSEWHEEL:
            self._music_wheel(ev.y)
            return True
        if ev.type == pygame.DROPFILE:
            self._music_handle_drop(ev.file)
            return True
        return False

    def _ml_tag(self, ev) -> bool:
        if ev.type == pygame.KEYDOWN:
            self._tag_modal_key(ev)
            return True
        if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
            w, h = self.screen.get_size()
            self._tag_modal_click(*ev.pos, w, h)
            return True
        if ev.type == pygame.MOUSEWHEEL:
            self._tag_modal_wheel(ev.y)
            return True
        return False

    def _ml_img_editor(self, ev) -> bool:
        """The image editor is a full screen tool: it takes everything."""
        self._img_editor_handle_event(ev)
        return True

    def _ml_newobj(self, ev) -> bool:
        if ev.type == pygame.KEYDOWN:
            self._newobj_key(ev)
            return True
        if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
            w, h = self.screen.get_size()
            self._newobj_click(*ev.pos, w, h)
            return True
        return False

    def _ml_lang(self, ev) -> bool:
        if ev.type == pygame.KEYDOWN:
            self._lang_key(ev)
            return True
        if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
            w, h = self.screen.get_size()
            self._lang_click(*ev.pos, w, h)
            return True
        if ev.type == pygame.MOUSEWHEEL:
            self._lang_modal_wheel(ev.y)
            return True
        return False
