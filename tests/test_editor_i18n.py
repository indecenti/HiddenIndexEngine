"""
tests/test_editor_i18n.py

Contratto i18n dell'editor:

  1. ogni chiave usata dal codice (`self._TR(...)`, `lang_manager.get(...)`,
     `engine.language_manager.tr(...)`) esiste in TUTTE le lingue supportate;
  2. nessun valore vuoto;
  3. i placeholder `{...}` di una traduzione coincidono con quelli dell'inglese
     (una traduzione che ne perde uno manda in errore `str.format`);
  4. l'inglese e' la lingua di default e l'unico fallback.

Il test e' volutamente sorgente-driven: aggiungere una stringa hardcoded nuova
non lo fa fallire, ma aggiungere una chiave senza traduzione si'.
"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path

import pytest

from editor.constants import DEFAULT_LANG, LANGS
from engine.language_manager import DEFAULT_LANG as ENGINE_DEFAULT_LANG
from engine.language_manager import FALLBACK_LANG, LanguageManager

ROOT = Path(__file__).resolve().parents[1]
EDITOR_DIR = ROOT / "editor"
STRINGS_DIR = ROOT / "engine" / "assets" / "strings"

PLACEHOLDER_RE = re.compile(r"\{([a-zA-Z_][a-zA-Z_0-9]*|\d+)[^{}]*\}")


def _iter_editor_sources():
    for path in sorted(EDITOR_DIR.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        yield path


def _collect_keys() -> dict[str, set[str]]:
    """key -> insieme dei file che la usano."""
    keys: dict[str, set[str]] = {}
    for path in _iter_editor_sources():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not node.args:
                continue
            func = node.func
            if isinstance(func, ast.Attribute):
                if func.attr == "_TR":
                    pass
                elif func.attr == "get" and isinstance(func.value, ast.Attribute) \
                        and func.value.attr == "lang_manager":
                    pass
                else:
                    continue
            elif isinstance(func, ast.Name) and func.id == "tr":
                pass
            else:
                continue
            first = node.args[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                keys.setdefault(first.value, set()).add(
                    str(path.relative_to(ROOT)))
    return keys


def _load(lang: str) -> dict[str, str]:
    return json.loads((STRINGS_DIR / f"{lang}.json").read_text(
        encoding="utf-8-sig"))


EDITOR_KEYS = _collect_keys()
TABLES = {lang: _load(lang) for lang in LANGS}


def test_default_and_fallback_sono_inglese():
    assert DEFAULT_LANG == "en"
    assert ENGINE_DEFAULT_LANG == "en"
    assert FALLBACK_LANG == "en"


def test_fallback_non_sovrascrivibile():
    """load_for_game ignora un fallback diverso da EN."""
    lm = LanguageManager()
    lm.load_for_game("engine", "it", fallback="fr")
    assert lm._fallback_lang == "en"


def test_editor_usa_almeno_le_chiavi_note():
    # sentinella: se il collector smette di funzionare il test diventa vuoto
    assert len(EDITOR_KEYS) > 300


@pytest.mark.parametrize("lang", LANGS)
def test_tutte_le_chiavi_editor_tradotte(lang):
    table = TABLES[lang]
    missing = sorted(k for k in EDITOR_KEYS if k not in table)
    empty = sorted(k for k in EDITOR_KEYS
                   if k in table and not str(table[k]).strip())
    assert not missing, (
        f"[{lang}] {len(missing)} chiavi usate dall'editor e non tradotte: "
        f"{missing[:15]}")
    assert not empty, f"[{lang}] chiavi con valore vuoto: {empty[:15]}"


@pytest.mark.parametrize("lang", [x for x in LANGS if x != "en"])
def test_placeholder_coerenti_con_inglese(lang):
    en = TABLES["en"]
    table = TABLES[lang]
    bad: list[str] = []
    for key in EDITOR_KEYS:
        if key not in en or key not in table:
            continue
        ph_en = set(PLACEHOLDER_RE.findall(str(en[key])))
        ph_tr = set(PLACEHOLDER_RE.findall(str(table[key])))
        if ph_en != ph_tr:
            bad.append(f"{key}: en={sorted(ph_en)} {lang}={sorted(ph_tr)}")
    assert not bad, f"[{lang}] placeholder incoerenti: {bad[:15]}"


@pytest.mark.parametrize("lang", LANGS)
def test_nessun_valore_corrotto(lang):
    """Sequenze tipiche di UTF-8 letto come latin-1."""
    table = TABLES[lang]
    bad = [k for k, v in table.items()
           if isinstance(v, str) and ("Ã" in v or "â€" in v or "â†" in v)]
    assert not bad, f"[{lang}] valori con encoding corrotto: {bad[:10]}"


@pytest.mark.parametrize("lang", LANGS)
def test_chiavi_ui_allineate_fra_lingue(lang):
    """Le chiavi non-oggetto devono esistere in tutte le lingue supportate."""
    union: set[str] = set()
    for table in TABLES.values():
        union |= {k for k in table if not k.startswith(("obj_", "tag_"))}
    missing = sorted(union - set(TABLES[lang]))
    assert not missing, (
        f"[{lang}] {len(missing)} chiavi UI presenti in altre lingue e non qui: "
        f"{missing[:15]}")
