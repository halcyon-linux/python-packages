"""fp - Fuzzy File Previewer.

Python 3.13 port of the original ``fp`` bash script.

A fast, interactive file/directory browser with preview capabilities using
fd, fzf and bat. The selected path is printed to stdout, which makes the tool
composable with other commands.
"""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path
from typing import NoReturn

SCRIPT_NAME: str = Path(sys.argv[0]).name or "fp"
VERSION: str = "1.0.0"
REQUIRED_TOOLS: tuple[str, ...] = ("fd", "fzf", "bat")

DESCRIPTION = """\
An interactive file and directory browser with live preview.
Uses fd for fast file discovery, fzf for fuzzy selection, and bat for
syntax-highlighted previews. The selected file/directory path is printed
to stdout, making it composable with other commands.
"""

EPILOG = f"""\
ARGUMENTS:
    SEARCH_PATH         Optional directory to search (default: current directory)
                        Examples: /var/log, ~/Documents, .

DEPENDENCIES:
    Required:
        fd      - Fast file finder (https://github.com/sharkdp/fd)
        fzf     - Fuzzy finder (https://github.com/junegunn/fzf)
        bat     - Syntax highlighter (https://github.com/sharkdp/bat)

    Optional (for directory preview):
        ls      - List directory contents (fallback to basic ls)
        tree    - Display directory tree (preferred if available)

EXAMPLES:
    # Browse current directory
    {SCRIPT_NAME}

    # Browse specific directory
    {SCRIPT_NAME} /var/log

    # Open selected file in editor
    vim $({SCRIPT_NAME})

    # Change to selected directory
    cd $({SCRIPT_NAME})

    # Copy selected file
    cp $({SCRIPT_NAME} ~/Documents) /backup/

    # Open in default editor
    ${{EDITOR:-vim}} "$({SCRIPT_NAME})"

EXIT CODES:
    0    Success - file/directory selected
    1    Error - missing dependencies or invalid arguments
    130  Interrupted - user cancelled selection (Ctrl-C or Esc)

NOTES:
    - Hidden files and directories are included in search
    - Follows symbolic links
    - Excludes .git directories by default
    - Preview window shows file contents or directory listings
    - Use arrow keys or type to filter, Enter to select, Esc to cancel
"""


class ArgumentParser(argparse.ArgumentParser):
    """ArgumentParser that exits with status 1 on usage errors.

    argparse exits with 2 by default; the shell version this replaces used 1.
    """

    def error(self, message: str) -> NoReturn:
        self.print_usage(sys.stderr)
        print(f"{self.prog}: error: {message}", file=sys.stderr)
        raise SystemExit(1)


def exit_status(returncode: int) -> int:
    """Translate a subprocess return code into a shell-style exit status."""
    return 128 - returncode if returncode < 0 else returncode


def command_exists(command: str) -> bool:
    """Return True if ``command`` can be found in PATH."""
    return shutil.which(command) is not None


def check_dependencies() -> None:
    """Exit with a helpful message when a required tool is missing."""
    missing = [tool for tool in REQUIRED_TOOLS if not command_exists(tool)]
    if missing:
        print(
            f"Error: Missing required dependencies: {' '.join(missing)}",
            file=sys.stderr,
        )
        print(f"Please install them before running {SCRIPT_NAME}", file=sys.stderr)
        print(f"Run '{SCRIPT_NAME} --help' for more information", file=sys.stderr)
        raise SystemExit(1)


def _ls_supports(flags: list[str]) -> bool:
    """Return True if ``ls`` accepts the given flags on this system."""
    try:
        result = subprocess.run(
            ["ls", *flags, "/"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    except OSError:
        return False
    return result.returncode == 0


def get_ls_command() -> str:
    """Pick the best available directory listing command for previews."""
    # Prefer tree if available for better directory visualization.
    if command_exists("tree"):
        return "tree -C -L 2"

    # GNU ls installed as gls (macOS via coreutils).
    if command_exists("gls"):
        return "gls -lhF --color=always"

    if not command_exists("ls"):
        return "ls -lhF"

    # GNU ls with --color support.
    if _ls_supports(["--color=always"]):
        return "ls -lhF --color=always"

    # BSD ls with -G (macOS/BSD).
    if _ls_supports(["-G"]):
        return "ls -lhFG"

    # Ultimate fallback: plain ls.
    return "ls -lhF"


def build_parser() -> argparse.ArgumentParser:
    parser = ArgumentParser(
        prog=SCRIPT_NAME,
        usage=f"{SCRIPT_NAME} [OPTIONS] [SEARCH_PATH]",
        description=f"{SCRIPT_NAME} v{VERSION} - Fuzzy File Previewer\n\n{DESCRIPTION}",
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "search_path",
        nargs="?",
        default=".",
        metavar="SEARCH_PATH",
        help="directory to search (default: current directory)",
    )
    parser.add_argument(
        "-v",
        "--version",
        action="version",
        version=f"{SCRIPT_NAME} v{VERSION}",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    search_path: str = args.search_path

    if not Path(search_path).is_dir():
        print(f"Error: Directory not found: {search_path}", file=sys.stderr)
        return 1

    check_dependencies()

    ls_cmd = get_ls_command()

    fd_command = [
        "fd",
        "--hidden",
        "--follow",
        "--exclude",
        ".git",
        ".",
        search_path,
    ]
    preview = (
        f"if [ -d {{}} ]; then {ls_cmd} {{}} 2>/dev/null || "
        "echo 'Cannot read directory'; "
        "else bat --style=numbers --color=always {} 2>/dev/null || cat {}; fi"
    )
    fzf_command = [
        "fzf",
        "--height=80%",
        "--layout=reverse",
        "--border=rounded",
        "--preview-window=right:50%:wrap",
        f"--preview={preview}",
    ]

    # fzf renders its UI on the terminal and prints the selection on stdout,
    # so stdout is inherited here: `cd $(fp)` keeps working.
    try:
        source = subprocess.Popen(
            fd_command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL
        )
    except OSError as exc:
        print(f"Error: failed to run fd: {exc}", file=sys.stderr)
        return 1

    with source:
        try:
            result = subprocess.run(fzf_command, stdin=source.stdout, check=False)
        except OSError as exc:
            source.kill()
            print(f"Error: failed to run fzf: {exc}", file=sys.stderr)
            return 1

    return exit_status(result.returncode)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
