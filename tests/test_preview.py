"""Tests for transformers_ocr.preview — coordinate transforms and rotation."""

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from transformers_ocr import preview as tocr_preview


class TestPreviewAvailable:
    def test_preview_available_returns_bool(self):
        result = tocr_preview.preview_available()
        assert isinstance(result, bool)

    def test_preview_available_matches_sdl_flag(self):
        assert tocr_preview.preview_available() == tocr_preview._HAS_SDL2


class TestPreviewImageNoSdl:
    """Tests for preview_image when SDL2 is not available."""

    def test_returns_path_when_no_sdl(self, capsys):
        with patch.object(tocr_preview, "_HAS_SDL2", False):
            result = tocr_preview.preview_image("/some/path.png")
        assert result == "/some/path.png"
        assert "unavailable" in capsys.readouterr().err.lower()

    def test_returns_path_with_can_overwrite(self, capsys):
        with patch.object(tocr_preview, "_HAS_SDL2", False):
            result = tocr_preview.preview_image("/img.png", can_overwrite=True)
        assert result == "/img.png"


class TestPreviewImageWithSdl:
    """Tests for preview_image when SDL2 is available."""

    def test_calls_crop_overlay(self):
        mock_overlay = MagicMock()
        mock_overlay.return_value.run.return_value = "/cropped.png"
        with patch.object(tocr_preview, "_HAS_SDL2", True), \
             patch.object(tocr_preview, "_CropOverlay", mock_overlay):
            result = tocr_preview.preview_image("/input.png", can_overwrite=True)
        mock_overlay.assert_called_once_with("/input.png", True)
        mock_overlay.return_value.run.assert_called_once()
        assert result == "/cropped.png"

    def test_overlay_returns_none_on_cancel(self):
        mock_overlay = MagicMock()
        mock_overlay.return_value.run.return_value = None
        with patch.object(tocr_preview, "_HAS_SDL2", True), \
             patch.object(tocr_preview, "_CropOverlay", mock_overlay):
            result = tocr_preview.preview_image("/input.png")
        assert result is None

    def test_overlay_exception_returns_original_path(self, capsys):
        mock_overlay = MagicMock()
        mock_overlay.side_effect = RuntimeError("SDL init failed")
        with patch.object(tocr_preview, "_HAS_SDL2", True), \
             patch.object(tocr_preview, "_CropOverlay", mock_overlay):
            result = tocr_preview.preview_image("/input.png")
        assert result == "/input.png"
        assert "failed" in capsys.readouterr().err.lower()

    def test_overlay_run_exception_returns_original_path(self, capsys):
        mock_overlay = MagicMock()
        mock_overlay.return_value.run.side_effect = RuntimeError("render error")
        with patch.object(tocr_preview, "_HAS_SDL2", True), \
             patch.object(tocr_preview, "_CropOverlay", mock_overlay):
            result = tocr_preview.preview_image("/input.png")
        assert result == "/input.png"
        assert "failed" in capsys.readouterr().err.lower()


# ═══════════════════════════════════════════════════
# _transform_point helpers
# ═══════════════════════════════════════════════════


class TestTransformPointCW90:
    """Tests for _transform_point_cw90."""

    def test_origin(self):
        # (0,0) in 100×200 → (200 - 0, 0) = (200, 0)
        x, y = tocr_preview._transform_point_cw90(0, 0, 100, 200)
        assert x == pytest.approx(200.0)
        assert y == pytest.approx(0.0)

    def test_bottom_right(self):
        # (100, 200) in 100×200 → (200 - 200, 100) = (0, 100)
        x, y = tocr_preview._transform_point_cw90(100, 200, 100, 200)
        assert x == pytest.approx(0.0)
        assert y == pytest.approx(100.0)

    def test_center(self):
        # (50, 100) in 100×200 → (200 - 100, 50) = (100, 50)
        x, y = tocr_preview._transform_point_cw90(50, 100, 100, 200)
        assert x == pytest.approx(100.0)
        assert y == pytest.approx(50.0)

    def test_square_image(self):
        x, y = tocr_preview._transform_point_cw90(30, 70, 100, 100)
        assert x == pytest.approx(100 - 70)
        assert y == pytest.approx(30.0)


