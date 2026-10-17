"""Tests for the uupd-update package."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import sys
import tomllib
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

import uupd_update


def require(name: str):
    value = getattr(uupd_update, name, None)
    if value is None:
        raise AssertionError(f"uupd_update.{name} is not implemented")
    return value


class PackageTests(unittest.TestCase):
    def test_package_exposes_only_uupd_update_command(self):
        project = tomllib.loads(
            (Path(__file__).parents[1] / "pyproject.toml").read_text(encoding="utf-8")
        )["project"]
        self.assertEqual(project["name"], "uupd-update")
        self.assertEqual(project["scripts"], {"uupd-update": "uupd_update:main"})

    def test_module_is_importable(self):
        self.assertIsNotNone(importlib.util.find_spec("uupd_update"))


class ReadStateTests(unittest.TestCase):
    def test_returns_stripped_state(self):
        with patch.object(uupd_update.subprocess, "run",
                          return_value=Mock(returncode=0, stdout="active\n")):
            self.assertEqual(require("read_state")("uupd.service"), "active")

    def test_failed_query_is_empty_state(self):
        with patch.object(uupd_update.subprocess, "run",
                          return_value=Mock(returncode=1, stdout="")):
            self.assertEqual(require("read_state")("uupd.service"), "")

    def test_queries_the_active_state_property(self):
        with patch.object(uupd_update.subprocess, "run",
                          return_value=Mock(returncode=0, stdout="inactive\n")) as run:
            require("read_state")("uupd-manual.service")
        self.assertEqual(
            run.call_args.args[0],
            ["systemctl", "show", "-p", "ActiveState", "--value", "uupd-manual.service"],
        )


class TimestampTests(unittest.TestCase):
    def test_returns_timestamp_and_forces_c_locale(self):
        with patch.object(uupd_update.subprocess, "run",
                          return_value=Mock(returncode=0,
                                            stdout="Mon 2026-10-17 10:00:00 UTC\n")) as run:
            self.assertEqual(require("inactive_exit_timestamp")("uupd.service"),
                             "Mon 2026-10-17 10:00:00 UTC")
        self.assertEqual(run.call_args.kwargs["env"]["LC_ALL"], "C")

    def test_failed_query_is_empty(self):
        with patch.object(uupd_update.subprocess, "run",
                          return_value=Mock(returncode=1, stdout="")):
            self.assertEqual(require("inactive_exit_timestamp")("uupd.service"), "")


class PickTargetTests(unittest.TestCase):
    def test_prefers_main_then_manual_then_starts_manual(self):
        pick = require("pick_target")
        self.assertEqual(pick("active", "inactive"), ("uupd.service", False))
        self.assertEqual(pick("activating", "inactive"), ("uupd.service", False))
        self.assertEqual(pick("inactive", "active"), ("uupd-manual.service", False))
        self.assertEqual(pick("failed", "deactivating"), ("uupd-manual.service", False))
        self.assertEqual(pick("failed", "inactive"), ("uupd-manual.service", True))

    def test_missing_services_are_treated_as_inactive(self):
        self.assertEqual(require("pick_target")("", ""), ("uupd-manual.service", True))
        self.assertEqual(require("pick_target")("", "active"), ("uupd-manual.service", False))


class JournalArgsTests(unittest.TestCase):
    def test_since_when_attaching_and_zero_lines_otherwise(self):
        args = require("journal_args")
        base = ["journalctl", "-u", "uupd.service", "-f", "-o", "cat",
                "--synchronize-on-exit=yes"]
        self.assertEqual(args("uupd.service", "Mon 2026-10-17 10:00:00 UTC"),
                         base + ["--since", "Mon 2026-10-17 10:00:00 UTC"])
        self.assertEqual(args("uupd.service", ""), base + ["--lines=0"])


class ExecStatusTests(unittest.TestCase):
    def test_returns_status_or_empty(self):
        with patch.object(uupd_update.subprocess, "run",
                          return_value=Mock(returncode=0, stdout="1\n")):
            self.assertEqual(require("exec_status")("uupd.service"), "1")
        with patch.object(uupd_update.subprocess, "run",
                          return_value=Mock(returncode=1, stdout="")):
            self.assertEqual(require("exec_status")("uupd.service"), "")


class ExitCodeTests(unittest.TestCase):
    def test_empty_is_success_numeric_passes_through_garbage_is_two(self):
        code = require("exit_code")
        self.assertEqual(code(""), 0)
        self.assertEqual(code("0"), 0)
        self.assertEqual(code("137"), 137)
        self.assertEqual(code("abc"), 2)


class StreamJournalTests(unittest.TestCase):
    def test_spawns_journalctl_with_inherited_output(self):
        with patch.object(uupd_update.subprocess, "Popen", return_value=Mock()) as popen:
            process = require("stream_journal")("uupd.service", "")
        popen.assert_called_once_with(["journalctl", "-u", "uupd.service", "-f", "-o", "cat",
                                       "--synchronize-on-exit=yes", "--lines=0"])
        self.assertIs(process, popen.return_value)


class StopJournalTests(unittest.TestCase):
    def test_terminates_only_a_running_child(self):
        stop = require("stop_journal")
        running = Mock()
        running.poll.return_value = None
        stop(running)
        running.terminate.assert_called_once_with()
        exited = Mock()
        exited.poll.return_value = 1
        stop(exited)
        exited.terminate.assert_not_called()


class WaitServiceTests(unittest.TestCase):
    def test_start_wait_when_starting(self):
        with patch.object(uupd_update.subprocess, "run",
                          return_value=Mock(returncode=1)) as run:
            require("wait_for_service")("uupd-manual.service", True)
        self.assertEqual(run.call_args.args[0],
                         ["systemctl", "start", "--wait", "uupd-manual.service"])

    def test_polls_until_inactive_when_attaching(self):
        with patch.object(uupd_update, "read_state",
                          side_effect=["active", "active", "failed"]) as state, \
             patch.object(uupd_update.time, "sleep") as sleep:
            require("wait_for_service")("uupd.service", False)
        self.assertEqual(state.call_count, 3)
        self.assertEqual(sleep.call_count, 2)

    def test_missing_state_does_not_spin(self):
        with patch.object(uupd_update, "read_state", return_value=""), \
             patch.object(uupd_update.time, "sleep") as sleep:
            require("wait_for_service")("uupd.service", False)
        sleep.assert_not_called()


class StopHandlersTests(unittest.TestCase):
    def test_handlers_stop_journal_and_exit_by_signal(self):
        handlers = {}

        def capture(sig, handler):
            handlers[sig] = handler

        with patch.object(uupd_update.signal, "signal", side_effect=capture), \
             patch.object(uupd_update, "stop_journal") as stop:
            require("install_stop_handlers")(Mock())
            self.assertEqual(set(handlers),
                             {uupd_update.signal.SIGTERM, uupd_update.signal.SIGHUP})
            for sig, handler in handlers.items():
                with self.assertRaises(SystemExit) as raised:
                    handler(sig, None)
                self.assertEqual(raised.exception.code, 128 + sig)
        self.assertEqual(stop.call_count, 2)


class MainTests(unittest.TestCase):
    def test_attach_reuses_running_service_and_passes_exit_code(self):
        with patch.object(uupd_update, "read_state", side_effect=["active", "inactive"]), \
             patch.object(uupd_update, "inactive_exit_timestamp", return_value="TS"), \
             patch.object(uupd_update, "stream_journal") as stream, \
             patch.object(uupd_update, "install_stop_handlers"), \
             patch.object(uupd_update, "wait_for_service") as wait, \
             patch.object(uupd_update, "exec_status", return_value="1"), \
             patch.object(uupd_update, "stop_journal") as stop:
            self.assertEqual(require("main")([]), 1)
        stream.assert_called_once_with("uupd.service", "TS")
        wait.assert_called_once_with("uupd.service", False)
        stop.assert_called_once_with(stream.return_value)

    def test_starts_manual_service_when_none_running(self):
        with patch.object(uupd_update, "read_state", side_effect=["inactive", "failed"]), \
             patch.object(uupd_update, "inactive_exit_timestamp") as timestamp, \
             patch.object(uupd_update, "stream_journal") as stream, \
             patch.object(uupd_update, "install_stop_handlers"), \
             patch.object(uupd_update, "wait_for_service") as wait, \
             patch.object(uupd_update, "exec_status", return_value="0"), \
             patch.object(uupd_update, "stop_journal"):
            self.assertEqual(require("main")([]), 0)
        timestamp.assert_not_called()
        stream.assert_called_once_with("uupd-manual.service", "")
        wait.assert_called_once_with("uupd-manual.service", True)

    def test_ctrl_c_returns_130_after_stopping_journal(self):
        with patch.object(uupd_update, "read_state", side_effect=["active", "inactive"]), \
             patch.object(uupd_update, "inactive_exit_timestamp", return_value="TS"), \
             patch.object(uupd_update, "stream_journal"), \
             patch.object(uupd_update, "install_stop_handlers"), \
             patch.object(uupd_update, "wait_for_service", side_effect=KeyboardInterrupt), \
             patch.object(uupd_update, "stop_journal") as stop:
            self.assertEqual(require("main")([]), 130)
        stop.assert_called_once()

    def test_missing_systemctl_reports_and_fails(self):
        with patch.object(uupd_update.subprocess, "run",
                          side_effect=FileNotFoundError("systemctl")), \
             patch.object(uupd_update, "stop_journal") as stop, \
             contextlib.redirect_stderr(io.StringIO()) as err:
            self.assertEqual(require("main")([]), 1)
        self.assertTrue(err.getvalue())
        stop.assert_not_called()

    def test_version_flag_exits_zero(self):
        with contextlib.redirect_stdout(io.StringIO()) as out, \
             self.assertRaises(SystemExit) as raised:
            require("main")(["--version"])
        self.assertEqual(raised.exception.code, 0)
        self.assertIn("uupd-update", out.getvalue())


if __name__ == "__main__":
    unittest.main()
