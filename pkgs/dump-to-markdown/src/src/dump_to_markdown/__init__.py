"""dump_to_markdown -- dump a project tree into a single Markdown document.

Walk every file and folder under a project root and produce a single
Markdown document that contains, for every file found, a heading with
its path -- relative to the project root, prefixed with the root
folder's own name (e.g. ``myproject/src/main.py``) -- followed by a
fenced code block holding that file's contents. The fence's language
hint is chosen from the file's extension, exact filename, or (for
extensionless scripts) its shebang line, so the block gets sensible
syntax highlighting wherever the Markdown is rendered.

Only the ``.git`` directory is skipped by default. Every other file and
folder -- including other dotfiles/dotdirs -- is walked and included.

Requirements
------------
Python 3.8 or newer. No third-party packages -- everything used here
(argparse, dataclasses, logging, os, pathlib, re, sys, typing) is part
of the standard library.

Usage
-----
    dump-to-markdown
    dump-to-markdown --root /path/to/project --output dump.md
    dump-to-markdown --exclude-dir node_modules --exclude-dir .venv
    dump-to-markdown --max-size 500000
    dump-to-markdown --follow-symlinks
    dump-to-markdown -v

Run ``dump-to-markdown --help`` for the full option list, or use the
module form: ``python3 -m dump_to_markdown``.
"""

from __future__ import annotations

import argparse
import logging
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, List, Optional, Set

__version__ = "1.2.0"

__all__ = [
    "DEFAULT_EXCLUDED_DIRS",
    "EXTENSION_LANG_MAP",
    "FILENAME_LANG_MAP",
    "LoadedFile",
    "SHEBANG_LANG_MAP",
    "build_markdown",
    "choose_fence",
    "detect_language",
    "iter_project_files",
    "load_file",
    "main",
    "parse_args",
]

logger = logging.getLogger("dump_to_markdown")


def _configure_logging(verbose: bool) -> None:
    # force=True (Python 3.8+) makes this safe to call more than once in
    # the same process (e.g. if `main()` is imported and re-invoked by
    # another script or a test suite) instead of silently no-op'ing.
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
        force=True,
    )


# --------------------------------------------------------------------------
# Language detection for fenced code blocks
# --------------------------------------------------------------------------

# Extension -> Markdown fence language identifier.
EXTENSION_LANG_MAP = {
    ".py": "python",
    ".pyi": "python",
    ".sh": "bash",
    ".bash": "bash",
    ".zsh": "zsh",
    ".fish": "fish",
    ".js": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".jsx": "jsx",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".json": "json",
    ".json5": "json5",
    ".jsonc": "jsonc",
    ".yml": "yaml",
    ".yaml": "yaml",
    ".toml": "toml",
    ".ini": "ini",
    ".cfg": "ini",
    ".conf": "conf",
    ".md": "markdown",
    ".markdown": "markdown",
    ".rst": "rst",
    ".html": "html",
    ".htm": "html",
    ".css": "css",
    ".scss": "scss",
    ".sass": "sass",
    ".less": "less",
    ".xml": "xml",
    ".svg": "xml",
    ".sql": "sql",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".hpp": "cpp",
    ".hh": "cpp",
    ".cs": "csharp",
    ".java": "java",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".go": "go",
    ".rs": "rust",
    ".rb": "ruby",
    ".php": "php",
    ".pl": "perl",
    ".lua": "lua",
    ".r": "r",
    ".swift": "swift",
    ".m": "objectivec",
    ".mm": "objectivec",
    ".scala": "scala",
    ".ex": "elixir",
    ".exs": "elixir",
    ".erl": "erlang",
    ".hs": "haskell",
    ".vim": "vim",
    ".dockerfile": "dockerfile",
    ".mk": "makefile",
    ".gradle": "groovy",
    ".groovy": "groovy",
    ".diff": "diff",
    ".patch": "diff",
    ".csv": "csv",
    ".tsv": "tsv",
    ".env": "bash",
    ".just": "make",
    ".service": "ini",
    ".mount": "ini",
    ".timer": "ini",
    ".socket": "ini",
    ".rules": "text",
    ".repo": "ini",
    ".desktop": "ini",
    ".txt": "text",
    ".tex": "latex",
    ".proto": "protobuf",
    ".graphql": "graphql",
    ".gql": "graphql",
    ".ps1": "powershell",
    ".bat": "batch",
    ".cmd": "batch",
    ".nix": "nix",
    ".tf": "hcl",
    ".hcl": "hcl",
    ".vue": "vue",
    ".svelte": "svelte",
    ".dart": "dart",
    ".zig": "zig",
}

