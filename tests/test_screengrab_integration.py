"""Integration tests for transformers_ocr.screengrab — require Xvfb.

Run via:
    make test-xvfb

Requires: xorg-server-xvfb, libx11, sdl2, sdl2_image, python-pytest-timeout

IMPORTANT: WAYLAND_DISPLAY must be unset when running these tests,
otherwise they will be skipped. The Makefile handles this via `env -u`.
"""

import ctypes
import ctypes.util
import os
import struct
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from transformers_ocr import screengrab


# ═══════════════════════════════════════════════════
# Skip conditions
# ═══════════════════════════════════════════════════

def _has_display() -> bool:
    return bool(os.environ.get("DISPLAY"))


def _has_wayland() -> bool:
    """If WAYLAND_DISPLAY is set, we can't reliably test X11 capture."""
    return bool(os.environ.get("WAYLAND_DISPLAY"))


def _has_xlib() -> bool:
    return ctypes.util.find_library("X11") is not None


def _has_sdl2() -> bool:
    return screengrab._load_sdl2() is not None


def _has_sdl2_image() -> bool:
    return screengrab._load_sdl2_image() is not None


def _can_open_display() -> bool:
    """Actually try to open the X display."""
    if not _has_xlib():
        return False
    try:
        xlib = ctypes.CDLL(ctypes.util.find_library("X11"))
        xlib.XOpenDisplay.argtypes = [ctypes.c_char_p]
        xlib.XOpenDisplay.restype = ctypes.c_void_p
        xlib.XCloseDisplay.argtypes = [ctypes.c_void_p]
        xlib.XCloseDisplay.restype = ctypes.c_int
        display = xlib.XOpenDisplay(None)
        if not display:
            return False
        xlib.XCloseDisplay(display)
        return True
    except OSError:
        return False


def _skip_reason() -> str:
    if _has_wayland():
        return (
            "WAYLAND_DISPLAY is set — X11 tests unreliable under XWayland. "
            "Run via `make test-xvfb` which unsets WAYLAND_DISPLAY."
        )
    if not _has_display():
        return "No DISPLAY set. Run under Xvfb: make test-xvfb"
    if not _can_open_display():
        return f"Cannot open DISPLAY={os.environ.get('DISPLAY')}"
    return ""


requires_x11 = pytest.mark.skipif(
    _has_wayland() or not (_has_display() and _can_open_display()),
    reason=_skip_reason(),
)
requires_sdl2 = pytest.mark.skipif(
    not (_has_sdl2() and _has_sdl2_image()),
    reason="SDL2 / SDL2_image not available",
)


# ═══════════════════════════════════════════════════
# Helper
# ═══════════════════════════════════════════════════

def _get_png_dimensions(path: str) -> tuple[int, int]:
    """Read width/height from PNG IHDR chunk."""
    with open(path, "rb") as f:
        sig = f.read(8)
        assert sig == b"\x89PNG\r\n\x1a\n", f"Not a PNG: {sig!r}"
        _length = struct.unpack(">I", f.read(4))[0]
        chunk_type = f.read(4)
        assert chunk_type == b"IHDR"
        width, height = struct.unpack(">II", f.read(8))
    return width, height


def _get_root_geometry() -> tuple[int, int]:
    """Get root window width, height via Xlib."""
    xlib = ctypes.CDLL(ctypes.util.find_library("X11"))
    xlib.XOpenDisplay.argtypes = [ctypes.c_char_p]
    xlib.XOpenDisplay.restype = ctypes.c_void_p
    xlib.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
    xlib.XDefaultRootWindow.restype = ctypes.c_ulong
    xlib.XCloseDisplay.argtypes = [ctypes.c_void_p]
    xlib.XCloseDisplay.restype = ctypes.c_int

    c_uint, c_int, c_ulong = ctypes.c_uint, ctypes.c_int, ctypes.c_ulong
    xlib.XGetGeometry.argtypes = [
        ctypes.c_void_p, c_ulong,
        ctypes.POINTER(c_ulong),
        ctypes.POINTER(c_int), ctypes.POINTER(c_int),
        ctypes.POINTER(c_uint), ctypes.POINTER(c_uint),
        ctypes.POINTER(c_uint), ctypes.POINTER(c_uint),
    ]

    display = xlib.XOpenDisplay(None)
    assert display, "Cannot open display"
    try:
        root = xlib.XDefaultRootWindow(display)
        root_ret, x_ret, y_ret = c_ulong(), c_int(), c_int()
        w_ret, h_ret, bw_ret, d_ret = c_uint(), c_uint(), c_uint(), c_uint()
        xlib.XGetGeometry(
            display, root, ctypes.byref(root_ret),
            ctypes.byref(x_ret), ctypes.byref(y_ret),
            ctypes.byref(w_ret), ctypes.byref(h_ret),
            ctypes.byref(bw_ret), ctypes.byref(d_ret),
        )
        return w_ret.value, h_ret.value
    finally:
        xlib.XCloseDisplay(display)


# ═══════════════════════════════════════════════════
# Xlib basic sanity
# ═══════════════════════════════════════════════════

