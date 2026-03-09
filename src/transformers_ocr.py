#!/usr/bin/python3
# Copyright: Ren Tatsumoto <tatsu at autistici.org> and contributors
# License: GNU GPL, version 3 or later; http://www.gnu.org/licenses/gpl.html

import argparse
import dataclasses
import datetime
import enum
import fcntl
import json
import os
import shlex
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
from argparse import RawTextHelpFormatter
from pathlib import Path
from typing import AnyStr, IO, Iterable, Optional


# ---------------------------------------------------------------------------
# Paths and constants
# ---------------------------------------------------------------------------

def _get_home() -> str:
    """Get the user's home directory safely."""
    try:
        return str(Path.home())
    except (RuntimeError, KeyError):
        home = os.environ.get("HOME")
        if home:
            return home
        raise RuntimeError("Cannot determine home directory. Set $HOME.")


def _get_runtime_dir() -> str:
    """Return a user-private directory for PID / FIFO files."""
    runtime_dir = os.environ.get("XDG_RUNTIME_DIR")
    if runtime_dir and os.path.isdir(runtime_dir):
        subdir = os.path.join(runtime_dir, "transformers_ocr")
    else:
        subdir = os.path.join(
            tempfile.gettempdir(), f"transformers_ocr_{os.getuid()}"
        )
    os.makedirs(subdir, mode=0o700, exist_ok=True)
    return subdir


_HOME = _get_home()
_RUNTIME_DIR = _get_runtime_dir()

MANGA_OCR_PREFIX = os.path.join(_HOME, ".local", "share", "manga_ocr")
MANGA_OCR_PYENV_PATH = os.path.join(MANGA_OCR_PREFIX, "pyenv")
MANGA_OCR_PYENV_PIP_PATH = os.path.join(MANGA_OCR_PYENV_PATH, "bin", "pip")
HUGGING_FACE_CACHE_PATH = os.path.join(_HOME, ".cache", "huggingface")
CONFIG_PATH = os.path.join(
    os.environ.get("XDG_CONFIG_HOME", os.path.join(_HOME, ".config")),
    "transformers_ocr",
    "config",
)

PIPE_PATH = os.path.join(_RUNTIME_DIR, "manga_ocr.fifo")
PID_FILE = os.path.join(_RUNTIME_DIR, "manga_ocr.pid")
LOCK_FILE = os.path.join(_RUNTIME_DIR, "manga_ocr.lock")

PROGRAM = "transformers_ocr"
JOIN = "、"
CLIP_TEXT_PLACEHOLDER = "%TEXT%"
VALID_ACTIONS = frozenset({"recognize", "hold", "stop"})


# ---------------------------------------------------------------------------
# Platform detection (lazy — no module-level side effects)
# ---------------------------------------------------------------------------

def _is_xorg() -> bool:
    return "WAYLAND_DISPLAY" not in os.environ


class Platform(enum.Enum):
    GNOME = enum.auto()
    KDE = enum.auto()
    XFCE = enum.auto()
    Xorg = enum.auto()
    Wayland = enum.auto()

    @classmethod
    def current(cls) -> "Platform":
        desktop = os.environ.get("XDG_CURRENT_DESKTOP", "")
        if desktop == "GNOME":
            return cls.GNOME
        if desktop == "KDE":
            return cls.KDE
        if desktop == "XFCE":
            return cls.XFCE
        if _is_xorg():
            return cls.Xorg
        return cls.Wayland


def _get_clip_copy_args() -> tuple[str, ...]:
    if _is_xorg():
        return ("xclip", "-selection", "clipboard")
    return ("wl-copy",)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class MissingProgram(RuntimeError):
    pass


class StopRequested(Exception):
    pass


