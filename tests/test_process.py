"""Tests for transformers_ocr.process"""

import os
import signal
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from transformers_ocr import config as tocr_config
from transformers_ocr import process as tocr_process


class TestProcessManagement:
    def test_is_running_self(self):
        assert tocr_process.is_running(os.getpid()) is True

    def test_is_running_nonexistent(self):
        assert tocr_process.is_running(99999999) is False

    def test_is_running_zero(self):
        assert tocr_process.is_running(0) is False

    def test_is_running_negative(self):
        assert tocr_process.is_running(-1) is False

    def test_is_running_permission_error(self):
        with patch("os.kill", side_effect=PermissionError):
            assert tocr_process.is_running(1) is True

    def test_get_pid_valid(self, tmp_path):
        (tmp_path / "pid").write_text(str(os.getpid()))
        with patch.object(tocr_config, "PID_FILE", str(tmp_path / "pid")), \
             patch.object(tocr_process, "PID_FILE", str(tmp_path / "pid")):
            assert tocr_process.get_pid() == os.getpid()

    def test_get_pid_missing_file(self):
        with patch.object(tocr_process, "PID_FILE", "/nonexistent"):
            assert tocr_process.get_pid() is None

    def test_get_pid_dead_process(self, tmp_path):
        (tmp_path / "pid").write_text("99999999")
        with patch.object(tocr_process, "PID_FILE", str(tmp_path / "pid")):
            assert tocr_process.get_pid() is None

    def test_get_pid_garbage(self, tmp_path):
        (tmp_path / "pid").write_text("not_a_number")
        with patch.object(tocr_process, "PID_FILE", str(tmp_path / "pid")):
            assert tocr_process.get_pid() is None

    def test_get_pid_empty(self, tmp_path):
        (tmp_path / "pid").write_text("")
        with patch.object(tocr_process, "PID_FILE", str(tmp_path / "pid")):
            assert tocr_process.get_pid() is None

    def test_kill_after_already_dead(self):
        with patch.object(tocr_process, "is_running", return_value=False):
            tocr_process.kill_after(99999, timeout_s=1)

    def test_kill_after_sends_sigkill(self):
        with patch.object(tocr_process, "is_running", return_value=True), \
             patch("os.kill") as mock_kill, \
             patch("time.sleep"):
            tocr_process.kill_after(12345, timeout_s=0.1, step_s=0.1)
            mock_kill.assert_called_with(12345, signal.SIGKILL)

    def test_kill_after_exits_during_wait(self):
        calls = [0]

        def alive_then_dead(_pid):
            calls[0] += 1
            return calls[0] <= 2

        with patch.object(tocr_process, "is_running", side_effect=alive_then_dead), \
             patch("time.sleep"), \
             patch("os.kill") as mock_kill:
            tocr_process.kill_after(12345, timeout_s=1, step_s=0.1)
            mock_kill.assert_not_called()


class TestLock:
    def test_acquire_and_release(self, tmp_path):
        with patch.object(tocr_process, "LOCK_FILE", str(tmp_path / "test.lock")):
            fd = tocr_process._acquire_lock()
            assert fd is not None
            tocr_process._release_lock(fd)

    def test_double_acquire_fails(self, tmp_path):
        with patch.object(tocr_process, "LOCK_FILE", str(tmp_path / "test.lock")):
            fd1 = tocr_process._acquire_lock()
            fd2 = tocr_process._acquire_lock()
            assert fd1 is not None
            assert fd2 is None
            tocr_process._release_lock(fd1)

    def test_release_none(self):
        tocr_process._release_lock(None)


class TestStopListening:
    def test_already_stopped(self, capsys):
        with patch.object(tocr_process, "get_pid", return_value=None):
            tocr_process.stop_listening()
        assert "Already stopped" in capsys.readouterr().out

    def test_sends_stop_via_pipe(self):
        with patch.object(tocr_process, "get_pid", return_value=12345), \
             patch.object(tocr_process, "write_command_to_pipe") as mock_write, \
             patch.object(tocr_process, "kill_after") as mock_kill:
            tocr_process.stop_listening()
            assert mock_write.call_args[0][0].action == "stop"
            mock_kill.assert_called_once_with(12345, timeout_s=3)

    def test_pipe_error_sends_sigterm(self):
        with patch.object(tocr_process, "get_pid", return_value=12345), \
             patch.object(tocr_process, "write_command_to_pipe", side_effect=FileNotFoundError), \
             patch("os.kill") as mock_sig, \
             patch.object(tocr_process, "kill_after"):
            tocr_process.stop_listening()
            mock_sig.assert_called_once_with(12345, signal.SIGTERM)


class TestEnsureListening:
    def test_not_downloaded(self):
        with patch.object(tocr_config, "CONFIG_PATH", "/nonexistent"), \
             patch.object(tocr_config, "MANGA_OCR_PREFIX", "/nonexistent"), \
             patch.object(tocr_process, "MANGA_OCR_PREFIX", "/nonexistent"), \
             pytest.raises(SystemExit):
            tocr_process.ensure_listening()

    def test_lock_not_acquired(self, tmp_path, capsys):
        with patch.object(tocr_process, "MANGA_OCR_PREFIX", str(tmp_path)), \
             patch.object(tocr_process, "_acquire_lock", return_value=None):
            tocr_process.ensure_listening()
        assert "Already running" in capsys.readouterr().out

    def test_pid_exists(self, tmp_path, capsys):
        lock = MagicMock()
        with patch.object(tocr_process, "MANGA_OCR_PREFIX", str(tmp_path)), \
             patch.object(tocr_process, "_acquire_lock", return_value=lock), \
             patch.object(tocr_process, "get_pid", return_value=9999), \
             patch.object(tocr_process, "_release_lock") as mock_rel:
            tocr_process.ensure_listening()
        assert "Already running" in capsys.readouterr().out
        mock_rel.assert_called_once_with(lock)

    def test_starts_listener(self, tmp_path, capsys):
        pid_file = tmp_path / "pid"
        lock = MagicMock()
        proc = MagicMock(pid=42)
        with patch.object(tocr_process, "MANGA_OCR_PREFIX", str(tmp_path)), \
             patch.object(tocr_process, "_acquire_lock", return_value=lock), \
             patch.object(tocr_process, "get_pid", return_value=None), \
             patch.object(tocr_process, "prepare_pipe"), \
             patch.object(tocr_process, "PID_FILE", str(pid_file)), \
             patch("subprocess.Popen", return_value=proc), \
             patch.object(tocr_process, "_release_lock") as mock_rel:
            tocr_process.ensure_listening()
        assert pid_file.read_text() == "42"
        assert "Started" in capsys.readouterr().out
        mock_rel.assert_called_once_with(lock)
