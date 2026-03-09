# Changelog

## [Unreleased] — 2026-03-10

Fork of [Ajatt-Tools/transformers_ocr](https://github.com/Ajatt-Tools/transformers_ocr) (archived).
Repository moved to https://gitlab.com/fkzys/transformers-ocr.

### Security

- **Runtime files moved out of world-writable `/tmp`.**
  PID file, FIFO pipe, and lock file are now created under
  `$XDG_RUNTIME_DIR/transformers_ocr/` (mode 0700) with a
  UID-based fallback, preventing symlink attacks and cross-user
  interference.
- **FIFO commands are now validated.**
  Incoming JSON on the named pipe is checked for valid `action`
  values and proper `file_path` types. Malformed or unknown
  commands are logged and skipped instead of crashing the listener.
- **FIFO is created with restricted permissions** (mode 0600).

### Fixed

- **TOCTOU race condition in `prepare_pipe`.**
  Replaced check-then-act pattern with atomic `os.mkfifo` guarded
  by `FileExistsError`, eliminating the window for file substitution.
- **Race condition when starting the listener.**
  Concurrent `ensure_listening` calls are now serialized with an
  exclusive file lock (`fcntl.flock`), preventing duplicate listener
  processes.
- **`kill_after` could SIGKILL an already-exited (or recycled) PID.**
  Now returns immediately when the process is gone; SIGKILL is only
  sent if the process is still alive after the timeout.
- **`is_running` used `/proc` existence check.**
  Replaced with `os.kill(pid, 0)` which correctly handles
  `PermissionError` (process exists but owned by another user).
- **`is_installed` crashed on non-Arch systems.**
  `pacman` call is now wrapped in `try/except FileNotFoundError`.
- **`grim_select`: `slurp` cancellation produced a raw
  `CalledProcessError`.**
  Now caught and re-raised as `ScreenshotCancelled` with a clear
  message.
- **User-provided images were deleted after recognition.**
  Added `delete_after` field to `OcrCommand`; files passed via
  `--image-path` are preserved, only auto-created temp files are
  cleaned up.
- **Temporary screenshot files leaked on errors.**
  `run_ocr` now uses `try/finally` to ensure cleanup.
- **`notify_send` spawned zombie processes.**
  Replaced `Popen` (no `wait`) with `subprocess.run(timeout=10)`.
- **`_to_clip` left zombie processes when not writing to stdin.**
  Added `p.wait(timeout=10)` for the no-stdin branch and
  `TimeoutExpired` handling with `p.kill()`.
- **`KeyboardInterrupt` during `download` printed a raw traceback.**
  Now caught in `main()` with a clean message and exit code 130.
- **`download_manga_ocr` could fail silently with a stale venv.**
  The virtual environment is now recreated on every `download` call,
  and network connectivity is verified from within the venv before
  running `pip install`.
- **Typo: `spectactle_select`** → `spectacle_select`.
- **`stderr=sys.stdout` in `maim_select`** → `stderr=subprocess.DEVNULL`.
- **`ensure_listening` bypassed wrapper scripts.**
  The subprocess was launched via a hardcoded path to the venv Python
  and `__file__`, skipping any wrapper (e.g. bwrap sandbox) installed
  earlier in `$PATH`. Now uses the program name for standard PATH
  lookup, allowing wrappers to intercept the `start --foreground`
  invocation.

### Changed

- **No more module-level side effects.**
  `IS_XORG`, `CURRENT_PLATFORM`, and `CLIP_COPY_ARGS` globals are
  removed. Platform detection and clipboard args are now computed
  lazily via `Platform.current()` and `_get_clip_copy_args()`,
  making the module safely importable and testable.
- **`$HOME` access is safe.**
  Uses `pathlib.Path.home()` with a fallback and a clear error
  message instead of a bare `os.environ["HOME"]` that raised
  `KeyError`.
- **`main()` no longer calls `prepare_pipe()` unconditionally.**
  The FIFO is only created when actually needed (`ensure_listening`,
  `MangaOcrWrapper.init`), avoiding pointless side effects for
  commands like `status`, `purge`, and `download`.
- **`CalledProcessError` from subcommands is now caught in `main()`**
  and printed as a human-readable message instead of a traceback.
- **Redundant `bool()` wrapper removed** from `_should_force_cpu`.

### Makefile

- **Added `DESTDIR` support** for staged installs and package
  building (`makepkg`, `dpkg-buildpackage`, etc.).
- **Replaced `echo -e` with `printf`** for POSIX compatibility.
- **Replaced `wildcard *.py`** with an explicit file list to prevent
  accidental installation of helper modules or test files.
- **`uninstall` uses `rm -f`** instead of `rm --`, making it
  idempotent.
- **Replaced `ln -srf` (GNU-only) with `ln -sf`** for portability.
- **`install` message prints before actions**, not after.
- **Removed no-op `clean` rule** that deleted a nonexistent `out/`
  directory.
