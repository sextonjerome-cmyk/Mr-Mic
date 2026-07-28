"""Mr. Mic settings window — everything editable without opening a text editor.

Hotkeys are recorded by pressing them. Devices can be added, edited, reordered
(order = priority), disabled, or removed. Lives on the shared Tk thread in
`ui.py` as a Toplevel; the app is told to reload when you hit Save.
"""

import logging
import tkinter as tk

import audio
import chime
import config
import hotkeys
import theme
import ui

log = logging.getLogger("mrmic")

WIDTH = 560
FONT = ("Segoe UI", 10)
BOLD = ("Segoe UI Semibold", 10)
SMALL = ("Segoe UI", 8)
HEAD = ("Segoe UI Semibold", 9)

KIND_LABELS = {
    "headset": "🎧  Headset",
    "earbuds": "🎵  Earphones",
    "bluetooth": "📶  Bluetooth",
    "speaker": "🔊  Speakers",
}
LEAVE_ALONE = "— leave alone —"
DOUBLE_CLICK_LABELS = {
    "mute_mic": "🎤  Mute the microphone",
    "mute_speakers": "🔇  Mute the speakers",
    "off": "Off — single click switches instantly",
}

# Tk keysym -> the name the `keyboard` library uses
MODIFIER_KEYS = {
    "Control_L": "ctrl", "Control_R": "ctrl",
    "Alt_L": "alt", "Alt_R": "alt",
    "Shift_L": "shift", "Shift_R": "shift",
    "Super_L": "windows", "Super_R": "windows",
}
KEY_NAMES = {
    "space": "space", "Return": "enter", "Tab": "tab", "BackSpace": "backspace",
    "Prior": "page up", "Next": "page down", "Delete": "delete", "Insert": "insert",
    "Home": "home", "End": "end", "Pause": "pause", "Scroll_Lock": "scroll lock",
    "Print": "print screen", "Caps_Lock": "caps lock", "Num_Lock": "num lock",
    "Up": "up", "Down": "down", "Left": "left", "Right": "right",
    "minus": "-", "equal": "=", "bracketleft": "[", "bracketright": "]",
    "semicolon": ";", "apostrophe": "'", "comma": ",", "period": ".",
    "slash": "/", "backslash": "\\", "grave": "`",
}


def dark_titlebar(win):
    """Windows 11 keeps the title bar light unless the window opts in
    (DWMWA_USE_IMMERSIVE_DARK_MODE = 20). Best effort."""
    try:
        import ctypes
        win.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(win.winfo_id())
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, 20, ctypes.byref(ctypes.c_int(1)), ctypes.sizeof(ctypes.c_int)
        )
    except Exception:
        pass


# -- small themed widgets ---------------------------------------------------

def label(parent, text, bg=theme.BG, fg=theme.TEXT, font=FONT, **kw):
    return tk.Label(parent, text=text, bg=bg, fg=fg, font=font, **kw)


def check(parent, text, var, bg=theme.BG, command=None):
    return tk.Checkbutton(
        parent, text=text, variable=var, command=command, bg=bg, fg=theme.TEXT,
        font=FONT, selectcolor=theme.FIELD, activebackground=bg,
        activeforeground=theme.TEXT, highlightthickness=0, bd=0,
        anchor="w", cursor="hand2",
    )


def entry(parent, var, width=24):
    return tk.Entry(
        parent, textvariable=var, width=width, bg=theme.FIELD, fg=theme.TEXT,
        font=FONT, relief="flat", insertbackground=theme.TEXT,
        highlightthickness=1, highlightbackground=theme.BORDER,
        highlightcolor=theme.BLUE,
    )


def button(parent, text, command, bg=theme.FIELD, fg=theme.TEXT, width=None, font=FONT):
    btn = tk.Label(parent, text=text, bg=bg, fg=fg, font=font, cursor="hand2",
                   padx=10, pady=4)
    if width:
        btn.config(width=width)
    btn.bind("<Button-1>", lambda e: command())
    btn.bind("<Enter>", lambda e: btn.config(bg=theme.BORDER))
    btn.bind("<Leave>", lambda e: btn.config(bg=bg))
    return btn


