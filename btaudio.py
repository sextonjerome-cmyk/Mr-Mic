"""Connect and disconnect paired Bluetooth audio devices.

Turning the whole Bluetooth radio off works but is a sledgehammer — it drops
every other paired thing with it (Jerome has four serial-over-Bluetooth COM
ports). Disconnecting one device leaves the radio up.

Windows has no public "disconnect" call, but `BluetoothSetServiceState` on the
device's A2DP Audio Sink service does exactly that, and — usefully — needs no
administrator rights (verified 2026-08-01, both directions returned
ERROR_SUCCESS as a normal user).
"""

import ctypes
import logging
from ctypes import wintypes

log = logging.getLogger("mrmic")

_bt = ctypes.WinDLL("bthprops.cpl")

BLUETOOTH_MAX_NAME_SIZE = 248
ERROR_SUCCESS = 0
SERVICE_DISABLE, SERVICE_ENABLE = 0x00, 0x01
AUDIO_MAJOR_CLASS = 0x04  # class-of-device major: Audio/Video


class GUID(ctypes.Structure):
    _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD),
                ("Data3", wintypes.WORD), ("Data4", ctypes.c_ubyte * 8)]


def _guid(text):
    value = GUID()
    ctypes.windll.ole32.CLSIDFromString(ctypes.c_wchar_p("{" + text + "}"),
                                        ctypes.byref(value))
    return value


AUDIO_SINK = _guid("0000110B-0000-1000-8000-00805F9B34FB")


class SYSTEMTIME(ctypes.Structure):
    _fields_ = [(name, wintypes.WORD) for name in
                ("wYear", "wMonth", "wDayOfWeek", "wDay",
                 "wHour", "wMinute", "wSecond", "wMilliseconds")]


class DEVICE_INFO(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("Address", ctypes.c_ulonglong),
        ("ulClassofDevice", wintypes.ULONG),
        ("fConnected", wintypes.BOOL),
        ("fRemembered", wintypes.BOOL),
        ("fAuthenticated", wintypes.BOOL),
        ("stLastSeen", SYSTEMTIME),
        ("stLastUsed", SYSTEMTIME),
        ("szName", wintypes.WCHAR * BLUETOOTH_MAX_NAME_SIZE),
    ]


class SEARCH_PARAMS(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("fReturnAuthenticated", wintypes.BOOL),
        ("fReturnRemembered", wintypes.BOOL),
        ("fReturnUnknown", wintypes.BOOL),
        ("fReturnConnected", wintypes.BOOL),
        ("fIssueInquiry", wintypes.BOOL),
        ("cTimeoutMultiplier", ctypes.c_ubyte),
        ("hRadio", wintypes.HANDLE),
    ]


# Declare these or ctypes assumes a 32-bit int return and truncates the 64-bit
# search handle, which lands as an access violation a call later.
_bt.BluetoothFindFirstDevice.restype = wintypes.HANDLE
_bt.BluetoothFindFirstDevice.argtypes = [ctypes.POINTER(SEARCH_PARAMS),
                                         ctypes.POINTER(DEVICE_INFO)]
_bt.BluetoothFindNextDevice.restype = wintypes.BOOL
_bt.BluetoothFindNextDevice.argtypes = [wintypes.HANDLE, ctypes.POINTER(DEVICE_INFO)]
_bt.BluetoothFindDeviceClose.restype = wintypes.BOOL
_bt.BluetoothFindDeviceClose.argtypes = [wintypes.HANDLE]
_bt.BluetoothSetServiceState.restype = wintypes.DWORD
_bt.BluetoothSetServiceState.argtypes = [wintypes.HANDLE, ctypes.POINTER(DEVICE_INFO),
                                         ctypes.POINTER(GUID), wintypes.DWORD]


def _search_params():
    params = SEARCH_PARAMS()
    params.dwSize = ctypes.sizeof(params)
    params.fReturnAuthenticated = True
    params.fReturnRemembered = True
    params.fReturnUnknown = False
    params.fReturnConnected = True
    params.fIssueInquiry = False   # no radio scan — this must stay quick
    params.cTimeoutMultiplier = 2
    params.hRadio = None
    return params


def paired(audio_only=True):
    """Paired devices as [{name, connected, info}], newest API state each call."""
    found = []
    info = DEVICE_INFO()
    info.dwSize = ctypes.sizeof(info)
    try:
        handle = _bt.BluetoothFindFirstDevice(ctypes.byref(_search_params()),
                                              ctypes.byref(info))
    except OSError:
        log.exception("bluetooth: enumeration failed")
        return found
    if not handle:
        return found
    try:
        while True:
            major = (info.ulClassofDevice >> 8) & 0x1F
            if not audio_only or major == AUDIO_MAJOR_CLASS:
                found.append({
                    "name": info.szName,
                    "connected": bool(info.fConnected),
                    "info": DEVICE_INFO.from_buffer_copy(info),
                })
            nxt = DEVICE_INFO()
            nxt.dwSize = ctypes.sizeof(nxt)
            if not _bt.BluetoothFindNextDevice(handle, ctypes.byref(nxt)):
                break
            info = nxt
    finally:
        _bt.BluetoothFindDeviceClose(handle)
    return found


def set_connected(device, connected):
    """Connect or disconnect one device (a dict from paired()).
    Returns True on success. Takes a second or two — keep it off the UI thread."""
    try:
        rc = _bt.BluetoothSetServiceState(
            None, ctypes.byref(device["info"]), ctypes.byref(AUDIO_SINK),
            SERVICE_ENABLE if connected else SERVICE_DISABLE)
    except OSError:
        log.exception("bluetooth: set state failed for %s", device.get("name"))
        return False
    if rc != ERROR_SUCCESS:
        log.warning("bluetooth: %s %s -> error %s", device.get("name"),
                    "connect" if connected else "disconnect", rc)
    else:
        log.info("bluetooth: %s %s", device.get("name"),
                 "connected" if connected else "disconnected")
    return rc == ERROR_SUCCESS


if __name__ == "__main__":
    for dev in paired():
        print(f"  {'CONNECTED' if dev['connected'] else 'idle     '}  {dev['name']}")
