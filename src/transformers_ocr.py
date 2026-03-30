#!/usr/bin/python3
# Thin wrapper — delegates to the transformers_ocr package.
# Installed as /usr/bin/transformers_ocr by `make install`.

import os
import sys


def _ensure_package_importable():
    """Add the installed package location to sys.path if not already present.

    This handles the case where the entry-point lives in a directory
    (e.g. ~/.local/bin) whose corresponding site-packages is not on
    sys.path — common with systemd user units and sudo installs.
    """
    try:
        import transformers_ocr  # noqa: F401 — already importable
        return
    except ImportError:
        pass

    import sysconfig
    for scheme in ("posix_user", "posix_prefix"):
        try:
            sp = sysconfig.get_path("purelib", scheme)
        except KeyError:
            continue
        if sp and os.path.isdir(os.path.join(sp, "transformers_ocr")):
            sys.path.insert(0, sp)
            return

    script_dir = os.path.dirname(os.path.abspath(__file__))
    pkg_dir = os.path.join(script_dir, "transformers_ocr")
    if os.path.isdir(pkg_dir):
        sys.path.insert(0, script_dir)
        return

    bin_dir = os.path.dirname(os.path.abspath(__file__))
    prefix = os.path.dirname(bin_dir)
    import glob
    candidates = glob.glob(
        os.path.join(prefix, "lib", "python*", "site-packages")
    )
    for sp in candidates:
        if os.path.isdir(os.path.join(sp, "transformers_ocr")):
            sys.path.insert(0, sp)
            return


_ensure_package_importable()

from transformers_ocr.cli import main  # noqa: E402

if __name__ == "__main__":
    main()
