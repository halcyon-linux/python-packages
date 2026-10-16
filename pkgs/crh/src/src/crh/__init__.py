"""Custom display resolution and EDID helper for rpm-ostree systems."""

from __future__ import annotations

import os
import re
import shlex
import subprocess
import sys
import time
from collections.abc import Sequence
from pathlib import Path

OS_RELEASE = Path("/etc/os-release")
DRM_ROOT = Path("/sys/class/drm")
CRH_TMP = Path("/tmp/crh")
FIRMWARE_EDID = Path("/usr/local/lib/firmware/edid/edid.bin")
DRACUT_EDID = Path("/etc/dracut.conf.d/edid.conf")
RESOLUTION_PATTERN = re.compile(r":[0-9]+x[0-9]+[M]?[R]?@[0-9]+[e]?")


def read_ostree_version(path: Path = OS_RELEASE) -> str:
    for line in path.read_text(encoding="utf-8").splitlines():
        key, separator, value = line.partition("=")
        if key == "OSTREE_VERSION" and separator:
            try:
                return shlex.split(value)[0]
            except (ValueError, IndexError):
                return ""
    return ""


def run_command(
    args: Sequence[str], *, capture_output: bool = False, input_text: str | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        text=True,
        capture_output=capture_output,
        input=input_text,
        check=False,
    )


def parse_mode_options(kargs: str) -> list[str]:
    return re.findall(r"(?:^|\s)video=([^\s]*)", kargs)


def is_edid_mode(mode: str, kargs: str) -> bool:
    connector = mode.split(":", 1)[0]
    return connector in re.findall(r"firmware=([^:\s]+)", kargs)


def valid_resolution(value: str) -> bool:
    return RESOLUTION_PATTERN.search(value) is not None


def build_resolution(
    monitor: str, xyres: str, refresh: str, modifiers: set[str]
) -> str:
    before_refresh = "".join(flag for flag in "MR" if flag in modifiers)
    after_refresh = "".join(flag for flag in "ime" if flag in modifiers)
    return f"{monitor}:{xyres}{before_refresh}@{refresh}{after_refresh}"


def _style(text: str, code: str) -> str:
    return f"\033[{code}m{text}\033[0m" if sys.stdout.isatty() else text


def confirm(message: str) -> bool:
    print(f"{message} {_style('(Y/n)', '33')} ", end="", flush=True)
    try:
        reply = input()
    except EOFError:
        reply = ""
    return not reply or reply.lower().startswith("y")


def press_any_key() -> None:
    print("Press Enter to continue...")
    try:
        input()
    except EOFError:
        pass


def choose(*options: str) -> str:
    for index, option in enumerate(options, 1):
        print(f"  {index}. {option}")
    while True:
        try:
            choice = input("Select an option: ").strip()
        except EOFError:
            return "Cancel" if "Cancel" in options else options[-1]
        if choice in options:
            return choice
        if choice.isdigit() and 1 <= int(choice) <= len(options):
            return options[int(choice) - 1]
        print(f"Enter a number from 1 to {len(options)} or an option name.")


def _clear_screen() -> None:
    if sys.stdout.isatty():
        print("\033[2J\033[H", end="")


def get_kargs() -> str:
    result = run_command(["rpm-ostree", "kargs"], capture_output=True)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "rpm-ostree kargs failed")
    return result.stdout


def print_status(kargs: str | None = None) -> tuple[str, list[str]]:
    kargs = get_kargs() if kargs is None else kargs
    modes = parse_mode_options(kargs)
    print("Current custom resolution(s) are: ", end="")
    if not modes:
        print(_style("None", "1"))
        return kargs, modes
    for mode in modes:
        print(_style(mode, "1"), end=" ")
        if is_edid_mode(mode, kargs):
            print(_style("(EDID)", "34"), end="")
    print()
    return kargs, modes


def confirm_reboot(yes: str | None = None) -> int:
    if yes == "-y":
        print("The system will reboot in 5 seconds!")
        time.sleep(5)
        return run_command(["systemctl", "reboot"]).returncode
    if confirm("Reboot now?"):
        return run_command(["systemctl", "reboot"]).returncode
    return 0


