"""Tests for the user-setup package."""

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

import user_setup


def require(name: str):
    value = getattr(user_setup, name, None)
    if value is None:
        raise AssertionError(f"user_setup.{name} is not implemented")
    return value


class PackageTests(unittest.TestCase):
    def test_package_exposes_both_setup_commands(self):
        project = tomllib.loads(
            (Path(__file__).parents[1] / "pyproject.toml").read_text(encoding="utf-8")
        )["project"]
        self.assertEqual(project["name"], "user-setup")
        self.assertEqual(
            project["scripts"],
            {
                "user-setup": "user_setup:main",
                "privileged-user-setup": "user_setup:privileged_main",
            },
        )

    def test_module_is_importable(self):
        self.assertIsNotNone(importlib.util.find_spec("user_setup"))


class ReadImageInfoTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.path = Path(self._tmp.name) / "image-info.json"

    def test_reads_name_and_fedora_version(self):
        self.path.write_text(
            json.dumps({"image-name": "bazzfin-nvidia", "fedora-version": "44"}),
            encoding="utf-8",
        )
        self.assertEqual(
            require("read_image_info")(self.path), ("bazzfin-nvidia", "44")
        )

    def test_missing_file_raises_user_setup_error(self):
        with self.assertRaises(require("UserSetupError")):
            require("read_image_info")(self.path)


class ConfigDirTests(unittest.TestCase):
    def test_xdg_data_home_wins(self):
        with patch.dict(os.environ, {"XDG_DATA_HOME": "/data"}):
            self.assertEqual(
                require("config_dir")(Path("/home/alice")), Path("/data/bazzite")
            )

    def test_defaults_to_local_share(self):
        with patch.dict(os.environ, {"XDG_DATA_HOME": ""}):
            self.assertEqual(
                require("config_dir")(Path("/home/alice")),
                Path("/home/alice/.local/share/bazzite"),
            )


class LegacyMarkerTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.home = Path(self._tmp.name)
        self.config = self.home / ".local/share/bazzite"
        self.config.mkdir(parents=True)

    def test_markers_are_moved_into_the_config_dir(self):
        (self.home / ".bazzite-configured").write_text("58\n", encoding="utf-8")
        (self.home / ".bazzite-configured-fedora-version").write_text(
            "44\n", encoding="utf-8"
        )
        require("migrate_legacy_markers")(
            self.home, self.config / "version", self.config / "fedora_version"
        )
        self.assertEqual((self.config / "version").read_text(), "58\n")
        self.assertEqual((self.config / "fedora_version").read_text(), "44\n")
        self.assertFalse((self.home / ".bazzite-configured").exists())

    def test_no_markers_is_a_noop(self):
        require("migrate_legacy_markers")(
            self.home, self.config / "version", self.config / "fedora_version"
        )
        self.assertFalse((self.config / "version").exists())


class AlreadyConfiguredTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.config = Path(self._tmp.name)
        self.version_file = self.config / "version"
        self.fedora_file = self.config / "fedora_version"
        self.image_file = self.config / "image_name"

    def write_all(self):
        self.version_file.write_text("58\n", encoding="utf-8")
        self.fedora_file.write_text("44\n", encoding="utf-8")
        self.image_file.write_text("bazzfin-nvidia\n", encoding="utf-8")

    def test_matching_state_is_configured(self):
        self.write_all()
        self.assertTrue(
            require("already_configured")(
                self.version_file, self.fedora_file, self.image_file,
                "44", "bazzfin-nvidia",
            )
        )

    def test_missing_files_reconfigure(self):
        self.assertFalse(
            require("already_configured")(
                self.version_file, self.fedora_file, self.image_file,
                "44", "bazzfin-nvidia",
            )
        )

    def test_version_bump_reconfigures(self):
        self.write_all()
        self.version_file.write_text("57\n", encoding="utf-8")
        self.assertFalse(
            require("already_configured")(
                self.version_file, self.fedora_file, self.image_file,
                "44", "bazzfin-nvidia",
            )
        )

    def test_new_fedora_version_reconfigures(self):
        self.write_all()
        self.assertFalse(
            require("already_configured")(
                self.version_file, self.fedora_file, self.image_file,
                "45", "bazzfin-nvidia",
            )
        )


class PrivilegedCallTests(unittest.TestCase):
    def test_pkexec_argv_and_status(self):
        with patch.object(
            user_setup.subprocess, "run", return_value=Mock(returncode=2)
        ) as run:
            self.assertEqual(require("run_privileged_setup")("alice"), 2)
        self.assertEqual(
            run.call_args.args[0],
            ["pkexec", "/usr/bin/privileged-user-setup", "alice"],
        )

    def test_missing_pkexec_is_exit_127(self):
        with patch.object(
            user_setup.subprocess, "run", side_effect=FileNotFoundError("pkexec")
        ):
            self.assertEqual(require("run_privileged_setup")("alice"), 127)


class TemplatesDirTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.home = Path(self._tmp.name)

    def test_xdg_user_dir_output_wins(self):
        with patch.object(
            user_setup.subprocess,
            "run",
            return_value=Mock(returncode=0, stdout="/data/Templates\n"),
        ):
            self.assertEqual(
                require("templates_dir")(self.home), Path("/data/Templates")
            )

    def test_empty_output_falls_back(self):
        with patch.object(
            user_setup.subprocess,
            "run",
            return_value=Mock(returncode=0, stdout=""),
        ):
            self.assertEqual(
                require("templates_dir")(self.home), self.home / "Templates"
            )

    def test_failure_falls_back(self):
        with patch.object(
            user_setup.subprocess,
            "run",
            return_value=Mock(returncode=1, stdout="/data/Templates\n"),
        ):
            self.assertEqual(
                require("templates_dir")(self.home), self.home / "Templates"
            )

    def test_home_output_falls_back(self):
        with patch.object(
            user_setup.subprocess,
            "run",
            return_value=Mock(returncode=0, stdout=f"{self.home}\n"),
        ):
            self.assertEqual(
                require("templates_dir")(self.home), self.home / "Templates"
            )

    def test_missing_binary_falls_back(self):
        with patch.object(
            user_setup.subprocess, "run", side_effect=FileNotFoundError("xdg-user-dir")
        ):
            self.assertEqual(
                require("templates_dir")(self.home), self.home / "Templates"
            )


class LinkTemplatesTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.source_dir = self.root / "sources"
        self.source_dir.mkdir()
        self.target_dir = self.root / "Templates"

    def test_existing_sources_are_symlinked(self):
        source = self.source_dir / "vkBasalt.conf"
        source.write_text("x", encoding="utf-8")
        missing = self.source_dir / "missing.conf"
        require("link_templates")(self.target_dir, (source, missing))
        link = self.target_dir / "vkBasalt.conf"
        self.assertTrue(link.is_symlink())
        self.assertEqual(link.resolve(), source.resolve())
        self.assertFalse((self.target_dir / "missing.conf").exists())

    def test_existing_targets_are_kept(self):
        source = self.source_dir / "vkBasalt.conf"
        source.write_text("x", encoding="utf-8")
        self.target_dir.mkdir()
        existing = self.target_dir / "vkBasalt.conf"
        existing.write_text("mine", encoding="utf-8")
        require("link_templates")(self.target_dir, (source,))
        self.assertFalse(existing.is_symlink())
        self.assertEqual(existing.read_text(), "mine")


class SystemdEscapeTests(unittest.TestCase):
    def test_output_is_trimmed(self):
        with patch.object(
            user_setup.subprocess,
            "run",
            return_value=Mock(returncode=0, stdout="alice\n"),
        ):
            self.assertEqual(require("systemd_escape")("alice"), "alice")

    def test_missing_binary_yields_empty(self):
        with patch.object(
            user_setup.subprocess, "run", side_effect=FileNotFoundError("systemd-escape")
        ):
            self.assertEqual(require("systemd_escape")("alice"), "")


class PrivilegedMainTests(unittest.TestCase):
    def test_runs_both_best_effort_steps(self):
        with patch.object(
            user_setup.subprocess, "run", return_value=Mock(returncode=0)
        ) as run, patch.object(user_setup, "systemd_escape", return_value="alice"), \
             patch.object(user_setup.grp, "getgrnam", side_effect=KeyError("libvirt")):
            self.assertEqual(require("privileged_main")(["alice"]), 0)
        self.assertEqual(
            [call.args[0] for call in run.call_args_list],
            [
                ["timedatectl", "set-ntp", "true"],
                ["tailscale", "set", "--operator=alice"],
            ],
        )

    def test_libvirt_group_adds_user(self):
        with patch.object(
            user_setup.subprocess, "run", return_value=Mock(returncode=0)
        ) as run, patch.object(user_setup, "systemd_escape", return_value="alice"), \
             patch.object(user_setup.grp, "getgrnam", return_value=Mock()):
            self.assertEqual(require("privileged_main")(["alice"]), 0)
        self.assertEqual(
            run.call_args.args[0], ["usermod", "-aG", "libvirt", "alice"]
        )

    def test_usermod_status_is_returned(self):
        with patch.object(user_setup, "run_best_effort", return_value=2) as run, \
             patch.object(user_setup.grp, "getgrnam", return_value=Mock()):
            self.assertEqual(require("privileged_main")(["alice"]), 2)
        self.assertEqual(run.call_args.args[0], ["usermod", "-aG", "libvirt", "alice"])

    def test_failing_steps_do_not_abort(self):
        with patch.object(user_setup, "run_best_effort", return_value=1) as run, \
             patch.object(user_setup, "systemd_escape", return_value="alice"), \
             patch.object(user_setup.grp, "getgrnam", side_effect=KeyError("libvirt")):
            self.assertEqual(require("privileged_main")(["alice"]), 0)
        self.assertEqual(run.call_count, 2)


class MainTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.home = Path(self._tmp.name)
        self.config = self.home / ".local/share/bazzite"

    def test_low_euid_exits_early(self):
        with patch.object(user_setup.os, "geteuid", return_value=999), \
             patch.object(user_setup, "read_image_info") as read, \
             contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(require("main")([]), 0)
        read.assert_not_called()
        self.assertIn("unsupported user", out.getvalue())

    def test_matching_state_skips_privileged_step(self):
        self.config.mkdir(parents=True)
        (self.config / "version").write_text("58\n", encoding="utf-8")
        (self.config / "fedora_version").write_text("44\n", encoding="utf-8")
        (self.config / "image_name").write_text("bazzfin-nvidia\n", encoding="utf-8")
        with patch.object(user_setup.os, "geteuid", return_value=1000), \
             patch.object(user_setup.Path, "home", return_value=self.home), \
             patch.object(
                 user_setup,
                 "read_image_info",
                 return_value=("bazzfin-nvidia", "44"),
             ), \
             patch.dict(os.environ, {"XDG_DATA_HOME": ""}), \
             patch.object(user_setup, "run_privileged_setup") as privileged, \
             contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(require("main")([]), 0)
        privileged.assert_not_called()
        self.assertIn("User setup v58 has already run. Exiting.", out.getvalue())

    def test_fresh_run_calls_privileged_helper_and_writes_state(self):
        with patch.object(user_setup.os, "geteuid", return_value=1000), \
             patch.object(user_setup.Path, "home", return_value=self.home), \
             patch.object(
                 user_setup,
                 "read_image_info",
                 return_value=("bazzfin-nvidia", "44"),
             ), \
             patch.dict(os.environ, {"XDG_DATA_HOME": "", "USER": "alice"}), \
             patch.object(
                 user_setup, "run_privileged_setup", return_value=0
             ) as privileged, \
             patch.object(user_setup, "templates_dir") as templates, \
             patch.object(user_setup, "link_templates") as link:
            self.assertEqual(require("main")([]), 0)
        privileged.assert_called_once_with("alice")
        templates.assert_called_once_with(self.home)
        link.assert_called_once_with(templates.return_value)
        self.assertEqual((self.config / "version").read_text(), "58\n")
        self.assertEqual((self.config / "fedora_version").read_text(), "44\n")
        self.assertEqual((self.config / "image_name").read_text(), "bazzfin-nvidia\n")

    def test_failed_privileged_helper_leaves_state_unwritten(self):
        with patch.object(user_setup.os, "geteuid", return_value=1000), \
             patch.object(user_setup.Path, "home", return_value=self.home), \
             patch.object(
                 user_setup,
                 "read_image_info",
                 return_value=("bazzfin-nvidia", "44"),
             ), \
             patch.dict(os.environ, {"XDG_DATA_HOME": "", "USER": "alice"}), \
             patch.object(user_setup, "run_privileged_setup", return_value=3), \
             patch.object(user_setup, "link_templates") as link:
            self.assertEqual(require("main")([]), 3)
        link.assert_not_called()
        self.assertFalse((self.config / "version").exists())

    def test_unreadable_image_info_is_an_error(self):
        with patch.object(user_setup.os, "geteuid", return_value=1000), \
             patch.object(user_setup.Path, "home", return_value=self.home), \
             patch.dict(os.environ, {"XDG_DATA_HOME": ""}), \
             patch.object(
                 user_setup,
                 "read_image_info",
                 side_effect=require("UserSetupError")("boom"),
             ), \
             contextlib.redirect_stderr(io.StringIO()) as err:
            self.assertEqual(require("main")([]), 1)
        self.assertIn("boom", err.getvalue())

    def test_legacy_markers_are_migrated_before_the_gate(self):
        self.home.joinpath(".bazzite-configured").write_text("57\n", encoding="utf-8")
        with patch.object(user_setup.os, "geteuid", return_value=1000), \
             patch.object(user_setup.Path, "home", return_value=self.home), \
             patch.object(
                 user_setup,
                 "read_image_info",
                 return_value=("bazzfin-nvidia", "44"),
             ), \
             patch.dict(os.environ, {"XDG_DATA_HOME": "", "USER": "alice"}), \
             patch.object(user_setup, "run_privileged_setup", return_value=0), \
             patch.object(user_setup, "templates_dir", return_value=self.home), \
             patch.object(user_setup, "link_templates"):
            self.assertEqual(require("main")([]), 0)
        self.assertEqual((self.config / "version").read_text(), "58\n")


if __name__ == "__main__":
    unittest.main()
