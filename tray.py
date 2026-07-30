"""Tray icon images for Mr. Mic — drawn with PIL, colors from theme.py.

One glyph per device kind (headset / earbuds / bluetooth / speaker). Keep
them chunky: they render at 16 px.
"""

from PIL import Image, ImageDraw

import theme

SIZE = 64

# Which color each device kind wears when it is the active one.
KIND_COLORS = {
    "headset": theme.GREEN,
    "headphones": theme.BLUE,
    "earbuds": theme.BLUE,
    "bluetooth": theme.BLUE,
    "speaker": theme.AMBER,
}


def _canvas():
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    return img, ImageDraw.Draw(img)


def headset_icon(color=theme.GREEN):
    """Headset with mic boom — over-ear headset with a microphone."""
    img, d = _canvas()
    d.arc((8, 6, 56, 54), start=180, end=360, fill=color, width=7)
    d.rounded_rectangle((6, 28, 20, 52), radius=6, fill=color)
    d.rounded_rectangle((44, 28, 58, 52), radius=6, fill=color)
    d.line((16, 52, 26, 59), fill=color, width=5)
    d.ellipse((24, 55, 34, 64), fill=color)
    return img


def headphones_icon(color=theme.BLUE):
    """Over-ear cups and a band, no mic boom — the Skullcandy. Same silhouette
    as the headset minus the boom; the color is what tells them apart at 16 px
    (headset is green, these are blue)."""
    img, d = _canvas()
    d.arc((7, 6, 57, 56), start=180, end=360, fill=color, width=8)
    d.rounded_rectangle((4, 30, 22, 58), radius=8, fill=color)
    d.rounded_rectangle((42, 30, 60, 58), radius=8, fill=color)
    return img


def earbuds_icon(color=theme.BLUE):
    """Two buds on a cable — the wired earphones in the headphone jack."""
    img, d = _canvas()
    d.ellipse((4, 6, 28, 30), fill=color)
    d.ellipse((36, 6, 60, 30), fill=color)
    d.line((16, 28, 16, 44), fill=color, width=7)
    d.line((48, 28, 48, 44), fill=color, width=7)
    d.arc((16, 32, 48, 60), start=0, end=180, fill=color, width=7)
    return img


def bluetooth_icon(color=theme.BLUE):
    """The bare Bluetooth rune. A rune drawn *inside* headphones turns to mush
    at 16 px — the rune alone is the thing people actually recognise."""
    img, d = _canvas()
    spine = ((32, 6), (32, 58))
    d.line(spine, fill=color, width=7, joint="curve")
    d.line(((32, 6), (47, 20), (17, 33)), fill=color, width=7, joint="curve")
    d.line(((32, 58), (47, 44), (17, 31)), fill=color, width=7, joint="curve")
    return img


def speaker_icon(color=theme.AMBER):
    """Speaker with sound waves — the laptop speakers (or any plain output)."""
    img, d = _canvas()
    d.rectangle((6, 24, 18, 40), fill=color)
    d.polygon(((18, 24), (32, 10), (32, 54), (18, 40)), fill=color)
    d.arc((30, 18, 50, 46), start=-55, end=55, fill=color, width=5)
    d.arc((36, 8, 64, 56), start=-50, end=50, fill=color, width=5)
    return img


GLYPHS = {
    "headset": headset_icon,
    "headphones": headphones_icon,
    "earbuds": earbuds_icon,
    "bluetooth": bluetooth_icon,
    "speaker": speaker_icon,
}


def icon_for(kind, muted=False):
    """Icon for the active device kind. None = the current default isn't any
    configured device, so draw a dim speaker. Muted draws it in RED."""
    if kind is None:
        return speaker_icon(theme.DIM)
    color = theme.RED if muted else KIND_COLORS.get(kind, theme.AMBER)
    return GLYPHS.get(kind, speaker_icon)(color)
