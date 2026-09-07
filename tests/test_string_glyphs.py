"""
tests/test_string_glyphs.py

Every character the UI strings contain must exist in the font the editor draws
with. It is not a theoretical worry: `aud_fix_btn` shipped as "✔ FIX" and
`aud_rescan` as "↺ RESCAN", and the UI font stack (Segoe UI, Arial,
DejaVu Sans) has neither glyph, so the auditor showed an empty box where the
mark should have been, in all five languages.

The check is empirical: a missing glyph renders as the font's "notdef" box, so
rendering a character from a Private Use Area codepoint gives the shape a
missing character produces, and any character rendering to that same shape is
missing too. The editor draws its icons with `_draw_shape_icon`, not with text
glyphs, so a UI string never needs a symbol the font does not have.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pytest

pygame = pytest.importorskip("pygame")

from editor.constants import LANGS

ROOT = Path(__file__).resolve().parents[1]
STRINGS_DIR = ROOT / "engine" / "assets" / "strings"

# Codepoint no font defines: rendering it yields the "missing glyph" shape.
MISSING_SAMPLE = ""


@pytest.fixture(scope="module")
def fonts():
    pygame.init()
    pygame.display.set_mode((64, 64))
    from editor.ui.draw import _FONTS, _init_fonts, reset_fonts
    reset_fonts()
    _init_fonts(1.0)
    yield dict(_FONTS)
    reset_fonts()
    pygame.quit()


def _characters(lang: str) -> set[str]:
    data = json.loads((STRINGS_DIR / f"{lang}.json").read_text(encoding="utf-8"))
    chars: set[str] = set()
    for value in data.values():
        if isinstance(value, str):
            chars.update(value)
    return chars


def _shape(font, char: str) -> bytes:
    return pygame.image.tostring(font.render(char, True, (255, 255, 255)), "RGBA")


@pytest.mark.parametrize("lang", LANGS)
def test_every_character_has_a_glyph(lang, fonts):
    font = fonts["md"]
    notdef = _shape(font, MISSING_SAMPLE)
    missing = sorted(c for c in _characters(lang)
                     if c.isprintable() and not c.isspace()
                     and _shape(font, c) == notdef)
    assert not missing, (
        f"{lang}: characters the UI font cannot draw: "
        + ", ".join(f"U+{ord(c):04X}" for c in missing))


def test_the_probe_itself_detects_a_missing_glyph(fonts):
    """Guard the guard: the probe must recognise a character that is absent."""
    font = fonts["md"]
    assert _shape(font, MISSING_SAMPLE) == _shape(font, "")
    assert _shape(font, "A") != _shape(font, MISSING_SAMPLE)
