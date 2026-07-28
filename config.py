"""Settings for Mr. Mic — defaults here, user values in settings.json.

Devices are a LIST, not a fixed pair. Order is priority: when the active
device disappears, Mr. Mic falls back to the first available one below it.
Each entry:

  key            stable id, used in logs and settings (never shown)
  label          what you see in the tray menu
  icon           headset | earbuds | bluetooth | speaker  (tray glyph)
  output_match   name substring of the speaker endpoint ("" = leave alone)
  input_match    name substring of the mic endpoint      ("" = leave alone)
  output_id/input_id  exact endpoint ids, filled in once matched (survives
                 renames; cleared automatically if the id goes stale)
  enabled        False hides it from the menu and auto-switching
  auto           take over automatically when it turns on / gets plugged in
  detect         "endpoint" (default — is it Active in Windows?) or
                 "battery" (HyperX dongle: the endpoint never changes, so
                 a battery reply is the only on/off signal)
"""

import json
import os
import sys

if getattr(sys, "frozen", False):  # PyInstaller exe — live next to the exe
    APP_DIR = os.path.dirname(sys.executable)
else:
    APP_DIR = os.path.dirname(os.path.abspath(__file__))
SETTINGS_PATH = os.path.join(APP_DIR, "settings.json")
LOG_PATH = os.path.join(APP_DIR, "mrmic.log")

ICONS = ("headset", "earbuds", "bluetooth", "speaker")

DEVICE_DEFAULTS = {
    "key": "device",
    "label": "Device",
    "icon": "speaker",
    "output_match": "",
    "output_id": None,
    "input_match": "",
    "input_id": None,
    "enabled": True,
    "auto": True,
    "detect": "endpoint",
}

DEFAULTS = {
    "hotkey": "ctrl+alt+h",
    "mute_hotkey": "",
    "mic_mute_hotkey": "",
    "_hotkey_examples": "ctrl+alt+h | pause | v+c (two keys pressed together) | shift+ctrl+p",
    "notifications": False,
    "chime": True,
    "autodetect": True,
    "poll_seconds": 2,
    "battery_warn": 20,
    "aliases": {
        "HyperX": "HyperX",
        "Speakers (Realtek": "Laptop speakers",
        "Headphones (Realtek": "Earphones",
        "Microphone (Realtek": "Earphone mic",
        "Microphone Array": "Laptop mic",
        "Hesh ANC": "Hesh ANC",
        "USB2.0": "ButtKicker",
        "Virtual Desktop": "Virtual Desktop",
    },
    "devices": [
        {
            "key": "headset", "label": "HyperX Headset", "icon": "headset",
            "output_match": "HyperX", "output_id": None,
            "input_match": "HyperX", "input_id": None,
            "enabled": True, "auto": True, "detect": "battery",
        },
        {
            "key": "earphones", "label": "Earphones (jack)", "icon": "earbuds",
            "output_match": "Headphones (Realtek", "output_id": None,
            "input_match": "Microphone (Realtek", "input_id": None,
            "enabled": True, "auto": True, "detect": "endpoint",
        },
        {
            # Bluetooth: point output at the "Headphones (…)" endpoint (A2DP,
            # good sound) and leave the mic alone. Selecting the "Headset (…)"
            # mic flips the link to hands-free mode and the music turns to mush.
            "key": "hesh", "label": "Skullcandy Hesh ANC", "icon": "bluetooth",
            "output_match": "Headphones (Hesh ANC", "output_id": None,
            "input_match": "", "input_id": None,
            "enabled": True, "auto": True, "detect": "endpoint",
        },
        {
            "key": "laptop", "label": "Laptop speakers", "icon": "speaker",
            "output_match": "Speakers (Realtek", "output_id": None,
            "input_match": "Microphone Array", "input_id": None,
            "enabled": True, "auto": True, "detect": "endpoint",
        },
    ],
}

# Keys that never belong in settings.json (comments, computed values)
_SKIP_ON_SAVE = ()


def normalize_device(dev):
    """Fill in any missing device fields so the rest of the app can assume
    they exist."""
    out = dict(DEVICE_DEFAULTS)
    out.update({k: v for k, v in dev.items() if k in DEVICE_DEFAULTS})
    out["icon"] = out["icon"] if out["icon"] in ICONS else "speaker"
    out["detect"] = "battery" if out.get("detect") == "battery" else "endpoint"
    return out


def _from_old_profiles(profiles):
    """settings.json written before the device list existed had a
    {"headset": {...}, "laptop": {...}} dict. Carry it forward."""
    known = {
        "headset": ("HyperX Headset", "headset", "battery"),
        "laptop": ("Laptop speakers", "speaker", "endpoint"),
    }
    devices = []
    for key, prof in profiles.items():
        label, icon, detect = known.get(key, (key.title(), "speaker", "endpoint"))
        devices.append(normalize_device({
            "key": key, "label": label, "icon": icon, "detect": detect,
            "output_match": prof.get("output_match") or "",
            "output_id": prof.get("output_id"),
            "input_match": prof.get("input_match") or "",
            "input_id": prof.get("input_id"),
        }))
    # laptop is the fallback — keep it last
    devices.sort(key=lambda d: d["key"] == "laptop")
    return devices


def _merge_defaults(devices):
    """Add any default device the user's file doesn't have yet (so an old
    settings.json gains Earphones and the Hesh without losing its ids)."""
    have = {d["key"] for d in devices}
    fallback = [d for d in devices if d["key"] == "laptop"]
    for default in DEFAULTS["devices"]:
        if default["key"] in have or default["key"] == "laptop":
            continue
        at = devices.index(fallback[0]) if fallback else len(devices)
        devices.insert(at, normalize_device(default))
    return devices


def load():
    cfg = json.loads(json.dumps(DEFAULTS))  # deep copy
    try:
        with open(SETTINGS_PATH, encoding="utf-8") as f:
            user = json.load(f)
    except (OSError, ValueError):
        return cfg

    devices = None
    for key, value in user.items():
        if key == "devices" and isinstance(value, list):
            devices = [normalize_device(d) for d in value if isinstance(d, dict)]
        elif key == "profiles" and isinstance(value, dict):
            if devices is None:
                devices = _merge_defaults(_from_old_profiles(value))
        elif key == "aliases" and isinstance(value, dict):
            # merge, don't replace — an older file otherwise loses the names
            # for devices added since it was written
            cfg["aliases"].update(value)
        else:
            cfg[key] = value
    if devices:
        cfg["devices"] = devices
    return cfg


def save(cfg):
    out = {k: v for k, v in cfg.items() if k not in _SKIP_ON_SAVE}
    with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
        f.write("\n")
