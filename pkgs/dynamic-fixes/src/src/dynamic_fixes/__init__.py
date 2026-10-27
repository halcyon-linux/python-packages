"""Toggle the Intel GTK renderer workaround based on the loaded GPU modules.

Replaces bazzite-dynamic-fixes. Intel GPUs need GSK_RENDERER=gl to avoid
GTK4/libadwaita graphical glitches. The fix is written to the user's
environment.d when the xe or i915 module is loaded and in use, and removed
again when no Intel GPU is active.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

MODULES_FILE = Path("/proc/modules")
INTEL_MODULES = ("xe", "i915")
ENV_DIR_RELATIVE = Path(".config/environment.d")
ENV_FILE_NAME = "intel-gtk-fix.conf"
ENV_CONTENT = "GSK_RENDERER=gl\n"
__version__ = "1.0.0"


def read_modules(path: Path = MODULES_FILE) -> str:
    """The loaded-module table; an unreadable file reads as empty."""
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def intel_gpu_in_use(modules: str) -> bool:
    """True when xe/i915 is loaded and its use count is above zero."""
    for line in modules.splitlines():
        fields = line.split()
        if len(fields) < 3 or fields[0] not in INTEL_MODULES:
            continue
        try:
            uses = int(fields[2])
        except ValueError:
            continue
        if uses > 0:
            return True
    return False


def env_file(home: Path | None = None) -> Path:
    """$HOME/.config/environment.d/intel-gtk-fix.conf."""
    base = Path.home() if home is None else home
    return base / ENV_DIR_RELATIVE / ENV_FILE_NAME


def daemon_reload() -> int:
    """systemctl --user daemon-reload; returns its exit status."""
    return subprocess.run(
        ["systemctl", "--user", "daemon-reload"], check=False
    ).returncode


def main(argv: list[str] | None = None) -> int:
    target = env_file()
    in_use = intel_gpu_in_use(read_modules())
    if in_use and not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(ENV_CONTENT, encoding="utf-8")
        return daemon_reload()
    if not in_use and target.exists():
        target.unlink()
        return daemon_reload()
    return 0
