"""Tests for transformers_ocr.platform"""

import os
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from transformers_ocr import platform as tocr_platform
from transformers_ocr.exceptions import MissingProgram


class TestPlatformDetection:
    def test_is_xorg_no_wayland(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("WAYLAND_DISPLAY", None)
            assert tocr_platform._is_xorg() is True

    def test_is_xorg_wayland_set(self):
        with patch.dict(os.environ, {"WAYLAND_DISPLAY": "wayland-0"}):
            assert tocr_platform._is_xorg() is False

    def test_platform_xorg(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("WAYLAND_DISPLAY", None)
            assert tocr_platform.Platform.current() == tocr_platform.Platform.Xorg

    def test_platform_wayland(self):
        with patch.dict(os.environ, {"WAYLAND_DISPLAY": "wayland-0"}):
            assert tocr_platform.Platform.current() == tocr_platform.Platform.Wayland

    def test_only_two_platform_members(self):
        """GNOME, KDE, XFCE variants were removed."""
        names = {m.name for m in tocr_platform.Platform}
        assert names == {"Xorg", "Wayland"}

    def test_clip_args_xorg(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("WAYLAND_DISPLAY", None)
            assert tocr_platform.get_clip_copy_args() == ("xclip", "-selection", "clipboard")

    def test_clip_args_wayland(self):
        with patch.dict(os.environ, {"WAYLAND_DISPLAY": "wayland-0"}):
            assert tocr_platform.get_clip_copy_args() == ("wl-copy",)


class TestRaiseIfMissing:
    """raise_if_missing now takes a single program and uses shutil.which only."""

    def test_present(self):
        with patch("shutil.which", return_value="/usr/bin/bash"):
            tocr_platform.raise_if_missing("bash")

    def test_absent(self):
        with patch("shutil.which", return_value=None), \
             pytest.raises(MissingProgram, match="grim"):
            tocr_platform.raise_if_missing("grim")

    def test_single_arg_only(self):
        """Function signature accepts exactly one program."""
        import inspect
        sig = inspect.signature(tocr_platform.raise_if_missing)
        params = list(sig.parameters.keys())
        assert len(params) == 1


class TestFullscreenScreenshot:
    """take_fullscreen_screenshot now delegates to screengrab.grab_fullscreen."""

    def test_calls_grab_fullscreen_success(self):
        with patch("transformers_ocr.screengrab.grab_fullscreen", return_value=True) as mock_grab:
            tocr_platform.take_fullscreen_screenshot("/tmp/full.png")
            mock_grab.assert_called_once_with("/tmp/full.png")

    def test_grab_fullscreen_failure_raises(self):
        with patch("transformers_ocr.screengrab.grab_fullscreen", return_value=False), \
             pytest.raises(RuntimeError, match="Screen capture failed"):
            tocr_platform.take_fullscreen_screenshot("/tmp/full.png")

    def test_error_message_mentions_x11(self):
        with patch("transformers_ocr.screengrab.grab_fullscreen", return_value=False):
            try:
                tocr_platform.take_fullscreen_screenshot("/tmp/full.png")
            except RuntimeError as e:
                assert "X11" in str(e)

    def test_error_message_mentions_wayland(self):
        with patch("transformers_ocr.screengrab.grab_fullscreen", return_value=False):
            try:
                tocr_platform.take_fullscreen_screenshot("/tmp/full.png")
            except RuntimeError as e:
                assert "Wayland" in str(e)
