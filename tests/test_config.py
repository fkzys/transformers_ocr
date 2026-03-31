"""Tests for transformers_ocr.config"""

import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from transformers_ocr import config as tocr_config


class TestConfigParsing:
    def test_valid_pair(self):
        assert tocr_config._is_valid_key_val_pair("force_cpu=yes") is True

    def test_valid_pair_with_placeholder(self):
        assert tocr_config._is_valid_key_val_pair("clip_command=goldendict %TEXT%") is True

    def test_comment_rejected(self):
        assert tocr_config._is_valid_key_val_pair("# comment=ignored") is False

    def test_no_equals_rejected(self):
        assert tocr_config._is_valid_key_val_pair("no_equals") is False

    def test_empty_rejected(self):
        assert tocr_config._is_valid_key_val_pair("") is False

    def test_get_config(self, tmp_path):
        (tmp_path / "config").write_text("force_cpu=yes\nclip_command=goldendict %TEXT%\n# comment\n\n")
        with patch.object(tocr_config, "CONFIG_PATH", str(tmp_path / "config")):
            cfg = tocr_config.get_config()
        assert cfg == {"force_cpu": "yes", "clip_command": "goldendict %TEXT%"}

    def test_get_config_missing_file(self):
        with patch.object(tocr_config, "CONFIG_PATH", "/nonexistent"):
            assert tocr_config.get_config() == {}

    def test_get_config_strips_whitespace(self, tmp_path):
        (tmp_path / "config").write_text("  force_cpu  =  yes  \n")
        with patch.object(tocr_config, "CONFIG_PATH", str(tmp_path / "config")):
            assert tocr_config.get_config()["force_cpu"] == "yes"

    def test_get_config_value_with_equals(self, tmp_path):
        (tmp_path / "config").write_text("clip_command=cmd --opt=val\n")
        with patch.object(tocr_config, "CONFIG_PATH", str(tmp_path / "config")):
            assert tocr_config.get_config()["clip_command"] == "cmd --opt=val"


class TestTrOcrConfig:
    def test_trocr_force_cpu_yes(self, tmp_path):
        (tmp_path / "config").write_text("force_cpu=yes\n")
        with patch.object(tocr_config, "CONFIG_PATH", str(tmp_path / "config")):
            assert tocr_config.TrOcrConfig().force_cpu is True

    def test_trocr_force_cpu_true(self, tmp_path):
        (tmp_path / "config").write_text("force_cpu=true\n")
        with patch.object(tocr_config, "CONFIG_PATH", str(tmp_path / "config")):
            assert tocr_config.TrOcrConfig().force_cpu is True

    def test_trocr_force_cpu_no(self, tmp_path):
        (tmp_path / "config").write_text("force_cpu=no\n")
        with patch.object(tocr_config, "CONFIG_PATH", str(tmp_path / "config")):
            assert tocr_config.TrOcrConfig().force_cpu is False

    def test_trocr_force_cpu_default(self):
        with patch.object(tocr_config, "CONFIG_PATH", "/nonexistent"):
            assert tocr_config.TrOcrConfig().force_cpu is False

    def test_trocr_clip_args_custom(self, tmp_path):
        (tmp_path / "config").write_text("clip_command=goldendict %TEXT%\n")
        with patch.object(tocr_config, "CONFIG_PATH", str(tmp_path / "config")):
            assert tocr_config.TrOcrConfig().clip_args == ["goldendict", "%TEXT%"]

    def test_trocr_clip_args_default_none(self):
        with patch.object(tocr_config, "CONFIG_PATH", "/nonexistent"):
            assert tocr_config.TrOcrConfig().clip_args is None

    def test_trocr_screenshot_dir_valid(self, tmp_path):
        sdir = tmp_path / "screenshots"
        sdir.mkdir()
        (tmp_path / "config").write_text(f"screenshot_dir={sdir}\n")
        with patch.object(tocr_config, "CONFIG_PATH", str(tmp_path / "config")):
            assert tocr_config.TrOcrConfig().screenshot_dir == str(sdir)

    def test_trocr_screenshot_dir_nonexistent(self, tmp_path):
        (tmp_path / "config").write_text("screenshot_dir=/nonexistent\n")
        with patch.object(tocr_config, "CONFIG_PATH", str(tmp_path / "config")):
            assert tocr_config.TrOcrConfig().screenshot_dir is None

    def test_trocr_model_default(self):
        with patch.object(tocr_config, "CONFIG_PATH", "/nonexistent"):
            assert tocr_config.TrOcrConfig().model == tocr_config.DEFAULT_MODEL

    def test_trocr_model_custom(self, tmp_path):
        (tmp_path / "config").write_text("model=jzhang533/manga-ocr-base-2025\n")
        with patch.object(tocr_config, "CONFIG_PATH", str(tmp_path / "config")):
            assert tocr_config.TrOcrConfig().model == "jzhang533/manga-ocr-base-2025"

    def test_default_model_is_safetensors(self):
        assert tocr_config.DEFAULT_MODEL == "tatsumoto/manga-ocr-base"

    # ── preview config option removed ──

    def test_no_preview_attribute(self):
        """The 'preview' config option was removed."""
        with patch.object(tocr_config, "CONFIG_PATH", "/nonexistent"):
            cfg = tocr_config.TrOcrConfig()
            assert not hasattr(cfg, "preview")

    def test_preview_key_in_file_ignored(self, tmp_path):
        """Even if 'preview=yes' is in config file, no attribute is set."""
        (tmp_path / "config").write_text("preview=yes\n")
        with patch.object(tocr_config, "CONFIG_PATH", str(tmp_path / "config")):
            cfg = tocr_config.TrOcrConfig()
            assert not hasattr(cfg, "preview")


class TestPaths:
    def test_get_home(self):
        assert os.path.isdir(tocr_config._get_home())

    def test_get_home_fallback(self):
        with patch("pathlib.Path.home", side_effect=RuntimeError), \
             patch.dict(os.environ, {"HOME": "/tmp"}):
            assert tocr_config._get_home() == "/tmp"

    def test_get_home_no_home_raises(self):
        with patch("pathlib.Path.home", side_effect=RuntimeError), \
             patch.dict(os.environ, {}, clear=True), \
             pytest.raises(RuntimeError, match="Cannot determine"):
            tocr_config._get_home()

    def test_get_runtime_dir_xdg(self, tmp_path):
        rd = tmp_path / "runtime"
        rd.mkdir()
        with patch.dict(os.environ, {"XDG_RUNTIME_DIR": str(rd)}):
            result = tocr_config._get_runtime_dir()
        assert result == str(rd / "transformers_ocr")
        assert os.path.isdir(result)

    def test_get_runtime_dir_fallback(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("XDG_RUNTIME_DIR", None)
            result = tocr_config._get_runtime_dir()
        assert f"transformers_ocr_{os.getuid()}" in result
        assert os.path.isdir(result)
