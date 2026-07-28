"""Switch chimes for Mr. Mic — tiny generated WAVs, played async.

Switching TO something you wear (headset, earphones, Bluetooth) plays the
notes rising; falling back to plain speakers plays them falling, so you can
tell which way it went without looking.

Several styles to pick from in Settings. Everything is synthesised here — no
sound files ship with the app — and each style is rendered to assets/ the
first time it is used, then reused.
"""

import logging
import math
import os
import struct
import wave
import winsound

import config

log = logging.getLogger("mrmic")

ASSETS = os.path.join(config.APP_DIR, "assets")
RATE = 22050

# Each style: the notes (low to high — reversed for the falling version), how
# long each note lasts, the waveform, how fast it dies away, and its partials
# (ratio, loudness) which is what actually makes a bell sound like a bell and
# a marimba sound like a marimba.
STYLES = {
    "beep": {
        "label": "Beep — the original",
        "notes": (659, 880), "ms": 95, "wave": "sine", "decay": 0.0,
        "partials": ((1, 1.0),), "volume": 0.35,
    },
    "soft": {
        "label": "Soft — gentle and low",
        "notes": (392, 523), "ms": 180, "wave": "sine", "decay": 0.4,
        "partials": ((1, 1.0), (2, 0.22)), "volume": 0.32,
    },
    "marimba": {
        "label": "Marimba — warm wooden knock",
        "notes": (587, 880), "ms": 140, "wave": "sine", "decay": 1.8,
        "partials": ((1, 1.0), (4, 0.35)), "volume": 0.42,
    },
    "bell": {
        "label": "Bell — soft ringing chime",
        "notes": (784, 1047), "ms": 430, "wave": "sine", "decay": 1.1,
        "partials": ((1, 1.0), (2.76, 0.45), (5.4, 0.2)), "volume": 0.30,
    },
    "blip": {
        "label": "Blip — one very short tick",
        "notes": (1046,), "ms": 50, "wave": "triangle", "decay": 1.2,
        "partials": ((1, 1.0),), "volume": 0.35,
        "down_notes": (523,),
    },
    "arcade": {
        "label": "Arcade — three chirpy notes",
        "notes": (523, 659, 784), "ms": 70, "wave": "square", "decay": 0.0,
        "partials": ((1, 1.0),), "volume": 0.22,
    },
}
DEFAULT_STYLE = "beep"


def style_or_default(name):
    return name if name in STYLES else DEFAULT_STYLE


def _wave_value(kind, phase):
    if kind == "square":
        return 0.7 if math.sin(phase) >= 0 else -0.7
    if kind == "triangle":
        return (2 / math.pi) * math.asin(math.sin(phase))
    return math.sin(phase)


def _render(path, notes, spec):
    per_note = int(RATE * spec["ms"] / 1000)
    attack = max(1, int(RATE * 0.005))
    release = max(1, int(per_note * 0.18))
    total_amp = sum(amp for _, amp in spec["partials"])
    frames = bytearray()
    for freq in notes:
        for i in range(per_note):
            t = i / RATE
            env = min(1.0, i / attack)
            if spec["decay"] > 0:
                env *= math.exp(-spec["decay"] * 5 * i / per_note)
            elif i > per_note - release:
                env *= (per_note - i) / release
            value = sum(amp * _wave_value(spec["wave"], 2 * math.pi * freq * ratio * t)
                        for ratio, amp in spec["partials"]) / total_amp
            frames += struct.pack("<h", int(32767 * spec["volume"] * env * value))
    with wave.open(path, "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(RATE)
        f.writeframes(bytes(frames))


def paths(style=DEFAULT_STYLE):
    """The (rising, falling) WAVs for a style, rendering them if needed."""
    style = style_or_default(style)
    spec = STYLES[style]
    os.makedirs(ASSETS, exist_ok=True)
    up_notes = tuple(spec["notes"])
    down_notes = tuple(spec.get("down_notes") or reversed(up_notes))
    result = []
    for suffix, notes in (("up", up_notes), ("down", down_notes)):
        path = os.path.join(ASSETS, f"chime_{style}_{suffix}.wav")
        if not os.path.exists(path):
            _render(path, notes, spec)
        result.append(path)
    return result[0], result[1]


def play(kind, style=DEFAULT_STYLE):
    """kind is a device icon kind: "speaker" falls, everything worn rises."""
    up, down = paths(style)
    path = down if kind == "speaker" else up
    winsound.PlaySound(
        path, winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)


def preview(style, rising=True):
    """Play one style once, for the Test button in Settings."""
    try:
        play("headset" if rising else "speaker", style)
    except Exception:
        log.exception("chime preview failed")


if __name__ == "__main__":
    import time
    for name, spec in STYLES.items():
        print(f"{name:<9} {spec['label']}")
        play("headset", name)
        time.sleep(1.1)
        play("speaker", name)
        time.sleep(1.3)
