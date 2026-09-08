"""
tests/test_source_hygiene.py

Three mistakes the language does not complain about and no reviewer reliably
spots, all of which cost something real in this repository:

  - the same key written twice in one dict literal, where Python silently keeps
    the last and drops the first. tools/tag_fix_pass2.py had two, so two tag
    assignments were being thrown away every run.
  - a name used in an annotation that was never imported. engine/core.py used
    Optional without it, which does not raise only because Python leaves
    annotations on attribute targets unevaluated.
  - a sentence written straight into a drawing call instead of going through
    _TR. It reads fine to whoever wrote it and is invisible to everyone else:
    the asset studio drew eight English buttons under translated headings, the
    preset modal was in Italian in all five languages, and the game selector
    answered "ERRORE: Scena non trovata!" to a French user.

Pure ast, no lint dependency: this runs wherever the suite runs.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

SOURCE_DIRS = ("engine", "editor", "tools")
SKIP_PARTS = {"__pycache__", "web_template", ".venv"}


def python_files() -> list[Path]:
    files: list[Path] = []
    for folder in SOURCE_DIRS:
        root = Path(folder)
        if not root.exists():
            continue
        files.extend(p for p in root.rglob("*.py")
                     if not SKIP_PARTS & set(p.parts))
    return sorted(files)


ALL_FILES = python_files()


def test_there_are_sources_to_check():
    assert len(ALL_FILES) > 50, "the file discovery found almost nothing"


def duplicate_keys(node: ast.Dict) -> list:
    """The literal keys written more than once in one dict."""
    seen, dupes = set(), []
    for key in node.keys:
        if not isinstance(key, ast.Constant):
            continue                      # computed key: nothing to compare
        if not isinstance(key.value, (str, int, float, bool)):
            continue
        if key.value in seen:
            dupes.append(key.value)
        seen.add(key.value)
    return dupes


@pytest.mark.parametrize("path", ALL_FILES, ids=lambda p: str(p))
def test_no_dict_literal_repeats_a_key(path):
    """A repeated key drops the first value without a word of warning."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    offences = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            for key in duplicate_keys(node):
                offences.append(f"line {node.lineno}: {key!r}")
    assert not offences, (
        f"{path} writes the same key twice, the first value is lost:\n  "
        + "\n  ".join(offences))


def annotation_names(tree: ast.AST) -> set[str]:
    """The bare names used as annotations anywhere in a module."""
    names: set[str] = set()
    for node in ast.walk(tree):
        annotation = getattr(node, "annotation", None) or getattr(node, "returns", None)
        if annotation is None:
            continue
        for sub in ast.walk(annotation):
            if isinstance(sub, ast.Name):
                names.add(sub.id)
    return names


def bound_names(tree: ast.AST) -> set[str]:
    """Everything the module imports, defines or assigns at any level."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                names.add(alias.asname or alias.name.split(".")[0])
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            names.add(node.id)
        elif isinstance(node, ast.arg):
            names.add(node.arg)
        elif isinstance(node, ast.alias):
            names.add(alias_name(node))
    return names


def alias_name(node: ast.alias) -> str:
    return node.asname or node.name.split(".")[0]


def builtin_types() -> set[str]:
    """Builtins usable as an annotation: the classes, not the functions.

    int and BaseException are types and annotate fine. any is a function, and
    writing `x: any` is always a slip for typing.Any: it reads as a type, it
    passes, and it means nothing.
    """
    import builtins

    return {name for name in dir(builtins)
            if isinstance(getattr(builtins, name), type)} | {"None"}


BUILTIN_ANNOTATIONS = builtin_types()


@pytest.mark.parametrize("path", ALL_FILES, ids=lambda p: str(p))
def test_every_annotation_name_is_available(path):
    """An annotation naming something never imported is a NameError waiting
    for the line to move to class or module scope."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    available = bound_names(tree) | BUILTIN_ANNOTATIONS
    missing = sorted(n for n in annotation_names(tree) if n not in available)
    assert not missing, f"{path} annotates with names it never imports: {missing}"


# -----------------------------------------------------------------------------
# 3. NO UI TEXT WRITTEN STRAIGHT INTO A DRAWING CALL
# -----------------------------------------------------------------------------

# Which argument of each drawing helper carries the text the user reads.
TEXT_ARG = {"_draw_text": 1, "_draw_text_wrapped": 1, "_button": 2}

# Literals that are deliberately not translated, and why.
ALLOWED_LITERALS = {
    "HIDDEN INDEX",       # the product name
    "HIDDEN ENGINE",      # the product name
}

UI_DIRS = ("editor", "engine")


def ui_files() -> list[Path]:
    return [p for p in ALL_FILES if p.parts[0] in UI_DIRS]


def literal_ui_text(tree: ast.AST) -> list[str]:
    """Sentences handed to a drawing helper as a plain string literal.

    A single word can be a glyph, a unit or an icon id, so a literal is only
    claimed to be UI text once it contains a space: that is what a sentence
    has, and what a translated label needs room for.
    """
    offences = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
        index = TEXT_ARG.get(name)
        if index is None or len(node.args) <= index:
            continue
        argument = node.args[index]
        if not (isinstance(argument, ast.Constant)
                and isinstance(argument.value, str)):
            continue
        text = argument.value
        if text.strip() in ALLOWED_LITERALS:
            continue
        if " " in text.strip() and any(c.isalpha() for c in text):
            offences.append(f"line {node.lineno}: {name}(..., {text!r})")
    return offences


@pytest.mark.parametrize("path", ui_files(), ids=lambda p: str(p))
def test_no_drawing_call_carries_untranslated_text(path):
    """Every string the user reads goes through _TR or tr, with a key."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    offences = literal_ui_text(tree)
    assert not offences, (
        f"{path} draws text no language file can reach:\n  "
        + "\n  ".join(offences)
        + "\n  route it through _TR and add the key to all five files in "
          "engine/assets/strings/")


def test_the_untranslated_text_guard_can_fail():
    """A guard that never fires is not a guard."""
    tree = ast.parse('_draw_text(surf, "Please wait...", "sm", C, 0, 0)')
    assert literal_ui_text(tree)


def test_the_guard_leaves_a_translated_call_alone():
    tree = ast.parse('_draw_text(surf, self._TR("k", "Please wait..."), "sm")')
    assert not literal_ui_text(tree)
