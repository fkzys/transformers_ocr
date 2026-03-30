# Copyright: Ren Tatsumoto <tatsu at autistici.org> and contributors
# Copyright: fkzys and contributors
# License: GNU GPL, version 3 or later; http://www.gnu.org/licenses/gpl.html

"""Command-line interface."""

import argparse
import os
import subprocess
import sys
import tempfile
from argparse import RawTextHelpFormatter
from typing import Optional

from transformers_ocr import PROGRAM
from transformers_ocr.download import download_manga_ocr, purge_manga_ocr_data
from transformers_ocr.exceptions import MissingProgram, ScreenshotCancelled
from transformers_ocr.fifo import write_command_to_pipe
from transformers_ocr.notify import notify_send
from transformers_ocr.ocr_command import OcrCommand
from transformers_ocr.platform import Platform, take_screenshot
from transformers_ocr.process import (
    ensure_listening,
    get_pid,
    stop_listening,
)
from transformers_ocr.wrapper import MangaOcrWrapper


def _safe_remove(path: str):
    try:
        os.remove(path)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Client-side OCR entry point
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


def _prog_name() -> str:
    return os.path.basename(sys.argv[0])


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def create_args_parser() -> argparse.ArgumentParser:
    platform = Platform.current()
    parser = argparse.ArgumentParser(
        description="An OCR tool that uses Transformers.",
        formatter_class=RawTextHelpFormatter,
    )
    parser.epilog = (
        f"\nPlatform: {platform.name}\n"
        f"You need to run '{_prog_name()} download' once after installation.\n"
        f"{_prog_name()} home page: "
        "https://gitlab.com/fkzys/transformers-ocr"
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
