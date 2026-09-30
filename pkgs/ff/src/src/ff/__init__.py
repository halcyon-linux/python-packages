"""ff - Fast File Finder.

Python 3.13 port of the original ``ff`` bash script: a wrapper around fd
(preferred) with an automatic fallback to find, offering a consistent
interface across both backends.

Arguments are parsed with a hand-written loop that mirrors the shell version,
because option values may legitimately start with a dash (for example
``-s -1M``), which a generic option parser would reject.
"""

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

SCRIPT_NAME: str = Path(sys.argv[0]).name or "ff"
SCRIPT_VERSION: str = "2.0"

# Colors are only emitted when stdout is a terminal.
if sys.stdout.isatty():
    RED = "\033[0;31m"
    GREEN = "\033[0;32m"
    YELLOW = "\033[1;33m"
    BLUE = "\033[0;34m"
    CYAN = "\033[0;36m"
    NC = "\033[0m"
else:
    RED = GREEN = YELLOW = BLUE = CYAN = NC = ""


def exit_status(returncode: int) -> int:
    """Translate a subprocess return code into a shell-style exit status."""
    return 128 - returncode if returncode < 0 else returncode


def print_error(message: str) -> None:
    print(f"{RED}Error: {message}{NC}", file=sys.stderr)


def print_info(message: str) -> None:
    print(f"{BLUE}→ {message}{NC}")


def print_warning(message: str) -> None:
    print(f"{YELLOW}Warning: {message}{NC}", file=sys.stderr)


def usage() -> None:
    print(f"""\
{CYAN}Fast File Finder (ff){NC} - Version {SCRIPT_VERSION}

{CYAN}DESCRIPTION{NC}
    A user-friendly wrapper around fd (preferred) with automatic fallback to find.
    Provides a consistent interface for file searching across both tools.

{CYAN}SYNOPSIS{NC}
    {SCRIPT_NAME} [OPTIONS] <pattern> [directory]

{CYAN}ARGUMENTS{NC}
    <pattern>       Search pattern to match against filenames
                    - With fd: treated as regex by default (use --glob for glob mode)
                    - With find: treated as glob pattern (use * wildcards explicitly)

    [directory]     Root directory for search (default: current directory)
                    Must be a valid, existing directory

{CYAN}OPTIONS{NC}
    -t, --type TYPE
        Filter by entry type:
            f  = regular file
            d  = directory
            l  = symlink (symbolic link)
            x  = executable (fd only)

    -e, --extension EXT
        Filter by file extension (e.g., txt, sh, pdf)
        Examples: -e txt  or  --extension pdf

    -i, --ignore-case
        Perform case-insensitive pattern matching
        Note: fd uses "smart case" by default (case-insensitive unless pattern
              contains uppercase letters)

    -H, --hidden
        Include hidden files and directories in search results
        Note: fd ignores hidden entries by default; find includes them by default
              This option normalizes behavior between both tools

    -d, --max-depth NUM
        Limit directory traversal to maximum depth NUM
        Example: -d 2 searches only 2 levels deep

    -s, --size SIZE
        Filter by file size. Format: [+|-]NUMBER[UNIT]
        Units: b (bytes), k (kilobytes), M (megabytes), G (gigabytes)
        Examples:
            +100k   files larger than 100KB
            -1M     files smaller than 1MB
            500k    files exactly 500KB (find only)

    -x, --exec COMMAND
        Execute COMMAND for each matched file
        Use {{}} as placeholder for the filename in COMMAND
        Example: -x 'echo "Found: {{}}"'
        Security: Filenames are safely passed as arguments to prevent injection

    -c, --count
        Display only the count of matching entries (no filenames)

    -0, --print0
        Use null character (\\0) as output delimiter instead of newline
        Useful for piping to xargs -0 to handle filenames with special characters

    -g, --glob
        Treat pattern as glob instead of regex (fd only)
        With find, glob is always used

    -h, --help
        Display this help message and exit

    -v, --version
        Display version information and exit

{CYAN}BACKEND DETECTION{NC}
    This script automatically detects which tool is available:
    • Preferred: {GREEN}fd{NC} (faster, user-friendly, respects .gitignore)
    • Fallback: {YELLOW}find{NC} (universal, available on all Unix systems)

    The script ensures consistent behavior regardless of which backend is used.

{CYAN}DEFAULT BEHAVIOR{NC}
    • Both backends hide hidden files/directories by default (use -H to show)
    • Pattern matching:
      - fd: regex by default (more powerful but requires escaping metacharacters)
      - find: glob by default (traditional shell wildcards like *.txt)
    • Paths matching .gitignore patterns are ignored (fd only, naturally)

{CYAN}EXAMPLES{NC}
    Basic search for files containing "readme":
        {SCRIPT_NAME} readme

    Find all shell scripts in /usr/local/bin:
        {SCRIPT_NAME} -e sh /usr/local/bin

    Case-insensitive search for "config":
        {SCRIPT_NAME} -i config

    Find directories named "test" (max depth 3):
        {SCRIPT_NAME} -t d -d 3 test

    Find files larger than 100MB:
        {SCRIPT_NAME} -s +100M /var/log

    Execute command on each result:
        {SCRIPT_NAME} -t f -e log -x 'wc -l {{}}' /var/log

    Count all Python files:
        {SCRIPT_NAME} -e py -c ~/projects

    Find with null-separated output (safe for xargs):
        {SCRIPT_NAME} -e txt -0 | xargs -0 grep "pattern"

    Find hidden config files:
        {SCRIPT_NAME} -H -e conf ~/.config

    Using glob pattern with fd:
        {SCRIPT_NAME} -g '*.txt' /documents

{CYAN}NOTES{NC}
    • When using -x/--exec, always quote commands with spaces or special chars
    • The {{}} placeholder in -x commands is expanded by the backend itself
    • For complex filtering, consider using fd directly for more advanced options
    • Pattern syntax differs: fd uses regex, find uses globs (unless -g is used)

{CYAN}SEE ALSO{NC}
    fd(1), find(1), grep(1), xargs(1)
""")


