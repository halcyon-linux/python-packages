"""Tests for the ublue-motd package."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

import ublue_motd


def require(name: str):
    value = getattr(ublue_motd, name, None)
    if value is None:
        raise AssertionError(f"ublue_motd.{name} is not implemented")
    return value


class PackageTests(unittest.TestCase):
    def test_package_exposes_only_ublue_motd_command(self):
        project = tomllib.loads(
            (Path(__file__).parents[1] / "pyproject.toml").read_text(encoding="utf-8")
        )["project"]
        self.assertEqual(project["name"], "ublue-motd")
        self.assertEqual(project["scripts"], {"ublue-motd": "ublue_motd:main"})

    def test_module_is_importable(self):
        self.assertIsNotNone(importlib.util.find_spec("ublue_motd"))


class ImageInfoTests(unittest.TestCase):
    def test_reads_fields_and_strips_ostree_prefix(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp, "image-info.json")
            path.write_text(json.dumps({
                "image-ref": "ostree-image-signed:docker://ghcr.io/halcyon-linux/bazzfin-nvidia",
                "image-branch": "stable",
                "version": "44.20261017",
            }))
            info = require("read_image_info")(path)
        self.assertEqual(
            require("strip_image_ref")(info["image-ref"]),
            "ghcr.io/halcyon-linux/bazzfin-nvidia",
        )
        self.assertEqual(info["image-branch"], "stable")
        self.assertEqual(info["version"], "44.20261017")

    def test_missing_or_corrupt_file_returns_empty_dict(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(require("read_image_info")(Path(tmp, "missing.json")), {})
            bad = Path(tmp, "bad.json")
            bad.write_text("{not json")
            self.assertEqual(require("read_image_info")(bad), {})


class BootStatusTests(unittest.TestCase):
    def test_healthy_green_yellow_and_missing(self):
        lines = require("boot_status_lines")
        with tempfile.TemporaryDirectory() as tmp:
            green = Path(tmp, "green")
            green.write_text("boot status is GREEN\n")
            self.assertEqual(lines(green), ["󰟀 `Boot Status: Healthy 󰄳`"])
            yellow = Path(tmp, "yellow")
            yellow.write_text("boot status is YELLOW\nwarning one\nmore\n")
            self.assertEqual(lines(yellow), ["󰟀 `boot status is YELLOW warning one more`"])
            self.assertEqual(lines(Path(tmp, "missing")), [])


class StagedUpdateTests(unittest.TestCase):
    def test_detects_staged_deployment_only(self):
        staged = json.dumps({"deployments": [{"booted": True, "staged": False}, {"staged": True}]})
        self.assertEqual(len(require("staged_update_lines")(staged)), 1)
        not_staged = json.dumps({"deployments": [{"booted": True, "staged": False}]})
        self.assertEqual(require("staged_update_lines")(not_staged), [])
        self.assertEqual(require("staged_update_lines")(""), [])
        self.assertEqual(require("staged_update_lines")("not json"), [])


class RpmOstreeStatusTests(unittest.TestCase):
    def test_success_returns_stdout_and_pins_timeout(self):
        result = Mock(returncode=0, stdout='{"deployments": []}')
        with patch.object(ublue_motd.subprocess, "run", return_value=result) as run:
            self.assertEqual(require("rpm_ostree_status")(), '{"deployments": []}')
        self.assertEqual(run.call_args.kwargs["timeout"], ublue_motd.RPM_OSTREE_TIMEOUT)

    def test_nonzero_returncode_and_slow_or_missing_binary_yield_empty(self):
        with patch.object(ublue_motd.subprocess, "run", return_value=Mock(returncode=1, stdout="err")):
            self.assertEqual(require("rpm_ostree_status")(), "")
        for error in (ublue_motd.subprocess.TimeoutExpired("rpm-ostree", 1.5), FileNotFoundError("rpm-ostree")):
            with patch.object(ublue_motd.subprocess, "run", side_effect=error):
                self.assertEqual(require("rpm_ostree_status")(), "")


class DiskTests(unittest.TestCase):
    def test_percent_matches_df_semantics(self):
        fake = os.statvfs_result((4096, 4096, 1000, 100, 50, 0, 0, 0, 0, 255))
        with patch.object(ublue_motd.os, "statvfs", return_value=fake):
            self.assertEqual(require("disk_usage_percent")("/"), 95)

    def test_prefers_sysroot_when_root_is_a_composefs_overlay(self):
        fake = os.statvfs_result((4096, 4096, 1000, 100, 800, 0, 0, 0, 0, 255))
        with patch.object(ublue_motd.os.path, "ismount", side_effect=lambda p: p == "/sysroot"), \
             patch.object(ublue_motd.os, "statvfs", return_value=fake) as statvfs:
            self.assertEqual(require("disk_usage_percent")(), 53)
        statvfs.assert_called_once_with("/sysroot")

    def test_uses_root_when_sysroot_is_not_a_mount(self):
        fake = os.statvfs_result((4096, 4096, 1000, 100, 50, 0, 0, 0, 0, 255))
        with patch.object(ublue_motd.os.path, "ismount", return_value=False), \
             patch.object(ublue_motd.os, "statvfs", return_value=fake) as statvfs:
            self.assertEqual(require("disk_usage_percent")(), 95)
        statvfs.assert_called_once_with("/")

    def test_warning_only_at_threshold(self):
        self.assertEqual(require("disk_lines")(89), [])
        self.assertEqual(len(require("disk_lines")(90)), 1)


class NvidiaTests(unittest.TestCase):
    NVRM = (
        "NVRM version: NVIDIA UNIX Open Kernel Module for x86_64  "
        "590.48.01  Release Build  (dvs-builder@build)  Tue Jan 1 00:00:00 UTC 2026\n"
    )

    def test_parses_version_and_tolerates_absence(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp, "version")
            path.write_text(self.NVRM)
            self.assertEqual(require("nvidia_version")(path), "590.48.01")
            self.assertEqual(require("nvidia_version")(Path(tmp, "missing")), "")

    def test_system_line_includes_nvidia_only_when_present(self):
        line = require("system_line")
        self.assertEqual(line("7.2.7-ogc1.1.fc44", "590.48.01"),
                         "󰒓 `Kernel 7.2.7-ogc1.1.fc44 · NVIDIA 590.48.01`")
        self.assertEqual(line("7.2.7-ogc1.1.fc44", ""), "󰒓 `Kernel 7.2.7-ogc1.1.fc44`")


class TipTests(unittest.TestCase):
    def test_picks_only_nonempty_lines_and_tolerates_absence(self):
        with tempfile.TemporaryDirectory() as tmp:
            tips = Path(tmp)
            (tips / "10-a.md").write_text("first\n\n  second  \n")
            (tips / "20-b.md").write_text("third\n")
            seen = {require("pick_tip")(tips) for _ in range(50)}
            self.assertTrue(seen)
            self.assertTrue(seen <= {"first", "second", "third"})
            self.assertEqual(require("pick_tip")(Path(tmp, "missing")), "")


class RenderTests(unittest.TestCase):
    def test_substitutes_known_vars_and_leaves_unknown(self):
        out = require("render")(
            "A ${MOTD_IMAGE_NAME} B $MOTD_TIP C ${UNKNOWN}",
            {"MOTD_IMAGE_NAME": "img", "MOTD_TIP": "tip"},
        )
        self.assertEqual(out, "A img B tip C ${UNKNOWN}")


class BannerTests(unittest.TestCase):
    def test_assembles_image_status_system_and_tip(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "image.json").write_text(json.dumps({
                "image-ref": "ostree-image-signed:docker://ghcr.io/x/y",
                "image-branch": "stable",
                "version": "44.1",
            }))
            (tmp / "template.md").write_text(
                "${MOTD_IMAGE_NAME}:${MOTD_IMAGE_BRANCH}${MOTD_IMAGE_BUILD}|"
                "${MOTD_STATUS}|${MOTD_SYSTEM}|${MOTD_TIP}"
            )
            (tmp / "tips").mkdir()
            (tmp / "tips" / "10.md").write_text("the tip\n")
            env = {
                "MOTD_IMAGE_INFO_FILE": str(tmp / "image.json"),
                "MOTD_TEMPLATE_FILE": str(tmp / "template.md"),
                "MOTD_TIP_DIRECTORY": str(tmp / "tips"),
            }
            with patch.dict(os.environ, env, clear=False), \
                 patch.object(ublue_motd, "boot_status_lines", return_value=[]), \
                 patch.object(ublue_motd, "rpm_ostree_status", return_value=""), \
                 patch.object(ublue_motd, "disk_usage_percent", return_value=10), \
                 patch.object(ublue_motd, "nvidia_version", return_value="590.48.01"), \
                 patch.object(ublue_motd.os, "uname", return_value=Mock(release="6.1")):
                text = require("banner")()
        self.assertEqual(text, "ghcr.io/x/y:stable (build 44.1)||󰒓 `Kernel 6.1 · NVIDIA 590.48.01`|the tip")

    def test_missing_template_falls_back_and_missing_image_stays_silent(self):
        env = {"MOTD_TEMPLATE_FILE": "/nonexistent/template.md",
               "MOTD_IMAGE_INFO_FILE": "/nonexistent/image.json",
               "MOTD_TIP_DIRECTORY": "/nonexistent/tips"}
        with patch.dict(os.environ, env, clear=False), \
             patch.object(ublue_motd, "boot_status_lines", return_value=[]), \
             patch.object(ublue_motd, "rpm_ostree_status", return_value=""):
            text = require("banner")()
        self.assertIn("Welcome to Halcyon", text)

    def test_template_read_failure_falls_back(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "template.md").write_text("${MOTD_IMAGE_NAME}")
            real_read_text = Path.read_text

            def flaky(self, *args, **kwargs):
                if self == tmp / "template.md":
                    raise OSError("boom")
                return real_read_text(self, *args, **kwargs)

            env = {"MOTD_TEMPLATE_FILE": str(tmp / "template.md"),
                   "MOTD_IMAGE_INFO_FILE": "/nonexistent/image.json",
                   "MOTD_TIP_DIRECTORY": "/nonexistent/tips"}
            with patch.dict(os.environ, env, clear=False), \
                 patch.object(ublue_motd.Path, "read_text", flaky), \
                 patch.object(ublue_motd, "boot_status_lines", return_value=[]), \
                 patch.object(ublue_motd, "rpm_ostree_status", return_value=""):
                text = require("banner")()
        self.assertIn("Welcome to Halcyon", text)


class CliTests(unittest.TestCase):
    def test_toggle_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp, \
             patch.dict(os.environ, {"XDG_CONFIG_HOME": tmp}, clear=False):
            flag = require("disable_flag_path")()
            self.assertEqual(require("main")(["toggle"]), 0)
            self.assertTrue(flag.exists())
            self.assertEqual(require("main")(["toggle"]), 0)
            self.assertFalse(flag.exists())

    def test_banner_silent_when_flag_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "no-show-user-motd").touch()
            with patch.dict(os.environ, {"XDG_CONFIG_HOME": tmp}, clear=False), \
                 contextlib.redirect_stdout(io.StringIO()) as out:
                self.assertEqual(require("main")([]), 0)
            self.assertEqual(out.getvalue(), "")

    def test_banner_silent_for_root(self):
        with patch.object(ublue_motd.os, "geteuid", return_value=0), \
             contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(require("main")([]), 0)
        self.assertEqual(out.getvalue(), "")

    def test_show_banner_prints_markdown_without_glow(self):
        with patch.object(ublue_motd.shutil, "which", return_value=None), \
             contextlib.redirect_stdout(io.StringIO()) as out:
            require("show_banner")("hello ${x}")
        self.assertEqual(out.getvalue(), "hello ${x}\n")

    def test_show_banner_glow_pins_width_and_falls_back_on_error(self):
        with patch.object(ublue_motd.shutil, "which", return_value="/usr/bin/glow"), \
             patch.object(ublue_motd, "sys", Mock(stdout=Mock(isatty=lambda: True))), \
             patch.object(ublue_motd.shutil, "get_terminal_size", return_value=os.terminal_size((120, 40))), \
             patch.object(ublue_motd.subprocess, "run", return_value=Mock(returncode=0)) as run:
            require("show_banner")("hi")
        self.assertEqual(run.call_args.args[0], ["glow", "-w", "120", "-"])
        self.assertEqual(run.call_args.kwargs["input"], "hi")

        with patch.object(ublue_motd.shutil, "which", return_value="/usr/bin/glow"), \
             patch.object(ublue_motd, "sys", Mock(stdout=Mock(isatty=lambda: True))), \
             patch.object(ublue_motd.subprocess, "run", return_value=Mock(returncode=1)), \
             contextlib.redirect_stdout(io.StringIO()) as out:
            require("show_banner")("hi")
        self.assertEqual(out.getvalue(), "hi\n")

    def test_toggle_without_home_errors_cleanly(self):
        with patch.dict(os.environ, {}, clear=True), \
             contextlib.redirect_stderr(io.StringIO()) as err:
            self.assertEqual(require("main")(["toggle"]), 1)
        self.assertTrue(err.getvalue())

    def test_banner_without_home_renders(self):
        with patch.dict(os.environ, {}, clear=True), \
             patch.object(ublue_motd, "show_banner") as show, \
             patch.object(ublue_motd, "banner", return_value="text"):
            self.assertEqual(require("main")([]), 0)
        show.assert_called_once_with("text")


if __name__ == "__main__":
    unittest.main()
