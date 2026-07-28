"""One Tk thread for all of Mr. Mic's windows.

Tk is not thread-safe and hates having two roots in one process, so there is
exactly one hidden root here. The mixer flyout and the settings window are
Toplevels on it. Anything that touches Tk (or COM, for the mixer) goes
through `call()`, which runs it on this thread.
"""

import logging
import queue
import threading
import tkinter as tk

log = logging.getLogger("mrmic")

_q = queue.SimpleQueue()
_ready = threading.Event()
root = None


def start():
    """Spin up the Tk thread and wait for the root to exist."""
    if _ready.is_set():
        return
    threading.Thread(target=_run, daemon=True).start()
    _ready.wait(10)


def call(fn):
    """Run fn() on the Tk thread, soon."""
    _q.put(fn)


def _run():
    global root
    import audio
    audio._com_init()  # the mixer reads endpoint volumes from this thread
    root = tk.Tk()
    root.withdraw()
    _ready.set()
    _pump()
    root.mainloop()


def _pump():
    while True:
        try:
            fn = _q.get_nowait()
        except queue.Empty:
            break
        try:
            fn()
        except Exception:
            log.exception("ui callback failed")
    root.after(100, _pump)


# -- shared widgets ---------------------------------------------------------

def place_near_cursor(win, width, height, margin=8):
    """Put a popup just above the mouse, clamped to the screen."""
    px, py = win.winfo_pointerx(), win.winfo_pointery()
    sw, sh = win.winfo_screenwidth(), win.winfo_screenheight()
    x = min(max(px - width // 2, margin), sw - width - margin)
    y = max(py - height - 12, margin)
    win.geometry(f"{width}x{height}+{x}+{y}")


def center(win, width, height):
    sw, sh = win.winfo_screenwidth(), win.winfo_screenheight()
    win.geometry(f"{width}x{height}+{(sw - width) // 2}+{max((sh - height) // 3, 20)}")
