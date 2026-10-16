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

    def test_eof_is_not_confirmation(self):
        with (
            patch("builtins.input", side_effect=EOFError),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            self.assertIsNone(crh.confirm("Continue?"))

    def test_blank_enter_is_confirmation(self):
        with (
            patch("builtins.input", return_value=""),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            self.assertTrue(crh.confirm("Continue?"))

    def test_eof_does_not_confirm_remove_all(self):
        with (
            patch("builtins.input", side_effect=EOFError),
            patch.object(crh, "run_command", create=True) as run,
            contextlib.redirect_stdout(io.StringIO()),
        ):
            self.assertEqual(
                require("remove_all")(["DP-1:1920x1080@60"], "", yes=False), 0
            )

        run.assert_not_called()

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
                [
                    "rpm-ostree",
                    "kargs",
                    "--delete-if-present=video=DP-1:1920x1080@60",
                    "--delete-if-present=firmware_class.path=/usr/local/lib/firmware",
                    "--delete-if-present=drm.edid_firmware=DP-1:edid/edid.bin",
                ],
                ["sudo", "rm", "-v", str(crh.FIRMWARE_EDID)],
                ["sudo", "rm", "-v", str(crh.DRACUT_EDID)],
                ["systemctl", "reboot"],
            ],
        )

    def test_remove_all_reports_removal_failures_without_rebooting(self):
        succeeded = CompletedProcess([], 0, stdout="", stderr="")
        failed = CompletedProcess([], 1, stdout="", stderr="")
        with tempfile.TemporaryDirectory() as temporary_directory:
            surviving = Path(temporary_directory) / "edid.bin"
            surviving.write_bytes(b"old-edid")
            with (
                patch.object(crh, "FIRMWARE_EDID", surviving),
                patch.object(crh, "DRACUT_EDID", Path(temporary_directory) / "gone.conf"),
                patch.object(
                    crh, "run_command", side_effect=[succeeded, failed, failed, succeeded]
                ) as run,
                contextlib.redirect_stdout(io.StringIO()),
            ):
                self.assertEqual(
                    require("remove_all")(
                        ["DP-1:1920x1080@60"],
                        "drm.edid_firmware=DP-1:edid/edid.bin",
                        yes=True,
                    ),
                    1,
                )

            self.assertNotIn(
                ["systemctl", "reboot"],
                [call.args[0] for call in run.call_args_list],
            )

    def test_failed_remove_all_kargs_keeps_edid_files(self):
        failed = CompletedProcess([], 1, stdout="", stderr="kargs failed")
        with (
            patch.object(crh, "run_command", return_value=failed) as run,
            contextlib.redirect_stdout(io.StringIO()),
        ):
            self.assertEqual(
                require("remove_all")(
                    ["DP-1:1920x1080@60"],
                    "drm.edid_firmware=DP-1:edid/edid.bin",
                    yes=True,
                ),
                1,
            )

        self.assertEqual(run.call_args.args[0][0:2], ["rpm-ostree", "kargs"])
        self.assertFalse(
            any(call.args[0][:2] == ["sudo", "rm"] for call in run.call_args_list)
        )

    def test_interactive_remove_deletes_selected_mode_not_only_connector(self):
        mode = "DP-1:1920x1080@60"
        with (
            patch.object(crh, "choose", return_value=mode),
            patch.object(crh, "confirm", return_value=True),
            patch.object(crh, "_apply_kargs", return_value=0) as apply,
            contextlib.redirect_stdout(io.StringIO()),
        ):
            self.assertEqual(
                require("remove_interactive")([mode], "video=" + mode), 0
            )

        self.assertEqual(
            apply.call_args.args[0], [f"--delete-if-present=video={mode}"]
        )

    def test_interactive_remove_edid_mode_removes_files_after_kargs(self):
        mode = "DP-1:1920x1080@60"
        kargs = "drm.edid_firmware=DP-1:edid/edid.bin video=" + mode
        events = []
        succeeded = CompletedProcess([], 0, stdout="", stderr="")

        def record(args, **kwargs):
            events.append(args)
            return succeeded

        with (
            patch.object(crh, "choose", return_value=mode),
            patch.object(crh, "confirm", return_value=True),
            patch.object(crh, "run_command", side_effect=record),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            self.assertEqual(require("remove_interactive")([mode], kargs), 0)

        self.assertEqual(
            events[0],
            [
                "rpm-ostree",
                "kargs",
                f"--delete-if-present=video={mode}",
                "--delete-if-present=firmware_class.path=/usr/local/lib/firmware",
                f"--delete-if-present=drm.edid_firmware={mode.split(':', 1)[0]}:edid/edid.bin",
            ],
        )
        self.assertEqual(
            events[1:3],
            [
                ["sudo", "rm", "-vi", str(crh.FIRMWARE_EDID)],
                ["sudo", "rm", "-vi", str(crh.DRACUT_EDID)],
            ],
        )

    def test_direct_remove_requires_exact_mode_match(self):
        mode = "DP-1:1920x1080@60"
        with (
            patch.object(crh, "get_kargs", return_value=f"video={mode}"),
            patch.object(crh, "run_command", create=True) as run,
            contextlib.redirect_stdout(io.StringIO()),
        ):
            self.assertEqual(require("remove")(":1920x1080@60"), 1)

        run.assert_not_called()

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

    def test_dump_edid_refuses_symlink_target(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            drm_root = root / "drm"
            edid = drm_root / "card0" / "card0-DP-1" / "edid"
            edid.parent.mkdir(parents=True)
            edid.write_bytes(b"new-edid")
            crh_tmp = root / "tmp" / "crh"
            crh_tmp.mkdir(parents=True, mode=0o700)
            victim = root / "important.txt"
            victim.write_bytes(b"keep this")
            (crh_tmp / "edid.bin").symlink_to(victim)

            with (
                patch.object(crh, "DRM_ROOT", drm_root),
                patch.object(crh, "CRH_TMP", crh_tmp),
                patch.object(crh, "choose_monitor", return_value="DP-1"),
                contextlib.redirect_stdout(io.StringIO()),
                contextlib.redirect_stderr(io.StringIO()),
            ):
                self.assertEqual(require("dump_edid")(), 1)

            self.assertEqual(victim.read_bytes(), b"keep this")

    def test_add_edid_cancel_does_not_install_file(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            crh_tmp = Path(temporary_directory) / "crh"
            edited_edid = crh_tmp / "edited" / "edid.bin"
            edited_edid.parent.mkdir(parents=True)
            edited_edid.write_bytes(b"new-edid")
            with (
                patch.object(crh, "CRH_TMP", crh_tmp),
                patch.object(crh, "print_status", return_value=("", [])),
                patch.object(crh, "choose_monitor", return_value=None),
                patch.object(crh, "run_command", create=True) as run,
                contextlib.redirect_stdout(io.StringIO()),
            ):
                self.assertEqual(require("add_edid")(), 0)

        run.assert_not_called()

    def test_failed_add_edid_kargs_installs_files_first(self):
        succeeded = CompletedProcess([], 0, stdout="", stderr="")
        failed = CompletedProcess([], 1, stdout="", stderr="kargs failed")
        with tempfile.TemporaryDirectory() as temporary_directory:
            crh_tmp = Path(temporary_directory) / "crh"
            edited_edid = crh_tmp / "edited" / "edid.bin"
            edited_edid.parent.mkdir(parents=True)
            edited_edid.write_bytes(b"new-edid")
            with (
                patch.object(crh, "CRH_TMP", crh_tmp),
                patch.object(crh, "print_status", return_value=("", [])),
                patch.object(crh, "choose_monitor", return_value="DP-1"),
                patch.object(
                    crh, "run_command", side_effect=[succeeded] * 5 + [failed]
                ) as run,
                contextlib.redirect_stdout(io.StringIO()),
            ):
                self.assertEqual(require("add_edid")(), 1)

        self.assertEqual(
            [call.args[0] for call in run.call_args_list],
            [
                ["sudo", "mkdir", "-p", str(crh.FIRMWARE_EDID.parent)],
                ["sudo", "cp", str(edited_edid), str(crh.FIRMWARE_EDID)],
                ["sudo", "mkdir", "-p", str(crh.DRACUT_EDID.parent)],
                ["sudo", "touch", str(crh.DRACUT_EDID)],
                ["sudo", "tee", str(crh.DRACUT_EDID)],
                [
                    "rpm-ostree",
                    "kargs",
                    "--append-if-missing=firmware_class.path=/usr/local/lib/firmware",
                    "--append-if-missing=drm.edid_firmware=DP-1:edid/edid.bin",
                    "--append-if-missing=video=DP-1:e",
                ],
            ],
        )

    def test_eof_during_edid_placement_aborts(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            crh_tmp = Path(temporary_directory) / "crh"
            with (
                patch.object(crh, "CRH_TMP", crh_tmp),
                patch.object(crh, "print_status", return_value=("", [])),
                patch("builtins.input", side_effect=EOFError),
                patch.object(crh, "run_command") as run,
                contextlib.redirect_stdout(io.StringIO()),
                contextlib.redirect_stderr(io.StringIO()),
            ):
                self.assertEqual(require("add_edid")(), 1)

        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