# Exact filenames (no/unusual extension) -> fence language.
FILENAME_LANG_MAP = {
    "Dockerfile": "dockerfile",
    "Containerfile": "dockerfile",
    "Makefile": "makefile",
    "makefile": "makefile",
    "GNUmakefile": "makefile",
    "Justfile": "make",
    "justfile": "make",
    "CMakeLists.txt": "cmake",
    ".gitignore": "text",
    ".gitattributes": "text",
    ".gitmodules": "ini",
    ".dockerignore": "text",
    ".editorconfig": "ini",
    ".flake8": "ini",
    ".npmrc": "ini",
    ".yarnrc": "yaml",
    "LICENSE": "text",
    "LICENCE": "text",
    "COPYING": "text",
}

# Shebang interpreter (basename, after resolving `env`) -> fence language.
# Only consulted for extensionless files whose name isn't in
# FILENAME_LANG_MAP -- see detect_language().
SHEBANG_LANG_MAP = {
    "python": "python",
    "python3": "python",
    "bash": "bash",
    "sh": "bash",
    "dash": "bash",
    "zsh": "zsh",
    "fish": "fish",
    "perl": "perl",
    "ruby": "ruby",
    "node": "javascript",
    "nodejs": "javascript",
    "make": "make",
}

DEFAULT_EXCLUDED_DIRS: Set[str] = {".git"}

# Extensions that are essentially always binary; trusted outright so we
# don't even open these files.
BINARY_EXTENSIONS: Set[str] = {
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".webp", ".tiff",
    ".pdf", ".zip", ".tar", ".gz", ".tgz", ".bz2", ".xz", ".7z", ".rar",
    ".exe", ".dll", ".so", ".dylib", ".o", ".a", ".class", ".jar",
    ".mp3", ".mp4", ".avi", ".mov", ".mkv", ".wav", ".flac", ".ogg",
    ".ttf", ".otf", ".woff", ".woff2", ".eot",
    ".pyc", ".pyo", ".whl",
    ".db", ".sqlite", ".sqlite3",
}

_BACKTICK_RUN_RE = re.compile(r"`+")


def _shebang_language_from_line(first_line: str) -> Optional[str]:
    """Map a ``#!...`` line to a fence language, or None if inapplicable."""
    if not first_line.startswith("#!"):
        return None
    parts = first_line[2:].split()
    if not parts:
        return None
    interpreter = Path(parts[0]).name
    if interpreter == "env" and len(parts) > 1:
        interpreter = Path(parts[1]).name
    return SHEBANG_LANG_MAP.get(interpreter)


def detect_language(path: Path, sample_text: Optional[str] = None) -> str:
    """Return a Markdown fence language identifier for ``path``.

    ``sample_text`` -- the file's already-decoded content, if available --
    is reused (never re-read from disk) to sniff a shebang line for
    extensionless scripts that aren't in FILENAME_LANG_MAP.
    """
    if path.name in FILENAME_LANG_MAP:
        return FILENAME_LANG_MAP[path.name]

    suffix = path.suffix.lower()
    if suffix in EXTENSION_LANG_MAP:
        return EXTENSION_LANG_MAP[suffix]

    if not suffix and sample_text:
        first_line = sample_text.split("\n", 1)[0]
        shebang_lang = _shebang_language_from_line(first_line)
        if shebang_lang:
            return shebang_lang

    return "text"


def choose_fence(content: str) -> str:
    """Pick a backtick fence long enough that it can't collide with ``content``."""
    longest = max((len(m.group()) for m in _BACKTICK_RUN_RE.finditer(content)), default=0)
    return "`" * max(3, longest + 1)


