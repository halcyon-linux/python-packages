"""Tests for the gameclass package."""

from __future__ import annotations

import importlib.util
import contextlib
import io
import os
import subprocess
import sys
import threading
import unittest
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

import gameclass


def require(name: str):
    value = getattr(gameclass, name, None)
    if value is None:
        raise AssertionError(f"gameclass.{name} is not implemented")
    return value


class PackageTests(unittest.TestCase):
    def test_gameclass_module_is_importable(self):
        self.assertIsNotNone(importlib.util.find_spec("gameclass"))

    def test_parse_gameclass_splits_executable_and_class(self):
        self.assertEqual(
            require("parse_gameclass")("game=Game Window=ignored"),
            ("game", "Game Window"),
        )

    def test_parse_gameclass_rejects_empty_fields(self):
        for value in ("game", "=Window", "game="):
            with self.subTest(value=value), self.assertRaises(ValueError):
                require("parse_gameclass")(value)

    def test_main_rejects_no_command_before_starting_watcher(self):
        with (
            patch.dict(os.environ, {"GAMECLASS": "game=Window"}, clear=True),
            patch.object(threading, "Thread") as thread_class,
            contextlib.redirect_stdout(io.StringIO()),
        ):
            self.assertEqual(require("main")([]), 1)

        thread_class.assert_not_called()

    def test_main_rejects_missing_gameclass_environment(self):
        with (
            patch.dict(os.environ, {}, clear=True),
            patch.object(threading, "Thread") as thread_class,
            contextlib.redirect_stdout(io.StringIO()),
        ):
            self.assertEqual(require("main")(["game"]), 1)

        thread_class.assert_not_called()

    def test_command_from_args_quotes_shell_arguments(self):
        self.assertEqual(
            require("command_from_args")(["game", "two words", "semi;colon"]),
            "game 'two words' 'semi;colon'",
        )

    def test_window_lines_extract_id_and_pid(self):
        self.assertEqual(
            require("parse_window_list")(
                "0x012 0 1234 host game title\n0x034 0 5678 host other\n"
            ),
            [("0x012", 1234), ("0x034", 5678)],
        )

    def test_main_runs_command_and_stops_watcher(self):
        thread = MagicMock()
        result = CompletedProcess([], 17, stdout="", stderr="")
        with (
            patch.dict(os.environ, {"GAMECLASS": "game=Window"}, clear=True),
            patch.object(gameclass, "watch_windows", return_value=None, create=True),
            patch.object(threading, "Thread", return_value=thread) as thread_class,
            patch.object(subprocess, "run", return_value=result) as run,
        ):
            status = require("main")(["game", "two words"])

        thread_class.assert_called_once()
        thread.start.assert_called_once()
        thread.join.assert_called_once()
        self.assertEqual(status, 0)
        run.assert_called_once_with(
            "game 'two words'", shell=True, executable="/bin/sh", check=False
        )

    def test_command_environment_overrides_arguments(self):
        thread = MagicMock()
        with (
            patch.dict(
                os.environ,
                {"GAMECLASS": "game=Window", "COMMAND": "custom command"},
                clear=True,
            ),
            patch.object(gameclass, "watch_windows", return_value=None, create=True),
            patch.object(threading, "Thread", return_value=thread),
            patch.object(
                subprocess,
                "run",
                return_value=CompletedProcess([], 0, stdout="", stderr=""),
            ) as run,
        ):
            require("main")(["ignored", "arguments"])

        run.assert_called_once_with(
            "custom command", shell=True, executable="/bin/sh", check=False
        )

    def test_watcher_sets_class_for_matching_window(self):
        class StopAfterOnePoll:
            waits = 0

            def wait(self, _seconds):
                self.waits += 1
                return self.waits > 1

        results = [
            CompletedProcess(
                [], 0, stdout="0x012 0 1234 host game title\n", stderr=""
            ),
            CompletedProcess([], 0, stdout="OldClass\n", stderr=""),
            CompletedProcess([], 0, stdout="", stderr=""),
        ]
        with (
            patch.object(gameclass, "run_command", side_effect=results, create=True) as run,
            patch.object(gameclass, "read_cmdline", return_value="/usr/bin/game", create=True),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            require("watch_windows")("game", "NewClass", StopAfterOnePoll())

        self.assertEqual(
            [call.args[0] for call in run.call_args_list],
            [
                ["wmctrl", "-l", "-p"],
                ["xdotool", "getwindowclassname", "0x012"],
                ["xdotool", "set_window", "--class", "NewClass", "0x012"],
            ],
        )


if __name__ == "__main__":
    unittest.main()
