"""Mr. Mic — one hotkey (or just turning a device on) switches the Windows
default output AND input to whichever headset, earphones or speaker you want.

Run:  pythonw main.py   (or run-mrmic.bat)
"""

import logging
import os
import subprocess
import sys
import threading
import time

import pystray
from pystray import Menu, MenuItem as Item

import audio
import battery
import chime
import config
import hotkeys
import mixer
import settings_ui
import tray
import ui

log = logging.getLogger("mrmic")

STARTUP_DIR = os.path.join(
    os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs\Startup"
)
SHORTCUT = os.path.join(STARTUP_DIR, "Mr Mic.lnk")

# How many polls to wait for the second half of a device (a jack's microphone
# comes up a beat after its speakers) before saying it isn't there.
PENDING_TRIES = 6


def _double_click_seconds():
    """Windows' own double-click interval — how long a single tray click has to
    be held back to know it wasn't the first half of a double click."""
    try:
        import ctypes
        return min(max(ctypes.windll.user32.GetDoubleClickTime(), 200), 600) / 1000
    except Exception:
        return 0.5


DOUBLE_CLICK_S = _double_click_seconds()


class MrMic:
    def __init__(self):
        self.cfg = config.load()
        self.icon = None
        self._stop = threading.Event()
        self.battery = None
        self._battery_warned = False
        self._battery_misses = 0
        self._battery_on = False
        self._available = {}    # device key -> was it connected last poll
        self._last_active = None  # key of the device we were last knowingly on
        self._pending = None      # device still waiting for its other half
        self._pending_missing = []
        self._pending_tries = 0
        self._muted = False     # last known output mute, for the tray icon
        self._click_timer = None
        self._dblclick_at = 0.0
        self.mixer = None
        self.settings = None

    def alias(self, name):
        if not name:
            return "?"
        for needle, short in self.cfg.get("aliases", {}).items():
            if needle.lower() in name.lower():
                return short
        return name if len(name) <= 28 else name[:26] + "…"

    # -- devices -----------------------------------------------------------

    def devices(self):
        """Enabled devices, in priority order (first = highest)."""
        return [d for d in self.cfg.get("devices", []) if d.get("enabled", True)]

    def resolve(self, device, flow, endpoints=None):
        """The Windows endpoint this device wants for output or input, or None
        if it isn't connected (or the device deliberately leaves it alone).
        Pass `endpoints` (from audio.list_devices) when checking several
        devices at once — otherwise every check re-enumerates."""
        key = "output" if flow == audio.RENDER else "input"
        match = device.get(f"{key}_match") or ""
        device_id = device.get(f"{key}_id")
        if not match and not device_id:
            return None
        if endpoints is None:
            return audio.find_device(flow, match, device_id)
        return audio.match_device(endpoints, match, device_id)

    def active_device(self, endpoints=None):
        """Which configured device the current default output belongs to."""
        default_id, _ = audio.get_default(audio.RENDER)
        if not default_id:
            return None
        if endpoints is None:
            endpoints = audio.list_devices(audio.RENDER, audio.STATE_ACTIVE)
        for device in self.devices():
            out = self.resolve(device, audio.RENDER, endpoints)
            if out and out["id"] == default_id:
                return device
        return None

    def activate(self, device, source="manual"):
        out = self.resolve(device, audio.RENDER)
        mic = self.resolve(device, audio.CAPTURE)
        for endpoint in (out, mic):
            if endpoint:
                audio.set_default(endpoint["id"])
        self._remember_ids(device, out, mic)
        self._last_active = device["key"]

        wants_mic = bool(device.get("input_match") or device.get("input_id"))
        missing = [name for name, endpoint, wanted in
                   (("speakers", out, True), ("microphone", mic, wants_mic))
                   if wanted and not endpoint]
        log.info("switched to %s (%s)%s", device["label"], source,
                 f" — no {' or '.join(missing)} yet" if missing else "")
        self._refresh_icon()
        if self.cfg.get("chime"):
            try:
                chime.play(device.get("icon", "speaker"),
                           self.cfg.get("chime_style", chime.DEFAULT_STYLE))
            except Exception:
                log.exception("chime failed")
        # Half a device is normal for a second or two: Windows brings a jack's
        # microphone up after its speakers. Don't cry about it yet — wait for
        # the other half, and only complain if it never turns up.
        self._pending = device["key"] if missing else None
        self._pending_missing = missing
        self._pending_tries = 0
        if not missing and self.cfg.get("notifications"):
            self._notify(device["label"])

    def _finish_pending(self, endpoints):
        """The speakers of a device landed but its mic hadn't appeared yet (or
        vice versa). Re-apply the missing half as soon as Windows offers it,
        quietly — no second chime. Gives up after a few polls so it can never
        fight a device you pick by hand later."""
        if not self._pending:
            return
        device = next((d for d in self.devices() if d["key"] == self._pending), None)
        current = self.active_device(endpoints)
        self._pending_tries += 1
        if device is None or current is None or current["key"] != self._pending:
            self._pending = None  # something else took over; let it be
            return
        if self._pending_tries > PENDING_TRIES:
            log.info("%s: %s never showed up", device["label"],
                     " or ".join(self._pending_missing))
            self._notify(f"{device['label']} — "
                         f"{' or '.join(self._pending_missing)} not found!")
            self._pending = None
            return
        out = self.resolve(device, audio.RENDER, endpoints)
        mic = self.resolve(device, audio.CAPTURE)
        wants_mic = bool(device.get("input_match") or device.get("input_id"))
        if not out or (wants_mic and not mic):
            return  # still only half there — look again next poll
        for endpoint in (out, mic):
            if endpoint:
                audio.set_default(endpoint["id"])
        self._remember_ids(device, out, mic)
        log.info("%s: %s caught up", device["label"],
                 " and ".join(self._pending_missing))
        self._pending = None
        self._refresh_icon()

    def _remember_ids(self, device, out, mic):
        """Endpoint ids change when a dongle lands on a new USB port. Whenever
        a name match finds something, save the id it landed on."""
        changed = False
        for endpoint, key in ((out, "output_id"), (mic, "input_id")):
            if endpoint and device.get(key) != endpoint["id"]:
                device[key] = endpoint["id"]
                changed = True
        if changed:
            try:
                config.save(self.cfg)
            except OSError:
                log.exception("could not save refreshed endpoint ids")

    def cycle(self, *_):
        """Hotkey / tray default action: step to the next connected device.
        With two devices set up this is exactly the old toggle."""
        usable = [d for d in self.devices() if self.resolve(d, audio.RENDER)]
        if not usable:
            self._notify("No configured device is connected")
            return
        current = self.active_device()
        keys = [d["key"] for d in usable]
        if current is None or current["key"] not in keys:
            nxt = usable[0]
        else:
            nxt = usable[(keys.index(current["key"]) + 1) % len(usable)]
        self.activate(nxt)

    def set_device(self, flow, dev):
        """Menu: pick one raw Windows endpoint, without touching the other side."""
        audio.set_default(dev["id"])
        log.info("set %s -> %s", audio.FLOW_NAMES[flow], dev["name"])
        self._refresh_icon()
        if self.cfg.get("notifications"):
            self._notify(f"{audio.FLOW_NAMES[flow].capitalize()}: {dev['name']}")

    # -- mute --------------------------------------------------------------

    def toggle_output_mute(self, *_):
        state = audio.toggle_mute(audio.RENDER)
        if state is None:
            self._notify("Nothing to mute — no default speakers")
            return
        self._muted = state
        log.info("output %s", "muted" if state else "unmuted")
        self._refresh_icon()

    def toggle_mic_mute(self, *_):
        state = audio.toggle_mute(audio.CAPTURE)
        if state is None:
            self._notify("Nothing to mute — no default microphone")
            return
        log.info("microphone %s", "muted" if state else "unmuted")
        if self.cfg.get("notifications"):
            self._notify("🎤 Mic muted" if state else "🎤 Mic live")

    # -- watch loop (battery + auto switching) -----------------------------

    def _battery_wanted(self):
        return any(d.get("detect") == "battery" for d in self.devices())

    def _poll_battery(self):
        """Read the HyperX dongle. The reply doubles as the headset's on/off
        signal — this dongle never changes its Windows endpoint state when the
        headset powers down. Two misses in a row = off (debounce)."""
        level = battery.read_battery()
        if level is not None:
            self._battery_misses = 0
            on = True
        else:
            self._battery_misses += 1
            on = self._battery_on if self._battery_misses < 2 else False
        if level != self.battery:
            self.battery = level
            self._refresh_icon()
        warn_at = self.cfg.get("battery_warn", 20)
        if level is not None and level <= warn_at and not self._battery_warned:
            self._battery_warned = True
            self._notify(f"🔋 Headset battery low: {level}%")
        elif level is not None and level > warn_at:
            self._battery_warned = False
        self._battery_on = bool(on)
        return self._battery_on

    def _availability(self, endpoints):
        """key -> is this device connected right now."""
        battery_on = self._poll_battery() if self._battery_wanted() else False
        state = {}
        for device in self.devices():
            if device.get("detect") == "battery":
                state[device["key"]] = battery_on
            else:
                state[device["key"]] = (
                    self.resolve(device, audio.RENDER, endpoints) is not None)
        return state

    def _auto_switch(self, now, endpoints):
        """Turning something on is a deliberate act, so a device that just
        appeared wins — whatever its priority. Priority only decides where to
        land when the device you were using disappears."""
        previous = self._available
        current = self.active_device(endpoints)
        # Read this before updating it: on the tick where a jack is pulled,
        # Windows has usually already moved the default, so `current` is the
        # fallback and only the old value still knows what we were on.
        was_on = self._last_active
        if current is not None:
            self._last_active = current["key"]

        for device in self.devices():
            key = device["key"]
            if not (now.get(key) and not previous.get(key)):
                continue
            log.info("%s is connected", device["label"])
            if not device.get("auto", True):
                continue
            # Switch even when Windows has already moved the output here by
            # itself. It moves Console and Multimedia and routinely leaves
            # Communications — and the microphone — behind; setting all six is
            # the entire point of the app. It also means you always get the
            # chime, so a switch never happens silently.
            self.activate(device, source="auto")
            return

        vanished = [d for d in self.devices()
                    if previous.get(d["key"]) and not now.get(d["key"])]
        for device in vanished:
            log.info("%s is gone", device["label"])
        if not vanished:
            return
        # Some other device went away and we weren't using it — nothing to do.
        lost_ours = any(d["key"] == was_on for d in vanished)
        if not lost_ours and current is not None:
            return

        # Windows does move the default by itself when a jack is pulled, but
        # only the output: the microphone and the Communications roles are
        # routinely left on the device that just left the building. Claim the
        # fallback properly rather than trusting it — and chime, so the switch
        # is never silent.
        for device in self.devices():
            if device.get("auto", True) and now.get(device["key"]):
                self.activate(device, source="auto")
                return

    def watch_loop(self):
        first = True
        while not self._stop.is_set():
            try:
                endpoints = audio.list_devices(audio.RENDER, audio.STATE_ACTIVE)
                now = self._availability(endpoints)
                if self.cfg.get("autodetect") and not first:
                    self._auto_switch(now, endpoints)
                self._available = now
                first = False
                self._finish_pending(endpoints)
                muted = bool(audio.get_mute(audio.RENDER))
                if muted != self._muted:
                    self._muted = muted
                    self._refresh_icon()
            except Exception:
                log.exception("device watch failed")
            self._stop.wait(self.cfg.get("poll_seconds", 2))

    def battery_text(self, item=None):
        if self.battery is None:
            return f"{battery.dot(None)} Battery: — (headset off?)"
        return f"{battery.dot(self.battery)} Battery: {self.battery}%"

    # -- tray --------------------------------------------------------------

    def _notify(self, message):
        try:
            self.icon.notify(message, "Mr. Mic")
        except Exception:
            pass

    def _refresh_icon(self):
        if not self.icon:
            return
        device = self.active_device()
        _, out_name = audio.get_default(audio.RENDER)
        _, in_name = audio.get_default(audio.CAPTURE)
        self.icon.icon = tray.icon_for(device["icon"] if device else None, self._muted)
        batt = f" · 🔋 {self.battery}%" if self.battery is not None else ""
        mute = " · muted" if self._muted else ""
        self.icon.title = (
            f"Speaker: {self.alias(out_name)} · Mic: {self.alias(in_name)}{batt}{mute}"
        )

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

    def _device_row(self, device):
        """pystray inspects the callback signature and rejects anything with
        more than (icon, item) — so bind `device` by closure, not by default
        argument."""
        connected = self._available.get(device["key"], True)

        def on_click(icon, item):
            self.activate(device)

        def is_checked(item):
            current = self.active_device()
            return current is not None and current["key"] == device["key"]

        suffix = "" if connected else "  (off)"
        return Item(f"{device['label']}{suffix}", on_click,
                    checked=is_checked, radio=True, enabled=connected)

    def _device_items(self):
        """One radio row per configured device, greyed out when unplugged."""
        return [self._device_row(d) for d in self.devices()]

    def _menu_items(self):
        items = []
        if self._battery_wanted():
            items.append(Item(self.battery_text, None, enabled=False))
        items += [
            Item("Switch device  ⇄", self.cycle, default=True),
            Menu.SEPARATOR,
        ]
        items += self._device_items()
        items += [
            Menu.SEPARATOR,
            Item("🔇 Mute speakers", self.toggle_output_mute,
                 checked=lambda item: bool(audio.get_mute(audio.RENDER))),
            Item("🎤 Mute microphone", self.toggle_mic_mute,
                 checked=lambda item: bool(audio.get_mute(audio.CAPTURE))),
            Item("Mixer (middle-click)", lambda: self.mixer.show()),
            Item("All Windows devices", Menu(
                Item("Output", self._device_menu(audio.RENDER)),
                Item("Input", self._device_menu(audio.CAPTURE)),
            )),
            Menu.SEPARATOR,
            Item("Switch automatically", self.toggle_autodetect,
                 checked=lambda item: bool(self.cfg.get("autodetect"))),
            Item("Start with Windows", self.toggle_autostart,
                 checked=lambda item: os.path.exists(SHORTCUT)),
            Menu.SEPARATOR,
            Item("⚙ Settings…", lambda: self.settings.show()),
            Item("📖 Guide", lambda: os.startfile(
                os.path.join(config.APP_DIR, "mrmic-guide.html"))),
            Item("Reload settings", self.reload),
            Item("Exit", self.quit),
        ]
        return items

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

    def bind_hotkeys(self):
        for name, cfg_key, action in (
            ("switch", "hotkey", self.cycle),
            ("mute", "mute_hotkey", self.toggle_output_mute),
            ("mic_mute", "mic_mute_hotkey", self.toggle_mic_mute),
        ):
            combo = self.cfg.get(cfg_key, "")
            try:
                hotkeys.bind(name, combo, action)
                if combo:
                    log.info("hotkey bound: %s = %s", name, combo)
            except (ValueError, KeyError):
                log.exception("bad hotkey %r for %s", combo, name)
                self._notify(f"Bad hotkey '{combo}' — fix it in Settings")

    def reload(self, *_):
        self.cfg = config.load()
        self.bind_hotkeys()
        self._available = {}
        self._refresh_icon()
        self._notify("Settings reloaded")
        log.info("settings reloaded")

    def quit(self, *_):
        self._stop.set()
        if self._click_timer is not None:
            self._click_timer.cancel()
        hotkeys.unbind_all()
        self.icon.stop()

    # -- lifecycle ---------------------------------------------------------

    def _hook_clicks(self):
        """pystray only maps a plain left and right click. Take the tray
        messages over so middle-click can open the mixer and double-click can
        mute.

        Windows sends a double click as UP, DBLCLK, UP — so the first click's
        action always fires before anyone knows a double click was coming, and
        the trailing UP would fire it a second time. Hence: hold the single
        click for the double-click interval, and ignore the UP that trails a
        DBLCLK."""
        from pystray._util import win32 as pw32
        WM_LBUTTONUP, WM_LBUTTONDBLCLK, WM_MBUTTONUP = 0x0202, 0x0203, 0x0208
        original = self.icon._on_notify

        def on_notify(wparam, lparam):
            if lparam == WM_MBUTTONUP:
                self.mixer.show()
            elif lparam == WM_LBUTTONUP:
                self._left_click()
            elif lparam == WM_LBUTTONDBLCLK:
                self._left_double_click()
            else:
                original(wparam, lparam)

        self.icon._message_handlers[pw32.WM_NOTIFY] = on_notify

    def _double_click_action(self):
        action = self.cfg.get("tray_double_click", "mute_mic")
        return action if action in ("mute_mic", "mute_speakers") else None

    def _left_click(self):
        if time.monotonic() - self._dblclick_at < 0.4:
            return  # the trailing button-up of a double click
        if self._double_click_action() is None:
            self.cycle()  # nothing to wait for — switch immediately
            return
        if self._click_timer is not None:
            self._click_timer.cancel()
        self._click_timer = threading.Timer(DOUBLE_CLICK_S, self._delayed_cycle)
        self._click_timer.daemon = True
        self._click_timer.start()

    def _delayed_cycle(self):
        try:
            self.cycle()
        finally:
            audio.com_release_thread()  # this thread is about to die

    def _left_double_click(self):
        self._dblclick_at = time.monotonic()
        if self._click_timer is not None:
            self._click_timer.cancel()
            self._click_timer = None
        if self._double_click_action() == "mute_speakers":
            self.toggle_output_mute()
        else:
            self.toggle_mic_mute()

    def run(self):
        current = self.active_device()
        self.icon = pystray.Icon(
            "mrmic", tray.icon_for(current["icon"] if current else None), "Mr. Mic",
            Menu(self._menu_items),
        )
        ui.start()
        self.mixer = mixer.Mixer(self.alias, battery=lambda: self.battery)
        self.settings = settings_ui.SettingsWindow(self)
        try:
            self._hook_clicks()
        except Exception:
            log.exception("tray click hook failed — use the menu instead")
        self.bind_hotkeys()
        threading.Thread(target=self.watch_loop, daemon=True).start()
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
        filename=config.LOG_PATH, level=logging.INFO, encoding="utf-8",
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
