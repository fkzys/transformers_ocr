# Copyright: fkzys and contributors
# License: GNU GPL, version 3 or later; http://www.gnu.org/licenses/gpl.html

"""Native fullscreen capture via ctypes — no external tools required.

X11:     Xlib XGetImage
Wayland: xdg-desktop-portal Screenshot (D-Bus via libdbus-1)

Falls back to external tools (grim/maim) if native capture fails.
"""

import ctypes
import ctypes.util
import os
import random
import shutil
import string as string_mod
import sys
import time


# ---------------------------------------------------------------------------
# SDL2 library loading (shared with preview.py)
# ---------------------------------------------------------------------------

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


def _load_sdl2():
    lib = _load_lib(("SDL2", "SDL2-2.0"))
    if lib is not None:
        lib.SDL_FreeSurface.argtypes = [ctypes.c_void_p]
        lib.SDL_FreeSurface.restype = None
    return lib


def _load_sdl2_image():
    return _load_lib(("SDL2_image", "SDL2_image-2.0"))


# ---------------------------------------------------------------------------
# Wayland detection
# ---------------------------------------------------------------------------

def _is_wayland() -> bool:
    return "WAYLAND_DISPLAY" in os.environ


# ---------------------------------------------------------------------------
# X11 capture via Xlib
# ---------------------------------------------------------------------------

class _XImage(ctypes.Structure):
    """XImage structure — only the fields we need."""
    _fields_ = [
        ("width", ctypes.c_int),
        ("height", ctypes.c_int),
        ("xoffset", ctypes.c_int),
        ("format", ctypes.c_int),
        ("data", ctypes.c_char_p),
        ("byte_order", ctypes.c_int),
        ("bitmap_unit", ctypes.c_int),
        ("bitmap_bit_order", ctypes.c_int),
        ("bitmap_pad", ctypes.c_int),
        ("depth", ctypes.c_int),
        ("bytes_per_line", ctypes.c_int),
        ("bits_per_pixel", ctypes.c_int),
        ("red_mask", ctypes.c_ulong),
        ("green_mask", ctypes.c_ulong),
        ("blue_mask", ctypes.c_ulong),
    ]


