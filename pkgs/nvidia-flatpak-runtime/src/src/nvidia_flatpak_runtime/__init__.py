"""Keep the NVIDIA Flatpak runtimes in step with the system driver.

Port of ublue-nvidia-flatpak-runtime-sync and -notify (workaround for
https://github.com/flatpak/flatpak/issues/3907). The sync half is a
check/sync pair driven by a systemd service + ExecCondition: `check` exits 0
when a runtime is missing (so the service runs), 1 when everything matches;
`sync` installs the GL and GL32 runtimes from flathub. The notify half
shows a desktop notification with actions pointing at the docs, bazaar, or
the yafti update flow.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

NVIDIA_VERSION_FILE = Path("/sys/module/nvidia/version")
FLATHUB_REPO = "https://flathub.org/repo/flathub.flatpakrepo"
FLATPAK_KINDS = ("GL", "GL32")
NOTIFY_SEND = "/usr/bin/notify-send"
NOTIFY_TITLE = "Nvidia Flatpak Runtime Mismatch"
# The shell string kept the backslash-n pairs literal; notify-send receives
# exactly these bytes.
NOTIFY_BODY = (
    "Bazzite noticed that there is an Nvidia flatpak runtime mismatch!\\n\\n"
    "Hardware acceleration will not work in Flatpak Apps before you update it.\\n"
)
SEE_MORE_URL = (
    "https://docs.bazzite.gg/General/issues_and_resolutions/"
    "#flatpak-apps-have-no-hardware-acceleration-on-nvidia"
)
USAGE = "Usage: nvidia-flatpak-runtime-sync {check|sync}"
YAFTI_ARGS = (
    "/usr/bin/yafti_gtk.py",
    "/usr/share/yafti/yafti.yml",
    "--action-id",
    "update-nvidia-runtime",
)
__version__ = "1.0.0"


def flatpak_version(version: str) -> str:
    """NVIDIA 580.95.05 -> 580-95-05, the flatpak runtime naming."""
    return version.replace(".", "-")


def runtime_ref(kind: str, version: str) -> str:
    """org.freedesktop.Platform.<kind>.nvidia-<dashed version>."""
    return f"org.freedesktop.Platform.{kind}.nvidia-{flatpak_version(version)}"


def system_nvidia_version(path: Path | None = None) -> str:
    """The loaded driver version; an unreadable file aborts like the shell did."""
    source = NVIDIA_VERSION_FILE if path is None else path
    return source.read_text(encoding="utf-8").strip()


def sync_needed(version: str) -> bool:
    """True when either the GL or the GL32 runtime is missing."""
    for kind in FLATPAK_KINDS:
        try:
            result = subprocess.run(
                ["flatpak", "info", "--system", runtime_ref(kind, version)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        except FileNotFoundError:
            return True
        if result.returncode != 0:
            return True
    return False


def sync_main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else list(argv)
    try:
        version = system_nvidia_version()
    except OSError as error:
        print(f"nvidia-flatpak-runtime-sync: {error}", file=sys.stderr)
        return 1
    action = args[0] if args else ""
    if action == "check":
        if sync_needed(version):
            print(f"NVIDIA Flatpak runtime {version} needs to be installed")
            return 0
        print(f"NVIDIA Flatpak runtime {version} already installed")
        return 1
    if action == "sync":
        print(f"Installing NVIDIA Flatpak runtime version {version}")
        try:
            remote = subprocess.run(
                [
                    "flatpak",
                    "remote-add",
                    "--system",
                    "--if-not-exists",
                    "flathub",
                    FLATHUB_REPO,
                ],
                check=False,
            )
            if remote.returncode != 0:
                return remote.returncode
            install = subprocess.run(
                [
                    "flatpak",
                    "install",
                    "--system",
                    "--noninteractive",
                    "-y",
                    "flathub",
                    runtime_ref("GL", version),
                    runtime_ref("GL32", version),
                ],
                check=False,
            )
        except FileNotFoundError:
            print(
                "nvidia-flatpak-runtime-sync: flatpak not found",
                file=sys.stderr,
            )
            return 127
        return install.returncode
    print(USAGE)
    return 1


def notify_argv() -> list[str]:
    """The argv the shell assembled through eval, with its quoting resolved."""
    return [
        NOTIFY_SEND,
        "--app-name=Bazzite Nvidia Runtime Checker",
        "--expire-time=0",
        NOTIFY_TITLE,
        NOTIFY_BODY,
        "--action=see_more=See more",
        "--action=update_flatpak=Update all Flatpaks",
        "--action=update_runtime_only=Update Runtime Only",
    ]


def run_action(command: list[str]) -> int:
    """Run the chosen action, inheriting the terminal; 127 when it is missing."""
    try:
        return subprocess.run(command, check=False).returncode
    except FileNotFoundError:
        print(f"{command[0]}: command not found", file=sys.stderr)
        return 127


def notify_main(argv: list[str] | None = None) -> int:
    try:
        result = subprocess.run(
            notify_argv(), capture_output=True, text=True, check=False
        )
    except FileNotFoundError:
        print(
            "nvidia-flatpak-runtime-notify: notify-send not found",
            file=sys.stderr,
        )
        return 127
    if result.returncode != 0:
        return result.returncode
    action = result.stdout.rstrip("\n")
    if action == "see_more":
        return run_action(["xdg-open", SEE_MORE_URL])
    if action == "update_flatpak":
        return run_action(["/usr/bin/bazaar"])
    if action == "update_runtime_only":
        return run_action(list(YAFTI_ARGS))
    return 0
