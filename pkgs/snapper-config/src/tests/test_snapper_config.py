"""Tests for the snapper-config package."""

from __future__ import annotations

import importlib.util
import sys
import tomllib
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

import snapper_config


def require(name: str):
    value = getattr(snapper_config, name, None)
    if value is None:
        raise AssertionError(f"snapper_config.{name} is not implemented")
    return value


class PackageTests(unittest.TestCase):
    def test_package_exposes_only_the_snapper_config_command(self):
        project = tomllib.loads(
            (Path(__file__).parents[1] / "pyproject.toml").read_text(encoding="utf-8")
        )["project"]
        self.assertEqual(project["name"], "snapper-config")
        self.assertEqual(
            project["scripts"],
            {"snapper-config": "snapper_config:main"},
        )

    def test_module_is_importable(self):
        self.assertIsNotNone(importlib.util.find_spec("snapper_config"))


class RunSudoTests(unittest.TestCase):
    def test_command_is_wrapped_in_sudo(self):
        with patch.object(
            snapper_config.subprocess, "run", return_value=Mock(returncode=0)
        ) as run:
            self.assertEqual(require("run_sudo")(("snapper", "get-config")), 0)
        self.assertEqual(run.call_args.args[0], ["sudo", "snapper", "get-config"])

    def test_status_is_passed_through(self):
        with patch.object(
            snapper_config.subprocess, "run", return_value=Mock(returncode=4)
        ):
            self.assertEqual(require("run_sudo")(("snapper", "get-config")), 4)

    def test_missing_sudo_is_exit_127(self):
        with patch.object(
            snapper_config.subprocess, "run", side_effect=FileNotFoundError("sudo")
        ):
            self.assertEqual(require("run_sudo")(("snapper", "get-config")), 127)


class DefaultsTests(unittest.TestCase):
    def test_all_defaults_run_in_order(self):
        with patch.object(snapper_config, "run_sudo", return_value=0) as run:
            require("set_snapper_defaults")()
        self.assertEqual(
            [call.args[0] for call in run.call_args_list],
            [
                ("snapper", "set-config", "TIMELINE_MIN_AGE=1800"),
                ("snapper", "set-config", "TIMELINE_LIMIT_DAILY=0"),
                ("snapper", "set-config", "TIMELINE_LIMIT_HOURLY=0"),
                ("snapper", "set-config", "TIMELINE_LIMIT_MONTHLY=0"),
                ("snapper", "set-config", "TIMELINE_LIMIT_WEEKLY=0"),
                ("snapper", "set-config", "TIMELINE_LIMIT_QUARTERLY=0"),
                ("snapper", "set-config", "TIMELINE_LIMIT_YEARLY=0"),
                ("snapper", "set-config", "NUMBER_MIN_AGE=1800"),
                ("snapper", "set-config", "NUMBER_LIMIT=0"),
                ("snapper", "set-config", "NUMBER_LIMIT_IMPORTANT=0"),
                ("systemctl", "enable", "--now", "snapper-cleanup.timer"),
            ],
        )


class CleanupTests(unittest.TestCase):
    def test_both_cleanups_run_and_last_status_is_returned(self):
        with patch.object(
            snapper_config, "run_sudo", side_effect=[0, 3]
        ) as run:
            self.assertEqual(require("cleanup_snapper")(), 3)
        self.assertEqual(
            [call.args[0] for call in run.call_args_list],
            [("snapper", "cleanup", "number"), ("snapper", "cleanup", "timeline")],
        )


class DisableTests(unittest.TestCase):
    def test_config_is_deleted_and_timers_stopped(self):
        with patch.object(snapper_config, "run_sudo", return_value=0) as run:
            require("disable_snapper")()
        self.assertEqual(
            [call.args[0] for call in run.call_args_list],
            [
                ("snapper", "-c", "root", "delete-config"),
                ("systemctl", "disable", "--now", "snapper-timeline.timer"),
                ("systemctl", "disable", "--now", "snapper-boot.timer"),
            ],
        )


