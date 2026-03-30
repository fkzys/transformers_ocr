# Copyright: Ren Tatsumoto <tatsu at autistici.org> and contributors
# Copyright: fkzys and contributors
# License: GNU GPL, version 3 or later; http://www.gnu.org/licenses/gpl.html

"""Named-pipe (FIFO) helpers."""

import json
import os
import stat
import sys
from typing import IO, Iterable

from transformers_ocr.config import PIPE_PATH
from transformers_ocr.ocr_command import OcrCommand


def is_fifo(path: str) -> bool:
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
