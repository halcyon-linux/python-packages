"""Bazzite rollback helper."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

IMAGE_INFO = Path("/usr/share/ublue-os/image-info.json")
ISSUES_URL = "https://github.com/halcyon-linux/bazzite-fork/issues"


@dataclass(frozen=True)
class ImageConfig:
    image: str
    provider: str
    branch: str


def load_image_info(path: Path = IMAGE_INFO) -> ImageConfig:
    info = json.loads(path.read_text(encoding="utf-8"))
    image = info.get("image-name")
    provider = info.get("image-vendor")
    if not isinstance(image, str) or not image:
        raise ValueError(f"image-name missing or empty in {path}")
    if not isinstance(provider, str) or not provider:
        raise ValueError(f"image-vendor missing or empty in {path}")
    branch = info.get("image-branch")
    return ImageConfig(image, provider, "stable" if branch is None else str(branch))


def run_command(args: Sequence[str], *, capture_output: bool = False):
    return subprocess.run(
        args,
        text=True,
        capture_output=capture_output,
        check=False,
    )


def _status_data(*args: str) -> dict:
    result = run_command(["rpm-ostree", "status", *args, "--json"], capture_output=True)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "rpm-ostree status failed")
    return json.loads(result.stdout)


def _skopeo_command(*args: str) -> list[str]:
    command = ["skopeo", *args]
    if shutil.which("bkt"):
        return ["bkt", "--ttl=30m", "--stale=5m", "--", "command", *command]
    return command


def filter_tags(tags: Sequence[str], track: str = "all") -> list[str]:
    if track == "stable":
        tags = [tag for tag in tags if tag.startswith("stable")]
    elif track == "testing":
        tags = [tag for tag in tags if tag.startswith("testing")]
    return sorted(tags)


def skopeo_tags(provider: str, image: str, track: str = "all") -> list[str]:
    reference = f"docker://ghcr.io/{provider}/{image}"
    result = run_command(_skopeo_command("list-tags", reference), capture_output=True)
    if result.returncode:
        raise RuntimeError(
            result.stderr.strip() or f"skopeo could not list {reference}"
        )
    return filter_tags(json.loads(result.stdout).get("Tags", []), track)


def available_variants(provider: str, config: ImageConfig) -> list[str]:
    print(f"Checking variants from {provider}...", file=sys.stderr)
    variants = []
    for variant in (config.image,):
        result = run_command(
            _skopeo_command("list-tags", f"docker://ghcr.io/{provider}/{variant}"),
            capture_output=True,
        )
        if result.returncode == 0:
            variants.append(variant)
    return variants


def parse_current_ref(reference: str | None) -> tuple[str, str]:
    if not reference:
        return "", ""
    match = re.search(r".*/(?P<image>[^:]+):(?P<tag>[^:]+)$", reference)
    return (match.group("image"), match.group("tag")) if match else ("", "")


def signing_scheme() -> str:
    status = _status_data("-b")
    references = [
        deployment.get("container-image-reference", "")
        for deployment in status.get("deployments", [])
    ]
    if any(
        "ostree-image-signed" in reference
        for reference in references
        if isinstance(reference, str)
    ):
        return "ostree-image-signed:docker://ghcr.io"
    return "ostree-unverified-registry:ghcr.io"


def build_rebase_ref(target: str, config: ImageConfig) -> str:
    if target.startswith("ostree-"):
        return target
    if ":" in target:
        target = f"{config.provider}/{target}"
    else:
        target = f"{config.provider}/{config.image}:{target}"
    return f"ostree-image-signed:docker://ghcr.io/{target}"


def _style(text: str, code: str) -> str:
    return f"\033[{code}m{text}\033[0m" if sys.stdout.isatty() else text


def _read_input() -> str:
    try:
        return input()
    except EOFError:
        return ""


def confirm(message: str) -> bool | None:
    print(f"{message} {_style('(Y/n)', '33')} ", end="", flush=True)
    try:
        reply = input()
    except EOFError:
        print()
        return None
    return not reply or reply.lower().startswith("y")


def current_de() -> str:
    """Detect the active desktop environment using the shell helper's rules."""
    if (
        "GNOME" in os.environ.get("XDG_CURRENT_DESKTOP", "")
        or "gnome" in os.environ.get("DESKTOP_SESSION", "")
        or shutil.which("gnome-shell")
    ):
        return "gnome"
    if (
        "KDE" in os.environ.get("XDG_CURRENT_DESKTOP", "")
        or "plasma" in os.environ.get("DESKTOP_SESSION", "")
        or shutil.which("plasmashell")
    ):
        return "kde"
    return "unknown"


