"""rmtmp - Secure Temporary Files Cleanup.

Python 3.13 port of the original ``rmtmp`` bash script.

Purpose: safely remove old temporary files and directories from /tmp and
/var/tmp.

Features:
  - Dry-run mode to preview deletions
  - Interactive confirmation prompt (y/N)
  - Handles both regular files and dotfiles
  - Comprehensive error handling
  - Configurable age threshold
  - Detailed logging
  - Excludes critical system files

Usage:
    sudo ./rmtmp.py              # Interactive mode with confirmation
    sudo ./rmtmp.py --dry-run    # Preview what would be deleted
    sudo ./rmtmp.py --yes        # Skip confirmation (for automated use)
"""

import argparse
import contextlib
import io
import os
import re
import shutil
import signal
import sys
import time
from collections.abc import Callable, Iterator
from datetime import datetime
from pathlib import Path
from typing import NoReturn
from types import FrameType

SCRIPT_NAME: str = Path(sys.argv[0]).name or "rmtmp"

# ============================================================================
# CONFIGURATION
# ============================================================================

# Days old before a file is considered for deletion.
# The semantics of find's "-mtime +N" are preserved: N means "strictly more
# than N whole days", so DAYS_OLD=6 selects files that are 7+ days old.
DEFAULT_DAYS_OLD: int = 6

# Directories to clean.
TMP_DIRS: tuple[str, ...] = ("/tmp", "/var/tmp")

# Files and directories to always exclude (regular expressions matched against
# the base name of the entry).
EXCLUDE_PATTERNS: tuple[str, ...] = (
    r"lost\+found",
    r"systemd-private-.*",
    r"\.X11-unix",
    r"\.ICE-unix",
    r"\.font-unix",
    r"\.XIM-unix",
    r"\.Test-unix",
)

SECONDS_PER_DAY: int = 86400


class ArgumentParser(argparse.ArgumentParser):
    """ArgumentParser that exits with status 1 on usage errors.

    argparse exits with 2 by default; the shell version this replaces used 1.
    """

    def error(self, message: str) -> NoReturn:
        self.print_usage(sys.stderr)
        print(f"{self.prog}: error: {message}", file=sys.stderr)
        raise SystemExit(1)


def default_log_file() -> Path:
    """Pick the log file: /var/log when writable, /tmp otherwise."""
    override = os.environ.get("LOG_FILE")
    if override:
        return Path(override)
    if os.access("/var/log", os.W_OK):
        return Path("/var/log/tmp-cleanup.log")
    return Path("/tmp/tmp-cleanup.log")


def read_days_old() -> int:
    """Read DAYS_OLD from the environment, validating it."""
    raw = os.environ.get("DAYS_OLD")
    if raw is None or raw == "":
        return DEFAULT_DAYS_OLD
    try:
        value = int(raw)
    except ValueError:
        print(f"ERROR: DAYS_OLD must be an integer, got: {raw!r}", file=sys.stderr)
        raise SystemExit(1) from None
    if value < 0:
        print("ERROR: DAYS_OLD must not be negative", file=sys.stderr)
        raise SystemExit(1)
    return value


# ============================================================================
# LOGGING
# ============================================================================


class Logger:
    """Timestamped logger writing to stderr and, when possible, a log file."""

    def __init__(self, log_file: Path) -> None:
        self.log_file = log_file
        self._handle: io.TextIOBase | None = None

    def open(self) -> bool:
        """Try to open the log file for appending. Returns True on success."""
        directory = self.log_file.parent
        if not directory.is_dir():
            try:
                directory.mkdir(parents=True, exist_ok=True)
            except OSError:
                print(
                    f"Warning: Cannot create log directory: {directory}",
                    file=sys.stderr,
                )
                return False
        try:
            # Long-lived handle: closed by close() at the end of the run.
            self._handle = self.log_file.open("a", encoding="utf-8")  # noqa: SIM115
        except OSError:
            print(
                f"Warning: Cannot write to log file: {self.log_file}", file=sys.stderr
            )
            return False
        return True

    def close(self) -> None:
        if self._handle is not None:
            try:
                self._handle.close()
            finally:
                self._handle = None

    def log(self, level: str, message: str) -> None:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        entry = f"[{timestamp}] [{level}] {message}"
        print(entry, file=sys.stderr)
        if self._handle is not None:
            try:
                self._handle.write(entry + "\n")
                self._handle.flush()
            except OSError:
                # Never let logging failures abort the cleanup.
                self.close()

    def info(self, message: str) -> None:
        self.log("INFO", message)

    def warn(self, message: str) -> None:
        self.log("WARN", message)

    def error(self, message: str) -> None:
        self.log("ERROR", message)


