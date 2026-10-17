"""Login banner facts for ublue-based bootc images."""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import shutil
import string
import subprocess
import sys
from pathlib import Path

IMAGE_INFO_FILE = Path("/usr/share/ublue-os/image-info.json")
TEMPLATE_FILE = Path("/usr/share/ublue-os/motd/template.md")
TIPS_DIR = Path("/usr/share/ublue-os/motd/tips")
BOOT_STATUS_FILE = Path("/etc/motd.d/boot-status")
NVIDIA_VERSION_FILE = Path("/proc/driver/nvidia/version")
RPM_OSTREE_TIMEOUT = 1.5
DISK_WARN_PERCENT = 90
__version__ = "1.0.1"


def read_image_info(path: Path) -> dict[str, str]:
    """Read image-info.json; missing, corrupt or non-object content yields {}."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return {key: value for key, value in data.items() if isinstance(value, str)}
    except Exception:
        return {}


def strip_image_ref(ref: str) -> str:
    return ref.removeprefix("ostree-image-signed:docker://")


def boot_status_lines(path: Path) -> list[str]:
    """One greenboot health line, or [] when the status file is absent."""
    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, ValueError):
        return []
    if "status is GREEN" in content:
        return ["󰟀 `Boot Status: Healthy 󰄳`"]
    collapsed = " ".join(content.split())
    return [f"󰟀 `{collapsed}`"]


def rpm_ostree_status(timeout: float = RPM_OSTREE_TIMEOUT) -> str:
    # shortcut: single fixed timeout; if this ever feels slow on a machine, add a cache file — not a daemon.
    try:
        result = subprocess.run(
            ["rpm-ostree", "status", "--json"],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return ""
    return result.stdout if result.returncode == 0 else ""


def staged_update_lines(raw: str) -> list[str]:
    """One line when rpm-ostree reports a staged deployment."""
    if not raw:
        return []
    try:
        data = json.loads(raw)
        if any(deployment.get("staged") for deployment in data.get("deployments", [])):
            return ["󰚰 `Update staged — reboot to apply`"]
    except Exception:
        return []
    return []


def disk_usage_percent(path: str = "/") -> int:
    # composefs-booted images show a read-only overlay at "/"; the real disk is /sysroot
    if path == "/" and os.path.ismount("/sysroot"):
        path = "/sysroot"
    stat = os.statvfs(path)
    used = stat.f_blocks - stat.f_bfree
    total = used + stat.f_bavail
    return round(100 * used / total) if total else 0


def disk_lines(percent: int) -> list[str]:
    if percent >= DISK_WARN_PERCENT:
        return [f"󰋊 `Root filesystem {percent}% full — free space before updating`"]
    return []


def nvidia_version(path: Path) -> str:
    """NVIDIA driver version from /proc, or "" when absent."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, ValueError):
        return ""
    match = re.search(r"NVRM version:.*?(\d+\.\d+(?:\.\d+)?)", text)
    return match.group(1) if match else ""


def system_line(kernel: str, nvidia: str) -> str:
    driver = f" · NVIDIA {nvidia}" if nvidia else ""
    return f"󰒓 `Kernel {kernel}{driver}`"


def pick_tip(tips_dir: Path) -> str:
    """One random non-empty line from tips/*.md, or "" when nothing to pick."""
    lines = []
    for tip in sorted(tips_dir.glob("*.md")):
        try:
            lines.extend(line.strip() for line in tip.read_text(encoding="utf-8").splitlines())
        except (OSError, ValueError):
            continue
    lines = [line for line in lines if line]
    return random.choice(lines) if lines else ""


FALLBACK_TEMPLATE = """# Welcome to Halcyon 󰊴
󱋩 `${MOTD_IMAGE_NAME}:${MOTD_IMAGE_BRANCH}`${MOTD_IMAGE_BUILD}
${MOTD_STATUS}
${MOTD_SYSTEM}
"""


def render(template_text: str, values: dict[str, str]) -> str:
    return string.Template(template_text).safe_substitute(values)


def banner() -> str:
    """Assemble the banner text from local facts; every failure omits its line."""
    info = read_image_info(Path(os.environ.get("MOTD_IMAGE_INFO_FILE", IMAGE_INFO_FILE)))
    version = info.get("version", "")
    values = {
        "MOTD_IMAGE_NAME": strip_image_ref(info.get("image-ref", "")),
        "MOTD_IMAGE_BRANCH": info.get("image-branch", ""),
        "MOTD_IMAGE_BUILD": f" (build {version})" if version else "",
        "MOTD_STATUS": "\n".join(
            boot_status_lines(BOOT_STATUS_FILE)
            + staged_update_lines(rpm_ostree_status())
            + disk_lines(disk_usage_percent())
        ),
        "MOTD_SYSTEM": system_line(os.uname().release, nvidia_version(NVIDIA_VERSION_FILE)),
        "MOTD_TIP": pick_tip(Path(os.environ.get("MOTD_TIP_DIRECTORY", TIPS_DIR))),
    }
    template_path = Path(os.environ.get("MOTD_TEMPLATE_FILE", TEMPLATE_FILE))
    try:
        template = template_path.read_text(encoding="utf-8")
    except (OSError, ValueError):
        template = FALLBACK_TEMPLATE
    return render(template, values)


def show_banner(text: str) -> None:
    """glow when available and stdout is a terminal; raw markdown otherwise."""
    if shutil.which("glow") is None:
        print(text)
        return
    args = ["glow"]
    if sys.stdout.isatty():
        args += ["-w", str(shutil.get_terminal_size((80, 24)).columns)]
    args.append("-")
    result = subprocess.run(args, input=text, text=True, check=False)
    if result.returncode != 0:
        print(text)


def disable_flag_path() -> Path:
    """Where the no-show flag lives; raises RuntimeError without HOME."""
    base = os.environ.get("XDG_CONFIG_HOME")
    if base:
        return Path(base, "no-show-user-motd")
    home = os.environ.get("HOME")
    if not home:
        raise RuntimeError("cannot locate the config directory: set HOME or XDG_CONFIG_HOME")
    return Path(home, ".config", "no-show-user-motd")


def toggle_flag() -> int:
    try:
        flag = disable_flag_path()
    except RuntimeError as error:
        print(error, file=sys.stderr)
        return 1
    if flag.exists():
        flag.unlink()
        print("MOTD banner enabled.")
    else:
        flag.parent.mkdir(parents=True, exist_ok=True)
        flag.touch()
        print("MOTD banner disabled.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ublue-motd", description=__doc__)
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("toggle", help="enable or disable the login banner")
    args = parser.parse_args(argv)
    if args.command == "toggle":
        return toggle_flag()
    if os.geteuid() == 0:
        return 0
    try:
        if disable_flag_path().exists():
            return 0
    except RuntimeError:
        pass
    show_banner(banner())
    return 0
