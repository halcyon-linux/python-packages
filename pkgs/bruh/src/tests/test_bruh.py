"""Tests for the bruh package."""

from __future__ import annotations

import io
import os
import sys
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

import bruh


class PackageTests(unittest.TestCase):
    def test_moment_routes_to_rollback_and_preserves_arguments(self):
        with patch.object(os, "execvp") as execvp:
            bruh.main(["moment", "-y"])

        execvp.assert_called_once_with(
            "brh", ["brh", "rollback", "moment", "-y"]
        )

    def test_regular_arguments_are_forwarded_unchanged(self):
        with patch.object(os, "execvp") as execvp:
            bruh.main(["rebase", "testing", "-y"])

        execvp.assert_called_once_with("brh", ["brh", "rebase", "testing", "-y"])

    def test_no_arguments_start_brh_interactive_mode(self):
        with patch.object(os, "execvp") as execvp:
            bruh.main([])

        execvp.assert_called_once_with("brh", ["brh"])

    def test_missing_brh_returns_shell_command_not_found_status(self):
        with (
            patch.object(os, "execvp", side_effect=FileNotFoundError("brh")),
            redirect_stderr(io.StringIO()),
        ):
            result = bruh.main(["current"])

        self.assertEqual(result, 127)

    def test_other_exec_error_returns_shell_permission_status(self):
        with (
            patch.object(os, "execvp", side_effect=PermissionError("brh")),
            redirect_stderr(io.StringIO()),
        ):
            result = bruh.main(["current"])

        self.assertEqual(result, 126)


if __name__ == "__main__":
    unittest.main()