def _grab_x11(output_path: str) -> bool:
    """Capture the full X11 root window and save as PNG via SDL2_image.

    Uses SDL_CreateRGBSurfaceFrom for zero-copy pixel access.
    Returns True on success, False if libraries are unavailable.
    """
    xlib_name = ctypes.util.find_library("X11")
    if not xlib_name:
        return False
    try:
        xlib = ctypes.CDLL(xlib_name)
    except OSError:
        return False

    sdl = _load_sdl2()
    sdl_img = _load_sdl2_image()
    if sdl is None or sdl_img is None:
        return False

    c_ulong = ctypes.c_ulong
    c_int = ctypes.c_int
    c_uint = ctypes.c_uint
    c_void_p = ctypes.c_void_p
    c_char_p = ctypes.c_char_p
    c_uint32 = ctypes.c_uint32

    xlib.XOpenDisplay.argtypes = [c_char_p]
    xlib.XOpenDisplay.restype = c_void_p
    xlib.XDefaultRootWindow.argtypes = [c_void_p]
    xlib.XDefaultRootWindow.restype = c_ulong
    xlib.XGetGeometry.argtypes = [
        c_void_p, c_ulong,
        ctypes.POINTER(c_ulong),
        ctypes.POINTER(c_int), ctypes.POINTER(c_int),
        ctypes.POINTER(c_uint), ctypes.POINTER(c_uint),
        ctypes.POINTER(c_uint), ctypes.POINTER(c_uint),
    ]
    xlib.XGetGeometry.restype = c_int
    xlib.XGetImage.argtypes = [
        c_void_p, c_ulong,
        c_int, c_int, c_uint, c_uint,
        c_ulong, c_int,
    ]
    xlib.XGetImage.restype = c_void_p
    xlib.XDestroyImage.argtypes = [c_void_p]
    xlib.XDestroyImage.restype = c_int
    xlib.XCloseDisplay.argtypes = [c_void_p]
    xlib.XCloseDisplay.restype = c_int

    display = xlib.XOpenDisplay(None)
    if not display:
        return False

    try:
        root = xlib.XDefaultRootWindow(display)

        root_ret = c_ulong()
        x_ret, y_ret = c_int(), c_int()
        w_ret, h_ret = c_uint(), c_uint()
        bw_ret, depth_ret = c_uint(), c_uint()

        xlib.XGetGeometry(
            display, root, ctypes.byref(root_ret),
            ctypes.byref(x_ret), ctypes.byref(y_ret),
            ctypes.byref(w_ret), ctypes.byref(h_ret),
            ctypes.byref(bw_ret), ctypes.byref(depth_ret),
        )

        width = w_ret.value
        height = h_ret.value
        if width == 0 or height == 0:
            return False

        ZPixmap = 2
        AllPlanes = 0xFFFFFFFF
        ximage = xlib.XGetImage(
            display, root, 0, 0, width, height, AllPlanes, ZPixmap,
        )
        if not ximage:
            return False

        try:
            ximg = ctypes.cast(ximage, ctypes.POINTER(_XImage)).contents
            bpp = ximg.bits_per_pixel
            stride = ximg.bytes_per_line
            data_ptr = ximg.data

            if bpp != 32 or not data_ptr:
                print(f"screengrab: unsupported bpp={bpp}", file=sys.stderr)
                return False

            # Zero-copy: create SDL surface directly from XImage data.
            # X11 32-bit ZPixmap is typically BGRx on little-endian.
            sdl.SDL_CreateRGBSurfaceFrom.argtypes = [
                c_void_p, c_int, c_int, c_int, c_int,
                c_uint32, c_uint32, c_uint32, c_uint32,
            ]
            sdl.SDL_CreateRGBSurfaceFrom.restype = c_void_p

            surf = sdl.SDL_CreateRGBSurfaceFrom(
                data_ptr, width, height, bpp, stride,
                0x00FF0000,  # R mask
                0x0000FF00,  # G mask
                0x000000FF,  # B mask
                0x00000000,  # A mask (X11 has no alpha)
            )
            if not surf:
                return False

            try:
                sdl_img.IMG_SavePNG.argtypes = [c_void_p, c_char_p]
                sdl_img.IMG_SavePNG.restype = c_int
                rc = sdl_img.IMG_SavePNG(surf, output_path.encode("utf-8"))
                return rc == 0
            finally:
                sdl.SDL_FreeSurface(surf)
        finally:
            xlib.XDestroyImage(ximage)
    finally:
        xlib.XCloseDisplay(display)


# ---------------------------------------------------------------------------
# Wayland capture via xdg-desktop-portal (D-Bus / libdbus-1)
# ---------------------------------------------------------------------------

class _DBusError(ctypes.Structure):
    _fields_ = [
        ("name", ctypes.c_char_p),
        ("message", ctypes.c_char_p),
        ("dummy1", ctypes.c_uint),
        ("dummy2", ctypes.c_void_p),
        ("dummy3", ctypes.c_void_p),
        ("dummy4", ctypes.c_void_p),
        ("dummy5", ctypes.c_void_p),
        ("padding1", ctypes.c_void_p),
    ]


# libdbus DBusMessageIter is opaque; 14 pointers is generous.
_ITER_BYTES = 14 * ctypes.sizeof(ctypes.c_void_p)

# D-Bus type codes
_DBUS_BUS_SESSION = 0
_T_STRING = ord("s")
_T_ARRAY = ord("a")
_T_VARIANT = ord("v")
_T_BOOLEAN = ord("b")
_T_UINT32 = ord("u")
_T_DICT_ENTRY = ord("e")
_T_INVALID = 0


