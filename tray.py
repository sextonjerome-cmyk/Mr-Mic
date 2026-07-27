"""Tray icon images for Mr. Mic — drawn with PIL in the CobbAttack palette."""

from PIL import Image, ImageDraw

import theme

SIZE = 64


def _canvas():
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    return img, ImageDraw.Draw(img)


def headset_icon(color=theme.GREEN):
    """Headset with mic boom — shown when the HyperX profile is active."""
    img, d = _canvas()
    d.arc((8, 6, 56, 54), start=180, end=360, fill=color, width=7)
    d.rounded_rectangle((6, 28, 20, 52), radius=6, fill=color)
    d.rounded_rectangle((44, 28, 58, 52), radius=6, fill=color)
    d.line((16, 52, 26, 59), fill=color, width=5)
    d.ellipse((24, 55, 34, 64), fill=color)
    return img


def speaker_icon(color=theme.BLUE):
    """Speaker with sound waves — shown when the laptop profile is active."""
    img, d = _canvas()
    d.rectangle((6, 24, 18, 40), fill=color)
    d.polygon(((18, 24), (32, 10), (32, 54), (18, 40)), fill=color)
    d.arc((30, 18, 50, 46), start=-55, end=55, fill=color, width=5)
    d.arc((36, 8, 64, 56), start=-50, end=50, fill=color, width=5)
    return img


def icon_for(profile):
    if profile == "headset":
        return headset_icon(theme.GREEN)
    if profile == "laptop":
        return speaker_icon(theme.AMBER)
    # neither profile matches the current default (some other device)
    return speaker_icon(theme.DIM)
