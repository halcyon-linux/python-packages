"""Tests for the halcyon-boot-remount package."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import sys
import tomllib
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

import halcyon_boot_remount


def require(name: str):
    value = getattr(halcyon_boot_remount, name, None)
    if value is None:
        raise AssertionError(f"halcyon_boot_remount.{name} is not implemented")
    return value


RO_MOUNTS = "proc /proc proc rw,nosuid 0 0\ndev /boot ext4 ro,relatime 0 0\n"
RW_MOUNTS = "proc /proc proc rw,nosuid 0 0\ndev /boot ext4 rw,relatime 0 0\n"
NO_BOOT = "proc /proc proc rw,nosuid 0 0\n"


class PackageTests(unittest.TestCase):
    def test_package_exposes_only_the_boot_remount_command(self):
        project = tomllib.loads(
            (Path(__file__).parents[1] / "pyproject.toml").read_text(encoding="utf-8")
        )["project"]
        self.assertEqual(project["name"], "halcyon-boot-remount")
        self.assertEqual(
            project["scripts"], {"halcyon-boot-remount": "halcyon_boot_remount:main"}
        )

    def test_module_is_importable(self):
        self.assertIsNotNone(importlib.util.find_spec("halcyon_boot_remount"))


class MountParsingTests(unittest.TestCase):
    def test_options_come_from_the_boot_line(self):
        self.assertEqual(require("boot_mount_options")(RO_MOUNTS), "ro,relatime")
        self.assertEqual(require("boot_mount_options")(RW_MOUNTS), "rw,relatime")

    def test_missing_boot_line_is_none(self):
        self.assertIsNone(require("boot_mount_options")(NO_BOOT))

    def test_read_only_flag_is_detected_between_commas(self):
        boot_is_read_only = require("boot_is_read_only")
        self.assertTrue(boot_is_read_only(RO_MOUNTS))
        self.assertTrue(boot_is_read_only("dev /boot ext4 rw,relatime,ro 0 0\n"))
        self.assertFalse(boot_is_read_only(RW_MOUNTS))
        self.assertFalse(boot_is_read_only(NO_BOOT))

    def test_unreadable_mounts_file_reads_as_empty(self):
        with patch.object(
            halcyon_boot_remount.Path, "read_text", side_effect=OSError("boom")
        ):
            self.assertEqual(require("read_mounts")(), "")


class RemountRwTests(unittest.TestCase):
    def test_already_rw_prints_zero_and_does_not_mount(self):
        with patch.object(halcyon_boot_remount, "read_mounts", return_value=RW_MOUNTS), \
             patch.object(halcyon_boot_remount.subprocess, "run") as run, \
             contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(require("main")(["rw"]), 0)
        run.assert_not_called()
        self.assertEqual(out.getvalue(), "0\n")

    def test_read_only_remounts_and_prints_one(self):
        with patch.object(halcyon_boot_remount, "read_mounts", return_value=RO_MOUNTS), \
             patch.object(halcyon_boot_remount.subprocess, "run",
                          return_value=Mock(returncode=0)) as run, \
             contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(require("main")(["rw"]), 0)
        self.assertEqual(run.call_args.args[0], ["mount", "-o", "remount,rw", "/boot"])
        self.assertEqual(out.getvalue(), "1\n")

    def test_failed_remount_exits_thirteen_without_state(self):
        with patch.object(halcyon_boot_remount, "read_mounts", return_value=RO_MOUNTS), \
             patch.object(halcyon_boot_remount.subprocess, "run",
                          return_value=Mock(returncode=32)), \
             contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(require("main")(["rw"]), 13)
        self.assertEqual(out.getvalue(), "")

    def test_missing_mount_binary_is_exit_thirteen(self):
        with patch.object(halcyon_boot_remount, "read_mounts", return_value=RO_MOUNTS), \
             patch.object(halcyon_boot_remount.subprocess, "run",
                          side_effect=FileNotFoundError("mount")):
            self.assertEqual(require("main")(["rw"]), 13)


class RemountRoTests(unittest.TestCase):
    def test_state_one_restores_read_only(self):
        with patch.object(halcyon_boot_remount.subprocess, "run",
                          return_value=Mock(returncode=0)) as run:
            self.assertEqual(require("main")(["ro", "1"]), 0)
        self.assertEqual(run.call_args.args[0], ["mount", "-o", "remount,ro", "/boot"])

    def test_state_zero_or_missing_is_a_noop(self):
        with patch.object(halcyon_boot_remount.subprocess, "run") as run:
            self.assertEqual(require("main")(["ro", "0"]), 0)
            self.assertEqual(require("main")(["ro"]), 0)
        run.assert_not_called()

    def test_failed_restore_exits_thirteen(self):
        with patch.object(halcyon_boot_remount.subprocess, "run",
                          return_value=Mock(returncode=32)):
            self.assertEqual(require("main")(["ro", "1"]), 13)


class UsageTests(unittest.TestCase):
    def test_no_arguments_is_usage_error(self):
        with contextlib.redirect_stderr(io.StringIO()) as err:
            self.assertEqual(require("main")([]), 2)
        self.assertIn("Usage:", err.getvalue())

    def test_unknown_subcommand_is_usage_error(self):
        with contextlib.redirect_stderr(io.StringIO()) as err:
            self.assertEqual(require("main")(["status"]), 2)
        self.assertIn("Usage:", err.getvalue())


if __name__ == "__main__":
    unittest.main()
