---
title: TRANSFORMERS_OCR
section: 8
header: System Administration
footer: transformers_ocr
---

# NAME

transformers_ocr — screen OCR tool using Hugging Face transformers models

# SYNOPSIS

**transformers_ocr** [*options*] *command*

**transformers_ocr** [*options*] **recognize** [**\--image-path** *PATH*]

**transformers_ocr** [*options*] **hold** [**\--image-path** *PATH*]

# DESCRIPTION

**transformers_ocr** is an OCR tool that uses Hugging Face transformers models
(manga-ocr by default) to extract text from screen regions. It runs as a
background listener process that communicates via a FIFO pipe. A screenshot
is taken, optionally previewed for cropping, then sent to the OCR model.

Supports both X11 and Wayland. Requires a downloaded model (run **download**
once after installation).

# COMMANDS

**recognize** [**\--image-path** *PATH*]
:   OCR a part of the screen. Takes a screenshot and extracts text.
    If **\--image-path** is given, uses that file instead of a screenshot.
    Aliases: **ocr**.

**hold** [**\--image-path** *PATH*]
:   OCR and hold a part of the screen. Same as **recognize** but holds the
    result for manual inspection.

**start** [**\--foreground**]
:   Start the background listener process. With **\--foreground**, runs in
    the current terminal. Aliases: **listen**.

**stop**
:   Stop the background listener.

**restart**
:   Stop and restart the listener.

**status**
:   Print listening status, platform, and model.

**download**
:   Download the OCR model files. Must be run once after installation.

**purge**
:   Delete all downloaded model data. Aliases: **nuke**.

# OPTIONS

**-h**, **\--help**
:   Show usage summary and exit.

# EXIT STATUS

**0**
:   Success.

**1**
:   Error. Common causes: missing dependencies, model not downloaded,
    screenshot cancelled.

**130**
:   Interrupted (Ctrl+C).

# FILES

**~/.local/share/manga_ocr/\***
:   Downloaded model data (populated by **transformers_ocr download**).

# SEE ALSO

**manga-ocr**(1)
