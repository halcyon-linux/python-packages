"""Tests for the nvidia-flatpak-runtime package."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

import nvidia_flatpak_runtime


def require(name: str):
    value = getattr(nvidia_flatpak_runtime, name, None)
    if value is None:
        raise AssertionError(f"nvidia_flatpak_runtime.{name} is not implemented")
    return value


class PackageTests(unittest.TestCase):
    def test_package_exposes_both_runtime_commands(self):
        project = tomllib.loads(
            (Path(__file__).parents[1] / "pyproject.toml").read_text(encoding="utf-8")
        )["project"]
        self.assertEqual(project["name"], "nvidia-flatpak-runtime")
        self.assertEqual(
            project["scripts"],
            {
                "nvidia-flatpak-runtime-sync": "nvidia_flatpak_runtime:sync_main",
                "nvidia-flatpak-runtime-notify": "nvidia_flatpak_runtime:notify_main",
            },
        )

    def test_module_is_importable(self):
        self.assertIsNotNone(importlib.util.find_spec("nvidia_flatpak_runtime"))


class RuntimeNamingTests(unittest.TestCase):
    def test_dots_become_dashes(self):
        self.assertEqual(require("flatpak_version")("580.95.05"), "580-95-05")

    def test_runtime_refs(self):
        runtime_ref = require("runtime_ref")
        self.assertEqual(
            runtime_ref("GL", "580.95.05"),
            "org.freedesktop.Platform.GL.nvidia-580-95-05",
        )
        self.assertEqual(
            runtime_ref("GL32", "580.95.05"),
            "org.freedesktop.Platform.GL32.nvidia-580-95-05",
        )


class SystemVersionTests(unittest.TestCase):
    def test_version_file_is_trimmed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "version"
            path.write_text("580.95.05\n", encoding="utf-8")
            self.assertEqual(require("system_nvidia_version")(path), "580.95.05")

    def test_missing_file_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(OSError):
                require("system_nvidia_version")(Path(tmp) / "missing")


class SyncNeededTests(unittest.TestCase):
    def test_both_runtimes_installed(self):
        with patch.object(
            nvidia_flatpak_runtime.subprocess,
            "run",
            return_value=Mock(returncode=0),
        ) as run:
            self.assertFalse(require("sync_needed")("580.95.05"))
        self.assertEqual(
            [call.args[0][3] for call in run.call_args_list],
            [
                "org.freedesktop.Platform.GL.nvidia-580-95-05",
                "org.freedesktop.Platform.GL32.nvidia-580-95-05",
            ],
        )

    def test_first_missing_runtime_is_enough(self):
        with patch.object(
            nvidia_flatpak_runtime.subprocess,
            "run",
            return_value=Mock(returncode=1),
        ) as run:
            self.assertTrue(require("sync_needed")("580.95.05"))
        self.assertEqual(run.call_count, 1)

    def test_second_missing_runtime_is_detected(self):
        with patch.object(
            nvidia_flatpak_runtime.subprocess,
            "run",
            side_effect=[Mock(returncode=0), Mock(returncode=1)],
        ):
            self.assertTrue(require("sync_needed")("580.95.05"))

    def test_missing_flatpak_counts_as_needed(self):
        with patch.object(
            nvidia_flatpak_runtime.subprocess,
            "run",
            side_effect=FileNotFoundError("flatpak"),
        ):
            self.assertTrue(require("sync_needed")("580.95.05"))


class SyncMainTests(unittest.TestCase):
    def test_check_in_sync_exits_one(self):
        with patch.object(
            nvidia_flatpak_runtime, "system_nvidia_version", return_value="580.95.05"
        ), patch.object(nvidia_flatpak_runtime, "sync_needed", return_value=False), \
             contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(require("sync_main")(["check"]), 1)
        self.assertIn(
            "NVIDIA Flatpak runtime 580.95.05 already installed", out.getvalue()
        )

    def test_check_needing_sync_exits_zero(self):
        with patch.object(
            nvidia_flatpak_runtime, "system_nvidia_version", return_value="580.95.05"
        ), patch.object(nvidia_flatpak_runtime, "sync_needed", return_value=True), \
             contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(require("sync_main")(["check"]), 0)
        self.assertIn(
            "NVIDIA Flatpak runtime 580.95.05 needs to be installed", out.getvalue()
        )

    def test_sync_installs_both_runtimes(self):
        with patch.object(
            nvidia_flatpak_runtime, "system_nvidia_version", return_value="580.95.05"
        ), patch.object(
            nvidia_flatpak_runtime.subprocess,
            "run",
            side_effect=[Mock(returncode=0), Mock(returncode=0)],
        ) as run, contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(require("sync_main")(["sync"]), 0)
        self.assertEqual(
            run.call_args_list[0].args[0],
            [
                "flatpak",
                "remote-add",
                "--system",
                "--if-not-exists",
                "flathub",
                "https://flathub.org/repo/flathub.flatpakrepo",
            ],
        )
        self.assertEqual(
            run.call_args_list[1].args[0],
            [
                "flatpak",
                "install",
                "--system",
                "--noninteractive",
                "-y",
                "flathub",
                "org.freedesktop.Platform.GL.nvidia-580-95-05",
                "org.freedesktop.Platform.GL32.nvidia-580-95-05",
            ],
        )
        self.assertIn(
            "Installing NVIDIA Flatpak runtime version 580.95.05", out.getvalue()
        )

    def test_remote_add_failure_skips_install(self):
        with patch.object(
            nvidia_flatpak_runtime, "system_nvidia_version", return_value="580.95.05"
        ), patch.object(
            nvidia_flatpak_runtime.subprocess,
            "run",
            return_value=Mock(returncode=3),
        ) as run:
            self.assertEqual(require("sync_main")(["sync"]), 3)
        self.assertEqual(run.call_count, 1)

    def test_install_failure_keeps_status(self):
        with patch.object(
            nvidia_flatpak_runtime, "system_nvidia_version", return_value="580.95.05"
        ), patch.object(
            nvidia_flatpak_runtime.subprocess,
            "run",
            side_effect=[Mock(returncode=0), Mock(returncode=5)],
        ):
            self.assertEqual(require("sync_main")(["sync"]), 5)

    def test_missing_flatpak_is_exit_127(self):
        with patch.object(
            nvidia_flatpak_runtime, "system_nvidia_version", return_value="580.95.05"
        ), patch.object(
            nvidia_flatpak_runtime.subprocess,
            "run",
            side_effect=FileNotFoundError("flatpak"),
        ), contextlib.redirect_stderr(io.StringIO()) as err:
            self.assertEqual(require("sync_main")(["sync"]), 127)
        self.assertIn("flatpak not found", err.getvalue())

    def test_unreadable_version_file_is_an_error(self):
        with patch.object(
            nvidia_flatpak_runtime,
            "NVIDIA_VERSION_FILE",
            Path("/nonexistent/version"),
        ), contextlib.redirect_stderr(io.StringIO()) as err:
            self.assertEqual(require("sync_main")(["check"]), 1)
        self.assertIn("nonexistent", err.getvalue())

    def test_unknown_action_prints_usage(self):
        with patch.object(
            nvidia_flatpak_runtime, "system_nvidia_version", return_value="580.95.05"
        ), contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(require("sync_main")(["frobnicate"]), 1)
            self.assertEqual(require("sync_main")([]), 1)
        self.assertIn("Usage:", out.getvalue())


class NotifyTests(unittest.TestCase):
    def test_notify_argv_matches_the_shell_version(self):
        self.assertEqual(
            require("notify_argv")(),
            [
                "/usr/bin/notify-send",
                "--app-name=Bazzite Nvidia Runtime Checker",
                "--expire-time=0",
                "Nvidia Flatpak Runtime Mismatch",
                "Bazzite noticed that there is an Nvidia flatpak runtime mismatch!\\n\\n"
                "Hardware acceleration will not work in Flatpak Apps before you update it.\\n",
                "--action=see_more=See more",
                "--action=update_flatpak=Update all Flatpaks",
                "--action=update_runtime_only=Update Runtime Only",
            ],
        )

    def run_notify(self, action: str, notify_code: int = 0, action_code: int = 0):
        with patch.object(
            nvidia_flatpak_runtime.subprocess,
            "run",
            side_effect=[
                Mock(returncode=notify_code, stdout=f"{action}\n"),
                Mock(returncode=action_code),
            ],
        ) as run:
            status = require("notify_main")([])
        return status, run

    def test_see_more_opens_the_docs(self):
        status, run = self.run_notify("see_more")
        self.assertEqual(status, 0)
        self.assertEqual(
            run.call_args.args[0],
            [
                "xdg-open",
                "https://docs.bazzite.gg/General/issues_and_resolutions/"
                "#flatpak-apps-have-no-hardware-acceleration-on-nvidia",
            ],
        )

    def test_update_flatpak_launches_bazaar(self):
        status, run = self.run_notify("update_flatpak")
        self.assertEqual(status, 0)
        self.assertEqual(run.call_args.args[0], ["/usr/bin/bazaar"])

    def test_update_runtime_only_runs_yafti(self):
        status, run = self.run_notify("update_runtime_only")
        self.assertEqual(status, 0)
        self.assertEqual(
            run.call_args.args[0],
            [
                "/usr/bin/yafti_gtk.py",
                "/usr/share/yafti/yafti.yml",
                "--action-id",
                "update-nvidia-runtime",
            ],
        )

    def test_dismissed_notification_does_nothing(self):
        status, run = self.run_notify("")
        self.assertEqual(status, 0)
        self.assertEqual(run.call_count, 1)

    def test_action_status_is_returned(self):
        status, _ = self.run_notify("see_more", action_code=2)
        self.assertEqual(status, 2)

    def test_notify_send_failure_is_returned(self):
        with patch.object(
            nvidia_flatpak_runtime.subprocess,
            "run",
            return_value=Mock(returncode=4, stdout=""),
        ) as run:
            self.assertEqual(require("notify_main")([]), 4)
        self.assertEqual(run.call_count, 1)

    def test_missing_notify_send_is_exit_127(self):
        with patch.object(
            nvidia_flatpak_runtime.subprocess,
            "run",
            side_effect=FileNotFoundError("notify-send"),
        ), contextlib.redirect_stderr(io.StringIO()) as err:
            self.assertEqual(require("notify_main")([]), 127)
        self.assertIn("notify-send not found", err.getvalue())


if __name__ == "__main__":
    unittest.main()
