"""
tests/test_runtime_strings.py

String keys the game runtime asks for must exist in all five engine languages.

  - Without an inline default a missing key reaches the player as the key
    itself: the HUD showed "HUD_FOUND_ALL" when a scene was cleared, and the
    hint dialog, its buttons and the hint tooltips had no text in any language.
  - With an English default a missing UI key does not show a key, but it shows
    English in every other language: the Italian hint panel said "HINTS
    AVAILABLE" and "Ready". UI keys are therefore checked too.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
LANGS = ("en", "it", "de", "es", "fr")
# self.lang("k"), self._lang("k"), lang_fn("k"), tr("k"), self.lang.get("k")
_CALLEE = r"(?:\b_lang|\.lang|\blang_fn|\btr|\.lang\.get)"
CALL = re.compile(_CALLEE + r"""\(\s*["']([a-z][a-z0-9_]+)["']\s*\)""")
CALL_WITH_DEFAULT = re.compile(_CALLEE + r"""\(\s*["']([a-z][a-z0-9_]+)["']\s*,""")
UI_PREFIXES = ("hud_", "btn_", "menu_title_", "label_", "msg_", "settings_group_", "card_",
               "mission_", "confirm_", "total_score", "time_elapsed", "objects_found",
               "perfect_score")


def _runtime_keys() -> dict[str, set[str]]:
    found: dict[str, set[str]] = {}
    for path in (ROOT / "engine").rglob("*.py"):
        src = path.read_text(encoding="utf-8")
        for key in CALL.findall(src):
            found.setdefault(key, set()).add(path.name)
        for key in CALL_WITH_DEFAULT.findall(src):
            if key.startswith(UI_PREFIXES):
                found.setdefault(key, set()).add(path.name)
    return found


def test_the_scan_sees_the_runtime():
    keys = _runtime_keys()
    assert "hud_found_all" in keys and "hud_confirm" in keys
    assert "hud_hint_ready" in keys, "a UI key with a default is scanned too"


@pytest.mark.parametrize("lang", LANGS)
def test_every_key_the_runtime_needs_is_translated(lang):
    table = json.loads((ROOT / "engine" / "assets" / "strings" / f"{lang}.json")
                       .read_text(encoding="utf-8"))
    missing = sorted(f"{k} ({', '.join(sorted(files))})"
                     for k, files in _runtime_keys().items()
                     if not str(table.get(k, "")).strip())
    assert not missing, f"{lang}: " + "; ".join(missing)
