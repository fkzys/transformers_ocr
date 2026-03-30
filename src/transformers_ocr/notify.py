# Copyright: Ren Tatsumoto <tatsu at autistici.org> and contributors
# Copyright: fkzys and contributors
# License: GNU GPL, version 3 or later; http://www.gnu.org/licenses/gpl.html

"""Desktop notifications."""

import subprocess


def notify_send(msg: str):
    print(msg)
    try:
        subprocess.run(
            ("notify-send", "transformers-ocr", msg),
            shell=False,
            timeout=10,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except FileNotFoundError:
        pass
    except subprocess.TimeoutExpired:
        pass
