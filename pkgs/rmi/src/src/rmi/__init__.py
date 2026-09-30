"""rmi - Safe Removal Tool.

Python 3.13 port of the original ``rmi`` bash script.

Moves files and directories to the XDG trash directory instead of deleting
them. Name collisions are resolved with GNU-mv style numbered backups: the
item already present in the trash is renamed to ``name.~1~``, ``name.~2~``,
... and the newly trashed item keeps the plain name.
"""

import argparse
import os
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import NoReturn
from urllib.parse import quote

SCRIPT_NAME: str = Path(sys.argv[0]).name or "rmi"
VERSION: str = "2.0.1"

_XDG_DATA_HOME = os.environ.get("XDG_DATA_HOME") or str(
    Path.home() / ".local" / "share"
)
TRASH_DIR: Path = Path(_XDG_DATA_HOME) / "Trash" / "files"
TRASH_INFO_DIR: Path = Path(_XDG_DATA_HOME) / "Trash" / "info"

# Colors are only emitted when stdout is a terminal.
if sys.stdout.isatty():
    COLOR_RED = "\033[0;31m"
    COLOR_GREEN = "\033[0;32m"
    COLOR_YELLOW = "\033[0;33m"
    COLOR_RESET = "\033[0m"
else:
    COLOR_RED = COLOR_GREEN = COLOR_YELLOW = COLOR_RESET = ""

DESCRIPTION = f"""\
A safer alternative to 'rm' that moves files and directories to the XDG
Trash directory instead of permanently deleting them. Files can be restored
using your desktop environment's trash manager or manually from:
{TRASH_DIR}
"""

EPILOG = f"""\
EXAMPLES:
    # Interactive mode (default) - prompts for confirmation
    {SCRIPT_NAME} file.txt document.pdf

    # Force mode - no confirmation prompt
    {SCRIPT_NAME} -f unwanted_file.log

    # Verbose mode - shows where files are moved
    {SCRIPT_NAME} -v old_project/

    # Combined flags
    {SCRIPT_NAME} -f -v *.tmp

    # Trash multiple items at once
    {SCRIPT_NAME} file1.txt file2.txt directory/

    # Names starting with a dash need the end-of-options marker
    {SCRIPT_NAME} -- -weird-name.txt

NOTES:
    - Files are moved to: {TRASH_DIR}
    - If a file with the same name already exists in the trash, numbered
      backups are created (e.g. file.txt, file.txt.~1~, file.txt.~2~)
    - The trash directory itself cannot be trashed
    - Non-existent files are skipped with a warning

SEE ALSO:
    rm(1), mv(1), trash-cli, XDG Base Directory Specification
"""

BACKUP_SUFFIX = re.compile(r"\.~(\d+)~$")


class ArgumentParser(argparse.ArgumentParser):
    """ArgumentParser that exits with status 1 on usage errors.

    argparse exits with 2 by default; the shell version this replaces used 1.
    """

    def error(self, message: str) -> NoReturn:
        self.print_usage(sys.stderr)
        print(f"{self.prog}: error: {message}", file=sys.stderr)
        raise SystemExit(1)


def print_message(color: str, message: str) -> None:
    """Print a colored message to stdout."""
    print(f"{color}{message}{COLOR_RESET}")


def print_error(message: str) -> None:
    """Print a colored error message to stderr."""
    print(f"{COLOR_RED}{message}{COLOR_RESET}", file=sys.stderr)


def next_backup_path(destination: Path) -> Path:
    """Return the next free ``name.~N~`` path next to ``destination``."""
    highest = 0
    prefix = destination.name + ".~"
    try:
        entries = list(destination.parent.iterdir())
    except OSError:
        entries = []
    for entry in entries:
        if not entry.name.startswith(prefix):
            continue
        match = BACKUP_SUFFIX.search(entry.name[len(destination.name) :])
        if match:
            highest = max(highest, int(match.group(1)))
    return destination.parent / f"{destination.name}.~{highest + 1}~"


def write_trashinfo(original: Path, destination: Path) -> None:
    """Write the XDG .trashinfo companion so desktop trash managers can restore.

    The move has already succeeded by the time this runs; a failure here only
    costs restore-tooling support, never the user's data, so every error is
    reported and swallowed.
    """
    try:
        TRASH_INFO_DIR.mkdir(parents=True, exist_ok=True)
        info_path = TRASH_INFO_DIR / f"{destination.name}.trashinfo"
        suffix = 0
        while info_path.exists():
            suffix += 1
            info_path = TRASH_INFO_DIR / f"{destination.name}.~{suffix}~.trashinfo"
        escaped = quote(str(original), safe="/")
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        info_path.write_text(
            "[Trash Info]\n" f"Path={escaped}\n" f"DeletionDate={stamp}\n",
            encoding="utf-8",
        )
    except OSError as exc:
        print_error(
            f"Warning: could not write .trashinfo for '{destination.name}': {exc}"
        )