def _setup_dbus_functions(dbus):
    """Declare argtypes/restype for every libdbus function we call."""
    P = ctypes.c_void_p
    CP = ctypes.c_char_p
    I = ctypes.c_int
    B = ctypes.c_bool
    EP = ctypes.POINTER(_DBusError)

    dbus.dbus_error_init.argtypes = [EP]
    dbus.dbus_error_init.restype = None
    dbus.dbus_error_is_set.argtypes = [EP]
    dbus.dbus_error_is_set.restype = B
    dbus.dbus_error_free.argtypes = [EP]
    dbus.dbus_error_free.restype = None

    dbus.dbus_bus_get.argtypes = [I, EP]
    dbus.dbus_bus_get.restype = P
    dbus.dbus_bus_get_unique_name.argtypes = [P]
    dbus.dbus_bus_get_unique_name.restype = CP
    dbus.dbus_bus_add_match.argtypes = [P, CP, EP]
    dbus.dbus_bus_add_match.restype = None
    dbus.dbus_bus_remove_match.argtypes = [P, CP, EP]
    dbus.dbus_bus_remove_match.restype = None

    dbus.dbus_connection_send_with_reply_and_block.argtypes = [P, P, I, EP]
    dbus.dbus_connection_send_with_reply_and_block.restype = P
    dbus.dbus_connection_read_write_dispatch.argtypes = [P, I]
    dbus.dbus_connection_read_write_dispatch.restype = B
    dbus.dbus_connection_pop_message.argtypes = [P]
    dbus.dbus_connection_pop_message.restype = P

    dbus.dbus_message_new_method_call.argtypes = [CP, CP, CP, CP]
    dbus.dbus_message_new_method_call.restype = P
    dbus.dbus_message_unref.argtypes = [P]
    dbus.dbus_message_unref.restype = None
    dbus.dbus_message_get_path.argtypes = [P]
    dbus.dbus_message_get_path.restype = CP
    dbus.dbus_message_is_signal.argtypes = [P, CP, CP]
    dbus.dbus_message_is_signal.restype = B

    dbus.dbus_message_iter_init.argtypes = [P, P]
    dbus.dbus_message_iter_init.restype = B
    dbus.dbus_message_iter_get_arg_type.argtypes = [P]
    dbus.dbus_message_iter_get_arg_type.restype = I
    dbus.dbus_message_iter_get_basic.argtypes = [P, P]
    dbus.dbus_message_iter_get_basic.restype = None
    dbus.dbus_message_iter_next.argtypes = [P]
    dbus.dbus_message_iter_next.restype = B
    dbus.dbus_message_iter_recurse.argtypes = [P, P]
    dbus.dbus_message_iter_recurse.restype = None

    dbus.dbus_message_iter_init_append.argtypes = [P, P]
    dbus.dbus_message_iter_init_append.restype = None
    dbus.dbus_message_iter_append_basic.argtypes = [P, I, P]
    dbus.dbus_message_iter_append_basic.restype = B
    dbus.dbus_message_iter_open_container.argtypes = [P, I, CP, P]
    dbus.dbus_message_iter_open_container.restype = B
    dbus.dbus_message_iter_close_container.argtypes = [P, P]
    dbus.dbus_message_iter_close_container.restype = B


def _make_iter():
    return ctypes.create_string_buffer(_ITER_BYTES)


def _append_dict_entry_sv_string(dbus, dict_iter, key: bytes, value: bytes):
    """Append a single {sv} entry where v contains a string."""
    entry = _make_iter()
    # DICT_ENTRY container — signature must be None
    dbus.dbus_message_iter_open_container(
        dict_iter, _T_DICT_ENTRY, None, entry,
    )

    k = ctypes.c_char_p(key)
    dbus.dbus_message_iter_append_basic(entry, _T_STRING, ctypes.byref(k))

    variant = _make_iter()
    dbus.dbus_message_iter_open_container(entry, _T_VARIANT, b"s", variant)
    v = ctypes.c_char_p(value)
    dbus.dbus_message_iter_append_basic(variant, _T_STRING, ctypes.byref(v))
    dbus.dbus_message_iter_close_container(entry, variant)

    dbus.dbus_message_iter_close_container(dict_iter, entry)


