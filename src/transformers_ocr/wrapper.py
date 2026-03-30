# Copyright: Ren Tatsumoto <tatsu at autistici.org> and contributors
# Copyright: fkzys and contributors
# License: GNU GPL, version 3 or later; http://www.gnu.org/licenses/gpl.html

"""Server-side OCR listener that reads commands from the FIFO."""

import datetime
import os
import shutil
import subprocess

from transformers_ocr.config import (
    CLIP_TEXT_PLACEHOLDER,
    JOIN,
    PIPE_PATH,
    TrOcrConfig,
)
from transformers_ocr.exceptions import MissingProgram, StopRequested
from transformers_ocr.fifo import iter_commands, prepare_pipe
from transformers_ocr.notify import notify_send
from transformers_ocr.ocr_command import OcrCommand
from transformers_ocr.platform import get_clip_copy_args, raise_if_missing


def _safe_remove(path: str):
    try:
        os.remove(path)
    except OSError:
        pass


class MangaOcrWrapper:
    def __init__(self):
        self._config = TrOcrConfig()
        self._mocr = self._load_model()
        self._on_hold: list[str] = []

    def _load_model(self):
        """Load the OCR model specified in the config.

        Uses pretrained_model_name_or_path to select which HuggingFace
        model to load. This allows switching between different manga-ocr
        compatible models without changing anything else.
        """
        from manga_ocr import MangaOcr  # type: ignore

        print(f"Loading model: {self._config.model}")
        return MangaOcr(
            pretrained_model_name_or_path=self._config.model,
            force_cpu=self._config.force_cpu,
        )

    def init(self) -> "MangaOcrWrapper":
        prepare_pipe()
        print(f"Reading from {PIPE_PATH}")
        print(f"Model: {self._config.model}")
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
        cmd_args = list(self._config.clip_args or get_clip_copy_args())
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