def target_de(image: str) -> str:
    """The desktop environment implied by a Bazzite image name."""
    return "GNOME" if "gnome" in image else "KDE/Plasma"


def target_image_name(target: str, config: ImageConfig) -> str:
    """Extract the target image name for the desktop mismatch warning."""
    if target.startswith("ostree-"):
        return target.rsplit("/", 1)[-1].split(":", 1)[0]
    if ":" in target:
        return target.split(":", 1)[0]
    return config.image


def warn_if_de_mismatch(image: str) -> bool:
    """Ask before switching between GNOME and KDE/Plasma, as the shell did."""
    current = current_de()
    target = target_de(image)
    if (current == "gnome" and target != "GNOME") or (
        current == "kde" and target == "GNOME"
    ):
        message = (
            f"You're running {('GNOME' if current == 'gnome' else 'KDE/Plasma')} "
            f"but switching to {target} ({image})"
        )
        print()
        print(_style("⚠️  DESKTOP ENVIRONMENT WARNING ⚠️", "1;31"))
        print(_style(message, "33"))
        print(
            _style(
                "Switching DEs may cause issues and is unsupported. "
                "Consider backing up data.",
                "33",
            )
        )
        print()
        return bool(confirm("Continue anyway?"))
    return True


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
            return "Back" if "Back" in options else options[-1]
        if choice in options:
            return choice
        if choice.isdigit() and 1 <= int(choice) <= len(options):
            return options[int(choice) - 1]
        print(f"Enter a number from 1 to {len(options)} or an option name.")


def _clear_screen() -> None:
    if sys.stdout.isatty():
        print("\033[2J\033[H", end="")


def print_status() -> None:
    deployments = _status_data().get("deployments", [])
    current = next(
        (
            deployment.get("container-image-reference")
            for deployment in deployments
            if deployment.get("booted") is True
        ),
        None,
    )
    pending = next(
        (
            deployment.get("container-image-reference")
            for deployment in deployments
            if deployment.get("staged") is True
        ),
        None,
    )
    print(_style("Current System Status:", "1"))
    if current:
        print(f"  {_style('Active:', '1')} {_style(current, '32')}")
    if pending and pending != "null":
        print(
            f"  {_style('Pending:', '1')} {_style(pending, '33')} "
            f"{_style('(next boot)', '33')}"
        )
    print()


def current() -> None:
    deployments = _status_data().get("deployments", [])
    reference = next(
        (
            deployment.get("container-image-reference")
            for deployment in deployments
            if deployment.get("booted") is True
        ),
        None,
    )
    image, tag = parse_current_ref(reference)
    print(f"IMAGE:\t{_style(image, '1')}")
    print(f"TAG:\t{_style(tag, '1')}")


def rebase_to(config: ImageConfig, target: str, skip_confirm: bool = False) -> int:
    if not warn_if_de_mismatch(target_image_name(target, config)):
        return 1
    full_ref = build_rebase_ref(target, config)
    print(f"Rebasing to: {_style(full_ref, '1')}")
    if not skip_confirm and not confirm("Continue?"):
        print("Cancelled.")
        return 1
    print("Performing rebase...")
    result = run_command(["rpm-ostree", "rebase", full_ref])
    if result.returncode == 0:
        print(f"{_style('Rebase successful!', '32')} Reboot to apply changes.")
        return 0
    print(
        f"{_style('Rebase failed.', '31')} Image may not exist or be accessible."
    )
    return 1


def pick_image(config: ImageConfig, provider: str | None = None) -> str:
    provider = provider or config.provider
    variants = available_variants(provider, config)
    if not variants:
        message = f"No variants found for provider: {provider}"
        print(_style(message, "31"), file=sys.stderr)
        return "Back"
    print(f"Available images from {_style(provider, '32')}:", file=sys.stderr)
    return choose(*variants, "Back")


def pick_version(provider: str, image: str, track: str) -> str:
    versions = skopeo_tags(provider, image, track)
    if not versions:
        message = f"No {track} versions found for {image}"
        print(_style(message, "31"), file=sys.stderr)
        return "Back"
    print(f"{track} versions for {_style(image, '32')}:", file=sys.stderr)
    return choose(*versions, "Back")


def choose_filter(provider: str, image: str) -> str:
    options = []
    for track in ("stable", "testing"):
        try:
            if skopeo_tags(provider, image, track):
                options.append(track.title())
        except (OSError, RuntimeError, ValueError):
            pass
    options.extend(("All", "Back"))
    print(f"Available tracks for {_style(image, '32')}:", file=sys.stderr)
    return choose(*options)


