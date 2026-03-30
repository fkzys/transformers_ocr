"""Tests for the transformers_ocr package."""

import io
import json
import os
import signal
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from transformers_ocr import config as tocr_config
from transformers_ocr import cli as tocr_cli
from transformers_ocr import fifo as tocr_fifo
from transformers_ocr import notify as tocr_notify
from transformers_ocr import platform as tocr_platform
from transformers_ocr import process as tocr_process
from transformers_ocr import download as tocr_download
from transformers_ocr import wrapper as tocr_wrapper
from transformers_ocr.exceptions import (
    MissingProgram,
    ScreenshotCancelled,
    StopRequested,
)
from transformers_ocr.ocr_command import OcrCommand


# ═══════════════════════════════════════════════════
# OcrCommand
# ═══════════════════════════════════════════════════


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


# ═══════════════════════════════════════════════════
# Platform detection
# ═══════════════════════════════════════════════════


class TestPlatform:
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


# ═══════════════════════════════════════════════════
# Config
# ═══════════════════════════════════════════════════


class TestConfig:
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


# ═══════════════════════════════════════════════════
# iter_commands
# ═══════════════════════════════════════════════════


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


# ═══════════════════════════════════════════════════
# Process management
# ═══════════════════════════════════════════════════


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


# ═══════════════════════════════════════════════════
# Lock
# ═══════════════════════════════════════════════════


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


# ═══════════════════════════════════════════════════
# FIFO
# ═══════════════════════════════════════════════════


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


# ═══════════════════════════════════════════════════
# Dependency checks
# ═══════════════════════════════════════════════════


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


# ═══════════════════════════════════════════════════
# Paths
# ═══════════════════════════════════════════════════


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


# ═══════════════════════════════════════════════════
# Screenshot dispatch
# ═══════════════════════════════════════════════════


class TestScreenshot:
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
# Notifications
# ═══════════════════════════════════════════════════


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


# ═══════════════════════════════════════════════════
# Status
# ═══════════════════════════════════════════════════


class TestStatus:
    def test_running(self):
        with patch.object(tocr_process, "get_pid", return_value=1234), \
             patch.object(tocr_cli, "get_pid", return_value=1234):
            assert tocr_cli.status_str() == "Running"

    def test_stopped(self):
        with patch.object(tocr_process, "get_pid", return_value=None), \
             patch.object(tocr_cli, "get_pid", return_value=None):
            assert tocr_cli.status_str() == "Stopped"

    def test_print_status(self, capsys):
        with patch.object(tocr_cli, "get_pid", return_value=None), \
             patch.object(tocr_config, "CONFIG_PATH", "/nonexistent"), \
             patch.dict(os.environ, {"XDG_CURRENT_DESKTOP": "", "WAYLAND_DISPLAY": "w-0"}):
            tocr_cli.print_status()
        out = capsys.readouterr().out
        assert "Stopped" in out
        assert "Wayland" in out


# ═══════════════════════════════════════════════════
# run_ocr
# ═══════════════════════════════════════════════════


class TestRunOcr:
    def test_with_image_path(self):
        with patch.object(tocr_cli, "ensure_listening"), \
             patch.object(tocr_cli, "write_command_to_pipe") as mock_write:
            tocr_cli.run_ocr("recognize", image_path="/img.png")
            cmd = mock_write.call_args[0][0]
            assert cmd.action == "recognize"
            assert cmd.file_path == "/img.png"
            assert cmd.delete_after is False

    def test_with_screenshot(self):
        with patch.object(tocr_cli, "ensure_listening"), \
             patch("tempfile.mkstemp", return_value=(99, "/tmp/shot.png")), \
             patch("os.close"), \
             patch.object(tocr_cli, "take_screenshot"), \
             patch.object(tocr_cli, "write_command_to_pipe") as mock_write:
            tocr_cli.run_ocr("recognize")
            cmd = mock_write.call_args[0][0]
            assert cmd.delete_after is True
            assert cmd.file_path == "/tmp/shot.png"

    def test_screenshot_cancelled_cleanup(self):
        with patch.object(tocr_cli, "ensure_listening"), \
             patch("tempfile.mkstemp", return_value=(99, "/tmp/s.png")), \
             patch("os.close"), \
             patch.object(tocr_cli, "take_screenshot", side_effect=ScreenshotCancelled()), \
             patch.object(tocr_cli, "_safe_remove") as mock_rm, \
             pytest.raises(ScreenshotCancelled):
            tocr_cli.run_ocr("recognize")
        mock_rm.assert_called_with("/tmp/s.png")

    def test_unexpected_error_cleanup(self):
        with patch.object(tocr_cli, "ensure_listening"), \
             patch("tempfile.mkstemp", return_value=(99, "/tmp/s.png")), \
             patch("os.close"), \
             patch.object(tocr_cli, "take_screenshot", side_effect=RuntimeError("boom")), \
             patch.object(tocr_cli, "_safe_remove") as mock_rm, \
             pytest.raises(RuntimeError):
            tocr_cli.run_ocr("recognize")
        mock_rm.assert_called_with("/tmp/s.png")


