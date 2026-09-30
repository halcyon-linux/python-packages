"""screenshot - Wayland screenshot helper.

Python 3.13 port of the original ``screenshot`` bash script.

Required tools: grim, slurp (region mode), swappy, niri (window mode).
The JSON produced by ``niri msg --json pick-window`` is parsed with Python's
json module, so jq is no longer needed.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import NoReturn

PROG: str = Path(sys.argv[0]).name or "screenshot"

EXIT_OK = 0
EXIT_ERROR = 1

EPILOG = """\
Screenshots are piped straight into swappy for annotation and saving.

Modes:
    region      Select a rectangle with slurp (default)
    fullscreen  Capture every output at once
    window      Pick a window through niri's pick-window

Dependencies:
    grim, swappy, plus slurp (region mode) and niri (window mode)
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


def die(message: str, code: int = EXIT_ERROR) -> NoReturn:
    """Print an error message to stderr and exit."""
    print(f"Error: {message}", file=sys.stderr)
    raise SystemExit(code)


def require(*commands: str) -> None:
    """Exit when one of the required commands is not installed."""
    missing = [command for command in commands if shutil.which(command) is None]
    if missing:
        die(f"missing required command(s): {', '.join(missing)}")


def confirm(prompt: str) -> bool:
    """Ask a y/N question; anything but y/Y means no."""
    try:
        reply = input(prompt)
    except EOFError:
        print()
        return False
    return reply.strip().lower() in ("y", "yes")


def check_wayland() -> None:
    """Warn (and ask for confirmation) when not running under Wayland."""
    wayland_display = os.environ.get("WAYLAND_DISPLAY", "")
    session_type = os.environ.get("XDG_SESSION_TYPE", "")
    if not wayland_display and session_type != "wayland":
        print("Warning: Not in Wayland session", file=sys.stderr)
        if not confirm("Continue? [y/N] "):
            raise SystemExit(EXIT_OK)


def pipe_to_swappy(grim_args: list[str]) -> int:
    """Run ``grim ... - | swappy -f -`` and return the pipeline's exit status."""
    require("grim", "swappy")
    try:
        grim = subprocess.Popen([*grim_args, "-"], stdout=subprocess.PIPE)
    except OSError as exc:
        die(f"failed to run grim: {exc}")

    try:
        swappy = subprocess.Popen(["swappy", "-f", "-"], stdin=grim.stdout)
    except OSError as exc:
        if grim.stdout is not None:
            grim.stdout.close()
        grim.kill()
        grim.wait()
        die(f"failed to run swappy: {exc}")

    # Close the parent's copy so grim sees EPIPE if swappy exits early.
    if grim.stdout is not None:
        grim.stdout.close()

    swappy_status = swappy.wait()
    grim_status = grim.wait()

    # pipefail semantics: report the rightmost non-zero status.
    if swappy_status != 0:
        return exit_status(swappy_status)
    return exit_status(grim_status)


def capture_region() -> int:
    check_wayland()
    require("slurp")

    try:
        result = subprocess.run(
            ["slurp"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
        )
    except OSError as exc:
        die(f"failed to run slurp: {exc}")

    selection = result.stdout.strip()

    if result.returncode != 0:
        # slurp exits with 1 when the selection is cancelled.
        if result.returncode == 1:
            return EXIT_OK
        die("slurp failed")

    if not selection:
        return EXIT_ERROR

    return pipe_to_swappy(["grim", "-g", selection])


def capture_fullscreen() -> int:
    check_wayland()
    return pipe_to_swappy(["grim"])


def _format_coordinate(value: object) -> str:
    """Render a rectangle component the way jq would (no trailing '.0')."""
    if isinstance(value, bool) or value is None:
        raise ValueError("invalid geometry value")
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return str(int(value)) if value.is_integer() else repr(value)
    raise ValueError("invalid geometry value")


def capture_window() -> int:
    check_wayland()
    require("niri")

    # Use niri's pick-window to get window information.
    try:
        result = subprocess.run(
            ["niri", "msg", "--json", "pick-window"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        die(f"failed to run niri: {exc}")

    if result.returncode != 0:
        die("Failed to pick window")

    try:
        window_info = json.loads(result.stdout)
    except json.JSONDecodeError:
        die("Could not parse niri window information")

    rect = window_info.get("rect") if isinstance(window_info, dict) else None
    if not isinstance(rect, dict):
        die("No window selected or invalid geometry")

    try:
        x = _format_coordinate(rect["x"])
        y = _format_coordinate(rect["y"])
        width = _format_coordinate(rect["width"])
        height = _format_coordinate(rect["height"])
    except (KeyError, ValueError):
        die("No window selected or invalid geometry")

    geometry = f"{x},{y} {width}x{height}"
    return pipe_to_swappy(["grim", "-g", geometry])


def build_parser() -> argparse.ArgumentParser:
    parser = ArgumentParser(
        prog=PROG,
        usage=f"{PROG} [OPTION]",
        description="Capture a screenshot and open it in swappy.",
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "-r",
        "--region",
        dest="mode",
        action="store_const",
        const="region",
        help="capture region (default)",
    )
    mode.add_argument(
        "-f",
        "--fullscreen",
        dest="mode",
        action="store_const",
        const="fullscreen",
        help="capture fullscreen",
    )
    mode.add_argument(
        "-w",
        "--window",
        dest="mode",
        action="store_const",
        const="window",
        help="capture window",
    )
    parser.set_defaults(mode="region")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    match args.mode:
        case "region":
            return capture_region()
        case "fullscreen":
            return capture_fullscreen()
        case "window":
            return capture_window()
        case _:  # pragma: no cover - argparse restricts the choices
            die(f"Unknown mode '{args.mode}'")
            return EXIT_ERROR


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