def version() -> None:
    print(f"{SCRIPT_NAME} version {SCRIPT_VERSION}")
    print()
    if shutil.which("fd") is not None:
        print(f"Backend: {GREEN}fd{NC} (fast mode)")
        try:
            result = subprocess.run(
                ["fd", "--version"], capture_output=True, text=True, check=False
            )
        except OSError:
            result = None
        if result is not None and result.returncode == 0 and result.stdout.strip():
            print(result.stdout.strip())
        else:
            print("  fd is available")
    else:
        print(f"Backend: {YELLOW}find{NC} (fallback mode)")
        try:
            result = subprocess.run(
                ["find", "--version"], capture_output=True, text=True, check=False
            )
        except OSError:
            result = None
        if result is not None and result.returncode == 0 and result.stdout.strip():
            print(result.stdout.splitlines()[0])
        else:
            print("  find (standard Unix version)")


@dataclass(slots=True)
class Options:
    """Parsed command line options."""

    pattern: str = ""
    directory: str = "."
    file_type: str = ""
    extension: str = ""
    ignore_case: bool = False
    include_hidden: bool = False  # Matches fd's default of hiding hidden entries.
    max_depth: str = ""
    size_filter: str = ""
    exec_cmd: str = ""
    count_only: bool = False
    print_null: bool = False
    use_glob: bool = False


def run_backend(command: list[str], count_only: bool) -> int:
    """Run the backend command, mirroring ``cmd 2>/dev/null`` (and ``| wc -l``)."""
    try:
        if count_only:
            result = subprocess.run(
                command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=False
            )
            # ``wc -l`` counts newlines; --print0 output therefore counts as 0.
            print(result.stdout.count(b"\n"))
        else:
            result = subprocess.run(command, stderr=subprocess.DEVNULL, check=False)
    except OSError as exc:
        print_error(f"failed to run {command[0]}: {exc}")
        return 1
    return exit_status(result.returncode)


def search_with_fd(opts: Options) -> int:
    """Build and run the fd command line (argument order matches the original)."""
    args: list[str] = ["fd", opts.pattern, opts.directory]

    if opts.file_type:
        args += ["--type", opts.file_type]
    if opts.extension:
        args += ["--extension", opts.extension]
    if opts.ignore_case:
        args.append("--ignore-case")
    # fd hides hidden entries by default, so the flag is only added when asked for.
    if opts.include_hidden:
        args.append("--hidden")
    if opts.max_depth:
        args += ["--max-depth", opts.max_depth]
    if opts.size_filter:
        args += ["--size", opts.size_filter]
    if opts.use_glob:
        args.append("--glob")
    if opts.exec_cmd:
        # fd expands {} inside the command and passes the file name safely.
        args += ["--exec", "sh", "-c", opts.exec_cmd, "sh"]
    if opts.print_null:
        args.append("--print0")

    return run_backend(args, opts.count_only)


