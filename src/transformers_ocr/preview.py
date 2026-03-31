# Copyright: fkzys and contributors
# License: GNU GPL, version 3 or later; http://www.gnu.org/licenses/gpl.html

"""Fullscreen overlay for cropping, with pan/zoom/rotate.

Takes a fullscreen screenshot as input, lets the user select
a region to crop, then returns the cropped (and optionally
rotated) image for OCR.

Controls
~~~~~~~~
Select     left-click drag to draw crop rectangle
Pan        middle-click drag  (when zoomed in)
Zoom       scroll wheel  /  ``+``  /  ``-``
Rotate     ``r`` → CW 90°,  ``R`` → CCW 90°
Reset      ``0``
Accept     Enter  /  Space  (crops to selection)
Cancel     Escape  /  right-click  /  close window
"""

import ctypes
import ctypes.util
import os
import sys
import tempfile
from typing import Optional


def _load_lib(names):
    for name in names:
        path = ctypes.util.find_library(name)
        if path:
            try:
                return ctypes.CDLL(path)
            except OSError:
                continue
        for so in (f"lib{name}.so", f"lib{name}.so.0", f"lib{name}-2.0.so.0"):
            try:
                return ctypes.CDLL(so)
            except OSError:
                continue
    return None


_sdl = _load_lib(("SDL2", "SDL2-2.0"))
_img = _load_lib(("SDL2_image", "SDL2_image-2.0"))
_HAS_SDL2 = _sdl is not None and _img is not None