# ============================================================================
# FILESYSTEM HELPERS
# ============================================================================


def compile_exclusions(patterns: tuple[str, ...]) -> list[re.Pattern[str]]:
    """Compile the exclusion patterns, anchored like the original ``^p$``."""
    return [re.compile(pattern) for pattern in patterns]


def is_excluded(path: Path, exclusions: list[re.Pattern[str]]) -> bool:
    """Return True when the entry's base name matches an exclusion pattern."""
    name = path.name
    return any(pattern.fullmatch(name) for pattern in exclusions)


def is_old(path: Path, threshold_seconds: float, now: float) -> bool:
    """Return True if the entry's own mtime is older than the threshold.

    ``lstat`` is used so symlinks are judged by their own timestamp, matching
    find's behaviour when it is not asked to dereference links.
    """
    try:
        stat_result = path.lstat()
    except OSError:
        return False
    return (now - stat_result.st_mtime) >= threshold_seconds


def is_empty_dir(path: Path) -> bool:
    """Return True if the directory has no entries at all."""
    try:
        with os.scandir(path) as entries:
            return not any(True for _ in entries)
    except OSError:
        return False


def walk_depth_first(
    root: Path, prune: Callable[[Path], bool] | None = None
) -> Iterator[tuple[Path, bool]]:
    """Yield ``(path, is_dir)`` below ``root``, children before their parents.

    Symbolic links are never followed and ``root`` itself is not yielded, which
    matches ``find ... -mindepth 1 -depth``. When ``prune`` is given, any entry
    it accepts is skipped, and directories it accepts are not descended into.
    """
    stack: list[tuple[Path, bool]] = [(root, False)]
    while stack:
        path, visited = stack.pop()
        if visited:
            if path != root:
                yield path, True
            continue

        try:
            with os.scandir(path) as scanner:
                entries = list(scanner)
        except OSError:
            entries = []

        stack.append((path, True))
        for entry in entries:
            entry_path = Path(entry.path)
            if prune is not None and prune(entry_path):
                continue
            try:
                entry_is_dir = entry.is_dir(follow_symlinks=False)
            except OSError:
                entry_is_dir = False
            if entry_is_dir:
                stack.append((entry_path, False))
            else:
                yield entry_path, False


# ============================================================================
# CLEANUP
# ============================================================================


