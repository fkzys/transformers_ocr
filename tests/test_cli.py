"""Tests for transformers_ocr.cli"""

import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from transformers_ocr import config as tocr_config
from transformers_ocr import cli as tocr_cli
from transformers_ocr import process as tocr_process
from transformers_ocr.exceptions import MissingProgram, ScreenshotCancelled


# ═══════════════════════════════════════════════════
# Status
# ═══════════════════════════════════════════════════


class TestStatus:
    def test_running(self):
        with patch.object(tocr_process, "get_pid", return_value=1234), \
             patch.object(tocr_cli, "get_pid", return_value=1234):
            assert tocr_cli.status_str() == "Running"

    def test_stopped(self):
        with patch.object(tocr_process, "get_pid", return_value=None), \
             patch.object(tocr_cli, "get_pid", return_value=None):
            assert tocr_cli.status_str() == "Stopped"

    def test_print_status(self, capsys):
        with patch.object(tocr_cli, "get_pid", return_value=None), \
             patch.object(tocr_config, "CONFIG_PATH", "/nonexistent"), \
             patch.dict(os.environ, {"XDG_CURRENT_DESKTOP": "", "WAYLAND_DISPLAY": "w-0"}):
            tocr_cli.print_status()
        out = capsys.readouterr().out
        assert "Stopped" in out
        assert "Wayland" in out


# ═══════════════════════════════════════════════════
# run_ocr — image_path provided
# ═══════════════════════════════════════════════════


class TestRunOcrWithImagePath:
    """Tests for run_ocr when image_path is given (always goes through preview)."""

    def test_with_image_path_accept_cropped(self):
        """preview_image returns a different path → delete_after=True."""
        with patch.object(tocr_config, "CONFIG_PATH", "/nonexistent"), \
             patch.object(tocr_cli, "ensure_listening"), \
             patch("transformers_ocr.preview.preview_image", return_value="/tmp/cropped.png") as mock_preview, \
             patch.object(tocr_cli, "write_command_to_pipe") as mock_write:
            tocr_cli.run_ocr("recognize", image_path="/img.png")
            mock_preview.assert_called_once_with("/img.png", can_overwrite=False)
            cmd = mock_write.call_args[0][0]
            assert cmd.action == "recognize"
            assert cmd.file_path == "/tmp/cropped.png"
            assert cmd.delete_after is True

    def test_with_image_path_same_returned(self):
        """preview_image returns same path → delete_after=False."""
        with patch.object(tocr_config, "CONFIG_PATH", "/nonexistent"), \
             patch.object(tocr_cli, "ensure_listening"), \
             patch("transformers_ocr.preview.preview_image", return_value="/img.png"), \
             patch.object(tocr_cli, "write_command_to_pipe") as mock_write:
            tocr_cli.run_ocr("recognize", image_path="/img.png")
            cmd = mock_write.call_args[0][0]
            assert cmd.file_path == "/img.png"
            assert cmd.delete_after is False

    def test_with_image_path_cancelled(self):
        """preview_image returns None → ScreenshotCancelled."""
        with patch.object(tocr_config, "CONFIG_PATH", "/nonexistent"), \
             patch.object(tocr_cli, "ensure_listening"), \
             patch("transformers_ocr.preview.preview_image", return_value=None), \
             pytest.raises(ScreenshotCancelled):
            tocr_cli.run_ocr("recognize", image_path="/img.png")

    def test_hold_with_image_path(self):
        """hold command with image_path works the same way."""
        with patch.object(tocr_config, "CONFIG_PATH", "/nonexistent"), \
             patch.object(tocr_cli, "ensure_listening"), \
             patch("transformers_ocr.preview.preview_image", return_value="/img.png"), \
             patch.object(tocr_cli, "write_command_to_pipe") as mock_write:
            tocr_cli.run_ocr("hold", image_path="/img.png")
            cmd = mock_write.call_args[0][0]
            assert cmd.action == "hold"


