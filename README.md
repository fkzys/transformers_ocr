# Transformers OCR

An OCR tool for the GNU operating system that uses `Transformers`.
Supports Xorg and Wayland.

This is a maintained fork of the [original project](https://github.com/Ajatt-Tools/transformers_ocr) by Ajatt-Tools (now archived).
Development continues at **https://gitlab.com/fkzys/transformers-ocr**.

https://user-images.githubusercontent.com/69171671/177458117-ba858b79-0b2e-4605-9985-5801d9685bd6.mp4

The application is designed to be lightweight and work well with tiling window managers.
It requires few dependencies — most of which you probably already have.
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

### Other distros (manual install)

**Step 1.** Install the dependencies for your platform.

<details>
<summary>Xorg</summary>

* [pip](https://pypi.org/project/pip/)
* [maim](https://github.com/naelstrof/maim)
* [xclip](https://github.com/astrand/xclip)

</details>

<details>
<summary>Wayland</summary>

* [pip](https://pypi.org/project/pip/)
* [grim](https://git.sr.ht/~emersion/grim)
* [slurp](https://github.com/emersion/slurp)
* [wl-clipboard](https://github.com/bugaevc/wl-clipboard) (`wl-copy`)

</details>

<details>
<summary>GNOME</summary>

* [pip](https://pypi.org/project/pip/)
* [gnome-screenshot](https://gitlab.gnome.org/GNOME/gnome-screenshot)
* [wl-clipboard](https://github.com/bugaevc/wl-clipboard) (`wl-copy`)

</details>

<details>
<summary>KDE</summary>

* [pip](https://pypi.org/project/pip/)
* [spectacle](https://github.com/KDE/spectacle/)
* [wl-clipboard](https://github.com/bugaevc/wl-clipboard) (`wl-copy`)

</details>

<details>
<summary>XFCE</summary>

* [pip](https://pypi.org/project/pip/)
* [xfce4-screenshooter](https://gitlab.xfce.org/apps/xfce4-screenshooter)
* [xclip](https://github.com/astrand/xclip)

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

A screen-selection tool will appear. Select a region containing text,
and the recognized result will be copied to the clipboard.

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

Example with Flameshot:

```bash
img=$(mktemp -u --suffix .png)
flameshot gui --path "$img" --delay 100
transformers_ocr recognize --image-path "$img"
```

> **Note:** when `--image-path` is used, the file is **not** deleted
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
| `clip_command` | Custom clipboard command (see below) | `xclip`/`wl-copy` |
| `force_cpu` | Force CPU inference (`yes`/`no`) | `no` |
| `screenshot_dir` | Save screenshots and OCR results to this directory | *(disabled)* |

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

## Purge

Remove all downloaded model data and the virtual environment:

```bash
transformers_ocr purge
```

## License

GNU GPL, version 3 or later.
