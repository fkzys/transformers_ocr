#!/usr/bin/python3
# Copyright: Ren Tatsumoto <tatsu at autistici.org> and contributors
# Copyright: fkzys and contributors
# License: GNU GPL, version 3 or later; http://www.gnu.org/licenses/gpl.html

# Thin wrapper installed as /usr/bin/transformers_ocr.
# The package lives in /usr/lib/transformers_ocr/.

import os
import sys

# Add the package directory to sys.path so that `import transformers_ocr`
# works regardless of which Python interpreter runs this script (system,
# venv, bwrap, etc.).
_PKGLIB = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    "..", "lib", "transformers_ocr",
)
if os.path.isdir(_PKGLIB) and _PKGLIB not in sys.path:
    sys.path.insert(0, _PKGLIB)

from transformers_ocr.cli import main  # noqa: E402

if __name__ == "__main__":
    main()
