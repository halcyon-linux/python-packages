"""Tests for the crh package."""

from __future__ import annotations

import importlib.util
import contextlib
import io
import sys
import tempfile
import tomllib
import time
import unittest
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

import crh


def require(name: str):
    value = getattr(crh, name, None)
    if value is None:
        raise AssertionError(f"crh.{name} is not implemented")
    return value


class PackageTests(unittest.TestCase):
    def test_package_exposes_only_crh_command(self):
        project = tomllib.loads(
            (Path(__file__).parents[1] / "pyproject.toml").read_text(encoding="utf-8")
        )["project"]
        self.assertEqual(project["name"], "crh")
        self.assertEqual(project["scripts"], {"crh": "crh:main"})

    def test_crh_module_is_importable(self):
        self.assertIsNotNone(importlib.util.find_spec("crh"))

    def test_parse_mode_options_extracts_all_video_arguments(self):
        self.assertEqual(
            require("parse_mode_options")(
                "quiet video=DP-1:1920x1080@60 video=HDMI-A-1:1280x720@60"
            ),
            ["DP-1:1920x1080@60", "HDMI-A-1:1280x720@60"],
        )

    def test_edid_mode_matches_connector(self):
        kargs = "drm.edid_firmware=DP-1:edid/edid.bin firmware_class.path=/usr/local/lib/firmware"
        self.assertTrue(require("is_edid_mode")("DP-1:1920x1080@60", kargs))
        self.assertFalse(require("is_edid_mode")("HDMI-A-1:1920x1080@60", kargs))

    def test_resolution_validation_uses_documented_form(self):
        self.assertTrue(require("valid_resolution")("DP-1:1920x1080MR@75e"))
        self.assertFalse(require("valid_resolution")("DP-1:1920x1080"))

    def test_interactive_resolution_places_modifiers_around_refresh(self):
        self.assertEqual(
            require("build_resolution")("DP-1", "1920x1080", "75", {"i", "m", "e"}),
            "DP-1:1920x1080@75ime",
        )

    def test_non_ostree_system_exits_without_rpm_ostree(self):
        with (
            patch.object(crh, "read_ostree_version", return_value="", create=True),
            patch.object(crh, "run_command", create=True) as run,
            contextlib.redirect_stdout(io.StringIO()),
        ):
            self.assertEqual(require("main")(["current"]), 0)

        run.assert_not_called()

    def test_add_appends_resolution_and_yes_reboots(self):
        status = CompletedProcess([], 0, stdout="State: idle\n", stderr="")
        success = CompletedProcess([], 0, stdout="", stderr="")
        with (
            patch.object(crh, "read_ostree_version", return_value="44", create=True),
            patch.object(crh, "run_command", side_effect=[status, success, success], create=True) as run,
            patch.object(time, "sleep"),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            self.assertEqual(require("main")(["add", "DP-1:1920x1080@60", "-y"]), 0)

        self.assertEqual(
            [call.args[0] for call in run.call_args_list],
            [
                ["rpm-ostree", "status"],
                ["rpm-ostree", "kargs", "--append-if-missing=video=DP-1:1920x1080@60"],
                ["systemctl", "reboot"],
            ],
        )

    def test_direct_add_does_not_prompt_before_applying(self):
        status = CompletedProcess([], 0, stdout="State: idle\n", stderr="")
        success = CompletedProcess([], 0, stdout="", stderr="")
        with (
            patch.object(crh, "read_ostree_version", return_value="44", create=True),
            patch.object(
                crh, "run_command", side_effect=[status, success, success], create=True
            ) as run,
            patch.object(crh, "confirm", return_value=False, create=True) as confirm,
            patch.object(time, "sleep"),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            self.assertEqual(require("main")(["add", "DP-1:1920x1080@60", "-y"]), 0)

        confirm.assert_not_called()
        self.assertEqual(
            [call.args[0] for call in run.call_args_list],
            [
                ["rpm-ostree", "status"],
                ["rpm-ostree", "kargs", "--append-if-missing=video=DP-1:1920x1080@60"],
                ["systemctl", "reboot"],
            ],
        )

    def test_remove_all_cancel_does_not_mutate_system(self):
        with patch.object(crh, "confirm", return_value=False, create=True), patch.object(
            crh, "run_command", create=True
        ) as run, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(
                require("remove_all")(["DP-1:1920x1080@60"], "", yes=False), 0
            )

        run.assert_not_called()

    def test_remove_all_yes_removes_edid_files_and_reboots(self):
        success = CompletedProcess([], 0, stdout="", stderr="")
        with (
            patch.object(crh, "confirm", create=True) as confirm,
            patch.object(crh, "run_command", side_effect=[success] * 4, create=True) as run,
            patch.object(time, "sleep"),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            self.assertEqual(
                require("remove_all")(
                    ["DP-1:1920x1080@60"],
                    "drm.edid_firmware=DP-1:edid/edid.bin",
                    yes=True,
                ),
                0,
            )

        confirm.assert_not_called()
        self.assertEqual(
            [call.args[0] for call in run.call_args_list],
            [
                ["sudo", "rm", "-v", str(crh.FIRMWARE_EDID)],
                ["sudo", "rm", "-v", str(crh.DRACUT_EDID)],
                [
                    "rpm-ostree",
                    "kargs",
                    "--delete-if-present=video=DP-1:1920x1080@60",
                    "--delete-if-present=firmware_class.path=/usr/local/lib/firmware",
                    "--delete-if-present=drm.edid_firmware=DP-1:edid/edid.bin",
                ],
                ["systemctl", "reboot"],
            ],
        )

    def test_dump_edid_saves_bytes_to_crh_tmp(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            drm_root = root / "drm"
            edid = drm_root / "card0" / "card0-DP-1" / "edid"
            edid.parent.mkdir(parents=True)
            edid.write_bytes(b"edid-data")
            crh_tmp = root / "tmp" / "crh"
            with (
                patch.object(crh, "DRM_ROOT", drm_root),
                patch.object(crh, "CRH_TMP", crh_tmp),
                patch.object(crh, "choose_monitor", return_value="DP-1"),
                patch.object(crh, "press_any_key"),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                self.assertEqual(crh.dump_edid(), 0)

            self.assertEqual((crh_tmp / "edid.bin").read_bytes(), b"edid-data")


if __name__ == "__main__":
    unittest.main()
