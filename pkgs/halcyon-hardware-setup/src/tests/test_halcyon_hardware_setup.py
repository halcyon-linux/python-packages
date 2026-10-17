"""Tests for the halcyon-hardware-setup package."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

import halcyon_hardware_setup


def require(name: str):
    value = getattr(halcyon_hardware_setup, name, None)
    if value is None:
        raise AssertionError(f"halcyon_hardware_setup.{name} is not implemented")
    return value


class PackageTests(unittest.TestCase):
    def test_package_exposes_only_the_hardware_setup_command(self):
        project = tomllib.loads(
            (Path(__file__).parents[1] / "pyproject.toml").read_text(encoding="utf-8")
        )["project"]
        self.assertEqual(project["name"], "halcyon-hardware-setup")
        self.assertEqual(
            project["scripts"],
            {"halcyon-hardware-setup": "halcyon_hardware_setup:main"},
        )

    def test_module_is_importable(self):
        self.assertIsNotNone(importlib.util.find_spec("halcyon_hardware_setup"))


class ReadImageInfoTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.path = Path(self._tmp.name) / "image-info.json"

    def test_reads_the_three_identity_fields(self):
        self.path.write_text(
            json.dumps(
                {
                    "image-name": "bazzfin-nvidia",
                    "image-branch": "stable",
                    "fedora-version": "44",
                }
            ),
            encoding="utf-8",
        )
        self.assertEqual(
            require("read_image_info")(self.path),
            ("bazzfin-nvidia", "stable", "44"),
        )

    def test_missing_file_raises_setup_error(self):
        with self.assertRaises(require("SetupError")) as caught:
            require("read_image_info")(self.path)
        self.assertEqual(caught.exception.exit_code, 1)

    def test_missing_keys_read_as_jq_null(self):
        self.path.write_text(json.dumps({"image-name": "bazzfin-nvidia"}), encoding="utf-8")
        self.assertEqual(
            require("read_image_info")(self.path),
            ("bazzfin-nvidia", "null", "null"),
        )

    def test_non_string_values_read_as_jq_null(self):
        self.path.write_text(
            json.dumps({"image-name": 3, "image-branch": None, "fedora-version": "44"}),
            encoding="utf-8",
        )
        self.assertEqual(
            require("read_image_info")(self.path), ("null", "null", "44")
        )


class StateFileTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.state_dir = Path(self._tmp.name)

    def test_trailing_newline_is_trimmed(self):
        (self.state_dir / "hws_version").write_text("81\n", encoding="utf-8")
        self.assertEqual(require("read_state_file")(self.state_dir, "hws_version"), "81")

    def test_missing_file_reads_as_empty(self):
        self.assertEqual(require("read_state_file")(self.state_dir, "hws_version"), "")

    def test_previous_state_maps_all_four_files(self):
        for name, value in (
            ("hws_version", "81"),
            ("image_name", "bazzfin-nvidia"),
            ("image_branch", "stable"),
            ("fedora_version", "44"),
        ):
            (self.state_dir / name).write_text(value + "\n", encoding="utf-8")
        self.assertEqual(
            require("read_previous_state")(self.state_dir),
            {
                "hws_version": "81",
                "image_name": "bazzfin-nvidia",
                "image_branch": "stable",
                "fedora_version": "44",
            },
        )


class AlreadyConfiguredTests(unittest.TestCase):
    def setUp(self):
        self.known = {
            "hws_version": "81",
            "image_name": "bazzfin-nvidia",
            "image_branch": "stable",
            "fedora_version": "44",
        }
        self.check = require("already_configured")

    def test_matching_identity_is_configured(self):
        self.assertTrue(self.check(self.known, "bazzfin-nvidia", "stable", "44"))

    def test_each_mismatch_reconfigures(self):
        self.assertFalse(self.check({}, "bazzfin-nvidia", "stable", "44"))
        self.assertFalse(
            self.check({**self.known, "hws_version": "80"}, "bazzfin-nvidia", "stable", "44")
        )
        self.assertFalse(
            self.check(self.known, "bazzfin-nvidia", "testing", "44")
        )
        self.assertFalse(self.check(self.known, "bazzfin-nvidia", "stable", "45"))


class KargArgsTests(unittest.TestCase):
    def test_complete_kargs_need_nothing(self):
        kargs = "kvm.ignore_msrs=1 kvm.report_ignored_msrs=0 bluetooth.disable_ertm=1"
        self.assertEqual(require("karg_args")(kargs), [])

    def test_missing_kargs_are_appended(self):
        self.assertEqual(
            require("karg_args")("quiet rhgb"),
            [
                "--append-if-missing=bluetooth.disable_ertm=1",
                "--append-if-missing=kvm.ignore_msrs=1",
                "--append-if-missing=kvm.report_ignored_msrs=0",
            ],
        )

    def test_partially_configured_kargs(self):
        self.assertEqual(
            require("karg_args")("bluetooth.disable_ertm=1 kvm.ignore_msrs=1"),
            ["--append-if-missing=kvm.report_ignored_msrs=0"],
        )

    def test_nomodeset_is_removed(self):
        kargs = "bluetooth.disable_ertm=1 kvm.ignore_msrs=1 kvm.report_ignored_msrs=0 nomodeset"
        self.assertEqual(require("karg_args")(kargs), ["--delete-if-present=nomodeset"])


class ApplyKargsTests(unittest.TestCase):
    def test_no_changes_prints_and_skips_rpm_ostree(self):
        with patch.object(halcyon_hardware_setup.subprocess, "run") as run, \
             contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertFalse(
                require("apply_kargs")(
                    "bluetooth.disable_ertm=1 kvm.ignore_msrs=1 kvm.report_ignored_msrs=0"
                )
            )
        run.assert_not_called()
        self.assertIn("No karg changes needed", out.getvalue())

    def test_changes_are_applied_after_plymouth_message(self):
        run_returns = [Mock(returncode=0), Mock(returncode=0)]
        with patch.object(
            halcyon_hardware_setup.subprocess, "run", side_effect=run_returns
        ) as run, contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertTrue(require("apply_kargs")("quiet nomodeset"))
        calls = [call.args[0] for call in run.call_args_list]
        self.assertEqual(
            calls[0],
            [
                "plymouth",
                "display-message",
                "--text=Preparing System - Please wait, this may take a while",
            ],
        )
        self.assertEqual(
            calls[1],
            [
                "rpm-ostree",
                "kargs",
                "--append-if-missing=bluetooth.disable_ertm=1",
                "--append-if-missing=kvm.ignore_msrs=1",
                "--append-if-missing=kvm.report_ignored_msrs=0",
                "--delete-if-present=nomodeset",
            ],
        )
        text = out.getvalue()
        self.assertIn("Adding needed kargs for bluetooth", text)
        self.assertIn("Adding needed kargs for virtualization", text)
        self.assertIn("Removing nomodeset", text)
        self.assertIn("Found needed karg changes", text)

    def test_missing_plymouth_is_ignored(self):
        with patch.object(
            halcyon_hardware_setup.subprocess,
            "run",
            side_effect=[FileNotFoundError("plymouth"), Mock(returncode=0)],
        ) as run:
            self.assertTrue(require("apply_kargs")("quiet"))
        self.assertEqual(run.call_count, 2)

    def test_failed_apply_is_a_setup_error(self):
        with patch.object(
            halcyon_hardware_setup.subprocess,
            "run",
            side_effect=[Mock(returncode=0), Mock(returncode=1)],
        ):
            with self.assertRaises(require("SetupError")) as caught:
                require("apply_kargs")("quiet")
        self.assertEqual(caught.exception.exit_code, 1)

    def test_current_kargs_reads_rpm_ostree_output(self):
        with patch.object(
            halcyon_hardware_setup.subprocess,
            "run",
            return_value=Mock(returncode=0, stdout="kargs = quiet\n"),
        ) as run:
            self.assertEqual(require("current_kargs")(), "kargs = quiet")
        self.assertEqual(run.call_args.args[0], ["rpm-ostree", "kargs"])

    def test_current_kargs_failure_keeps_exit_code(self):
        with patch.object(
            halcyon_hardware_setup.subprocess,
            "run",
            return_value=Mock(returncode=5, stdout=""),
        ):
            with self.assertRaises(require("SetupError")) as caught:
                require("current_kargs")()
        self.assertEqual(caught.exception.exit_code, 5)


class HostnameTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.hostname_file = Path(self._tmp.name) / "hostname"

    def test_nineteen_characters_fit(self):
        self.assertFalse(require("hostname_too_long")("a" * 19))

    def test_twenty_characters_are_replaced(self):
        # bash counted the newline, so 20 characters were already too long
        self.assertTrue(require("hostname_too_long")("a" * 20))

    def test_short_hostname_touches_missing_hostname_file(self):
        with patch.object(halcyon_hardware_setup, "HOSTNAME_FILE", self.hostname_file), \
             patch.object(halcyon_hardware_setup.subprocess, "run") as run:
            require("fix_hostname")("short")
        run.assert_not_called()
        self.assertTrue(self.hostname_file.exists())

    def test_long_hostname_is_replaced(self):
        with patch.object(halcyon_hardware_setup, "HOSTNAME_FILE", self.hostname_file), \
             patch.object(
                 halcyon_hardware_setup.subprocess, "run", return_value=Mock(returncode=0)
             ) as run:
            require("fix_hostname")("a" * 20)
        self.assertEqual(
            run.call_args.args[0], ["hostnamectl", "set-hostname", "bazzite"]
        )

    def test_default_hostname_comes_from_the_system(self):
        with patch.object(halcyon_hardware_setup, "HOSTNAME_FILE", self.hostname_file), \
             patch.object(
                 halcyon_hardware_setup.socket, "gethostname", return_value="a" * 20
             ), \
             patch.object(
                 halcyon_hardware_setup.subprocess, "run", return_value=Mock(returncode=0)
             ) as run:
            require("fix_hostname")()
        run.assert_called_once()

    def test_failed_hostnamectl_is_a_setup_error(self):
        with patch.object(halcyon_hardware_setup, "HOSTNAME_FILE", self.hostname_file), \
             patch.object(
                 halcyon_hardware_setup.subprocess, "run", return_value=Mock(returncode=3)
             ):
            with self.assertRaises(require("SetupError")) as caught:
                require("fix_hostname")("a" * 20)
        self.assertEqual(caught.exception.exit_code, 3)


class WriteStateTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.state_dir = Path(self._tmp.name) / "bazzite"

    def test_state_files_are_written_with_trailing_newlines(self):
        require("write_state")(self.state_dir, "bazzfin-nvidia", "stable", "44")
        self.assertEqual((self.state_dir / "hws_version").read_text(), "81\n")
        self.assertEqual((self.state_dir / "image_name").read_text(), "bazzfin-nvidia\n")
        self.assertEqual((self.state_dir / "image_branch").read_text(), "stable\n")
        self.assertEqual((self.state_dir / "fedora_version").read_text(), "44\n")


class MainTests(unittest.TestCase):
    def test_matching_identity_skips_everything(self):
        with patch.object(
            halcyon_hardware_setup,
            "read_image_info",
            return_value=("bazzfin-nvidia", "stable", "44"),
        ), patch.object(
            halcyon_hardware_setup,
            "read_previous_state",
            return_value={
                "hws_version": "81",
                "image_name": "bazzfin-nvidia",
                "image_branch": "stable",
                "fedora_version": "44",
            },
        ), patch.object(halcyon_hardware_setup, "fix_hostname") as fix, \
             patch.object(halcyon_hardware_setup, "apply_kargs") as apply, \
             patch.object(halcyon_hardware_setup, "write_state") as write, \
             contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(require("main")([]), 0)
        fix.assert_not_called()
        apply.assert_not_called()
        write.assert_not_called()
        self.assertIn("Hardware setup already ran for version 81, skipping", out.getvalue())

    def test_fresh_run_writes_state_without_reboot_when_kargs_unchanged(self):
        with patch.object(
            halcyon_hardware_setup,
            "read_image_info",
            return_value=("bazzfin-nvidia", "stable", "44"),
        ), patch.object(halcyon_hardware_setup, "read_previous_state", return_value={}), \
             patch.object(halcyon_hardware_setup, "fix_hostname") as fix, \
             patch.object(halcyon_hardware_setup, "apply_kargs", return_value=False), \
             patch.object(halcyon_hardware_setup, "write_state") as write, \
             patch.object(halcyon_hardware_setup.subprocess, "run") as run:
            self.assertEqual(require("main")([]), 0)
        fix.assert_called_once_with()
        write.assert_called_once_with(
            halcyon_hardware_setup.STATE_DIR, "bazzfin-nvidia", "stable", "44"
        )
        run.assert_not_called()

    def test_changed_kargs_trigger_reboot(self):
        with patch.object(
            halcyon_hardware_setup,
            "read_image_info",
            return_value=("bazzfin-nvidia", "stable", "44"),
        ), patch.object(halcyon_hardware_setup, "read_previous_state", return_value={}), \
             patch.object(halcyon_hardware_setup, "fix_hostname"), \
             patch.object(halcyon_hardware_setup, "apply_kargs", return_value=True), \
             patch.object(halcyon_hardware_setup, "write_state"), \
             patch.object(
                 halcyon_hardware_setup.subprocess, "run", return_value=Mock(returncode=0)
             ) as run, contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(require("main")([]), 0)
        self.assertEqual(run.call_args.args[0], ["reboot"])
        self.assertIn("Rebooting to apply karg changes", out.getvalue())

    def test_setup_error_returns_its_exit_code(self):
        with patch.object(
            halcyon_hardware_setup,
            "read_image_info",
            side_effect=require("SetupError")("boom", 4),
        ), contextlib.redirect_stderr(io.StringIO()) as err:
            self.assertEqual(require("main")([]), 4)
        self.assertIn("boom", err.getvalue())


if __name__ == "__main__":
    unittest.main()