class Cleaner:
    """Encapsulates the cleanup run and its configuration."""

    def __init__(
        self,
        logger: Logger,
        days_old: int,
        dry_run: bool,
        exclusions: list[re.Pattern[str]],
    ) -> None:
        self.log = logger
        self.days_old = days_old
        self.dry_run = dry_run
        self.exclusions = exclusions
        self.threshold_seconds = (days_old + 1) * SECONDS_PER_DAY

    def _is_excluded(self, path: Path) -> bool:
        """Predicate used to prune excluded entries during traversal.

        The original script only tested the exclusion list when it was about to
        delete an entry, so files *inside* an excluded directory such as
        systemd-private-* were still removed. Pruning here protects the whole
        subtree, which is what the exclusion list is for.
        """
        return is_excluded(path, self.exclusions)

    def safe_delete(self, target: Path) -> bool:
        """Delete a file, symlink or empty directory. Returns False on failure."""
        # Skip if it disappeared in the meantime.
        if not target.exists() and not target.is_symlink():
            return True

        if is_excluded(target, self.exclusions):
            self.log.info(f"Skipping excluded item: {target}")
            return True

        if self.dry_run:
            self.log.info(f"[DRY-RUN] Would delete: {target}")
            return True

        if target.is_dir() and not target.is_symlink():
            try:
                target.rmdir()
            except OSError:
                try:
                    shutil.rmtree(target)
                except OSError:
                    self.log.warn(f"Failed to remove directory: {target}")
                    return False
                self.log.info(f"Removed directory tree: {target}")
            else:
                self.log.info(f"Removed empty directory: {target}")
            return True

        try:
            target.unlink()
        except FileNotFoundError:
            return True
        except OSError:
            self.log.warn(f"Failed to remove file: {target}")
            return False
        self.log.info(f"Removed file: {target}")
        return True

    def clean_tmp_dir(self, tmp_dir: str) -> None:
        """Clean a single temporary directory."""
        root = Path(tmp_dir)
        if not root.is_dir():
            self.log.warn(f"Directory does not exist: {tmp_dir}")
            return

        self.log.info(f"Cleaning temporary directory: {tmp_dir}")
        self.log.info(
            f"Target: files modified more than {self.days_old + 1} days ago"
        )

        count = 0
        failed = 0

        # First pass: regular files and symlinks.
        now = time.time()
        files = [
            path
            for path, entry_is_dir in walk_depth_first(root, self._is_excluded)
            if not entry_is_dir and is_old(path, self.threshold_seconds, now)
        ]
        for path in files:
            if self.safe_delete(path):
                count += 1
            else:
                failed += 1

        # Second pass: directories, removed only when they are empty.
        now = time.time()
        directories = [
            path
            for path, entry_is_dir in walk_depth_first(root, self._is_excluded)
            if entry_is_dir
            and is_empty_dir(path)
            and is_old(path, self.threshold_seconds, now)
        ]
        for path in directories:
            if self.safe_delete(path):
                count += 1
            else:
                failed += 1

        self.log.info(
            f"Cleanup complete for {tmp_dir}: {count} items processed, {failed} failed"
        )

    def count_candidates(self, tmp_dir: str) -> int:
        """Approximate how many entries the run would touch."""
        root = Path(tmp_dir)
        if not root.is_dir():
            return 0
        now = time.time()
        total = 0
        for path, entry_is_dir in walk_depth_first(root, self._is_excluded):
            if entry_is_dir and not is_empty_dir(path):
                continue
            if is_old(path, self.threshold_seconds, now):
                total += 1
        return total


# ============================================================================
# USER INTERACTION
# ============================================================================


def current_username() -> str:
    """Return the effective user name, falling back to the numeric UID."""
    try:
        import pwd

        return pwd.getpwuid(os.geteuid()).pw_name
    except (ImportError, KeyError, OSError):
        return str(os.geteuid())


def check_root() -> None:
    """Abort unless running with root privileges."""
    if os.geteuid() != 0:
        print(
            "ERROR: This script must be run as root or with sudo", file=sys.stderr
        )
        print(f"Usage: sudo {SCRIPT_NAME}", file=sys.stderr)
        raise SystemExit(1)


def confirm_cleanup(cleaner: Cleaner, log_file: Path, skip_confirm: bool) -> None:
    """Show a summary and ask the user to confirm (unless --yes was given)."""
    if skip_confirm:
        cleaner.log.info("Skipping confirmation (automated mode)")
        return

    print()
    print("==========================================")
    print(
        "DRY-RUN MODE: Preview Only"
        if cleaner.dry_run
        else "Temporary Files Cleanup Confirmation"
    )
    print("==========================================")
    print("This script will process files from:")
    for tmp_dir in TMP_DIRS:
        print(f"  - {tmp_dir}")
    print()
    print(f"Target: Files modified more than {cleaner.days_old + 1} days ago")
    print()

    total_count = 0
    print("Scanning directories...")
    for tmp_dir in TMP_DIRS:
        if not Path(tmp_dir).is_dir():
            continue
        dir_count = cleaner.count_candidates(tmp_dir)
        print(f"{tmp_dir}: approximately {dir_count} items will be affected")
        total_count += dir_count

    print()
    print(f"Total items to be processed: approximately {total_count}")
    print()

    if cleaner.dry_run:
        print("DRY-RUN: No files will actually be deleted")
        print()
        with contextlib.suppress(EOFError):
            input("Press Enter to continue with preview...")
        print()
        return

    print(f"Logs will be written to: {log_file}")
    print()

    while True:
        try:
            response = input("Do you want to proceed with cleanup? (y/N): ")
        except EOFError:
            response = ""
            print()
        match response.strip().lower():
            case "y" | "yes":
                print()
                print("Proceeding with cleanup...")
                print()
                return
            case "n" | "no" | "":
                print()
                print("Cleanup cancelled by user.")
                print()
                raise SystemExit(0)
            case _:
                print(
                    "Invalid response. Please enter 'y' for yes or 'n' for no "
                    "(or press Enter for no)."
                )


