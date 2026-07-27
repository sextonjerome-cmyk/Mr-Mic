"""Global hotkey binding for Mr. Mic.

The `keyboard` library accepts modifier combos ("ctrl+alt+h"), single keys
("pause"), and plain-key chords ("v+c" — both held together).
"""

import keyboard

_handle = None


def bind(hotkey, callback):
    """Bind hotkey (replacing any previous one). Raises ValueError on a bad
    hotkey string so the caller can tell the user."""
    global _handle
    unbind()
    _handle = keyboard.add_hotkey(hotkey, callback)


def unbind():
    global _handle
    if _handle is not None:
        try:
            keyboard.remove_hotkey(_handle)
        except (KeyError, ValueError):
            pass
        _handle = None
