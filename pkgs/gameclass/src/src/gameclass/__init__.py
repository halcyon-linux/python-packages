"""Set the WM_CLASS of a launched command's window."""

from __future__ import annotations

import os
import re
import shlex
import subprocess
import sys
import threading
from pathlib import Path
from typing import Sequence


def parse_gameclass(value: str) -> tuple[str, str]:
    fields = value.split("=")
    executable = fields[0] if fields else ""
    window_class = fields[1] if len(fields) > 1 else ""
    if not executable or not window_class:
        raise ValueError("Incorrect environment variable formatting.")
    return executable, window_class


def command_from_args(args: Sequence[str]) -> str:
    return shlex.join(args)


def parse_window_list(output: str) -> list[tuple[str, int]]:
    windows = []
    for line in output.splitlines():
        fields = line.split(None, 3)
        if len(fields) < 3:
            continue
        try:
            windows.append((fields[0], int(fields[2])))
        except ValueError:
            continue
    return windows


def read_cmdline(pid: int) -> str:
    try:
        return Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b"").decode(
            errors="replace"
        )
    except OSError:
        return ""


def run_command(args: Sequence[str], *, capture_output: bool = False):
    return subprocess.run(
        args,
        text=True,
        capture_output=capture_output,
        check=False,
    )


def _style(text: str, code: str) -> str:
    return f"\033[{code}m{text}\033[0m" if sys.stdout.isatty() else text


def watch_windows(executable: str, window_class: str, stop_event: threading.Event) -> None:
    try:
        pattern = re.compile(executable)
    except re.error:
        return

    while not stop_event.wait(1):
        result = run_command(["wmctrl", "-l", "-p"], capture_output=True)
        window_id = None
        for candidate, pid in parse_window_list(result.stdout):
            window_id = None
            if pattern.search(read_cmdline(pid)):
                window_id = candidate
        if not window_id:
            continue

        current = run_command(
            ["xdotool", "getwindowclassname", window_id], capture_output=True
        )
        if current.stdout.strip() != window_class:
            run_command(["xdotool", "set_window", "--class", window_class, window_id])
            print("Set WM_CLASS.")


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    program = Path(sys.argv[0]).name
    if not args:
        print(
            "No arguments provided.\n\n"
            f"Usage: env GAMECLASS='<executable>=<window class>' {program} [COMMAND]..."
        )
        return 1

    gameclass = os.environ.get("GAMECLASS", "")
    if not gameclass:
        print(
            "No environment variable set.\n\n"
            f"Usage: env GAMECLASS='<executable>=<window class>' {program} [COMMAND]..."
        )
        return 1

    try:
        executable, window_class = parse_gameclass(gameclass)
    except ValueError:
        print(
            "Incorrect environment variable formatting.\n\n"
            f"Usage: env GAMECLASS='<executable>=<window class>' {program} [COMMAND]..."
        )
        return 1

    command = os.environ.get("COMMAND") or command_from_args(args)
    stop_event = threading.Event()
    watcher = threading.Thread(
        target=watch_windows,
        args=(executable, window_class, stop_event),
        daemon=True,
    )
    watcher.start()
    try:
        subprocess.run(command, shell=True, executable="/bin/sh", check=False)
    except OSError as error:
        print(f"gameclass: {error}", file=sys.stderr)
        return 1
    finally:
        stop_event.set()
        watcher.join()
    return 0
