"""Tests for the dump-to-markdown package."""

from __future__ import annotations

from pathlib import Path

import pytest

from dump_to_markdown import (
    DEFAULT_EXCLUDED_DIRS,
    LoadedFile,
    build_markdown,
    choose_fence,
    detect_language,
    iter_project_files,
    load_file,
    main,
    parse_args,
)

# --------------------------------------------------------------------------
# detect_language
# --------------------------------------------------------------------------


def test_detect_language_by_extension(tmp_path: Path):
    assert detect_language(tmp_path / "main.py") == "python"
    assert detect_language(tmp_path / "recipe.yml") == "yaml"
    assert detect_language(tmp_path / "recipes.just") == "make"
    assert detect_language(tmp_path / "unit.service") == "ini"


def test_detect_language_by_exact_filename(tmp_path: Path):
    assert detect_language(tmp_path / "Dockerfile") == "dockerfile"
    assert detect_language(tmp_path / "Justfile") == "make"
    assert detect_language(tmp_path / ".gitignore") == "text"
    # Exact filename wins over extension mapping.
    assert detect_language(tmp_path / "CMakeLists.txt") == "cmake"


def test_detect_language_by_shebang(tmp_path: Path):
    p = tmp_path / "run"  # extensionless, not in FILENAME_LANG_MAP
    assert detect_language(p, sample_text="#!/usr/bin/env bash\nset -euo pipefail\n") == "bash"
    assert detect_language(p, sample_text="#!/usr/bin/python3\n") == "python"


def test_detect_language_fallback(tmp_path: Path):
    p = tmp_path / "mystery"
    assert detect_language(p) == "text"
    assert detect_language(p, sample_text="just plain text\n") == "text"


# --------------------------------------------------------------------------
# choose_fence
# --------------------------------------------------------------------------


def test_choose_fence_default_and_growth():
    assert choose_fence("no backticks here") == "```"
    # A single-backtick run still only warrants the 3-backtick minimum.
    assert choose_fence("inline `code` span") == "```"
    # A 3-backtick run in the content forces a 4-backtick fence.
    assert choose_fence("```\nfenced\n```") == "````"


# --------------------------------------------------------------------------
# load_file
# --------------------------------------------------------------------------


def test_load_file_text(tmp_path: Path):
    p = tmp_path / "a.txt"
    p.write_text("hello\n", encoding="utf-8")
    assert load_file(p) == LoadedFile(binary=False, text="hello\n")


def test_load_file_trusted_binary_extension(tmp_path: Path):
    p = tmp_path / "img.png"
    p.write_bytes(b"not really a png")  # no NUL byte; extension trusted anyway
    assert load_file(p).binary is True


def test_load_file_nul_byte_is_binary(tmp_path: Path):
    p = tmp_path / "blob.dat"
    p.write_bytes(b"abcdefg\x00hijklmn")
    assert load_file(p).binary is True


def test_load_file_heavily_replaced_utf8_is_binary(tmp_path: Path):
    p = tmp_path / "junk.log"
    p.write_bytes(bytes(range(0x80, 0x100)) * 64)  # invalid UTF-8 throughout
    assert load_file(p).binary is True


def test_load_file_unreadable_reports_error(tmp_path: Path):
    loaded = load_file(tmp_path / "missing.txt")
    assert loaded.binary is False
    assert loaded.error is not None


# --------------------------------------------------------------------------
# iter_project_files
# --------------------------------------------------------------------------


def test_iter_project_files_sorted_and_excludes_git(tmp_path: Path):
    (tmp_path / "b").mkdir()
    (tmp_path / "a").mkdir()
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text("")
    (tmp_path / "a" / "one.txt").write_text("")
    (tmp_path / "b" / "two.txt").write_text("")
    (tmp_path / "top.txt").write_text("")

    got = [
        p.relative_to(tmp_path).as_posix()
        for p in iter_project_files(tmp_path, DEFAULT_EXCLUDED_DIRS)
    ]

    assert ".git/config" not in got
    # os.walk yields the root's files first; within each dir, sorted.
    assert got == ["top.txt", "a/one.txt", "b/two.txt"]


def test_iter_project_files_custom_exclusions(tmp_path: Path):
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "x.js").write_text("")
    (tmp_path / "keep").mkdir()
    (tmp_path / "keep" / "y.py").write_text("")

    got = [
        p.relative_to(tmp_path).as_posix()
        for p in iter_project_files(tmp_path, DEFAULT_EXCLUDED_DIRS | {"node_modules"})
    ]
    assert got == ["keep/y.py"]


