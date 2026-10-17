"""Tests for the halcyon-powersave package."""

from __future__ import annotations

import importlib.util
import sys
import tomllib
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

import halcyon_powersave


def require(name: str):
    value = getattr(halcyon_powersave, name, None)
    if value is None:
        raise AssertionError(f"halcyon_powersave.{name} is not implemented")
    return value


class PackageTests(unittest.TestCase):
    def test_package_exposes_only_the_powersave_command(self):
        project = tomllib.loads(
            (Path(__file__).parents[1] / "pyproject.toml").read_text(encoding="utf-8")
        )["project"]
        self.assertEqual(project["name"], "halcyon-powersave")
        self.assertEqual(
            project["scripts"], {"halcyon-powersave": "halcyon_powersave:main"}
        )

    def test_module_is_importable(self):
        self.assertIsNotNone(importlib.util.find_spec("halcyon_powersave"))


class ProfileTests(unittest.TestCase):
    def test_zero_selects_balanced(self):
        self.assertEqual(require("profile_for")("0"), "balanced")

    def test_unset_or_empty_defaults_to_power_saver(self):
        profile_for = require("profile_for")
        self.assertEqual(profile_for(None), "power-saver")
        self.assertEqual(profile_for(""), "power-saver")

    def test_anything_else_is_power_saver(self):
        self.assertEqual(require("profile_for")("1"), "power-saver")


class GdbusArgsTests(unittest.TestCase):
    def test_argv_matches_the_shell_version(self):
        self.assertEqual(
            require("gdbus_args")("power-saver"),
            [
                "gdbus",
                "call",
                "--system",
                "--dest",
                "net.hadess.PowerProfiles",
                "--object-path",
                "/net/hadess/PowerProfiles",
                "--method",
                "org.freedesktop.DBus.Properties.Set",
                "net.hadess.PowerProfiles",
                "ActiveProfile",
                "<'power-saver'>",
            ],
        )


class MainTests(unittest.TestCase):
    def test_no_argument_selects_power_saver(self):
        with patch.object(
            halcyon_powersave.subprocess, "run", return_value=Mock(returncode=0)
        ) as run:
            self.assertEqual(require("main")([]), 0)
        self.assertEqual(run.call_args.args[0][-1], "<'power-saver'>")

    def test_zero_selects_balanced(self):
        with patch.object(
            halcyon_powersave.subprocess, "run", return_value=Mock(returncode=0)
        ) as run:
            self.assertEqual(require("main")(["0"]), 0)
        self.assertEqual(run.call_args.args[0][-1], "<'balanced'>")

    def test_gdbus_status_is_passed_through(self):
        with patch.object(
            halcyon_powersave.subprocess, "run", return_value=Mock(returncode=1)
        ):
            self.assertEqual(require("main")([]), 1)

    def test_missing_gdbus_is_exit_127(self):
        with patch.object(
            halcyon_powersave.subprocess, "run", side_effect=FileNotFoundError("gdbus")
        ):
            self.assertEqual(require("main")([]), 127)

    def test_defaults_to_sys_argv(self):
        with patch.object(sys, "argv", ["halcyon-powersave", "0"]), \
             patch.object(
                 halcyon_powersave.subprocess, "run", return_value=Mock(returncode=0)
             ) as run:
            self.assertEqual(require("main")(), 0)
        self.assertEqual(run.call_args.args[0][-1], "<'balanced'>")


if __name__ == "__main__":
    unittest.main()
