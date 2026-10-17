"""One-shot hardware setup for the current machine.

Port of bazzite-hardware-setup. Runs once per image identity (name, branch,
Fedora version) plus HWS_VER: applies the kernel arguments this machine
needs, shortens an over-long hostname, and records the identity it ran for
under /etc/bazzite. A reboot is issued when the kernel arguments changed.
"""

from __future__ import annotations

import json
import socket
import subprocess
import sys
from pathlib import Path

IMAGE_INFO_FILE = Path("/usr/share/ublue-os/image-info.json")
STATE_DIR = Path("/etc/bazzite")
HOSTNAME_FILE = Path("/etc/hostname")
HWS_VER = "81"
HOSTNAME_FALLBACK = "bazzite"
PLYMOUTH_MESSAGE = "Preparing System - Please wait, this may take a while"
KARG_MESSAGES = {
    "--append-if-missing=bluetooth.disable_ertm=1": "Adding needed kargs for bluetooth",
    "--append-if-missing=kvm.ignore_msrs=1": "Adding needed kargs for virtualization",
    "--append-if-missing=kvm.report_ignored_msrs=0": "Adding needed kargs for virtualization",
    "--delete-if-present=nomodeset": "Removing nomodeset",
}
__version__ = "1.0.0"


class SetupError(Exception):
    """A step the shell script aborted on (its `set -e` behaviour)."""

    def __init__(self, message: str, exit_code: int = 1):
        super().__init__(message)
        self.exit_code = exit_code


def read_image_info(path: Path = IMAGE_INFO_FILE) -> tuple[str, str, str]:
    """image-name, image-branch and fedora-version from image-info.json.

    Values that are absent or not strings read as "null", matching the jq
    filter the shell script used.
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise SetupError(f"cannot read {path}: {error}") from error

    def value(key: str) -> str:
        raw = data.get(key) if isinstance(data, dict) else None
        return raw if isinstance(raw, str) else "null"

    return value("image-name"), value("image-branch"), value("fedora-version")


def read_state_file(state_dir: Path, name: str) -> str:
    """One recorded state value; "" when the file does not exist."""
    try:
        return (state_dir / name).read_text(encoding="utf-8").rstrip("\n")
    except OSError:
        return ""


def read_previous_state(state_dir: Path = STATE_DIR) -> dict[str, str]:
    """The identity recorded by the previous run, empty strings when unset."""
    return {
        "hws_version": read_state_file(state_dir, "hws_version"),
        "image_name": read_state_file(state_dir, "image_name"),
        "image_branch": read_state_file(state_dir, "image_branch"),
        "fedora_version": read_state_file(state_dir, "fedora_version"),
    }


def already_configured(
    known: dict[str, str], image_name: str, image_branch: str, fedora_version: str
) -> bool:
    """True when the recorded identity matches this run's HWS_VER and image."""
    return (
        known.get("hws_version") == HWS_VER
        and known.get("image_name") == image_name
        and known.get("image_branch") == image_branch
        and known.get("fedora_version") == fedora_version
    )


def karg_args(kargs: str) -> list[str]:
    """The rpm-ostree kargs operations this kernel command line needs."""
    needed: list[str] = []
    if "disable_ertm" not in kargs:
        needed.append("--append-if-missing=bluetooth.disable_ertm=1")
    if "kvm.ignore_msrs=1" not in kargs:
        needed.append("--append-if-missing=kvm.ignore_msrs=1")
    if "kvm.report_ignored_msrs=0" not in kargs:
        needed.append("--append-if-missing=kvm.report_ignored_msrs=0")
    if "nomodeset" in kargs:
        needed.append("--delete-if-present=nomodeset")
    return needed


def current_kargs() -> str:
    """`rpm-ostree kargs` output; a failure aborts the run like set -e did."""
    result = subprocess.run(
        ["rpm-ostree", "kargs"], capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        raise SetupError(
            f"rpm-ostree kargs failed with exit code {result.returncode}",
            result.returncode,
        )
    return result.stdout.strip()


def apply_kargs(kargs: str | None = None) -> bool:
    """Report and apply missing/obsolete kernel args; True when anything changed."""
    if kargs is None:
        kargs = current_kargs()
    print(f"Current kargs: {kargs}")
    needed = karg_args(kargs)
    for item in needed:
        print(KARG_MESSAGES[item])
    if not needed:
        print("No karg changes needed")
        return False
    print(f"Found needed karg changes, applying the following: {' '.join(needed)}")
    try:
        subprocess.run(
            ["plymouth", "display-message", f"--text={PLYMOUTH_MESSAGE}"], check=False
        )
    except FileNotFoundError:
        pass
    result = subprocess.run(["rpm-ostree", "kargs", *needed], check=False)
    if result.returncode != 0:
        raise SetupError(
            f"rpm-ostree kargs failed with exit code {result.returncode}", 1
        )
    return True


def hostname_too_long(hostname: str) -> bool:
    """Whether to fall back to the short hostname.

    The shell script counted `hostname | wc -m`, which includes the trailing
    newline, so a 20-character hostname was already replaced.
    """
    return len(hostname) + 1 > 20


def fix_hostname(hostname: str | None = None) -> None:
    """Shorten distrobox-hostile hostnames and make sure /etc/hostname exists."""
    current = socket.gethostname() if hostname is None else hostname
    if hostname_too_long(current):
        result = subprocess.run(
            ["hostnamectl", "set-hostname", HOSTNAME_FALLBACK], check=False
        )
        if result.returncode != 0:
            raise SetupError(
                f"hostnamectl failed with exit code {result.returncode}",
                result.returncode,
            )
    if not HOSTNAME_FILE.exists():
        try:
            HOSTNAME_FILE.touch()
        except OSError as error:
            raise SetupError(f"cannot create {HOSTNAME_FILE}: {error}") from error


def write_state(
    state_dir: Path, image_name: str, image_branch: str, fedora_version: str
) -> None:
    """Record the identity this run configured, for the next boot to compare."""
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "hws_version").write_text(f"{HWS_VER}\n", encoding="utf-8")
    (state_dir / "image_name").write_text(f"{image_name}\n", encoding="utf-8")
    (state_dir / "image_branch").write_text(f"{image_branch}\n", encoding="utf-8")
    (state_dir / "fedora_version").write_text(
        f"{fedora_version}\n", encoding="utf-8"
    )


def main(argv: list[str] | None = None) -> int:
    try:
        image_name, image_branch, fedora_version = read_image_info()
        known = read_previous_state()
        if already_configured(known, image_name, image_branch, fedora_version):
            print(
                f"Hardware setup already ran for version {known.get('hws_version', '')}, skipping"
            )
            return 0
        fix_hostname()
        should_reboot = apply_kargs()
        write_state(STATE_DIR, image_name, image_branch, fedora_version)
        if should_reboot:
            print("Rebooting to apply karg changes")
            result = subprocess.run(["reboot"], check=False)
            if result.returncode != 0:
                raise SetupError(
                    f"reboot failed with exit code {result.returncode}",
                    result.returncode,
                )
        return 0
    except SetupError as error:
        print(f"hardware-setup: {error}", file=sys.stderr)
        return error.exit_code
