"""fkill - Fuzzy Process Killer.

Python 3.13 port of the original ``fkill`` bash script.

A safe, interactive process termination tool using fzf.
Default behavior uses SIGTERM (graceful shutdown).
"""

import argparse
import os
import re
import shutil
import signal
import subprocess
import sys
from pathlib import Path
from typing import NoReturn

SCRIPT_NAME: str = Path(sys.argv[0]).name or "fkill"
VERSION: str = "2.0.0"

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_KILL_FAILED = 2

# The shell version validates the extracted PID with ^[0-9]+$.
PID_PATTERN = re.compile(r"[0-9]+")

EPILOG = f"""\
DEPENDENCIES:
    Required: fzf, ps

    Install fzf: https://github.com/junegunn/fzf

EXAMPLES:
    # Normal usage - graceful kill with SIGTERM
    {SCRIPT_NAME}

    # Pre-filter for Chrome processes
    {SCRIPT_NAME} chrome

    # Force kill (SIGKILL) mode
    {SCRIPT_NAME} --force
    {SCRIPT_NAME} -f node

    # Get help
    {SCRIPT_NAME} --help

EXIT CODES:
    0    Success or user cancelled
    1    Error (missing dependencies, invalid arguments)
    2    Process kill failed

SIGNALS:
    SIGTERM (15)  Default - Allows graceful shutdown with cleanup
                  Process can save data, close files, release resources

    SIGKILL (9)   Force mode - Immediate termination, no cleanup
                  Cannot be caught or ignored by the process
                  May cause data corruption, orphaned processes, or
                  unclosed sockets. Use only as last resort.

NOTES:
    - The script excludes itself from the selection list
    - Pressing ESC or Ctrl-C in fzf will safely cancel the operation
    - Using SIGTERM is strongly recommended; use --force only for
      unresponsive processes
"""


class ArgumentParser(argparse.ArgumentParser):
    """ArgumentParser that exits with status 1 on usage errors.

    argparse exits with 2 by default; the shell version this replaces used 1.
    """

    def error(self, message: str) -> NoReturn:
        self.print_usage(sys.stderr)
        print(f"{self.prog}: error: {message}", file=sys.stderr)
        raise SystemExit(1)


def error_exit(message: str, code: int = EXIT_ERROR) -> NoReturn:
    """Print an error message to stderr and exit with the given code."""
    print(f"Error: {message}", file=sys.stderr)
    raise SystemExit(code)


def check_dependencies() -> None:
    """Verify that the external tools used by this script are available."""
    missing = [tool for tool in ("fzf", "ps") if shutil.which(tool) is None]
    if missing:
        error_exit(f"Missing required dependencies: {' '.join(missing)}", EXIT_ERROR)


def get_process_list(process_filter: str) -> tuple[list[str], dict[str, str]]:
    """Return formatted ``ps`` lines plus a mapping of PID to command name.

    Mirrors ``ps -eo pid=,user=,pcpu=,pmem=,comm= | grep -vE ... | awk ...``:
    the awk-style formatting and the case-insensitive filter are done in Python.
    """
    try:
        result = subprocess.run(
            ["ps", "-eo", "pid=,user=,pcpu=,pmem=,comm="],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            check=False,
        )
    except OSError as exc:
        error_exit(f"failed to run ps: {exc}", EXIT_ERROR)

    if result.returncode != 0:
        error_exit("ps failed to list processes", EXIT_ERROR)

    # Exclude this script itself from the list. The fallback guards against an
    # empty alternation, which would match every line and hide all processes.
    names_to_hide = {SCRIPT_NAME, Path(SCRIPT_NAME).stem} - {""}
    exclude = re.compile(
        "|".join(re.escape(name) for name in sorted(names_to_hide)) or r"(?!)"
    )

    # Only this process is hidden. The parent shell is deliberately left in the
    # list: the shell version shows it too, and hiding it would remove a
    # legitimate target.
    own_pid = str(os.getpid())

    lines: list[str] = []
    names: dict[str, str] = {}

    for raw in result.stdout.splitlines():
        if not raw.strip() or exclude.search(raw):
            continue
        fields = raw.split(maxsplit=4)
        if len(fields) < 5:
            continue
        pid, user, pcpu, pmem, comm = fields
        if pid == own_pid:
            continue
        if process_filter:
            formatted_probe = f"{pid} {user} {pcpu} {pmem} {comm}"
            if process_filter.lower() not in formatted_probe.lower():
                continue
        lines.append(f"{pid:>6}  {user:<12}  {pcpu:>5}%  {pmem:>5}%  {comm}")
        names[pid] = comm

    return lines, names


