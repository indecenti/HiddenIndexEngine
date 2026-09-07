"""
tests/test_build_engine_data.py

What a desktop build puts in engine/data. The runtime opens only the global
catalogs and the tag taxonomy from there; the rest of that folder is the
editor's, and used to be copied into every package wholesale.

These pin the two halves of the rule: the build must find the same catalogs
the runtime will look for, and it must slim them to what the game places.
"""

from __future__ import annotations

import json

import pytest

from editor.build_system import (
    RUNTIME_DATA_FILES,
    _find_global_catalogs,
    _pack_engine_data,
)


def write_catalog(path, ids):
    path.write_text(json.dumps(
        {"objects": [{"id": i, "icon": f"objects/{i}.png"} for i in ids]}),
        encoding="utf-8")


@pytest.fixture
def data_src(tmp_path):
    """An engine/data as it really looks: catalogs plus the editor's clutter."""
    src = tmp_path / "data"
    src.mkdir()
    write_catalog(src / "global_cartoon_catalog.json", ["lamp", "cat", "tree"])
    write_catalog(src / "global_real_catalog.json", ["chair", "lamp"])
    src.joinpath("tags_taxonomy.json").write_text('{"tags": []}', encoding="utf-8")
    src.joinpath("effects_catalog.json").write_text('{"effects": []}', encoding="utf-8")
    # The editor's own, and heavy: 17 MB and 1.6 MB in the real project.
    src.joinpath("object_profiles.db").write_bytes(b"x" * 4096)
    src.joinpath("bg_cache.db").write_bytes(b"y" * 2048)
    # Backups, in both shapes the project has produced.
    write_catalog(src / "global_objects_catalog_backup_20260420_184414.json", ["old"])
    src.joinpath("global_real_catalog.json.bak").write_text("{}", encoding="utf-8")
    return src


# -----------------------------------------------------------------------------
# FINDING THE CATALOGS
# -----------------------------------------------------------------------------

def test_the_catalogs_are_found_and_the_backups_are_not(data_src):
    found = {p.name for p in _find_global_catalogs(data_src)}
    assert found == {"global_cartoon_catalog.json", "global_real_catalog.json"}


def test_the_build_looks_for_what_the_runtime_looks_for(data_src):
    """The two globs must agree, or the build ships catalogs nobody reads."""
    from engine import catalog_manager

    build_side = {p.name for p in _find_global_catalogs(data_src)}

    all_files = list(data_src.glob("global_*_catalog.json"))
    runtime_side = {
        f.name for f in all_files
        if "backup" not in f.name.lower() and not f.name.endswith(".bak")
    }
    assert build_side == runtime_side
    assert hasattr(catalog_manager, "_load_global_catalog"), (
        "the runtime discovery this mirrors has moved; check they still agree")


def test_a_folder_with_no_catalogs_is_not_an_error(tmp_path):
    assert _find_global_catalogs(tmp_path / "nothing_here") == []


# -----------------------------------------------------------------------------
# PACKING
# -----------------------------------------------------------------------------

def test_only_the_used_objects_are_shipped(data_src, tmp_path):
    dst = tmp_path / "pkg" / "engine" / "data"
    _pack_engine_data(data_src, dst, used_objects={"lamp", "chair"})

    cartoon = json.loads((dst / "global_cartoon_catalog.json").read_text(encoding="utf-8"))
    real = json.loads((dst / "global_real_catalog.json").read_text(encoding="utf-8"))
    assert [o["id"] for o in cartoon["objects"]] == ["lamp"]
    assert [o["id"] for o in real["objects"]] == ["chair", "lamp"]


def test_the_catalogs_keep_the_names_the_runtime_globs_for(data_src, tmp_path):
    dst = tmp_path / "pkg"
    _pack_engine_data(data_src, dst, used_objects={"lamp"})
    shipped = {p.name for p in dst.glob("global_*_catalog.json")}
    assert shipped == {"global_cartoon_catalog.json", "global_real_catalog.json"}


def test_the_taxonomy_travels_with_them(data_src, tmp_path):
    dst = tmp_path / "pkg"
    _pack_engine_data(data_src, dst, used_objects=set())
    for name in RUNTIME_DATA_FILES:
        assert (dst / name).exists(), f"{name} is read by the runtime"


def test_the_editors_own_files_stay_behind(data_src, tmp_path):
    """The profile database and the background cache are 18 MB of editor state."""
    dst = tmp_path / "pkg"
    _pack_engine_data(data_src, dst, used_objects={"lamp"})
    shipped = {p.name for p in dst.iterdir()}
    assert "object_profiles.db" not in shipped
    assert "bg_cache.db" not in shipped
    assert "effects_catalog.json" not in shipped, "the effects palette is the editor's"


def test_no_backup_is_ever_shipped(data_src, tmp_path):
    dst = tmp_path / "pkg"
    _pack_engine_data(data_src, dst, used_objects={"old", "lamp"})
    shipped = [p.name for p in dst.iterdir()]
    assert not any("backup" in n.lower() or n.endswith(".bak") for n in shipped), shipped


def test_a_game_using_nothing_ships_empty_catalogs_not_full_ones(data_src, tmp_path):
    dst = tmp_path / "pkg"
    stats = _pack_engine_data(data_src, dst, used_objects=set())
    assert stats["kept"] == 0
    assert stats["total"] == 5
    for cat in dst.glob("global_*_catalog.json"):
        assert json.loads(cat.read_text(encoding="utf-8"))["objects"] == []


def test_the_packing_is_reported_for_the_build_log(data_src, tmp_path):
    stats = _pack_engine_data(data_src, tmp_path / "pkg", used_objects={"lamp", "cat"})
    assert stats["catalogs"] == 2
    assert stats["kept"] == 3          # lamp and cat in cartoon, lamp in real
    assert stats["total"] == 5
    assert stats["bytes"] > 0


def test_slimming_is_smaller_than_shipping_everything(data_src, tmp_path):
    dst = tmp_path / "pkg"
    _pack_engine_data(data_src, dst, used_objects={"lamp"})
    shipped = sum(p.stat().st_size for p in dst.rglob("*") if p.is_file())
    whole_folder = sum(p.stat().st_size for p in data_src.rglob("*") if p.is_file())
    assert shipped < whole_folder


def test_an_unreadable_catalog_does_not_stop_the_build(data_src, tmp_path):
    """One broken file must not cost the whole package."""
    (data_src / "global_broken_catalog.json").write_text("{not json", encoding="utf-8")
    dst = tmp_path / "pkg"
    stats = _pack_engine_data(data_src, dst, used_objects={"lamp"})
    assert (dst / "global_cartoon_catalog.json").exists(), "the good ones still ship"
    assert stats["catalogs"] == 3, "it was found"
    assert not (dst / "global_broken_catalog.json").exists(), (
        "shipping it empty would make its objects look merely unused")


def test_the_destination_is_created_if_it_is_not_there(data_src, tmp_path):
    dst = tmp_path / "deep" / "pkg" / "engine" / "data"
    _pack_engine_data(data_src, dst, used_objects={"lamp"})
    assert dst.is_dir()