def _apply_kargs(
    arguments: Sequence[str],
    success_message: str,
    failure_message: str,
    reboot_flag: str | None = None,
) -> int:
    print("Adding kernel arguments..." if arguments[0].startswith("--append") else "Removing kernel arguments...")
    print(f"Command: rpm-ostree kargs {' '.join(arguments)}")
    result = run_command(["rpm-ostree", "kargs", *arguments])
    if result.returncode:
        print(_style(failure_message, "31"))
        return 1
    print(f"{_style(success_message, '32')} Reboot to apply changes.")
    return confirm_reboot(reboot_flag)


def _monitor_entries(connected_only: bool) -> list[tuple[str, str]]:
    monitors = []
    for status_path in sorted(DRM_ROOT.glob("*/status")):
        match = re.match(r"card[^-]+-(.+)", status_path.parent.name)
        if not match:
            continue
        try:
            status = status_path.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if connected_only and status != "connected":
            continue
        monitors.append((match.group(1), status))
    return monitors


def choose_monitor(connected_only: bool) -> str | None:
    monitors = _monitor_entries(connected_only)
    options = [f"{name}:{status}" for name, status in monitors]
    choice = choose(*options, "Cancel")
    return None if choice == "Cancel" else choice.split(":", 1)[0]


def add_to() -> int:
    print("Select a monitor, this should be any one of the connected ports.")
    monitor = choose_monitor(connected_only=False)
    if monitor is None:
        return 0

    while True:
        print(f"Enter your resolution for {_style(monitor, '1')} (for example, 1920x1080).")
        try:
            xyres = input("    Your Resolution: ")
        except EOFError:
            return 0
        if re.search(r"[0-9]+x[0-9]+", xyres):
            break
        print(f"Invalid resolution {_style(xyres, '1')}")

    try:
        refresh = input("    Your Refresh Rate: ")
    except EOFError:
        return 0
    choices = (
        ("M", "Do you want the timing to use VESA Coordinated Video Timings?"),
        ("R", "Do you want reduced blanking?"),
        ("i", "Is this resolution interlaced?"),
        ("m", "Do you want to add margins to the calculation?"),
        ("e", "Do you want to make this display always enabled?"),
    )
    modifiers = set()
    for flag, prompt in choices:
        if confirm(prompt):
            modifiers.add(flag)
    resolution = build_resolution(monitor, xyres, refresh, modifiers)
    print(f"Your kernel argument for the resolution is {_style(resolution, '1')}")
    if not confirm("Would you like to apply it now?"):
        print("Cancelled.")
        return 0
    return _apply_kargs(
        [f"--append-if-missing=video={resolution}"],
        "Custom resolution added successfully!",
        "Adding kernel arguments failed. You may have an update in the background.",
    )


def add(resolution: str | None = None, reboot_flag: str | None = None) -> int:
    if not resolution and not reboot_flag:
        return add_to()
    if not resolution or not valid_resolution(resolution):
        print(f"Invalid resolution {_style(resolution or '', '1')}")
        print("Usage: add <name>:<xres>x<yres>[M][R][@<refresh>][i][m][e]")
        print("Examples: add DP1:1920x1080MR@75e")
        return 1
    print(f"Your kernel argument for the resolution is {_style(resolution, '1')}")
    return _apply_kargs(
        [f"--append-if-missing=video={resolution}"],
        "Custom resolution added successfully!",
        "Adding kernel arguments failed. You may have an update in the background.",
        reboot_flag,
    )


def _remove_edid_files(interactive: bool) -> None:
    option = "-vi" if interactive else "-v"
    run_command(["sudo", "rm", option, str(FIRMWARE_EDID)])
    run_command(["sudo", "rm", option, str(DRACUT_EDID)])


