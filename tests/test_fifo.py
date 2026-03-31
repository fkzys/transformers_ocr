"""Tests for transformers_ocr.fifo"""

import io
import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from transformers_ocr import config as tocr_config
from transformers_ocr import fifo as tocr_fifo
from transformers_ocr import wrapper as tocr_wrapper
from transformers_ocr.ocr_command import OcrCommand


class TestFifo:
    def test_is_fifo_true(self, tmp_path):
        fifo = tmp_path / "test.fifo"
        os.mkfifo(str(fifo))
        assert tocr_fifo.is_fifo(str(fifo)) is True

    def test_is_fifo_regular_file(self, tmp_path):
        f = tmp_path / "regular"
        f.write_text("hello")
        assert tocr_fifo.is_fifo(str(f)) is False

    def test_is_fifo_missing(self):
        assert tocr_fifo.is_fifo("/nonexistent") is False

    def test_prepare_pipe_creates(self, tmp_path):
        with patch.object(tocr_config, "PIPE_PATH", str(tmp_path / "new.fifo")), \
             patch.object(tocr_fifo, "PIPE_PATH", str(tmp_path / "new.fifo")):
            tocr_fifo.prepare_pipe()
        assert tocr_fifo.is_fifo(str(tmp_path / "new.fifo"))

    def test_prepare_pipe_existing_fifo(self, tmp_path):
        fifo = tmp_path / "existing.fifo"
        os.mkfifo(str(fifo))
        with patch.object(tocr_fifo, "PIPE_PATH", str(fifo)):
            tocr_fifo.prepare_pipe()
        assert tocr_fifo.is_fifo(str(fifo))

    def test_prepare_pipe_replaces_regular_file(self, tmp_path):
        f = tmp_path / "notfifo"
        f.write_text("regular file")
        with patch.object(tocr_fifo, "PIPE_PATH", str(f)):
            tocr_fifo.prepare_pipe()
        assert tocr_fifo.is_fifo(str(f))

    def test_safe_remove(self, tmp_path):
        f = tmp_path / "removeme"
        f.write_text("bye")
        tocr_wrapper._safe_remove(str(f))
        assert not f.exists()

    def test_safe_remove_missing(self):
        tocr_wrapper._safe_remove("/nonexistent")


class TestIterCommands:
    def test_valid_commands(self):
        lines = "\n".join([
            OcrCommand(action="recognize", file_path="/a.png").as_json(),
            OcrCommand(action="hold", file_path="/b.png").as_json(),
        ]) + "\n"
        cmds = list(tocr_fifo.iter_commands(io.StringIO(lines)))
        assert [c.action for c in cmds] == ["recognize", "hold"]

    def test_stop_command(self):
        line = OcrCommand(action="stop", file_path=None).as_json() + "\n"
        cmds = list(tocr_fifo.iter_commands(io.StringIO(line)))
        assert len(cmds) == 1 and cmds[0].action == "stop"

    def test_empty_lines_skipped(self):
        line = OcrCommand(action="stop", file_path=None).as_json()
        cmds = list(tocr_fifo.iter_commands(io.StringIO(f"\n\n{line}\n\n")))
        assert len(cmds) == 1

    def test_invalid_json_skipped(self, capsys):
        cmds = list(tocr_fifo.iter_commands(io.StringIO("not json\n")))
        assert len(cmds) == 0
        assert "skipping" in capsys.readouterr().err.lower()

    def test_invalid_action_skipped(self, capsys):
        line = json.dumps({"action": "bad", "file_path": "/x"}) + "\n"
        cmds = list(tocr_fifo.iter_commands(io.StringIO(line)))
        assert len(cmds) == 0

    def test_missing_required_field_skipped(self, capsys):
        line = json.dumps({"action": "recognize"}) + "\n"
        cmds = list(tocr_fifo.iter_commands(io.StringIO(line)))
        assert len(cmds) == 0

    def test_extra_fields_skipped(self, capsys):
        line = json.dumps({"action": "stop", "file_path": None, "extra": "x"}) + "\n"
        cmds = list(tocr_fifo.iter_commands(io.StringIO(line)))
        assert len(cmds) == 0
