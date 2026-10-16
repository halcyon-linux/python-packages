"""Launch the bbrew Homebrew TUI, bootstrapping Homebrew's environment."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from collections.abc import Sequence

BREW_PATH = "/home/linuxbrew/.linuxbrew/bin/brew"
BBREW_FORMULA = "Valkyrie00/homebrew-bbrew/bbrew"
EXPORT_PATTERN = re.compile(r"export ([A-Za-z_][A-Za-z0-9_]*)=(.*)")


def run_command(
    args: Sequence[str],
    *,
    env: dict[str, str] | None = None,
    capture_output: bool = False,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args, text=True, capture_output=capture_output, check=False, env=env
    )


def brew_environment(brew: str) -> dict[str, str]:
    """Return the environment with `brew shellenv` exports applied."""
    environment = os.environ.copy()
    try:
        result = run_command([brew, "shellenv"], capture_output=True)
    except OSError:
        return environment
    if result.returncode:
        return environment
    for line in result.stdout.splitlines():
        match = EXPORT_PATTERN.fullmatch(line)
        if match is None:
            continue
        name, value = match.group(1), match.group(2).strip().rstrip(";")
        if len(value) > 1 and value.startswith('"') and value.endswith('"'):
            value = value[1:-1]
        value = value.replace("${PATH+:$PATH}", f":{environment.get('PATH', '')}")
        value = value.replace("${INFOPATH:-}", environment.get("INFOPATH", ""))
        environment[name] = value
    return environment


def main(argv: list[str] | None = None) -> int | None:
    args = list(sys.argv[1:] if argv is None else argv)
    environment = os.environ.copy()
    if os.path.isfile(BREW_PATH):
        environment = brew_environment(BREW_PATH)
    if shutil.which("bbrew", path=environment.get("PATH")) is None:
        try:
            run_command(["brew", "install", BBREW_FORMULA], env=environment)
        except FileNotFoundError as error:
            print(f"bbrew-helper: {error}", file=sys.stderr)
            return 127
        except OSError as error:
            print(f"bbrew-helper: {error}", file=sys.stderr)
            return 126
    try:
        os.execvpe("bbrew", ["bbrew", *args], environment)
    except FileNotFoundError as error:
        print(f"bbrew-helper: {error}", file=sys.stderr)
        return 127
    except OSError as error:
        print(f"bbrew-helper: {error}", file=sys.stderr)
        return 126
    return None
