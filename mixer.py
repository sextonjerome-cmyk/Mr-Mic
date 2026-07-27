"""Mr. Mic mixer flyout — EarTrumpet-style per-device / per-app volumes.

Middle-click the tray icon to open. Runs a tkinter loop on its own thread;
all Tk *and* COM calls for the mixer happen on that thread.
"""

import logging
import queue
import threading
import tkinter as tk
from ctypes import POINTER, cast

import comtypes
import psutil
from PIL import Image, ImageDraw, ImageTk
from pycaw.api.audiopolicy import IAudioSessionControl2
from pycaw.pycaw import IAudioEndpointVolume, IAudioSessionManager2, ISimpleAudioVolume

import appicons
import audio
import battery as battery_mod
import theme

log = logging.getLogger("mrmic")

SESSION_EXPIRED = 2
WIDTH = 340


class Slider(tk.Canvas):
    """EarTrumpet-style slider: thin track, light fill, round grab handle.
    Plain dark mode — no accent colors."""

    PAD = 10
    RADIUS = 7

    def __init__(self, parent, value, on_change, bg, label, length=200, height=26):
        super().__init__(parent, width=length, height=height, bg=bg,
                         highlightthickness=0, cursor="hand2")
        self.value = value  # 0..100
        self.on_change = on_change
        self.label = label
        self.bind("<Configure>", lambda e: self._redraw())
        self.bind("<Button-1>", self._drag)
        self.bind("<B1-Motion>", self._drag)

    def _span(self):
        w = self.winfo_width()
        if w <= 1:
            w = int(self["width"])
        return self.PAD, w - self.PAD

    def _redraw(self):
        self.delete("all")
        x0, x1 = self._span()
        y = int(self["height"]) // 2
        fx = x0 + (x1 - x0) * self.value / 100
        self.create_line(x0, y, x1, y, width=4, capstyle="round", fill=theme.FIELD)
        if fx > x0:
            self.create_line(x0, y, fx, y, width=4, capstyle="round", fill=theme.TEXT)
        r = self.RADIUS
        self.create_oval(fx - r, y - r, fx + r, y + r, fill=theme.TEXT, outline="")

    def _drag(self, event):
        x0, x1 = self._span()
        self.value = (min(max(event.x, x0), x1) - x0) / (x1 - x0) * 100
        self.label.config(text=f"{round(self.value)}")
        self.on_change(self.value / 100)
        self._redraw()


