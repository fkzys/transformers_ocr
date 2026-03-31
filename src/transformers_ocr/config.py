# Copyright: Ren Tatsumoto <tatsu at autistici.org> and contributors
# Copyright: fkzys and contributors
# License: GNU GPL, version 3 or later; http://www.gnu.org/licenses/gpl.html

"""Configuration loading and path constants."""

import os
import shlex
import tempfile
from pathlib import Path


# ---------------------------------------------------------------------------
# Paths
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


HOME = _get_home()
RUNTIME_DIR = _get_runtime_dir()

MANGA_OCR_PREFIX = os.path.join(HOME, ".local", "share", "manga_ocr")
MANGA_OCR_PYENV_PATH = os.path.join(MANGA_OCR_PREFIX, "pyenv")
MANGA_OCR_PYENV_PIP_PATH = os.path.join(MANGA_OCR_PYENV_PATH, "bin", "pip")
HUGGING_FACE_CACHE_PATH = os.path.join(HOME, ".cache", "huggingface")

CONFIG_PATH = os.path.join(
    os.environ.get("XDG_CONFIG_HOME", os.path.join(HOME, ".config")),
    "transformers_ocr",
    "config",
)

PIPE_PATH = os.path.join(RUNTIME_DIR, "manga_ocr.fifo")
PID_FILE = os.path.join(RUNTIME_DIR, "manga_ocr.pid")
LOCK_FILE = os.path.join(RUNTIME_DIR, "manga_ocr.lock")

JOIN = "、"
CLIP_TEXT_PLACEHOLDER = "%TEXT%"

# Known models that work with the manga-ocr architecture.
KNOWN_MODELS = (
    "tatsumoto/manga-ocr-base",
    "jzhang533/manga-ocr-base-2025",
    "kha-white/manga-ocr-base",
)
DEFAULT_MODEL = "tatsumoto/manga-ocr-base"


# ---------------------------------------------------------------------------
# Config file parsing
# ---------------------------------------------------------------------------

def _is_valid_key_val_pair(line: str) -> bool:
    return "=" in line and not line.startswith("#")


def get_config() -> dict[str, str]:
    config: dict[str, str] = {}
    if os.path.isfile(CONFIG_PATH):
        with open(CONFIG_PATH, encoding="utf8") as f:
            for line in filter(_is_valid_key_val_pair, f.read().splitlines()):
                key, value = line.split("=", maxsplit=1)
                config[key.strip()] = value.strip()
    return config


class TrOcrConfig:
    def __init__(self):
        self._config = get_config()
        self.force_cpu = self._should_force_cpu()
        self.model = self._config.get("model", DEFAULT_MODEL)
        self.clip_args = self._key_to_cmd_args("clip_command")
        self.screenshot_dir = self._get_screenshot_dir()
        self.preview = self._config.get("preview", "no") in ("true", "yes")

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