# ═══════════════════════════════════════════════════
# run_ocr — screenshot path (no image_path)
# ═══════════════════════════════════════════════════


class TestRunOcrScreenshot:
    """Tests for run_ocr without image_path (fullscreen screenshot + preview)."""

    def test_screenshot_accept(self):
        """Fullscreen screenshot taken, then preview, result forwarded."""
        with patch.object(tocr_config, "CONFIG_PATH", "/nonexistent"), \
             patch.object(tocr_cli, "ensure_listening"), \
             patch("tempfile.mkstemp", return_value=(99, "/tmp/full.png")), \
             patch("os.close"), \
             patch.object(tocr_cli, "take_fullscreen_screenshot") as mock_fs, \
             patch("transformers_ocr.preview.preview_image", return_value="/tmp/cropped.png"), \
             patch.object(tocr_cli, "write_command_to_pipe") as mock_write:
            tocr_cli.run_ocr("recognize")
            mock_fs.assert_called_once_with("/tmp/full.png")
            cmd = mock_write.call_args[0][0]
            assert cmd.file_path == "/tmp/cropped.png"
            assert cmd.delete_after is True

    def test_screenshot_preview_cancelled(self):
        """User cancels in overlay → cleanup + ScreenshotCancelled."""
        with patch.object(tocr_config, "CONFIG_PATH", "/nonexistent"), \
             patch.object(tocr_cli, "ensure_listening"), \
             patch("tempfile.mkstemp", return_value=(99, "/tmp/full.png")), \
             patch("os.close"), \
             patch.object(tocr_cli, "take_fullscreen_screenshot"), \
             patch("transformers_ocr.preview.preview_image", return_value=None), \
             patch.object(tocr_cli, "_safe_remove") as mock_rm, \
             pytest.raises(ScreenshotCancelled):
            tocr_cli.run_ocr("recognize")
        mock_rm.assert_called_with("/tmp/full.png")

    def test_fullscreen_screenshot_error_cleanup(self):
        """Fullscreen screenshot fails → cleanup and re-raise."""
        with patch.object(tocr_config, "CONFIG_PATH", "/nonexistent"), \
             patch.object(tocr_cli, "ensure_listening"), \
             patch("tempfile.mkstemp", return_value=(99, "/tmp/full.png")), \
             patch("os.close"), \
             patch.object(tocr_cli, "take_fullscreen_screenshot", side_effect=RuntimeError("fail")), \
             patch.object(tocr_cli, "_safe_remove") as mock_rm, \
             pytest.raises(RuntimeError, match="fail"):
            tocr_cli.run_ocr("recognize")
        mock_rm.assert_called_with("/tmp/full.png")

    def test_screenshot_preview_returns_same_path(self):
        """preview_image returns the same temp path → delete_after=True (it's still a temp)."""
        with patch.object(tocr_config, "CONFIG_PATH", "/nonexistent"), \
             patch.object(tocr_cli, "ensure_listening"), \
             patch("tempfile.mkstemp", return_value=(99, "/tmp/full.png")), \
             patch("os.close"), \
             patch.object(tocr_cli, "take_fullscreen_screenshot"), \
             patch("transformers_ocr.preview.preview_image", return_value="/tmp/full.png"), \
             patch.object(tocr_cli, "write_command_to_pipe") as mock_write:
            tocr_cli.run_ocr("recognize")
            cmd = mock_write.call_args[0][0]
            assert cmd.file_path == "/tmp/full.png"
            assert cmd.delete_after is True


# ═══════════════════════════════════════════════════
# CLI parser
# ═══════════════════════════════════════════════════