def _append_dict_entry_sv_bool(dbus, dict_iter, key: bytes, value: bool):
    """Append a single {sv} entry where v contains a boolean."""
    entry = _make_iter()
    dbus.dbus_message_iter_open_container(
        dict_iter, _T_DICT_ENTRY, None, entry,
    )

    k = ctypes.c_char_p(key)
    dbus.dbus_message_iter_append_basic(entry, _T_STRING, ctypes.byref(k))

    variant = _make_iter()
    dbus.dbus_message_iter_open_container(entry, _T_VARIANT, b"b", variant)
    bval = ctypes.c_uint32(1 if value else 0)
    dbus.dbus_message_iter_append_basic(variant, _T_BOOLEAN, ctypes.byref(bval))
    dbus.dbus_message_iter_close_container(entry, variant)

    dbus.dbus_message_iter_close_container(dict_iter, entry)


def _build_screenshot_message(dbus, token: str):
    """Build the Screenshot D-Bus method-call message."""
    msg = dbus.dbus_message_new_method_call(
        b"org.freedesktop.portal.Desktop",
        b"/org/freedesktop/portal/desktop",
        b"org.freedesktop.portal.Screenshot",
        b"Screenshot",
    )
    if not msg:
        return None

    it = _make_iter()
    dbus.dbus_message_iter_init_append(msg, it)

    # arg 1: parent_window (string, empty)
    empty = ctypes.c_char_p(b"")
    dbus.dbus_message_iter_append_basic(it, _T_STRING, ctypes.byref(empty))

    # arg 2: options a{sv}
    dict_iter = _make_iter()
    dbus.dbus_message_iter_open_container(it, _T_ARRAY, b"{sv}", dict_iter)

    _append_dict_entry_sv_string(dbus, dict_iter, b"handle_token", token.encode())
    _append_dict_entry_sv_bool(dbus, dict_iter, b"interactive", False)

    dbus.dbus_message_iter_close_container(it, dict_iter)

    return msg


def _parse_response_uri(dbus, signal) -> str | None:
    """Extract the "uri" from a portal Response signal. Returns None on failure."""
    it = _make_iter()
    if not dbus.dbus_message_iter_init(signal, it):
        return None

    # arg 1: uint32 response_code
    if dbus.dbus_message_iter_get_arg_type(it) != _T_UINT32:
        return None
    code = ctypes.c_uint32()
    dbus.dbus_message_iter_get_basic(it, ctypes.byref(code))
    if code.value != 0:
        print(f"screengrab: portal denied (code={code.value})", file=sys.stderr)
        return None

    if not dbus.dbus_message_iter_next(it):
        return None

    # arg 2: a{sv}
    if dbus.dbus_message_iter_get_arg_type(it) != _T_ARRAY:
        return None

    dict_it = _make_iter()
    dbus.dbus_message_iter_recurse(it, dict_it)

    while dbus.dbus_message_iter_get_arg_type(dict_it) != _T_INVALID:
        entry_it = _make_iter()
        dbus.dbus_message_iter_recurse(dict_it, entry_it)

        if dbus.dbus_message_iter_get_arg_type(entry_it) == _T_STRING:
            key_ptr = ctypes.c_char_p()
            dbus.dbus_message_iter_get_basic(entry_it, ctypes.byref(key_ptr))
            key = key_ptr.value.decode() if key_ptr.value else ""

            if key == "uri" and dbus.dbus_message_iter_next(entry_it):
                if dbus.dbus_message_iter_get_arg_type(entry_it) == _T_VARIANT:
                    var_it = _make_iter()
                    dbus.dbus_message_iter_recurse(entry_it, var_it)
                    if dbus.dbus_message_iter_get_arg_type(var_it) == _T_STRING:
                        uri_ptr = ctypes.c_char_p()
                        dbus.dbus_message_iter_get_basic(var_it, ctypes.byref(uri_ptr))
                        if uri_ptr.value:
                            return uri_ptr.value.decode()

        dbus.dbus_message_iter_next(dict_it)

    return None