# --------------------------------------------------------------------------
# File loading (single read, binary/text classification)
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class LoadedFile:
    """Result of attempting to load a file's textual content."""

    binary: bool
    text: str = ""
    error: Optional[str] = None


def load_file(path: Path, sniff_size: int = 8192) -> LoadedFile:
    """Read ``path`` once and classify it as text or binary.

    Detection order:
      1. A known-binary extension is trusted outright (no I/O at all).
      2. The raw bytes are read exactly once. A NUL byte in the first
         ``sniff_size`` bytes is treated as a strong binary signal (the
         same heuristic ``file(1)`` and git use).
      3. The full content is decoded as UTF-8. Files that decode cleanly
         are text. Files that don't are retried with ``errors="replace"``;
         if more than 1% of the resulting characters are replacement
         characters, the file is treated as binary instead of dumping a
         wall of U+FFFD into the Markdown output.
    """
    if path.suffix.lower() in BINARY_EXTENSIONS:
        return LoadedFile(binary=True)

    try:
        raw = path.read_bytes()
    except OSError as exc:
        return LoadedFile(binary=False, error=str(exc))

    if b"\x00" in raw[:sniff_size]:
        return LoadedFile(binary=True)

    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("utf-8", errors="replace")
        if text and (text.count("\ufffd") / len(text)) > 0.01:
            return LoadedFile(binary=True)

    return LoadedFile(binary=False, text=text)


# --------------------------------------------------------------------------
# Directory walking
# --------------------------------------------------------------------------


def iter_project_files(
    root: Path,
    excluded_dirs: Set[str],
    follow_symlinks: bool = False,
) -> Iterator[Path]:
    """Yield every file (and, when not following symlinks, every symlinked
    directory as a standalone marker entry) under ``root``.

    Directories named in ``excluded_dirs`` are pruned wherever they occur
    in the tree. Results within each directory are sorted for
    deterministic output.

    Without ``follow_symlinks``, ``os.walk`` already refuses to descend
    into a symlinked directory -- but it also never appears in
    ``filenames``, so by default it would vanish from the walk entirely.
    We surface it here as a yielded path so the caller can note it in the
    output instead of silently dropping it. With ``follow_symlinks=True``
    symlinked directories are walked normally; a cycle of symlinks can
    then make this loop forever, exactly as with ``find -L``.
    """
    for dirpath, dirnames, filenames in os.walk(root, followlinks=follow_symlinks):
        dirnames[:] = sorted(d for d in dirnames if d not in excluded_dirs)

        if not follow_symlinks:
            kept = []
            for name in dirnames:
                full = Path(dirpath) / name
                if full.is_symlink():
                    yield full  # marker: noted, not traversed
                else:
                    kept.append(name)
            dirnames[:] = kept

        for filename in sorted(filenames):
            yield Path(dirpath) / filename


# --------------------------------------------------------------------------
# Markdown generation
# --------------------------------------------------------------------------