# ═══════════════════════════════════════════════════
# MangaOcrWrapper
# ═══════════════════════════════════════════════════


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
        w._maybe_save_result("/fake.png", "text")  # should not raise

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


# ═══════════════════════════════════════════════════
# stop_listening / ensure_listening
# ═══════════════════════════════════════════════════


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


# ═══════════════════════════════════════════════════
# Purge
# ═══════════════════════════════════════════════════


class TestPurge:
    @patch("shutil.rmtree")
    def test_purge(self, mock_rmtree, capsys):
        tocr_download.purge_manga_ocr_data()
        assert mock_rmtree.call_count == 2
        paths = [c[0][0] for c in mock_rmtree.call_args_list]
        assert tocr_config.MANGA_OCR_PREFIX in paths
        assert tocr_config.HUGGING_FACE_CACHE_PATH in paths
        assert "Purged" in capsys.readouterr().out


# ═══════════════════════════════════════════════════
# CLI / main
# ═══════════════════════════════════════════════════


class TestCli:
    def test_parser_recognize(self):
        args = tocr_cli.create_args_parser().parse_args(["recognize"])
        assert hasattr(args, "func")
        assert args.image_path is None

    def test_parser_recognize_image(self):
        args = tocr_cli.create_args_parser().parse_args(["recognize", "--image-path", "/img.png"])
        assert args.image_path == "/img.png"

    def test_parser_hold(self):
        assert hasattr(tocr_cli.create_args_parser().parse_args(["hold"]), "func")

    def test_parser_stop(self):
        assert hasattr(tocr_cli.create_args_parser().parse_args(["stop"]), "func")

    def test_parser_status(self):
        assert hasattr(tocr_cli.create_args_parser().parse_args(["status"]), "func")

    def test_parser_download(self):
        assert hasattr(tocr_cli.create_args_parser().parse_args(["download"]), "func")

    def test_parser_purge(self):
        assert hasattr(tocr_cli.create_args_parser().parse_args(["purge"]), "func")

    def test_parser_start_foreground(self):
        args = tocr_cli.create_args_parser().parse_args(["start", "--foreground"])
        assert args.foreground is True

    def test_parser_start_default(self):
        args = tocr_cli.create_args_parser().parse_args(["start"])
        assert args.foreground is False

    def test_parser_alias_ocr(self):
        assert hasattr(tocr_cli.create_args_parser().parse_args(["ocr"]), "func")

    def test_parser_alias_nuke(self):
        assert hasattr(tocr_cli.create_args_parser().parse_args(["nuke"]), "func")

    def test_parser_alias_listen(self):
        assert hasattr(tocr_cli.create_args_parser().parse_args(["listen"]), "func")

    def test_main_no_args(self, capsys):
        with patch("sys.argv", ["trocr"]):
            tocr_cli.main()
        out = capsys.readouterr().out
        assert "commands" in out.lower() or "ocr" in out.lower()

    def test_main_missing_program(self):
        with patch("sys.argv", ["trocr", "recognize"]), \
             patch.object(tocr_cli, "run_ocr", side_effect=MissingProgram("grim")), \
             patch.object(tocr_cli, "notify_send") as mock:
            tocr_cli.main()
            assert "grim" in mock.call_args[0][0]

    def test_main_screenshot_cancelled(self):
        with patch("sys.argv", ["trocr", "recognize"]), \
             patch.object(tocr_cli, "run_ocr", side_effect=ScreenshotCancelled()), \
             patch.object(tocr_cli, "notify_send") as mock:
            tocr_cli.main()
            assert "cancelled" in mock.call_args[0][0].lower()

    def test_main_keyboard_interrupt(self):
        with patch("sys.argv", ["trocr", "recognize"]), \
             patch.object(tocr_cli, "run_ocr", side_effect=KeyboardInterrupt), \
             pytest.raises(SystemExit, match="130"):
            tocr_cli.main()

    def test_main_subprocess_error(self):
        with patch("sys.argv", ["trocr", "recognize"]), \
             patch.object(tocr_cli, "run_ocr", side_effect=subprocess.CalledProcessError(2, "cmd")):
            with pytest.raises(SystemExit) as exc:
                tocr_cli.main()
            assert exc.value.code == 2