class HasConfigTests(unittest.TestCase):
    def test_successful_get_config_is_true(self):
        with patch.object(
            snapper_config.subprocess, "run", return_value=Mock(returncode=0)
        ) as run:
            self.assertTrue(require("has_config")())
        self.assertEqual(run.call_args.args[0], ["sudo", "snapper", "get-config"])
        self.assertEqual(run.call_args.kwargs["stdout"], snapper_config.subprocess.DEVNULL)
        self.assertEqual(run.call_args.kwargs["stderr"], snapper_config.subprocess.DEVNULL)

    def test_failed_get_config_is_false(self):
        with patch.object(
            snapper_config.subprocess, "run", return_value=Mock(returncode=1)
        ):
            self.assertFalse(require("has_config")())

    def test_missing_snapper_is_false(self):
        with patch.object(
            snapper_config.subprocess, "run", side_effect=FileNotFoundError("snapper")
        ):
            self.assertFalse(require("has_config")())


class EnableTests(unittest.TestCase):
    def test_existing_config_is_left_alone(self):
        with patch.object(snapper_config, "has_config", return_value=True), \
             patch.object(snapper_config, "run_sudo") as run, \
             patch.object(snapper_config.subprocess, "Popen") as popen:
            self.assertEqual(require("enable")(), 0)
        run.assert_not_called()
        popen.assert_not_called()

    def test_missing_config_creates_it_and_opens_btrfs_assistant(self):
        with patch.object(snapper_config, "has_config", return_value=False), \
             patch.object(snapper_config, "set_snapper_defaults") as defaults, \
             patch.object(snapper_config, "run_sudo", return_value=0) as run, \
             patch.object(
                 snapper_config.subprocess, "run", return_value=Mock(returncode=0)
             ) as zenity, \
             patch.object(snapper_config.subprocess, "Popen") as popen:
            self.assertEqual(require("enable")(), 0)
        self.assertEqual(
            [call.args[0] for call in run.call_args_list],
            [
                ("snapper", "create-config", "/var/home"),
                ("systemctl", "disable", "--now", "snapper-timeline.timer"),
                ("systemctl", "disable", "--now", "snapper-boot.timer"),
            ],
        )
        defaults.assert_called_once_with()
        self.assertEqual(zenity.call_args.args[0][0], "zenity")
        self.assertIn("btrfs-assistant", zenity.call_args.args[0][2])
        popen.assert_called_once_with(["btrfs-assistant-launcher"])


class MainTests(unittest.TestCase):
    def test_default_action_enables(self):
        with patch.object(snapper_config, "enable", return_value=0) as enable:
            self.assertEqual(require("main")([]), 0)
            self.assertEqual(require("main")(["enable"]), 0)
        self.assertEqual(enable.call_count, 2)

    def test_clean_action(self):
        with patch.object(snapper_config, "cleanup_snapper", return_value=0) as clean:
            self.assertEqual(require("main")(["clean"]), 0)
        clean.assert_called_once_with()

    def test_wipe_action_resets_cleans_and_disables(self):
        with patch.object(snapper_config, "set_snapper_defaults") as defaults, \
             patch.object(snapper_config, "cleanup_snapper") as clean, \
             patch.object(snapper_config, "disable_snapper") as disable, \
             patch.object(snapper_config, "run_sudo", return_value=0) as run:
            self.assertEqual(require("main")(["wipe"]), 0)
        defaults.assert_called_once_with()
        clean.assert_called_once_with()
        disable.assert_called_once_with()
        self.assertEqual(
            run.call_args.args[0],
            ("systemctl", "disable", "--now", "snapper-cleanup.timer"),
        )

    def test_unknown_action_disables(self):
        with patch.object(snapper_config, "disable_snapper", return_value=0) as disable:
            self.assertEqual(require("main")(["disable"]), 0)
        disable.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
