# Copyright: Ren Tatsumoto <tatsu at autistici.org> and contributors
# Copyright: fkzys and contributors
# License: GNU GPL, version 3 or later; http://www.gnu.org/licenses/gpl.html

"""Platform detection and clipboard helpers."""

import enum
import os
import shutil

from transformers_ocr.exceptions import MissingProgram


# ---------------------------------------------------------------------------
# Platform detection
# ---------------------------------------------------------------------------

def _is_xorg() -> bool:
    return "WAYLAND_DISPLAY" not in os.environ


class Platform(enum.Enum):
    Xorg = enum.auto()
    Wayland = enum.auto()

    @classmethod
    def current(cls) -> "Platform":
        if _is_xorg():
            return cls.Xorg
        return cls.Wayland


# ---------------------------------------------------------------------------
# Clipboard
# ---------------------------------------------------------------------------

def get_clip_copy_args() -> tuple[str, ...]:
    if _is_xorg():
        return ("xclip", "-selection", "clipboard")
    return ("wl-copy",)


def raise_if_missing(program: str):
    from transformers_ocr import PROGRAM
    if not shutil.which(program):
        raise MissingProgram(
            f"{program} must be installed for {PROGRAM} to work."
        )


# ---------------------------------------------------------------------------
# Screenshot
# ---------------------------------------------------------------------------

def take_fullscreen_screenshot(screenshot_path: str):
    """Capture the entire screen without any selection UI."""
    from transformers_ocr.screengrab import grab_fullscreen
    if not grab_fullscreen(screenshot_path):
        raise RuntimeError(
            "Screen capture failed. "
            "On X11: ensure libX11 is available. "
            "On Wayland: ensure xdg-desktop-portal is running."
        )
