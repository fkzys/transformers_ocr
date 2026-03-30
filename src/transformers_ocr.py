#!/usr/bin/python3
# Thin wrapper — delegates to the transformers_ocr package.
# Installed as /usr/bin/transformers_ocr by `make install`.

from transformers_ocr.cli import main

if __name__ == "__main__":
    main()
