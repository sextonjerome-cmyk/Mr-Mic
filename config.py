"""Settings for Mr. Mic — defaults here, user values in settings.json."""

import json
import os
import sys

if getattr(sys, "frozen", False):  # PyInstaller exe — live next to the exe
    APP_DIR = os.path.dirname(sys.executable)
else:
    APP_DIR = os.path.dirname(os.path.abspath(__file__))
SETTINGS_PATH = os.path.join(APP_DIR, "settings.json")
LOG_PATH = os.path.join(APP_DIR, "mrmic.log")

DEFAULTS = {
    "hotkey": "ctrl+alt+h",
    "_hotkey_examples": "ctrl+alt+h | pause | v+c (two keys pressed together) | shift+ctrl+p",
    "notifications": False,
    "chime": True,
    "autodetect": True,
    "poll_seconds": 2,
    "battery_warn": 20,
    "aliases": {
        "HyperX": "HyperX",
        "Speakers (Realtek": "Laptop speakers",
        "Realtek": "Laptop",
        "Microphone Array": "Laptop mic",
        "USB2.0": "ButtKicker",
        "Virtual Desktop": "Virtual Desktop",
    },
    "profiles": {
        "headset": {
            "output_match": "HyperX", "output_id": None,
            "input_match": "HyperX", "input_id": None,
        },
        "laptop": {
            "output_match": "Speakers (Realtek", "output_id": None,
            "input_match": "Microphone Array", "input_id": None,
        },
    },
}


def load():
    cfg = json.loads(json.dumps(DEFAULTS))  # deep copy
    try:
        with open(SETTINGS_PATH, encoding="utf-8") as f:
            user = json.load(f)
    except (OSError, ValueError):
        return cfg
    for key, value in user.items():
        if key == "profiles":
            for name, prof in value.items():
                cfg["profiles"].setdefault(name, {}).update(prof)
        else:
            cfg[key] = value
    return cfg


def save(cfg):
    with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)
        f.write("\n")
