"""
tests/test_editor_modal_routing.py

Input routing of the editor modals: which modal receives a key, a click or a
wheel event, and what happens when two modals are open at the same time.
Runs the real LevelEditor headless and spies on the handlers, because the
routing is the behaviour under test, not the modal bodies.
"""

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pytest

pygame = pytest.importorskip("pygame")

from editor.constants import STATE_MAIN


# Every legacy modal, with the flag that keeps it open and the handler that
# has to receive each kind of event. "" means the modal handles that event
# inline in the dispatcher instead of in a method of its own.
MODALS = {
    "lang":          dict(flag="_lang_modal",          key="_lang_key",          click="_lang_click"),
    "newobj":        dict(flag="_newobj_modal",        key="_newobj_key",        click="_newobj_click"),
    "tag":           dict(flag="_tag_modal_active",    key="_tag_modal_key",     click="_tag_modal_click"),
    "music":         dict(flag="_music_modal",         key="_music_modal_key",   click="_music_modal_click",
                          wheel="_music_wheel"),
    "background":    dict(flag="_bg_modal",            key="_bg_modal_key",      click="_bg_modal_click",
                          wheel="_bg_modal_wheel"),
    "video":         dict(flag="_vid_modal",           key="_vid_modal_key",     click="_vid_modal_click",
                          wheel="_vid_modal_wheel"),
    "icon":          dict(flag="_icon_modal",          click="_icon_click"),
    "minigame":      dict(flag="_minigame_modal",      click="_minigame_click",  wheel="_minigame_wheel"),
    "stats":         dict(flag="_stats_modal",         key="_stats_modal_key",   click="_stats_modal_click",
                          wheel="_stats_modal_wheel"),
    "scatter":       dict(flag="_scatter_modal_open",  key="_scatter_modal_key", click="_scatter_modal_click",
                          wheel="_scatter_modal_wheel"),
    "recovery":      dict(flag="_recovery_modal",      click="_recovery_modal_click"),
    "confirm_leave": dict(flag="_confirm_leave_modal", click="_confirm_leave_click"),
}

# Handlers whose return value decides whether the event was consumed.
TRUTHY_HANDLERS = {"_icon_click", "_scatter_modal_click", "_scatter_modal_wheel"}

MODAL_FLAGS = [spec["flag"] for spec in MODALS.values()] + [
    "_img_editor_active", "_auditor_active", "_ctx_menu",
]


@pytest.fixture(scope="module")
def editor():
    """A real editor, headless, with no game loaded."""
    from editor.editor_base import LevelEditor
    pygame.init()
    ed = LevelEditor(Path(os.getcwd()))
    ed.state = STATE_MAIN
    yield ed
    ed.running = False
    pygame.quit()


@pytest.fixture(autouse=True)
def clean_state(editor):
    """No modal open and no leftover events between tests."""
    pygame.event.clear()
    for flag in MODAL_FLAGS:
        setattr(editor, flag, None if flag == "_ctx_menu" else False)
    editor.modal_stack.clear()
    yield
    pygame.event.clear()
    for flag in MODAL_FLAGS:
        setattr(editor, flag, None if flag == "_ctx_menu" else False)
    editor.modal_stack.clear()