def move_to_trash(item: Path, verbose: bool) -> bool:
    """Move a single item into the trash, backing up any existing entry."""
    destination = TRASH_DIR / item.name

    # Resolve BEFORE the move: afterwards the original path no longer exists
    # and the .trashinfo Path= field would record the wrong location.
    try:
        original = item.resolve()
    except OSError:
        original = item.absolute()

    try:
        if destination.exists() or destination.is_symlink():
            backup = next_backup_path(destination)
            destination.rename(backup)
            if verbose:
                print(f"backed up '{destination}' -> '{backup}'")
        shutil.move(str(item), str(destination))
    except (OSError, shutil.Error) as exc:
        print_error(f"Error: Failed to move '{item}': {exc}")
        return False

    write_trashinfo(original, destination)

    if verbose:
        print(f"moved '{item}' -> '{destination}'")
    return True


def confirm(prompt: str) -> bool:
    """Ask a y/N question; anything but y/Y means no."""
    try:
        reply = input(prompt)
    except EOFError:
        print()
        return False
    return reply.strip().lower() in ("y", "yes")


def build_parser() -> argparse.ArgumentParser:
    parser = ArgumentParser(
        prog=SCRIPT_NAME,
        usage=f"{SCRIPT_NAME} [OPTIONS] <file1> [file2 ...]",
        description=f"{SCRIPT_NAME} - Safe Removal Tool (Version {VERSION})\n\n"
        + DESCRIPTION,
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "paths",
        nargs="*",
        metavar="FILE",
        help="one or more files or directories to move to trash",
    )
    parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="skip confirmation prompt (non-interactive mode)",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="show detailed output of operations",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"{SCRIPT_NAME} version {VERSION}",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.paths:
        print_error("Error: No files or directories specified")
        print(f"Usage: {SCRIPT_NAME} [OPTIONS] <file1> [file2 ...]")
        print(f"Try '{SCRIPT_NAME} --help' for more information.")
        return 1

    try:
        TRASH_DIR.mkdir(parents=True, exist_ok=True)
        TRASH_INFO_DIR.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        print_error(f"Error: Cannot create trash directory: {exc}")
        return 1

    if args.verbose:
        print(f"Trash directory: {TRASH_DIR}")

    try:
        trash_realpath = TRASH_DIR.resolve(strict=True)
    except OSError as exc:
        print_error(f"Error: Cannot resolve trash directory: {exc}")
        return 1

    valid_targets: list[Path] = []
    for raw in args.paths:
        item = Path(raw)

        # '.', '..' and '/' have no usable base name; mv refuses these too,
        # and attempting the move would copy before failing.
        if item.name in ("", ".", ".."):
            print_message(
                COLOR_YELLOW,
                f"Warning: Refusing to trash '{raw}': please name the item "
                "explicitly, skipping",
            )
            continue

        # Path.exists() follows symlinks; a broken symlink must still be trashed.
        if not item.exists() and not item.is_symlink():
            print_message(COLOR_YELLOW, f"Warning: '{raw}' does not exist, skipping")
            continue

        try:
            item_realpath = item.resolve()
        except OSError as exc:
            print_message(COLOR_YELLOW, f"Warning: cannot resolve '{raw}': {exc}")
            continue

        if item_realpath == trash_realpath:
            print_message(
                COLOR_YELLOW,
                "Warning: Cannot trash the trash directory itself, skipping",
            )
            continue

        if item_realpath in trash_realpath.parents:
            print_message(
                COLOR_YELLOW,
                f"Warning: Cannot trash '{raw}': it contains the trash "
                "directory, skipping",
            )
            continue

        valid_targets.append(item)

    if not valid_targets:
        print_message(COLOR_YELLOW, "No valid items to trash")
        return 0

    print("Moving to trash:")
    for item in valid_targets:
        print(f"  - {item.name}")

    if not args.force and not confirm("Continue? [y/N]: "):
        print_message(COLOR_YELLOW, "Operation cancelled")
        return 0

    move_count = sum(move_to_trash(item, args.verbose) for item in valid_targets)

    if move_count > 0:
        print_message(
            COLOR_GREEN, f"✓ Successfully moved {move_count} item(s) to trash"
        )
        return 0

    print_error("✗ Failed to move any items")
    return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print()
        sys.exit(130)
