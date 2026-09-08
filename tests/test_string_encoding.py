"""
tests/test_string_encoding.py

What the language files are allowed to contain.

At some point a pass folded the accented letters of the language files to
ASCII and left an apostrophe where the accent had been. 266 French strings,
27 Italian and 19 Spanish came out of it: the French editor said "E'diter",
"SCE'NE", "PROJETS RE'CENTS" and "Version de l'E'diteur", and a few strings
came out worse than that ("Macinacaffa'\\xa8" for "Macinacaff\\u00e8",
"Casina'\\xb2" for "Casin\\u00f2"). Two more had been read as cp1252 and
written back as UTF-8, so "C\\u0153ur Humain" had become "C\\u00c5\\u201cur".

None of it raised anything. It is only visible to somebody who reads that
language, which is exactly the reader nobody has. These tests are what looks
instead:

  1. no accent is spelled as an apostrophe;
  2. no string carries the signature of a mis-decoded UTF-8 sequence;
  3. every string is in composed form, so a screenshot never shows "E" plus
     a floating accent;
  4. a key exists in every language or in none.
"""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
ENGINE_STRINGS = ROOT / "engine" / "assets" / "strings"
GAME_STRINGS = sorted((ROOT / "games").glob("*/strings/*.json"))
LANGS = ("en", "it", "es", "fr", "de")

# A letter, then apostrophes, then letters: one token of running text.
TOKEN = re.compile(r"[^\W\d_][\w']*", re.UNICODE)
# A vowel immediately followed by an apostrophe is how the folding pass left
# every accent it removed.
ACCENT_AS_APOSTROPHE = re.compile(r"[aeiouAEIOU]'")

# Where the apostrophe really is an apostrophe.
ALLOWED_TOKENS = {
    "Abe's", "Santa's", "TIME'S",        # English possessives
    "Squalo'", "Proprieta'",             # inside an Italian quoted phrase
    "Fondo'", "Background'",             # inside a quoted phrase
}

# The first character of a UTF-8 sequence read as cp1252 is one of these,
# followed by a byte from the same misreading.
MOJIBAKE = re.compile(r"[ÃÅÂ][-¿‘-„Œœ€]")


def language_files() -> list:
    return sorted(ENGINE_STRINGS.glob("*.json")) + GAME_STRINGS


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


ALL_FILES = language_files()


def test_there_are_language_files_to_check():
    assert len(ALL_FILES) >= len(LANGS)


@pytest.mark.parametrize("path", ALL_FILES, ids=lambda p: str(p.relative_to(ROOT)))
def test_no_accent_is_spelled_as_an_apostrophe(path):
    offenders = {}
    for key, value in load(path).items():
        if not isinstance(value, str):
            continue
        for token in TOKEN.findall(value):
            if ACCENT_AS_APOSTROPHE.search(token) and token not in ALLOWED_TOKENS:
                offenders.setdefault(key, set()).add(token)
    assert not offenders, (
        f"{path.name} spells accents with an apostrophe: "
        + ", ".join(f"{k}={sorted(v)}" for k, v in sorted(offenders.items())[:8]))


@pytest.mark.parametrize("path", ALL_FILES, ids=lambda p: str(p.relative_to(ROOT)))
def test_no_string_was_read_in_the_wrong_encoding(path):
    offenders = {k: v for k, v in load(path).items()
                 if isinstance(v, str) and MOJIBAKE.search(v)}
    assert not offenders, f"{path.name} holds mis-decoded UTF-8: {offenders}"


@pytest.mark.parametrize("path", ALL_FILES, ids=lambda p: str(p.relative_to(ROOT)))
def test_every_string_is_in_composed_form(path):
    """A decomposed "E" plus a combining acute draws as "E" plus a mark."""
    offenders = [k for k, v in load(path).items()
                 if isinstance(v, str) and unicodedata.normalize("NFC", v) != v]
    assert not offenders, f"{path.name} holds decomposed text: {offenders[:8]}"


@pytest.mark.parametrize("path", ALL_FILES, ids=lambda p: str(p.relative_to(ROOT)))
def test_no_key_is_left_over_from_a_folding_pass(path):
    """A key with an accent or an apostrophe in it is one the code cannot
    reach: the tag ids the catalogs use are ASCII, by `slugify_tag`."""
    offenders = [k for k in load(path) if not k.isascii() or "'" in k]
    assert not offenders, f"{path.name} has unreachable keys: {offenders}"


def test_the_apostrophe_guard_can_fail():
    """A guard that never fires is not a guard."""
    assert ACCENT_AS_APOSTROPHE.search("SCE'NE")
    assert not ACCENT_AS_APOSTROPHE.search("SCÈNE")


def catalog_label_keys() -> set:
    """Every label_key the catalogs point at."""
    keys = set()
    paths = list((ROOT / "engine" / "data").glob("global_*catalog.json"))
    paths += list((ROOT / "games").glob("*/objects_catalog.json"))
    for path in paths:
        if "backup" in path.name:
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        entries = data if isinstance(data, list) else data.get("objects", [])
        for entry in entries if isinstance(entries, list) else []:
            if isinstance(entry, dict) and entry.get("label_key"):
                keys.add(entry["label_key"])
    return keys


def test_every_name_a_catalog_uses_exists_in_english():
    """English is the only fallback, so a missing English name has nothing
    behind it: 61 objects were named in Italian and nowhere else, and the
    editor showed the raw key for them in every other language."""
    english = set(load(ENGINE_STRINGS / "en.json"))
    missing = sorted(catalog_label_keys() - english)
    assert not missing, (
        f"{len(missing)} catalog objects have no English name: {missing[:8]}")


@pytest.mark.parametrize("lang", LANGS[1:])
def test_the_editor_chrome_is_complete_in_every_language(lang):
    """A name of a catalog object falls back to English and reads fine. A
    button of the editor does not: it is chrome, and it must be translated."""
    content = ("obj_", "tag_", "cat_", "taxo_")
    english = {k for k in load(ENGINE_STRINGS / "en.json")
               if not k.startswith(content)}
    missing = sorted(english - set(load(ENGINE_STRINGS / f"{lang}.json")))
    assert not missing, f"{lang} has no text for {len(missing)} keys: {missing[:8]}"
