"""
tests/test_catalog_tags.py

Catalog tags. The editor renders a tag chip with `_TR(f"tag_{tag}", ...)`, a key
built at runtime, so the source-driven check in test_editor_i18n.py cannot see
it. Two things went wrong here and neither was caught:

  1. tags used by the catalogs had no `tag_<id>` key at all, so the chip fell
     back to the raw Italian id and the catalog showed a mix of languages;
  2. two ids were truncated by an old pass that stripped non-ASCII characters
     ("citta" -> "citt", "casino" -> "casin"), which no lookup could ever match.

This pins both: every tag a catalog uses is translated in all five languages,
and a tag id stays a plain lowercase ASCII slug.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from editor.constants import LANGS

ROOT = Path(__file__).resolve().parents[1]
STRINGS_DIR = ROOT / "engine" / "assets" / "strings"
TAXONOMY = ROOT / "engine" / "data" / "tags_taxonomy.json"

# A tag id is used to build a translation key and a filter chip: lowercase
# ASCII words joined by underscores, nothing else.
TAG_ID_RE = re.compile(r"^[a-z0-9]+(?:_[a-z0-9]+)*$")


def _catalog_files() -> list[Path]:
    files = sorted((ROOT / "engine" / "data").glob("global_*_catalog.json"))
    files += sorted((ROOT / "games").glob("*/objects_catalog.json"))
    return files


def _entries(path: Path) -> list:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return data
    return data.get("objects", data.get("catalog", []))


def _used_tags() -> set[str]:
    tags: set[str] = set()
    for path in _catalog_files():
        for entry in _entries(path):
            tags.update(entry.get("tags", []))
    return tags


def _strings(lang: str) -> dict:
    return json.loads((STRINGS_DIR / f"{lang}.json").read_text(encoding="utf-8"))


def test_the_catalogs_are_not_empty():
    assert _catalog_files(), "no catalog to check"
    assert _used_tags(), "no catalog entry carries a tag"


@pytest.mark.parametrize("lang", LANGS)
def test_every_used_tag_is_translated(lang):
    strings = _strings(lang)
    missing = sorted(t for t in _used_tags() if f"tag_{t}" not in strings)
    assert not missing, f"{lang}: tags without a tag_<id> key: {missing}"


@pytest.mark.parametrize("lang", LANGS)
def test_every_taxonomy_tag_is_translated(lang):
    """The tag picker offers the whole registry, not only what is in use."""
    taxonomy = json.loads(TAXONOMY.read_text(encoding="utf-8"))["tags"]
    strings = _strings(lang)
    missing = sorted(t for t in taxonomy if f"tag_{t}" not in strings)
    assert not missing, f"{lang}: taxonomy tags without a key: {missing}"


@pytest.mark.parametrize("lang", LANGS)
def test_no_tag_label_is_empty(lang):
    strings = _strings(lang)
    blank = sorted(t for t in _used_tags() if not str(strings[f"tag_{t}"]).strip())
    assert not blank, f"{lang}: empty tag labels: {blank}"


def test_tag_ids_are_plain_slugs():
    bad = sorted(t for t in _used_tags() if not TAG_ID_RE.match(t))
    assert not bad, f"tag ids that cannot build a translation key: {bad}"


def test_taxonomy_ids_are_plain_slugs():
    taxonomy = json.loads(TAXONOMY.read_text(encoding="utf-8"))["tags"]
    bad = sorted(t for t in taxonomy if not TAG_ID_RE.match(t))
    assert not bad, f"taxonomy ids that cannot build a translation key: {bad}"


def test_no_unreachable_uppercase_tag_key():
    """Tag ids are lowercased by TagManager: an uppercase key is dead weight."""
    for lang in LANGS:
        upper = sorted(k for k in _strings(lang)
                       if k.startswith("tag_") and k != k.lower())
        assert not upper, f"{lang}: unreachable tag keys: {upper}"


# ─────────────────────────────────────────────────────────────────────────────
# NORMALIZZAZIONE (editor/core/tags.py)
# ─────────────────────────────────────────────────────────────────────────────

from editor.core.tags import slugify_tag  # noqa: E402


@pytest.mark.parametrize("raw,expected", [
    ("Citta\u0300", "citta"),          # combining accent, decomposed
    ("Citt\u00e0", "citta"),           # precomposed accent
    ("casin\u00f2", "casino"),
    ("Valle Camonica", "valle_camonica"),
    ("  MIXED-Case  ", "mixed_case"),
    ("ferro_stiro", "ferro_stiro"),
    ("2000s", "2000s"),
])
def test_slugify_tag_produces_a_usable_id(raw, expected):
    assert slugify_tag(raw) == expected


@pytest.mark.parametrize("raw", ["", "   ", "---", None])
def test_slugify_tag_rejects_what_has_no_id_left(raw):
    assert slugify_tag(raw) == ""


def test_every_slug_is_already_canonical():
    """Slugifying a stored id must be a no-op: the registry is normalized."""
    taxonomy = json.loads(TAXONOMY.read_text(encoding="utf-8"))["tags"]
    for tag in taxonomy:
        assert slugify_tag(tag) == tag
    for tag in _used_tags():
        assert slugify_tag(tag) == tag