def remove_all(modes: Sequence[str], kargs: str, yes: bool = False) -> int:
    if not modes:
        print("No custom resolutions to remove.")
        return 0
    if not yes and not confirm("Remove All Custom Resolutions?"):
        print("Cancelled.")
        return 0

    arguments = []
    for mode in modes:
        arguments.append(f"--delete-if-present=video={mode}")
        if is_edid_mode(mode, kargs):
            arguments.extend(
                (
                    "--delete-if-present=firmware_class.path=/usr/local/lib/firmware",
                    f"--delete-if-present=drm.edid_firmware={mode.split(':', 1)[0]}:edid/edid.bin",
                )
            )
            _remove_edid_files(interactive=not yes)
    return _apply_kargs(
        arguments,
        "Custom resolution removed successfully!",
        "Removing kernel arguments failed. You may have an update in the background.",
        "-y" if yes else None,
    )


def remove_interactive(modes: Sequence[str], kargs: str) -> int:
    if not modes:
        print("No custom resolutions to remove.")
        return 0
    options = [
        f"{mode} (EDID)" if is_edid_mode(mode, kargs) else mode for mode in modes
    ]
    selected = choose(*options, "Back")
    if selected == "Back":
        return 0
    selected_mode = selected.removesuffix(" (EDID)")
    monitor = selected_mode.rsplit(":", 1)[0]
    if not confirm(f"Remove {_style(monitor, '1')}?"):
        print("Cancelled.")
        return 0
    arguments = [f"--delete-if-present=video={monitor}"]
    if is_edid_mode(selected_mode, kargs):
        arguments.extend(
            (
                "--delete-if-present=firmware_class.path=/usr/local/lib/firmware",
                f"--delete-if-present=drm.edid_firmware={monitor}:edid/edid.bin",
            )
        )
        _remove_edid_files(interactive=True)
    return _apply_kargs(
        arguments,
        "Custom resolution removed successfully!",
        "Removing kernel arguments failed. You may have an update in the background.",
    )


def remove(resolution: str | None = None, reboot_flag: str | None = None) -> int:
    kargs = get_kargs()
    _, modes = print_status(kargs)
    if not resolution and not reboot_flag:
        return remove_interactive(modes, kargs)
    if resolution == "all":
        return remove_all(modes, kargs, yes=reboot_flag == "-y")
    if not resolution or not valid_resolution(resolution):
        print(f"Invalid resolution {_style(resolution or '', '1')}")
        print("Usage: rm <name>:<xres>x<yres>[M][R][@<refresh>][i][m][e]")
        print("Examples: rm DP1:1920x1080MR@75e")
        return 1
    if resolution not in " ".join(modes):
        print("The resolution you are trying to remove does not exist!")
        return 1
    return _apply_kargs(
        [f"--delete-if-present=video={resolution}"],
        "Custom resolution removed successfully!",
        "Removing kernel arguments failed. You may have an update in the background.",
        reboot_flag,
    )


def dump_edid() -> int:
    print("Select a monitor to extract the edid from:")
    monitor = choose_monitor(connected_only=True)
    if monitor is None:
        return 0
    paths = sorted(DRM_ROOT.glob(f"card*/card*-{monitor}/edid"))
    if not paths:
        print(f"No EDID found for {monitor}.", file=sys.stderr)
        return 1
    try:
        edid = paths[0].read_bytes()
        CRH_TMP.mkdir(parents=True, exist_ok=True)
        (CRH_TMP / "edid.bin").write_bytes(edid)
    except OSError as error:
        print(f"crh: {error}", file=sys.stderr)
        return 1
    print(f"EDID dumped at {_style(str(CRH_TMP / 'edid.bin'), '1')}, edit it in your EDID editor.")
    press_any_key()
    return 0


