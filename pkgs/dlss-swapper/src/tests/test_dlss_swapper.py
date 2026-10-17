"""Tests for the dlss-swapper package."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import os
import sys
import tomllib
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

import dlss_swapper


def require(name: str):
    value = getattr(dlss_swapper, name, None)
    if value is None:
        raise AssertionError(f"dlss_swapper.{name} is not implemented")
    return value


PRESET_EXPECTED = {
    "DXVK_NVAPI_DRS_NGX_DLSS_RR_OVERRIDE": "on",
    "DXVK_NVAPI_DRS_NGX_DLSS_SR_OVERRIDE": "on",
    "DXVK_NVAPI_DRS_NGX_DLSS_FG_OVERRIDE": "on",
    "DXVK_NVAPI_DRS_NGX_DLSS_RR_OVERRIDE_RENDER_PRESET_SELECTION": "render_preset_latest",
    "DXVK_NVAPI_DRS_NGX_DLSS_SR_OVERRIDE_RENDER_PRESET_SELECTION": "render_preset_latest",
}


class PackageTests(unittest.TestCase):
    def test_package_exposes_both_wrappers(self):
        project = tomllib.loads(
            (Path(__file__).parents[1] / "pyproject.toml").read_text(encoding="utf-8")
        )["project"]
        self.assertEqual(project["name"], "dlss-swapper")
        self.assertEqual(
            project["scripts"],
            {
                "dlss-swapper": "dlss_swapper:main",
                "dlss-swapper-dll": "dlss_swapper:dll_main",
            },
        )

    def test_module_is_importable(self):
        self.assertIsNotNone(importlib.util.find_spec("dlss_swapper"))


class EnvironmentTests(unittest.TestCase):
    def test_preset_environment_matches_the_shell_exports(self):
        self.assertEqual(require("PRESET_ENV"), PRESET_EXPECTED)

    def test_ngx_updater_is_a_separate_switch(self):
        self.assertEqual(require("NGX_UPDATER_ENV"), {"PROTON_ENABLE_NGX_UPDATER": "1"})


class ExecWithTests(unittest.TestCase):
    def test_no_arguments_exits_zero_without_exec(self):
        with patch.object(dlss_swapper.os, "execvpe") as execvpe:
            self.assertEqual(require("exec_with")(PRESET_EXPECTED, []), 0)
        execvpe.assert_not_called()

    def test_command_is_exec_with_overrides_in_environment(self):
        with patch.dict(os.environ, {}), \
             patch.object(dlss_swapper.os, "execvpe") as execvpe:
            self.assertEqual(
                require("exec_with")(PRESET_EXPECTED, ["game.sh", "--flag"]), 0
            )
            file, args, environment = execvpe.call_args.args
            snapshot = dict(environment)
        self.assertEqual(file, "game.sh")
        self.assertEqual(args, ["game.sh", "--flag"])
        for key, value in PRESET_EXPECTED.items():
            self.assertEqual(snapshot[key], value)

    def test_missing_command_is_exit_127(self):
        with patch.dict(os.environ, {}), \
             patch.object(
                 dlss_swapper.os, "execvpe",
                 side_effect=FileNotFoundError("game.sh"),
             ):
            with contextlib.redirect_stderr(io.StringIO()) as err:
                self.assertEqual(
                    require("exec_with")(PRESET_EXPECTED, ["game.sh"]), 127
                )
        self.assertIn("command not found", err.getvalue())

    def test_not_executable_command_is_exit_126(self):
        with patch.dict(os.environ, {}), \
             patch.object(
                 dlss_swapper.os, "execvpe",
                 side_effect=PermissionError("game.sh"),
             ):
            with contextlib.redirect_stderr(io.StringIO()) as err:
                self.assertEqual(
                    require("exec_with")(PRESET_EXPECTED, ["game.sh"]), 126
                )
        self.assertIn("permission denied", err.getvalue())


class MainTests(unittest.TestCase):
    def test_main_enables_the_ngx_updater(self):
        with patch.dict(os.environ, {}), \
             patch.object(dlss_swapper.os, "execvpe") as execvpe:
            self.assertEqual(require("main")(["%command%"]), 0)
            snapshot = dict(execvpe.call_args.args[2])
        self.assertEqual(snapshot["PROTON_ENABLE_NGX_UPDATER"], "1")
        for key, value in PRESET_EXPECTED.items():
            self.assertEqual(snapshot[key], value)

    def test_dll_main_skips_the_ngx_updater(self):
        with patch.dict(os.environ, {}), \
             patch.object(dlss_swapper.os, "execvpe") as execvpe:
            self.assertEqual(require("dll_main")(["%command%"]), 0)
            snapshot = dict(execvpe.call_args.args[2])
        self.assertNotIn("PROTON_ENABLE_NGX_UPDATER", snapshot)
        for key, value in PRESET_EXPECTED.items():
            self.assertEqual(snapshot[key], value)

    def test_defaults_to_sys_argv(self):
        with patch.dict(os.environ, {}), \
             patch.object(sys, "argv", ["dlss-swapper", "%command%"]), \
             patch.object(dlss_swapper.os, "execvpe") as execvpe:
            self.assertEqual(require("main")(), 0)
        self.assertEqual(execvpe.call_args.args[1], ["%command%"])


if __name__ == "__main__":
    unittest.main()