class TestTransformPoint:
    """Tests for _transform_point (multi-step CW rotations)."""

    def test_zero_steps_identity(self):
        x, y = tocr_preview._transform_point(10, 20, 100, 200, 0)
        assert x == pytest.approx(10.0)
        assert y == pytest.approx(20.0)

    def test_one_step_matches_cw90(self):
        x1, y1 = tocr_preview._transform_point_cw90(10, 20, 100, 200)
        x2, y2 = tocr_preview._transform_point(10, 20, 100, 200, 1)
        assert x1 == pytest.approx(x2)
        assert y1 == pytest.approx(y2)

    def test_four_steps_identity(self):
        """360° rotation = identity."""
        x, y = tocr_preview._transform_point(37, 53, 800, 600, 4)
        assert x == pytest.approx(37.0)
        assert y == pytest.approx(53.0)

    def test_two_steps_180(self):
        # 180° on 100×200: (x,y) → (100-x, 200-y)
        x, y = tocr_preview._transform_point(10, 20, 100, 200, 2)
        assert x == pytest.approx(90.0)
        assert y == pytest.approx(180.0)

    def test_three_steps_270(self):
        # Check roundtrip: 3 steps + 1 step = identity
        x3, y3 = tocr_preview._transform_point(25, 75, 800, 600, 3)
        # After 3 steps effective size is (600, 800), so one more step:
        x4, y4 = tocr_preview._transform_point_cw90(x3, y3, 600, 800)
        # x4,y4 should be original point since 3+1 = 4 ≡ 0
        assert x4 == pytest.approx(25.0)
        assert y4 == pytest.approx(75.0)

    def test_symmetry_origin(self):
        """Origin stays consistent through rotations."""
        x1, y1 = tocr_preview._transform_point(0, 0, 100, 200, 1)
        assert x1 == pytest.approx(200.0)
        assert y1 == pytest.approx(0.0)

    def test_large_image(self):
        x, y = tocr_preview._transform_point(1920, 1080, 3840, 2160, 1)
        # One CW90: (2160 - 1080, 1920) = (1080, 1920)
        assert x == pytest.approx(1080.0)
        assert y == pytest.approx(1920.0)