def test_iter_project_files_symlinked_dir_is_marker(tmp_path: Path):
    (tmp_path / "real").mkdir()
    (tmp_path / "real" / "f.txt").write_text("")
    (tmp_path / "link").symlink_to(tmp_path / "real")

    got = [
        p.relative_to(tmp_path).as_posix()
        for p in iter_project_files(tmp_path, DEFAULT_EXCLUDED_DIRS)
    ]

    assert "link" in got  # surfaced as a marker...
    assert "link/f.txt" not in got  # ...but not traversed


# --------------------------------------------------------------------------
# build_markdown
# --------------------------------------------------------------------------


def test_build_markdown_headings_fences_and_counts(tmp_path: Path):
    root = tmp_path / "myproject"
    (root / "src").mkdir(parents=True)
    (root / "src" / "main.py").write_text("print('hi')\n")
    (root / "notes.md").write_text("# notes\n")
    out = tmp_path / "dump.md"

    embedded = build_markdown(root, out, DEFAULT_EXCLUDED_DIRS, max_size=None)
    text = out.read_text(encoding="utf-8")

    assert embedded == 2
    assert text.startswith("# Project dump: myproject\n")
    assert "## `myproject/src/main.py`\n\n```python\nprint('hi')\n```\n" in text
    assert "## `myproject/notes.md`\n\n```markdown\n# notes\n```\n" in text


def test_build_markdown_never_embeds_own_output(tmp_path: Path):
    root = tmp_path / "proj"
    root.mkdir()
    out = root / "dump.md"

    build_markdown(root, out, DEFAULT_EXCLUDED_DIRS, max_size=None)

    assert "## `proj/dump.md`" not in out.read_text(encoding="utf-8")


def test_build_markdown_skips_oversize_and_binary(tmp_path: Path):
    root = tmp_path / "proj"
    root.mkdir()
    (root / "big.txt").write_text("x" * 100)
    (root / "img.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    out = tmp_path / "dump.md"

    embedded = build_markdown(root, out, DEFAULT_EXCLUDED_DIRS, max_size=50)
    text = out.read_text(encoding="utf-8")

    assert embedded == 0
    assert "_Skipped: file is 100 bytes, over the 50-byte limit._" in text
    assert "_Skipped: binary file" in text


def test_build_markdown_notes_directory_symlink(tmp_path: Path):
    root = tmp_path / "proj"
    (root / "elsewhere").mkdir(parents=True)
    (root / "elsewhere" / "f.txt").write_text("")
    (root / "alias").symlink_to(root / "elsewhere")
    out = tmp_path / "dump.md"

    build_markdown(root, out, DEFAULT_EXCLUDED_DIRS, max_size=None)
    text = out.read_text(encoding="utf-8")

    assert "## `proj/alias`" in text
    assert "_Directory symlink, not followed._" in text
    assert "alias/f.txt" not in text


def test_build_markdown_fence_grows_for_backtick_content(tmp_path: Path):
    root = tmp_path / "proj"
    root.mkdir()
    (root / "doc.md").write_text("````\nnested fence\n````\n")
    out = tmp_path / "dump.md"

    build_markdown(root, out, DEFAULT_EXCLUDED_DIRS, max_size=None)
    text = out.read_text(encoding="utf-8")

    assert "`````markdown\n````\nnested fence\n````\n`````\n" in text


# --------------------------------------------------------------------------
# parse_args
# --------------------------------------------------------------------------


def test_parse_args_defaults():
    args = parse_args([])
    assert args.exclude_dir == []
    assert args.max_size is None
    assert args.follow_symlinks is False
    assert args.verbose is False


def test_parse_args_repeatable_exclude():
    args = parse_args(["--exclude-dir", "node_modules", "--exclude-dir", ".venv"])
    assert args.exclude_dir == ["node_modules", ".venv"]


def test_parse_args_rejects_negative_max_size(capsys: pytest.CaptureFixture[str]):
    with pytest.raises(SystemExit):
        parse_args(["--max-size", "-1"])
    assert "must be >= 0" in capsys.readouterr().err


def test_parse_args_version(capsys: pytest.CaptureFixture[str]):
    with pytest.raises(SystemExit) as excinfo:
        parse_args(["--version"])
    assert excinfo.value.code == 0
    assert "dump-to-markdown 1.2.0" in capsys.readouterr().out


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------


def test_main_writes_dump_relative_to_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = tmp_path / "proj"
    root.mkdir()
    (root / "a.py").write_text("x = 1\n")
    monkeypatch.chdir(tmp_path)

    assert main(["--root", str(root)]) == 0
    assert (tmp_path / "project_dump.md").exists()


def test_main_returns_1_for_missing_root():
    assert main(["--root", "/nonexistent/halcyon/dtm/test/path"]) == 1