def add_edid() -> int:
    kargs, modes = print_status()
    edited_edid = CRH_TMP / "edited" / "edid.bin"
    edited_edid.parent.mkdir(parents=True, exist_ok=True)
    print(f"Place your edited EDID into {_style(str(edited_edid.parent), '1')}")
    while not edited_edid.is_file() or edited_edid.stat().st_size == 0:
        if not confirm("Confirm that you have placed the EDID: "):
            if not edited_edid.is_file() or edited_edid.stat().st_size == 0:
                print("Your EDID is empty! Check it and try again.")
    if run_command(["sudo", "mkdir", "-p", str(FIRMWARE_EDID.parent)]).returncode:
        return 1
    if run_command(["sudo", "cp", str(edited_edid), str(FIRMWARE_EDID)]).returncode:
        return 1

    print("Select your monitor to set:")
    monitor = choose_monitor(connected_only=False)
    if monitor is None:
        return 0
    if run_command(["sudo", "mkdir", "-p", str(DRACUT_EDID.parent)]).returncode:
        return 1
    if run_command(["sudo", "touch", str(DRACUT_EDID)]).returncode:
        return 1
    dracut_line = 'install_items+=" /usr/local/lib/firmware/edid/edid.bin "\n'
    if run_command(["sudo", "tee", str(DRACUT_EDID)], input_text=dracut_line).returncode:
        return 1

    arguments = [
        "--append-if-missing=firmware_class.path=/usr/local/lib/firmware",
        f"--append-if-missing=drm.edid_firmware={monitor}:edid/edid.bin",
    ]
    for mode in modes:
        if mode.split(":", 1)[0] == monitor and "e" not in mode.split(":", 1)[-1]:
            arguments.append(f"--delete-if-present=video={mode}")
    arguments.append(f"--append-if-missing=video={monitor}:e")
    return _apply_kargs(
        arguments,
        "Custom EDID set successfully!",
        "Adding kernel arguments failed. You may have an update in the background.",
    )


def helptext() -> str:
    command = Path(sys.argv[0]).name
    return f"""====== Custom Resolution Helper ======

Set a custom resolution using modedb kernel arguments.

Usage: {command} [OPTION] [ARGUMENT]

Options:
  current             Show current custom resolutions
  add [RESOLUTION]    Add a custom resolution
  rm [RESOLUTION]     Remove a custom resolution
  rm all              Remove all custom resolutions
  add-edid            Add an EDID for a selected display
  dump-edid           Dump the EDID from a selected display

Resolution format: <name>:<xres>x<yres>[M][R][-<bpp>][@<refresh>][i][m][eDd]
Examples: {command} current; {command} add DP1:1920x1080MR@75e"""


def interactive_menu() -> int:
    actions = ("Add", "Remove", "Remove-All", "Add-EDID", "Dump-EDID", "Exit")
    while True:
        _clear_screen()
        print(helptext())
        kargs, modes = print_status()
        action = choose(*actions)
        try:
            if action == "Add":
                _clear_screen()
                add_to()
            elif action == "Remove":
                _clear_screen()
                remove_interactive(modes, kargs)
            elif action == "Remove-All":
                remove_all(modes, kargs)
            elif action == "Add-EDID":
                _clear_screen()
                add_edid()
            elif action == "Dump-EDID":
                _clear_screen()
                dump_edid()
            elif action == "Exit":
                print("Exiting")
                return 0
        except (OSError, RuntimeError, ValueError) as error:
            print(f"crh: {error}", file=sys.stderr)
            press_any_key()


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    try:
        if not read_ostree_version():
            print("This is NOT Fedora Atomic, exiting")
            return 0
        status = run_command(["rpm-ostree", "status"], capture_output=True)
        if status.returncode or "State: idle" not in status.stdout:
            print(
                "You have an unfinished update! Please try again after waiting "
                "for the update to complete and rebooting.\n"
                "You can check via rpm-ostree status."
            )
            return 1
        command = args[0] if args else ""
        if command == "current":
            print_status()
            return 0
        if command == "add":
            return add(args[1] if len(args) > 1 else None, args[2] if len(args) > 2 else None)
        if command == "rm":
            return remove(args[1] if len(args) > 1 else None, args[2] if len(args) > 2 else None)
        if command == "add-edid":
            return add_edid()
        if command == "dump-edid":
            return dump_edid()
        if command in ("", "help", "-h", "--help"):
            return interactive_menu()
        print(f"Unknown option: {command}. Run without arguments for interactive mode.")
        return 0
    except (OSError, RuntimeError, ValueError) as error:
        print(f"crh: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
