"""
tests/conftest.py

Shared fixtures for the suite.

Several modules init pygame in a fixture and call pygame.quit() when they are
done. The editor keeps its fonts in a module level cache (editor/ui/draw.py),
and a pygame.Font that outlived a pygame.quit() is a dangling SDL_ttf handle:
using it in the next module crashes the interpreter with an access violation
instead of raising, and pygame.init() makes the font system report itself as
healthy again while those handles stay dead. Dropping the cache around every
module keeps the modules independent.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True, scope="module")
def _fresh_editor_fonts():
    try:
        from editor.ui.draw import reset_fonts
    except Exception:                      # editor not importable: nothing to do
        yield
        return
    reset_fonts()
    yield
    reset_fonts()