if _HAS_SDL2:
    _u32 = ctypes.c_uint32
    _i32 = ctypes.c_int32
    _c_int = ctypes.c_int
    _c_float = ctypes.c_float
    _c_double = ctypes.c_double
    _c_char_p = ctypes.c_char_p
    _void_p = ctypes.c_void_p
    _u8 = ctypes.c_uint8
    _u16 = ctypes.c_uint16

    SDL_INIT_VIDEO = 0x00000020
    SDL_INIT_EVENTS = 0x00004000

    SDL_WINDOW_SHOWN = 0x00000004
    SDL_WINDOW_BORDERLESS = 0x00000010
    SDL_WINDOW_FULLSCREEN_DESKTOP = 0x00001001
    SDL_WINDOW_ALLOW_HIGHDPI = 0x00002000
    SDL_WINDOW_ALWAYS_ON_TOP = 0x00008000
    SDL_WINDOW_INPUT_GRABBED = 0x00000100
    SDL_WINDOW_KEYBOARD_GRABBED = 0x00100000
    SDL_WINDOW_SKIP_TASKBAR = 0x00010000

    SDL_RENDERER_ACCELERATED = 0x00000002
    SDL_RENDERER_PRESENTVSYNC = 0x00000004
    SDL_RENDERER_SOFTWARE = 0x00000001

    SDL_QUIT = 0x100
    SDL_KEYDOWN = 0x300
    SDL_MOUSEBUTTONDOWN = 0x401
    SDL_MOUSEBUTTONUP = 0x402
    SDL_MOUSEMOTION = 0x400
    SDL_MOUSEWHEEL = 0x403
    SDL_WINDOWEVENT = 0x200

    SDL_WINDOWEVENT_EXPOSED = 3

    SDL_SCANCODE_ESCAPE = 41
    SDL_SCANCODE_RETURN = 40
    SDL_SCANCODE_KP_ENTER = 88
    SDL_SCANCODE_SPACE = 44
    SDL_SCANCODE_R = 21
    SDL_SCANCODE_0 = 39
    SDL_SCANCODE_MINUS = 45
    SDL_SCANCODE_EQUALS = 46

    KMOD_SHIFT = 0x0003
    SDL_BUTTON_LEFT = 1
    SDL_BUTTON_MIDDLE = 2
    SDL_BUTTON_RIGHT = 3

    SDL_BLENDMODE_BLEND = 1
    SDL_PIXELFORMAT_RGBA8888 = 373694468

    IMG_INIT_PNG = 0x00000002
    IMG_INIT_JPG = 0x00000001

    SDL_HINT_VIDEO_WAYLAND_ALLOW_LIBDECOR = b"SDL_VIDEO_WAYLAND_ALLOW_LIBDECOR"
    SDL_HINT_VIDEO_WAYLAND_PREFER_LIBDECOR = b"SDL_VIDEO_WAYLAND_PREFER_LIBDECOR"
    SDL_HINT_VIDEO_X11_NET_WM_BYPASS_COMPOSITOR = b"SDL_VIDEO_X11_NET_WM_BYPASS_COMPOSITOR"

    SDL_SYSTEM_CURSOR_CROSSHAIR = 3

    class SDL_Rect(ctypes.Structure):
        _fields_ = [("x", _i32), ("y", _i32), ("w", _i32), ("h", _i32)]

    class SDL_FRect(ctypes.Structure):
        _fields_ = [("x", _c_float), ("y", _c_float),
                     ("w", _c_float), ("h", _c_float)]

    class SDL_Surface(ctypes.Structure):
        _fields_ = [
            ("flags", _u32), ("format", _void_p),
            ("w", _c_int), ("h", _c_int), ("pitch", _c_int),
            ("pixels", _void_p),
        ]

    class SDL_DisplayMode(ctypes.Structure):
        _fields_ = [
            ("format", _u32), ("w", _c_int), ("h", _c_int),
            ("refresh_rate", _c_int), ("driverdata", _void_p),
        ]

    class _SDL_KeyboardEvent(ctypes.Structure):
        _fields_ = [
            ("type", _u32), ("timestamp", _u32),
            ("windowID", _u32), ("state", _u8),
            ("repeat", _u8), ("padding2", _u8), ("padding3", _u8),
            ("scancode", _i32), ("sym", _i32), ("mod", _u16),
        ]

    class _SDL_MouseButtonEvent(ctypes.Structure):
        _fields_ = [
            ("type", _u32), ("timestamp", _u32),
            ("windowID", _u32), ("which", _u32),
            ("button", _u8), ("state", _u8),
            ("clicks", _u8), ("padding1", _u8),
            ("x", _i32), ("y", _i32),
        ]

    class _SDL_MouseMotionEvent(ctypes.Structure):
        _fields_ = [
            ("type", _u32), ("timestamp", _u32),
            ("windowID", _u32), ("which", _u32), ("state", _u32),
            ("x", _i32), ("y", _i32), ("xrel", _i32), ("yrel", _i32),
        ]

    class _SDL_MouseWheelEvent(ctypes.Structure):
        _fields_ = [
            ("type", _u32), ("timestamp", _u32),
            ("windowID", _u32), ("which", _u32),
            ("x", _i32), ("y", _i32), ("direction", _u32),
            ("preciseX", _c_float), ("preciseY", _c_float),
            ("mouseX", _i32), ("mouseY", _i32),
        ]

    class _SDL_WindowEvent(ctypes.Structure):
        _fields_ = [
            ("type", _u32), ("timestamp", _u32),
            ("windowID", _u32), ("event", _u8),
            ("padding1", _u8), ("padding2", _u8), ("padding3", _u8),
            ("data1", _i32), ("data2", _i32),
        ]

    class SDL_Event(ctypes.Union):
        _fields_ = [
            ("type", _u32),
            ("key", _SDL_KeyboardEvent),
            ("button", _SDL_MouseButtonEvent),
            ("motion", _SDL_MouseMotionEvent),
            ("wheel", _SDL_MouseWheelEvent),
            ("window", _SDL_WindowEvent),
            ("_padding", _u8 * 128),
        ]

    # --- function signatures ---
    _sdl.SDL_Init.argtypes = [_u32]; _sdl.SDL_Init.restype = _c_int
    _sdl.SDL_Quit.argtypes = []; _sdl.SDL_Quit.restype = None
    _sdl.SDL_SetHint.argtypes = [_c_char_p, _c_char_p]; _sdl.SDL_SetHint.restype = ctypes.c_bool
    _sdl.SDL_GetDesktopDisplayMode.argtypes = [_c_int, ctypes.POINTER(SDL_DisplayMode)]
    _sdl.SDL_GetDesktopDisplayMode.restype = _c_int
    _sdl.SDL_CreateWindow.argtypes = [_c_char_p, _c_int, _c_int, _c_int, _c_int, _u32]
    _sdl.SDL_CreateWindow.restype = _void_p
    _sdl.SDL_DestroyWindow.argtypes = [_void_p]; _sdl.SDL_DestroyWindow.restype = None
    _sdl.SDL_CreateRenderer.argtypes = [_void_p, _c_int, _u32]; _sdl.SDL_CreateRenderer.restype = _void_p
    _sdl.SDL_DestroyRenderer.argtypes = [_void_p]; _sdl.SDL_DestroyRenderer.restype = None
    _sdl.SDL_CreateTextureFromSurface.argtypes = [_void_p, _void_p]
    _sdl.SDL_CreateTextureFromSurface.restype = _void_p
    _sdl.SDL_DestroyTexture.argtypes = [_void_p]; _sdl.SDL_DestroyTexture.restype = None
    _sdl.SDL_FreeSurface.argtypes = [_void_p]; _sdl.SDL_FreeSurface.restype = None
    _sdl.SDL_SetRenderDrawColor.argtypes = [_void_p, _u8, _u8, _u8, _u8]
    _sdl.SDL_SetRenderDrawColor.restype = _c_int
    _sdl.SDL_SetRenderDrawBlendMode.argtypes = [_void_p, _c_int]
    _sdl.SDL_SetRenderDrawBlendMode.restype = _c_int
    _sdl.SDL_RenderClear.argtypes = [_void_p]; _sdl.SDL_RenderClear.restype = _c_int
    _sdl.SDL_RenderCopy.argtypes = [_void_p, _void_p, ctypes.POINTER(SDL_Rect), ctypes.POINTER(SDL_Rect)]
    _sdl.SDL_RenderCopy.restype = _c_int
    _sdl.SDL_RenderCopyExF.argtypes = [
        _void_p, _void_p, ctypes.POINTER(SDL_Rect), ctypes.POINTER(SDL_FRect),
        _c_double, ctypes.POINTER(SDL_FRect), _c_int,
    ]
    _sdl.SDL_RenderCopyExF.restype = _c_int
    _sdl.SDL_RenderPresent.argtypes = [_void_p]; _sdl.SDL_RenderPresent.restype = None
    _sdl.SDL_RenderFillRect.argtypes = [_void_p, ctypes.POINTER(SDL_Rect)]
    _sdl.SDL_RenderFillRect.restype = _c_int
    _sdl.SDL_RenderDrawRect.argtypes = [_void_p, ctypes.POINTER(SDL_Rect)]
    _sdl.SDL_RenderDrawRect.restype = _c_int
    _sdl.SDL_RenderDrawLineF.argtypes = [_void_p, _c_float, _c_float, _c_float, _c_float]
    _sdl.SDL_RenderDrawLineF.restype = _c_int
    _sdl.SDL_PollEvent.argtypes = [ctypes.POINTER(SDL_Event)]; _sdl.SDL_PollEvent.restype = _c_int
    _sdl.SDL_GetWindowSize.argtypes = [_void_p, ctypes.POINTER(_c_int), ctypes.POINTER(_c_int)]
    _sdl.SDL_GetWindowSize.restype = None
    _sdl.SDL_GetError.argtypes = []; _sdl.SDL_GetError.restype = _c_char_p
    _sdl.SDL_GetModState.argtypes = []; _sdl.SDL_GetModState.restype = _c_int
    _sdl.SDL_SetTextureBlendMode.argtypes = [_void_p, _c_int]; _sdl.SDL_SetTextureBlendMode.restype = _c_int
    _sdl.SDL_CreateRGBSurfaceWithFormat.argtypes = [_u32, _c_int, _c_int, _c_int, _u32]
    _sdl.SDL_CreateRGBSurfaceWithFormat.restype = ctypes.POINTER(SDL_Surface)
    _sdl.SDL_CreateSoftwareRenderer.argtypes = [ctypes.POINTER(SDL_Surface)]
    _sdl.SDL_CreateSoftwareRenderer.restype = _void_p
    _sdl.SDL_UpperBlit.argtypes = [_void_p, ctypes.POINTER(SDL_Rect), _void_p, ctypes.POINTER(SDL_Rect)]
    _sdl.SDL_UpperBlit.restype = _c_int
    _sdl.SDL_CreateSystemCursor.argtypes = [_c_int]; _sdl.SDL_CreateSystemCursor.restype = _void_p
    _sdl.SDL_SetCursor.argtypes = [_void_p]; _sdl.SDL_SetCursor.restype = None
    _sdl.SDL_FreeCursor.argtypes = [_void_p]; _sdl.SDL_FreeCursor.restype = None
    _img.IMG_Init.argtypes = [_c_int]; _img.IMG_Init.restype = _c_int
    _img.IMG_Quit.argtypes = []; _img.IMG_Quit.restype = None
    _img.IMG_Load.argtypes = [_c_char_p]; _img.IMG_Load.restype = _void_p
    _img.IMG_SavePNG.argtypes = [_void_p, _c_char_p]; _img.IMG_SavePNG.restype = _c_int
    # SDL_BlitSurface is a macro for SDL_UpperBlit
    _sdl_blit = _sdl.SDL_UpperBlit


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def preview_available() -> bool:
    return _HAS_SDL2


