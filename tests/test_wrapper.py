"""Tests for transformers_ocr.wrapper (MangaOcrWrapper)."""

import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from transformers_ocr import config as tocr_config
from transformers_ocr import notify as tocr_notify
from transformers_ocr import platform as tocr_platform
from transformers_ocr import wrapper as tocr_wrapper
from transformers_ocr.exceptions import MissingProgram, StopRequested
from transformers_ocr.ocr_command import OcrCommand


class TestMangaOcrWrapper:
    def _make_wrapper(self, **config_overrides):
        with patch.object(tocr_config, "CONFIG_PATH", "/nonexistent"):
            w = object.__new__(tocr_wrapper.MangaOcrWrapper)
            w._config = tocr_config.TrOcrConfig()
            for k, v in config_overrides.items():
                setattr(w._config, k, v)
            w._on_hold = []
            w._mocr = MagicMock()
            return w

    # ── _ocr text replacements ──

    def test_ocr_ascii_ellipsis(self):
        w = self._make_wrapper()
        w._mocr.return_value = "text...end"
        assert w._ocr("/f") == "text…end"

    def test_ocr_japanese_ellipsis(self):
        w = self._make_wrapper()
        w._mocr.return_value = "テスト。。。"
        assert w._ocr("/f") == "テスト…"

    def test_ocr_fullwidth_ellipsis(self):
        w = self._make_wrapper()
        w._mocr.return_value = "テスト．．．"
        assert w._ocr("/f") == "テスト…"

    def test_ocr_no_replacement(self):
        w = self._make_wrapper()
        w._mocr.return_value = "普通のテキスト"
        assert w._ocr("/f") == "普通のテキスト"

    def test_ocr_multiple_replacements(self):
        w = self._make_wrapper()
        w._mocr.return_value = "a...b。。。c"
        assert w._ocr("/f") == "a…b…c"

    # ── _process_command ──

    def test_process_stop(self):
        w = self._make_wrapper()
        with pytest.raises(StopRequested):
            w._process_command(OcrCommand(action="stop", file_path=None))

    def test_process_hold(self, tmp_path):
        img = tmp_path / "img.png"
        img.write_bytes(b"png")
        w = self._make_wrapper()
        w._mocr.return_value = "held"
        with patch.object(tocr_notify, "notify_send"), \
             patch.object(tocr_wrapper, "notify_send"):
            w._process_command(OcrCommand(action="hold", file_path=str(img)))
        assert w._on_hold == ["held"]

    def test_process_recognize_joins_held(self, tmp_path):
        img = tmp_path / "img.png"
        img.write_bytes(b"png")
        w = self._make_wrapper()
        w._on_hold = ["part1", "part2"]
        w._mocr.return_value = "part3"
        with patch.object(tocr_wrapper, "notify_send"), \
             patch.object(w, "_to_clip") as mock_clip:
            w._process_command(OcrCommand(action="recognize", file_path=str(img)))
        mock_clip.assert_called_once_with("part1、part2、part3")
        assert w._on_hold == []

    def test_process_deletes_temp_file(self, tmp_path):
        img = tmp_path / "temp.png"
        img.write_bytes(b"png")
        w = self._make_wrapper()
        w._mocr.return_value = "text"
        with patch.object(tocr_wrapper, "notify_send"), patch.object(w, "_to_clip"):
            w._process_command(OcrCommand(action="recognize", file_path=str(img), delete_after=True))
        assert not img.exists()

    def test_process_preserves_user_image(self, tmp_path):
        img = tmp_path / "user.png"
        img.write_bytes(b"png")
        w = self._make_wrapper()
        w._mocr.return_value = "text"
        with patch.object(tocr_wrapper, "notify_send"), patch.object(w, "_to_clip"):
            w._process_command(OcrCommand(action="recognize", file_path=str(img), delete_after=False))
        assert img.exists()

    # ── _to_clip ──

    def test_to_clip_stdin(self):
        w = self._make_wrapper()
        with patch.dict(os.environ, {}, clear=False), \
             patch.object(tocr_platform, "raise_if_missing"), \
             patch.object(tocr_wrapper, "raise_if_missing"), \
             patch("subprocess.Popen") as mock_popen, \
             patch.object(tocr_wrapper, "notify_send"):
            os.environ.pop("WAYLAND_DISPLAY", None)
            proc = MagicMock()
            mock_popen.return_value = proc
            w._to_clip("hello")
            assert mock_popen.call_args[0][0][0] == "xclip"
            assert mock_popen.call_args[1]["stdin"] is not None
            proc.communicate.assert_called_once_with(input=b"hello", timeout=10)

    def test_to_clip_placeholder(self):
        w = self._make_wrapper(clip_args=["goldendict", "%TEXT%"])
        with patch.object(tocr_wrapper, "raise_if_missing"), \
             patch("subprocess.Popen") as mock_popen, \
             patch.object(tocr_wrapper, "notify_send"):
            proc = MagicMock()
            mock_popen.return_value = proc
            w._to_clip("テスト")
            assert mock_popen.call_args[0][0] == ["goldendict", "テスト"]
            assert mock_popen.call_args[1]["stdin"] is None
            proc.wait.assert_called_once_with(timeout=10)

    def test_to_clip_missing_program(self):
        w = self._make_wrapper()
        with patch.object(tocr_wrapper, "raise_if_missing", side_effect=MissingProgram("xclip")), \
             patch.object(tocr_wrapper, "notify_send") as mock_notify:
            w._to_clip("hello")
            assert "xclip" in mock_notify.call_args[0][0]

    def test_to_clip_timeout(self):
        w = self._make_wrapper()
        with patch.object(tocr_wrapper, "raise_if_missing"), \
             patch("subprocess.Popen") as mock_popen, \
             patch.object(tocr_wrapper, "notify_send") as mock_notify:
            proc = MagicMock()
            proc.communicate.side_effect = subprocess.TimeoutExpired("cmd", 10)
            mock_popen.return_value = proc
            w._to_clip("hello")
            proc.kill.assert_called_once()
            assert "timed out" in mock_notify.call_args[0][0].lower()

    # ── _maybe_save_result ──

    def test_maybe_save_result(self, tmp_path):
        sdir = tmp_path / "shots"
        sdir.mkdir()
        img = tmp_path / "src.png"
        img.write_bytes(b"png data")
        w = self._make_wrapper(screenshot_dir=str(sdir))
        w._maybe_save_result(str(img), "recognized text")
        assert len(list(sdir.glob("*.gt.txt"))) == 1
        assert len(list(sdir.glob("*.png"))) == 1
        assert list(sdir.glob("*.gt.txt"))[0].read_text() == "recognized text"

    def test_maybe_save_result_disabled(self, tmp_path):
        w = self._make_wrapper(screenshot_dir=None)
        w._maybe_save_result("/fake.png", "text")

    # ── _load_model ──

    def test_load_model_passes_config(self):
        mock_manga_ocr = MagicMock()
        with patch.object(tocr_config, "CONFIG_PATH", "/nonexistent"), \
             patch.dict(sys.modules, {"manga_ocr": mock_manga_ocr}):
            w = tocr_wrapper.MangaOcrWrapper()
            mock_manga_ocr.MangaOcr.assert_called_once_with(
                pretrained_model_name_or_path=tocr_config.DEFAULT_MODEL,
                force_cpu=False,
            )

    def test_load_model_custom(self, tmp_path):
        (tmp_path / "config").write_text("model=jzhang533/manga-ocr-base-2025\n")
        mock_manga_ocr = MagicMock()
        with patch.object(tocr_config, "CONFIG_PATH", str(tmp_path / "config")), \
             patch.dict(sys.modules, {"manga_ocr": mock_manga_ocr}):
            w = tocr_wrapper.MangaOcrWrapper()
            mock_manga_ocr.MangaOcr.assert_called_once_with(
                pretrained_model_name_or_path="jzhang533/manga-ocr-base-2025",
                force_cpu=False,
            )

    def test_load_model_force_cpu(self, tmp_path):
        (tmp_path / "config").write_text("force_cpu=yes\n")
        mock_manga_ocr = MagicMock()
        with patch.object(tocr_config, "CONFIG_PATH", str(tmp_path / "config")), \
             patch.dict(sys.modules, {"manga_ocr": mock_manga_ocr}):
            w = tocr_wrapper.MangaOcrWrapper()
            mock_manga_ocr.MangaOcr.assert_called_once_with(
                pretrained_model_name_or_path=tocr_config.DEFAULT_MODEL,
                force_cpu=True,
            )
