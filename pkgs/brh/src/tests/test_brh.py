"""Tests for the brh package."""

from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

import brh


class PackageTests(unittest.TestCase):
    def test_load_image_info_uses_stable_when_branch_is_missing(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            image_info = Path(temporary_directory) / "image-info.json"
            image_info.write_text(
                json.dumps({"image-name": "image", "image-vendor": "provider"}),
                encoding="utf-8",
            )

            self.assertEqual(
                brh.load_image_info(image_info),
                brh.ImageConfig("image", "provider", "stable"),
            )

    def test_filter_tags_sorts_and_selects_track_prefix(self):
        tags = ["testing-2", "stable-2", "stable", "testing-1", "other"]

        self.assertEqual(brh.filter_tags(tags, "stable"), ["stable", "stable-2"])
        self.assertEqual(brh.filter_tags(tags, "testing"), ["testing-1", "testing-2"])
        self.assertEqual(brh.filter_tags(tags, "all"), sorted(tags))

    def test_build_rebase_ref_accepts_tag_image_tag_and_full_ref(self):
        config = brh.ImageConfig("default-image", "default-provider", "stable")

        self.assertEqual(
            brh.build_rebase_ref("testing", config),
            (
                "ostree-image-signed:docker://ghcr.io/"
                "default-provider/default-image:testing"
            ),
        )
        self.assertEqual(
            brh.build_rebase_ref("other-image:testing", config),
            "ostree-image-signed:docker://ghcr.io/default-provider/other-image:testing",
        )
        full_ref = "ostree-unverified-registry:ghcr.io/other/image:stable"
        self.assertEqual(brh.build_rebase_ref(full_ref, config), full_ref)

    def test_parse_current_ref_extracts_image_and_tag(self):
        self.assertEqual(
            brh.parse_current_ref(
                "ostree-image-signed:docker://ghcr.io/vendor/image:testing"
            ),
            ("image", "testing"),
        )

    def test_signing_scheme_matches_current_deployment(self):
        status = json.dumps(
            {
                "deployments": [
                    {
                        "container-image-reference": (
                            "ostree-image-signed:docker://ghcr.io/vendor/image:stable"
                        )
                    }
                ]
            }
        )
        with patch.object(
            brh,
            "run_command",
            return_value=CompletedProcess([], 0, stdout=status, stderr=""),
            create=True,
        ) as run:
            self.assertEqual(
                brh.signing_scheme(), "ostree-image-signed:docker://ghcr.io"
            )
        run.assert_called_once_with(
            ["rpm-ostree", "status", "-b", "--json"], capture_output=True
        )

    def test_signing_scheme_falls_back_for_null_deployment_reference(self):
        status = json.dumps(
            {"deployments": [{"container-image-reference": None}]}
        )
        with patch.object(
            brh,
            "run_command",
            return_value=CompletedProcess([], 0, stdout=status, stderr=""),
        ):
            try:
                scheme = brh.signing_scheme()
            except TypeError as error:
                self.fail(f"null references should use the fallback scheme: {error}")

        self.assertEqual(scheme, "ostree-unverified-registry:ghcr.io")

    def test_list_command_uses_image_config_and_track_filter(self):
        config = brh.ImageConfig("image", "provider", "stable")
        result = CompletedProcess(
            [],
            0,
            stdout=json.dumps({"Tags": ["testing-1", "stable-2", "stable"]}),
            stderr="",
        )
        output = io.StringIO()
        with (
            patch.object(brh, "load_image_info", return_value=config),
            patch.object(brh, "run_command", return_value=result) as run,
            contextlib.redirect_stdout(output),
            contextlib.redirect_stderr(io.StringIO()),
        ):
            self.assertEqual(brh.main(["list", "stable"]), 0)

        self.assertEqual(output.getvalue(), "stable\nstable-2\n")

        run.assert_called_once_with(
            ["skopeo", "list-tags", "docker://ghcr.io/provider/image"],
            capture_output=True,
        )

    def test_rebase_yes_skips_confirmation_and_rebases_to_default_image(self):
        config = brh.ImageConfig("image", "provider", "stable")
        with (
            patch.object(brh, "load_image_info", return_value=config),
            patch.object(
                brh,
                "run_command",
                return_value=CompletedProcess([], 0, stdout="", stderr=""),
            ) as run,
            contextlib.redirect_stdout(io.StringIO()),
        ):
            self.assertEqual(brh.main(["rebase", "testing", "-y"]), 0)

        run.assert_called_once_with(
            [
                "rpm-ostree",
                "rebase",
                "ostree-image-signed:docker://ghcr.io/provider/image:testing",
            ]
        )

    def test_eof_at_custom_provider_prompt_uses_default_provider(self):
        config = brh.ImageConfig("image", "provider", "stable")
        with (
            patch("builtins.input", side_effect=EOFError),
            patch.object(brh, "pick_image", return_value="Back") as pick_image,
            contextlib.redirect_stdout(io.StringIO()),
        ):
            try:
                brh._interactive_custom_provider(config)
            except EOFError:
                self.fail("EOF at the provider prompt should use the default")

        pick_image.assert_called_once_with(config, "ublue-os")

    def test_skopeo_tags_uses_bkt_when_installed(self):
        result = CompletedProcess([], 0, stdout='{"Tags": ["stable"]}', stderr="")
        with patch("brh.shutil.which", return_value="/usr/bin/bkt"), patch.object(
            brh, "run_command", return_value=result
        ) as run:
            self.assertEqual(brh.skopeo_tags("provider", "image"), ["stable"])

        run.assert_called_once_with(
            [
                "bkt",
                "--ttl=30m",
                "--stale=5m",
                "--",
                "command",
                "skopeo",
                "list-tags",
                "docker://ghcr.io/provider/image",
            ],
            capture_output=True,
        )

    def test_rollback_cancel_does_not_run_rpm_ostree(self):
        with (
            patch.object(brh, "confirm", return_value=False),
            patch.object(brh, "run_command") as run,
            contextlib.redirect_stdout(io.StringIO()),
        ):
            self.assertEqual(brh.rollback(), 0)

        run.assert_not_called()

    def test_eof_is_not_confirmation(self):
        with (
            patch("builtins.input", side_effect=EOFError),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            self.assertIsNone(brh.confirm("Continue?"))

    def test_rollback_eof_does_not_run_rpm_ostree(self):
        with (
            patch("builtins.input", side_effect=EOFError),
            patch.object(brh, "run_command") as run,
            contextlib.redirect_stdout(io.StringIO()),
        ):
            self.assertEqual(brh.rollback(), 0)

        run.assert_not_called()

    def test_rebase_eof_does_not_run_rpm_ostree(self):
        config = brh.ImageConfig("image", "provider", "stable")
        with (
            patch("builtins.input", side_effect=EOFError),
            patch.object(brh, "run_command") as run,
            contextlib.redirect_stdout(io.StringIO()),
        ):
            self.assertEqual(brh.rebase_to(config, "testing"), 1)

        run.assert_not_called()

    def test_choose_accepts_numbered_selection(self):
        with patch("builtins.input", return_value="2"), contextlib.redirect_stdout(
            io.StringIO()
        ):
            self.assertEqual(brh.choose("List", "Back"), "Back")

    def test_choose_filter_only_offers_tracks_with_tags(self):
        with patch.object(
            brh,
            "skopeo_tags",
            side_effect=lambda _provider, _image, track: ["stable"]
            if track == "stable"
            else [],
        ), patch.object(
            brh, "choose", return_value="Stable"
        ) as choose, contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(brh.choose_filter("provider", "image"), "Stable")

        choose.assert_called_once_with("Stable", "All", "Back")

    def test_interactive_lookup_error_returns_to_menu(self):
        config = brh.ImageConfig("image", "provider", "stable")
        with (
            patch.object(brh, "print_status"),
            patch.object(brh, "choose", side_effect=["List Images", "Exit"]),
            patch.object(
                brh, "_interactive_list", side_effect=RuntimeError("GHCR unavailable")
            ),
            patch.object(brh, "press_any_key"),
            contextlib.redirect_stdout(io.StringIO()),
            contextlib.redirect_stderr(io.StringIO()),
        ):
            try:
                result = brh.interactive_menu(config)
            except RuntimeError as error:
                self.fail(f"interactive lookup errors should return to the menu: {error}")

        self.assertEqual(result, 0)


if __name__ == "__main__":
    unittest.main()