def dropdown(parent, var, options, width=34):
    menu = tk.OptionMenu(parent, var, *options)
    menu.config(bg=theme.FIELD, fg=theme.TEXT, font=FONT, width=width, anchor="w",
                relief="flat", highlightthickness=1,
                highlightbackground=theme.BORDER, activebackground=theme.BORDER,
                activeforeground=theme.TEXT, cursor="hand2", bd=0)
    menu["menu"].config(bg=theme.PANEL, fg=theme.TEXT, font=FONT,
                        activebackground=theme.BORDER, activeforeground=theme.TEXT,
                        relief="flat", bd=0)
    return menu


def section(parent, title):
    label(parent, title.upper(), fg=theme.DIM, font=HEAD).pack(
        anchor="w", padx=16, pady=(14, 2))
    bar = tk.Frame(parent, bg=theme.BORDER, height=1)
    bar.pack(fill="x", padx=16)
    box = tk.Frame(parent, bg=theme.BG)
    box.pack(fill="x", padx=16, pady=(6, 0))
    return box


class ScrollFrame(tk.Frame):
    """Canvas + inner frame, so a tall settings page still fits on screen."""

    def __init__(self, parent):
        super().__init__(parent, bg=theme.BG)
        self.canvas = tk.Canvas(self, bg=theme.BG, highlightthickness=0)
        self.inner = tk.Frame(self.canvas, bg=theme.BG)
        self.canvas.pack(side="left", fill="both", expand=True)
        self._window = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.inner.bind("<Configure>", self._resize)
        self.canvas.bind("<Configure>",
                         lambda e: self.canvas.itemconfig(self._window, width=e.width))
        # bind on this window, not bind_all — bind_all would hijack the wheel
        # for the mixer flyout too, and outlive this window when it closes
        self.winfo_toplevel().bind("<MouseWheel>", self._wheel)

    def _resize(self, _e):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _wheel(self, event):
        try:
            self.canvas.yview_scroll(-event.delta // 120, "units")
        except tk.TclError:
            pass


# -- device endpoint choices ------------------------------------------------

def endpoint_choices(flow):
    """Every endpoint Windows remembers, newest state first, deduped by name.
    Includes NotPresent ones on purpose — that is how you set up a headset
    that is not in the room right now."""
    seen = {}
    try:
        devices = audio.list_devices(flow, audio.STATE_MASK_ALL)
    except Exception:
        log.exception("settings: could not list endpoints")
        return [LEAVE_ALONE], {}
    for dev in devices:
        name = dev["name"]
        if not name or name == "None":
            continue
        rank = 0 if dev["state"] == audio.STATE_ACTIVE else 1
        if name not in seen or rank < seen[name][0]:
            seen[name] = (rank, dev)
    ordered = sorted(seen.values(), key=lambda pair: (pair[0], pair[1]["name"].lower()))
    return [LEAVE_ALONE] + [
        f"{dev['name']}    ·  {'connected' if rank == 0 else dev['state_name']}"
        for rank, dev in ordered
    ], {
        f"{dev['name']}    ·  {'connected' if rank == 0 else dev['state_name']}": dev
        for rank, dev in ordered
    }


# -- hotkey capture ---------------------------------------------------------

class HotkeyField:
    """Click it, press the keys you want, done. Esc cancels, Backspace clears."""

    def __init__(self, parent, value, on_capture):
        self.value = value
        self.on_capture = on_capture  # (True) starting, (False) finished
        self.recording = False
        self.held = []
        self.widget = tk.Label(
            parent, text=self._text(), bg=theme.FIELD, fg=theme.TEXT, font=FONT,
            width=26, anchor="w", padx=8, pady=4, cursor="hand2",
            highlightthickness=1, highlightbackground=theme.BORDER,
        )
        self.widget.bind("<Button-1>", lambda e: self.start())

    def _text(self):
        return self.value if self.value else "— not set —"

    def clear(self):
        """Back to no hotkey at all. There has to be a visible way to do this —
        a key combo you have to know about isn't one."""
        self.stop()
        self.value = ""
        self.widget.config(text=self._text(), fg=theme.TEXT,
                           highlightbackground=theme.BORDER)

    def start(self):
        if self.recording:
            return
        self.recording = True
        self.held = []
        self.on_capture(True)
        self.widget.config(text="press keys…  (Esc cancels)", fg=theme.BLUE,
                           highlightbackground=theme.BLUE)
        self.widget.focus_set()
        self.widget.bind("<KeyPress>", self._press)
        self.widget.bind("<KeyRelease>", self._release)
        self.widget.bind("<FocusOut>", lambda e: self.stop())

    def stop(self, save=None):
        if not self.recording:
            return
        self.recording = False
        self.widget.unbind("<KeyPress>")
        self.widget.unbind("<KeyRelease>")
        self.widget.unbind("<FocusOut>")
        if save is not None:
            self.value = save
        self.widget.config(text=self._text(), fg=theme.TEXT,
                           highlightbackground=theme.BORDER)
        self.on_capture(False)

    def _press(self, event):
        keysym = event.keysym
        if keysym == "Escape":
            self.stop()
            return "break"
        if keysym == "BackSpace" and not self.held:
            self.stop(save="")
            return "break"
        if keysym in MODIFIER_KEYS:
            name = MODIFIER_KEYS[keysym]
            if name not in self.held:
                self.held.append(name)
            self.widget.config(text="+".join(self.held) + "+…")
            return "break"
        name = KEY_NAMES.get(keysym)
        if name is None:
            name = keysym.lower() if len(keysym) == 1 else keysym.lower()
        combo = "+".join(self.held + [name])
        if hotkeys.is_valid(combo):
            self.stop(save=combo)
        else:
            self.widget.config(text=f"{combo} — not usable", fg=theme.RED)
            self.widget.after(900, lambda: self.stop())
        return "break"

    def _release(self, event):
        name = MODIFIER_KEYS.get(event.keysym)
        if name and name in self.held:
            self.held.remove(name)
        return "break"


def _preselect(dev_map, match, device_id):
    """Which dropdown row is this device already pointing at?"""
    if device_id:
        for choice, dev in dev_map.items():
            if dev["id"] == device_id:
                return choice
    if match:
        needle = match.lower()
        for choice, dev in dev_map.items():
            if needle in dev["name"].lower():
                return choice
    return LEAVE_ALONE


# -- add / edit one device --------------------------------------------------

class DeviceDialog:
    def __init__(self, parent, device, on_ok):
        self.device = config.normalize_device(device)
        self.on_ok = on_ok
        self.win = tk.Toplevel(parent)
        self.win.title("Mr. Mic — Device")
        self.win.configure(bg=theme.BG)
        self.win.transient(parent)
        self.win.resizable(False, False)
        dark_titlebar(self.win)

        out_options, self.out_map = endpoint_choices(audio.RENDER)
        in_options, self.in_map = endpoint_choices(audio.CAPTURE)

        self.name = tk.StringVar(value=self.device["label"])
        self.kind = tk.StringVar(value=KIND_LABELS[self.device["icon"]])
        self.out_pick = tk.StringVar(
            value=_preselect(self.out_map, self.device["output_match"],
                             self.device["output_id"]))
        self.in_pick = tk.StringVar(
            value=_preselect(self.in_map, self.device["input_match"],
                             self.device["input_id"]))
        self.out_match = tk.StringVar(value=self.device["output_match"])
        self.in_match = tk.StringVar(value=self.device["input_match"])
        self.auto = tk.BooleanVar(value=self.device["auto"])
        self.by_battery = tk.BooleanVar(value=self.device["detect"] == "battery")

        body = tk.Frame(self.win, bg=theme.BG)
        body.pack(fill="both", expand=True, padx=16, pady=14)

        row = tk.Frame(body, bg=theme.BG)
        row.pack(fill="x", pady=(0, 10))
        label(row, "Name", width=10, anchor="w").pack(side="left")
        entry(row, self.name, width=34).pack(side="left")

        row = tk.Frame(body, bg=theme.BG)
        row.pack(fill="x", pady=(0, 10))
        label(row, "Icon", width=10, anchor="w").pack(side="left")
        dropdown(row, self.kind, list(KIND_LABELS.values()), width=14).pack(side="left")

        self._picker(body, "Speakers", self.out_pick, out_options, self.out_match,
                     self.out_map)
        self._picker(body, "Microphone", self.in_pick, in_options, self.in_match,
                     self.in_map)

        check(body, "Switch to it automatically when it turns on / is plugged in",
              self.auto).pack(anchor="w", pady=(4, 0))
        check(body, "This is the HyperX dongle (detect by battery, not by Windows)",
              self.by_battery).pack(anchor="w")
        label(body, "The HyperX dongle looks connected to Windows even when the "
                    "headset is off,\nso only that one needs the battery trick.",
              fg=theme.DIM, font=SMALL, justify="left").pack(anchor="w", padx=22)

        buttons = tk.Frame(body, bg=theme.BG)
        buttons.pack(fill="x", pady=(16, 0))
        button(buttons, "Cancel", self.win.destroy).pack(side="right")
        button(buttons, "OK", self._ok, bg=theme.BLUE, fg=theme.BG,
               font=BOLD).pack(side="right", padx=(0, 8))

        self.win.bind("<Escape>", lambda e: self.win.destroy())
        self.win.update_idletasks()
        ui.center(self.win, self.win.winfo_reqwidth(), self.win.winfo_reqheight())
        self.win.grab_set()

    def _picker(self, parent, title, pick_var, options, match_var, dev_map):
        wrap = tk.Frame(parent, bg=theme.BG)
        wrap.pack(fill="x", pady=(0, 8))
        row = tk.Frame(wrap, bg=theme.BG)
        row.pack(fill="x")
        label(row, title, width=10, anchor="w").pack(side="left")
        dropdown(row, pick_var, options, width=34).pack(side="left")

        sub = tk.Frame(wrap, bg=theme.BG)
        sub.pack(fill="x", pady=(2, 0))
        label(sub, "", width=10).pack(side="left")
        label(sub, "matches", fg=theme.DIM, font=SMALL).pack(side="left", padx=(0, 6))
        entry(sub, match_var, width=30).pack(side="left")

        def picked(*_):
            choice = pick_var.get()
            dev = dev_map.get(choice)
            if dev:
                match_var.set(dev["name"])
                self._picked_ids[title] = dev["id"]
            elif choice == LEAVE_ALONE:
                match_var.set("")
                self._picked_ids[title] = None
        if not hasattr(self, "_picked_ids"):
            self._picked_ids = {}
        pick_var.trace_add("write", picked)

    def _ok(self):
        picked = getattr(self, "_picked_ids", {})
        kind = next(k for k, v in KIND_LABELS.items() if v == self.kind.get())
        out_match = self.out_match.get().strip()
        in_match = self.in_match.get().strip()
        device = dict(self.device)
        device.update({
            "label": self.name.get().strip() or "Device",
            "icon": kind,
            "output_match": out_match,
            "input_match": in_match,
            "auto": bool(self.auto.get()),
            "detect": "battery" if self.by_battery.get() else "endpoint",
        })
        # A fresh pick from the dropdown wins. Otherwise keep the saved id —
        # unless the match text was hand-edited, in which case the old id would
        # silently override what was just typed (ids are checked first).
        if "Speakers" in picked:
            device["output_id"] = picked["Speakers"]
        elif out_match != self.device["output_match"]:
            device["output_id"] = None
        if "Microphone" in picked:
            device["input_id"] = picked["Microphone"]
        elif in_match != self.device["input_match"]:
            device["input_id"] = None
        if not out_match:
            device["output_id"] = None
        if not in_match:
            device["input_id"] = None
        if not device["key"] or device["key"] == "device":
            device["key"] = _slug(device["label"])
        self.on_ok(config.normalize_device(device))
        self.win.destroy()


def _slug(text):
    keep = [c.lower() if c.isalnum() else "-" for c in text]
    return "".join(keep).strip("-") or "device"


# -- the settings window ----------------------------------------------------

class SettingsWindow:
    def __init__(self, app):
        self.app = app
        self.win = None

    def show(self):
        ui.call(self._open)

    def _open(self):
        if self.win is not None and self.win.winfo_exists():
            self.win.deiconify()
            self.win.lift()
            self.win.focus_force()
            return
        self._build()

    # -- build -------------------------------------------------------------

    def _build(self):
        cfg = self.app.cfg
        self.devices = [config.normalize_device(d) for d in cfg.get("devices", [])]

        self.win = tk.Toplevel(ui.root)
        self.win.title("Mr. Mic — Settings")
        self.win.configure(bg=theme.BG)
        self.win.protocol("WM_DELETE_WINDOW", self._close)
        dark_titlebar(self.win)

        scroller = ScrollFrame(self.win)
        scroller.pack(fill="both", expand=True)
        body = scroller.inner

        label(body, "Mr. Mic", font=("Segoe UI Semibold", 14)).pack(
            anchor="w", padx=16, pady=(14, 0))
        label(body, "Everything here saves to settings.json — no text editor needed.",
              fg=theme.DIM, font=SMALL).pack(anchor="w", padx=16)

        # hotkeys
        box = section(body, "Hotkeys")
        self.hotkey_fields = {}
        for key, title in (("hotkey", "Switch device"),
                           ("mute_hotkey", "Mute speakers"),
                           ("mic_mute_hotkey", "Mute microphone")):
            row = tk.Frame(box, bg=theme.BG)
            row.pack(fill="x", pady=2)
            label(row, title, width=18, anchor="w").pack(side="left")
            field = HotkeyField(row, cfg.get(key, ""), self._capture)
            field.widget.pack(side="left")
            button(row, "✕  clear", field.clear, bg=theme.BG, fg=theme.RED,
                   font=SMALL).pack(side="left", padx=(4, 0))
            self.hotkey_fields[key] = field
        label(box, "Click a box and press the keys you want. "
                   "“✕ clear” sets it back to no hotkey.",
              fg=theme.DIM, font=SMALL).pack(anchor="w", pady=(4, 0))

        # tray double-click
        box = section(body, "Double-click the tray icon")
        self.dbl = tk.StringVar(
            value=DOUBLE_CLICK_LABELS.get(cfg.get("tray_double_click", "mute_mic"),
                                          DOUBLE_CLICK_LABELS["mute_mic"]))
        dropdown(box, self.dbl, list(DOUBLE_CLICK_LABELS.values()),
                 width=30).pack(anchor="w")
        label(box, "A quick mute for when someone starts talking to you.\n"
                   "Costs a single click about half a second: Windows can't tell "
                   "a single\nclick from the first half of a double one until "
                   "that long has passed.\nSet it to Off and switching by click "
                   "is instant again.",
              fg=theme.DIM, font=SMALL, justify="left").pack(anchor="w", pady=(4, 0))

        # devices
        box = section(body, "Devices")
        label(box, "Top of the list wins when two are on at once. "
                   "Untick to hide one without deleting it.",
              fg=theme.DIM, font=SMALL, justify="left").pack(anchor="w", pady=(0, 6))
        self.device_box = tk.Frame(box, bg=theme.BG)
        self.device_box.pack(fill="x")
        self._rebuild_devices()
        button(box, "+  Add device", self._add).pack(anchor="w", pady=(8, 0))

        # options
        box = section(body, "Options")
        self.autodetect = tk.BooleanVar(value=bool(cfg.get("autodetect", True)))
        self.chime = tk.BooleanVar(value=bool(cfg.get("chime", True)))
        self.notifications = tk.BooleanVar(value=bool(cfg.get("notifications", False)))
        check(box, "Switch automatically when a device turns on or is plugged in",
              self.autodetect).pack(anchor="w")
        check(box, "Play a chime when switching", self.chime).pack(anchor="w")
        row = tk.Frame(box, bg=theme.BG)
        row.pack(fill="x", padx=(22, 0), pady=(2, 0))
        styles = {key: spec["label"] for key, spec in chime.STYLES.items()}
        self.chime_style_labels = styles
        self.chime_style = tk.StringVar(
            value=styles.get(cfg.get("chime_style", chime.DEFAULT_STYLE),
                             styles[chime.DEFAULT_STYLE]))
        dropdown(row, self.chime_style, list(styles.values()),
                 width=28).pack(side="left")
        button(row, "▶  Test", self._test_chime).pack(side="left", padx=(6, 0))
        check(box, "Show a notification when switching",
              self.notifications).pack(anchor="w")
        row = tk.Frame(box, bg=theme.BG)
        row.pack(fill="x", pady=(6, 0))
        label(row, "Warn when battery drops to", anchor="w").pack(side="left")
        self.battery_warn = tk.StringVar(value=str(cfg.get("battery_warn", 20)))
        entry(row, self.battery_warn, width=4).pack(side="left", padx=6)
        label(row, "%").pack(side="left")

        # footer
        footer = tk.Frame(body, bg=theme.BG)
        footer.pack(fill="x", padx=16, pady=16)
        self.status = label(footer, "", fg=theme.DIM, font=SMALL)
        self.status.pack(side="left")
        button(footer, "Save", self._save, bg=theme.BLUE, fg=theme.BG,
               font=BOLD).pack(side="right")
        button(footer, "Cancel", self._close).pack(side="right", padx=(0, 8))

        self.win.update_idletasks()
        height = min(body.winfo_reqheight() + 10,
                     int(self.win.winfo_screenheight() * 0.85))
        ui.center(self.win, WIDTH, height)
        self.win.lift()
        self.win.focus_force()

    def _rebuild_devices(self):
        for child in self.device_box.winfo_children():
            child.destroy()
        if not self.devices:
            label(self.device_box, "No devices yet — add one below.",
                  fg=theme.DIM, font=SMALL).pack(anchor="w")
        for index, device in enumerate(self.devices):
            self._device_row(index, device)

    def _device_row(self, index, device):
        row = tk.Frame(self.device_box, bg=theme.PANEL)
        row.pack(fill="x", pady=1)

        enabled = tk.BooleanVar(value=device["enabled"])

        def toggle(device=device, var=enabled):
            device["enabled"] = bool(var.get())
        check(row, "", enabled, bg=theme.PANEL, command=toggle).pack(side="left")

        text = f"{KIND_LABELS[device['icon']].split()[0]}  {device['label']}"
        label(row, text, bg=theme.PANEL,
              fg=theme.TEXT if device["enabled"] else theme.DIM,
              anchor="w").pack(side="left", pady=4)
        if device["auto"]:
            label(row, "auto", bg=theme.PANEL, fg=theme.GREEN,
                  font=SMALL).pack(side="left", padx=6)

        for glyph, action, tip in (
            ("✕", lambda i=index: self._remove(i), "remove"),
            ("Edit", lambda i=index: self._edit(i), "edit"),
            ("▼", lambda i=index: self._move(i, 1), "down"),
            ("▲", lambda i=index: self._move(i, -1), "up"),
        ):
            button(row, glyph, action, bg=theme.PANEL,
                   fg=theme.RED if glyph == "✕" else theme.TEXT,
                   font=SMALL).pack(side="right", padx=1)

    # -- actions -----------------------------------------------------------

    def _capture(self, started):
        """Global hotkeys must stand down while the user is pressing keys —
        otherwise recording ctrl+alt+h fires the switch."""
        if started:
            hotkeys.unbind_all()
        else:
            self.app.bind_hotkeys()

    def _chime_style_key(self):
        return next((k for k, v in self.chime_style_labels.items()
                     if v == self.chime_style.get()), chime.DEFAULT_STYLE)

    def _test_chime(self):
        """Rising then falling, so you hear both halves of the pair."""
        style = self._chime_style_key()
        chime.preview(style, rising=True)
        self.win.after(900, lambda: chime.preview(style, rising=False))

    def _move(self, index, delta):
        target = index + delta
        if 0 <= target < len(self.devices):
            self.devices[index], self.devices[target] = (
                self.devices[target], self.devices[index])
            self._rebuild_devices()

    def _remove(self, index):
        if 0 <= index < len(self.devices):
            del self.devices[index]
            self._rebuild_devices()

    def _edit(self, index):
        def done(device):
            self.devices[index] = device
            self._rebuild_devices()
        DeviceDialog(self.win, self.devices[index], done)

    def _add(self):
        def done(device):
            keys = {d["key"] for d in self.devices}
            while device["key"] in keys:
                device["key"] += "-2"
            self.devices.append(device)
            self._rebuild_devices()
        DeviceDialog(self.win, {"label": "New device"}, done)

    def _save(self):
        cfg = self.app.cfg
        for key, field in self.hotkey_fields.items():
            field.stop()
            cfg[key] = field.value
        cfg["devices"] = self.devices
        cfg["tray_double_click"] = next(
            (k for k, v in DOUBLE_CLICK_LABELS.items() if v == self.dbl.get()),
            "mute_mic")
        cfg["autodetect"] = bool(self.autodetect.get())
        cfg["chime"] = bool(self.chime.get())
        cfg["chime_style"] = self._chime_style_key()
        cfg["notifications"] = bool(self.notifications.get())
        try:
            cfg["battery_warn"] = max(0, min(100, int(self.battery_warn.get())))
        except ValueError:
            pass
        try:
            config.save(cfg)
        except OSError:
            log.exception("could not write settings.json")
            self.status.config(text="Could not write settings.json", fg=theme.RED)
            return
        self.app.reload()
        self.status.config(text="Saved.", fg=theme.GREEN)
        self.win.after(700, self._close)

    def _close(self):
        for field in getattr(self, "hotkey_fields", {}).values():
            field.stop()
        if self.win is not None:
            self.win.destroy()
            self.win = None
        self.app.bind_hotkeys()
