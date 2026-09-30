"""Tests for the rmi package.

`rmi -h` — the build-time smoke test — never reaches the code that actually
moves a file. A missing `datetime` import shipped in the image for exactly that
reason: the tool trashed the file, then died with a NameError while writing the
.trashinfo companion.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import rmi


@pytest.fixture(autouse=True)
def isolated_trash(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Point the module's trash constants at a throwaway directory."""
    files = tmp_path / "Trash" / "files"
    info = tmp_path / "Trash" / "info"
    monkeypatch.setattr(rmi, "TRASH_DIR", files)
    monkeypatch.setattr(rmi, "TRASH_INFO_DIR", info)
    files.mkdir(parents=True)
    info.mkdir(parents=True)
    return files, info


def test_move_to_trash_writes_trashinfo(tmp_path: Path, isolated_trash):
    files, info = isolated_trash

    target = tmp_path / "doc.txt"
    target.write_text("hello\n", encoding="utf-8")

    assert rmi.move_to_trash(target, verbose=False) is True
    assert (files / "doc.txt").read_text(encoding="utf-8") == "hello\n"
    assert not target.exists()

    written = (info / "doc.txt.trashinfo").read_text(encoding="utf-8")
    assert written.startswith("[Trash Info]\n")
    assert "Path=" in written
    assert "DeletionDate=" in written


def test_trashinfo_records_where_the_file_came_from(tmp_path: Path, isolated_trash):
    _files, info = isolated_trash

    nested = tmp_path / "sub"
    nested.mkdir()
    target = nested / "note.md"
    target.write_text("x", encoding="utf-8")

    rmi.move_to_trash(target, verbose=False)

    written = (info / "note.md.trashinfo").read_text(encoding="utf-8")
    path_line = next(l for l in written.splitlines() if l.startswith("Path="))
    # The original location, not the trash location the file moved to.
    assert path_line.endswith("/sub/note.md")


def test_collision_creates_numbered_backup(tmp_path: Path, isolated_trash):
    files, _info = isolated_trash
    (files / "dup.txt").write_text("old", encoding="utf-8")

    target = tmp_path / "dup.txt"
    target.write_text("new", encoding="utf-8")

    assert rmi.move_to_trash(target, verbose=False) is True
    assert (files / "dup.txt").read_text(encoding="utf-8") == "new"
    assert (files / "dup.txt.~1~").read_text(encoding="utf-8") == "old"


def test_main_skips_dot_and_missing_paths(tmp_path: Path):
    assert rmi.main(["-f", ".", str(tmp_path / "nope.txt")]) == 0


def test_main_with_no_arguments_returns_1():
    assert rmi.main([]) == 1
