"""Mr. Mic — one hotkey (or headset power) switches Windows default output
AND input between the HyperX headset and the laptop speakers/mic.

Run:  pythonw main.py   (or run-mrmic.bat)
"""

import logging
import os
import subprocess
import sys
import threading

import pystray
from pystray import Menu, MenuItem as Item

import audio
import battery
import chime
import config
import hotkeys
import mixer
import tray

log = logging.getLogger("mrmic")

STARTUP_DIR = os.path.join(
    os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs\Startup"
)
SHORTCUT = os.path.join(STARTUP_DIR, "Mr Mic.lnk")


class MrMic:
    def __init__(self):
        self.cfg = config.load()
        self.icon = None
        self._stop = threading.Event()
        self.battery = None
        self._battery_warned = False
        self.mixer = None

    def alias(self, name):
        if not name:
            return "?"
        for needle, short in self.cfg.get("aliases", {}).items():
            if needle.lower() in name.lower():
                return short
        return name if len(name) <= 28 else name[:26] + "…"

    # -- profiles ----------------------------------------------------------

    def _resolve(self, profile, flow):
        prof = self.cfg["profiles"][profile]
        key = "output" if flow == audio.RENDER else "input"
        return audio.find_device(flow, prof.get(f"{key}_match"), prof.get(f"{key}_id"))

    def current_profile(self):
        default_id, _ = audio.get_default(audio.RENDER)
        for name in ("headset", "laptop"):
            dev = self._resolve(name, audio.RENDER)
            if dev and dev["id"] == default_id:
                return name
        return None

    def set_profile(self, name, source="manual"):
        out_dev = self._resolve(name, audio.RENDER)
        in_dev = self._resolve(name, audio.CAPTURE)
        for dev in (out_dev, in_dev):
            if dev:
                audio.set_default(dev["id"])
        label = "🎧 Headset" if name == "headset" else "🔊 Laptop"
        missing = [w for w, d in (("output", out_dev), ("input", in_dev)) if not d]
        log.info("switched to %s (%s)%s", name, source,
                 f" — missing {'/'.join(missing)}" if missing else "")
        self._refresh_icon()
        if self.cfg.get("chime"):
            try:
                chime.play(name)
            except Exception:
                log.exception("chime failed")
        if missing:
            self._notify(f"{label} — {'/'.join(missing)} not found!")
        elif self.cfg.get("notifications"):
            self._notify(label)

    def toggle(self, *_):
        current = self.current_profile()
        self.set_profile("laptop" if current == "headset" else "headset")

    def set_device(self, flow, dev):
        audio.set_default(dev["id"])
        log.info("set %s -> %s", audio.FLOW_NAMES[flow], dev["name"])
        self._refresh_icon()
        if self.cfg.get("notifications"):
            self._notify(f"{audio.FLOW_NAMES[flow].capitalize()}: {dev['name']}")

    # -- headset watch (battery + auto-detect) -----------------------------

    def headset_watch_loop(self):
        """One loop drives both: battery display and auto profile switching.
        The dongle only answers the battery request while the headset is
        powered on, so a battery reading doubles as an on/off signal —
        more reliable than Windows endpoint states, which this dongle
        never changes. Two misses in a row = headset off (debounce)."""
        headset_on = None  # unknown until the first solid reading
        misses = 0
        while not self._stop.is_set():
            try:
                level = battery.read_battery()
                if level is not None:
                    misses = 0
                    now_on = True
                else:
                    misses += 1
                    now_on = False if misses >= 2 else headset_on
                if level != self.battery:
                    self.battery = level
                    self._refresh_icon()
                warn_at = self.cfg.get("battery_warn", 20)
                if level is not None and level <= warn_at and not self._battery_warned:
                    self._battery_warned = True
                    self._notify(f"🔋 Headset battery low: {level}%")
                elif level is not None and level > warn_at:
                    self._battery_warned = False
                if (self.cfg.get("autodetect") and now_on is not None
                        and headset_on is not None and now_on != headset_on):
                    log.info("headset power: %s (battery signal)", "ON" if now_on else "OFF")
                    self.set_profile("headset" if now_on else "laptop", source="auto")
                if now_on is not None:
                    headset_on = now_on
            except Exception:
                log.exception("headset watch failed")
            self._stop.wait(self.cfg.get("poll_seconds", 2))

    def battery_text(self, item=None):
        if self.battery is None:
            return "Battery: — (headset off?)"
        return f"Battery: {self.battery}%"

    # -- tray --------------------------------------------------------------

    def _notify(self, message):
        try:
            self.icon.notify(message, "Mr. Mic")
        except Exception:
            pass

    def _refresh_icon(self):
        if not self.icon:
            return
        profile = self.current_profile()
        _, out_name = audio.get_default(audio.RENDER)
        _, in_name = audio.get_default(audio.CAPTURE)
        self.icon.icon = tray.icon_for(profile)
        batt = f" · 🔋 {self.battery}%" if self.battery is not None else ""
        self.icon.title = f"Speaker: {self.alias(out_name)} · Mic: {self.alias(in_name)}{batt}"

    def _device_menu(self, flow):
        def items():
            def entry(dev):
                def on_click(icon, item):
                    self.set_device(flow, dev)

                def is_checked(item):
                    return audio.get_default(flow)[0] == dev["id"]

                return Item(self.alias(dev["name"]), on_click, checked=is_checked, radio=True)
            return [entry(d) for d in audio.list_devices(flow, audio.STATE_ACTIVE)]
        return Menu(items)

    def _menu(self):
        return Menu(
            Item("Toggle  🎧 ⇄ 🔊", self.toggle, default=True),
            Menu.SEPARATOR,
            Item("🎧 Headset", lambda: self.set_profile("headset")),
            Item("🔊 Laptop", lambda: self.set_profile("laptop")),
            Item(self.battery_text, None, enabled=False),
            Item("Mixer (middle-click)", lambda: self.mixer.show()),
            Item("Output device", self._device_menu(audio.RENDER)),
            Item("Input device", self._device_menu(audio.CAPTURE)),
            Menu.SEPARATOR,
            Item("Auto-detect headset power", self.toggle_autodetect,
                 checked=lambda item: bool(self.cfg.get("autodetect"))),
            Item("Start with Windows", self.toggle_autostart,
                 checked=lambda item: os.path.exists(SHORTCUT)),
            Menu.SEPARATOR,
            Item("📖 Guide", lambda: os.startfile(
                os.path.join(config.APP_DIR, "mrmic-guide.html"))),
            Item("Edit settings", lambda: os.startfile(config.SETTINGS_PATH)),
            Item("Reload settings", self.reload),
            Item("Exit", self.quit),
        )

    # -- menu actions ------------------------------------------------------

    def toggle_autodetect(self, *_):
        self.cfg["autodetect"] = not self.cfg.get("autodetect")
        config.save(self.cfg)

    def toggle_autostart(self, *_):
        if os.path.exists(SHORTCUT):
            os.remove(SHORTCUT)
            log.info("autostart disabled")
        else:
            if getattr(sys, "frozen", False):
                target, args = sys.executable, ""
            else:
                target = sys.executable.replace("python.exe", "pythonw.exe")
                args = f'\"{os.path.join(config.APP_DIR, "main.py")}\"'
            ps = (
                "$ws = New-Object -ComObject WScript.Shell; "
                f"$s = $ws.CreateShortcut('{SHORTCUT}'); "
                f"$s.TargetPath = '{target}'; "
                f"$s.Arguments = '{args}'; "
                f"$s.WorkingDirectory = '{config.APP_DIR}'; "
                "$s.Save()"
            )
            subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps],
                creationflags=subprocess.CREATE_NO_WINDOW, check=True,
            )
            log.info("autostart enabled")

    def bind_hotkey(self):
        combo = self.cfg.get("hotkey", "ctrl+alt+h")
        try:
            hotkeys.bind(combo, self.toggle)
            log.info("hotkey bound: %s", combo)
        except ValueError:
            log.exception("bad hotkey %r", combo)
            self._notify(f"Bad hotkey '{combo}' — check settings.json")

    def reload(self, *_):
        self.cfg = config.load()
        self.bind_hotkey()
        self._refresh_icon()
        self._notify("Settings reloaded")
        log.info("settings reloaded")

    def quit(self, *_):
        self._stop.set()
        hotkeys.unbind()
        self.icon.stop()

    # -- lifecycle ---------------------------------------------------------

    def _hook_middle_click(self):
        """pystray only maps left/right clicks; route middle-click to the mixer."""
        from pystray._util import win32 as pw32
        WM_MBUTTONUP = 0x0208
        original = self.icon._on_notify

        def on_notify(wparam, lparam):
            if lparam == WM_MBUTTONUP:
                self.mixer.show()
            else:
                original(wparam, lparam)

        self.icon._message_handlers[pw32.WM_NOTIFY] = on_notify

    def run(self):
        self.icon = pystray.Icon(
            "mrmic", tray.icon_for(self.current_profile()), "Mr. Mic", self._menu()
        )
        self.mixer = mixer.Mixer(self.alias)
        try:
            self._hook_middle_click()
        except Exception:
            log.exception("middle-click hook failed — use the menu's Mixer item")
        self.bind_hotkey()
        threading.Thread(target=self.headset_watch_loop, daemon=True).start()
        self._refresh_icon_soon()
        self.icon.run()

    def _refresh_icon_soon(self):
        # icon.run() blocks; refresh tooltip shortly after the icon exists
        threading.Timer(1.0, self._refresh_icon).start()


