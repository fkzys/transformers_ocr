# Tests

## Overview

| File | Framework | What it tests |
|------|-----------|---------------|
| `test_cli.py` | pytest | Status display (running/stopped), `run_ocr` with `image_path` (preview accept/cancel/same-path), `run_ocr` screenshot path (fullscreen capture + preview, cancel cleanup, error cleanup), CLI argument parser (all subcommands, aliases, removed `--preview` flag, `--image-path`), `main()` error handling (missing program, cancelled screenshot, KeyboardInterrupt, subprocess error) |
| `test_config.py` | pytest | Config file parsing (`_is_valid_key_val_pair`, comments, empty lines, whitespace stripping, values containing `=`), `TrOcrConfig` fields (`force_cpu`, `clip_args`, `screenshot_dir`, `model`, default model value), removed `preview` attribute verification, path helpers (`_get_home` fallback/error, `_get_runtime_dir` XDG/fallback) |
| `test_download.py` | pytest | `purge_manga_ocr_data` — removes both `MANGA_OCR_PREFIX` and `HUGGING_FACE_CACHE_PATH` via `shutil.rmtree` |
| `test_fifo.py` | pytest | FIFO detection (`is_fifo` for FIFO/regular/missing), `prepare_pipe` (create/existing/replace regular file), `_safe_remove` (existing/missing), `iter_commands` (valid commands, stop command, empty lines, invalid JSON, invalid action, missing fields, extra fields) |
| `test_notify.py` | pytest | `notify_send` — calls `notify-send` subprocess, handles missing binary (`FileNotFoundError`), handles timeout (`TimeoutExpired`) |
| `test_ocr_command.py` | pytest | `OcrCommand` — JSON serialization (`as_json`), validation (valid actions, invalid action, missing/non-string `file_path`), JSON roundtrip, default `delete_after` |
| `test_platform.py` | pytest | Platform detection (`_is_xorg`, `Platform.current()`, only two enum members), clipboard args (xclip vs wl-copy), `raise_if_missing` (present/absent, single-arg signature), `take_fullscreen_screenshot` (delegates to `screengrab.grab_fullscreen`, failure raises `RuntimeError` mentioning X11 and Wayland) |
| `test_preview.py` | pytest | `preview_available` flag, `preview_image` without SDL2 (returns original path), `preview_image` with SDL2 (calls `_CropOverlay`, cancel returns `None`, exception returns original path), coordinate transforms (`_transform_point_cw90`, `_transform_point` multi-step/identity/180°/270°), `_CropOverlay` internals without SDL init: `_effective_size` at all rotations, screen↔image coordinate roundtrip, viewport center roundtrip, `_get_crop_rect` (no selection, tiny selection, valid rect, swapped coords, clamped to image, all rotations), `_fit`, `_zoom_at` (increase/decrease/clamp min-max), `_rotate` (CW/CCW/full circle/zero/180°, selection preserved and normalized, viewport center preserved), `_accept`/`_cancel` |
| `test_process.py` | pytest | `is_running` (self/nonexistent/zero/negative/PermissionError), `get_pid` (valid/missing file/dead process/garbage/empty), `kill_after` (already dead, sends SIGKILL, exits during wait), file locking (`_acquire_lock`/`_release_lock`, double acquire fails), `stop_listening` (already stopped, sends stop via pipe, pipe error falls back to SIGTERM), `ensure_listening` (not downloaded, lock not acquired, PID exists, starts listener subprocess) |
| `test_screengrab.py` | pytest | Wayland detection (`_is_wayland`), `grab_fullscreen` dispatch (Wayland→portal, X11→`_grab_x11`, failure messages), X11 capture error paths (no Xlib, load failure, no SDL2, no SDL2_image, display open failure), Wayland portal error paths (no libdbus, load failure, bus connection failure), `_save_portal_file` (move success, move-fails-copy-succeeds, both fail, URI prefix), library loading (`_load_lib` find_library/fallback SO names/all fail, `_load_sdl2` sets argtypes, `_load_sdl2_image`), D-Bus helpers (`_setup_dbus_functions` argtypes, `_make_iter` buffer size, `_build_screenshot_message` success/failure, `_parse_response_uri` no-init/wrong-type), `_XImage`/`_DBusError` structure fields and defaults |
| `test_screengrab_integration.py` | pytest | **Requires Xvfb.** Xlib sanity (open/close display, root window nonzero size, Xvfb 1920×1080 match), `_grab_x11` integration (creates valid PNG, correct header, reasonable file size, nonexistent dir fails, two captures no resource leak, independent output files), `grab_fullscreen` X11 path (valid PNG, confirms non-Wayland path), capture content validation (PNG dimensions match root window geometry) |
| `test_wrapper.py` | pytest | `MangaOcrWrapper` — OCR text replacements (ASCII/Japanese/fullwidth ellipsis, no replacement, multiple replacements), `_process_command` (stop raises `StopRequested`, hold accumulates text, recognize joins held text with `、`, `delete_after` removes temp file, preserves user image), `_to_clip` (stdin pipe via xclip, `%TEXT%` placeholder substitution, missing program notification, timeout kills process), `_maybe_save_result` (saves PNG + `.gt.txt` to screenshot_dir, disabled when `None`), `_load_model` (passes default/custom model and `force_cpu` to `MangaOcr`) |

