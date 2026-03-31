# Transformers OCR

[![CI](https://github.com/rpPH4kQocMjkm2Ve/transformers_ocr/actions/workflows/ci.yml/badge.svg)](https://github.com/rpPH4kQocMjkm2Ve/transformers_ocr/actions/workflows/ci.yml)
![License](https://img.shields.io/github/license/rpPH4kQocMjkm2Ve/transformers_ocr)

An OCR tool for the GNU operating system that uses `Transformers`.
Supports Xorg and Wayland.

This is a maintained fork of the [original project](https://github.com/Ajatt-Tools/transformers_ocr) by Ajatt-Tools (now archived).
Development continues at **https://gitlab.com/fkzys/transformers_ocr**.

https://user-images.githubusercontent.com/69171671/177458117-ba858b79-0b2e-4605-9985-5801d9685bd6.mp4

The application is designed to be lightweight and work well with tiling window managers.
Screen capture and the crop/preview overlay use native libraries (Xlib, D-Bus, SDL2)
loaded via ctypes — no external screenshot tools are required.
The heavier Python libraries (`manga-ocr`, `transformers`, `torch`) are installed
into an isolated virtual environment under `~/.local/share/manga_ocr`
to keep your system clean.

> If your machine is slow, consider using Tesseract instead.

## Installation

### Arch Linux

Install from the AUR:

```bash
yay -S transformers_ocr-git
```

Install with [gitpkg](https://gitlab.com/fkzys/gitpkg):

```
gitpkg install transformers_ocr
```

### Other distros (manual install)

**Step 1.** Install the dependencies for your platform.

<details>
<summary>Xorg</summary>

* [pip](https://pypi.org/project/pip/)
* [xclip](https://github.com/astrand/xclip) (clipboard)
* [libX11](https://www.x.org/) (screen capture — usually already installed)
* [SDL2](https://www.libsdl.org/) + [SDL2_image](https://github.com/libsdl-org/SDL_image) (crop/preview overlay — optional but recommended)

</details>

<details>
<summary>Wayland</summary>

* [pip](https://pypi.org/project/pip/)
* [wl-clipboard](https://github.com/bugaevc/wl-clipboard) (`wl-copy`)
* [xdg-desktop-portal](https://github.com/flatpak/xdg-desktop-portal) (screen capture — usually already running)
* [SDL2](https://www.libsdl.org/) + [SDL2_image](https://github.com/libsdl-org/SDL_image) (crop/preview overlay — optional but recommended)

</details>

**Step 2.** Clone and install.

```bash
git clone 'https://gitlab.com/fkzys/transformers-ocr.git'
cd transformers-ocr
sudo make install
```

To uninstall:

```bash
sudo make uninstall
```

## Setup

Download the `manga-ocr` model and dependencies (only needed once):

```bash
transformers_ocr download
```

Files are saved to `~/.local/share/manga_ocr`.
On the first recognition run, additional model weights will be
downloaded to `~/.cache/huggingface`.

## Usage

Show all available commands:

```bash
transformers_ocr --help
```

### Recognize text

```bash
transformers_ocr recognize
```

A fullscreen screenshot is taken, then a crop overlay appears.
Draw a rectangle around the text you want to recognize, press
Enter or Space to confirm. The recognized result is copied to the clipboard.

**Overlay controls:**

| Action | Input |
|--------|-------|
| Select region | Left-click drag |
| Pan | Middle-click drag |
| Zoom | Scroll wheel / `+` / `-` |
| Rotate CW 90° | `r` |
| Rotate CCW 90° | `Shift+r` |
| Reset view | `0` |
| Accept | Enter / Space |
| Clear selection | Right-click (when selection exists) |
| Cancel | Escape / Right-click (no selection) / close window |

If SDL2 is not installed, the overlay is skipped and the full screenshot
is sent directly to OCR.

### Keyboard shortcut

Bind the command to a hotkey in your window manager config.

**i3wm** example (`~/.config/i3/config`):

```
bindsym $mod+o        exec --no-startup-id transformers_ocr recognize
bindsym $mod+Shift+o  exec --no-startup-id transformers_ocr hold
```

**Sway** example (`~/.config/sway/config`):

```
bindsym $mod+o        exec transformers_ocr recognize
bindsym $mod+Shift+o  exec transformers_ocr hold
```

### Background listener

On the first call, `transformers_ocr` automatically starts a background
listener process. To speed up the very first recognition, you can start
it ahead of time (e.g. from `~/.profile`, `~/.xinitrc`, or your WM's
autostart):

```bash
transformers_ocr start
```

Other listener commands:

```bash
transformers_ocr stop      # stop the listener
transformers_ocr restart   # restart the listener
transformers_ocr status    # print current status
```

### Systemd user service

A systemd user unit is shipped and installed automatically.
You can use it instead of manually adding `transformers_ocr start` to
your autostart:

```bash
systemctl --user enable --now transformers_ocr.service
```

To check the service status:

```bash
systemctl --user status transformers_ocr.service
```

To stop and disable:

```bash
systemctl --user disable --now transformers_ocr.service
```

The service starts the daemon in foreground mode, automatically restarts
on failure, and is bound to `graphical-session.target`.

## Holding text

Often a sentence is split across multiple speech bubbles.
Screenshotting the entire area (including gaps) produces junk,
but processing each bubble separately gives incomplete sentences.

The **hold** feature solves this:

1. Call `transformers_ocr hold` on each speech bubble — text is
   recognized and remembered.
2. Call `transformers_ocr recognize` on the last bubble — all held
   pieces are joined together and copied to the clipboard.

https://user-images.githubusercontent.com/69171671/233484898-776ea15a-5a7a-443a-ac2e-5d06fb61540b.mp4

## Passing an image path

Use `--image-path` to recognize an existing image file instead of
taking a screenshot:

```bash
transformers_ocr recognize --image-path /path/to/image.png
```

The crop overlay still appears, letting you select a region within the
image. If you crop, the original file is left untouched and a temporary
cropped copy is used for OCR.

Example with Flameshot:

```bash
img=$(mktemp -u --suffix .png)
flameshot gui --path "$img" --delay 100
transformers_ocr recognize --image-path "$img"
```

> **Note:** when `--image-path` is used, the original file is **not** deleted
> after recognition.

## Config file

Create an optional config file:

```bash
mkdir -p ~/.config/transformers_ocr
touch ~/.config/transformers_ocr/config
```

Format: `key=value`, one per line. Lines starting with `#` are comments.

### Available options

| Key | Description | Default |
|-----|-------------|---------|
| `model` | HuggingFace model to use (see below) | `tatsumoto/manga-ocr-base` |
| `clip_command` | Custom clipboard command (see below) | `xclip`/`wl-copy` |
| `force_cpu` | Force CPU inference (`yes`/`no`) | `no` |
| `screenshot_dir` | Save screenshots and OCR results to this directory | *(disabled)* |

### Choosing a model

By default, `transformers_ocr` uses
[`tatsumoto/manga-ocr-base`](https://huggingface.co/tatsumoto/manga-ocr-base),
which ships weights in the
[safetensors](https://huggingface.co/docs/safetensors/) format
(no pickle, faster loading).

Other compatible models:

| Model | Notes |
|-------|-------|
| `tatsumoto/manga-ocr-base` | **Default.** Safetensors format. |
| `jzhang533/manga-ocr-base-2025` | Safetensors format. |
| `kha-white/manga-ocr-base` | Original model. Uses pickle-based weights. |

To switch:

```bash
echo 'model=jzhang533/manga-ocr-base-2025' >> ~/.config/transformers_ocr/config
transformers_ocr restart
```

Any HuggingFace model path or local directory path compatible with the
manga-ocr architecture is accepted.

### Custom clipboard command

Instead of copying to the system clipboard, you can send text to any
program. Use `%TEXT%` as a placeholder for the recognized text
(passed as an argument). If `%TEXT%` is omitted, text is written to
the program's stdin.

```bash
# Send directly to GoldenDict
echo 'clip_command=goldendict %TEXT%' >> ~/.config/transformers_ocr/config
transformers_ocr restart
```

### Force CPU

```bash
echo 'force_cpu=yes' >> ~/.config/transformers_ocr/config
transformers_ocr restart
```

## Architecture

```
┌─────────────┐      FIFO       ┌──────────────┐
│  CLI client  │ ──────────────▶ │   Listener   │
│  (recognize, │  OcrCommand    │  (wrapper.py) │
│   hold, …)   │  as JSON       │              │
└──────┬───────┘                └──────┬───────┘
       │                               │
  screenshot                     manga-ocr model
  + crop overlay                 + clipboard
  (screengrab.py,                  (xclip/wl-copy
   preview.py)                    or custom cmd)
```

The CLI client takes a screenshot (via Xlib on X11 or xdg-desktop-portal
on Wayland), opens an SDL2 crop overlay, then writes an `OcrCommand`
(JSON) to a named pipe. The listener daemon reads commands, runs the
manga-ocr model, and copies recognized text to the clipboard.

Communication between client and listener uses a FIFO at
`$XDG_RUNTIME_DIR/transformers_ocr/manga_ocr.fifo`. The listener is
started automatically on the first `recognize`/`hold` call and can be
managed with `start`/`stop`/`restart`/`status`.

## Purge

Remove all downloaded model data and the virtual environment:

```bash
transformers_ocr purge
```

## Tests

See [`tests/README.md`](tests/README.md) for details.

## License

GNU GPL, version 3 or later.