def enable_dark_menus():
    """Win32 popup menus are light unless the process opts into dark mode via
    undocumented uxtheme ordinals 135 (SetPreferredAppMode, 2 = ForceDark)
    and 136 (FlushMenuThemes). Best effort — harmless if Windows changes it."""
    try:
        import ctypes
        uxtheme = ctypes.WinDLL("uxtheme")
        uxtheme[135](2)
        uxtheme[136]()
    except Exception:
        log.info("dark menu opt-in unavailable")


def already_running():
    """Named mutex — a second instance would double-fire the hotkey."""
    import ctypes
    ctypes.windll.kernel32.CreateMutexW(None, False, "MrMic_SingleInstance")
    return ctypes.windll.kernel32.GetLastError() == 183  # ERROR_ALREADY_EXISTS


def main():
    logging.basicConfig(
        filename=config.LOG_PATH, level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    logging.getLogger().addHandler(logging.StreamHandler())
    if already_running():
        log.info("Mr. Mic is already running — exiting")
        return
    log.info("Mr. Mic starting")
    try:
        # never compete with DCS/VR for CPU time
        import psutil
        psutil.Process().nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
    except Exception:
        log.info("could not lower process priority")
    enable_dark_menus()
    MrMic().run()


if __name__ == "__main__":
    main()
