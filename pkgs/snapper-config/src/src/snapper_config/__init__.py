"""Manage the root snapper config used by the rollback recipes.

Port of bazzite-snapper-config. `enable` (the default) creates the config
for /var/home with retention set to zero and opens btrfs-assistant so the
user can pick real values; `clean` runs the cleanups; `wipe` resets the
defaults, cleans and disables snapshots; any other value disables the
timeline and boot timers.
"""

from __future__ import annotations

import subprocess
import sys

SNAPPER_DEFAULTS = (
    ("snapper", "set-config", "TIMELINE_MIN_AGE=1800"),
    ("snapper", "set-config", "TIMELINE_LIMIT_DAILY=0"),
    ("snapper", "set-config", "TIMELINE_LIMIT_HOURLY=0"),
    ("snapper", "set-config", "TIMELINE_LIMIT_MONTHLY=0"),
    ("snapper", "set-config", "TIMELINE_LIMIT_WEEKLY=0"),
    ("snapper", "set-config", "TIMELINE_LIMIT_QUARTERLY=0"),
    ("snapper", "set-config", "TIMELINE_LIMIT_YEARLY=0"),
    ("snapper", "set-config", "NUMBER_MIN_AGE=1800"),
    ("snapper", "set-config", "NUMBER_LIMIT=0"),
    ("snapper", "set-config", "NUMBER_LIMIT_IMPORTANT=0"),
    ("systemctl", "enable", "--now", "snapper-cleanup.timer"),
)
ZENITY_TEXT = (
    "Please change retention settings to what you want in the Snapper "
    "Settings tab in btrfs-assistant. Deleted data that still exist in a "
    "snapshot will still use disk space!"
)
__version__ = "1.0.0"


def run_sudo(command: tuple[str, ...]) -> int:
    """Run one command through sudo, inheriting the terminal for passwords."""
    try:
        return subprocess.run(["sudo", *command], check=False).returncode
    except FileNotFoundError:
        return 127


def set_snapper_defaults() -> None:
    """Zero retention; the user is expected to change it in btrfs-assistant."""
    for command in SNAPPER_DEFAULTS:
        run_sudo(command)


def cleanup_snapper() -> int:
    """Run the number and timeline cleanups; returns the last exit status."""
    run_sudo(("snapper", "cleanup", "number"))
    return run_sudo(("snapper", "cleanup", "timeline"))


def disable_snapper() -> int:
    """Delete the root config and stop the timeline and boot timers."""
    run_sudo(("snapper", "-c", "root", "delete-config"))
    run_sudo(("systemctl", "disable", "--now", "snapper-timeline.timer"))
    return run_sudo(("systemctl", "disable", "--now", "snapper-boot.timer"))


def has_config() -> bool:
    """True when `snapper get-config` succeeds; output is discarded."""
    try:
        result = subprocess.run(
            ["sudo", "snapper", "get-config"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    except FileNotFoundError:
        return False
    return result.returncode == 0


def enable() -> int:
    """Create the /var/home config when missing and set the defaults."""
    if has_config():
        return 0
    run_sudo(("snapper", "create-config", "/var/home"))
    set_snapper_defaults()
    run_sudo(("systemctl", "disable", "--now", "snapper-timeline.timer"))
    run_sudo(("systemctl", "disable", "--now", "snapper-boot.timer"))
    try:
        subprocess.run(["zenity", "--info", f"--text={ZENITY_TEXT}"], check=False)
    except FileNotFoundError:
        pass
    try:
        subprocess.Popen(["btrfs-assistant-launcher"])
    except FileNotFoundError:
        pass
    return 0


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else list(argv)
    action = args[0] if args else ""
    if action in ("", "enable"):
        return enable()
    if action == "clean":
        return cleanup_snapper()
    if action == "wipe":
        set_snapper_defaults()
        cleanup_snapper()
        disable_snapper()
        return run_sudo(("systemctl", "disable", "--now", "snapper-cleanup.timer"))
    return disable_snapper()
