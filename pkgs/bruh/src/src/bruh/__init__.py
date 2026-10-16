"""Bash-compatible argument forwarding for the bruh command."""

from __future__ import annotations

import os
import sys


def main(argv: list[str] | None = None) -> int | None:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] == "moment":
        args.insert(0, "rollback")
    command = ["brh", *args]
    try:
        os.execvp("brh", command)
    except FileNotFoundError as error:
        print(f"bruh: {error}", file=sys.stderr)
        return 127
    except OSError as error:
        print(f"bruh: {error}", file=sys.stderr)
        return 126
    return None