# ============================================================================
# ENTRY POINT
# ============================================================================


def build_parser() -> argparse.ArgumentParser:
    parser = ArgumentParser(
        prog=SCRIPT_NAME,
        usage=f"{SCRIPT_NAME} [OPTIONS]",
        description="Safely remove old temporary files and directories from "
        "/tmp and /var/tmp.",
        epilog=f"""\
Environment Variables:
  DAYS_OLD          Number of days threshold (default: {DEFAULT_DAYS_OLD}, meaning
                    {DEFAULT_DAYS_OLD + 1}+ days old files)
  LOG_FILE          Path to log file (default: /var/log/tmp-cleanup.log,
                    or /tmp/tmp-cleanup.log when /var/log is not writable)

Examples:
  sudo {SCRIPT_NAME}                 # Interactive mode with confirmation
  sudo {SCRIPT_NAME} --dry-run       # Preview deletions
  sudo {SCRIPT_NAME} --yes           # Automated mode without confirmation
  DAYS_OLD=13 sudo {SCRIPT_NAME}     # Delete files 14+ days old
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "-d",
        "--dry-run",
        action="store_true",
        help="preview what would be deleted without actually deleting",
    )
    parser.add_argument(
        "-y",
        "--yes",
        dest="skip_confirm",
        action="store_true",
        help="skip confirmation prompt (for automated use)",
    )
    return parser


def install_signal_handlers(logger: Logger) -> None:
    """Log and exit cleanly when the process is asked to terminate."""

    def handler(signum: int, _frame: FrameType | None) -> None:
        logger.error(f"Script interrupted by signal {signal.Signals(signum).name}")
        logger.close()
        raise SystemExit(128 + signum)

    signal.signal(signal.SIGTERM, handler)
    signal.signal(signal.SIGHUP, handler)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    days_old = read_days_old()
    log_file = default_log_file()

    # Check for root privileges first.
    check_root()

    logger = Logger(log_file)
    logger.open()
    install_signal_handlers(logger)

    cleaner = Cleaner(
        logger=logger,
        days_old=days_old,
        dry_run=args.dry_run,
        exclusions=compile_exclusions(EXCLUDE_PATTERNS),
    )

    try:
        logger.info("==========================================")
        if cleaner.dry_run:
            logger.info("DRY-RUN MODE: Preview only, no deletions")
        else:
            logger.info("Starting temporary files cleanup")
        logger.info("==========================================")

        logger.info(f"Running as user: {current_username()} (UID: {os.geteuid()})")
        logger.info(f"Files older than {days_old + 1} days will be processed")

        confirm_cleanup(cleaner, log_file, args.skip_confirm)

        for tmp_dir in TMP_DIRS:
            cleaner.clean_tmp_dir(tmp_dir)

        logger.info("==========================================")
        if cleaner.dry_run:
            logger.info("DRY-RUN completed - no files were deleted")
        else:
            logger.info("Cleanup completed successfully")
        logger.info("==========================================")
    except KeyboardInterrupt:
        # The shell version traps INT alongside TERM and logs before exiting.
        logger.error("Script interrupted")
        raise
    finally:
        logger.close()

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print(file=sys.stderr)
        sys.exit(130)
