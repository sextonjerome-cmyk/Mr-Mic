"""Core Audio for Mr. Mic — enumerate endpoints, read defaults, set defaults.

Uses the undocumented-but-stable IPolicyConfig COM interface (same one
SoundSwitch uses) to change the Windows default device. Never hardcode
endpoint IDs here — they live in settings.json.
"""

import threading
import warnings

# pycaw warns about two unreadable properties on ghost devices — harmless noise.
warnings.filterwarnings("ignore", category=UserWarning, module="pycaw")

import comtypes
from comtypes import COMMETHOD, GUID, HRESULT, IUnknown
from ctypes import POINTER, c_int, c_void_p
from ctypes.wintypes import BOOL, DWORD, LPCWSTR

from pycaw.constants import CLSID_MMDeviceEnumerator
from pycaw.pycaw import AudioUtilities, IMMDeviceEnumerator

# EDataFlow
RENDER, CAPTURE, ALL = 0, 1, 2
# ERole
CONSOLE, MULTIMEDIA, COMMUNICATIONS = 0, 1, 2
ALL_ROLES = (CONSOLE, MULTIMEDIA, COMMUNICATIONS)
# DEVICE_STATE_*
STATE_ACTIVE = 0x1
STATE_MASK_ALL = 0xF
STATE_NAMES = {0x1: "Active", 0x2: "Disabled", 0x4: "NotPresent", 0x8: "Unplugged"}

FLOW_NAMES = {RENDER: "output", CAPTURE: "input"}

_tls = threading.local()


def _com_init():
    """comtypes needs COM initialized once per thread (tray/hotkey callbacks
    run on their own threads)."""
    if getattr(_tls, "done", False):
        return
    try:
        comtypes.CoInitialize()
    except OSError:
        pass
    _tls.done = True


def _enumerator():
    _com_init()
    return comtypes.CoCreateInstance(
        CLSID_MMDeviceEnumerator, IMMDeviceEnumerator, comtypes.CLSCTX_INPROC_SERVER
    )


class IPolicyConfig(IUnknown):
    # Vtable order matters; only SetDefaultEndpoint is ever called, the rest
    # are typed loosely as placeholders.
    _iid_ = GUID("{f8679f50-850a-41cf-9c72-430f290290c8}")
    _methods_ = (
        COMMETHOD([], HRESULT, "GetMixFormat",
                  (["in"], LPCWSTR, "id"), (["out"], POINTER(c_void_p), "fmt")),
        COMMETHOD([], HRESULT, "GetDeviceFormat",
                  (["in"], LPCWSTR, "id"), (["in"], c_int, "default"),
                  (["out"], POINTER(c_void_p), "fmt")),
        COMMETHOD([], HRESULT, "ResetDeviceFormat", (["in"], LPCWSTR, "id")),
        COMMETHOD([], HRESULT, "SetDeviceFormat",
                  (["in"], LPCWSTR, "id"), (["in"], c_void_p, "endpoint"),
                  (["in"], c_void_p, "mix")),
        COMMETHOD([], HRESULT, "GetProcessingPeriod",
                  (["in"], LPCWSTR, "id"), (["in"], c_int, "default"),
                  (["in"], c_void_p, "def_period"), (["in"], c_void_p, "min_period")),
        COMMETHOD([], HRESULT, "SetProcessingPeriod",
                  (["in"], LPCWSTR, "id"), (["in"], c_void_p, "period")),
        COMMETHOD([], HRESULT, "GetShareMode",
                  (["in"], LPCWSTR, "id"), (["in"], c_void_p, "mode")),
        COMMETHOD([], HRESULT, "SetShareMode",
                  (["in"], LPCWSTR, "id"), (["in"], c_void_p, "mode")),
        COMMETHOD([], HRESULT, "GetPropertyValue",
                  (["in"], LPCWSTR, "id"), (["in"], BOOL, "fx"),
                  (["in"], c_void_p, "key"), (["in"], c_void_p, "value")),
        COMMETHOD([], HRESULT, "SetPropertyValue",
                  (["in"], LPCWSTR, "id"), (["in"], BOOL, "fx"),
                  (["in"], c_void_p, "key"), (["in"], c_void_p, "value")),
        COMMETHOD([], HRESULT, "SetDefaultEndpoint",
                  (["in"], LPCWSTR, "id"), (["in"], DWORD, "role")),
        COMMETHOD([], HRESULT, "SetEndpointVisibility",
                  (["in"], LPCWSTR, "id"), (["in"], BOOL, "visible")),
    )


CLSID_PolicyConfigClient = GUID("{870af99c-171d-4f9e-af0d-e63df40c2bc9}")


def list_devices(flow=ALL, mask=STATE_MASK_ALL):
    """All endpoints as dicts: {flow, id, name, state, state_name}."""
    devices = []
    enum = _enumerator()
    flows = (RENDER, CAPTURE) if flow == ALL else (flow,)
    for fl in flows:
        collection = enum.EnumAudioEndpoints(fl, mask)
        for i in range(collection.GetCount()):
            dev = collection.Item(i)
            state = dev.GetState()
            wrapped = AudioUtilities.CreateDevice(dev)
            devices.append({
                "flow": fl,
                "id": wrapped.id,
                "name": wrapped.FriendlyName,
                "state": state,
                "state_name": STATE_NAMES.get(state, hex(state)),
            })
    return devices


def get_default(flow, role=CONSOLE):
    """(id, name) of the current default device, or (None, None)."""
    try:
        enum = _enumerator()
        dev = enum.GetDefaultAudioEndpoint(flow, role)
        wrapped = AudioUtilities.CreateDevice(dev)
        return wrapped.id, wrapped.FriendlyName
    except comtypes.COMError:
        return None, None


def set_default(device_id, roles=ALL_ROLES):
    """Make device_id the Windows default for the given roles."""
    _com_init()
    policy = comtypes.CoCreateInstance(
        CLSID_PolicyConfigClient, IPolicyConfig, comtypes.CLSCTX_ALL
    )
    for role in roles:
        policy.SetDefaultEndpoint(device_id, role)


def find_device(flow, name_match, device_id=None, active_only=True):
    """Find an endpoint by exact id first, then case-insensitive name substring.
    Returns the device dict or None."""
    mask = STATE_ACTIVE if active_only else STATE_MASK_ALL
    devices = list_devices(flow, mask)
    if device_id:
        for dev in devices:
            if dev["id"] == device_id:
                return dev
    if name_match:
        needle = name_match.lower()
        for dev in devices:
            if needle in dev["name"].lower():
                return dev
    return None