def helptext(config: ImageConfig) -> str:
    program = Path(sys.argv[0]).name
    return f"""====== {config.image} Rollback Helper ======

This tool helps with rollbacks and rebases for {config.image}.

Usage: {program} [OPTION] [ARGUMENT]

Options:
  list [BRANCH]      List available images (default: {config.branch})
  rollback           Rollback to previous image
  current            Show current image
  rebase [TARGET]    Rebase to target (format: TAG, IMAGE:TAG, or full ostree ref)

Examples:
  {program} list {config.branch}
  {program} rebase testing
  {program} rebase {config.image}:{config.branch}

For help: {ISSUES_URL}"""


def list_images(config: ImageConfig, branch: str | None = None) -> None:
    branch = config.branch if branch is None else branch
    if branch == "all":
        print("Listing all available images...", file=sys.stderr)
    else:
        print(f"Listing {branch} versions...", file=sys.stderr)
    print("\n".join(skopeo_tags(config.provider, config.image, branch)))


def rollback(yes: bool = False) -> int:
    if not yes and not confirm("Rollback to previous image?"):
        print("Cancelled.")
        return 0
    result = run_command(["rpm-ostree", "rollback"])
    if result.returncode == 0:
        print("Reboot for changes to take effect", file=sys.stderr)
    return result.returncode


def _is_yes_flag(value: str | None) -> bool:
    return value in ("-y", "--yes")


def _interactive_list(config: ImageConfig) -> None:
    _clear_screen()
    image = pick_image(config)
    if image == "Back":
        return
    track = choose_filter(config.provider, image)
    if track != "Back":
        _clear_screen()
        print("\n".join(skopeo_tags(config.provider, image, track.lower())))
        press_any_key()


def _interactive_rebase(config: ImageConfig) -> None:
    image = pick_image(config)
    if image == "Back":
        return
    track = choose_filter(config.provider, image)
    if track == "Back":
        return
    version = pick_version(config.provider, image, track.lower())
    if version != "Back":
        _clear_screen()
        rebase_to(
            config,
            f"ostree-image-signed:docker://ghcr.io/{config.provider}/{image}:{version}",
        )
        press_any_key()


def _interactive_custom_provider(config: ImageConfig) -> None:
    _clear_screen()
    print("Enter provider name (default: ublue-os):")
    provider = _read_input().strip().lower() or "ublue-os"
    image = pick_image(config, provider)
    if image != "Back":
        print("Enter image:tag or press Enter to browse versions:")
        manual_target = _read_input().strip()
        if manual_target:
            rebase_to(config, f"{signing_scheme()}/{provider}/{manual_target}")
        else:
            track = choose_filter(provider, image)
            if track != "Back":
                version = pick_version(provider, image, track.lower())
                if version != "Back":
                    rebase_to(
                        config,
                        f"{signing_scheme()}/{provider}/{image}:{version}",
                    )
    press_any_key()


def interactive_menu(config: ImageConfig) -> int:
    actions = (
        "List Images",
        "Show Current",
        "Rollback",
        "Rebase",
        "Custom Provider",
        "Exit",
    )
    while True:
        _clear_screen()
        print(helptext(config))
        print()
        try:
            print_status()
            action = choose(*actions)
            if action == "List Images":
                _interactive_list(config)
            elif action == "Show Current":
                _clear_screen()
                current()
                press_any_key()
            elif action == "Rollback":
                _clear_screen()
                rollback()
                press_any_key()
            elif action == "Rebase":
                _clear_screen()
                _interactive_rebase(config)
            elif action == "Custom Provider":
                _interactive_custom_provider(config)
            elif action == "Exit":
                print("Exiting...")
                return 0
        except (OSError, RuntimeError, ValueError) as error:
            print(f"brh: {error}", file=sys.stderr)
            press_any_key()


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    try:
        config = load_image_info()
        command = args[0] if args else ""
        if command in ("", "help", "-h", "--help"):
            return interactive_menu(config)
        if command == "list":
            list_images(config, args[1] if len(args) > 1 else None)
            return 0
        if command == "rollback":
            return rollback(_is_yes_flag(args[1] if len(args) > 1 else None))
        if command == "current":
            current()
            return 0
        if command == "rebase":
            if len(args) < 2 or not args[1]:
                print("Usage: rebase TARGET", file=sys.stderr)
                print(
                    f"Examples: rebase stable, rebase {config.image}:testing",
                    file=sys.stderr,
                )
                return 1
            return rebase_to(
                config,
                args[1],
                _is_yes_flag(args[2] if len(args) > 2 else None),
            )
        print(f"Unknown option: {command}. Run without arguments for interactive mode.")
        return 0
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as error:
        print(f"brh: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
