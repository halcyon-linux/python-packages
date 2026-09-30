"""fconf - fuzzy configuration finder and editor.

Python 3.13 port of the original ``fconf`` bash script.

Searches for files (including hidden ones) in the given directories, previews
them with syntax highlighting and opens the selection in ``$EDITOR``.
"""

import argparse
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from typing import NoReturn

PROG: str = Path(sys.argv[0]).name or "fconf"
REQUIRED_TOOLS: tuple[str, ...] = ("fd", "fzf", "bat")
DEFAULT_EDITOR: str = "nvim"

DESCRIPTION = """\
A fuzzy configuration finder and editor. Searches for hidden files and regular
files in specified directories (or defaults to the current directory and home),
previews them with syntax highlighting, and opens your selection in your
preferred editor.
"""

EPILOG = """\
Arguments:
  PATHS...          Optional directories to search. If provided, only these
                    paths will be searched. If omitted, defaults to the current
                    directory (.) and the home directory ($HOME).

                    Examples:
                      fconf                    # Search . and $HOME
                      fconf /etc               # Search only /etc
                      fconf /etc ~/.config     # Search /etc and ~/.config

Environment Variables:
  EDITOR            The editor to use for opening files (default: nvim).
                    You can override this by setting EDITOR in your shell:
                      export EDITOR=nano
                      export EDITOR=emacs
                      export EDITOR=code

Required Dependencies:
  The following CLI tools must be installed and available in your PATH:

  1. fd    - A simple, fast and user-friendly alternative to 'find'
             Install: https://github.com/sharkdp/fd

  2. fzf   - A command-line fuzzy finder
             Install: https://github.com/junegunn/fzf

  3. bat   - A cat clone with syntax highlighting (used for file previews)
             Install: https://github.com/sharkdp/bat

  If any of these tools are missing, the script exits with an error. Please
  install them using your system's package manager (apt, dnf, brew, pacman...).

Examples:
  # Search current directory and home with default editor (nvim)
  fconf

  # Search only /etc directory
  fconf /etc

  # Search multiple custom directories
  fconf ~/.config /etc/nginx

  # Use a different editor for this session
  EDITOR=nano fconf

  # Use a different editor permanently (add to ~/.bashrc or ~/.zshrc)
  export EDITOR=emacs
  fconf

How It Works:
  1. fd finds all files (including hidden ones) in the search paths
  2. fzf presents an interactive fuzzy finder interface
  3. bat provides syntax-highlighted previews as you navigate
  4. Your selected file opens in nvim (or your configured EDITOR)

Tips:
  - In the fzf interface, just start typing to filter files
  - Use arrow keys or Ctrl-j/k to navigate
  - Press Enter to select and open a file
  - Press Esc or Ctrl-c to cancel without opening anything
  - The preview window shows file contents with syntax highlighting
"""


def exit_status(returncode: int) -> int:
    """Translate a subprocess return code into a shell-style exit status."""
    return 128 - returncode if returncode < 0 else returncode


class ArgumentParser(argparse.ArgumentParser):
    """ArgumentParser that exits with status 1 on usage errors.

    argparse exits with 2 by default; the shell version this replaces used 1.
    """

    def error(self, message: str) -> NoReturn:
        self.print_usage(sys.stderr)
        print(f"{self.prog}: error: {message}", file=sys.stderr)
        raise SystemExit(1)


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
            f"Run '{PROG} --help' for installation instructions."
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
    """Run ``producer | fzf`` and return the selected line (empty if cancelled).

    fzf draws its interface on stderr and reads keys from /dev/tty, so only its
    stdout is captured here. A non-zero fzf exit status (1 = no match,
    130 = interrupted) is treated as "nothing selected", mirroring the shell's
    ``|| true``.
    """
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


def build_parser() -> argparse.ArgumentParser:
    parser = ArgumentParser(
        prog=PROG,
        usage=f"{PROG} [OPTIONS] [PATHS...]",
        description=DESCRIPTION,
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "paths",
        nargs="*",
        metavar="PATHS",
        help="directories to search (default: . and $HOME)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    check_dependencies(REQUIRED_TOOLS)

    search_paths: list[str] = args.paths or [".", str(Path.home())]

    fd_command = ["fd", "--type", "f", "--hidden", ".", *search_paths]
    fzf_command = [
        "fzf",
        "--height=60%",
        "--layout=reverse",
        "--border=rounded",
        "--prompt=Edit Config > ",
        "--no-multi",
        "--preview",
        "bat --style=numbers --color=always {}",
    ]

    selected = fuzzy_select(fd_command, fzf_command)

    if not selected:
        print("No file selected. Exiting.")
        return 0

    print(f"Opening: {selected}")
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