## Running

```bash
# All tests (unit + integration)
make test

# Unit tests only (no display server required)
make test-unit

# Integration tests only (starts Xvfb on :99)
make test-xvfb

# Individual suite
python -m pytest tests/test_config.py -v
python -m pytest tests/test_cli.py -v
python -m pytest tests/test_preview.py -v
# ... etc.

# Smoke test in systemd-nspawn container (requires root + pacstrap)
sudo make test-smoke
```

## How they work

### Unit tests (`test_cli.py` .. `test_wrapper.py`)

Standard pytest suites. No display server, no real OCR model, no filesystem side effects beyond `tmp_path`. All external dependencies are mocked:

- **subprocess calls** (`notify-send`, `xclip`, `wl-copy`, `Popen`) — mocked via `unittest.mock.patch`
- **config file** — `tocr_config.CONFIG_PATH` patched to `tmp_path` files or `/nonexistent`
- **manga-ocr model** — `MangaOcr` replaced with `MagicMock` via `sys.modules`
- **SDL2/preview overlay** — `_CropOverlay` and `_HAS_SDL2` patched; coordinate math tested on stub objects created via `object.__new__()` bypassing `__init__`
- **platform detection** — `WAYLAND_DISPLAY` environment variable manipulated via `patch.dict(os.environ)`
- **PID/lock files** — written to `tmp_path`, `PID_FILE`/`LOCK_FILE` patched
- **screengrab native libraries** — `ctypes.CDLL`, `ctypes.util.find_library`, and internal `_load_lib`/`_load_sdl2` patched to return `MagicMock` or `None`

### Integration tests (`test_screengrab_integration.py`)

Require a running X11 display. The Makefile target `test-xvfb`:

1. Kills any stale Xvfb on `:99`
2. Starts `Xvfb :99 -screen 0 1920x1080x24`
3. Runs pytest with `DISPLAY=:99` and `WAYLAND_DISPLAY` unset
4. Tears down Xvfb after tests complete

Tests use skip markers (`requires_x11`, `requires_sdl2`) that check for a working display connection, Xlib availability, and SDL2/SDL2_image. The helper `_get_root_geometry()` calls Xlib directly via ctypes to verify root window dimensions. PNG output is validated by reading the IHDR chunk.

### Smoke test (`make test-smoke`)

Creates a disposable Arch Linux container via `pacstrap` + `systemd-nspawn`, copies the project source in, and runs both `make test-unit` and `make test-xvfb` inside the container. Requires root. Cleans up the container on completion.

## Test environment

- Unit tests create temporary files via pytest's `tmp_path` fixture, automatically cleaned up
- No root privileges required for unit or integration tests
- No real OCR model is loaded — `manga_ocr.MangaOcr` is always mocked
- No screenshots are taken outside of Xvfb integration tests
- Integration tests capture the Xvfb root window (blank/black screen) — content doesn't matter, only format and dimensions are validated
- `WAYLAND_DISPLAY` is explicitly unset for integration tests to force the X11 code path

## Dependencies

### Unit tests

```
python-pytest
python-pytest-timeout
```

### Integration tests (additional)

```
xorg-server-xvfb
libx11
sdl2
sdl2_image
```
