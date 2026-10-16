"""Tests for the bbrew-helper package."""

from __future__ import annotations

import io
import os
import sys
import tempfile
import tomllib
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

import bbrew_helper


class PackageTests(unittest.TestCase):
    def test_package_installs_bbrew_helper_command(self):
        project = tomllib.loads(
            (Path(__file__).parents[1] / "pyproject.toml").read_text(encoding="utf-8")
        )["project"]
        self.assertEqual(project["name"], "bbrew-helper")
        self.assertEqual(project["scripts"], {"bbrew-helper": "bbrew_helper:main"})

    def test_missing_bbrew_installs_formula_then_execs_bbrew(self):
        installed = CompletedProcess([], 0, stdout="", stderr="")
        with (
            patch.object(bbrew_helper, "BREW_PATH", "/nonexistent/brew"),
            patch.object(bbrew_helper, "run_command", return_value=installed) as run,
            patch.object(bbrew_helper.shutil, "which", return_value=None),
            patch.object(os, "execvpe") as execvpe,
        ):
            bbrew_helper.main(["list"])

        self.assertEqual(
            run.call_args.args[0],
            ["brew", "install", "Valkyrie00/homebrew-bbrew/bbrew"],
        )
        execvpe.assert_called_once()
        self.assertEqual(execvpe.call_args.args[0:2], ("bbrew", ["bbrew", "list"]))
        self.assertEqual(
            execvpe.call_args.args[2]["PATH"], os.environ.get("PATH")
        )

    def test_existing_bbrew_is_not_reinstalled(self):
        with (
            patch.object(bbrew_helper, "BREW_PATH", "/nonexistent/brew"),
            patch.object(bbrew_helper, "run_command") as run,
            patch.object(bbrew_helper.shutil, "which", return_value="/usr/bin/bbrew"),
            patch.object(os, "execvpe") as execvpe,
        ):
            bbrew_helper.main([])

        run.assert_not_called()
        self.assertEqual(execvpe.call_args.args[0:2], ("bbrew", ["bbrew"]))

    def test_shellenv_exports_are_applied_to_the_environment(self):
        path = os.environ.get("PATH", "")
        infopath = os.environ.get("INFOPATH", "")
        shellenv = CompletedProcess(
            [],
            0,
            stdout=(
                'export HOMEBREW_PREFIX="/home/linuxbrew/.linuxbrew";\n'
                'export PATH="/home/linuxbrew/.linuxbrew/bin:'
                '/home/linuxbrew/.linuxbrew/sbin${PATH+:$PATH}";\n'
                '[ -z "${MANPATH-}" ] || { export MANPATH="x"; };\n'
                'export INFOPATH="/home/linuxbrew/.linuxbrew/share/info:${INFOPATH:-}";\n'
            ),
            stderr="",
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            brew = Path(temporary_directory) / "brew"
            brew.touch()
            with (
                patch.object(bbrew_helper, "BREW_PATH", str(brew)),
                patch.object(bbrew_helper, "run_command", return_value=shellenv) as run,
                patch.object(bbrew_helper.shutil, "which", return_value="/usr/bin/bbrew"),
                patch.object(os, "execvpe") as execvpe,
            ):
                bbrew_helper.main(["tui"])

        self.assertEqual(run.call_args.args[0], [str(brew), "shellenv"])
        self.assertTrue(run.call_args.kwargs["capture_output"])
        environment = execvpe.call_args.args[2]
        self.assertEqual(environment["HOMEBREW_PREFIX"], "/home/linuxbrew/.linuxbrew")
        self.assertEqual(
            environment["PATH"],
            "/home/linuxbrew/.linuxbrew/bin:/home/linuxbrew/.linuxbrew/sbin:" + path,
        )
        self.assertEqual(
            environment["INFOPATH"],
            "/home/linuxbrew/.linuxbrew/share/info:" + infopath,
        )
        self.assertEqual(environment.get("MANPATH"), os.environ.get("MANPATH"))

    def test_shellenv_failure_leaves_environment_untouched(self):
        failed = CompletedProcess([], 1, stdout="", stderr="boom")
        with tempfile.TemporaryDirectory() as temporary_directory:
            brew = Path(temporary_directory) / "brew"
            brew.touch()
            with (
                patch.object(bbrew_helper, "BREW_PATH", str(brew)),
                patch.object(bbrew_helper, "run_command", return_value=failed),
                patch.object(bbrew_helper.shutil, "which", return_value="/usr/bin/bbrew"),
                patch.object(os, "execvpe") as execvpe,
            ):
                bbrew_helper.main([])

        environment = execvpe.call_args.args[2]
        self.assertEqual(environment, dict(os.environ))

    def test_missing_brew_returns_shell_command_not_found_status(self):
        with (
            patch.object(bbrew_helper, "BREW_PATH", "/nonexistent/brew"),
            patch.object(
                bbrew_helper, "run_command", side_effect=FileNotFoundError("brew")
            ),
            patch.object(bbrew_helper.shutil, "which", return_value=None),
            redirect_stderr(io.StringIO()),
        ):
            result = bbrew_helper.main(["list"])

        self.assertEqual(result, 127)

    def test_install_permission_error_returns_shell_permission_status(self):
        with (
            patch.object(bbrew_helper, "BREW_PATH", "/nonexistent/brew"),
            patch.object(
                bbrew_helper, "run_command", side_effect=PermissionError("brew")
            ),
            patch.object(bbrew_helper.shutil, "which", return_value=None),
            redirect_stderr(io.StringIO()),
        ):
            result = bbrew_helper.main(["list"])

        self.assertEqual(result, 126)

    def test_bbrew_missing_after_install_returns_shell_command_not_found_status(self):
        installed = CompletedProcess([], 1, stdout="", stderr="no tap")
        with (
            patch.object(bbrew_helper, "BREW_PATH", "/nonexistent/brew"),
            patch.object(bbrew_helper, "run_command", return_value=installed),
            patch.object(bbrew_helper.shutil, "which", return_value=None),
            patch.object(os, "execvpe", side_effect=FileNotFoundError("bbrew")),
            redirect_stderr(io.StringIO()),
        ):
            result = bbrew_helper.main(["list"])

        self.assertEqual(result, 127)

    def test_other_exec_error_returns_shell_permission_status(self):
        with (
            patch.object(bbrew_helper, "BREW_PATH", "/nonexistent/brew"),
            patch.object(bbrew_helper, "run_command"),
            patch.object(bbrew_helper.shutil, "which", return_value="/usr/bin/bbrew"),
            patch.object(os, "execvpe", side_effect=PermissionError("bbrew")),
            redirect_stderr(io.StringIO()),
        ):
            result = bbrew_helper.main([])

        self.assertEqual(result, 126)


if __name__ == "__main__":
    unittest.main()
