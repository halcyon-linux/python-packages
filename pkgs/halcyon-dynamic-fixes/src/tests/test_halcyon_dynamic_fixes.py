"""Tests for the halcyon-dynamic-fixes package."""

from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

import halcyon_dynamic_fixes


def require(name: str):
    value = getattr(halcyon_dynamic_fixes, name, None)
    if value is None:
        raise AssertionError(f"halcyon_dynamic_fixes.{name} is not implemented")
    return value


XE_IN_USE = "xe 2797568 1 i915 Live 0x0000000000000000\n"
I915_UNUSED = "i915 4407296 0 - Live 0x0000000000000000\n"
AMD = "amdgpu 12345678 12 - Live 0x0000000000000000\n"


class PackageTests(unittest.TestCase):
    def test_package_exposes_only_the_dynamic_fixes_command(self):
        project = tomllib.loads(
            (Path(__file__).parents[1] / "pyproject.toml").read_text(encoding="utf-8")
        )["project"]
        self.assertEqual(project["name"], "halcyon-dynamic-fixes")
        self.assertEqual(
            project["scripts"], {"halcyon-dynamic-fixes": "halcyon_dynamic_fixes:main"}
        )

    def test_module_is_importable(self):
        self.assertIsNotNone(importlib.util.find_spec("halcyon_dynamic_fixes"))


class ModuleDetectionTests(unittest.TestCase):
    def test_in_use_intel_modules_are_detected(self):
        in_use = require("intel_gpu_in_use")
        self.assertTrue(in_use(XE_IN_USE))
        self.assertTrue(in_use("i915 4407296 2 - Live 0x0\n"))

    def test_zero_use_count_is_not_in_use(self):
        in_use = require("intel_gpu_in_use")
        self.assertFalse(in_use(I915_UNUSED))
        self.assertFalse(in_use("xe 1 0 - Live 0x0\n"))

    def test_other_modules_are_ignored(self):
        self.assertFalse(require("intel_gpu_in_use")(AMD))
        self.assertFalse(require("intel_gpu_in_use")(""))

    def test_malformed_count_is_ignored(self):
        self.assertFalse(require("intel_gpu_in_use")("xe 123 abc - Live 0x0\n"))

    def test_unreadable_modules_file_reads_as_empty(self):
        with patch.object(
            halcyon_dynamic_fixes.Path, "read_text", side_effect=OSError("boom")
        ):
            self.assertEqual(require("read_modules")(), "")


class EnvFileTests(unittest.TestCase):
    def test_env_file_lives_under_home(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = require("env_file")(Path(tmp))
            self.assertEqual(
                path,
                Path(tmp) / ".config/environment.d" / "intel-gtk-fix.conf",
            )

    def test_env_file_defaults_to_path_home(self):
        with patch.dict(os.environ, {"HOME": "/home/tester"}):
            self.assertEqual(
                require("env_file")(),
                Path("/home/tester/.config/environment.d/intel-gtk-fix.conf"),
            )


class MainTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.home = Path(self._tmp.name)
        self.target = halcyon_dynamic_fixes.env_file(self.home)

    def run_main(self, modules: str):
        with patch.object(halcyon_dynamic_fixes, "env_file", return_value=self.target), \
             patch.object(halcyon_dynamic_fixes, "read_modules", return_value=modules), \
             patch.object(halcyon_dynamic_fixes, "daemon_reload",
                          return_value=0) as reload:
            status = require("main")([])
        return status, reload

    def test_intel_gpu_writes_fix_and_reloads(self):
        status, reload = self.run_main(XE_IN_USE)
        self.assertEqual(status, 0)
        reload.assert_called_once_with()
        self.assertEqual(self.target.read_text(encoding="utf-8"), "GSK_RENDERER=gl\n")

    def test_intel_gpu_with_existing_fix_does_nothing(self):
        self.target.parent.mkdir(parents=True)
        self.target.write_text("GSK_RENDERER=gl\n", encoding="utf-8")
        status, reload = self.run_main(XE_IN_USE)
        self.assertEqual(status, 0)
        reload.assert_not_called()

    def test_no_intel_gpu_removes_fix_and_reloads(self):
        self.target.parent.mkdir(parents=True)
        self.target.write_text("GSK_RENDERER=gl\n", encoding="utf-8")
        status, reload = self.run_main(AMD)
        self.assertEqual(status, 0)
        reload.assert_called_once_with()
        self.assertFalse(self.target.exists())

    def test_no_intel_gpu_without_fix_does_nothing(self):
        status, reload = self.run_main(AMD)
        self.assertEqual(status, 0)
        reload.assert_not_called()
        self.assertFalse(self.target.exists())

    def test_daemon_reload_status_is_passed_through(self):
        with patch.object(halcyon_dynamic_fixes, "env_file", return_value=self.target), \
             patch.object(halcyon_dynamic_fixes, "read_modules", return_value=XE_IN_USE), \
             patch.object(halcyon_dynamic_fixes.subprocess, "run",
                          return_value=Mock(returncode=1)):
            self.assertEqual(require("main")([]), 1)


if __name__ == "__main__":
    unittest.main()
