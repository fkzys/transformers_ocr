"""Tests for transformers_ocr.notify"""

import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from transformers_ocr import notify as tocr_notify


class TestNotify:
    @patch("subprocess.run")
    def test_calls_notify_send(self, mock_run, capsys):
        tocr_notify.notify_send("test msg")
        assert "notify-send" in mock_run.call_args[0][0]
        assert "test msg" in capsys.readouterr().out

    @patch("subprocess.run", side_effect=FileNotFoundError)
    def test_missing_binary(self, _mock):
        tocr_notify.notify_send("test")

    @patch("subprocess.run", side_effect=subprocess.TimeoutExpired("x", 10))
    def test_timeout(self, _mock):
        tocr_notify.notify_send("test")
