"""Per-user setup: privileged one-time tweaks plus default template files.

Port of bazzite-user-setup and bazzite-privileged-user-setup. The user half
runs from halcyon-user-setup.service as the desktop user, keeps its state
under $XDG_DATA_HOME/bazzite, and calls halcyon-privileged-user-setup
through polkit for the root-only steps (NTP, tailscale operator, libvirt
group). It finishes by symlinking the shipped template configs into the
user's Templates directory.
"""

from __future__ import annotations

import grp
import json
import os
import subprocess
import sys
from pathlib import Path

IMAGE_INFO_FILE = Path("/usr/share/ublue-os/image-info.json")
PRIVILEGED_HELPER = "/usr/bin/halcyon-privileged-user-setup"
SETUP_VERSION = "58"
TEMPLATE_SOURCES = (
    Path("/etc/vkBasalt.conf"),
    Path("/etc/dxvk-example.conf"),
    Path("/usr/share/doc/mangohud/MangoHud.conf.example"),
)
__version__ = "1.0.0"


class UserSetupError(Exception):
    """A step the shell script aborted on (its `set -e` behaviour)."""


def read_image_info(path: Path = IMAGE_INFO_FILE) -> tuple[str, str]:
    """image-name and fedora-version; unreadable files abort like jq did."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise UserSetupError(f"cannot read {path}: {error}") from error

    def value(key: str) -> str:
        raw = data.get(key) if isinstance(data, dict) else None
        return raw if isinstance(raw, str) else "null"

    return value("image-name"), value("fedora-version")


def config_dir(home: Path | None = None) -> Path:
    """$XDG_DATA_HOME/bazzite, defaulting to ~/.local/share/bazzite."""
    base = Path.home() if home is None else home
    xdg_data_home = os.environ.get("XDG_DATA_HOME", "")
    data_home = Path(xdg_data_home) if xdg_data_home else base / ".local/share"
    return data_home / "bazzite"


def read_value(path: Path) -> str:
    """File contents like $(<file): trailing newlines trimmed."""
    return path.read_text(encoding="utf-8").rstrip("\n")


def migrate_legacy_markers(
    home: Path, version_file: Path, fedora_version_file: Path
) -> None:
    """Move the pre-XDG dotfile markers into the config dir (mv -f)."""
    for legacy, target in (
        (home / ".bazzite-configured", version_file),
        (home / ".bazzite-configured-fedora-version", fedora_version_file),
    ):
        if legacy.is_file():
            legacy.replace(target)


def already_configured(
    version_file: Path,
    fedora_version_file: Path,
    image_name_file: Path,
    fedora_version: str,
    image_name: str,
) -> bool:
    """True when all three state files exist and match the current image."""
    return (
        version_file.is_file()
        and fedora_version_file.is_file()
        and image_name_file.is_file()
        and read_value(version_file) == SETUP_VERSION
        and read_value(fedora_version_file) == fedora_version
        and read_value(image_name_file) == image_name
    )


def run_privileged_setup(user: str) -> int:
    """Run the privileged half through pkexec; its exit status is returned."""
    try:
        return subprocess.run(
            ["pkexec", PRIVILEGED_HELPER, user], check=False
        ).returncode
    except FileNotFoundError:
        print("halcyon-user-setup: pkexec not found", file=sys.stderr)
        return 127


def templates_dir(home: Path) -> Path:
    """xdg-user-dir TEMPLATES, falling back to ~/Templates."""
    value = ""
    try:
        result = subprocess.run(
            ["xdg-user-dir", "TEMPLATES"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            value = result.stdout.rstrip("\n")
    except FileNotFoundError:
        value = ""
    if not value or value == str(home):
        return home / "Templates"
    return Path(value)


def link_templates(
    target_dir: Path, sources: tuple[Path, ...] = TEMPLATE_SOURCES
) -> None:
    """mkdir -p the target and symlink every shipped template into it."""
    target_dir.mkdir(parents=True, exist_ok=True)
    for source in sources:
        if not source.is_file():
            continue
        target = target_dir / source.name
        if not target.exists():
            target.symlink_to(source)


def main(argv: list[str] | None = None) -> int:
    if os.geteuid() < 1000:
        print("Bazzite user setup ran as an unsupported user. Exiting.")
        return 0
    try:
        home = Path.home()
        image_name, fedora_version = read_image_info()
        data_dir = config_dir(home)
        data_dir.mkdir(parents=True, exist_ok=True)
        version_file = data_dir / "version"
        fedora_version_file = data_dir / "fedora_version"
        image_name_file = data_dir / "image_name"
        migrate_legacy_markers(home, version_file, fedora_version_file)
        if already_configured(
            version_file,
            fedora_version_file,
            image_name_file,
            fedora_version,
            image_name,
        ):
            print(f"User setup v{SETUP_VERSION} has already run. Exiting.")
            return 0
        status = run_privileged_setup(os.environ.get("USER", ""))
        if status != 0:
            return status
        link_templates(templates_dir(home))
        version_file.write_text(f"{SETUP_VERSION}\n", encoding="utf-8")
        fedora_version_file.write_text(f"{fedora_version}\n", encoding="utf-8")
        image_name_file.write_text(f"{image_name}\n", encoding="utf-8")
        return 0
    except (UserSetupError, OSError) as error:
        print(f"halcyon-user-setup: {error}", file=sys.stderr)
        return 1


def systemd_escape(value: str) -> str:
    """systemd-escape output; "" when the tool is unavailable (bash left it empty)."""
    try:
        result = subprocess.run(
            ["systemd-escape", value], capture_output=True, text=True, check=False
        )
    except FileNotFoundError:
        return ""
    return result.stdout.rstrip("\n")


def run_best_effort(command: list[str]) -> int:
    """Run a command whose failure does not abort the script (no set -e here)."""
    try:
        return subprocess.run(command, check=False).returncode
    except FileNotFoundError:
        print(f"{command[0]}: command not found", file=sys.stderr)
        return 127


def privileged_main(argv: list[str] | None = None) -> int:
    """Root-only half, invoked through polkit by halcyon-user-setup."""
    args = sys.argv[1:] if argv is None else list(argv)
    user = args[0] if args else ""
    run_best_effort(["timedatectl", "set-ntp", "true"])
    run_best_effort(["tailscale", "set", f"--operator={systemd_escape(user)}"])
    try:
        grp.getgrnam("libvirt")
    except KeyError:
        return 0
    return run_best_effort(["usermod", "-aG", "libvirt", user])