class Spy:
    """Records the calls and, optionally, claims the event as consumed."""

    def __init__(self, consumes: bool = False):
        self.calls: list = []
        self.consumes = consumes

    def __call__(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return self.consumes

    @property
    def called(self) -> bool:
        return bool(self.calls)


def spy_on(monkeypatch, editor, *names) -> dict:
    """Replace handlers with spies; the ones whose result is read say yes."""
    spies = {}
    for name in names:
        if not name:
            continue
        spy = Spy(consumes=name in TRUTHY_HANDLERS)
        monkeypatch.setattr(editor, name, spy, raising=False)
        spies[name] = spy
    return spies


KEY_EVENT = dict(type=pygame.KEYDOWN, key=pygame.K_a, unicode="a", mod=0, scancode=4)
CLICK_EVENT = dict(type=pygame.MOUSEBUTTONDOWN, pos=(400, 300), button=1, touch=False)
WHEEL_EVENT = dict(type=pygame.MOUSEWHEEL, x=0, y=1, flipped=False, touch=False,
                   precise_x=0.0, precise_y=1.0)


def post(**event):
    kind = event.pop("type")
    pygame.event.post(pygame.event.Event(kind, **event))


# -----------------------------------------------------------------------------
# ONE MODAL OPEN: THE EVENT REACHES IT
# -----------------------------------------------------------------------------

@pytest.mark.parametrize("name", sorted(n for n, s in MODALS.items() if s.get("key")))
def test_an_open_modal_receives_the_keys(editor, monkeypatch, name):
    spec = MODALS[name]
    spies = spy_on(monkeypatch, editor, spec["key"])
    setattr(editor, spec["flag"], True)
    post(**KEY_EVENT)
    editor._handle_events()
    assert spies[spec["key"]].called, f"{name} did not get the key"


@pytest.mark.parametrize("name", sorted(n for n, s in MODALS.items() if s.get("click")))
def test_an_open_modal_receives_the_clicks(editor, monkeypatch, name):
    spec = MODALS[name]
    spies = spy_on(monkeypatch, editor, spec["click"])
    setattr(editor, spec["flag"], True)
    post(**CLICK_EVENT)
    editor._handle_events()
    assert spies[spec["click"]].called, f"{name} did not get the click"


@pytest.mark.parametrize("name", sorted(n for n, s in MODALS.items() if s.get("wheel")))
def test_an_open_modal_receives_the_wheel(editor, monkeypatch, name):
    spec = MODALS[name]
    spies = spy_on(monkeypatch, editor, spec["wheel"])
    setattr(editor, spec["flag"], True)
    post(**WHEEL_EVENT)
    editor._handle_events()
    assert spies[spec["wheel"]].called, f"{name} did not get the wheel"


def test_the_image_editor_takes_every_event(editor, monkeypatch):
    spies = spy_on(monkeypatch, editor, "_img_editor_handle_event")
    editor._img_editor_active = True
    post(**KEY_EVENT)
    post(**CLICK_EVENT)
    post(**WHEEL_EVENT)
    editor._handle_events()
    assert len(spies["_img_editor_handle_event"].calls) == 3


def test_the_auditor_takes_every_event(editor, monkeypatch):
    spies = spy_on(monkeypatch, editor, "_auditor_handle_event")
    editor._auditor_active = True
    post(**KEY_EVENT)
    post(**CLICK_EVENT)
    editor._handle_events()
    assert len(spies["_auditor_handle_event"].calls) == 2


def test_the_stack_modal_takes_the_input(editor, monkeypatch):
    """A modal on the unified stack is app modal, it beats the legacy ones."""
    seen = []

    class StackModal:
        def handle_event(self, ed, ev):
            seen.append(ev.type)
            return True

        def render(self, ed):
            pass

    lang = spy_on(monkeypatch, editor, "_lang_key")["_lang_key"]
    editor._lang_modal = True
    editor.modal_stack.append(StackModal())
    post(**KEY_EVENT)
    editor._handle_events()
    assert seen == [pygame.KEYDOWN]
    assert not lang.called


# -----------------------------------------------------------------------------
# NO MODAL OPEN: THE EDITOR ITSELF GETS THE EVENT
# -----------------------------------------------------------------------------

def test_without_modals_the_editor_handles_the_event(editor, monkeypatch):
    spies = spy_on(monkeypatch, editor, "_on_key", "_on_mdown", "_on_wheel")
    post(**KEY_EVENT)
    post(**CLICK_EVENT)
    post(**WHEEL_EVENT)
    editor._handle_events()
    assert spies["_on_key"].called
    assert spies["_on_mdown"].called
    assert spies["_on_wheel"].called


def test_quit_is_never_swallowed_by_a_modal(editor, monkeypatch):
    """Closing the window must work whatever is open on top."""
    spies = spy_on(monkeypatch, editor, "_request_nav", "_auditor_handle_event")
    editor._auditor_active = True
    post(type=pygame.QUIT)
    editor._handle_events()
    assert spies["_request_nav"].called
    assert not spies["_auditor_handle_event"].called


# -----------------------------------------------------------------------------
# TWO MODALS OPEN: THE ONE ON TOP WINS
# -----------------------------------------------------------------------------

def test_the_quit_dialog_beats_the_auditor(editor, monkeypatch):
    """The quit confirmation is drawn over the auditor, so it takes the input.

    Reachable for real: the window close button posts QUIT, which is never
    swallowed by a modal, so the dialog opens on top of the open auditor.
    """
    spies = spy_on(monkeypatch, editor, "_confirm_leave_click", "_auditor_handle_event")
    editor._auditor_active = True
    editor._confirm_leave_modal = True
    post(**CLICK_EVENT)
    editor._handle_events()
    assert spies["_confirm_leave_click"].called
    assert not spies["_auditor_handle_event"].called


def test_the_quit_dialog_beats_the_image_editor(editor, monkeypatch):
    spies = spy_on(monkeypatch, editor, "_confirm_leave_click", "_img_editor_handle_event")
    editor._img_editor_active = True
    editor._confirm_leave_modal = True
    post(**CLICK_EVENT)
    editor._handle_events()
    assert spies["_confirm_leave_click"].called
    assert not spies["_img_editor_handle_event"].called


def test_the_quit_dialog_beats_the_text_modals_on_the_keyboard(editor, monkeypatch):
    """Key routing must follow the same order the modals are drawn in."""
    spies = spy_on(monkeypatch, editor, "_lang_key", "_newobj_key", "_tag_modal_key")
    editor._lang_modal = True
    editor._newobj_modal = True
    editor._tag_modal_active = True
    editor._confirm_leave_modal = True
    editor._pending_action = None
    post(type=pygame.KEYDOWN, key=pygame.K_ESCAPE, unicode="\x1b", mod=0, scancode=41)
    editor._handle_events()
    assert not any(s.called for s in spies.values())
    assert editor._confirm_leave_modal is False     # ESC dismissed the dialog


def test_the_recovery_dialog_beats_the_scatter_modal(editor, monkeypatch):
    spies = spy_on(monkeypatch, editor, "_recovery_modal_click", "_scatter_modal_click")
    editor._scatter_modal_open = True
    editor._recovery_modal = True
    post(**CLICK_EVENT)
    editor._handle_events()
    assert spies["_recovery_modal_click"].called
    assert not spies["_scatter_modal_click"].called


# -----------------------------------------------------------------------------
# ORDER: WHAT IS DRAWN LAST IS WHAT GETS THE INPUT
# -----------------------------------------------------------------------------

def test_the_modals_are_drawn_in_the_reverse_of_the_input_order(editor, monkeypatch):
    """One order for both, so nothing answers from under another modal."""
    from editor.mixins.modal_router import ModalRouterMixin

    drawn = []
    for layer in ModalRouterMixin.MODAL_LAYERS:
        setattr(editor, layer.flag, True)
        monkeypatch.setattr(editor, layer.render,
                            lambda w, h, name=layer.name: drawn.append(name),
                            raising=False)
    editor.modal_stack.clear()
    editor._modal_render(800, 600)

    assert drawn == [ly.name for ly in reversed(ModalRouterMixin.MODAL_LAYERS)]


def test_only_the_open_modals_are_drawn(editor, monkeypatch):
    from editor.mixins.modal_router import ModalRouterMixin

    drawn = []
    for layer in ModalRouterMixin.MODAL_LAYERS:
        monkeypatch.setattr(editor, layer.render,
                            lambda w, h, name=layer.name: drawn.append(name),
                            raising=False)
    editor._stats_modal = True
    editor._lang_modal = True
    editor._modal_render(800, 600)
    assert drawn == ["lang", "stats"]


def test_the_stack_is_drawn_over_the_flag_modals(editor, monkeypatch):
    order = []

    class StackModal:
        def render(self, ed):
            order.append("stack")

        def handle_event(self, ed, ev):
            return True

    monkeypatch.setattr(editor, "_r_stats_modal",
                        lambda w, h: order.append("stats"), raising=False)
    editor._stats_modal = True
    editor.modal_stack.append(StackModal())
    editor._modal_render(800, 600)
    assert order == ["stats", "stack"]


# -----------------------------------------------------------------------------
# WHAT A MODAL BLOCKS AND WHAT IT LETS THROUGH
# -----------------------------------------------------------------------------

def test_a_modal_blocks_the_editor_underneath(editor, monkeypatch):
    """The status bar and the canvas must not answer under a modal."""
    spies = spy_on(monkeypatch, editor, "_on_mdown", "_on_key", "_on_wheel", "_lang_click",
                   "_lang_key", "_lang_modal_wheel")
    editor._lang_modal = True
    post(**KEY_EVENT)
    post(**CLICK_EVENT)
    post(**WHEEL_EVENT)
    editor._handle_events()
    assert not spies["_on_mdown"].called
    assert not spies["_on_key"].called
    assert not spies["_on_wheel"].called
    assert spies["_lang_click"].called and spies["_lang_key"].called


def test_a_click_outside_the_context_menu_goes_through(editor, monkeypatch):
    """Closing the menu must not eat the click that closed it."""
    monkeypatch.setattr(editor, "_get_ctx_items", lambda: [], raising=False)
    monkeypatch.setattr(editor, "_get_ctx_menu_info", lambda items: (100, 80, 0, 0),
                        raising=False)
    spies = spy_on(monkeypatch, editor, "_ctx_menu_click", "_on_mdown")
    editor._ctx_menu = {"x": 0, "y": 0}
    post(**CLICK_EVENT)                       # (400, 300), outside the menu
    editor._handle_events()
    assert editor._ctx_menu is None
    assert not spies["_ctx_menu_click"].called
    assert spies["_on_mdown"].called


def test_a_click_inside_the_context_menu_is_taken(editor, monkeypatch):
    monkeypatch.setattr(editor, "_get_ctx_items", lambda: [], raising=False)
    monkeypatch.setattr(editor, "_get_ctx_menu_info", lambda items: (600, 500, 0, 0),
                        raising=False)
    spies = spy_on(monkeypatch, editor, "_ctx_menu_click", "_on_mdown")
    editor._ctx_menu = {"x": 0, "y": 0}
    post(**CLICK_EVENT)                       # (400, 300), inside the menu
    editor._handle_events()
    assert spies["_ctx_menu_click"].called
    assert not spies["_on_mdown"].called


def test_the_scatter_modal_lets_the_canvas_work(editor, monkeypatch):
    """Its click handler answers False outside the panel: the canvas gets it."""
    monkeypatch.setattr(editor, "_scatter_modal_click",
                        lambda *a, **k: False, raising=False)
    spies = spy_on(monkeypatch, editor, "_on_mdown")
    editor._scatter_modal_open = True
    post(**CLICK_EVENT)
    editor._handle_events()
    assert spies["_on_mdown"].called


def test_a_file_dropped_reaches_the_modal_that_wants_it(editor, monkeypatch):
    spies = spy_on(monkeypatch, editor, "_bg_handle_drop", "_music_handle_drop")
    editor._bg_modal = True
    pygame.event.post(pygame.event.Event(pygame.DROPFILE, file="C:/tmp/a.png"))
    editor._handle_events()
    assert spies["_bg_handle_drop"].called
    assert not spies["_music_handle_drop"].called


# -----------------------------------------------------------------------------
# END TO END: A REAL MODAL, OPENED FOR REAL, ANSWERS THE ROUTER
# -----------------------------------------------------------------------------

def test_the_real_translations_modal_scrolls_and_closes(editor):
    """No spies here: open it, drive it, read its own state back."""
    editor._lang_open()                       # engine strings, no game needed
    assert editor._lang_modal is True
    assert len(editor._lang_keys) > 50, "not enough keys to scroll"
    editor._lang_scroll = 0

    for _ in range(3):
        post(**WHEEL_EVENT | {"y": -1})       # a wheel down is a scroll down
        editor._handle_events()
    assert editor._lang_scroll == 3

    post(**WHEEL_EVENT | {"y": 1})
    editor._handle_events()
    assert editor._lang_scroll == 2

    post(type=pygame.KEYDOWN, key=pygame.K_ESCAPE, unicode="", mod=0, scancode=41)
    editor._handle_events()
    assert editor._lang_modal is False

    # And with it closed the editor gets its input back.
    editor._lang_scroll = 0
    post(**WHEEL_EVENT | {"y": -1})
    editor._handle_events()
    assert editor._lang_scroll == 0


def test_the_real_translations_modal_renders_where_the_router_puts_it(editor):
    """The router draws it, and drawing it changes the screen."""
    editor._lang_open()
    editor.screen.fill((0, 0, 0))
    before = pygame.image.tostring(editor.screen, "RGB")
    editor._modal_render(*editor.screen.get_size())
    after = pygame.image.tostring(editor.screen, "RGB")
    assert before != after
    editor._lang_modal = False