def preview_image(
    image_path: str,
    *,
    can_overwrite: bool = True,
) -> Optional[str]:
    if not _HAS_SDL2:
        print("Preview unavailable: install SDL2 + SDL2_image.", file=sys.stderr)
        return image_path
    try:
        return _CropOverlay(image_path, can_overwrite).run()
    except Exception as exc:
        print(f"Preview failed: {exc}", file=sys.stderr)
        return image_path


# ---------------------------------------------------------------------------
# Coordinate transform helper
# ---------------------------------------------------------------------------

def _transform_point_cw90(x: float, y: float, ew: float, _eh: float) -> tuple[float, float]:
    """Transform a point from old rotated space to new rotated space after CW 90°.

    Before rotation the effective size is (ew, eh).
    After CW 90° the effective size becomes (eh, ew).
    A point (x, y) maps to (eh - y, x).
    """
    return _eh - y, x


def _transform_point(
    x: float, y: float,
    ew: float, eh: float,
    steps: int,
) -> tuple[float, float]:
    """Transform a point through *steps* CW-90° rotations.

    *ew*, *eh* are the effective image size BEFORE the rotation.
    *steps* is 1..3 (already taken mod 4, 0 means no-op).
    """
    cx, cy = x, y
    cw, ch = ew, eh
    for _ in range(steps):
        cx, cy = _transform_point_cw90(cx, cy, cw, ch)
        cw, ch = ch, cw  # effective size swaps after each 90°
    return cx, cy


