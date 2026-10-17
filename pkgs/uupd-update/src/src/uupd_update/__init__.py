"""Front-end for uupd: attach to or start the update service and stream its journal."""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import time

MAIN_SERVICE = "uupd.service"
MANUAL_SERVICE = "uupd-manual.service"
INACTIVE_STATES = ("inactive", "failed", "")
__version__ = "1.0.0"


def read_state(unit: str) -> str:
    """ActiveState of unit; "" when the unit is unknown or systemctl fails."""
    result = subprocess.run(
        ["systemctl", "show", "-p", "ActiveState", "--value", unit],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else ""


def inactive_exit_timestamp(unit: str) -> str:
    """When the unit last started; "" when systemctl has nothing to report."""
    result = subprocess.run(
        ["systemctl", "show", "-p", "InactiveExitTimestamp", "--value", unit],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "LC_ALL": "C"},
    )
    return result.stdout.strip() if result.returncode == 0 else ""


def pick_target(main_state: str, manual_state: str) -> tuple[str, bool]:
    """(service, needs_start): the first active service, else the manual service to start."""
    if main_state not in INACTIVE_STATES:
        return MAIN_SERVICE, False
    if manual_state not in INACTIVE_STATES:
        return MANUAL_SERVICE, False
    return MANUAL_SERVICE, True


def journal_args(unit: str, since: str) -> list[str]:
    args = ["journalctl", "-u", unit, "-f", "-o", "cat", "--synchronize-on-exit=yes"]
    if since:
        return args + ["--since", since]
    return args + ["--lines=0"]


def exec_status(unit: str) -> str:
    """ExecMainStatus of the finished unit; "" when systemctl has nothing to report."""
    result = subprocess.run(
        ["systemctl", "show", "-p", "ExecMainStatus", "--value", unit],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else ""


def exit_code(raw: str) -> int:
    """The service's status as our exit code; empty means success, garbage mirrors bash (2)."""
    if not raw:
        return 0
    try:
        return int(raw)
    except ValueError:
        return 2


def stream_journal(unit: str, since: str) -> subprocess.Popen:
    """Follow the unit's journal on our stdout/stderr; the child runs until stopped."""
    return subprocess.Popen(journal_args(unit, since))


def stop_journal(process: subprocess.Popen) -> None:
    if process.poll() is None:
        process.terminate()


def wait_for_service(unit: str, needs_start: bool) -> None:
    """Block until the service has finished: start --wait, or poll an attached one."""
    if needs_start:
        subprocess.run(["systemctl", "start", "--wait", unit], check=False)
        return
    while read_state(unit) not in INACTIVE_STATES:
        time.sleep(1)


def install_stop_handlers(process: subprocess.Popen) -> None:
    """SIGTERM/SIGHUP stop the journal child and exit by the signal, like the bash trap."""
    def stop(signum: int, _frame: object) -> None:
        stop_journal(process)
        raise SystemExit(128 + signum)

    for sig in (signal.SIGTERM, signal.SIGHUP):
        signal.signal(sig, stop)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="uupd-update", description=__doc__)
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.parse_args(argv)
    process = None
    try:
        target, needs_start = pick_target(read_state(MAIN_SERVICE), read_state(MANUAL_SERVICE))
        since = "" if needs_start else inactive_exit_timestamp(target)
        process = stream_journal(target, since)
        install_stop_handlers(process)
        wait_for_service(target, needs_start)
        return exit_code(exec_status(target))
    except FileNotFoundError as error:
        print(f"uupd-update: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130
    finally:
        if process is not None:
            stop_journal(process)
