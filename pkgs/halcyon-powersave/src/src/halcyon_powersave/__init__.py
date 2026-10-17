"""Switch the power-profiles-daemon active profile through gdbus.

Replaces bazzite-powersave, which ujust recipes (and keybindings) call with
no argument for power-saver or with 0 for balanced.
"""

from __future__ import annotations

import subprocess
import sys

DEST = "net.hadess.PowerProfiles"
OBJECT_PATH = "/net/hadess/PowerProfiles"
METHOD = "org.freedesktop.DBus.Properties.Set"
PROPERTY = "ActiveProfile"
BALANCED = "balanced"
POWER_SAVER = "power-saver"
__version__ = "1.0.0"


def profile_for(argument: str | None) -> str:
    """balanced for the literal "0"; anything else (or unset) is power-saver."""
    value = argument if argument else "1"
    return BALANCED if value == "0" else POWER_SAVER


def gdbus_args(profile: str) -> list[str]:
    """The gdbus argv from the shell script, variant quoting included."""
    return [
        "gdbus",
        "call",
        "--system",
        "--dest",
        DEST,
        "--object-path",
        OBJECT_PATH,
        "--method",
        METHOD,
        DEST,
        PROPERTY,
        f"<'{profile}'>",
    ]


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else list(argv)
    argument = args[0] if args else None
    try:
        return subprocess.run(gdbus_args(profile_for(argument)), check=False).returncode
    except FileNotFoundError:
        print("halcyon-powersave: gdbus not found", file=sys.stderr)
        return 127