def select_process(lines: list[str], process_filter: str) -> str:
    """Run fzf over the process list and return the selected line (or "")."""
    fzf_command = [
        "fzf",
        "--height=40%",
        "--layout=reverse",
        "--no-multi",
        "--header=PID    USER          CPU    MEM   COMMAND",
        "--header-lines=0",
        "--prompt=Select process to kill > ",
        f"--query={process_filter}",
        "--preview=ps -p {1} -o pid,ppid,user,%cpu,%mem,etime,cmd",
        "--preview-window=down:3:wrap",
    ]

    try:
        result = subprocess.run(
            fzf_command,
            input="\n".join(lines) + ("\n" if lines else ""),
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            check=False,
        )
    except OSError as exc:
        error_exit(f"failed to run fzf: {exc}", EXIT_ERROR)

    # Non-zero status means "no match" (1) or "cancelled" (130): nothing selected.
    if result.returncode != 0:
        return ""
    return result.stdout.strip("\n")


def confirm(prompt: str) -> bool:
    """Ask a y/N question; anything but y/Y means no."""
    try:
        reply = input(prompt)
    except EOFError:
        print()
        return False
    return reply.strip().lower() in ("y", "yes")


def kill_process(pid: int, process_name: str, signal_name: str, signum: int) -> int:
    """Confirm and then send the configured signal to ``pid``."""
    if signal_name == "KILL":
        print("⚠️  WARNING: Using SIGKILL (-9) - no graceful shutdown!")

    if not confirm(f"Kill PID {pid} ({process_name}) with SIG{signal_name}? [y/N] "):
        print("✗ Cancelled.")
        return EXIT_OK

    try:
        os.kill(pid, signum)
    except ProcessLookupError:
        error_exit(f"Process {pid} no longer exists", EXIT_KILL_FAILED)
    except PermissionError:
        error_exit(
            f"Failed to kill process {pid}. May require elevated privileges.",
            EXIT_KILL_FAILED,
        )
    except OSError as exc:
        error_exit(f"Failed to kill process {pid}: {exc}", EXIT_KILL_FAILED)

    print(f"✓ Process {pid} killed with SIG{signal_name}.")
    return EXIT_OK


def process_exists(pid: int) -> bool:
    """Return True if a process with this PID exists (even if not ours)."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def build_parser() -> argparse.ArgumentParser:
    parser = ArgumentParser(
        prog=SCRIPT_NAME,
        usage=f"{SCRIPT_NAME} [OPTIONS] [FILTER]",
        description=(
            f"fkill v{VERSION} - Fuzzy Process Killer\n\n"
            "Interactive process termination tool using fzf for fuzzy selection.\n"
            "Defaults to SIGTERM for graceful shutdown. Supports optional\n"
            "pre-filtering and force-kill mode."
        ),
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "filter",
        nargs="?",
        default="",
        metavar="FILTER",
        help=(
            "optional process name used to pre-filter the list and "
            "pre-populate the fzf query (e.g. 'chrome', 'node')"
        ),
    )
    parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="use SIGKILL (-9) instead of SIGTERM (-15); prevents graceful "
        "shutdown and may cause data loss or corruption",
    )
    parser.add_argument(
        "-v",
        "--version",
        action="version",
        version=f"{SCRIPT_NAME} version {VERSION}",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    check_dependencies()

    signal_name = "KILL" if args.force else "TERM"
    signum = int(signal.SIGKILL if args.force else signal.SIGTERM)

    lines, names = get_process_list(args.filter)
    if not lines:
        print("✗ No matching processes found.")
        return EXIT_OK

    selected = select_process(lines, args.filter)
    if not selected:
        print("✗ No process selected.")
        return EXIT_OK

    fields = selected.split()
    pid_text = fields[0] if fields else ""
    if not PID_PATTERN.fullmatch(pid_text):
        error_exit(f"Invalid PID extracted: {pid_text}", EXIT_ERROR)

    pid = int(pid_text)
    process_name = names.get(pid_text, fields[-1] if fields else "unknown")

    if not process_exists(pid):
        error_exit(f"Process {pid} no longer exists", EXIT_ERROR)

    return kill_process(pid, process_name, signal_name, signum)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print()
        sys.exit(130)