def _grab_wayland_portal(output_path: str) -> bool:
    """Capture via xdg-desktop-portal Screenshot interface.

    Uses libdbus-1 directly through ctypes.
    Returns True on success, False on failure.
    """
    dbus_name = ctypes.util.find_library("dbus-1")
    if not dbus_name:
        return False
    try:
        dbus = ctypes.CDLL(dbus_name)
    except OSError:
        return False

    _setup_dbus_functions(dbus)

    err = _DBusError()
    dbus.dbus_error_init(ctypes.byref(err))

    conn = dbus.dbus_bus_get(_DBUS_BUS_SESSION, ctypes.byref(err))
    if not conn or dbus.dbus_error_is_set(ctypes.byref(err)):
        dbus.dbus_error_free(ctypes.byref(err))
        return False

    try:
        unique = dbus.dbus_bus_get_unique_name(conn)
        if not unique:
            return False
        sender = unique.decode().replace(".", "_").lstrip(":")

        token = "trocr_" + "".join(
            random.choices(string_mod.ascii_lowercase + string_mod.digits, k=8)
        )
        request_path = (
            f"/org/freedesktop/portal/desktop/request/{sender}/{token}"
        )

        # Subscribe to the Response signal BEFORE sending the request.
        match_rule = (
            f"type='signal',"
            f"interface='org.freedesktop.portal.Request',"
            f"member='Response',"
            f"path='{request_path}'"
        ).encode()

        dbus.dbus_bus_add_match(conn, match_rule, ctypes.byref(err))
        if dbus.dbus_error_is_set(ctypes.byref(err)):
            return False

        try:
            msg = _build_screenshot_message(dbus, token)
            if not msg:
                return False

            try:
                reply = dbus.dbus_connection_send_with_reply_and_block(
                    conn, msg, 5000, ctypes.byref(err),
                )
                if reply:
                    dbus.dbus_message_unref(reply)
                if dbus.dbus_error_is_set(ctypes.byref(err)):
                    err_msg = err.message.decode() if err.message else "unknown"
                    print(f"screengrab: D-Bus call failed: {err_msg}", file=sys.stderr)
                    return False
            finally:
                dbus.dbus_message_unref(msg)

            # Poll for the Response signal (up to 30 s).
            deadline = time.monotonic() + 30.0
            req_path_bytes = request_path.encode()
            while time.monotonic() < deadline:
                dbus.dbus_connection_read_write_dispatch(conn, 200)
                while True:
                    sig = dbus.dbus_connection_pop_message(conn)
                    if not sig:
                        break
                    try:
                        if not dbus.dbus_message_is_signal(
                            sig,
                            b"org.freedesktop.portal.Request",
                            b"Response",
                        ):
                            continue
                        path = dbus.dbus_message_get_path(sig)
                        if path and path == req_path_bytes:
                            uri = _parse_response_uri(dbus, sig)
                            if not uri:
                                return False
                            return _save_portal_file(uri, output_path)
                    finally:
                        dbus.dbus_message_unref(sig)

            print("screengrab: portal timeout", file=sys.stderr)
            return False

        finally:
            dbus.dbus_bus_remove_match(conn, match_rule, ctypes.byref(err))

    finally:
        dbus.dbus_error_free(ctypes.byref(err))


def _save_portal_file(uri: str, output_path: str) -> bool:
    """Move the portal's temporary screenshot file to output_path."""
    file_path = uri.removeprefix("file://")
    try:
        shutil.move(file_path, output_path)
        return True
    except OSError:
        pass
    try:
        shutil.copy2(file_path, output_path)
        os.unlink(file_path)
        return True
    except OSError as e:
        print(f"screengrab: failed to save: {e}", file=sys.stderr)
        return False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def grab_fullscreen(output_path: str) -> bool:
    """Capture the entire screen and save as PNG.

    Returns True on success, False if native capture is unavailable.
    """
    if _is_wayland():
        if _grab_wayland_portal(output_path):
            return True
        print("screengrab: portal failed on Wayland", file=sys.stderr)
        return False
    else:
        if _grab_x11(output_path):
            return True
        print("screengrab: X11 grab failed", file=sys.stderr)
        return False
