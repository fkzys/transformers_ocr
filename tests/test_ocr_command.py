"""Tests for OcrCommand."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from transformers_ocr.ocr_command import OcrCommand


class TestOcrCommand:
    def test_as_json_recognize(self):
        cmd = OcrCommand(action="recognize", file_path="/tmp/img.png", delete_after=True)
        data = json.loads(cmd.as_json())
        assert data == {"action": "recognize", "file_path": "/tmp/img.png", "delete_after": True}

    def test_as_json_stop(self):
        data = json.loads(OcrCommand(action="stop", file_path=None).as_json())
        assert data["action"] == "stop"
        assert data["file_path"] is None

    def test_validate_recognize(self):
        cmd = OcrCommand(action="recognize", file_path="/img.png").validate()
        assert cmd.action == "recognize"

    def test_validate_hold(self):
        cmd = OcrCommand(action="hold", file_path="/img.png").validate()
        assert cmd.action == "hold"

    def test_validate_stop_none_path(self):
        cmd = OcrCommand(action="stop", file_path=None).validate()
        assert cmd.action == "stop"

    def test_validate_invalid_action(self):
        with pytest.raises(ValueError, match="Invalid action"):
            OcrCommand(action="destroy", file_path="/x").validate()

    def test_validate_missing_file_path(self):
        with pytest.raises(ValueError, match="file_path is required"):
            OcrCommand(action="recognize", file_path=None).validate()

    def test_validate_non_string_file_path(self):
        with pytest.raises(TypeError, match="file_path must be a string"):
            OcrCommand(action="recognize", file_path=123).validate()

    def test_roundtrip(self):
        orig = OcrCommand(action="hold", file_path="/img.png", delete_after=True)
        assert OcrCommand(**json.loads(orig.as_json())) == orig

    def test_default_delete_after(self):
        assert OcrCommand(action="recognize", file_path="/x").delete_after is False
