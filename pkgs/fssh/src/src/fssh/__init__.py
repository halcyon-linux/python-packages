"""fssh - Fuzzy SSH Launcher.

Python 3.13 port of the original ``fssh`` bash script.

Interactive SSH host selection using fzf over the Host entries of
``~/.ssh/config``.

Arguments are parsed the same way the shell version parses them: the first
argument is either ``-h``/``--help`` or the initial fzf query.
"""

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import NoReturn

PROG: str = Path(sys.argv[0]).name or "fssh"
SSH_CONFIG: Path = Path.home() / ".ssh" / "config"

# Matches the awk program of the original: lines that start with "Host " and
# that contain no wildcard character.
HOST_LINE = re.compile(r"^Host ")

HELP_TEXT = f"""\
Fuzzy SSH Launcher

DESCRIPTION
    An interactive SSH host selector that uses fzf to provide fuzzy searching
    through hosts defined in your ~/.ssh/config file. Launch SSH sessions with
    ease by filtering through your configured hosts.

USAGE
    {PROG} [query]

ARGUMENTS
    query       Optional initial search query for fzf filtering.
                If provided, fzf will start with this text in the search box,
                allowing you to quickly narrow down host matches.

                Examples:
                    {PROG} prod    # Start with "prod" in the search box
                    {PROG} web     # Start with "web" in the search box
                    {PROG}         # Start with empty search box

FLAGS/OPTIONS
    -h, --help  Display this help message and exit.

DEPENDENCIES
    This script requires the following tools to be installed:

    - fzf             Fuzzy finder for interactive selection
    - openssh-client  SSH client (provides the ssh command)

    The preview window additionally uses grep and column, which are part of
    any standard base system.

CONFIGURATION
    The script reads host definitions from ~/.ssh/config. Ensure this file
    exists and contains Host entries. Example config:

        Host webserver web
            HostName 192.168.1.100
            User admin

        Host database db prod-db
            HostName db.example.com
            User dbadmin
            Port 2222

    Note: Host entries with wildcards (e.g., Host *) are automatically excluded.

EXAMPLES
    # Launch with empty search, browse all hosts
    {PROG}

    # Start searching for hosts containing "prod"
    {PROG} prod

    # Quickly filter to staging hosts
    {PROG} staging

    # Search for database hosts
    {PROG} db

NOTES
    - Multiple aliases per Host line are fully supported
    - Wildcard hosts (Host *) are automatically filtered out
    - The script replaces itself with SSH, avoiding lingering processes
    - Press Ctrl+C in fzf to cancel without connecting
"""


def die(message: str, hint: str | None = None, code: int = 1) -> NoReturn:
    """Print an error (plus optional hint) to stderr and exit."""
    print(f"Error: {message}", file=sys.stderr)
    if hint:
        print(hint, file=sys.stderr)
    raise SystemExit(code)


def read_hosts(config: Path) -> list[str]:
    """Return every alias of every non-wildcard ``Host`` line, in file order."""
    try:
        text = config.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        die(f"could not read {config}: {exc}")

    hosts: list[str] = []
    for line in text.splitlines():
        if not HOST_LINE.match(line) or "*" in line:
            continue
        hosts.extend(line.split()[1:])
    return hosts


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)

    if args and args[0] in ("-h", "--help"):
        print(HELP_TEXT, end="")
        return 0

    query = args[0] if args else ""

    if not SSH_CONFIG.is_file():
        die(
            "~/.ssh/config not found",
            "Please create an SSH config file with Host entries.",
        )

    for command in ("fzf", "ssh"):
        if shutil.which(command) is None:
            die(
                f"Required command '{command}' not found",
                f"Please install {command} and try again.",
            )

    hosts = read_hosts(SSH_CONFIG)
    if not hosts:
        die(
            "no usable Host entries found in ~/.ssh/config",
            "Add at least one non-wildcard 'Host' entry.",
        )

    fzf_command = [
        "fzf",
        "--height",
        "40%",
        "--layout",
        "reverse",
        "--border",
        "rounded",
        "--prompt=SSH to > ",
        "--no-multi",
        f"--query={query}",
        "--preview",
        'ssh -G {} | grep -E "^(hostname|user|port|identityfile)" | column -t',
        "--preview-window",
        "right:40%:wrap",
    ]

    try:
        result = subprocess.run(
            fzf_command,
            input="\n".join(hosts) + "\n",
            stdout=subprocess.PIPE,
            text=True,
            check=False,
        )
    except OSError as exc:
        die(f"failed to run fzf: {exc}")

    if result.returncode != 0:
        # 1 = no match, 130 = cancelled: nothing to connect to.
        return 0

    host = result.stdout.strip()
    if not host:
        return 0

    # Replace this process with ssh so the wrapper does not linger in the
    # process tree during the session.
    try:
        os.execvp("ssh", ["ssh", host])
    except OSError as exc:
        die(f"failed to exec ssh: {exc}")

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
