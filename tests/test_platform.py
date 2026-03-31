"""Tests for transformers_ocr.platform"""

import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from transformers_ocr import platform as tocr_platform
from transformers_ocr.exceptions import MissingProgram, ScreenshotCancelled


class TestPlatformDetection:
    def test_is_xorg_no_wayland(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("WAYLAND_DISPLAY", None)
            assert tocr_platform._is_xorg() is True

    def test_is_xorg_wayland_set(self):
        with patch.dict(os.environ, {"WAYLAND_DISPLAY": "wayland-0"}):
            assert tocr_platform._is_xorg() is False

    def test_platform_gnome(self):
        with patch.dict(os.environ, {"XDG_CURRENT_DESKTOP": "GNOME"}):
            assert tocr_platform.Platform.current() == tocr_platform.Platform.GNOME

    def test_platform_kde(self):
        with patch.dict(os.environ, {"XDG_CURRENT_DESKTOP": "KDE"}):
            assert tocr_platform.Platform.current() == tocr_platform.Platform.KDE

    def test_platform_xfce(self):
        with patch.dict(os.environ, {"XDG_CURRENT_DESKTOP": "XFCE"}):
            assert tocr_platform.Platform.current() == tocr_platform.Platform.XFCE

    def test_platform_xorg(self):
        with patch.dict(os.environ, {"XDG_CURRENT_DESKTOP": ""}, clear=False):
            os.environ.pop("WAYLAND_DISPLAY", None)
            assert tocr_platform.Platform.current() == tocr_platform.Platform.Xorg

    def test_platform_wayland(self):
        with patch.dict(os.environ, {"XDG_CURRENT_DESKTOP": "", "WAYLAND_DISPLAY": "wayland-0"}):
            assert tocr_platform.Platform.current() == tocr_platform.Platform.Wayland

    def test_clip_args_xorg(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("WAYLAND_DISPLAY", None)
            assert tocr_platform.get_clip_copy_args() == ("xclip", "-selection", "clipboard")

    def test_clip_args_wayland(self):
        with patch.dict(os.environ, {"WAYLAND_DISPLAY": "wayland-0"}):
            assert tocr_platform.get_clip_copy_args() == ("wl-copy",)


class TestDependencyChecks:
    def test_is_installed_which(self):
        with patch("shutil.which", return_value="/usr/bin/bash"):
            assert tocr_platform.is_installed("bash") is True

    def test_is_installed_not_found(self):
        with patch("shutil.which", return_value=None), \
             patch("subprocess.call", side_effect=FileNotFoundError):
            assert tocr_platform.is_installed("nonexistent") is False

    def test_is_installed_pacman_fallback(self):
        with patch("shutil.which", return_value=None), \
             patch("subprocess.call", return_value=0):
            assert tocr_platform.is_installed("pkg") is True

    def test_is_installed_pacman_not_found(self):
        with patch("shutil.which", return_value=None), \
             patch("subprocess.call", return_value=1):
            assert tocr_platform.is_installed("missing") is False

    def test_raise_if_missing_present(self):
        with patch.object(tocr_platform, "is_installed", return_value=True):
            tocr_platform.raise_if_missing("a", "b")

    def test_raise_if_missing_absent(self):
        with patch.object(tocr_platform, "is_installed", return_value=False), \
             pytest.raises(MissingProgram, match="grim"):
            tocr_platform.raise_if_missing("grim")


class TestScreenshotDispatch:
    @pytest.mark.parametrize("env,expected_fn", [
        ({"XDG_CURRENT_DESKTOP": "GNOME", "WAYLAND_DISPLAY": "w-0"}, "_gnome_screenshot_select"),
        ({"XDG_CURRENT_DESKTOP": "KDE", "WAYLAND_DISPLAY": "w-0"}, "_spectacle_select"),
        ({"XDG_CURRENT_DESKTOP": "XFCE"}, "_xfce_screenshooter_select"),
    ])
    def test_dispatch_desktop(self, env, expected_fn):
        with patch.dict(os.environ, env, clear=False), \
             patch.object(tocr_platform, expected_fn) as mock_fn:
            tocr_platform.take_screenshot("/tmp/s.png")
            mock_fn.assert_called_once_with("/tmp/s.png")

    def test_dispatch_xorg(self):
        with patch.dict(os.environ, {"XDG_CURRENT_DESKTOP": ""}, clear=False):
            os.environ.pop("WAYLAND_DISPLAY", None)
            with patch.object(tocr_platform, "_maim_select") as mock:
                tocr_platform.take_screenshot("/tmp/s.png")
                mock.assert_called_once_with("/tmp/s.png")

    def test_dispatch_wayland(self):
        with patch.dict(os.environ, {"XDG_CURRENT_DESKTOP": "", "WAYLAND_DISPLAY": "w-0"}), \
             patch.object(tocr_platform, "_grim_select") as mock:
            tocr_platform.take_screenshot("/tmp/s.png")
            mock.assert_called_once_with("/tmp/s.png")

    def test_grim_slurp_cancelled(self):
        with patch.object(tocr_platform, "raise_if_missing"), \
             patch("subprocess.check_output", side_effect=subprocess.CalledProcessError(1, "slurp")), \
             pytest.raises(ScreenshotCancelled, match="cancelled"):
            tocr_platform._grim_select("/tmp/s.png")

    def test_grim_slurp_empty_geometry(self):
        with patch.object(tocr_platform, "raise_if_missing"), \
             patch("subprocess.check_output", return_value=b"\n"), \
             pytest.raises(ScreenshotCancelled, match="empty geometry"):
            tocr_platform._grim_select("/tmp/s.png")


# ═══════════════════════════════════════════════════
# take_fullscreen_screenshot dispatch
# ═══════════════════════════════════════════════════


class TestFullscreenScreenshot:
    """Tests for take_fullscreen_screenshot added in this diff."""

    @pytest.mark.parametrize("platform_val,tool,expected_args", [
        (
            tocr_platform.Platform.GNOME, "gnome-screenshot",
            ("gnome-screenshot", "-f", "/tmp/full.png"),
        ),
        (
            tocr_platform.Platform.KDE, "spectacle",
            ("spectacle", "-n", "-b", "-f", "-o", "/tmp/full.png"),
        ),
        (
            tocr_platform.Platform.XFCE, "xfce4-screenshooter",
            ("xfce4-screenshooter", "-f", "-s", "/tmp/full.png"),
        ),
        (
            tocr_platform.Platform.Wayland, "grim",
            ("grim", "/tmp/full.png"),
        ),
    ])
    def test_fullscreen_dispatch(self, platform_val, tool, expected_args):
        with patch.object(tocr_platform.Platform, "current", return_value=platform_val), \
             patch.object(tocr_platform, "raise_if_missing") as mock_check, \
             patch("subprocess.run") as mock_run:
            tocr_platform.take_fullscreen_screenshot("/tmp/full.png")
            mock_check.assert_called_once_with(tool)
            assert mock_run.call_args[0][0] == expected_args
            assert mock_run.call_args[1]["check"] is True

    def test_fullscreen_xorg_maim(self):
        with patch.object(tocr_platform.Platform, "current", return_value=tocr_platform.Platform.Xorg), \
             patch.object(tocr_platform, "raise_if_missing") as mock_check, \
             patch("subprocess.run") as mock_run:
            tocr_platform.take_fullscreen_screenshot("/tmp/full.png")
            mock_check.assert_called_once_with("maim")
            args = mock_run.call_args[0][0]
            assert args[0] == "maim"
            assert "--hidecursor" in args
            assert "/tmp/full.png" in args

    def test_fullscreen_missing_tool_raises(self):
        with patch.object(tocr_platform.Platform, "current", return_value=tocr_platform.Platform.Wayland), \
             patch.object(tocr_platform, "raise_if_missing", side_effect=MissingProgram("grim")), \
             pytest.raises(MissingProgram, match="grim"):
            tocr_platform.take_fullscreen_screenshot("/tmp/full.png")

    def test_fullscreen_subprocess_error(self):
        with patch.object(tocr_platform.Platform, "current", return_value=tocr_platform.Platform.Wayland), \
             patch.object(tocr_platform, "raise_if_missing"), \
             patch("subprocess.run", side_effect=subprocess.CalledProcessError(1, "grim")), \
             pytest.raises(subprocess.CalledProcessError):
            tocr_platform.take_fullscreen_screenshot("/tmp/full.png")