class Mixer:
    def __init__(self, alias, battery=lambda: None):
        self.alias = alias
        self.battery = battery
        self._q = queue.SimpleQueue()
        self._refs = []  # keep COM pointers + PhotoImages alive while open
        self._icon_cache = {}  # exe path -> PIL image
        threading.Thread(target=self._run, daemon=True).start()

    def show(self):
        self._q.put("show")

    # -- tk thread ---------------------------------------------------------

    def _run(self):
        audio._com_init()
        self.root = tk.Tk()
        self.root.withdraw()
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.configure(bg=theme.BORDER)
        self.frame = tk.Frame(self.root, bg=theme.BG)
        self.frame.pack(fill="both", expand=True, padx=1, pady=1)
        self.root.bind("<Escape>", lambda e: self._hide())
        self.root.bind("<FocusOut>", self._maybe_hide)
        self._poll()
        self.root.mainloop()

    def _poll(self):
        try:
            while True:
                self._q.get_nowait()
                self._show()
        except queue.Empty:
            pass
        self.root.after(120, self._poll)

    def _hide(self):
        self.root.withdraw()
        self._refs.clear()

    def _maybe_hide(self, _event):
        self.root.after(120, lambda: self._hide() if self._focus_lost() else None)

    def _focus_lost(self):
        try:
            return self.root.focus_get() is None
        except (KeyError, tk.TclError):
            return False  # focus is on a widget tk can't resolve — still ours

    # -- audio plumbing (tk thread only) -----------------------------------

    def _endpoint_volume(self, dev_id):
        dev = audio._enumerator().GetDevice(dev_id)
        iface = dev.Activate(IAudioEndpointVolume._iid_, comtypes.CLSCTX_ALL, None)
        return cast(iface, POINTER(IAudioEndpointVolume))

    def _sessions(self, dev_id):
        dev = audio._enumerator().GetDevice(dev_id)
        iface = dev.Activate(IAudioSessionManager2._iid_, comtypes.CLSCTX_ALL, None)
        manager = cast(iface, POINTER(IAudioSessionManager2))
        enum = manager.GetSessionEnumerator()
        grouped = {}  # one slider per app — apps like DCS own several sessions
        for i in range(enum.GetCount()):
            try:
                ctl = enum.GetSession(i)
                if ctl.GetState() == SESSION_EXPIRED:
                    continue
                ctl2 = ctl.QueryInterface(IAudioSessionControl2)
                simple = ctl.QueryInterface(ISimpleAudioVolume)
                pid = ctl2.GetProcessId()
                exe = None
                if pid:
                    proc = psutil.Process(pid)
                    name = proc.name().rsplit(".exe", 1)[0].capitalize()
                    try:
                        exe = proc.exe()
                    except psutil.Error:
                        pass
                else:
                    name = "System sounds"
                grouped.setdefault((name, exe), []).append(simple)
            except (comtypes.COMError, psutil.Error):
                continue
        return sorted((n, e, s) for (n, e), s in grouped.items())

    # -- UI build ----------------------------------------------------------

    def _app_image(self, name, exe):
        key = exe or name
        if key not in self._icon_cache:
            img = appicons.exe_icon(exe) if exe else None
            if img is None:
                img = self._letter_icon(name)
            self._icon_cache[key] = img
        return self._icon_cache[key]

    @staticmethod
    def _letter_icon(name, size=18):
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.ellipse((0, 0, size - 1, size - 1), fill=theme.FIELD)
        d.text((size // 2, size // 2), (name or "?")[0].upper(),
               fill=theme.TEXT, anchor="mm")
        return img

    def _tooltip(self, widget, text):
        tip = {}

        def enter(_e):
            tw = tk.Toplevel(self.root)
            tw.overrideredirect(True)
            tw.attributes("-topmost", True)
            tw.geometry(f"+{widget.winfo_rootx() + 12}+{widget.winfo_rooty() - 24}")
            tk.Label(tw, text=text, bg=theme.FIELD, fg=theme.TEXT,
                     font=("Segoe UI", 8), padx=6, pady=1).pack()
            tip["w"] = tw

        def leave(_e):
            w = tip.pop("w", None)
            if w:
                w.destroy()

        widget.bind("<Enter>", enter)
        widget.bind("<Leave>", leave)

    def _slider(self, parent, value, on_change, bg=theme.BG):
        row = tk.Frame(parent, bg=bg)
        label = tk.Label(row, text=f"{round(value)}", width=3, anchor="e",
                         bg=bg, fg=theme.TEXT, font=("Segoe UI", 10))
        scale = Slider(row, value, on_change, bg=bg, label=label, length=WIDTH - 110)
        scale.pack(side="left", fill="x", expand=True, padx=(0, 6))
        label.pack(side="right")
        return row

    def _device_section(self, dev, is_default, prefix=""):
        """Header (name + mute) and master slider for one device."""
        epv = self._endpoint_volume(dev["id"])

        header = tk.Frame(self.frame, bg=theme.PANEL)
        header.pack(fill="x", pady=(8, 0), padx=8)
        title = prefix + self.alias(dev["name"]) + ("  ●" if is_default else "")
        tk.Label(header, text=title, bg=theme.PANEL, fg=theme.TEXT,
                 font=("Segoe UI Semibold", 10)).pack(side="left", padx=6, pady=3)
        if "hyperx" in dev["name"].lower():
            level = self.battery()
            if level is not None:
                tk.Label(header, text=f"🔋 {level}%", bg=theme.PANEL,
                         fg=battery_mod.color(level, theme),
                         font=("Segoe UI Semibold", 10)).pack(side="left", pady=3)

        mute_btn = tk.Label(header, text="🔇" if epv.GetMute() else "🔊",
                            bg=theme.PANEL, fg=theme.TEXT if epv.GetMute() else theme.DIM,
                            cursor="hand2", font=("Segoe UI", 10))
        mute_btn.pack(side="right", padx=6)

        def toggle_mute(_e, epv=epv, btn=mute_btn):
            muted = not epv.GetMute()
            epv.SetMute(muted, None)
            btn.config(text="🔇" if muted else "🔊",
                       fg=theme.TEXT if muted else theme.DIM)
        mute_btn.bind("<Button-1>", toggle_mute)

        body = tk.Frame(self.frame, bg=theme.PANEL)
        body.pack(fill="x", padx=8)
        master = self._slider(
            body, epv.GetMasterVolumeLevelScalar() * 100,
            lambda v, epv=epv: epv.SetMasterVolumeLevelScalar(v, None),
            bg=theme.PANEL,
        )
        master.pack(fill="x", padx=6, pady=(2, 6))
        return epv

    def _show(self):
        self._refs.clear()
        for child in self.frame.winfo_children():
            child.destroy()

        try:
            devices = audio.list_devices(audio.RENDER, audio.STATE_ACTIVE)
        except Exception:
            log.exception("mixer: device enumeration failed")
            return
        default_id, _ = audio.get_default(audio.RENDER)

        for dev in devices:
            is_default = dev["id"] == default_id
            try:
                epv = self._device_section(dev, is_default)
                sessions = self._sessions(dev["id"])
            except comtypes.COMError:
                continue
            self._refs.append((epv, sessions))

            for name, exe, simples in sessions:
                srow = tk.Frame(self.frame, bg=theme.BG)
                srow.pack(fill="x", padx=16)

                base = self._app_image(name, exe)
                dim = base.copy()
                dim.putalpha(dim.split()[3].point(lambda a: a // 4))
                normal_ph = ImageTk.PhotoImage(base)
                dim_ph = ImageTk.PhotoImage(dim)
                self._refs.append((normal_ph, dim_ph))

                muted = bool(simples[0].GetMute())
                icon_lbl = tk.Label(srow, image=dim_ph if muted else normal_ph,
                                    bg=theme.BG, cursor="hand2")
                icon_lbl.pack(side="left", padx=(0, 8), pady=2)
                self._tooltip(icon_lbl, f"{name} — click to mute/unmute")

                def toggle_app_mute(_e, group=simples, lbl=icon_lbl,
                                    on=normal_ph, off=dim_ph):
                    m = not bool(group[0].GetMute())
                    for s in group:
                        s.SetMute(m, None)
                    lbl.config(image=off if m else on)
                icon_lbl.bind("<Button-1>", toggle_app_mute)

                def set_group(v, group=simples):
                    for s in group:
                        s.SetMasterVolume(v, None)

                slider = self._slider(
                    srow, simples[0].GetMasterVolume() * 100, set_group,
                    bg=theme.BG,
                )
                slider.pack(side="left", fill="x", expand=True, pady=1)

        # microphones — master + mute only, no app sessions
        default_in, _ = audio.get_default(audio.CAPTURE)
        for dev in audio.list_devices(audio.CAPTURE, audio.STATE_ACTIVE):
            try:
                epv = self._device_section(dev, dev["id"] == default_in, prefix="🎤 ")
            except comtypes.COMError:
                continue
            self._refs.append((epv,))

        tk.Frame(self.frame, bg=theme.BG, height=8).pack()

        self.root.update_idletasks()
        w = max(WIDTH, self.frame.winfo_reqwidth())
        h = self.frame.winfo_reqheight() + 2
        px, py = self.root.winfo_pointerx(), self.root.winfo_pointery()
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        x = min(max(px - w // 2, 8), sw - w - 8)
        y = max(py - h - 12, 8)
        self.root.geometry(f"{w}x{h}+{x}+{y}")
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()
