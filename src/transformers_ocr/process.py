# Copyright: Ren Tatsumoto <tatsu at autistici.org> and contributors
# Copyright: fkzys and contributors
# License: GNU GPL, version 3 or later; http://www.gnu.org/licenses/gpl.html

"""Process management: start / stop / status of the listener daemon."""

import fcntl
import os
import signal
import subprocess
import sys
import time
from typing import IO

from transformers_ocr import PROGRAM
from transformers_ocr.config import (
    LOCK_FILE,
    MANGA_OCR_PREFIX,
    PID_FILE,
)
from transformers_ocr.fifo import prepare_pipe, write_command_to_pipe
from transformers_ocr.ocr_command import OcrCommand


def is_running(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def get_pid() -> int | None:
    try:
        with open(PID_FILE) as pid_file:
            pid = int(pid_file.read().strip())
    except (ValueError, FileNotFoundError, OSError):
        return None
    return pid if is_running(pid) else None


def _acquire_lock() -> IO | None:
    try:
        lock_fd = open(LOCK_FILE, "w")
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return lock_fd
    except (OSError, IOError):
        return None


def _release_lock(lock_fd: IO | None):
    if lock_fd is not None:
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            lock_fd.close()
        except OSError:
            pass


def ensure_listening():
    if not os.path.exists(MANGA_OCR_PREFIX):
        print("manga-ocr is not downloaded.")
        sys.exit(1)

    lock_fd = _acquire_lock()
    if lock_fd is None:
        print("Already running.")
        return
    try:
        if get_pid() is not None:
            print("Already running.")
            return

        prepare_pipe()
        p = subprocess.Popen(
            (PROGRAM, "start", "--foreground"),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        with open(PID_FILE, "w") as pid_file:
            pid_file.write(str(p.pid))
        print("Started manga_ocr listener.")
    finally:
        _release_lock(lock_fd)


def kill_after(pid: int, timeout_s: float, step_s: float = 0.1):
    """Wait for graceful exit, then SIGKILL only if still alive."""
    for _step in range(int(timeout_s / step_s)):
        if not is_running(pid):
            print(" Stopped.")
            return
        time.sleep(step_s)
        print(".", end="", flush=True)
    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        print(" Stopped.")
    else:
        print(" Killed.")


def stop_listening():
    pid = get_pid()
    if pid is None:
        print("Already stopped.")
        return
    try:
        write_command_to_pipe(OcrCommand(action="stop", file_path=None))
    except (FileNotFoundError, OSError):
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            print("Already stopped.")
            return
    kill_after(pid, timeout_s=3)