def build_markdown(
    root: Path,
    output_path: Path,
    excluded_dirs: Set[str],
    max_size: Optional[int],
    follow_symlinks: bool = False,
) -> int:
    """Write the Markdown dump to ``output_path``. Returns the number of
    files whose contents were actually embedded (excludes skipped ones).

    Each heading is the file's path relative to ``root``, prefixed with
    ``root``'s own directory name -- e.g. ``myproject/src/main.py`` rather
    than just ``src/main.py`` -- so a heading reads as a full project-
    relative path even once copied out of context.
    """
    resolved_output = output_path.resolve()
    root_resolved = root.resolve()
    # .name is '' for a filesystem root like "/"; fall back to a literal
    # label rather than emitting a heading that starts with "/...".
    root_name = root_resolved.name or "root"
    embedded_count = 0
    total_count = 0

    with output_path.open("w", encoding="utf-8", newline="\n") as out:
        out.write(f"# Project dump: {root_name}\n\n")

        for file_path in iter_project_files(root, excluded_dirs, follow_symlinks):
            if file_path.resolve() == resolved_output:
                # Never embed the file we are currently writing.
                continue

            total_count += 1
            rel_str = file_path.relative_to(root).as_posix()
            heading_path = f"{root_name}/{rel_str}"
            # Wrapped in an inline code span so a path containing
            # Markdown-special characters (#, *, _, [ ]) can't distort
            # the rendered heading.
            out.write(f"## `{heading_path}`\n\n")

            is_link = file_path.is_symlink()
            if is_link:
                try:
                    target = os.readlink(file_path)
                except OSError:
                    target = "?"
                out.write(f"_Symlink -> `{target}`_\n\n")

            if is_link and file_path.is_dir():
                out.write("_Directory symlink, not followed._\n\n")
                continue

            try:
                size = file_path.stat().st_size
            except OSError as exc:
                out.write(f"_Could not stat file: {exc}._\n\n")
                logger.warning("Could not stat %s: %s", rel_str, exc)
                continue

            if max_size is not None and size > max_size:
                out.write(
                    f"_Skipped: file is {size} bytes, "
                    f"over the {max_size}-byte limit._\n\n"
                )
                logger.info("Skipped (too large, %d bytes): %s", size, rel_str)
                continue

            loaded = load_file(file_path)

            if loaded.error is not None:
                out.write(f"_Could not read file: {loaded.error}._\n\n")
                logger.warning("Could not read %s: %s", rel_str, loaded.error)
                continue

            if loaded.binary:
                out.write(f"_Skipped: binary file ({size} bytes)._\n\n")
                logger.info("Skipped (binary): %s", rel_str)
                continue

            language = detect_language(file_path, sample_text=loaded.text)
            fence = choose_fence(loaded.text)
            out.write(f"{fence}{language}\n")
            out.write(loaded.text)
            if loaded.text and not loaded.text.endswith("\n"):
                out.write("\n")
            out.write(f"{fence}\n\n")

            embedded_count += 1
            logger.debug("Embedded %s as %s", rel_str, language)

    logger.info(
        "Processed %d file(s): %d embedded, %d skipped/errored",
        total_count,
        embedded_count,
        total_count - embedded_count,
    )
    return embedded_count


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _non_negative_int(value: str) -> int:
    try:
        ivalue = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"not an integer: {value!r}") from exc
    if ivalue < 0:
        raise argparse.ArgumentTypeError(f"must be >= 0: {value!r}")
    return ivalue


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="dump-to-markdown",
        description=(
            "Recursively dump every file under a project root into a single "
            "Markdown file, one heading + fenced code block per file."
        ),
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        help="Root directory to scan (default: current directory).",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=Path("project_dump.md"),
        help="Path of the Markdown file to write (default: ./project_dump.md).",
    )
    parser.add_argument(
        "--exclude-dir",
        action="append",
        default=[],
        metavar="DIRNAME",
        help=(
            "Extra directory name to exclude (repeatable). "
            "'.git' is always excluded."
        ),
    )
    parser.add_argument(
        "--max-size",
        type=_non_negative_int,
        default=None,
        metavar="BYTES",
        help="Skip embedding files larger than this many bytes.",
    )
    parser.add_argument(
        "--follow-symlinks",
        action="store_true",
        help=(
            "Descend into symlinked directories instead of just noting them. "
            "Caution: a symlink cycle will make the scan loop forever, the "
            "same risk as `find -L`."
        ),
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable debug-level logging.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    _configure_logging(args.verbose)

    root = args.root.resolve()
    if not root.is_dir():
        logger.error("Root path is not a directory: %s", root)
        return 1

    output_path = args.output
    if not output_path.is_absolute():
        output_path = Path.cwd() / output_path

    excluded_dirs = DEFAULT_EXCLUDED_DIRS | set(args.exclude_dir)

    logger.info("Root:      %s", root)
    logger.info("Output:    %s", output_path)
    logger.info("Excluding: %s", ", ".join(sorted(excluded_dirs)))
    if args.follow_symlinks:
        logger.info("Following symlinked directories (cycles will hang).")

    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if output_path.exists():
            logger.warning("Output file already exists; it will be overwritten: %s", output_path)
        build_markdown(
            root,
            output_path,
            excluded_dirs,
            args.max_size,
            follow_symlinks=args.follow_symlinks,
        )
    except OSError as exc:
        logger.error("Failed to write %s: %s", output_path, exc)
        return 1

    logger.info("Done -> %s", output_path)
    return 0
