"""
tests/test_source_hygiene.py

Two mistakes the language does not complain about and no reviewer reliably
spots, both of which cost real data in this repository:

  - the same key written twice in one dict literal, where Python silently keeps
    the last and drops the first. tools/tag_fix_pass2.py had two, so two tag
    assignments were being thrown away every run.
  - a name used in an annotation that was never imported. engine/core.py used
    Optional without it, which does not raise only because Python leaves
    annotations on attribute targets unevaluated.

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
