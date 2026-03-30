# Copyright: Ren Tatsumoto <tatsu at autistici.org> and contributors
# Copyright: fkzys and contributors
# License: GNU GPL, version 3 or later; http://www.gnu.org/licenses/gpl.html

"""Download and purge manga-ocr data."""

import os
import shutil
import subprocess
import sys

from transformers_ocr.config import (
    HUGGING_FACE_CACHE_PATH,
    MANGA_OCR_PREFIX,
    MANGA_OCR_PYENV_PATH,
    MANGA_OCR_PYENV_PIP_PATH,
)


def download_manga_ocr():
    print("Downloading manga-ocr...")
    os.makedirs(MANGA_OCR_PREFIX, exist_ok=True)

    # Always recreate venv to avoid stale symlinks after Python upgrades.
    if os.path.exists(MANGA_OCR_PYENV_PATH):
        print("Recreating virtual environment...")
        shutil.rmtree(MANGA_OCR_PYENV_PATH)

    subprocess.run(
        ("python3", "-m", "venv", "--symlinks", MANGA_OCR_PYENV_PATH),
        check=True,
    )

    # Verify the venv works before proceeding.
    venv_python = os.path.join(MANGA_OCR_PYENV_PATH, "bin", "python3")
    try:
        subprocess.run(
            (
                venv_python,
                "-c",
                "import ssl, socket; socket.getaddrinfo('pypi.org', 443)",
            ),
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


def purge_manga_ocr_data():
    shutil.rmtree(MANGA_OCR_PREFIX, ignore_errors=True)
    shutil.rmtree(HUGGING_FACE_CACHE_PATH, ignore_errors=True)
    print("Purged all downloaded manga-ocr data.")
