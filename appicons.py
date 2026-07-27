"""Extract app icons from exe files for the mixer flyout (pure ctypes, no pywin32)."""

import ctypes
import logging
from ctypes import wintypes

from PIL import Image

log = logging.getLogger("mrmic")

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
shell32 = ctypes.windll.shell32


class ICONINFO(ctypes.Structure):
    _fields_ = [
        ("fIcon", wintypes.BOOL),
        ("xHotspot", wintypes.DWORD),
        ("yHotspot", wintypes.DWORD),
        ("hbmMask", wintypes.HBITMAP),
        ("hbmColor", wintypes.HBITMAP),
    ]


class BITMAP(ctypes.Structure):
    _fields_ = [
        ("bmType", wintypes.LONG),
        ("bmWidth", wintypes.LONG),
        ("bmHeight", wintypes.LONG),
        ("bmWidthBytes", wintypes.LONG),
        ("bmPlanes", wintypes.WORD),
        ("bmBitsPixel", wintypes.WORD),
        ("bmBits", ctypes.c_void_p),
    ]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", wintypes.LONG),
        ("biHeight", wintypes.LONG),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wintypes.DWORD * 3)]


class SHFILEINFO(ctypes.Structure):
    _fields_ = [
        ("hIcon", wintypes.HICON),
        ("iIcon", ctypes.c_int),
        ("dwAttributes", wintypes.DWORD),
        ("szDisplayName", ctypes.c_wchar * 260),
        ("szTypeName", ctypes.c_wchar * 80),
    ]


# Without explicit argtypes, 64-bit handles get truncated to c_int and the
# GDI calls fail at random. Declare everything we touch.
user32.GetIconInfo.argtypes = [wintypes.HICON, ctypes.POINTER(ICONINFO)]
user32.DestroyIcon.argtypes = [wintypes.HICON]
user32.GetDC.argtypes = [wintypes.HWND]
user32.GetDC.restype = wintypes.HDC
user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
gdi32.GetObjectW.argtypes = [wintypes.HGDIOBJ, ctypes.c_int, ctypes.c_void_p]
gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
gdi32.GetDIBits.argtypes = [
    wintypes.HDC, wintypes.HBITMAP, wintypes.UINT, wintypes.UINT,
    ctypes.c_void_p, ctypes.POINTER(BITMAPINFO), wintypes.UINT,
]
shell32.ExtractIconExW.argtypes = [
    wintypes.LPCWSTR, ctypes.c_int,
    ctypes.POINTER(wintypes.HICON), ctypes.POINTER(wintypes.HICON), wintypes.UINT,
]
shell32.SHGetFileInfoW.argtypes = [
    wintypes.LPCWSTR, wintypes.DWORD, ctypes.POINTER(SHFILEINFO),
    wintypes.UINT, wintypes.UINT,
]
SHGFI_ICON = 0x100


def _hicon_to_image(hicon):
    info = ICONINFO()
    if not user32.GetIconInfo(hicon, ctypes.byref(info)):
        return None
    try:
        bmp = BITMAP()
        if not gdi32.GetObjectW(info.hbmColor, ctypes.sizeof(BITMAP), ctypes.byref(bmp)):
            return None
        w, h = bmp.bmWidth, bmp.bmHeight
        bmi = BITMAPINFO()
        bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bmi.bmiHeader.biWidth = w
        bmi.bmiHeader.biHeight = -h  # top-down
        bmi.bmiHeader.biPlanes = 1
        bmi.bmiHeader.biBitCount = 32
        buf = (ctypes.c_char * (w * h * 4))()
        hdc = user32.GetDC(0)
        try:
            if not gdi32.GetDIBits(hdc, info.hbmColor, 0, h, buf, ctypes.byref(bmi), 0):
                return None
        finally:
            user32.ReleaseDC(0, hdc)
        img = Image.frombuffer("RGBA", (w, h), bytes(buf), "raw", "BGRA", 0, 1)
        if img.getextrema()[3] == (0, 0):  # no alpha channel — icon uses the mask
            img.putalpha(255)
        return img
    finally:
        gdi32.DeleteObject(info.hbmColor)
        gdi32.DeleteObject(info.hbmMask)


def _extract_hicon(exe_path):
    large = wintypes.HICON()
    count = shell32.ExtractIconExW(exe_path, 0, ctypes.byref(large), None, 1)
    if count >= 1 and large.value:
        return large.value
    # Store apps keep icons outside the exe — ask the shell instead
    sfi = SHFILEINFO()
    if shell32.SHGetFileInfoW(exe_path, 0, ctypes.byref(sfi), ctypes.sizeof(sfi), SHGFI_ICON):
        return sfi.hIcon or None
    return None


def exe_icon(exe_path, size=18):
    """PIL image of the exe's icon at `size` px, or None."""
    if not exe_path:
        return None
    try:
        hicon = _extract_hicon(exe_path)
        if not hicon:
            return None
        try:
            img = _hicon_to_image(hicon)
        finally:
            user32.DestroyIcon(hicon)
        if img is None:
            return None
        return img.resize((size, size), Image.LANCZOS)
    except Exception:
        log.debug("icon extraction failed for %s", exe_path, exc_info=True)
        return None