class ScreenshotCancelled(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# OcrCommand  (validated data contract for the FIFO protocol)
# ---------------------------------------------------------------------------

@dataclasses.dataclass
class OcrCommand:
    action: str
    file_path: str | None
    delete_after: bool = False

    def as_json(self) -> str:
        return json.dumps(dataclasses.asdict(self))

    def validate(self) -> "OcrCommand":
        if self.action not in VALID_ACTIONS:
            raise ValueError(f"Invalid action: {self.action!r}")
        if self.action != "stop" and not self.file_path:
            raise ValueError(
                f"file_path is required for action {self.action!r}"
            )
        if self.file_path is not None and not isinstance(self.file_path, str):
            raise TypeError(
                f"file_path must be a string, got {type(self.file_path)}"
            )
        return self


# ---------------------------------------------------------------------------
# Dependency checks
# ---------------------------------------------------------------------------

def is_installed(program: str) -> bool:
    if shutil.which(program):
        return True
    try:
        return (
            subprocess.call(
                ("pacman", "-Qq", program),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            == 0
        )
    except FileNotFoundError:
        return False


def raise_if_missing(*programs: str):
    for prog in programs:
        if not is_installed(prog):
            raise MissingProgram(
                f"{prog} must be installed for {PROGRAM} to work."
            )


# ---------------------------------------------------------------------------
# Screenshot helpers
# ---------------------------------------------------------------------------

def gnome_screenshot_select(screenshot_path: str):
    raise_if_missing("gnome-screenshot")
    subprocess.run(
        ("gnome-screenshot", "-a", "-f", screenshot_path),
        check=True,
    )


def spectacle_select(screenshot_path: str):
    raise_if_missing("spectacle")
    subprocess.run(
        ("spectacle", "-n", "-b", "-r", "-o", screenshot_path),
        check=True,
        stderr=subprocess.DEVNULL,
    )


def xfce_screenshooter_select(screenshot_path: str):
    raise_if_missing("xfce4-screenshooter")
    subprocess.run(
        ("xfce4-screenshooter", "-r", "-s", screenshot_path),
        check=True,
        stderr=subprocess.DEVNULL,
    )


def maim_select(screenshot_path: str):
    raise_if_missing("maim")
    subprocess.run(
        (
            "maim", "--select", "--hidecursor",
            "--format=png", "--quality", "1", screenshot_path,
        ),
        check=True,
        stderr=subprocess.DEVNULL,
    )


def grim_select(screenshot_path: str):
    raise_if_missing("grim", "slurp")
    try:
        geometry = (
            subprocess.check_output(["slurp"], stderr=subprocess.DEVNULL)
            .decode()
            .strip()
        )
    except subprocess.CalledProcessError as ex:
        raise ScreenshotCancelled("slurp selection cancelled") from ex
    if not geometry:
        raise ScreenshotCancelled("slurp returned empty geometry")
    subprocess.run(
        ("grim", "-g", geometry, screenshot_path),
        check=True,
    )


def take_screenshot(screenshot_path: str):
    platform = Platform.current()
    match platform:
        case Platform.GNOME:
            gnome_screenshot_select(screenshot_path)
        case Platform.KDE:
            spectacle_select(screenshot_path)
        case Platform.XFCE:
            xfce_screenshooter_select(screenshot_path)
        case Platform.Xorg:
            maim_select(screenshot_path)
        case Platform.Wayland:
            grim_select(screenshot_path)


# ---------------------------------------------------------------------------
# FIFO helpers
# ---------------------------------------------------------------------------

def is_fifo(path: AnyStr) -> bool:
    try:
        return stat.S_ISFIFO(os.stat(path).st_mode)
    except (FileNotFoundError, OSError):
        return False


def prepare_pipe():
    """Create the named pipe atomically."""
    try:
        st = os.lstat(PIPE_PATH)
        if stat.S_ISFIFO(st.st_mode):
            return
        os.remove(PIPE_PATH)
    except FileNotFoundError:
        pass
    try:
        os.mkfifo(PIPE_PATH, mode=0o600)
    except FileExistsError:
        if not is_fifo(PIPE_PATH):
            raise


def write_command_to_pipe(command: OcrCommand):
    with open(PIPE_PATH, "w") as pipe:
        pipe.write(command.as_json())


def _safe_remove(path: str):
    try:
        os.remove(path)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Process management
# ---------------------------------------------------------------------------

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
            (
                os.path.join(MANGA_OCR_PREFIX, "pyenv", "bin", "python3"),
                __file__,
                "start",
                "--foreground",
            ),
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


# ---------------------------------------------------------------------------
# OCR entry point (client side)
# ---------------------------------------------------------------------------

def run_ocr(command: str, image_path: Optional[str] = None) -> None:
    ensure_listening()
    if image_path is not None:
        write_command_to_pipe(
            OcrCommand(action=command, file_path=image_path, delete_after=False)
        )
        return

    fd, screenshot_path = tempfile.mkstemp(suffix=".png")
    os.close(fd)
    try:
        take_screenshot(screenshot_path)
    except (subprocess.CalledProcessError, ScreenshotCancelled):
        _safe_remove(screenshot_path)
        raise ScreenshotCancelled()
    except Exception:
        _safe_remove(screenshot_path)
        raise
    write_command_to_pipe(
        OcrCommand(action=command, file_path=screenshot_path, delete_after=True)
    )


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------

def notify_send(msg: str):
    print(msg)
    try:
        subprocess.run(
            ("notify-send", "manga-ocr", msg),
            shell=False,
            timeout=10,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except FileNotFoundError:
        pass
    except subprocess.TimeoutExpired:
        pass


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def is_valid_key_val_pair(line: str) -> bool:
    return "=" in line and not line.startswith("#")


def get_config() -> dict[str, str]:
    config: dict[str, str] = {}
    if os.path.isfile(CONFIG_PATH):
        with open(CONFIG_PATH, encoding="utf8") as f:
            for line in filter(is_valid_key_val_pair, f.read().splitlines()):
                key, value = line.split("=", maxsplit=1)
                config[key.strip()] = value.strip()
    return config


class TrOcrConfig:
    def __init__(self):
        self._config = get_config()
        self.force_cpu = self._should_force_cpu()
        self.clip_args = self._key_to_cmd_args("clip_command")
        self.screenshot_dir = self._get_screenshot_dir()

    def _should_force_cpu(self) -> bool:
        return self._config.get("force_cpu", "no") in ("true", "yes")

    def _key_to_cmd_args(self, key: str) -> list[str] | None:
        try:
            return shlex.split(self._config[key])
        except (KeyError, ValueError):
            return None

    def _get_screenshot_dir(self) -> str | None:
        screenshot_dir = self._config.get("screenshot_dir")
        if screenshot_dir and os.path.isdir(screenshot_dir):
            return screenshot_dir
        return None


# ---------------------------------------------------------------------------
# FIFO command stream (server side)
# ---------------------------------------------------------------------------

def iter_commands(stream: IO) -> Iterable[OcrCommand]:
    for line in stream:
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
            yield OcrCommand(**data).validate()
        except (json.JSONDecodeError, TypeError, ValueError) as ex:
            print(
                f"Warning: skipping invalid command: {ex}", file=sys.stderr
            )


# ---------------------------------------------------------------------------
# Listener (server)
# ---------------------------------------------------------------------------

class MangaOcrWrapper:
    def __init__(self):
        from manga_ocr import MangaOcr  # type: ignore

        self._config = TrOcrConfig()
        self._mocr = MangaOcr(force_cpu=self._config.force_cpu)
        self._on_hold: list[str] = []

    def init(self) -> "MangaOcrWrapper":
        prepare_pipe()
        print(f"Reading from {PIPE_PATH}")
        print(f"Custom clip args: {self._config.clip_args}")
        return self

    def _ocr(self, file_path: str) -> str:
        return (
            self._mocr(file_path)
            .replace("...", "…")
            .replace("。。。", "…")
            .replace("．．．", "…")
        )

    def _process_command(self, command: OcrCommand):
        match command:
            case OcrCommand(action="stop"):
                raise StopRequested()
            case OcrCommand(
                action=action,
                file_path=file_path,
                delete_after=delete_after,
            ) if file_path and os.path.isfile(file_path):
                try:
                    match action:
                        case "hold":
                            text = self._ocr(file_path)
                            self._on_hold.append(text)
                            notify_send(f"Holding {text}")
                        case "recognize":
                            text = JOIN.join(
                                (*self._on_hold, self._ocr(file_path))
                            )
                            self._to_clip(text)
                            self._on_hold.clear()
                            self._maybe_save_result(file_path, text)
                finally:
                    if delete_after:
                        _safe_remove(file_path)

    def _to_clip(self, text: str):
        cmd_args = list(self._config.clip_args or _get_clip_copy_args())
        try:
            idx = cmd_args.index(CLIP_TEXT_PLACEHOLDER)
            pass_text_to_stdin = False
            cmd_args[idx] = text
        except ValueError:
            pass_text_to_stdin = True

        try:
            raise_if_missing(cmd_args[0])
            p = subprocess.Popen(
                cmd_args,
                stdin=(subprocess.PIPE if pass_text_to_stdin else None),
                shell=False,
                start_new_session=True,
            )
            if pass_text_to_stdin:
                p.communicate(input=text.encode(), timeout=10)
            else:
                p.wait(timeout=10)
        except MissingProgram as ex:
            notify_send(str(ex))
            return
        except subprocess.TimeoutExpired:
            p.kill()
            p.wait()
            notify_send("Clipboard command timed out")
            return
        notify_send(f"Copied {text}")

    def _maybe_save_result(self, file_path: str, text: str):
        if self._config.screenshot_dir:
            stamp = datetime.datetime.now().strftime("trocr_%Y%m%d_%H%M%S")
            text_out = os.path.join(
                self._config.screenshot_dir, f"{stamp}.gt.txt"
            )
            png_out = os.path.join(
                self._config.screenshot_dir, f"{stamp}.png"
            )
            shutil.copy(file_path, png_out)
            with open(text_out, "w", encoding="utf8") as of:
                of.write(text)

    def loop(self):
        try:
            while True:
                with open(PIPE_PATH) as fifo:
                    for command in iter_commands(fifo):
                        self._process_command(command)
        except StopRequested:
            notify_send("Stopped listening.")


# ---------------------------------------------------------------------------
# Top-level actions
# ---------------------------------------------------------------------------

def run_listener():
    MangaOcrWrapper().init().loop()


def start_listening(args):
    if args.foreground:
        run_listener()
    else:
        ensure_listening()


def restart_listener():
    stop_listening()
    ensure_listening()


def status_str() -> str:
    return "Running" if get_pid() else "Stopped"


def print_status():
    print(f"{status_str()}, {Platform.current().name}.")


def download_manga_ocr():
    print("Downloading manga-ocr...")
    os.makedirs(MANGA_OCR_PREFIX, exist_ok=True)

    # Always recreate venv to avoid stale symlinks after Python upgrades
    if os.path.exists(MANGA_OCR_PYENV_PATH):
        print("Recreating virtual environment...")
        shutil.rmtree(MANGA_OCR_PYENV_PATH)

    subprocess.run(
        ("python3", "-m", "venv", "--symlinks", MANGA_OCR_PYENV_PATH),
        check=True,
    )

    # Verify the venv works before proceeding
    venv_python = os.path.join(MANGA_OCR_PYENV_PATH, "bin", "python3")
    try:
        subprocess.run(
            (venv_python, "-c", "import ssl, socket; "
             "socket.getaddrinfo('pypi.org', 443)"),
            check=True,
            timeout=15,
            capture_output=True,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as ex:
        print(
            "Error: virtual environment cannot reach PyPI.\n"
            "Check your network connection and SSL certificates.",
            file=sys.stderr,
        )
        raise SystemExit(1) from ex

    subprocess.run(
        (MANGA_OCR_PYENV_PIP_PATH, "install", "--upgrade", "pip"),
        check=True,
    )
    subprocess.run(
        (MANGA_OCR_PYENV_PIP_PATH, "install", "--upgrade", "manga-ocr"),
        check=True,
    )
    print("Downloaded manga-ocr.")


def prog_name() -> str:
    return os.path.basename(sys.argv[0])


def purge_manga_ocr_data():
    shutil.rmtree(MANGA_OCR_PREFIX, ignore_errors=True)
    shutil.rmtree(HUGGING_FACE_CACHE_PATH, ignore_errors=True)
    print("Purged all downloaded manga-ocr data.")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def create_args_parser() -> argparse.ArgumentParser:
    platform = Platform.current()
    parser = argparse.ArgumentParser(
        description="An OCR tool that uses Transformers.",
        formatter_class=RawTextHelpFormatter,
    )
    parser.epilog = (
        f"\nPlatform: {platform.name}\n"
        f"You need to run '{prog_name()} download' once after installation.\n"
        f"{prog_name()} home page: "
        "https://github.com/Ajatt-Tools/transformers_ocr"
    )

    subparsers = parser.add_subparsers(title="commands")

    recognize_parser = subparsers.add_parser(
        "recognize", help="OCR a part of the screen.", aliases=["ocr"],
    )
    recognize_parser.add_argument(
        "--image-path", help="Path to image to parse.",
        metavar="<path>", default=None,
    )
    recognize_parser.set_defaults(
        func=lambda args: run_ocr("recognize", image_path=args.image_path),
    )

    hold_parser = subparsers.add_parser(
        "hold", help="OCR and hold a part of the screen.",
    )
    hold_parser.add_argument(
        "--image-path", help="Path to image to parse.",
        metavar="<path>", default=None,
    )
    hold_parser.set_defaults(
        func=lambda args: run_ocr("hold", image_path=args.image_path),
    )

    download_parser = subparsers.add_parser(
        "download", help="Download OCR files.",
    )
    download_parser.set_defaults(func=lambda _args: download_manga_ocr())

    start_parser = subparsers.add_parser(
        "start", help="Start listening.", aliases=["listen"],
    )
    start_parser.add_argument("--foreground", action="store_true")
    start_parser.set_defaults(func=start_listening)

    stop_parser = subparsers.add_parser("stop", help="Stop listening.")
    stop_parser.set_defaults(func=lambda _args: stop_listening())

    status_parser = subparsers.add_parser(
        "status", help="Print listening status.",
    )
    status_parser.set_defaults(func=lambda _args: print_status())

    restart_parser = subparsers.add_parser(
        "restart", help="Stop listening and start listening.",
    )
    restart_parser.set_defaults(func=lambda _args: restart_listener())

    nuke_parser = subparsers.add_parser(
        "purge", help="Purge all manga-ocr data.", aliases=["nuke"],
    )
    nuke_parser.set_defaults(func=lambda _args: purge_manga_ocr_data())

    return parser


def main():
    parser = create_args_parser()
    if len(sys.argv) < 2:
        parser.print_help()
        return
    args = parser.parse_args()
    try:
        args.func(args)
    except MissingProgram as ex:
        notify_send(str(ex))
    except ScreenshotCancelled:
        notify_send("Screenshot cancelled.")
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        sys.exit(130)
    except subprocess.CalledProcessError as ex:
        print(f"Command failed: {ex}", file=sys.stderr)
        sys.exit(ex.returncode)


if __name__ == "__main__":
    main()
