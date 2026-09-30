"""fe - Fuzzy Edit.

Python 3.13 port of the original ``fe`` bash script.

Interactive file finder and editor using fd, fzf and bat.

Arguments are parsed the same way the shell version parses them: the first
argument is either ``-h``/``--help`` or the (optional) fzf query, so queries
that start with a dash are still handed straight to fzf.
"""

import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from typing import NoReturn

PROG: str = Path(sys.argv[0]).name or "fe"
REQUIRED_TOOLS: tuple[str, ...] = ("fd", "fzf", "bat")
DEFAULT_EDITOR: str = "nvim"

HELP_TEXT = f"""\
fe - Fuzzy Edit

DESCRIPTION
    Interactive file finder and editor that combines fd, fzf, and bat to
    provide a fast, user-friendly way to search and edit files.

USAGE
    {PROG} [OPTIONS] [QUERY]

ARGUMENTS
    QUERY               Optional search query to pre-populate fzf's search.
                        If provided, fzf will start with this query already
                        entered. If there's exactly one match, it will be
                        automatically selected. If there are no matches, the
                        script exits without opening an editor.

OPTIONS
    -h, --help          Display this help message and exit

DEPENDENCIES
    This script requires the following tools to be installed:

    - fd                Fast file finder (https://github.com/sharkdp/fd)
    - fzf               Command-line fuzzy finder (https://github.com/junegunn/fzf)
    - bat               Syntax-highlighted cat clone (https://github.com/sharkdp/bat)
    - nvim              Neovim text editor (default, can be overridden)

ENVIRONMENT VARIABLES
    EDITOR              Text editor to use. Defaults to 'nvim' if not set.
                        Examples: vim, emacs, nano, code

EXAMPLES
    # Open fe with no initial query
    {PROG}

    # Pre-populate search with "config"
    {PROG} config

    # Search for files containing "test"
    {PROG} test

    # Use a different editor for this session
    EDITOR=vim {PROG}

    # Search for README files
    {PROG} README

FEATURES
    - Recursively searches files in the current directory
    - Follows symbolic links
    - Excludes .git directories
    - Shows file previews with syntax highlighting (first 500 lines)
    - Auto-selects if only one match found
    - Exits gracefully if no matches found
    - Supports cancellation with ESC or Ctrl-C

KEY BINDINGS (in fzf)
    Ctrl-K/Up           Move selection up
    Ctrl-J/Down         Move selection down
    Enter               Open selected file in editor
    ESC / Ctrl-C        Cancel and exit
    Ctrl-/              Toggle preview window

EXIT CODES
    0                   Success (file selected and opened, or no match with query)
    1                   Error occurred
    130                 User cancelled (ESC or Ctrl-C)
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

    if args and args[0] in ("-h", "--help"):
        print(HELP_TEXT, end="")
        return 0

    query = args[0] if args else ""

    check_dependencies(REQUIRED_TOOLS)

    fd_command = ["fd", "--type", "f", "--hidden", "--follow", "--exclude", ".git", "."]
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
        "--preview",
        "bat --style=numbers --color=always --line-range :500 {}",
        f"--query={query}",
        "--select-1",
        "--exit-0",
        "--no-multi",
    ]

    selected = fuzzy_select(fd_command, fzf_command)
    if not selected:
        return 0

    command = [*editor_command(), selected]
    try:
        return exit_status(subprocess.run(command).returncode)
    except OSError as exc:
        die(f"failed to run {command[0]}: {exc}")


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
