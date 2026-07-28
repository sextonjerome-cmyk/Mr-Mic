"""Switch chimes for Mr. Mic — tiny generated WAVs, played async.

Switching TO something you wear (headset, earphones, Bluetooth) plays two
rising notes; falling back to plain speakers plays two falling notes, so you
can tell which way it went without looking. Generated once into assets/.
"""

import math
import os
import struct
import wave
import winsound

import config

ASSETS = os.path.join(config.APP_DIR, "assets")
RATE = 22050
VOLUME = 0.35


def _render(path, freqs, note_ms=95):
    frames = bytearray()
    fade = int(RATE * 0.012)
    per_note = int(RATE * note_ms / 1000)
    for freq in freqs:
        for i in range(per_note):
            amp = VOLUME
            if i < fade:
                amp *= i / fade
            elif i > per_note - fade:
                amp *= (per_note - i) / fade
            sample = int(32767 * amp * math.sin(2 * math.pi * freq * i / RATE))
            frames += struct.pack("<h", sample)
    with wave.open(path, "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(RATE)
        f.writeframes(bytes(frames))


def ensure():
    os.makedirs(ASSETS, exist_ok=True)
    up = os.path.join(ASSETS, "chime_headset.wav")
    down = os.path.join(ASSETS, "chime_laptop.wav")
    if not os.path.exists(up):
        _render(up, (659, 880))     # E5 -> A5, rising = headset
    if not os.path.exists(down):
        _render(down, (880, 659))   # A5 -> E5, falling = laptop
    return {"headset": up, "laptop": down}


def play(kind):
    """kind is a device icon kind: "speaker" falls, everything worn rises."""
    paths = ensure()
    path = paths["laptop"] if kind == "speaker" else paths["headset"]
    winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