class TestCropOverlayUnit:
    """Unit tests for _CropOverlay internals (coordinate math, crop rect logic).

    These test the pure-logic methods without actually initialising SDL.
    """

    def _make_overlay_stub(self, img_w=800, img_h=600, scr_w=1920, scr_h=1080):
        """Create a _CropOverlay without calling __init__ (no SDL)."""
        obj = object.__new__(tocr_preview._CropOverlay)
        obj._path = "/fake.png"
        obj._can_overwrite = True
        obj._result = None
        obj._running = True
        obj._needs_redraw = True
        obj._rot = 0
        obj._zoom = 1.0
        obj._ox = 0.0
        obj._oy = 0.0
        obj._sel_active = False
        obj._has_sel = False
        obj._sel_x0 = obj._sel_y0 = 0.0
        obj._sel_x1 = obj._sel_y1 = 0.0
        obj._pan_active = False
        obj._pan_start_x = obj._pan_start_y = 0
        obj._pan_ox = obj._pan_oy = 0.0
        obj._ptr_x = obj._ptr_y = 0
        obj._img_w = img_w
        obj._img_h = img_h
        obj._scr_w = scr_w
        obj._scr_h = scr_h
        # These are SDL resources, not needed for logic tests
        obj._surface = None
        obj._texture = None
        obj._renderer = None
        obj._window = None
        obj._cursor = None
        return obj

    # ── _effective_size ──

    def test_effective_size_no_rotation(self):
        ov = self._make_overlay_stub(800, 600)
        assert ov._effective_size() == (800.0, 600.0)

    def test_effective_size_90_rotation(self):
        ov = self._make_overlay_stub(800, 600)
        ov._rot = 90
        assert ov._effective_size() == (600.0, 800.0)

    def test_effective_size_180_rotation(self):
        ov = self._make_overlay_stub(800, 600)
        ov._rot = 180
        assert ov._effective_size() == (800.0, 600.0)

    def test_effective_size_270_rotation(self):
        ov = self._make_overlay_stub(800, 600)
        ov._rot = 270
        assert ov._effective_size() == (600.0, 800.0)

    # ── coordinate transforms roundtrip ──

    def test_screen_to_image_roundtrip(self):
        ov = self._make_overlay_stub(800, 600, 1920, 1080)
        ov._zoom = 1.5
        ov._ox = 10.0
        ov._oy = -20.0
        sx, sy = 500.0, 300.0
        ix, iy = ov._screen_to_image(sx, sy)
        sx2, sy2 = ov._image_to_screen(ix, iy)
        assert abs(sx - sx2) < 0.01
        assert abs(sy - sy2) < 0.01

    def test_screen_to_image_center(self):
        ov = self._make_overlay_stub(100, 100, 200, 200)
        ov._zoom = 1.0
        ov._ox = 0.0
        ov._oy = 0.0
        # Image centered: top-left at (50, 50), so center of image at (100, 100)
        ix, iy = ov._screen_to_image(100.0, 100.0)
        assert abs(ix - 50.0) < 0.01
        assert abs(iy - 50.0) < 0.01

    # ── _viewport_center_in_image / _center_image_point ──

    def test_viewport_center_roundtrip(self):
        ov = self._make_overlay_stub(800, 600, 1920, 1080)
        ov._zoom = 1.5
        ov._ox = 30.0
        ov._oy = -10.0
        ix, iy = ov._viewport_center_in_image()
        ov._center_image_point(ix, iy)
        assert abs(ov._ox - 30.0) < 0.01
        assert abs(ov._oy - (-10.0)) < 0.01

    def test_center_image_point_origin(self):
        ov = self._make_overlay_stub(800, 600, 1920, 1080)
        ov._zoom = 1.0
        ov._center_image_point(0.0, 0.0)
        # After centering (0,0) on screen center, _image_to_screen(0,0) should be screen center
        sx, sy = ov._image_to_screen(0.0, 0.0)
        assert abs(sx - 1920 / 2) < 0.01
        assert abs(sy - 1080 / 2) < 0.01

    # ── _get_crop_rect ──

    def test_get_crop_rect_no_selection(self):
        ov = self._make_overlay_stub()
        ov._has_sel = False
        assert ov._get_crop_rect() is None

    def test_get_crop_rect_tiny_selection(self):
        ov = self._make_overlay_stub()
        ov._has_sel = True
        ov._sel_x0, ov._sel_y0 = 10.0, 10.0
        ov._sel_x1, ov._sel_y1 = 11.0, 11.0  # only 1px
        assert ov._get_crop_rect() is None

    def test_get_crop_rect_valid_no_rotation(self):
        ov = self._make_overlay_stub(800, 600)
        ov._has_sel = True
        ov._sel_x0, ov._sel_y0 = 100.0, 50.0
        ov._sel_x1, ov._sel_y1 = 400.0, 300.0
        rect = ov._get_crop_rect()
        assert rect is not None
        rx, ry, rw, rh = rect
        assert rx == 100
        assert ry == 50
        assert rw == 300
        assert rh == 250

    def test_get_crop_rect_swapped_coords(self):
        """Selection drawn right-to-left / bottom-to-top."""
        ov = self._make_overlay_stub(800, 600)
        ov._has_sel = True
        ov._sel_x0, ov._sel_y0 = 400.0, 300.0
        ov._sel_x1, ov._sel_y1 = 100.0, 50.0
        rect = ov._get_crop_rect()
        assert rect is not None
        rx, ry, rw, rh = rect
        assert rx == 100
        assert ry == 50
        assert rw == 300
        assert rh == 250

    def test_get_crop_rect_clamped_to_image(self):
        ov = self._make_overlay_stub(800, 600)
        ov._has_sel = True
        ov._sel_x0, ov._sel_y0 = -50.0, -50.0
        ov._sel_x1, ov._sel_y1 = 900.0, 700.0
        rect = ov._get_crop_rect()
        assert rect is not None
        rx, ry, rw, rh = rect
        assert rx == 0
        assert ry == 0
        assert rw == 800
        assert rh == 600

    def test_get_crop_rect_90_rotation(self):
        """After 90° CW rotation, crop coords are transformed back to original space."""
        ov = self._make_overlay_stub(800, 600)
        ov._rot = 90
        ov._has_sel = True
        ov._sel_x0, ov._sel_y0 = 100.0, 200.0
        ov._sel_x1, ov._sel_y1 = 300.0, 500.0
        rect = ov._get_crop_rect()
        assert rect is not None
        rx, ry, rw, rh = rect
        assert rw > 0
        assert rh > 0
        assert rx >= 0 and ry >= 0
        assert rx + rw <= 800
        assert ry + rh <= 600

    def test_get_crop_rect_180_rotation(self):
        ov = self._make_overlay_stub(800, 600)
        ov._rot = 180
        ov._has_sel = True
        ov._sel_x0, ov._sel_y0 = 100.0, 100.0
        ov._sel_x1, ov._sel_y1 = 400.0, 400.0
        rect = ov._get_crop_rect()
        assert rect is not None
        rx, ry, rw, rh = rect
        assert rw > 0 and rh > 0

    def test_get_crop_rect_270_rotation(self):
        ov = self._make_overlay_stub(800, 600)
        ov._rot = 270
        ov._has_sel = True
        ov._sel_x0, ov._sel_y0 = 50.0, 50.0
        ov._sel_x1, ov._sel_y1 = 200.0, 300.0
        rect = ov._get_crop_rect()
        assert rect is not None
        rx, ry, rw, rh = rect
        assert rw > 0 and rh > 0

    # ── _fit ──

    def test_fit_resets_offset(self):
        ov = self._make_overlay_stub(800, 600, 1920, 1080)
        ov._ox = 100.0
        ov._oy = -50.0
        ov._zoom = 3.0
        ov._fit()
        assert ov._ox == 0.0
        assert ov._oy == 0.0
        expected_zoom = min(1920 / 800, 1080 / 600)
        assert abs(ov._zoom - expected_zoom) < 0.001

    # ── _zoom_at ──

    def test_zoom_at_increases(self):
        ov = self._make_overlay_stub()
        old = ov._zoom
        ov._zoom_at(1.25, 960.0, 540.0)
        assert ov._zoom > old

    def test_zoom_at_decreases(self):
        ov = self._make_overlay_stub()
        ov._zoom = 2.0
        ov._zoom_at(0.8, 960.0, 540.0)
        assert ov._zoom < 2.0

    def test_zoom_clamped_min(self):
        ov = self._make_overlay_stub()
        ov._zoom = 0.15
        ov._zoom_at(0.01, 960.0, 540.0)
        assert ov._zoom >= ov._MIN_ZOOM

    def test_zoom_clamped_max(self):
        ov = self._make_overlay_stub()
        ov._zoom = 19.0
        ov._zoom_at(100.0, 960.0, 540.0)
        assert ov._zoom <= ov._MAX_ZOOM

    def test_zoom_at_no_change_when_at_limit(self):
        ov = self._make_overlay_stub()
        ov._zoom = ov._MAX_ZOOM
        old_ox = ov._ox
        ov._zoom_at(2.0, 960.0, 540.0)
        assert ov._zoom == ov._MAX_ZOOM
        assert ov._ox == old_ox

    # ── _rotate (new behavior: preserves selection and viewport) ──

    def test_rotate_cw_preserves_selection(self):
        ov = self._make_overlay_stub()
        ov._has_sel = True
        ov._sel_x0, ov._sel_y0 = 100.0, 100.0
        ov._sel_x1, ov._sel_y1 = 300.0, 200.0
        ov._rotate(90)
        assert ov._rot == 90
        assert ov._has_sel is True  # selection preserved now

    def test_rotate_ccw(self):
        ov = self._make_overlay_stub()
        ov._rotate(-90)
        assert ov._rot == 270

    def test_rotate_full_circle(self):
        ov = self._make_overlay_stub()
        for _ in range(4):
            ov._rotate(90)
        assert ov._rot == 0

    def test_rotate_zero_degrees_noop(self):
        ov = self._make_overlay_stub()
        ov._ox = 42.0
        ov._oy = -7.0
        ov._rotate(0)
        assert ov._rot == 0
        assert ov._ox == 42.0
        assert ov._oy == -7.0

    def test_rotate_180_degrees(self):
        ov = self._make_overlay_stub()
        ov._rotate(180)
        assert ov._rot == 180

    def test_rotate_selection_normalized(self):
        """After rotation, selection coords should be normalized (x0<=x1, y0<=y1)."""
        ov = self._make_overlay_stub(800, 600)
        ov._has_sel = True
        ov._sel_x0, ov._sel_y0 = 100.0, 50.0
        ov._sel_x1, ov._sel_y1 = 400.0, 300.0
        ov._rotate(90)
        assert ov._sel_x0 <= ov._sel_x1
        assert ov._sel_y0 <= ov._sel_y1

    def test_rotate_preserves_viewport_center(self):
        """Viewport center should map to the same image point after rotation."""
        ov = self._make_overlay_stub(800, 600, 1920, 1080)
        ov._zoom = 1.5
        ov._ox = 20.0
        ov._oy = -30.0
        # Get image point at viewport center before rotation
        vc_before = ov._viewport_center_in_image()
        ov._rotate(90)
        # After rotation, the viewport center should still correspond to the
        # transformed version of the original center point
        vc_after = ov._viewport_center_in_image()
        # Transform the original center point through the same rotation
        expected = tocr_preview._transform_point(vc_before[0], vc_before[1], 800.0, 600.0, 1)
        assert abs(vc_after[0] - expected[0]) < 1.0
        assert abs(vc_after[1] - expected[1]) < 1.0

    def test_rotate_without_selection(self):
        """Rotation without selection should not crash."""
        ov = self._make_overlay_stub()
        ov._has_sel = False
        ov._sel_active = False
        ov._rotate(90)
        assert ov._rot == 90
        assert ov._has_sel is False

    # ── _accept / _cancel ──

    def test_cancel_sets_result_none(self):
        ov = self._make_overlay_stub()
        ov._cancel()
        assert ov._result is None
        assert ov._running is False

    def test_accept_calls_save_cropped(self):
        ov = self._make_overlay_stub()
        with patch.object(ov, "_save_cropped", return_value="/saved.png"):
            ov._accept()
        assert ov._result == "/saved.png"
        assert ov._running is False