@requires_x11
class TestXlibSanity:
    """Verify we can talk to X at all."""

    def test_open_close_display(self):
        xlib = ctypes.CDLL(ctypes.util.find_library("X11"))
        xlib.XOpenDisplay.argtypes = [ctypes.c_char_p]
        xlib.XOpenDisplay.restype = ctypes.c_void_p
        xlib.XCloseDisplay.argtypes = [ctypes.c_void_p]
        xlib.XCloseDisplay.restype = ctypes.c_int

        display = xlib.XOpenDisplay(None)
        assert display, f"Failed to open DISPLAY={os.environ.get('DISPLAY')}"
        xlib.XCloseDisplay(display)

    def test_root_window_has_nonzero_size(self):
        w, h = _get_root_geometry()
        assert w > 0, "Root window width is 0"
        assert h > 0, "Root window height is 0"

    def test_root_window_matches_xvfb_config(self):
        """If running under our Xvfb :99, expect 1920×1080."""
        if os.environ.get("DISPLAY") != ":99":
            pytest.skip("Not our Xvfb display")
        w, h = _get_root_geometry()
        assert w == 1920, f"Expected width=1920, got {w}"
        assert h == 1080, f"Expected height=1080, got {h}"


# ═══════════════════════════════════════════════════
# _grab_x11 integration
# ═══════════════════════════════════════════════════

@requires_x11
@requires_sdl2
class TestGrabX11Integration:
    """Full integration: capture X11 root window to PNG file."""

    @pytest.mark.timeout(10)
    def test_capture_creates_png(self, tmp_path):
        output = tmp_path / "screenshot.png"
        result = screengrab._grab_x11(str(output))
        assert result is True, "X11 capture returned False"
        assert output.exists(), "Screenshot file not created"
        assert output.stat().st_size > 0, "Screenshot file is empty"

    @pytest.mark.timeout(10)
    def test_capture_png_header(self, tmp_path):
        """Verify the file starts with PNG magic bytes."""
        output = tmp_path / "screenshot.png"
        assert screengrab._grab_x11(str(output)) is True
        with open(output, "rb") as f:
            header = f.read(8)
        assert header == b"\x89PNG\r\n\x1a\n", f"Not a PNG: {header!r}"

    @pytest.mark.timeout(10)
    def test_capture_reasonable_size(self, tmp_path):
        """A 1920×1080 capture should produce at least a few KB."""
        output = tmp_path / "screenshot.png"
        assert screengrab._grab_x11(str(output)) is True
        size = output.stat().st_size
        assert size > 1024, f"Screenshot suspiciously small: {size} bytes"

    @pytest.mark.timeout(10)
    def test_capture_to_nonexistent_dir_fails(self):
        result = screengrab._grab_x11("/nonexistent/dir/screenshot.png")
        assert result is False

    @pytest.mark.timeout(15)
    def test_capture_twice_no_leak(self, tmp_path):
        """Run capture twice to catch resource leaks (display, XImage)."""
        for i in range(2):
            output = tmp_path / f"shot_{i}.png"
            assert screengrab._grab_x11(str(output)) is True
            assert output.exists()

    @pytest.mark.timeout(15)
    def test_capture_different_paths(self, tmp_path):
        """Two captures produce independent files."""
        out1 = tmp_path / "a.png"
        out2 = tmp_path / "b.png"
        assert screengrab._grab_x11(str(out1)) is True
        assert screengrab._grab_x11(str(out2)) is True
        assert out1.stat().st_size > 0
        assert out2.stat().st_size > 0


# ═══════════════════════════════════════════════════
# grab_fullscreen integration (X11 path)
# ═══════════════════════════════════════════════════

@requires_x11
@requires_sdl2
class TestGrabFullscreenX11:
    """Test the public API under X11 (no WAYLAND_DISPLAY)."""

    @pytest.mark.timeout(10)
    def test_fullscreen_produces_valid_png(self, tmp_path):
        output = tmp_path / "full.png"
        result = screengrab.grab_fullscreen(str(output))
        assert result is True
        assert output.exists()
        with open(output, "rb") as f:
            assert f.read(4) == b"\x89PNG"

    @pytest.mark.timeout(10)
    def test_fullscreen_not_wayland_path(self, tmp_path):
        """Verify we're going through X11, not Wayland portal."""
        assert not os.environ.get("WAYLAND_DISPLAY"), \
            "WAYLAND_DISPLAY must be unset for this test"
        output = tmp_path / "full.png"
        assert screengrab.grab_fullscreen(str(output)) is True


# ═══════════════════════════════════════════════════
# Capture content validation
# ═══════════════════════════════════════════════════

@requires_x11
@requires_sdl2
class TestCaptureContent:
    """Verify the captured image has correct dimensions."""

    @pytest.mark.timeout(10)
    def test_dimensions_match_display(self, tmp_path):
        """Screenshot dimensions should match root window size."""
        expected_w, expected_h = _get_root_geometry()
        output = tmp_path / "shot.png"
        assert screengrab._grab_x11(str(output)) is True
        actual_w, actual_h = _get_png_dimensions(str(output))
        assert actual_w == expected_w, f"Width: {actual_w} != {expected_w}"
        assert actual_h == expected_h, f"Height: {actual_h} != {expected_h}"

    @pytest.mark.timeout(10)
    def test_fullscreen_dimensions(self, tmp_path):
        """grab_fullscreen should also produce correct dimensions."""
        expected_w, expected_h = _get_root_geometry()
        output = tmp_path / "full.png"
        assert screengrab.grab_fullscreen(str(output)) is True
        actual_w, actual_h = _get_png_dimensions(str(output))
        assert actual_w == expected_w
        assert actual_h == expected_h
