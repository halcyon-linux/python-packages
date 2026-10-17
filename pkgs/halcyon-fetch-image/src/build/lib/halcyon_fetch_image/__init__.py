"""Print the image name:branch and a signed/unsigned marker for fastfetch.

Replaces the bazzite-fetch-image shell helper used as a fastfetch command.
Reads /usr/share/ublue-os/image-info.json, then checks the booted rpm-ostree
deployment: signed images get a plain glyph, unsigned ones get a blinking
red glyph.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

IMAGE_INFO_FILE = Path("/usr/share/ublue-os/image-info.json")
SIGNED_MARKER = "\U0000f456"
UNSIGNED_MARKER = "\U0000f2fc"
RED_FLASHING = "\033[6;31m"
SIGNED_ORIGIN_MARKER = "ostree-image-signed"
__version__ = "1.0.0"


def image_label(path: Path = IMAGE_INFO_FILE) -> str:
    """image-name:image-branch, or "" when image-info.json cannot be read."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ""
    if not isinstance(data, dict):
        return ""
    name = data.get("image-name", "")
    branch = data.get("image-branch", "")
    if not isinstance(name, str) or not isinstance(branch, str):
        return ""
    return f"{name}:{branch}"


def booted_status() -> str:
    """rpm-ostree status --json --booted; "" when the command fails."""
    try:
        result = subprocess.run(
            ["rpm-ostree", "status", "--json", "--booted"],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return ""
    return result.stdout if result.returncode == 0 else ""


def booted_is_signed(status: str) -> bool:
    """True when the booted deployment's origin carries the signed marker."""
    return SIGNED_ORIGIN_MARKER in status


def main(argv: list[str] | None = None) -> int:
    parts = [image_label()]
    if booted_is_signed(booted_status()):
        parts.append(f" {SIGNED_MARKER}")
    else:
        parts.append(f" {RED_FLASHING}{UNSIGNED_MARKER}")
    sys.stdout.write("".join(parts))
    return 0
