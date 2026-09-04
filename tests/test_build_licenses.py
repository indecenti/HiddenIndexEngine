"""
tests/test_build_licenses.py

Legal notices shipped with a build (editor/build_common.py):

  1. every distributed build carries the engine terms, the notice, the
     third-party notices (pygame is LGPL: its text must travel with the binary)
     and the asset terms;
  2. the files are written as .txt, because the Android packaging drops *.md;
  3. a game with its own commercial engine license overrides the repository one;
  4. a missing source file degrades the bundle instead of failing the build.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from editor.build_common import (GAME_LICENSE_OVERRIDE, LICENSE_DIR_NAME,
                                 LICENSE_INDEX_NAME, LICENSE_SOURCES,
                                 build_license_bundle, write_license_bundle)

ROOT = Path(__file__).resolve().parents[1]


def test_repository_ships_every_source_file():
    """The bundle is only as good as the files it copies."""
    for src_name, _out in LICENSE_SOURCES:
        assert (ROOT / src_name).is_file(), f"{src_name} missing from the repository"


def test_bundle_contains_the_expected_files():
    bundle = build_license_bundle(ROOT)
    expected = {out for _src, out in LICENSE_SOURCES} | {LICENSE_INDEX_NAME}
    assert set(bundle) == expected
    assert all(name.endswith(".txt") for name in bundle), \
        "the Android packaging excludes *.md: every notice must be a .txt"
    assert all(text.strip() for text in bundle.values())


def test_bundle_carries_the_license_texts():
    bundle = build_license_bundle(ROOT)
    assert "PolyForm Noncommercial License 1.0.0" in bundle["ENGINE-LICENSE.txt"]
    assert "LGPL" in bundle["THIRD-PARTY-NOTICES.txt"]
    assert "pygame" in bundle[LICENSE_INDEX_NAME]
    assert "HiddenIndexEngine" in bundle["NOTICE.txt"]


def test_a_commercial_game_overrides_the_engine_terms(tmp_path):
    """A game sold under a commercial license must not ship the NC text."""
    game = tmp_path / "games" / "g1"
    game.mkdir(parents=True)
    (game / GAME_LICENSE_OVERRIDE).write_text("Commercial license for ACME Ltd.",
                                              encoding="utf-8")
    bundle = build_license_bundle(ROOT, game)
    assert bundle["ENGINE-LICENSE.txt"] == "Commercial license for ACME Ltd."
    # everything else still comes from the repository
    assert "LGPL" in bundle["THIRD-PARTY-NOTICES.txt"]


def test_missing_sources_degrade_instead_of_raising(tmp_path):
    bundle = build_license_bundle(tmp_path)          # empty directory
    assert set(bundle) == {LICENSE_INDEX_NAME}       # the index is always written


def test_write_bundle_creates_the_folder(tmp_path):
    out = write_license_bundle(ROOT, tmp_path)
    assert out == tmp_path / LICENSE_DIR_NAME and out.is_dir()
    written = {p.name for p in out.iterdir()}
    assert written == set(build_license_bundle(ROOT))
    assert (out / "ENGINE-LICENSE.txt").read_text(encoding="utf-8").strip()


def test_android_packaging_would_include_the_folder():
    """buildozer.spec must not exclude the notices from the APK."""
    from editor.android_build_system import _generate_buildozer_spec

    spec = _generate_buildozer_spec("g1", "Game One", "1.0")
    exts = next(l for l in spec.splitlines() if l.startswith("source.include_exts"))
    excluded_dirs = next(l for l in spec.splitlines() if l.startswith("source.exclude_dirs"))
    assert "txt" in exts.split("=", 1)[1]
    assert LICENSE_DIR_NAME not in excluded_dirs
