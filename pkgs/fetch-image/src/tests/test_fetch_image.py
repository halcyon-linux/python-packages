"""Tests for the fetch-image package."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

import fetch_image


def require(name: str):
    value = getattr(fetch_image, name, None)
    if value is None:
        raise AssertionError(f"fetch_image.{name} is not implemented")
    return value


SIGNED_STATUS = (
    '{"deployments": [{"origin": "ostree-image-signed:docker://ghcr.io/halcyon-linux/bazzfin-nvidia:stable"}]}'
)
UNSIGNED_STATUS = (
    '{"deployments": [{"origin": "ostree-unverified-registry:docker://ghcr.io/halcyon-linux/bazzfin-nvidia:stable"}]}'
)


class PackageTests(unittest.TestCase):
    def test_package_exposes_only_the_fetch_image_command(self):
        project = tomllib.loads(
            (Path(__file__).parents[1] / "pyproject.toml").read_text(encoding="utf-8")
        )["project"]
        self.assertEqual(project["name"], "fetch-image")
        self.assertEqual(
            project["scripts"], {"fetch-image": "fetch_image:main"}
        )

    def test_module_is_importable(self):
        self.assertIsNotNone(importlib.util.find_spec("fetch_image"))


class ImageLabelTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.path = Path(self._tmp.name) / "image-info.json"

    def test_label_joins_image_name_and_branch(self):
        self.path.write_text(
            json.dumps({"image-name": "bazzfin-nvidia", "image-branch": "stable"}),
            encoding="utf-8",
        )
        self.assertEqual(require("image_label")(self.path), "bazzfin-nvidia:stable")

    def test_missing_file_yields_empty_label(self):
        self.assertEqual(require("image_label")(self.path), "")

    def test_invalid_json_yields_empty_label(self):
        self.path.write_text("not json", encoding="utf-8")
        self.assertEqual(require("image_label")(self.path), "")

    def test_non_string_values_yield_empty_label(self):
        self.path.write_text(json.dumps({"image-name": 3}), encoding="utf-8")
        self.assertEqual(require("image_label")(self.path), "")


class BootedStatusTests(unittest.TestCase):
    def test_signed_origin_is_detected(self):
        is_signed = require("booted_is_signed")
        self.assertTrue(is_signed(SIGNED_STATUS))
        self.assertFalse(is_signed(UNSIGNED_STATUS))
        self.assertFalse(is_signed(""))

    def test_status_runs_rpm_ostree_and_returns_stdout(self):
        with patch.object(
            fetch_image.subprocess,
            "run",
            return_value=Mock(returncode=0, stdout=SIGNED_STATUS),
        ) as run:
            self.assertEqual(require("booted_status")(), SIGNED_STATUS)
        self.assertEqual(
            run.call_args.args[0],
            ["rpm-ostree", "status", "--json", "--booted"],
        )

    def test_failed_rpm_ostree_reads_as_empty(self):
        with patch.object(
            fetch_image.subprocess,
            "run",
            return_value=Mock(returncode=1, stdout=""),
        ):
            self.assertEqual(require("booted_status")(), "")

    def test_missing_rpm_ostree_reads_as_empty(self):
        with patch.object(
            fetch_image.subprocess, "run", side_effect=FileNotFoundError("rpm-ostree")
        ):
            self.assertEqual(require("booted_status")(), "")


class MainTests(unittest.TestCase):
    def run_main(self, status: str) -> str:
        with patch.object(fetch_image, "image_label", return_value="bazzfin-nvidia:stable"), \
             patch.object(fetch_image, "booted_status", return_value=status), \
             contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(require("main")([]), 0)
        return out.getvalue()

    def test_signed_image_gets_plain_marker(self):
        self.assertEqual(self.run_main(SIGNED_STATUS), "bazzfin-nvidia:stable \U0000f456")

    def test_unsigned_image_gets_flashing_red_marker(self):
        self.assertEqual(
            self.run_main(UNSIGNED_STATUS),
            "bazzfin-nvidia:stable \033[6;31m\U0000f2fc",
        )

    def test_no_trailing_newline(self):
        self.assertFalse(self.run_main(SIGNED_STATUS).endswith("\n"))


if __name__ == "__main__":
    unittest.main()