class TestCliParser:
    def test_parser_recognize(self):
        args = tocr_cli.create_args_parser().parse_args(["recognize"])
        assert hasattr(args, "func")
        assert args.image_path is None

    def test_parser_recognize_image(self):
        args = tocr_cli.create_args_parser().parse_args(["recognize", "--image-path", "/img.png"])
        assert args.image_path == "/img.png"

    def test_parser_hold(self):
        assert hasattr(tocr_cli.create_args_parser().parse_args(["hold"]), "func")

    def test_parser_stop(self):
        assert hasattr(tocr_cli.create_args_parser().parse_args(["stop"]), "func")

    def test_parser_status(self):
        assert hasattr(tocr_cli.create_args_parser().parse_args(["status"]), "func")

    def test_parser_download(self):
        assert hasattr(tocr_cli.create_args_parser().parse_args(["download"]), "func")

    def test_parser_purge(self):
        assert hasattr(tocr_cli.create_args_parser().parse_args(["purge"]), "func")

    def test_parser_start_foreground(self):
        args = tocr_cli.create_args_parser().parse_args(["start", "--foreground"])
        assert args.foreground is True

    def test_parser_start_default(self):
        args = tocr_cli.create_args_parser().parse_args(["start"])
        assert args.foreground is False

    def test_parser_alias_ocr(self):
        assert hasattr(tocr_cli.create_args_parser().parse_args(["ocr"]), "func")

    def test_parser_alias_nuke(self):
        assert hasattr(tocr_cli.create_args_parser().parse_args(["nuke"]), "func")

    def test_parser_alias_listen(self):
        assert hasattr(tocr_cli.create_args_parser().parse_args(["listen"]), "func")

    # ── --preview flag removed ──

    def test_parser_recognize_no_preview_flag(self):
        """--preview flag was removed; passing it should fail."""
        with pytest.raises(SystemExit):
            tocr_cli.create_args_parser().parse_args(["recognize", "--preview"])

    def test_parser_recognize_no_preview_short(self):
        with pytest.raises(SystemExit):
            tocr_cli.create_args_parser().parse_args(["recognize", "-p"])

    def test_parser_hold_no_preview_flag(self):
        with pytest.raises(SystemExit):
            tocr_cli.create_args_parser().parse_args(["hold", "--preview"])

    def test_parser_recognize_no_preview_attr(self):
        """Parsed args should not have a 'preview' attribute."""
        args = tocr_cli.create_args_parser().parse_args(["recognize"])
        assert not hasattr(args, "preview")

    def test_parser_hold_no_preview_attr(self):
        args = tocr_cli.create_args_parser().parse_args(["hold"])
        assert not hasattr(args, "preview")

    def test_parser_recognize_with_image(self):
        args = tocr_cli.create_args_parser().parse_args([
            "recognize", "--image-path", "/img.png",
        ])
        assert args.image_path == "/img.png"


class TestCliMain:
    def test_main_no_args(self, capsys):
        with patch("sys.argv", ["trocr"]):
            tocr_cli.main()
        out = capsys.readouterr().out
        assert "commands" in out.lower() or "ocr" in out.lower()

    def test_main_missing_program(self):
        with patch("sys.argv", ["trocr", "recognize"]), \
             patch.object(tocr_cli, "run_ocr", side_effect=MissingProgram("grim")), \
             patch.object(tocr_cli, "notify_send") as mock:
            tocr_cli.main()
            assert "grim" in mock.call_args[0][0]

    def test_main_screenshot_cancelled(self):
        with patch("sys.argv", ["trocr", "recognize"]), \
             patch.object(tocr_cli, "run_ocr", side_effect=ScreenshotCancelled()), \
             patch.object(tocr_cli, "notify_send") as mock:
            tocr_cli.main()
            assert "cancelled" in mock.call_args[0][0].lower()

    def test_main_keyboard_interrupt(self):
        with patch("sys.argv", ["trocr", "recognize"]), \
             patch.object(tocr_cli, "run_ocr", side_effect=KeyboardInterrupt), \
             pytest.raises(SystemExit, match="130"):
            tocr_cli.main()

    def test_main_subprocess_error(self):
        with patch("sys.argv", ["trocr", "recognize"]), \
             patch.object(tocr_cli, "run_ocr", side_effect=subprocess.CalledProcessError(2, "cmd")):
            with pytest.raises(SystemExit) as exc:
                tocr_cli.main()
            assert exc.value.code == 2
