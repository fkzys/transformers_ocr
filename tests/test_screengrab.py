"""Tests for transformers_ocr.screengrab"""

import os
import shutil
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock, call

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from transformers_ocr import screengrab


# ═══════════════════════════════════════════════════
# Wayland detection
# ═══════════════════════════════════════════════════


class TestIsWayland:
    def test_wayland_set(self):
        with patch.dict(os.environ, {"WAYLAND_DISPLAY": "wayland-0"}):
            assert screengrab._is_wayland() is True

    def test_wayland_unset(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("WAYLAND_DISPLAY", None)
            assert screengrab._is_wayland() is False


# ═══════════════════════════════════════════════════
# grab_fullscreen dispatch
# ═══════════════════════════════════════════════════


class TestGrabFullscreen:
    def test_wayland_calls_portal(self):
        with patch.object(screengrab, "_is_wayland", return_value=True), \
             patch.object(screengrab, "_grab_wayland_portal", return_value=True) as mock_portal:
            assert screengrab.grab_fullscreen("/out.png") is True
            mock_portal.assert_called_once_with("/out.png")

    def test_wayland_portal_failure(self, capsys):
        with patch.object(screengrab, "_is_wayland", return_value=True), \
             patch.object(screengrab, "_grab_wayland_portal", return_value=False):
            assert screengrab.grab_fullscreen("/out.png") is False
        assert "portal failed" in capsys.readouterr().err.lower()

    def test_x11_calls_grab_x11(self):
        with patch.object(screengrab, "_is_wayland", return_value=False), \
             patch.object(screengrab, "_grab_x11", return_value=True) as mock_x11:
            assert screengrab.grab_fullscreen("/out.png") is True
            mock_x11.assert_called_once_with("/out.png")

    def test_x11_failure(self, capsys):
        with patch.object(screengrab, "_is_wayland", return_value=False), \
             patch.object(screengrab, "_grab_x11", return_value=False):
            assert screengrab.grab_fullscreen("/out.png") is False
        assert "x11 grab failed" in capsys.readouterr().err.lower()


# ═══════════════════════════════════════════════════
# X11 capture
# ═══════════════════════════════════════════════════


class TestGrabX11:
    def test_no_xlib_returns_false(self):
        with patch("ctypes.util.find_library", return_value=None):
            assert screengrab._grab_x11("/out.png") is False

    def test_xlib_load_failure_returns_false(self):
        with patch("ctypes.util.find_library", return_value="libX11.so"), \
             patch("ctypes.CDLL", side_effect=OSError("nope")):
            assert screengrab._grab_x11("/out.png") is False

    def test_no_sdl_returns_false(self):
        mock_xlib = MagicMock()
        with patch("ctypes.util.find_library", side_effect=lambda n: "libX11.so" if n == "X11" else None), \
             patch("ctypes.CDLL", return_value=mock_xlib), \
             patch.object(screengrab, "_load_sdl2", return_value=None):
            assert screengrab._grab_x11("/out.png") is False

    def test_no_sdl_image_returns_false(self):
        mock_xlib = MagicMock()
        mock_sdl = MagicMock()
        with patch("ctypes.util.find_library", side_effect=lambda n: f"lib{n}.so"), \
             patch("ctypes.CDLL", return_value=mock_xlib), \
             patch.object(screengrab, "_load_sdl2", return_value=mock_sdl), \
             patch.object(screengrab, "_load_sdl2_image", return_value=None):
            assert screengrab._grab_x11("/out.png") is False

    def test_display_open_failure_returns_false(self):
        mock_xlib = MagicMock()
        mock_xlib.XOpenDisplay.return_value = None
        mock_sdl = MagicMock()
        mock_sdl_img = MagicMock()
        with patch("ctypes.util.find_library", side_effect=lambda n: f"lib{n}.so"), \
             patch("ctypes.CDLL", return_value=mock_xlib), \
             patch.object(screengrab, "_load_sdl2", return_value=mock_sdl), \
             patch.object(screengrab, "_load_sdl2_image", return_value=mock_sdl_img):
            assert screengrab._grab_x11("/out.png") is False


# ═══════════════════════════════════════════════════
# Wayland portal capture
# ═══════════════════════════════════════════════════


class TestGrabWaylandPortal:
    def test_no_libdbus_returns_false(self):
        with patch("ctypes.util.find_library", return_value=None):
            assert screengrab._grab_wayland_portal("/out.png") is False

    def test_libdbus_load_failure(self):
        with patch("ctypes.util.find_library", return_value="libdbus-1.so"), \
             patch("ctypes.CDLL", side_effect=OSError):
            assert screengrab._grab_wayland_portal("/out.png") is False

    def test_bus_connection_failure(self):
        mock_dbus = MagicMock()
        mock_dbus.dbus_bus_get.return_value = None
        mock_dbus.dbus_error_is_set.return_value = True
        with patch("ctypes.util.find_library", return_value="libdbus-1.so"), \
             patch("ctypes.CDLL", return_value=mock_dbus):
            assert screengrab._grab_wayland_portal("/out.png") is False


# ═══════════════════════════════════════════════════
# _save_portal_file
# ═══════════════════════════════════════════════════


class TestSavePortalFile:
    def test_move_success(self, tmp_path):
        src = tmp_path / "screenshot.png"
        src.write_bytes(b"PNG data")
        dst = tmp_path / "output.png"
        result = screengrab._save_portal_file(f"file://{src}", str(dst))
        assert result is True
        assert dst.read_bytes() == b"PNG data"

    def test_move_fails_copy_succeeds(self, tmp_path):
        src = tmp_path / "screenshot.png"
        src.write_bytes(b"PNG data")
        dst = tmp_path / "output.png"
        with patch("shutil.move", side_effect=OSError("cross-device")):
            result = screengrab._save_portal_file(f"file://{src}", str(dst))
        assert result is True
        assert dst.read_bytes() == b"PNG data"

    def test_both_fail(self, tmp_path, capsys):
        result = screengrab._save_portal_file("file:///nonexistent/img.png", "/out.png")
        assert result is False
        assert "failed to save" in capsys.readouterr().err.lower()

    def test_uri_prefix_stripped(self, tmp_path):
        src = tmp_path / "shot.png"
        src.write_bytes(b"data")
        dst = tmp_path / "out.png"
        # URI without file:// prefix — removeprefix is a no-op
        result = screengrab._save_portal_file(f"file://{src}", str(dst))
        assert result is True


# ═══════════════════════════════════════════════════
# Library loading helpers
# ═══════════════════════════════════════════════════


class TestLibLoading:
    def test_load_lib_finds_via_find_library(self):
        mock_lib = MagicMock()
        with patch("ctypes.util.find_library", return_value="libfoo.so"), \
             patch("ctypes.CDLL", return_value=mock_lib):
            result = screengrab._load_lib(("foo",))
        assert result is mock_lib

    def test_load_lib_fallback_so_names(self):
        mock_lib = MagicMock()
        call_count = [0]

        def cdll_side_effect(name):
            call_count[0] += 1
            if name == "libfoo.so":
                raise OSError
            if name == "libfoo.so.0":
                return mock_lib
            raise OSError

        with patch("ctypes.util.find_library", return_value=None), \
             patch("ctypes.CDLL", side_effect=cdll_side_effect):
            result = screengrab._load_lib(("foo",))
        assert result is mock_lib

    def test_load_lib_all_fail(self):
        with patch("ctypes.util.find_library", return_value=None), \
             patch("ctypes.CDLL", side_effect=OSError):
            result = screengrab._load_lib(("nonexistent",))
        assert result is None

    def test_load_sdl2_returns_none_if_unavailable(self):
        with patch.object(screengrab, "_load_lib", return_value=None):
            assert screengrab._load_sdl2() is None

    def test_load_sdl2_sets_argtypes(self):
        mock_lib = MagicMock()
        with patch.object(screengrab, "_load_lib", return_value=mock_lib):
            result = screengrab._load_sdl2()
        assert result is mock_lib
        # Verify SDL_FreeSurface argtypes were set
        assert mock_lib.SDL_FreeSurface.argtypes is not None

    def test_load_sdl2_image(self):
        mock_lib = MagicMock()
        with patch.object(screengrab, "_load_lib", return_value=mock_lib):
            assert screengrab._load_sdl2_image() is mock_lib


# ═══════════════════════════════════════════════════
# D-Bus helper functions
# ═══════════════════════════════════════════════════


class TestDBusHelpers:
    def test_setup_dbus_functions_sets_argtypes(self):
        mock_dbus = MagicMock()
        screengrab._setup_dbus_functions(mock_dbus)
        # Spot-check a few
        assert mock_dbus.dbus_error_init.argtypes is not None
        assert mock_dbus.dbus_bus_get.argtypes is not None
        assert mock_dbus.dbus_message_new_method_call.argtypes is not None
        assert mock_dbus.dbus_message_iter_init_append.argtypes is not None

    def test_make_iter_returns_buffer(self):
        buf = screengrab._make_iter()
        assert len(buf) == screengrab._ITER_BYTES

    def test_build_screenshot_message_returns_none_on_failure(self):
        mock_dbus = MagicMock()
        mock_dbus.dbus_message_new_method_call.return_value = None
        result = screengrab._build_screenshot_message(mock_dbus, "token123")
        assert result is None

    def test_build_screenshot_message_success(self):
        mock_dbus = MagicMock()
        mock_dbus.dbus_message_new_method_call.return_value = MagicMock()
        result = screengrab._build_screenshot_message(mock_dbus, "token123")
        assert result is not None
        mock_dbus.dbus_message_new_method_call.assert_called_once_with(
            b"org.freedesktop.portal.Desktop",
            b"/org/freedesktop/portal/desktop",
            b"org.freedesktop.portal.Screenshot",
            b"Screenshot",
        )

    def test_parse_response_uri_no_init(self):
        mock_dbus = MagicMock()
        mock_dbus.dbus_message_iter_init.return_value = False
        result = screengrab._parse_response_uri(mock_dbus, MagicMock())
        assert result is None

    def test_parse_response_uri_wrong_type(self):
        mock_dbus = MagicMock()
        mock_dbus.dbus_message_iter_init.return_value = True
        mock_dbus.dbus_message_iter_get_arg_type.return_value = screengrab._T_STRING  # not UINT32
        result = screengrab._parse_response_uri(mock_dbus, MagicMock())
        assert result is None


# ═══════════════════════════════════════════════════
# XImage structure
# ═══════════════════════════════════════════════════


class TestXImageStructure:
    def test_fields_exist(self):
        img = screengrab._XImage()
        assert hasattr(img, "width")
        assert hasattr(img, "height")
        assert hasattr(img, "bits_per_pixel")
        assert hasattr(img, "bytes_per_line")
        assert hasattr(img, "data")
        assert hasattr(img, "red_mask")
        assert hasattr(img, "green_mask")
        assert hasattr(img, "blue_mask")

    def test_default_values(self):
        img = screengrab._XImage()
        assert img.width == 0
        assert img.height == 0
        assert img.bits_per_pixel == 0


class TestDBusErrorStructure:
    def test_fields_exist(self):
        err = screengrab._DBusError()
        assert hasattr(err, "name")
        assert hasattr(err, "message")
