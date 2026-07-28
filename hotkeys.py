"""Global hotkeys for Mr. Mic.

The `keyboard` library accepts modifier combos ("ctrl+alt+h"), single keys
("pause"), and plain-key chords ("v+c" — both held together). Several
hotkeys can be bound at once (toggle, mute output, mute mic); each is
tracked by name so it can be rebound on its own.
"""

import keyboard

_handles = {}


def bind(name, hotkey, callback):
    """Bind (or rebind) one named hotkey. An empty string just unbinds it.
    Raises ValueError on a bad hotkey string so the caller can say so."""
    unbind(name)
    if not hotkey or not hotkey.strip():
        return
    _handles[name] = keyboard.add_hotkey(hotkey.strip(), callback)


def unbind(name):
    handle = _handles.pop(name, None)
    if handle is not None:
        try:
            keyboard.remove_hotkey(handle)
        except (KeyError, ValueError):
            pass


def unbind_all():
    for name in list(_handles):
        unbind(name)


def is_valid(hotkey):
    """True if `keyboard` can parse this combo — used by the settings window
    before saving."""
    if not hotkey or not hotkey.strip():
        return True  # blank = "no hotkey", always fine
    try:
        keyboard.parse_hotkey(hotkey.strip())
        return True
    except (ValueError, KeyError):
        return False