def search_with_find(opts: Options) -> int:
    """Build and run the find command line (argument order matches the original)."""
    args: list[str] = ["find", opts.directory]

    # Depth options must come early in a find command line.
    if not opts.include_hidden:
        # -mindepth 1 keeps the prune below from matching the starting
        # directory itself: `find . -name ".*" -prune` otherwise prunes "."
        # (and any start directory whose name begins with a dot), which would
        # silently return no results at all.
        args.append("-mindepth")
        args.append("1")
    if opts.max_depth:
        args += ["-maxdepth", opts.max_depth]

    # Normalize behavior with fd: exclude hidden entries unless asked for.
    if not opts.include_hidden:
        args += ["(", "-name", ".*", "-prune", ")", "-o"]

    if opts.file_type:
        if opts.file_type == "x":
            args += ["(", "-type", "f", "-executable", ")"]
        else:
            args += ["(", "-type", opts.file_type, ")"]
    else:
        args += ["(", "-type", "f", "-o", "-type", "d", "-o", "-type", "l", ")"]

    name_flag = "-iname" if opts.ignore_case else "-name"
    if opts.extension:
        args += [name_flag, f"*.{opts.extension}"]
    else:
        args += [name_flag, opts.pattern]

    if opts.size_filter:
        args += ["-size", opts.size_filter]

    if opts.exec_cmd:
        # Safe exec: the file name is passed as "$1" to sh -c, never interpolated.
        args += ["-exec", "sh", "-c", opts.exec_cmd, "sh", "{}", ";"]
    elif opts.print_null:
        args.append("-print0")
    else:
        args.append("-print")

    return run_backend(args, opts.count_only)


def parse_args(argv: list[str]) -> Options:
    """Parse arguments exactly like the shell version's while/case loop."""
    opts = Options()
    positionals: list[str] = []
    index = 0

    def require_value(flag: str, position: int) -> str:
        if position + 1 >= len(argv):
            print_error(f"Option {flag} requires an argument")
            raise SystemExit(1)
        return argv[position + 1]

    while index < len(argv):
        arg = argv[index]
        match arg:
            case "-h" | "--help":
                usage()
                raise SystemExit(0)
            case "-v" | "--version":
                version()
                raise SystemExit(0)
            case "-t" | "--type":
                opts.file_type = require_value(arg, index)
                index += 2
            case "-e" | "--extension":
                opts.extension = require_value(arg, index)
                index += 2
            case "-i" | "--ignore-case":
                opts.ignore_case = True
                index += 1
            case "-H" | "--hidden":
                opts.include_hidden = True
                index += 1
            case "-d" | "--max-depth":
                opts.max_depth = require_value(arg, index)
                index += 2
            case "-s" | "--size":
                opts.size_filter = require_value(arg, index)
                index += 2
            case "-x" | "--exec":
                opts.exec_cmd = require_value(arg, index)
                index += 2
            case "-c" | "--count":
                opts.count_only = True
                index += 1
            case "-0" | "--print0":
                opts.print_null = True
                index += 1
            case "-g" | "--glob":
                opts.use_glob = True
                index += 1
            case "--":
                index += 1
                break
            case _ if arg.startswith("-"):
                print_error(f"Unknown option: {arg}")
                print("Use -h or --help for usage information")
                raise SystemExit(1)
            case _:
                positionals.append(arg)
                index += 1

    # Everything after "--" is positional.
    positionals.extend(argv[index:])

    if positionals:
        opts.pattern = positionals[0]
    if len(positionals) > 1:
        # Like the original, later positionals overwrite the directory.
        opts.directory = positionals[-1]

    return opts


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)

    if not args:
        usage()
        return 0

    opts = parse_args(args)

    if not opts.pattern:
        print_error("Missing required argument: pattern")
        print("Use -h or --help for usage information")
        return 1

    if not Path(opts.directory).is_dir():
        print_error(f"Directory not found: {opts.directory}")
        return 1

    if shutil.which("fd") is not None:
        return search_with_fd(opts)

    if shutil.which("find") is None:
        print_error("Neither 'fd' nor 'find' is available in PATH")
        return 1

    if opts.use_glob:
        print_warning("The --glob flag is fd-specific and has no effect with find")
    return search_with_find(opts)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
    except BrokenPipeError:
        # e.g. `ff pattern | head`. Redirect stdout to devnull so Python's
        # shutdown flush cannot raise a second BrokenPipeError, then report
        # the usual shell status for a SIGPIPE death.
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, sys.stdout.fileno())
        sys.exit(141)