# ---------------------------------------------------------------------------
# Crop overlay
# ---------------------------------------------------------------------------

class _CropOverlay:
    """Fullscreen overlay: user draws a rectangle to crop, can rotate."""

    _ZOOM_STEP = 1.25
    _MIN_ZOOM = 0.1
    _MAX_ZOOM = 20.0

    def __init__(self, image_path: str, can_overwrite: bool):
        self._path = image_path
        self._can_overwrite = can_overwrite
        self._result: Optional[str] = None
        self._running = True
        self._needs_redraw = True

        # View state
        self._rot: int = 0
        self._zoom: float = 1.0
        self._ox: float = 0.0
        self._oy: float = 0.0

        # Crop selection in IMAGE coordinates (after rotation)
        self._sel_active = False
        self._has_sel = False
        self._sel_x0: float = 0.0
        self._sel_y0: float = 0.0
        self._sel_x1: float = 0.0
        self._sel_y1: float = 0.0

        # Pan state
        self._pan_active = False
        self._pan_start_x: int = 0
        self._pan_start_y: int = 0
        self._pan_ox: float = 0.0
        self._pan_oy: float = 0.0

        self._ptr_x: int = 0
        self._ptr_y: int = 0

        # --- init ---
        if _sdl.SDL_Init(SDL_INIT_VIDEO | SDL_INIT_EVENTS) != 0:
            raise RuntimeError(f"SDL_Init: {_sdl.SDL_GetError().decode()}")
        _img.IMG_Init(IMG_INIT_PNG | IMG_INIT_JPG)

        _sdl.SDL_SetHint(SDL_HINT_VIDEO_X11_NET_WM_BYPASS_COMPOSITOR, b"0")
        _sdl.SDL_SetHint(SDL_HINT_VIDEO_WAYLAND_ALLOW_LIBDECOR, b"0")
        _sdl.SDL_SetHint(SDL_HINT_VIDEO_WAYLAND_PREFER_LIBDECOR, b"0")

        self._surface = _img.IMG_Load(image_path.encode("utf-8"))
        if not self._surface:
            raise RuntimeError(f"IMG_Load: {_sdl.SDL_GetError().decode()}")
        surf = ctypes.cast(self._surface, ctypes.POINTER(SDL_Surface))
        self._img_w = surf.contents.w
        self._img_h = surf.contents.h

        dm = SDL_DisplayMode()
        _sdl.SDL_GetDesktopDisplayMode(0, ctypes.byref(dm))
        self._scr_w = dm.w if dm.w > 0 else 1920
        self._scr_h = dm.h if dm.h > 0 else 1080

        self._window = _sdl.SDL_CreateWindow(
            b"", 0, 0, self._scr_w, self._scr_h,
            (
                SDL_WINDOW_SHOWN
                | SDL_WINDOW_FULLSCREEN_DESKTOP
                | SDL_WINDOW_KEYBOARD_GRABBED
                | SDL_WINDOW_INPUT_GRABBED
                | SDL_WINDOW_SKIP_TASKBAR
            ),
        )
        if not self._window:
            raise RuntimeError(f"SDL_CreateWindow: {_sdl.SDL_GetError().decode()}")

        self._renderer = _sdl.SDL_CreateRenderer(
            self._window, -1, SDL_RENDERER_ACCELERATED | SDL_RENDERER_PRESENTVSYNC,
        )
        if not self._renderer:
            self._renderer = _sdl.SDL_CreateRenderer(
                self._window, -1, SDL_RENDERER_SOFTWARE,
            )
        if not self._renderer:
            raise RuntimeError(f"SDL_CreateRenderer: {_sdl.SDL_GetError().decode()}")

        self._texture = _sdl.SDL_CreateTextureFromSurface(self._renderer, self._surface)
        if not self._texture:
            raise RuntimeError(f"Texture: {_sdl.SDL_GetError().decode()}")
        _sdl.SDL_SetTextureBlendMode(self._texture, SDL_BLENDMODE_BLEND)

        self._cursor = _sdl.SDL_CreateSystemCursor(SDL_SYSTEM_CURSOR_CROSSHAIR)
        if self._cursor:
            _sdl.SDL_SetCursor(self._cursor)

        self._fit()

    # ── coordinate transforms ───────────────────────────────────────

    def _effective_size(self) -> tuple[float, float]:
        if (self._rot // 90) % 2 == 1:
            return float(self._img_h), float(self._img_w)
        return float(self._img_w), float(self._img_h)

    def _screen_to_image(self, sx: float, sy: float) -> tuple[float, float]:
        """Convert screen pixel to image pixel (in rotated space)."""
        ew, eh = self._effective_size()
        # Image top-left on screen
        ix = (self._scr_w - ew * self._zoom) / 2.0 + self._ox
        iy = (self._scr_h - eh * self._zoom) / 2.0 + self._oy
        # To image coords
        img_x = (sx - ix) / self._zoom
        img_y = (sy - iy) / self._zoom
        return img_x, img_y

    def _image_to_screen(self, img_x: float, img_y: float) -> tuple[float, float]:
        """Convert image pixel (rotated space) to screen pixel."""
        ew, eh = self._effective_size()
        ix = (self._scr_w - ew * self._zoom) / 2.0 + self._ox
        iy = (self._scr_h - eh * self._zoom) / 2.0 + self._oy
        return ix + img_x * self._zoom, iy + img_y * self._zoom

    def _viewport_center_in_image(self) -> tuple[float, float]:
        """Return the image-space point currently at the screen center."""
        return self._screen_to_image(self._scr_w / 2.0, self._scr_h / 2.0)

    def _center_image_point(self, img_x: float, img_y: float):
        """Adjust offsets so that (img_x, img_y) in image space sits at screen center."""
        ew, eh = self._effective_size()
        # screen center = (scr_w/2, scr_h/2)
        # image_to_screen(img_x, img_y) should equal screen center
        # ix + img_x * zoom = scr_w / 2
        # ix = (scr_w - ew * zoom) / 2 + ox
        # => ox = scr_w/2 - img_x * zoom - (scr_w - ew * zoom) / 2
        self._ox = self._scr_w / 2.0 - img_x * self._zoom - (self._scr_w - ew * self._zoom) / 2.0
        self._oy = self._scr_h / 2.0 - img_y * self._zoom - (self._scr_h - eh * self._zoom) / 2.0

    def _fit(self):
        ew, eh = self._effective_size()
        if ew > 0 and eh > 0:
            self._zoom = min(self._scr_w / ew, self._scr_h / eh)
        else:
            self._zoom = 1.0
        self._ox = 0.0
        self._oy = 0.0
        self._needs_redraw = True

    # ── render ──────────────────────────────────────────────────────

    def _render(self):
        sw, sh = self._scr_w, self._scr_h
        ew, eh = self._effective_size()

        scaled_w = ew * self._zoom
        scaled_h = eh * self._zoom
        dx = (sw - scaled_w) / 2.0 + self._ox
        dy = (sh - scaled_h) / 2.0 + self._oy

        orig_sw = self._img_w * self._zoom
        orig_sh = self._img_h * self._zoom
        cx = dx + scaled_w / 2.0
        cy = dy + scaled_h / 2.0

        src = SDL_Rect(0, 0, self._img_w, self._img_h)
        dst = SDL_FRect(
            _c_float(cx - orig_sw / 2.0), _c_float(cy - orig_sh / 2.0),
            _c_float(orig_sw), _c_float(orig_sh),
        )

        # Clear to dark
        _sdl.SDL_SetRenderDrawColor(self._renderer, 0x11, 0x11, 0x11, 0xFF)
        _sdl.SDL_RenderClear(self._renderer)

        # Draw image
        _sdl.SDL_RenderCopyExF(
            self._renderer, self._texture,
            ctypes.byref(src), ctypes.byref(dst),
            _c_double(float(self._rot % 360)), None, 0,
        )

        # Draw dark overlay outside selection (dimming)
        if self._has_sel or self._sel_active:
            self._draw_selection_overlay(sw, sh)

        _sdl.SDL_RenderPresent(self._renderer)
        self._needs_redraw = False

    def _draw_crosshair(self):
        _sdl.SDL_SetRenderDrawBlendMode(self._renderer, SDL_BLENDMODE_BLEND)
        _sdl.SDL_SetRenderDrawColor(self._renderer, 0xFF, 0xFF, 0xFF, 0x66)
        px, py = float(self._ptr_x), float(self._ptr_y)
        sw, sh = float(self._scr_w), float(self._scr_h)
        _sdl.SDL_RenderDrawLineF(self._renderer, _c_float(px), _c_float(0), _c_float(px), _c_float(sh))
        _sdl.SDL_RenderDrawLineF(self._renderer, _c_float(0), _c_float(py), _c_float(sw), _c_float(py))

    def _draw_selection_overlay(self, sw: int, sh: int):
        """Dim everything outside the selection rectangle."""
        x0, y0 = self._sel_x0, self._sel_y0
        x1, y1 = self._sel_x1, self._sel_y1

        # Clamp to image bounds
        ew, eh = self._effective_size()
        x0 = max(0, min(x0, ew))
        y0 = max(0, min(y0, eh))
        x1 = max(0, min(x1, ew))
        y1 = max(0, min(y1, eh))

        # Normalize
        if x0 > x1: x0, x1 = x1, x0
        if y0 > y1: y0, y1 = y1, y0

        # Convert to screen
        sx0, sy0 = self._image_to_screen(x0, y0)
        sx1, sy1 = self._image_to_screen(x1, y1)

        isx0, isy0 = int(sx0), int(sy0)
        isx1, isy1 = int(sx1), int(sy1)

        # Draw dark overlay on the 4 regions outside selection
        _sdl.SDL_SetRenderDrawBlendMode(self._renderer, SDL_BLENDMODE_BLEND)
        _sdl.SDL_SetRenderDrawColor(self._renderer, 0x00, 0x00, 0x00, 0x99)

        # Top
        if isy0 > 0:
            r = SDL_Rect(0, 0, sw, isy0)
            _sdl.SDL_RenderFillRect(self._renderer, ctypes.byref(r))
        # Bottom
        if isy1 < sh:
            r = SDL_Rect(0, isy1, sw, sh - isy1)
            _sdl.SDL_RenderFillRect(self._renderer, ctypes.byref(r))
        # Left
        sel_h = isy1 - isy0
        if isx0 > 0 and sel_h > 0:
            r = SDL_Rect(0, isy0, isx0, sel_h)
            _sdl.SDL_RenderFillRect(self._renderer, ctypes.byref(r))
        # Right
        if isx1 < sw and sel_h > 0:
            r = SDL_Rect(isx1, isy0, sw - isx1, sel_h)
            _sdl.SDL_RenderFillRect(self._renderer, ctypes.byref(r))

        # Selection border
        _sdl.SDL_SetRenderDrawColor(self._renderer, 0xFF, 0xFF, 0xFF, 0xFF)
        border = SDL_Rect(isx0, isy0, isx1 - isx0, isy1 - isy0)
        _sdl.SDL_RenderDrawRect(self._renderer, ctypes.byref(border))

    # ── zoom ────────────────────────────────────────────────────────

    def _zoom_at(self, factor: float, px: float, py: float):
        old = self._zoom
        new = max(self._MIN_ZOOM, min(self._MAX_ZOOM, old * factor))
        if new == old:
            return
        self._zoom = new
        s = new / old
        cx = px - self._scr_w / 2.0
        cy = py - self._scr_h / 2.0
        self._ox = cx * (1.0 - s) + self._ox * s
        self._oy = cy * (1.0 - s) + self._oy * s
        self._needs_redraw = True

    def _rotate(self, degrees: int):
        """Rotate by *degrees* (±90, ±180, …).

        Preserves the viewport center and any active selection.
        """
        steps = (degrees // 90) % 4
        if steps == 0:
            return

        old_ew, old_eh = self._effective_size()

        # 1. Remember what image point is at screen center
        vc_x, vc_y = self._viewport_center_in_image()

        # 2. Transform selection
        if self._has_sel or self._sel_active:
            self._sel_x0, self._sel_y0 = _transform_point(
                self._sel_x0, self._sel_y0, old_ew, old_eh, steps,
            )
            self._sel_x1, self._sel_y1 = _transform_point(
                self._sel_x1, self._sel_y1, old_ew, old_eh, steps,
            )
            # Normalize so x0 <= x1, y0 <= y1 (not strictly required
            # since _draw_selection_overlay and _get_crop_rect handle it,
            # but keeps the invariant clean).
            if self._sel_x0 > self._sel_x1:
                self._sel_x0, self._sel_x1 = self._sel_x1, self._sel_x0
            if self._sel_y0 > self._sel_y1:
                self._sel_y0, self._sel_y1 = self._sel_y1, self._sel_y0

        # 3. Apply rotation
        self._rot = (self._rot + degrees) % 360

        # 4. Transform viewport center to new rotated space and re-center
        new_vc_x, new_vc_y = _transform_point(vc_x, vc_y, old_ew, old_eh, steps)
        self._center_image_point(new_vc_x, new_vc_y)

        self._needs_redraw = True

    # ── crop & save ─────────────────────────────────────────────────

    def _get_crop_rect(self) -> Optional[tuple[int, int, int, int]]:
        """Return (x, y, w, h) in original image pixels, or None."""
        if not self._has_sel:
            return None

        ew, eh = self._effective_size()
        x0 = max(0.0, min(self._sel_x0, self._sel_x1))
        y0 = max(0.0, min(self._sel_y0, self._sel_y1))
        x1 = min(ew, max(self._sel_x0, self._sel_x1))
        y1 = min(eh, max(self._sel_y0, self._sel_y1))

        if x1 - x0 < 2 or y1 - y0 < 2:
            return None

        # Convert from rotated-image space to original-image space
        steps = (self._rot // 90) % 4
        ix0, iy0 = x0, y0
        ix1, iy1 = x1, y1
        ow, oh = float(self._img_w), float(self._img_h)

        if steps == 1:
            nix0 = iy0
            niy0 = ew - ix1
            nix1 = iy1
            niy1 = ew - ix0
            ix0, iy0, ix1, iy1 = nix0, niy0, nix1, niy1
        elif steps == 2:
            nix0 = ew - ix1
            niy0 = eh - iy1
            nix1 = ew - ix0
            niy1 = eh - iy0
            ix0, iy0, ix1, iy1 = nix0, niy0, nix1, niy1
        elif steps == 3:
            nix0 = eh - iy1
            niy0 = ix0
            nix1 = eh - iy0
            niy1 = ix1
            ix0, iy0, ix1, iy1 = nix0, niy0, nix1, niy1

        rx = max(0, int(ix0))
        ry = max(0, int(iy0))
        rw = min(self._img_w, int(ix1)) - rx
        rh = min(self._img_h, int(iy1)) - ry

        if rw < 2 or rh < 2:
            return None
        return rx, ry, rw, rh

    def _save_cropped(self) -> Optional[str]:
        crop = self._get_crop_rect()
        if crop is None:
            return self._path

        rx, ry, rw, rh = crop

        # Blit the crop region to a new surface
        out_surf = _sdl.SDL_CreateRGBSurfaceWithFormat(
            0, rw, rh, 32, SDL_PIXELFORMAT_RGBA8888,
        )
        if not out_surf:
            raise RuntimeError("Failed to create crop surface")

        src_rect = SDL_Rect(rx, ry, rw, rh)
        dst_rect = SDL_Rect(0, 0, rw, rh)
        _sdl_blit(self._surface, ctypes.byref(src_rect),
                  ctypes.cast(out_surf, _void_p), ctypes.byref(dst_rect))

        if self._can_overwrite:
            out_path = self._path
        else:
            fd, out_path = tempfile.mkstemp(suffix=".png")
            os.close(fd)

        if _img.IMG_SavePNG(out_surf, out_path.encode("utf-8")) != 0:
            _sdl.SDL_FreeSurface(out_surf)
            raise RuntimeError(f"IMG_SavePNG: {_sdl.SDL_GetError().decode()}")

        _sdl.SDL_FreeSurface(out_surf)
        return out_path

    # ── accept / cancel ─────────────────────────────────────────────

    def _accept(self):
        self._result = self._save_cropped()
        self._running = False

    def _cancel(self):
        self._result = None
        self._running = False

    # ── event loop ──────────────────────────────────────────────────

    def run(self) -> Optional[str]:
        ev = SDL_Event()
        while self._running:
            while _sdl.SDL_PollEvent(ctypes.byref(ev)):
                self._handle(ev)
                if not self._running:
                    break
            if self._needs_redraw and self._running:
                self._render()
        self._cleanup()
        return self._result

    def _handle(self, ev: SDL_Event):
        t = ev.type

        if t == SDL_QUIT:
            self._cancel()

        elif t == SDL_KEYDOWN:
            self._handle_key(ev.key)

        elif t == SDL_MOUSEBUTTONDOWN:
            btn = ev.button.button
            if btn == SDL_BUTTON_LEFT:
                # Start selection
                ix, iy = self._screen_to_image(ev.button.x, ev.button.y)
                self._sel_x0 = ix
                self._sel_y0 = iy
                self._sel_x1 = ix
                self._sel_y1 = iy
                self._sel_active = True
                self._has_sel = False
                self._needs_redraw = True
            elif btn == SDL_BUTTON_MIDDLE:
                self._pan_active = True
                self._pan_start_x = ev.button.x
                self._pan_start_y = ev.button.y
                self._pan_ox = self._ox
                self._pan_oy = self._oy
            elif btn == SDL_BUTTON_RIGHT:
                if self._has_sel:
                    # Clear selection
                    self._has_sel = False
                    self._sel_active = False
                    self._needs_redraw = True
                else:
                    self._cancel()

        elif t == SDL_MOUSEBUTTONUP:
            btn = ev.button.button
            if btn == SDL_BUTTON_LEFT and self._sel_active:
                self._sel_active = False
                # Check if selection is big enough
                x0, y0 = self._sel_x0, self._sel_y0
                x1, y1 = self._sel_x1, self._sel_y1
                if abs(x1 - x0) > 3 and abs(y1 - y0) > 3:
                    self._has_sel = True
                else:
                    self._has_sel = False
                self._needs_redraw = True
            elif btn == SDL_BUTTON_MIDDLE:
                self._pan_active = False

        elif t == SDL_MOUSEMOTION:
            self._ptr_x = ev.motion.x
            self._ptr_y = ev.motion.y
            if self._sel_active:
                ix, iy = self._screen_to_image(ev.motion.x, ev.motion.y)
                self._sel_x1 = ix
                self._sel_y1 = iy
                self._needs_redraw = True
            elif self._pan_active:
                self._ox = self._pan_ox + (ev.motion.x - self._pan_start_x)
                self._oy = self._pan_oy + (ev.motion.y - self._pan_start_y)
                self._needs_redraw = True

        elif t == SDL_MOUSEWHEEL:
            dy = ev.wheel.y
            if dy != 0:
                factor = self._ZOOM_STEP if dy > 0 else (1.0 / self._ZOOM_STEP)
                self._zoom_at(factor, float(self._ptr_x), float(self._ptr_y))

        elif t == SDL_WINDOWEVENT:
            self._needs_redraw = True

    def _handle_key(self, key):
        sc = key.scancode
        mod = _sdl.SDL_GetModState()
        shift = bool(mod & KMOD_SHIFT)

        if sc in (SDL_SCANCODE_RETURN, SDL_SCANCODE_KP_ENTER, SDL_SCANCODE_SPACE):
            self._accept()
        elif sc == SDL_SCANCODE_ESCAPE:
            self._cancel()
        elif sc == SDL_SCANCODE_R and not shift:
            self._rotate(90)
        elif sc == SDL_SCANCODE_R and shift:
            self._rotate(-90)
        elif sc == SDL_SCANCODE_EQUALS:
            self._zoom_at(self._ZOOM_STEP, float(self._ptr_x), float(self._ptr_y))
        elif sc == SDL_SCANCODE_MINUS:
            self._zoom_at(1.0 / self._ZOOM_STEP, float(self._ptr_x), float(self._ptr_y))
        elif sc == SDL_SCANCODE_0:
            self._has_sel = False
            self._sel_active = False
            self._fit()

    def _cleanup(self):
        if self._texture:
            _sdl.SDL_DestroyTexture(self._texture); self._texture = None
        if self._surface:
            _sdl.SDL_FreeSurface(self._surface); self._surface = None
        if self._renderer:
            _sdl.SDL_DestroyRenderer(self._renderer); self._renderer = None
        if self._window:
            _sdl.SDL_DestroyWindow(self._window); self._window = None
        _img.IMG_Quit()
        if self._cursor:
            _sdl.SDL_FreeCursor(self._cursor); self._cursor = None
        _sdl.SDL_Quit()
