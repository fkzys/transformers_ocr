# Copyright: Ren Tatsumoto <tatsu at autistici.org> and contributors
# Copyright: fkzys and contributors
# License: GNU GPL, version 3 or later; http://www.gnu.org/licenses/gpl.html

"""Platform detection, screenshot and clipboard helpers."""

import enum
import os
import shutil
import subprocess

from transformers_ocr.exceptions import MissingProgram, ScreenshotCancelled


# ---------------------------------------------------------------------------
# Platform detection
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
    from transformers_ocr import PROGRAM
    for prog in programs:
        if not is_installed(prog):
            raise MissingProgram(
                f"{prog} must be installed for {PROGRAM} to work."
            )


def get_clip_copy_args() -> tuple[str, ...]:
    if _is_xorg():
        return ("xclip", "-selection", "clipboard")
    return ("wl-copy",)


# ---------------------------------------------------------------------------
# Screenshot helpers
# ---------------------------------------------------------------------------

def _gnome_screenshot_select(screenshot_path: str):
    raise_if_missing("gnome-screenshot")
    subprocess.run(("gnome-screenshot", "-a", "-f", screenshot_path), check=True)


def _spectacle_select(screenshot_path: str):
    raise_if_missing("spectacle")
    subprocess.run(
        ("spectacle", "-n", "-b", "-r", "-o", screenshot_path),
        check=True,
        stderr=subprocess.DEVNULL,
    )


def _xfce_screenshooter_select(screenshot_path: str):
    raise_if_missing("xfce4-screenshooter")
    subprocess.run(
        ("xfce4-screenshooter", "-r", "-s", screenshot_path),
        check=True,
        stderr=subprocess.DEVNULL,
    )


def _maim_select(screenshot_path: str):
    raise_if_missing("maim")
    subprocess.run(
        (
            "maim", "--select", "--hidecursor",
            "--format=png", "--quality", "1", screenshot_path,
        ),
        check=True,
        stderr=subprocess.DEVNULL,
    )


def _grim_select(screenshot_path: str):
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
    subprocess.run(("grim", "-g", geometry, screenshot_path), check=True)


def take_screenshot(screenshot_path: str):
    platform = Platform.current()
    match platform:
        case Platform.GNOME:
            _gnome_screenshot_select(screenshot_path)
        case Platform.KDE:
            _spectacle_select(screenshot_path)
        case Platform.XFCE:
            _xfce_screenshooter_select(screenshot_path)
        case Platform.Xorg:
            _maim_select(screenshot_path)
        case Platform.Wayland:
            _grim_select(screenshot_path)
