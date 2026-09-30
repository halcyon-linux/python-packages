"""se - Search & Edit.

Python 3.13 port of the original ``se`` bash script.

A fast fuzzy search-and-edit tool that combines ripgrep, fzf and bat: search
for a pattern across files, preview the hits with syntax highlighting, and open
the selection in your editor at the exact line.

Arguments are parsed the same way the shell version parses them, so patterns
that start with a dash are still passed through to ripgrep unchanged.
"""

import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from typing import NoReturn

PROG: str = Path(sys.argv[0]).name or "se"
REQUIRED_TOOLS: tuple[str, ...] = ("rg", "fzf", "bat")
DEFAULT_EDITOR: str = "nvim"

HELP_TEXT = f"""\
se - Search & Edit

DESCRIPTION:
    A fast fuzzy search-and-edit tool that combines ripgrep, fzf, and bat.
    Search for a pattern across files, preview results with syntax highlighting,
    and open the selected file in your editor at the exact line.

USAGE:
    {PROG} <pattern> [directory]
    {PROG} -h | --help

ARGUMENTS:
    pattern       The search pattern (required)
    directory     Optional directory to search (defaults to current directory)

OPTIONS:
    -h, --help    Show this help message

DEPENDENCIES:
    Required tools (must be installed):
    - ripgrep (rg)  : Fast recursive search
    - fzf           : Fuzzy finder with preview
    - bat           : Syntax highlighting for preview

ENVIRONMENT:
    EDITOR        Editor to use (defaults to nvim if not set)

EXAMPLES:
    # Search for 'function' in current directory
    {PROG} function

    # Search for 'TODO' in a specific directory
    {PROG} TODO src/

    # Search with regex pattern
    {PROG} 'class \\w+Controller'

NOTES:
    - Press ESC or Ctrl+C to cancel the selection
    - The script handles filenames with special characters safely
    - Syntax highlighting is automatically detected by file extension
"""


def exit_status(returncode: int) -> int:
    """Translate a subprocess return code into a shell-style exit status."""
    return 128 - returncode if returncode < 0 else returncode


def die(message: str, code: int = 1) -> NoReturn:
    """Print an error message to stderr and exit."""
    print(f"Error: {message}", file=sys.stderr)
    raise SystemExit(code)


def check_dependencies(tools: tuple[str, ...]) -> None:
    """Exit with a clear message if any required tool is missing."""
    missing = [tool for tool in tools if shutil.which(tool) is None]
    if missing:
        die(
            f"missing required dependencies: {', '.join(missing)}\n"
            f"Run '{PROG} --help' for more information."
        )


def editor_command() -> list[str]:
    """Return the editor command line taken from $EDITOR (default: nvim)."""
    raw = os.environ.get("EDITOR") or DEFAULT_EDITOR
    try:
        command = shlex.split(raw)
    except ValueError as exc:
        die(f"could not parse $EDITOR ({raw!r}): {exc}")
    if not command:
        command = [DEFAULT_EDITOR]
    if shutil.which(command[0]) is None:
        die(f"editor not found in PATH: {command[0]}")
    return command


def fuzzy_select(producer: list[str], fzf: list[str]) -> str:
    """Run ``producer | fzf`` and return the selected line (empty if cancelled)."""
    try:
        source = subprocess.Popen(
            producer, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL
        )
    except OSError as exc:
        die(f"failed to run {producer[0]}: {exc}")

    with source:
        try:
            result = subprocess.run(
                fzf, stdin=source.stdout, stdout=subprocess.PIPE, text=True
            )
        except OSError as exc:
            source.kill()
            die(f"failed to run {fzf[0]}: {exc}")

    if result.returncode != 0:
        return ""
    return result.stdout.strip("\n")


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)

    if not args:
        print(HELP_TEXT, end="")
        return 1

    if args[0] in ("-h", "--help"):
        print(HELP_TEXT, end="")
        return 0

    pattern = args[0]
    search_dir = args[1] if len(args) > 1 else "."

    check_dependencies(REQUIRED_TOOLS)

    # A tab is used as the field separator so filenames containing colons are
    # still parsed correctly. Format: filename<TAB>line<TAB>content
    rg_command = [
        "rg",
        "--line-number",
        "--no-heading",
        "--smart-case",
        "--field-match-separator=\t",
        pattern,
        search_dir,
    ]
    fzf_command = [
        "fzf",
        "--height",
        "80%",
        "--layout",
        "reverse",
        "--info",
        "inline",
        "--border",
        "rounded",
        "--delimiter",
        "\t",
        "--no-multi",
        "--preview",
        "bat --style=numbers --color=always --highlight-line {2} {1}",
        "--preview-window",
        "up,60%,border-bottom,+{2}+3/3,~3",
        "--prompt",
        "Search Results > ",
    ]

    selection = fuzzy_select(rg_command, fzf_command)

    # Exit cleanly if the user cancelled fzf (no selection made).
    if not selection:
        return 0

    fields = selection.split("\t")
    if len(fields) < 2 or not fields[1].isdigit():
        die(f"could not parse the selected match: {selection!r}")

    file_path, line = fields[0], fields[1]

    command = [*editor_command(), f"+{line}", file_path]
    try:
        return exit_status(subprocess.run(command).returncode)
    except OSError as exc:
        die(f"failed to run {command[0]}: {exc}")


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
