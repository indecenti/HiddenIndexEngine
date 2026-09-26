"""
tools/menu_layout_check.py

Layout rules for one painted menu frame, checked on the boxes MenuSystem
records through its layout probe (`MenuSystem.layout_probe`, `MenuSystem.probe`).

A frame passes when:

  1. nothing the player reads or presses is cut by the screen edge;
  2. every icon stays inside its own button - a glyph growing out of its plate
     on hover is a cut image, only the other way round;
  3. no two texts overlap;
  4. no text overlaps a button, card or icon it does not belong to;
  5. no two buttons, cards or corner controls overlap;
  6. no text is smaller than the readable floor.

Used by tests/test_menu_layout.py and by tools/menu_audit.py --check.
"""
from __future__ import annotations

from dataclasses import dataclass

import pygame

# Boxes the player presses or looks at as one object.
SOLID_KINDS = ("button", "card", "chrome")
# Tolerance for antialiased edges and rounding between ref and screen pixels.
EDGE_TOLERANCE = 1
# Smallest line height a text may have, in reference pixels (the line height
# of a 17 px face, the micro role of docs/engine/MENU_UX_PLAN.md).
MIN_TEXT_LINE_REF = 17


@dataclass(frozen=True)
class Violation:
    rule: str
    detail: str

    def __str__(self) -> str:
        return f"{self.rule}: {self.detail}"


def _inside(inner: pygame.Rect, outer: pygame.Rect, tol: int = EDGE_TOLERANCE) -> bool:
    return (inner.left >= outer.left - tol and inner.top >= outer.top - tol
            and inner.right <= outer.right + tol and inner.bottom <= outer.bottom + tol)


def _overlap(a: pygame.Rect, b: pygame.Rect, tol: int = EDGE_TOLERANCE) -> bool:
    return a.inflate(-2 * tol, -2 * tol).colliderect(b.inflate(-2 * tol, -2 * tol))


def _name(kind: str, owner: str, rect: pygame.Rect) -> str:
    return f"{kind}[{owner}]@({rect.x},{rect.y},{rect.w},{rect.h})"


def check_frame(boxes: list, screen_size: tuple[int, int],
                scale: float = 1.0) -> list[Violation]:
    """Return the rule violations of one frame's probed boxes."""
    screen = pygame.Rect(0, 0, *screen_size)
    out: list[Violation] = []
    texts = [(k, r, o) for k, r, o in boxes if k == "text"]
    solids = [(k, r, o) for k, r, o in boxes if k in SOLID_KINDS]
    icons = [(k, r, o) for k, r, o in boxes if k == "icon"]

    for kind, rect, owner in boxes:
        if kind in ("text", "icon", "row") + SOLID_KINDS and not _inside(rect, screen):
            out.append(Violation("cut", _name(kind, owner, rect)))

    for _k, icon, owner in icons:
        plates = [r for k, r, o in solids if o == owner]
        if plates and not any(_inside(icon, plate) for plate in plates):
            out.append(Violation("icon-out-of-button", _name("icon", owner, icon)))

    for i, (_k, a, oa) in enumerate(texts):
        for _k2, b, ob in texts[i + 1:]:
            if a != b and _overlap(a, b):
                out.append(Violation("text-over-text",
                                     f"{_name('text', oa, a)} x {_name('text', ob, b)}"))

    for _k, t, ot in texts:
        for kind, r, o in solids + icons:
            if o != ot and _overlap(t, r):
                out.append(Violation("text-over-" + kind,
                                     f"{_name('text', ot, t)} x {_name(kind, o, r)}"))

    for i, (ka, a, oa) in enumerate(solids):
        for kb, b, ob in solids[i + 1:]:
            if oa != ob and _overlap(a, b):
                out.append(Violation(f"{ka}-over-{kb}",
                                     f"{_name(ka, oa, a)} x {_name(kb, ob, b)}"))

    floor = int(MIN_TEXT_LINE_REF * scale)
    for _k, t, ot in texts:
        if t.h < floor:
            out.append(Violation("text-too-small", f"{_name('text', ot, t)} < {floor}px"))
    return out
