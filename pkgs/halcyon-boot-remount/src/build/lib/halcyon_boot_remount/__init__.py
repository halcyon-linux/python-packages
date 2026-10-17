"""Remount /boot read-write for an operation, then restore the prior state.

Replaces the sourced bazzite-boot-remount shell library on bootc images,
where /boot is mounted read-only and ujust recipes must remount it around
grub updates. Because the recipes run each step in its own process, the
"was /boot initially read-only" state travels through the command line:
`rw` prints 1 when it remounted (0 when /boot was already read-write), and
`ro 1` restores the read-only mount.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

MOUNTS_FILE = Path("/proc/mounts")
BOOT_MOUNT = "/boot"
__version__ = "1.0.0"


def read_mounts(path: Path = MOUNTS_FILE) -> str:
    """The kernel mount table; an unreadable file reads as empty."""
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def boot_mount_options(mounts: str) -> str | None:
    """The options field of the /boot mount, or None when it is not mounted."""
    for line in mounts.splitlines():
        fields = line.split()
        if len(fields) >= 4 and fields[1] == BOOT_MOUNT:
            return fields[3]
    return None


def boot_is_read_only(mounts: str) -> bool:
    """True when /boot is mounted and its option list carries the ro flag."""
    options = boot_mount_options(mounts)
    return options is not None and "ro" in options.split(",")


def remount(mode: str) -> int:
    """mount -o remount,<mode> /boot; returns its exit status."""
    return subprocess.run(
        ["mount", "-o", f"remount,{mode}", BOOT_MOUNT], check=False
    ).returncode


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else list(argv)
    if not args or args[0] not in ("rw", "ro"):
        print("Usage: halcyon-boot-remount {rw | ro STATE}", file=sys.stderr)
        return 2
    try:
        if args[0] == "rw":
            if not boot_is_read_only(read_mounts()):
                print("0")
                return 0
            if remount("rw") != 0:
                return 13
            print("1")
            return 0
        state = args[1] if len(args) > 1 else ""
        if state == "1" and remount("ro") != 0:
            return 13
        return 0
    except FileNotFoundError:
        # The bash library ran `mount ... || exit 13`; a missing mount binary
        # is a failed remount, not a crash.
        return 13
